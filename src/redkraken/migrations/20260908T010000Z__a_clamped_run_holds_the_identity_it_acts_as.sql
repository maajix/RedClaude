-- ===========================================================================
-- Ticket 72 -- a clamped run holds the Identity it acts as
-- ===========================================================================
-- `roles.clamp_to_identity_leases` is set on one role, and the roster says what
-- it is for:
--
--     two hunters sharing one upstream slot is the session mixing that the
--     identity model exists to prevent.
--
-- Neither half of the enforcement was keyed on that sentence. Both were keyed
-- on the Hypothesis:
--
--   * `identity_held_for(tasks)` joins `hypotheses` and asks whether either of
--     the two Identity columns is under an unreleased Lease. A Hypothesis that
--     names neither answers "not held" for every claimant.
--   * `claim_task()` wrote the Leases under
--     `IF v_clamp AND v_task.hypothesis_id IS NOT NULL`, and then only for the
--     non-NULL of `identity_a_entity_id` and `identity_b_entity_id`.
--
-- The escaping population is the both-NULL one and not every NULL one, because
-- the old INSERT leased each non-NULL slot: a single-identity Hypothesis took
-- its one Lease and `identity_held_for` gated it. What took none is the
-- Hypothesis that names nobody, which is the ordinary unauthenticated hunt.
-- 018:26 measured the corpus this schema was drawn from and puts that case in a
-- larger bucket -- "49 of 55 investigations in the corpus have at least one NULL
-- identity slot -- every unauthenticated hypothesis, and every single-identity
-- one" -- without splitting the two, so the unauthenticated share is somewhere
-- at or below 49 in 55 and 018 does not say where. It is not a rare shape
-- either way, and `max_concurrent = 2` meant two such hunters through one
-- upstream slot -- exactly the sentence above, in the case it was written for.
--
-- The ticket's Why reaches the same hole by a route that is closed. It says a
-- `hunt` Task with no Hypothesis "takes no lease and passes no gate", and that
-- Task cannot be claimed at all: `claimable_for` asks `ready_for`, and
-- `ready_for` has returned `hunt.no_hypothesis` since 023:482. What is open is
-- the Task that HAS a Hypothesis which names nobody, which is the ordinary
-- unauthenticated hunt. The defect is the one the ticket describes; only the
-- row that reaches it is different.
--
-- The How offers two readings and prefers the second, which is what this
-- follows: the Identity requirement is a property of the TASK. A clamped Task
-- carries the Identities it will act as, `claim_task()` leases those, and
-- nothing in the claim path reads `hypotheses` for the question any more.
--
-- One thing follows from that which no criterion states and which the design
-- does not work without. If a clamped Task must name what it acts as, then an
-- unauthenticated hunt has to name something, and refusing it instead -- the
-- other end of criterion 2 -- would refuse every hunt that has not logged in,
-- which is where hunting starts. It acts as the Program's ANONYMOUS Identity:
-- one row of `class = 'anonymous'`, held like any other. That is not a
-- bookkeeping convenience. Two anonymous hunters
-- share one upstream slot and one cookie jar exactly as two authenticated ones
-- would, so the anonymous Identity is the thing the roster's sentence is most
-- often about. Its consequence is deliberate and visible: while one
-- unauthenticated hunt runs, a second one waits, and `web_hunter`'s two slots
-- are reachable only by two hunts that act as different Identities.
--
-- Criterion 2's refusal keeps a reachable cause after that. A clamped Task with
-- no Identity is what the roster gaining a clamp leaves behind: the Tasks
-- opened before the change carry nothing, and `claimable_for` refuses them with
-- `clamped_without_identity` rather than starting them leaseless.
--
-- Criterion 3 is answered by making the column load-bearing rather than by
-- deleting it. `effective_lane_capacity.clamp_to_identity_leases` is now read
-- twice: by the claim's own gate, and by `scheduler_lane_state.headroom`, which
-- for a clamped lane is the smaller of the free slots and the Program's unheld
-- Identities. That is a true bound and not a second copy of the per-claim gate
-- -- with two Identities and one hunt running, the lane has one slot and one
-- free Identity and reports one. It is an upper bound and not a count of
-- claimable Tasks: the free Identities are the Program's, not the ones this
-- lane's pending Tasks happen to act as, so a lane can report headroom and
-- still have every Task in it refused `identity_held`. That is the right way
-- round -- `claimable_for` asks `identity_held` before it asks `lane_full`, so
-- the coarser number can never refuse a Task the finer one would have allowed.
-- Bounding `max_slots` instead would have been wrong twice over: it is
-- `roles.max_concurrent` by definition (023:237, 037:403), and 023's
-- `check_scheduler_closure()` fails a lane whose `min_slots` exceeds it.


-- ---------------------------------------------------------------------------
-- 1. What a clamped Task acts as
-- ---------------------------------------------------------------------------

