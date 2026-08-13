-- ---------------------------------------------------------------------------
-- 20260813T235500Z__rank_by_value_cost_and_what_it_unlocks.sql        (PH2-26)
--
-- 023 gave the scheduler a priority with four things in it: novelty,
-- confidence, the model's two estimates, and tokens. It is auditable and it is
-- deterministic, and it is also blind in three directions the spec names.
--
--   * Tokens are not the whole cost. A Task that costs little and takes twenty
--     minutes of an engagement's wall time is not cheap, and a Task whose kind
--     has historically needed approval-class tool calls costs the operator
--     attention that no token count records.
--   * Nothing in the formula knows that one Task makes others possible. A
--     recon Task on a subject three analyze Tasks are waiting on scores on its
--     own merits and loses to a rich hunt, and the three stay unready forever.
--   * The weights themselves are one mutable row. Changing them rewrote what
--     every past Ranking pass is read back as, because nothing recorded which
--     numbers produced a priority.
--
-- This file closes all three, and the shape is: components on the row they are
-- about, weights that are a version rather than a setting, and unlock value
-- that comes from edges something can be held to.
--
--   * seven factor columns on `tasks`, each written by the pass that ranked it,
--     beside the version of the weights that ranked it;
--   * `value_for`, `time_for`, `safety_for` and `unlock_for`, joining
--     `novelty_for`, `cost_for` and `confidence_for` -- all STABLE, all
--     clock-free, all bounded, because decision 12 says a pass is a function of
--     rows and a weights version and nothing else;
--   * `task_dependencies` and the vocabulary of bases that says which edges may
--     move a priority at all -- an edge nothing derives is worth zero, not a
--     guess in either direction;
--   * versioned weights, immutable once written, and one operator verb that
--     supersedes rather than edits.
--
-- The unlock term here is DIRECT: one edge, one dependent Task, counted once.
-- Marginal unlock -- what a Task adds over what is already coming, and the
-- chain-derived edges that make that question worth asking -- is ticket 41,
-- which is blocked by this file and by 40.
-- ---------------------------------------------------------------------------


-- ---------------------------------------------------------------------------
-- 1. Weights are a version, and a version is immutable
-- ---------------------------------------------------------------------------
-- Criterion 5 is two statements, and only the second one is hard. Versioning
-- weights is a primary key that already existed. Not rewriting historical
-- passes means an UPDATE of a weights row has to be refused, because a past
-- `scheduler.ranked` event names its weights by version and nothing else --
-- edit version 1 in place and every pass ever recorded now claims to have been
-- produced by numbers that did not exist when it ran.

ALTER TABLE scheduler_weights
    -- The effort a Task costs, as three shares that sum to one. Version 1's
    -- defaults are the old formula exactly: tokens at full weight, the other
    -- two at zero. The row is not being changed, it is being spelled out.
    ADD COLUMN w_tokens               numeric NOT NULL DEFAULT 1,
    ADD COLUMN w_time                 numeric NOT NULL DEFAULT 0,
    ADD COLUMN w_safety               numeric NOT NULL DEFAULT 0,
    -- What a unit of unlocked value is worth against a unit of direct value.
    -- Zero on version 1, for the same reason.
    ADD COLUMN w_unlock               numeric NOT NULL DEFAULT 0,
    ADD COLUMN time_reference_seconds numeric NOT NULL DEFAULT 900,
    ADD COLUMN time_prior             jsonb   NOT NULL DEFAULT
        '{"recon":0.30,"hunt":0.60,"analyze":0.40,"validate":0.25,"report":0.40}'::jsonb,
    ADD COLUMN safety_prior           numeric NOT NULL DEFAULT 0.5;

-- The shares are constrained to sum to one, and that is what makes the
-- priority's denominator bounded by construction: `cost_for` and `time_for`
-- return a number in [cost_floor, 1] and `safety_for` one in [0, 1], so any
-- convex combination of the three is in [0, 1] -- and the `greatest(...,
-- cost_floor)` around the whole denominator is what keeps it off zero when the
-- only term with weight is the one that may be zero. Safety is floored at zero
-- and not at `cost_floor` deliberately: a kind whose runs have never needed a
-- privileged call cost the operator no attention, and a floor would charge it
-- for attention it never took.
--
-- Without the sum an operator can set three weights of 5 and produce a formula
-- whose numbers no longer compare across Programs, which is the failure mode a
-- normalised component was introduced to prevent. `w_gain + w_impact = 1` is
-- the same constraint on the numerator, and it is what makes `value_for` a
-- normalised value rather than a weighted sum that happens to be small.
ALTER TABLE scheduler_weights
    ADD CONSTRAINT scheduler_weights_value_shares_ck
        CHECK (w_gain + w_impact = 1),
    ADD CONSTRAINT scheduler_weights_effort_shares_ck
        CHECK (w_tokens + w_time + w_safety = 1),
    ADD CONSTRAINT scheduler_weights_shares_nonneg_ck
        CHECK (w_gain >= 0 AND w_impact >= 0
           AND w_tokens >= 0 AND w_time >= 0 AND w_safety >= 0),
    ADD CONSTRAINT scheduler_weights_unlock_ck
        CHECK (w_unlock >= 0 AND w_unlock <= 1),
    ADD CONSTRAINT scheduler_weights_safety_prior_ck
        CHECK (safety_prior >= 0 AND safety_prior <= 1),
    ADD CONSTRAINT scheduler_weights_time_reference_ck
        CHECK (time_reference_seconds > 0);

COMMENT ON COLUMN scheduler_weights.w_tokens IS
  'The share of a Task''s effort that its token cost accounts for. With w_time and w_safety it sums to one, so the denominator of a priority stays in [cost_floor, 1] whatever an operator sets.';
COMMENT ON COLUMN scheduler_weights.w_time IS
  'The share of effort that elapsed run time accounts for. Zero on version 1, which is what makes version 1 the formula 023 shipped.';
COMMENT ON COLUMN scheduler_weights.w_safety IS
  'The share of effort that the risk class of the tool calls a kind has historically needed accounts for -- the operator attention a Task costs, which no token count records.';
