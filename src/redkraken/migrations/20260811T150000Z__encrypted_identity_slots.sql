-- PH2-12: Identity labels resolve to encrypted, lease-gated proxy-side state.

CREATE TABLE identity_slots (
    id                 uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id         uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    identity_entity_id uuid NOT NULL UNIQUE,
    revision           bigint NOT NULL CHECK (revision > 0),
    alg                text NOT NULL REFERENCES seal_algorithms(name),
    nonce              bytea NOT NULL CHECK (octet_length(nonce) = 32),
    kek_gen            integer NOT NULL REFERENCES secret_kek(gen),
    envelope           bytea NOT NULL CHECK (octet_length(envelope) > 0),
    ciphertext_sha256  char(64) NOT NULL CHECK (ciphertext_sha256 ~ '^[0-9a-f]{64}$'),
    byte_size          bigint NOT NULL CHECK (byte_size > 0),
    value_fpr          bytea NOT NULL CHECK (octet_length(value_fpr) = 4),
    updated_at         timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, program_id),
    FOREIGN KEY (identity_entity_id, program_id)
        REFERENCES identities(entity_id, program_id)
);

COMMENT ON TABLE identity_slots IS
  'Mutable, authenticated ciphertext for one Identity cookie jar and origin-bound authorization material. Plaintext exists only in the control adapter and proxy process.';
COMMENT ON COLUMN identity_slots.revision IS
  'Monotonic and authenticated as associated data, so an older valid envelope cannot be rolled back onto the current slot.';
COMMENT ON COLUMN identity_slots.byte_size IS
  'Plaintext length for audit and bounds; no unkeyed plaintext hash is stored because a small credential document must not become offline-guessable.';

INSERT INTO purge_cascade_edges(table_name, column_name, rationale) VALUES
    ('identity_slots', 'program_id', 'program-scoped encrypted Identity state');

INSERT INTO event_types(id, family, subject_table, description) VALUES
    ('identity_slot.provisioned', 'row', 'identity_slots',
     'control-side material was sealed into an Identity slot'),
    ('identity_slot.updated', 'row', 'identity_slots',
     'the proxy persisted target-issued session state for an Identity');

INSERT INTO event_table_config(
    table_name, created_type, updated_type, ignored_columns, redacted_columns
) VALUES (
    'identity_slots', 'identity_slot.provisioned', 'identity_slot.updated',
    '{updated_at}', '{envelope,nonce,value_fpr}'
);

ALTER TABLE identity_slots ENABLE ROW LEVEL SECURITY;
CREATE POLICY identity_slots_rk2_runtime ON identity_slots
    AS PERMISSIVE FOR ALL TO rk2_runtime USING (true) WITH CHECK (true);

SELECT attach_event_triggers();


-- One key-generation initializer shared by wire Artifacts and Identity slots.
CREATE FUNCTION ensure_active_secret_kek(p_salt bytea, p_root_check bytea)
RETURNS TABLE(generation integer, salt_hex text, root_check_hex text)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
BEGIN
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
        RAISE EXCEPTION 'key proposal has the wrong shape' USING ERRCODE = '23514';
    END IF;

    BEGIN
        INSERT INTO secret_kek(gen, salt, root_check) VALUES (1, p_salt, p_root_check);
    EXCEPTION WHEN unique_violation THEN
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

CREATE OR REPLACE FUNCTION ensure_proxy_wire_keying(
    p_capability text, p_salt bytea, p_root_check bytea
) RETURNS TABLE(generation integer, salt_hex text, root_check_hex text)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM resolve_egress_capability(p_capability)) THEN
        RAISE EXCEPTION 'egress capability refused' USING ERRCODE = '23514';
    END IF;
    RETURN QUERY SELECT * FROM ensure_active_secret_kek(p_salt, p_root_check);
END $fn$;


