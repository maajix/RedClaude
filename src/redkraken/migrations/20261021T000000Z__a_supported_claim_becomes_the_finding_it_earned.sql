-- ---------------------------------------------------------------------------
-- a_supported_claim_becomes_the_finding_it_earned.sql   (ticket 156)
--
-- `rk2hunt16` on 22 August ran the whole chain for the first time: recon
-- proposed a claim, the pass graded it testable, a hunt authored a Test, a
-- `perform` Task replayed it, the replay held, and `H2` transitioned to
-- `supported`. Then the campaign stopped. Lap 5 reported `nothing_to_execute`
-- and the run ended with `findings = 0`.
--
-- Nothing opens work against a claim at `supported`. `propose_finding` is in
-- the tool group `state.propose`, held by `recon`, `web_hunter` and
-- `js_analyst`, and no derivation puts any of the three in front of a settled
-- claim. `validate` is not that step and cannot be: `ready_for`'s validate arm
-- wants a candidate Finding that already exists, and `validator` holds only
-- `validate.judge`. Validation is what happens after the Finding.
--
-- So the Task is the caller, the same way 152 made a Task the caller of
-- `replay.run`. `conclude` is a kind like the other six: the scheduler derives
-- it from rows the runtime wrote itself, ranks it, offers it, and the claim
-- opens the Agent run whose one job is to say what the settled claim is a
-- Finding OF -- a class from the vocabulary and a title a person will read.
--
-- Its role is `web_hunter`, which already holds `state.propose` and
-- `net.request`. `role_task_kinds` is UNIQUE on kind and PRIMARY KEY on
-- (role, kind), so a second kind on an existing role is legal and needs no new
-- role -- and the hunter is the right one: it is the role that already looks at
-- a target and decides what a weakness in it is called.
--
-- What this does NOT do is let a model ask for the kind. `rk2_promote_tasks`
-- opens Tasks from a child's suggestion, and `conclude` is not on that list on
-- purpose: the runtime derives this kind from a transition it wrote, and a
-- model asking for it would be a model asking to conclude.
-- ---------------------------------------------------------------------------

-- ===========================================================================
-- 1. The kind
-- ===========================================================================
--
-- Three rows, in the order the foreign keys need them, and no fourth: 0019
-- replaced both `kind` CHECK constraints with references to `task_kinds`, so
-- the vocabulary grows here and everywhere downstream of it at once.
--
-- No new role. `check_role_kind_mapping` arm (c) asserts `roles.executes_tasks`
-- agrees with the mapping, and the hunter already executes `hunt`, so the
-- summary column is already true and stays true.

INSERT INTO task_kinds (kind) VALUES ('conclude');

INSERT INTO role_task_kinds (role, kind) VALUES ('web_hunter', 'conclude');

-- The lane, which is the third thing a kind needs to exist. `lane_capacity` is
-- a view over `scheduler_lanes` joined to the mapping above, so a kind with no
-- default lane row has no capacity at all and `check_role_kind_mapping` arm (d)
-- says so.
--
-- No floor. An entitlement is a slot held open for work that should always be
-- able to start, and a conclusion cannot exist until a replay has settled
-- something; a floor would be holding a slot for work that is not there yet.
-- The ceiling is the hunter's own `max_concurrent`, because `lane_capacity`
-- takes it from the role and no lane may raise it.
--
-- The seed goes in with the trigger off and the trigger goes back on ALWAYS,
-- which is 016's required state and the shape 152 used for the same reason:
-- 037 froze this table against an unversioned quota move by a runtime, and a
-- new kind's default lane is not that -- it is the schema growing, in a
-- migration, once.

ALTER TABLE scheduler_lanes DISABLE TRIGGER scheduler_lanes_no_unversioned_write;

INSERT INTO scheduler_lanes (program_id, kind, min_slots) VALUES
    (NULL, 'conclude', 0);

ALTER TABLE scheduler_lanes
    ENABLE ALWAYS TRIGGER scheduler_lanes_no_unversioned_write;

-- The quota profiles, which 037 refuses to leave incomplete: a profile that
-- does not name every kind silently reverts that lane to the default, and that
-- is a quota move nobody wrote down. No floor in any of the three, for the
-- reason the default lane has none.

INSERT INTO lane_quota_profile_slots (profile, kind, min_slots) VALUES
    ('breadth',  'conclude', 0),
    ('balanced', 'conclude', 0),
    ('depth',    'conclude', 0);

