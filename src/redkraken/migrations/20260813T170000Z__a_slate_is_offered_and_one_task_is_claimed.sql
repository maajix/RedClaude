-- ===========================================================================
-- Production harness 23 -- the Slate is offered, and one Task is claimed
-- ===========================================================================
--
-- 023 built the scheduler's ranking half and left the offer/claim half saying
-- the same thing twice. `rank_candidates` decides what may be offered with a
-- WHERE clause; `claim_task` decides whether it may still be taken with an
-- IF/ELSIF chain. Two spellings of one rule is the reason the two disagree
-- today, and every criterion of this ticket is about a place they disagree:
--
--   * the slate does not ask whether an Identity the Task needs is held, so a
--     Task whose confidence is 0 for exactly that reason is offered anyway;
--   * the claim does not ask whether the Task is still affordable, whether the
--     Identity is still free, or whether the slate it came off has expired --
--     the three things most likely to have moved between the offer and the
--     claim, because they are the three another run changes;
--   * choosing nothing took the first slate row without asking anything about
--     it, so a runtime that picked nothing got a refusal where the ticket asks
--     for the first STILL-VALID entry.
--
-- So the shape of this file is: say the rule once, have both callers read it,
-- and keep on the slate row what the offer decided rather than deriving it
-- again afterwards.
--
-- Nothing here reads the clock on the ranking path. Decision 12 makes that a
-- property of the function text, arm (g) of `check_scheduler_closure()` checks
-- it for the three factor functions, and this file extends the same textual
-- rule to every function the eligibility rule is now made of. The one clock
-- this file adds is in `claim_task`, which is not on that path: an offer has an
-- expiry, and asking whether it has passed is the whole of what an expiry is.


-- ---------------------------------------------------------------------------
-- 1. Whether an Identity the Task needs is held, said once
-- ---------------------------------------------------------------------------

-- `released_at IS NULL` and nothing else, which is 023's argument and not a new
-- one: an expired-but-unreleased lease is the sweep's problem, and putting
-- `expires_at > now()` here would put the clock inside the ranking pass.
--
-- This existed already, inside gate 2 of `confidence_for`, where the slate
-- filter could not see it. A Task whose Identity is held scores confidence 0
-- and is ranked last -- and then offered, because `rank_candidates` never asked.
-- Criterion 2 wants it not offered at all, which needs the rule somewhere both
-- halves can read.
CREATE FUNCTION identity_held_for(t tasks) RETURNS boolean
LANGUAGE sql STABLE AS $fn$
    SELECT EXISTS (
        SELECT 1 FROM hypotheses h
          JOIN identity_leases l
            ON l.identity_entity_id IN (h.identity_a_entity_id,
                                        h.identity_b_entity_id)
         WHERE h.id = t.hypothesis_id AND l.released_at IS NULL)
$fn$;

COMMENT ON FUNCTION identity_held_for(tasks) IS
    'Whether either Identity this Task''s Hypothesis names is under an '
    'unreleased Lease. The ranking half and the claim half both read it, so '
    'the two cannot come to different conclusions about the same Lease.';

-- Gate 2 of the ranking factor, now routed through the function above. Same
-- rule, same rows, same answer -- one place.
CREATE OR REPLACE FUNCTION confidence_for(t tasks, w scheduler_weights) RETURNS numeric
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
    IF identity_held_for(t) THEN RETURN 0; END IF;

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


-- ---------------------------------------------------------------------------
-- 2. What makes a Task claimable, said once
-- ---------------------------------------------------------------------------

