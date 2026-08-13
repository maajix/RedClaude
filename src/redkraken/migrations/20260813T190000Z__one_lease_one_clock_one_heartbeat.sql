-- ===========================================================================
-- Production harness 24 -- one lease, one clock, one heartbeat
-- ===========================================================================
-- CONTEXT.md's **Lease**: "An exclusive, expiring hold taken by one agent run
-- -- on an identity, and on the task it is executing. [...] Both leases of one
-- run share a single clock and a single heartbeat: a run whose task lease is
-- alive always holds live identity leases."
--
-- Every clause of that was true at the moment `claim_task` wrote the two rows
-- and about nothing afterwards. There was no heartbeat at all: `lease_ttl` was
-- a deadline nothing could extend, so a run longer than thirty minutes had its
-- work taken back underneath it, and a run shorter than that held its identity
-- for the remainder of the half hour whatever happened to it. 014 has carried
-- `lease_expires_at` in `tasks`'s ignored event columns since ticket 08, with
-- the comment "a lease heartbeat would otherwise emit a task.updated per
-- renewal", which is a column reserved for a renewal nobody had written.
--
-- And "expired" was never asked. `resume_program()` unclaimed every claimed or
-- running Task of the Program and released every identity lease it could see,
-- without looking at a single expiry -- so a second `rk run` against a Program
-- with work in flight was not a competitor the leases refused, it was a
-- competitor that dissolved them and then claimed what they had held. That is
-- the state criterion 3 names, reached by the one path criterion 5 names.
--
-- Four verbs, and they are the whole surface:
--
--   heartbeat_leases(run)  one reading of the clock moves both leases or
--                          neither, and a lapsed lease is not resurrected.
--   release_leases(run)    the one statement of "this run holds nothing now",
--                          which the closing and the reconciler both call.
--   reconcile_leases()     what an expired owner leaves behind, recovered;
--                          what a live one holds, reported and left alone.
--   resume_program(p)      the same distinction on the restart path, which is
--                          where the competing claim actually came from.


-- ---------------------------------------------------------------------------
-- 1. The renewal is a non-event on both tables, not on one
-- ---------------------------------------------------------------------------
-- 014 exempted `tasks.lease_expires_at` so a heartbeat would not write a
-- `task.updated` every renewal. `identity_leases.expires_at` is the same column
-- on the other half of the same lease and was never exempted, because the
-- heartbeat it was written against did not exist yet. Exempting it now is what
-- makes one beat one silence rather than one silence and one event.
--
-- Silence, not absence: 016's emitter records a suppressed write when every
-- column that changed was ignored, so `check_event_log_integrity` can still
-- tell a deliberate non-event from a trigger somebody disabled. `released_at`
-- is untouched by this and stays an event, which is the asymmetry that matters
-- -- renewing a hold is bookkeeping, ending one is a fact about the Program.
UPDATE event_table_config
   SET ignored_columns = ignored_columns || '{expires_at}'
 WHERE table_name = 'identity_leases';

SELECT attach_event_triggers();


-- ---------------------------------------------------------------------------
-- 2. The heartbeat
-- ---------------------------------------------------------------------------
-- One reading of `now()`, written to both leases. `now()` and not
-- `clock_timestamp()`, and that is the whole mechanism behind "cannot disagree
-- on liveness": `now()` is the transaction's timestamp, so the two UPDATEs
-- below cannot land a microsecond apart no matter how much work sits between
-- them. `claim_task` writes the pair the same way, which is why they start
-- equal, and the standing check reads both functions' text for the other clock.
--
-- A beat does not resurrect. If the Task lease has already lapsed then some
-- reconciliation is entitled to the row -- may already have taken it -- and a
-- heartbeat that pushed the expiry back into the future would be this process
-- claiming work it no longer holds. It reports that it did not beat instead,
-- and the identity leases are left alone in the same breath: extending them
-- under a dead task lease is exactly the disagreement this ticket is about.
CREATE FUNCTION heartbeat_leases(p_agent_run uuid) RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p       uuid := rk2_program_required();
    w       scheduler_weights%ROWTYPE;
    v_run   agent_runs%ROWTYPE;
    v_until timestamptz;
    n_task  bigint := 0;
    n_ident bigint := 0;
