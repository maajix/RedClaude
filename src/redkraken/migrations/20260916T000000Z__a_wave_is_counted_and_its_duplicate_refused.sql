-- ===========================================================================
-- Ticket 80 -- a wave is counted, and its duplicate is refused
-- ===========================================================================
-- Anthropic's multiagent report says that instances of one model run together
-- decide alike: 18 of 30 agents chose the same branch name, over half built the
-- same kind of project unprompted. The roles here are instances of one model
-- reading one Program's Surface, so a wave of hunters is that experiment with
-- this repository's budgets paying for it. The ticket's first criterion is that
-- the harness stop assuming either way and emit the number.
--
-- Two functions, and the split between them is the ticket's own: measure first,
-- enforce second.
--
-- `wave_report` is the measurement. It counts what one wave came back with --
-- distinct subjects, distinct Property classes, distinct claims -- against how
-- many agents were in it, and it counts them off `hypothesis_provenance`,
-- which 20260814T070000Z already writes one row of per staged element that
-- reached a Hypothesis. Nothing new is recorded to make the measurement
-- possible: correlation is a property of rows this schema has kept since
-- Hypotheses became promotable, and a wave that never happened is a report of
-- zeroes rather than a missing table.
--
-- `subject_held_for` is the enforcement, and it is on the claim path because
-- that is the only place it can be. Asking the model to diversify is asking the
-- thing that is correlated to correct its own correlation; the scheduler,
-- which is not an instance of the model, can simply decline to hand two agents
-- the same work at the same time. It refuses rather than cancels: the arm reads
-- `claimed` and `running`, so the second Task is refused while the first runs
-- and is claimable the moment it finishes. No proposal is lost, and the wave
-- spends its concurrency on different subjects instead of on one subject twice.
--
-- The key is (kind, subject, Property class) and not (subject, Property class),
-- which the criterion states. `kind` is in it because a `validate` and a `hunt`
-- over one subject are not the same work -- refusing the validate for the hunt
-- that raised it would stop the Test the claim exists to run. Two Tasks of one
-- kind over one subject and one class are the same work by every column the
-- scheduler has, which is what the criterion is about.
--
-- A NULL Property class is compared as a value, not skipped: two recon Tasks
-- over one Entity carry no Hypothesis between them and are still two agents
-- looking at one thing. `IS NOT DISTINCT FROM` is what makes them collide,
-- which is the same operator `hypotheses_dedup_idx` uses on the same question.


-- ---------------------------------------------------------------------------
-- 1. What a wave came back with
-- ---------------------------------------------------------------------------

