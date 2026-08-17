-- ===========================================================================
-- Ticket 75 -- a claim is refused for the concurrency it would actually spend
-- ===========================================================================
-- `scheduler_weights.max_concurrent_subagents` is how many subagents may run
-- at once. The arm that spends it counted the Program's claimed and running
-- subagent Tasks and then refused whatever claim was in front of it:
--
--     IF (SELECT count(*) FROM tasks c
--           JOIN effective_lane_capacity lc ON ... JOIN roles r ON ...
--          WHERE c.program_id = t.program_id
--            AND c.status IN ('claimed','running')
--            AND r.runs_as = 'subagent') >= w.max_concurrent_subagents THEN
--         RETURN 'global_subagent_cap';
--
-- The candidate's own role never entered it. 019 makes three of the five agent
-- roles subagents -- recon, web_hunter and js_analyst -- and gives each of them
-- exactly one kind, so a Program hunting on all three lanes is at a cap of 3 by
-- doing the thing it was built to do. From there every further claim of every
-- kind was refused, including `validate`, whose validator holds a session, and
-- `report`, whose reporter is a renderer that spends no model at all. The
-- scheduler was refusing work it had the capacity for -- and refusing it
-- consistently, which is why nothing ever failed: `claimable_for` is what the
-- offer filters by and what the claim re-asks (170000Z), so the Slate stopped
-- offering those Tasks too and the two halves went on agreeing about the wrong
-- answer.
--
-- The reading taken here is the one the column's name and 73's comment already
-- give. The number bounds subagents, and both populations it bounds are
-- populations of subagents: the scheduler's, which is Program-wide and outlives
-- an orchestrator session, and the pre-tool gate's, which is one session's
-- outstanding delegations. A validate or a report is in neither, because
-- neither starts a child. So the arm is asked only of a candidate whose own
-- lane role runs as a subagent. What the count counts does not move -- only
-- which claims have to answer to it.
--
-- One site, because 73 left one. `check_slate_claim()` fails a `rank_candidates`
-- or a `claim_task` that decides eligibility without `claimable_for`, so the
-- offer and the claim move together here by construction rather than by two
-- edits made in step, which is the drift ticket 23 exists to prevent.
-- ---------------------------------------------------------------------------


-- ---------------------------------------------------------------------------
-- 1. What the candidate would start
-- ---------------------------------------------------------------------------

-- A predicate of its own, in the shape and in the naming its neighbours are in:
-- `ready_for`, `identity_held_for`, `skills_ungranted_for` and
-- `budget_refusal_for` all answer one question about one Task, and this is
-- another one. Named for what it decides rather than for the column it reads,
-- because `runs_as = 'subagent'` is how the roster spells it today and the
-- question the cap asks is whether claiming this Task puts a child on this
-- machine.
--
-- `effective_lane_capacity` and not `role_task_kinds`, though the two agree by
-- construction -- the view derives its role from that table -- because the
-- count below reads the view, and one source for "the role that runs this kind"
-- is what keeps the guard and the count talking about the same population.
CREATE FUNCTION subagent_started_for(t tasks) RETURNS boolean
LANGUAGE sql STABLE AS $fn$
    SELECT EXISTS (
        SELECT 1 FROM effective_lane_capacity lc
          JOIN roles r ON r.role = lc.role
         WHERE lc.program_id = t.program_id
           AND lc.kind = t.kind
           AND r.runs_as = 'subagent'
    )
$fn$;

COMMENT ON FUNCTION subagent_started_for(tasks) IS
    'True when claiming this Task would start a subagent, which is the one '
    'role kind the cross-role concurrency cap bounds. The one role that runs a '
    'kind is injective (019), so this is a question about the Task rather than '
    'about which of several roles might take it: a validator holds a session '
    'and a reporter is a renderer, and claiming either starts no child.';

REVOKE ALL ON FUNCTION subagent_started_for(tasks) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION subagent_started_for(tasks) TO rk2_runtime;


-- ---------------------------------------------------------------------------
-- 2. The one eligibility rule, with the cap asked of the claims that spend it
-- ---------------------------------------------------------------------------