CREATE FUNCTION identity_slot_keying(
    p_program uuid, p_identity text, p_salt bytea, p_root_check bytea
) RETURNS TABLE(
    identity_entity_id uuid,
    revision bigint,
    generation integer,
    salt_hex text,
    root_check_hex text
)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE v_identity uuid; v_revision bigint;
BEGIN
    IF p_program IS DISTINCT FROM rk2_program()
       OR NOT EXISTS (SELECT 1 FROM programs p
                       WHERE p.id = p_program AND p.closed_at IS NULL) THEN
        RAISE EXCEPTION 'Identity Program refused' USING ERRCODE = '23514';
    END IF;
    SELECT i.entity_id, coalesce(s.revision, 0)
      INTO v_identity, v_revision
      FROM identities i
      LEFT JOIN identity_slots s ON s.identity_entity_id = i.entity_id
     WHERE i.program_id = p_program AND i.slot_name = p_identity
       AND i.invalidated_at IS NULL;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Identity label refused' USING ERRCODE = '23514';
    END IF;

    RETURN QUERY
    SELECT v_identity, v_revision, k.generation, k.salt_hex, k.root_check_hex
      FROM ensure_active_secret_kek(p_salt, p_root_check) k;
END $fn$;


CREATE FUNCTION assert_identity_slot_state(p_state jsonb) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE v_envelope bytea;
BEGIN
    IF coalesce(jsonb_typeof(p_state), 'null') <> 'object'
       OR (SELECT array_agg(key ORDER BY key) FROM jsonb_object_keys(p_state) key)
          IS DISTINCT FROM ARRAY[
              'alg','byte_size','ciphertext_sha256','envelope_hex',
              'kek_gen','nonce_hex','revision','value_fpr_hex'
          ]::text[]
       OR coalesce((p_state ->> 'revision')::bigint, 0) < 1
       OR coalesce((p_state ->> 'byte_size')::bigint, 0) < 1
       OR coalesce((p_state ->> 'kek_gen')::integer, 0) < 1
       OR coalesce(p_state ->> 'nonce_hex', '') !~ '^[0-9a-f]{64}$'
       OR coalesce(p_state ->> 'value_fpr_hex', '') !~ '^[0-9a-f]{8}$'
       OR coalesce(p_state ->> 'ciphertext_sha256', '') !~ '^[0-9a-f]{64}$'
       OR coalesce(p_state ->> 'envelope_hex', '') !~ '^([0-9a-f]{2})+$'
       OR NOT EXISTS (SELECT 1 FROM seal_algorithms a
                       WHERE a.name = p_state ->> 'alg')
       OR NOT EXISTS (SELECT 1 FROM secret_kek k
                       WHERE k.gen = (p_state ->> 'kek_gen')::integer) THEN
        RAISE EXCEPTION 'Identity slot state has the wrong shape' USING ERRCODE = '23514';
    END IF;
    v_envelope := decode(p_state ->> 'envelope_hex', 'hex');
    IF encode(digest(v_envelope, 'sha256'), 'hex')
          IS DISTINCT FROM p_state ->> 'ciphertext_sha256' THEN
        RAISE EXCEPTION 'Identity slot envelope digest disagrees' USING ERRCODE = '23514';
    END IF;
END $fn$;