COMMENT ON COLUMN scheduler_weights.w_unlock IS
  'What a unit of unlocked value is worth against a unit of direct value. At zero the scheduler is greedy; at one an unlocked path counts as much as the Task''s own.';
COMMENT ON COLUMN scheduler_weights.time_reference_seconds IS
  'The elapsed time that normalises to 1.0, as cost_reference_tokens does for tokens.';
COMMENT ON COLUMN scheduler_weights.time_prior IS
  'Task kind -> fraction of time_reference_seconds, used until that kind has run often enough in this Program to have a median of its own.';
COMMENT ON COLUMN scheduler_weights.safety_prior IS
  'The safety cost assumed for a kind with no measured tool calls behind it. Mid-scale on purpose: an unmeasured kind is neither known-harmless nor known-dangerous.';

CREATE FUNCTION scheduler_weights_is_immutable() RETURNS trigger
LANGUAGE plpgsql AS $fn$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION
            'scheduler weights version % is named by every Ranking pass it produced', OLD.version
            USING ERRCODE = 'restrict_violation',
                  HINT = 'deactivate it and insert a new version instead';
    END IF;
    IF to_jsonb(NEW) - 'active' IS DISTINCT FROM to_jsonb(OLD) - 'active' THEN
        RAISE EXCEPTION
            'scheduler weights version % may be activated or deactivated, not rewritten', OLD.version
            USING ERRCODE = 'restrict_violation',
                  HINT = 'SELECT version_scheduler_weights(''{"w_unlock": 0.5}''::jsonb)';
    END IF;
    RETURN NEW;
END $fn$;

CREATE TRIGGER scheduler_weights_versions_are_immutable
    BEFORE UPDATE OR DELETE ON scheduler_weights
    FOR EACH ROW EXECUTE FUNCTION scheduler_weights_is_immutable();

COMMENT ON FUNCTION scheduler_weights_is_immutable() IS
  'A weights version is what a recorded Ranking pass points at. Editing one in place changes what every past pass claims to have been produced by, which is the half of criterion 5 that is not free.';

-- The operator's verb. Copy the active row, apply the changes named, insert it
-- as the next version, and make it the active one -- in that order, because
-- `scheduler_weights_one_active` is a plain unique index and not deferrable.
--
-- SECURITY DEFINER and granted to `rk2_human` alone, the shape 026 uses for
-- every verb an operator holds and no model-reachable role may reach. Ticket 59
-- owns the CLI that calls it.
CREATE FUNCTION version_scheduler_weights(p_changes jsonb) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $fn$
DECLARE
    v_from  scheduler_weights%ROWTYPE;
    v_row   scheduler_weights%ROWTYPE;
    v_next  integer;
    v_bad   text;
BEGIN
    IF jsonb_typeof(p_changes) <> 'object' OR p_changes = '{}'::jsonb THEN
        RAISE EXCEPTION 'version_scheduler_weights takes a non-empty object of weights to change'
            USING ERRCODE = 'invalid_parameter_value';
    END IF;

    SELECT * INTO v_from FROM scheduler_weights WHERE active;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'no active scheduler_weights row to version from';
    END IF;

    -- A key this table does not have is a weight the operator thinks they set
    -- and did not: `jsonb_populate_record` ignores it silently, and the new
    -- version would be a copy of the old one wearing a new number.
    SELECT string_agg(k.key, ', ' ORDER BY k.key) INTO v_bad
      FROM jsonb_object_keys(p_changes) AS k(key)
     WHERE k.key IN ('version', 'active', 'created_at')
        OR NOT EXISTS (SELECT 1 FROM pg_attribute a
                        WHERE a.attrelid = 'scheduler_weights'::regclass
                          AND a.attnum > 0 AND NOT a.attisdropped
                          AND a.attname = k.key);
    IF v_bad IS NOT NULL THEN
        RAISE EXCEPTION 'not a weight this verb may set: %', v_bad
            USING ERRCODE = 'invalid_parameter_value',
                  HINT = 'version and active are the verb''s to decide';
    END IF;

    SELECT max(version) + 1 INTO v_next FROM scheduler_weights;
    v_row := jsonb_populate_record(v_from, p_changes);
    v_row.version    := v_next;
    v_row.active     := true;
    v_row.created_at := clock_timestamp();

    UPDATE scheduler_weights SET active = false WHERE active;
    INSERT INTO scheduler_weights VALUES (v_row.*);
    RETURN v_next;
END $fn$;

COMMENT ON FUNCTION version_scheduler_weights(jsonb) IS
  'Supersede the active weights with a new version carrying the changes named and the previous version''s value for everything else. The old row keeps its numbers, so the passes that cite it still read back as what they were.';

