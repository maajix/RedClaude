-- ---------------------------------------------------------------------------
-- 20260925T010000Z__a_finished_run_says_what_its_playbook_produced.sql
--                                                                  (ticket 121)
--
-- 027 gave `playbook_selections.outcome` three values and a default of
-- `running`, and 045 wrote down which columns of that row a run is still
-- allowed to move: "`outcome` and `went_stale_at` are what a run updates".
-- Neither has ever moved. `record_playbook_selection` inserts at the default
-- and returns, `mark_stale_selections` has no caller anywhere in the tree, and
-- every rule that reads the far end of those two columns has therefore been
-- unfalsifiable since the day it was written -- the `produced` and `exhausted`
-- arms of `playbook_selections_outcome_check`, the
-- `playbook_selections_dropped_has_no_outcome` clause that asserts a dropped
-- row stays at `running`, and `check_playbook_integrity`'s `stale_during_run`,
-- which asks for a selection that is stale and still running and can never find
-- one.
--
-- The cost is not bookkeeping. `playbook_candidates` drops a Playbook for a
-- subject with the reason `exhausted` when an earlier selection on the same
-- (program, subject, playbook) carries that outcome, and that is the only
-- memory the funnel has. With nothing writing it, a Playbook that has already
-- been run against a subject and found nothing is offered again on every pass
-- for as long as the hunt lasts, and what the harness already tried is
-- recoverable from a transcript rather than from a table.
--
-- WHAT `produced` IS MEASURED BY, WHICH IS THE DECISION THIS FILE OWES.
--
-- 046 states the constraint plainly. `playbook_promotion_evidence` joins a
-- selection to a hypothesis on (program, subject, property class) through
-- `playbook_outputs`, "and there is no other edge between a selection and the
-- hypothesis it caused": 010 measured a keep limit of three, so up to three
-- Playbooks sit on one subject and nothing downstream can say which of them the
-- model was following when it raised a claim. This file does not invent a
-- narrower edge. It settles the outcome off the one edge the schema already
-- grades promotions with, so that the row a promotion reads and the row a
-- selection writes are answering the same question.
--
-- The two answers are not symmetric, and the predicate is written to fail
-- towards the reversible one. A wrong `exhausted` is permanent: the Playbook is
-- dropped for that subject on every later pass and no later run can undo it. A
-- wrong `produced` costs one more offer. So `produced` is the generous arm --
-- a hypothesis on a class this Playbook declares, at whatever status it reached
-- and whether or not something later superseded it -- and `exhausted` is what
-- is left when the run raised nothing the Playbook claims to be able to
-- conclude. That is deliberately wider than `playbook_promotion_evidence`,
-- which goes on requiring `supported`, evidence of the supporting polarity and
-- an Observation under that: promotion is a conjunction, so a selection settled
-- `produced` here has cleared the first of its conditions and none of the rest,
-- and widening this arm cannot promote anything the narrow one refuses.
--
-- A Playbook that declares no output class at all settles `produced`, and the
-- word is wrong in the direction the paragraph above chose to be wrong in.
-- There is no class to look for, so the measurement could never have come out
-- any other way, and reading the absence of a declaration as the absence of a
-- result would retire that Playbook on that subject forever on the strength of
-- a question nobody could have answered. `playbook._playbook` requires
-- `bb:outputs` and refuses an empty one, so the only rows this arm can reach
-- are catalogue rows somebody wrote by hand.
--
-- WHEN, WHICH IS THE OTHER HALF OF NOT WRITING `exhausted` BY ACCIDENT.
--
-- Only once the Task itself is settled. `finish_task_attempt` gives a Task back
-- to the queue with its attempt spent whenever the attempt promoted nothing and
-- the Task has attempts left, and the retry runs under the selection this
-- attempt recorded -- `playbook_selections` is unique on (task_id, playbook_id),
-- so there is no second set for it to record. A settlement that fired on the
-- attempt rather than on the Task would therefore retire a Playbook because a
-- container failed to start, and would retire it in front of the retry that was
-- about to run it properly. So the verb reads the Task's status for itself and
-- answers that the Task is still open for anything outside `done`, `failed` and
-- `abandoned`, rather than taking a word from the caller that closed it.
--
-- That leaves the Task nobody was awake to settle: `reconcile_leases` retires a
-- Task whose owner stopped beating, and no runtime calls this verb for it. Its
-- selections stay at `running`, which is what every selection in the corpus was
-- before this file, so the Playbook goes on being offered exactly as it did
-- yesterday. Untouched rather than swept, because a second sweep that settled
-- Tasks it had never watched would be writing `exhausted` about runs it knows
-- nothing about, and that is the one value worth being slow with.
--
-- THE SWEEP, WHICH ALREADY EXISTED AND HAD NOBODY TO RUN IT.
--
-- `mark_stale_selections` needs nothing from this file. 027 wrote it, it is
-- open to PUBLIC, and `rk2_runtime` has held EXECUTE on it and UPDATE on
-- `playbook_selections` since 029 seeded the surface 66 now declares. What it
-- lacked was a caller, and the caller is `rk run`'s own pass, beside the Lease
-- reconciliation and before anything is offered. 027 is explicit that staleness
-- is evaluated at selection and never mid-run, so the sweep is a record and not
-- an eviction: it stamps `went_stale_at` on a live selection whose Playbook
-- expired under it and leaves the run alone, and `stale_during_run` is what
-- turns that stamp into something an operator reads.
--
-- Depends on 027 (the column, the constraints and the sweep), 030 and 046 (the
-- promotion edge this reuses) and 045 (the freeze that admits exactly these two
-- columns). A new file rather than an edit to any of them: a recorded migration
-- whose file has changed is schema drift and `rk db migrate` refuses the whole
-- corpus for it.
-- ---------------------------------------------------------------------------


