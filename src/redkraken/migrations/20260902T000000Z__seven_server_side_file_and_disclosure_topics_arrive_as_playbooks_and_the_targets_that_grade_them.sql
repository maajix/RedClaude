-- ---------------------------------------------------------------------------
-- 20260902T000000Z__seven_server_side_file_and_disclosure_topics_arrive_as_playbooks_and_the_targets_that_grade_them.sql
--                                                                   (ticket 54)
--
-- Ticket 54 migrates the v1 packs about what a server does with a caller's
-- bytes after it has them -- a blob it reconstructs, a name it resolves, a file
-- it stores, a URL it fetches -- and the two packs about what a server says it
-- did. Seven readings, and what separates them is not the payload: it is which
-- of the target's own decisions the caller got to make.
--
-- Four things happen.
--
--   1. Three surface facts -- `path_valued_parameter`,
--      `serialized_object_parameter`, `tech_openapi` -- and the branches of
--      `subject_facts` that compute them. Spelled out literally for 049's
--      reason: the `fact_not_computed` rule reads the view's own definition
--      text, and a name assembled by concatenation is invisible to it.
--
--      The first two need no schema change, because `parameters.value_class` is
--      free text: 003 left it open and a recon pass could already write `path`
--      or `serialized` into it. What was missing was any way to ASK, which is
--      what a fact is.
--
--   2. Five new Property classes. Two of this ticket's seven land on leaves 018
--      already named and nobody had claimed -- `injection.path` and
--      `information_disclosure.error_detail`. The other five split three of
--      018's leaves, and each split is argued below where it is made.
--
--   3. The seven Playbooks, as rows. Every one is `draft` for 049's reason:
--      `playbooks_stable_is_promoted` and 036's promotion guard make `stable`
--      unreachable until the evaluator has run the exact text against the
--      fixture catalogue, and no evaluation has happened yet.
--
--   4. Seven fixtures, as rows.
--
-- A new file rather than an edit to 053: a recorded migration whose file has
-- changed is schema drift and `rk db migrate` refuses the whole corpus for it.
-- ---------------------------------------------------------------------------


-- ===========================================================================
-- 1. Three facts, and the branches that compute them
-- ===========================================================================

-- `path_valued_parameter` and `serialized_object_parameter` are the two value
-- classes this ticket's readings key on, and both are about what the caller's
-- string BECOMES rather than what it looks like. A path is a value the route
-- resolves against a directory; a serialised object is a value the route
-- reconstructs into a type. Neither is `opaque_id`, and a corpus that called
-- them that would have three Playbooks asking about identifiers.
--
-- They are separate facts rather than one `structured_parameter` for the reason
-- 053 gives at `tech_sql`: they are what tells two of this ticket's Playbooks
-- apart. The same authenticated route with the same one parameter is
-- `file-resolution` when the value names a document and `deserialization` when
-- the value carries a type, and nothing else in the surface says which.
--
-- `tech_openapi` is one fact over three fingerprints, for the reason `tech_cdn`
-- is: a reading that compares a response against a published contract does not
-- care whether the contract was served by a Swagger UI or a Redoc page. What it
-- needs to know is that the application publishes one at all.
INSERT INTO surface_facts (id, scope, description) VALUES
 ('path_valued_parameter','endpoint','a parameter whose value the route resolves as a path'),
 ('serialized_object_parameter','endpoint','a parameter whose value the route reconstructs into an object'),
 ('tech_openapi','application','the application publishes a machine-readable API contract')
ON CONFLICT (id) DO NOTHING;

-- The view, restated whole because `CREATE OR REPLACE VIEW` has no way to add a
-- branch to a UNION without restating the rest. Two parameter branches are new
-- and three names join the technology block; every other branch is 053's,
-- verbatim, with the column list unchanged so the replacement is legal.
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
-- The new body shape, beside the three 003 had. `%xml%` catches `text/xml`,
-- `application/xml` and the `+xml` suffix types -- SOAP, Atom, SVG -- which is
-- the whole set of bodies a document parser is reached through.
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
-- The two value classes 053's corpus had no reading for. `value_class` is free
-- text on `parameters`, so a recon pass could already record either of these and
-- nothing could ask about them; these two branches are what makes them askable.
UNION ALL SELECT DISTINCT ep.program_id, ep.entity_id, 'path_valued_parameter'
  FROM ep JOIN parameters p ON p.endpoint_id = ep.entity_id WHERE p.value_class = 'path'
