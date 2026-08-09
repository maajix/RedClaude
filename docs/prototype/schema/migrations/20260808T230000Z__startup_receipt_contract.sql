-- Ticket 06: remove raw allowed-receipt writes from the serving role.

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rk2_proxy') THEN
        RAISE EXCEPTION 'role rk2_proxy missing; run migrate.sh provision';
    END IF;
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO rk2_proxy', current_database());
END $$;
GRANT USAGE ON SCHEMA public TO rk2_proxy;
REVOKE ALL ON receipts FROM rk2_proxy;


CREATE FUNCTION register_proxy_artifacts(
    p_capability text,
    p_request_agent_sha text,
    p_request_wire_sha text,
    p_response_agent_sha text,
    p_response_wire_sha text
) RETURNS void LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM resolve_egress_capability(p_capability)) THEN
        RAISE EXCEPTION 'egress capability refused' USING ERRCODE = '23514';
    END IF;
    INSERT INTO artifacts (sha256, byte_size, content_type, visibility, encrypted)
    SELECT v.sha, 0, NULL, v.visibility, v.encrypted
      FROM (VALUES
        (p_request_agent_sha,  'agent_visible', false),
        (p_request_wire_sha,   'credential_bearing', true),
        (p_response_agent_sha, 'agent_visible', false),
        (p_response_wire_sha,  'credential_bearing', true)
      ) AS v(sha, visibility, encrypted)
     WHERE v.sha IS NOT NULL
    ON CONFLICT (sha256) DO NOTHING;
END $fn$;