-- Rows and not columns, because the caller is a console panel and the panel
-- machinery reads statements: five measures as five rows keeps the order in
-- the function, where the vocabulary is, instead of in a Python tuple that
-- would have to be edited beside it.
--
-- A wave is a busy period and not a lifetime, so the window is computed before
-- anything is counted in it. `numbered` is the gaps-and-islands walk over the
-- run intervals: a run that starts at or after the latest end so far opens a
-- new wave, and one that starts before it joins the one running. The report is
-- the last wave's, because what an operator asks after dispatching eight
-- hunters is what those eight came back with, not what the engagement has done
-- since it opened -- and a Program whose runs never stopped overlapping has one
-- wave, which is the honest reading of a queue that never drained.
--
-- The same instant rule in both places: `started_at >= earlier_end` opens a new
-- wave for a run that begins exactly when the previous one ended, and `ORDER BY
-- at, delta` lands -1 before +1 at one instant, so a handover is not counted as
-- an overlap either time. An unfinished run is live now, which is what
-- `coalesce(finished_at, now())` says.
--
-- `agents run` is the wave's size and `peak concurrent` is its own maximum. The
-- two differ whenever the wave was a chain rather than a burst, which is what
-- makes the ratio underneath readable: four agents that were never more than
-- two at a time bought two agents' concurrency.
--
-- Only runs that answer a Task are counted. A run with no Task is not in the
-- wave -- it is the orchestrator that dispatched it -- and counting it would
-- put the dispatcher in the population its own dispatching is measured against.
CREATE FUNCTION wave_report(p_program uuid)
RETURNS TABLE (ord integer, measure text, measured bigint)
LANGUAGE sql STABLE AS $fn$
    WITH runs AS (
        SELECT a.id, a.started_at, coalesce(a.finished_at, now()) AS ended_at
          FROM agent_runs a
         WHERE a.program_id = p_program AND a.task_id IS NOT NULL
    ),
    reached AS (
        SELECT id, started_at, ended_at,
               max(ended_at) OVER (ORDER BY started_at, id
                                   ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING)
                 AS earlier_end
          FROM runs
    ),
    numbered AS (
        SELECT id, started_at, ended_at,
               count(*) FILTER (WHERE earlier_end IS NULL OR started_at >= earlier_end)
                 OVER (ORDER BY started_at, id ROWS UNBOUNDED PRECEDING) AS wave
          FROM reached
    ),
    wave AS (
        SELECT id, started_at, ended_at FROM numbered
         WHERE wave = (SELECT max(wave) FROM numbered)
    ),
    edges AS (
        SELECT started_at AS at, 1 AS delta FROM wave
         UNION ALL
        SELECT ended_at, -1 FROM wave
    ),
    overlap AS (
        SELECT sum(delta) OVER (ORDER BY at, delta) AS live FROM edges
    ),
    came_back AS (
        SELECT h.id, h.subject_entity_id, h.property_class
          FROM hypothesis_provenance hp
          JOIN hypotheses h ON h.id = hp.hypothesis_id
         WHERE hp.program_id = p_program
           AND hp.agent_run_id IN (SELECT id FROM wave)
    )
    SELECT v.ord, v.measure, v.measured
      FROM (VALUES
        (0, 'agents run',
            (SELECT count(*) FROM wave)),
        (1, 'peak concurrent',
            coalesce((SELECT max(live) FROM overlap), 0)),
        (2, 'distinct subjects',
            (SELECT count(DISTINCT subject_entity_id) FROM came_back)),
        (3, 'distinct property classes',
            (SELECT count(DISTINCT property_class) FROM came_back)),
        (4, 'distinct claims',
            (SELECT count(DISTINCT id) FROM came_back))
      ) AS v(ord, measure, measured)
     ORDER BY v.ord
$fn$;