-- And the ranking priors. `check_scheduler_closure` arm (a) refuses a kind
-- missing from `cost_prior` by name, and it is right to: `cost_for` reads the
-- kind out of that document, and a NULL cost fails the affordability comparison
-- silently, so the Task would be ranked and never offered. `time_for` reads
-- `time_prior` the same way and is not checked by name, which is a reason to
-- be careful rather than a reason to skip it.
--
-- Cheap, and the numbers say why: a conclusion sends at most one request and
-- writes one sentence about rows that are already on file. Dearer than a
-- replay, which spends no token at all, and far cheaper than a hunt.
--
-- A version is immutable, so the trigger comes off and goes back on ALWAYS,
-- the same shape the lane seed above uses. Not `version_scheduler_weights`:
-- every existing version was written before this kind existed, so none of them
-- states a policy about it, and cutting a new version would say an operator had
-- changed their mind about weights they never had the chance to set. Completing
-- the document is what makes the old versions replayable at all.

ALTER TABLE scheduler_weights
    DISABLE TRIGGER scheduler_weights_versions_are_immutable;

UPDATE scheduler_weights
   SET cost_prior = cost_prior || '{"conclude": 0.20}'::jsonb,
       time_prior = time_prior || '{"conclude": 0.25}'::jsonb;

ALTER TABLE scheduler_weights
    ENABLE ALWAYS TRIGGER scheduler_weights_versions_are_immutable;


-- ===========================================================================
-- 2. When one is ready
-- ===========================================================================
--
-- Re-stated whole rather than patched, because `ready_for` is one CASE over the
-- kind vocabulary and a kind with no arm falls through to `unknown_kind` --
-- which is not a refusal an operator can act on, it is the scheduler saying
-- this kind was never taught to it.
--
-- Four conditions. The claim exists and is supported, because that is what a
-- Finding rests on; no Finding rests on it yet, which is what makes the work
-- worth doing and is also `open_finding`'s own merge case seen from this side;
-- and the subject has an address, for the reason the hunt arm has that check --
-- the hunter is going to be handed a target, and a Task that would be retired
-- at the dispatch step should never have been offered.

CREATE OR REPLACE FUNCTION ready_for(t tasks) RETURNS text
LANGUAGE plpgsql STABLE AS $fn$
DECLARE ok boolean;
BEGIN
    IF t.subject_entity_id IS NOT NULL THEN
        SELECT e.in_scope INTO ok FROM entities e WHERE e.id = t.subject_entity_id;
        IF NOT coalesce(ok, false) THEN RETURN t.kind || '.subject_not_in_scope'; END IF;
    END IF;

    IF t.kind = 'recon' THEN
        IF t.subject_entity_id IS NULL THEN RETURN 'recon.no_subject'; END IF;
        IF rk2_subject_addressable(t.subject_entity_id) IS NOT TRUE THEN
            RETURN 'recon.no_address';
        END IF;
        RETURN NULL;

    ELSIF t.kind = 'hunt' THEN
        IF t.hypothesis_id IS NULL THEN RETURN 'hunt.no_hypothesis'; END IF;
        IF NOT EXISTS (SELECT 1 FROM hypotheses h
                        WHERE h.id = t.hypothesis_id AND h.status = 'testable') THEN
            RETURN 'hunt.hypothesis_not_testable';
        END IF;
        -- Asked only where there is a subject to ask it about. A hunt Task
        -- with none is undispatchable too, but it is not this predicate's
        -- sentence to say so: `derive_chain_unlocks` takes the subject off the
        -- frontier and a NULL there is the runtime's case, ended by
        -- `retire_task` at the point the URL comes back missing.
        IF t.subject_entity_id IS NOT NULL
           AND rk2_subject_addressable(t.subject_entity_id) IS NOT TRUE THEN
            RETURN 'hunt.no_address';
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

    ELSIF t.kind = 'perform' THEN
        IF t.test_id IS NULL THEN RETURN 'perform.no_test'; END IF;
        IF NOT EXISTS (SELECT 1 FROM tests ts
                         JOIN hypotheses h ON h.id = ts.hypothesis_id
                        WHERE ts.id = t.test_id AND h.status = 'testable') THEN
            RETURN 'perform.claim_not_testable';
        END IF;
        IF EXISTS (SELECT 1 FROM test_replays tp WHERE tp.test_id = t.test_id) THEN
            RETURN 'perform.already_performed';
        END IF;
        RETURN NULL;

    ELSIF t.kind = 'conclude' THEN
        IF t.hypothesis_id IS NULL THEN RETURN 'conclude.no_hypothesis'; END IF;
        IF NOT EXISTS (SELECT 1 FROM hypotheses h
                        WHERE h.id = t.hypothesis_id AND h.status = 'supported') THEN
            RETURN 'conclude.claim_not_supported';
        END IF;
        IF EXISTS (SELECT 1 FROM finding_hypotheses fh
                    WHERE fh.hypothesis_id = t.hypothesis_id) THEN
            RETURN 'conclude.already_found';
        END IF;
        IF t.subject_entity_id IS NOT NULL
           AND rk2_subject_addressable(t.subject_entity_id) IS NOT TRUE THEN
            RETURN 'conclude.no_address';
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
-- 3. What is left to learn from one
-- ===========================================================================
--
-- The arm that keeps the Task alive long enough to be offered, and the reason
-- it is here rather than in `cancel_reason_for`'s kind list.
--
-- `cancel_reason_for` ends with "nothing left to learn is nothing worth
-- running", read off `novelty_for`. Without an arm this function falls through
-- to its closing `RETURN 0`, the general rule reads that as answered, and every
-- `conclude` Task the pass derived is abandoned before it is offered once. 152
-- measured exactly this for `perform` in `rk2hunt13`, and the fix belongs in
-- the same place: a kind whose novelty is a real question gets an arm, rather
-- than the sweep growing a second hard-coded exception beside `report`'s.
--
-- Shaped like `validate`'s, because the Task names the claim and this is a
-- lookup rather than a scan. A settled claim no Finding rests on is the whole
-- of what has not been written down about it; once one does, a second
-- conclusion of the same claim would be `open_finding` merging into the row
-- that is already there, which is also what `ready_for` says when it refuses
-- `conclude.already_found`.

