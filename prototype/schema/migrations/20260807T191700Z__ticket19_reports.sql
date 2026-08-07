-- ---------------------------------------------------------------------------
-- 20260807T191700Z__ticket19_reports.sql   (ticket 19 -- the report)
--
-- Was `029_ticket19_reports.sql` on branch prototype/report-format. What the
-- fold changed:
--
--   * 029 ended section 3 with a DO block that enabled RLS, wrote two policies
--     per table and issued relation grants to both roles, under the comment
--     "020's sweep already ran". Ticket 33 turned that sweep into
--     `apply_state_rls()`, a finalizer, and replaced the `rk2_state` half of it
--     with the `state_read_surface` column registry. The whole block is gone:
--     RLS and both policies come from the finalizer, the `rk2_runtime` grants
--     come from `ALTER DEFAULT PRIVILEGES FOR ROLE rk2_owner`, and the eleven
--     tables 029 published to `rk2_state` are enumerated in section Z below.
--   * 029 seeds `vulnerability_classes`, which is what 009 reserved it for
--     ("seed set: ticket 19"). `tests/seed.sql` had been carrying one row of
--     that vocabulary as a stand-in; the stand-in is removed there, not
--     duplicated here.
--   * 029 classified none of its eleven tables for emission (section Z).
--   * `check_report_grounding()` is registered in `standing_checks` (section Z);
--     without a row there `check_check_registration()` refuses the run.
--
-- What the fold did NOT change: `reject_non_agent_evidence` still only raises
-- for `provenance_kind = 'receipt'`, so ticket 27's `content_match` -- whose
-- `allowed_provenance` is `{tool_run}` -- passes it untouched. The two tickets
-- do not collide; the trigger asks about the lane of a receipt, and a tool run
-- has no receipt to have a lane.
-- ---------------------------------------------------------------------------

SET client_min_messages = notice;


-- ===========================================================================
-- 1. `vulnerability_classes` -- the seed ticket 06 handed to this ticket
-- ===========================================================================

-- Granularity: ticket 27 measured 8 property-class families over 33 leaves and
-- proved 8 was too coarse to write with. This seed keeps the SAME 8 families as
-- the aggregation axis and puts 32 CWE-anchored classes underneath them, so the
-- two vocabularies aggregate to the same eight buckets and no third taxonomy
-- appears. It is deliberately NOT a mirror of the 33 leaves: a property class
-- is what was tested, a vulnerability class is what was found, and 018 already
-- made that mapping many-to-many and advisory.
--
-- `short_name` and `remediation` are report fields: `short_name` is the token
-- the impact sentence uses ("Pug SSTI"), `remediation` is the curated paragraph
-- the long-form platform template emits. Neither is ever model-authored.
ALTER TABLE vulnerability_classes
    ADD COLUMN family_id   text REFERENCES property_class_families(id),
    ADD COLUMN short_name  text,
    ADD COLUMN cvss_ui     text NOT NULL DEFAULT 'N' CHECK (cvss_ui IN ('N','R')),
    ADD COLUMN remediation text;

INSERT INTO vulnerability_classes (id, cwe_id, name, family_id, short_name, cvss_ui, remediation) VALUES
 ('idor','CWE-639','Authorization bypass through user-controlled key','authorization','IDOR','N',
  'Resolve the object from the session identity, not from a client-supplied identifier, and check ownership on every read and write path.'),
 ('missing_authorization','CWE-862','Missing authorization','authorization','missing authz','N',
  'Add a server-side authorization check to the handler; deny by default and enumerate the roles allowed to reach it.'),
 ('incorrect_authorization','CWE-863','Incorrect authorization','authorization','broken authz','N',
  'Fix the authorization predicate so it compares the acting identity against the object owner rather than against the request.'),
 ('tenant_isolation_break','CWE-284','Improper access control across tenants','authorization','tenant break','N',
  'Scope every query by tenant at the data layer so a handler cannot address another tenant''s rows at all.'),
 ('privilege_escalation','CWE-269','Improper privilege management','authorization','privesc','N',
  'Derive privileges server-side from the stored role; never accept a role, scope or tier from the request.'),
 ('function_level_access','CWE-285','Improper authorization of administrative function','authorization','function-level authz','N',
  'Put administrative handlers behind the same authorization middleware as the rest of the application and assert it in tests.'),
 ('missing_authentication','CWE-306','Missing authentication for critical function','authentication','missing authn','N',
  'Require an authenticated session on the handler and reject anonymous requests before any side effect.'),
 ('improper_authentication','CWE-287','Improper authentication','authentication','broken authn','N',
  'Verify the credential server-side against the stored value and fail closed on any verification error.'),
 ('weak_credential_recovery','CWE-640','Weak password recovery mechanism','authentication','recovery flow','N',
  'Bind the reset token to the account, make it single-use, short-lived and unguessable, and invalidate sessions on use.'),
 ('signature_not_verified','CWE-347','Improper verification of cryptographic signature','authentication','signature bypass','N',
  'Verify the signature with a pinned algorithm and key; reject tokens whose header selects the algorithm.'),
 ('auth_rate_limit_missing','CWE-307','Improper restriction of excessive authentication attempts','authentication','credential stuffing','N',
  'Rate-limit authentication per identity and per origin, and lock or step up after a threshold.'),
 ('sqli','CWE-89','SQL injection','injection','SQLi','N',
  'Use parameterised queries; never build SQL by string concatenation from request data.'),
 ('command_injection','CWE-78','OS command injection','injection','command injection','N',
  'Call the target program with an argument vector, never through a shell, and reject values outside an allowlist.'),
 ('ssti','CWE-1336','Server-side template injection','injection','SSTI','N',
  'Never pass request data to the template compiler as template source. Render a fixed template and pass request data as context values.'),
 ('code_injection','CWE-94','Code injection','injection','code injection','N',
  'Remove the dynamic evaluation path; if it must exist, drive it from a fixed allowlist of server-side identifiers.'),
 ('xss_reflected','CWE-79','Reflected cross-site scripting','injection','reflected XSS','R',
  'Contextually encode on output and set a Content-Security-Policy that forbids inline script.'),
 ('xss_stored','CWE-79','Stored cross-site scripting','injection','stored XSS','N',
  'Contextually encode on output, sanitise stored markup with a vetted allowlist parser, and set a Content-Security-Policy.'),
 ('xxe','CWE-611','XML external entity injection','injection','XXE','N',
  'Disable external entity and DTD processing in the XML parser.'),
 ('deserialization','CWE-502','Deserialization of untrusted data','injection','insecure deserialization','N',
  'Do not deserialise attacker-controlled data into arbitrary types; use a data-only format with a schema.'),
 ('ssrf','CWE-918','Server-side request forgery','injection','SSRF','N',
  'Resolve and validate the destination against an allowlist after DNS resolution, and block link-local and private ranges.'),
 ('path_traversal','CWE-22','Path traversal','injection','path traversal','N',
  'Resolve the path and assert the result is inside the intended directory; never join request data onto a filesystem path.'),
 ('open_redirect','CWE-601','Open redirect','injection','open redirect','R',
  'Redirect only to a server-side allowlist of paths, never to a URL taken from the request.'),
 ('unrestricted_upload','CWE-434','Unrestricted upload of file with dangerous type','injection','file upload','N',
  'Validate the type server-side, store outside the web root under a generated name, and serve with a fixed content type.'),
 ('error_disclosure','CWE-209','Information exposure through an error message','information_disclosure','error disclosure','N',
  'Return a generic error to the client and keep stack traces and query text in server-side logs.'),
 ('sensitive_data_exposure','CWE-200','Exposure of sensitive information to an unauthorized actor','information_disclosure','data exposure','N',
  'Return only the fields the caller is entitled to; build responses from an explicit projection rather than from the record.'),
 ('directory_listing','CWE-548','Exposure of information through directory listing','information_disclosure','directory listing','N',
  'Disable automatic directory indexes on the server.'),
 ('mass_assignment','CWE-915','Improperly controlled modification of dynamically-determined object attributes','business_logic','mass assignment','N',
  'Bind request bodies to an explicit allowlist of writable fields.'),
 ('workflow_bypass','CWE-841','Improper enforcement of behavioral workflow','business_logic','workflow bypass','N',
  'Enforce the state machine server-side and reject a transition whose predecessor did not happen.'),
 ('replay','CWE-345','Insufficient verification of data authenticity','business_logic','replay','N',
  'Bind each request to a single-use server-issued nonce and reject repeats.'),
 ('resource_exhaustion','CWE-770','Allocation of resources without limits or throttling','rate_limiting','resource exhaustion','N',
  'Bound the work a single request can request, and throttle per identity and per origin.'),
 ('session_fixation','CWE-384','Session fixation','session_handling','session fixation','N',
  'Issue a new session identifier on privilege change and never accept one supplied by the client.'),
 ('insufficient_session_expiration','CWE-613','Insufficient session expiration','session_handling','session expiry','N',
  'Expire sessions server-side on an absolute and an idle deadline, and invalidate on logout and password change.'),
 ('cookie_flags','CWE-1004','Sensitive cookie without HttpOnly flag','session_handling','cookie flags','N',
  'Set HttpOnly, Secure and SameSite on session cookies.'),
 ('csrf','CWE-352','Cross-site request forgery','session_handling','CSRF','R',
  'Require a per-session anti-CSRF token on every state-changing request and set SameSite on the session cookie.'),
 ('cleartext_transmission','CWE-319','Cleartext transmission of sensitive information','transport','cleartext','N',
  'Serve only over TLS, redirect HTTP to HTTPS, and set HSTS.'),
 ('certificate_validation','CWE-295','Improper certificate validation','transport','cert validation','N',
  'Validate the chain and the hostname; do not disable verification in any environment that reaches production data.'),
 ('permissive_cors','CWE-942','Overly permissive cross-domain policy','transport','CORS','N',
  'Reflect only origins on a server-side allowlist and never combine a wildcard origin with credentials.');