BEGIN
    SELECT * INTO w FROM scheduler_weights WHERE active;
    IF NOT FOUND THEN RAISE EXCEPTION 'no active scheduler_weights row'; END IF;

    SELECT * INTO v_run FROM agent_runs WHERE id = p_agent_run AND program_id = p;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'agent run % is not this Program''s', p_agent_run
            USING ERRCODE = 'check_violation';
    END IF;

    PERFORM set_actor('runtime');
    PERFORM set_cause(v_run.id, v_run.task_id);

    v_until := now() + w.lease_ttl;

    -- The Task lease is the liveness, so it is asked first and its answer
    -- decides the identity half. A run with no Task -- the orchestrator is one
    -- -- has no task lease to beat, and reporting that is not an error: it is
    -- a caller heartbeating something that was never leased.
    UPDATE tasks SET lease_expires_at = v_until
     WHERE id = v_run.task_id AND program_id = p
       AND status IN ('claimed','running')
       AND lease_expires_at IS NOT NULL AND lease_expires_at > now();
    GET DIAGNOSTICS n_task = ROW_COUNT;

    IF n_task = 0 THEN
        RETURN jsonb_build_object('agent_run', v_run.label, 'beat', false,
                                  'reason', CASE WHEN v_run.task_id IS NULL
                                                 THEN 'the run holds no task lease'
                                                 ELSE 'the task lease has lapsed' END,
                                  'expires_at', NULL, 'identity_leases', 0);
    END IF;

    UPDATE identity_leases SET expires_at = v_until
     WHERE program_id = p AND holder_agent_run_id = v_run.id AND released_at IS NULL;
    GET DIAGNOSTICS n_ident = ROW_COUNT;

    RETURN jsonb_build_object('agent_run', v_run.label, 'beat', true,
                              'reason', NULL, 'expires_at', v_until,
                              'identity_leases', n_ident);
END $fn$;

COMMENT ON FUNCTION heartbeat_leases(uuid) IS
    'Moves one run''s Task Lease and every Identity Lease it holds to the same '
    'new expiry, from one reading of the transaction clock. Idempotent: the '
    'expiry is set, never accumulated. A lapsed Task Lease is reported, not '
    'renewed, and its Identity Leases are left where they are.';


-- ---------------------------------------------------------------------------
-- 3. The release, said once
-- ---------------------------------------------------------------------------
-- Six functions have written some version of "release this run's identity
-- leases" -- the closing, the sweep, the resume, the park, the refusal
-- lifecycle, the receipt sweep -- and each of them also had to remember the
-- Task's own lease column separately, or not remember it. `resume_program()`
-- is where not remembering showed: it unclaimed Tasks and left
-- `lease_expires_at` pointing at a future the row no longer had any claim on.
--
-- This is that statement, for one run, with both halves of the lease in it.
-- It settles nothing else: what the Task becomes is the caller's question, and
-- a release that also decided that would be two decisions with one name.
CREATE FUNCTION release_leases(p_agent_run uuid) RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p       uuid := rk2_program_required();
    v_run   agent_runs%ROWTYPE;
    n_task  bigint := 0;
    n_ident bigint := 0;
BEGIN
    SELECT * INTO v_run FROM agent_runs WHERE id = p_agent_run AND program_id = p;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'agent run % is not this Program''s', p_agent_run
            USING ERRCODE = 'check_violation';
    END IF;

    PERFORM set_actor('runtime');
    PERFORM set_cause(v_run.id, v_run.task_id);

    -- `IS NOT NULL` is what makes the second call a no-op rather than a second
    -- identical write: without it the row is updated to the value it already
    -- holds, the emitter sees nothing changed, and the count says one lease was
    -- released twice.
    UPDATE tasks SET lease_expires_at = NULL
     WHERE id = v_run.task_id AND program_id = p AND lease_expires_at IS NOT NULL;
    GET DIAGNOSTICS n_task = ROW_COUNT;

    UPDATE identity_leases SET released_at = now()
     WHERE program_id = p AND holder_agent_run_id = v_run.id AND released_at IS NULL;
    GET DIAGNOSTICS n_ident = ROW_COUNT;

    RETURN jsonb_build_object('agent_run', v_run.label,
                              'task_lease_released', n_task > 0,
                              'identity_leases', n_ident);
