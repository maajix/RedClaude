-- PH2-10 criterion 5: credential-bearing response headers are a wire-only
-- view.  The proxy records the redacted bytes the Agent received and seals the
-- exact target response under the installation root key.

CREATE FUNCTION ensure_proxy_wire_keying(
    p_capability text,
    p_salt bytea,
    p_root_check bytea
) RETURNS TABLE(generation integer, salt_hex text, root_check_hex text)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE
    v_program uuid;
BEGIN
    SELECT a.program_id INTO v_program
      FROM resolve_egress_capability(p_capability) a;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'egress capability refused' USING ERRCODE = '23514';
    END IF;

    SELECT k.gen, encode(k.salt, 'hex'), encode(k.root_check, 'hex')
      INTO generation, salt_hex, root_check_hex
      FROM secret_kek k
     WHERE k.retired_at IS NULL
     ORDER BY k.gen DESC LIMIT 1;

    IF FOUND THEN
        RETURN NEXT;
        RETURN;
    END IF;
    IF EXISTS (SELECT 1 FROM secret_kek) THEN
        RAISE EXCEPTION 'every key generation is retired' USING ERRCODE = '23514';
    END IF;
    IF octet_length(p_salt) <> 32 OR octet_length(p_root_check) <> 16 THEN
        RAISE EXCEPTION 'proxy key proposal has the wrong shape' USING ERRCODE = '23514';
    END IF;

    BEGIN
        INSERT INTO secret_kek(gen, salt, root_check)
        VALUES (1, p_salt, p_root_check);
    EXCEPTION WHEN unique_violation THEN
        -- Another live proxy established the same installation generation.
        -- The caller verifies the returned check against its own root before
        -- encrypting anything, so losing this race cannot select a wrong key.
        NULL;
    END;

    SELECT k.gen, encode(k.salt, 'hex'), encode(k.root_check, 'hex')
      INTO generation, salt_hex, root_check_hex
      FROM secret_kek k
     WHERE k.retired_at IS NULL
     ORDER BY k.gen DESC LIMIT 1;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'no active key generation' USING ERRCODE = '23514';
    END IF;
    RETURN NEXT;
END $fn$;

REVOKE ALL ON FUNCTION ensure_proxy_wire_keying(text,bytea,bytea) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION ensure_proxy_wire_keying(text,bytea,bytea) TO rk2_proxy;


