-- ---------------------------------------------------------------------------
-- 023_ticket08_scheduler.sql   (ticket 08, re-resolution)
--
-- Ticket 32 executed ticket 08's answer and found that the ranking pass does
-- not run: `novelty_for`, `cost_for` and `confidence_for` were named and never
-- written, and three of their inputs could not be written down at all. Four
-- resolved tickets have since voided other parts of the answer. This migration
-- is the executable scheduler that survives all of it.
--
-- What it assumes underneath it, in order:
--   001..018  ticket 06/07/32/35/27      (this branch's base, 0879189)
--   019       ticket 34 role -> kind     (a4bcfa9, never vendored)
--   020       ticket 12 state access     (2f236f3, RLS + task_slate)
--   021       ticket 26 scope policy     (2aa206c, entities.in_scope projected)
-- 022 is ticket 13's and nothing here depends on it.
--
-- The five things this migration is for:
--
--   1. The three unspecifiable inputs (32/D12) become specifiable.
--      |vocabulary| is ticket 27's EIGHT FAMILIES, not the 33 leaves -- 27
--      measured family coverage as 2.6x more discriminating (range 0.625 vs
--      0.24). recon novelty's numerator routes through `hypotheses`, because
--      `observations` has no `property_class` and 27 says not to add one. The
--      analyze denominator is the observation-kind vocabulary 27 built. `N` in
--      "the last N runs" becomes `scheduler_weights.history_window_n`. The
--      skills registry the confidence gate reads is created here with exactly
--      the two fields ticket 08 said it needs.
--
--   2. The lane caps are the roster's (34). `scheduler_lanes.max_slots` is
--      gone; capacity is `roles.max_concurrent` through `lane_capacity`, and
--      the cross-lane cap of 3 is `scheduler_weights.max_concurrent_subagents`.
--      This migration adds the piece 34 could not: a lane row with a non-NULL
--      `program_id` was UNREACHABLE, because the claim query joined
--      `program_id IS NOT DISTINCT FROM NULL`. Ticket 35 left that question
--      open and it is answered here -- `effective_lane_capacity` resolves the
--      override, and `check_scheduler_closure()` fails if it stops doing so.
--
--   3. The lane cap is held by `pg_advisory_xact_lock` (32/D15), reversing
--      ticket 08's "no lock is needed here".
--
--   4. The scheduler never takes a program as an argument. `rk2_program()` is
--      the only source (12), so the program cannot arrive from model output,
--      and RLS is not something the scheduler works around.
--
--   5. The ranking pass has no `now()` in it. Decision 12 required that and
--      then ticket 32's stand-in put `now()` in the identity-lease gate anyway.
--      A live lease is `released_at IS NULL`; expiry is the sweep's job, which
--      is where the clock belongs.
-- ---------------------------------------------------------------------------

SET client_min_messages = warning;


-- ===========================================================================
-- 1. The tunables that were missing, and the ones that were wrong
-- ===========================================================================

ALTER TABLE scheduler_weights
    -- 32/D12: "the last N completed agent_runs" never said what N is.
    ADD COLUMN history_window_n smallint NOT NULL DEFAULT 20
        CHECK (history_window_n >= 1),
    -- How long a slate stands before the runtime must recompute it. Ticket 08
    -- gave slate entries "an expiry" and never a number.
    ADD COLUMN slate_ttl interval NOT NULL DEFAULT interval '5 minutes',
    -- Decision 4 of ticket 08's round 5: two recomputes per wake, then sleep.
    ADD COLUMN max_recomputes_per_wake smallint NOT NULL DEFAULT 2
        CHECK (max_recomputes_per_wake >= 1);

-- `task_slate.ordinal` is `CHECK (ordinal BETWEEN 1 AND 5)` in migration 020.
-- `slate_size` is a number in a different table in a different ticket. Nothing
-- tied them together, so raising slate_size to 6 would have produced a check
-- violation at the first pass instead of a bigger slate.
ALTER TABLE scheduler_weights
    ADD CONSTRAINT scheduler_weights_slate_fits_task_slate
    CHECK (slate_size BETWEEN 1 AND 5);

COMMENT ON CONSTRAINT scheduler_weights_slate_fits_task_slate ON scheduler_weights IS
  'Ticket 12''s task_slate.ordinal is CHECK (1..5). This is the same number, and the two tables belong to different tickets, so it is written down as a constraint rather than as an agreement.';

-- Decision 9: two budget envelopes, program and agent run. The agent-run
-- envelope is `cost_reference_tokens` and has existed since 012. The program
-- envelope had no column anywhere.
ALTER TABLE programs
    ADD COLUMN token_budget bigint CHECK (token_budget IS NULL OR token_budget > 0);

COMMENT ON COLUMN programs.token_budget IS
  'The program envelope of ticket 08 decision 9, in tokens (Q17: rate-limit budget, not dollars, is the scarce resource). NULL means unbounded, which is what a program opened without one gets -- deliberately not a default number, because a made-up ceiling that silently stops a multi-hour run is worse than none.';

CREATE VIEW program_budget AS
    SELECT p.id AS program_id,
           p.token_budget,
           coalesce(sum(a.input_tokens + a.output_tokens), 0)::bigint AS tokens_spent,
           CASE WHEN p.token_budget IS NULL THEN NULL
                ELSE greatest(p.token_budget
                              - coalesce(sum(a.input_tokens + a.output_tokens), 0), 0)
           END::bigint AS tokens_left
      FROM programs p
      LEFT JOIN agent_runs a ON a.program_id = p.id
     GROUP BY p.id, p.token_budget;

COMMENT ON VIEW program_budget IS
  'Spend is summed from agent_runs rather than decremented into a column: a counter and the runs it counts can disagree across an abort, and Q29 says recompute, not restore.';


-- ===========================================================================
-- 2. The skills registry -- exactly the two fields the gate needs
-- ===========================================================================

-- Ticket 08's own hand-off says: "the confidence gate needs exactly two fields
-- from the registry: a stable name and an enabled flag. Nothing else about
-- skill format reaches the scheduler." That is the whole table. Ticket 09/17
-- own everything else about a skill; this is the join column they must keep.
CREATE TABLE skills (
    name        text PRIMARY KEY CHECK (name ~ '^[a-z0-9][a-z0-9_-]{0,63}$'),
    enabled     boolean NOT NULL DEFAULT true,
    description text NOT NULL DEFAULT ''
);

COMMENT ON TABLE skills IS
  'The registry `tasks.required_skills` cites. Global for the same reason `roles` is: a skill is a capability of the harness, not of a target.';

INSERT INTO program_global_tables (table_name, reason) VALUES
    ('skills', 'the skill registry is a property of the harness, like the agent roster; a per-program registry would let one program require a skill another has disabled');

-- Two different failures, deliberately handled in two different places.
--
-- A task naming a skill that does not exist is a TYPO: it is not a runtime
-- state, no wait makes it true, and it must never reach the queue. That is a
-- constraint.
--
-- A task naming a skill that exists and is DISABLED is a runtime state that can
-- change under the task. That is the confidence gate, which scores it 0 and
-- leaves the row alone -- so re-enabling the skill makes the work claimable
-- again without recreating anything.
CREATE FUNCTION tasks_required_skills_exist() RETURNS trigger
LANGUAGE plpgsql AS $fn$
DECLARE missing text;
BEGIN
    SELECT string_agg(s, ', ') INTO missing
      FROM unnest(NEW.required_skills) AS s
     WHERE NOT EXISTS (SELECT 1 FROM skills k WHERE k.name = s);
    IF missing IS NOT NULL THEN
        RAISE EXCEPTION
            'tasks.required_skills names skills that are not registered: %', missing
            USING ERRCODE = 'foreign_key_violation';
    END IF;
    RETURN NEW;
END $fn$;

CREATE TRIGGER tasks_required_skills_registered
    BEFORE INSERT OR UPDATE OF required_skills ON tasks
    FOR EACH ROW EXECUTE FUNCTION tasks_required_skills_exist();

ALTER TABLE tasks ENABLE ALWAYS TRIGGER tasks_required_skills_registered;


-- ===========================================================================
-- 3. The near-match penalty becomes reachable (32/D14)
-- ===========================================================================

-- `hypothesis_near_matches` stored the MATCHED hypothesis and the candidate as
-- free text, so from the hypothesis the candidate became there was no way back
-- to the row -- and the `penalised` action exists for exactly that lookup.
-- Ticket 27 later added `key_collision`, which has no candidate row either.
ALTER TABLE hypothesis_near_matches
    ADD COLUMN candidate_hypothesis_id uuid;

-- Ticket 35 rule 3: a citation between two program-scoped rows carries the
-- program on both sides. `check_program_isolation()` at the end of this file is
-- what proves it was not forgotten -- and it earned its keep here: the first
-- version of this key was ON DELETE CASCADE, and check (d) refused the
-- migration with `cascade_fires_after_noaction hypothesis_near_matches ->
-- hypotheses`. Two keys between the same pair of tables with different delete
-- rules fire in trigger-name order, so the NO ACTION check on
-- `matched_hypothesis_id` would have run before this CASCADE cleared the row
-- and reported a violation that was about to stop being true. NO ACTION also
-- happens to be the honest rule: a near-match row is the record of a dedup
-- decision, and it should block the deletion of a hypothesis it explains rather
-- than quietly disappear with it.
ALTER TABLE hypothesis_near_matches
    ADD CONSTRAINT hypothesis_near_matches_candidate_fk
    FOREIGN KEY (candidate_hypothesis_id, program_id)
    REFERENCES hypotheses (id, program_id) ON DELETE NO ACTION;

-- The action decides whether a candidate row exists at all:
--   suppressed     -- the candidate was refused, so there is no hypothesis
--   key_collision  -- likewise, the unique index refused it
--   penalised      -- the candidate WAS created, and this column is how the
--                     ranking pass finds the penalty that applies to it
ALTER TABLE hypothesis_near_matches
    ADD CONSTRAINT hypothesis_near_matches_candidate_matches_action
    CHECK ((action = 'penalised') = (candidate_hypothesis_id IS NOT NULL));

CREATE INDEX hypothesis_near_matches_candidate_idx
    ON hypothesis_near_matches (candidate_hypothesis_id)
 WHERE action = 'penalised';


-- ===========================================================================
-- 4. Lanes: the per-program override was unreachable
-- ===========================================================================

-- `scheduler_lanes` is the only table in the schema with a nullable
-- `program_id` -- ticket 35 flagged it and left the consequence open. The
-- consequence is a live defect: every claim query written so far joins
-- `l.program_id IS NOT DISTINCT FROM NULL`, so a row inserted for a specific
-- program is never read by anything. A per-program lane override was
-- expressible and inert.
--
-- Resolution is precedence, not exclusion: the program's row if there is one,
-- the default row otherwise. `max_slots` still comes from the roster (34) and
-- is NOT overridable -- concurrency is a property of the agent, and a program
-- may not grant itself more hunters than the roster will spawn. What a program
-- may move is `min_slots`, its entitlement, which is ticket 30's whole subject.
CREATE VIEW effective_lane_capacity AS
    SELECT p.id  AS program_id,
           k.kind,
           m.role,
           l.min_slots,
           r.max_concurrent AS max_slots,
           r.clamp_to_identity_leases,
           l.overridden
      FROM programs p
      CROSS JOIN task_kinds k
      JOIN role_task_kinds m ON m.kind = k.kind
      JOIN roles r           ON r.role = m.role
      CROSS JOIN LATERAL (
          SELECT sl.min_slots, sl.program_id IS NOT NULL AS overridden
            FROM scheduler_lanes sl
           WHERE sl.kind = k.kind
             AND (sl.program_id = p.id OR sl.program_id IS NULL)
           ORDER BY sl.program_id NULLS LAST
           LIMIT 1
      ) l;

COMMENT ON VIEW effective_lane_capacity IS
  'One row per (program, kind). min_slots is the program''s override where one exists and the default otherwise; max_slots is always the roster''s per-role max_concurrent, which no program may raise.';

-- An override may not promise more slots than the roster will staff. The
-- default-lane version of this is check (e) of ticket 34's
-- check_role_kind_mapping(), which reads `lane_capacity` and therefore only
-- ever saw the NULL-program rows.
ALTER TABLE scheduler_lanes
    ADD CONSTRAINT scheduler_lanes_min_slots_bounded
    CHECK (min_slots <= 8);

COMMENT ON CONSTRAINT scheduler_lanes_min_slots_bounded ON scheduler_lanes IS
  'A coarse ceiling so a nonsense entitlement is refused at write time; the exact per-kind bound is check (e) of check_role_kind_mapping(), which needs the join.';

-- What the loop reads: live occupancy against capacity, per lane, per program.
CREATE VIEW scheduler_lane_state AS
    SELECT c.program_id, c.kind, c.role, c.min_slots, c.max_slots, c.overridden,
           coalesce(live.n, 0)                             AS live_slots,
           greatest(c.max_slots - coalesce(live.n, 0), 0)  AS headroom,
           greatest(c.min_slots - coalesce(live.n, 0), 0)  AS deficit
      FROM effective_lane_capacity c
      LEFT JOIN LATERAL (
          SELECT count(*) AS n FROM tasks t
           WHERE t.program_id = c.program_id AND t.kind = c.kind
             AND t.status IN ('claimed','running')
      ) live ON true;


-- ===========================================================================
-- 5. novelty -- a per-kind SQL function over rows, never a model number
-- ===========================================================================

CREATE FUNCTION novelty_for(t tasks) RETURNS numeric
LANGUAGE plpgsql STABLE AS $fn$
DECLARE
    covered   integer;
    total     integer;
    n_ev      integer;
    st        text;
    sim       numeric;
    fired     boolean;
BEGIN
    IF t.kind = 'recon' THEN
        -- Ticket 27, measured: the denominator is the 8 FAMILIES, not the 33
        -- leaves. Family coverage ranged 0.625 across the corpus against 0.24
        -- for leaf coverage, so the leaf denominator makes every recon task
        -- look equally novel forever.
        --
        -- And the numerator routes through `hypotheses`, not `observations`:
        -- 27 executed the schema and found `observations` has no
        -- `property_class` at all, and said explicitly not to add one. A
        -- property class is a claim about what a test IS; an observation is a
        -- fact. What "has this property been looked at on this subject" means
        -- is therefore "has a hypothesis about it been written down".
        SELECT count(DISTINCT pc.family_id) INTO covered
          FROM hypotheses h
          JOIN property_classes pc ON pc.id = h.property_class
         WHERE h.subject_entity_id = t.subject_entity_id
           AND h.superseded_by IS NULL;
        SELECT count(*) INTO total FROM property_class_families;
        RETURN greatest(1.0 - covered::numeric / total, 0);

    ELSIF t.kind = 'analyze' THEN
        -- Same shape over the other vocabulary 27 built. "analysis-kind" is
        -- decidable now: it is a kind a tool run may back, which is exactly
        -- what offline analysis over a content-addressed artifact produces.
        SELECT count(DISTINCT o.kind) INTO covered
          FROM observations o
          JOIN observation_kinds k ON k.id = o.kind
         WHERE o.subject_entity_id = t.subject_entity_id
           AND o.provenance_kind = 'tool_run'
           AND 'tool_run' = ANY (k.allowed_provenance);
        SELECT count(*) INTO total
          FROM observation_kinds WHERE 'tool_run' = ANY (allowed_provenance);
        RETURN greatest(1.0 - covered::numeric / total, 0);

    ELSIF t.kind = 'hunt' THEN
        SELECT h.status INTO st FROM hypotheses h WHERE h.id = t.hypothesis_id;
        SELECT EXISTS (SELECT 1 FROM hypothesis_retest_triggers x
                        WHERE x.hypothesis_id = t.hypothesis_id
                          AND x.fired_at IS NOT NULL) INTO fired;
        IF st IN ('supported','refuted') AND NOT fired THEN
            RETURN 0;
        END IF;
        SELECT count(*) INTO n_ev
          FROM hypothesis_evidence WHERE hypothesis_id = t.hypothesis_id;
        -- 32/D14 is closed: the row is found from the hypothesis the candidate
        -- BECAME, which is what `penalised` always meant and could not express.
        SELECT max(nm.similarity) INTO sim
          FROM hypothesis_near_matches nm
         WHERE nm.candidate_hypothesis_id = t.hypothesis_id
           AND nm.action = 'penalised';
        RETURN (1.0 / (1 + n_ev)) * coalesce(1 - sim, 1);

    ELSIF t.kind = 'validate' THEN
        -- 32/D13 was closed by migration 015: a validate task names its
        -- finding, so this is a lookup rather than a scan of the subject.
        RETURN CASE WHEN EXISTS (
                 SELECT 1 FROM findings f
                  WHERE f.id = t.finding_id
                    AND f.status IN ('validated','reported','rejected'))
               THEN 0 ELSE 1 END;

    ELSIF t.kind = 'report' THEN
        RETURN CASE WHEN EXISTS (
                 SELECT 1 FROM findings f
                  WHERE f.program_id = t.program_id AND f.status = 'validated'
                    AND f.reported_at IS NULL) THEN 1 ELSE 0 END;
    END IF;
    RETURN 0;
END $fn$;


-- ===========================================================================
-- 6. cost -- measured against the run budget, over the roster's window
-- ===========================================================================

CREATE FUNCTION cost_for(t tasks, w scheduler_weights) RETURNS numeric
LANGUAGE plpgsql STABLE AS $fn$
DECLARE
    v_role text;
    med    numeric;
    n      integer;
    prior  numeric;
    est    numeric;
BEGIN
    -- Ticket 34 made this a lookup: role_task_kinds is UNIQUE (kind), so
    -- "(role, kind)" is well defined and the window can no longer be polluted
    -- by a taskless orchestrator run, which is what ticket 34's D28 measured.
    SELECT m.role INTO v_role FROM role_task_kinds m WHERE m.kind = t.kind;

    SELECT count(*), percentile_cont(0.5) WITHIN GROUP (ORDER BY r.total)
      INTO n, med
      FROM (SELECT (ar.input_tokens + ar.output_tokens) AS total
              FROM agent_runs ar
             WHERE ar.program_id = t.program_id
               AND ar.stop_reason = 'completed'
               AND ar.role = v_role
               AND ar.kind = t.kind
               AND ar.input_tokens IS NOT NULL
               AND ar.output_tokens IS NOT NULL
             -- deterministic: started_at ties are broken by id, exactly as the
             -- queue order is, so two passes read the same N rows
             ORDER BY ar.started_at DESC, ar.id DESC
             LIMIT w.history_window_n) r;

    prior := coalesce((w.cost_prior ->> t.kind)::numeric, 0.5);
    est := (coalesce(n, 0) * coalesce(med, 0)
            + w.shrinkage_n0 * prior * w.cost_reference_tokens)
           / (coalesce(n, 0) + w.shrinkage_n0);
    RETURN least(greatest(est / w.cost_reference_tokens, w.cost_floor), 1.0);
END $fn$;


-- ===========================================================================
-- 7. confidence -- gates, then a shrunk success rate
-- ===========================================================================

CREATE FUNCTION confidence_for(t tasks, w scheduler_weights) RETURNS numeric
LANGUAGE plpgsql STABLE AS $fn$
DECLARE
    v_role    text;
    n         integer;
    successes integer;
    ok        boolean;
BEGIN
    -- Gate 1: the subject is in scope.
    --
    -- Ticket 26 caches `decide_static` as a projection on `entities`, and this
    -- reads the cache. That is legitimate for exactly one reason: a stale
    -- projection can WASTE a task but cannot AUTHORISE a request. If the
    -- projection says in-scope and the live policy disagrees, the task is
    -- offered, claimed, and its first request is refused by the proxy, which
    -- decides against the policy and not against this column. The asymmetry is
    -- the whole licence for the cache, so the scheduler tolerating staleness is
    -- a design property, not an oversight.
    IF t.subject_entity_id IS NOT NULL THEN
        SELECT e.in_scope INTO ok FROM entities e WHERE e.id = t.subject_entity_id;
        IF NOT coalesce(ok, false) THEN RETURN 0; END IF;
    END IF;

    -- Gate 2: the identities the hypothesis names are not held by someone else.
    --
    -- `released_at IS NULL` and nothing else. Ticket 32's stand-in also tested
    -- `expires_at > now()`, which put the clock inside the ranking pass and
    -- quietly broke decision 12. An expired-but-unreleased lease is the SWEEP's
    -- problem; while it is unreleased it is held, and `identity_leases` has a
    -- unique index saying so.
    IF t.hypothesis_id IS NOT NULL AND EXISTS (
         SELECT 1 FROM hypotheses h
           JOIN identity_leases l
             ON l.identity_entity_id IN (h.identity_a_entity_id,
                                         h.identity_b_entity_id)
          WHERE h.id = t.hypothesis_id AND l.released_at IS NULL) THEN
        RETURN 0;
    END IF;

    -- Gate 3: every required skill exists (a constraint by now) and is enabled.
    IF EXISTS (SELECT 1 FROM unnest(t.required_skills) AS s
                WHERE NOT EXISTS (SELECT 1 FROM skills k
                                   WHERE k.name = s AND k.enabled)) THEN
        RETURN 0;
    END IF;

    SELECT m.role INTO v_role FROM role_task_kinds m WHERE m.kind = t.kind;

    -- A success is `completed` AND at least one receipt-backed observation --
    -- never "the agent said done".
    SELECT count(*),
           count(*) FILTER (WHERE ar.stop_reason = 'completed' AND EXISTS (
               SELECT 1 FROM observations o
                WHERE o.agent_run_id = ar.id AND o.provenance_kind = 'receipt'))
      INTO n, successes
      FROM (SELECT ar2.* FROM agent_runs ar2
             WHERE ar2.program_id = t.program_id
               AND ar2.role = v_role AND ar2.kind = t.kind
               AND ar2.finished_at IS NOT NULL
             ORDER BY ar2.started_at DESC, ar2.id DESC
             LIMIT w.history_window_n) ar;

    RETURN (coalesce(successes, 0) + w.shrinkage_n0 * w.confidence_prior)
           / (coalesce(n, 0) + w.shrinkage_n0);
END $fn$;


-- ===========================================================================
-- 8. readiness -- a predicate over current rows, not a DAG
-- ===========================================================================

-- Returns NULL when the task is ready, else the name of the predicate that
-- refused it. The name is what `scheduler.idle` reports, so "the harness
-- stopped" and "the harness finished" are distinguishable from outside.
CREATE FUNCTION ready_for(t tasks) RETURNS text
LANGUAGE plpgsql STABLE AS $fn$
DECLARE ok boolean;
BEGIN
    IF t.subject_entity_id IS NOT NULL THEN
        SELECT e.in_scope INTO ok FROM entities e WHERE e.id = t.subject_entity_id;
        IF NOT coalesce(ok, false) THEN RETURN t.kind || '.subject_not_in_scope'; END IF;
    END IF;

    IF t.kind = 'recon' THEN
        IF t.subject_entity_id IS NULL THEN RETURN 'recon.no_subject'; END IF;
        RETURN NULL;

    ELSIF t.kind = 'hunt' THEN
        IF t.hypothesis_id IS NULL THEN RETURN 'hunt.no_hypothesis'; END IF;
        IF NOT EXISTS (SELECT 1 FROM hypotheses h
                        WHERE h.id = t.hypothesis_id AND h.status = 'testable') THEN
            RETURN 'hunt.hypothesis_not_testable';
        END IF;
        RETURN NULL;

    ELSIF t.kind = 'analyze' THEN
        -- "at least one agent-visible artifact reachable from an observation on
        -- the subject". Reachability is ticket 12's `artifact_refs` bridge:
        -- `artifacts` is content-addressed and program-global, so a bare hash
        -- lookup would cross programs.
        IF NOT EXISTS (
             SELECT 1
               FROM observations o
               JOIN receipts r     ON r.id = o.receipt_id
               JOIN artifact_refs x ON x.ref_label = r.label
                                   AND x.program_id = o.program_id
               JOIN artifacts a    ON a.sha256 = x.sha256
              WHERE o.subject_entity_id = t.subject_entity_id
                AND a.visibility = 'agent_visible'
                AND NOT a.encrypted AND a.purged_at IS NULL) THEN
            RETURN 'analyze.no_agent_visible_artifact';
        END IF;
        RETURN NULL;

    ELSIF t.kind = 'validate' THEN
        IF t.finding_id IS NULL THEN RETURN 'validate.no_finding'; END IF;
        IF NOT EXISTS (SELECT 1 FROM findings f
                        WHERE f.id = t.finding_id AND f.status = 'candidate') THEN
            RETURN 'validate.finding_not_candidate';
        END IF;
        IF NOT EXISTS (SELECT 1 FROM tests ts
                         JOIN finding_hypotheses fh ON fh.hypothesis_id = ts.hypothesis_id
                        WHERE fh.finding_id = t.finding_id) THEN
            RETURN 'validate.no_test_spec';
        END IF;
        RETURN NULL;

    ELSIF t.kind = 'report' THEN
        IF NOT EXISTS (SELECT 1 FROM findings f
                        WHERE f.program_id = t.program_id AND f.status = 'validated') THEN
            RETURN 'report.no_validated_finding';
        END IF;
        RETURN NULL;
    END IF;
    RETURN t.kind || '.unknown_kind';
END $fn$;


-- ===========================================================================
-- 9. cancellation -- runtime-only, and an LLM never cancels a task
-- ===========================================================================

CREATE FUNCTION cancel_reason_for(t tasks, w scheduler_weights) RETURNS text
LANGUAGE plpgsql STABLE AS $fn$
DECLARE ok boolean; st text; fired boolean; left_ bigint;
BEGIN
    IF EXISTS (SELECT 1 FROM programs p
                WHERE p.id = t.program_id AND p.closed_at IS NOT NULL) THEN
        RETURN 'program_closed';
    END IF;

    SELECT b.tokens_left INTO left_ FROM program_budget b WHERE b.program_id = t.program_id;
    IF left_ IS NOT NULL AND left_ <= 0 THEN RETURN 'budget_exhausted'; END IF;

    IF t.attempts >= w.max_attempts THEN RETURN 'attempts_exhausted'; END IF;

    IF t.subject_entity_id IS NOT NULL THEN
        SELECT e.in_scope INTO ok FROM entities e WHERE e.id = t.subject_entity_id;
        IF NOT coalesce(ok, false) THEN RETURN 'out_of_scope'; END IF;
    END IF;

    IF t.hypothesis_id IS NOT NULL THEN
        SELECT h.status, h.superseded_by IS NOT NULL INTO st, ok
          FROM hypotheses h WHERE h.id = t.hypothesis_id;
        IF ok THEN RETURN 'superseded'; END IF;
        SELECT EXISTS (SELECT 1 FROM hypothesis_retest_triggers x
                        WHERE x.hypothesis_id = t.hypothesis_id
                          AND x.fired_at IS NOT NULL) INTO fired;
        IF st IN ('supported','refuted') AND NOT fired THEN RETURN 'answered'; END IF;
        -- a candidate that stage 2 suppressed leaves the hypothesis gone
        IF st IS NULL THEN RETURN 'near_duplicate'; END IF;
    END IF;

    IF t.kind = 'validate' AND EXISTS (
         SELECT 1 FROM findings f WHERE f.id = t.finding_id
           AND f.status IN ('validated','reported','rejected')) THEN
        RETURN 'answered';
    END IF;

    -- The general rule, last: nothing left to learn is nothing worth running.
    --
    -- Except for `report`, and the exception is not a special case -- it is the
    -- one kind whose novelty is a function of rows that have not arrived yet.
    -- `novelty_for('report')` is 1 exactly when an unreported validated finding
    -- exists, so a report task in a young program scores 0, and without this
    -- guard `rank_pass` would abandon it as `answered` on the first pass and
    -- the program would validate findings with no report task left alive. The
    -- admission matrix found this: the fixture happened to validate FG20 before
    -- the first pass, which hid it. Nothing to report yet is unready, not
    -- answered, and `ready_for` already says so.
    IF t.kind <> 'report' AND novelty_for(t) = 0 THEN RETURN 'answered'; END IF;
    RETURN NULL;
END $fn$;


-- ===========================================================================
-- 10. The ranking pass, as one statement, with no clock in it
-- ===========================================================================

-- No program argument, on purpose. Ticket 12 binds `rk2.program_id` on the
-- connection from runtime session config; ticket 11's R-PROGRAM refuses a
-- program identifier anywhere in a tool input tree. A `p_program uuid`
-- parameter here would be the same hole one layer down.
CREATE FUNCTION rk2_program_required() RETURNS uuid
LANGUAGE plpgsql STABLE AS $fn$
DECLARE p uuid;
BEGIN
    p := rk2_program();
    IF p IS NULL THEN
        RAISE EXCEPTION 'rk2.program_id is not set on this connection'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN p;
END $fn$;

CREATE FUNCTION rank_pass(p_trigger text DEFAULT 'timer') RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p            uuid := rk2_program_required();
    w            scheduler_weights%ROWTYPE;
    n_cancelled  bigint := 0;
    n_ranked     bigint := 0;
    n_fired      bigint := 0;
    by_reason    jsonb;
    top          jsonb;
    t0           timestamptz := clock_timestamp();
BEGIN
    SELECT * INTO w FROM scheduler_weights WHERE active;
    IF NOT FOUND THEN RAISE EXCEPTION 'no active scheduler_weights row'; END IF;

    -- (1) Retest re-entry. Decision 11: the pass owns it, because it is the
    -- only runtime step that reads the whole program. `fired_at` is stamped in
    -- the same statement, or a changed fingerprint re-fires every pass forever.
    WITH due AS (
        SELECT x.id, x.hypothesis_id
          FROM hypothesis_retest_triggers x
          JOIN hypotheses h ON h.id = x.hypothesis_id
          LEFT JOIN LATERAL (
              SELECT sf.fingerprint FROM surface_fingerprints sf
               WHERE sf.program_id = h.program_id
               ORDER BY sf.computed_at DESC, sf.id DESC LIMIT 1
          ) cur ON true
         WHERE h.program_id = p
           AND h.status IN ('refuted','inconclusive','supported')
           AND x.fired_at IS NULL
           AND x.fingerprint IS DISTINCT FROM cur.fingerprint
           AND cur.fingerprint IS NOT NULL
    ), fired AS (
        UPDATE hypothesis_retest_triggers x
           SET fired_at = now(), fingerprint = (
               SELECT sf.fingerprint FROM surface_fingerprints sf
                WHERE sf.program_id = p ORDER BY sf.computed_at DESC, sf.id DESC LIMIT 1)
          FROM due WHERE x.id = due.id
        RETURNING x.hypothesis_id
    ), moved AS (
        INSERT INTO hypothesis_transitions
            (program_id, hypothesis_id, from_status, to_status, actor_kind, rationale)
        SELECT p, h.id, h.status, 'testable', 'runtime', 'retest trigger fired'
          FROM hypotheses h
         WHERE h.id IN (SELECT hypothesis_id FROM fired)
        RETURNING hypothesis_id
    )
    SELECT count(*) INTO n_fired FROM moved;

    -- (2) Cancellation, before ranking: a task that should not run must not be
    -- ranked into a slate this pass.
    WITH c AS (
        SELECT t.id, cancel_reason_for(t, w) AS reason
          FROM tasks t WHERE t.program_id = p AND t.status = 'pending'
    ), u AS (
        UPDATE tasks t SET status = 'abandoned', abandoned_reason = c.reason,
                           finished_at = now(), priority = NULL
          FROM c WHERE t.id = c.id AND c.reason IS NOT NULL
        RETURNING t.abandoned_reason AS reason
    )
    SELECT count(*), coalesce(jsonb_object_agg(reason, n), '{}'::jsonb)
      INTO n_cancelled, by_reason
      FROM (SELECT reason, count(*) AS n FROM u GROUP BY reason) g;

    -- (3) The ranking. One statement, four columns, no `now()`.
    WITH r AS (
        SELECT t.id,
               novelty_for(t)         AS novelty,
               cost_for(t, w)         AS estimated_cost,
               confidence_for(t, w)   AS confidence
          FROM tasks t
         WHERE t.program_id = p AND t.status = 'pending'
    ), u AS (
        UPDATE tasks t
           SET novelty = r.novelty,
               estimated_cost = r.estimated_cost,
               confidence_of_execution = r.confidence,
               -- NULL, not 0: an unestimated task must sink via NULLS LAST, and
               -- a task scored 0 is a different statement from one never scored
               priority = CASE
                   WHEN t.expected_information_gain IS NULL
                     OR t.potential_impact IS NULL THEN NULL
                   ELSE r.novelty * r.confidence
                        * (w.w_gain * t.expected_information_gain
                         + w.w_impact * t.potential_impact)
                        / greatest(r.estimated_cost, w.cost_floor)
               END
          FROM r WHERE t.id = r.id
        RETURNING t.id
    )
    SELECT count(*) INTO n_ranked FROM u;

    SELECT coalesce(jsonb_agg(j ORDER BY ord), '[]'::jsonb) INTO top
      FROM (
        SELECT row_number() OVER (ORDER BY t.priority DESC NULLS LAST,
                                           t.created_at, t.id) AS ord,
               jsonb_build_object(
                 'task', t.label, 'kind', t.kind,
                 'priority', round(t.priority, 6),
                 'factors', jsonb_build_object(
                     'novelty', round(t.novelty, 6),
                     'gain', t.expected_information_gain,
                     'impact', t.potential_impact,
                     'cost', round(t.estimated_cost, 6),
                     'confidence', round(t.confidence_of_execution, 6))) AS j
          FROM tasks t WHERE t.program_id = p AND t.status = 'pending'
          ORDER BY t.priority DESC NULLS LAST, t.created_at, t.id
          LIMIT 10) s;

    INSERT INTO events (program_id, type, actor_kind, payload)
    VALUES (p, 'scheduler.ranked', 'runtime', jsonb_build_object(
        'trigger', p_trigger,
        'weights_version', w.version,
        'candidates', n_ranked,
        'retest_triggers_fired', n_fired,
        'abandoned_by_reason', by_reason,
        'lane_slots', (SELECT coalesce(jsonb_object_agg(kind, live_slots), '{}'::jsonb)
                         FROM scheduler_lane_state WHERE program_id = p),
        'top', top,
        'further_omitted', greatest(n_ranked - 10, 0),
        'duration_ms', round(extract(epoch FROM clock_timestamp() - t0) * 1000)));

    RETURN jsonb_build_object('ranked', n_ranked, 'abandoned', n_cancelled,
                              'retests_fired', n_fired);
END $fn$;


-- ===========================================================================
-- 11. The slate -- five entries, entitlement first, then greedy
-- ===========================================================================

-- Decision 8 said starvation is bounded structurally by per-kind quotas and not
-- by an aging term, and then nothing read `min_slots`. Greedy-within-lane alone
-- does not bound starvation: a rich vein of hunt work outranks every recon task
-- in the program, so the recon lane's entitlement of 1 is never taken and the
-- broad cheap work never runs.
--
-- The entitlement is therefore a SORT KEY, not a reservation. A lane below
-- min_slots gets its deficit many tasks placed ahead of the greedy order, and
-- exactly that many -- so `min_slots` cannot starve the greedy queue either.
CREATE FUNCTION rank_candidates()
RETURNS TABLE (task_id uuid, kind text, entitled boolean, rnk bigint)
LANGUAGE sql STABLE AS $fn$
    WITH w AS (SELECT * FROM scheduler_weights WHERE active),
         b AS (SELECT * FROM program_budget WHERE program_id = rk2_program()),
         cand AS (
            SELECT t.id, t.kind, t.priority, t.created_at, t.estimated_cost,
                   s.deficit, s.headroom
              FROM tasks t
              JOIN scheduler_lane_state s
                ON s.program_id = t.program_id AND s.kind = t.kind
              CROSS JOIN w, b
             WHERE t.program_id = rk2_program()
               AND t.status = 'pending'
               AND ready_for(t) IS NULL
               AND s.headroom > 0
               -- affordable: the run this task would start must fit the
               -- program envelope. Unbounded budget means always affordable.
               AND (b.tokens_left IS NULL
                    OR b.tokens_left >= t.estimated_cost * w.cost_reference_tokens)
               -- the cross-lane cap ticket 34 put on scheduler_weights, which
               -- no per-kind table can express
               AND (SELECT count(*) FROM tasks c
                      JOIN effective_lane_capacity lc
                        ON lc.program_id = c.program_id AND lc.kind = c.kind
                      JOIN roles r ON r.role = lc.role
                     WHERE c.program_id = t.program_id
                       AND c.status IN ('claimed','running')
                       AND r.runs_as = 'subagent') < w.max_concurrent_subagents
         ), ordered AS (
            SELECT c.*,
                   row_number() OVER (ORDER BY c.priority DESC NULLS LAST,
                                               c.created_at, c.id) AS rnk,
                   row_number() OVER (PARTITION BY c.kind
                                      ORDER BY c.priority DESC NULLS LAST,
                                               c.created_at, c.id) AS in_lane
              FROM cand c
         )
    SELECT o.id, o.kind, (o.in_lane <= o.deficit) AS entitled, o.rnk
      FROM ordered o
     ORDER BY (o.in_lane <= o.deficit) DESC, o.rnk;
$fn$;

CREATE FUNCTION offer_slate()
RETURNS TABLE (ordinal integer, task_label text, kind text, subject_label text,
               priority numeric, factors jsonb, why_ready text, expires_at timestamptz)
LANGUAGE plpgsql AS $fn$
DECLARE
    p   uuid := rk2_program_required();
    w   scheduler_weights%ROWTYPE;
    sid uuid := uuidv7();
BEGIN
    SELECT * INTO w FROM scheduler_weights WHERE active;

    -- A superseded slate must stop being claimable, or the orchestrator can
    -- pick from a stale offer after the world moved. Consumed, not deleted:
    -- ticket 16 has to be able to ask what was offered and never taken.
    UPDATE task_slate SET consumed = true
     WHERE program_id = p AND NOT consumed;

    INSERT INTO task_slate (slate_id, program_id, task_id, ordinal)
    SELECT sid, p, c.task_id,
           row_number() OVER (ORDER BY c.entitled DESC, c.rnk)::integer
      FROM rank_candidates() c
     ORDER BY c.entitled DESC, c.rnk
     LIMIT w.slate_size;

    RETURN QUERY
    SELECT s.ordinal, t.label, t.kind, e.label,
           round(t.priority, 6),
           jsonb_build_object('novelty', round(t.novelty, 6),
                              'gain', t.expected_information_gain,
                              'impact', t.potential_impact,
                              'cost', round(t.estimated_cost, 6),
                              'confidence', round(t.confidence_of_execution, 6),
                              'entitled', s.ordinal <= (
                                  SELECT count(*) FROM rank_candidates() rc
                                   WHERE rc.entitled)),
           'ready',
           s.offered_at + w.slate_ttl
      FROM task_slate s
      JOIN tasks t ON t.id = s.task_id
      LEFT JOIN entities e ON e.id = t.subject_entity_id
     WHERE s.slate_id = sid
     ORDER BY s.ordinal;
END $fn$;


-- ===========================================================================
-- 12. The claim -- one re-validating transaction, under the advisory lock
-- ===========================================================================

-- Ticket 32/D15: six concurrent claims against a lane capped at 2 left six
-- tasks live. `SKIP LOCKED` stops two transactions taking the same ROW; it does
-- nothing about six transactions each counting the same headroom and each
-- concluding there is room. Ticket 08's claim protocol said "concurrency is
-- handled a layer up by tasks_live_dedup_idx, so no lock is needed here". That
-- is wrong, and it is wrong in the direction that spends money.
--
-- `pg_advisory_xact_lock(program)` serialises the counting window. It is the
-- same lock the loop already holds per program (decision: one asyncio task per
-- program), so the two collapse into one and this function is safe whether the
-- caller is the loop or a second runtime process.
CREATE FUNCTION claim_task(p_task_label text DEFAULT NULL)
RETURNS text LANGUAGE plpgsql AS $fn$
DECLARE
    p        uuid := rk2_program_required();
    w        scheduler_weights%ROWTYPE;
    v_task   tasks%ROWTYPE;
    v_role   text;
    v_runs_as text;
    v_clamp  boolean;
    v_model  text;
    v_effort text;
    v_run    uuid;
    v_reason text;
BEGIN
    SELECT * INTO w FROM scheduler_weights WHERE active;

    -- Everything after this point is inside the counting window.
    PERFORM pg_advisory_xact_lock(hashtextextended(p::text, 0));

    IF p_task_label IS NULL THEN
        -- Decision 3: the orchestrator picking nothing means the runtime takes
        -- position 1. This is the runtime's own path and takes no label.
        SELECT t.* INTO v_task
          FROM task_slate s JOIN tasks t ON t.id = s.task_id
         WHERE s.program_id = p AND NOT s.consumed
         ORDER BY s.ordinal LIMIT 1;
        IF NOT FOUND THEN RETURN NULL; END IF;
    ELSE
        SELECT t.* INTO v_task
          FROM task_slate s JOIN tasks t ON t.id = s.task_id
         WHERE s.program_id = p AND NOT s.consumed AND t.label = p_task_label;
        IF NOT FOUND THEN
            -- Ticket 12's rule, kept: a label that is not on the current slate
            -- is refused rather than honoured. The loop maps this onto decision
            -- 3's "runtime takes position 1" by calling claim_task(NULL) once;
            -- that fallback belongs in the loop, not in the commit surface,
            -- because here it would mean the model naming a task and getting a
            -- different one without being told.
            RAISE EXCEPTION 'task % is not on the current slate', p_task_label
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;

    -- Re-validate every filter inside the transaction. The slate is a
    -- suggestion that was true when it was computed; this is the check that
    -- makes it true when it is acted on.
    SELECT t.* INTO v_task FROM tasks t WHERE t.id = v_task.id FOR UPDATE;

    -- Cancellation is asked FIRST, before readiness. Both would refuse, but
    -- they mean different things and only one of them is permanent, and the
    -- refusal string is what ticket 16 reads. The admission matrix
    -- (`tests/matrix.sql`) caught the original order: a hunt task whose
    -- hypothesis is `refuted` was refused as `hunt.hypothesis_not_testable`,
    -- which reads as "not yet" for a task that is never coming back, and an
    -- out-of-scope subject was refused as `recon.subject_not_in_scope` rather
    -- than `out_of_scope`. Asking the permanent question first also matches
    -- `rank_pass`, which cancels before it ranks.
    IF v_task.status <> 'pending' THEN v_reason := 'not_pending';
    ELSIF cancel_reason_for(v_task, w) IS NOT NULL THEN
        v_reason := cancel_reason_for(v_task, w);
    ELSIF ready_for(v_task) IS NOT NULL THEN v_reason := ready_for(v_task);
    ELSIF NOT EXISTS (SELECT 1 FROM scheduler_lane_state s
                       WHERE s.program_id = p AND s.kind = v_task.kind
                         AND s.headroom > 0) THEN v_reason := 'lane_full';
    ELSIF (SELECT count(*) FROM tasks c
             JOIN effective_lane_capacity lc
               ON lc.program_id = c.program_id AND lc.kind = c.kind
             JOIN roles r ON r.role = lc.role
            WHERE c.program_id = p AND c.status IN ('claimed','running')
              AND r.runs_as = 'subagent') >= w.max_concurrent_subagents THEN
        v_reason := 'global_subagent_cap';
    END IF;

    IF v_reason IS NOT NULL THEN
        -- No `UPDATE task_slate SET consumed` here, deliberately. The first
        -- draft had one and it was a comment pretending to be a write: the
        -- RAISE on the next line aborts the transaction and takes the update
        -- with it, in this function and in any caller's subtransaction alike.
        -- Nothing needs it. `offer_slate()` consumes every outstanding row of
        -- the program before it writes a new slate, and the loop answers a
        -- refusal by recomputing rather than by re-claiming -- at which point
        -- `rank_pass` has already abandoned a cancellable task and
        -- `rank_candidates` already filters an unready one, so the entry
        -- cannot come back. What is left is the race this re-validation
        -- exists for, and a race is transient by definition.
        RAISE EXCEPTION 'task % is no longer claimable: %', v_task.label, v_reason
            USING ERRCODE = 'check_violation';
    END IF;

    SELECT m.role, r.runs_as, r.clamp_to_identity_leases
      INTO v_role, v_runs_as, v_clamp
      FROM role_task_kinds m JOIN roles r ON r.role = m.role
     WHERE m.kind = v_task.kind;

    v_model  := CASE WHEN v_runs_as = 'renderer' THEN 'none' ELSE 'claude-opus-5' END;
    v_effort := CASE WHEN v_runs_as = 'renderer' THEN 'none' ELSE 'high' END;

    UPDATE tasks
       SET status = 'claimed', attempts = attempts + 1, claimed_at = now(),
           lease_expires_at = now() + w.lease_ttl
     WHERE id = v_task.id;

    INSERT INTO agent_runs (program_id, task_id, role, model, effort, mission_packet)
    VALUES (p, v_task.id, v_role, v_model, v_effort, '{}')
    RETURNING id INTO v_run;

    -- Decision 7: the identity lease shares the task lease's clock. Two clocks
    -- would admit a live task lease beside a dead identity lease, and the agent
    -- would read the proxy's refusal to inject as the TARGET changing
    -- behaviour -- the false positive the identity model exists to prevent.
    IF v_clamp AND v_task.hypothesis_id IS NOT NULL THEN
        INSERT INTO identity_leases (identity_entity_id, holder_agent_run_id,
                                     expires_at, program_id)
        SELECT i, v_run, now() + w.lease_ttl, p
          FROM (SELECT unnest(ARRAY[h.identity_a_entity_id, h.identity_b_entity_id]) AS i
                  FROM hypotheses h WHERE h.id = v_task.hypothesis_id) x
         WHERE i IS NOT NULL;
    END IF;

    UPDATE task_slate SET consumed = true
     WHERE program_id = p AND task_id = v_task.id AND NOT consumed;

    RETURN (SELECT label FROM agent_runs WHERE id = v_run);
END $fn$;


-- ===========================================================================
-- 13. Lease expiry -- resume_program()'s body, scoped to one task
-- ===========================================================================

-- Decision 7: lease expiry and crash resume are one mechanism, which keeps
-- Q29's "one case, not four" literally true. This is that body with a WHERE
-- clause, plus the one thing resume does not do -- retire a task that has used
-- up its attempts, so an expiring lease cannot loop forever.
CREATE FUNCTION sweep_expired_leases() RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p       uuid := rk2_program_required();
    w       scheduler_weights%ROWTYPE;
    n_task  bigint; n_run bigint; n_lease bigint; n_hyp bigint; n_gone bigint;
BEGIN
    SELECT * INTO w FROM scheduler_weights WHERE active;
    PERFORM set_config('app.actor_kind', 'runtime', true);

    CREATE TEMP TABLE _expired ON COMMIT DROP AS
        SELECT t.id, t.hypothesis_id, t.attempts
          FROM tasks t
         WHERE t.program_id = p AND t.status IN ('claimed','running')
           AND t.lease_expires_at IS NOT NULL AND t.lease_expires_at < now();

    UPDATE agent_runs a SET finished_at = now(), stop_reason = 'aborted', result = NULL
     WHERE a.program_id = p AND a.finished_at IS NULL
       AND a.task_id IN (SELECT id FROM _expired);
    GET DIAGNOSTICS n_run = ROW_COUNT;

    UPDATE identity_leases l SET released_at = now()
     WHERE l.program_id = p AND l.released_at IS NULL
       AND l.holder_agent_run_id IN (
           SELECT a.id FROM agent_runs a WHERE a.task_id IN (SELECT id FROM _expired));
    GET DIAGNOSTICS n_lease = ROW_COUNT;

    INSERT INTO hypothesis_transitions
        (program_id, hypothesis_id, from_status, to_status, actor_kind, rationale)
    SELECT p, h.id, 'testing', 'testable', 'runtime', 'task lease expired'
      FROM hypotheses h
     WHERE h.status = 'testing'
       AND h.id IN (SELECT hypothesis_id FROM _expired WHERE hypothesis_id IS NOT NULL);
    GET DIAGNOSTICS n_hyp = ROW_COUNT;

    UPDATE tasks t SET status = 'abandoned', abandoned_reason = 'attempts_exhausted',
                       finished_at = now(), lease_expires_at = NULL, priority = NULL
     WHERE t.id IN (SELECT id FROM _expired WHERE attempts >= w.max_attempts);
    GET DIAGNOSTICS n_gone = ROW_COUNT;

    UPDATE tasks t SET status = 'pending', claimed_at = NULL, priority = NULL,
                       lease_expires_at = NULL
     WHERE t.id IN (SELECT id FROM _expired WHERE attempts < w.max_attempts);
    GET DIAGNOSTICS n_task = ROW_COUNT;

    RETURN jsonb_build_object('tasks_returned', n_task, 'tasks_retired', n_gone,
                              'runs_aborted', n_run, 'leases_released', n_lease,
                              'hypotheses_returned_to_testable', n_hyp);
END $fn$;


-- ===========================================================================
-- 14. Idle -- and why, because "stopped" and "finished" must differ
-- ===========================================================================

CREATE FUNCTION scheduler_idle_report() RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p       uuid := rk2_program_required();
    payload jsonb;
    n_flight bigint;
BEGIN
    SELECT count(*) INTO n_flight FROM agent_runs
     WHERE program_id = p AND finished_at IS NULL;

    SELECT jsonb_build_object(
        'reason_counts', (
            SELECT coalesce(jsonb_object_agg(k, n), '{}'::jsonb) FROM (
                SELECT CASE WHEN t.status = 'parked' THEN 'parked'
                            WHEN t.status = 'abandoned' THEN 'abandoned'
                            WHEN ready_for(t) IS NOT NULL THEN 'unready'
                            ELSE 'claimable' END AS k, count(*) AS n
                  FROM tasks t
                 WHERE t.program_id = p
                   AND t.status IN ('pending','parked','abandoned')
                 GROUP BY 1) s),
        'unready_by_predicate', (
            SELECT coalesce(jsonb_object_agg(k, n), '{}'::jsonb) FROM (
                SELECT ready_for(t) AS k, count(*) AS n
                  FROM tasks t
                 WHERE t.program_id = p AND t.status = 'pending'
                   AND ready_for(t) IS NOT NULL
                 GROUP BY 1) s),
        'runs_in_flight', n_flight,
        -- terminal only with zero parked tasks and zero unfired retest
        -- triggers: a retest can create work hours from now, so "no work right
        -- now" is not "done", and only the operator closes a program.
        'terminal', n_flight = 0
            AND NOT EXISTS (SELECT 1 FROM tasks t
                             WHERE t.program_id = p AND t.status IN ('pending','parked','claimed','running'))
            AND NOT EXISTS (SELECT 1 FROM hypothesis_retest_triggers x
                              JOIN hypotheses h ON h.id = x.hypothesis_id
                             WHERE h.program_id = p AND x.fired_at IS NULL)
    ) INTO payload;

    INSERT INTO events (program_id, type, actor_kind, payload)
    VALUES (p, 'scheduler.idle', 'runtime', payload);
    RETURN payload;
END $fn$;


-- ===========================================================================
-- 15. The scheduler surface is the runtime's, not the agent's
-- ===========================================================================

-- Postgres grants EXECUTE on a new function to PUBLIC. Ticket 12 enumerated the
-- agent role's read surface table by table and deliberately withheld
-- `scheduler_weights` and `scheduler_lanes` ("an agent that can read the
-- weights can aim at them") -- and then every function created afterwards was
-- callable by `rk2_state` by default. The SELECT privileges make most of them
-- fail, which is luck, not design: one SECURITY DEFINER function would be the
-- whole model.
DO $$
DECLARE f text;
BEGIN
    FOREACH f IN ARRAY ARRAY[
        'novelty_for(tasks)', 'cost_for(tasks,scheduler_weights)',
        'confidence_for(tasks,scheduler_weights)', 'ready_for(tasks)',
        'cancel_reason_for(tasks,scheduler_weights)', 'rank_pass(text)',
        'rank_candidates()', 'offer_slate()', 'claim_task(text)',
        'sweep_expired_leases()', 'scheduler_idle_report()',
        'rk2_program_required()']
    LOOP
        EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC', f);
        EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO rk2_runtime', f);
    END LOOP;
END $$;

REVOKE ALL ON program_budget, effective_lane_capacity, scheduler_lane_state FROM PUBLIC;
GRANT SELECT ON program_budget, effective_lane_capacity, scheduler_lane_state TO rk2_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON skills TO rk2_runtime;

-- Ticket 12's RLS loop ran in migration 020 and bound the tables that existed
-- THEN. Migration 021 (ticket 26) then created two more program-scoped tables,
-- and `check_state_access()` has been reporting four problems in the composed
-- stack ever since -- which nobody saw, because each ticket ran its own
-- migration against its own database. Re-running 020's own rule is the fix, and
-- doing it by rule rather than by naming the two tables is what makes the next
-- migration's tables safe too.
DO $$
DECLARE t text;
BEGIN
    FOR t IN
        SELECT c.relname FROM pg_class c
         WHERE c.relkind = 'r' AND c.relnamespace = 'public'::regnamespace
           AND EXISTS (SELECT 1 FROM pg_attribute a
                        WHERE a.attrelid = c.oid AND a.attname = 'program_id'
                          AND a.attnum > 0 AND NOT a.attisdropped)
           AND c.relname NOT IN (SELECT table_name FROM program_global_tables)
           AND NOT c.relrowsecurity
         ORDER BY c.relname
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format(
            'CREATE POLICY %I ON %I AS PERMISSIVE FOR ALL TO rk2_state '
            'USING (program_id = rk2_program()) WITH CHECK (program_id = rk2_program())',
            t || '_rk2_state', t);
        EXECUTE format(
            'CREATE POLICY %I ON %I AS PERMISSIVE FOR ALL TO rk2_runtime '
            'USING (true) WITH CHECK (true)', t || '_rk2_runtime', t);
        RAISE NOTICE 'scheduler: enabled RLS on % (created after migration 020)', t;
    END LOOP;
END $$;


-- ===========================================================================
-- 16. The standing check
-- ===========================================================================

CREATE FUNCTION check_scheduler_closure()
RETURNS TABLE (problem text, detail text) LANGUAGE sql STABLE AS $fn$
    -- (a) every kind the roster grants can be ranked by every factor. A kind
    --     with no branch in one of the three functions is a task that ranks 0
    --     forever and nobody notices.
    SELECT 'kind_has_no_cost_prior'::text, k.kind
      FROM task_kinds k, scheduler_weights w
     WHERE w.active AND NOT (w.cost_prior ? k.kind)
UNION ALL
    -- (b) the per-program lane override is reachable. This is the defect the
    --     migration exists to close; asserting it means dropping the view or
    --     reverting the join cannot make overrides silently inert again.
    SELECT 'lane_override_unreachable', p.id::text || ' ' || l.kind
      FROM scheduler_lanes l JOIN programs p ON p.id = l.program_id
     WHERE NOT EXISTS (SELECT 1 FROM effective_lane_capacity c
                        WHERE c.program_id = l.program_id AND c.kind = l.kind
                          AND c.overridden)
UNION ALL
    -- (c) an entitlement above the roster's cap, now for OVERRIDE rows too --
    --     ticket 34's check (e) reads `lane_capacity`, which only ever contains
    --     the NULL-program rows.
    SELECT 'lane_min_above_role_cap',
           coalesce(c.program_id::text, 'default') || ' ' || c.kind
      FROM effective_lane_capacity c WHERE c.min_slots > c.max_slots
UNION ALL
    -- (d) every skill a task requires is registered.
    SELECT 'task_requires_unregistered_skill', t.label || ' ' || s
      FROM tasks t CROSS JOIN LATERAL unnest(t.required_skills) AS s
     WHERE NOT EXISTS (SELECT 1 FROM skills k WHERE k.name = s)
UNION ALL
    -- (e) a penalised near-match names the hypothesis it penalises.
    SELECT 'near_match_penalty_unreachable', nm.id::text
      FROM hypothesis_near_matches nm
     WHERE nm.action = 'penalised' AND nm.candidate_hypothesis_id IS NULL
UNION ALL
    -- (f) the slate cannot be larger than the table that holds it.
    SELECT 'slate_size_exceeds_task_slate', w.slate_size::text
      FROM scheduler_weights w WHERE w.active AND w.slate_size > 5
UNION ALL
    -- (g) the ranking pass has no clock in it. Decision 12 is a property of the
    --     text, so it is checked against the text: `now()` / `current_timestamp`
    --     inside the three factor functions would make two replays of the same
    --     rows disagree, and nothing else would ever say so. Comments are
    --     stripped first: the first version of this check fired on a comment
    --     explaining why the clock is absent, which is the check calling its
    --     own documentation a defect.
    SELECT 'ranking_factor_reads_the_clock', p.proname
      FROM pg_proc p
     WHERE p.pronamespace = 'public'::regnamespace
       AND p.proname IN ('novelty_for','cost_for','confidence_for')
       AND regexp_replace(p.prosrc, '--[^' || chr(10) || ']*', '', 'g')
           ~* '(now\(\)|current_timestamp|clock_timestamp)'
UNION ALL
    -- (h) the claim takes the lock. Ticket 32 found lane caps unheld without
    --     it, and ticket 08's text still says no lock is needed.
    SELECT 'claim_task_takes_no_advisory_lock', 'claim_task'
      FROM pg_proc p
     WHERE p.pronamespace = 'public'::regnamespace AND p.proname = 'claim_task'
       AND p.prosrc !~ 'pg_advisory_xact_lock'
UNION ALL
    -- (i) no scheduler function is callable by PUBLIC.
    SELECT 'scheduler_function_public_executable', p.proname
      FROM pg_proc p
     WHERE p.pronamespace = 'public'::regnamespace
       AND p.proname IN ('novelty_for','cost_for','confidence_for','ready_for',
                         'cancel_reason_for','rank_pass','rank_candidates',
                         'offer_slate','claim_task','sweep_expired_leases',
                         'scheduler_idle_report')
       AND has_function_privilege('public', p.oid, 'EXECUTE')
$fn$;


-- ===========================================================================
-- 17. Applying the migration is the proof
-- ===========================================================================

DO $$
DECLARE v text;
BEGIN
    SELECT string_agg(problem || ' ' || detail, '; ' ORDER BY problem, detail)
      INTO v FROM check_scheduler_closure();
    IF v IS NOT NULL THEN
        RAISE EXCEPTION 'scheduler is not closed after 023: %', v;
    END IF;
    RAISE NOTICE 'scheduler: check_scheduler_closure() is silent';
END $$;

DO $$
DECLARE v text;
BEGIN
    SELECT string_agg(problem || ' ' || detail, '; ' ORDER BY problem, detail)
      INTO v FROM check_program_isolation();
    IF v IS NOT NULL THEN
        RAISE EXCEPTION 'program isolation is not closed after 023: %', v;
    END IF;
    RAISE NOTICE 'scheduler: check_program_isolation() is still silent';
END $$;

DO $$
DECLARE v text;
BEGIN
    SELECT string_agg(problem || ' ' || detail, '; ' ORDER BY problem, detail)
      INTO v FROM check_role_kind_mapping();
    IF v IS NOT NULL THEN
        RAISE EXCEPTION 'role/kind mapping is not closed after 023: %', v;
    END IF;
END $$;

DO $$
DECLARE v text;
BEGIN
    SELECT string_agg(rule || ' ' || obj, '; ' ORDER BY rule, obj)
      INTO v FROM check_state_access();
    IF v IS NOT NULL THEN
        RAISE EXCEPTION 'state access is not closed after 023: %', v;
    END IF;
    RAISE NOTICE 'scheduler: check_state_access() is silent (four problems before)';
END $$;

-- ticket 07's standing obligation: every trigger fires under replica mode too.
DO $$
DECLARE r record;
BEGIN
    FOR r IN SELECT c.relname AS tbl, t.tgname
               FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid
              WHERE NOT t.tgisinternal
                AND c.relnamespace = 'public'::regnamespace AND t.tgenabled <> 'A'
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ALWAYS TRIGGER %I', r.tbl, r.tgname);
    END LOOP;
END $$;