-- A table and not a `uuid[]` on `tasks`, for 017 rule 3's reason: an array of
-- Identity ids is a citation the catalogue cannot check, and one naming another
-- Program's Identity would be exactly the crossing the rule exists to refuse.
-- Both edges cascade and the row reaches the purge root directly, which is 016
-- and 074's shape: generation 1, gone before any check of any later generation
-- is asked.
CREATE TABLE task_identities (
    task_id            uuid NOT NULL,
    identity_entity_id uuid NOT NULL,
    program_id         uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    PRIMARY KEY (task_id, identity_entity_id),
    FOREIGN KEY (task_id, program_id) REFERENCES tasks (id, program_id)
        ON DELETE CASCADE,
    FOREIGN KEY (identity_entity_id, program_id)
        REFERENCES identities (entity_id, program_id) ON DELETE CASCADE
);

COMMENT ON TABLE task_identities IS
  'Ticket 72: the Identities a Task will act as, which is what a clamped role''s run takes a Lease on. Derived when the Task is opened, from its Hypothesis where that names an Identity and from the Program''s anonymous Identity where it does not -- so that "what this run acts as" is a property of the Task and not of whether a Hypothesis happened to fill in a nullable column.';

CREATE INDEX task_identities_identity_idx
    ON task_identities (identity_entity_id, program_id);

-- The rows are projected from the Task, so the only thing that may move them is
-- the projection -- 021's rule for `entities.in_scope`, and its mechanism: a
-- transaction-local flag the deriving function raises and lowers around its own
-- writes. Without it "what this run acts as" would be a claim any statement
-- could edit under a live Lease, which is the property the clamp is made of.
-- UPDATE is refused outright, with no flag that permits it: a row here is a
-- Task, an Identity and the Program they share and nothing else, so there is
-- nothing to amend -- it is derived or it is gone. Nothing records when, either:
-- the projection empties and refills, so a stamp would be the age of the last
-- re-derivation rather than of the answer, and no check and no view asks.
CREATE FUNCTION task_identities_are_projected() RETURNS trigger
LANGUAGE plpgsql AS $fn$
BEGIN
    IF TG_OP = 'DELETE'
       AND (coalesce(current_setting('rk2.identity_projection', true), 'off') = 'on'
            OR coalesce(current_setting('app.purging', true), 'off') = 'on') THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION
        'task_identities is projected from the Task it belongs to; change the '
        'Task''s kind or hypothesis and let the projection follow';
END $fn$;

CREATE TRIGGER task_identities_projected
    BEFORE UPDATE OR DELETE ON task_identities
    FOR EACH ROW EXECUTE FUNCTION task_identities_are_projected();


-- ---------------------------------------------------------------------------
-- 2. The anonymous Identity
-- ---------------------------------------------------------------------------

