-- ---------------------------------------------------------------------------
-- 20261101T000000Z__a_task_names_the_one_identity_it_acts_as.sql
--                                                                  (ticket 131)
--
-- Ticket 97 settled that an Identity slot is a property of the Tool run, set by
-- the runtime and never an argument a model may name. What it left is a
-- property nobody sets: `execution._authorize` opens every egress Tool run with
-- `"identity_slot": ""`, so no agent-issued request has ever carried an
-- Identity, however many Playbooks ask for one.
--
-- THE DECISION, of the three shapes ticket 131 laid out.
--
-- The Task carries the choice, and the differential is two Tasks. Both halves
-- of ticket 97's own preferred shape, because on their own neither is enough: a
-- run opened under `identity_a` alone leaves `identity_b` unreachable forever,
-- and a Task column with no derivation that fills it differently for the two
-- halves leaves the differential expressible and underived. The third shape --
-- the Tool run carries both and the door picks -- stays refused for ticket 97's
-- measured reason: `gate_tool_call` grades an empty slot `constrained` and a
-- filled one `approval_required`, two classes and two digests, so a slot chosen
-- after a human answered would spend a real account outside the answer given.
--
-- Four consequences, and each of them is a section below.
--
--   1. `tasks.selected_identity_entity_id` is NOT NULL and carries the Program
--      in its foreign key, so a Task names exactly one Identity and it is one
--      of its own Program's. There is no `NULL means anonymous` reading: an
--      unauthenticated hunt names the Program's anonymous Identity, which is
--      the row 20260908T010000Z already mints and leases for exactly that
--      reason.
--   2. The default is anonymous and it is written down rather than assumed. A
--      caller that has decided otherwise says so in the INSERT; every other
--      caller gets the Identity that acts as nobody. That is the conservative
--      direction: the alternative default -- inherit the Hypothesis's
--      `identity_a` on every kind -- would give a Task no clamped role runs a
--      real Identity it holds no Lease on, and `resolve_egress_identity`
--      refuses a named slot with no live Lease rather than sending it
--      anonymously. A run would stop being able to reach the target at all.
--   3. `task_identities` -- what a clamped run leases -- becomes exactly the
--      selection. It was both of the Hypothesis's Identities, which is what
--      made "the slot the Hypothesis was paired against" name two things.
--   4. `derive_hypothesis_hunts` opens one hunt Task per (claim, Identity), so
--      a Hypothesis naming two Identities derives two Tasks and the
--      identity-differential reading eleven Playbooks are written around is a
--      thing the scheduler can actually produce.
--
-- What this file does not do is widen any authority. A Task selecting a
-- non-anonymous Identity still reaches `net_borrowed_identity`, is still graded
-- `approval_required` asking `credential_needed`, and still parks for a person
-- before a single request leaves. What changes is that the question can now be
-- asked at all.
--
-- Depends on 0003 (`identities`), 0032 (`tasks_id_program_key`), 0016
-- (`purge_cascade_edges`), 20260908T010000Z (`task_identities`, the projection
-- and the clamp), 20260925T020000Z (the current `rk2_anonymous_identity`) and
-- 20261012T000000Z (the hunt frontier and the derivation). A new file rather
-- than an edit to any of them: a recorded migration whose file has changed is
-- schema drift and `rk db migrate` refuses the whole corpus for it.
-- ---------------------------------------------------------------------------


-- ===========================================================================
-- 1. The column
-- ===========================================================================

ALTER TABLE tasks ADD COLUMN selected_identity_entity_id uuid;