-- 018 built `property_class_vulnerability_classes` and left it empty on
-- purpose: "which class each property class expects" is this ticket's call. It
-- is advisory -- it drives `finding_class_divergence`, which is a review
-- signal, not a constraint. Seeded for the leaves whose expected outcome is
-- actually determinate; a leaf with no row here asks no question.
INSERT INTO property_class_vulnerability_classes (property_class_id, vulnerability_class_id, note) VALUES
 ('authorization.object_ownership','idor',NULL),
 ('authorization.object_ownership','incorrect_authorization',NULL),
 ('authorization.object_ownership','sensitive_data_exposure','reads that cross no ownership boundary but return more than they should'),
 ('authorization.function_access','missing_authorization',NULL),
 ('authorization.function_access','function_level_access',NULL),
 ('authorization.tenant_isolation','tenant_isolation_break',NULL),
 ('authorization.token_scope','privilege_escalation',NULL),
 ('authorization.token_scope','signature_not_verified','a scope that is trusted because the token was not verified'),
 ('authorization.state_transition','workflow_bypass',NULL),
 ('authentication.credential_verification','improper_authentication',NULL),
 ('authentication.credential_verification','missing_authentication',NULL),
 ('authentication.factor_enforcement','improper_authentication',NULL),
 ('authentication.federation_trust','signature_not_verified',NULL),
 ('authentication.recovery_flow','weak_credential_recovery',NULL),
 ('injection.query_language','sqli',NULL),
 ('injection.command','command_injection',NULL),
 ('injection.template','ssti',NULL),
 ('injection.template','code_injection','a template sink that is really an eval sink'),
 ('injection.markup','xss_reflected',NULL),
 ('injection.markup','xss_stored',NULL),
 ('injection.document_parser','xxe',NULL),
 ('injection.document_parser','deserialization',NULL),
 ('injection.request_forgery','ssrf',NULL),
 ('injection.request_forgery','open_redirect',NULL),
 ('injection.path','path_traversal',NULL),
 ('information_disclosure.error_detail','error_disclosure',NULL),
 ('information_disclosure.identifier_oracle','sensitive_data_exposure',NULL),
 ('information_disclosure.artifact_exposure','directory_listing',NULL),
 ('information_disclosure.excess_field','sensitive_data_exposure',NULL),
 ('information_disclosure.excess_field','mass_assignment','the read side of a field that is also writable'),
 ('business_logic.workflow_order','workflow_bypass',NULL),
 ('business_logic.quantity_or_price','mass_assignment',NULL),
 ('business_logic.replay','replay',NULL),
 ('rate_limiting.per_identity','auth_rate_limit_missing',NULL),
 ('rate_limiting.per_origin','resource_exhaustion',NULL),
 ('rate_limiting.resource_cost','resource_exhaustion',NULL),
 ('session_handling.lifetime','insufficient_session_expiration',NULL),
 ('session_handling.fixation','session_fixation',NULL),
 ('session_handling.cookie_scope','cookie_flags',NULL),
 ('session_handling.csrf','csrf',NULL),
 ('transport.tls_configuration','cleartext_transmission',NULL),
 ('transport.certificate_trust','certificate_validation',NULL),
 ('transport.header_policy','permissive_cors',NULL);


-- ===========================================================================
-- 2. The document vocabulary -- effects, blocks, templates, mechanisms
-- ===========================================================================

-- The impact sentence names an EFFECT, and an effect is only sayable if an
-- observation witnesses it (`finding_effects.witness_observation_id`, NOT
-- NULL). The CVSS impact metrics live here too, so "what the finding does" and
-- "what it scores" cannot drift apart: they are the same row.
CREATE TABLE report_effects (
    id           text PRIMARY KEY,
    phrase       text NOT NULL,          -- lower case; the renderer capitalises the first
    impact_c     text NOT NULL CHECK (impact_c IN ('N','L','H')),
    impact_i     text NOT NULL CHECK (impact_i IN ('N','L','H')),
    impact_a     text NOT NULL CHECK (impact_a IN ('N','L','H')),
    scope_change boolean NOT NULL DEFAULT false
);

INSERT INTO report_effects (id, phrase, impact_c, impact_i, impact_a, scope_change) VALUES
 ('command_execution',        'command execution',                'H','H','H', false),
 ('arbitrary_file_read',      'arbitrary file read',              'H','N','N', false),
 ('arbitrary_file_write',     'arbitrary file write',             'N','H','N', false),
 ('cross_account_read',       'cross-account data disclosure',    'H','N','N', true),
 ('cross_account_write',      'cross-account modification',       'N','H','N', true),
 ('account_takeover',         'account takeover',                 'H','H','N', false),
 ('session_theft',            'session theft',                    'H','L','N', true),
 ('internal_network_access',  'access to internal network services','H','L','N', true),
 ('price_manipulation',       'price manipulation',               'N','H','N', false),
 ('information_disclosure',   'disclosure of non-public data',    'L','N','N', false),
 ('service_disruption',       'service disruption',               'N','N','H', false);

-- The block registry. A template may only order and include these; it may not
-- author one. That is the whole of "what is fixed and what is a template".
CREATE TABLE report_blocks (
    id          text PRIMARY KEY,
    name        text NOT NULL,
    description text NOT NULL
);

