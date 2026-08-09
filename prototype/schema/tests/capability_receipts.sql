-- Ticket 02: expansion path for capability-backed allowed receipts.
-- Every case rolls its fixture back and leaves only its boolean result.

GRANT USAGE ON SCHEMA t TO rk2_runtime;
GRANT INSERT ON t.results TO rk2_runtime;
GRANT USAGE ON SEQUENCE t.results_ord_seq TO rk2_runtime;

SET ROLE rk2_runtime;
SELECT set_config('app.actor_kind', 'runtime', false);
SELECT set_config('rk2.program_id', '11111111-1111-7111-8111-111111111111', false);

DO $$
DECLARE
    first_auth jsonb;
    auth       jsonb;
    first_cap  text;
    cap        text;
    receipt_id uuid;
    ok         boolean := false;
    note       text := 'capability path failed';
BEGIN
    BEGIN
        INSERT INTO tasks
            (id, program_id, label, kind, status, claimed_at, lease_expires_at)
        VALUES
            ('02a00000-0000-7000-8000-000000000001',
             '11111111-1111-7111-8111-111111111111', 'T_CAP_ALLOW', 'recon',
             'running', now(), now() + interval '30 minutes');
        INSERT INTO agent_runs
            (id, program_id, label, task_id, role, model, effort, mission_packet)
        VALUES
            ('02a00000-0000-7000-8000-000000000002',
             '11111111-1111-7111-8111-111111111111', 'AR_CAP_ALLOW',
             '02a00000-0000-7000-8000-000000000001', 'recon',
             'claude-opus-5', 'high', '{}');
        INSERT INTO tool_runs
            (id, program_id, label, agent_run_id, task_id, tool, args, status,
             tool_use_id, transport, mcp_server)
        VALUES
            ('02a00000-0000-7000-8000-000000000003',
             '11111111-1111-7111-8111-111111111111', 'TR_CAP_ALLOW',
             '02a00000-0000-7000-8000-000000000002',
             '02a00000-0000-7000-8000-000000000001',
             'mcp__rk2__state_read', '{"view":"scope"}', 'running',
             'toolu_cap_allow', 'mcp', 'rk2');

        first_auth := authorize_tool_run('02a00000-0000-7000-8000-000000000003');
        auth := authorize_tool_run('02a00000-0000-7000-8000-000000000003');
        first_cap := first_auth ->> 'capability';
        cap := auth ->> 'capability';

        receipt_id := write_allowed_receipt(cap, jsonb_build_object(
            'reason', 'capability test', 'method', 'GET', 'scheme', 'https',
            'host', 'acme.test', 'port', 443, 'path', '/api/orders/1',
            'status_code', 200, 'scope_class', 'target',
            'program_id', '22222222-2222-7222-8222-222222222222',
            'tool_run_id', 'ffffffff-ffff-7fff-8fff-ffffffffffff',
            'lane', 'replay', 'decision', 'blocked', 'scope_version', 999));

        PERFORM set_config(
            'rk2.program_id', '22222222-2222-7222-8222-222222222222', false);
        IF EXISTS (SELECT 1 FROM resolve_egress_capability(cap)) THEN
            RAISE EXCEPTION 'cross-program capability resolved';
        END IF;
        BEGIN
            PERFORM write_allowed_receipt(cap, '{"scope_class":"target"}');
            RAISE EXCEPTION 'cross-program writer accepted capability';
        EXCEPTION WHEN SQLSTATE '23514' THEN
            NULL;
        END;
        PERFORM set_config(
            'rk2.program_id', '11111111-1111-7111-8111-111111111111', false);

        ok := auth ->> 'decision' = 'allow'
          AND first_cap <> cap
          AND octet_length(decode(cap, 'hex')) = 32
          AND NOT EXISTS (SELECT 1 FROM resolve_egress_capability(first_cap))
          AND (SELECT tool_run_id FROM resolve_egress_capability(cap)) =
              '02a00000-0000-7000-8000-000000000003'::uuid
          AND EXISTS (
                SELECT 1 FROM tool_runs
                 WHERE id = '02a00000-0000-7000-8000-000000000003'
                   AND decision = 'allow'
                   AND egress_token_sha256 = encode(digest(cap, 'sha256'), 'hex')
                   AND egress_token_sha256 <> cap)
          AND EXISTS (
                SELECT 1 FROM receipts
                 WHERE id = receipt_id
                   AND program_id = '11111111-1111-7111-8111-111111111111'
                   AND tool_run_id = '02a00000-0000-7000-8000-000000000003'
                   AND lane = 'agent' AND decision = 'allowed'
                   AND scope_version = 1 AND method = 'GET'
                   AND host = 'acme.test' AND status_code = 200)
          AND NOT EXISTS (
                SELECT 1 FROM tool_runs
                 WHERE to_jsonb(tool_runs)::text LIKE '%' || cap || '%')
          AND NOT EXISTS (
                SELECT 1 FROM receipts
                 WHERE to_jsonb(receipts)::text LIKE '%' || cap || '%')
          AND NOT EXISTS (
                SELECT 1 FROM events
                 WHERE to_jsonb(events)::text LIKE '%' || cap || '%')
          AND NOT EXISTS (SELECT 1 FROM resolve_egress_capability(NULL))
          AND NOT EXISTS (
                SELECT 1 FROM resolve_egress_capability(repeat('0', 64)));
        note := CASE WHEN ok THEN 'random capability authorizes one derived receipt without persistence'
                     ELSE 'one or more capability assertions were false' END;
        RAISE EXCEPTION 'K_ROLLBACK';
    EXCEPTION WHEN OTHERS THEN
        IF SQLERRM <> 'K_ROLLBACK' THEN
            ok := false;
            note := left(SQLERRM, 240);
        END IF;
    END;
    INSERT INTO t.results (id, kind, pass, note)
    VALUES ('K01 allowed capability writes a derived receipt', 'capability', ok, note);