CREATE OR REPLACE FUNCTION novelty_for(t tasks) RETURNS numeric
LANGUAGE plpgsql STABLE AS $fn$
DECLARE
    covered   integer;
    total     integer;
    n_ev      integer;
    st        text;
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
        -- Ticket 127: the `penalised` discount that used to multiply this is
        -- gone with the action it belonged to. There is no similarity in this
        -- schema to discount by.
        RETURN 1.0 / (1 + n_ev);

    ELSIF t.kind = 'validate' THEN
        -- 32/D13 was closed by migration 015: a validate task names its
        -- finding, so this is a lookup rather than a scan of the subject.
        RETURN CASE WHEN EXISTS (
                 SELECT 1 FROM findings f
                  WHERE f.id = t.finding_id
                    AND f.status IN ('validated','reported','rejected'))
               THEN 0 ELSE 1 END;

    ELSIF t.kind = 'perform' THEN
        -- Ticket 152, found in the first live run that had a `perform` Task in
        -- it. Without this arm the function fell through to the closing
        -- `RETURN 0`, `cancel_reason_for`'s general rule read that as nothing
        -- left to learn, and every `perform` Task the pass derived was
        -- abandoned as `answered` before it could be offered once. `rk2hunt13`
        -- measured it exactly: T5 abandoned with 0 attempts, T6 pending and
        -- ready with `claimable_for = 'answered'`, and the lap that should
        -- have claimed T6 reported `nothing_to_execute`.
        --
        -- Shaped like `validate`'s and for the same reason: the Task names the
        -- Test it performs, so this is a lookup and not a scan of the subject.
        -- A specification nobody has walked is the whole of what is not yet
        -- known about it; once a replay is on file there is nothing further a
        -- second walk of the same actions could learn, which is also what
        -- `ready_for` says when it refuses `perform.already_performed`.
        RETURN CASE WHEN EXISTS (
                 SELECT 1 FROM test_replays tp WHERE tp.test_id = t.test_id)
               THEN 0 ELSE 1 END;

    ELSIF t.kind = 'conclude' THEN
        -- Ticket 156. A settled claim that no Finding rests on has one thing
        -- left to learn about it, and it is the thing this kind exists to
        -- write down: what the claim is a Finding OF. Once an edge in
        -- `finding_hypotheses` names it there is nothing further, and the
        -- second conclusion of one claim would be a merge into a row that is
        -- already open.
        RETURN CASE WHEN EXISTS (
                 SELECT 1 FROM finding_hypotheses fh
                  WHERE fh.hypothesis_id = t.hypothesis_id)
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
-- 4. The one cancellation that would kill it in the pass it was born in
-- ===========================================================================
--
-- `cancel_reason_for` ends a Task whose claim has settled: "a claim at
-- `supported` or `refuted` that nothing has re-opened is answered, and work
-- asking the same question again is a loop". Correct for every kind that
-- existed when it was written, and exactly backwards for this one -- a claim at
-- `supported` is the reason a `conclude` Task exists, so the arm would abandon
-- every one of them in step (2) of the same pass that derived them in step
-- (3e).
--
-- The exception is narrow and stays narrow. A `conclude` Task on a REFUTED
-- claim is still answered and still ends here: nothing rests a Finding on a
-- claim that settled the other way, and the arm is what stops one that was
-- derived before a retest turned the claim over.
--
-- Nothing else in this function changes, and the trailing novelty sweep is
-- left exactly as it was: section 3 gave the kind a real novelty, which is the
-- preferred half of the choice 152's `report` exception documents.