INSERT INTO report_blocks (id, name, description) VALUES
 ('provenance_header','Provenance header',
  'lane of the cited receipts + ts_arrival of the earliest one. Never wall-clock at render time.'),
 ('impact_sentence','Impact sentence',
  'one sentence: witnessed effects, technique, endpoint. No severity word.'),
 ('attack_chain','Attack chain',
  'numbered list, one item per finding_chain_steps row: bolded mechanism label + templated prose.'),
 ('poc_payload','Proof-of-concept payload',
  'one fenced block, the payload extracted from the validating tests.spec action.'),
 ('repro_steps','Steps to reproduce',
  'the same spec rendered as curl commands a triager runs without the harness.'),
 ('evidence_manifest','Evidence',
  'cited receipt labels, artifact hashes, redacted excerpts.'),
 ('severity_block','Severity',
  'computed CVSS v3.1 base vector and band, labelled as computed rather than adjudicated.'),
 ('affected_assets','Affected assets',
  'subject entity and the application it belongs to.'),
 ('remediation','Remediation',
  'the curated paragraph on the vulnerability class. Never generated.');

CREATE TABLE report_templates (
    id       text PRIMARY KEY,
    platform text NOT NULL,
    name     text NOT NULL,
    notes    text
);

INSERT INTO report_templates (id, platform, name, notes) VALUES
 ('rk2.default','rk2','redKraken default',
  'the operator''s four parts, in order, and nothing else. Fits on a screen.'),
 ('platform.long_form','generic','Long-form submission',
  'the shape every major platform form asks for: summary, assets, steps, evidence, severity, remediation.'),
 ('platform.cvss_required','generic','CVSS-required submission',
  'default plus the computed vector, for programs whose form refuses a submission without one.');

CREATE TABLE report_template_blocks (
    template_id text NOT NULL REFERENCES report_templates(id),
    ordinal     integer NOT NULL,
    block_id    text NOT NULL REFERENCES report_blocks(id),
    PRIMARY KEY (template_id, ordinal),
    UNIQUE (template_id, block_id)
);

INSERT INTO report_template_blocks (template_id, ordinal, block_id) VALUES
 ('rk2.default',1,'provenance_header'),
 ('rk2.default',2,'impact_sentence'),
 ('rk2.default',3,'attack_chain'),
 ('rk2.default',4,'poc_payload'),
 ('platform.long_form',1,'provenance_header'),
 ('platform.long_form',2,'impact_sentence'),
 ('platform.long_form',3,'affected_assets'),
 ('platform.long_form',4,'attack_chain'),
 ('platform.long_form',5,'poc_payload'),
 ('platform.long_form',6,'repro_steps'),
 ('platform.long_form',7,'evidence_manifest'),
 ('platform.long_form',8,'severity_block'),
 ('platform.long_form',9,'remediation'),
 ('platform.cvss_required',1,'provenance_header'),
 ('platform.cvss_required',2,'impact_sentence'),
 ('platform.cvss_required',3,'attack_chain'),
 ('platform.cvss_required',4,'poc_payload'),
 ('platform.cvss_required',5,'severity_block');

-- The mechanism library. THIS is the reconciliation of the operator's
-- explanatory chain steps with ticket 11's deterministic renderer: the
-- explanation is a fact about a TECHNOLOGY, curated once, selected by a cited
-- observation; the target-specific parts are slots filled from cited rows.
--
-- `min_citations = 2` is what lets a step carry a mechanism that is in no
-- single row: the WAF-bypass step is a statement about the RELATION between two
-- receipts, and a step row can cite both.
CREATE TABLE report_mechanisms (
    id                  text PRIMARY KEY,
    class_id            text REFERENCES vulnerability_classes(id),
    label               text NOT NULL,          -- the bolded label in the numbered list
    template            text NOT NULL,          -- {slot} placeholders only
    slots               text[] NOT NULL,
    requires_technology text,                   -- licensed by a cited technology observation
    min_citations       integer NOT NULL DEFAULT 1 CHECK (min_citations >= 1)
);

INSERT INTO report_mechanisms (id, class_id, label, template, slots, requires_technology, min_citations) VALUES
 ('ssti.injection_point','ssti','Injection point',
  'The `{param}` field submitted to `{method} {path}` is concatenated into the template source before compilation, so its bytes are parsed as template syntax rather than rendered as data.',
  ARRAY['param','method','path'], NULL, 1),
 ('ssti.sink.pug','ssti','Sink',
  'The sink is the {engine} template compiler. A {engine} template is compiled to a JavaScript function, so the evaluation context reaches the Node globals `process` and `require` -- template injection is code injection on this engine, not an output-encoding problem.',
  ARRAY['engine'], 'Pug', 1),
 ('ssti.escalation.node_rce','command_injection','Escalation to RCE',
  'From that context `process.mainModule.require(''child_process'')` is reachable, and the response to `{method} {path}` carried the output of the executed command with status `{status}`.',
  ARRAY['method','path','status'], 'Pug', 1),
 ('filter.bypass_differential',NULL,'WAF bypass',
  'The request carrying `{blocked_token}` is rejected with `{blocked_status}`; the identical request carrying `{allowed_token}` reaches the sink and returns `{allowed_status}`. The filter therefore matches the literal token, not the effect, and the sink is reachable around it.',
  ARRAY['blocked_token','blocked_status','allowed_token','allowed_status'], NULL, 2),
 ('idor.injection_point','idor','Injection point',
  'The `{param}` field on `{method} {path}` is used to address the object directly, so the object is selected by the request rather than by the session.',
  ARRAY['param','method','path'], NULL, 1),
 ('idor.differential','idor','Cross-identity differential',
  'The same request issued as `{identity_a}` and as `{identity_b}` returns status `{status}` for both, and the response bodies are identical -- the second identity has no claim to the object and is served it anyway.',
  ARRAY['identity_a','identity_b','status'], NULL, 2),
 ('generic.control', NULL, 'Control',
  'The same request against `{control_path}` returns `{control_status}`, so the behaviour is specific to `{path}` and not a property of the application as a whole.',
  ARRAY['control_path','control_status','path'], NULL, 1);

-- Redaction rules. Structural, deterministic, and reversible-by-hash: the
-- replacement carries the plaintext length and the sha256 of the removed range,
-- so a triager who is later given the full artifact can prove the excerpt was
-- not doctored, and the operator can answer "what was there" without shipping
-- another user's data in the first message.
CREATE TABLE redaction_rules (
    id         text PRIMARY KEY,
    label      text NOT NULL,
    pattern    text NOT NULL,     -- POSIX regex, applied to agent-visible artifact text
    rationale  text NOT NULL
);

INSERT INTO redaction_rules (id, label, pattern, rationale) VALUES
 ('email','email','[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}','another user''s address'),
 ('phone','phone','\+?[0-9][0-9 ().-]{8,}[0-9]','another user''s number'),
 ('bearer','bearer-token','(?i)bearer [A-Za-z0-9._~+/-]{16,}','credential material'),
 ('jwt','jwt','eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}','credential material'),
 ('card','pan','\b(?:[0-9]{4}[ -]?){3}[0-9]{4}\b','payment data'),
 ('national_id','national-id','\b[0-9]{3}-[0-9]{2}-[0-9]{4}\b','government identifier');


-- ===========================================================================
-- 3. The per-finding report rows
-- ===========================================================================

-- A program's own "do not send us this" list. Bounty programs publish one, and
-- a report that ignores it costs reputation rather than earning a bounty. It is
-- a hard blocker, not a warning.
CREATE TABLE program_known_issues (
    id           uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id   uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    class_id     text NOT NULL REFERENCES vulnerability_classes(id),
    entity_like  text,          -- SQL LIKE over entities.dedup_key; NULL = whole program
    source       text NOT NULL CHECK (source IN ('program_policy','operator','prior_submission')),
    note         text NOT NULL,
    UNIQUE (id, program_id)
);