REVOKE ALL ON FUNCTION register_proxy_artifacts(text,text,text,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION register_proxy_artifacts(text,text,text,text,text) TO rk2_proxy;
GRANT EXECUTE ON FUNCTION authorize_egress_request(text,text,text,text),
                          write_allowed_receipt(text,jsonb) TO rk2_proxy;


CREATE FUNCTION write_blocked_receipt(
    p_program uuid,
    p_receipt jsonb,
    p_capability text DEFAULT NULL
) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE
    v_receipt receipts%ROWTYPE;
    v_id      uuid;
    v_tool_run_id uuid;
    v_lane text;
BEGIN
    IF p_program IS DISTINCT FROM rk2_program()
       OR coalesce(jsonb_typeof(p_receipt), 'null') <> 'object' THEN
        RAISE EXCEPTION 'blocked receipt refused' USING ERRCODE = '23514';
    END IF;
    IF p_capability IS NOT NULL
       AND position(p_capability IN p_receipt::text) > 0 THEN
        RAISE EXCEPTION 'receipt payload contains protected capability'
            USING ERRCODE = '23514';
    END IF;
    IF p_capability IS NOT NULL THEN
        SELECT a.tool_run_id INTO v_tool_run_id
          FROM resolve_egress_capability(p_capability) a;
    END IF;

    v_receipt := jsonb_populate_record(NULL::receipts, p_receipt);
    v_id := uuidv7();
    v_receipt.id := v_id;
    v_receipt.program_id := p_program;
    v_receipt.label := '';
    v_receipt.tool_run_id := v_tool_run_id;
    v_lane := CASE WHEN p_capability IS NULL
                        AND p_receipt ->> 'lane' = 'control'
                   THEN 'control' ELSE 'agent' END;
    v_receipt.lane := v_lane;
    v_receipt.decision := 'blocked';
    v_receipt.scope_version := CASE WHEN v_lane = 'control' THEN NULL
        ELSE (SELECT scope_version FROM programs WHERE id=p_program) END;
    v_receipt.scope_class := CASE WHEN v_lane = 'control' THEN 'control_plane'
        ELSE coalesce(v_receipt.scope_class, 'denied') END;
    v_receipt.ts_arrival := coalesce(v_receipt.ts_arrival, clock_timestamp());
    v_receipt.intercepted := coalesce(v_receipt.intercepted, true);

    PERFORM set_config('app.actor_kind', 'runtime', true);
    INSERT INTO receipts (
        id, program_id, label, tool_run_id, lane, decision, reason,
        identity_entity_id, method, scheme, host, port, path, query_sha256,
        pinned_ips, status_code, ts_arrival, ts_egress, waited_ms, notes,
        scope_version, scope_class, intercepted
    ) VALUES (
        v_receipt.id, v_receipt.program_id, v_receipt.label,
        v_receipt.tool_run_id, v_receipt.lane, v_receipt.decision,
        coalesce(v_receipt.reason, 'capability refused'),
        v_receipt.identity_entity_id, v_receipt.method, v_receipt.scheme,
        v_receipt.host, v_receipt.port, v_receipt.path,
        v_receipt.query_sha256, v_receipt.pinned_ips, v_receipt.status_code,
        v_receipt.ts_arrival, v_receipt.ts_egress, v_receipt.waited_ms,
        v_receipt.notes, v_receipt.scope_version, v_receipt.scope_class,
        v_receipt.intercepted
    );
    RETURN v_id;
END $fn$;

REVOKE ALL ON FUNCTION write_blocked_receipt(uuid,jsonb,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION write_blocked_receipt(uuid,jsonb,text) TO rk2_proxy;


CREATE FUNCTION enforce_allowed_receipt_capability() RETURNS trigger
LANGUAGE plpgsql AS $fn$
BEGIN
    IF NEW.lane = 'agent' AND NEW.decision = 'allowed'
       AND NOT EXISTS (
           SELECT 1
             FROM tool_runs tr
             JOIN agent_runs ar
               ON ar.id = tr.agent_run_id AND ar.program_id = tr.program_id
             LEFT JOIN tasks t
               ON t.id = tr.task_id AND t.program_id = tr.program_id
            WHERE tr.id = NEW.tool_run_id
              AND tr.program_id = NEW.program_id
              AND tr.status = 'running'
              AND tr.decision = 'allow'
              AND tr.egress_token_sha256 IS NOT NULL
              AND tr.egress_token_expires_at > clock_timestamp()
              AND ar.finished_at IS NULL
              AND ((tr.task_id IS NULL AND ar.task_id IS NULL)
                   OR (tr.task_id IS NOT NULL AND ar.task_id = tr.task_id
                       AND t.status IN ('claimed', 'running')
                       AND t.lease_expires_at > clock_timestamp()))
       ) THEN
        RAISE EXCEPTION 'allowed agent receipt lacks a live authorized capability'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $fn$;

REVOKE ALL ON FUNCTION enforce_allowed_receipt_capability() FROM PUBLIC;
CREATE TRIGGER receipts_allowed_capability
    BEFORE INSERT OR UPDATE ON receipts
    FOR EACH ROW EXECUTE FUNCTION enforce_allowed_receipt_capability();
ALTER TABLE receipts ENABLE ALWAYS TRIGGER receipts_allowed_capability;


CREATE FUNCTION check_capability_receipt_fence()
RETURNS TABLE(problem text, detail text) LANGUAGE sql STABLE AS $fn$
    SELECT 'proxy_can_insert_receipts', 'rk2_proxy has direct INSERT'
     WHERE has_table_privilege('rk2_proxy', 'receipts', 'INSERT')
    UNION ALL
    SELECT 'allowed_receipt_trigger_missing', 'trigger absent or not ENABLE ALWAYS'
     WHERE NOT EXISTS (
        SELECT 1 FROM pg_trigger
         WHERE tgrelid = 'receipts'::regclass
           AND tgname = 'receipts_allowed_capability' AND tgenabled = 'A')
    UNION ALL
    SELECT 'proxy_writer_missing', 'rk2_proxy cannot execute a required writer'
     WHERE NOT has_function_privilege(
               'rk2_proxy', 'write_allowed_receipt(text,jsonb)', 'EXECUTE')
        OR NOT has_function_privilege(
               'rk2_proxy', 'write_blocked_receipt(uuid,jsonb,text)', 'EXECUTE');
$fn$;

REVOKE ALL ON FUNCTION check_capability_receipt_fence() FROM PUBLIC;

INSERT INTO standing_checks (name, query, owner_ticket, note) VALUES
 ('capability_receipt_fence', 'SELECT * FROM check_capability_receipt_fence()', '57',
  'proxy has writer-only access and allowed agent receipts require a live capability');

ALTER FUNCTION check_role_catalogue() RENAME TO base_role_catalogue;
CREATE FUNCTION check_role_catalogue()
RETURNS TABLE(check_name text, ok boolean, detail text)
LANGUAGE plpgsql STABLE AS $fn$
BEGIN
    RETURN QUERY SELECT * FROM base_role_catalogue();
    RETURN QUERY SELECT 'proxy_role_exists'::text,
        EXISTS (SELECT 1 FROM pg_roles WHERE rolname='rk2_proxy'),
        'role = rk2_proxy'::text;
    RETURN QUERY SELECT 'proxy_is_not_owner_or_human'::text,
        NOT pg_has_role('rk2_proxy','rk2_owner','USAGE')
        AND NOT pg_has_role('rk2_proxy','rk2_human','USAGE'),
        'owner=' || pg_has_role('rk2_proxy','rk2_owner','USAGE')::text
        || ' human=' || pg_has_role('rk2_proxy','rk2_human','USAGE')::text;
END $fn$;
REVOKE ALL ON FUNCTION base_role_catalogue(), check_role_catalogue() FROM PUBLIC;

UPDATE standing_checks
   SET note = 'seven roles, and no model- or proxy-reachable role can become rk2_human'
 WHERE name = 'role_catalogue';

COMMENT ON FUNCTION write_blocked_receipt(uuid,jsonb,text) IS
  'Writes only blocked agent or control receipts; authority fields are derived and a valid capability is used only for agent attribution.';