-- The Program travels in the key, which is 017 rule 3: an Identity id on its
-- own is a citation the catalogue cannot check, and one naming another
-- Program's Identity would be exactly the crossing the rule refuses. `ON DELETE
-- CASCADE` and a registry row for the same reason `task_identities` has one:
-- outside a purge nothing deletes an Identity, and inside one a NO ACTION key
-- from a Task to an Identity is a Program that cannot be purged.
ALTER TABLE tasks
    ADD CONSTRAINT tasks_selected_identity_program_fk
        FOREIGN KEY (selected_identity_entity_id, program_id)
        REFERENCES identities (entity_id, program_id) ON DELETE CASCADE;

INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
    ('tasks', 'selected_identity_entity_id',
     'ON DELETE CASCADE to identities: the one Identity a Task acts as, and a Task whose Identity is gone acts as nobody');

COMMENT ON COLUMN tasks.selected_identity_entity_id IS
 'Ticket 131: the one Identity this Task acts as, chosen when the Task is opened and never NULL. Anonymous is a choice like any other and is spelled as the Program''s anonymous Identity row rather than as an absence, so that "no Identity was decided" and "this run acts as nobody" stay two different states. The runtime reads it into tool_runs.args.identity_slot when it opens an egress Tool run; a clamped role''s claim takes the Lease on it. Two Identities is two Tasks over the one Hypothesis -- ticket 97 settled that a reading needing two Identities is two runs, because one Tool run is many exchanges and a per-call slot would be a per-call answer to a question the row answers once.';


-- ===========================================================================
-- 2. The read half of the anonymous Identity
-- ===========================================================================

-- `rk2_anonymous_identity` writes, so nothing STABLE may call it and the
-- frontier in section 5 is STABLE. The lookup is split out rather than
-- duplicated: two copies of "where the Program's anonymous Identity is" would
-- be two answers the moment one of them learned about a second dedup key.
-- Answering NULL where none has been minted is the honest answer and the useful
-- one -- a Program that has never opened a Task has no Task naming it either,
-- so every caller here reads the NULL as "nothing matches" and is right.
CREATE FUNCTION rk2_anonymous_identity_id(p_program uuid) RETURNS uuid
LANGUAGE sql STABLE AS $fn$
    SELECT e.id
      FROM entities e
     WHERE e.program_id = p_program AND e.type = 'identity'
       AND e.dedup_key = 'anonymous-identity'
$fn$;

COMMENT ON FUNCTION rk2_anonymous_identity_id(uuid) IS
    'The Program''s anonymous Identity if it has been minted, else nothing. The '
    'read half of rk2_anonymous_identity, split out because that one writes and '
    'a STABLE caller may not.';

REVOKE ALL ON FUNCTION rk2_anonymous_identity_id(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION rk2_anonymous_identity_id(uuid) TO rk2_runtime;

INSERT INTO runtime_verb_surface (verb, added_by, note) VALUES
    ('rk2_anonymous_identity_id(uuid)', '131',
     'the read half of rk2_anonymous_identity, reached from the hunt frontier and from the trigger that defaults a Task''s Identity; the runtime holds the writer already and this is the half a STABLE caller may ask');

-- Restated whole because a plpgsql body cannot be amended in place. Every line
-- is 20260925T020000Z's except the first statement, which now asks the lookup
-- above instead of spelling the same predicate a second time.
CREATE OR REPLACE FUNCTION rk2_anonymous_identity(p_program uuid) RETURNS uuid
LANGUAGE plpgsql AS $fn$
DECLARE v_entity uuid;
BEGIN
    v_entity := rk2_anonymous_identity_id(p_program);
    IF v_entity IS NOT NULL THEN RETURN v_entity; END IF;

    INSERT INTO entities (program_id, type, dedup_key, metadata)
    VALUES (p_program, 'identity', 'anonymous-identity',
            jsonb_build_object('source', 'identity_clamp', 'ticket', '72'))
    RETURNING id INTO v_entity;

    INSERT INTO identities (entity_id, slot_name, class)
    VALUES (v_entity, '_anonymous', 'anonymous');

    -- After both rows and not between them, because the projection is about
    -- the Entity and the Entity is not finished until the slot it stands for
    -- exists. Only on the branch that created one: the early return above
    -- found a row some earlier Task already projected, and re-projecting a
    -- Program to discover that nothing moved is work every Task in the run
    -- would repeat.
    IF EXISTS (SELECT 1 FROM programs p
                WHERE p.id = p_program AND p.scope_version IS NOT NULL) THEN
        PERFORM refresh_scope_projection(p_program);
    END IF;

    RETURN v_entity;
END $fn$;


-- ===========================================================================
-- 3. Anonymous is chosen, not defaulted into by silence
-- ===========================================================================

-- BEFORE INSERT and on the Task itself, for the reason 20260908T010000Z put the
-- projection there: there are five inserters of a Task in the corpus and the
-- roster may add a sixth tomorrow, and a trigger is the one place all of them
-- pass through. `coalesce` and not an override -- a caller that has decided is
-- the authority on its own decision, and this is what happens when nobody has.
--
-- Not on UPDATE. The column is NOT NULL, so an UPDATE that tried to clear it is
-- refused by the constraint rather than quietly re-defaulted, and an UPDATE that
-- names another Identity is a re-selection the projection in section 4 follows.
CREATE FUNCTION select_task_identity() RETURNS trigger
LANGUAGE plpgsql AS $fn$
BEGIN
    NEW.selected_identity_entity_id := coalesce(
        NEW.selected_identity_entity_id, rk2_anonymous_identity(NEW.program_id));
    RETURN NEW;
END $fn$;

COMMENT ON FUNCTION select_task_identity() IS
    'Ticket 131: a Task opened without naming an Identity acts as the Program''s '
    'anonymous one, and says so in a column rather than by leaving it empty. '
    'The anonymous Identity is minted on demand, so the first Task of a Program '
    'is what creates it.';

CREATE TRIGGER tasks_select_identity
    BEFORE INSERT ON tasks
    FOR EACH ROW EXECUTE FUNCTION select_task_identity();

-- Every Task that predates this file. `set_actor` because the anonymous
-- Identity's `entities` row emits and a migration has no actor of its own;
-- `runtime` because that is what a default is -- 20260908T010000Z and
-- 20260925T020000Z declare the same thing for the same reason.
--
-- The Hypothesis is deliberately not read here. A Task that ran under an empty
-- slot ran as nobody, and writing the Identity its Hypothesis happened to name
-- onto a row that has already been dispatched would be this file inventing an
-- attempt profile nobody executed.
DO $$
DECLARE v_program uuid;
BEGIN
    PERFORM set_actor('runtime', 'ticket 131 identity selection backfill');

    FOR v_program IN
        SELECT DISTINCT t.program_id FROM tasks t
         WHERE t.selected_identity_entity_id IS NULL
         ORDER BY 1
    LOOP
        UPDATE tasks SET selected_identity_entity_id = rk2_anonymous_identity(v_program)
         WHERE program_id = v_program AND selected_identity_entity_id IS NULL;
    END LOOP;
END $$;

ALTER TABLE tasks ALTER COLUMN selected_identity_entity_id SET NOT NULL;


-- ===========================================================================
-- 4. What a clamped run leases is what its Task selected
-- ===========================================================================

-- One row and not two. 20260908T010000Z filled this from both of the
-- Hypothesis's Identity columns, which is the defect ticket 131 opens with: a
-- Task that acts as two Identities has no answer to "which one did this request
-- spend", and every Playbook written around the difference between them was
-- reading both halves as the same anonymous caller anyway.
--
-- Still nothing at all when no clamped role runs the Task's kind, and still an
-- empty-then-fill rather than an upsert, both for the reasons that file gives:
-- a Task that leaves the clamped population by changing kind must leave this
-- table with it.
CREATE OR REPLACE FUNCTION rk2_project_task_identities(t tasks) RETURNS void
LANGUAGE plpgsql AS $fn$
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
    VALUES (t.id, t.selected_identity_entity_id, t.program_id);
END $fn$;

COMMENT ON FUNCTION rk2_project_task_identities(tasks) IS
    'Empties and refills one Task''s task_identities rows: exactly the one '
    'Identity the Task selected, or nothing at all when no clamped role runs '
    'its kind. Ticket 131 narrowed it from the two Identities the Hypothesis '
    'named, because a run opened under two of them can say which one it spent '
    'no better than a run opened under none.';

COMMENT ON TABLE task_identities IS
  'Ticket 72, narrowed by ticket 131: the one Identity a Task acts as, which is what a clamped role''s run takes a Lease on. Projected from tasks.selected_identity_entity_id -- so that "what this run acts as" is a property of the Task and not of whether a Hypothesis happened to fill in a nullable column.';

-- The projection follows a re-selection as well as a re-pointing. Without this
-- the column and the Lease would disagree the moment an operator moved a Task
-- from one Identity to another, and every check downstream reads the table.
-- `derive_task_identities` is unchanged and still refuses to move any of it
-- under a live hold.
DROP TRIGGER tasks_derive_identities ON tasks;
CREATE TRIGGER tasks_derive_identities
    AFTER INSERT OR UPDATE OF kind, hypothesis_id, selected_identity_entity_id ON tasks
    FOR EACH ROW EXECUTE FUNCTION derive_task_identities();

-- Every clamped Task that predates this file, so that a database with work in
-- flight does not have to drain before the narrowing means anything. A Task
-- whose run is holding a Lease is left alone: it took what it took, and the
-- projection is refused under a hold for the reason 20260908T010000Z gives.
DO $$
DECLARE r tasks%ROWTYPE;
BEGIN
    PERFORM set_actor('runtime', 'ticket 131 identity projection backfill');

    FOR r IN
        SELECT t.* FROM tasks t
          JOIN role_task_kinds m ON m.kind = t.kind
          JOIN roles rl ON rl.role = m.role AND rl.clamp_to_identity_leases
         WHERE NOT EXISTS (SELECT 1 FROM task_held_identities(t.id))
         ORDER BY t.id
    LOOP
        PERFORM rk2_project_task_identities(r);
    END LOOP;
END $$;


-- ===========================================================================
-- 5. The differential is two Tasks
-- ===========================================================================

-- The frontier grows a column and stops being one row per claim. A Hypothesis
-- naming two Identities is two rows, one per Identity, and a Hypothesis naming
-- none is one row for the anonymous Identity -- which may not have been minted
-- yet, in which case the column is NULL and the derivation resolves it, because
-- minting is a write and this function is STABLE.
--
-- The `NOT EXISTS` moves with it. It was "no hunt Task names this claim", which
-- is what made a second Task over one Hypothesis underivable; it is now "no
-- hunt Task names this claim under this Identity". Both halves of a differential
-- are derived, and neither is derived twice.
--
-- Dropped and recreated rather than replaced: the return type gains a column,
-- and `CREATE OR REPLACE FUNCTION` cannot change one.
DROP FUNCTION rk2_hypothesis_hunt_frontier(uuid);

CREATE FUNCTION rk2_hypothesis_hunt_frontier(p_program_id uuid)
RETURNS TABLE (hypothesis_id uuid, subject_entity_id uuid,
               identity_entity_id uuid, created_at timestamptz)
LANGUAGE sql STABLE AS $fn$
    SELECT h.id, h.subject_entity_id, x.identity_entity_id, h.created_at
      FROM hypotheses h
      JOIN entities e ON e.id = h.subject_entity_id AND e.program_id = h.program_id
      CROSS JOIN LATERAL (
          -- One row per Identity the claim names, or one anonymous row when it
          -- names none. `DISTINCT` because a claim naming nobody unnests two
          -- NULLs and a claim naming one Identity twice is one Task.
          SELECT DISTINCT
                 coalesce(named.id, rk2_anonymous_identity_id(h.program_id))
                     AS identity_entity_id
            FROM (SELECT unnest(ARRAY[h.identity_a_entity_id,
                                      h.identity_b_entity_id]) AS id) named
           WHERE named.id IS NOT NULL
              OR (h.identity_a_entity_id IS NULL AND h.identity_b_entity_id IS NULL)
      ) x
     WHERE h.program_id = p_program_id
       AND h.status = 'testable'
       AND h.superseded_by IS NULL
       AND e.in_scope
       AND NOT EXISTS (SELECT 1 FROM tasks k
                        WHERE k.program_id = h.program_id
                          AND k.kind = 'hunt'
                          AND k.hypothesis_id = h.id
                          AND k.selected_identity_entity_id
                              IS NOT DISTINCT FROM x.identity_entity_id);
$fn$;

COMMENT ON FUNCTION rk2_hypothesis_hunt_frontier(uuid) IS
  'The (testable claim, Identity) pairs of a Program that no hunt Task names yet. Ticket 131: a claim naming two Identities is two rows and becomes two Tasks, which is how an identity differential is taken -- one Tool run is many exchanges and cannot spend two Identities. Any status rather than a live one: a Task that ran and finished is an answer, and deriving it again is a loop.';

REVOKE ALL ON FUNCTION rk2_hypothesis_hunt_frontier(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION rk2_hypothesis_hunt_frontier(uuid) TO rk2_runtime;

-- The live dedup key grows with the column, which is 20261014T000000Z's rule
-- for `test_id` and the same rule: a kind that acts on one row has to be able
-- to name it, and two hunt Tasks over one claim under two Identities are two
-- pieces of work rather than one written twice. Without this the second half of
-- every differential collides with the first on
-- (program, kind, subject, hypothesis, NULL finding, NULL test), which is a
-- `unique_violation` raised out of the middle of the ranking pass.
DROP INDEX tasks_live_dedup_idx;
CREATE UNIQUE INDEX tasks_live_dedup_idx
    ON tasks (program_id, kind, subject_entity_id, hypothesis_id, finding_id,
              test_id, selected_identity_entity_id)
       NULLS NOT DISTINCT
 WHERE status IN ('pending','claimed','running','parked');

-- Restated whole because a plpgsql body cannot be amended in place. Every line
-- is 20261012T000000Z's except the derivation's column list and the frontier's
-- new ordering key, which keeps the ceiling reproducible now that one claim can
-- produce two rows.
CREATE OR REPLACE FUNCTION derive_hypothesis_hunts() RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p        uuid := rk2_program_required();
    ceiling  smallint;
    n_graded bigint := 0;
    n_wanted bigint := 0;
    n_tasks  bigint := 0;
BEGIN
    SELECT w.max_hunts_derived_per_pass INTO ceiling
      FROM scheduler_weights w WHERE w.active;
    IF NOT FOUND THEN RAISE EXCEPTION 'no active scheduler_weights row'; END IF;

    -- (1) Grading. Uncapped: see 20261012T000000Z section 1.
    WITH graded AS (
        INSERT INTO hypothesis_transitions
                    (hypothesis_id, program_id, from_status, to_status,
                     actor_kind, rationale)
        SELECT g.hypothesis_id, p, 'proposed', 'testable', 'runtime',
               'the ranking pass graded this claim settleable by a Test'
          FROM rk2_gradable_claims(p) g
        RETURNING 1 AS one
    )
    SELECT count(*) INTO n_graded FROM graded;

    SELECT count(*) INTO n_wanted FROM rk2_hypothesis_hunt_frontier(p);

    -- (2) The Tasks, oldest claim first. Oldest and not highest-ranked: the
    --     ranking scores Tasks and these Tasks do not exist yet, so the only
    --     order available here is the order the claims arrived in. It is
    --     deterministic, which is what the ceiling needs to be reproducible.
    --
    --     The Identity is written rather than defaulted, and it is the only
    --     caller in the corpus that writes one: this is where the two halves of
    --     a differential stop being the same anonymous caller. A NULL from the
    --     frontier is a Program whose anonymous Identity has not been minted,
    --     and `select_task_identity` mints it on the way in.
    WITH wanted AS (
        SELECT fr.hypothesis_id, fr.subject_entity_id, fr.identity_entity_id
          FROM rk2_hypothesis_hunt_frontier(p) fr
         ORDER BY fr.created_at, fr.hypothesis_id, fr.identity_entity_id
         LIMIT ceiling
    ), made AS (
        INSERT INTO tasks (program_id, kind, hypothesis_id, subject_entity_id,
                           selected_identity_entity_id)
        SELECT p, 'hunt', w.hypothesis_id, w.subject_entity_id, w.identity_entity_id
          FROM wanted w
        RETURNING 1 AS one
    )
    SELECT count(*) INTO n_tasks FROM made;

    RETURN jsonb_build_object('graded', n_graded,
                              'candidates', n_wanted,
                              'derived', n_tasks,
                              'deferred', greatest(n_wanted - n_tasks, 0),
                              'ceiling', ceiling);
END $fn$;

COMMENT ON FUNCTION derive_hypothesis_hunts() IS
  'Grades every gradable proposed claim testable, then opens up to max_hunts_derived_per_pass hunt Tasks against the (claim, Identity) pairs no hunt Task names. The entrance to the loop between recon and a Finding. Ticket 131: a claim naming two Identities derives two Tasks, one per Identity, which is what an identity differential is.';
