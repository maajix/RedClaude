-- ---------------------------------------------------------------------------
-- 20260904T000000Z__three_http_integrity_and_parsing_topics_arrive_as_playbooks_and_the_targets_that_grade_them.sql
--                                                                   (ticket 56)
--
-- Ticket 56 migrates the v1 packs about the protocol itself -- how a request is
-- framed on the wire, who is allowed to read the answer, and which of two
-- occurrences of one parameter name each half of an application believes. Three
-- readings, and what they share is that all three v1 packs were mostly
-- unusable: their arms either cannot survive an interception proxy, or land on
-- somebody who is not part of the engagement.
--
-- Four things happen.
--
--   1. One surface fact, `repeated_parameter_name`, and the join that computes
--      it. Endpoint scope, and it is a self-join over `parameters` rather than a
--      column: 020's uniqueness is `(endpoint_id, location, name)`, so a name
--      that repeats does so across two carriers by construction, and that is
--      exactly the shape the parsing reading needs.
--
--   2. Two new Property classes, both splits of leaves 018 named, argued below
--      where they are made.
--
--   3. The three Playbooks, as rows. All three `draft` for 049's reason.
--
--   4. Two fixtures, as rows. Only two, for three Playbooks, and section 4 says
--      why the third has none.
--
-- Criterion 2 of the ticket -- use proxy-internal transport observations where
-- interception would invalidate the claim -- is what shapes the first of the
-- three. 025 records `transport.request_framing` as `unmakeable` behind an
-- `ENABLE ALWAYS` trigger, so no Hypothesis about how a request was framed can
-- be inserted at all, however carefully a reading argues for it. What survives
-- of v1's desync pack is `transport.tls_configuration`, one of the two leaves
-- 025 left `probe_only` -- `transport.certificate_trust` is the other, and it
-- is a different question over different `allowed_fields`, which is why nothing
-- here claims it. `tls_configuration`'s own fields are `tls_version`, `cipher`
-- and `alpn`, and it is settled by a measurement the proxy takes on a lane it
-- does not intercept rather than by anything a reading can send.
--
-- A new file rather than an edit to 055: a recorded migration whose file has
-- changed is schema drift and `rk db migrate` refuses the whole corpus for it.
-- ---------------------------------------------------------------------------


-- ===========================================================================
-- 1. One fact, and the join that computes it
-- ===========================================================================

-- `endpoint` scope, like every other fact that says what a route TAKES.
--
-- It is deliberately not "a parameter appears twice". 020 keys `parameters` on
-- `(endpoint_id, location, name)`, so one name can appear at most once per
-- carrier and a second occurrence is necessarily in a different carrier -- the
-- query string and the body, the query string and a cookie, the body and a
-- header. That is not a weaker version of the fact the reading wanted; it is the
-- fact it wanted, because two carriers is what makes two halves of an
-- application able to disagree. A name repeated inside one carrier is a list,
-- and every framework in the v1 table agrees about lists.
--
-- The recon pass records what it observed being accepted, which is why this is a
-- trigger rather than something the reading discovers by sending. Discovering it
-- would mean sending every known name twice against a route that writes.
INSERT INTO surface_facts (id, scope, description) VALUES
 ('repeated_parameter_name','endpoint','the same parameter name is accepted in two different carriers of one request')
ON CONFLICT (id) DO NOTHING;

-- The view, restated whole because `CREATE OR REPLACE VIEW` has no way to add a
-- branch to a UNION without restating the rest. One branch joins the parameter
-- block; every other branch is 055's, verbatim, with the column list unchanged
-- so the replacement is legal.
CREATE OR REPLACE VIEW subject_facts AS
WITH ep AS (
    SELECT e.id AS entity_id, e.program_id, ep.application_id, ep.method,
           ep.auth_required, ep.request_content_type
      FROM entities e JOIN endpoints ep ON ep.entity_id = e.id
     WHERE e.in_scope
)
-- endpoint shape
SELECT program_id, entity_id AS subject_entity_id, 'authenticated_endpoint'::text AS fact
  FROM ep WHERE auth_required IS TRUE