UNION ALL SELECT DISTINCT ep.program_id, ep.entity_id, 'serialized_object_parameter'
  FROM ep JOIN parameters p ON p.endpoint_id = ep.entity_id WHERE p.value_class = 'serialized'
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
-- Spelled out rather than 'tech_' || lower(t.name), for the reason 049, 050, 051
-- and 052 give at this same branch. Twenty-four names map onto four new facts
-- because a query language is one fact however it was fingerprinted, and the
-- readings that key on it do not care which vendor answered. `activerecord` and
-- `rails` both appear because a recon pass may name either the framework or the
-- mapper inside it, and the fact is the same either way.
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
                       ('redoc',         'tech_openapi')) AS known(name, fact)
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
-- 2. Five Property classes
-- ===========================================================================

-- Five leaves, and every one of them is a split of something 018 named. 018 cut
-- injection by the interpreter and information disclosure by the channel, and
-- both cuts hold; what these five say is that three of its leaves had two
-- different TESTS inside them, and a leaf whose test is ambiguous cannot grade
-- anything.
--
--   `object_graph`       018 put "object graph" inside `document_parser`,
--                        beside XML and spreadsheets. The two are not one test.
--                        A parser is reached by a document and answers by
--                        reporting where it stopped reading, which is why
--                        `structured-injection` is graded on an error detail. A
--                        deserialiser is reached by a blob and answers by
--                        CONSTRUCTING something -- the caller names a type and
--                        the route builds it -- which is a difference between
--                        two successful responses and has nothing to do with an
--                        error. Left in one leaf, a target that reconstructs
--                        whatever type it is handed and a target that reports a
--                        parse offset would grade each other.
--
--   `stored_file`        018 has `injection.path` for what a name RESOLVES to
--                        and `markup` for what a document is interpreted as in
--                        a browser. Neither is this: the bytes are inert, the
--                        name is reduced to its last segment, and the defect is
--                        that the server decided what it had stored by reading
--                        the extension the caller chose. It is a decision made
--                        at retrieval about a file the target owns, which is
--                        why the Playbook that asks it is the only one in this
--                        ticket that mutates.
--
--   `url_authority`      018 has `request_forgery` -- "input controls a request
--                        the server itself makes" -- and `webhooks` claims it.
--                        That reading is answered by an ARRIVAL: a correlator
--                        the Program controls says a request reached it. This
--                        one is answered by a DISAGREEMENT: the route validated
--                        one authority and fetched another, and the response
--                        body says which host answered. A target can be either
--                        without being the other -- a route that fetches
--                        exactly what it validated is still a request forgery
--                        surface, and a parser confusion in a route that never
--                        leaves the process is still a parser confusion -- so
--                        one leaf could not grade both.
--
--   `undeclared_field`   018 has `excess_field`, "beyond what the CALLER IS
--                        ENTITLED TO", and `graphql` claims it. Entitlement is
--                        a second identity: the field belongs to somebody, and
--                        showing it to the wrong caller is the finding. This
--                        leaf is about a DECLARATION: the application published
--                        a contract and the response carries names the contract
--                        does not have. One identity is enough to ask it, and no
--                        answer to it says anything about who owns the field.
--
--   `credential_material` 018 has `artifact_exposure`, "a file reachable that
--                        was not meant to be published", and `attack-surface`
--                        claims it. The bundle this leaf is about is meant to be
--                        published -- it is the application's own JavaScript,
--                        served to every visitor by design. What was not meant
--                        to be in it is a working credential, and the test is
--                        therefore not "can this be fetched" but "does this
--                        string do anything", which is a request the string is
--                        presented in rather than a request for a file.
INSERT INTO property_classes (id, family_id, name, description) VALUES
 ('injection.object_graph','injection','Object graph injection',
  'input decides which type a route reconstructs from a serialised value, rather than only what the reconstructed value holds'),
 ('injection.stored_file','injection','Stored file interpretation',
  'the name a caller gives an uploaded file decides how the target later serves it back'),
 ('injection.url_authority','injection','URL authority confusion',
  'the authority a route validates in a caller-supplied URL is not the authority it fetches'),
 ('information_disclosure.undeclared_field','information_disclosure','Undeclared field',
  'a successful response carries fields the application''s own published contract does not declare'),
 ('information_disclosure.credential_material','information_disclosure','Credential material',
  'a document the target publishes on purpose carries a credential that is honoured')