CREATE OR REPLACE FUNCTION cancel_reason_for(t tasks, w scheduler_weights) RETURNS text
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
        -- 034: a refutation suppresses equivalent work only while it is still
        -- current AND something on file settles it. An imported negative is
        -- neither, and `refresh_negative_knowledge` reopens the claim in step
        -- (1) of the same pass that reaches this check in step (2), so the
        -- suppression it would otherwise inherit never survives a pass.
        IF st = 'refuted'
           AND rk2_negative_standing(rk2_current_negative(t.hypothesis_id)) = 'settled' THEN
            RETURN 'settled_negative';
        END IF;
        SELECT EXISTS (SELECT 1 FROM hypothesis_retest_triggers x
                        WHERE x.hypothesis_id = t.hypothesis_id
                          AND x.fired_at IS NOT NULL) INTO fired;
        -- Ticket 156's one exception, written as what it is rather than as a
        -- kind list: a settled claim answers the work that was asking whether
        -- it holds, and `conclude` is not that work -- it is the work that
        -- writes down what the answer was. Only `supported`, because a refuted
        -- claim answers a conclusion too.
        IF st IN ('supported','refuted') AND NOT fired
           AND NOT (t.kind = 'conclude' AND st = 'supported') THEN
            RETURN 'answered';
        END IF;
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
-- 5. The frontier and the derivation
-- ===========================================================================
--
-- A ceiling of its own, and not the hunts' or the performances'. The three
-- numbers cap three different ends of one loop -- how much new work a pass may
-- open, how much authored work it may spend, and how many settled answers it
-- may write up -- and an operator throttling one has no reason to be
-- throttling the others.

ALTER TABLE scheduler_weights
    ADD COLUMN max_conclusions_derived_per_pass smallint NOT NULL DEFAULT 3
        CHECK (max_conclusions_derived_per_pass >= 0);

COMMENT ON COLUMN scheduler_weights.max_conclusions_derived_per_pass IS
  'How many `conclude` Tasks one ranking pass may open. 0 stops the derivation without stopping the pass, which is how an operator holds settled claims on file while they read them.';

-- The frontier, and every clause in it is a refusal `open_finding` would
-- otherwise make after the work.
--
-- `supported`, not superseded, subject in scope: arms 1, 2 and 3 of
-- `rk2_finding_refusal`, asked before a Task is opened rather than after a
-- child has spent its turns.
--
-- The settling transition is arm 7, and it is the clause that does real work
-- here. A claim can be `supported` without one -- an import, a human
-- correction, a transition citing no Receipt -- and `propose_finding` resolves
-- the run through exactly this join, so a claim with no such row would send the
-- hunter to be refused for a reason it cannot act on. The Task does not carry
-- the run: the claim names it, `propose_finding` looks it up the same way, and
-- a copy on the Task would be a second answer to a question the transition
-- already settles.
--
-- And no Finding on the claim yet, and no `conclude` Task naming it in any
-- status -- any status rather than a live one, for the reason the hunt frontier
-- gives: a Task that ran and finished is an answer, and deriving it again is a
-- loop.

