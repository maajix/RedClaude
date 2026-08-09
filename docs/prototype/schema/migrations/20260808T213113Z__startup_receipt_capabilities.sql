-- Ticket 02: add the capability-backed receipt path beside legacy writes.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

ALTER TABLE tool_runs ADD COLUMN egress_token_expires_at timestamptz;

-- Tokens minted by the earlier prototype had no lifetime. Invalidate any that
-- survived deployment instead of silently treating them as capabilities.
SELECT set_config('app.actor_kind', 'runtime', true);
UPDATE tool_runs SET egress_token_sha256 = NULL
 WHERE egress_token_sha256 IS NOT NULL;

ALTER TABLE tool_runs DROP CONSTRAINT tool_runs_egress_token_ck;
ALTER TABLE tool_runs ADD CONSTRAINT tool_runs_egress_token_ck CHECK (
    (egress_token_sha256 IS NULL) = (egress_token_expires_at IS NULL)
    AND (egress_token_sha256 IS NULL OR
         (status = 'running' AND decision = 'allow'
          AND egress_token_sha256 ~ '^[0-9a-f]{64}$'))
);

-- Gate output and live capability state are database-owned. Runtime callers
-- may close a run (which revokes its capability) but may not grant themselves
-- an allow decision or install a digest.
CREATE FUNCTION guard_tool_run_authorization() RETURNS trigger
LANGUAGE plpgsql AS $fn$
BEGIN
    IF NOT pg_has_role(current_user, 'rk2_owner', 'USAGE') THEN
        IF TG_OP = 'INSERT' THEN
            IF NEW.risk_class IS NOT NULL OR NEW.decision IS NOT NULL
               OR NEW.decision_reason IS NOT NULL
               OR NEW.egress_token_sha256 IS NOT NULL
               OR NEW.egress_token_expires_at IS NOT NULL THEN
                RAISE EXCEPTION 'tool-run authorization fields are database-owned'
                    USING ERRCODE = '42501';
            END IF;
        ELSIF NEW.risk_class IS DISTINCT FROM OLD.risk_class
           OR NEW.decision IS DISTINCT FROM OLD.decision
           OR NEW.decision_reason IS DISTINCT FROM OLD.decision_reason
           OR ((NEW.egress_token_sha256 IS DISTINCT FROM OLD.egress_token_sha256
                OR NEW.egress_token_expires_at IS DISTINCT FROM OLD.egress_token_expires_at)
               AND NEW.egress_token_sha256 IS NOT NULL) THEN
            RAISE EXCEPTION 'tool-run authorization fields are database-owned'
                USING ERRCODE = '42501';
        END IF;
    END IF;

    IF NEW.status <> 'running' OR NEW.decision IS DISTINCT FROM 'allow'
       OR NEW.egress_token_sha256 IS NULL THEN
        NEW.egress_token_sha256 := NULL;
        NEW.egress_token_expires_at := NULL;
    END IF;
    RETURN NEW;
END $fn$;

REVOKE ALL ON FUNCTION guard_tool_run_authorization() FROM PUBLIC;

CREATE TRIGGER tool_runs_authorization_owned
    BEFORE INSERT OR UPDATE ON tool_runs
    FOR EACH ROW EXECUTE FUNCTION guard_tool_run_authorization();
ALTER TABLE tool_runs ENABLE ALWAYS TRIGGER tool_runs_authorization_owned;


