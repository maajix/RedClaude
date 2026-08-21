-- ---------------------------------------------------------------------------
-- 20260923T000000Z__the_runtime_takes_its_own_transport_measurement.sql
--                                                                   (ticket 93)
--
-- 025 built `receipts.transport_citable` over `purpose = 'transport_measurement'`
-- and no writer has ever set that purpose: 021 gives the column a default of
-- `target_traffic`, `write_allowed_receipt` does not name it in its INSERT, and
-- `grep purpose src/redkraken/proxy.py` finds prose. So one side of the argument
-- 025 records has been in the schema since 025 and the other side has never been
-- made. This is the lane, and the trust decision the lane could not be walked
-- without.
--
-- THE MEASUREMENT IS A SECOND SOCKET, NOT A SECOND ROW ABOUT THE FIRST.
--
-- 025 is explicit that a measurement adds no listener and no lane: "it is the
-- same proxy process opening the connection itself", and "one egress path
-- survives; what changes is who terminates the TLS". The tempting reading is
-- that the upstream half of an intercepted exchange already *is* an
-- unintercepted handshake -- the door dialled it, against the system store, on
-- its own socket -- so a second row over the same handshake would cost nothing.
-- It is the wrong reading. On that connection the door is carrying an agent's
-- request, so `receipts_served_transport_needs_tool_run` would be satisfied by
-- the agent's own Tool run, and a probe filed under the Tool run of the party it
-- is evidence against is exactly the attribution 042 exists to refuse. The door
-- therefore opens its own connection, under its own Tool run, and terminates
-- the TLS itself with nobody downstream. `intercepted = false` on that row is
-- then a fact about the socket rather than a claim about it.
--
-- THE TRUST ANCHOR, WHICH IS THE DECISION THIS TICKET OWES.
--
-- 025 says the chain is "verified against the SYSTEM trust store rather than the
-- run CA". That is right for a live target and settles nothing for a fixture:
-- `evaluation.served` mints an authority per call into a directory that dies
-- with the context manager, so a fixture leaf verifies against nothing this
-- machine holds, and 88 recorded that as ticket 93's to answer.
--
-- The answer is the first of the two the ticket offers: THE EVALUATOR'S PER-RUN
-- AUTHORITY IS A TRUST ANCHOR FOR THE MEASUREMENT OF THE PROGRAM IT WAS MINTED
-- FOR, AND FOR NO OTHER. The reason is that the second option makes the class
-- ungradeable rather than honest. A fixture measurement recorded unverified is
-- never citable, `transport.tls_configuration` is `probe_only` over exactly the
-- three fields only a measurement carries, and 88 shipped the pair precisely so
-- that the class could be graded -- so choosing "unverified on purpose" would
-- ship a fixture that can only ever produce the negative half of its own pair.
--
-- What makes the anchor narrow enough to be one is where it is kept.
-- `fixture_addresses` is keyed by `program_id`, holds one row per evaluation
-- Program, is read only by `authorize_fixture_address` for the one host and port
-- that Program serves, and is cascaded away when the Program is purged. An
-- anchor stored there cannot vouch for a second Program, for a second host, or
-- for anything at all after the evaluation ends. Every other target on this
-- door still verifies against the system store, because every other target
-- reaches `connect` with no anchor to use.
--
-- The run CA is still not a trust anchor, and the distinction is the one 025
-- draws: the run CA signs the leaf the AGENT sees, so trusting it would make the
-- door's own forgery verifiable and every intercepted exchange citable. The
-- fixture authority signs the leaf the DOOR sees, on the far side, and the door
-- is the party taking the measurement.
--
-- `scope_class` moves for the same reason the anchor exists. 025's shape
-- constraint required `scope_class = 'target'`, written when `target` was the
-- only class a served exchange could carry; 20260914 added `fixture` for the
-- synthetic target the harness starts for an evaluation, and a measurement of
-- one is the case this ticket exists to make. The clause is widened to those two
-- and no further: `egress_support`, `control_plane` and `denied` still cannot
-- carry a measurement.
--
-- Depends on 0025 (the purpose, the columns and the citability), 20260914 (the
-- fixture address and the fourth class) and 20260922T060000Z (the https
-- fixture). A new file rather than an edit to any of them: a recorded migration
-- whose file has changed is schema drift and `rk db migrate` refuses the whole
-- corpus for it.
-- ---------------------------------------------------------------------------