CREATE FUNCTION rk2_finding_frontier(p_program_id uuid)
RETURNS TABLE (hypothesis_id uuid, subject_entity_id uuid, created_at timestamptz)
LANGUAGE sql STABLE AS $fn$
    SELECT h.id, h.subject_entity_id, h.created_at
      FROM hypotheses h
      JOIN entities e ON e.id = h.subject_entity_id AND e.program_id = h.program_id
     WHERE h.program_id = p_program_id
       AND h.status = 'supported'
       AND h.superseded_by IS NULL
       AND e.in_scope
       AND EXISTS (SELECT 1
                     FROM hypothesis_transitions ht
                     JOIN test_run_receipts trr ON trr.receipt_id = ht.receipt_id
                    WHERE ht.hypothesis_id = h.id
                      AND ht.from_status = 'testing'
                      AND ht.to_status = 'supported'
                      AND ht.actor_kind = 'runtime')
       AND NOT EXISTS (SELECT 1 FROM finding_hypotheses fh
                        WHERE fh.hypothesis_id = h.id)
       AND NOT EXISTS (SELECT 1 FROM tasks k
                        WHERE k.program_id = h.program_id
                          AND k.kind = 'conclude'
                          AND k.hypothesis_id = h.id);
$fn$;

COMMENT ON FUNCTION rk2_finding_frontier(uuid) IS
  'The claims of a Program that a replay settled at supported, that are still canonical, whose subject is in scope, that no Finding rests on, and that no `conclude` Task names in any status. Every clause is a refusal open_finding would otherwise make after the work.';