CREATE FUNCTION record_proxy_exchange(
    p_capability text,
    p_receipt    jsonb,
    p_artifacts  jsonb,
    p_seals      jsonb
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE
    v_program   uuid;
    v_tool_run  uuid;
    v_id        uuid;
    v_label     text;
    v_named     text[];
    v_problem   text;
    v_wire_n    integer;
BEGIN
    IF p_capability IS NULL
       OR coalesce(jsonb_typeof(p_receipt), 'null') <> 'object'
       OR coalesce(jsonb_typeof(p_artifacts), 'null') <> 'array'
       OR coalesce(jsonb_typeof(p_seals), 'null') <> 'array' THEN
        RAISE EXCEPTION 'proxy exchange refused' USING ERRCODE = '23514';
    END IF;
    IF position(p_capability IN p_artifacts::text) > 0
       OR position(p_capability IN p_seals::text) > 0 THEN
        RAISE EXCEPTION 'artifact payload contains protected capability'
            USING ERRCODE = '23514';
    END IF;

    SELECT a.program_id, a.tool_run_id INTO v_program, v_tool_run
      FROM resolve_egress_capability(p_capability) a;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'egress capability refused' USING ERRCODE = '23514';
    END IF;

    IF EXISTS (
        SELECT 1 FROM jsonb_to_recordset(p_artifacts)
          AS a(sha256 text, byte_size bigint, content_type text)
         WHERE a.sha256 IS NULL OR a.sha256 !~ '^[0-9a-f]{64}$'
            OR a.byte_size IS NULL OR a.byte_size < 0
    ) THEN
        RAISE EXCEPTION 'proxy exchange names an artifact with no hash or no byte count'
            USING ERRCODE = '23514';
    END IF;

    IF EXISTS (
        SELECT 1 FROM jsonb_to_recordset(p_seals)
          AS s(sha256 text, byte_size bigint, content_type text, alg text,
               nonce_hex text, kek_gen integer, ciphertext_sha256 text,
               agent_sha256 text, value_fpr_hex text, field text)
         WHERE s.sha256 IS NULL OR s.sha256 !~ '^[0-9a-f]{64}$'
            OR s.byte_size IS NULL OR s.byte_size < 0
            OR s.alg IS NULL OR s.nonce_hex IS NULL
            OR s.nonce_hex !~ '^[0-9a-f]{64}$'
            OR s.kek_gen IS NULL OR s.kek_gen < 1
            OR s.ciphertext_sha256 IS NULL
            OR s.ciphertext_sha256 !~ '^[0-9a-f]{64}$'
            OR s.agent_sha256 IS NULL OR s.agent_sha256 !~ '^[0-9a-f]{64}$'
            OR s.agent_sha256 = s.sha256
            OR s.value_fpr_hex IS NULL OR s.value_fpr_hex !~ '^[0-9a-f]{8}$'
            OR coalesce(btrim(s.field), '') = ''
            OR NOT EXISTS (SELECT 1 FROM secret_kek k
                            WHERE k.gen = s.kek_gen AND k.retired_at IS NULL)
    ) THEN
        RAISE EXCEPTION 'proxy exchange names an unusable wire seal'
            USING ERRCODE = '23514';
    END IF;

    SELECT count(*) INTO v_wire_n
      FROM (VALUES (nullif(p_receipt ->> 'request_wire_sha', '')),
                   (nullif(p_receipt ->> 'response_wire_sha', ''))) AS w(sha256)
     WHERE w.sha256 IS NOT NULL;
    IF v_wire_n <> jsonb_array_length(p_seals)
       OR (nullif(p_receipt ->> 'request_wire_sha', '') IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM jsonb_to_recordset(p_seals)
              AS s(sha256 text, agent_sha256 text)
             WHERE s.sha256 = p_receipt ->> 'request_wire_sha'
               AND s.agent_sha256 = p_receipt ->> 'request_agent_sha'))
       OR (nullif(p_receipt ->> 'response_wire_sha', '') IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM jsonb_to_recordset(p_seals)
              AS s(sha256 text, agent_sha256 text)
             WHERE s.sha256 = p_receipt ->> 'response_wire_sha'
               AND s.agent_sha256 = p_receipt ->> 'response_agent_sha'))
       OR EXISTS (
            SELECT 1 FROM jsonb_to_recordset(p_seals)
              AS s(sha256 text, agent_sha256 text)
             WHERE NOT (
                 (s.sha256 = p_receipt ->> 'request_wire_sha'
                  AND s.agent_sha256 = p_receipt ->> 'request_agent_sha')
                 OR
                 (s.sha256 = p_receipt ->> 'response_wire_sha'
                  AND s.agent_sha256 = p_receipt ->> 'response_agent_sha')
             )) THEN
        RAISE EXCEPTION 'wire hashes do not describe the sealed transformation pairs'
            USING ERRCODE = '23514';
    END IF;

    PERFORM set_actor('runtime');
    INSERT INTO artifacts(sha256, byte_size, content_type, visibility, encrypted)
    SELECT a.sha256, a.byte_size, a.content_type, 'agent_visible', false
      FROM jsonb_to_recordset(p_artifacts)
        AS a(sha256 text, byte_size bigint, content_type text)
    ON CONFLICT (sha256) DO NOTHING;

    SELECT string_agg(a.sha256 || ' (' || d.detail || ')', '; ')
      INTO v_problem
      FROM jsonb_to_recordset(p_artifacts)
        AS a(sha256 text, byte_size bigint, content_type text)
      LEFT JOIN artifacts x ON x.sha256 = a.sha256
      CROSS JOIN LATERAL (SELECT CASE
          WHEN x.sha256 IS NULL THEN 'not registered'
          WHEN x.byte_size <> a.byte_size THEN 'registered with another length'
          WHEN x.visibility <> 'agent_visible' OR x.encrypted THEN 'not agent-visible'
          WHEN x.purged_at IS NOT NULL THEN 'purged'
      END AS detail) d
     WHERE d.detail IS NOT NULL;
    IF v_problem IS NOT NULL THEN
        RAISE EXCEPTION 'proxy exchange names artifacts it did not store: %', v_problem
            USING ERRCODE = '23514';
    END IF;

    SELECT array_agg(a.sha256) INTO v_named
      FROM jsonb_to_recordset(p_artifacts)
        AS a(sha256 text, byte_size bigint, content_type text);
    IF nullif(p_receipt ->> 'request_agent_sha', '') IS NULL
       OR nullif(p_receipt ->> 'response_agent_sha', '') IS NULL
       OR NOT (p_receipt ->> 'request_agent_sha' = ANY (coalesce(v_named, '{}')))
       OR NOT (p_receipt ->> 'response_agent_sha' = ANY (coalesce(v_named, '{}'))) THEN
        RAISE EXCEPTION 'proxy exchange must name the stored bytes of both directions'
            USING ERRCODE = '23514';
    END IF;

    INSERT INTO artifacts(sha256, byte_size, content_type, visibility, encrypted)
    SELECT s.sha256, s.byte_size, s.content_type, 'credential_bearing', true
      FROM jsonb_to_recordset(p_seals)
        AS s(sha256 text, byte_size bigint, content_type text)
    ON CONFLICT (sha256) DO NOTHING;

    SELECT string_agg(s.sha256, ', ') INTO v_problem
      FROM jsonb_to_recordset(p_seals)
        AS s(sha256 text, byte_size bigint, content_type text)
      LEFT JOIN artifacts a ON a.sha256 = s.sha256
     WHERE a.sha256 IS NULL OR a.byte_size <> s.byte_size
        OR a.visibility <> 'credential_bearing' OR NOT a.encrypted
        OR a.purged_at IS NOT NULL;
    IF v_problem IS NOT NULL THEN
        RAISE EXCEPTION 'wire artifact registration disagrees for %', v_problem
            USING ERRCODE = '23514';
    END IF;

    INSERT INTO artifact_references(program_id, sha256, kind)
    SELECT DISTINCT v_program, s.agent_sha256, 'runtime'
      FROM jsonb_to_recordset(p_seals) AS s(agent_sha256 text)
    ON CONFLICT (program_id, sha256, kind) DO NOTHING;

    INSERT INTO artifact_seal(
        sha256, scope_kind, scope_id, visibility, byte_size, alg, nonce,
        kek_gen, ciphertext_sha256, agent_sha256
    )
    SELECT s.sha256, 'program', v_program, 'credential_bearing', s.byte_size,
           s.alg, decode(s.nonce_hex, 'hex'), s.kek_gen,
           s.ciphertext_sha256, s.agent_sha256
      FROM jsonb_to_recordset(p_seals)
        AS s(sha256 text, byte_size bigint, alg text, nonce_hex text,
             kek_gen integer, ciphertext_sha256 text, agent_sha256 text)
    ON CONFLICT (sha256) DO NOTHING;

    SELECT string_agg(s.sha256, ', ') INTO v_problem
      FROM jsonb_to_recordset(p_seals)
        AS s(sha256 text, byte_size bigint, alg text, nonce_hex text,
             kek_gen integer, ciphertext_sha256 text, agent_sha256 text)
      LEFT JOIN artifact_seal x ON x.sha256 = s.sha256
     WHERE x.sha256 IS NULL OR x.scope_kind <> 'program' OR x.scope_id <> v_program
        OR x.byte_size <> s.byte_size OR x.alg <> s.alg
        OR encode(x.nonce, 'hex') <> s.nonce_hex OR x.kek_gen <> s.kek_gen
        OR x.ciphertext_sha256 <> s.ciphertext_sha256
        OR x.agent_sha256 <> s.agent_sha256;
    IF v_problem IS NOT NULL THEN
        RAISE EXCEPTION 'wire seal is already claimed under another context: %', v_problem
            USING ERRCODE = '23514';
    END IF;

    INSERT INTO secret_access_log(
        verb, scope_kind, scope_id, kek_gen, program_id, tool_run_id,
        field, value_len, value_fpr, outcome, detail
    )
    SELECT 'seal', 'program', v_program, s.kek_gen, v_program, v_tool_run,
           s.field, s.byte_size, decode(s.value_fpr_hex, 'hex'), 'ok',
           'proxy sealed a target response transformation'
      FROM jsonb_to_recordset(p_seals)
        AS s(byte_size bigint, kek_gen integer, value_fpr_hex text, field text);

    v_id := write_allowed_receipt(p_capability, p_receipt);
    SELECT r.label INTO v_label FROM receipts r WHERE r.id = v_id;
    RETURN jsonb_build_object('receipt_id', v_id, 'label', v_label,
                              'tool_run_id', v_tool_run);
