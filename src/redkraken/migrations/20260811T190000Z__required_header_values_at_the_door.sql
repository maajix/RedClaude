-- Origin: story 8, "exact target headers configured outside model-visible
-- state, so that required program identifiers can be injected without exposing
-- their values", and §4's "Required headers are injected at the proxy."
--
-- Ticket 08 compiled the declaration: `program_required_headers` holds the name
-- on the agent read surface and the `slot://` reference off it. Nothing ever
-- resolved that reference. The name was checkable, the pointer was stored, and
-- every request left the door without the header -- which for a bounty
-- identifier is the failure that gets a Program's traffic mistaken for an
-- attack, and cannot be noticed from inside the harness because the record and
-- the wire agree perfectly about a header neither of them has.
--
-- This is the resolution half. It follows the Identity slot arrangement of
-- `20260811T150000Z` rather than inventing a second one, because the two hold
-- the same kind of thing: a short secret the door needs, the control side
-- writes, and no agent-facing role may read.
--
--   * The plaintext exists in two processes, the provisioning command and the
--     door, and nowhere else. Canonical state holds an authenticated ciphertext.
--   * No unkeyed digest of the plaintext is stored. A bounty identifier is short
--     enough to search, so `ciphertext_sha256` names the envelope and
--     `value_fpr` is keyed -- enough to say two values are one, not enough to
--     guess either.
--   * The reader takes a live capability, not a Program. A header value is
--     material for an authorized request, so it is reachable exactly when a
--     request is, and the attempt is on the secret access log either way.
--
-- What is deliberately NOT here: a per-scope-version binding. An Identity slot
-- carries `binding_revision` because its declaration names an entity whose
-- configuration revision can change under it. A required header is a name and a
-- pointer, and the join in `open_required_headers` is against the capability's
-- own live scope version -- so a header that was withdrawn is not returned, and
-- one that was renamed is a different row. Binding the ciphertext to the version
-- as well would invalidate every provisioned value whenever an unrelated scope
-- rule moved, which is a re-provisioning treadmill and not a safety property.

CREATE TABLE program_header_slots (
    -- A surrogate key even though (program_id, name) identifies the row: the
    -- event log addresses every subject by `id`, and a table that emits events
    -- without one is a check that cannot run rather than a check that passes.
    id                uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id        uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    -- The same field-name rule the declaration carries, for the same reason: a
    -- "header" holding a colon or a newline is two headers.
    name              text NOT NULL
                      CHECK (name ~ '^[A-Za-z0-9!#$%&''*+.^_`|~-]{1,64}$'),
    revision          bigint NOT NULL CHECK (revision > 0),
    alg               text NOT NULL REFERENCES seal_algorithms(name),
    nonce             bytea NOT NULL CHECK (octet_length(nonce) = 32),
    kek_gen           integer NOT NULL REFERENCES secret_kek(gen),
    envelope          bytea NOT NULL CHECK (octet_length(envelope) > 0),
    ciphertext_sha256 char(64) NOT NULL CHECK (ciphertext_sha256 ~ '^[0-9a-f]{64}$'),
    byte_size         bigint NOT NULL CHECK (byte_size > 0),
    value_fpr         bytea NOT NULL CHECK (octet_length(value_fpr) = 4),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    UNIQUE (program_id, name)
);

-- Field names are case-insensitive on the wire, so two spellings of one name are
-- one header provisioned twice and which value the door sent would be decided by
-- row order. The declaration is unique the same way.
CREATE UNIQUE INDEX program_header_slots_name_idx
    ON program_header_slots (program_id, lower(name));

COMMENT ON TABLE program_header_slots IS
  'Authenticated ciphertext for one Program required-header value. Plaintext exists only in the provisioning command and the proxy process; no role below the owner may read the row.';
COMMENT ON COLUMN program_header_slots.revision IS
  'Monotonic and authenticated as associated data, so a retired identifier cannot be rolled back onto a live Program.';
COMMENT ON COLUMN program_header_slots.byte_size IS
  'Plaintext length for audit and bounds; no unkeyed plaintext hash is stored because a short identifier must not become offline-guessable.';

INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
    ('program_header_slots', 'program_id', 'program-scoped: the purge root');