-- ===========================================================================
-- 1. The anchor, on the row that already scopes a fixture to one Program
-- ===========================================================================

ALTER TABLE fixture_addresses ADD COLUMN trust_anchor text;

-- Both directions. An https fixture with no anchor is a fixture whose
-- measurement can never verify, which is the state this migration exists to
-- leave; an http fixture with one is an anchor for a handshake that does not
-- happen, and an unused trust anchor is the kind of row that is later read as
-- permission for something else.
ALTER TABLE fixture_addresses ADD CONSTRAINT fixture_addresses_anchor_iff_https
    CHECK ((trust_anchor IS NOT NULL) = (protocol = 'https'));

-- A certificate and not a key. The evaluator holds both -- `tls.authority`
-- writes `ca.pem` beside `ca-key.pem` -- and handing this column the private
-- half would put a signing key in a table the door reads on every request.
ALTER TABLE fixture_addresses ADD CONSTRAINT fixture_addresses_anchor_is_a_certificate
    CHECK (trust_anchor IS NULL
           OR (trust_anchor LIKE '-----BEGIN CERTIFICATE-----%'
               AND trust_anchor NOT LIKE '%PRIVATE KEY%'));

COMMENT ON COLUMN fixture_addresses.trust_anchor IS
 'The PEM certificate of the authority `evaluation.served` minted for this '
 'fixture, and the only anchor a transport measurement of it verifies against. '
 'Scoped to one Program by this table''s primary key and purged with it: it '
 'vouches for the one host and port this row names and for nothing else. NULL '
 'for a cleartext fixture, which has no handshake to verify.';


-- ===========================================================================
-- 2. The opener admits it, and the reader hands it to the door
-- ===========================================================================

-- Dropped and recreated rather than replaced: an argument is being added, and
-- `CREATE OR REPLACE` cannot change a function's arity. The body is 88's with
-- one parameter and one INSERT column added.
DROP FUNCTION open_fixture_address(uuid, text, text, integer, text);

CREATE FUNCTION open_fixture_address(
    p_program      uuid,
    p_protocol     text,
    p_host         text,
    p_port         integer,
    p_address      text,
    p_trust_anchor text
) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE
    v_version integer;
    v_host    text;
    v_address inet;
    v_class   text;
BEGIN
    PERFORM 1 FROM evaluation_programs e WHERE e.program_id = p_program;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'program % is not marked as an evaluation', p_program
          USING HINT = 'mark it in evaluation_programs first; a fixture address '
                       'belongs to a Program that exists to grade a Playbook',
                ERRCODE = '23514';
    END IF;

    IF p_protocol IS NULL OR p_protocol NOT IN ('http', 'https') THEN
        RAISE EXCEPTION 'a fixture is served over http or https, not %',
            coalesce(p_protocol, '<null>') USING ERRCODE = '23514';
    END IF;
    IF p_port IS NULL OR p_port < 1 OR p_port > 65535 THEN
        RAISE EXCEPTION 'a fixture address states no port in 1-65535'
            USING ERRCODE = '23514';
    END IF;

    -- Ticket 93. Said here as a sentence rather than left to the check
    -- constraint, for 88's reason: this function refusing anonymously is what
    -- 078 wrote it to avoid, and "an https fixture is measured against its own
    -- authority" is a rule a caller can act on where "violates
    -- fixture_addresses_anchor_iff_https" is not.
    IF (p_trust_anchor IS NOT NULL) <> (p_protocol = 'https') THEN
        RAISE EXCEPTION
            'an https fixture address carries the authority its handshake is '
            'measured against, and an http one carries none'
          USING DETAIL = 'protocol ' || p_protocol || ', anchor '
                         || CASE WHEN p_trust_anchor IS NULL THEN 'absent'
                                 ELSE 'present' END,
                ERRCODE = '23514';
    END IF;

    -- The policy's own spelling of the name, so that what is stored is what
    -- `authorize_fixture_address` will be asked about: the door canonicalises
    -- the request and this function canonicalises the fixture address, and two
    -- normalisers over one name is the differential this schema keeps avoiding.
    v_host := scope_normalize_host(p_host);
    IF v_host IS NULL THEN
        RAISE EXCEPTION 'a fixture address states no host' USING ERRCODE = '23514';
    END IF;

    BEGIN
        v_address := p_address::inet;
    EXCEPTION WHEN invalid_text_representation THEN
        RAISE EXCEPTION 'a fixture address states no address: %',
            coalesce(p_address, '<null>') USING ERRCODE = '23514';
    END;

    SELECT p.scope_version INTO v_version FROM programs p WHERE p.id = p_program;
    IF v_version IS NULL THEN
        RAISE EXCEPTION 'program % has no compiled scope to check a fixture address against',
            p_program USING ERRCODE = '23514';
    END IF;

    -- The coverage question, the same one `authorize_egress_address` asks: this
    -- is about the machine the fixture is on, not about a path. `target` and
    -- nothing weaker -- an `egress_support` host is somewhere the harness may
    -- talk to on its own business, and a Playbook is not graded against one.
    SELECT s.scope_class INTO v_class
      FROM scope_class_of(p_program, v_version, v_host, p_port,
                          '/', '/', p_protocol, 'coverage') s;
    IF coalesce(v_class, 'denied') <> 'target' THEN
        RAISE EXCEPTION 'the scope of program % does not class %:% as a target',
            p_program, v_host, p_port
          USING DETAIL = 'a fixture address changes the address a target is dialled at; '
                         'it does not make something a target',
                ERRCODE = '23514';
    END IF;

    INSERT INTO fixture_addresses (program_id, protocol, host, port, address, trust_anchor)
    VALUES (p_program, p_protocol, v_host, p_port, v_address, p_trust_anchor);