-- ===========================================================================
-- 1. The writer 045 named and nobody wrote
-- ===========================================================================

-- One argument, and it is the Task. Everything else this settlement turns on
-- is on the rows the Task already names: the Program and the subject are frozen
-- on the selection, the status is on the Task, and the classes are on the
-- Playbook. `record_playbook_selection` takes the Program from the Task for the
-- same reason -- a caller that could name it could settle selections belonging
-- to a run it was not closing.
CREATE FUNCTION settle_playbook_selections(p_task uuid)
RETURNS jsonb LANGUAGE plpgsql AS $fn$
DECLARE
    v_task      tasks%ROWTYPE;
    n_produced  integer := 0;
    n_exhausted integer := 0;
BEGIN
    SELECT * INTO v_task FROM tasks t WHERE t.id = p_task;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'task % does not exist', p_task USING ERRCODE = '23514';
    END IF;

    -- A Task on its way back to the queue is not a Playbook that has been
    -- tried, and answering rather than raising is what lets the runtime call
    -- this after every attempt without knowing which attempt was the last one.
    IF v_task.status NOT IN ('done', 'failed', 'abandoned') THEN
        RETURN jsonb_build_object(
            'task', v_task.label, 'task_status', v_task.status, 'settled', false,
            'produced', 0, 'exhausted', 0);
    END IF;

    -- `dropped_because IS NULL` is not an optimisation. A dropped Playbook was
    -- never loaded and never read, so it produced nothing and exhausted
    -- nothing, and `playbook_selections_dropped_has_no_outcome` says so as a
    -- constraint. This clause is what holds the first writer of this column to
    -- the rule the column was given before there was one.
    --
    -- `outcome = 'running'` for the second half of the same idea: a settled
    -- selection is a decision already taken, and a Task closed twice -- which
    -- `finish_task_attempt` explicitly tolerates -- must not get a second
    -- answer out of a subject that has moved since the first.
    WITH settled AS (
        UPDATE playbook_selections s
           SET outcome = CASE
                 WHEN EXISTS (
                        SELECT 1
                          FROM playbook_outputs po
                          JOIN hypotheses h
                            ON h.program_id        = s.program_id
                           AND h.subject_entity_id = s.subject_entity_id
                           AND h.property_class    = po.property_class
                         WHERE po.playbook_id = s.playbook_id)
                      THEN 'produced'
                 WHEN NOT EXISTS (
                        SELECT 1 FROM playbook_outputs po
                         WHERE po.playbook_id = s.playbook_id)
                      THEN 'produced'
                 ELSE 'exhausted'
               END
         WHERE s.task_id = p_task
           AND s.dropped_because IS NULL
           AND s.outcome = 'running'
        RETURNING s.outcome AS outcome)
    SELECT count(*) FILTER (WHERE outcome = 'produced')::int,
           count(*) FILTER (WHERE outcome = 'exhausted')::int
      INTO n_produced, n_exhausted
      FROM settled;

    RETURN jsonb_build_object(
        'task', v_task.label, 'task_status', v_task.status, 'settled', true,
        'produced', n_produced, 'exhausted', n_exhausted);
