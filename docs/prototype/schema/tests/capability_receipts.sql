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

RESET ROLE;

DO $$
DECLARE ok boolean; note text;
BEGIN
    SELECT NOT has_table_privilege('rk2_proxy','receipts','INSERT')
       AND has_function_privilege('rk2_proxy','write_allowed_receipt(text,jsonb)','EXECUTE')
       AND has_function_privilege('rk2_proxy','write_blocked_receipt(uuid,jsonb,text)','EXECUTE')
       AND EXISTS (SELECT 1 FROM pg_trigger WHERE tgrelid='receipts'::regclass
                    AND tgname='receipts_allowed_capability' AND tgenabled='A')
      INTO ok;
    note := CASE WHEN ok THEN 'proxy is writer-only and the invariant is ENABLE ALWAYS'
                 ELSE 'proxy grants or invariant trigger are wrong' END;
    INSERT INTO t.results (id, kind, pass, note)
    VALUES ('K05 proxy uses only fenced receipt writers', 'capability', ok, note);
END $$;

DO $$
DECLARE ok boolean := false; note text := 'owner loaded the hole-open receipt';
BEGIN
    BEGIN
        INSERT INTO tool_runs(id,program_id,label,tool,status)
        VALUES('02e00000-0000-7000-8000-000000000001',
               '11111111-1111-7111-8111-111111111111','TR_HOLE_OWNER',
               'mcp__rk2__state_read','running');
        BEGIN
            INSERT INTO receipts(program_id,lane,decision,reason,ts_arrival,
                                 tool_run_id,scope_version,scope_class)
            VALUES('11111111-1111-7111-8111-111111111111','agent','allowed',
                   'old fixture hole',now(),
                   '02e00000-0000-7000-8000-000000000001',1,'target');
        EXCEPTION WHEN SQLSTATE '23514' THEN
            ok := position('live authorized capability' in SQLERRM) > 0;
            note := CASE WHEN ok THEN 'database owner cannot load an undecided allowed receipt'
                         ELSE left(SQLERRM,240) END;
        END;
        RAISE EXCEPTION 'K_ROLLBACK';
    EXCEPTION WHEN OTHERS THEN
        IF SQLERRM <> 'K_ROLLBACK' THEN ok := false; note := left(SQLERRM,240); END IF;
    END;
    INSERT INTO t.results(id,kind,pass,note)
    VALUES('K06 owner hole-open seed is refused','capability',ok,note);
END $$;

DO $$
DECLARE no_run boolean := false; fake boolean := false; note text;
BEGIN
    BEGIN
        INSERT INTO receipts(program_id,lane,decision,reason,ts_arrival,
                             scope_version,scope_class)
        VALUES('11111111-1111-7111-8111-111111111111','agent','allowed',
               'no tool',now(),1,'target');
    EXCEPTION WHEN SQLSTATE '23514' THEN no_run := true;
    END;
    BEGIN
        PERFORM write_allowed_receipt(repeat('0',64), '{"scope_class":"target"}');
    EXCEPTION WHEN SQLSTATE '23514' THEN fake := true;
    END;
    note := CASE WHEN no_run AND fake THEN 'no-tool and fabricated-capability paths refused'
                 ELSE 'one raw bypass was accepted' END;
    INSERT INTO t.results(id,kind,pass,note)
    VALUES('K07 raw allowed bypasses fail','capability',no_run AND fake,note);
END $$;

DO $$
DECLARE rid uuid; ok boolean := false; note text := 'blocked writer failed';
BEGIN
    BEGIN
        rid := write_blocked_receipt(
            '11111111-1111-7111-8111-111111111111',
            '{"lane":"agent","decision":"allowed","tool_run_id":"ffffffff-ffff-7fff-8fff-ffffffffffff","reason":"fixture refusal","method":"GET","host":"acme.test","path":"/blocked","status_code":407,"scope_class":"denied"}');
        ok := EXISTS (SELECT 1 FROM receipts WHERE id=rid AND lane='agent'
                      AND decision='blocked' AND tool_run_id IS NULL);
        note := CASE WHEN ok THEN 'blocked writer forced blocked authority fields'
                     ELSE 'blocked writer accepted caller authority' END;
        RAISE EXCEPTION 'K_ROLLBACK';
    EXCEPTION WHEN OTHERS THEN
        IF SQLERRM <> 'K_ROLLBACK' THEN ok := false; note := left(SQLERRM,240); END IF;
    END;
    INSERT INTO t.results(id,kind,pass,note)
    VALUES('K08 blocked writer cannot create allowed','capability',ok,note);
END $$;

DO $$
DECLARE rid uuid; ok boolean := false; note text := 'control refusal writer failed';
BEGIN
    BEGIN
        rid := write_blocked_receipt(
            '11111111-1111-7111-8111-111111111111',
            '{"lane":"control","decision":"allowed","reason":"create_api_key refused","method":"POST","host":"api.anthropic.test","path":"/api/oauth/claude_cli/create_api_key","status_code":403,"scope_class":"target"}');
        ok := EXISTS (SELECT 1 FROM receipts WHERE id=rid AND lane='control'
                      AND decision='blocked' AND tool_run_id IS NULL
                      AND scope_version IS NULL AND scope_class='control_plane');
        note := CASE WHEN ok THEN 'control refusal fields were derived, not accepted'
                     ELSE 'control caller authority survived' END;
        RAISE EXCEPTION 'K_ROLLBACK';
    EXCEPTION WHEN OTHERS THEN
        IF SQLERRM <> 'K_ROLLBACK' THEN ok := false; note := left(SQLERRM,240); END IF;
    END;
    INSERT INTO t.results(id,kind,pass,note)
    VALUES('K10 control refusal cannot become target evidence','capability',ok,note);
END $$;

DO $$
DECLARE grants_red boolean; trigger_red boolean; writer_red boolean; ok boolean;
BEGIN
    EXECUTE 'GRANT INSERT ON receipts TO rk2_proxy';
    SELECT EXISTS (SELECT 1 FROM check_capability_receipt_fence()
                    WHERE problem='proxy_can_insert_receipts') INTO grants_red;
    EXECUTE 'REVOKE INSERT ON receipts FROM rk2_proxy';

    EXECUTE 'ALTER TABLE receipts DISABLE TRIGGER receipts_allowed_capability';
    SELECT EXISTS (SELECT 1 FROM check_capability_receipt_fence()
                    WHERE problem='allowed_receipt_trigger_missing') INTO trigger_red;
    EXECUTE 'ALTER TABLE receipts ENABLE ALWAYS TRIGGER receipts_allowed_capability';

    EXECUTE 'REVOKE EXECUTE ON FUNCTION write_blocked_receipt(uuid,jsonb,text) FROM rk2_proxy';
    SELECT EXISTS (SELECT 1 FROM check_capability_receipt_fence()
                    WHERE problem='proxy_writer_missing') INTO writer_red;
    EXECUTE 'GRANT EXECUTE ON FUNCTION write_blocked_receipt(uuid,jsonb,text) TO rk2_proxy';

    ok := grants_red AND trigger_red AND writer_red
          AND NOT EXISTS (SELECT 1 FROM check_capability_receipt_fence());
    INSERT INTO t.results(id,kind,pass,note)
    VALUES('K09 receipt fence negative controls turn red','capability',ok,
           CASE WHEN ok THEN 'privilege, trigger and writer controls each detected drift'
                ELSE 'a fence claim had no working negative control' END);
END $$;

SET ROLE rk2_runtime;

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