UNION ALL SELECT program_id, entity_id, 'unauthenticated_endpoint' FROM ep WHERE auth_required IS FALSE
UNION ALL SELECT program_id, entity_id, 'unknown_auth_endpoint'    FROM ep WHERE auth_required IS NULL
UNION ALL SELECT program_id, entity_id, 'state_changing_method'    FROM ep WHERE method IN ('POST','PUT','PATCH','DELETE')
UNION ALL SELECT program_id, entity_id, 'read_method'              FROM ep WHERE method IN ('GET','HEAD')
UNION ALL SELECT program_id, entity_id, 'json_request'             FROM ep WHERE request_content_type LIKE '%json%'
UNION ALL SELECT program_id, entity_id, 'form_request'             FROM ep WHERE request_content_type LIKE '%form-urlencoded%'
UNION ALL SELECT program_id, entity_id, 'multipart_request'        FROM ep WHERE request_content_type LIKE '%multipart%'
UNION ALL SELECT program_id, entity_id, 'xml_request'              FROM ep WHERE request_content_type LIKE '%xml%'
-- parameters
UNION ALL SELECT DISTINCT ep.program_id, ep.entity_id,
       CASE p.location WHEN 'path' THEN 'path_parameter' WHEN 'query' THEN 'query_parameter'
                       WHEN 'body' THEN 'body_parameter' WHEN 'header' THEN 'header_parameter'
                       ELSE 'cookie_parameter' END
  FROM ep JOIN parameters p ON p.endpoint_id = ep.entity_id
UNION ALL SELECT DISTINCT ep.program_id, ep.entity_id, 'object_identifier'
  FROM ep JOIN parameters p ON p.endpoint_id = ep.entity_id
 WHERE p.value_class IN ('uuid','integer_id','opaque_id')
UNION ALL SELECT DISTINCT ep.program_id, ep.entity_id, 'numeric_identifier'
  FROM ep JOIN parameters p ON p.endpoint_id = ep.entity_id WHERE p.value_class = 'integer_id'
UNION ALL SELECT DISTINCT ep.program_id, ep.entity_id, 'reflected_parameter'
  FROM ep JOIN parameters p ON p.endpoint_id = ep.entity_id WHERE p.reflected IS TRUE
UNION ALL SELECT DISTINCT ep.program_id, ep.entity_id, 'url_valued_parameter'
  FROM ep JOIN parameters p ON p.endpoint_id = ep.entity_id WHERE p.value_class = 'url'
UNION ALL SELECT DISTINCT ep.program_id, ep.entity_id, 'file_parameter'
  FROM ep JOIN parameters p ON p.endpoint_id = ep.entity_id WHERE p.value_class = 'file'
UNION ALL SELECT DISTINCT ep.program_id, ep.entity_id, 'email_valued_parameter'
  FROM ep JOIN parameters p ON p.endpoint_id = ep.entity_id WHERE p.value_class = 'email'
UNION ALL SELECT DISTINCT ep.program_id, ep.entity_id, 'quantity_valued_parameter'
  FROM ep JOIN parameters p ON p.endpoint_id = ep.entity_id WHERE p.value_class = 'number'
UNION ALL SELECT DISTINCT ep.program_id, ep.entity_id, 'path_valued_parameter'
  FROM ep JOIN parameters p ON p.endpoint_id = ep.entity_id WHERE p.value_class = 'path'
UNION ALL SELECT DISTINCT ep.program_id, ep.entity_id, 'serialized_object_parameter'
  FROM ep JOIN parameters p ON p.endpoint_id = ep.entity_id WHERE p.value_class = 'serialized'
-- 056's branch. A self-join on the name with the carriers required to differ,
-- which is the only shape 020's uniqueness admits.
UNION ALL SELECT DISTINCT ep.program_id, ep.entity_id, 'repeated_parameter_name'
  FROM ep JOIN parameters p ON p.endpoint_id = ep.entity_id
          JOIN parameters q ON q.endpoint_id = ep.entity_id
                           AND q.name = p.name
                           AND q.location <> p.location
UNION ALL SELECT DISTINCT ep.program_id, ep.entity_id, 'redirect_target'
  FROM ep JOIN relationships r ON r.src_entity_id = ep.entity_id AND r.type = 'redirects_to'
UNION ALL SELECT DISTINCT ep.program_id, ep.entity_id, 'flow_step'
  FROM ep JOIN relationships r ON r.dst_entity_id = ep.entity_id AND r.type = 'redirects_to'
UNION ALL SELECT DISTINCT ep.program_id, ep.entity_id, 'embedded_document'
  FROM ep JOIN relationships r ON r.dst_entity_id = ep.entity_id AND r.type = 'embeds'
-- application shape
UNION ALL SELECT ep.program_id, ep.entity_id,
       CASE a.kind WHEN 'graphql' THEN 'graphql_surface' WHEN 'spa' THEN 'spa_surface'
                   WHEN 'api' THEN 'api_surface' WHEN 'web' THEN 'web_surface'
                   ELSE 'websocket_surface' END
  FROM ep JOIN applications a ON a.entity_id = ep.application_id
 WHERE a.kind IN ('graphql','spa','api','web','websocket')