REVOKE ALL ON FUNCTION rk2_finding_frontier(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION rk2_finding_frontier(uuid) TO rk2_runtime;

CREATE FUNCTION derive_finding_claims() RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p        uuid := rk2_program_required();
    ceiling  smallint;
    n_wanted bigint := 0;
    n_tasks  bigint := 0;
BEGIN
    SELECT w.max_conclusions_derived_per_pass INTO ceiling
      FROM scheduler_weights w WHERE w.active;
    IF NOT FOUND THEN RAISE EXCEPTION 'no active scheduler_weights row'; END IF;

    SELECT count(*) INTO n_wanted FROM rk2_finding_frontier(p);

    -- Oldest claim first, for the reason the other two derivations order that
    -- way: these Tasks do not exist yet, so there is no ranking to prefer one
    -- by, and arrival order is the one deterministic answer -- which is what
    -- makes the ceiling reproducible.
    WITH wanted AS (
        SELECT fr.hypothesis_id, fr.subject_entity_id
          FROM rk2_finding_frontier(p) fr
         ORDER BY fr.created_at, fr.hypothesis_id
         LIMIT ceiling
    ), made AS (
        INSERT INTO tasks (program_id, kind, hypothesis_id, subject_entity_id)
        -- The subject rides along, and it is the claim's own. Every other kind
        -- names one, `ready_for` checks it is in scope before it looks at the
        -- kind at all, and a Task with none would be the only row in this table
        -- whose report could not say what it was about.
        SELECT p, 'conclude', w.hypothesis_id, w.subject_entity_id FROM wanted w
        RETURNING 1 AS one
    )
    SELECT count(*) INTO n_tasks FROM made;

    RETURN jsonb_build_object('candidates', n_wanted,
                              'derived', n_tasks,
                              'deferred', greatest(n_wanted - n_tasks, 0),
                              'ceiling', ceiling);
END $fn$;

COMMENT ON FUNCTION derive_finding_claims() IS
  'Opens up to max_conclusions_derived_per_pass `conclude` Tasks against settled claims no Finding rests on. The last step of the loop derive_hypothesis_hunts enters and derive_test_performances settles.';

REVOKE ALL ON FUNCTION derive_finding_claims() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION derive_finding_claims() TO rk2_runtime;


-- ===========================================================================
-- 6. The pass calls it
-- ===========================================================================

CREATE OR REPLACE FUNCTION rank_pass(p_trigger text DEFAULT 'timer') RETURNS jsonb
LANGUAGE plpgsql AS $rank$

DECLARE
    p            uuid := rk2_program_required();
    w            scheduler_weights%ROWTYPE;
    n_cancelled  bigint := 0;
    n_ranked     bigint := 0;
    n_fired      bigint := 0;
    v_retests    jsonb;
    edges        jsonb;
    unlocks      jsonb;
    hunts        jsonb;
    performances jsonb;
    conclusions  jsonb;
    by_reason    jsonb;
    top          jsonb;
    t0           timestamptz := clock_timestamp();
BEGIN
    SELECT * INTO w FROM scheduler_weights WHERE active;
    IF NOT FOUND THEN RAISE EXCEPTION 'no active scheduler_weights row'; END IF;

    -- (1) Retest re-entry. Decision 11: the pass owns it, because it is the
    -- only runtime step that reads the whole program. 034 moved the body out
    -- into `refresh_negative_knowledge`, which is where the kept refutations
    -- are and where 022's per-Application fingerprint comparison had to go; the
    -- pass keeps the decision about WHEN, which is what decision 11 was about.
    --
    -- It stays first, and that ordering is load-bearing twice over. A claim
    -- whose refutation stopped being current has to be out of `refuted` before
    -- step (2) reads its status, or the Task asking the question again is
    -- abandoned in the same pass that reopened it. And an imported refutation
    -- -- one nothing on file settles -- is reopened here before step (2) could
    -- ever read it as suppression.
    v_retests := refresh_negative_knowledge();
    n_fired   := (v_retests ->> 'reopened')::bigint;

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

    -- (3) Dependency edges, after cancellation and before ranking, for the
    -- same reason in both directions: a Task abandoned above must stop
    -- unlocking anything, and an edge derived below must be visible to the
    -- ranking in this pass rather than the next one.
    edges := derive_task_dependencies();

    -- (3b) Chain unlocks, after the edges for the first of those two reasons
    -- and before the ranking for the second. Not folded into (3): that function
    -- is 026's two rules over `ready_for` and this one creates Tasks, and a
    -- derivation that both restates a readiness predicate and mints rows would
    -- be two jobs sharing a name and a transaction-local licence.
    --
    -- The Tasks it creates are not put through (2). They cannot need it: the
    -- frontier will not name a subject off the Surface or a superseded
    -- hypothesis, and the other cancellation reasons are about a history a Task
    -- created moments ago does not have. The pass after this one asks anyway.
    unlocks := derive_chain_unlocks();

    -- (3c) Claims into work, after the chain unlocks and before the ranking,
    -- for the second of the two reasons above: a Task derived from a claim must
    -- be ranked in the pass that derived it or it waits a whole pass to be
    -- looked at. It runs after (3b) rather than before it because a chain
    -- unlock is a Task the corpus already knew how to want, and where both
    -- would name the same hypothesis the guard in either one sees the other's
    -- row and does not duplicate it -- whichever ran first.
    --
    -- Like (3b)'s Tasks, these are not put through (2). They cannot need it:
    -- the frontier will not name a subject off the Surface or a superseded
    -- claim, and the other cancellation reasons are about a history a Task
    -- created moments ago does not have. The pass after this one asks anyway.
    hunts := derive_hypothesis_hunts();

    -- (3d) The performances, after the hunts and before the ranking, for the
    -- third time in this function and the same two reasons. A Test authored by
    -- a hunt in the pass before this one is on file with nothing to perform it;
    -- this is what opens the Task that does. Not folded into (3c): that
    -- function grades claims and opens the work that produces a Test, and this
    -- one opens the work that spends one, which is the other end of the same
    -- loop and a different question about a different row.
    --
    -- Like (3b)'s and (3c)'s, these are not put through (2), and for the reason
    -- (3c) gives: a Task created moments ago has no history for a cancellation
    -- rule to read.
    performances := derive_test_performances();

    -- (3e) The conclusions, last of the four and for the same two reasons a
    -- fourth time. This one is the end of the loop rather than a step inside
    -- it: (3c) turns a claim into a question, (3d) spends the answer, and this
    -- opens the work that writes down what the answer was. Ticket 156 -- until
    -- it, a claim reached `supported` and the campaign stopped there, because
    -- `propose_finding` had no Task that would ever put a role holding it in
    -- front of a settled claim.
    --
    -- Not put through (2) either, and here that is not merely unnecessary but
    -- would be wrong: step (2) reads a `supported` claim as an answered
    -- question, and section 4 is what stops it reading these Tasks that way at
    -- all.
    conclusions := derive_finding_claims();

    -- (4) The ranking. One statement, eight components, no clock in it.
    WITH r AS (
        SELECT t.id,
               novelty_for(t)         AS novelty,
               cost_for(t, w)         AS estimated_cost,
               time_for(t, w)         AS estimated_time,
               safety_for(t, w)       AS safety_cost,
               confidence_for(t, w)   AS confidence,
               value_for(t, w)        AS direct_value,
               unlock_for(t, w)       AS direct_unlock,
               chain_unlock_for(t)    AS chain_unlock
          FROM tasks t
         WHERE t.program_id = p AND t.status = 'pending'
    ), u AS (
        UPDATE tasks t
           SET novelty = r.novelty,
               estimated_cost = r.estimated_cost,
               estimated_time = r.estimated_time,
               safety_cost = r.safety_cost,
               confidence_of_execution = r.confidence,
               direct_value = r.direct_value,
               chain_unlock_value = r.chain_unlock,
               unlock_value = least(r.direct_unlock + r.chain_unlock, 1.0),
               ranked_weights_version = w.version,
               -- NULL, not 0: an unestimated task must sink via NULLS LAST, and
               -- a task scored 0 is a different statement from one never scored
               priority = CASE
                   WHEN r.direct_value IS NULL THEN NULL
                   ELSE r.novelty * r.confidence
                        * (r.direct_value
                           + w.w_unlock * least(r.direct_unlock + r.chain_unlock, 1.0))
                        / greatest(w.w_tokens * r.estimated_cost
                                 + w.w_time   * r.estimated_time
                                 + w.w_safety * r.safety_cost, w.cost_floor)
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
                 'factors', task_rank_factors(t)) AS j
          FROM tasks t WHERE t.program_id = p AND t.status = 'pending'
          ORDER BY t.priority DESC NULLS LAST, t.created_at, t.id
          LIMIT 10) s;

    INSERT INTO events (program_id, type, actor_kind, payload)
    VALUES (p, 'scheduler.ranked', 'runtime', jsonb_build_object(
        'trigger', p_trigger,
        'weights_version', w.version,
        'candidates', n_ranked,
        'retests', v_retests,
        'abandoned_by_reason', by_reason,
        'dependency_edges', edges,
        'chain_unlocks', unlocks,
        'hypothesis_hunts', hunts,
        'test_performances', performances,
        'finding_claims', conclusions,
        'lane_slots', (SELECT coalesce(jsonb_object_agg(kind, live_slots), '{}'::jsonb)
                         FROM scheduler_lane_state WHERE program_id = p),
        'top', top,
        'further_omitted', greatest(n_ranked - 10, 0),
        'duration_ms', round(extract(epoch FROM clock_timestamp() - t0) * 1000)));

    RETURN jsonb_build_object('ranked', n_ranked, 'abandoned', n_cancelled,
                              -- `retests_fired` is 023's key and stays what it
                              -- was: how many claims re-entered. `retests` is
                              -- the breakdown behind it, so a caller can tell a
                              -- pass that reopened nothing because nothing moved
                              -- from one that reopened nothing because it found
                              -- nothing to reopen.
                              'retests_fired', n_fired,
                              'retests', v_retests,
                              'edges_derived', edges -> 'derived',
                              'edges_withdrawn', edges -> 'withdrawn',
                              'unlock_candidates', unlocks -> 'candidates',
                              'unlocks_derived', unlocks -> 'derived',
                              'unlocks_withdrawn', unlocks -> 'withdrawn',
                              'claims_graded', hunts -> 'graded',
                              'hunts_derived', hunts -> 'derived',
                              'hunts_deferred', hunts -> 'deferred',
                              'performances_derived', performances -> 'derived',
                              'performances_deferred', performances -> 'deferred',
                              'conclusions_derived', conclusions -> 'derived',
                              'conclusions_deferred', conclusions -> 'deferred');
END
 $rank$;


-- ===========================================================================
-- 7. The two verbs the runtime gained
-- ===========================================================================
--
-- 029's rule: a function the runtime may execute is a verb somebody declared,
-- and one it may execute without a row is a surface that grew by accident.

INSERT INTO runtime_verb_surface (verb, added_by, note) VALUES
  ('rk2_finding_frontier(uuid)', '156',
   'the settled claims no Finding rests on and no conclude Task names, which is what the derivation opens Tasks against'),
  ('derive_finding_claims()', '156',
   'opens the Tasks that write them up; called by rank_pass and by nothing else');