ON CONFLICT (id) DO NOTHING;


-- ===========================================================================
-- 3. Seven Playbooks, as rows
-- ===========================================================================

-- 045's shape, 049's reasoning, and the same two digests: `source_sha256` is
-- the file as it sits on disk and `version` is the compiled document the model
-- is handed. Both are written out rather than computed, so a corpus that drifts
-- from these rows is caught by `test_playbook` rather than trusted.
--
-- Six are `constrained` and one is `approval_required`, and the split is the
-- only mutation in the ticket. `file-upload` has to STORE something twice before
-- it can ask its question -- the claim is about what retrieval says, and there
-- is nothing to retrieve until an upload happened -- so it is `mutates_object`,
-- and 032's `RISK_FLOOR` puts that no lower than `constrained` while the
-- document's own step 1 asks for the grant anyway. Everything else reads.
--
-- Six are `stable_session` and one is `none`. `secrets` is the exception and it
-- is the honest one: its subject is a document served to anybody, its arms are a
-- candidate string presented once and a request carrying nothing, and it holds
-- no session at all -- which is the whole reason it does not carry
-- `use-identity`.
INSERT INTO playbooks (path, source_sha256, version, category, status, stale_after,
                       risk, effects, baseline, specificity, provenance) VALUES
 ('playbooks/deserialization/playbook.md',
  'e4fd17dccf46393b0ba9b9db84d1c8ebc4c47f189143e956b1c489b93b546f7a',
  '83966887791bc8f1980aed23db1bf18b57ac79c25d59a9044ec220389dff0171',
  'injection', 'draft', '2027-04-15T00:00:00Z',
  'constrained', 'read_only', 'stable_session', 3,
  'Written for ticket 54 as the v2 replacement for v1''s deserialization pack against a new object_graph leaf added by ticket 54; the pack''s gadget page is attached as a maintainer reference and every chain, every payload generator and every proof-by-execution in it is refused by step 6.'),
 ('playbooks/exceptional-conditions/playbook.md',
  'cf36efa62b642793e07808aafea3557f56e6008312122198e40e7b81c2dd6fc2',
  '7d25a688265e3961129f2d9b31c6bf513b17305c739522ad0f60175727999f7b',
  'information_disclosure', 'draft', '2027-04-15T00:00:00Z',
  'constrained', 'read_only', 'stable_session', 3,
  'Written for ticket 54 as the v2 replacement for v1''s exceptional-conditions page against the error_detail leaf of the ticket 18 vocabulary; the v1 page carried no attachments, and its fuzzing lists and its overlong-input advice are refused by step 7.'),
 ('playbooks/file-resolution/playbook.md',
  '567e2591af04cbeed9fd2f97e9cbb1076dfe06994b06b1e94b028c45d8161ba7',
  '7fa6796113b8e606831ba9b67b4b8d8f418f425c071571123a2ab66a9eaaa723',
  'injection', 'draft', '2027-04-15T00:00:00Z',
  'constrained', 'read_only', 'stable_session', 3,
  'Written for ticket 54 as the v2 replacement for v1''s file-resolution pack against the path leaf of the ticket 18 vocabulary; the pack''s three pages are attached as maintainer references and their wrapper chains, their filter chains and their read-until-you-find-a-key advice are refused by step 7.'),
 ('playbooks/file-upload/playbook.md',
  '0c40be4e29de6c84c8f599105a5f9dac77c587a4e6f84f5fd5a059cc719f8f63',
  '05304b9dff594779248593a53079acaac9d3f99d8112db5210e2baf73ddb5a8a',
  'injection', 'draft', '2027-04-15T00:00:00Z',
  'approval_required', 'mutates_object', 'stable_session', 3,
  'Written for ticket 54 as the v2 replacement for v1''s file-upload page against a new stored_file leaf added by ticket 54; the v1 text is attached as a maintainer reference and its shells, its polyglots and its overwrite techniques are refused by step 7.'),
 ('playbooks/information-disclosure/playbook.md',
  '6727ca014e1043df0ceda1d2b51e9068a8f341075363fc7bf460977c22834bc0',
  '3631e440a636e18f555ac94bc0f30e97aeea4b1b2c3cf1f75f778bf1604f9ab0',
  'information_disclosure', 'draft', '2027-04-15T00:00:00Z',
  'constrained', 'read_only', 'stable_session', 3,
  'Written for ticket 54 as the v2 replacement for v1''s information-disclosure page against a new undeclared_field leaf added by ticket 54; the v1 page carried no attachments, and its advice to harvest whatever the extra fields contain is refused by step 7.'),
 ('playbooks/secrets/playbook.md',
  'a9e423196f35f7e5f846baeaf1c4fc409b3edf5b5b843e4a25704f336f4c4820',
  '7281778511516cdb2304881d23cdc85e27a0c5196d4a5e16c8ed3d425b9e976b',
  'information_disclosure', 'draft', '2027-04-15T00:00:00Z',
  'constrained', 'read_only', 'none', 3,
  'Written for ticket 54 as the v2 replacement for v1''s secrets page against a new credential_material leaf added by ticket 54; the v1 page carried no attachments, and its advice to enumerate what a found key reaches is refused by step 6.'),
 ('playbooks/ssrf-url-routing/playbook.md',
  'ff726c3233bc0febb660e59014ad5b81e68fa4a7c8905e04c9e23c4e1f1aef94',
  '3a64988df8a671b240dd3df7e646cd657d6a098f44832b8ec197256d3b19162f',
  'injection', 'draft', '2027-04-15T00:00:00Z',
  'constrained', 'read_only', 'stable_session', 3,
  'Written for ticket 54 as the v2 replacement for v1''s ssrf-url-routing pack against a new url_authority leaf added by ticket 54; the pack''s four pages are attached as maintainer references and their metadata endpoints, their port sweeps, their rebinding races and their internal-range wordlists are refused by step 7.')
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
-- ticket declares an `any` arm, for 050's reason, and all seven carry exactly
-- three facts.
--
-- Four of the seven are an authenticated read told apart by one parameter's
-- value class, which is what section 1 is for: a number is
-- `exceptional-conditions`, a path is `file-resolution`, a URL is
-- `ssrf-url-routing`, and a serialised blob on a write is `deserialization`.
-- The remaining three key on something the route is rather than something it
-- takes -- a file and a path together on a write, a published contract, a
-- document another document loads.
--
-- `file-upload` is the only Playbook in the catalogue whose trigger list needs
-- TWO parameters on one endpoint, and that is deliberate. A file in a multipart
-- body is `command-directory-injection`: an upload that reaches a converter. An
-- upload whose destination the caller also names is this one. A route with the
-- file alone matches neither, and that is the correct answer -- there is nothing
-- to compare two retrievals of if the caller never chose a name.
INSERT INTO playbook_triggers (playbook_id, mode, fact)
SELECT p.id, v.mode, v.fact
  FROM playbooks p, (VALUES
        ('playbooks/deserialization/playbook.md',        'all', 'authenticated_endpoint'),
        ('playbooks/deserialization/playbook.md',        'all', 'serialized_object_parameter'),
        ('playbooks/deserialization/playbook.md',        'all', 'state_changing_method'),
        ('playbooks/exceptional-conditions/playbook.md', 'all', 'authenticated_endpoint'),
        ('playbooks/exceptional-conditions/playbook.md', 'all', 'quantity_valued_parameter'),
        ('playbooks/exceptional-conditions/playbook.md', 'all', 'read_method'),
        ('playbooks/file-resolution/playbook.md',        'all', 'authenticated_endpoint'),
        ('playbooks/file-resolution/playbook.md',        'all', 'path_valued_parameter'),
        ('playbooks/file-resolution/playbook.md',        'all', 'read_method'),
        ('playbooks/file-upload/playbook.md',            'all', 'file_parameter'),
        ('playbooks/file-upload/playbook.md',            'all', 'path_valued_parameter'),
        ('playbooks/file-upload/playbook.md',            'all', 'state_changing_method'),
        ('playbooks/information-disclosure/playbook.md', 'all', 'authenticated_endpoint'),
        ('playbooks/information-disclosure/playbook.md', 'all', 'read_method'),
        ('playbooks/information-disclosure/playbook.md', 'all', 'tech_openapi'),
        ('playbooks/secrets/playbook.md',                'all', 'embedded_document'),
        ('playbooks/secrets/playbook.md',                'all', 'read_method'),
        ('playbooks/secrets/playbook.md',                'all', 'spa_surface'),
        ('playbooks/ssrf-url-routing/playbook.md',       'all', 'authenticated_endpoint'),
        ('playbooks/ssrf-url-routing/playbook.md',       'all', 'read_method'),
        ('playbooks/ssrf-url-routing/playbook.md',       'all', 'url_valued_parameter'))
        AS v(path, mode, fact)
 WHERE p.path = v.path