-- Spelled out rather than 'tech_' || lower(t.name), for the reason 049 through
-- 055 give at this same branch. The list is 055's unchanged: this ticket adds no
-- fingerprint, because the one reading here that keys on a technology keys on
-- `tech_edge_proxy`, which 055 already computes.
UNION ALL SELECT DISTINCT ep.program_id, ep.entity_id, known.fact
  FROM ep JOIN relationships r ON r.src_entity_id = ep.application_id AND r.type = 'runs'
          JOIN technologies t ON t.entity_id = r.dst_entity_id
          JOIN (VALUES ('jwt',           'tech_jwt'),
                       ('oauth',         'tech_oauth'),
                       ('saml',          'tech_saml'),
                       ('soap',          'tech_soap'),
                       ('graphql',       'tech_graphql'),
                       ('grpc',          'tech_grpc'),
                       ('llm',           'tech_llm'),
                       ('webauthn',      'tech_webauthn'),
                       ('cdn',           'tech_cdn'),
                       ('cloudflare',    'tech_cdn'),
                       ('cloudfront',    'tech_cdn'),
                       ('fastly',        'tech_cdn'),
                       ('akamai',        'tech_cdn'),
                       ('varnish',       'tech_cdn'),
                       ('postgresql',    'tech_sql'),
                       ('mysql',         'tech_sql'),
                       ('mariadb',       'tech_sql'),
                       ('mssql',         'tech_sql'),
                       ('oracle',        'tech_sql'),
                       ('sqlite',        'tech_sql'),
                       ('mongodb',       'tech_document_store'),
                       ('couchdb',       'tech_document_store'),
                       ('elasticsearch', 'tech_document_store'),
                       ('redis',         'tech_document_store'),
                       ('dynamodb',      'tech_document_store'),
                       ('django',        'tech_orm'),
                       ('rails',         'tech_orm'),
                       ('prisma',        'tech_orm'),
                       ('sequelize',     'tech_orm'),
                       ('hibernate',     'tech_orm'),
                       ('activerecord',  'tech_orm'),
                       ('jinja',         'tech_template'),
                       ('twig',          'tech_template'),
                       ('freemarker',    'tech_template'),
                       ('velocity',      'tech_template'),
                       ('handlebars',    'tech_template'),
                       ('erb',           'tech_template'),
                       ('smarty',        'tech_template'),
                       ('openapi',       'tech_openapi'),
                       ('swagger',       'tech_openapi'),
                       ('redoc',         'tech_openapi'),
                       ('wordpress',     'tech_cms'),
                       ('drupal',        'tech_cms'),
                       ('joomla',        'tech_cms'),
                       ('typo3',         'tech_cms'),
                       ('ghost',         'tech_cms'),
                       ('nginx',         'tech_edge_proxy'),
                       ('haproxy',       'tech_edge_proxy'),
                       ('traefik',       'tech_edge_proxy'),
                       ('envoy',         'tech_edge_proxy'),
                       ('apache',        'tech_edge_proxy'),
                       ('iis',           'tech_edge_proxy'),
                       ('kubernetes',    'tech_orchestrator'),
                       ('openshift',     'tech_orchestrator'),
                       ('nomad',         'tech_orchestrator'),
                       ('ecs',           'tech_orchestrator'),
                       ('sentry',        'tech_telemetry'),
                       ('datadog',       'tech_telemetry'),
                       ('splunk',        'tech_telemetry'),
                       ('kibana',        'tech_telemetry'),
                       ('opentelemetry', 'tech_telemetry'),
                       ('logstash',      'tech_telemetry'),
                       ('graylog',       'tech_telemetry'),
                       ('newrelic',      'tech_telemetry'),
                       ('sourcemap',     'tech_build_manifest'),
                       ('webpack',       'tech_build_manifest'),
                       ('vite',          'tech_build_manifest'),
                       ('rollup',        'tech_build_manifest'),
                       ('parcel',        'tech_build_manifest')) AS known(name, fact)
            ON known.name = lower(t.name)
-- program shape
UNION ALL SELECT ep.program_id, ep.entity_id, 'multiple_test_identities'
  FROM ep WHERE (SELECT count(*) FROM entities ie JOIN identities i ON i.entity_id = ie.id
                  WHERE ie.program_id = ep.program_id AND i.class = 'user'
                    AND i.invalidated_at IS NULL) >= 2