END $fn$;

COMMENT ON FUNCTION settle_playbook_selections(uuid) IS
 'Ticket 121. Says what the Playbooks a settled Task ran under produced, on the '
 'one edge there is between a selection and a claim: a hypothesis for this '
 'Program and subject on a class the Playbook declares as an output. Anything '
 'else is `exhausted`, which is what stops the same Playbook being offered '
 'against the same subject on every later pass. Answers without writing while '
 'the Task can still be retried, and never touches a dropped selection.';

REVOKE ALL ON FUNCTION settle_playbook_selections(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION settle_playbook_selections(uuid) TO rk2_runtime;

-- 66's registry rather than the grant above on its own: `apply_runtime_grants`
-- grants what this table names and `check_runtime_privileges` fails on anything
-- the runtime holds beyond it, so a closed verb with no row here is a verb the
-- next finalizer takes back.
INSERT INTO runtime_verb_surface (verb, added_by, note) VALUES
    ('settle_playbook_selections(uuid)', '121',
     'writes what a settled Task''s kept Playbook selections produced, which is what `exhausted` then suppresses');


-- ===========================================================================
-- 2. What this migration claims, asserted
-- ===========================================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_proc
         WHERE proname = 'settle_playbook_selections'
           AND has_function_privilege('rk2_runtime', oid, 'EXECUTE')
    ) THEN
        RAISE EXCEPTION 'ticket 121: the runtime cannot settle a selection';
    END IF;

    -- The sweep half. Nothing here grants it, so this is the assertion that the
    -- caller `rk run` just acquired is a caller that will be allowed to run:
    -- the verb is reachable and the table it writes is writable.
    IF NOT EXISTS (
        SELECT 1 FROM pg_proc
         WHERE proname = 'mark_stale_selections'
           AND has_function_privilege('rk2_runtime', oid, 'EXECUTE')
    ) OR NOT has_table_privilege('rk2_runtime', 'playbook_selections', 'UPDATE') THEN
        RAISE EXCEPTION 'ticket 121: the staleness sweep has a caller that cannot run it';
    END IF;

    -- The three rules this file exists to make falsifiable, asserted at the
    -- moment their first writer arrives. Each of them was satisfiable by doing
    -- nothing for as long as the column never moved, so a later migration that
    -- dropped one would have cost nothing yesterday and costs the whole of this
    -- ticket today.
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conrelid = 'playbook_selections'::regclass
           AND conname = 'playbook_selections_dropped_has_no_outcome'
    ) THEN
        RAISE EXCEPTION 'ticket 121: a dropped selection is no longer held to running';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conrelid = 'playbook_selections'::regclass
           AND conname = 'playbook_selections_outcome_check'
           AND pg_get_constraintdef(oid) LIKE '%exhausted%'
    ) THEN
        RAISE EXCEPTION 'ticket 121: the outcome vocabulary no longer offers exhausted';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
         WHERE tgrelid = 'playbook_selections'::regclass
           AND tgname = 'playbook_selection_frozen'
    ) THEN
        RAISE EXCEPTION 'ticket 121: nothing holds the rest of a selection frozen';
    END IF;

    -- And the edge the settlement is measured on. `playbook_outputs` empty
    -- would not raise anywhere: every selection would settle through the
    -- no-declared-class arm and read `produced` forever, which is this file
    -- doing nothing while reporting that it worked.
    IF NOT EXISTS (SELECT 1 FROM playbook_outputs) THEN
        RAISE EXCEPTION 'ticket 121: no Playbook declares an output to measure a run against';
    END IF;
END $$;