-- Three statements and not two. 029 set `ALTER DEFAULT PRIVILEGES FOR ROLE
-- rk2_owner ... GRANT EXECUTE ON FUNCTIONS TO rk2_runtime`, so every function
-- this file creates arrives with the runtime already on its ACL and revoking
-- PUBLIC does not take it off. Without the third line "granted to rk2_human
-- alone" is a comment the installation contradicts, and the connection a model
-- reaches through can reweight the scheduler.
REVOKE ALL ON FUNCTION version_scheduler_weights(jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION version_scheduler_weights(jsonb) FROM rk2_runtime, rk2_state;
GRANT EXECUTE ON FUNCTION version_scheduler_weights(jsonb) TO rk2_human;

-- What the verb deliberately does NOT do is run the passes. Criterion 5 says
-- changing the weights creates a new Ranking pass, and it does: `rank_pass`
-- recomputes every pending Task in the Program it is bound to under whichever
-- version is active, so the first pass after this statement is that new pass,
-- and it records itself as one.
--
-- The verb cannot be the thing that runs them. A pass is scoped to one Program
-- by `rk2_program_required` and by the row policies under it; the operator's
-- connection is bound to no Program, and there is no bound on how many are
-- open. A verb that ranked all of them would be an operator's UPDATE holding
-- write locks across every Program in the installation, taken by someone
-- changing a number. The loop already ranks before it offers, which is the
-- other half of why: a Task cannot be chosen under weights no pass has applied.

-- Version 2: the configuration this ticket exists to make possible. Tokens
-- still dominate effort, elapsed time and safety carry the rest, and an
-- unlocked path is worth half of a direct one. Version 1 keeps its numbers and
-- stops being active, which is the whole difference between versioning weights
-- and editing them.
--
-- Shipping it is not a policy this file invented for itself: version 1 prices
-- unlocking at zero, so an installation left on it can never satisfy criterion
-- 3 -- no Task ever outranks a richer one for what it unblocks, whatever the
-- edges say. The feature would be reachable only by an operator who read this
-- file. The numbers are the defensible ones and not the tuned ones: tokens keep
-- the majority they had, and half is what "an unlocked path counts, and counts
-- for less than the work in front of you" comes to.
-- Through the verb, not through an INSERT of its own: the operator's path and
-- the corpus's path being the same statement is what stops the two drifting,
-- and applying this file is then the first exercise of it.
SELECT version_scheduler_weights(jsonb_build_object(
    'w_tokens', 0.60, 'w_time', 0.25, 'w_safety', 0.15, 'w_unlock', 0.50));


-- ---------------------------------------------------------------------------
-- 2. The components, on the row they are about
-- ---------------------------------------------------------------------------
-- Criterion 1 says a rank result exposes its components. They are columns and
-- not a jsonb blob because `check_task_ranking` below asks whether any of them
-- is missing on a ranked Task, and a key absent from a document is not a
-- question a constraint can be asked.

ALTER TABLE tasks
    ADD COLUMN direct_value           numeric,
    ADD COLUMN estimated_time         numeric,
    ADD COLUMN safety_cost            numeric,
    ADD COLUMN unlock_value           numeric,
    ADD COLUMN ranked_weights_version integer REFERENCES scheduler_weights(version);

-- All four are bounded, because criterion 1 says a rank result exposes a
-- NORMALISED value and an unbounded number is not one. `tasks` has never
-- constrained `expected_information_gain` or `potential_impact` to a scale, so
-- the bound cannot be asserted of the estimates -- it is applied by `value_for`,
-- which clamps, and recorded here, which is the assertion that it did. Clamping
-- and not rejecting: a model's bad estimate should sink a Task's ranking, not
-- fail the pass that ranks every other Task in the Program.
ALTER TABLE tasks
    ADD CONSTRAINT tasks_direct_value_ck
        CHECK (direct_value IS NULL OR (direct_value >= 0 AND direct_value <= 1)),
    ADD CONSTRAINT tasks_estimated_time_ck
        CHECK (estimated_time IS NULL OR (estimated_time >= 0 AND estimated_time <= 1)),
    ADD CONSTRAINT tasks_safety_cost_ck
        CHECK (safety_cost IS NULL OR (safety_cost >= 0 AND safety_cost <= 1)),
    ADD CONSTRAINT tasks_unlock_value_ck
        CHECK (unlock_value IS NULL OR (unlock_value >= 0 AND unlock_value <= 1));

COMMENT ON COLUMN tasks.direct_value IS
  'The value of this Task on its own: the weighted combination of the model''s information-gain and impact estimates, normalised into [0, 1]. NULL when either estimate is absent, which is what sinks an unestimated Task rather than scoring it.';
COMMENT ON COLUMN tasks.estimated_time IS
  'Normalised elapsed time, from the median of what this kind has taken in this Program, shrunk toward the kind''s prior. The half of cost that tokens do not measure.';
COMMENT ON COLUMN tasks.safety_cost IS
  'Normalised risk class of the tool calls this kind has needed, shrunk toward safety_prior. What the Task costs the operator in attention rather than in budget.';
COMMENT ON COLUMN tasks.unlock_value IS
  'The value of the pending Tasks a sound dependency edge says this one unblocks, capped at one. Direct unlock only: what a Task adds over the unlocks already coming is ticket 41.';
COMMENT ON COLUMN tasks.ranked_weights_version IS
  'Which weights version produced the priority on this row. Without it a stored priority is a number nobody can reproduce, and reading two Programs'' queues together compares two formulas.';


-- ---------------------------------------------------------------------------
-- 3. Value -- what the model said the Task is worth
-- ---------------------------------------------------------------------------
-- Split out of `rank_pass` so that `unlock_for` can ask it of the OTHER Task,
-- which is the question the whole unlock term is made of.
--
-- The clamp is criterion 1's word "normalized". With `w_gain + w_impact = 1`
-- and estimates in [0, 1] it never fires; nothing constrains those estimates,
-- so it is what makes the claim true rather than customary.
--
-- The NULL arm is explicit and cannot be folded into the clamp: `greatest(NULL,
-- 0)` is 0 in SQL, not NULL, so clamping an absent estimate would silently
-- report a Task nobody estimated as one worth nothing -- which is the exact
-- distinction criterion 6 turns on.
CREATE FUNCTION value_for(t tasks, w scheduler_weights) RETURNS numeric
LANGUAGE sql STABLE AS $fn$
    SELECT CASE
        WHEN t.expected_information_gain IS NULL OR t.potential_impact IS NULL
            THEN NULL
        ELSE least(greatest(w.w_gain * t.expected_information_gain
                          + w.w_impact * t.potential_impact, 0), 1.0)
        END;
$fn$;

COMMENT ON FUNCTION value_for(tasks, scheduler_weights) IS
  'The Task''s own value under these weights, normalised into [0, 1], or NULL when either estimate is missing -- NULL and not zero, because an unestimated Task is a different statement from a worthless one.';


-- ---------------------------------------------------------------------------
-- 4. Time -- the same shape as cost, over a different measurement
-- ---------------------------------------------------------------------------
-- Deliberately `cost_for` with three words changed. The estimator is the one
-- ticket 34 settled: median over this Program's last `history_window_n`
-- completed runs of this (role, kind), shrunk toward a per-kind prior with
-- `shrinkage_n0` pseudo-observations, then normalised and bounded. A second
-- estimator with different behaviour at small N would make two components of
-- one formula disagree about what "little evidence" means.
--
-- Which is why the shrinkage itself is one function and not three copies of an
-- expression. 023 wrote it inline in `cost_for`; this file would have written it
-- twice more, and the three would then have been free to drift -- a `+ 1` in one
-- of them is a change no test compares against the other two, and every
-- component would still look bounded and behave differently at N = 0.
CREATE FUNCTION shrunk_toward(
    p_n integer, p_observed numeric, p_prior numeric, p_n0 numeric
) RETURNS numeric
LANGUAGE sql IMMUTABLE AS $fn$
    SELECT (coalesce(p_n, 0) * coalesce(p_observed, 0) + p_n0 * p_prior)
         / (coalesce(p_n, 0) + p_n0);
$fn$;

COMMENT ON FUNCTION shrunk_toward(integer, numeric, numeric, numeric) IS
  'One measurement of N observations, pulled toward a prior worth p_n0 pseudo-observations. The single definition of what "little evidence" means, so cost, time and safety cannot disagree about it.';

REVOKE ALL ON FUNCTION shrunk_toward(integer, numeric, numeric, numeric) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION shrunk_toward(integer, numeric, numeric, numeric)
    TO rk2_runtime;

-- 023's `cost_for`, rewritten around the helper and otherwise untouched: the
-- claim above is that all three components shrink the same way, and a claim
-- with one exception in it is not one.
CREATE OR REPLACE FUNCTION cost_for(t tasks, w scheduler_weights) RETURNS numeric
LANGUAGE plpgsql STABLE AS $fn$
DECLARE
    v_role text;
    med    numeric;
    n      integer;
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

    est := shrunk_toward(n, med,
                         coalesce((w.cost_prior ->> t.kind)::numeric, 0.5)
                             * w.cost_reference_tokens,
                         w.shrinkage_n0);
    RETURN least(greatest(est / w.cost_reference_tokens, w.cost_floor), 1.0);
END $fn$;

CREATE FUNCTION time_for(t tasks, w scheduler_weights) RETURNS numeric
LANGUAGE plpgsql STABLE AS $fn$
DECLARE
    v_role text;
    med    numeric;
    n      integer;
    est    numeric;
BEGIN
    SELECT m.role INTO v_role FROM role_task_kinds m WHERE m.kind = t.kind;

    SELECT count(*), percentile_cont(0.5) WITHIN GROUP (ORDER BY r.seconds)
      INTO n, med
      FROM (SELECT extract(epoch FROM (ar.finished_at - ar.started_at)) AS seconds
              FROM agent_runs ar
             WHERE ar.program_id = t.program_id
               AND ar.stop_reason = 'completed'
               AND ar.role = v_role
               AND ar.kind = t.kind
               AND ar.finished_at IS NOT NULL
             -- deterministic, as the token window is: started_at ties break by
             -- id, so two passes over the same rows read the same N
             ORDER BY ar.started_at DESC, ar.id DESC
             LIMIT w.history_window_n) r;

    est := shrunk_toward(n, med,
                         coalesce((w.time_prior ->> t.kind)::numeric, 0.5)
                             * w.time_reference_seconds,
                         w.shrinkage_n0);
    RETURN least(greatest(est / w.time_reference_seconds, w.cost_floor), 1.0);
END $fn$;

COMMENT ON FUNCTION time_for(tasks, scheduler_weights) IS
  'Normalised elapsed time for this Task''s kind in this Program, bounded to [cost_floor, 1]. A kind with no history is its prior, which is criterion 6''s bounded fallback.';


-- ---------------------------------------------------------------------------
-- 5. Safety -- what the kind has historically needed permission for
-- ---------------------------------------------------------------------------
-- The unit is the Agent run and not the Tool run, so that this component and
-- the other two count the same population and `shrinkage_n0` means one thing.
-- A run is scored by its WORST call: a run that made one approval-class request
-- among forty autonomous ones cost the operator a decision, and an average over
-- calls would report that run as nearly free.
--
-- A completed run with no Tool run scores zero, which is correct and not a
-- gap: it touched nothing.

CREATE FUNCTION safety_for(t tasks, w scheduler_weights) RETURNS numeric
LANGUAGE plpgsql STABLE AS $fn$
DECLARE
    v_role text;
    n      integer;
    mean   numeric;
BEGIN
    SELECT m.role INTO v_role FROM role_task_kinds m WHERE m.kind = t.kind;

    SELECT count(*), avg(r.worst) INTO n, mean
      FROM (SELECT coalesce((SELECT max(risk_rank(tr.risk_class))
                               FROM tool_runs tr
                              WHERE tr.agent_run_id = ar.id
                                AND tr.risk_class IS NOT NULL), 0)::numeric / 3
                   AS worst
              FROM agent_runs ar
             WHERE ar.program_id = t.program_id
               AND ar.stop_reason = 'completed'
               AND ar.role = v_role
               AND ar.kind = t.kind
             ORDER BY ar.started_at DESC, ar.id DESC
             LIMIT w.history_window_n) r;

    -- Floored at zero and not at `cost_floor`: a kind whose runs have never
    -- needed a privileged call costs the operator no attention, and charging it
    -- a floor would price attention nobody paid.
    RETURN least(greatest(shrunk_toward(n, mean, w.safety_prior, w.shrinkage_n0),
                          0), 1.0);
END $fn$;

COMMENT ON FUNCTION safety_for(tasks, scheduler_weights) IS
  'The mean worst risk class of this kind''s recent Agent runs, normalised over the four classes and shrunk toward safety_prior. Per run and not per Tool run: one approval-class call is what the run cost the operator.';


-- ---------------------------------------------------------------------------
-- 6. Dependency edges, and which of them may move a priority
-- ---------------------------------------------------------------------------
-- Criterion 4 is the reason this is two tables. An edge that nothing derives --
-- a model's opinion that finishing A would help B -- must contribute zero, and
-- zero is not the same as a small penalty or a small benefit. Both of those are
-- guesses, and both are reachable by a model that writes enough edges.
--
-- So the basis is a foreign key into a vocabulary that says, per basis, whether
-- the edge is sound. `unlock_for` joins that table. Nothing else decides.

CREATE TABLE task_dependency_bases (
    basis       text PRIMARY KEY,
    sound       boolean NOT NULL,
    description text NOT NULL
);

COMMENT ON TABLE task_dependency_bases IS
  'How a dependency edge came to be known, and whether that provenance is sound enough to move a priority. An unsound basis contributes zero unlock value -- not a penalty, not a discount.';

INSERT INTO task_dependency_bases (basis, sound, description) VALUES
    ('runtime_rule', true,
     'derived by derive_task_dependencies from the same predicate ready_for reports, and withdrawn by it when the rows stop supporting it'),
    ('proposed', false,
     'asserted by a model or an operator; recorded so the claim is visible, worth zero until a rule derives the same edge');

INSERT INTO program_global_tables (table_name, reason) VALUES
    ('task_dependency_bases', 'the vocabulary of dependency provenance, corpus-wide');

INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
    ('task_dependency_bases', 'reference',
     'the soundness vocabulary, changed only by migration', '26');

GRANT SELECT ON task_dependency_bases TO rk2_runtime;

-- The edges themselves. `predicate` is what makes criterion 3's "provably"
-- checkable: the edge names the `ready_for` string it claims to settle, so the
-- derivation can be withdrawn the moment the blocked Task is blocked on
-- something else instead. An edge that only said "A unlocks B" could never be
-- falsified by the rows.
CREATE TABLE task_dependencies (
    id                  uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id          uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    task_id             uuid NOT NULL,   -- the blocked Task
    unlocked_by_task_id uuid NOT NULL,   -- the Task that would unblock it
    basis               text NOT NULL REFERENCES task_dependency_bases(basis),
    predicate           text NOT NULL,
    derived_at          timestamptz NOT NULL DEFAULT now(),
    CHECK (task_id <> unlocked_by_task_id),
    UNIQUE (task_id, unlocked_by_task_id, basis),
    -- No delete action on either, which is 016's purge rule: the only edge that
    -- may cascade is the one to the purge root, and it is the one registered
    -- below. A Task is never deleted on its own in this schema, and a key that
    -- cascaded from one would be a second way for rows to leave a Program.
    FOREIGN KEY (task_id, program_id)             REFERENCES tasks (id, program_id),
    FOREIGN KEY (unlocked_by_task_id, program_id) REFERENCES tasks (id, program_id)
);

CREATE INDEX task_dependencies_unlocker_idx
    ON task_dependencies (program_id, unlocked_by_task_id);

COMMENT ON TABLE task_dependencies IS
  'One row per claim that finishing one Task would settle what another is waiting for. Unique per (blocked, unlocker, basis): a proposed edge cannot occupy the slot a runtime rule would derive, and so cannot suppress the sound version of itself.';

COMMENT ON COLUMN task_dependencies.predicate IS
  'The ready_for value this edge claims to settle. The derivation withdraws the edge when the blocked Task reports a different one, which is what keeps an edge from outliving its reason.';

INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
    ('task_dependencies', 'program_id', 'program-scoped: the purge root');

INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
    ('task_dependencies', 'derived',
     'recomputed from tasks and ready_for by every Ranking pass; scheduler.ranked records what they produced', '26');

GRANT SELECT, INSERT, DELETE ON task_dependencies TO rk2_runtime;

-- The runtime needs INSERT and DELETE here because the derivation runs as the
-- runtime. That grant, on its own, hands the whole of criterion 4 to whatever
-- can reach that connection: `basis` is a foreign key and nothing else, so one
-- INSERT naming `runtime_rule` buys a fabricated edge the full value of
-- everything it claims to unblock, and one DELETE suppresses a real one. The
-- vocabulary would be bound on exactly the role it has to bind.
--
-- So a sound basis is the derivation's to write, and the derivation says so by
-- setting a transaction-local flag around its own two statements -- the shape
-- 013 uses for `app.purging`, and for the same reason: the privilege is held by
-- a step, not by a role. A caller that wants to record a claim writes it with
-- basis `proposed`, which is what that basis is for.
--
-- DELETE has to consult `app.purging` as well, because a program-scoped table
-- with a BEFORE DELETE trigger that does not is a program nobody can purge --
-- 030 checks for precisely that.
CREATE FUNCTION task_dependencies_runtime_rule_is_derived() RETURNS trigger
LANGUAGE plpgsql AS $fn$
DECLARE
    v_basis text := CASE WHEN TG_OP = 'DELETE' THEN OLD.basis ELSE NEW.basis END;
BEGIN
    IF v_basis <> 'runtime_rule'
       OR coalesce(current_setting('app.deriving_dependencies', true), 'off') = 'on'
       OR (TG_OP = 'DELETE'
           AND coalesce(current_setting('app.purging', true), 'off') = 'on') THEN
        RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
    END IF;

    RAISE EXCEPTION
        'a runtime_rule dependency is derive_task_dependencies''s to write, not a caller''s'
        USING ERRCODE = 'insufficient_privilege',
              HINT = 'record the claim with basis ''proposed''; a rule derives the sound edge when the rows support it';
END $fn$;

CREATE TRIGGER task_dependencies_sound_basis_is_derived
    BEFORE INSERT OR UPDATE OR DELETE ON task_dependencies
    FOR EACH ROW EXECUTE FUNCTION task_dependencies_runtime_rule_is_derived();

COMMENT ON FUNCTION task_dependencies_runtime_rule_is_derived() IS
  'A sound basis is written by the derivation and by nothing else. Without this the GRANT the derivation needs is a way for anything holding the runtime connection to mint the unlock value of its choice.';

-- The derivation. Two rules today, both of them a restatement of a branch of
-- `ready_for`, and the table is the extension point for the rest.
--
-- Withdrawal comes first and is not optional: an edge whose blocked Task has
-- moved on, or is now blocked on something else, is a priority being paid to a
-- Task for work that is already done.
CREATE FUNCTION derive_task_dependencies() RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p         uuid := rk2_program_required();
    n_dropped bigint := 0;
    n_added   bigint := 0;
BEGIN
    -- Transaction-local, and switched back off below rather than left on for
    -- whatever the rest of the pass does. The licence belongs to these two
    -- statements.
    PERFORM set_config('app.deriving_dependencies', 'on', true);

    WITH gone AS (
        DELETE FROM task_dependencies d
         USING tasks b, tasks u
         WHERE d.program_id = p
           AND d.basis = 'runtime_rule'
           AND b.id = d.task_id           AND b.program_id = d.program_id
           AND u.id = d.unlocked_by_task_id AND u.program_id = d.program_id
           AND (b.status <> 'pending'
             OR u.status <> 'pending'
             OR ready_for(b) IS DISTINCT FROM d.predicate)
        RETURNING 1 AS one
    )
    SELECT count(*) INTO n_dropped FROM gone;

    WITH derived AS (
        -- An analyze Task with no agent-visible artifact on its subject, and
        -- the recon Task that would produce one. Same subject: reconnaissance
        -- elsewhere unblocks nothing here.
        SELECT b.id AS blocked, u.id AS unlocker, 'analyze.no_agent_visible_artifact'::text AS predicate
          FROM tasks b
          JOIN tasks u
            ON u.program_id = b.program_id
           AND u.kind = 'recon'
           AND u.status = 'pending'
           AND u.subject_entity_id = b.subject_entity_id
         WHERE b.program_id = p
           AND b.kind = 'analyze'
           AND b.status = 'pending'
           AND b.subject_entity_id IS NOT NULL
           AND ready_for(b) = 'analyze.no_agent_visible_artifact'
      UNION ALL
        -- A report Task waiting for a validated finding, and every pending
        -- validate Task in the Program. Not per subject: `report.
        -- no_validated_finding` is asked of the Program, so any validation
        -- settles it.
        SELECT b.id, u.id, 'report.no_validated_finding'::text
          FROM tasks b
          JOIN tasks u
            ON u.program_id = b.program_id
           AND u.kind = 'validate'
           AND u.status = 'pending'
         WHERE b.program_id = p
           AND b.kind = 'report'
           AND b.status = 'pending'
           AND ready_for(b) = 'report.no_validated_finding'
    ), added AS (
        INSERT INTO task_dependencies
            (program_id, task_id, unlocked_by_task_id, basis, predicate)
        SELECT p, d.blocked, d.unlocker, 'runtime_rule', d.predicate
          FROM derived d
        ON CONFLICT (task_id, unlocked_by_task_id, basis) DO NOTHING
        RETURNING 1 AS one
    )
    SELECT count(*) INTO n_added FROM added;

    PERFORM set_config('app.deriving_dependencies', 'off', true);
    RETURN jsonb_build_object('derived', n_added, 'withdrawn', n_dropped);
END $fn$;

COMMENT ON FUNCTION derive_task_dependencies() IS
  'Withdraw the runtime-derived edges the rows no longer support, then derive the ones they do. Called by rank_pass before ranking, for the reason cancellation is: an edge the pass does not refresh is one the pass pays for.';

REVOKE ALL ON FUNCTION derive_task_dependencies() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION derive_task_dependencies() TO rk2_runtime;

-- The unlock term. Sum over the DISTINCT pending Tasks a sound edge says this
-- one unblocks, capped at one so that no amount of downstream work makes a
-- single Task's numerator unbounded.
--
-- A dependent with no estimates contributes nothing: `value_for` returns NULL
-- and `sum` skips it. That is criterion 4's rule applied to the other axis --
-- an unmeasured dependent is not evidence of value, and inventing a number for
-- it would let unestimated work inflate the thing that is supposed to be
-- earned.
--
-- A dependent's value is SHARED between the pending Tasks that would settle it.
-- The report rule is where this stops being a nicety: `report.
-- no_validated_finding` is settled by any one validation, so ten pending
-- validate Tasks all name the same report Task, and crediting each of them with
-- the whole of it would hand out that value ten times for work one Task does.
-- Every validate Task in the Program would then outrank everything else on the
-- strength of a report nobody has written. Shared, the total credit paid for a
-- blocked Task is its value exactly once, however many Tasks could settle it.
--
-- The share is equal and not weighted by which unlocker is likelier to get
-- there: that is what a Task adds over the unlocks already coming, and it is
-- ticket 41's question, not this one's.
CREATE FUNCTION unlock_for(t tasks, w scheduler_weights) RETURNS numeric
LANGUAGE sql STABLE AS $fn$
    SELECT least(coalesce(sum(s.share), 0), 1.0)
      FROM (SELECT DISTINCT b.id,
                   value_for(b, w)
                     / greatest((SELECT count(DISTINCT d2.unlocked_by_task_id)
                                   FROM task_dependencies d2
                                   JOIN task_dependency_bases k2
                                     ON k2.basis = d2.basis AND k2.sound
                                   JOIN tasks u2
                                     ON u2.id = d2.unlocked_by_task_id
                                    AND u2.program_id = d2.program_id
                                  WHERE d2.task_id = b.id
                                    AND d2.program_id = b.program_id
                                    AND u2.status = 'pending'), 1) AS share
              FROM task_dependencies d
              JOIN task_dependency_bases k ON k.basis = d.basis AND k.sound
              JOIN tasks b ON b.id = d.task_id AND b.program_id = d.program_id
             WHERE d.unlocked_by_task_id = t.id
               AND d.program_id = t.program_id
               AND b.status = 'pending') s;
$fn$;

COMMENT ON FUNCTION unlock_for(tasks, scheduler_weights) IS
  'The value of the still-pending Tasks that sound edges say this one unblocks, each shared between the pending Tasks that could settle it, capped at one. An edge whose basis is not sound is not counted, and a dependent with no estimates contributes nothing rather than a guess.';

REVOKE ALL ON FUNCTION value_for(tasks, scheduler_weights) FROM PUBLIC;
REVOKE ALL ON FUNCTION time_for(tasks, scheduler_weights) FROM PUBLIC;
REVOKE ALL ON FUNCTION safety_for(tasks, scheduler_weights) FROM PUBLIC;
REVOKE ALL ON FUNCTION unlock_for(tasks, scheduler_weights) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION value_for(tasks, scheduler_weights)  TO rk2_runtime;
GRANT EXECUTE ON FUNCTION time_for(tasks, scheduler_weights)   TO rk2_runtime;
GRANT EXECUTE ON FUNCTION safety_for(tasks, scheduler_weights) TO rk2_runtime;
GRANT EXECUTE ON FUNCTION unlock_for(tasks, scheduler_weights) TO rk2_runtime;


-- ---------------------------------------------------------------------------
-- 7. The pass, with the other four factors in it
-- ---------------------------------------------------------------------------
-- First, what a rank result exposes -- one function, two callers. The event and
-- the Slate built the same five keys twice and had already drifted once: the
-- event rounded and the offer rounded differently. Criterion 1 is that a rank
-- result exposes its components, and one spelling of them is what keeps the two
-- readers agreeing about what they are.

CREATE FUNCTION task_rank_factors(t tasks) RETURNS jsonb
LANGUAGE sql STABLE AS $fn$
    SELECT jsonb_build_object(
        'novelty',         round(t.novelty, 6),
        'gain',            t.expected_information_gain,
        'impact',          t.potential_impact,
        'value',           round(t.direct_value, 6),
        'cost',            round(t.estimated_cost, 6),
        'time',            round(t.estimated_time, 6),
        'safety',          round(t.safety_cost, 6),
        'unlock',          round(t.unlock_value, 6),
        'confidence',      round(t.confidence_of_execution, 6),
        'weights_version', t.ranked_weights_version);
$fn$;

COMMENT ON FUNCTION task_rank_factors(tasks) IS
  'Every component of this Task''s priority and the weights version that combined them, in the one spelling the Slate and the scheduler.ranked event both report.';

REVOKE ALL ON FUNCTION task_rank_factors(tasks) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION task_rank_factors(tasks) TO rk2_runtime;

-- And then the formula:
--
--     priority = novelty * confidence * (value + w_unlock * unlock)
--                / max(w_tokens*cost + w_time*time + w_safety*safety, cost_floor)
--
-- Under version 1's weights this is the 023 formula character for character:
-- w_unlock is zero, w_tokens is one, and the other two contribute nothing. That
-- is deliberate. A formula change that cannot be shown to be a superset of the
-- one it replaces is a formula change nobody can review.
--
-- The clock stays out of it. `derive_task_dependencies` writes `derived_at`
-- through a column default, which is the same licence step (1) has for stamping
-- `fired_at`: the pass may record WHEN it ran, and may not READ it.
CREATE OR REPLACE FUNCTION rank_pass(p_trigger text DEFAULT 'timer') RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p            uuid := rk2_program_required();
    w            scheduler_weights%ROWTYPE;
    n_cancelled  bigint := 0;
    n_ranked     bigint := 0;
    n_fired      bigint := 0;
    edges        jsonb;
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

    -- (3) Dependency edges, after cancellation and before ranking, for the
    -- same reason in both directions: a Task abandoned above must stop
    -- unlocking anything, and an edge derived below must be visible to the
    -- ranking in this pass rather than the next one.
    edges := derive_task_dependencies();

    -- (4) The ranking. One statement, seven components, no clock in it.
    WITH r AS (
        SELECT t.id,
               novelty_for(t)         AS novelty,
               cost_for(t, w)         AS estimated_cost,
               time_for(t, w)         AS estimated_time,
               safety_for(t, w)       AS safety_cost,
               confidence_for(t, w)   AS confidence,
               value_for(t, w)        AS direct_value,
               unlock_for(t, w)       AS unlock_value
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
               unlock_value = r.unlock_value,
               ranked_weights_version = w.version,
               -- NULL, not 0: an unestimated task must sink via NULLS LAST, and
               -- a task scored 0 is a different statement from one never scored
               priority = CASE
                   WHEN r.direct_value IS NULL THEN NULL
                   ELSE r.novelty * r.confidence
                        * (r.direct_value + w.w_unlock * r.unlock_value)
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
        'retest_triggers_fired', n_fired,
        'abandoned_by_reason', by_reason,
        'dependency_edges', edges,
        'lane_slots', (SELECT coalesce(jsonb_object_agg(kind, live_slots), '{}'::jsonb)
                         FROM scheduler_lane_state WHERE program_id = p),
        'top', top,
        'further_omitted', greatest(n_ranked - 10, 0),
        'duration_ms', round(extract(epoch FROM clock_timestamp() - t0) * 1000)));

    RETURN jsonb_build_object('ranked', n_ranked, 'abandoned', n_cancelled,
                              'retests_fired', n_fired,
                              'edges_derived', edges -> 'derived',
                              'edges_withdrawn', edges -> 'withdrawn');