UNION ALL SELECT ep.program_id, ep.entity_id, 'privileged_identity_available'
  FROM ep WHERE EXISTS (SELECT 1 FROM entities ie JOIN identities i ON i.entity_id = ie.id
                         WHERE ie.program_id = ep.program_id AND i.class = 'privileged'
                           AND i.invalidated_at IS NULL)
UNION ALL SELECT ep.program_id, ep.entity_id, 'anonymous_identity_available'
  FROM ep WHERE EXISTS (SELECT 1 FROM entities ie JOIN identities i ON i.entity_id = ie.id
                         WHERE ie.program_id = ep.program_id AND i.class = 'anonymous'
                           AND i.invalidated_at IS NULL)
UNION ALL SELECT ep.program_id, ep.entity_id, 'tenant_boundary'
  FROM ep WHERE (SELECT count(DISTINCT r.dst_entity_id)
                   FROM entities ie JOIN identities i ON i.entity_id = ie.id
                   JOIN relationships r ON r.src_entity_id = ie.id AND r.type = 'member_of'
                  WHERE ie.program_id = ep.program_id) >= 2;


-- ===========================================================================
-- 2. Two Property classes
-- ===========================================================================

-- Two leaves, both splits of something 018 named, and the third Playbook in this
-- ticket adds none at all because 018 already has the leaf it lands on.
--
--   `cross_origin_read`  018 has `session_handling.csrf` -- a state-changing
--                        request accepted because it carried a session the
--                        caller did not choose to send -- and `realtime` claims
--                        it. This is the read half of the same neighbourhood and
--                        it is a different defect. Nothing is written; the
--                        request the target answers is one the caller was
--                        entitled to make; and what is wrong is that the answer
--                        carries a header instructing the browser to hand it to
--                        a document from somewhere else. A target can have
--                        either without the other -- a token-defended write
--                        behind a reflecting read is exactly this ticket's
--                        fixture -- so one leaf could not grade both.
--
--   `parameter_precedence` 018 cuts injection by what the value reaches: a
--                        query, a template, a shell, a parser. This one reaches
--                        none of them, and that is the point of putting it in
--                        the same family rather than a different one: the defect
--                        is still that a value arrived somewhere it was not
--                        checked for, but the somewhere is the application's own
--                        second reader rather than an interpreter. The value
--                        carries no payload at all -- it is a string the
--                        application refuses on its own list -- and a leaf that
--                        required a payload would grade this wrong in the safe
--                        direction, which is the direction that loses findings.
--
-- The third reading, `http-desync`, outputs `transport.tls_configuration`, which
-- 018 named and 025 constrained, and no Playbook until now claimed. Nothing to
-- add: the leaf exists, `transport_makeability` already says what may be made of
-- it, and 034's `property_class_vulnerability_classes` already maps it.
INSERT INTO property_classes (id, family_id, name, description) VALUES
 ('session_handling.cross_origin_read','session_handling','Cross-origin read',
  'a response to an authenticated request carries headers permitting a document from an origin the deployment did not choose to read it'),
 ('injection.parameter_precedence','injection','Parameter precedence',
  'two components of one application resolve one parameter name to different occurrences, so what was checked is not what was used')
ON CONFLICT (id) DO NOTHING;


-- ===========================================================================
-- 3. Three Playbooks, as rows
-- ===========================================================================