-- NULL when the Task may be claimed right now, else the name of the condition
-- that refuses it. The name is the refusal string the runtime reports and the
-- one `scheduler.idle` reads, so the vocabulary is the same one 023 raised.
--
-- The order is the order the questions mean different things in, and it is
-- 023's order with three questions inserted:
--
--   1. `not_pending`         -- somebody else already has it
--   2. `cancel_reason_for`   -- permanent: it is never coming back
--   3. `ready_for`           -- not yet: it may come back
--   4. `not_ranked`          -- no cost has been computed for it
--   5. `unaffordable`        -- the run it would start does not fit the budget
--   6. `identity_held`       -- another run holds an Identity it needs
--   7. `lane_full`           -- transient, and about the lane, not the Task
--   8. `global_subagent_cap` -- transient, and about the Program
--
-- Cancellation is asked before readiness for 023's reason: both refuse, only
-- one is permanent, and a hunt Task whose Hypothesis is refuted reading
-- `hunt.hypothesis_not_testable` says "not yet" about work that is finished.
--
-- 4 is new and not a tightening in disguise. 023 spelled it as arithmetic --
-- `tokens_left >= estimated_cost * cost_reference_tokens` is NULL when the cost
-- is, and a NULL predicate drops the row -- so an unranked Task was already
-- unoffered, silently, and only when the budget was bounded. A Program with an
-- unbounded budget offered unranked Tasks and sorted them by a NULL priority.
--
-- No clock, on purpose: `rank_candidates` reads this, and criterion 1 says two
-- passes over fixed rows and a fixed weights version return the same order.
-- Slate expiry is therefore NOT here. It is a property of the offer, not of the
-- Task, and it lives in `claim_task` where the offer does.
CREATE FUNCTION claimable_for(t tasks, w scheduler_weights) RETURNS text
LANGUAGE plpgsql STABLE AS $fn$
DECLARE v text;
BEGIN
    -- `IS DISTINCT FROM`, not `<>`. `tasks.status` is NOT NULL, so the two
    -- agree about every row that exists -- and disagree about the row that does
    -- not: `NULL <> 'pending'` is NULL, the IF does not fire, and a Task nobody
    -- found would fall through every remaining question and come out claimable.
    IF t.status IS DISTINCT FROM 'pending' THEN RETURN 'not_pending'; END IF;

    v := cancel_reason_for(t, w);
    IF v IS NOT NULL THEN RETURN v; END IF;

    v := ready_for(t);
    IF v IS NOT NULL THEN RETURN v; END IF;

    IF t.estimated_cost IS NULL THEN RETURN 'not_ranked'; END IF;

    IF EXISTS (SELECT 1 FROM program_budget b
                WHERE b.program_id = t.program_id
                  AND b.tokens_left IS NOT NULL
                  AND b.tokens_left < t.estimated_cost * w.cost_reference_tokens) THEN
        RETURN 'unaffordable';
    END IF;

    IF identity_held_for(t) THEN RETURN 'identity_held'; END IF;

    IF NOT EXISTS (SELECT 1 FROM scheduler_lane_state s
                    WHERE s.program_id = t.program_id AND s.kind = t.kind
                      AND s.headroom > 0) THEN
        RETURN 'lane_full';
    END IF;

    IF (SELECT count(*) FROM tasks c
          JOIN effective_lane_capacity lc
            ON lc.program_id = c.program_id AND lc.kind = c.kind
          JOIN roles r ON r.role = lc.role
         WHERE c.program_id = t.program_id
           AND c.status IN ('claimed','running')
           AND r.runs_as = 'subagent') >= w.max_concurrent_subagents THEN
        RETURN 'global_subagent_cap';
    END IF;

    RETURN NULL;
END $fn$;

COMMENT ON FUNCTION claimable_for(tasks, scheduler_weights) IS
    'NULL when this Task may be claimed, else the name of the condition that '
    'refuses it. The offer filters on it and the claim re-asks it, so the '
    'snapshot the orchestrator was given and the decision the runtime commits '
    'cannot be answers to two different questions.';


-- ---------------------------------------------------------------------------
-- 3. The offer: the filter, and what it decided kept on the row
-- ---------------------------------------------------------------------------

