-- ===========================================================================
-- 025_ticket24_transport_claims.sql
--
-- Ticket 24 -- what an agent may claim about transport and TLS.
--
-- The measurement this migration is built on (ticket 04, and the matrix in
-- docs/prototype/scope-proxy/run_tls_local.sh re-run here): behind the interception
-- proxy the agent's TLS parameters are the PROXY's. Issuer and subject and
-- fingerprint and validity are the run CA's, always. ALPN is whatever the proxy
-- offered, which with an unpinned proxy can be `h2` when the origin only speaks
-- `http/1.1`. Version and cipher matched the origin in every cell measured --
-- BY COINCIDENCE, because the same OpenSSL with the same defaults sat on both
-- sides. None of it is evidence about the target.
--
-- Ticket 27 left this structurally unmakeable rather than merely unproven:
-- `receipts` carried no TLS columns at all, so `transport.tls_configuration`
-- and `transport.certificate_trust` could never reach `supported` because there
-- was nothing for an observation to point at. This migration is where that
-- changes, and the shape of the change is the answer to the ticket:
--
--   1. The gap is RECORDED, not inferred. Wire-side columns are separate from
--      client-side columns on the same row, and the divergence between them is
--      a generated column, so an intercepted receipt carries its own refutation.
--   2. Citability is a GENERATED column. Not a flag the proxy sets, not a field
--      a reviewer reads. Nobody -- not the agent, not the runtime, not the proxy
--      -- can write `transport_citable = true`.
--   3. A separate MEASUREMENT PURPOSE, not a separate egress path and not a
--      separate lane. `purpose = 'transport_measurement'` is the runtime's own
--      unintercepted handshake, taken through the same scope decision, the same
--      per-target concurrency slot and the same token bucket as agent traffic
--      (measured in the proxy prototype). One egress path survives; what
--      changes is who terminates the TLS.
--   4. Unmakeable classes are refused at INSERT with their mechanism, by a
--      trigger, before a triager ever sees the claim.
--
-- Depends on 001-022 and the canonical fixture. Applies after 018, not because
-- of numbering but because 018 must run after the fixture; see
-- tests/seed_vocab_reconcile.sql.
-- ===========================================================================

-- [ticket 33 consolidation] BEGIN;/COMMIT; removed: ./migrate.sh wraps every
-- migration in one transaction with its rk2_meta.schema_migrations row, and an
-- inner COMMIT would end that transaction early. Refused by ./migrate.sh lint.

-- ---------------------------------------------------------------------------
-- 1. receipts: two sides of the handshake, and a citability that is derived.
-- ---------------------------------------------------------------------------

-- The measurement purpose. Ticket 14 proved containment over plaintext and
-- handed TLS here; its topology is one proxy listener per program on that
-- program's lane address, and a measurement does not add a listener -- it is
-- the same proxy process opening the connection itself, with the target's real
-- certificate chain verified against the SYSTEM trust store rather than the run
-- CA.
--
-- So the causal Lane is already correct without touching it: the proxy acted as
-- a client of the target on its own behalf, which is `proxy_internal`. The
-- prototype instead invented a fifth Lane value, and the cost was that
-- `transport_citable` -- the whole point of this migration -- keyed citability
-- off the answer to "who caused this request", which is not the question
-- citability turns on. 021's `purpose` column carries it.
ALTER TABLE receipts DROP CONSTRAINT receipts_purpose_check;
ALTER TABLE receipts ADD CONSTRAINT receipts_purpose_check
    CHECK (purpose IN ('target_traffic','control_plane','transport_measurement'));

ALTER TABLE receipts
    ADD COLUMN intercepted boolean NOT NULL DEFAULT true,
    ADD COLUMN alpn_pin_mode text
        CHECK (alpn_pin_mode IN ('off','mirror','strict')),
    -- what the AGENT's TLS stack negotiated: with the proxy, about the proxy.
    ADD COLUMN agent_tls_version   text,
    ADD COLUMN agent_cipher        text,
    ADD COLUMN agent_alpn          text,
    ADD COLUMN agent_cert_sha256   text,
    ADD COLUMN agent_cert_issuer   text,
    ADD COLUMN agent_cert_subject  text,
    ADD COLUMN agent_cert_not_after timestamptz,
    -- what the PROXY negotiated upstream: with the target, about the target.
    ADD COLUMN wire_tls_version    text,
    ADD COLUMN wire_cipher         text,
    ADD COLUMN wire_alpn           text,
    ADD COLUMN wire_cert_sha256    text,
    ADD COLUMN wire_cert_issuer    text,
    ADD COLUMN wire_cert_subject   text,
    ADD COLUMN wire_cert_not_after timestamptz,
    ADD COLUMN wire_sni            text,
    ADD COLUMN wire_chain_verified boolean,
    ADD COLUMN wire_hostname_verified boolean;