END $fn$;

COMMENT ON FUNCTION open_fixture_address(uuid, text, text, integer, text, text) IS
 'Records where an evaluation Program''s fixture is listening, on the scheme it '
 'was actually bound on, with the authority its handshake is measured against. '
 'Refuses a Program that is not an evaluation, a scheme that is neither http nor '
 'https, an anchor that does not match the scheme, a host its own policy does '
 'not class as a target, and any address that is not one private host.';

-- Also dropped and recreated: a column is being added to the result, and
-- `CREATE OR REPLACE` cannot change a function's return type either.
DROP FUNCTION authorize_fixture_address(text, text, text, integer);

CREATE FUNCTION authorize_fixture_address(
    p_capability text,
    p_protocol   text,
    p_host       text,
    p_port       integer
) RETURNS TABLE (
    address      text,
    scope_class  text,
    trust_anchor text
)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE
    v_auth    record;
    v_host    text;
    v_row     record;
    v_version integer;
    v_class   text;
BEGIN
    SELECT * INTO v_auth FROM resolve_egress_identity(p_capability);
    IF NOT FOUND THEN
        RAISE EXCEPTION 'egress capability refused' USING ERRCODE = '23514';
    END IF;

    v_host := scope_normalize_host(p_host);
    SELECT host(e.address) AS address, e.trust_anchor INTO v_row
      FROM fixture_addresses e
     WHERE e.program_id = v_auth.program_id
       AND e.protocol = p_protocol
       AND e.host = v_host
       AND e.port = p_port;
    IF v_row IS NULL THEN
        RETURN;
    END IF;

    SELECT p.scope_version INTO v_version FROM programs p WHERE p.id = v_auth.program_id;
    SELECT s.scope_class INTO v_class
      FROM scope_class_of(v_auth.program_id, v_version, v_host, p_port,
                          '/', '/', p_protocol, 'coverage') s;
    IF coalesce(v_class, 'denied') <> 'target' THEN
        RAISE EXCEPTION 'the scope of program % no longer classes %:% as a target',
            v_auth.program_id, v_host, p_port
          USING DETAIL = 'a recorded fixture address is where a target is dialled, '
                         'not a standing permission to dial it',
                ERRCODE = '23514';
    END IF;

    RETURN QUERY SELECT v_row.address, 'fixture'::text, v_row.trust_anchor;
END $fn$;