-- 045's shape, 049's reasoning, and the same two digests: `source_sha256` is the
-- file as it sits on disk and `version` is the compiled document the model is
-- handed. Both are written out rather than computed, so a corpus that drifts
-- from these rows is caught by `test_playbook` rather than trusted.
--
-- All three are `constrained`. Two are `read_only` and one is not, and the odd
-- one out is the whole reason this ticket is small.
--
-- `request-parsing` is `mutates_object` and `pristine_surface`, because its arm
-- is a write: the only way to establish that a validator and a builder read
-- different occurrences of one name is to let them both run and compare what the
-- receipt said against what was produced. 032's composition rule then keeps it
-- off any surface another reading is holding still, which is correct -- it makes
-- objects, and it names them in the finding so an operator can remove them.
--
-- `request-integrity` is `read_only` and `stable_session`: it holds one session
-- throughout and its whole claim is about what the target says may be done with
-- that session's answer. The write on its subject is deliberately never sent.
--
-- `http-desync` is `read_only` and `none`. It presents nothing and it changes
-- nothing; what it asks for is a measurement the proxy takes on a lane it does
-- not intercept, and until 024 hands that lane over, the honest outcome of the
-- whole document is `inconclusive` naming the missing capability. That is stated
-- in its own ceiling rather than hidden here.
--
-- `stale_after` is 2027-05-15, the same date 055 used, and for the same reason
-- 023 and 024 make it matter: protocol behaviour at an edge is exactly the
-- knowledge that rots, and past that date this document cannot be selected
-- stably until somebody re-evaluates it.
INSERT INTO playbooks (path, source_sha256, version, category, status, stale_after,
                       risk, effects, baseline, specificity, provenance) VALUES
 ('playbooks/http-desync/playbook.md',
  '40c933022d7b8e9c7c594c2b173c967a3bfe322c9a5ab7d54fc857d7a24be05f',
  '2d2f0043ee08b27a4558b2b6b0d0b17689bb500dc30421590232f53679a09051',
  'transport', 'draft', '2027-05-15T00:00:00Z',
  'constrained', 'read_only', 'none', 3,
  'Written for ticket 56 as the v2 replacement for v1''s http-desync pack against the tls_configuration leaf 018 already named; the pack''s three pages are attached as maintainer references and its smuggling, desync, coalescing and tunnelling techniques are refused by step 6, because 025 records request framing as unmakeable behind the interception proxy and enforces that refusal in a trigger.'),
 ('playbooks/request-integrity/playbook.md',
  'a4d76f94d7805718cc34a47e24957f69d5cff144bb0364d7e1ade99a5ee8474f',
  '88f5cdb95d370edb5708d326402a63e41de2b094c2169e65e9613220d1804e92',
  'session_handling', 'draft', '2027-05-15T00:00:00Z',
  'constrained', 'read_only', 'stable_session', 3,
  'Written for ticket 56 as the v2 replacement for v1''s request-integrity pack against a new cross_origin_read leaf added by ticket 56; the pack''s two pages are attached as maintainer references, its forged-write proofs are refused by step 7, and the write half of its subject stays 018''s session_handling.csrf, which `realtime` outputs.'),
 ('playbooks/request-parsing/playbook.md',
  '491befb5f68018ecf7cd6e8c324c08aab640d0ff55e47cea7d85340da50b6078',
  '1bd54787c410fd568677c21a085a8806bff891fbf01f6ac2fb24b279cd338a23',
  'injection', 'draft', '2027-05-15T00:00:00Z',
  'constrained', 'mutates_object', 'pristine_surface', 3,
  'Written for ticket 56 as the v2 replacement for v1''s request-parsing pack against a new parameter_precedence leaf added by ticket 56; the pack''s four pages are attached as maintainer references, and its response-splitting payloads, its host-header rewrites and its filter-evasion catalogue are refused by step 7.')
ON CONFLICT (path) DO UPDATE SET
    source_sha256 = excluded.source_sha256,
    version       = excluded.version,
    category      = excluded.category,
    status        = excluded.status,
    stale_after   = excluded.stale_after,
    risk          = excluded.risk,
    effects       = excluded.effects,
    baseline      = excluded.baseline,
    specificity   = excluded.specificity,
    provenance    = excluded.provenance;

-- `specificity` above is the count of `all` rows here, and
-- `specificity_disagrees` is the database recomputing it. No Playbook in this
-- ticket declares an `any` arm, for 050's reason, and all three carry exactly
-- three facts.
--
-- What keeps the three off each other and off the forty-seven subjects the
-- catalogue already reaches:
--
--   `http-desync` is the only reading anywhere that pairs `tech_edge_proxy` with
--   `spa_surface`. `deployment`, the other `tech_edge_proxy` reading, needs
--   `web_surface`; `web-cache` keys on `tech_cdn`, which 055 kept separate from
--   the edge proxy for exactly this reason; `secrets` and `supply-chain`, the
--   other `spa_surface` reads, need `embedded_document` and
--   `tech_build_manifest`.
--
--   `request-integrity` is an authenticated read with a header parameter.
--   `workload-identities`, the nearest neighbour on `header_parameter`, needs
--   `unknown_auth_endpoint` and `tenant_boundary`; `cms` and `logging`, the
--   other authenticated reads, need a fingerprint each.
--
--   `request-parsing` is the only reading that keys on section 1's new fact at
--   all, which by itself is enough -- but it is worth recording what the earlier
--   drafts of this triple collided with, because both collisions were with
--   readings whose triggers are a strict subset once the carrier is wrong. On a
--   read method the same subject also fires `cookies` (`cookie_parameter`,
--   `read_method`) when the second carrier is a cookie, and
--   `workload-identities` when it is a header. `state_changing_method` with the
--   two carriers in the query string and the body is the canonical shape of the
--   defect anyway, and it collides with neither.
INSERT INTO playbook_triggers (playbook_id, mode, fact)
SELECT p.id, v.mode, v.fact
  FROM playbooks p, (VALUES
        ('playbooks/http-desync/playbook.md',       'all', 'read_method'),
        ('playbooks/http-desync/playbook.md',       'all', 'spa_surface'),
        ('playbooks/http-desync/playbook.md',       'all', 'tech_edge_proxy'),
        ('playbooks/request-integrity/playbook.md', 'all', 'authenticated_endpoint'),
        ('playbooks/request-integrity/playbook.md', 'all', 'header_parameter'),
        ('playbooks/request-integrity/playbook.md', 'all', 'read_method'),
        ('playbooks/request-parsing/playbook.md',   'all', 'repeated_parameter_name'),
        ('playbooks/request-parsing/playbook.md',   'all', 'state_changing_method'),
        ('playbooks/request-parsing/playbook.md',   'all', 'web_surface'))
        AS v(path, mode, fact)
 WHERE p.path = v.path