-- `scheduler_weights` comes in as a CROSS JOIN and not as a CTE. `WITH w AS
-- (SELECT * FROM scheduler_weights ...)` yields an anonymous record, and
-- `claimable_for(t, w)` needs the named composite -- the CTE spelling fails to
-- resolve the function at all.
CREATE OR REPLACE FUNCTION rank_candidates()
RETURNS TABLE (task_id uuid, kind text, entitled boolean, rnk bigint)
LANGUAGE sql STABLE AS $fn$
    WITH cand AS (
            SELECT t.id, t.kind, t.priority, t.created_at, s.deficit
              FROM tasks t
              JOIN scheduler_lane_state s
                ON s.program_id = t.program_id AND s.kind = t.kind
              CROSS JOIN scheduler_weights w
             WHERE w.active
               AND t.program_id = rk2_program()
               AND claimable_for(t, w) IS NULL
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

-- The entitlement is a decision of the offer, so it is kept on the row the
-- offer wrote. 023 recomputed it afterwards, once per offered row, as
-- `s.ordinal <= (SELECT count(*) FROM rank_candidates() WHERE entitled)` --
-- true only because the slate is sorted by entitlement, and a re-derivation of
-- a fact the same function had just had in its hand.
ALTER TABLE task_slate
    ADD COLUMN entitled boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN task_slate.entitled IS
    'Whether this entry was placed by its lane''s min_slots deficit rather '
    'than by priority alone -- what the offer decided, kept rather than '
    'derived again by whoever reads the slate next.';

-- Dropped and recreated rather than replaced: the return type changes, and
-- `CREATE OR REPLACE` cannot change it.
--
-- `why_ready` goes. It was the constant `'ready'` for every row of every slate
-- ever offered, because a Task that is not ready is not on the slate -- a
-- column that cannot say anything else is not an explanation, it is a
-- restatement of the filter. `entitled` is the answer to the question it was
-- reaching for, and now it is on the row rather than recomputed.
DROP FUNCTION offer_slate();

CREATE FUNCTION offer_slate()
RETURNS TABLE (ordinal integer, task_label text, kind text, subject_label text,
               priority numeric, factors jsonb, entitled boolean,
               expires_at timestamptz)
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
    --
    -- The choice made against it goes the same way, and for the stronger
    -- version of the same reason: a pick that outlived the list it was made
    -- from is a choice between options the chooser can no longer see.
    UPDATE task_slate s SET consumed = true
     WHERE s.program_id = p AND NOT s.consumed;

    UPDATE task_picks k SET consumed = true
     WHERE k.program_id = p AND NOT k.consumed;

    INSERT INTO task_slate (slate_id, program_id, task_id, ordinal, entitled)
    SELECT sid, p, c.task_id,
           (row_number() OVER (ORDER BY c.entitled DESC, c.rnk))::integer,
           c.entitled
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
                              'confidence', round(t.confidence_of_execution, 6)),
           s.entitled,
           s.offered_at + w.slate_ttl
      FROM task_slate s
      JOIN tasks t ON t.id = s.task_id
      LEFT JOIN entities e ON e.id = t.subject_entity_id
     WHERE s.slate_id = sid
     ORDER BY s.ordinal;
END $fn$;

COMMENT ON FUNCTION offer_slate() IS
    'At most slate_size Tasks that are ready, role-compatible, lane-legal, '
    'affordable and identity-available, each with the factors it was ranked '
    'on, whether its lane''s deficit placed it, and when the offer expires.';


-- ---------------------------------------------------------------------------
-- 4. The orchestrator's choice is a row
-- ---------------------------------------------------------------------------

-- CONTEXT.md's **Slate**: "the runtime decides what may be chosen; the
-- orchestrator decides which; the runtime commits the claim." Three steps in
-- two processes -- the model runs inside an Agent boundary and cannot call
-- `claim_task`, which is a runtime verb -- so the middle step has to survive as
-- state between them, and this is that state. Ticket 18's roster has named it
-- since it was compiled: `mcp__rk2__pick_task` is `writes=("task_picks",)`,
-- and `tests/test_roster.py` carries the name as its one pending relation with
-- this ticket against it.
--
-- The row is a request and not a decision, which is why it is not on `tasks`.
-- A column there would be the model writing a canonical row, and every refusal
-- below would be a canonical row it had to be walked back out of.
CREATE TABLE task_picks (
    id         uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    slate_id   uuid NOT NULL,
    task_id    uuid NOT NULL,
    picked_at  timestamptz NOT NULL DEFAULT now(),
    consumed   boolean NOT NULL DEFAULT false,
    FOREIGN KEY (task_id, program_id) REFERENCES tasks (id, program_id)
);

-- One live choice per Program. Changing your mind is `pick_task` consuming the
-- old row, so "which one did it choose" has one answer rather than an ordering
-- question over rows with the same timestamp.
CREATE UNIQUE INDEX task_picks_outstanding_idx
    ON task_picks (program_id) WHERE NOT consumed;

COMMENT ON TABLE task_picks IS
    'Which entry of the offered Slate the orchestrator chose. A request the '
    'runtime re-decides, not a decision: the claim re-asks every eligibility '
    'condition and may refuse it.';

INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
    ('task_picks', 'program_id', 'program-scoped: the purge root');

