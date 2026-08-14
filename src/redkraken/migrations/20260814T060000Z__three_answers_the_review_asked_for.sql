-- Three corrections the whole-tree review found, and nothing else.
--
-- None of them is a feature. Each is a place where the corpus says one thing in
-- prose and does another in SQL, and each is fixed here rather than in the file
-- that introduced it because a migration's checksum is what proves it has not
-- been edited since it was applied.
--
--   1. `relationship_provenance` has no `COMMENT ON TABLE` and its twin
--      `entity_provenance` does. It is the only table in the timestamped era
--      without one.
--
--   2. `charge_unmeasured_run` charges a run that was killed and settles a run
--      that was parked at zero. 025's own prose names park as one of the six
--      endings that reconcile, and the argument it makes against settling an
--      abort at zero is word for word the argument against settling a park at
--      zero.
--
--   3. 025 set a convention when it added `budget_refusal_for` to the
--      eligibility rule: the ticket that adds an arm adds that arm's no-clock
--      check, in its own file, because "a check that has to be edited in a
--      neighbour's file to cover a new arm is a check the next ticket forgets".
--      027 added `skills_ungranted_for` and forgot exactly that.


-- ---------------------------------------------------------------------------
-- 1. The provenance twin that was never described
-- ---------------------------------------------------------------------------
-- The same sentence as `entity_provenance`, because it is the same table about
-- the other half of the surface. Not `state_read_surface`: the registry there
-- deliberately stops at `origins` on the record -- "which Receipt, from which
-- run, at which second is the supervisor's question" -- and widening an agent's
-- read surface is not something a missing comment is evidence for.

COMMENT ON TABLE relationship_provenance IS
    'One row per piece of evidence for one Relationship. Append-only in '
    'practice: convergence adds rows, never replaces them.';


-- ---------------------------------------------------------------------------
-- 2. A parked run spent what it promised, not nothing
-- ---------------------------------------------------------------------------
-- A park is not a pause inside a live child. `park_authorized_tool_run` marks
-- the run finished, releases both halves of the Lease, unbinds the session and
-- abandons every other open Tool run under it -- the child is gone, and it is
-- gone at a tool call, which means it had already reached the model and already
-- spent tokens. Nothing writes its usage afterwards: `finish_task_attempt`
-- updates `WHERE finished_at IS NULL`, and park set `finished_at` on the way
-- out, so the measured number the runtime holds lands nowhere.
--
-- Settled at zero, that is a Program which gets its whole promise back for work
-- it paid for, and a model that parks itself is a model that runs for free.
-- Charged what it reserved, it is the same rule as an abort and for the same
-- stated reason: what it promised is the only number anyone has a right to.
--
-- The resumed run reserves again, so a parked-and-resumed unit of work is
-- charged its ceiling twice. That is the conservative direction and the
-- intended one -- the alternative is a park that costs nothing, which is a
-- budget with a hole in it rather than a budget that is sometimes strict.
--
-- Still only when nothing was measured. A run that reported usage keeps it.

CREATE OR REPLACE FUNCTION charge_unmeasured_run() RETURNS trigger
LANGUAGE plpgsql AS $fn$
DECLARE v_promised bigint;
BEGIN
    IF NEW.stop_reason IN ('aborted', 'parked')
       AND NEW.input_tokens IS NULL AND NEW.output_tokens IS NULL
       AND NEW.runs_as IS DISTINCT FROM 'renderer' THEN
        SELECT br.tokens INTO v_promised
          FROM budget_reservations br
         WHERE br.agent_run_id = NEW.id AND br.settled_at IS NULL;
        -- A promise of nothing is nothing to charge: an unbounded Program with
        -- no per-run ceiling reserved NULL, and there is no number to write.
        IF v_promised IS NOT NULL THEN
            NEW.input_tokens  := v_promised;
            -- Both columns, because `program_budget` sums `input + output` per
            -- run and NULL + n is NULL: a charge written to one column alone
            -- is a charge the Program's own budget never sees.
            NEW.output_tokens := 0;
        END IF;
    END IF;
    RETURN NEW;
END $fn$;

COMMENT ON FUNCTION charge_unmeasured_run() IS
    'Charges a run that was killed, lost or parked what its claim reserved, '
    'because a run that cannot report is not a run that spent nothing. Only '
    'when nothing was measured: a reported zero is a measurement and stands.';


-- ---------------------------------------------------------------------------
-- 3. The arm 027 added, guarded the way 025 said to guard one
-- ---------------------------------------------------------------------------
-- `skills_ungranted_for` reads no clock today. This is what keeps that true:
-- the ranking filter runs it through `claimable_for`, and a wall clock anywhere
-- under that filter makes two passes over the same rows disagree -- which is
-- decision 12, and which 023 and 025 each assert for the arms they own.
--
-- Arms (a) to (f) are 027's, reproduced unchanged. `CREATE OR REPLACE` replaces
-- the whole body, so they are here because they have to be, not because they
-- changed.