-- Emitting rather than exempt, and redacted the same three columns its sibling
-- redacts. "A required-header value was replaced" is a fact an operator has to
-- be able to read off the log; the ciphertext, the nonce and the keyed
-- fingerprint are not, so the after-image carries the revision and the size and
-- none of the material.
INSERT INTO event_types(id, family, subject_table, description) VALUES
    ('header_slot.provisioned', 'row', 'program_header_slots',
     'control-side material was sealed into a required-header slot'),
    ('header_slot.updated', 'row', 'program_header_slots',
     'a required-header value was replaced with a newer revision');

INSERT INTO event_table_config(
    table_name, created_type, updated_type, ignored_columns, redacted_columns
) VALUES (
    'program_header_slots', 'header_slot.provisioned', 'header_slot.updated',
    '{updated_at}', '{envelope,nonce,value_fpr}'
);

ALTER TABLE program_header_slots ENABLE ROW LEVEL SECURITY;

SELECT attach_event_triggers();


-- ---------------------------------------------------------------------------
-- The shape of one provisioned slot
-- ---------------------------------------------------------------------------
-- The control side seals; the database refuses to store anything that is not a
-- complete, self-consistent envelope. Written as an assertion rather than as
-- column constraints because the document arrives as one value and a partial
-- one has to be refused whole.

CREATE FUNCTION assert_header_slot_state(p_state jsonb) RETURNS void
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
        RAISE EXCEPTION 'header slot state has the wrong shape' USING ERRCODE = '23514';
    END IF;
    v_envelope := decode(p_state ->> 'envelope_hex', 'hex');
    IF encode(digest(v_envelope, 'sha256'), 'hex')
          IS DISTINCT FROM p_state ->> 'ciphertext_sha256' THEN
        RAISE EXCEPTION 'header slot envelope digest disagrees' USING ERRCODE = '23514';
    END IF;
END $fn$;


-- ---------------------------------------------------------------------------
-- Keying: the salt and the check value, never the secret
-- ---------------------------------------------------------------------------
-- The same handshake `identity_slot_keying` performs, for the same reason. The
-- database supplies a random salt and the check value for the active generation;
-- the control side derives its key from a secret this connection never sees, and
-- a caller holding the wrong root learns so before it writes a ciphertext
-- nobody can open.

CREATE FUNCTION header_slot_keying(
    p_program uuid, p_name text, p_salt bytea, p_root_check bytea
) RETURNS TABLE(
    name text,
    revision bigint,
    generation integer,
    salt_hex text,
    root_check_hex text,
    audit_id uuid
)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE
    v_name text;
    v_revision bigint;
    v_generation integer;
    v_salt_hex text;
    v_root_check_hex text;
    v_audit uuid;
BEGIN
    IF p_program IS DISTINCT FROM rk2_program()
       OR NOT EXISTS (SELECT 1 FROM programs p
                       WHERE p.id = p_program AND p.closed_at IS NULL) THEN
        RAISE EXCEPTION 'header Program refused' USING ERRCODE = '23514';
    END IF;
    -- Declared at the Program's live scope version, in the declaration's own
    -- spelling. Provisioning a header the policy does not require would be a
    -- value the door never sends and an operator who believes it does.
    SELECT h.name, coalesce(s.revision, 0)
      INTO v_name, v_revision
      FROM programs p
      JOIN program_required_headers h
        ON h.program_id = p.id AND h.version = p.scope_version
      LEFT JOIN program_header_slots s
        ON s.program_id = h.program_id AND lower(s.name) = lower(h.name)
     WHERE p.id = p_program AND lower(h.name) = lower(p_name);
    IF NOT FOUND THEN
        RAISE EXCEPTION 'header name refused' USING ERRCODE = '23514';
    END IF;

    SELECT k.generation, k.salt_hex, k.root_check_hex
      INTO v_generation, v_salt_hex, v_root_check_hex
      FROM ensure_active_secret_kek(p_salt, p_root_check) k;
    v_audit := uuidv7();
    INSERT INTO secret_access_log(
        id, operation_id,
        verb, scope_kind, scope_id, kek_gen, program_id,
        field, outcome, detail
    ) VALUES (
        v_audit, v_audit,
        'rootcheck', 'program', p_program, v_generation, p_program,
        'header_slot:' || lower(v_name), 'attempted',
        'control side requested a required-header root check'
    );
    RETURN QUERY SELECT v_name, v_revision, v_generation, v_salt_hex,
                        v_root_check_hex, v_audit;