-- Which forging key signed the leaf the agent saw. Null off the intercepted
-- lanes. This is the blast-radius audit trail for section 7.
ALTER TABLE receipts ADD COLUMN interception_ca_id uuid;

-- The gap, computed. Seven fields, compared pairwise. `IS DISTINCT FROM` so
-- "the proxy negotiated nothing and told the agent h2" is a divergence and
-- "neither side negotiated anything" is not.
ALTER TABLE receipts ADD COLUMN transport_divergence text[]
    GENERATED ALWAYS AS (array_remove(ARRAY[
        CASE WHEN agent_tls_version   IS DISTINCT FROM wire_tls_version   THEN 'tls_version'    END,
        CASE WHEN agent_cipher        IS DISTINCT FROM wire_cipher        THEN 'cipher'         END,
        CASE WHEN agent_alpn          IS DISTINCT FROM wire_alpn          THEN 'alpn'           END,
        CASE WHEN agent_cert_sha256   IS DISTINCT FROM wire_cert_sha256   THEN 'cert_sha256'    END,
        CASE WHEN agent_cert_issuer   IS DISTINCT FROM wire_cert_issuer   THEN 'cert_issuer'    END,
        CASE WHEN agent_cert_subject  IS DISTINCT FROM wire_cert_subject  THEN 'cert_subject'   END,
        CASE WHEN agent_cert_not_after IS DISTINCT FROM wire_cert_not_after THEN 'cert_not_after' END
    ], NULL)) STORED;

-- Citability, derived. The prototype had the proxy WRITE this flag, which means
-- a compromised or merely buggy proxy could mint a citable receipt; the forged
-- row in tls_local.py's gate matrix is exactly that attack. Here the column is
-- GENERATED, so the whole class is gone at the canonical layer: the only way to
-- obtain a citable receipt is to actually have taken an unintercepted,
-- chain-verified, hostname-verified measurement handshake.
ALTER TABLE receipts ADD COLUMN transport_citable boolean
    GENERATED ALWAYS AS (
        purpose = 'transport_measurement'
        AND intercepted = false
        AND decision = 'allowed'
        AND wire_tls_version IS NOT NULL
        AND wire_chain_verified IS TRUE
        AND wire_hostname_verified IS TRUE
    ) STORED;

ALTER TABLE receipts
    -- A measurement is taken by the proxy on its own behalf, is by definition
    -- not intercepted, has no agent-side handshake to describe, and is in scope
    -- like anything else. The lane clause is the one that stops a measurement
    -- from being minted on the agent's causal lane and then cited as if a
    -- subagent had seen it.
    ADD CONSTRAINT receipts_transport_measurement_shape CHECK (
        purpose <> 'transport_measurement' OR (
            lane = 'proxy_internal'
            AND intercepted = false
            AND agent_tls_version IS NULL AND agent_cipher IS NULL
            AND agent_alpn IS NULL AND agent_cert_sha256 IS NULL
            AND agent_cert_issuer IS NULL AND agent_cert_subject IS NULL
            AND agent_cert_not_after IS NULL
            AND interception_ca_id IS NULL
            AND scope_class = 'target')),
    -- Ticket 13's rule, extended: a measurement is egress, so served egress on
    -- it names a tool run too. The probe is a `tool_runs` row with
    -- transport = 'runtime' and tool_use_id NULL.
    ADD CONSTRAINT receipts_served_transport_needs_tool_run CHECK (
        NOT (purpose = 'transport_measurement' AND decision = 'allowed'
             AND tool_run_id IS NULL)),
    -- THE GAP MUST BE VISIBLE. On the agent lane you record both sides of the
    -- handshake or neither. Recording only what the agent saw -- which is what
    -- a proxy that does not know it is lying would do -- is unwritable.
    ADD CONSTRAINT receipts_agent_transport_records_both_sides CHECK (
        lane <> 'agent'
        OR (agent_tls_version IS NULL) = (wire_tls_version IS NULL)),
    -- An intercepted receipt is signed by a CA we minted; if it carries a leaf
    -- at all it must name which one.
    ADD CONSTRAINT receipts_intercepted_leaf_names_ca CHECK (
        intercepted = false
        OR agent_cert_sha256 IS NULL
        OR interception_ca_id IS NOT NULL);