END $fn$;

COMMENT ON FUNCTION release_leases(uuid) IS
    'Ends one run''s hold on its Task and on every Identity it leased. '
    'Idempotent: a second call releases nothing and says so, because a lease '
    'already given back is not a lease.';


-- The closing reads it rather than restating it. Everything else about this
-- function is 020's, including the order the comment there argues for: Tool
-- runs close before the Agent run, because closing a Tool run is what revokes
-- its capability.
CREATE OR REPLACE FUNCTION finish_task_attempt(p_agent_run uuid, p_stop_reason text DEFAULT 'completed')
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

    UPDATE tool_runs SET status = 'error', finished_at = now()
     WHERE program_id = p AND agent_run_id = v_run.id AND status = 'running';
    GET DIAGNOSTICS n_tool = ROW_COUNT;

    UPDATE agent_runs SET finished_at = now(), stop_reason = p_stop_reason
     WHERE id = v_run.id AND finished_at IS NULL;
    GET DIAGNOSTICS n_run = ROW_COUNT;

    n_lease := (release_leases(v_run.id) ->> 'identity_leases')::bigint;

    IF v_run.task_id IS NULL THEN
        RETURN jsonb_build_object('agent_run', v_run.label, 'task', NULL,
                                  'task_status', NULL, 'runs_closed', n_run,
                                  'tool_runs_closed', n_tool, 'leases_released', n_lease);
    END IF;

    SELECT * INTO v_task FROM tasks WHERE id = v_run.task_id FOR UPDATE;
    v_accepted := EXISTS (SELECT 1 FROM proposals pr
                           WHERE pr.task_id = v_task.id AND pr.status = 'promoted');

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
-- 4. Reconciliation, which is a question about expiry
-- ---------------------------------------------------------------------------
-- 023's `sweep_expired_leases()` under the name that says what it decides. Two
-- things about it were wrong for this ticket rather than merely differently
-- named, and both are why the rename is a replacement:
--
--   * it built a `TEMP TABLE _expired ON COMMIT DROP`, so a second call in one
--     transaction raised `relation "_expired" already exists`. A reconciler
--     that cannot be called twice is not idempotent, and idempotence is the
--     property criterion 4 asks of every verb here.
--   * it reported what it recovered and never what it declined to. "Nothing
--     was expired" and "four runs are alive and holding their work" produced
--     the same answer, and criterion 5 is the difference between them.
--
-- What makes an owner live is that it beat inside the TTL. That is the only
-- liveness this system has and the only one it needs: a process that died
-- stops beating, and a process that is alive and not beating has nothing to
-- distinguish it from one that died.
DROP FUNCTION sweep_expired_leases();

CREATE FUNCTION reconcile_leases() RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p       uuid := rk2_program_required();
    w       scheduler_weights%ROWTYPE;
    v_dead  uuid[];
    v_run   record;
    n_live  bigint := 0;
    n_task  bigint := 0; n_gone bigint := 0; n_run bigint := 0;
    n_lease bigint := 0; n_hyp bigint := 0;
BEGIN
    SELECT * INTO w FROM scheduler_weights WHERE active;
    IF NOT FOUND THEN RAISE EXCEPTION 'no active scheduler_weights row'; END IF;
    PERFORM set_actor('runtime');

    -- One pass over the in-flight rows, splitting them by the clock. A Task in
    -- flight with no expiry at all is counted dead: the claim writes one, so
    -- its absence is a row that lost its lease without losing its status, and
    -- leaving it in flight forever is the one outcome nothing recovers from.
    SELECT count(*) FILTER (WHERE live),
           coalesce(array_agg(id) FILTER (WHERE NOT live), '{}'::uuid[])
      INTO n_live, v_dead
      FROM (SELECT t.id,
                   t.lease_expires_at IS NOT NULL AND t.lease_expires_at > now() AS live
              FROM tasks t
             WHERE t.program_id = p AND t.status IN ('claimed','running')) x;

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

    -- Criterion 6, in two statements that partition the same set. Neither
    -- touches `attempts`: the attempt was made -- `claim_task` counted it and a
    -- child ran against it -- and a recovery that gave it back would loop
    -- forever on work that fails the same way each time, while one that spent a
    -- second would retire a Task for having crashed once.
    UPDATE tasks t SET status = 'abandoned', abandoned_reason = 'attempts_exhausted',
                       finished_at = now(), priority = NULL
     WHERE t.id = ANY (v_dead) AND t.attempts >= w.max_attempts;
    GET DIAGNOSTICS n_gone = ROW_COUNT;

    UPDATE tasks t SET status = 'pending', claimed_at = NULL, priority = NULL
     WHERE t.id = ANY (v_dead) AND t.attempts < w.max_attempts;
    GET DIAGNOSTICS n_task = ROW_COUNT;

    RETURN jsonb_build_object('tasks_left_to_live_owners', n_live,
                              'tasks_returned', n_task, 'tasks_retired', n_gone,
                              'runs_aborted', n_run, 'leases_released', n_lease,
                              'hypotheses_returned_to_testable', n_hyp);