END $fn$;


CREATE FUNCTION confirm_header_root_check(
    p_program uuid, p_name text, p_audit uuid, p_outcome text
) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE v_attempt secret_access_log%ROWTYPE;
BEGIN
    IF p_program IS DISTINCT FROM rk2_program()
       OR p_outcome NOT IN ('ok', 'denied') THEN
        RAISE EXCEPTION 'header root check confirmation refused' USING ERRCODE = '23514';
    END IF;
    SELECT * INTO v_attempt FROM secret_access_log
     WHERE id = p_audit AND operation_id = p_audit AND verb = 'rootcheck'
       AND program_id = p_program AND scope_kind = 'program'
       AND field = 'header_slot:' || lower(p_name)
       AND outcome = 'attempted';
    IF NOT FOUND THEN
        RAISE EXCEPTION 'header root check attempt changed' USING ERRCODE = '23514';
    END IF;
    INSERT INTO secret_access_log(
        operation_id, verb, scope_kind, scope_id, kek_gen, program_id,
        field, outcome, detail
    ) VALUES (
        p_audit, v_attempt.verb, v_attempt.scope_kind, v_attempt.scope_id,
        v_attempt.kek_gen, v_attempt.program_id, v_attempt.field, p_outcome,
        CASE p_outcome
            WHEN 'ok' THEN 'control side confirmed the required-header root check'
            ELSE 'control side refused a required-header root mismatch'
        END
    );
END $fn$;


CREATE FUNCTION provision_header_slot(
    p_program uuid, p_name text, p_expected_revision bigint, p_state jsonb
) RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE v_name text; v_written bigint;
BEGIN
    IF p_program IS DISTINCT FROM rk2_program() THEN
        RAISE EXCEPTION 'header Program refused' USING ERRCODE = '23514';
    END IF;
    SELECT h.name INTO v_name
      FROM programs p
      JOIN program_required_headers h
        ON h.program_id = p.id AND h.version = p.scope_version
     WHERE p.id = p_program AND p.closed_at IS NULL
       AND lower(h.name) = lower(p_name);
    IF NOT FOUND THEN
        RAISE EXCEPTION 'header name refused' USING ERRCODE = '23514';
    END IF;
    PERFORM assert_header_slot_state(p_state);
    IF (p_state ->> 'revision')::bigint <> p_expected_revision + 1 THEN
        RAISE EXCEPTION 'header slot revision changed' USING ERRCODE = '23514';
    END IF;

    PERFORM set_actor('runtime', 'required-header provisioning');
    INSERT INTO program_header_slots(
        program_id, name, revision, alg, nonce, kek_gen,
        envelope, ciphertext_sha256, byte_size, value_fpr
    ) VALUES (
        p_program, v_name, (p_state ->> 'revision')::bigint,
        p_state ->> 'alg', decode(p_state ->> 'nonce_hex', 'hex'),
        (p_state ->> 'kek_gen')::integer,
        decode(p_state ->> 'envelope_hex', 'hex'), p_state ->> 'ciphertext_sha256',
        (p_state ->> 'byte_size')::bigint,
        decode(p_state ->> 'value_fpr_hex', 'hex')
    )
    ON CONFLICT (program_id, name) DO UPDATE SET
        revision = EXCLUDED.revision,
        alg = EXCLUDED.alg,
        nonce = EXCLUDED.nonce,
        kek_gen = EXCLUDED.kek_gen,
        envelope = EXCLUDED.envelope,
        ciphertext_sha256 = EXCLUDED.ciphertext_sha256,
        byte_size = EXCLUDED.byte_size,
        value_fpr = EXCLUDED.value_fpr,
        updated_at = now()
    WHERE program_header_slots.revision = p_expected_revision
    RETURNING revision INTO v_written;
    IF v_written IS NULL THEN
        RAISE EXCEPTION 'header slot revision changed during provisioning'
            USING ERRCODE = '40001';
    END IF;

    INSERT INTO secret_access_log(
        verb, scope_kind, scope_id, kek_gen, program_id,
        field, value_len, value_fpr, outcome, detail
    ) VALUES (
        'seal', 'program', p_program, (p_state ->> 'kek_gen')::integer,
        p_program, 'header_slot:' || lower(v_name),
        (p_state ->> 'byte_size')::integer,
        decode(p_state ->> 'value_fpr_hex', 'hex'), 'ok',
        'control side provisioned an encrypted required-header value'
    );
    RETURN v_written;