END $fn$;


-- ---------------------------------------------------------------------------
-- 8. What the audit reads
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION offer_slate()
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

    PERFORM supersede_pick(p);

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
           task_rank_factors(t),
           s.entitled,
           s.offered_at + w.slate_ttl
      FROM task_slate s
      JOIN tasks t ON t.id = s.task_id
      LEFT JOIN entities e ON e.id = t.subject_entity_id
     WHERE s.slate_id = sid
     ORDER BY s.ordinal;
END $fn$;


-- ---------------------------------------------------------------------------
-- 9. The check
-- ---------------------------------------------------------------------------
-- Textual where the invariant is about what a function may read, structural
-- where it is about rows. Both kinds are here because this ticket's two silent
-- failure modes are one of each: a clock inside a factor makes two replays of
-- the same rows disagree and nothing else would say so, and a priority stored
-- without the version that produced it is a number that reads as reproducible
-- and is not.

CREATE FUNCTION check_task_ranking()
RETURNS TABLE (problem text, subject text, detail text)
LANGUAGE sql STABLE AS $fn$
    -- (a) decision 12, extended to everything this file puts inside a pass --
    --     the four factors, the shrinkage under three of them, and the
    --     derivation the pass runs before it ranks. Comments are stripped
    --     first, as check_scheduler_closure's arm (g) does: the first version of
    --     that check fired on a comment explaining why the clock is absent.
    --
    --     `derive_task_dependencies` is in the list and its rows carry
    --     `derived_at`, which is not a contradiction: the default on the column
    --     stamps when the pass ran, and no branch of the function reads it.
    SELECT 'ranking_factor_reads_the_clock'::text, p.proname::text,
           'a Ranking pass step reads the clock; two replays of one set of rows would disagree'::text
      FROM pg_proc p
     WHERE p.pronamespace = 'public'::regnamespace
       AND p.proname IN ('value_for','time_for','safety_for','unlock_for',
                         'task_rank_factors','shrunk_toward',
                         'derive_task_dependencies')
       AND regexp_replace(p.prosrc, '--[^' || chr(10) || ']*', '', 'g')
           ~* '(now\(\)|current_timestamp|clock_timestamp)'