-- ---------------------------------------------------------------------------
-- 2. Two property classes the vocabulary was missing.
--
-- 018 gave the transport family three leaves. A refusal is only useful if it
-- names a mechanism, and "no such property class" names nothing -- the agent
-- retries with a different string. These two are the claims the proxy makes
-- structurally impossible rather than merely unobserved, and they are in the
-- vocabulary PRECISELY so that the refusal can cite them.
-- ---------------------------------------------------------------------------

INSERT INTO property_classes (id, family_id, name, description) VALUES
 ('transport.request_framing', 'transport', 'Request framing',
  'Chunked/content-length disagreement, request smuggling, desync, connection reuse across requests.'),
 ('transport.datagram_transport', 'transport', 'Datagram transport',
  'HTTP/3, QUIC, and anything else that does not travel over the proxy''s TCP+TLS path.');

-- ---------------------------------------------------------------------------
-- 3. transport_makeability -- the decision, as a table.
--
-- This is the ticket's actual answer, in the only form that survives contact
-- with an LLM: not prose in a review checklist but rows a trigger reads and the
-- MCP schema publishes.
--
--   agent_ok    the agent's own receipt is sufficient evidence. Only the
--               header policy, because headers survive the proxy intact.
--   probe_only  a claim is possible, but only from a measurement receipt, and
--               only over the listed fields.
--   unmakeable  no evidence this design can produce settles it. Refused.
-- ---------------------------------------------------------------------------

CREATE TABLE transport_makeability (
    property_class  text PRIMARY KEY REFERENCES property_classes (id),
    makeability     text NOT NULL CHECK (makeability IN ('agent_ok','probe_only','unmakeable')),
    reason          text NOT NULL,
    allowed_fields  text[] NOT NULL DEFAULT '{}',
    CONSTRAINT transport_makeability_fields_iff_probe CHECK (
        (makeability = 'probe_only') = (cardinality(allowed_fields) > 0))
);

COMMENT ON TABLE transport_makeability IS
 'Ticket 24. Per property class: whether a transport claim can be made at all, '
 'from which kind of receipt, and over which receipt fields. Read by '
 'transport_claim_guard() and published by mcp_transport_makeability().';

INSERT INTO transport_makeability (property_class, makeability, reason, allowed_fields) VALUES
 ('transport.tls_configuration', 'probe_only',
  'The agent terminates TLS against the interception proxy. Version and cipher '
  'matched the origin in every measured cell BY COINCIDENCE -- same OpenSSL, '
  'same defaults, both sides -- and ALPN did not: an unpinned proxy told a '
  'client h2 while the origin spoke http/1.1 only. Requires a measurement '
  'receipt.',
  ARRAY['tls_version','cipher','alpn']),
 ('transport.certificate_trust', 'probe_only',
  'Every certificate field the agent sees belongs to the run CA. Issuer, '
  'subject, fingerprint and notAfter diverged in 100% of intercepted flows '
  'measured. Requires a measurement receipt, whose chain is verified '
  'against the system store and not the run CA.',
  ARRAY['cert_sha256','cert_issuer','cert_subject','cert_not_after']),
 ('transport.header_policy', 'agent_ok',
  'Headers cross the proxy unmodified apart from the injected Authorization, '
  'which the runtime knows it added. HSTS, CSP and cookie attributes are the '
  'target''s own bytes, so the agent-lane receipt is sufficient.',
  '{}'),
 ('transport.request_framing', 'unmakeable',
  'mitmproxy PARSES and RE-SERIALISES every request. The byte framing the '
  'target sees is the proxy''s, not the agent''s, so a smuggling or desync '
  'result describes the proxy. Pinning ALPN does not help: it fixes which '
  'protocol is spoken, not who writes the frames. A real test needs a raw '
  'socket, which the one-egress-path rule denies.',
  '{}'),
 ('transport.datagram_transport', 'unmakeable',
  'The proxy is TCP+TLS. HTTP/3 and QUIC do not traverse it, so their absence '
  'from a receipt is a fact about the proxy. A measurement does not fix this '
  'either -- it speaks TLS over TCP.',
  '{}');