CREATE OR REPLACE FUNCTION check_orchestrator_dispatch()
RETURNS TABLE (problem text, subject text, detail text)
LANGUAGE sql STABLE AS $fn$
    -- (a) criterion 4, against the rule that carries it, as a chain of two: the
    --     admission rule has to ask the skill predicate, and the skill predicate
    --     has to ask the grants. Either link cut is a `claimable_for` that
    --     admits work no role can run, and the Task would fail inside a child
    --     that had already started.
    SELECT 'skill_rule_not_shared', asked.fn,
           'the admission rule decides without asking which role may load the Task''s Skills'
      FROM (VALUES ('claimable_for'::text, 'skills_ungranted_for'::text),
                   ('skills_ungranted_for', 'role_skills')) AS asked(fn, asks)
      JOIN pg_proc p ON p.proname = asked.fn
                    AND p.pronamespace = 'public'::regnamespace
     WHERE p.prosrc !~ asked.asks

UNION ALL
    -- (b) the same criterion as an outcome rather than as text: whatever the
    --     rule says, no outstanding Slate entry may be one whose Skills the
    --     role that would run it cannot load. It asks the same predicate the
    --     rule asks, so this arm reports on what the offer did rather than on a
    --     second, hand-copied idea of what it should have done.
    SELECT 'slate_offers_an_unloadable_skill', t.label,
           'an offered Task requires a Skill the one role that runs its kind was never granted'
      FROM task_slate s JOIN tasks t ON t.id = s.task_id
     WHERE NOT s.consumed AND skills_ungranted_for(t)

UNION ALL
    -- (c) the orchestrator holds no egress, stated against the rows rather than
    --     against the roster. Planning that reached a target is testing nobody
    --     scheduled, nobody budgeted and no Task accounts for -- and the run
    --     that made a choice is the one run in the corpus that must never have
    --     a Receipt behind it. Keyed on having recorded a choice rather than on
    --     the role, because `rk send` records an operator's own request as an
    --     orchestrator session and that request is a person's, not a model's.
    SELECT 'planning_reached_a_target', ar.label,
           'the session a choice was recorded against also opened a request to a target'
      FROM agent_runs ar
      JOIN tool_runs tr ON tr.agent_run_id = ar.id
     WHERE tr.tool = 'mcp__rk2__net_request'
       AND EXISTS (SELECT 1 FROM events e
                    WHERE e.agent_run_id = ar.id AND e.type = 'scheduler.chose')

UNION ALL
    -- (d) 023's rule for the scheduler surface, extended to the two verbs this
    --     file adds. A model that could open its own session could attribute a
    --     choice to a run nothing dispatched.
    SELECT 'choice_verb_reachable_by_the_agent', p.proname::text,
           'a connection a model reaches through can open a planning session or commit a choice'
      FROM pg_proc p
     WHERE p.pronamespace = 'public'::regnamespace
       AND p.proname IN ('open_orchestrator_session','record_choice')
       AND has_function_privilege('rk2_state', p.oid, 'EXECUTE')

UNION ALL
    -- (e) criterion 6's auditability half: every recorded choice names the
    --     Task-less session that made it. An Event naming a worker run would
    --     be a choice attributed to the thing that was chosen.
    SELECT 'choice_is_unattributed', e.id::text,
           'a recorded choice names no Task-less orchestrator session'
      FROM events e
      LEFT JOIN agent_runs ar ON ar.id = e.agent_run_id
     WHERE e.type = 'scheduler.chose'
       AND (ar.id IS NULL OR ar.role <> 'orchestrator' OR ar.task_id IS NOT NULL)

UNION ALL
    -- (f) and its determinism half. The runtime dispatches on these five words;
    --     a sixth in the log is an outcome nothing downstream has a branch for.
    SELECT 'choice_outcome_unknown', coalesce(e.payload ->> 'outcome', '<none>'),
           'a recorded choice carries an outcome the runtime has no branch for'
      FROM events e
     WHERE e.type = 'scheduler.chose'
       AND coalesce(e.payload ->> 'outcome', '')
           NOT IN ('chosen','off_slate','no_choice','malformed','unavailable')

UNION ALL
    -- (g) 025's convention, applied to the arm this ticket added. Comments are
    --     stripped first, or the check fires on the comment explaining its own
    --     absence -- the same guard 023 needed for the same reason.
    SELECT 'eligibility_reads_the_clock', p.proname,
           'a function the ranking filter runs reads the wall clock'
      FROM pg_proc p
     WHERE p.pronamespace = 'public'::regnamespace
       AND p.proname = 'skills_ungranted_for'
       AND regexp_replace(p.prosrc, '--[^' || chr(10) || ']*', '', 'g')
           ~* '(now\(\)|current_timestamp|clock_timestamp)'
$fn$;

COMMENT ON FUNCTION check_orchestrator_dispatch() IS
  'One orchestrator decision is bounded on both sides: what may be offered excludes Tasks whose Skills the running role lacks and is decided without reading the clock, what is recorded names the Task-less session that chose and one of five outcomes, and the session that chose never reached a target.';

REVOKE ALL ON FUNCTION check_orchestrator_dispatch() FROM PUBLIC;


-- No new table, so the finalizers have nothing new to policy -- called anyway,
-- because a file that is self-contained when applied by hand is the property
-- every other migration here keeps.
SELECT apply_state_rls();
SELECT apply_state_grants();