-- `audit`, for `proposals`'s reason and not `task_slate`'s. A pick is not
-- recomputable from anything -- it is what a model decided -- and the Event
-- that stands for it is the claim it becomes, or the refusal it earns.
INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
    ('task_picks', 'audit',
     'the runtime record of having received a choice; the claim it becomes is what emits', '23');

GRANT SELECT, INSERT, UPDATE, DELETE ON task_picks TO rk2_runtime;

-- The orchestrator's verb. It refuses an off-slate label here, where the model
-- is still running and can be told, as well as in `claim_task`, where the
-- runtime is protected. Two checks of one statement, which is the arrangement
-- rather than two statements: the label is resolved against the outstanding
-- slate both times, and `task_picks.slate_id` records which list it was
-- resolved against so the claim can tell a live choice from an outlived one.
CREATE FUNCTION pick_task(p_task_label text) RETURNS text
LANGUAGE plpgsql AS $fn$
DECLARE
    p       uuid := rk2_program_required();
    v_slate uuid;
    v_task  uuid;
BEGIN
    SELECT s.slate_id, s.task_id INTO v_slate, v_task
      FROM task_slate s JOIN tasks t ON t.id = s.task_id
     WHERE s.program_id = p AND NOT s.consumed AND t.label = p_task_label;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'task % is not on the current slate', p_task_label
            USING ERRCODE = 'check_violation';
    END IF;

    UPDATE task_picks k SET consumed = true
     WHERE k.program_id = p AND NOT k.consumed;

    INSERT INTO task_picks (program_id, slate_id, task_id)
    VALUES (p, v_slate, v_task);
    RETURN p_task_label;
END $fn$;

COMMENT ON FUNCTION pick_task(text) IS
    'Records which offered Task the orchestrator chose, superseding any '
    'earlier choice. Refuses a label the current Slate does not carry.';


-- ---------------------------------------------------------------------------
-- 5. The claim: one re-validating transaction, under the advisory lock
-- ---------------------------------------------------------------------------

-- 023's structure, kept: `pg_advisory_xact_lock(program)` serialises the
-- counting window, because `SKIP LOCKED` stops two transactions taking the same
-- ROW and does nothing about six transactions each counting the same headroom
-- and each concluding there is room.
--
-- Three things are different.
--
-- The re-validation is `claimable_for` rather than a chain that restates most
-- of `rank_candidates`. That is criterion 3 -- "rechecks every eligibility
-- condition" is only checkable against a list of conditions that exists
-- somewhere, and 023's chain omitted affordability and identity availability
-- precisely because there was no list to be measured against.
--
-- The slate has an expiry and the claim enforces it. `offer_slate` has returned
-- `offered_at + slate_ttl` since 023 and nothing ever compared it to anything,
-- so an orchestrator that thought about a slate for an hour claimed off it. The
-- check is on the whole outstanding slate rather than per row, because
-- `offer_slate` writes one slate at a time and its rows share an `offered_at`.
--
-- Choosing nothing walks the slate. Decision 3 says the runtime takes position
-- 1 when the orchestrator picks nothing; criterion 5 says the first STILL-VALID
-- entry. Those differ only when position 1 stopped being claimable between the
-- offer and the claim, which is the case the re-validation exists for -- and
-- there the older reading refuses a claim while four claimable Tasks sit on the
-- slate. Walking is not a second scheduler: the order is the offer's own, and
-- the runtime takes the first entry the ONE eligibility rule still admits.
--
-- A choice does not walk. A model that named a Task and got a different one
-- would be told nothing about the substitution, so a pick that has gone stale
-- is a refusal -- criterion 4, and 023's own argument for refusing an off-slate
-- label. Ticket 18's roster comment says the opposite ("it falls through to the
-- next slate entry when the choice has gone stale"); it was written before this
-- ticket and this ticket owns the behaviour, so the comment is corrected rather
-- than implemented.
--
-- Three ways in, in this order: the caller names one, the orchestrator's
-- outstanding pick names one, or nobody named one. The argument comes first
-- because it is the runtime speaking for itself, and a runtime that asked the
-- model's row what it meant to do would have no way to claim anything else.
CREATE OR REPLACE FUNCTION claim_task(p_task_label text DEFAULT NULL)
RETURNS text LANGUAGE plpgsql AS $fn$
DECLARE
    p         uuid := rk2_program_required();
    w         scheduler_weights%ROWTYPE;
    v_task    tasks%ROWTYPE;
    v_entry   record;
    v_id      uuid;
    v_offered timestamptz;
    v_role    text;
    v_runs_as text;
    v_clamp   boolean;
    v_model   text;
    v_effort  text;
    v_run     uuid;
    v_reason  text;