-- 017: a table with no program_id must declare itself global and say why.
INSERT INTO program_global_tables (table_name, reason) VALUES
 ('transport_makeability',
  'Vocabulary. Whether a transport claim is makeable is a property of the '
  'interception design, identical for every program.');

-- ---------------------------------------------------------------------------
-- 4. The observation kind that ticket 27 could not admit.
--
-- 27 could not add this because there was no provenance record to point at.
-- Section 1 creates one, so the kind becomes admissible -- and `{receipt}`
-- only: a tool_run alone would be the agent describing its own socket.
-- ---------------------------------------------------------------------------

INSERT INTO observation_kinds (id, name, is_evidential, allowed_provenance, description) VALUES
 ('transport_parameters_observed', 'Transport parameters observed', true, ARRAY['receipt'],
  'TLS version, cipher, ALPN or certificate fields as negotiated with the '
  'target. Admissible only from a receipt with transport_citable, i.e. the '
  'measurement lane. Every asserted field is checked against the receipt''s '
  'wire_* column at INSERT.');

-- ---------------------------------------------------------------------------
-- 5. The guards. Four ENABLE ALWAYS triggers -- ticket 07 measured that
--    `session_replication_role = 'replica'` silently skips ordinary ones, and a
--    guard a restore can turn off is not a guard.
-- ---------------------------------------------------------------------------

-- 5a. An unmakeable class is refused where it is first written, with its
--     mechanism attached. This is the "before a triager sees it" requirement:
--     the hypothesis never enters the backlog.
CREATE FUNCTION transport_hypothesis_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE m record;
BEGIN
    SELECT * INTO m FROM transport_makeability
     WHERE property_class = NEW.property_class;
    IF NOT FOUND THEN RETURN NEW; END IF;

    IF m.makeability = 'unmakeable' THEN
        RAISE EXCEPTION
          'transport claim refused: % is unmakeable behind the interception proxy. %',
          NEW.property_class, m.reason
          USING ERRCODE = 'check_violation';
    END IF;

    -- No arm here for reaching `supported`. It would be redundant: ticket 06's
    -- transition_rules already demand two supporting and one control evidence
    -- row for hypothesis testing->supported, and 5c below makes every
    -- supporting row on a probe-only class require a citable receipt. The
    -- promotion is constrained transitively, by the layer that decides, and a
    -- second copy of the rule here would only be a second thing to keep in
    -- sync. `check_transport_claims()` item 2 is the detector for the state
    -- itself, if some later migration reopens the path.
    RETURN NEW;
END $$;

CREATE TRIGGER transport_hypothesis_guard
    BEFORE INSERT OR UPDATE ON hypotheses
    FOR EACH ROW EXECUTE FUNCTION transport_hypothesis_guard();
ALTER TABLE hypotheses ENABLE ALWAYS TRIGGER transport_hypothesis_guard;

-- 5b. A transport observation must cite a citable receipt, and every field it
--     asserts must equal that receipt's wire-side column. The agent cannot
--     assert a value the wire did not show -- including a value it read off its
--     own (proxy-issued) certificate.
CREATE FUNCTION transport_observation_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE r receipts; j jsonb; k text; v text; w text;
BEGIN
    IF NEW.kind <> 'transport_parameters_observed' THEN RETURN NEW; END IF;

    IF NEW.provenance_kind <> 'receipt' OR NEW.receipt_id IS NULL THEN
        RAISE EXCEPTION
          'transport observation refused: transport_parameters_observed needs a '
          'receipt; a tool_run alone is the agent describing its own socket'
          USING ERRCODE = 'check_violation';
    END IF;

    SELECT * INTO r FROM receipts WHERE id = NEW.receipt_id;
    IF NOT r.transport_citable THEN
        RAISE EXCEPTION
          'transport observation refused: receipt % is purpose=%, lane=%, '
          'intercepted=%, divergence=%. Its TLS parameters are the proxy''s, '
          'not the target''s.',
          r.label, r.purpose, r.lane, r.intercepted,
          coalesce(r.transport_divergence, '{}')
          USING ERRCODE = 'check_violation';
    END IF;

    j := coalesce(NEW.metadata -> 'transport', '{}'::jsonb);
    IF jsonb_typeof(j) <> 'object' OR j = '{}'::jsonb THEN
        RAISE EXCEPTION
          'transport observation refused: metadata.transport must name the '
          'fields being asserted'
          USING ERRCODE = 'check_violation';
    END IF;

    FOR k, v IN SELECT key, value #>> '{}' FROM jsonb_each(j) LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_attribute
                        WHERE attrelid = 'receipts'::regclass
                          AND attname = 'wire_' || k AND attnum > 0) THEN
            RAISE EXCEPTION
              'transport observation refused: % is not a recorded wire field', k
              USING ERRCODE = 'check_violation';
        END IF;
        w := to_jsonb(r) ->> ('wire_' || k);
        IF w IS DISTINCT FROM v THEN
            RAISE EXCEPTION
              'transport observation refused: asserts %=% but receipt % measured %',
              k, coalesce(v,'null'), r.label, coalesce(w,'null')
              USING ERRCODE = 'check_violation';
        END IF;
    END LOOP;
    RETURN NEW;
