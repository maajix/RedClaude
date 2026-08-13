-- ---------------------------------------------------------------------------
-- 20260814T000000Z__the_orchestrator_chooses_and_the_runtime_dispatches.sql
--                                                                    (PH2-27)
--
-- 170000Z built both ends of the Slate and left the middle empty. `offer_slate`
-- writes a bounded list, `pick_task` records a choice against it and
-- `claim_task` commits one -- and nothing in the corpus ever ran a model over
-- the list, so the only caller of the whole apparatus was a runtime taking
-- entry one. ADR 0003 is a three-clause sentence and two of the clauses had no
-- subject: "the runtime decides what may be chosen; the orchestrator decides
-- which; the runtime commits the claim."
--
-- What is missing is not a decision procedure. It is the four durable facts a
-- decision needs either side of it:
--
--   * a session to make it in, which is an Agent run with no Task -- the
--     orchestrator must never hold a lane slot, and 0019's
--     `agent_runs_executes_tasks_fk` is what makes that structural rather than
--     a habit;
--   * one record of what the model answered, whatever it answered, including
--     when it answered nothing and when it answered something unreadable;
--   * the downgrade that keeps `pick_task`'s refusal from becoming a silence:
--     a choice the Slate no longer carries is recorded as refused rather than
--     quietly replaced with the runtime's own pick;
--   * an admission rule that knows a Task's Skills are a property of the role
--     that would run it. A `hunt` requiring `use-identity` is claimable and an
--     `analyze` requiring it is not, and until this file nothing anywhere asked.
--
-- The last one is criterion 4 and it is the only change here to a rule that was
-- already running. Everything else is new surface.
--
-- What this file does NOT do is decide anything about the choice. There is no
-- scoring, no tie-break and no second-guessing of what the model returned: the
-- runtime bounds the list, the model names one entry of it, and `claim_task`
-- re-asks every eligibility condition inside the transaction that takes the
-- Task. A verb here that improved on the model's answer would be the runtime
-- choosing twice and the orchestrator choosing never.
-- ---------------------------------------------------------------------------


-- ---------------------------------------------------------------------------
-- 1. The session a choice is made in
-- ---------------------------------------------------------------------------
-- A verb rather than an INSERT in the runtime, for the reason 200000Z made the
-- claim read `roles`: the model and the effort a role runs at are the roster's
-- statement, and a runtime that spelled them into an INSERT would be a second
-- roster that agrees until someone edits one of them.
--
-- No Task, and that is the whole shape of it. `agent_runs.executes_tasks` is
-- generated from `task_id IS NOT NULL` and joined to `roles(role,
-- executes_tasks)` by a foreign key, so an orchestrator run that carried a Task
-- would be refused by the schema rather than by a rule someone remembered to
-- write. ADR 0003 wants exactly that: the session that chooses never competes
-- for a lane slot with the work it is choosing between.
--
-- No reservation either, and not by omission: `budget_reservations.task_id` is
-- NOT NULL and its `kind` is the lane the promise is held against, neither of
-- which a planning session has. What it spends is still counted -- the run's
-- own `input_tokens` and `output_tokens` are what `program_budget` sums, over
-- every run of the Program and not only the ones that held a Task -- so the
-- choice costs the Program what it cost, it just cannot promise it in advance.
CREATE FUNCTION open_orchestrator_session() RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p        uuid := rk2_program_required();
    v_model  text;
    v_effort text;
    v_run    uuid;
    v_label  text;
    v_cap    integer;
    v_tokens bigint;
BEGIN
    SELECT r.model, r.effort INTO v_model, v_effort
      FROM roles r WHERE r.role = 'orchestrator';
    IF NOT FOUND THEN
        RAISE EXCEPTION 'the roster has no orchestrator row to open a session as'
            USING ERRCODE = 'check_violation';
    END IF;

    INSERT INTO agent_runs (program_id, role, model, effort, mission_packet)
    VALUES (p, 'orchestrator', v_model, v_effort, '{}')
    RETURNING id, label INTO v_run, v_label;

    -- Both ceilings travel with the session for the reason the claim carries
    -- them: the container's one network reaches the capability proxy and no
    -- database, so a number the child is bounded by is a number that was read
    -- here or not at all. The subagent cap is the same one active weights row
    -- the claim reads; the token ceiling is the Program's own per-run one,
    -- which is what a run may spend rather than what anything has held for it.
    SELECT w.max_concurrent_subagents INTO v_cap
      FROM scheduler_weights w WHERE w.active;
    SELECT c.run_tokens INTO v_tokens
      FROM program_capacity c WHERE c.program_id = p;

    RETURN jsonb_build_object(
        'agent_run', v_run::text, 'label', v_label,
        'model', v_model, 'effort', v_effort,
        'subagent_cap', v_cap, 'token_cap', v_tokens);