ON CONFLICT (playbook_id, mode, fact) DO NOTHING;

-- One class each, for 051's reason: `playbook_fixture_binding` is total over
-- `fixtures`, so two Playbooks sharing a class would each be graded `in` on the
-- other's target and neither result would say which document was right.
--
-- Two of these were named by 018 and left unclaimed for thirty-five Playbooks.
-- `injection.path` waited because every earlier reading about a caller-supplied
-- string was about a browser, a query or an identity; `information_disclosure.
-- error_detail` waited because 046 wrote a fixture for it as an out-of-class
-- negative and no Playbook was allowed to want it.
INSERT INTO playbook_outputs (playbook_id, property_class)
SELECT p.id, v.property_class
  FROM playbooks p, (VALUES
        ('playbooks/deserialization/playbook.md',        'injection.object_graph'),
        ('playbooks/exceptional-conditions/playbook.md', 'information_disclosure.error_detail'),
        ('playbooks/file-resolution/playbook.md',        'injection.path'),
        ('playbooks/file-upload/playbook.md',            'injection.stored_file'),
        ('playbooks/information-disclosure/playbook.md', 'information_disclosure.undeclared_field'),
        ('playbooks/secrets/playbook.md',                'information_disclosure.credential_material'),
        ('playbooks/ssrf-url-routing/playbook.md',       'injection.url_authority'))
        AS v(path, property_class)
 WHERE p.path = v.path
