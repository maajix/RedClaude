-- ---------------------------------------------------------------------------
-- 20260913T000000Z__recovery_ends_what_the_crash_left_open.sql        (PH2-61)
--
-- Ticket 61 runs one campaign twice -- once straight through, once with the
-- process stopped either side of eight commits -- and compares what the two
-- leave behind. Criterion 4 is the assertion that makes the comparison worth
-- making: "every restart reconciles idempotently with no duplicate Events,
-- fabricated attempts, stranded Leases, zombie runs or false terminal state".
--
-- The interrupted campaign failed it twice, and both failures are the same
-- shape: the recovery paths take a Task back off a dead owner without finishing
-- what that owner had open, and without asking what it had already achieved.
--
-- FIRST, a stranded Tool run. `finish_task_attempt` closes the Tool runs of the
-- run it is closing, and says why in a comment older than this file: "Tool runs
-- close before the Agent run, because closing a Tool run is what revokes its
-- capability". Neither `reconcile_leases` nor `resume_program` did, and both
-- abort Agent runs -- so a pass stopped between `INSERT INTO tool_runs` and the
-- door's answer left a Tool run `running` inside a run marked `aborted`, which
-- is `check_execution_closure`'s own `open_tool_run_of_closed_agent_run`. The
-- campaign left three of them, and the standing check found all three.
--
-- SECOND, a Task run twice. `finish_task_attempt` asks `task_result_accepted`
-- before it decides what a Task becomes, because a Task whose result the
-- runtime accepted is done whatever else happened to the attempt. The recovery
-- paths did not ask: a pass stopped after the promotion commit and before the
-- closing one left a Task with a promoted proposal against it, and the next
-- pass claimed it, spent a second attempt on it, made the same requests against
-- the target again and promoted a second copy. That is criterion 4's fabricated
-- attempt and criterion 5's duplicate row in one, and it is the reason the
-- interrupted campaign held fifteen `endpoint_discovered` Observations where
-- the control held thirteen.
--
-- THIRD, a Finding nobody could ask about again. `abandon_validation` states
-- in its own comment what it is for -- "the runtime calls it on every path out
-- of a session it opened, so a crashed validator does not leave a Finding
-- permanently under judgement" -- and neither recovery path called it, so a
-- crashed validator did exactly that. The attempt stays `open`, and an open
-- attempt is what `open_validation_session` will not open a second session
-- behind: the Finding stays `validating`, the request stays `queued`, and
-- nothing can ever judge it. That is criterion 4's false terminal state,
-- written across three tables at once.
--
-- All three fixes are the same move: the question a closing already asks, asked
-- in the one place every ending goes through.
-- ---------------------------------------------------------------------------


-- ---------------------------------------------------------------------------
-- 1. A run that ends closes what it opened
-- ---------------------------------------------------------------------------
-- The statement `finish_task_attempt` has carried since 020, as a verb, so the
-- reconciler and the restart sweep stop having to remember it -- and so that
-- a fourth path added tomorrow cannot forget it. `error` and not `abandoned`
-- because this is the closing's own word for the same fact: the run that owned
-- this Tool run ended without it. The park path keeps `abandoned` and its
-- explanation, which is a different fact -- an operator's decision, not a
-- process that stopped.
--
-- No `program_id` filter: a Tool run belongs to exactly one Agent run and the
-- composite FK ties both to one Program, so the run's identity is the whole of
-- the question. `status = 'running'` is what makes a second call close nothing
-- rather than rewrite a `finished_at` somebody is reading.
CREATE FUNCTION close_tool_runs(p_agent_run uuid) RETURNS bigint
LANGUAGE plpgsql AS $fn$
DECLARE n bigint;
BEGIN
    UPDATE tool_runs SET status = 'error', finished_at = now()
     WHERE agent_run_id = p_agent_run AND status = 'running';
    GET DIAGNOSTICS n = ROW_COUNT;
    RETURN n;
END $fn$;

COMMENT ON FUNCTION close_tool_runs(uuid) IS
    'Closes every Tool run still open inside one Agent run, which is what '
    'revokes each one''s capability. Idempotent: a Tool run already closed is '
    'not closed again, and its finish time is the moment it actually ended.';