ON CONFLICT (playbook_id, mode, fact) DO NOTHING;

-- One class each, for 051's reason: `playbook_fixture_binding` is total over
-- `fixtures`, so two Playbooks sharing a class would each be graded `in` on the
-- other's target and neither result would say which document was right.
INSERT INTO playbook_outputs (playbook_id, property_class)
SELECT p.id, v.property_class
  FROM playbooks p, (VALUES
        ('playbooks/http-desync/playbook.md',       'transport.tls_configuration'),
        ('playbooks/request-integrity/playbook.md', 'session_handling.cross_origin_read'),
        ('playbooks/request-parsing/playbook.md',   'injection.parameter_precedence'))
        AS v(path, property_class)
 WHERE p.path = v.path
ON CONFLICT (playbook_id, property_class) DO NOTHING;

-- `skill_sha256_at_promotion` stays NULL on every row, for 050's reason.
--
-- All three carry `compare-responses`, because all three are answered by two
-- readings differing in one thing -- the lane a measurement was taken on, the
-- origin a request announced, the carrier a name arrived in.
--
-- `request-integrity` carries `use-identity` beside it, because it holds a
-- session throughout and its claim is about what may be done with that session's
-- answer. The other two carry `compare-responses` alone, and the bare row is the
-- point: `http-desync` presents nothing and reads a measurement rather than a
-- document, and `request-parsing` reads two documents the target produced from
-- its own catalogue. Neither handles anything untrusted in 044's sense, and a
-- skill claiming otherwise would be a claim about work the document does not do.
--
-- That also makes `request-integrity` and `request-parsing` loadable by
-- `web_hunter` only, and `http-desync` too: `compare-responses` is not in
-- `recon`'s or `js_analyst`'s vocabulary.
INSERT INTO playbook_skills (playbook_id, skill_name)
SELECT p.id, v.skill_name
  FROM playbooks p, (VALUES
        ('playbooks/http-desync/playbook.md',       'compare-responses'),
        ('playbooks/request-integrity/playbook.md', 'compare-responses'),
        ('playbooks/request-integrity/playbook.md', 'use-identity'),
        ('playbooks/request-parsing/playbook.md',   'compare-responses'))
        AS v(path, skill_name)
 WHERE p.path = v.path
ON CONFLICT (playbook_id, skill_name) DO NOTHING;

-- Three rows each: what refutes, what the control has to show, and what the
-- claim itself rests on.
--
-- `http-desync` is the only Playbook in the corpus whose three rows are all
-- `transport_parameters_observed`, and that is 025's doing rather than a choice.
-- 025 gates that kind behind a `receipt` provenance, a `transport_citable`
-- receipt and a field-by-field check of `metadata.transport` against the
-- receipt's own `wire_*` columns, so it is the only kind that can carry a
-- statement about a negotiated protocol at all. A `response_differential` here
-- would be a claim about two bodies, and this reading never compares bodies.
--
-- The other two are the corpus's usual triple: a variant that did not move
-- refutes, a control that did not move supports, and the claim rests on a
-- differential between two responses that differ in exactly one thing.
INSERT INTO playbook_evidence
        (playbook_id, to_status, role, observation_kind, polarity, min_count)