END $fn$;


-- ---------------------------------------------------------------------------
-- The door's read
-- ---------------------------------------------------------------------------
-- One row per header the capability's live scope version requires, in the
-- declaration's order, with the envelope when there is one and nulls when there
-- is not. Both cases are answers the door has to act on: a declared header with
-- no provisioned value is a request that must not leave, and returning nothing
-- for it would be indistinguishable from a Program that requires no headers.

CREATE FUNCTION open_required_headers(p_capability text)
RETURNS TABLE(
    ord integer,
    name text,
    revision bigint,
    alg text,
    nonce_hex text,
    kek_gen integer,
    envelope_hex text,
    ciphertext_sha256 text,
    salt_hex text,
    root_check_hex text,
    audit_id uuid
)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE v_auth record; v_version integer; v_audit uuid;
BEGIN
    SELECT * INTO v_auth FROM resolve_egress_capability(p_capability);
    IF NOT FOUND THEN
        RAISE EXCEPTION 'egress capability refused' USING ERRCODE = '23514';
    END IF;
    SELECT p.scope_version INTO v_version
      FROM programs p WHERE p.id = v_auth.program_id;

    v_audit := uuidv7();
    INSERT INTO secret_access_log(
        id, operation_id,
        verb, scope_kind, scope_id, kek_gen, program_id, tool_run_id,
        field, outcome, detail
    )
    SELECT v_audit, v_audit, 'open', 'program', v_auth.program_id,
           (SELECT k.gen FROM secret_kek k WHERE k.retired_at IS NULL
             ORDER BY k.gen DESC LIMIT 1),
           v_auth.program_id, v_auth.tool_run_id,
           'header_slot', 'attempted',
           'proxy requested ' || count(*) || ' required-header value(s)'
      FROM program_required_headers h
     WHERE h.program_id = v_auth.program_id AND h.version = v_version
    HAVING count(*) > 0;

    RETURN QUERY
    SELECT h.ord, h.name, s.revision, s.alg, encode(s.nonce, 'hex'), s.kek_gen,
           encode(s.envelope, 'hex'), s.ciphertext_sha256::text,
           encode(k.salt, 'hex'), encode(k.root_check, 'hex'), v_audit
      FROM program_required_headers h
      LEFT JOIN program_header_slots s
        ON s.program_id = h.program_id AND lower(s.name) = lower(h.name)
      LEFT JOIN secret_kek k ON k.gen = s.kek_gen
     WHERE h.program_id = v_auth.program_id AND h.version = v_version
     ORDER BY h.ord;
END $fn$;


CREATE FUNCTION confirm_required_headers_open(
    p_capability text, p_audit uuid, p_outcome text
) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE v_auth record; v_attempt secret_access_log%ROWTYPE;
BEGIN
    SELECT * INTO v_auth FROM resolve_egress_capability(p_capability);
    IF NOT FOUND OR p_outcome NOT IN ('ok', 'denied') THEN
        RAISE EXCEPTION 'required-header open confirmation refused' USING ERRCODE = '23514';
    END IF;
    SELECT * INTO v_attempt FROM secret_access_log
     WHERE id = p_audit AND operation_id = p_audit AND verb = 'open'
       AND program_id = v_auth.program_id AND tool_run_id = v_auth.tool_run_id
       AND scope_kind = 'program' AND field = 'header_slot'
       AND outcome = 'attempted';
    IF NOT FOUND THEN
        RAISE EXCEPTION 'required-header open audit attempt changed' USING ERRCODE = '23514';
    END IF;
    INSERT INTO secret_access_log(
        operation_id, verb, scope_kind, scope_id, kek_gen, program_id,
        tool_run_id, field, outcome, detail
    ) VALUES (
        p_audit, v_attempt.verb, v_attempt.scope_kind, v_attempt.scope_id,
        v_attempt.kek_gen, v_attempt.program_id, v_attempt.tool_run_id,
        v_attempt.field, p_outcome,
        CASE p_outcome
            WHEN 'ok' THEN 'proxy opened every required-header value it was sent'
            ELSE 'proxy refused unauthenticated required-header material'
        END
    );