ON CONFLICT (playbook_id, property_class) DO NOTHING;

-- `skill_sha256_at_promotion` stays NULL on every row, for 050's reason.
--
-- Six carry `compare-responses` and `use-identity`, which is what these readings
-- are: two requests that differ in one thing, sent under a leased Identity so
-- that they came from the same caller. Two carry `handle-untrusted-content`
-- beside them, and both because the material being read is a document the target
-- produced rather than a response to a request the reading composed --
-- `information-disclosure` reads a published contract and `secrets` reads a
-- served bundle.
--
-- `secrets` is the one row without `use-identity`, and dropping it is the point
-- rather than an omission. Its subject is served to anybody, and its whole claim
-- is what a candidate string is worth to a caller who holds nothing else. A
-- session in the second arm would make the answer ambiguous: the route might
-- have answered because of the session rather than because of the string.
INSERT INTO playbook_skills (playbook_id, skill_name)
SELECT p.id, v.skill_name
  FROM playbooks p, (VALUES
        ('playbooks/deserialization/playbook.md',        'compare-responses'),
        ('playbooks/deserialization/playbook.md',        'use-identity'),
        ('playbooks/exceptional-conditions/playbook.md', 'compare-responses'),
        ('playbooks/exceptional-conditions/playbook.md', 'use-identity'),
        ('playbooks/file-resolution/playbook.md',        'compare-responses'),
        ('playbooks/file-resolution/playbook.md',        'use-identity'),
        ('playbooks/file-upload/playbook.md',            'compare-responses'),
        ('playbooks/file-upload/playbook.md',            'use-identity'),
        ('playbooks/information-disclosure/playbook.md', 'compare-responses'),
        ('playbooks/information-disclosure/playbook.md', 'handle-untrusted-content'),
        ('playbooks/information-disclosure/playbook.md', 'use-identity'),
        ('playbooks/secrets/playbook.md',                'compare-responses'),
        ('playbooks/secrets/playbook.md',                'handle-untrusted-content'),
        ('playbooks/ssrf-url-routing/playbook.md',       'compare-responses'),
        ('playbooks/ssrf-url-routing/playbook.md',       'use-identity'))
        AS v(path, skill_name)
 WHERE p.path = v.path
