-- ---------------------------------------------------------------------------
-- 20260925T030000Z__a_secret_read_names_the_exchange.sql
--                                                                  (ticket 123)
--
-- `secret_access_log.receipt_id` has been in the schema since `0024` and no
-- statement has ever set it. Thirteen writers put rows in that table, and every
-- one of them left the column NULL: the trail can say that a credential was
-- read, whose Program read it, under which key generation and on which Tool run,
-- and it cannot say which request it was read for.
--
-- WHY THAT LAST DISTINCTION IS THE ONE WORTH BUILDING
--
-- Six of the thirteen already carry `tool_run_id`, and a reader who stops there
-- concludes the trail is attributed. It is attributed to a run. A Tool run is one
-- capability, one lease and one budget, and it makes as many requests as the
-- fence allows; the question a credential audit exists to answer is which of
-- them carried the value. `receipts` is the row that names an exchange, and this
-- column is the only edge between the two tables. Until it is written the audit
-- answers a coarser question than the one it was built for, and answers it in a
-- way that reads as though it had answered the finer one.
--
-- WHAT THIS FILE LEAVES ALONE, SAID HERE SO IT IS NOT REDISCOVERED
--
-- The wiring report that found this column lists it beside four others of the
-- same table and presents all five as one gap. Four of them are not defects.
--
-- `peer_pid`, `peer_uid` and `peer_exe` exist to record what a keyholder reads
-- off `SO_PEERCRED` about somebody else. Every writer in this corpus is writing
-- about itself, and a process filling those three in about itself is recording a
-- claim it could have made up. `src/redkraken/artifact.py` has said so in a
-- comment since ticket 07, and the decision stands.
--
-- `dek_gen` numbers a wrapped data key. Ticket 07 replaced the envelope `0024`
-- designed with a key derived per Program and per generation from a file the
-- operator names on the command line, `artifact_seal` seals against `secret_kek`
-- directly, and `check_wire_artifact_secrecy` grades a row in `secret_dek` a
-- violation rather than an absence. There is no data key to number, and a writer
-- for that column would have to put back the design that was removed first.
--
-- WHICH OF THE THIRTEEN NAME AN EXCHANGE NOW
--
-- Three, and which three is decided by when each row is written rather than by
-- what each writer knows.
--
-- `record_proxy_exchange` audits the wire seals of an exchange and then mints
-- that exchange's Receipt a few lines later. It had the Receipt all along and
-- had it in the wrong order; the two statements swap places here. Nothing is at
-- risk in the swap. This is one function in one transaction, so neither
-- statement outlives the other, and the "audit row before the thing it records"
-- ordering that `rk artifact open` keeps is kept there for a reason that does
-- not apply: that command writes a file the database cannot roll back, and this
-- one writes nothing it cannot.
--
-- `record_identity_proxy_exchange` audits the session state a target issued and
-- then delegates the Receipt to `record_proxy_exchange`. Same shape and the same
-- fix: the exchange is filed first, and the cookie jar's row cites it.
--
-- `src/redkraken/artifact.py` is the third, and it is the one that had to find
-- its Receipt rather than hold it. `rk artifact open` is an operator decrypting
-- stored wire bytes, possibly weeks later, with nothing but a label in hand. The
-- edge is already there and had never been read: a sealed wire artifact is filed
-- under the hash of its plaintext, and that hash is what the Receipt of the
-- exchange recorded as `request_wire_sha` or `response_wire_sha`. So the command
-- reads the exchange out of the store and every row it writes from the lookup
-- onwards names it, including the refusals -- which request an operator tried
-- and failed to open a credential for is the question an audit asks most often.
-- Two Receipts naming one artifact is identical bytes sent twice, and the answer
-- there is NULL: a back-link that is sometimes a guess is worth less than one
-- that is always a fact.
--
-- WHY THE OTHER TEN CANNOT
--
-- Four of them are the proxy-side opens, and they are the four that make this a
-- narrower fix than it looks. `open_identity_slot` and `open_required_headers`
-- write an `attempted` row, `confirm_identity_slot_open` and
-- `confirm_required_headers_open` write its terminal outcome, and all four run
-- while the request is still being built: before it is sent, before there is a
-- status code, and before anything has a Receipt to name. The pair could be
-- back-filled once the exchange lands, and deliberately is not.
-- `secret_access_log.operation_id` exists precisely so that the outcome of an
-- attempt is a second row rather than an edit of the first, and an audit table
-- that is UPDATE-ed to add a fact is an audit table that can be UPDATE-ed to
-- remove one. What ties those four rows to the exchange is the Tool run they
-- share with it and the order they were written in, which is weaker than a
-- foreign key and is the honest strength of what is actually known. Closing that
-- half means the door carrying its `audit_id` into the exchange writer, which is
-- a change to `src/redkraken/proxy.py` and a decision about append-only audit,
-- and neither belongs in a ticket whose finding was one NULL column.
--
-- The remaining six are control side. `identity_slot_keying`,
-- `confirm_identity_root_check`, `provision_identity_slot`,
-- `header_slot_keying`, `confirm_header_root_check` and `provision_header_slot`
-- run under `rk identity provision` and `rk header provision`, where an operator
-- is establishing key material before anything has been sent anywhere. There is
-- no exchange, and there is no request that a value has yet been used for.
--
-- No column, no constraint and no grant. The column is `0024`'s and has been
-- waiting for a writer; the two functions keep their signatures, so
-- `CREATE OR REPLACE` keeps their owner and their ACL, and this file asserts
-- that rather than restating the grants and hoping the two spellings agree. It
-- asserts the shape of the access list as well as its survival: the door reaches
-- `record_proxy_exchange` only through `record_identity_proxy_exchange`, because
-- `20260811T150000Z` revoked the direct EXECUTE when it added the wrapper, and a
-- replacement that handed the direct verb back would widen the door quietly. No
-- foreign key either: `secret_access_log.program_id` is `ON DELETE SET NULL`
-- because an access that happened is a fact a purge does not get to erase, and
-- an unconstrained `receipt_id` keeps the same property without a second
-- cascade edge to declare.
--
-- Depends on `0024` (the column), `20260811T140000Z` (the exchange writer) and
-- `20260811T150000Z` (the Identity exchange writer). A new file rather than an
-- edit to any of them: a recorded migration whose file has changed is schema
-- drift and `rk db migrate` refuses the whole corpus for it.
-- ---------------------------------------------------------------------------