END $$;

DO $$
DECLARE auth jsonb; ok boolean := false; note text := 'deny path failed';
BEGIN
    BEGIN
        INSERT INTO tasks
            (id, program_id, label, kind, status, claimed_at, lease_expires_at)
        VALUES
            ('02b00000-0000-7000-8000-000000000001',
             '11111111-1111-7111-8111-111111111111', 'T_CAP_DENY', 'recon',
             'running', now(), now() + interval '30 minutes');
        INSERT INTO agent_runs
            (id, program_id, label, task_id, role, model, effort, mission_packet)
        VALUES
            ('02b00000-0000-7000-8000-000000000002',
             '11111111-1111-7111-8111-111111111111', 'AR_CAP_DENY',
             '02b00000-0000-7000-8000-000000000001', 'recon',
             'claude-opus-5', 'high', '{}');
        INSERT INTO tool_runs
            (id, program_id, label, agent_run_id, task_id, tool, status,
             tool_use_id, transport)
        VALUES
            ('02b00000-0000-7000-8000-000000000003',
             '11111111-1111-7111-8111-111111111111', 'TR_CAP_DENY',
             '02b00000-0000-7000-8000-000000000002',
             '02b00000-0000-7000-8000-000000000001',
             'Bash', 'running', 'toolu_cap_deny', 'builtin');
        auth := authorize_tool_run('02b00000-0000-7000-8000-000000000003');
        ok := auth ->> 'decision' = 'deny'
          AND auth ->> 'capability' IS NULL
          AND EXISTS (SELECT 1 FROM tool_runs
                       WHERE id = '02b00000-0000-7000-8000-000000000003'
                         AND decision = 'deny' AND egress_token_sha256 IS NULL);
        note := CASE WHEN ok THEN 'deny is stamped without a capability'
                     ELSE 'deny received a capability or was not stamped' END;
        RAISE EXCEPTION 'K_ROLLBACK';
    EXCEPTION WHEN OTHERS THEN
        IF SQLERRM <> 'K_ROLLBACK' THEN ok := false; note := left(SQLERRM, 240); END IF;
    END;
    INSERT INTO t.results (id, kind, pass, note)
    VALUES ('K02 only allow mints a capability', 'capability', ok, note);
END $$;

DO $$
DECLARE ok boolean := false; note text := 'direct decision write was accepted';
BEGIN
    BEGIN
        INSERT INTO tasks
            (id, program_id, label, kind, status, claimed_at, lease_expires_at)
        VALUES
            ('02c00000-0000-7000-8000-000000000001',
             '11111111-1111-7111-8111-111111111111', 'T_CAP_DIRECT', 'recon',
             'running', now(), now() + interval '30 minutes');
        INSERT INTO agent_runs
            (id, program_id, label, task_id, role, model, effort, mission_packet)
        VALUES
            ('02c00000-0000-7000-8000-000000000002',
             '11111111-1111-7111-8111-111111111111', 'AR_CAP_DIRECT',
             '02c00000-0000-7000-8000-000000000001', 'recon',
             'claude-opus-5', 'high', '{}');
        INSERT INTO tool_runs
            (id, program_id, label, agent_run_id, task_id, tool, status,
             tool_use_id, transport, mcp_server)
        VALUES
            ('02c00000-0000-7000-8000-000000000003',
             '11111111-1111-7111-8111-111111111111', 'TR_CAP_DIRECT',
             '02c00000-0000-7000-8000-000000000002',
             '02c00000-0000-7000-8000-000000000001',
             'mcp__rk2__state_read', 'running', 'toolu_cap_direct', 'mcp', 'rk2');
        BEGIN
            UPDATE tool_runs SET decision = 'allow'
             WHERE id = '02c00000-0000-7000-8000-000000000003';
        EXCEPTION WHEN SQLSTATE '42501' THEN
            ok := position('database-owned' in SQLERRM) > 0;
            note := CASE WHEN ok THEN 'runtime direct write refused' ELSE left(SQLERRM, 240) END;
        END;
        RAISE EXCEPTION 'K_ROLLBACK';
    EXCEPTION WHEN OTHERS THEN
        IF SQLERRM <> 'K_ROLLBACK' THEN ok := false; note := left(SQLERRM, 240); END IF;
    END;
    INSERT INTO t.results (id, kind, pass, note)
    VALUES ('K03 decision fields are database-owned', 'capability', ok, note);
