-- ---------------------------------------------------------------------------
-- A Task waiting on a person is not a Task to hand back
--
-- WHAT WAS MEASURED. `rk2here`, lap 14 of hunt-sitting03, 2026-08-26. The
-- Program held a provisioned Identity for the first time -- 191 and 193 -- so
-- `call_risk_rules` answered `ask` to a request made as somebody, which is what
-- that rule is for. Seven milliseconds later the park was undone:
--
--     48913  task.updated  after  {"status": "parked",
--                                  "pending_decision_id": "01a03e95-949d-..."}
--                          before {"status": "claimed"}
--     48914  task.updated  after  {"status": "pending"}
--                          before {"status": "parked"}
--
-- and the question could no longer be answered at all:
--
--     D1 was not approved: decision D1 no longer validates against the current
--     configuration: task_no_longer_parked
--
-- `hunt.sh` stops on `awaiting_decision`, `answer_decision` refuses every
-- answer, and the campaign cannot proceed in either direction. A deadlock, with
-- the only way out of it by hand.
--
-- THE MECHANISM. `park_authorized_tool_run` ends the Agent run -- `stop_reason
-- = 'parked'` -- because 20260814T060000Z states that a park is not a pause
-- inside a live child. The pass then runs its ordinary closing over the run it
-- was already holding, and `finish_task_attempt` asks whether the Task is
-- settled:
--
--     IF v_task.status IN ('done','failed','abandoned') THEN
--
-- `parked` is not in that list, so the last arm runs and puts the Task back on
-- the queue. It writes `status`, `claimed_at` and `priority` and does not touch
-- `pending_decision_id`, which is exactly the one-column diff event 48914
-- recorded -- and which leaves the row naming a decision it is no longer parked
-- for.
--
-- WHY IT SURFACED NOW. Nothing in this tree had ever parked a Task in a live
-- campaign. `20261028T000000Z` built the path the model asks for, `0026` and
-- `20260816T000000Z` the two the gate asks for, and the gate arm that fires
-- here -- `net_borrowed_identity` -- needs a Program that acts as a named
-- Identity. `20261120T000000Z` is what gave one to every campaign.
--
-- THE RULE. `parked` joins the settled list. A parked Task is not settled in
-- the sense the other three are -- it will run again -- but it is settled in the
-- sense this branch is asking about: nothing about it is this runtime's to
-- decide any more. The one verb that may take it out of `parked` is
-- `answer_decision`, which clears `pending_decision_id` in the same statement.
--
-- The reported `task_status` becomes `parked` rather than `pending`, which is
-- what the pass should have been saying all along: the Task did not go back on
-- the queue, it is waiting for a person.
--
-- WHAT IS NOT CHANGED. The attempt still counts. `claim_task` counted it, a
-- child ran and reached a tool call, and refunding it would let a Program that
-- parks the same question forever never exhaust its attempts. The recovery paths
-- are already right: `split_tasks_in_flight` reads `status IN
-- ('claimed','running')`, so nothing parked is ever seen as wreckage.
--
-- The body below is the installed definition with that one list widened and
-- nothing else touched. Written out whole rather than patched, because 165 and
-- the two files after it grew the signature and a hand-written copy of it is a
-- second place the parameter list lives.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.finish_task_attempt(p_agent_run uuid, p_stop_reason text DEFAULT 'completed'::text, p_input_tokens bigint DEFAULT NULL::bigint, p_output_tokens bigint DEFAULT NULL::bigint, p_uncached_input_tokens bigint DEFAULT NULL::bigint, p_cache_creation_input_tokens bigint DEFAULT NULL::bigint, p_cache_read_input_tokens bigint DEFAULT NULL::bigint, p_answer_count integer DEFAULT NULL::integer, p_budget_tokens bigint DEFAULT NULL::bigint, p_budget_policy text DEFAULT NULL::text, p_attempt_profile_sha256 text DEFAULT NULL::text, p_error_detail text DEFAULT NULL::text)
 RETURNS jsonb
 LANGUAGE plpgsql
