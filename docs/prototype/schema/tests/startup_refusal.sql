-- Ticket 07: startup refusal is one durable runtime outcome.

GRANT USAGE ON SCHEMA t TO rk2_runtime;
GRANT INSERT ON t.results TO rk2_runtime;
GRANT USAGE ON SEQUENCE t.results_ord_seq TO rk2_runtime;

SET ROLE rk2_runtime;
SELECT set_config('app.actor_kind', 'runtime', false);
SELECT set_config('rk2.program_id', '11111111-1111-7111-8111-111111111111', false);

DO $outer$
DECLARE
    first_close boolean;
    second_close boolean;
    before_hyp bigint;
    ok boolean := false;
    note text := 'startup cleanup failed';
    refusal jsonb := '[{"code":"credential_vector","vector":"ANTHROPIC_BASE_URL","source":"env:ANTHROPIC_BASE_URL","effect":"destination_override"}]';
BEGIN
    BEGIN
        INSERT INTO tasks
            (id, program_id, label, kind, subject_entity_id, status, attempts,
             claimed_at, lease_expires_at, priority)
        VALUES
            ('07000000-0000-7000-8000-000000000001',
             '11111111-1111-7111-8111-111111111111', 'T_STARTUP_REFUSAL',
             'recon', 'aaaaaaaa-0000-7000-8000-000000000005', 'claimed', 1,
             now(), now() + interval '30 minutes', 1);
        INSERT INTO agent_runs
            (id, program_id, label, task_id, role, model, effort, mission_packet)
        VALUES
            ('07000000-0000-7000-8000-000000000002',
             '11111111-1111-7111-8111-111111111111', 'AR_STARTUP_REFUSAL',
             '07000000-0000-7000-8000-000000000001', 'recon',
             'claude-opus-5', 'high', '{}');
        INSERT INTO agent_sessions
            (id, program_id, session_id, agent_run_id, task_id)
        VALUES
            ('07000000-0000-7000-8000-000000000003',
             '11111111-1111-7111-8111-111111111111', 'startup-refusal-session',
             '07000000-0000-7000-8000-000000000002',
             '07000000-0000-7000-8000-000000000001');
        INSERT INTO identity_leases
            (id, program_id, identity_entity_id, holder_agent_run_id, expires_at)
        VALUES
            ('07000000-0000-7000-8000-000000000004',
             '11111111-1111-7111-8111-111111111111',
             'aaaaaaaa-0000-7000-8000-000000000003',
             '07000000-0000-7000-8000-000000000002',
             now() + interval '30 minutes');

        SELECT count(*) INTO before_hyp FROM hypothesis_transitions;
        first_close := close_startup_refusal(
            '07000000-0000-7000-8000-000000000002', 'pre_spawn',
            '0.2.132', '2.1.224', refusal);
        second_close := close_startup_refusal(
            '07000000-0000-7000-8000-000000000002', 'pre_spawn',
            '0.2.132', '2.1.224', refusal);

        SELECT first_close AND NOT second_close
          AND EXISTS (
                SELECT 1 FROM agent_runs
                 WHERE id = '07000000-0000-7000-8000-000000000002'
                   AND finished_at IS NOT NULL AND stop_reason = 'refusal'
                   AND result IS NULL)
          AND EXISTS (
                SELECT 1 FROM tasks
                 WHERE id = '07000000-0000-7000-8000-000000000001'
                   AND status = 'pending' AND attempts = 0
                   AND claimed_at IS NULL AND lease_expires_at IS NULL
                   AND finished_at IS NULL AND priority IS NULL
                   AND pending_decision_id IS NULL)
          AND EXISTS (
                SELECT 1 FROM identity_leases
                 WHERE id = '07000000-0000-7000-8000-000000000004'
                   AND released_at IS NOT NULL)
          AND EXISTS (
                SELECT 1 FROM agent_sessions
                 WHERE id = '07000000-0000-7000-8000-000000000003'
                   AND unbound_at IS NOT NULL)
          AND NOT EXISTS (
                SELECT 1 FROM agent_sessions
                 WHERE agent_run_id = '07000000-0000-7000-8000-000000000002'
                   AND unbound_at IS NULL)
          AND (SELECT count(*) FROM events
                WHERE type = 'startup.refused'
                  AND agent_run_id = '07000000-0000-7000-8000-000000000002') = 1
          AND EXISTS (
                SELECT 1 FROM events
                 WHERE type = 'startup.refused' AND actor_kind = 'runtime'
                   AND program_id = '11111111-1111-7111-8111-111111111111'
                   AND agent_run_id = '07000000-0000-7000-8000-000000000002'
                   AND task_id = '07000000-0000-7000-8000-000000000001'
                   AND payload = jsonb_build_object(
                       'schema_version', 1, 'phase', 'pre_spawn',
                       'sdk_version', '0.2.132', 'cli_version', '2.1.224',
                       'violations', refusal))
          AND NOT EXISTS (
                SELECT 1 FROM tool_runs
                 WHERE agent_run_id = '07000000-0000-7000-8000-000000000002')
          AND NOT EXISTS (
                SELECT 1 FROM receipts r JOIN tool_runs tr ON tr.id = r.tool_run_id
                 WHERE tr.agent_run_id = '07000000-0000-7000-8000-000000000002')
          AND (SELECT count(*) FROM hypothesis_transitions) = before_hyp
          INTO ok;
        note := CASE WHEN ok THEN 'one transaction closes, unbinds and releases exactly once'
                     ELSE 'one or more lifecycle assertions were false' END;
        RAISE EXCEPTION 'L_ROLLBACK';
    EXCEPTION WHEN OTHERS THEN
        IF SQLERRM <> 'L_ROLLBACK' THEN ok := false; note := left(SQLERRM, 240); END IF;
    END;
    INSERT INTO t.results(id, kind, pass, note)
    VALUES('L01 startup refusal cleanup is atomic and idempotent', 'startup', ok, note);