ON CONFLICT (playbook_id, skill_name) DO NOTHING;

-- Three rows each: what refutes, what the control has to show, and what the
-- claim itself rests on.
--
-- Four refute with a `response_invariant` on the variant leg, which is 053's
-- shape and for 053's reason: the arm went in, the route answered exactly as it
-- answers without it, and nothing resolved, reconstructed or fetched anything.
--
-- The supported kinds are four, because these readings are answered in four
-- different places.
--
--   `response_differential`  `deserialization`, `file-resolution`,
--                            `file-upload`, `ssrf-url-routing`. All four are
--                            answered by what came back being different, and in
--                            each the difference is the target having made a
--                            decision the caller chose -- which type, which
--                            document, which content type, which host.
--   `error_detail`           `exceptional-conditions`. The finding IS the
--                            failure text, so the citation is the failure.
--   `content_match`          `information-disclosure`, on all three legs. The
--                            comparison is between two stored documents -- the
--                            contract and the response -- and what says a name
--                            is in one and not the other is a match over the
--                            Artifact rather than anything about a response
--                            body. Its only allowed provenance is a tool run,
--                            which is the honest source for that.
--   `credential_effect`      `secrets`, on the variant legs. A string that
--                            looks like a key is nothing; what makes it a
--                            finding is the target honouring it, and that is a
--                            credential having an effect. The control leg is a
--                            `content_match` instead, because what the control
--                            has to establish is that the candidate was IN the
--                            document -- a decoy that never appeared cannot be
--                            evidence of anything.
INSERT INTO playbook_evidence
        (playbook_id, to_status, role, observation_kind, polarity, min_count)
SELECT p.id, v.to_status, v.role, v.kind, v.polarity, v.min_count
  FROM playbooks p, (VALUES
        ('playbooks/deserialization/playbook.md',        'refuted',   'variant', 'response_invariant',    'refutes',  1),
        ('playbooks/deserialization/playbook.md',        'supported', 'control', 'response_invariant',    'supports', 1),
        ('playbooks/deserialization/playbook.md',        'supported', 'variant', 'response_differential', 'supports', 1),
        ('playbooks/exceptional-conditions/playbook.md', 'refuted',   'variant', 'response_invariant',    'refutes',  1),
        ('playbooks/exceptional-conditions/playbook.md', 'supported', 'control', 'response_invariant',    'supports', 1),
        ('playbooks/exceptional-conditions/playbook.md', 'supported', 'variant', 'error_detail',          'supports', 1),
        ('playbooks/file-resolution/playbook.md',        'refuted',   'variant', 'response_invariant',    'refutes',  1),
        ('playbooks/file-resolution/playbook.md',        'supported', 'control', 'response_invariant',    'supports', 1),
        ('playbooks/file-resolution/playbook.md',        'supported', 'variant', 'response_differential', 'supports', 1),
        ('playbooks/file-upload/playbook.md',            'refuted',   'variant', 'response_invariant',    'refutes',  1),
        ('playbooks/file-upload/playbook.md',            'supported', 'control', 'response_invariant',    'supports', 1),
        ('playbooks/file-upload/playbook.md',            'supported', 'variant', 'response_differential', 'supports', 1),
        ('playbooks/information-disclosure/playbook.md', 'refuted',   'variant', 'content_match',         'refutes',  1),
        ('playbooks/information-disclosure/playbook.md', 'supported', 'control', 'content_match',         'supports', 1),
        ('playbooks/information-disclosure/playbook.md', 'supported', 'variant', 'content_match',         'supports', 1),
        ('playbooks/secrets/playbook.md',                'refuted',   'variant', 'credential_effect',     'refutes',  1),
        ('playbooks/secrets/playbook.md',                'supported', 'control', 'content_match',         'supports', 1),
        ('playbooks/secrets/playbook.md',                'supported', 'variant', 'credential_effect',     'supports', 1),
        ('playbooks/ssrf-url-routing/playbook.md',       'refuted',   'variant', 'response_invariant',    'refutes',  1),
        ('playbooks/ssrf-url-routing/playbook.md',       'supported', 'control', 'response_invariant',    'supports', 1),
        ('playbooks/ssrf-url-routing/playbook.md',       'supported', 'variant', 'response_differential', 'supports', 1))
        AS v(path, to_status, role, kind, polarity, min_count)
 WHERE p.path = v.path