BEGIN
    SELECT * INTO w FROM scheduler_weights WHERE active;

    -- Everything after this point is inside the counting window.
    PERFORM pg_advisory_xact_lock(hashtextextended(p::text, 0));

    -- The offer expired. Refused rather than silently re-offered: the caller
    -- asked to commit a choice it made against a list, and the honest answer is
    -- that the list is gone. The loop answers this by offering again.
    SELECT min(s.offered_at) INTO v_offered
      FROM task_slate s WHERE s.program_id = p AND NOT s.consumed;
    IF v_offered IS NOT NULL AND v_offered + w.slate_ttl < now() THEN
        RAISE EXCEPTION 'the slate offered at % expired after %', v_offered, w.slate_ttl
            USING ERRCODE = 'check_violation';
    END IF;

    v_id := NULL;
    IF p_task_label IS NOT NULL THEN
        SELECT s.task_id INTO v_id
          FROM task_slate s JOIN tasks t ON t.id = s.task_id
         WHERE s.program_id = p AND NOT s.consumed AND t.label = p_task_label;
        IF NOT FOUND THEN
            -- Off-slate, cross-Program and already-consumed all arrive here,
            -- and all three are the same refusal: the Program is a predicate on
            -- `task_slate` and `rk2_program_required()` is where it comes from,
            -- so another Program's label is a label this Program was never
            -- offered.
            RAISE EXCEPTION 'task % is not on the current slate', p_task_label
                USING ERRCODE = 'check_violation';
        END IF;
    ELSE
        SELECT k.task_id INTO v_id
          FROM task_picks k WHERE k.program_id = p AND NOT k.consumed;
        IF FOUND AND NOT EXISTS (
             SELECT 1 FROM task_slate s
              WHERE s.program_id = p AND NOT s.consumed AND s.task_id = v_id) THEN
            -- The pick outlived its entry. `offer_slate` consumes both together
            -- so a new offer cannot leave one behind; what reaches here is a
            -- choice whose Task was claimed by something else off the same
            -- slate, which is the stale choice criterion 4 names.
            RAISE EXCEPTION 'the choice recorded for this program is no longer on the slate'
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;

    IF v_id IS NOT NULL THEN
        -- The slate is a suggestion that was true when it was computed. This is
        -- the check that makes it true when it is acted on, under the row lock
        -- so that two claimants of one Task serialise here.
        SELECT t.* INTO v_task FROM tasks t WHERE t.id = v_id FOR UPDATE;
        v_reason := claimable_for(v_task, w);
        IF v_reason IS NOT NULL THEN
            -- No `UPDATE task_slate SET consumed` before this, deliberately.
            -- The RAISE aborts the transaction and would take the update with
            -- it, in this function and in any caller's subtransaction alike.
            -- Nothing needs it: `offer_slate()` consumes every outstanding row
            -- of the Program before it writes a new slate.
            RAISE EXCEPTION 'task % is no longer claimable: %', v_task.label, v_reason
                USING ERRCODE = 'check_violation';
        END IF;
    ELSE
        FOR v_entry IN
            SELECT s.task_id FROM task_slate s
             WHERE s.program_id = p AND NOT s.consumed
             ORDER BY s.ordinal
        LOOP
            SELECT t.* INTO v_task FROM tasks t WHERE t.id = v_entry.task_id FOR UPDATE;
            IF claimable_for(v_task, w) IS NULL THEN
                v_id := v_entry.task_id;
                EXIT;
            END IF;
        END LOOP;
        -- Nothing claimable, including nothing offered. NULL rather than a
        -- refusal: an empty slate is the queue being idle, and the runtime
        -- reports idleness through `scheduler_idle_report()`, which can say
        -- which predicate refused every Task. A raise here would make "nothing
        -- to do" indistinguishable from "the world moved under a choice".
        IF v_id IS NULL THEN RETURN NULL; END IF;
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

    -- The choice has been acted on, whichever entry the claim took. A pick left
    -- outstanding here would be read by the next claim as a choice about a Task
    -- that is already running.
    UPDATE task_picks SET consumed = true
     WHERE program_id = p AND NOT consumed;

    RETURN (SELECT label FROM agent_runs WHERE id = v_run);