REVOKE ALL ON FUNCTION wave_report(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION wave_report(uuid) TO rk2_runtime;

COMMENT ON FUNCTION wave_report(uuid) IS
    'What a Program''s last wave came back with, against how many agents were '
    'in it: the wave''s size, how many of it overlapped at once, and the '
    'distinct subjects, Property classes and claims its runs reached. A wave is '
    'the busy period -- runs that overlap, and the runs that overlap those -- '
    'so an engagement''s earlier waves are not counted in the one running now. '
    'Ticket 80''s first '
    'criterion -- correlated choice is a number this harness emits rather than '
    'a property it assumes it has or does not. Counted off '
    'hypothesis_provenance, so a claim two agents converged on is one claim '
    'here however many of them proposed it, which is what makes the ratio the '
    'measurement. Operator-side only: an agent that could read how many of its '
    'peers proposed what would have been handed the consensus that blind '
    'validation exists to keep out of its packet.';


-- ---------------------------------------------------------------------------
-- 2. The duplicate, refused where the claim is decided
-- ---------------------------------------------------------------------------

-- The shape of its neighbours (`ready_for`, `identity_held_for`,
-- `subagent_started_for`): one question about one Task, no clock, not reachable
-- by an agent. `o.id <> t.id` and not a status test on `t`: `claimable_for` has
-- already refused anything that is not `pending`, and a Task cannot be claimed
-- and pending at once, so the exclusion is defence against a caller asking this
-- of a row the eligibility rule would not have reached.
CREATE FUNCTION subject_held_for(t tasks) RETURNS boolean
LANGUAGE sql STABLE AS $fn$
    SELECT t.subject_entity_id IS NOT NULL
       AND EXISTS (
        SELECT 1 FROM tasks o
         WHERE o.program_id = t.program_id
           AND o.id <> t.id
           AND o.status IN ('claimed', 'running')
           AND o.kind = t.kind
           AND o.subject_entity_id = t.subject_entity_id
           AND (SELECT h.property_class FROM hypotheses h WHERE h.id = o.hypothesis_id)
               IS NOT DISTINCT FROM
               (SELECT h.property_class FROM hypotheses h WHERE h.id = t.hypothesis_id))
$fn$;

REVOKE ALL ON FUNCTION subject_held_for(tasks) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION subject_held_for(tasks) TO rk2_runtime;

COMMENT ON FUNCTION subject_held_for(tasks) IS
    'Whether another Task of this Program is already claimed or running over '
    'this Task''s subject, kind and Property class. Ticket 80''s second '
    'criterion: where a wave''s agents converge, the scheduler declines the '
    'second one rather than the model being asked to be original. Transient by '
    'construction -- it reads claimed and running, so the refused Task is '
    'claimable again as soon as the run holding its subject finishes, and the '
    'wave spends its concurrency on different subjects instead of on one '
    'subject twice.';

-- Restated whole rather than patched, because a plpgsql body cannot be amended
-- in place. Every arm is 072's, in 072's order; one is added between the two
-- concurrency arms. After `lane_full` because the lane is the coarser bound and
-- answers for every kind, and before `global_subagent_cap` because a duplicate
-- is refused whether or not the claim would start a subagent -- the cap is the
-- narrower population and the more specific reason, so it stays last.
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

    IF subject_held_for(t) THEN RETURN 'subject_held'; END IF;

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
    'than its Hypothesis''s nullable columns. Its subject_held arm is ticket '
    '80''s: a wave of one model''s instances decides alike, so two agents are '
    'not given one subject, kind and Property class at once -- refused while '
    'the first runs, claimable when it ends. Its global_subagent_cap arm is '
    'asked only of a Task that would start a subagent (subagent_started_for), '
    'and counts the Program''s claimed and running subagent Tasks, which is the '
    'wider of the two populations max_concurrent_subagents bounds: the pre-tool '
    'gate counts one session''s outstanding delegations against the same '
    'number. A validate or a report is in neither population, so neither is '
    'refused for concurrency it does not spend. Its budget arms ask '
    '`budget_refusal_for`, which reads capacity that claims in flight have '
    'already promised, so two claims cannot each be told the same tokens are '
    'free.';


-- ---------------------------------------------------------------------------
-- 3. The standing check
-- ---------------------------------------------------------------------------

-- A check of this file's own, for 026's reason: a check that has to be edited
-- in a neighbour's file to cover a new function is a check the next ticket
-- forgets. Arms (a) and (b) hold the two functions to what the rest of the
-- eligibility rule is held to; arm (c) is the state the second one exists to
-- make unreachable, asked of the rows rather than of the source.
CREATE FUNCTION check_wave_measurement()
RETURNS TABLE (problem text, subject text, detail text)
LANGUAGE sql STABLE AS $fn$
    -- (a) 023's arm (h), applied to both functions this file adds. The REVOKEs
    --     above are made once; this is what keeps them made, since a later
    --     `CREATE OR REPLACE` that dropped and recreated either would hand it
    --     back to PUBLIC. The wave counts matter here beyond the convention: an
    --     agent that can read how many of its peers proposed what has been
    --     handed the consensus a blind packet is built to withhold.
    SELECT 'wave_function_agent_reachable'::text, p.proname,
           'a surface an agent can reach executes a wave function'
      FROM pg_proc p
     WHERE p.pronamespace = 'public'::regnamespace
       AND p.proname IN ('wave_report', 'subject_held_for')
       AND (has_function_privilege('public', p.oid, 'EXECUTE')
            OR has_function_privilege('rk2_state', p.oid, 'EXECUTE'))

  UNION ALL
    -- (b) 025's convention, applied to the predicate the ranking filter now
    --     runs. A clock in it makes two passes over the same rows disagree
    --     exactly as thoroughly as a clock in any of its neighbours.
    SELECT 'eligibility_reads_the_clock', p.proname,
           'a function the ranking filter runs reads the wall clock'
      FROM pg_proc p
     WHERE p.pronamespace = 'public'::regnamespace
       AND p.proname = 'subject_held_for'
       AND regexp_replace(p.prosrc, '--[^' || chr(10) || ']*', '', 'g')
           ~* '(now\(\)|current_timestamp|clock_timestamp)'

  UNION ALL
    -- (c) The duplicate itself, as rows, and asked through the same function
    --     the claim path asks rather than restated here: a check that spelled
    --     the rule out a second time would keep reporting the old rule the day
    --     the rule changed, which is the failure a standing check exists to
    --     catch rather than to have. Self-clearing rather than permanent: both
    --     statuses it reads are ones a run leaves, so a pair claimed before
    --     this arm existed reports until the older run finishes and then stops.
    --     What it cannot report is a pair this file admitted, because
    --     `claim_task` holds a Program-wide advisory lock and re-asks
    --     `claimable_for` inside it. One row per claim in a colliding pair, so
    --     a pair names both of the runs an operator would have to look at.
    SELECT 'duplicate_subject_claimed', a.label,
           'another claim of this Program holds the same kind, subject and '
           'Property class'
      FROM tasks a
     WHERE a.status IN ('claimed', 'running')
       AND subject_held_for(a)
$fn$;

REVOKE ALL ON FUNCTION check_wave_measurement() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION check_wave_measurement() TO rk2_runtime, rk2_human;

COMMENT ON FUNCTION check_wave_measurement() IS
    'A wave is measured on the operator''s side and its duplicate is refused on '
    'the claim path. Both properties fail quietly without this: a wave function '
    'an agent can call puts its peers'' choices in front of it, and a claim path '
    'that stopped asking subject_held_for would go back to spending two budgets '
    'on one subject with nothing failing -- the offer filters on the same rule, '
    'so the slate would simply grow again.';

-- 066's registry: a function closed to PUBLIC that the runtime may still call
-- says so here, in one place, rather than in whichever migration granted it.
INSERT INTO runtime_verb_surface (verb, added_by, note) VALUES
    ('wave_report(uuid)', '80',
     'what a Program''s agents came back with against how many of them ran, which the operator console reads and the agent connection may not'),
    ('subject_held_for(tasks)', '80',
     'whether another claim of this Program already holds this Task''s kind, subject and Property class, which is the arm the eligibility rule refuses a wave''s duplicate on'),
    ('check_wave_measurement()', '80',
     'the standing check behind both, which every run asks with the rest of them');

INSERT INTO standing_checks(name, query, owner_ticket, note) VALUES
    ('wave_measurement', 'SELECT * FROM check_wave_measurement()', '80',
     'the wave counts are operator-side and clock-free, and no two claims of one Program hold the same kind, subject and Property class');


-- ---------------------------------------------------------------------------
-- 4. Consensus is not a column the blind packet may read
-- ---------------------------------------------------------------------------
-- The paper's hidden-profile result is the reason this section exists: asked to
-- judge with a group, models scored 17-36% against a solo ceiling near 100%,
-- because the fact one agent holds loses to what the others already believe.
-- The validator here is meant to be that solo judge, and 20260815T180000Z built
-- its packet from a column allowlist and asserted that the allowlist reaches
-- none of the relations a hunter's prose lives in.
--
-- That list is about narrative. This one is about agreement, which is the other
-- half of the ticket's criterion and was not named: a verdict another session
-- recorded, an attempt somebody else opened, a queue position, a review gate's
-- state. None of them is prose, all of them are somebody else's conclusion, and
-- a packet that grew a count of them would still pass every check written so
-- far. So the same assertion is made again over the relations where agreement
-- is kept -- resolved by name first, because a list of names that no longer
-- resolve is a check that passes for the wrong reason.
--
-- Asserted here rather than made a standing check because it is a property of
-- the installed function and not of anybody's data: it holds or the file does
-- not apply, and the test suite asks it again of the function that is actually
-- installed so that a later CREATE OR REPLACE cannot widen it quietly.

DO $$
DECLARE
    v_agreement text[] := ARRAY['verdicts', 'validation_attempts',
                                'validation_queue', 'review_gates'];
    v_unknown   text;
    v_leak      text;
BEGIN
    SELECT string_agg(named, ', ' ORDER BY named) INTO v_unknown
      FROM unnest(v_agreement) AS named
     WHERE to_regclass(named) IS NULL;
    IF v_unknown IS NOT NULL THEN
        RAISE EXCEPTION 'the consensus check names %, which is not a relation',
            v_unknown;
    END IF;

    SELECT string_agg(DISTINCT c.relname, ', ' ORDER BY c.relname) INTO v_leak
      FROM pg_depend d
      JOIN pg_class c ON c.oid = d.refobjid
     WHERE d.classid = 'pg_proc'::regclass
       AND d.objid = 'rk2_validation_packet(uuid,uuid,uuid)'::regprocedure
       AND d.refclassid = 'pg_class'::regclass
       AND c.relname = ANY (v_agreement);
    IF v_leak IS NOT NULL THEN
        RAISE EXCEPTION 'the validation packet reaches %, which is where agreement is kept',
            v_leak;
    END IF;
END $$;


-- ---------------------------------------------------------------------------
-- 5. The invariants this file must not have broken
-- ---------------------------------------------------------------------------

DO $$
DECLARE n integer; d text;
BEGIN
    -- The restatement above is the whole of `claimable_for`, so the arms it
    -- inherited are the ones that can have gone missing in the copying. Asked
    -- of the source, because what is being checked is that the text still says
    -- them and not that some row happens to reach them.
    SELECT count(*) INTO n
      FROM unnest(ARRAY['not_pending', 'not_ranked', 'unaffordable',
                        'clamped_without_identity', 'identity_held',
                        'no_role_runs_this_kind', 'skill_not_granted_to_role',
                        'lane_full', 'subject_held', 'global_subagent_cap']) AS arm
     WHERE (SELECT prosrc FROM pg_proc
             WHERE proname = 'claimable_for'
               AND pronamespace = 'public'::regnamespace) LIKE '%' || arm || '%';
    IF n <> 10 THEN
        RAISE EXCEPTION 'claimable_for lost an arm in the restatement: % of 10 present', n;
    END IF;

    -- 073's check, restated as this file's own concern rather than trusted:
    -- the cap is still asked only of a claim that starts a subagent, which is
    -- the neighbour arm the new one was inserted in front of.
    SELECT count(*) INTO n FROM check_subagent_cap_guard();
    IF n <> 0 THEN
        SELECT string_agg(problem || ' ' || subject, ', ') INTO d
          FROM check_subagent_cap_guard();
        RAISE EXCEPTION 'the subagent cap guard no longer holds: %', d;
    END IF;

    -- And this file's own, on a corpus that has no claims in it yet: the check
    -- is registered, it runs, and it finds nothing.
    SELECT count(*) INTO n FROM check_wave_measurement();
    IF n <> 0 THEN
        RAISE EXCEPTION 'the wave check reports % problem(s) on a fresh schema', n;
    END IF;
END $$;