ON CONFLICT (playbook_id, to_status, role, observation_kind) DO NOTHING;

-- The material the model never gets. Nine files behind four Playbooks;
-- `exceptional-conditions`, `information-disclosure` and `secrets` have nothing
-- attached because their v1 pages were single pages of advice rather than packs,
-- and the advice is what the Playbook rejects. Recorded so a maintainer can find
-- them and hashed so a maintainer can tell whether they moved.
--
-- Three of the four under `ssrf-url-routing` describe questions this Playbook
-- does not grade: `open-redirection.md` is `client_side.navigation` and belongs
-- to `routing`, and `dns-rebinding.md` and `pdf-generators.md` both end at
-- `injection.request_forgery`, which is `webhooks`. They are attached here
-- because that is where v1's pack put them and the disposition ledger records
-- where each v1 page went, not where its subject is graded. Each note says so in
-- its own text.
INSERT INTO playbook_references (playbook_id, name, path, sha256)
SELECT p.id, v.name, v.path, v.sha256
  FROM playbooks p, (VALUES
        ('playbooks/deserialization/playbook.md', 'deserialization-attacks.md',
         'playbooks/deserialization/references/deserialization-attacks.md',
         'fdda0bb262156cc461addfe28fc9afa1cc57e67a29ca6a43ed60326ffc83676c'),
        ('playbooks/file-resolution/playbook.md', 'lfi.md',
         'playbooks/file-resolution/references/lfi.md',
         '9416f9cfe485c5cfae999adf8783b50d4718211d41eae9eb62a16dc7ca52bfa5'),
        ('playbooks/file-resolution/playbook.md', 'path-traversal-encoding-variants.md',
         'playbooks/file-resolution/references/path-traversal-encoding-variants.md',
         'bcf06d0f7d19775914dbf238af4f7fe8a47da62eb6f1c25ef09efeea75518391'),
        ('playbooks/file-resolution/playbook.md', 'php-filter-chain-lfi-rce.md',
         'playbooks/file-resolution/references/php-filter-chain-lfi-rce.md',
         '01e1c13265606307c04d857404e249c251817ce59d6c8d0832d3b5b4ca1c0eac'),
        ('playbooks/file-upload/playbook.md', 'file-upload.md',
         'playbooks/file-upload/references/file-upload.md',
         'f5b4af645b8959d40ec3b021c2a3bb370a83673838a0be465a67ba588eb9afe9'),
        ('playbooks/ssrf-url-routing/playbook.md', 'dns-rebinding.md',
         'playbooks/ssrf-url-routing/references/dns-rebinding.md',
         'c5e0470f4211da97b12bec53e231ec8de9a832b69c7304031db210e236d71e0b'),
        ('playbooks/ssrf-url-routing/playbook.md', 'open-redirection.md',
         'playbooks/ssrf-url-routing/references/open-redirection.md',
         '9372af0aaee81236496493b80568d20a1a3863c82f83be80ef2b2ecd79a1f92c'),
        ('playbooks/ssrf-url-routing/playbook.md', 'pdf-generators.md',
         'playbooks/ssrf-url-routing/references/pdf-generators.md',
         '2eb9d187c7de655334459eef0aba78a1f6d866d2f81bc8c32b5190bff0fe11c6'),
        ('playbooks/ssrf-url-routing/playbook.md', 'ssrf.md',
         'playbooks/ssrf-url-routing/references/ssrf.md',
         '702ffaba6dd0cf217f7318b7c918217990906cd43b062ce93a89604247048657'))
        AS v(playbook_path, name, path, sha256)
 WHERE p.path = v.playbook_path
ON CONFLICT (playbook_id, name) DO NOTHING;


-- ===========================================================================
-- 4. Seven targets, as rows
-- ===========================================================================