END $fn$;

COMMENT ON FUNCTION reconcile_leases() IS
    'Recovers what an expired owner left in flight and reports what a live one '
    'still holds, distinguishing the two by the expiry the heartbeat writes. '
    'Idempotent, and never a side effect of a read: nothing in this corpus '
    'calls it, which the standing check asserts.';


-- ---------------------------------------------------------------------------
-- 5. The restart path asks the same question
-- ---------------------------------------------------------------------------
-- 013's body by way of 022, 026 and 030, with the distinction section 4 makes
-- put into it. Every `rk run` against an existing Program calls this, so what
-- it used to mean was: a second `rk run` releases the first one's leases and is
-- then free to claim what they held. That is criterion 3's competing claim, and
-- it did not arrive through `claim_task` -- which has always refused it -- but
-- through the restart that ran before the claim.
--
-- The cost is stated rather than hidden: after a crash, the dead process's
-- Tasks stay claimed until their lease lapses, which is `lease_ttl` at worst.
-- That is what an expiring hold is, and section 2 is what makes the TTL a real
-- bound rather than a guess -- a live process keeps beating, so the TTL is only
-- ever paid by one that stopped.
CREATE OR REPLACE FUNCTION resume_program(p_program uuid) RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    n_tasks bigint; n_runs bigint; n_leases bigint;
    n_hyp bigint; n_recs bigint; n_bind bigint; n_dec bigint;
    n_live bigint; v_dead uuid[];
BEGIN
    PERFORM set_actor('runtime');

    n_dec  := expire_due_decisions(p_program);
    n_recs := sweep_open_receipts(p_program);

    SELECT count(*) FILTER (WHERE live),
           coalesce(array_agg(id) FILTER (WHERE NOT live), '{}'::uuid[])
      INTO n_live, v_dead
      FROM (SELECT t.id,
                   t.lease_expires_at IS NOT NULL AND t.lease_expires_at > now() AS live
              FROM tasks t
             WHERE t.program_id = p_program AND t.status IN ('claimed','running')) x;

    -- `lease_expires_at` is cleared here and was not before, which was the
    -- quiet half of the same bug: a Task went back to `pending` carrying an
    -- expiry it no longer had any hold under, and the only reason nothing read
    -- it was that every reader also checked the status.
    UPDATE tasks SET status = 'pending', claimed_at = NULL, priority = NULL,
                     lease_expires_at = NULL
     WHERE id = ANY (v_dead);
    GET DIAGNOSTICS n_tasks = ROW_COUNT;

    -- Read after the statement above, so "still in flight" means the live ones
    -- and nothing else. A run with no Task holds no lease and is therefore not
    -- live by this definition -- it is aborted, as it always was.
    UPDATE agent_runs a
       SET finished_at = now(), stop_reason = 'aborted', result = NULL
     WHERE a.program_id = p_program AND a.finished_at IS NULL
       AND NOT EXISTS (SELECT 1 FROM tasks t
                        WHERE t.id = a.task_id
                          AND t.status IN ('claimed','running')
                          AND t.lease_expires_at IS NOT NULL
                          AND t.lease_expires_at > now());
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
                        WHERE t.hypothesis_id = h.id
                          AND t.status IN ('claimed','running')
                          AND t.lease_expires_at IS NOT NULL
                          AND t.lease_expires_at > now());
    GET DIAGNOSTICS n_hyp = ROW_COUNT;

    RETURN jsonb_build_object('tasks_unclaimed', n_tasks,
                              'tasks_left_to_live_owners', n_live,
                              'agent_runs_aborted', n_runs,
                              'leases_released', n_leases,
                              'hypotheses_returned_to_testable', n_hyp,
                              'tool_receipts_abandoned', n_recs,
                              'session_bindings_dropped', n_bind,
                              'decisions_expired', n_dec);