-- One row per Program, made on demand rather than at program creation, and the
-- reason is the emitter: `entities` carries an `event_table_config` row, so
-- writing one requires `set_actor()`, and `programs` does not (027:81 -- "no
-- program.created event type exists; the root row emits nothing"). A trigger on
-- `programs` would therefore have made every bare `INSERT INTO programs`
-- declare an actor it does not otherwise need. The Task insert that reaches
-- this already has one, because `tasks` emits.
--
-- `class = 'anonymous'` takes no `secret_ref` (003's CHECK), and 021's recon
-- already writes anonymous Identities with none, so nothing downstream learns a
-- new shape here.
--
-- The slot name is `_anonymous` and the leading underscore is the whole point.
-- `identities_slot_idx` is unique per Program, and `reconcile_identities` writes
-- `slot_name` straight from the configured `identity.name`, which `config.SLUG`
-- requires to start `[a-z0-9]`. So no configuration can name this slot, and the
-- question of who collides with whom does not arise. Spelling it `anonymous`
-- would have left the answer depending on which row was written first: an
-- operator who configures `anonymous` after the first hunt fails at
-- `rk configure`, but one who configures it before fails INSIDE the first hunt
-- Task's INSERT, as a `unique_violation` raised from a trigger -- which is the
-- outcome a reserved name is supposed to prevent, not schedule.
--
-- `origin` is left at its default of `configured`, which is the honest one of
-- the four: the anonymous Identity is not observed on the target and not
-- proposed by a model, it is a consequence of the harness being configured to
-- hunt at all. Nothing is owed a provenance row for it -- 021's check asks that
-- of `proposed` and of nothing else.
CREATE FUNCTION rk2_anonymous_identity(p_program uuid) RETURNS uuid
LANGUAGE plpgsql AS $fn$
DECLARE v_entity uuid;
BEGIN
    SELECT e.id INTO v_entity
      FROM entities e
     WHERE e.program_id = p_program AND e.type = 'identity'
       AND e.dedup_key = 'anonymous-identity';
    IF FOUND THEN RETURN v_entity; END IF;

    INSERT INTO entities (program_id, type, dedup_key, metadata)
    VALUES (p_program, 'identity', 'anonymous-identity',
            jsonb_build_object('source', 'identity_clamp', 'ticket', '72'))
    RETURNING id INTO v_entity;

    INSERT INTO identities (entity_id, slot_name, class)
    VALUES (v_entity, '_anonymous', 'anonymous');

    RETURN v_entity;
END $fn$;

COMMENT ON FUNCTION rk2_anonymous_identity(uuid) IS
    'The Program''s anonymous Identity, created the first time a clamped Task '
    'needs to act as it. An unauthenticated hunt still occupies one upstream '
    'slot and one cookie jar, so it is leased like any other Identity rather '
    'than being the absence of one.';

REVOKE ALL ON FUNCTION rk2_anonymous_identity(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION rk2_anonymous_identity(uuid) TO rk2_runtime;


-- ---------------------------------------------------------------------------
-- 3. The derivation
-- ---------------------------------------------------------------------------

-- On the Task rather than at every site that opens one. There are three inserts
-- of a `hunt` Task in the corpus (021, 038, 073's `open_task`) and the roster
-- may clamp a fourth role tomorrow; a trigger is the one place all of them pass
-- through.
--
-- On UPDATE as well as INSERT, of the two columns the answer is computed from.
-- A Task's Hypothesis is not fixed at insert: the harness opens a hunt and
-- points it at a Hypothesis afterwards, and re-pointing it changes what the run
-- would act as. Answering only at insert would leave the table describing a
-- Task that no longer exists -- and it would do it silently, because every
-- check downstream reads this table rather than the Hypothesis.
--
-- What it will not do is move the answer under a run that is already holding
-- it. A live Lease is the promise that this upstream slot belongs to this run,
-- and rewriting the Task's Identities beneath it would leave the run holding a
-- an Identity its Task no longer names while arm (b) demands a Lease on one it
-- never took.

-- The walk from a Task to the Identities its runs are holding, said once. Two
-- places ask it and they ask it differently -- the guard below wants to know
-- whether there is any, section 7's arm (b) wants to know whether a particular
-- one is among them -- so what is shared is the set and not the predicate.
CREATE FUNCTION task_held_identities(p_task uuid)
RETURNS TABLE (identity_entity_id uuid)
LANGUAGE sql STABLE AS $fn$
    SELECT l.identity_entity_id
      FROM identity_leases l
      JOIN agent_runs a ON a.id = l.holder_agent_run_id
     WHERE a.task_id = p_task AND l.released_at IS NULL
$fn$;

COMMENT ON FUNCTION task_held_identities(uuid) IS
    'The Identities a Task''s runs currently hold unreleased Leases on, which '
    'is the measured half of the clamp -- task_identities is the owed half.';

REVOKE ALL ON FUNCTION task_held_identities(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION task_held_identities(uuid) TO rk2_runtime;

-- The derivation itself, taking the Task rather than the trigger's NEW so that
-- the backfill below runs the same code over the Tasks that predate the file.
-- Two copies of this body would be two answers to "what does a clamped Task act
-- as" -- one for rows written after the migration and one for rows written
-- before, which is the disagreement the projection exists to prevent.
CREATE FUNCTION rk2_project_task_identities(t tasks) RETURNS void
LANGUAGE plpgsql AS $fn$
DECLARE n integer;
BEGIN
    PERFORM set_config('rk2.identity_projection', 'on', true);
    DELETE FROM task_identities WHERE task_id = t.id;
    PERFORM set_config('rk2.identity_projection', 'off', true);

    IF NOT EXISTS (SELECT 1 FROM role_task_kinds m
                     JOIN roles r ON r.role = m.role
                    WHERE m.kind = t.kind AND r.clamp_to_identity_leases) THEN
        RETURN;
    END IF;

    INSERT INTO task_identities (task_id, identity_entity_id, program_id)
    SELECT t.id, x.i, t.program_id
      FROM (SELECT unnest(ARRAY[h.identity_a_entity_id,
                                h.identity_b_entity_id]) AS i
              FROM hypotheses h WHERE h.id = t.hypothesis_id) x
     WHERE x.i IS NOT NULL
    ON CONFLICT DO NOTHING;

    GET DIAGNOSTICS n = ROW_COUNT;
    IF n = 0 THEN
        INSERT INTO task_identities (task_id, identity_entity_id, program_id)
        VALUES (t.id, rk2_anonymous_identity(t.program_id), t.program_id);
    END IF;
END $fn$;

COMMENT ON FUNCTION rk2_project_task_identities(tasks) IS
    'Empties and refills one Task''s task_identities rows: the Identities its '
    'Hypothesis names, or the Program''s anonymous Identity when it names none, '
    'or nothing at all when no clamped role runs its kind.';

REVOKE ALL ON FUNCTION rk2_project_task_identities(tasks) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION rk2_project_task_identities(tasks) TO rk2_runtime;

CREATE FUNCTION derive_task_identities() RETURNS trigger
LANGUAGE plpgsql AS $fn$
BEGIN
    IF TG_OP = 'UPDATE'
       AND EXISTS (SELECT 1 FROM task_held_identities(NEW.id)) THEN
        RAISE EXCEPTION
            'task % holds an Identity Lease; what it acts as cannot be re-pointed'
            ' under the run holding it', NEW.label
            USING ERRCODE = 'check_violation';
    END IF;

    PERFORM rk2_project_task_identities(NEW);
    RETURN NULL;
END $fn$;

COMMENT ON FUNCTION derive_task_identities() IS
    'Runs the projection when a Task is opened and again when its kind or its '
    'Hypothesis moves, so that task_identities is the clamped population and '
    'nothing else -- including when a Task leaves that population by changing '
    'kind, which is why the projection empties before it fills. Refuses to '
    're-point a Task whose run is already holding an Identity Lease.';

CREATE TRIGGER tasks_derive_identities
    AFTER INSERT OR UPDATE OF kind, hypothesis_id ON tasks
    FOR EACH ROW EXECUTE FUNCTION derive_task_identities();

-- Every Task that predates this file, so that a database with work in flight
-- does not have to drain before the clamp means anything. `set_actor` because
-- the anonymous Identity's `entities` row emits and a migration has no actor of
-- its own; `runtime` because that is what the derivation is -- 041 and
-- 20260811T150000Z declare the same thing for the same reason.
DO $$
DECLARE r tasks%ROWTYPE;
BEGIN
    PERFORM set_actor('runtime', 'ticket 72 identity clamp backfill');

    FOR r IN
        SELECT t.* FROM tasks t
          JOIN role_task_kinds m ON m.kind = t.kind
          JOIN roles rl ON rl.role = m.role AND rl.clamp_to_identity_leases
         WHERE NOT EXISTS (SELECT 1 FROM task_identities ti
                            WHERE ti.task_id = t.id)
         ORDER BY t.id
    LOOP
        PERFORM rk2_project_task_identities(r);
    END LOOP;
END $$;


-- ---------------------------------------------------------------------------
-- 4. The claim
-- ---------------------------------------------------------------------------

-- The clamp as a question about one Task, in the shape its neighbours are in
-- (`ready_for`, `identity_held_for`, `subagent_started_for`). Through
-- `effective_lane_capacity` and not `role_task_kinds` for 075's reason: the
-- lane bound in section 5 reads the view, and one source for "the role that
-- runs this kind" is what keeps the gate and the bound talking about the same
-- population.
CREATE FUNCTION identity_clamped_for(t tasks) RETURNS boolean
LANGUAGE sql STABLE AS $fn$
    SELECT EXISTS (
        SELECT 1 FROM effective_lane_capacity lc
         WHERE lc.program_id = t.program_id
           AND lc.kind = t.kind
           AND lc.clamp_to_identity_leases
    )
$fn$;

COMMENT ON FUNCTION identity_clamped_for(tasks) IS
    'Whether the one role that runs this Task''s kind is clamped to Identity '
    'Leases, read from effective_lane_capacity so that the claim''s gate and '
    'the lane''s headroom bound cannot disagree about which lanes are clamped.';

REVOKE ALL ON FUNCTION identity_clamped_for(tasks) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity_clamped_for(tasks) TO rk2_runtime;

-- Same rule, same Leases, different source, and deliberately nothing else.
-- `released_at IS NULL` alone is still 023's argument and still not a new one:
-- an expired-but-unreleased Lease is the sweep's problem, and a clock here would
-- put one inside the ranking pass. What changes is that the Identities are the
-- Task's own rather than its Hypothesis's, so an unauthenticated hunt is now
-- capable of being held.
--
-- What is NOT added is a carve-out for a Lease an earlier run of this same Task
-- holds. It reads like tidiness -- the Task is not blocked by itself -- but the
-- only caller that could reach it is a re-claim of a Task whose previous run
-- ended without releasing, and `identity_leases_exclusive_idx` would refuse that
-- claim anyway, one statement later and as a raw `unique_violation` instead of
-- as `identity_held`. The gate is the place that names the reason.
CREATE OR REPLACE FUNCTION identity_held_for(t tasks) RETURNS boolean
LANGUAGE sql STABLE AS $fn$
    SELECT EXISTS (
        SELECT 1 FROM task_identities ti
          JOIN identity_leases l
            ON l.identity_entity_id = ti.identity_entity_id
         WHERE ti.task_id = t.id AND l.released_at IS NULL)
$fn$;

COMMENT ON FUNCTION identity_held_for(tasks) IS
    'Whether an Identity this Task will act as is under an unreleased Lease. '
    'The ranking half and the claim half both read it, so the two cannot come '
    'to different conclusions about the same Lease. Ticket 72 moved the source '
    'from the Task''s Hypothesis to the Task''s own task_identities, which is '
    'what makes an unauthenticated hunt capable of holding and of being held.';

-- Restated whole rather than patched, because a plpgsql body cannot be amended
-- in place. Every arm is 075's, in 075's order; one is added ahead of the
-- Identity gate it belongs beside.
CREATE OR REPLACE FUNCTION claimable_for(t tasks, w scheduler_weights) RETURNS text
LANGUAGE plpgsql STABLE AS $fn$
DECLARE v text;
BEGIN
    IF t.status IS DISTINCT FROM 'pending' THEN RETURN 'not_pending'; END IF;

    v := cancel_reason_for(t, w);
    IF v IS NOT NULL THEN RETURN v; END IF;

    v := ready_for(t);
    IF v IS NOT NULL THEN RETURN v; END IF;

    IF t.estimated_cost IS NULL THEN RETURN 'not_ranked'; END IF;

    IF NOT EXISTS (SELECT 1 FROM program_budget b
                    WHERE b.program_id = t.program_id
                      AND (b.tokens_left IS NULL
                           OR b.tokens_left >= t.estimated_cost * w.cost_reference_tokens)) THEN
        RETURN 'unaffordable';
    END IF;

    v := budget_refusal_for(t);
    IF v IS NOT NULL THEN RETURN v; END IF;

    -- Criterion 2. Ahead of `identity_held` because the two answer different
    -- questions and the emptier one is the more specific: a clamped Task with
    -- no Identity is not contending for anything, it has nothing to contend
    -- with, and starting it would be the lease-free start the ticket refuses.
    -- Reachable when the roster gains a clamp after the Task was opened, which
    -- is the one way a Task can be clamped and carry no rows.
    IF identity_clamped_for(t)
       AND NOT EXISTS (SELECT 1 FROM task_identities ti
                        WHERE ti.task_id = t.id) THEN
        RETURN 'clamped_without_identity';
    END IF;

    IF identity_held_for(t) THEN RETURN 'identity_held'; END IF;

    IF NOT EXISTS (SELECT 1 FROM effective_lane_capacity lc
                    WHERE lc.program_id = t.program_id AND lc.kind = t.kind) THEN
        RETURN 'no_role_runs_this_kind';
    END IF;

    IF skills_ungranted_for(t) THEN RETURN 'skill_not_granted_to_role'; END IF;

    IF NOT EXISTS (SELECT 1 FROM scheduler_lane_state s
                    WHERE s.program_id = t.program_id AND s.kind = t.kind
                      AND s.headroom > 0) THEN
        RETURN 'lane_full';
    END IF;

    IF subagent_started_for(t)
       AND (SELECT count(*) FROM tasks c
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
    'refuses it. The offer filters on it and the claim re-asks it, so the list '
    'the orchestrator was given and the decision the runtime commits cannot be '
    'answers to two different questions. Its clamped_without_identity arm is '
    'ticket 72''s: a role the roster clamps may not start a run that acts as '
    'nothing, and the Identities it acts as are the Task''s own rows rather '
    'than its Hypothesis''s nullable columns. Its global_subagent_cap arm is '
    'asked only of a Task that would start a subagent (subagent_started_for), '
    'and counts the Program''s claimed and running subagent Tasks, which is the '
    'wider of the two populations max_concurrent_subagents bounds: the pre-tool '
    'gate counts one session''s outstanding delegations against the same '
    'number. A validate or a report is in neither population, so neither is '
    'refused for concurrency it does not spend. Its budget arms ask '
    '`budget_refusal_for`, which reads capacity that claims in flight have '
    'already promised. Its skill_not_granted_to_role arm asks role_skills '
    'whether the one role that runs this kind may load what the Task requires, '
    'because a Skill a role lacks is a load-time error and not something to '
    'discover inside a started child.';

-- Restated whole for the same reason. Every line is 075's except the Lease
-- block, which now reads the Task's own Identities and asserts that it wrote
-- something: `claimable_for` has already refused a clamped Task with no rows,
-- so reaching here with none is the two disagreeing, and that is a bug in this
-- file rather than a Task to start leaseless.
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
    v_clamp   boolean;
    v_model   text;
    v_effort  text;
    v_run     uuid;
    v_reason  text;
    v_leases  integer;
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

    SELECT m.role, r.clamp_to_identity_leases, r.model, r.effort
      INTO v_role, v_clamp, v_model, v_effort
      FROM role_task_kinds m JOIN roles r ON r.role = m.role
     WHERE m.kind = v_task.kind;

    UPDATE tasks
       SET status = 'claimed', attempts = attempts + 1, claimed_at = now(),
           lease_expires_at = now() + w.lease_ttl
     WHERE id = v_task.id;

    INSERT INTO agent_runs (program_id, task_id, role, model, effort, mission_packet)
    VALUES (p, v_task.id, v_role, v_model, v_effort, '{}')
    RETURNING id INTO v_run;

    -- The promise. Written after the run exists because it names it, and read
    -- by the next claim through `program_capacity` -- which is why it has to be
    -- written before this transaction ends rather than by whoever starts the
    -- child. The amounts are the same expressions `budget_refusal_for` just
    -- admitted the Task against, from the same view in the same transaction.
    INSERT INTO budget_reservations (program_id, agent_run_id, task_id, kind,
                                     tokens, requests)
    SELECT p, v_run, v_task.id, v_task.kind, c.run_tokens, c.run_requests
      FROM program_capacity c WHERE c.program_id = p;

    -- Decision 7: the identity lease shares the task lease's clock. Two clocks
    -- would admit a live task lease beside a dead identity lease, and the agent
    -- would read the proxy's refusal to inject as the TARGET changing
    -- behaviour -- the false positive the identity model exists to prevent.
    --
    -- Ticket 72: every Identity the Task will act as, and no second condition.
    -- `identity_leases_exclusive_idx` is what makes two claimants of one
    -- Identity serialise if the gate above ever misses one.
    IF v_clamp THEN
        INSERT INTO identity_leases (identity_entity_id, holder_agent_run_id,
                                     expires_at, program_id)
        SELECT ti.identity_entity_id, v_run, now() + w.lease_ttl, p
          FROM task_identities ti WHERE ti.task_id = v_task.id;

        GET DIAGNOSTICS v_leases = ROW_COUNT;
        IF v_leases = 0 THEN
            RAISE EXCEPTION 'task % is clamped and names no identity to hold', v_task.label
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;

    UPDATE task_slate SET consumed = true
     WHERE program_id = p AND task_id = v_task.id AND NOT consumed;

    -- The choice has been acted on, whichever entry the claim took. A pick left
    -- outstanding here would be read by the next claim as a choice about a Task
    -- that is already running.
    PERFORM supersede_pick(p);

    RETURN (SELECT label FROM agent_runs WHERE id = v_run);
END $fn$;


-- ---------------------------------------------------------------------------
-- 5. The lane
-- ---------------------------------------------------------------------------

-- Criterion 3. `headroom` and not `max_slots`: `max_slots` is the roster's
-- `max_concurrent` by definition and no program may move it, and 023's
-- `check_scheduler_closure()` fails any lane whose `min_slots` exceeds it -- so
-- a Program with fewer Identities than its entitlement would have failed the
-- closure check rather than reported a smaller lane.
--
-- The two subtractions do not double-count, because they are combined with
-- `least` and not with a sum: a running clamped Task takes one slot AND holds
-- its Identity, so it is removed once from each side and the smaller of the two
-- remainders is what is really claimable. Free Identities are counted over the
-- whole Program rather than per Task, which makes this an upper bound and not a
-- restatement of `identity_held_for` -- whether the particular Identity a Task
-- wants is free stays the claim's question.
CREATE OR REPLACE VIEW scheduler_lane_state AS
    SELECT c.program_id, c.kind, c.role, c.min_slots, c.max_slots, c.overridden,
           coalesce(live.n, 0)                             AS live_slots,
           CASE WHEN c.clamp_to_identity_leases
                THEN least(greatest(c.max_slots - coalesce(live.n, 0), 0),
                           coalesce(free.n, 0))
                ELSE greatest(c.max_slots - coalesce(live.n, 0), 0)
           END                                             AS headroom,
           greatest(c.min_slots - coalesce(live.n, 0), 0)  AS deficit
      FROM effective_lane_capacity c
      LEFT JOIN LATERAL (
          SELECT count(*) AS n FROM tasks t
           WHERE t.program_id = c.program_id AND t.kind = c.kind
             AND t.status IN ('claimed','running')
      ) live ON true
      LEFT JOIN LATERAL (
          SELECT count(*) AS n FROM identities i
           WHERE i.program_id = c.program_id
             AND i.invalidated_at IS NULL
             AND NOT EXISTS (SELECT 1 FROM identity_leases l
                              WHERE l.identity_entity_id = i.entity_id
                                AND l.released_at IS NULL)
      ) free ON true;

COMMENT ON VIEW scheduler_lane_state IS
  'Live occupancy against capacity, per lane, per program. A lane whose role is clamped to Identity Leases has its headroom bounded by the Program''s unheld Identities as well as by its free slots, which is what makes effective_lane_capacity.clamp_to_identity_leases an input to capacity rather than a column nothing reads.';


-- ---------------------------------------------------------------------------
-- 6. Ticket 24's arm, withdrawn
-- ---------------------------------------------------------------------------

-- `check_lease_liveness()` arm (i) asked its question of three things: the role
-- clamps, the Hypothesis names an Identity, the Task is held. The middle one is
-- the defect written down -- it excused exactly the runs this ticket is about.
--
-- With that condition gone the arm says: a clamped Task in flight that names
-- Identities and holds no Lease at all. Section 7's arm (b) says: a clamped Task
-- in flight that names an Identity it holds no Lease on. Every row the first can
-- return is a row the second returns, so keeping both would report one defect
-- twice under two names, and the weaker name is the one that reads as though it
-- were a separate rule. The arm comes out; 024's `lease_liveness` keeps the
-- eight arms that are about a Lease's own liveness, and "a clamped run holds
-- what its Task acts as" belongs to this ticket's check, which is 026's rule.
--
-- Restated whole because a `sql` body is not patchable; arms (a) to (h) are
-- 024's, character for character.
CREATE OR REPLACE FUNCTION check_lease_liveness()
RETURNS TABLE (problem text, subject text, detail text)
LANGUAGE sql STABLE AS $fn$
    -- (a) the glossary's sentence, as a row test. A live identity lease whose
    --     holder is executing a Task must expire when that Task's lease does;
    --     one clock means one value, not two values close together.
    SELECT 'identity_lease_outlives_its_task_lease', l.id::text,
           'an unreleased Identity Lease whose expiry is not its Task Lease''s'
      FROM identity_leases l
      JOIN agent_runs a ON a.id = l.holder_agent_run_id
      JOIN tasks t ON t.id = a.task_id
     WHERE l.released_at IS NULL
       AND t.status IN ('claimed','running')
       AND t.lease_expires_at IS DISTINCT FROM l.expires_at

  UNION ALL
    -- (b) the other direction of the same sentence: a hold whose holder has
    --     stopped. `release_leases` is what makes this impossible; an arm
    --     rather than a comment because six functions end runs.
    SELECT 'identity_lease_held_by_a_finished_run', l.id::text,
           'an unreleased Identity Lease held by an Agent run that has finished'
      FROM identity_leases l
      JOIN agent_runs a ON a.id = l.holder_agent_run_id
     WHERE l.released_at IS NULL AND a.finished_at IS NOT NULL

  UNION ALL
    -- (c) a Task in flight with nothing holding it. Not merely untidy: it is
    --     invisible to every expiry comparison, so nothing would ever recover
    --     it and nothing would ever say why.
    SELECT 'task_in_flight_without_a_lease', t.label,
           'a claimed or running Task with no lease expiry'
      FROM tasks t
     WHERE t.status IN ('claimed','running') AND t.lease_expires_at IS NULL

  UNION ALL
    -- (d) the mirror: a lease on a Task nobody is executing. `resume_program`
    --     left these behind for three tickets.
    SELECT 'task_lease_outlives_its_flight', t.label,
           'a Task that is not claimed or running and still carries a lease expiry'
      FROM tasks t
     WHERE t.status NOT IN ('claimed','running') AND t.lease_expires_at IS NOT NULL

  UNION ALL
    -- (e) one clock, textually. `clock_timestamp()` advances inside a
    --     statement, so two writes from it are two clocks however adjacent
    --     they look. Comments are stripped first, for 023's reason: the first
    --     version of its own textual arm fired on a comment explaining why the
    --     clock was absent.
    SELECT 'lease_writer_reads_a_statement_clock', p.proname,
           'a function that writes a lease expiry from clock_timestamp()'
      FROM pg_proc p
     WHERE p.pronamespace = 'public'::regnamespace
       AND p.proname IN ('claim_task','heartbeat_leases')
       AND regexp_replace(p.prosrc, '--[^' || chr(10) || ']*', '', 'g')
           ~* 'clock_timestamp'

  UNION ALL
    -- (f) criterion 5's second half. Reconciliation is explicit, which means
    --     no other function in this database reaches it -- not a view, not a
    --     read, not a trigger. The runtime calls it; nothing calls the runtime.
    SELECT 'reconciliation_is_reachable_from_another_function', p.proname,
           'a database function calls reconcile_leases()'
      FROM pg_proc p
     WHERE p.pronamespace = 'public'::regnamespace
       AND p.proname NOT IN ('reconcile_leases','check_lease_liveness')
       AND regexp_replace(p.prosrc, '--[^' || chr(10) || ']*', '', 'g')
           ~ 'reconcile_leases'

  UNION ALL
    -- A view is the other way a read could reach it: Postgres will happily let
    -- a VOLATILE function be selected from one, and then "run the reconciler"
    -- and "read the queue" are the same statement.
    SELECT 'reconciliation_is_reachable_from_a_view', v.viewname,
           'a view selects reconcile_leases()'
      FROM pg_views v
     WHERE v.schemaname = 'public' AND v.definition ~ 'reconcile_leases'

  UNION ALL
    -- (g) every lease write declares an actor. The emitter raises without one,
    --     so this is not what makes attribution true -- it is what stops a
    --     verb from being written that can only be called inside somebody
    --     else's transaction.
    SELECT 'lease_verb_declares_no_actor', p.proname,
           'a lease verb that writes without calling set_actor()'
      FROM pg_proc p
     WHERE p.pronamespace = 'public'::regnamespace
       AND p.proname IN ('heartbeat_leases','release_leases','reconcile_leases',
                         'resume_program')
       AND p.prosrc !~ 'set_actor'

  UNION ALL
    -- (h) 023's arm (i), for the verbs this file adds.
    SELECT 'lease_function_public_executable', p.proname,
           'an agent-reachable role can call a lease verb'
      FROM pg_proc p
     WHERE p.pronamespace = 'public'::regnamespace
       AND p.proname IN ('lease_live_for','heartbeat_leases','release_leases',
                         'reconcile_leases')
       AND has_function_privilege('public', p.oid, 'EXECUTE')
$fn$;

REVOKE ALL ON FUNCTION check_lease_liveness() FROM PUBLIC;

-- 024's sentence, less the clause arm (i) carried. "One half missing entirely"
-- is now section 7's question and is asked per Identity there.
COMMENT ON FUNCTION check_lease_liveness() IS
    'What a Lease can get wrong: two halves of one hold disagreeing about when '
    'it ends, a hold outliving its holder, a Task in flight with nothing '
    'holding it or holding one it is not in, a second clock, and a '
    'reconciliation something else can trigger. Whether a clamped run holds the '
    'Identities its Task acts as is 072''s check_identity_clamp().';


-- ---------------------------------------------------------------------------
-- 7. What keeps it
-- ---------------------------------------------------------------------------

-- This ticket's own check rather than arms bolted onto 024's, which is 026's
-- rule and the one 074 and 075 took. Three arms, one per way the clamp can stop
-- meaning what the roster says it means.
--
-- What is deliberately not an arm is the other direction -- a run holding a
-- Lease its Task does not name. `claim_task` is the only writer of
-- `identity_leases` and writes them from `task_identities` alone, so in the
-- claim path the question cannot come out any other way; and a lane the roster
-- does not clamp derives no `task_identities` at all, so asking it globally
-- would make every Identity a recon or analyze run holds into a violation.
-- What stops a Lease from becoming a request under the wrong Identity is the
-- request side -- `rk2_replay_plan` and `enforce_allowed_receipt_capability`,
-- both of which read the Lease the run actually holds.
CREATE FUNCTION check_identity_clamp()
RETURNS TABLE (problem text, subject text, detail text)
LANGUAGE sql STABLE AS $fn$
    -- (a) a clamped Task that acts as nothing. The refusal keeps this out of
    --     flight, so a row here is the refusal having been bypassed -- a
    --     hand-written status change, or a derivation that did not run.
    SELECT 'clamped_task_acts_as_nothing', t.label,
           'status ' || t.status || ' on a clamped lane with no task_identities row'
      FROM tasks t
     WHERE t.status IN ('claimed','running')
       AND identity_clamped_for(t)
       AND NOT EXISTS (SELECT 1 FROM task_identities ti WHERE ti.task_id = t.id)

  UNION ALL
    -- (b) criterion 1's "every", which arm (i) of 024's check does not ask:
    --     that arm passes a run holding one Lease of the two its Task names.
    SELECT 'task_identity_not_held_by_its_run', t.label,
           'the run acts as ' || i.slot_name || ' and holds no lease on it'
      FROM tasks t
      JOIN task_identities ti ON ti.task_id = t.id
      JOIN identities i ON i.entity_id = ti.identity_entity_id
     WHERE lease_live_for(t)
       AND identity_clamped_for(t)
       AND NOT EXISTS (SELECT 1 FROM task_held_identities(t.id) hi
                        WHERE hi.identity_entity_id = ti.identity_entity_id)

  UNION ALL
    -- (c) criterion 3 as a standing question rather than as an edit that was
    --     made once. The column is in a capacity view; if nothing in the lane's
    --     own state reads it, it is back to being a name that claims a bound it
    --     does not apply.
    SELECT 'lane_state_ignores_the_clamp', 'scheduler_lane_state',
           'the lane view does not read clamp_to_identity_leases, so the column bounds nothing'
     WHERE pg_get_viewdef('scheduler_lane_state'::regclass)
           !~ 'clamp_to_identity_leases'
$fn$;

REVOKE ALL ON FUNCTION check_identity_clamp() FROM PUBLIC;

COMMENT ON FUNCTION check_identity_clamp() IS
    'What the Identity clamp can get wrong: a clamped run in flight acting as '
    'nothing, a run holding fewer Leases than its Task names, and the lane view '
    'going back to ignoring the column that says the lane is clamped.';

INSERT INTO standing_checks(name, query, owner_ticket, note) VALUES
    ('identity_clamp', 'SELECT * FROM check_identity_clamp()', '72',
     'a clamped role''s run holds one Lease per Identity its Task acts as, and the lane it claims from counts those Leases as capacity');


-- ---------------------------------------------------------------------------
-- 8. Wiring
-- ---------------------------------------------------------------------------

INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
    ('task_identities', 'derived',
     'the Identities a clamped Task will act as, derived from its Hypothesis or from the Program''s anonymous Identity at the moment the Task is opened; the Task it belongs to emits', '72');

INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
    ('task_identities', 'program_id',
     'program-scoped: the purge root'),
    ('task_identities', 'task_id',
     'ON DELETE CASCADE to tasks: what a task that is gone would have acted as'),
    ('task_identities', 'identity_entity_id',
     'ON DELETE CASCADE to identities: an identity that is gone is acted as by nobody');

SELECT attach_event_triggers();
SELECT attach_actor_kind_guards();

-- DELETE stays granted, because the projection re-runs as whoever moved the
-- Task and emptying before filling is how a Task that stops being clamped stops
-- naming Identities. What keeps a hand-written delete out is the trigger's flag,
-- which only the projection raises -- the privilege is not the fence here.
GRANT SELECT, INSERT, DELETE ON task_identities TO rk2_runtime;
GRANT SELECT ON task_identities TO rk2_human;

-- 029's default privileges hand every new table the four verbs to `rk2_runtime`.
-- A row here is a Task, an Identity and the Program they share; there is nothing
-- an UPDATE could mean.
REVOKE UPDATE ON TABLE task_identities FROM rk2_runtime;


-- ---------------------------------------------------------------------------
-- 9. The invariants this file must not have broken
-- ---------------------------------------------------------------------------

DO $$
DECLARE n integer; d text;
BEGIN
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_identity_clamp();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-72 refuses to finish: % clamp violation(s): %', n, d;
    END IF;

    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_lease_liveness();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-72 refuses to finish: % lease violation(s): %', n, d;
    END IF;

    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_purge_travel();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-72 refuses to finish: % purge violation(s): %', n, d;
    END IF;

    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_program_isolation();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-72 refuses to finish: % isolation violation(s): %', n, d;
    END IF;
END $$;