END $$;

RESET ROLE;
SELECT set_config('app.actor_kind', 'runtime', false);
SELECT set_config('rk2.program_id', '11111111-1111-7111-8111-111111111111', false);

DO $$
DECLARE auth jsonb; cap text; ok boolean := false; note text := 'lifecycle check failed';
BEGIN
    BEGIN
        INSERT INTO tasks
            (id, program_id, label, kind, status, claimed_at, lease_expires_at)
        VALUES
            ('02d00000-0000-7000-8000-000000000001',
             '11111111-1111-7111-8111-111111111111', 'T_CAP_LIFE', 'recon',
             'running', now(), now() + interval '30 minutes');
        INSERT INTO agent_runs
            (id, program_id, label, task_id, role, model, effort, mission_packet)
        VALUES
            ('02d00000-0000-7000-8000-000000000002',
             '11111111-1111-7111-8111-111111111111', 'AR_CAP_LIFE',
             '02d00000-0000-7000-8000-000000000001', 'recon',
             'claude-opus-5', 'high', '{}');
        INSERT INTO tool_runs
            (id, program_id, label, agent_run_id, task_id, tool, args, status,
             tool_use_id, transport, mcp_server)
        VALUES
            ('02d00000-0000-7000-8000-000000000003',
             '11111111-1111-7111-8111-111111111111', 'TR_CAP_LIFE',
             '02d00000-0000-7000-8000-000000000002',
             '02d00000-0000-7000-8000-000000000001',
             'mcp__rk2__state_read', '{"view":"scope"}', 'running',
             'toolu_cap_life', 'mcp', 'rk2');

        auth := authorize_tool_run('02d00000-0000-7000-8000-000000000003');
        cap := auth ->> 'capability';
        UPDATE tool_runs SET egress_token_expires_at = now() - interval '1 second'
         WHERE id = '02d00000-0000-7000-8000-000000000003';
        IF EXISTS (SELECT 1 FROM resolve_egress_capability(cap)) THEN
            RAISE EXCEPTION 'expired capability resolved';
        END IF;

        auth := authorize_tool_run('02d00000-0000-7000-8000-000000000003');
        cap := auth ->> 'capability';
        UPDATE agent_runs SET finished_at = now(), stop_reason = 'completed'
         WHERE id = '02d00000-0000-7000-8000-000000000002';
        IF EXISTS (SELECT 1 FROM resolve_egress_capability(cap)) THEN
            RAISE EXCEPTION 'closed parent capability resolved';
        END IF;

        UPDATE agent_runs SET finished_at = NULL, stop_reason = NULL
         WHERE id = '02d00000-0000-7000-8000-000000000002';
        auth := authorize_tool_run('02d00000-0000-7000-8000-000000000003');
        cap := auth ->> 'capability';
        UPDATE tasks SET lease_expires_at = now() - interval '1 second'
         WHERE id = '02d00000-0000-7000-8000-000000000001';
        IF EXISTS (SELECT 1 FROM resolve_egress_capability(cap)) THEN
            RAISE EXCEPTION 'expired task lease capability resolved';
        END IF;

        UPDATE tasks SET lease_expires_at = now() + interval '30 minutes'
         WHERE id = '02d00000-0000-7000-8000-000000000001';
        auth := authorize_tool_run('02d00000-0000-7000-8000-000000000003');
        cap := auth ->> 'capability';
        UPDATE tool_runs SET status = 'success', finished_at = now(),
                             closed_by = 'PostToolUse'
         WHERE id = '02d00000-0000-7000-8000-000000000003';
        ok := NOT EXISTS (SELECT 1 FROM resolve_egress_capability(cap))
          AND EXISTS (SELECT 1 FROM tool_runs
                       WHERE id = '02d00000-0000-7000-8000-000000000003'
                         AND egress_token_sha256 IS NULL
                         AND egress_token_expires_at IS NULL);
        note := CASE WHEN ok THEN 'expiry, parent, lease and terminal state all invalidate'
                     ELSE 'terminal state left a capability active' END;
        RAISE EXCEPTION 'K_ROLLBACK';
    EXCEPTION WHEN OTHERS THEN
        IF SQLERRM <> 'K_ROLLBACK' THEN ok := false; note := left(SQLERRM, 240); END IF;
    END;
    INSERT INTO t.results (id, kind, pass, note)
    VALUES ('K04 capability resolution binds active lifetime', 'capability', ok, note);
END $$;
