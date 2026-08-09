-- ---------------------------------------------------------------------------
-- 018_ticket27_vocabularies.sql   (ticket 27)
--
-- Fills in the two closed vocabularies ticket 06 made load-bearing and left
-- empty: `observations.kind` and `hypotheses.property_class`.
--
-- The `property_class` granularity is not chosen here by argument. It is the
-- output of `tests/vocab_experiment.sql`, which runs the Q14 dedup index over a
-- 55-investigation corpus normalised from v1's five real engagement ledgers, at
-- three granularities, and counts what the index destroys and what it lets
-- through. Numbers in the ticket. The short form:
--
--     arm                       collisions   unwritable   fragmented
--     A  8 flat families          63/165      17 of 55     7
--     B  family.leaf              19/165       4 of 55    11
--     C  family.leaf + narrow     11/165       2 of 55    12
--
-- A collision is not recoverable -- the row cannot exist, so the second
-- hypothesis about that endpoint is destroyed. A fragmentation is recoverable:
-- ticket 08's stage-2 near-match pass already exists to catch it. The flat list
-- the ticket proposed loses 31% of the corpus outright, so it is rejected.
--
-- Before any of that could be measured, one thing had to be fixed:
--
--   The dedup index as ticket 06 shipped it is `NULLS DISTINCT` (the default).
--   49 of 55 investigations in the corpus have at least one NULL identity slot
--   -- every unauthenticated hypothesis, and every single-identity one -- so
--   the index never fired for them. Measured: 98 surplus rows across every arm,
--   including investigations carrying exactly one possible label. The Q14
--   dedup key did not exist for 89% of hypotheses.
-- ---------------------------------------------------------------------------


-- ===========================================================================
-- 1. property_class -- a two-level reference table, dedup on the leaf
-- ===========================================================================