END $fn$;


-- ---------------------------------------------------------------------------
-- Who may do what
-- ---------------------------------------------------------------------------
-- The same three roles the Identity slot table shuts out, and for the same
-- reason: `rk2_state` is the agent's read surface and a value it can select is a
-- value the model has; `rk2_proxy` reads through the capability-gated function
-- so that every open is on the access log; `rk2_human` reviews decisions and has
-- no business with the material behind one.
--
-- `rk2_runtime` keeps the standing grant 0029 gives every managed table. It is
-- the connection `rk header provision` writes through, and the role catalogue
-- requires read/write there on every public table -- an exception would be a
-- red standing check for a secrecy property this table does not have anyway,
-- because the value is an authenticated ciphertext and the key is not in the
-- database.

REVOKE ALL ON program_header_slots FROM PUBLIC;
REVOKE ALL ON program_header_slots FROM rk2_state, rk2_proxy, rk2_human;

REVOKE ALL ON FUNCTION assert_header_slot_state(jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION header_slot_keying(uuid,text,bytea,bytea) FROM PUBLIC;
REVOKE ALL ON FUNCTION confirm_header_root_check(uuid,text,uuid,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION provision_header_slot(uuid,text,bigint,jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION open_required_headers(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION confirm_required_headers_open(text,uuid,text) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION header_slot_keying(uuid,text,bytea,bytea),
    confirm_header_root_check(uuid,text,uuid,text),
    provision_header_slot(uuid,text,bigint,jsonb) TO rk2_runtime;

GRANT EXECUTE ON FUNCTION open_required_headers(text),
    confirm_required_headers_open(text,uuid,text) TO rk2_proxy;


-- ---------------------------------------------------------------------------
-- The standing rule
-- ---------------------------------------------------------------------------
-- One arm on the check that already owns required headers, rather than a new
-- family: it is a statement about a compiled scope policy, and an operator
-- reading `scope_policy` is already reading about this Program's headers.
--
-- What is deliberately NOT an arm: "declared and not provisioned". That is a
-- Program the door refuses on every request, which sounds like a gate failure
-- and is not one -- the gate states invariants over canonical state, and a
-- secret that has not arrived yet is an operator's next step rather than a
-- broken record. Making it fail the gate would also mean a correctly configured
-- Program cannot pass its first `rk run`, which is the run that has to create
-- the Program before `rk header provision` can resolve it. The Identity slot
-- makes the same call for the same reason. The refusal is at the door, under its
-- own decision token, and every attempt is on the secret access log.

CREATE OR REPLACE FUNCTION check_scope_policy()
RETURNS TABLE (problem text, object text, detail text)
LANGUAGE sql STABLE AS $$
    -- 1. A Program that compiled a policy and is running none. Every entity
    --    projects to denied, which is safe and is also indistinguishable from
    --    a policy that lists nothing -- the operator wrote a scope and the
    --    harness is not enforcing it.
    SELECT 'scope_version_missing', p.slug,
           'the Program has ' || count(v.version) || ' compiled version(s) and runs none'
      FROM programs p
      LEFT JOIN program_scope_versions v ON v.program_id = p.id
     WHERE p.scope_version IS NULL AND p.closed_at IS NULL
     GROUP BY p.id, p.slug
    HAVING count(v.version) > 0
  UNION ALL
    -- 2. The live version is not the newest configuration compiled.
    SELECT 'scope_version_not_current', p.slug,
           'live scope version ' || p.scope_version || ' compiled from revision ' ||
           coalesce(sv.configuration_revision::text, '(none)') ||
           ', but the newest configuration revision is ' || c.revision
      FROM programs p
      JOIN program_scope_versions sv
        ON sv.program_id = p.id AND sv.version = p.scope_version
      JOIN LATERAL (SELECT revision FROM program_configurations
                     WHERE program_id = p.id
                     ORDER BY revision DESC LIMIT 1) c ON true
     WHERE sv.configuration_revision IS DISTINCT FROM c.revision
  UNION ALL
    -- 3. The compiled policy does not name the bytes it was compiled from.
    SELECT 'scope_policy_digest_mismatch', p.slug || ' version ' || sv.version,
           'policy states configuration_sha256 ' ||
           coalesce(sv.policy->>'configuration_sha256', '(none)') ||
           ' but revision ' || c.revision || ' hashes to ' || c.canonical_sha256
      FROM programs p
      JOIN program_scope_versions sv
        ON sv.program_id = p.id AND sv.version = p.scope_version
      JOIN program_configurations c
        ON c.program_id = p.id AND c.revision = sv.configuration_revision
     WHERE sv.policy->>'configuration_sha256' IS DISTINCT FROM c.canonical_sha256
  UNION ALL
    -- 4. A required header's value reference became readable. The grant is the
    --    redaction; check_state_grants() enforces the registry, and this rule
    --    enforces what may enter it.
    SELECT 'header_value_is_readable', 'program_required_headers.' || s.column_name,
           'the agent read surface must carry header names only; the reference resolves to a runtime-owned secret'
      FROM state_read_surface s
     WHERE s.table_name = 'program_required_headers'
       AND s.column_name = 'value_ref'
  UNION ALL
    -- 5. A live version with no rules. Deny-by-default makes this safe and
    --    silent: the Program looks configured, every request is refused as
    --    `unlisted`, and the reason is that the compiler wrote a header row
    --    and no body.
    SELECT 'scope_version_has_no_rules', p.slug || ' version ' || sv.version,
           'the live scope version compiled to zero rules; every address is denied as unlisted'
      FROM programs p
      JOIN program_scope_versions sv
        ON sv.program_id = p.id AND sv.version = p.scope_version
     WHERE NOT EXISTS (SELECT 1 FROM program_scope_rules r
                        WHERE r.program_id = sv.program_id
                          AND r.version = sv.version)
  UNION ALL
    -- 6. A required header's value became readable through the slot table. The
    --    declaration's `value_ref` is a pointer and rule 4 keeps it off the read
    --    surface; this is the thing it points at, and one grant would undo both.
    --    `rk2_runtime` is absent by design -- it is the provisioning connection,
    --    the same exception `identity_slots` makes.
    SELECT 'header_slot_is_readable', 'program_header_slots to ' || r.name,
           'the provisioned header value is off the agent read surface and reachable only through open_required_headers'
      FROM (VALUES ('rk2_state'), ('rk2_proxy'), ('rk2_human')) AS r(name)
     WHERE has_table_privilege(r.name, 'program_header_slots', 'SELECT')
$$;

COMMENT ON FUNCTION check_scope_policy() IS
  'Every Program that compiled a policy runs the compiled form of its newest revision, the compiled form names the bytes it came from and has rules, and no required-header value is readable by the agent.';

UPDATE standing_checks
   SET note = 'the live scope version is the newest configuration compiled, it names the bytes it came from, and required-header values stay off the agent read surface'
 WHERE name = 'scope_policy';


DO $$
DECLARE n integer; d text;
BEGIN
    IF has_table_privilege('rk2_state', 'program_header_slots', 'SELECT')
       OR has_table_privilege('rk2_human', 'program_header_slots', 'SELECT')
       OR has_table_privilege('rk2_proxy', 'program_header_slots', 'SELECT') THEN
        RAISE EXCEPTION
            'an agent-facing role can read program_header_slots; the header '
            'value is reachable only through the capability-gated function';
    END IF;
    IF NOT has_function_privilege('rk2_proxy', 'open_required_headers(text)', 'EXECUTE') THEN
        RAISE EXCEPTION
            'rk2_proxy cannot open required headers; the door would send every '
            'request without the identifier the Program requires';
    END IF;

    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_scope_policy();
    IF n > 0 THEN
        RAISE EXCEPTION 'scope policy invariants broken (% problems): %', n, d;
    END IF;
END $$;