END $fn$;

COMMENT ON FUNCTION claim_task(text) IS
    'Commits one choice off the current Slate, re-asking every eligibility '
    'condition inside the transaction that takes the Task. A named Task and a '
    'recorded pick are both refused when they have gone stale; with neither, '
    'the Slate is walked in its own order and the first entry still admitted '
    'is taken.';


-- ---------------------------------------------------------------------------
-- 6. The scheduler surface is the runtime's, not the agent's
-- ---------------------------------------------------------------------------

-- Postgres grants EXECUTE on a new function to PUBLIC, so 023's loop is re-run
-- over the three functions this file adds and the one it dropped and recreated.
--
-- `pick_task` is on this list too, and it is the one that could look like it
-- belongs to the agent. It does not: the roster's `mcp__rk2__pick_task` is a
-- tool the runtime SERVES, and the handler behind it runs in the runtime's own
-- process against the runtime's own connection. A model that could reach this
-- function directly would be one that could pick for another Program.
DO $$
DECLARE f text;
BEGIN
    FOREACH f IN ARRAY ARRAY[
        'identity_held_for(tasks)', 'claimable_for(tasks,scheduler_weights)',
        'offer_slate()', 'pick_task(text)']
    LOOP
        EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC', f);
        EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO rk2_runtime', f);
    END LOOP;
END $$;


-- ---------------------------------------------------------------------------
-- 7. The standing check
-- ---------------------------------------------------------------------------

-- What the offer and the claim can get wrong, as rows. Three arms are textual,
-- for the reason arm (g) of `check_scheduler_closure()` is: the properties are
-- properties of what the functions are made of, and a later edit that quietly
-- takes one out is exactly what a standing check is for.
CREATE FUNCTION check_slate_claim()
RETURNS TABLE (problem text, subject text, detail text)
LANGUAGE sql STABLE AS $fn$
    -- (a) decision 12, extended to everything the eligibility rule is made of.
    --     023 checked the three factor functions; the filter now also runs
    --     `ready_for`, `cancel_reason_for`, `claimable_for` and
    --     `identity_held_for`, and a clock in any of them makes two passes over
    --     the same rows disagree just as thoroughly. Comments are stripped
    --     first, or the check fires on the comment explaining its own absence.
    SELECT 'eligibility_reads_the_clock', p.proname,
           'a function the ranking filter runs reads the wall clock'
      FROM pg_proc p
     WHERE p.pronamespace = 'public'::regnamespace
       AND p.proname IN ('ready_for','cancel_reason_for','identity_held_for',
                         'claimable_for','rank_candidates')
       AND regexp_replace(p.prosrc, '--[^' || chr(10) || ']*', '', 'g')
           ~* '(now\(\)|current_timestamp|clock_timestamp)'

  UNION ALL
    -- (b) both halves read the one rule. This is the defect the file exists to
    --     close: a caller that stops calling `claimable_for` has gone back to
    --     spelling the rule itself, and the two spellings drift silently
    --     because nothing ever compares them.
    SELECT 'eligibility_rule_not_shared', p.proname,
           'the offer or the claim decides eligibility without claimable_for'
      FROM pg_proc p
     WHERE p.pronamespace = 'public'::regnamespace
       AND p.proname IN ('rank_candidates','claim_task')
       AND p.prosrc !~ 'claimable_for'

  UNION ALL
    -- (c) the claim enforces the expiry the offer advertises. `offer_slate`
    --     returned `offered_at + slate_ttl` for a whole ticket before anything
    --     compared it to anything, which is an expiry only in the sense that it
    --     was printed.
    SELECT 'claim_ignores_slate_expiry', 'claim_task',
           'claim_task never reads slate_ttl, so the offer''s expiry is decorative'
      FROM pg_proc p
     WHERE p.pronamespace = 'public'::regnamespace AND p.proname = 'claim_task'
       AND p.prosrc !~ 'slate_ttl'

  UNION ALL
    -- (d) an offer is bounded. `slate_size` bounds the INSERT and
    --     `task_slate.ordinal` is `CHECK (1..5)`, so this can only fail if
    --     something other than `offer_slate` wrote the slate. Asked of the
    --     outstanding offer only: a `slate_size` an operator lowered would make
    --     every slate ever offered above the new number a violation, and a
    --     slate that has already been claimed off is not an offer any more.
    SELECT 'slate_larger_than_the_offer', s.slate_id::text,
           count(*)::text || ' entries against a slate_size of '
             || (SELECT w.slate_size::text FROM scheduler_weights w WHERE w.active)
      FROM task_slate s
     WHERE NOT s.consumed
     GROUP BY s.slate_id
    HAVING count(*) > (SELECT w.slate_size FROM scheduler_weights w WHERE w.active)

  UNION ALL
    -- (e) one Program, one outstanding offer. `offer_slate` consumes every
    --     unconsumed row before it writes, so two live slates would mean two
    --     lists the claim could take from and an ordinal 1 that names two
    --     Tasks -- the ambiguity criterion 5's fallback would resolve by
    --     accident.
    SELECT 'two_outstanding_slates', s.program_id::text,
           count(DISTINCT s.slate_id)::text || ' unconsumed slates in one Program'
      FROM task_slate s
     WHERE NOT s.consumed
     GROUP BY s.program_id
    HAVING count(DISTINCT s.slate_id) > 1

  UNION ALL
    -- (f) a claimed Task is off the slate. `claim_task` consumes the entry it
    --     took; an entry left outstanding for a Task that is running is an
    --     offer of work already in flight, and the next claim would refuse it
    --     as `not_pending` having walked past nothing.
    SELECT 'claimed_task_still_offered', t.label,
           'status ' || t.status || ' with an unconsumed slate entry'
      FROM task_slate s JOIN tasks t ON t.id = s.task_id
     WHERE NOT s.consumed AND t.status IN ('claimed','running')

  UNION ALL
    -- (g) a recorded choice is a choice off a list. `pick_task` resolves the
    --     label against the outstanding slate and stores which slate it
    --     resolved against, so a pick naming a pair that was never offered
    --     together means something else wrote the row.
    SELECT 'pick_names_an_unoffered_task', k.id::text,
           'a recorded choice whose Task was not on the Slate it names'
      FROM task_picks k
     WHERE NOT EXISTS (SELECT 1 FROM task_slate s
                        WHERE s.slate_id = k.slate_id AND s.task_id = k.task_id)

  UNION ALL
    -- (h) 023's arm (i), extended to the functions this file adds.
    SELECT 'scheduler_function_public_executable', p.proname,
           'an agent-reachable role can call a scheduler function'
      FROM pg_proc p
     WHERE p.pronamespace = 'public'::regnamespace
       AND p.proname IN ('identity_held_for','claimable_for','offer_slate','pick_task')
       AND has_function_privilege('public', p.oid, 'EXECUTE')