-- Restated whole rather than patched, because a plpgsql body cannot be amended
-- in place. Every arm is 27's, in 27's order; the last one gains the guard.
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

    -- The guard is first because it is the cheap half and because it is the
    -- claim's own property: a Task that starts no subagent has no business
    -- being measured against how many subagents are running. The count is
    -- unchanged -- claimed and running Tasks whose lane role runs as a
    -- subagent, across the whole Program -- and so is the bound it is compared
    -- against, which `check_subagent_cap()` requires be this column.
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
    'answers to two different questions. Its global_subagent_cap arm is asked '
    'only of a Task that would start a subagent (subagent_started_for), and counts '
    'the Program''s claimed and running subagent Tasks, which is the wider of '
    'the two populations max_concurrent_subagents bounds: the pre-tool gate '
    'counts one session''s outstanding delegations against the same number. A '
    'validate or a report is in neither population, so neither is refused for '
    'concurrency it does not spend. Its budget arms ask `budget_refusal_for`, '
    'which reads capacity that claims in flight have already promised. Its '
    'skill_not_granted_to_role arm asks role_skills whether the one role that '
    'runs this kind may load what the Task requires, because a Skill a role '
    'lacks is a load-time error and not something to discover inside a started '
    'child.';

-- 73 wrote what the number means on the column that holds it, and said the
-- scheduler "refuses an offer and a claim past this". That sentence is now one
-- word narrower on this side of the seam, and the column is where a reader of
-- either count arrives, so it is restated rather than left to age.
COMMENT ON COLUMN scheduler_weights.max_concurrent_subagents IS
  'How many subagents may run at once, across every lane. Counted twice, over two populations, and both are populations of subagents: the scheduler counts Tasks in claimed or running whose lane role runs as a subagent, across the whole Program and across orchestrator rotations, and refuses an offer and a claim of a Task that would start one past this (claimable_for); the runtime reads this column with the claim and gives it to the pre-tool gate, which counts the delegations one orchestrator session is holding, which is that SDK''s concurrency and that machine''s containers. The session''s population is a subset of the Program''s, which is why one number bounds both, and why they disagree during a rotation. A claim that starts no subagent -- a validate, which its validator runs as a session, or a report, which its reporter renders -- is in neither population and is not measured against this. Set on the one active weights row, which an operator versions for the whole scheduler: that row is the one statement of it, and the runtime carries no copy.';


-- ---------------------------------------------------------------------------
-- 3. The standing check
-- ---------------------------------------------------------------------------

-- A check of this file's own, and not three arms added to 73's and 23's, for
-- the reason 026 states where it added an arm to its own: a check that has to
-- be edited in a neighbour's file to cover a new function is a check the next
-- ticket forgets. So the new predicate carries the two properties its family
-- carries, and the narrowing this file made carries the one property that says
-- it is still made.
CREATE FUNCTION check_subagent_cap_guard()
RETURNS TABLE (problem text, subject text, detail text)
LANGUAGE sql STABLE AS $fn$
    -- (a) the regression this ticket exists to prevent, in the shape 73 wrote
    --     the sibling of: a function that counts running subagents and refuses
    --     on that count without asking whether the claim in front of it starts
    --     one is refusing work the Program has capacity for. Textual, because
    --     what it asserts is what the function is made of, and comments are
    --     stripped first or the check fires on the comment explaining itself.
    SELECT 'cap_refuses_a_claim_that_starts_nothing'::text, p.proname,
           'a function bounds a claim by the count of running subagents '
           'without asking subagent_started_for whether this claim adds one'
      FROM pg_proc p
     CROSS JOIN LATERAL (
         SELECT regexp_replace(p.prosrc, '--[^' || chr(10) || ']*', '', 'g')
     ) AS s(src)
     WHERE p.pronamespace = 'public'::regnamespace
       AND s.src ~ 'count\(\*\)[^;]*runs_as[^;]*''subagent'''
       AND s.src ~ 'max_concurrent_subagents'
       AND s.src !~ 'subagent_started_for'

  UNION ALL
    -- (b) 025's convention, applied to the function this ticket added, the way
    --     026 applied it to `skills_ungranted_for`. The ranking filter runs
    --     this one now, and a clock in it makes two passes over the same rows
    --     disagree exactly as thoroughly as a clock in any of its neighbours.
    SELECT 'eligibility_reads_the_clock', p.proname,
           'a function the ranking filter runs reads the wall clock'
      FROM pg_proc p
     WHERE p.pronamespace = 'public'::regnamespace
       AND p.proname = 'subagent_started_for'
       AND regexp_replace(p.prosrc, '--[^' || chr(10) || ']*', '', 'g')
           ~* '(now\(\)|current_timestamp|clock_timestamp)'

  UNION ALL
    -- (c) 23's arm (h), applied to the same function. The REVOKE above is made
    --     once; this is what keeps it made, since a later `CREATE OR REPLACE`
    --     that dropped and recreated the function would hand it back to PUBLIC.
    SELECT 'scheduler_function_public_executable', p.proname,
           'an agent-reachable role can call a scheduler function'
      FROM pg_proc p
     WHERE p.pronamespace = 'public'::regnamespace
       AND p.proname = 'subagent_started_for'
       AND has_function_privilege('public', p.oid, 'EXECUTE')