CREATE FUNCTION provision_identity_slot(
    p_program uuid, p_identity text, p_expected_revision bigint, p_state jsonb
) RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE v_identity uuid; v_written bigint;
BEGIN
    IF p_program IS DISTINCT FROM rk2_program() THEN
        RAISE EXCEPTION 'Identity Program refused' USING ERRCODE = '23514';
    END IF;
    SELECT i.entity_id INTO v_identity
      FROM identities i JOIN programs p ON p.id = i.program_id
     WHERE i.program_id = p_program AND i.slot_name = p_identity
       AND i.invalidated_at IS NULL AND p.closed_at IS NULL;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Identity label refused' USING ERRCODE = '23514';
    END IF;
    PERFORM assert_identity_slot_state(p_state);
    IF (p_state ->> 'revision')::bigint <> p_expected_revision + 1 THEN
        RAISE EXCEPTION 'Identity slot revision is not the next revision'
            USING ERRCODE = '23514';
    END IF;

    PERFORM set_actor('runtime', 'Identity provisioning');
    INSERT INTO identity_slots(
        program_id, identity_entity_id, revision, alg, nonce, kek_gen,
        envelope, ciphertext_sha256, byte_size, value_fpr
    ) VALUES (
        p_program, v_identity, (p_state ->> 'revision')::bigint,
        p_state ->> 'alg', decode(p_state ->> 'nonce_hex', 'hex'),
        (p_state ->> 'kek_gen')::integer,
        decode(p_state ->> 'envelope_hex', 'hex'), p_state ->> 'ciphertext_sha256',
        (p_state ->> 'byte_size')::bigint,
        decode(p_state ->> 'value_fpr_hex', 'hex')
    )
    ON CONFLICT (identity_entity_id) DO UPDATE SET
        revision = EXCLUDED.revision,
        alg = EXCLUDED.alg,
        nonce = EXCLUDED.nonce,
        kek_gen = EXCLUDED.kek_gen,
        envelope = EXCLUDED.envelope,
        ciphertext_sha256 = EXCLUDED.ciphertext_sha256,
        byte_size = EXCLUDED.byte_size,
        value_fpr = EXCLUDED.value_fpr,
        updated_at = now()
    WHERE identity_slots.program_id = p_program
      AND identity_slots.revision = p_expected_revision
    RETURNING revision INTO v_written;
    IF v_written IS NULL THEN
        RAISE EXCEPTION 'Identity slot revision changed during provisioning'
            USING ERRCODE = '40001';
    END IF;

    INSERT INTO secret_access_log(
        verb, scope_kind, scope_id, kek_gen, program_id,
        field, value_len, value_fpr, outcome, detail
    ) VALUES (
        'seal', 'identity', v_identity, (p_state ->> 'kek_gen')::integer,
        p_program, 'identity_slot', (p_state ->> 'byte_size')::integer,
        decode(p_state ->> 'value_fpr_hex', 'hex'), 'ok',
        'control side provisioned encrypted Identity material'
    );
    RETURN v_written;
END $fn$;


-- Derive the selected Identity from the capability's Tool run. The proxy never
-- accepts a model-authored Identity header or a Program-global slot lookup.
CREATE FUNCTION resolve_egress_identity(p_capability text)
RETURNS TABLE(
    program_id uuid,
    tool_run_id uuid,
    agent_run_id uuid,
    identity_entity_id uuid,
    identity_label text
)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE v_auth record; v_label text; v_identity uuid;
BEGIN
    SELECT * INTO v_auth FROM resolve_egress_capability(p_capability);
    IF NOT FOUND THEN
        RAISE EXCEPTION 'egress capability refused' USING ERRCODE = '23514';
    END IF;
    SELECT nullif(btrim(tr.args ->> 'identity_slot'), '') INTO v_label
      FROM tool_runs tr WHERE tr.id = v_auth.tool_run_id;
    IF v_label IS NOT NULL THEN
        SELECT i.entity_id INTO v_identity
          FROM identities i
          JOIN identity_leases l
            ON l.identity_entity_id = i.entity_id
           AND l.program_id = i.program_id
           AND l.holder_agent_run_id = v_auth.agent_run_id
           AND l.released_at IS NULL
           AND l.expires_at > clock_timestamp()
         WHERE i.program_id = v_auth.program_id
           AND i.slot_name = v_label
           AND i.invalidated_at IS NULL;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'Identity lease refused' USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN QUERY SELECT v_auth.program_id, v_auth.tool_run_id, v_auth.agent_run_id,
                        v_identity, v_label;
END $fn$;