CREATE TABLE finding_effects (
    id                    uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id            uuid NOT NULL,
    finding_id            uuid NOT NULL,
    ordinal               integer NOT NULL,
    effect_id             text NOT NULL REFERENCES report_effects(id),
    witness_observation_id uuid NOT NULL,
    UNIQUE (id, program_id),
    UNIQUE (finding_id, ordinal),
    UNIQUE (finding_id, effect_id),
    FOREIGN KEY (finding_id, program_id) REFERENCES findings (id, program_id) ON DELETE CASCADE,
    FOREIGN KEY (witness_observation_id, program_id) REFERENCES observations (id, program_id)
);

CREATE TABLE finding_chain_steps (
    id           uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id   uuid NOT NULL,
    finding_id   uuid NOT NULL,
    ordinal      integer NOT NULL,
    mechanism_id text NOT NULL REFERENCES report_mechanisms(id),
    params       jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (id, program_id),
    UNIQUE (finding_id, ordinal),
    FOREIGN KEY (finding_id, program_id) REFERENCES findings (id, program_id) ON DELETE CASCADE
);

CREATE TABLE finding_chain_step_citations (
    id             uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id     uuid NOT NULL,
    step_id        uuid NOT NULL,
    ordinal        integer NOT NULL,
    receipt_id     uuid,
    observation_id uuid,
    UNIQUE (id, program_id),
    UNIQUE (step_id, ordinal),
    CHECK ((receipt_id IS NOT NULL) <> (observation_id IS NOT NULL)),
    FOREIGN KEY (step_id, program_id) REFERENCES finding_chain_steps (id, program_id) ON DELETE CASCADE,
    FOREIGN KEY (receipt_id, program_id) REFERENCES receipts (id, program_id),
    FOREIGN KEY (observation_id, program_id) REFERENCES observations (id, program_id)
);

-- The bytes a human read. Immutable: an approval names one of these rows, and a
-- rendering whose content could change afterwards would make the approval mean
-- nothing.
CREATE TABLE report_renderings (
    id               uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id       uuid NOT NULL,
    finding_id       uuid NOT NULL,
    template_id      text NOT NULL REFERENCES report_templates(id),
    source_digest    text NOT NULL,
    content          text NOT NULL,
    content_sha256   text NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    renderer_version text NOT NULL,
    rendered_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, program_id),
    FOREIGN KEY (finding_id, program_id) REFERENCES findings (id, program_id) ON DELETE CASCADE
);

CREATE TRIGGER report_renderings_immutable
    BEFORE UPDATE OR DELETE ON report_renderings
    FOR EACH ROW EXECUTE FUNCTION reject_mutation_unless_purging();
ALTER TABLE report_renderings ENABLE ALWAYS TRIGGER report_renderings_immutable;

-- The approval names the exact bytes. No new gate: the transition to `reported`
-- is still ticket 06's `transition_rules` row, still `actor_kind='human'`,
-- still authorised by 026's `rk2_human` membership check.
ALTER TABLE finding_transitions
    ADD COLUMN approved_rendering_id uuid,
    ADD CONSTRAINT finding_transitions_rendering_fk
        FOREIGN KEY (approved_rendering_id, program_id)
        REFERENCES report_renderings (id, program_id);

INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
 ('program_known_issues',        'program_id','program-scoped: the purge root'),
 ('finding_effects',             'finding_id','report row, finding side'),
 ('finding_chain_steps',         'finding_id','report row, finding side'),
 ('finding_chain_step_citations','step_id',   'citation edge, step side'),
 ('report_renderings',           'finding_id','rendered document, finding side');

INSERT INTO program_global_tables (table_name, reason) VALUES
 ('report_effects',   'the effect vocabulary and its CVSS impact metrics are one list for every program'),
 ('report_blocks',    'the block registry: a platform template selects from it, never extends it'),
 ('report_templates', 'a platform''s form is the same form for every program'),
 ('report_template_blocks','ordering of the above'),
 ('report_mechanisms','curated knowledge about technologies, not about a target'),
 ('redaction_rules',  'what counts as another person''s data does not vary by program');

-- ===========================================================================
-- 4. Grounding -- ticket 05's submission gate, enforced at INSERT
-- ===========================================================================

-- Ticket 05 discarded a TRUE finding because its cited receipt did not exist,
-- and could only discover that at scoring time. The decision here is to reject
-- at submission: the citation is resolved when the row is written, the write
-- raises with the offending id in the message, and the agent may resubmit with
-- real receipts. Catching it later loses the finding.
CREATE FUNCTION reject_non_agent_evidence() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE v_lane text; v_kind text; v_obs uuid;
BEGIN
    v_obs := (to_jsonb(NEW) ->> TG_ARGV[0])::uuid;
    IF v_obs IS NULL THEN RETURN NEW; END IF;

    SELECT o.provenance_kind, r.lane INTO v_kind, v_lane
      FROM observations o LEFT JOIN receipts r ON r.id = o.receipt_id
     WHERE o.id = v_obs;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'ungrounded: observation % does not exist', v_obs;
    END IF;
    IF v_kind = 'receipt' AND v_lane IS DISTINCT FROM 'agent' THEN
        RAISE EXCEPTION 'ungrounded: observation % is backed by a % receipt; evidence may only cite the agent lane',
              v_obs, coalesce(v_lane, 'missing');
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER finding_evidence_agent_lane
    BEFORE INSERT ON finding_evidence
    FOR EACH ROW EXECUTE FUNCTION reject_non_agent_evidence('observation_id');
ALTER TABLE finding_evidence ENABLE ALWAYS TRIGGER finding_evidence_agent_lane;

CREATE FUNCTION reject_non_agent_citation() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE v_lane text;
BEGIN
    IF NEW.receipt_id IS NOT NULL THEN
        SELECT lane INTO v_lane FROM receipts WHERE id = NEW.receipt_id;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'ungrounded: receipt % does not exist', NEW.receipt_id;
        END IF;
        IF v_lane <> 'agent' THEN
            RAISE EXCEPTION 'ungrounded: receipt % is on the % lane; a report may only cite the agent lane',
                  NEW.receipt_id, v_lane;
        END IF;
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER chain_citation_agent_lane
    BEFORE INSERT ON finding_chain_step_citations
    FOR EACH ROW EXECUTE FUNCTION reject_non_agent_citation();
ALTER TABLE finding_chain_step_citations ENABLE ALWAYS TRIGGER chain_citation_agent_lane;

CREATE TRIGGER chain_citation_agent_lane_obs
    BEFORE INSERT ON finding_chain_step_citations
    FOR EACH ROW EXECUTE FUNCTION reject_non_agent_evidence('observation_id');
ALTER TABLE finding_chain_step_citations ENABLE ALWAYS TRIGGER chain_citation_agent_lane_obs;

-- Ticket 16 asked for exactly this: the join key by which an injected evidence
-- item counts as USED. A finding cites receipts by id, and this is the view its
-- `used_witness` metric joins against.
CREATE VIEW finding_cited_receipts AS
SELECT c.program_id, s.finding_id, c.receipt_id, 'chain_step'::text AS via
  FROM finding_chain_step_citations c
  JOIN finding_chain_steps s ON s.id = c.step_id
 WHERE c.receipt_id IS NOT NULL
UNION
SELECT c.program_id, s.finding_id, o.receipt_id, 'chain_step_observation'
  FROM finding_chain_step_citations c
  JOIN finding_chain_steps s ON s.id = c.step_id
  JOIN observations o ON o.id = c.observation_id
 WHERE o.receipt_id IS NOT NULL
UNION
SELECT fe.program_id, fe.finding_id, o.receipt_id, 'finding_evidence'
  FROM finding_evidence fe
  JOIN observations o ON o.id = fe.observation_id
 WHERE o.receipt_id IS NOT NULL;


-- ===========================================================================
-- 5. The fact projection, and the no-new-facts rule
-- ===========================================================================