UNION ALL
    -- (b) no scheduler function is callable by PUBLIC, the rule 023 states for
    --     the three factors that existed then.
    SELECT 'scheduler_function_public_executable', p.proname::text,
           'a model-reachable role could call a scheduler function'
      FROM pg_proc p
     WHERE p.pronamespace = 'public'::regnamespace
       AND p.proname IN ('value_for','time_for','safety_for','unlock_for',
                         'task_rank_factors','shrunk_toward',
                         'derive_task_dependencies','check_task_ranking')
       AND has_function_privilege('public', p.oid, 'EXECUTE')
UNION ALL
    -- (c) criterion 4, as a property of the code rather than of today's rows.
    --     Dropping the join is the one edit that makes every proposed edge
    --     move a priority, and the rows it would corrupt look exactly like
    --     rows that were ranked correctly.
    SELECT 'unlock_ignores_the_basis_table', 'unlock_for',
           'unlock_for no longer joins task_dependency_bases; an unsound edge would be worth its full value'
      FROM pg_proc p
     WHERE p.pronamespace = 'public'::regnamespace
       AND p.proname = 'unlock_for'
       AND p.prosrc !~ 'task_dependency_bases'
UNION ALL
    -- (d) the vocabulary has to keep both answers. A basis table where
    --     everything is sound is the join in (c) with extra steps.
    SELECT 'dependency_basis_vocabulary_incomplete', 'task_dependency_bases',
           'the vocabulary no longer distinguishes a sound basis from an unsound one'
     WHERE NOT EXISTS (SELECT 1 FROM task_dependency_bases WHERE sound)
        OR NOT EXISTS (SELECT 1 FROM task_dependency_bases WHERE NOT sound)