CREATE FUNCTION authorize_identity_egress_request(
    p_capability text,
    p_method text,
    p_protocol text,
    p_host text,
    p_port integer,
    p_path_raw text,
    p_path_norm text
) RETURNS TABLE(
    program_id uuid,
    tool_run_id uuid,
    scope_version integer,
    scope_class text,
    identity_entity_id uuid,
    identity_label text
)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE v_identity record; v_authorized record;
BEGIN
    SELECT * INTO v_identity FROM resolve_egress_identity(p_capability);
    SELECT * INTO v_authorized FROM authorize_egress_request(
        p_capability, p_method, p_protocol, p_host, p_port,
        p_path_raw, p_path_norm, coalesce(v_identity.identity_label, '')
    );
    RETURN QUERY SELECT v_authorized.program_id, v_authorized.tool_run_id,
                        v_authorized.scope_version, v_authorized.scope_class,
                        v_identity.identity_entity_id, v_identity.identity_label;
END $fn$;


CREATE FUNCTION authorize_identity_egress_address(
    p_capability text, p_protocol text, p_host text, p_port integer, p_address text
) RETURNS TABLE(scope_class text, reason text)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
BEGIN
    PERFORM * FROM resolve_egress_identity(p_capability);
    RETURN QUERY SELECT * FROM authorize_egress_address(
        p_capability, p_protocol, p_host, p_port, p_address
    );
END $fn$;


CREATE FUNCTION open_identity_slot(p_capability text, p_identity text)
RETURNS TABLE(
    identity_entity_id uuid,
    identity_label text,
    revision bigint,
    alg text,
    nonce_hex text,
    kek_gen integer,
    envelope_hex text,
    ciphertext_sha256 text,
    salt_hex text,
    root_check_hex text
)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE v_auth record; v_slot identity_slots%ROWTYPE;
BEGIN
    SELECT * INTO v_auth FROM resolve_egress_identity(p_capability);
    IF v_auth.identity_label IS NULL
       OR v_auth.identity_label IS DISTINCT FROM p_identity THEN
        RAISE EXCEPTION 'Identity selection refused' USING ERRCODE = '23514';
    END IF;
    SELECT * INTO v_slot FROM identity_slots s
     WHERE s.program_id = v_auth.program_id
       AND s.identity_entity_id = v_auth.identity_entity_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Identity has no provisioned slot' USING ERRCODE = '23514';
    END IF;

    INSERT INTO secret_access_log(
        verb, scope_kind, scope_id, kek_gen, program_id, tool_run_id,
        field, value_len, value_fpr, outcome, detail
    ) VALUES (
        'open_identity', 'identity', v_slot.identity_entity_id, v_slot.kek_gen,
        v_slot.program_id, v_auth.tool_run_id, 'identity_slot', v_slot.byte_size,
        v_slot.value_fpr, 'ok', 'proxy opened a live leased Identity slot'
    );

    RETURN QUERY
    SELECT v_slot.identity_entity_id, v_auth.identity_label, v_slot.revision,
           v_slot.alg, encode(v_slot.nonce, 'hex'), v_slot.kek_gen,
           encode(v_slot.envelope, 'hex'), v_slot.ciphertext_sha256::text,
           encode(k.salt, 'hex'),
           encode(k.root_check, 'hex')
      FROM secret_kek k WHERE k.gen = v_slot.kek_gen;
END $fn$;


