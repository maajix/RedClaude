-- Ticket 07: one durable outcome for pre-spawn and init refusals.

INSERT INTO event_types(id, family, subject_table, description) VALUES
 ('startup.refused', 'occurrence', NULL,
  'runtime startup assertion refused an agent run before tool service');

CREATE FUNCTION close_startup_refusal(
    p_agent_run_id uuid,
    p_phase text,
    p_sdk_version text,
    p_cli_version text,
    p_violations jsonb
) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE
    v_run agent_runs%ROWTYPE;
BEGIN
    IF p_phase NOT IN ('pre_spawn', 'init')
       OR jsonb_typeof(p_violations) IS DISTINCT FROM 'array'
       OR jsonb_array_length(p_violations) = 0
       OR EXISTS (
           SELECT 1 FROM jsonb_array_elements(p_violations) v
            WHERE jsonb_typeof(v) <> 'object'
               OR (SELECT array_agg(k ORDER BY k) FROM jsonb_object_keys(v) k)
                  IS DISTINCT FROM ARRAY['code','effect','source','vector']::text[]
       ) THEN
        RAISE EXCEPTION 'invalid startup refusal payload' USING ERRCODE = '22023';
    END IF;

    SELECT * INTO v_run FROM agent_runs
     WHERE id = p_agent_run_id AND program_id = rk2_program()
     FOR UPDATE;
    IF NOT FOUND OR v_run.finished_at IS NOT NULL THEN
        RETURN false;
    END IF;

    PERFORM set_config('app.actor_kind', 'runtime', true);
    UPDATE agent_runs
       SET finished_at = clock_timestamp(), stop_reason = 'refusal', result = NULL
     WHERE id = v_run.id;

    UPDATE tasks
       SET status = 'pending', attempts = greatest(attempts - 1, 0),
           claimed_at = NULL, lease_expires_at = NULL, finished_at = NULL,
           priority = NULL, pending_decision_id = NULL, abandoned_reason = NULL
     WHERE id = v_run.task_id AND program_id = v_run.program_id;

    UPDATE agent_sessions SET unbound_at = clock_timestamp()
     WHERE agent_run_id = v_run.id AND unbound_at IS NULL;
    UPDATE identity_leases SET released_at = clock_timestamp()
     WHERE holder_agent_run_id = v_run.id AND released_at IS NULL;

    INSERT INTO events(program_id, type, actor_kind, agent_run_id, task_id, payload)
    VALUES(v_run.program_id, 'startup.refused', 'runtime', v_run.id, v_run.task_id,
           jsonb_build_object(
             'schema_version', 1,
             'phase', p_phase,
             'sdk_version', p_sdk_version,
             'cli_version', p_cli_version,
             'violations', p_violations));
    RETURN true;
END $fn$;

REVOKE ALL ON FUNCTION close_startup_refusal(uuid,text,text,text,jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION close_startup_refusal(uuid,text,text,text,jsonb) TO rk2_runtime;

COMMENT ON FUNCTION close_startup_refusal(uuid,text,text,text,jsonb) IS
  'Idempotently closes one open agent run as a startup refusal, returns its task without consuming an attempt, releases bindings and leases, and emits exactly one startup.refused event.';
