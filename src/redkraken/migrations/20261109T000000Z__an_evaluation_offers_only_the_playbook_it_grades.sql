-- ---------------------------------------------------------------------------
-- 20261109T000000Z__an_evaluation_offers_only_the_playbook_it_grades.sql
--                                                        (ticket 179)
--
-- `record_playbook_selection` writes every row `select_playbooks` decided, kept
-- and dropped both. `a_evaluation_program_runs_one_playbook`
-- (20260824T000000Z) is a BEFORE INSERT trigger on the same table that raises
-- when an evaluation Program records a Playbook other than the one it grades.
-- The two do not fit: the selection offers whatever the subject's facts match,
-- the trigger refuses the second one, and because it refuses by raising it takes
-- the whole call down -- including the row for the Playbook actually under
-- evaluation, which had already been decided in the same statement.
--
-- What that costs, measured. Canary attempt five, database `rk2grade5`,
-- 2026-08-24. Five evaluations, one per graded pair. Four of them ended:
--
--     no Playbook could be selected for T3: 23514: program ... evaluates
--     playbooks/object-ownership/playbook.md, so it cannot also select
--     playbooks/attack-surface/playbook.md
--
-- and filed nothing: `playbook_selections` in that database holds four rows,
-- every one of them `attack-surface` inside `attack-surface`'s own evaluation.
-- `execution._select` turns the refusal into an `INVALID_CONFIGURATION`
-- violation, `evaluation._repeat` discards the repeat, and the verdict is
-- `untested` -- the same shape of silent zero tickets 175 through 178 each
-- found, arriving from a different direction.
--
-- The trigger is right about what must not be stored. It is in the wrong place
-- to be the thing that decides it: a guard that raises is a backstop, and a
-- backstop that fires on ordinary input is a filter that was never written. So
-- the filter is written here, one clause, where the rows are chosen:
--
--     an evaluation Program records the Playbook it evaluates and nothing else.
--
-- Everything outside an evaluation is unchanged -- `evaluation_programs` has no
-- row for a real Program, the coalesce falls through to `s.playbook_id`, and
-- every candidate is recorded exactly as before. The trigger stays where it is
-- and stops being reachable from this path, which is what a backstop is for.
--
-- Not a widening. Fewer rows are written, never more, and only inside a
-- Program whose whole purpose is one Playbook. `select_playbooks` returns every
-- matching Playbook exactly once, so the evaluated one is in the set whenever
-- the subject matched it at all; if the subject did not match it, this call
-- records nothing and the run reports the same "kept nothing" it reports today.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION record_playbook_selection(
        p_task uuid, p_subject uuid, p_property_class text DEFAULT NULL,
        p_ceiling text DEFAULT 'constrained', p_limit integer DEFAULT 3)
RETURNS integer LANGUAGE plpgsql AS $$
DECLARE
    v_program uuid;
    v_role    text;
    v_kept    integer := 0;
BEGIN
    SELECT t.program_id, m.role INTO v_program, v_role
      FROM tasks t LEFT JOIN role_task_kinds m ON m.kind = t.kind
     WHERE t.id = p_task;
    IF v_program IS NULL THEN
        RAISE EXCEPTION 'task % does not exist', p_task;
    END IF;
    IF v_role IS NULL THEN
        RAISE EXCEPTION 'no role executes the kind task % carries', p_task;
    END IF;

    -- One statement, because the freeze and the count are about the rows this
    -- call decided and nothing else. Reading them back off the Task instead
    -- would be a different question that happens to have the same answer today:
    -- `playbook_selections` is unique on (task_id, playbook_id), so a second
    -- call is refused before it can reach the freeze. That is a constraint
    -- somewhere else holding this function up, and it is one edit away from
    -- stopping.
    WITH decided AS (
        INSERT INTO playbook_selections
            (program_id, task_id, subject_entity_id, playbook_id,
             rank, dropped_because, dropped_detail)
        SELECT v_program, p_task, p_subject, s.playbook_id,
               s.rank, s.dropped_because, s.dropped_detail
          FROM select_playbooks(v_program, p_subject, p_property_class,
                                v_role, p_ceiling, p_limit) s
         -- Ticket 179. An evaluation Program records the Playbook it grades and
         -- nothing else. A real Program has no `evaluation_programs` row, the
         -- coalesce falls through to the candidate's own id, and every row is
         -- recorded as before.
         WHERE s.playbook_id = coalesce(
                   (SELECT e.playbook_id FROM evaluation_programs e
                     WHERE e.program_id = v_program),
                   s.playbook_id)
        RETURNING id, playbook_id, dropped_because
    ),
    -- A dropped Playbook was never loaded, and recording the Skills it would
    -- have used would be recording a run that did not happen.
    kept AS (
        SELECT id, playbook_id FROM decided WHERE dropped_because IS NULL
    ),
    frozen AS (
        INSERT INTO playbook_selection_skills
            (selection_id, program_id, skill_name, skill_sha256, skill_version)
        SELECT k.id, v_program, ps.skill_name, sk.source_sha256, sk.version
          FROM kept k
          JOIN playbook_skills ps ON ps.playbook_id = k.playbook_id
          JOIN skills sk ON sk.name = ps.skill_name
        RETURNING 1
    )
    SELECT count(*)::int INTO v_kept FROM kept;

    RETURN v_kept;
END $$;

COMMENT ON FUNCTION record_playbook_selection(uuid, uuid, text, text, integer) IS
    'Ticket 45 criterion 4: run the selection for a Task and write down what it '
    'decided, kept rows and dropped rows both, with the Playbook and Skill '
    'digests frozen as they stand now. The program and the role come from the '
    'Task; a caller that could name the role could record a selection made '
    'under one that will never run it. Ticket 179: inside an evaluation Program '
    'only the Playbook being graded is recorded, because the trigger that '
    'refuses a second one refuses by raising and would take the graded row with '
    'it.';