END $fn$;

COMMENT ON FUNCTION open_orchestrator_session() IS
    'Opens one Task-less Agent run for the orchestrator to decide in, at the '
    'model and effort the roster row states, and returns the two ceilings the '
    'child has no database to read: the cross-role subagent cap from the '
    'active weights and the Program''s per-run token ceiling. It holds no lane '
    'slot and reserves no budget, because a planning session has no Task and '
    'therefore no lane to promise against.';


-- ---------------------------------------------------------------------------
-- 2. The choice, recorded whatever it turned out to be
-- ---------------------------------------------------------------------------
INSERT INTO event_types (id, family, subject_table, description) VALUES
    ('scheduler.chose', 'occurrence', NULL,
     'one orchestrator decision over one Slate: what the model answered and what the runtime made of it (ticket 27)');

-- Criterion 6 in one verb. "Malformed, off-Slate and empty model responses all
-- leave a deterministic, safe and auditable outcome" is three requirements and
-- only the third needs a table: deterministic is the mapping below, safe is
-- that none of the three can reach a claim, and auditable is that each of them
-- writes the same Event with a different word in it.
--
-- The five words and what each one commits the runtime to:
--
--   chosen      one Slate label came back and is now this Program's
--               outstanding pick; the claim will re-validate it and refuse it
--               if the world moved.
--   off_slate   the label did not survive `pick_task` -- the Slate expired
--               under it, or the entry went while the model was thinking.
--               Nothing is picked and nothing is claimed this pass. ADR 0003
--               is explicit that a stale choice is REFUSED and not
--               substituted: falling through to entry one here would be the
--               runtime answering a question it was told the model owns.
--   no_choice   the session ran and picked nothing. This is the one outcome
--               the ADR gives a fallback to, and the fallback is
--               `claim_task()` with no argument, which walks the Slate in its
--               own order.
--   malformed   something came back that is not a choice. Treated as
--               `no_choice` by the runtime for what happens next, and recorded
--               apart from it because a model that answered unreadably and one
--               that declined are different runs to read back.
--   unavailable no session answered at all: refused at startup, no boundary,
--               or a child that died. Also falls back, because the runtime's
--               own walk is what the loop did before there was an orchestrator
--               and is the one behaviour that cannot depend on a model.
--
-- The downgrade is done here rather than in the caller because it is the
-- database that knows: `pick_task` is the authority on what the current Slate
-- carries, and a runtime that pre-checked the label against its own copy of the
-- list would be checking against a list that has no lock on it.
CREATE FUNCTION record_choice(p_agent_run uuid,
                              p_outcome text,
                              p_task_label text DEFAULT NULL,
                              p_detail text DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql AS $fn$
DECLARE
    p         uuid := rk2_program_required();
    v_run     agent_runs%ROWTYPE;
    v_outcome text := p_outcome;
    v_detail  text := p_detail;
    v_payload jsonb;
BEGIN
    IF p_outcome NOT IN ('chosen','no_choice','malformed','unavailable') THEN
        RAISE EXCEPTION 'a choice is chosen, no_choice, malformed or unavailable, not %',
            p_outcome USING ERRCODE = 'check_violation';
    END IF;
    -- A label with any other outcome is a caller contradicting itself, and the
    -- Event would carry a Task nobody chose. `chosen` without one is the same
    -- contradiction the other way.
    IF (p_outcome = 'chosen') <> (p_task_label IS NOT NULL) THEN
        RAISE EXCEPTION 'only a chosen outcome names a task (% named %)',
            p_outcome, coalesce(p_task_label, '<nothing>')
            USING ERRCODE = 'check_violation';
    END IF;

    SELECT * INTO v_run FROM agent_runs
     WHERE id = p_agent_run AND program_id = p FOR UPDATE;
    IF NOT FOUND THEN
        -- The Program is a predicate, not a lookup key. Another Program's
        -- session is not one this Program may record a choice against, and
        -- `rk2_program_required()` is where the boundary comes from.
        RAISE EXCEPTION 'agent run % is not this Program''s', p_agent_run
            USING ERRCODE = 'check_violation';
    END IF;
    IF v_run.role <> 'orchestrator' OR v_run.task_id IS NOT NULL THEN
        RAISE EXCEPTION '% is not a Task-less orchestrator session', v_run.label
            USING ERRCODE = 'check_violation';
    END IF;

    IF v_outcome = 'chosen' THEN
        BEGIN
            PERFORM pick_task(p_task_label);
        EXCEPTION WHEN check_violation THEN
            -- The subtransaction this handler opens is what rolls the refused
            -- pick back; everything above it stands. The Event is still
            -- written, with the reason the pick was refused in it, because a
            -- choice that was made and could not be committed is exactly the
            -- run an operator asking "why did nothing happen" is looking for.
            v_outcome := 'off_slate';
            v_detail  := coalesce(v_detail || '; ', '') || SQLERRM;
        END;
    END IF;

    v_payload := jsonb_build_object(
        'outcome', v_outcome,
        'task', CASE WHEN v_outcome = 'chosen' THEN p_task_label ELSE NULL END,
        'offered_task', p_task_label,
        'agent_run', v_run.label,
        'detail', v_detail);

    -- Named against the session that made the choice. `set_cause` would not do
    -- it: this is a direct INSERT rather than a row event, so the emitter that
    -- reads the cause settings never runs, and the run is written into the
    -- column instead. `llm` is the actor for every outcome a model produced,
    -- including the two that say it produced nothing usable; `unavailable` is
    -- the runtime saying no model ran, which is the runtime's own finding.
    INSERT INTO events (program_id, type, actor_kind, agent_run_id, payload)
    VALUES (p, 'scheduler.chose',
            CASE WHEN v_outcome = 'unavailable' THEN 'runtime' ELSE 'llm' END,
            v_run.id, v_payload);

    RETURN v_payload;
END $fn$;

COMMENT ON FUNCTION record_choice(uuid, text, text, text) IS
    'Records what one orchestrator session answered and what the runtime may '
    'do next: a chosen label becomes the Program''s outstanding pick, a label '
    'the current Slate no longer carries is downgraded to off_slate and picks '
    'nothing, and no_choice, malformed and unavailable each leave the Slate to '
    'the runtime''s own walk. Every one of the five writes one scheduler.chose '
    'Event, so a pass that claimed nothing still says why.';


-- ---------------------------------------------------------------------------
-- 3. A role that cannot load the Skill does not get the Task
-- ---------------------------------------------------------------------------
-- Criterion 4's second half: "rejects incompatible role or Skill combinations".
-- The first half was already structural -- `role_task_kinds` is unique on kind,
-- so a Task's kind selects one role and there is nothing to reject -- and the
-- second half had no rule anywhere in the corpus. `tasks.required_skills` was
-- checked for registration (0023's trigger) and for being enabled (the
-- confidence factor), and never once against the role that would have to run it.
--
-- 0032 already answers this question for a playbook: "a skill a role lacks is a
-- load-time error, not a runtime escalation -- so it is a filter here, not a
-- park later". `playbooks_admissible` filters on exactly this join. A Task
-- carrying the same requirement was admitted anyway, claimed, dispatched, and
-- discovered at load time inside a child that had already spent its startup.
--
-- Placed after `no_role_runs_this_kind` because it presupposes it: the join is
-- through `role_task_kinds`, so with no role for the kind there is no grant to
-- look for and the arm above is the truer answer. Clock-free, like every other
-- arm, which is what `check_slate_claim`'s first arm holds the whole rule to.
--
-- `role_skills` and not the roster's Python `skills` tuple: this is the
-- database's own grant list, the one `playbooks_admissible` and 0035's promotion
-- rule already decide by, and the claim has to decide by what the harness has
-- registered rather than by what a compiled document hopes exists.
--
-- Its own function because two statements ask it: the admission rule below and
-- the standing check's arm (b), which asks the same question of the rows the
-- rule produced. Written twice, the check would pass while quietly asking a
-- narrower question than the rule enforces -- and the two are meant to disagree
-- about nothing at all. `required_skills` defaults to `'{}'`, so a Task that
-- requires none unnests to no rows and is never ungranted.
CREATE FUNCTION skills_ungranted_for(t tasks) RETURNS boolean
LANGUAGE sql STABLE AS $fn$
    SELECT EXISTS (SELECT 1 FROM unnest(t.required_skills) AS s
                    WHERE NOT EXISTS (SELECT 1 FROM role_skills rs
                                        JOIN role_task_kinds m ON m.role = rs.role
                                       WHERE m.kind = t.kind AND rs.skill_name = s));
$fn$;

COMMENT ON FUNCTION skills_ungranted_for(tasks) IS
    'True when this Task requires a Skill the one role that runs its kind was '
    'never granted. The claim refuses on it and the standing check reports on '
    'it, so the rule the offer applies and the property the check asserts are '
    'one statement rather than two that can drift apart.';

REVOKE ALL ON FUNCTION skills_ungranted_for(tasks) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION skills_ungranted_for(tasks) TO rk2_runtime;

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
    'refuses it. The offer filters on it and the claim re-asks it, so the list '
    'the orchestrator was given and the decision the runtime commits cannot be '
    'answers to two different questions. Its global_subagent_cap arm counts '
    'the Program''s claimed and running subagent Tasks, which is the wider of '
    'the two populations max_concurrent_subagents bounds: the pre-tool gate '
    'counts one session''s outstanding delegations against the same number. '
    'Its budget arms ask `budget_refusal_for`, which reads capacity that '
    'claims in flight have already promised. Its skill_not_granted_to_role arm '
    'asks role_skills whether the one role that runs this kind may load what '
    'the Task requires, because a Skill a role lacks is a load-time error and '
    'not something to discover inside a started child.';


-- ---------------------------------------------------------------------------
-- 4. The scheduler surface is the runtime's, not the agent's
-- ---------------------------------------------------------------------------
-- 029's default privileges hand every new function to `rk2_runtime`, and
-- Postgres hands every new function to PUBLIC. The revoke is the load-bearing
-- half: `record_choice` writes a pick, and a connection a model reaches through
-- that could call it directly would be a model committing its own choice
-- without the Slate ever being consulted.
DO $$
DECLARE f text;
BEGIN
    FOREACH f IN ARRAY ARRAY[
        'open_orchestrator_session()', 'record_choice(uuid,text,text,text)']
    LOOP
        EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC', f);
        EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO rk2_runtime', f);
    END LOOP;
END $$;


-- ---------------------------------------------------------------------------
-- 5. The standing check
-- ---------------------------------------------------------------------------
-- What choosing and dispatching can get wrong, as rows. Two arms are textual,
-- for the reason `check_slate_claim`'s are: the property is a property of what
-- the function is made of, and a later edit that quietly takes it out is
-- exactly what a standing check exists to notice.
CREATE FUNCTION check_orchestrator_dispatch()
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
$fn$;

COMMENT ON FUNCTION check_orchestrator_dispatch() IS
  'One orchestrator decision is bounded on both sides: what may be offered excludes Tasks whose Skills the running role lacks, what is recorded names the Task-less session that chose and one of five outcomes, and the session that chose never reached a target.';

REVOKE ALL ON FUNCTION check_orchestrator_dispatch() FROM PUBLIC;

INSERT INTO standing_checks (name, query, owner_ticket, note) VALUES
    ('orchestrator_dispatch', 'SELECT * FROM check_orchestrator_dispatch()', '27',
     'the choice is recorded against a Task-less session, the Slate offers only work its role can run, and planning never reaches a target');


-- ---------------------------------------------------------------------------
-- 6. Bring the corpus to true
-- ---------------------------------------------------------------------------
-- No new table, so the finalizers have nothing new to policy -- called anyway,
-- because a file that is self-contained when applied by hand is the property
-- every other migration here keeps.
SELECT apply_state_rls();
SELECT apply_state_grants();

DO $$
DECLARE n integer; d text;
BEGIN
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_orchestrator_dispatch();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-27 refuses to finish: % dispatch problem(s): %', n, d;
    END IF;

    -- The two neighbours this file reached into: the admission rule, whose
    -- function it replaced, and the closure that owns the surface the two new
    -- verbs were just added to.
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_slate_claim();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-27 breaks the slate and the claim (% problems): %', n, d;
    END IF;

    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_scheduler_closure();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-27 breaks the scheduler closure (% problems): %', n, d;
    END IF;
END $$;