END $outer$;

DO $outer$
DECLARE ok boolean := false; note text := 'init refusal failed'; rid uuid;
BEGIN
    BEGIN
        INSERT INTO tasks
            (id, program_id, label, kind, subject_entity_id, status, attempts,
             claimed_at, lease_expires_at)
        VALUES
            ('07000000-0000-7000-8000-000000000011',
             '11111111-1111-7111-8111-111111111111', 'T_INIT_REFUSAL',
             'recon', 'aaaaaaaa-0000-7000-8000-000000000005', 'claimed', 1,
             now(), now() + interval '30 minutes');
        INSERT INTO agent_runs
            (id, program_id, label, task_id, role, model, effort, mission_packet)
        VALUES
            ('07000000-0000-7000-8000-000000000012',
             '11111111-1111-7111-8111-111111111111', 'AR_INIT_REFUSAL',
             '07000000-0000-7000-8000-000000000011', 'recon',
             'claude-opus-5', 'high', '{}');
        PERFORM close_startup_refusal(
            '07000000-0000-7000-8000-000000000012', 'init', NULL, NULL,
            '[{"code":"auth_source_unexpected","vector":null,"source":"init:apiKeySource","effect":"unverifiable"}]');
        SELECT id INTO rid FROM events
         WHERE type = 'startup.refused'
           AND agent_run_id = '07000000-0000-7000-8000-000000000012';
        SELECT rid IS NOT NULL
          AND (SELECT payload FROM events WHERE id = rid
                AND program_id = '11111111-1111-7111-8111-111111111111') =
              '{"schema_version":1,"phase":"init","sdk_version":null,"cli_version":null,"violations":[{"code":"auth_source_unexpected","vector":null,"source":"init:apiKeySource","effect":"unverifiable"}]}'::jsonb
          AND EXISTS (SELECT 1 FROM tasks
                       WHERE id = '07000000-0000-7000-8000-000000000011'
                         AND status = 'pending' AND attempts = 0)
          AND EXISTS (SELECT 1 FROM agent_runs
                       WHERE id = '07000000-0000-7000-8000-000000000012'
                         AND stop_reason = 'refusal' AND result IS NULL)
          INTO ok;
        note := CASE WHEN ok THEN 'init uses the same durable transaction and exact payload'
                     ELSE 'init state or payload differed' END;
        RAISE EXCEPTION 'L_ROLLBACK';
    EXCEPTION WHEN OTHERS THEN
        IF SQLERRM <> 'L_ROLLBACK' THEN ok := false; note := left(SQLERRM, 240); END IF;
    END;
    INSERT INTO t.results(id, kind, pass, note)
    VALUES('L02 init refusal uses the common lifecycle', 'startup', ok, note);
END $outer$;

SELECT t.expect_true('L03 unknown runs emit no refusal event',
  $$SELECT NOT close_startup_refusal(
       '07000000-0000-7000-8000-000000000099', 'pre_spawn', NULL, NULL,
       '[{"code":"unmeasured_runtime","vector":null,"source":"runtime:sdk-cli","effect":"unverifiable"}]')
     AND NOT EXISTS (SELECT 1 FROM events
                      WHERE agent_run_id = '07000000-0000-7000-8000-000000000099')$$);

SELECT t.expect_raise('L04 malformed refusal payloads fail closed',
  $$SELECT close_startup_refusal(
       '07000000-0000-7000-8000-000000000099', 'pre_spawn', NULL, NULL, '[]')$$,
  'invalid startup refusal payload');

SELECT t.expect_true('L05 refusal catalogue and privilege are narrow',
  $$SELECT EXISTS (SELECT 1 FROM event_types
                    WHERE id = 'startup.refused' AND family = 'occurrence'
                      AND subject_table IS NULL)
       AND EXISTS (SELECT 1 FROM event_types
                    WHERE id = 'agent.refused' AND family = 'occurrence')
       AND has_function_privilege(
             'rk2_runtime', 'close_startup_refusal(uuid,text,text,text,jsonb)', 'EXECUTE')
       AND NOT has_function_privilege(
             'rk2_proxy', 'close_startup_refusal(uuid,text,text,text,jsonb)', 'EXECUTE')$$);

RESET ROLE;