COMMENT ON FUNCTION authorize_fixture_address(text, text, text, integer) IS
 'The address an evaluation''s fixture is listening at, for the one host and port '
 'the request named, or no row at all. Refuses a lapsed capability, a lapsed '
 'Identity lease and a host this Program''s scope no longer classes as a target. '
 'The door dials what this answers with and pins it on the Receipt, and measures '
 'the handshake against the anchor it answers with and against nothing else; '
 'everything else resolves the name as it always did.';

REVOKE ALL ON FUNCTION
    open_fixture_address(uuid, text, text, integer, text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION
    authorize_fixture_address(text, text, text, integer) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION
    open_fixture_address(uuid, text, text, integer, text, text) TO rk2_runtime;
GRANT EXECUTE ON FUNCTION
    authorize_fixture_address(text, text, text, integer) TO rk2_proxy;

-- The declared surface follows the signature. `runtime_verb_surface` is checked
-- both ways -- a granted verb with no row and a row naming no verb both fail the
-- gate -- so the old identity text has to go with the old function.
DELETE FROM runtime_verb_surface
 WHERE verb = 'open_fixture_address(uuid, text, text, integer, text)';

INSERT INTO runtime_verb_surface (verb, added_by, note) VALUES
    ('open_fixture_address(uuid, text, text, integer, text, text)', '93',
     'records where an evaluation Program''s fixture is listening and the authority its transport measurement verifies against');


-- ===========================================================================
-- 3. A measurement of a fixture is a measurement of a target
-- ===========================================================================

ALTER TABLE receipts DROP CONSTRAINT receipts_transport_measurement_shape;
ALTER TABLE receipts ADD CONSTRAINT receipts_transport_measurement_shape CHECK (
    purpose <> 'transport_measurement' OR (
        lane = 'proxy_internal'
        AND intercepted = false
        AND agent_tls_version IS NULL AND agent_cipher IS NULL
        AND agent_alpn IS NULL AND agent_cert_sha256 IS NULL
        AND agent_cert_issuer IS NULL AND agent_cert_subject IS NULL
        AND agent_cert_not_after IS NULL
        AND interception_ca_id IS NULL
        -- 025 wrote `= 'target'` when a served exchange had no other class to
        -- carry. 20260914 added `fixture`, which is a target the harness started
        -- rather than a weaker permission, and grading the one class that can
        -- only be settled by a measurement is what that fixture is for. The
        -- three classes this still excludes are the ones it excluded before:
        -- `egress_support` is the harness's own business, `control_plane` is not
        -- a target at all, and `denied` never left the door.
        AND scope_class IN ('target', 'fixture')));


-- ===========================================================================
-- 4. The writer
-- ===========================================================================

-- One function rather than a widened `write_allowed_receipt`, and one call
-- rather than two, because of what the door is allowed to do. `rk2_proxy` holds
-- EXECUTE on writers and no DML on `receipts` or `tool_runs` at all -- that
-- split is ticket 66's, and a door that could INSERT its own Tool run could
-- mint the provenance for any receipt it liked. So the Tool run the probe is
-- filed under is opened here, in the same transaction as the row that cites it,
-- by the only party that may open one.
--
-- The Tool run is `transport = 'runtime'` with a NULL `tool_use_id`, which is
-- what 025's `receipts_served_transport_needs_tool_run` names in its comment and
-- what 022 already spells as a constraint, and it carries no `agent_run_id`:
-- there is no Agent run, because no agent asked for this. It is opened already
-- finished, because it is: the handshake is over by the time the door has
-- anything to file.
--
-- Nothing here may be taken from the caller except the wire. `purpose`, `lane`,
-- `decision` and `intercepted` are assigned rather than read, so the four
-- columns citability turns on are not four more things a door could be talked
-- into writing, and every `agent_*` column is cleared rather than checked, so a
-- payload that names one is a payload whose agent side is dropped rather than a
-- refusal the door has to handle mid-request.
CREATE FUNCTION record_transport_measurement(p_capability text, p_receipt jsonb)
RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public
AS $fn$
DECLARE
    v_auth          record;
    v_receipt       receipts%ROWTYPE;
    v_scope_version integer;
    v_tool_run      uuid;
    v_label         text;
BEGIN
    IF p_capability IS NULL
       OR coalesce(jsonb_typeof(p_receipt), 'null') <> 'object' THEN
        RAISE EXCEPTION 'egress capability refused' USING ERRCODE = '23514';
    END IF;
    -- 20260815's rule, for the same reason: a receipt payload that quotes the
    -- capability would put a live credential in a table the state role reads.
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

    PERFORM set_actor('runtime');
    INSERT INTO tool_runs (program_id, tool, args, status, finished_at, transport)
    VALUES (
        v_auth.program_id,
        'rk2.transport_measurement',
        jsonb_build_object(
            'scheme', v_receipt.scheme,
            'host', v_receipt.host,
            'port', v_receipt.port),
        'success', clock_timestamp(), 'runtime')
    RETURNING id INTO v_tool_run;

    v_receipt.id := uuidv7();
    v_receipt.program_id := v_auth.program_id;
    v_receipt.label := '';
    v_receipt.tool_run_id := v_tool_run;
    v_receipt.purpose := 'transport_measurement';
    v_receipt.lane := 'proxy_internal';
    v_receipt.decision := 'allowed';
    v_receipt.intercepted := false;
    v_receipt.scope_version := v_scope_version;
    v_receipt.ts_arrival := coalesce(v_receipt.ts_arrival, clock_timestamp());
    v_receipt.agent_tls_version := NULL;
    v_receipt.agent_cipher := NULL;
    v_receipt.agent_alpn := NULL;
    v_receipt.agent_cert_sha256 := NULL;
    v_receipt.agent_cert_issuer := NULL;
    v_receipt.agent_cert_subject := NULL;
    v_receipt.agent_cert_not_after := NULL;
    v_receipt.interception_ca_id := NULL;

    INSERT INTO receipts (
        id, program_id, label, tool_run_id, lane, decision, purpose, reason,
        method, scheme, host, port, path, pinned_ips,
        ts_arrival, ts_egress, waited_ms, notes, scope_version, scope_class,
        intercepted, wire_tls_version, wire_cipher, wire_alpn,
        wire_cert_sha256, wire_cert_issuer, wire_cert_subject,
        wire_cert_not_after, wire_sni, wire_chain_verified,
        wire_hostname_verified
    ) VALUES (
        v_receipt.id, v_receipt.program_id, v_receipt.label,
        v_receipt.tool_run_id, v_receipt.lane, v_receipt.decision,
        v_receipt.purpose, v_receipt.reason,
        v_receipt.method, v_receipt.scheme, v_receipt.host, v_receipt.port,
        v_receipt.path, v_receipt.pinned_ips,
        v_receipt.ts_arrival, v_receipt.ts_egress, v_receipt.waited_ms,
        v_receipt.notes, v_receipt.scope_version, v_receipt.scope_class,
        v_receipt.intercepted, v_receipt.wire_tls_version, v_receipt.wire_cipher,
        v_receipt.wire_alpn, v_receipt.wire_cert_sha256,
        v_receipt.wire_cert_issuer, v_receipt.wire_cert_subject,
        v_receipt.wire_cert_not_after, v_receipt.wire_sni,
        v_receipt.wire_chain_verified, v_receipt.wire_hostname_verified
    )
    RETURNING label INTO v_label;
    RETURN v_label;
END $fn$;

COMMENT ON FUNCTION record_transport_measurement(text, jsonb) IS
 'Ticket 93. Files one unintercepted handshake the door took on its own behalf: '
 'opens the runtime Tool run the probe is attributed to and writes the Receipt '
 'that cites it, with purpose, Lane, decision and interception assigned here '
 'rather than read from the caller. What the caller supplies is the wire side of '
 'the handshake and where it was taken; `transport_citable` follows from that '
 'and is writable by nobody.';

REVOKE ALL ON FUNCTION record_transport_measurement(text, jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION record_transport_measurement(text, jsonb) TO rk2_proxy;


-- ===========================================================================
-- 5. The one rule that has been contradicting 025 since 025
-- ===========================================================================
--
-- 007's decision 15 -- "the proxy fetching its own CSRF tokens is not anybody's
-- observation" -- refuses any Receipt on the `proxy_internal` Lane as the
-- provenance of an Observation. 025 then added `transport_parameters_observed`,
-- admitted it under `receipt` provenance only, and required that Receipt to be
-- `transport_citable`, which requires `purpose = 'transport_measurement'`, which
-- its own shape constraint requires to be on the `proxy_internal` Lane.
--
-- So the two rules have been unsatisfiable together since the day 025 shipped,
-- and nothing noticed because the writer that would have collided with them did
-- not exist: `transport_parameters_observed` had no admissible Receipt to point
-- at, so nobody ever wrote one. This ticket is where that stops being latent,
-- which is why the repair belongs here rather than in a file of its own.
--
-- Decision 15 keeps everything it was for. What the proxy does on its own
-- account -- a fetched token, a preflight, a redirect it followed for itself --
-- is still not evidence, because none of it is a measurement and none of it is
-- citable. The one thing that changes is the case 025 built the column for: a
-- Receipt whose `transport_citable` is true is the door reporting a handshake it
-- took on purpose, under a Tool run opened to say so, and it is the only
-- evidence this design can produce for a `probe_only` class.
--
-- Read off `transport_citable` rather than off `purpose`, deliberately. The
-- generated column is the one nobody can write, so what this guard admits is
-- exactly the set the rest of 025 admits, and a later migration that widened
-- `purpose` would not widen this.
CREATE OR REPLACE FUNCTION reject_proxy_internal_evidence() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE r receipts;
BEGIN
    IF NEW.receipt_id IS NOT NULL THEN
        SELECT * INTO r FROM receipts WHERE id = NEW.receipt_id;
        IF r.lane = 'proxy_internal' AND NOT r.transport_citable THEN
            RAISE EXCEPTION 'receipt % is lane proxy_internal and cannot back an observation',
                NEW.receipt_id;
        END IF;
    END IF;
    RETURN NEW;
END $$;

-- The transition guard is not touched, and the difference is worth stating
-- because the two read alike. `hypothesis_transition_refusal` asks about the
-- Receipt a TRANSITION cites -- the one a Test run produced -- and a measurement
-- is never that: it sends no request, so no replay produces it and
-- `requires_test_linked_receipt` would refuse it for a reason of its own. What a
-- measurement backs is the EVIDENCE, through the Observation this function
-- guards, and the promotion then rests on it transitively. Decision 15 stands
-- unchanged over transitions.


-- ===========================================================================
-- 6. What this migration claims, asserted
-- ===========================================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conrelid = 'receipts'::regclass
           AND conname = 'receipts_transport_measurement_shape'
           AND pg_get_constraintdef(oid) LIKE '%fixture%'
    ) THEN
        RAISE EXCEPTION 'ticket 93: a measurement of a fixture is still unwritable';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_attribute
         WHERE attrelid = 'fixture_addresses'::regclass
           AND attname = 'trust_anchor' AND attnum > 0
    ) THEN
        RAISE EXCEPTION 'ticket 93: a fixture address carries no trust anchor';
    END IF;

    -- The citability expression is what every one of these serves, and it is
    -- generated: if some later migration made it writable, the whole of 025 and
    -- the whole of this file would be decoration. 025 ships
    -- `check_transport_claims()`'s `citability_writable` arm for the same
    -- reason; this is the assertion at the moment the writer arrives.
    IF NOT EXISTS (
        SELECT 1 FROM pg_attribute
         WHERE attrelid = 'receipts'::regclass
           AND attname = 'transport_citable' AND attgenerated = 's'
    ) THEN
        RAISE EXCEPTION 'ticket 93: transport_citable is no longer generated';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_proc
         WHERE proname = 'record_transport_measurement'
           AND has_function_privilege('rk2_proxy', oid, 'EXECUTE')
    ) THEN
        RAISE EXCEPTION 'ticket 93: the door cannot file a measurement';
    END IF;

    -- And the split that made it one function: the door files through verbs and
    -- holds no DML of its own. A grant here would be the privilege this file
    -- argues it does not need.
    IF has_table_privilege('rk2_proxy', 'tool_runs', 'INSERT')
       OR has_table_privilege('rk2_proxy', 'receipts', 'INSERT') THEN
        RAISE EXCEPTION 'ticket 93: the door was given the DML the writer exists to avoid';
    END IF;
END $$;