END $$;

CREATE TRIGGER transport_observation_guard
    BEFORE INSERT OR UPDATE ON observations
    FOR EACH ROW EXECUTE FUNCTION transport_observation_guard();
ALTER TABLE observations ENABLE ALWAYS TRIGGER transport_observation_guard;

-- 5c. Supporting evidence for a probe-only class must be a transport
--     observation, and may only assert fields that class is allowed to assert.
--     This is the field restriction the prototype gate held in Python
--     (CLASS_FIELDS) moved to where it cannot be bypassed: a certificate
--     fingerprint is not evidence about cipher choice, and vice versa.
CREATE FUNCTION transport_evidence_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE m record; o observations; bad text;
BEGIN
    IF NEW.polarity <> 'supports' THEN RETURN NEW; END IF;

    SELECT tm.* INTO m FROM hypotheses h
      JOIN transport_makeability tm ON tm.property_class = h.property_class
     WHERE h.id = NEW.hypothesis_id;
    IF NOT FOUND OR m.makeability <> 'probe_only' THEN RETURN NEW; END IF;

    SELECT * INTO o FROM observations WHERE id = NEW.observation_id;
    IF o.kind <> 'transport_parameters_observed' THEN
        RAISE EXCEPTION
          'transport evidence refused: % needs a transport_parameters_observed '
          'observation, got %. %', m.property_class, o.kind, m.reason
          USING ERRCODE = 'check_violation';
    END IF;

    SELECT string_agg(key, ', ') INTO bad
      FROM jsonb_each(coalesce(o.metadata -> 'transport', '{}'::jsonb))
     WHERE key <> ALL (m.allowed_fields);
    IF bad IS NOT NULL THEN
        RAISE EXCEPTION
          'transport evidence refused: % may assert only %, observation asserts %',
          m.property_class, m.allowed_fields, bad
          USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER transport_evidence_guard
    BEFORE INSERT OR UPDATE ON hypothesis_evidence
    FOR EACH ROW EXECUTE FUNCTION transport_evidence_guard();
ALTER TABLE hypothesis_evidence ENABLE ALWAYS TRIGGER transport_evidence_guard;

-- 5d. The last gate before a human. A finding may not be validated or reported
--     while it rests on a transport hypothesis that never got there.
CREATE FUNCTION transport_finding_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE d text;
BEGIN
    IF NEW.status NOT IN ('validated','reported') THEN RETURN NEW; END IF;
    IF TG_OP = 'UPDATE' AND OLD.status = NEW.status THEN RETURN NEW; END IF;

    SELECT string_agg(h.label || ' (' || h.property_class || ', ' || h.status || ')', '; ')
      INTO d
      FROM finding_hypotheses fh
      JOIN hypotheses h ON h.id = fh.hypothesis_id
      JOIN transport_makeability tm ON tm.property_class = h.property_class
     WHERE fh.finding_id = NEW.id
       AND (tm.makeability = 'unmakeable' OR h.status <> 'supported');

    IF d IS NOT NULL THEN
        RAISE EXCEPTION
          'finding refused: rests on unsupported transport hypotheses: %', d
          USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER transport_finding_guard
    BEFORE INSERT OR UPDATE ON findings
    FOR EACH ROW EXECUTE FUNCTION transport_finding_guard();
ALTER TABLE findings ENABLE ALWAYS TRIGGER transport_finding_guard;