-- One positive per topic, each written from the class description rather than
-- from the Playbook's steps, and every one also an out-of-class negative for the
-- other forty-one Playbooks -- which is why nothing here declares a class it does
-- not hold, and why each ground truth spends most of its length saying which
-- neighbouring class is deliberately absent and what in the source keeps it out.
--
-- Criterion 5 names four controls and they are spread across the seven rather
-- than repeated in each: `path-pair` carries the secure normalisation -- a
-- traversal that resolves back inside the base and is served by both variants;
-- `diagnostic-detail-pair` carries the harmless error -- a value of the right
-- type that the route's own rule rejects identically on both;
-- `credential-material-pair` carries the decoy secret -- a string of exactly
-- credential shape, in both bundles, that no route honours; and
-- `url-authority-pair` carries the non-fetching URL -- a route that parses the
-- caller's URL, reports what it read and opens no socket at all.
--
-- `diagnostic-detail-pair` is the second target for
-- `information_disclosure.error_detail` and it does not replace 046's
-- `error-detail-pair`, which stays exactly as written. That one is an anonymous
-- search route with no session and no controls, and its job is to be a real
-- defect that no authorization Playbook may claim; widening it into a target for
-- this ticket would have destroyed what 046 built it for. Both are `in` for
-- `exceptional-conditions`, and 036's verdict requires a discriminating finding
-- on each -- which is the harder reading, not the softer one, because one of
-- them has no identity to lease.
INSERT INTO fixtures (id, kind, path, source_sha256, ground_truth_sha256) VALUES
 ('credential-material-pair', 'own_pair',
  'fixtures/credential-material-pair/fixture.md',
  'da0ae6310e74bf32984ab9b587b3c6b392d9b29de1b0719aa7580df53e5d914e',
  'e07604f3e20322f3d229e35dfb6dee649ef907cca7d94a3e47e53d824b2f9eb5'),
 ('diagnostic-detail-pair', 'own_pair',
  'fixtures/diagnostic-detail-pair/fixture.md',
  '7eaff4b4f745c8f672b1a555ec626a00ca12e337ee85da8f92743fa1269d3144',
  'b0d61464fb93f6be9e6f564780bb24d72cb41ac2e05eb587fd3d005e1b989796'),
 ('object-graph-pair', 'own_pair',
  'fixtures/object-graph-pair/fixture.md',
  '8b4bd9ba9e72988117559c6cca836a3de204cbd645580d9ce1d3c1fd09d29c83',
  'fe597069e784762d5e05550503a6017e7531c5eedbbe1b00672184b7957ac8e9'),
 ('path-pair', 'own_pair',
  'fixtures/path-pair/fixture.md',
  'd95067b4f137b13a330b9d775e192fbde87f9afdd0ceb1bf21dbcc419e50e6aa',
  'd632442394c026fb739c1cac44c697f90b61bb01ba49df25b8e80e5f6fa049bd'),
 ('stored-file-pair', 'own_pair',
  'fixtures/stored-file-pair/fixture.md',
  '157557d1cd69be367f7c6d9d5dad7c57e99254c0a97a0e75abd2ff5245487080',
  '38664aeb5e7cb4f4abc36725df15e282332f5d41bd5a7077583020cecf6af568'),
 ('undeclared-field-pair', 'own_pair',
  'fixtures/undeclared-field-pair/fixture.md',
  '93297b4ace063031fa41be63c6a347d8a80d3d4a4c26510e006e88c1db22a7bf',
  '534d3b367e0079990f6fffd8b8c4de151a9c1944ca5af0ed59ed230aad80d0d2'),
 ('url-authority-pair', 'own_pair',
  'fixtures/url-authority-pair/fixture.md',
  'a64237f21c1e460093d5430df4ae8ec607623e5632e4caadae4f2e34dec5156f',
  'aa2dd13bc298d871ba384b253571879af02aa6b88d7ba9834eeb611e913641d3')
ON CONFLICT (id) DO UPDATE SET
    kind                = excluded.kind,
    path                = excluded.path,
    source_sha256       = excluded.source_sha256,
    ground_truth_sha256 = excluded.ground_truth_sha256;

-- One class each, for 050's reason.
INSERT INTO fixture_classes (fixture_id, property_class) VALUES
 ('credential-material-pair', 'information_disclosure.credential_material'),
 ('diagnostic-detail-pair',   'information_disclosure.error_detail'),
 ('object-graph-pair',        'injection.object_graph'),
 ('path-pair',                'injection.path'),
 ('stored-file-pair',         'injection.stored_file'),
 ('undeclared-field-pair',    'information_disclosure.undeclared_field'),
 ('url-authority-pair',       'injection.url_authority')
ON CONFLICT (fixture_id, property_class) DO NOTHING;