-- Every scalar anywhere in a jsonb value, as text. Keys are NOT emitted: a key
-- is schema, a value is a fact about the target.
CREATE FUNCTION jsonb_scalars(j jsonb) RETURNS SETOF text
LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE v jsonb; t text;
BEGIN
    t := jsonb_typeof(j);
    IF t = 'object' THEN
        FOR v IN SELECT value FROM jsonb_each(j) LOOP
            RETURN QUERY SELECT * FROM jsonb_scalars(v);
        END LOOP;
    ELSIF t = 'array' THEN
        FOR v IN SELECT value FROM jsonb_array_elements(j) LOOP
            RETURN QUERY SELECT * FROM jsonb_scalars(v);
        END LOOP;
    ELSIF t IN ('string','number') THEN
        RETURN NEXT CASE t WHEN 'string' THEN j #>> '{}' ELSE j::text END;
    END IF;
    RETURN;
END $$;

-- Everything the cited rows say about the target. A slot value outside this set
-- is a fact the system does not have, wherever it came from.
CREATE FUNCTION finding_fact_tokens(p_finding uuid)
RETURNS TABLE (token text, source text)
LANGUAGE sql STABLE AS $$
    -- cited receipts: the request line and what came back
    SELECT t.tok, 'receipt' FROM finding_cited_receipts fcr
      JOIN receipts r ON r.id = fcr.receipt_id
      CROSS JOIN LATERAL (VALUES (r.method),(r.host),(r.path),(r.scheme),
                                 (r.status_code::text),(r.port::text)) t(tok)
     WHERE fcr.finding_id = p_finding AND t.tok IS NOT NULL
    UNION
    -- cited observations: the structured channel. `summary` is model-authored
    -- and is deliberately NOT here.
    SELECT s, 'observation_metadata' FROM (
        SELECT c.observation_id AS oid FROM finding_chain_step_citations c
          JOIN finding_chain_steps st ON st.id = c.step_id
         WHERE st.finding_id = p_finding AND c.observation_id IS NOT NULL
        UNION SELECT fe.observation_id FROM finding_evidence fe WHERE fe.finding_id = p_finding
    ) q JOIN observations o ON o.id = q.oid
      CROSS JOIN LATERAL jsonb_scalars(o.metadata) s
    UNION
    -- entities those observations are about, through their detail rows
    SELECT t.tok, 'entity' FROM (
        SELECT c.observation_id AS oid FROM finding_chain_step_citations c
          JOIN finding_chain_steps st ON st.id = c.step_id
         WHERE st.finding_id = p_finding AND c.observation_id IS NOT NULL
        UNION SELECT fe.observation_id FROM finding_evidence fe WHERE fe.finding_id = p_finding
    ) q JOIN observations o ON o.id = q.oid
      JOIN entities e ON e.id = o.subject_entity_id
      LEFT JOIN endpoints  ep ON ep.entity_id = e.id
      LEFT JOIN parameters pa ON pa.entity_id = e.id
      LEFT JOIN technologies te ON te.entity_id = e.id
      LEFT JOIN identities  idn ON idn.entity_id = e.id
      CROSS JOIN LATERAL (VALUES (e.dedup_key),(ep.method),(ep.path_template),
                                 (pa.name),(te.name),(te.version),(idn.slot_name)) t(tok)
     WHERE t.tok IS NOT NULL
    UNION
    -- the finding's own subject entity
    SELECT t.tok, 'subject_entity' FROM findings f
      JOIN entities e ON e.id = f.subject_entity_id
      LEFT JOIN endpoints  ep ON ep.entity_id = e.id
      LEFT JOIN parameters pa ON pa.entity_id = e.id
      CROSS JOIN LATERAL (VALUES (e.dedup_key),(ep.method),(ep.path_template),(pa.name)) t(tok)
     WHERE f.id = p_finding AND t.tok IS NOT NULL
    UNION
    -- the immutable spec the runtime replayed. Every scalar in it.
    SELECT s, 'test_spec' FROM findings f
      JOIN test_runs tr ON tr.id = f.validated_by_test_run_id
      JOIN tests t ON t.id = tr.test_id
      CROSS JOIN LATERAL jsonb_scalars(t.spec) s
     WHERE f.id = p_finding;
$$;

-- Rule 2 + rule 3, as a constraint. DEFERRED because a step's citations are
-- written after the step: at COMMIT both exist, and neither can be written
-- without the other holding.
CREATE FUNCTION enforce_chain_step_grounding() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE m report_mechanisms%ROWTYPE; k text; v text; n int; f uuid;
BEGIN
    SELECT * INTO m FROM report_mechanisms WHERE id = NEW.mechanism_id;
    f := NEW.finding_id;

    -- every slot the template declares is supplied, and nothing else is
    FOR k IN SELECT unnest(m.slots) LOOP
        IF NOT (NEW.params ? k) THEN
            RAISE EXCEPTION 'chain step %: mechanism % needs slot %', NEW.ordinal, m.id, k;
        END IF;
    END LOOP;
    FOR k IN SELECT jsonb_object_keys(NEW.params) LOOP
        IF NOT (k = ANY (m.slots)) THEN
            RAISE EXCEPTION 'chain step %: mechanism % has no slot %', NEW.ordinal, m.id, k;
        END IF;
    END LOOP;

    -- rule 2: no new facts
    FOR v IN SELECT jsonb_scalars(NEW.params) LOOP
        IF NOT EXISTS (SELECT 1 FROM finding_fact_tokens(f) t WHERE t.token = v) THEN
            RAISE EXCEPTION 'new fact: chain step % would print "%", which is in no row this finding cites',
                  NEW.ordinal, v;
        END IF;
    END LOOP;

    -- min citations
    SELECT count(*) INTO n FROM finding_chain_step_citations WHERE step_id = NEW.id;
    IF n < m.min_citations THEN
        RAISE EXCEPTION 'chain step %: mechanism % needs % citations, has %',
              NEW.ordinal, m.id, m.min_citations, n;
    END IF;

    -- rule 3: a mechanism sentence about a technology needs an observation
    -- about that technology among the step's citations
    IF m.requires_technology IS NOT NULL THEN
        IF NOT EXISTS (
            SELECT 1 FROM finding_chain_step_citations c
              JOIN observations o ON o.id = c.observation_id
              JOIN technologies te ON te.entity_id = o.subject_entity_id
             WHERE c.step_id = NEW.id AND o.kind = 'technology_identified'
               AND te.name = m.requires_technology)
        THEN
            RAISE EXCEPTION 'unlicensed mechanism: step % claims % behaviour with no cited technology_identified observation for %',
                  NEW.ordinal, m.requires_technology, m.requires_technology;
        END IF;
    END IF;

    RETURN NEW;
END $$;

CREATE CONSTRAINT TRIGGER chain_step_grounding
    AFTER INSERT OR UPDATE ON finding_chain_steps
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION enforce_chain_step_grounding();
ALTER TABLE finding_chain_steps ENABLE ALWAYS TRIGGER chain_step_grounding;


-- ===========================================================================
-- 6. Severity: the system rates, in public it only describes
-- ===========================================================================

-- CVSS v3.1 base only. No temporal, no environmental: environmental needs asset
-- knowledge the harness does not have, and a bounty triager rescoring with it
-- is the correct owner of that half of the vector.
CREATE FUNCTION cvss31_base_score(p_vector text) RETURNS numeric
LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
    m         text[];
    av numeric; ac numeric; pr numeric; ui numeric;
    c numeric; i numeric; a numeric;
    scope_c  boolean;
    iss numeric; impact numeric; expl numeric; raw numeric; scaled bigint;
    part text; kv text[];
    g   jsonb := '{}'::jsonb;