CREATE FUNCTION record_identity_proxy_exchange(
    p_capability text,
    p_receipt jsonb,
    p_artifacts jsonb,
    p_seals jsonb,
    p_identity text,
    p_expected_revision bigint,
    p_state jsonb
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE v_auth record; v_receipt jsonb; v_written bigint;
BEGIN
    SELECT * INTO v_auth FROM resolve_egress_identity(p_capability);
    IF coalesce(v_auth.identity_label, '') IS DISTINCT FROM coalesce(p_identity, '') THEN
        RAISE EXCEPTION 'Identity selection changed before Receipt write'
            USING ERRCODE = '23514';
    END IF;
    v_receipt := p_receipt - 'identity_entity_id';
    IF v_auth.identity_entity_id IS NOT NULL THEN
        v_receipt := jsonb_set(
            v_receipt, '{identity_entity_id}', to_jsonb(v_auth.identity_entity_id)
        );
    ELSIF p_state IS NOT NULL OR p_expected_revision IS NOT NULL THEN
        RAISE EXCEPTION 'anonymous exchange carries Identity state'
            USING ERRCODE = '23514';
    END IF;

    IF p_state IS NOT NULL THEN
        PERFORM assert_identity_slot_state(p_state);
        IF (p_state ->> 'revision')::bigint <> p_expected_revision + 1 THEN
            RAISE EXCEPTION 'Identity slot revision is not the next revision'
                USING ERRCODE = '23514';
        END IF;
        PERFORM set_actor('runtime', 'proxy Identity session capture');
        UPDATE identity_slots SET
            revision = (p_state ->> 'revision')::bigint,
            alg = p_state ->> 'alg',
            nonce = decode(p_state ->> 'nonce_hex', 'hex'),
            kek_gen = (p_state ->> 'kek_gen')::integer,
            envelope = decode(p_state ->> 'envelope_hex', 'hex'),
            ciphertext_sha256 = p_state ->> 'ciphertext_sha256',
            byte_size = (p_state ->> 'byte_size')::bigint,
            value_fpr = decode(p_state ->> 'value_fpr_hex', 'hex'),
            updated_at = now()
         WHERE program_id = v_auth.program_id
           AND identity_entity_id = v_auth.identity_entity_id
           AND revision = p_expected_revision
        RETURNING revision INTO v_written;
        IF v_written IS NULL THEN
            RAISE EXCEPTION 'Identity slot revision changed during exchange'
                USING ERRCODE = '40001';
        END IF;
        INSERT INTO secret_access_log(
            verb, scope_kind, scope_id, kek_gen, program_id, tool_run_id,
            field, value_len, value_fpr, outcome, detail
        ) VALUES (
            'seal', 'identity', v_auth.identity_entity_id,
            (p_state ->> 'kek_gen')::integer, v_auth.program_id,
            v_auth.tool_run_id, 'cookie_jar', (p_state ->> 'byte_size')::integer,
            decode(p_state ->> 'value_fpr_hex', 'hex'), 'ok',
            'proxy persisted target-issued Identity session state'
        );
    END IF;

    RETURN record_proxy_exchange(p_capability, v_receipt, p_artifacts, p_seals);
END $fn$;


-- Identity-bearing calls require human approval under the established risk
-- policy. Decision labels are Program-local (each Program has a D1), so the
-- human writer must resolve them under the same explicit Program binding as
-- every other cross-role control operation.
CREATE OR REPLACE FUNCTION answer_decision(
    p_label text,
    p_verdict text,
    p_reason text,
    p_grant interval DEFAULT interval '24 hours'
) RETURNS jsonb SECURITY DEFINER LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $fn$
DECLARE d pending_decisions%ROWTYPE;
BEGIN
    IF p_verdict NOT IN ('approved','denied') THEN
        RAISE EXCEPTION 'verdict must be approved or denied, got %', p_verdict;
    END IF;
    PERFORM set_actor('human', session_user);

    SELECT * INTO d FROM pending_decisions
     WHERE label = p_label AND program_id = rk2_program()
     FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'no decision % in the bound Program', p_label; END IF;

    UPDATE pending_decisions
       SET status = p_verdict, actor_kind = 'human', answered_at = now(),
           answered_by = session_user, answer = p_reason,
           grant_expires_at = CASE WHEN p_verdict = 'approved'
                                   THEN now() + p_grant ELSE NULL END
     WHERE id = d.id
    RETURNING * INTO d;

    IF p_verdict = 'approved' THEN
        UPDATE tasks SET status = 'pending', pending_decision_id = NULL, priority = NULL
         WHERE id = d.task_id;
    ELSE
        UPDATE tasks SET status = 'abandoned', abandoned_reason = 'decision_denied',
                         finished_at = now(), pending_decision_id = NULL, priority = NULL
         WHERE id = d.task_id;
    END IF;

    RETURN jsonb_build_object('label', d.label, 'status', d.status,
                              'answered_by', d.answered_by,
                              'grant_expires_at', d.grant_expires_at,
                              'equivalence_key', d.equivalence_key);
END $fn$;


CREATE OR REPLACE FUNCTION enforce_allowed_receipt_capability() RETURNS trigger
LANGUAGE plpgsql AS $fn$
BEGIN
    IF NEW.lane = 'agent' AND NEW.decision = 'allowed'
       AND NOT EXISTS (
           SELECT 1
             FROM tool_runs tr
             JOIN programs p ON p.id = tr.program_id AND p.closed_at IS NULL
             JOIN agent_runs ar ON ar.id = tr.agent_run_id AND ar.program_id = tr.program_id
             LEFT JOIN tasks t ON t.id = tr.task_id AND t.program_id = tr.program_id
            WHERE tr.id = NEW.tool_run_id
              AND tr.program_id = NEW.program_id
              AND NOT EXISTS (SELECT 1 FROM program_halts h
                               WHERE h.program_id = tr.program_id AND h.status = 'halted')
              AND tr.status = 'running' AND tr.decision = 'allow'
              AND tr.egress_token_sha256 IS NOT NULL
              AND tr.egress_token_expires_at > clock_timestamp()
              AND ar.finished_at IS NULL
              AND ((tr.task_id IS NULL AND ar.task_id IS NULL)
                   OR (tr.task_id IS NOT NULL AND ar.task_id = tr.task_id
                       AND t.status IN ('claimed', 'running')
                       AND t.lease_expires_at > clock_timestamp()))
              AND (
                  (coalesce(tr.args ->> 'identity_slot', '') = ''
                   AND NEW.identity_entity_id IS NULL)
                  OR EXISTS (
                      SELECT 1 FROM identities i
                      JOIN identity_slots s ON s.identity_entity_id = i.entity_id
                      JOIN identity_leases l
                        ON l.identity_entity_id = i.entity_id
                       AND l.program_id = i.program_id
                       AND l.holder_agent_run_id = ar.id
                       AND l.released_at IS NULL
                       AND l.expires_at > clock_timestamp()
                     WHERE i.entity_id = NEW.identity_entity_id
                       AND i.program_id = NEW.program_id
                       AND i.slot_name = tr.args ->> 'identity_slot'
                       AND i.invalidated_at IS NULL
                  )
              )
       ) THEN
        RAISE EXCEPTION 'allowed agent receipt lacks a live authorized capability and Identity'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $fn$;


REVOKE ALL ON FUNCTION ensure_active_secret_kek(bytea,bytea) FROM PUBLIC;
REVOKE ALL ON FUNCTION assert_identity_slot_state(jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION resolve_egress_identity(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION identity_slot_keying(uuid,text,bytea,bytea) FROM PUBLIC;
REVOKE ALL ON FUNCTION provision_identity_slot(uuid,text,bigint,jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION authorize_identity_egress_request(text,text,text,text,integer,text,text)
    FROM PUBLIC;
REVOKE ALL ON FUNCTION authorize_identity_egress_address(text,text,text,integer,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION open_identity_slot(text,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION record_identity_proxy_exchange(text,jsonb,jsonb,jsonb,text,bigint,jsonb)
    FROM PUBLIC;

REVOKE EXECUTE ON FUNCTION ensure_active_secret_kek(bytea,bytea),
    assert_identity_slot_state(jsonb), resolve_egress_identity(text),
    open_identity_slot(text,text),
    record_identity_proxy_exchange(text,jsonb,jsonb,jsonb,text,bigint,jsonb)
    FROM rk2_runtime;
GRANT EXECUTE ON FUNCTION identity_slot_keying(uuid,text,bytea,bytea),
    provision_identity_slot(uuid,text,bigint,jsonb) TO rk2_runtime;

REVOKE EXECUTE ON FUNCTION
    authorize_egress_request(text,text,text,text,integer,text,text,text),
    authorize_egress_address(text,text,text,integer,text),
    record_proxy_exchange(text,jsonb,jsonb,jsonb),
    identity_slot_keying(uuid,text,bytea,bytea),
    provision_identity_slot(uuid,text,bigint,jsonb)
    FROM rk2_proxy;
GRANT EXECUTE ON FUNCTION
    authorize_identity_egress_request(text,text,text,text,integer,text,text),
    authorize_identity_egress_address(text,text,text,integer,text),
    open_identity_slot(text,text),
    record_identity_proxy_exchange(text,jsonb,jsonb,jsonb,text,bigint,jsonb)
    TO rk2_proxy;

REVOKE ALL ON identity_slots FROM rk2_state, rk2_proxy, rk2_human;


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
    SELECT 'proxy_identity_writer_missing', 'rk2_proxy cannot execute the Identity fence'
     WHERE NOT has_function_privilege(
               'rk2_proxy',
               'authorize_identity_egress_request(text,text,text,text,integer,text,text)',
               'EXECUTE')
        OR NOT has_function_privilege(
               'rk2_proxy', 'authorize_identity_egress_address(text,text,text,integer,text)',
               'EXECUTE')
        OR NOT has_function_privilege('rk2_proxy', 'open_identity_slot(text,text)', 'EXECUTE')
        OR NOT has_function_privilege(
               'rk2_proxy',
               'record_identity_proxy_exchange(text,jsonb,jsonb,jsonb,text,bigint,jsonb)',
               'EXECUTE')
        OR NOT has_function_privilege(
               'rk2_proxy', 'ensure_proxy_wire_keying(text,bytea,bytea)', 'EXECUTE')
        OR NOT has_function_privilege(
               'rk2_proxy', 'write_blocked_receipt(uuid,jsonb,text)', 'EXECUTE')
    UNION ALL
    SELECT 'proxy_bypasses_identity_writer', 'rk2_proxy retains an unchecked writer'
     WHERE has_function_privilege('rk2_proxy', 'write_allowed_receipt(text,jsonb)', 'EXECUTE')
        OR has_function_privilege(
               'rk2_proxy', 'record_proxy_exchange(text,jsonb,jsonb,jsonb)', 'EXECUTE')
        OR has_function_privilege(
               'rk2_proxy',
               'authorize_egress_request(text,text,text,text,integer,text,text,text)',
               'EXECUTE')
        OR has_function_privilege(
               'rk2_proxy', 'authorize_egress_address(text,text,text,integer,text)', 'EXECUTE')
        OR has_function_privilege('rk2_proxy', 'provision_identity_slot(uuid,text,bigint,jsonb)',
                                  'EXECUTE')
        OR has_table_privilege('rk2_proxy', 'identity_slots', 'SELECT')
    UNION ALL
    SELECT 'state_can_reach_identity_slots', 'the agent-facing role can reach slot state'
     WHERE has_table_privilege('rk2_state', 'identity_slots', 'SELECT')
        OR has_function_privilege('rk2_state', 'open_identity_slot(text,text)', 'EXECUTE')
        OR has_function_privilege(
               'rk2_state', 'provision_identity_slot(uuid,text,bigint,jsonb)', 'EXECUTE')
    UNION ALL
    SELECT 'unsealed_zero_byte_wire_artifact', a.sha256
      FROM artifacts a
     WHERE a.encrypted AND a.byte_size = 0 AND a.purged_at IS NULL
       AND NOT EXISTS (SELECT 1 FROM artifact_seal s WHERE s.sha256 = a.sha256)
$fn$;

UPDATE standing_checks
   SET note = 'the proxy reaches Identity slots and allowed Receipts only through lease-gated writers; hunter reads and provisioning remain separate; every wire transformation is sealed'
 WHERE name = 'capability_receipt_fence';

DO $$
DECLARE n integer; d text;
BEGIN
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_capability_receipt_fence();
    IF n > 0 THEN
        RAISE EXCEPTION 'Identity capability fence broken (% problems): %', n, d;
    END IF;
END $$;