END $fn$;

CREATE OR REPLACE FUNCTION record_proxy_exchange(
    p_capability text,
    p_receipt jsonb,
    p_artifacts jsonb
) RETURNS jsonb LANGUAGE sql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
    SELECT record_proxy_exchange(p_capability, p_receipt, p_artifacts, '[]'::jsonb)
$fn$;

REVOKE ALL ON FUNCTION record_proxy_exchange(text,jsonb,jsonb,jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION record_proxy_exchange(text,jsonb,jsonb,jsonb) TO rk2_proxy;

CREATE OR REPLACE FUNCTION check_capability_receipt_fence()
RETURNS TABLE(problem text, detail text) LANGUAGE sql STABLE AS $fn$
    SELECT 'proxy_can_insert_receipts', 'rk2_proxy has direct INSERT'
     WHERE has_table_privilege('rk2_proxy', 'receipts', 'INSERT')
    UNION ALL
    SELECT 'allowed_receipt_trigger_missing', 'trigger absent or not ENABLE ALWAYS'
     WHERE NOT EXISTS (SELECT 1 FROM pg_trigger
                        WHERE tgrelid = 'receipts'::regclass
                          AND tgname = 'receipts_allowed_capability' AND tgenabled = 'A')
    UNION ALL
    SELECT 'proxy_writer_missing', 'rk2_proxy cannot execute a required writer'
     WHERE NOT has_function_privilege(
               'rk2_proxy', 'record_proxy_exchange(text,jsonb,jsonb,jsonb)', 'EXECUTE')
        OR NOT has_function_privilege(
               'rk2_proxy', 'write_blocked_receipt(uuid,jsonb,text)', 'EXECUTE')
        OR NOT has_function_privilege(
               'rk2_proxy', 'ensure_proxy_wire_keying(text,bytea,bytea)', 'EXECUTE')
        OR NOT has_function_privilege(
               'rk2_proxy',
               'authorize_egress_request(text,text,text,text,integer,text,text,text)',
               'EXECUTE')
        OR NOT has_function_privilege(
               'rk2_proxy', 'authorize_egress_address(text,text,text,integer,text)', 'EXECUTE')
    UNION ALL
    SELECT 'proxy_bypasses_the_exchange_writer',
           'rk2_proxy can execute write_allowed_receipt directly'
     WHERE has_function_privilege('rk2_proxy', 'write_allowed_receipt(text,jsonb)', 'EXECUTE')
    UNION ALL
    SELECT 'proxy_can_read_the_scope_rules', 'rk2_proxy has SELECT on program_scope_rules'
     WHERE has_table_privilege('rk2_proxy', 'program_scope_rules', 'SELECT')
    UNION ALL
    SELECT 'unsealed_zero_byte_wire_artifact', a.sha256
      FROM artifacts a
     WHERE a.encrypted AND a.byte_size = 0 AND a.purged_at IS NULL
       AND NOT EXISTS (SELECT 1 FROM artifact_seal s WHERE s.sha256 = a.sha256)
$fn$;

COMMENT ON FUNCTION record_proxy_exchange(text,jsonb,jsonb,jsonb) IS
  'Atomic proxy writer for agent-visible transcripts, sealed wire transformations and their capability-bound Receipt.';