-- The family is a rollup unit (reporting, ticket 16's coverage counts, the
-- scheduler's per-property diversity term), never a dedup key. It is a table
-- rather than a column so a typo cannot invent a ninth family.
CREATE TABLE property_class_families (
    id          text PRIMARY KEY,
    name        text NOT NULL,
    description text NOT NULL
);

INSERT INTO property_class_families (id, name, description) VALUES
 ('authorization',          'Authorization',
  'whether a principal may act on an object at all'),
 ('authentication',         'Authentication',
  'whether the claim to be a principal is actually verified'),
 ('injection',              'Injection',
  'whether attacker-controlled input reaches an interpreter, parser or fetcher'),
 ('information_disclosure', 'Information disclosure',
  'whether the response carries more than the caller is entitled to know'),
 ('business_logic',         'Business logic',
  'whether the application''s own rules about order, quantity and repetition hold'),
 ('rate_limiting',          'Rate limiting',
  'whether repetition or cost is bounded'),
 ('session_handling',       'Session handling',
  'whether a session begins, persists and ends when it should'),
 ('transport',              'Transport',
  'whether the channel itself carries the guarantees the application assumes');

-- The leaf. `id` is `family.leaf` so an agent citing a class in prose says
-- something a reader understands without a lookup, and so the family is
-- recoverable from the key by prefix in any query that has only the key.
--
-- The leaf answers "what test would settle this", not "what CWE is it". That
-- distinction is the whole design: `vulnerability_classes` (below) is the CWE
-- axis, and it is a different axis.
CREATE TABLE property_classes (
    id          text PRIMARY KEY,
    family_id   text NOT NULL REFERENCES property_class_families(id),
    name        text NOT NULL,
    description text NOT NULL,
    CHECK (id LIKE family_id || '.%'),
    CHECK (id ~ '^[a-z_]+\.[a-z_]+$')
);

CREATE INDEX property_classes_family_idx ON property_classes (family_id);

INSERT INTO property_classes (id, family_id, name, description) VALUES
 -- authorization: the identity pair in the dedup key already separates
 -- horizontal from vertical, so the leaf splits by WHAT is not checked, not by
 -- who is asking.
 ('authorization.object_ownership','authorization','Object ownership',
  'the object named by the request is not checked against the caller'),
 ('authorization.function_access','authorization','Function access',
  'the route or operation itself is reachable by a caller who should not reach it'),
 ('authorization.tenant_isolation','authorization','Tenant isolation',
  'the boundary crossed is an organisation or realm, not a single object'),
 ('authorization.token_scope','authorization','Token scope',
  'the credential is honoured beyond the scope, audience or binding it was minted for'),
 ('authorization.state_transition','authorization','State transition',
  'the object is in a state that should forbid this operation (revoked, deleted, closed)'),

 -- authentication: is the claim verified at all
 ('authentication.credential_verification','authentication','Credential verification',
  'the presented secret or signature is not actually checked'),
 ('authentication.factor_enforcement','authentication','Factor enforcement',
  'a required second factor or step-up can be skipped'),
 ('authentication.federation_trust','authentication','Federation trust',
  'an assertion from an external issuer is trusted further than it should be'),
 ('authentication.recovery_flow','authentication','Recovery flow',
  'the reset, recover or enrolment path grants what the primary path would refuse'),

 -- injection: split by the interpreter, because the interpreter is the test
 ('injection.query_language','injection','Query language injection',
  'input reaches a database query (SQL, NoSQL, LDAP, XPath)'),
 ('injection.command','injection','Command injection',
  'input reaches a shell or process invocation'),
 ('injection.template','injection','Template injection',
  'input reaches a server-side template or expression evaluator'),
 ('injection.markup','injection','Markup injection',
  'input reaches a browser as markup or script (XSS, HTML, SVG)'),
 ('injection.document_parser','injection','Document parser abuse',
  'input reaches a structured parser or deserialiser (XML/XXE, spreadsheet, object graph)'),
 ('injection.request_forgery','injection','Request forgery',
  'input controls a request the server itself makes (SSRF, header injection, redirect chains)'),
 ('injection.path','injection','Path traversal',
  'input reaches a filesystem or object-store path'),

 -- information disclosure: split by the channel the excess arrives on
 ('information_disclosure.error_detail','information_disclosure','Error detail',
  'a failure path returns internal detail (stack trace, query, version, path)'),
 ('information_disclosure.identifier_oracle','information_disclosure','Identifier oracle',
  'response differences reveal whether an identifier exists or is valid'),
 ('information_disclosure.artifact_exposure','information_disclosure','Artifact exposure',
  'a file or document is reachable that was not meant to be published'),
 ('information_disclosure.excess_field','information_disclosure','Excess field',
  'a successful response carries fields beyond what the caller is entitled to'),

 -- business logic
 ('business_logic.workflow_order','business_logic','Workflow order',
  'a step can be reached out of order or skipped'),
 ('business_logic.quantity_or_price','business_logic','Quantity or price',
  'an amount, price, quota or entitlement can be set to a value the rules forbid'),
 ('business_logic.replay','business_logic','Replay',
  'a single-use action succeeds more than once'),

 -- rate limiting: the leaf is the dimension the limit is keyed on, which is
 -- exactly what distinguishes the tests
 ('rate_limiting.per_identity','rate_limiting','Per-identity limit',
  'repetition against one account, key or object is not bounded'),
 ('rate_limiting.per_origin','rate_limiting','Per-origin limit',
  'repetition from one caller across many targets is not bounded'),
 ('rate_limiting.resource_cost','rate_limiting','Resource cost',
  'one request can be made arbitrarily expensive'),

 -- session handling
 ('session_handling.lifetime','session_handling','Session lifetime',
  'a session or token outlives expiry, logout or revocation'),
 ('session_handling.fixation','session_handling','Session fixation',
  'a session identifier chosen before authentication survives it'),
 ('session_handling.cookie_scope','session_handling','Cookie scope',
  'the cookie''s flags, domain or path expose it beyond its intended origin'),
 ('session_handling.csrf','session_handling','Cross-site request forgery',
  'a state-changing request is accepted without proof of same-origin intent'),

 -- transport. NOTE ticket 04: TLS interception through the scope proxy costs
 -- certificate identity and ALPN fidelity, so no hypothesis in this family can
 -- be settled by a proxy receipt. They are proposable and testable only by a
 -- tool run outside the proxy path. See the ticket's hand-off to 24.
 ('transport.tls_configuration','transport','TLS configuration',
  'the negotiated protocol, cipher or downgrade behaviour is weaker than assumed'),
 ('transport.certificate_trust','transport','Certificate trust',
  'the certificate presented is trusted more widely than the application assumes'),
 ('transport.header_policy','transport','Transport header policy',
  'HSTS, CSP or an equivalent channel policy is absent, permissive or misscoped');


-- ===========================================================================
-- 2. observations.kind -- closed, and split by whether it can be evidence
-- ===========================================================================

-- The ticket asks whether this vocabulary is closed at all. It is, for the same
-- reason `property_class` is: the value is written by promotion from agent
-- output, so a free string is a value a model invents. Measured on v1's 502
-- real non-surface leads, a free second label produced 150 distinct values of
-- which 62% were the workflow stage rather than the thing observed.
--
-- `is_evidential` is what makes "only some are evidence for anything"
-- enforceable rather than editorial. A discovered endpoint is a fact with
-- provenance and belongs in this table; it is not evidence for or against any
-- hypothesis, and the trigger below refuses to let it count as one.
--
-- `allowed_provenance` is the second, sharper column, and it is the standing
-- constraint written down. "LLM proposes, runtime commits" says an observation
-- is only real if it points at a runtime-generated provenance record: a proxy
-- receipt for network behaviour, a tool run over a content-addressed artifact
-- for local analysis. Ticket 06's CHECK already forces *one* of the two on every
-- row -- but it lets any kind cite either, so a model could assert a
-- `content_match` (a local-analysis fact) by pointing at a raw network receipt
-- it never analysed, or claim a `timing_differential` from a tool run that never
-- touched the wire. The record has to be the *right kind* of record, which is a
-- per-kind fact and therefore belongs in the vocabulary.
--
-- A kind whose set would be empty does not go in the table at all. That is the
-- test the ticket's proposed list fails: see the note under the insert.
CREATE TABLE observation_kinds (
    id                 text PRIMARY KEY CHECK (id ~ '^[a-z_]+$'),
    name               text NOT NULL,
    is_evidential      boolean NOT NULL,
    allowed_provenance text[] NOT NULL,
    description        text NOT NULL,
    -- non-empty, no duplicates, and nothing outside the two provenance records
    -- ticket 06's observations CHECK can actually store. Enumerated rather than
    -- computed because a CHECK may not carry a subquery, and because an empty
    -- set has to be unwritable, not merely discouraged.
    CONSTRAINT observation_kinds_allowed_provenance_closed
      CHECK (array_to_string(allowed_provenance, ',')
             IN ('receipt', 'tool_run', 'receipt,tool_run'))
);

INSERT INTO observation_kinds (id, name, is_evidential, allowed_provenance, description) VALUES
 -- evidential: each of these is a comparison or a decision, which is what a
 -- hypothesis can be tested against
 ('response_differential','Response differential', true, '{receipt}',
  'two requests differing in one controlled way produced different responses'),
 ('response_invariant','Response invariant', true, '{receipt}',
  'the controlled change produced no difference -- the observation a refutation needs'),
 ('timing_differential','Timing differential', true, '{receipt}',
  'response time changed measurably with the controlled change'),
 ('reflected_input','Reflected input', true, '{receipt,tool_run}',
  'supplied input appeared in the response, with its encoding context'),
 ('error_detail','Error detail', true, '{receipt,tool_run}',
  'the response carried an internal error, stack trace or interpreter message'),
 ('state_change','State change', true, '{receipt}',
  'a side effect was observable on a later request'),
 ('credential_effect','Credential effect', true, '{receipt}',
  'an authentication or authorisation decision was returned for a presented credential'),
 ('content_match','Content match', true, '{tool_run}',
  'a tool run over a content-addressed artifact matched a declared pattern'),
 ('header_policy_observed','Header policy observed', true, '{receipt,tool_run}',
  'a security-relevant response header was present, absent or carried a given value'),

 -- non-evidential: surface facts. Real observations, provenance and all; they
 -- populate entities and inform the scheduler, and they settle nothing.
 ('endpoint_discovered','Endpoint discovered', false, '{receipt,tool_run}',
  'a request path and method were seen to exist'),
 ('parameter_discovered','Parameter discovered', false, '{receipt,tool_run}',
  'a parameter was seen to be accepted by an endpoint'),
 ('technology_identified','Technology identified', false, '{receipt,tool_run}',
  'a component, framework or version was identified'),
 ('identity_established','Identity established', false, '{receipt}',
  'an identity slot became usable against the target'),
 ('artifact_captured','Artifact captured', false, '{receipt,tool_run}',
  'a response body or file was stored content-addressed for later analysis');

-- REJECTED, and the rejection is the point.
--
-- `out_of_band_interaction` ('the target contacted a host the runtime controls')
-- was in the first draft of this list and comes straight off the ticket's own
-- examples. It cannot be in the vocabulary, because its `allowed_provenance`
-- would be empty: the interaction is INBOUND. It never crosses the scope proxy,
-- so there is no receipt; it is not analysis of a stored artifact, so there is
-- no tool run. Admitting it would mean admitting an observation whose only
-- possible provenance is a receipt that has nothing to do with it -- a model
-- asserting a fact and pointing at unrelated evidence, which is precisely what
-- "LLM proposes, runtime commits" forbids.
--
-- It goes back in when the collector that generates its provenance exists: a
-- third `provenance_kind` ('oob_receipt') written by a runtime-controlled
-- listener. That is a migration, not a config edit, and it is downstream of the
-- deferred out-of-band work (Cloudflare tunnel / interactsh) the map names as
-- the example of a feature built after the loop runs end to end.
COMMENT ON COLUMN observation_kinds.allowed_provenance IS
  'Which provenance_kind values may back an observation of this kind. A kind with no admissible provenance record does not belong in this vocabulary -- see the out_of_band_interaction note in migration 018.';


-- ===========================================================================
-- 2b. Both vocabularies are global, deliberately
-- ===========================================================================

-- Ticket 35's rule 2: every table is program-scoped unless it declares itself
-- here, and `check_program_isolation()` fails the migration otherwise. This is
-- a decision, not paperwork, so it is taken explicitly:
--
--   Global. A property class is a claim about what a test *is*, not about a
--   target. Per-program vocabularies would make ticket 16's coverage counts
--   incomparable across programs, would let two programs disagree about what
--   `injection.markup` means, and would force `property_class` into the dedup
--   index as a composite `(program_id, property_class)` -- redundant, because
--   `subject_entity_id` is already program-scoped and pins the program on its
--   own. The same argument ticket 35 used for `vulnerability_classes` ("reference
--   data: CWE") and `transition_rules` ("one state machine for the whole system")
--   applies unchanged.
--
-- The consequence is deliberate and is the cost of the choice: a program cannot
-- add a property class for its own target. Extending the taxonomy is a
-- migration, which is what makes the dedup key mean the same thing in every
-- program and across resume.
INSERT INTO program_global_tables (table_name, reason) VALUES
    ('property_class_families',
     'reference data: the security-property taxonomy is a claim about what a test is, not about a target'),
    ('property_classes',
     'reference data: the dedup key must mean the same thing in every program, so the leaf set is not per-program'),
    ('observation_kinds',
     'reference data: what classes of fact exist, and which provenance record can back each'),
    ('property_class_vulnerability_classes',
     'reference data: it maps two global vocabularies to each other, so it can be scoped by neither');


-- ===========================================================================
-- 3. Existing rows adopt the vocabulary, then the FKs go on
-- ===========================================================================

-- The fixture picked its own strings before there was a vocabulary. The
-- vocabulary is the decision; the fixture follows it.
UPDATE hypotheses SET property_class = CASE property_class
    WHEN 'authz.horizontal' THEN 'authorization.object_ownership'
    WHEN 'authz.vertical'   THEN 'authorization.function_access'
    WHEN 'injection.sql'    THEN 'injection.query_language'
    ELSE property_class END
 WHERE property_class IN ('authz.horizontal','authz.vertical','injection.sql');

-- observations is an immutable table, so an existing row cannot be relabelled.
-- Nothing in this migration needs to: the FK is added after the check below,
-- and if it fails the migration fails, which is the correct outcome.
DO $$
DECLARE bad text;
BEGIN
    SELECT string_agg(DISTINCT o.kind, ', ') INTO bad
      FROM observations o
     WHERE NOT EXISTS (SELECT 1 FROM observation_kinds k WHERE k.id = o.kind);
    IF bad IS NOT NULL THEN
        RAISE EXCEPTION
            'observations carry kinds outside the vocabulary and are immutable: %', bad;
    END IF;
END $$;

ALTER TABLE hypotheses
    ADD CONSTRAINT hypotheses_property_class_fk
    FOREIGN KEY (property_class) REFERENCES property_classes(id);

ALTER TABLE observations
    ADD CONSTRAINT observations_kind_fk
    FOREIGN KEY (kind) REFERENCES observation_kinds(id);

-- The provenance record must be the right kind of record. Ticket 06 forced one
-- of the two to be present; this forces it to be the one the kind can actually
-- be produced by. A trigger rather than a CHECK because the rule lives in a
-- reference table, and ENABLE ALWAYS because ticket 07 found that
-- `session_replication_role = 'replica'` otherwise skips it.
CREATE FUNCTION enforce_kind_provenance() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE allowed text[];
BEGIN
    SELECT k.allowed_provenance INTO allowed
      FROM observation_kinds k WHERE k.id = NEW.kind;
    -- Membership is the FK's job, not this trigger's. A BEFORE INSERT trigger
    -- runs ahead of constraint checking, so raising here would mask
    -- `observations_kind_fk` and give a model a message about provenance when
    -- the real fault is an invented kind.
    IF allowed IS NULL THEN
        RETURN NEW;
    END IF;
    IF NOT (NEW.provenance_kind = ANY (allowed)) THEN
        RAISE EXCEPTION
            'observation kind % may not be backed by provenance_kind %; allowed: %',
            NEW.kind, NEW.provenance_kind, allowed;
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER observations_provenance_guard
    BEFORE INSERT ON observations
    FOR EACH ROW EXECUTE FUNCTION enforce_kind_provenance();

ALTER TABLE observations ENABLE ALWAYS TRIGGER observations_provenance_guard;


-- ===========================================================================
-- 4. The dedup index actually deduplicates
-- ===========================================================================

-- Measured, not argued: with the shipped `NULLS DISTINCT` index, 49 of the
-- corpus's 55 investigations never collide with themselves because at least one
-- identity slot is NULL. An unauthenticated hypothesis is the common case, so
-- the Q14 dedup key was inert for most of what it guards.
--
-- Rebuilding the index over a database that already accumulated duplicates
-- fails, so the duplicates are superseded first -- which is the schema's own
-- word for "this row is the same work as that one". The oldest row wins because
-- it is the one other rows may already cite.
WITH dupes AS (
    SELECT id,
           first_value(id) OVER w AS keeper
      FROM hypotheses
     WHERE superseded_by IS NULL
    WINDOW w AS (PARTITION BY subject_entity_id, identity_a_entity_id,
                              identity_b_entity_id, property_class
                 ORDER BY created_at, id)
)
UPDATE hypotheses h SET superseded_by = d.keeper
  FROM dupes d
 WHERE h.id = d.id AND d.id <> d.keeper;

DROP INDEX hypotheses_dedup_idx;

CREATE UNIQUE INDEX hypotheses_dedup_idx
    ON hypotheses (subject_entity_id, identity_a_entity_id,
                   identity_b_entity_id, property_class)
    NULLS NOT DISTINCT
 WHERE superseded_by IS NULL;


-- ===========================================================================
-- 5. A refused hypothesis leaves a trace
-- ===========================================================================

-- The residual collision rate is 11/165 and cannot be driven to zero by adding
-- leaves -- see the ticket's adversarial section, where three genuinely
-- different SAML defects share `authentication.federation_trust`. What can be
-- fixed is the *silence*: ticket 08 built `hypothesis_near_matches` so a
-- suppressed hypothesis leaves a trace, and a hard key collision is the same
-- event arriving through the index instead of through pgvector.
--
-- `similarity` and `embedding_model` are the stage-2 columns; a key collision
-- has neither, so they become nullable and a CHECK ties them to the action.
ALTER TABLE hypothesis_near_matches
    DROP CONSTRAINT hypothesis_near_matches_action_check;

ALTER TABLE hypothesis_near_matches
    ALTER COLUMN similarity      DROP NOT NULL,
    ALTER COLUMN embedding_model DROP NOT NULL;

ALTER TABLE hypothesis_near_matches
    ADD CONSTRAINT hypothesis_near_matches_action_check
        CHECK (action IN ('suppressed','penalised','key_collision')),
    ADD CONSTRAINT hypothesis_near_matches_stage2_cols
        CHECK ((action = 'key_collision'
                AND similarity IS NULL AND embedding_model IS NULL)
            OR (action <> 'key_collision'
                AND similarity IS NOT NULL AND embedding_model IS NOT NULL));


-- ===========================================================================
-- 6. Only evidence may be evidence
-- ===========================================================================

-- `hypothesis_evidence.role` already distinguishes baseline/variant/control
-- from context, and ticket 06's transition rules count the first three
-- (`min_supporting_evidence`, `min_control_evidence`). So the rule writes
-- itself: a non-evidential observation may be attached for context and can
-- never push a hypothesis to `supported`.
CREATE FUNCTION enforce_evidential_kind() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE k text; ev boolean;
BEGIN
    IF NEW.role = 'context' THEN
        RETURN NEW;
    END IF;
    SELECT o.kind, ok.is_evidential INTO k, ev
      FROM observations o JOIN observation_kinds ok ON ok.id = o.kind
     WHERE o.id = NEW.observation_id;
    IF NOT ev THEN
        RAISE EXCEPTION
            'observation kind % is not evidential and may only be cited with role=context, not %',
            k, NEW.role;
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER hypothesis_evidence_kind_guard
    BEFORE INSERT OR UPDATE ON hypothesis_evidence
    FOR EACH ROW EXECUTE FUNCTION enforce_evidential_kind();

ALTER TABLE hypothesis_evidence ENABLE ALWAYS TRIGGER hypothesis_evidence_kind_guard;


-- ===========================================================================
-- 7. property_class maps onto vulnerability_classes, and is not enforced
-- ===========================================================================

-- A hypothesis is about a property; a finding is an instance of a class. The
-- mapping is many-to-many in both directions -- `injection.request_forgery`
-- yields SSRF, open redirect or header injection depending on what came back,
-- and CWE-639 arrives from `authorization.object_ownership` or from
-- `information_disclosure.identifier_oracle`.
--
-- It is advisory on purpose. The findings worth having are the ones where the
-- property you tested and the class you found diverge: you probe
-- `authorization.object_ownership` on an id parameter and discover the id is
-- SQL-injectable. A constraint tying `findings.class_id` to the property class
-- of its hypotheses would refuse exactly that row.
--
-- ROWS ARE NOT SEEDED HERE. `vulnerability_classes` is ticket 19's call, and so
-- is which class each property class expects. This migration defines the shape
-- and the report; ticket 19 fills it.
CREATE TABLE property_class_vulnerability_classes (
    property_class_id      text NOT NULL REFERENCES property_classes(id),
    vulnerability_class_id text NOT NULL REFERENCES vulnerability_classes(id),
    note                   text,
    PRIMARY KEY (property_class_id, vulnerability_class_id)
);

-- The review signal that replaces the constraint. A finding appears here when
-- its class is not one its hypotheses' property classes expect. Empty until
-- ticket 19 seeds the mapping, and silent for property classes with no mapping
-- at all -- an unmapped property class is an unanswered question, not a
-- divergence.
CREATE VIEW finding_class_divergence AS
SELECT f.id AS finding_id, f.program_id, f.label, f.class_id,
       array_agg(DISTINCT h.property_class) AS hypothesis_property_classes
  FROM findings f
  JOIN finding_hypotheses fh ON fh.finding_id = f.id
  JOIN hypotheses h          ON h.id = fh.hypothesis_id
 WHERE EXISTS (SELECT 1 FROM property_class_vulnerability_classes m
                WHERE m.property_class_id = h.property_class)
   AND NOT EXISTS (SELECT 1 FROM property_class_vulnerability_classes m
                    WHERE m.property_class_id = h.property_class
                      AND m.vulnerability_class_id = f.class_id)
 GROUP BY f.id, f.program_id, f.label, f.class_id;


-- ===========================================================================
-- 8. One source of truth for the MCP input schema
-- ===========================================================================

-- Ticket 01 established that MCP input schemas are validated before the handler
-- body, so an `enum` in the tool schema rejects an unknown value before any
-- code sees it, with a message the model can act on. The FKs above are the
-- second line: they catch anything that reaches the database by another route
-- (a fixture, a repair script, a future tool that forgot).
--
-- Both layers read from these tables. `mcp_enum()` is what the MCP server calls
-- at startup to build the schema, so the enum cannot drift from the FK.
CREATE FUNCTION mcp_enum(p_vocabulary text) RETURNS jsonb
LANGUAGE sql STABLE AS $$
    SELECT CASE p_vocabulary
        WHEN 'property_class' THEN
            (SELECT jsonb_agg(id ORDER BY id) FROM property_classes)
        WHEN 'observation_kind' THEN
            (SELECT jsonb_agg(id ORDER BY id) FROM observation_kinds)
        WHEN 'observation_kind_evidential' THEN
            (SELECT jsonb_agg(id ORDER BY id) FROM observation_kinds WHERE is_evidential)
        ELSE NULL
    END
$$;

-- The description text the tool schema shows next to each enum value. A model
-- picking from a 33-item list needs the leaf's meaning, not just its name --
-- this is the whole reason the reference table carries a description column.
CREATE FUNCTION mcp_enum_described(p_vocabulary text) RETURNS jsonb
LANGUAGE sql STABLE AS $$
    SELECT CASE p_vocabulary
        WHEN 'property_class' THEN
            (SELECT jsonb_object_agg(id, description) FROM property_classes)
        WHEN 'observation_kind' THEN
            (SELECT jsonb_object_agg(id, description) FROM observation_kinds)
        ELSE NULL
    END
$$;


-- ===========================================================================
-- 9. The migration refuses to finish if it broke ticket 35
-- ===========================================================================

-- Ticket 35's closing assertion, repeated here for the same reason it exists
-- there: applying the migration is the proof. Four reference tables were added
-- and one unique index was rebuilt, and either could have re-opened a hole 017
-- closed.
DO $$
DECLARE n integer; d text;
BEGIN
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_program_isolation();
    IF n > 0 THEN
        RAISE EXCEPTION 'migration 018 breaks program isolation (% problems): %', n, d;
    END IF;
END $$;

-- And the vocabulary's own closing assertion: no kind may exist whose
-- provenance set is empty, and every observation in the database is backed by a
-- provenance record its kind admits.
DO $$
DECLARE bad text;
BEGIN
    SELECT string_agg(o.id::text || ' (' || o.kind || '/' || o.provenance_kind || ')', ', ')
      INTO bad
      FROM observations o
      JOIN observation_kinds k ON k.id = o.kind
     WHERE NOT (o.provenance_kind = ANY (k.allowed_provenance));
    IF bad IS NOT NULL THEN
        RAISE EXCEPTION
            'observations cite a provenance record their kind cannot produce: %', bad;
    END IF;
END $$;