-- ---------------------------------------------------------------------------
-- 6. The run CA.
--
-- Ticket 04 left "fresh per run, deleted with the output directory", and the
-- brief is right that this is not a v2 answer: it makes a universal forging key
-- for every client in the container, per run, with no record that it ever
-- existed. Settled here:
--
--   LIFETIME   one CA per PROGRAM, not per run and not per installation. Per
--              run means an unaudited forging key every few minutes and an
--              `agent_cert_issuer` value on old receipts that resolves to
--              nothing. Per installation means one key compromises every
--              engagement. Bounded to the engagement window, hard-capped at 90
--              days by CHECK. Rotation SUPERSEDES rather than deletes, so old
--              receipts still resolve.
--   STORAGE    the private key is NEVER in this database and never on disk in
--              the clear. This table holds the public identifier, the lifetime,
--              and a `secret_ref` into TICKET 15's KEK/DEK hierarchy. No second
--              secret store is being built here; a CHECK refuses anything that
--              looks like key material in any column.
--   BLAST      trust is scoped to one program's ephemeral agent container --
--              ticket 14's per-program lane -- and injected into each runtime's
--              own store in the IMAGE (Python cafile/SSL_CERT_FILE, curl
--              CURL_CA_BUNDLE, Node NODE_EXTRA_CA_CERTS, Go SSL_CERT_FILE,
--              chromium's NSS db). No host trust store is ever touched, and the
--              container is destroyed with the program.
--
-- INTERFACE NEEDED FROM TICKET 15, stated as a dependency and not assumed:
--   (a) decrypt-at-use with no file materialisation -- the key is handed to the
--       proxy process over the runtime->proxy channel, not written out;
--   (b) a per-program DEK, so destroying a program's secret material revokes
--       its CA by making the key undecryptable, without touching other programs.
-- FLAG: ticket 15's KEK is described as unlocked once per engagement and held
-- in the RUNTIME process. The proxy is a different process in a different
-- container (ticket 14), so either the CA key travels the runtime->proxy
-- channel or 15's holder must be reachable from the proxy. It must be the
-- former; the proxy must not become a second 1Password client, because that
-- would be a second egress path to a secret store.
-- ---------------------------------------------------------------------------

CREATE TABLE interception_cas (
    id            uuid PRIMARY KEY DEFAULT uuidv7(),
    -- NO ACTION, not CASCADE: ticket 12 measured that a cascading delete is a
    -- purge nobody recorded. Registered in purge_cascade_edges below instead.
    program_id    uuid NOT NULL REFERENCES programs (id),
    label         text NOT NULL,
    subject       text NOT NULL,
    spki_sha256   text NOT NULL CHECK (spki_sha256 ~ '^[0-9a-f]{64}$'),
    not_before    timestamptz NOT NULL,
    not_after     timestamptz NOT NULL,
    secret_ref    text NOT NULL,
    -- Rotation is retire-then-issue, in that order, so the two steps never
    -- overlap and no window exists in which a program has two live forging
    -- keys. `superseded_by` is the audit chain, filled in afterwards.
    retired_at    timestamptz,
    superseded_by uuid,
    created_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (program_id, id),
    UNIQUE (program_id, label),
    FOREIGN KEY (program_id, superseded_by) REFERENCES interception_cas (program_id, id),
    CONSTRAINT interception_cas_window CHECK (not_after > not_before),
    -- Engagement-bounded, hard cap. A CA that outlives the program it was
    -- minted for is the per-installation failure mode by another name.
    CONSTRAINT interception_cas_max_lifetime CHECK (
        not_after <= not_before + interval '90 days'),
    -- Ticket 15's reference format. Anything else means somebody built a second
    -- secret store.
    CONSTRAINT interception_cas_secret_ref_shape CHECK (
        secret_ref ~ '^(op://|kek:)'),
    CONSTRAINT interception_cas_supersede_needs_retire CHECK (
        superseded_by IS NULL OR retired_at IS NOT NULL),
    -- Defence in depth against the obvious mistake.
    CONSTRAINT interception_cas_no_key_material CHECK (
        position('PRIVATE KEY' in
            coalesce(secret_ref,'') || coalesce(subject,'') ||
            coalesce(label,'') || coalesce(spki_sha256,'')) = 0)
);

-- Exactly one CA may be current per program.
CREATE UNIQUE INDEX interception_cas_one_current
    ON interception_cas (program_id) WHERE retired_at IS NULL;

INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
 ('interception_cas', 'program_id',
  'program-scoped: the purge root. Purging a program destroys its CA record; '
  'ticket 15 destroying the program DEK is what makes the key itself '
  'unrecoverable.');

ALTER TABLE receipts ADD CONSTRAINT receipts_interception_ca_fk
    FOREIGN KEY (program_id, interception_ca_id)
    REFERENCES interception_cas (program_id, id);

COMMENT ON TABLE interception_cas IS
 'Ticket 24. Public identity and lifetime of a program''s interception CA. The '
 'private key lives only behind secret_ref (ticket 15); this table never holds '
 'it. Superseding rather than deleting keeps old receipts.agent_cert_issuer '
 'resolvable.';

-- ---------------------------------------------------------------------------
-- 7. check_transport_claims() -- the residual shapes, in 022's style.
-- ---------------------------------------------------------------------------

CREATE FUNCTION check_transport_claims(p_program uuid DEFAULT NULL)
RETURNS TABLE (problem text, subject text, detail text)
LANGUAGE sql STABLE AS $$
    -- 1. a transport claim resting on an intercepted receipt.
    SELECT 'claim_from_intercepted_receipt', o.label,
           'cites ' || r.label || ' (purpose=' || r.purpose
                    || ', lane=' || r.lane || ')'
      FROM observations o JOIN receipts r ON r.id = o.receipt_id
     WHERE o.kind = 'transport_parameters_observed'
       AND NOT r.transport_citable
       AND (p_program IS NULL OR o.program_id = p_program)

    UNION ALL
    -- 2. a supported hypothesis on a probe-only class with no citable support.
    SELECT 'unsupported_transport_hypothesis', h.label, h.property_class
      FROM hypotheses h JOIN transport_makeability tm
             ON tm.property_class = h.property_class
     WHERE h.status = 'supported' AND tm.makeability = 'probe_only'
       AND NOT EXISTS (
             SELECT 1 FROM hypothesis_evidence e
               JOIN observations o ON o.id = e.observation_id
               JOIN receipts r ON r.id = o.receipt_id
              WHERE e.hypothesis_id = h.id AND e.polarity = 'supports'
                AND r.transport_citable)
       AND (p_program IS NULL OR h.program_id = p_program)

    UNION ALL
    -- 3. an unmakeable class present at all.
    SELECT 'unmakeable_class_present', h.label, h.property_class
      FROM hypotheses h JOIN transport_makeability tm
             ON tm.property_class = h.property_class
     WHERE tm.makeability = 'unmakeable'
       AND (p_program IS NULL OR h.program_id = p_program)

    UNION ALL
    -- 4. an agent-lane receipt that recorded only one side of the handshake.
    SELECT 'one_sided_handshake_record', r.label, 'agent side without wire side'
      FROM receipts r
     WHERE r.lane = 'agent' AND r.agent_tls_version IS NOT NULL
       AND r.wire_tls_version IS NULL
       AND (p_program IS NULL OR r.program_id = p_program)

    UNION ALL
    -- 5. an intercepted leaf naming no CA -- an unattributable forging key.
    SELECT 'unattributed_forged_leaf', r.label, coalesce(r.agent_cert_issuer,'?')
      FROM receipts r
     WHERE r.intercepted AND r.agent_cert_sha256 IS NOT NULL
       AND r.interception_ca_id IS NULL
       AND (p_program IS NULL OR r.program_id = p_program)

    UNION ALL
    -- 6. a CA past its window still current.
    SELECT 'expired_ca_still_current', c.label, c.not_after::text
      FROM interception_cas c
     WHERE c.retired_at IS NULL AND c.not_after < now()
       AND (p_program IS NULL OR c.program_id = p_program)

    UNION ALL
    -- 7. the guards themselves. A dropped trigger is the failure this ticket is
    --    about: nothing raises, and everything looks fine.
    SELECT 'guard_missing', t, 'no ENABLE ALWAYS trigger'
      FROM unnest(ARRAY['transport_hypothesis_guard','transport_observation_guard',
                        'transport_evidence_guard','transport_finding_guard']) t
     WHERE NOT EXISTS (SELECT 1 FROM pg_trigger g
                        WHERE g.tgname = t AND NOT g.tgisinternal
                          AND g.tgenabled = 'A')

    UNION ALL
    -- 8. citability must stay derived. If a later migration makes it writable,
    --    every guard above becomes advisory.
    SELECT 'citability_writable', 'receipts.transport_citable',
           'column is not GENERATED'
     WHERE NOT EXISTS (SELECT 1 FROM pg_attribute
                        WHERE attrelid = 'receipts'::regclass
                          AND attname = 'transport_citable'
                          AND attgenerated = 's')

    UNION ALL
    -- 9. the agent connection can reach the ticket-15 reference for the
    --    forging key. Ticket 13's defect 3, one table over.
    SELECT 'ca_secret_ref_readable', 'interception_cas.secret_ref',
           'rk2_state holds SELECT on the ticket-15 secret reference'
     WHERE has_column_privilege('rk2_state', 'interception_cas', 'secret_ref', 'SELECT')

    UNION ALL
    -- 10. a table-level grant on receipts means the NEXT migration's column
    --     reaches the agent without anyone deciding that it should.
    SELECT 'receipts_grant_table_level', 'receipts',
           'rk2_state holds table-level SELECT rather than named columns'
     WHERE EXISTS (SELECT 1 FROM information_schema.table_privileges
                    WHERE table_name = 'receipts' AND grantee = 'rk2_state'
                      AND privilege_type = 'SELECT');
$$;

-- ---------------------------------------------------------------------------
-- 8. Grants.
--
-- Ticket 13 found that 020 grants table-level SELECT, so every column added
-- later reaches the agent connection automatically; `egress_token_sha256` did.
-- `receipts` still carries that grant. Same fix, same reason: the agent SHOULD
-- see the wire columns and its own citability -- that is how it learns what it
-- may claim -- but it should get them by name, so the next migration's column
-- does not arrive silently.
--
-- interception_cas is where the enumeration earns its keep: the agent may read
-- its own program's CA identity, so that the issuer on its own receipts
-- resolves to something, and `secret_ref` -- the pointer into ticket 15's
-- hierarchy -- is simply not in the list. A table-level grant here would have
-- handed it over.
-- ---------------------------------------------------------------------------

DO $$
DECLARE v_cols text;
BEGIN
    SELECT string_agg(quote_ident(attname), ', ' ORDER BY attnum) INTO v_cols
      FROM pg_attribute
     WHERE attrelid = 'receipts'::regclass AND attnum > 0 AND NOT attisdropped;
    EXECUTE 'REVOKE SELECT ON receipts FROM rk2_state';
    EXECUTE format('GRANT SELECT (%s) ON receipts TO rk2_state', v_cols);
END $$;

GRANT SELECT, INSERT, UPDATE ON transport_makeability TO rk2_runtime;
GRANT SELECT, INSERT, UPDATE ON interception_cas TO rk2_runtime;
GRANT SELECT ON transport_makeability TO rk2_state;
GRANT SELECT (id, program_id, label, subject, spki_sha256,
              not_before, not_after, retired_at, superseded_by, created_at)
    ON interception_cas TO rk2_state;

ALTER TABLE interception_cas ENABLE ROW LEVEL SECURITY;
CREATE POLICY interception_cas_rk2_runtime ON interception_cas
    FOR ALL TO rk2_runtime USING (true) WITH CHECK (true);
CREATE POLICY interception_cas_rk2_state ON interception_cas
    FOR SELECT TO rk2_state USING (program_id = rk2_program());

-- ---------------------------------------------------------------------------
-- 9. mcp_transport_makeability() -- the refusal, published.
--
-- 018's mcp_enum() builds the tool schema enum from the same rows the FK points
-- at, so the model cannot be offered a value the database will reject. The same
-- move here, one step further: the model is shown the REASON alongside the
-- verdict, in the same call that constrains it. An agent that is told
-- "transport.request_framing is unmakeable because the proxy re-serialises
-- every request" does not spend a turn discovering the refusal.
-- ---------------------------------------------------------------------------

CREATE FUNCTION mcp_transport_makeability() RETURNS jsonb
LANGUAGE sql STABLE AS $$
    SELECT jsonb_object_agg(property_class, jsonb_build_object(
               'makeability', makeability,
               'allowed_fields', to_jsonb(allowed_fields),
               'reason', reason))
      FROM transport_makeability;
$$;

-- ---------------------------------------------------------------------------
-- 10. Self-check.
-- ---------------------------------------------------------------------------

DO $$
DECLARE n int; d text;
BEGIN
    SELECT count(*), string_agg(problem || ':' || subject, '; ')
      INTO n, d FROM check_transport_claims();
    IF n > 0 THEN
        RAISE EXCEPTION 'migration 025 leaves % transport problems: %', n, d;
    END IF;
    RAISE NOTICE 'migration 025 applied; check_transport_claims() clean';
END $$;