AS $function$
DECLARE
    p         uuid := rk2_program_required();
    w         scheduler_weights%ROWTYPE;
    v_run     agent_runs%ROWTYPE;
    v_task    tasks%ROWTYPE;
    v_accepted boolean;
    v_status  text;
    v_profile text;
    v_ends    bigint := 0;
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
           output_tokens = coalesce(p_output_tokens, output_tokens),
           uncached_input_tokens
               = coalesce(p_uncached_input_tokens, uncached_input_tokens),
           cache_creation_input_tokens
               = coalesce(p_cache_creation_input_tokens, cache_creation_input_tokens),
           cache_read_input_tokens
               = coalesce(p_cache_read_input_tokens, cache_read_input_tokens),
           answer_count  = coalesce(p_answer_count, answer_count),
           budget_tokens = coalesce(p_budget_tokens, budget_tokens),
           budget_policy = coalesce(p_budget_policy, budget_policy),
           attempt_profile_sha256
               = coalesce(p_attempt_profile_sha256, attempt_profile_sha256),
           -- Truncated here as well as bounded on the column, because a run
           -- whose detail ran long is a run whose ending would otherwise be
           -- rolled back by the constraint that was meant to redact it.
           error_detail  = coalesce(left(p_error_detail, 2048), error_detail)
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

    -- Ticket 165's fourth open question. Only a budget ending counts, and only
    -- one carrying a profile: a run nobody digested is a run this rule cannot
    -- say anything about, and guessing would end Tasks that had changed.
    v_profile := coalesce(p_attempt_profile_sha256, v_run.attempt_profile_sha256);
    IF p_stop_reason = 'budget' AND v_profile IS NOT NULL THEN
        SELECT count(*) INTO v_ends FROM agent_runs a
         WHERE a.task_id = v_task.id
           AND a.stop_reason = 'budget'
           AND a.attempt_profile_sha256 = v_profile;
    END IF;

    -- `parked` among them, and it is the reason this file exists. A parked
    -- Task is waiting on a person: `park_authorized_tool_run` ended the run on
    -- the way in, so the closing that follows is this pass tidying up after a
    -- decision that has already been made about the Task. Handing it back to
    -- the queue leaves it naming a `pending_decision_id` it is not parked for,
    -- and `answer_decision` then refuses every answer with
    -- `task_no_longer_parked` -- a question nothing can approve and nothing can
    -- deny.
    IF v_task.status IN ('done','failed','abandoned','parked') THEN
        -- Already settled, or settled by somebody who is not this runtime. Not
        -- re-settled and not re-counted: a second call is a repeat of one
        -- attempt, not a second attempt.
        v_status := v_task.status;
    ELSIF v_accepted THEN
        v_status := 'done';
        UPDATE tasks SET status = 'done', finished_at = now(), priority = NULL
         WHERE id = v_task.id;
    ELSIF v_ends >= 2 THEN
        -- Before `attempts_exhausted`, because it is the more exact account of
        -- the same ending: the attempts were spent, and they were spent twice
        -- on the identical dispatch.
        v_status := 'abandoned';
        UPDATE tasks SET status = 'abandoned',
                         abandoned_reason = 'budget_exhausted_twice',
                         finished_at = now(), priority = NULL
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
                              'leases_released', n_lease,
                              'budget_ends', v_ends);
END $function$;

COMMENT ON FUNCTION finish_task_attempt(uuid,text,bigint,bigint,bigint,bigint,
                                        bigint,integer,bigint,text,text,text) IS
  'Closes one Agent run, its Tool runs and its Identity Leases, and settles the Task behind it: done where the runtime accepted a result, abandoned where the attempts are spent, and back on the queue otherwise. A Task already done, failed, abandoned or PARKED is left exactly as it is -- a parked Task is waiting on a person, and handing it back to the queue would leave it naming a decision it is not parked for, which nothing can then answer.';


-- The correction to what was already written. One Program hit this in a live
-- campaign, so the row it left behind is real: a Task on the queue still naming
-- the question it was parked for. Cleared rather than re-parked -- the run that
-- asked is finished and its capability with it, so there is nothing left to
-- resume; the runtime asks again when it next claims the Task, and this time the
-- park holds. The question itself is left for an operator to supersede, which is
-- what `answer_decision` tells them to do.
DO $$
DECLARE n integer;
BEGIN
    UPDATE tasks SET pending_decision_id = NULL
     WHERE status <> 'parked' AND pending_decision_id IS NOT NULL;
    GET DIAGNOSTICS n = ROW_COUNT;
    IF n > 0 THEN
        RAISE NOTICE 'cleared % stale decision reference(s) off unparked Tasks', n;
    END IF;

    SELECT count(*) INTO n FROM pg_proc
     WHERE pronamespace = 'public'::regnamespace
       AND proname = 'finish_task_attempt'
       AND prosrc ~ 'abandoned'',''parked';
    IF n <> 1 THEN
        RAISE EXCEPTION 'finish_task_attempt still hands a parked Task back to the queue';
    END IF;
END $$;