CREATE FUNCTION authorize_tool_run(p_tool_run_id uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE
    v_run        tool_runs%ROWTYPE;
    v_gate       jsonb;
    v_capability text;
    v_expires_at timestamptz;
BEGIN
    SELECT tr.* INTO v_run
      FROM tool_runs tr
      JOIN agent_runs ar
        ON ar.id = tr.agent_run_id AND ar.program_id = tr.program_id
      LEFT JOIN tasks t
        ON t.id = tr.task_id AND t.program_id = tr.program_id
     WHERE tr.id = p_tool_run_id
       AND tr.program_id = rk2_program()
       AND tr.status = 'running'
       AND ar.finished_at IS NULL
       AND ((tr.task_id IS NULL AND ar.task_id IS NULL)
            OR (tr.task_id IS NOT NULL AND ar.task_id = tr.task_id
                AND t.status IN ('claimed', 'running')
                AND t.lease_expires_at > clock_timestamp()))
     FOR UPDATE OF tr;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'tool run is not active in the current program'
            USING ERRCODE = '23514';
    END IF;

    v_gate := gate_tool_call(p_tool_run_id);
    IF v_gate ->> 'decision' IS NULL
       OR v_gate ->> 'decision' NOT IN ('allow', 'deny', 'ask') THEN
        RAISE EXCEPTION 'tool gate returned no valid decision'
            USING ERRCODE = '23514';
    END IF;

    IF v_gate ->> 'decision' = 'allow' THEN
        v_capability := encode(gen_random_bytes(32), 'hex');
        v_expires_at := clock_timestamp() + interval '5 minutes';
    END IF;

    PERFORM set_config('app.actor_kind', 'runtime', true);
    UPDATE tool_runs
       SET risk_class = v_gate ->> 'risk_class',
           decision = v_gate ->> 'decision',
           decision_reason = coalesce(v_gate ->> 'rule', 'gate'),
           egress_token_sha256 = CASE WHEN v_capability IS NULL THEN NULL
               ELSE encode(digest(v_capability, 'sha256'), 'hex') END,
           egress_token_expires_at = v_expires_at
     WHERE id = v_run.id;

    RETURN v_gate || jsonb_build_object(
        'capability', v_capability,
        'capability_expires_at', v_expires_at);
END $fn$;

REVOKE ALL ON FUNCTION authorize_tool_run(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION authorize_tool_run(uuid) TO rk2_runtime;


CREATE FUNCTION resolve_egress_capability(p_capability text)
RETURNS TABLE (
    program_id uuid,
    tool_run_id uuid,
    agent_run_id uuid,
    task_id uuid,
    decision text,
    capability_expires_at timestamptz
)
LANGUAGE sql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
    SELECT tr.program_id, tr.id, tr.agent_run_id, tr.task_id, tr.decision,
           tr.egress_token_expires_at
      FROM tool_runs tr
      JOIN agent_runs ar
        ON ar.id = tr.agent_run_id AND ar.program_id = tr.program_id
      LEFT JOIN tasks t
        ON t.id = tr.task_id AND t.program_id = tr.program_id
     WHERE p_capability IS NOT NULL
       AND tr.program_id = rk2_program()
       AND tr.egress_token_sha256 = encode(digest(p_capability, 'sha256'), 'hex')
       AND tr.egress_token_expires_at > clock_timestamp()
       AND tr.status = 'running'
       AND tr.decision = 'allow'
       AND ar.finished_at IS NULL
       AND ((tr.task_id IS NULL AND ar.task_id IS NULL)
            OR (tr.task_id IS NOT NULL AND ar.task_id = tr.task_id
                AND t.status IN ('claimed', 'running')
                AND t.lease_expires_at > clock_timestamp()));
$fn$;

REVOKE ALL ON FUNCTION resolve_egress_capability(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION resolve_egress_capability(text) TO rk2_runtime;


CREATE FUNCTION write_allowed_receipt(p_capability text, p_receipt jsonb)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE
    v_auth          record;
    v_receipt       receipts%ROWTYPE;
    v_scope_version integer;
    v_id            uuid;
BEGIN
    IF p_capability IS NULL
       OR coalesce(jsonb_typeof(p_receipt), 'null') <> 'object' THEN
        RAISE EXCEPTION 'egress capability refused' USING ERRCODE = '23514';
    END IF;
    IF position(p_capability IN p_receipt::text) > 0 THEN
        RAISE EXCEPTION 'receipt payload contains protected capability'
            USING ERRCODE = '23514';
    END IF;

    SELECT * INTO v_auth FROM resolve_egress_capability(p_capability);
    IF NOT FOUND THEN
        RAISE EXCEPTION 'egress capability refused' USING ERRCODE = '23514';
    END IF;
    SELECT scope_version INTO v_scope_version
      FROM programs WHERE id = v_auth.program_id;

    v_receipt := jsonb_populate_record(NULL::receipts, p_receipt);
    v_receipt.id := uuidv7();
    v_receipt.program_id := v_auth.program_id;
    v_receipt.label := '';
    v_receipt.tool_run_id := v_auth.tool_run_id;
    v_receipt.lane := 'agent';
    v_receipt.decision := 'allowed';
    v_receipt.scope_version := v_scope_version;
    v_receipt.ts_arrival := coalesce(v_receipt.ts_arrival, clock_timestamp());
    v_receipt.intercepted := coalesce(v_receipt.intercepted, true);

    PERFORM set_config('app.actor_kind', 'runtime', true);
    INSERT INTO receipts (
        id, program_id, label, tool_run_id, lane, decision, reason,
        identity_entity_id, method, scheme, host, port, path, query_sha256,
        pinned_ips, status_code, ts_arrival, ts_egress, waited_ms,
        request_agent_sha, request_wire_sha, response_agent_sha,
        response_wire_sha, notes, scope_version, scope_class, intercepted,
        alpn_pin_mode, agent_tls_version, agent_cipher, agent_alpn,
        agent_cert_sha256, agent_cert_issuer, agent_cert_subject,
        agent_cert_not_after, wire_tls_version, wire_cipher, wire_alpn,
        wire_cert_sha256, wire_cert_issuer, wire_cert_subject,
        wire_cert_not_after, wire_sni, wire_chain_verified,
        wire_hostname_verified, interception_ca_id
    ) VALUES (
        v_receipt.id, v_receipt.program_id, v_receipt.label,
        v_receipt.tool_run_id, v_receipt.lane, v_receipt.decision,
        v_receipt.reason, v_receipt.identity_entity_id, v_receipt.method,
        v_receipt.scheme, v_receipt.host, v_receipt.port, v_receipt.path,
        v_receipt.query_sha256, v_receipt.pinned_ips, v_receipt.status_code,
        v_receipt.ts_arrival, v_receipt.ts_egress, v_receipt.waited_ms,
        v_receipt.request_agent_sha, v_receipt.request_wire_sha,
        v_receipt.response_agent_sha, v_receipt.response_wire_sha,
        v_receipt.notes, v_receipt.scope_version, v_receipt.scope_class,
        v_receipt.intercepted, v_receipt.alpn_pin_mode,
        v_receipt.agent_tls_version, v_receipt.agent_cipher,
        v_receipt.agent_alpn, v_receipt.agent_cert_sha256,
        v_receipt.agent_cert_issuer, v_receipt.agent_cert_subject,
        v_receipt.agent_cert_not_after, v_receipt.wire_tls_version,
        v_receipt.wire_cipher, v_receipt.wire_alpn,
        v_receipt.wire_cert_sha256, v_receipt.wire_cert_issuer,
        v_receipt.wire_cert_subject, v_receipt.wire_cert_not_after,
        v_receipt.wire_sni, v_receipt.wire_chain_verified,
        v_receipt.wire_hostname_verified, v_receipt.interception_ca_id
    )
    RETURNING id INTO v_id;
    RETURN v_id;
END $fn$;

REVOKE ALL ON FUNCTION write_allowed_receipt(text, jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION write_allowed_receipt(text, jsonb) TO rk2_runtime;


-- Preserve the established parking transaction, but put its protected update
-- behind the same active-run authorization rather than duplicating its body.
ALTER FUNCTION park_for_human(uuid, interval)
    RENAME TO park_authorized_tool_run;
ALTER FUNCTION park_authorized_tool_run(uuid, interval) SECURITY DEFINER;
ALTER FUNCTION park_authorized_tool_run(uuid, interval)
    SET search_path = pg_catalog, public;
REVOKE ALL ON FUNCTION park_authorized_tool_run(uuid, interval) FROM PUBLIC;
REVOKE ALL ON FUNCTION park_authorized_tool_run(uuid, interval) FROM rk2_runtime;

CREATE FUNCTION park_for_human(
    p_tool_run_id uuid,
    p_ttl interval DEFAULT interval '4 hours'
) RETURNS text LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
BEGIN
    PERFORM authorize_tool_run(p_tool_run_id);
    RETURN park_authorized_tool_run(p_tool_run_id, p_ttl);
END $fn$;

REVOKE ALL ON FUNCTION park_for_human(uuid, interval) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION park_for_human(uuid, interval) TO rk2_runtime;

UPDATE event_table_config
   SET ignored_columns = array_append(ignored_columns, 'egress_token_expires_at')
 WHERE table_name = 'tool_runs'
   AND NOT ('egress_token_expires_at' = ANY (ignored_columns));

COMMENT ON FUNCTION authorize_tool_run(uuid) IS
  'Evaluates gate_tool_call, stamps its decision and returns a short-lived plaintext capability only for an active allow. Canonical state stores only SHA-256.';
COMMENT ON FUNCTION resolve_egress_capability(text) IS
  'Resolves a plaintext capability only while its program, tool run, parent run and optional task lease remain active.';
COMMENT ON FUNCTION write_allowed_receipt(text, jsonb) IS
  'Writes an allowed agent receipt with program, tool_run_id and decision derived from a live capability.';
