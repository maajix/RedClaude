-- ---------------------------------------------------------------------------
-- 20261124T000000Z__a_test_is_spent_in_the_state_its_claim_was_made_in.sql
--
-- Ticket 192. The far end of the loop, and the schema check standing in front
-- of it.
--
-- Ticket 191 made the lanes that explore work a target in every provisioned
-- state. The lane that settles what they find did not move.
-- `derive_test_performances` inserts a `perform` Task naming the Test, the
-- claim and the subject, and never the Identity, so `select_task_identity`
-- filled the NULL with the anonymous one. A hunt that finds something while
-- signed in authors a Test, and the Test is replayed signed out against a
-- target state the claim was never made about. It comes back negative, the
-- claim is refuted, and nothing records that the two runs were looking at
-- different things. That is worse than not testing it: it writes down a wrong
-- answer.
--
-- Three parts, in the order they have to happen.
--
-- 1. The check. 0019 carries
--
--        -- a renderer holds no session and drives no identity
--        CHECK (runs_as <> 'renderer' OR NOT clamp_to_identity_leases)
--
--    and the sentence was written about the `reporter`, which was the only
--    renderer 0019 shipped: it renders a document and sends nothing. Ticket
--    152's `performer` was made a renderer afterwards and drives the replay
--    Lane, which sends real requests to a real target through the door. The
--    check generalised a property of one row into a rule about a category, and
--    the category acquired a member the rule was never true of.
--
--    What `renderer` actually means is still checked, by the two constraints
--    this file does not touch: `roles_renderer_runs_no_model` and
--    `roles_renderer_loads_nothing`. Both are as true of the performer as of
--    the reporter. Driving an Identity is not in that family -- it is a
--    property of the lane's work, which `clamp_to_identity_leases` is the
--    column for, and the roster is where it is decided. A check that restates
--    a roster decision adds nothing and, here, contradicted it.
--
-- 2. The clamp. `claim_task` takes the Lease only for a clamped role, and both
--    the door and `rk2_replay_plan` refuse a named slot without a live one. So
--    inheriting the Identity without this would turn a silent wrong answer
--    into a loud refusal -- better, and still not the fix.
--
-- 3. The inheritance, in `select_task_identity`, which is the BEFORE INSERT
--    trigger every INSERT into `tasks` passes through. It belongs there rather
--    than in each derivation, and it is done only where there is exactly one
--    answer to inherit: a `perform` Task spends one Test, a Test was authored
--    by one run, and that run held one Identity, so
--    `tests.created_by_run_id -> agent_runs.task_id ->
--    tasks.selected_identity_entity_id` has a single value at the end of it.
--    A `conclude` Task or a chain unlock derived from a claim reached by two
--    Identities has two, and must not guess. Those stay anonymous by default
--    and stay ticket 192's open half.
--
-- What this does not change: no authority. A perform Task selecting a
-- non-anonymous Identity still reaches `net_borrowed_identity`, is still graded
-- `approval_required` asking `credential_needed`, and still parks for a person
-- before one request leaves.
-- ---------------------------------------------------------------------------

-- ===========================================================================
-- 1. The check that was about one row
-- ===========================================================================

ALTER TABLE roles DROP CONSTRAINT roles_check;

COMMENT ON COLUMN roles.clamp_to_identity_leases IS
  'Whether this role acts as an Identity and must hold its Lease for as long '
  'as it acts. Decided by the roster, for every role: a renderer that sends '
  'real requests through the replay Lane needs it exactly as much as a '
  'subagent does.';


-- ===========================================================================
-- 2. The lane that acts as an account holds it
-- ===========================================================================

UPDATE roles SET clamp_to_identity_leases = true
 WHERE role = 'performer';


-- ===========================================================================
-- 3. The inheritance
-- ===========================================================================

CREATE OR REPLACE FUNCTION select_task_identity() RETURNS trigger
LANGUAGE plpgsql AS $fn$
BEGIN
    -- Inherited before it is defaulted, and only where there is one answer to
    -- inherit. See the header: a Test has exactly one author, an author has
    -- exactly one Identity, and every other derivation has two or more.
    IF NEW.selected_identity_entity_id IS NULL
       AND NEW.kind = 'perform'
       AND NEW.test_id IS NOT NULL THEN
        SELECT k.selected_identity_entity_id
          INTO NEW.selected_identity_entity_id
          FROM tests t
          JOIN agent_runs ar ON ar.id = t.created_by_run_id
          JOIN tasks k ON k.id = ar.task_id
         WHERE t.id = NEW.test_id
           AND t.program_id = NEW.program_id;
    END IF;
    NEW.selected_identity_entity_id := coalesce(
        NEW.selected_identity_entity_id, rk2_anonymous_identity(NEW.program_id));
    RETURN NEW;