BEGIN
    IF p_vector IS NULL THEN RETURN NULL; END IF;

    FOREACH part IN ARRAY string_to_array(p_vector, '/') LOOP
        kv := string_to_array(part, ':');
        IF array_length(kv,1) = 2 THEN g := g || jsonb_build_object(kv[1], kv[2]); END IF;
    END LOOP;

    scope_c := (g->>'S') = 'C';
    av := CASE g->>'AV' WHEN 'N' THEN 0.85 WHEN 'A' THEN 0.62 WHEN 'L' THEN 0.55 WHEN 'P' THEN 0.2 END;
    ac := CASE g->>'AC' WHEN 'L' THEN 0.77 WHEN 'H' THEN 0.44 END;
    pr := CASE WHEN scope_c
               THEN CASE g->>'PR' WHEN 'N' THEN 0.85 WHEN 'L' THEN 0.68 WHEN 'H' THEN 0.50 END
               ELSE CASE g->>'PR' WHEN 'N' THEN 0.85 WHEN 'L' THEN 0.62 WHEN 'H' THEN 0.27 END END;
    ui := CASE g->>'UI' WHEN 'N' THEN 0.85 WHEN 'R' THEN 0.62 END;
    c  := CASE g->>'C' WHEN 'H' THEN 0.56 WHEN 'L' THEN 0.22 WHEN 'N' THEN 0 END;
    i  := CASE g->>'I' WHEN 'H' THEN 0.56 WHEN 'L' THEN 0.22 WHEN 'N' THEN 0 END;
    a  := CASE g->>'A' WHEN 'H' THEN 0.56 WHEN 'L' THEN 0.22 WHEN 'N' THEN 0 END;

    IF av IS NULL OR ac IS NULL OR pr IS NULL OR ui IS NULL
       OR c IS NULL OR i IS NULL OR a IS NULL OR g->>'S' IS NULL THEN
        RAISE EXCEPTION 'not a CVSS v3.1 base vector: %', p_vector;
    END IF;

    iss := 1 - ((1-c) * (1-i) * (1-a));
    impact := CASE WHEN scope_c
                   THEN 7.52 * (iss - 0.029) - 3.25 * power(iss - 0.02, 15)
                   ELSE 6.42 * iss END;
    IF impact <= 0 THEN RETURN 0.0; END IF;

    expl := 8.22 * av * ac * pr * ui;
    raw  := least(CASE WHEN scope_c THEN 1.08 * (impact + expl) ELSE impact + expl END, 10);

    -- CVSS v3.1 roundup, to the letter: smallest one-decimal value >= raw.
    scaled := round(raw * 100000)::bigint;
    IF scaled % 10000 = 0 THEN
        RETURN (scaled / 100000.0)::numeric(4,1);
    ELSE
        RETURN ((floor(scaled / 10000.0) + 1) / 10.0)::numeric(4,1);
    END IF;
END $$;

CREATE FUNCTION cvss_band(p_score numeric) RETURNS text
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE WHEN p_score = 0   THEN 'info'
                WHEN p_score < 4.0 THEN 'low'
                WHEN p_score < 7.0 THEN 'medium'
                WHEN p_score < 9.0 THEN 'high'
                ELSE 'critical' END;
$$;

-- The vector is DERIVED, never chosen: impact from the witnessed effects,
-- privileges from the spec's own preconditions, UI from the class, scope from
-- whether any witnessed effect crosses an identity boundary. A model never
-- names a metric, and there is no severity column a model may write.
CREATE FUNCTION compute_finding_cvss(p_finding uuid) RETURNS text
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_c text; v_i text; v_a text; v_s text; v_pr text; v_ui text;
    rank_of jsonb := '{"N":0,"L":1,"H":2}'::jsonb;
    n_c int; n_i int; n_a int; b_s boolean; n_eff int;
BEGIN
    -- No witnessed effect, no score. NULL rather than an exception: the
    -- unscorable finding is a `report_blockers` row, and a check that runs over
    -- every finding must not blow up on the one that is not ready.
    SELECT count(*) INTO n_eff FROM finding_effects WHERE finding_id = p_finding;
    IF n_eff = 0 THEN RETURN NULL; END IF;

    SELECT max((rank_of->>e.impact_c)::int), max((rank_of->>e.impact_i)::int),
           max((rank_of->>e.impact_a)::int), bool_or(e.scope_change)
      INTO n_c, n_i, n_a, b_s
      FROM finding_effects fe JOIN report_effects e ON e.id = fe.effect_id
     WHERE fe.finding_id = p_finding;

    v_c := (ARRAY['N','L','H'])[n_c + 1];
    v_i := (ARRAY['N','L','H'])[n_i + 1];
    v_a := (ARRAY['N','L','H'])[n_a + 1];
    v_s := CASE WHEN b_s THEN 'C' ELSE 'U' END;

    -- PR: does the replayed spec need an identity at all?
    SELECT CASE WHEN EXISTS (
             SELECT 1 FROM findings f
               JOIN test_runs tr ON tr.id = f.validated_by_test_run_id
               JOIN tests t ON t.id = tr.test_id
               CROSS JOIN LATERAL jsonb_array_elements(coalesce(t.spec->'preconditions','[]'::jsonb)) p
              WHERE f.id = p_finding AND p->>'kind' = 'identity')
           THEN 'L' ELSE 'N' END INTO v_pr;

    SELECT vc.cvss_ui INTO v_ui
      FROM findings f JOIN vulnerability_classes vc ON vc.id = f.class_id
     WHERE f.id = p_finding;

    -- AV:N and AC:L are constants here and that is a limitation, not a
    -- measurement: the destination is web/API targets reached over the network,
    -- and nothing in the schema measures attack complexity.
    RETURN format('AV:N/AC:L/PR:%s/UI:%s/S:%s/C:%s/I:%s/A:%s',
                  v_pr, coalesce(v_ui,'N'), v_s, v_c, v_i, v_a);
END $$;

CREATE FUNCTION apply_computed_severity(p_finding uuid) RETURNS text
LANGUAGE plpgsql AS $$
DECLARE v text; b text;
BEGIN
    v := compute_finding_cvss(p_finding);
    IF v IS NULL THEN
        RAISE EXCEPTION 'finding % has no witnessed effect: nothing to score', p_finding;
    END IF;
    b := cvss_band(cvss31_base_score(v));
    UPDATE findings SET severity = b, cvss_vector = v WHERE id = p_finding;
    RETURN v;
END $$;


-- ===========================================================================
-- 7. Duplicates, known issues, and everything else that blocks emission
-- ===========================================================================

-- The dedup key of a REPORT is coarser than ticket 06's hypothesis dedup key:
-- two hypotheses about different parameters of one endpoint are two
-- investigations but one report.
CREATE FUNCTION finding_signature(p_finding uuid) RETURNS text
LANGUAGE sql STABLE AS $$
    SELECT f.class_id || '|' || e.dedup_key
      FROM findings f JOIN entities e ON e.id = f.subject_entity_id
     WHERE f.id = p_finding;
$$;