UNION ALL
    -- (e) a priority nobody can reproduce.
    SELECT 'ranked_without_weights_version', t.label,
           'a stored priority with no weights version beside it'
      FROM tasks t
     WHERE t.priority IS NOT NULL AND t.ranked_weights_version IS NULL
UNION ALL
    -- (f) criterion 1, on the rows: a rank result exposes its components, so a
    --     ranked Task missing one is a result that cannot be audited.
    SELECT 'ranked_without_every_component', t.label,
           'a stored priority with a component missing under it'
      FROM tasks t
     WHERE t.priority IS NOT NULL
       AND (t.novelty IS NULL OR t.estimated_cost IS NULL
         OR t.estimated_time IS NULL OR t.safety_cost IS NULL
         OR t.confidence_of_execution IS NULL
         OR t.direct_value IS NULL OR t.unlock_value IS NULL)
UNION ALL
    -- (g) an edge that outlived its reason. The derivation withdraws these;
    --     this is the assertion that it ran.
    SELECT 'dependency_edge_predicate_stale', t.label,
           'a runtime-derived edge claims a predicate the blocked Task does not report'
      FROM task_dependencies d
      JOIN tasks t ON t.id = d.task_id AND t.program_id = d.program_id
     WHERE d.basis = 'runtime_rule'
       AND t.status = 'pending'
       AND ready_for(t) IS DISTINCT FROM d.predicate