END $fn$;

COMMENT ON FUNCTION resume_program(uuid) IS
    'The restart sweep: expired decisions, open receipts, and everything an '
    'owner that stopped beating left in flight. A Task whose Lease has not '
    'lapsed is left to the run that holds it, and counted rather than taken.';


-- ---------------------------------------------------------------------------
-- 6. The lease surface is the runtime's
-- ---------------------------------------------------------------------------
-- Postgres grants EXECUTE on a new function to PUBLIC. `reconcile_leases` is
-- the one that matters most here: criterion 5 says reconciliation must never
-- run as a side effect of a status read, and a function the reading role can
-- call is one a read could be written around tomorrow.
DO $$
DECLARE f text;
BEGIN
    FOREACH f IN ARRAY ARRAY[
        'heartbeat_leases(uuid)', 'release_leases(uuid)', 'reconcile_leases()']
    LOOP
        EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC', f);
        EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO rk2_runtime', f);
    END LOOP;
END $$;


-- ---------------------------------------------------------------------------
-- 7. The standing check
-- ---------------------------------------------------------------------------
-- What a lease can get wrong, as rows where rows can say it and as function
-- text where only the text can. Three arms are textual for the reason 023's
-- arm (g) is: "both leases share one clock" is a property of how the functions
-- are written, and an edit that quietly replaced `now()` with
-- `clock_timestamp()` would leave every row looking exactly as it does today
-- while making the two expiries disagree by however long the statement took.
CREATE FUNCTION check_lease_liveness()
RETURNS TABLE (problem text, subject text, detail text)
LANGUAGE sql STABLE AS $fn$
    -- (a) the glossary's sentence, as a row test. A live identity lease whose
    --     holder is executing a Task must expire when that Task's lease does;
    --     one clock means one value, not two values close together.
    SELECT 'identity_lease_outlives_its_task_lease', l.id::text,
           'an unreleased Identity Lease whose expiry is not its Task Lease''s'
      FROM identity_leases l
      JOIN agent_runs a ON a.id = l.holder_agent_run_id
      JOIN tasks t ON t.id = a.task_id
     WHERE l.released_at IS NULL
       AND t.status IN ('claimed','running')
       AND t.lease_expires_at IS DISTINCT FROM l.expires_at

  UNION ALL
    -- (b) the other direction of the same sentence: a hold whose holder has
    --     stopped. `release_leases` is what makes this impossible; an arm
    --     rather than a comment because six functions end runs.
    SELECT 'identity_lease_held_by_a_finished_run', l.id::text,
           'an unreleased Identity Lease held by an Agent run that has finished'
      FROM identity_leases l
      JOIN agent_runs a ON a.id = l.holder_agent_run_id
     WHERE l.released_at IS NULL AND a.finished_at IS NOT NULL

  UNION ALL
    -- (c) a Task in flight with nothing holding it. Not merely untidy: it is
    --     invisible to every expiry comparison, so nothing would ever recover
    --     it and nothing would ever say why.
    SELECT 'task_in_flight_without_a_lease', t.label,
           'a claimed or running Task with no lease expiry'
      FROM tasks t
     WHERE t.status IN ('claimed','running') AND t.lease_expires_at IS NULL

  UNION ALL
    -- (d) the mirror: a lease on a Task nobody is executing. `resume_program`
    --     left these behind for three tickets.
    SELECT 'task_lease_outlives_its_flight', t.label,
           'a Task that is not claimed or running and still carries a lease expiry'
      FROM tasks t
     WHERE t.status NOT IN ('claimed','running') AND t.lease_expires_at IS NOT NULL

  UNION ALL
    -- (e) one clock, textually. `clock_timestamp()` advances inside a
    --     statement, so two writes from it are two clocks however adjacent
    --     they look. Comments are stripped first, for 023's reason: the first
    --     version of its own textual arm fired on a comment explaining why the
    --     clock was absent.
    SELECT 'lease_writer_reads_a_statement_clock', p.proname,
           'a function that writes a lease expiry from clock_timestamp()'
      FROM pg_proc p
     WHERE p.pronamespace = 'public'::regnamespace
       AND p.proname IN ('claim_task','heartbeat_leases')
       AND regexp_replace(p.prosrc, '--[^' || chr(10) || ']*', '', 'g')
           ~* 'clock_timestamp'

  UNION ALL
    -- (f) criterion 5's second half. Reconciliation is explicit, which means
    --     no other function in this database reaches it -- not a view, not a
    --     read, not a trigger. The runtime calls it; nothing calls the runtime.
    SELECT 'reconciliation_is_reachable_from_another_function', p.proname,
           'a database function calls reconcile_leases()'
      FROM pg_proc p
     WHERE p.pronamespace = 'public'::regnamespace
       AND p.proname NOT IN ('reconcile_leases','check_lease_liveness')
       AND regexp_replace(p.prosrc, '--[^' || chr(10) || ']*', '', 'g')
           ~ 'reconcile_leases'

  UNION ALL
    -- (g) every lease write declares an actor. The emitter raises without one,
    --     so this is not what makes attribution true -- it is what stops a
    --     verb from being written that can only be called inside somebody
    --     else's transaction.
    SELECT 'lease_verb_declares_no_actor', p.proname,
           'a lease verb that writes without calling set_actor()'
      FROM pg_proc p
     WHERE p.pronamespace = 'public'::regnamespace
       AND p.proname IN ('heartbeat_leases','release_leases','reconcile_leases',
                         'resume_program')
       AND p.prosrc !~ 'set_actor'

  UNION ALL
    -- (h) 023's arm (i), for the verbs this file adds.
    SELECT 'lease_function_public_executable', p.proname,
           'an agent-reachable role can call a lease verb'
      FROM pg_proc p
     WHERE p.pronamespace = 'public'::regnamespace
       AND p.proname IN ('heartbeat_leases','release_leases','reconcile_leases')
       AND has_function_privilege('public', p.oid, 'EXECUTE')