CREATE FUNCTION report_blockers(p_finding uuid)
RETURNS TABLE (severity text, code text, detail text)
LANGUAGE sql STABLE AS $$
    -- a program said in writing it does not want this
    SELECT 'hard', 'known_issue', k.note
      FROM findings f
      JOIN entities e ON e.id = f.subject_entity_id
      JOIN program_known_issues k
        ON k.program_id = f.program_id AND k.class_id = f.class_id
       AND (k.entity_like IS NULL OR e.dedup_key LIKE k.entity_like)
     WHERE f.id = p_finding
    UNION ALL
    -- already told them, or about to tell them twice
    SELECT 'hard', 'duplicate', 'same signature as ' || o.label || ' (' || o.status || ')'
      FROM findings f JOIN findings o
        ON o.program_id = f.program_id AND o.id <> f.id
       AND finding_signature(o.id) = finding_signature(f.id)
       AND o.status IN ('validated','reported')
     WHERE f.id = p_finding AND f.duplicate_of_finding_id IS NULL
    UNION ALL
    -- ticket 06's rule, restated where the reporter can see it
    SELECT 'hard', 'not_validated', 'status=' || f.status ||
           ', validated_by_test_run_id=' || coalesce(f.validated_by_test_run_id::text,'null')
      FROM findings f
     WHERE f.id = p_finding
       AND (f.status <> 'validated' OR f.validated_by_test_run_id IS NULL)
    UNION ALL
    SELECT 'hard', 'no_effect', 'no finding_effects row: the impact sentence has nothing to say'
      FROM findings f WHERE f.id = p_finding
       AND NOT EXISTS (SELECT 1 FROM finding_effects fe WHERE fe.finding_id = f.id)
    UNION ALL
    SELECT 'hard', 'no_chain', 'no finding_chain_steps row'
      FROM findings f WHERE f.id = p_finding
       AND NOT EXISTS (SELECT 1 FROM finding_chain_steps s WHERE s.finding_id = f.id)
    UNION ALL
    SELECT 'hard', 'severity_stale',
           'stored ' || f.severity || '/' || coalesce(f.cvss_vector,'null') ||
           ', computed ' || cvss_band(cvss31_base_score(c.vec)) || '/' || c.vec
      FROM findings f CROSS JOIN LATERAL (SELECT compute_finding_cvss(f.id) AS vec) c
     WHERE f.id = p_finding AND c.vec IS NOT NULL
       AND (f.cvss_vector IS DISTINCT FROM c.vec
            OR f.severity <> cvss_band(cvss31_base_score(c.vec)))
    UNION ALL
    -- a witnessed effect whose witness is not among the finding's evidence
    SELECT 'hard', 'unwitnessed_effect', 'effect ' || fe.effect_id || ' cites an observation the finding does not'
      FROM finding_effects fe
     WHERE fe.finding_id = p_finding
       AND NOT EXISTS (SELECT 1 FROM finding_evidence x
                        WHERE x.finding_id = fe.finding_id AND x.observation_id = fe.witness_observation_id);
$$;

-- 018 built `finding_class_divergence` and left it empty pending this seed. It
-- is a SOFT signal: the mapping is advisory, and a finding whose class diverges
-- from its hypotheses' property classes is often the interesting one.
CREATE VIEW report_review_signals AS
SELECT d.finding_id, 'class_divergence'::text AS code,
       'class ' || d.class_id || ' not expected from ' || array_to_string(d.hypothesis_property_classes, ', ')
  FROM finding_class_divergence d;


-- ===========================================================================
-- 8. The source bundle -- the only thing the renderer may read
-- ===========================================================================

-- Rule 1 as code. `findings.title`, `observations.summary`,
-- `hypotheses.statement` and `tests.label` are model-writable and none of them
-- appears below. If a byte is not reachable from here it cannot reach a report.
CREATE FUNCTION report_source_bundle(p_finding uuid, p_template text)
RETURNS jsonb LANGUAGE sql STABLE AS $$
    SELECT jsonb_build_object(
      'finding_label', f.label,
      'template',      p_template,
      'blocks',        (SELECT jsonb_agg(b.block_id ORDER BY b.ordinal)
                          FROM report_template_blocks b WHERE b.template_id = p_template),
      'class', (SELECT jsonb_build_object('id',vc.id,'name',vc.name,'cwe',vc.cwe_id,
                                          'short_name',vc.short_name,'remediation',vc.remediation)
                  FROM vulnerability_classes vc WHERE vc.id = f.class_id),
      'subject', (SELECT jsonb_build_object('dedup_key',e.dedup_key,'type',e.type,
                                            'method',ep.method,'path',ep.path_template,
                                            'base_url',app.base_url)
                    FROM entities e
                    LEFT JOIN endpoints ep ON ep.entity_id = e.id
                    LEFT JOIN applications app ON app.entity_id = ep.application_id
                   WHERE e.id = f.subject_entity_id),
      'provenance', (SELECT jsonb_build_object(
                              'lane', (SELECT string_agg(DISTINCT r.lane, ',') FROM finding_cited_receipts fcr
                                         JOIN receipts r ON r.id = fcr.receipt_id
                                        WHERE fcr.finding_id = f.id),
                              'at',   (SELECT to_char(min(r.ts_arrival) AT TIME ZONE 'UTC','HH24:MI:SS')
                                         FROM finding_cited_receipts fcr
                                         JOIN receipts r ON r.id = fcr.receipt_id
                                        WHERE fcr.finding_id = f.id))),
      'effects', (SELECT coalesce(jsonb_agg(jsonb_build_object('id',re.id,'phrase',re.phrase)
                                            ORDER BY fe.ordinal), '[]'::jsonb)
                    FROM finding_effects fe JOIN report_effects re ON re.id = fe.effect_id
                   WHERE fe.finding_id = f.id),
      'technology', (SELECT te.name FROM finding_chain_step_citations c
                       JOIN finding_chain_steps st ON st.id = c.step_id
                       JOIN observations o ON o.id = c.observation_id
                       JOIN technologies te ON te.entity_id = o.subject_entity_id
                      WHERE st.finding_id = f.id AND o.kind = 'technology_identified'
                      ORDER BY st.ordinal, c.ordinal LIMIT 1),
      'chain', (SELECT coalesce(jsonb_agg(jsonb_build_object(
                          'ordinal', st.ordinal, 'label', m.label,
                          'template', m.template, 'params', st.params,
                          'citations', (SELECT coalesce(jsonb_agg(coalesce(r2.label, o2.label)
                                                        ORDER BY c2.ordinal), '[]'::jsonb)
                                          FROM finding_chain_step_citations c2
                                          LEFT JOIN receipts r2 ON r2.id = c2.receipt_id
                                          LEFT JOIN observations o2 ON o2.id = c2.observation_id
                                         WHERE c2.step_id = st.id))
                        ORDER BY st.ordinal), '[]'::jsonb)
                  FROM finding_chain_steps st JOIN report_mechanisms m ON m.id = st.mechanism_id
                 WHERE st.finding_id = f.id),
      'spec', (SELECT t.spec FROM test_runs tr JOIN tests t ON t.id = tr.test_id
                WHERE tr.id = f.validated_by_test_run_id),
      'spec_sha256', (SELECT t.spec_sha256 FROM test_runs tr JOIN tests t ON t.id = tr.test_id
                       WHERE tr.id = f.validated_by_test_run_id),
      'evidence', (SELECT coalesce(jsonb_agg(jsonb_build_object(
                            'receipt', r.label, 'method', r.method, 'path', r.path,
                            'status', r.status_code,
                            'request_sha', r.request_agent_sha,
                            'response_sha', r.response_agent_sha,
                            'visibility', (SELECT a.visibility FROM artifacts a
                                            WHERE a.sha256 = r.response_agent_sha))
                          ORDER BY r.ts_arrival, r.label), '[]'::jsonb)
                     FROM (SELECT DISTINCT receipt_id FROM finding_cited_receipts
                            WHERE finding_id = f.id) x
                     JOIN receipts r ON r.id = x.receipt_id),
      'severity', jsonb_build_object(
            'vector', f.cvss_vector, 'band', f.severity,
            'score',  CASE WHEN f.cvss_vector IS NULL THEN NULL
                           ELSE cvss31_base_score(f.cvss_vector) END,
            'origin', 'computed by the runtime from witnessed effects; not adjudicated'),
      'blockers', (SELECT coalesce(jsonb_agg(jsonb_build_object('code',code,'detail',detail)
                                             ORDER BY code, detail), '[]'::jsonb)
                     FROM report_blockers(f.id))
    )
    FROM findings f WHERE f.id = p_finding;
$$;