UNION ALL
    -- (h) criterion 5's other half. The weights are what every priority in the
    --     installation is computed from, so the verb that moves them is the
    --     operator's -- and 029's default privileges hand every new function to
    --     the runtime, which means the revoke above is load-bearing and a
    --     DROP/CREATE of this function silently undoes it.
    SELECT 'weights_verb_reachable_by_the_runtime', p.proname::text,
           'a connection a model reaches through can version the scheduler weights'
      FROM pg_proc p
     WHERE p.pronamespace = 'public'::regnamespace
       AND p.proname = 'version_scheduler_weights'
       AND (has_function_privilege('rk2_runtime', p.oid, 'EXECUTE')
         OR has_function_privilege('rk2_state', p.oid, 'EXECUTE'))
UNION ALL
    -- (i) criterion 4 again, against the grant that makes it necessary. The
    --     runtime holds INSERT and DELETE on the edges because the derivation
    --     runs as the runtime; without the trigger, that grant is a way to mint
    --     a sound basis, and the vocabulary the other arms guard would be
    --     decoration.
    SELECT 'sound_basis_is_writable_by_hand', 'task_dependencies',
           'no trigger holds runtime_rule to the derivation; any holder of the runtime connection could mint unlock value'
     WHERE NOT EXISTS (
        SELECT 1 FROM pg_trigger g
          JOIN pg_proc p ON p.oid = g.tgfoid
         WHERE g.tgrelid = 'task_dependencies'::regclass
           AND NOT g.tgisinternal
           AND p.proname = 'task_dependencies_runtime_rule_is_derived')