-- The judgement half, and it delegates rather than repeats: what abandoning a
-- validation means -- the attempt closed unanswered, the request taken off the
-- queue, the Finding given back to the candidates -- is 37's decision and is
-- written once, in 37's own verb. This is only the part 37 could not know: that
-- the session it was opened for is over.
--
-- Keyed by the run rather than by the Finding because that is the fact the
-- caller has. `outcome = 'open'` is what makes a second call close nothing,
-- and a run holds at most one open attempt -- the loop is over a set that is
-- empty or a single row, written as a loop because nothing in the schema
-- promises the second half of that sentence.
CREATE FUNCTION close_validation_attempts(p_agent_run uuid, p_reason text)
RETURNS bigint LANGUAGE plpgsql AS $fn$
DECLARE v record; n bigint := 0;
BEGIN
    FOR v IN SELECT va.program_id, va.finding_id FROM validation_attempts va
              WHERE va.agent_run_id = p_agent_run AND va.outcome = 'open'
    LOOP
        PERFORM abandon_validation(v.program_id, v.finding_id, p_reason);
        n := n + 1;
    END LOOP;
    RETURN n;
END $fn$;

COMMENT ON FUNCTION close_validation_attempts(uuid, text) IS
    'Abandons the validation an ending run was in the middle of, which is what '
    'gives the Finding back to the candidates and lets somebody ask again. '
    'Idempotent: an attempt already closed is not closed twice.';

-- And the backstop, on the transition every ending shares. 32's budget
-- settlement is attached exactly here for exactly this reason: a terminal path
-- that has to remember something is a terminal path that will eventually be
-- written without it, and this file exists because three of them were.
--
-- AFTER, and returning NULL: the row this fires on is already the row it fires
-- about, and nothing here changes it. The one thing it must not do is fire on
-- a run that is being reopened -- there is no such transition, because
-- `finished_at` is never set back to NULL.
--
-- The reason names the transition rather than the crash. `finish_task_attempt`
-- reaches here too, having already filed whatever the run answered, so a
-- sentence about a process that died would be wrong on the ordinary path and
-- right only by accident on the other one.
CREATE FUNCTION close_what_an_ended_run_left_open() RETURNS trigger
LANGUAGE plpgsql AS $fn$
BEGIN
    PERFORM close_tool_runs(NEW.id);
    PERFORM close_validation_attempts(
        NEW.id, 'the run holding this validation ended without a verdict');
    RETURN NULL;
END $fn$;

COMMENT ON FUNCTION close_what_an_ended_run_left_open() IS
    'Closes an ending run''s open Tool runs and its open validation attempt, '
    'whichever path ended it, so that "a finished attempt leaves nothing open" '
    'holds by construction rather than by every closing statement remembering '
    'to.';

CREATE TRIGGER agent_runs_close_what_they_left_open
    AFTER UPDATE OF finished_at ON agent_runs
    FOR EACH ROW WHEN (OLD.finished_at IS NULL AND NEW.finished_at IS NOT NULL)
    EXECUTE FUNCTION close_what_an_ended_run_left_open();