$fn$;

REVOKE ALL ON FUNCTION check_slate_claim() FROM PUBLIC;

COMMENT ON FUNCTION check_slate_claim() IS
    'What an offer, a choice and a claim can get wrong: a clock on the ranking '
    'path, a caller that stopped reading the shared eligibility rule, an '
    'expiry nothing enforces, a Slate that is unbounded, doubled or stale, and '
    'a choice made against a list that never carried it.';

INSERT INTO standing_checks(name, query, owner_ticket, note) VALUES
    ('slate_claim', 'SELECT * FROM check_slate_claim()', '23',
     'the offer and the claim read one clock-free eligibility rule, and a Program has at most one outstanding, bounded, unclaimed Slate with at most one live choice off it');


-- ---------------------------------------------------------------------------
-- 8. The invariants this file must not have broken
-- ---------------------------------------------------------------------------

-- The eligibility rule refuses a Task that does not exist rather than admitting
-- it. A NULL row through a plpgsql function is the shape a missing FROM clause
-- produces, and `claimable_for` returning NULL for it would mean "claimable".
DO $$
DECLARE v text;
BEGIN
    SELECT claimable_for(NULL::tasks, w) INTO v FROM scheduler_weights w WHERE w.active;
    IF v IS DISTINCT FROM 'not_pending' THEN
        RAISE EXCEPTION 'ph2-23: claimable_for(NULL) answered %, not not_pending', v;
    END IF;
END $$;

SELECT apply_state_rls();

DO $$
DECLARE n integer; d text;
BEGIN
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_program_isolation();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-23 breaks program isolation (% problems): %', n, d;
    END IF;

    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_scheduler_closure();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-23 breaks scheduler closure (% problems): %', n, d;
    END IF;

    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_slate_claim();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-23 refuses to finish: % slate violation(s): %', n, d;
    END IF;
END $$;