$fn$;

REVOKE ALL ON FUNCTION check_subagent_cap_guard() FROM PUBLIC;

COMMENT ON FUNCTION check_subagent_cap_guard() IS
    'The cross-role subagent cap is spent by the claims that start a subagent. '
    'A function that refuses on the count of running subagents without asking '
    'whether this claim adds one is refusing work the Program has capacity for, '
    'and it fails quietly, because the offer filters on the same rule and stops '
    'offering what the claim would refuse. The predicate that decides it is '
    'held to what the rest of the eligibility rule is held to: no clock, and '
    'not reachable by an agent.';

INSERT INTO standing_checks(name, query, owner_ticket, note) VALUES
    ('subagent_cap_guard', 'SELECT * FROM check_subagent_cap_guard()', '75',
     'the cap is asked only of a claim that starts a subagent, and the predicate that decides it is clock-free and not agent-reachable');


-- ---------------------------------------------------------------------------
-- 4. The invariants this file must not have broken
-- ---------------------------------------------------------------------------

DO $$
DECLARE n integer; d text;
BEGIN
    -- 73's check, which is the one this file could plausibly break: a cap
    -- compared against anything but the weights column. The guard is a second
    -- condition on the same IF, so the count and its bound stay one statement.
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_subagent_cap();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-75 refuses to finish: % subagent cap problem(s): %', n, d;
    END IF;

    -- And the rule this file rewrote, asked whether it is still the one both
    -- halves read, still free of the clock, and still bounded where 23 bounds
    -- it.
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_slate_claim();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-75 breaks the slate and the claim (% problems): %', n, d;
    END IF;

    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_lane_quota_closure();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-75 breaks lane quota closure (% problems): %', n, d;
    END IF;

    -- And this file's own, which on a corpus that has just applied it is a
    -- statement about the rule it rewrote a minute ago.
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_subagent_cap_guard();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-75 refuses to finish: % guard problem(s): %', n, d;
    END IF;

    -- The arm is still reachable. A guard that was accidentally universal --
    -- `subagent_started_for` returning false for everything, say, because the
    -- view it reads changed shape -- would turn the cap off rather than narrow
    -- it, and every test of it would go on passing by claiming successfully.
    --
    -- Asked of `role_task_kinds` and not of the view the predicate reads,
    -- because `effective_lane_capacity` is `programs` CROSS JOIN `task_kinds`
    -- and a freshly migrated database holds no Programs: the view is empty
    -- here, and the table it derives its role from is the strongest thing
    -- there is to ask at apply time. What the predicate answers for a real
    -- Program is `SlateClaimTest`'s, which claims one Task of every kind.
    SELECT count(*) INTO n FROM role_task_kinds m
      JOIN roles r ON r.role = m.role WHERE r.runs_as = 'subagent';
    IF n = 0 THEN
        RAISE EXCEPTION 'ph2-75 refuses to finish: no kind starts a subagent, so the cap bounds nothing';
    END IF;
END $$;