-- The closing reads the verb rather than restating it. It still calls it
-- explicitly, before the run ends, because it reports how many Tool runs it
-- closed and the trigger cannot hand a number back to the statement that fired
-- it. By the time the trigger runs there is nothing left to close, which is
-- what makes the pair one closing rather than two.
CREATE OR REPLACE FUNCTION finish_task_attempt(p_agent_run uuid,
                                    p_stop_reason text DEFAULT 'completed',
                                    p_input_tokens bigint DEFAULT NULL,
                                    p_output_tokens bigint DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql AS $fn$
DECLARE
    p         uuid := rk2_program_required();
    w         scheduler_weights%ROWTYPE;
    v_run     agent_runs%ROWTYPE;
    v_task    tasks%ROWTYPE;
    v_accepted boolean;
    v_status  text;
    n_tool    bigint := 0;
    n_lease   bigint := 0;
    n_run     bigint := 0;
BEGIN
    SELECT * INTO w FROM scheduler_weights WHERE active;
    IF NOT FOUND THEN RAISE EXCEPTION 'no active scheduler_weights row'; END IF;

    SELECT * INTO v_run FROM agent_runs
     WHERE id = p_agent_run AND program_id = p FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'agent run % is not this Program''s', p_agent_run
            USING ERRCODE = 'check_violation';
    END IF;

    PERFORM set_actor('runtime', 'rk run');
    PERFORM set_cause(v_run.id, v_run.task_id);

    n_tool := close_tool_runs(v_run.id);

    UPDATE agent_runs
       SET finished_at   = now(),
           stop_reason   = p_stop_reason,
           input_tokens  = coalesce(p_input_tokens,  input_tokens),
           output_tokens = coalesce(p_output_tokens, output_tokens)
     WHERE id = v_run.id AND finished_at IS NULL;
    GET DIAGNOSTICS n_run = ROW_COUNT;

    n_lease := (release_leases(v_run.id) ->> 'identity_leases')::bigint;

    IF v_run.task_id IS NULL THEN
        RETURN jsonb_build_object('agent_run', v_run.label, 'task', NULL,
                                  'task_status', NULL, 'runs_closed', n_run,
                                  'tool_runs_closed', n_tool, 'leases_released', n_lease);
    END IF;

    SELECT * INTO v_task FROM tasks WHERE id = v_run.task_id FOR UPDATE;
    v_accepted := task_result_accepted(v_task.id);

    IF v_task.status IN ('done','failed','abandoned') THEN
        -- Already settled. Not re-settled and not re-counted: a second call is
        -- a repeat of one attempt, not a second attempt.
        v_status := v_task.status;
    ELSIF v_accepted THEN
        v_status := 'done';
        UPDATE tasks SET status = 'done', finished_at = now(), priority = NULL
         WHERE id = v_task.id;
    ELSIF v_task.attempts >= w.max_attempts THEN
        v_status := 'abandoned';
        UPDATE tasks SET status = 'abandoned', abandoned_reason = 'attempts_exhausted',
                         finished_at = now(), priority = NULL
         WHERE id = v_task.id;
    ELSE
        -- Back to the queue with the attempt spent. The attempt is spent
        -- because it happened: `claim_task` counted it, a child ran, and a
        -- runtime that gave it back would loop on a task that fails the same
        -- way every time.
        v_status := 'pending';
        UPDATE tasks SET status = 'pending', claimed_at = NULL, priority = NULL
         WHERE id = v_task.id;
    END IF;

    RETURN jsonb_build_object('agent_run', v_run.label, 'task', v_task.label,
                              'task_status', v_status, 'accepted', v_accepted,
                              'runs_closed', n_run, 'tool_runs_closed', n_tool,
                              'leases_released', n_lease);
END $fn$;


-- ---------------------------------------------------------------------------
-- 2. What a Task in flight becomes when its owner is gone
-- ---------------------------------------------------------------------------
-- Which of them still has an owner, asked once. Both recovery paths need the
-- same two answers -- how many Tasks are still held by something that is
-- beating, and which ones are not -- and each of them used to ask in its own
-- copy of this statement. Two copies of a liveness rule is two rules: the day
-- one of them learns that a Task in flight with no expiry at all is dead, the
-- other keeps handing it back to a process that will never come for it.
--
-- A Task in flight with no expiry IS counted dead here, for that reason: the
-- claim writes one, so its absence is a row that lost its lease without losing
-- its status, and leaving it in flight forever is the one outcome nothing
-- recovers from.
CREATE FUNCTION split_tasks_in_flight(p_program uuid, OUT live bigint, OUT dead uuid[])
LANGUAGE sql STABLE AS $fn$
    SELECT count(*) FILTER (WHERE x.live),
           coalesce(array_agg(x.id) FILTER (WHERE NOT x.live), '{}'::uuid[])
      FROM (SELECT t.id, lease_live_for(t) AS live
              FROM tasks t
             WHERE t.program_id = p_program AND t.status IN ('claimed','running')) x
$fn$;

COMMENT ON FUNCTION split_tasks_in_flight(uuid) IS
    'The Tasks of one Program that are in flight, split by whether anything is '
    'still holding them: a count of the live ones and the ids of the dead. The '
    'one place recovery decides which is which.';


-- The three-way split `finish_task_attempt` makes for one run, made once for a
-- set of them, so that the reconciler, the restart sweep and the closing cannot
-- disagree about what a Task that lost its owner is. They did disagree: the
-- closing asked `task_result_accepted` and the other two did not, which is the
-- whole of the second bug -- a Task whose result the runtime had already
-- accepted went back to the queue as though the attempt had achieved nothing.
--
-- The arms are ordered and each later one re-reads the status, so the three
-- partition the set without asking the same question twice: a Task settled
-- `done` by the first statement is no longer in flight and the second and third
-- do not see it.
--
-- Nothing here touches `attempts`, for 24's reason: the attempt was made, and a
-- recovery that gave it back would loop forever on work that fails the same way
-- each time, while one that spent a second would retire a Task for having
-- crashed once.
CREATE FUNCTION settle_recovered_tasks(p_program uuid, p_dead uuid[]) RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    w      scheduler_weights%ROWTYPE;
    n_done bigint := 0; n_gone bigint := 0; n_back bigint := 0;
BEGIN
    SELECT * INTO w FROM scheduler_weights WHERE active;
    IF NOT FOUND THEN RAISE EXCEPTION 'no active scheduler_weights row'; END IF;

    -- Done, because the runtime accepted a result of it. `enforce_task_completion`
    -- permits exactly this predicate, so the arm cannot close a Task the trigger
    -- beside it would refuse.
    UPDATE tasks t SET status = 'done', finished_at = now(), priority = NULL,
                       lease_expires_at = NULL
     WHERE t.program_id = p_program AND t.id = ANY (p_dead)
       AND t.status IN ('claimed','running')
       AND task_result_accepted(t.id);
    GET DIAGNOSTICS n_done = ROW_COUNT;

    UPDATE tasks t SET status = 'abandoned', abandoned_reason = 'attempts_exhausted',
                       finished_at = now(), priority = NULL, lease_expires_at = NULL
     WHERE t.program_id = p_program AND t.id = ANY (p_dead)
       AND t.status IN ('claimed','running')
       AND t.attempts >= w.max_attempts;
    GET DIAGNOSTICS n_gone = ROW_COUNT;

    -- `lease_expires_at` is cleared by all three arms and not only by
    -- `release_leases`, and the repetition is deliberate: the release reaches
    -- the Task through the run that held it, and a Task in flight whose
    -- `agent_runs` row is gone has no such path. Leaving it settled with an
    -- expiry is `check_lease_liveness`'s own `task_lease_outlives_its_flight`.
    UPDATE tasks t SET status = 'pending', claimed_at = NULL, priority = NULL,
                       lease_expires_at = NULL
     WHERE t.program_id = p_program AND t.id = ANY (p_dead)
       AND t.status IN ('claimed','running');
    GET DIAGNOSTICS n_back = ROW_COUNT;

    RETURN jsonb_build_object('tasks_settled_done', n_done,
                              'tasks_retired', n_gone,
                              'tasks_returned', n_back);
END $fn$;

COMMENT ON FUNCTION settle_recovered_tasks(uuid, uuid[]) IS
    'What Tasks whose owner stopped beating become: done where the runtime '
    'already accepted a result of one, retired where its attempts are spent, '
    'and back in the queue otherwise. The closing''s own three-way split, said '
    'once, so that recovery cannot decide it differently.';


-- ---------------------------------------------------------------------------
-- 3. The two recovery paths ask it
-- ---------------------------------------------------------------------------
-- 24's body with its two settling statements replaced by the verb above, and
-- with the count of Tasks it found already complete added to what it reports.
-- An operator reading `1 recovered, 1 already done` is reading the difference
-- between a crash that cost an attempt and one that cost nothing at all.
CREATE OR REPLACE FUNCTION reconcile_leases() RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p       uuid := rk2_program_required();
    v_dead  uuid[];
    v_run   record;
    v_settled jsonb;
    n_live  bigint := 0;
    n_run   bigint := 0; n_lease bigint := 0; n_hyp bigint := 0;
BEGIN
    PERFORM set_actor('runtime');

    SELECT s.live, s.dead INTO n_live, v_dead FROM split_tasks_in_flight(p) s;

    UPDATE agent_runs a SET finished_at = now(), stop_reason = 'aborted', result = NULL
     WHERE a.program_id = p AND a.finished_at IS NULL AND a.task_id = ANY (v_dead);
    GET DIAGNOSTICS n_run = ROW_COUNT;

    FOR v_run IN SELECT a.id FROM agent_runs a
                  WHERE a.program_id = p AND a.task_id = ANY (v_dead)
    LOOP
        n_lease := n_lease + (release_leases(v_run.id) ->> 'identity_leases')::bigint;
    END LOOP;

    INSERT INTO hypothesis_transitions
        (program_id, hypothesis_id, from_status, to_status, actor_kind, rationale)
    SELECT p, h.id, 'testing', 'testable', 'runtime', 'task lease expired'
      FROM hypotheses h
     WHERE h.status = 'testing'
       AND h.id IN (SELECT t.hypothesis_id FROM tasks t
                     WHERE t.id = ANY (v_dead) AND t.hypothesis_id IS NOT NULL);
    GET DIAGNOSTICS n_hyp = ROW_COUNT;

    v_settled := settle_recovered_tasks(p, v_dead);

    RETURN v_settled || jsonb_build_object(
        'tasks_left_to_live_owners', n_live,
        'runs_aborted', n_run, 'leases_released', n_lease,
        'hypotheses_returned_to_testable', n_hyp);
END $fn$;

-- The restart path, which had only the middle arm of the three: everything a
-- dead owner held went back to `pending`, including work that was finished and
-- work whose attempts were spent. The first was the bug; the second was merely
-- slack, since `cancel_reason_for` refuses an exhausted Task at the next claim
-- -- but a Task that is never going to run again is retired here now, because
-- one settling statement means one answer.
CREATE OR REPLACE FUNCTION resume_program(p_program uuid) RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    n_runs bigint; n_leases bigint;
    n_hyp bigint; n_recs bigint; n_bind bigint; n_dec bigint;
    n_live bigint; v_dead uuid[]; v_settled jsonb;
BEGIN
    PERFORM set_actor('runtime');

    n_dec  := expire_due_decisions(p_program);
    n_recs := sweep_open_receipts(p_program);

    SELECT s.live, s.dead INTO n_live, v_dead
      FROM split_tasks_in_flight(p_program) s;

    v_settled := settle_recovered_tasks(p_program, v_dead);

    -- Read after the statement above, so "still in flight" means the live ones
    -- and nothing else. A run with no Task holds no lease and is therefore not
    -- live by this definition -- it is aborted, as it always was, and that is
    -- what ends the orchestrator turn a supervisor died in the middle of.
    UPDATE agent_runs a
       SET finished_at = now(), stop_reason = 'aborted', result = NULL
     WHERE a.program_id = p_program AND a.finished_at IS NULL
       AND NOT EXISTS (SELECT 1 FROM tasks t
                        WHERE t.id = a.task_id AND lease_live_for(t));
    GET DIAGNOSTICS n_runs = ROW_COUNT;

    UPDATE agent_sessions s SET unbound_at = now()
     WHERE s.program_id = p_program
       AND EXISTS (SELECT 1 FROM agent_runs r
                    WHERE r.id = s.agent_run_id AND r.finished_at IS NOT NULL)
       AND s.unbound_at IS NULL;
    GET DIAGNOSTICS n_bind = ROW_COUNT;

    UPDATE identity_leases l SET released_at = now()
     WHERE l.program_id = p_program AND l.released_at IS NULL
       AND EXISTS (SELECT 1 FROM agent_runs a
                    WHERE a.id = l.holder_agent_run_id AND a.finished_at IS NOT NULL);
    GET DIAGNOSTICS n_leases = ROW_COUNT;

    INSERT INTO hypothesis_transitions
        (program_id, hypothesis_id, from_status, to_status, actor_kind, rationale)
    SELECT p_program, h.id, 'testing', 'testable', 'runtime',
           'runtime abort: test did not complete'
      FROM hypotheses h
     WHERE h.program_id = p_program AND h.status = 'testing'
       AND NOT EXISTS (SELECT 1 FROM tasks t
                        WHERE t.hypothesis_id = h.id AND lease_live_for(t));
    GET DIAGNOSTICS n_hyp = ROW_COUNT;

    -- `tasks_unclaimed` keeps its name and its meaning -- Tasks taken back off
    -- a dead owner and offered again -- and the two arms it never had are
    -- reported beside it rather than folded into it.
    RETURN jsonb_build_object('tasks_unclaimed', v_settled -> 'tasks_returned',
                              'tasks_settled_done', v_settled -> 'tasks_settled_done',
                              'tasks_retired', v_settled -> 'tasks_retired',
                              'tasks_left_to_live_owners', n_live,
                              'agent_runs_aborted', n_runs,
                              'leases_released', n_leases,
                              'hypotheses_returned_to_testable', n_hyp,
                              'tool_receipts_abandoned', n_recs,
                              'session_bindings_dropped', n_bind,
                              'decisions_expired', n_dec);
END $fn$;


-- ---------------------------------------------------------------------------
-- 4. The surface
-- ---------------------------------------------------------------------------
-- Both verbs are the runtime's and nobody else's, for `reconcile_leases`'s own
-- reason: a function a reading role could call is a function some read could be
-- written around tomorrow. The trigger function is called by no role at all --
-- Postgres invokes it -- so it is closed to everything.
REVOKE ALL ON FUNCTION close_tool_runs(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION close_validation_attempts(uuid, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION close_what_an_ended_run_left_open() FROM PUBLIC;
REVOKE ALL ON FUNCTION settle_recovered_tasks(uuid, uuid[]) FROM PUBLIC;
REVOKE ALL ON FUNCTION split_tasks_in_flight(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION close_tool_runs(uuid) TO rk2_runtime;
GRANT EXECUTE ON FUNCTION close_validation_attempts(uuid, text) TO rk2_runtime;
GRANT EXECUTE ON FUNCTION settle_recovered_tasks(uuid, uuid[]) TO rk2_runtime;
GRANT EXECUTE ON FUNCTION split_tasks_in_flight(uuid) TO rk2_runtime;

INSERT INTO runtime_verb_surface (verb, added_by, note) VALUES
    ('close_tool_runs(uuid)', '61',
     'closes the Tool runs an ending Agent run left open, which is what revokes each one''s capability'),
    ('close_validation_attempts(uuid, text)', '61',
     'abandons the validation an ending Agent run was in the middle of, so the Finding can be asked about again'),
    ('settle_recovered_tasks(uuid, uuid[])', '61',
     'what Tasks whose owner stopped beating become: done, retired or back in the queue'),
    ('split_tasks_in_flight(uuid)', '61',
     'which of a Program''s in-flight Tasks still have an owner that is beating, and which do not');


-- ---------------------------------------------------------------------------
-- 5. What this file claims, asked of the database
-- ---------------------------------------------------------------------------
DO $$
DECLARE n bigint; d text;
BEGIN
    -- The two leaks this file closes, against the check that names them. Empty
    -- here because the corpus has no rows yet; the campaign is what proves it
    -- stays empty through a crash, and this is what proves the check still
    -- runs at all.
    SELECT count(*), string_agg(problem || ' on ' || subject || ': ' || detail, '; ')
      INTO n, d FROM check_execution_closure();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-61 leaves an attempt unclosed (% problems): %', n, d;
    END IF;

    SELECT count(*), string_agg(problem || ' on ' || subject || ': ' || detail, '; ')
      INTO n, d FROM check_lease_liveness();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-61 leaves a lease wrong (% problems): %', n, d;
    END IF;

    SELECT count(*), string_agg(problem || ' on ' || object || ': ' || detail, '; ')
      INTO n, d FROM check_runtime_privileges();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-61 leaves the runtime surface wrong (% problems): %', n, d;
    END IF;

    -- The trigger is the load-bearing half of section 1: without it the verb is
    -- one more statement three callers have to remember.
    IF NOT EXISTS (SELECT 1 FROM pg_trigger
                    WHERE tgrelid = 'agent_runs'::regclass
                      AND tgname = 'agent_runs_close_what_they_left_open') THEN
        RAISE EXCEPTION 'ph2-61 did not attach the closing to the ending run';
    END IF;

    SELECT count(*), string_agg(problem || ' on ' || subject || ': ' || detail, '; ')
      INTO n, d FROM check_validations();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-61 leaves a judgement wrong (% problems): %', n, d;
    END IF;
END $$;