-- `blockers` is deliberately NOT in the digest. Blockers are the gate evaluated
-- at approval time, not part of the document's identity -- and approving a
-- finding changes its own blocker set (status stops being `validated`), so a
-- digest that included them would invalidate the approval it just granted.
CREATE FUNCTION finding_source_digest(p_finding uuid, p_template text) RETURNS text
LANGUAGE sql STABLE AS $$
    SELECT encode(sha256(convert_to(
             (report_source_bundle(p_finding, p_template) - 'blockers')::text, 'UTF8')), 'hex');
$$;


-- ===========================================================================
-- 9. The approval gate -- preconditions on ticket 28's transition
-- ===========================================================================

CREATE FUNCTION enforce_report_approval() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE rr report_renderings%ROWTYPE; b record; fresh text;
BEGIN
    IF NEW.to_status <> 'reported' THEN RETURN NEW; END IF;

    IF NEW.approved_rendering_id IS NULL THEN
        RAISE EXCEPTION 'no approval: a transition to reported must name the report_renderings row the human read';
    END IF;

    SELECT * INTO rr FROM report_renderings WHERE id = NEW.approved_rendering_id;
    IF rr.finding_id <> NEW.finding_id THEN
        RAISE EXCEPTION 'approval names a rendering of finding %, not of %', rr.finding_id, NEW.finding_id;
    END IF;

    fresh := finding_source_digest(rr.finding_id, rr.template_id);
    IF rr.source_digest <> fresh THEN
        RAISE EXCEPTION 'stale approval: rendering % was made from source digest %, which is now %',
              rr.id, left(rr.source_digest,12), left(fresh,12);
    END IF;

    FOR b IN SELECT * FROM report_blockers(NEW.finding_id) WHERE severity = 'hard' LOOP
        RAISE EXCEPTION 'blocked: % -- %', b.code, b.detail;
    END LOOP;

    RETURN NEW;
END $$;

-- Name matters. BEFORE-row triggers fire in alphabetical order, and this one
-- sorts AFTER `finding_transitions_actor_kind_guard` on purpose: a caller who
-- is not a member of `rk2_human` must be told THAT, by 026, and not be handed a
-- report-shaped complaint about a missing rendering.
CREATE TRIGGER finding_transitions_report_approval
    BEFORE INSERT ON finding_transitions
    FOR EACH ROW EXECUTE FUNCTION enforce_report_approval();
ALTER TABLE finding_transitions ENABLE ALWAYS TRIGGER finding_transitions_report_approval;


-- ===========================================================================
-- 10. check_report_grounding() -- rules 1-5 as a query
-- ===========================================================================

CREATE FUNCTION check_report_grounding()
RETURNS TABLE (rule text, obj text, detail text)
LANGUAGE sql STABLE AS $$
    -- 1. a template may only reference registered blocks (FK does this) and
    --    every registered block must be reachable from some template
    SELECT 'block_unused', b.id, 'no template includes it'
      FROM report_blocks b
     WHERE NOT EXISTS (SELECT 1 FROM report_template_blocks t WHERE t.block_id = b.id)
    UNION ALL
    -- 2. a mechanism template may not contain a slot it did not declare, and
    --    may not declare one it does not use
    SELECT 'mechanism_slot_mismatch', m.id,
           'declared ' || array_to_string(m.slots,',') || ', used ' ||
           coalesce(array_to_string(ARRAY(SELECT (regexp_matches(m.template,'\{([a-z_]+)\}','g'))[1]), ','), '')
      FROM report_mechanisms m
     WHERE ARRAY(SELECT DISTINCT (regexp_matches(m.template,'\{([a-z_]+)\}','g'))[1] ORDER BY 1)
           IS DISTINCT FROM ARRAY(SELECT DISTINCT s FROM unnest(m.slots) s ORDER BY 1)
    UNION ALL
    -- 3. no report row may cite anything off the agent lane
    SELECT 'citation_off_agent_lane', s.finding_id::text, r.lane
      FROM finding_chain_step_citations c
      JOIN finding_chain_steps s ON s.id = c.step_id
      JOIN receipts r ON r.id = c.receipt_id
     WHERE r.lane <> 'agent'
    UNION ALL
    -- 4. no chain step may print a value that is in no cited row
    SELECT 'new_fact', s.finding_id::text, v
      FROM finding_chain_steps s CROSS JOIN LATERAL jsonb_scalars(s.params) v
     WHERE NOT EXISTS (SELECT 1 FROM finding_fact_tokens(s.finding_id) t WHERE t.token = v)
    UNION ALL
    -- 5. stored severity is the computed severity
    SELECT 'severity_stale', f.label, coalesce(f.cvss_vector,'null')
      FROM findings f CROSS JOIN LATERAL (SELECT compute_finding_cvss(f.id) AS vec) c
     WHERE c.vec IS NOT NULL AND f.cvss_vector IS DISTINCT FROM c.vec
    UNION ALL
    -- 6. an approved rendering that no longer matches its source
    SELECT 'approval_stale', rr.id::text, left(rr.source_digest,12)
      FROM finding_transitions ft JOIN report_renderings rr ON rr.id = ft.approved_rendering_id
     WHERE rr.source_digest <> finding_source_digest(rr.finding_id, rr.template_id);
$$;

COMMENT ON FUNCTION check_report_grounding() IS
    'ticket 19: the report rules as a query. Zero rows is the invariant.';


-- ===========================================================================
-- Z -- what the corpus requires of any migration, which 029 predated
-- ===========================================================================

-- Emission. Six of these are vocabulary and five are the report itself. None of
-- them emits: a report is a rendering of findings that already emitted, and the
-- transition to `reported` -- which does emit, through ticket 06's
-- `finding_transitions` -- is the event that says a report happened.
INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
 ('report_effects',              'reference', 'the effect vocabulary and its CVSS impact metrics; changed only by migration', '19'),
 ('report_blocks',               'reference', 'the block registry; changed only by migration', '19'),
 ('report_templates',            'reference', 'per-platform report form; changed only by migration', '19'),
 ('report_template_blocks',      'reference', 'the ordering of the above; changed only by migration', '19'),
 ('report_mechanisms',           'reference', 'curated sentence templates about technologies; changed only by migration', '19'),
 ('redaction_rules',             'reference', 'what counts as another person''s data; changed only by migration', '19'),
 ('program_known_issues',        'reference', 'the program''s published do-not-send list, entered by the operator through the control surface', '19'),
 ('finding_effects',             'covered',   'the impact half of a finding, written with it; finding.created/updated is the record', '19'),
 ('finding_chain_steps',         'covered',   'the chain half of a finding, written with it; finding.created/updated is the record', '19'),
 ('finding_chain_step_citations','covered',   'the citations of a chain step, written in the same statement as the step', '19'),
 ('report_renderings',           'derived',   'the bytes are a pure function of the finding and the template -- finding_source_digest() is that function -- and re-rendering is how a lost rendering comes back', '19');

-- The agent read surface. 029 issued `GRANT SELECT ... TO rk2_state` on all
-- eleven; ticket 33 made that a per-column decision, so the columns that
-- existed when this migration ran are enumerated and `apply_state_grants()`
-- issues them. A column added to one of these tables later is not published by
-- inheritance, which is the point.
INSERT INTO state_read_surface (table_name, column_name, added_by)
SELECT c.relname, a.attname, '19'
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
  JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
 WHERE c.relname IN ('report_effects','report_blocks','report_templates',
                     'report_template_blocks','report_mechanisms','redaction_rules',
                     'program_known_issues','finding_effects','finding_chain_steps',
                     'finding_chain_step_citations','report_renderings');

INSERT INTO standing_checks (name, query, owner_ticket, note) VALUES
 ('report_grounding', 'SELECT * FROM check_report_grounding()', '19',
  'no report cites off the agent lane, prints a fact in no cited row, or carries a severity or an approval that no longer matches what it was computed from');