SELECT p.id, v.to_status, v.role, v.kind, v.polarity, v.min_count
  FROM playbooks p, (VALUES
        ('playbooks/http-desync/playbook.md',       'refuted',   'variant', 'transport_parameters_observed', 'refutes',  1),
        ('playbooks/http-desync/playbook.md',       'supported', 'control', 'transport_parameters_observed', 'supports', 1),
        ('playbooks/http-desync/playbook.md',       'supported', 'variant', 'transport_parameters_observed', 'supports', 1),
        ('playbooks/request-integrity/playbook.md', 'refuted',   'variant', 'response_invariant',            'refutes',  1),
        ('playbooks/request-integrity/playbook.md', 'supported', 'control', 'response_invariant',            'supports', 1),
        ('playbooks/request-integrity/playbook.md', 'supported', 'variant', 'response_differential',         'supports', 1),
        ('playbooks/request-parsing/playbook.md',   'refuted',   'variant', 'response_invariant',            'refutes',  1),
        ('playbooks/request-parsing/playbook.md',   'supported', 'control', 'response_invariant',            'supports', 1),
        ('playbooks/request-parsing/playbook.md',   'supported', 'variant', 'response_differential',         'supports', 1))
        AS v(path, to_status, role, kind, polarity, min_count)
 WHERE p.path = v.path
ON CONFLICT (playbook_id, to_status, role, observation_kind) DO NOTHING;

-- The material the model never gets. Nine files behind three Playbooks, which is
-- the highest reference-to-Playbook ratio in the corpus and is what this ticket
-- is: three documents that survived, and nine pages of technique that did not.
-- Recorded so a maintainer can find them and hashed so a maintainer can tell
-- whether they moved.
--
-- Six of the nine describe work refused outright, and each says so in its own
-- text: the two smuggling pages and the tunnelling page because 025 records
-- request framing as unmakeable, the response-splitting page because its proof
-- lands on the next caller, the host-header page because its yields are a
-- message to a person or a cache entry served to everybody, and the filter
-- bypass page because a defeated filter is a statement about a product rather
-- than about the application behind it.
INSERT INTO playbook_references (playbook_id, name, path, sha256)
SELECT p.id, v.name, v.path, v.sha256
  FROM playbooks p, (VALUES
        ('playbooks/http-desync/playbook.md', 'http-attacks-http-2-downgrading.md',
         'playbooks/http-desync/references/http-attacks-http-2-downgrading.md',
         'e6c6d45ff38474fb598775d33370b2fb404c88ba7607f7d1c63b543de72390aa'),
        ('playbooks/http-desync/playbook.md', 'http-attacks-request-smuggling-and-http-desync.md',
         'playbooks/http-desync/references/http-attacks-request-smuggling-and-http-desync.md',
         'ffd347a69370545e79ced4b4488913033678350c6547edd4015312b415cf682a'),
        ('playbooks/http-desync/playbook.md', 'proxy-tunnels.md',
         'playbooks/http-desync/references/proxy-tunnels.md',
         'ee2dfcb88961621003c43ba147bb8e188be04016dc02d154d213b1547672da7b'),
        ('playbooks/request-integrity/playbook.md', 'cors.md',
         'playbooks/request-integrity/references/cors.md',
         'd03287254c60bbf211cb6f3edf9df049c54fcd7f9775cae300a7419053b67ead'),
        ('playbooks/request-integrity/playbook.md', 'csrf.md',
         'playbooks/request-integrity/references/csrf.md',
         'b65a0baa9034ca4b934a861e4435d36618f7b7a5f931f1f41c97122bcb5c1d8a'),
        ('playbooks/request-parsing/playbook.md', 'http-attacks-crlf-injection-and-response-splitting.md',
         'playbooks/request-parsing/references/http-attacks-crlf-injection-and-response-splitting.md',
         '86c4c2dae56618c6e9c179f423084a161054efff2f7a6c2b8db1f93f78b439df'),
        ('playbooks/request-parsing/playbook.md', 'http-attacks-host-header.md',
         'playbooks/request-parsing/references/http-attacks-host-header.md',
         '0b72495f6693247a6ca88a1375e5b427b5ca6ebeec91dba3a941a230b7d4dee1'),
        ('playbooks/request-parsing/playbook.md', 'parameter-pollution.md',
         'playbooks/request-parsing/references/parameter-pollution.md',
         '2b0eb939cc30bb0aa50e0774fccfc5053fa37ecae60e18e1bf28ec8e14d32683'),
        ('playbooks/request-parsing/playbook.md', 'waf-bypasses.md',
         'playbooks/request-parsing/references/waf-bypasses.md',
         'e1533b920a391f1e8689270266057af9b0dd243dcc51809815b07a4723195f11'))
        AS v(playbook_path, name, path, sha256)
 WHERE p.path = v.playbook_path