-- ===========================================================================
-- 1. The exchange writer mints the Receipt before it audits the seals
-- ===========================================================================

-- Verbatim from `20260811T140000Z__sealed_proxy_response_views.sql` apart from
-- the two statements that change places and the column they add. Reproduced in
-- full because `CREATE OR REPLACE` takes a whole body and because a function
-- assembled out of a diff is a function nobody can read in one place.

CREATE OR REPLACE FUNCTION record_proxy_exchange(
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

    -- Ticket 123, and the only change in this function. The Receipt is minted
    -- before the rows that are about it, so each one can say which exchange the
    -- wire bytes it audits were the wire side of.
    v_id := write_allowed_receipt(p_capability, p_receipt);

    INSERT INTO secret_access_log(
        verb, scope_kind, scope_id, kek_gen, program_id, tool_run_id, receipt_id,
        field, value_len, value_fpr, outcome, detail
    )
    SELECT 'seal', 'program', v_program, s.kek_gen, v_program, v_tool_run, v_id,
           s.field, s.byte_size, decode(s.value_fpr_hex, 'hex'), 'ok',
           'proxy sealed a target response transformation'
      FROM jsonb_to_recordset(p_seals)
        AS s(byte_size bigint, kek_gen integer, value_fpr_hex text, field text);

    SELECT r.label INTO v_label FROM receipts r WHERE r.id = v_id;
    RETURN jsonb_build_object('receipt_id', v_id, 'label', v_label,
                              'tool_run_id', v_tool_run);
END $fn$;


-- ===========================================================================
-- 2. And the Identity exchange writer audits the session capture after it
-- ===========================================================================

-- Verbatim from `20260811T150000Z__encrypted_identity_slots.sql` apart from one
-- declaration, one moved INSERT and the column it adds. The delegated call now
-- has a name because its answer is needed twice: once for the Receipt the audit
-- row cites and once for the caller, which gets exactly what it got before.

CREATE OR REPLACE FUNCTION record_identity_proxy_exchange(
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
DECLARE
    v_auth record;
    v_receipt jsonb;
    v_written bigint;
    v_binding bigint;
    v_result jsonb;
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

    IF v_auth.identity_entity_id IS NOT NULL THEN
        IF p_expected_revision IS NULL THEN
            RAISE EXCEPTION 'Identity exchange has no opened slot revision'
                USING ERRCODE = '23514';
        END IF;
        SELECT s.binding_revision INTO v_binding FROM identity_slots s
          JOIN entities e ON e.id = s.identity_entity_id
         WHERE s.program_id = v_auth.program_id
           AND s.identity_entity_id = v_auth.identity_entity_id
           AND s.revision = p_expected_revision
           AND s.binding_revision = (e.metadata ->> 'configuration_revision')::bigint
         FOR UPDATE OF s, e;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'Identity slot revision changed during exchange'
                USING ERRCODE = '40001';
        END IF;
    END IF;

    IF p_state IS NOT NULL THEN
        PERFORM assert_identity_slot_state(p_state);
        IF (p_state ->> 'revision')::bigint <> p_expected_revision + 1
           OR (p_state ->> 'binding_revision')::bigint <> v_binding THEN
            RAISE EXCEPTION 'Identity slot revision or configuration binding changed'
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
           AND binding_revision = v_binding
        RETURNING revision INTO v_written;
        IF v_written IS NULL THEN
            RAISE EXCEPTION 'Identity slot revision changed during exchange'
                USING ERRCODE = '40001';
        END IF;
    END IF;

    -- Ticket 123. The exchange is filed before the session capture is audited,
    -- which is the whole of the change here: the Receipt does not exist until
    -- `record_proxy_exchange` has written it, and a row inserted before that
    -- could name nothing. The slot itself is still updated above, under the lock
    -- it was already taken with, so nothing about who wins a concurrent capture
    -- moves.
    v_result := record_proxy_exchange(p_capability, v_receipt, p_artifacts, p_seals);

    IF p_state IS NOT NULL THEN
        INSERT INTO secret_access_log(
            verb, scope_kind, scope_id, kek_gen, program_id, tool_run_id,
            receipt_id, field, value_len, value_fpr, outcome, detail
        ) VALUES (
            'seal', 'identity', v_auth.identity_entity_id,
            (p_state ->> 'kek_gen')::integer, v_auth.program_id,
            v_auth.tool_run_id, (v_result ->> 'receipt_id')::uuid, 'cookie_jar',
            (p_state ->> 'byte_size')::integer,
            decode(p_state ->> 'value_fpr_hex', 'hex'), 'ok',
            'proxy persisted target-issued Identity session state'
        );
    END IF;

    RETURN v_result;
END $fn$;


-- ===========================================================================
-- 3. What the column is for, on the column
-- ===========================================================================

COMMENT ON COLUMN secret_access_log.receipt_id IS
 'The exchange this access was made for, where there is one. Set by '
 '`record_proxy_exchange` and `record_identity_proxy_exchange`, which mint the '
 'Receipt in the same transaction, and by `rk artifact open`, which finds it by '
 'the wire hash the Receipt and the sealed artifact already share. NULL on the '
 'control-side verbs, which establish key material before anything has been '
 'sent, and on the proxy-side slot and header opens, which run before the '
 'request they are part of has a Receipt to name: those rows are tied to their '
 'exchange by `tool_run_id` and by nothing stronger. NULL also where two '
 'Receipts name one set of wire bytes, because a back-link that guesses between '
 'two requests records neither of them.';


-- ===========================================================================
-- 4. What this migration claims, asserted
-- ===========================================================================

DO $$
BEGIN
    -- The column this file exists to give a writer. Asserted first, because
    -- every claim below is a claim about a statement that names it.
    IF NOT EXISTS (
        SELECT 1 FROM pg_attribute
         WHERE attrelid = 'secret_access_log'::regclass
           AND attname = 'receipt_id' AND attnum > 0 AND NOT attisdropped
    ) THEN
        RAISE EXCEPTION 'ticket 123: secret_access_log has no receipt_id to write';
    END IF;

    IF pg_get_functiondef('record_proxy_exchange(text,jsonb,jsonb,jsonb)'::regprocedure)
       NOT LIKE '%tool_run_id, receipt_id%' THEN
        RAISE EXCEPTION 'ticket 123: the exchange writer still audits a seal without its Receipt';
    END IF;

    IF pg_get_functiondef(
           'record_identity_proxy_exchange(text,jsonb,jsonb,jsonb,text,bigint,jsonb)'::regprocedure)
       NOT LIKE '%receipt_id, field, value_len%' THEN
        RAISE EXCEPTION 'ticket 123: the Identity exchange writer still audits a capture without its Receipt';
    END IF;

    -- The order, which is the whole of the repair and the one thing a column
    -- list cannot show. A body that named the column and still wrote the row
    -- first would insert a NULL and pass every check above.
    IF position('write_allowed_receipt(p_capability'
                IN pg_get_functiondef(
                       'record_proxy_exchange(text,jsonb,jsonb,jsonb)'::regprocedure))
       > position('INSERT INTO secret_access_log'
                  IN pg_get_functiondef(
                         'record_proxy_exchange(text,jsonb,jsonb,jsonb)'::regprocedure)) THEN
        RAISE EXCEPTION 'ticket 123: the seal audit still precedes the Receipt it names';
    END IF;

    -- And the reason this file carries no GRANT. `CREATE OR REPLACE` keeps the
    -- owner and the access list of the function it replaces, which is a belief
    -- until something checks it, and a door that lost this privilege would lose
    -- every exchange it files.
    --
    -- Both directions, because what the door holds is narrower than the shape
    -- suggests. `20260811T150000Z` took `rk2_proxy` off `record_proxy_exchange`
    -- and left it on `record_identity_proxy_exchange` alone, so every exchange
    -- the door files goes through the Identity wrapper whether or not an
    -- Identity was selected. A replacement that quietly widened that reach would
    -- be a worse outcome than one that narrowed it.
    --
    -- The standing `capability_receipt_fence` asks both questions on every run
    -- already. This is not a second opinion about them; it is the assertion at
    -- the moment the two functions are replaced, which is the moment an access
    -- list is at risk and the one run where the standing check has not happened
    -- yet.
    IF NOT has_function_privilege(
               'rk2_proxy',
               'record_identity_proxy_exchange(text,jsonb,jsonb,jsonb,text,bigint,jsonb)',
               'EXECUTE') THEN
        RAISE EXCEPTION 'ticket 123: replacing the Identity exchange writer dropped the door''s EXECUTE';
    END IF;
    IF has_function_privilege(
           'rk2_proxy', 'record_proxy_exchange(text,jsonb,jsonb,jsonb)', 'EXECUTE') THEN
        RAISE EXCEPTION 'ticket 123: replacing the exchange writer widened what the door may call';
    END IF;
END $$;