$fn$;

COMMENT ON FUNCTION check_task_ranking() IS
  'The Ranking pass is a function of rows and a weights version: no factor reads the clock, no priority is stored without the version and the components that produced it, and only a basis something derives can move one.';

REVOKE ALL ON FUNCTION check_task_ranking() FROM PUBLIC;

INSERT INTO standing_checks (name, query, owner_ticket, note) VALUES
    ('task_ranking', 'SELECT * FROM check_task_ranking()', '26',
     'every priority is reproducible from its components and its weights version, and only sound edges move one');


-- ---------------------------------------------------------------------------
-- 10. Bring the corpus to true
-- ---------------------------------------------------------------------------
-- `task_dependencies` is program-scoped and therefore needs both policies; the
-- finalizer that writes them runs at the end of every migrate run, and calling
-- it here is what makes this file self-contained if someone applies it by hand.
SELECT apply_state_rls();
SELECT apply_state_grants();

DO $$
DECLARE n integer; d text;
BEGIN
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_task_ranking();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-26 refuses to finish: % ranking problem(s): %', n, d;
    END IF;

    -- The three neighbours this file reached into: the pass and the offer,
    -- whose functions it replaced, and the isolation rule, which the new
    -- program-scoped table has to satisfy.
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_scheduler_closure();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-26 breaks the scheduler closure (% problems): %', n, d;
    END IF;

    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_slate_claim();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-26 breaks the slate and the claim (% problems): %', n, d;
    END IF;

    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_program_isolation();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-26 breaks program isolation (% problems): %', n, d;
    END IF;
END $$;