ON CONFLICT (playbook_id, name) DO NOTHING;


-- ===========================================================================
-- 4. Two targets, as rows
-- ===========================================================================

-- Two, for three Playbooks, and the missing one is `http-desync`'s.
--
-- Its class is `transport.tls_configuration`, and 025 records that class as
-- `probe_only` with `allowed_fields` of `tls_version`, `cipher` and `alpn` --
-- all three of which are properties of a TLS handshake and none of which exists
-- on a loopback fixture serving plain HTTP, which is what every fixture in this
-- catalogue is. A fixture that faked the fields would be grading the reading
-- against a handshake nobody performed, and 036's binding would then report a
-- Playbook as evaluated when nothing about it had been tested. Leaving it
-- unbound is the honest answer: `playbook_fixture_binding` is total over
-- `fixtures` rather than over `playbooks`, so a Playbook with no in-class target
-- is structurally fine, and `http-desync` is graded `out` on all fifty
-- fixtures -- which is a real result, because a reading that fired on one of
-- them would be firing on a target with no TLS at all.
--
-- The two that are here are one positive each, written from the class
-- description rather than from the Playbook's steps, and each is also an
-- out-of-class negative for the other forty-nine Playbooks.
--
-- Criterion 4 -- distinguish the defect from the arrangement somebody chose --
-- is what both are built around, and both carry the distinction inside one
-- process rather than across two.
--
-- `cross-origin-read-pair` shares the same account view with a named partner
-- origin on BOTH variants, header for header, credentials line included. The
-- only difference between the halves is what happens to every other origin. A
-- reading that reports the partner arrangement has reported something the secure
-- variant does too, and a reading that reports the wildcard on the public status
-- route has reported a document that says the same thing to everybody.
--
-- `parameter-precedence-pair` answers `201` with the same `"format": "csv"` on
-- both variants and differs only in what the stored artefact turns out to be.
-- That is deliberate: the receipt alone cannot settle this class, and a reading
-- that claimed it from the receipt would be claiming it from the half of the
-- exchange both variants agree about. Its `POST /orders/report` refuses a
-- repeated name outright on both halves, so repetition itself is never the
-- finding, and `X-Forwarded-Host` is ignored on both, so the authority question
-- the v1 pack spent a page on is answered in the negative by the target rather
-- than by the ceiling alone.
--
-- It presents no identity on either half, and its `bb:identities` is empty.
-- `request-parsing` holds no session and declares no `use-identity`, so a
-- fixture that gated its routes on one would answer `401` to every arm the
-- Playbook sends and the positive half of the evaluation would be unreachable.
-- Nothing about this class needs a principal: precedence is one name, two
-- readers and two answers.
--
-- Neither fixture carries a payload anywhere. `xml` is a format the builder
-- already knew, chosen because the application does not offer it, and it reaches
-- no interpreter: the injection leaves 052 and 053 built have their own targets,
-- and a value that did something would make two targets answer one question.
INSERT INTO fixtures (id, kind, path, source_sha256, ground_truth_sha256) VALUES
 ('cross-origin-read-pair', 'own_pair',
  'fixtures/cross-origin-read-pair/fixture.md',
  '10f9470294a5ad1df9cef9953682531d51c7f7518624bbe4920cd0454ea31eb7',
  '1516dad3c6409da3ca7d13502c0a123ace2e5a16aa8275f054f5540a9140719f'),
 ('parameter-precedence-pair', 'own_pair',
  'fixtures/parameter-precedence-pair/fixture.md',
  '519c4910df66a532e96ebaad5f5b3e7b5bac16bccffaf31fa1987724fec0e231',
  '1bbbef6e7b3e8913432e65e119e750cfb2ccaa57faa4c685ab2ffa0ab8f6b9f9')
ON CONFLICT (id) DO UPDATE SET
    kind                = excluded.kind,
    path                = excluded.path,
    source_sha256       = excluded.source_sha256,
    ground_truth_sha256 = excluded.ground_truth_sha256;

-- One class each, for 050's reason.
INSERT INTO fixture_classes (fixture_id, property_class) VALUES
 ('cross-origin-read-pair', 'session_handling.cross_origin_read'),
 ('parameter-precedence-pair', 'injection.parameter_precedence')
ON CONFLICT (fixture_id, property_class) DO NOTHING;