END $fn$;

COMMENT ON FUNCTION select_task_identity() IS
  'Fills tasks.selected_identity_entity_id: inherited from the Test''s author '
  'for a perform Task, and the anonymous Identity for everything else that '
  'did not say.';


-- ===========================================================================
-- 4. The Tasks that already exist
-- ===========================================================================

-- The same backfill 20261120T000000Z ran for `recon`, for the same reason:
-- `claim_task` raises on a clamped Task that names nothing to hold, and the
-- projection skipped these Tasks precisely because their role was not clamped
-- a moment ago. A Task whose run is holding a Lease is left alone.
DO $$
DECLARE r tasks%ROWTYPE; n integer := 0;
BEGIN
    FOR r IN
        SELECT t.* FROM tasks t
          JOIN role_task_kinds m ON m.kind = t.kind
         WHERE m.role = 'performer'
           AND NOT EXISTS (SELECT 1 FROM task_identities ti WHERE ti.task_id = t.id)
           AND NOT EXISTS (SELECT 1 FROM agent_runs ar
                             JOIN identity_leases l ON l.holder_agent_run_id = ar.id
                            WHERE ar.task_id = t.id AND l.released_at IS NULL)
         ORDER BY t.id
    LOOP
        PERFORM rk2_project_task_identities(r);
        n := n + 1;
    END LOOP;
    RAISE NOTICE 'ticket 192: projected task_identities for % perform Task(s)', n;
END $$;

-- The Identity of a `perform` Task that already exists is not rewritten. Every
-- one of them was derived from a Test authored by an anonymous run, so the
-- inheritance above would give them what they already hold -- and a statement
-- that moved a live Task to another state would be changing what a Lease was
-- taken for while it is held. Guard (ii) is what says so out loud.


-- ===========================================================================
-- 5. The guards
-- ===========================================================================

DO $$
DECLARE n integer; d text;
BEGIN
    -- (i) A clamped Task with nothing to hold is a claim that raises. The
    --     projection above exists to make this empty; if it is not, the
    --     backfill missed a row and the next claim of it stops the campaign.
    SELECT count(*), string_agg(t.label, ', ')
      INTO n, d
      FROM tasks t
      JOIN role_task_kinds m ON m.kind = t.kind
      JOIN roles r ON r.role = m.role
     WHERE r.clamp_to_identity_leases
       AND t.status IN ('pending', 'claimed', 'running', 'parked')
       AND NOT EXISTS (SELECT 1 FROM task_identities ti WHERE ti.task_id = t.id)
       AND NOT EXISTS (SELECT 1 FROM agent_runs ar
                         JOIN identity_leases l ON l.holder_agent_run_id = ar.id
                        WHERE ar.task_id = t.id AND l.released_at IS NULL);
    IF n > 0 THEN
        RAISE EXCEPTION 'a live clamped Task names no Identity to hold (%): %', n, d;
    END IF;

    -- (ii) Nothing that already existed moved. A perform Task whose Test was
    --      authored anonymously still selects the anonymous Identity.
    SELECT count(*), string_agg(t.label, ', ')
      INTO n, d
      FROM tasks t
      JOIN tests s ON s.id = t.test_id
      LEFT JOIN agent_runs ar ON ar.id = s.created_by_run_id
      LEFT JOIN tasks k ON k.id = ar.task_id
     WHERE t.kind = 'perform'
       AND t.selected_identity_entity_id
           IS DISTINCT FROM coalesce(k.selected_identity_entity_id,
                                     rk2_anonymous_identity_id(t.program_id));
    IF n > 0 THEN
        RAISE EXCEPTION
            'a perform Task is spent in a state its Test was not authored in (%): %',
            n, d;
    END IF;

    -- (iii) The check that was dropped protected something real about a
    --       renderer, and the two that carry it are still there.
    SELECT count(*) INTO n
      FROM pg_constraint
     WHERE conrelid = 'roles'::regclass
       AND conname IN ('roles_renderer_runs_no_model', 'roles_renderer_loads_nothing');
    IF n <> 2 THEN
        RAISE EXCEPTION 'a renderer is no longer held to running no model and loading nothing';
    END IF;
END $$;