$fn$;

REVOKE ALL ON FUNCTION check_lease_liveness() FROM PUBLIC;

COMMENT ON FUNCTION check_lease_liveness() IS
    'What a Lease can get wrong: two halves of one hold disagreeing about when '
    'it ends, a hold outliving its holder, a Task in flight with nothing '
    'holding it or holding one it is not in, a second clock, and a '
    'reconciliation something else can trigger.';

INSERT INTO standing_checks(name, query, owner_ticket, note) VALUES
    ('lease_liveness', 'SELECT * FROM check_lease_liveness()', '24',
     'both halves of one run''s Lease share one clock and one expiry, no hold outlives its holder, and reconciliation is reachable only from the runtime');


-- ---------------------------------------------------------------------------
-- 8. The invariants this file must not have broken
-- ---------------------------------------------------------------------------

-- Nothing here calls the three verbs, and that is deliberate rather than an
-- omission: every one of them starts at `rk2_program_required()`, and a
-- migration runs on an unbound connection because it is about the corpus and
-- not about any one Program. What they do is asserted where a Program exists,
-- which is `LeaseTest`.
DO $$
DECLARE n integer; d text;
BEGIN
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_lease_liveness();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-24 refuses to finish: % lease violation(s): %', n, d;
    END IF;

    -- Not `check_event_log_integrity()`: half of what it asks is whether every
    -- enforcement trigger is ENABLE ALWAYS, and the sweep that makes them so is
    -- a finalizer -- it runs after the last migration, so every migration sees
    -- its own triggers at 'O'. What section 1 changed is a registry row, and
    -- `attach_event_triggers()` above is the whole of acting on it.
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_scheduler_closure();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-24 breaks scheduler closure (% problems): %', n, d;
    END IF;
END $$;
