-- ---------------------------------------------------------------------------
-- 20260829T000000Z__eight_browser_and_client_side_topics_arrive_as_playbooks_and_the_targets_that_grade_them.sql
--                                                                   (ticket 52)
--
-- Ticket 52 migrates the v1 client-side and injection topics into authored v2
-- Playbooks and gives each of them a positive fixture. Eight of them, which is
-- twice what 051 carried, because v1 split this material across pages rather
-- than across packs: clickjacking, CORS/XSSI, XSS, dangling markup, DOM
-- vulnerabilities, prototype pollution, WebSocket attacks, broken link
-- hijacking and cache poisoning are nine pages describing eight readings.
--
-- Five things happen.
--
--   1. A relationship type. `embeds` is one document loading another, which is
--      what makes a widget an embedded document rather than a small page. It is
--      the second endpoint-to-endpoint type after 004's `redirects_to`.
--
--   2. Three surface facts -- `web_surface`, `embedded_document`, `tech_cdn` --
--      and the branches of `subject_facts` that compute them. Spelled out
--      literally for 049's reason: the `fact_not_computed` rule reads the view's
--      own definition text, and a name assembled by concatenation is invisible
--      to it.
--
--      `web_surface` needs no new Application kind. 003 has admitted `web`
--      since it was written and the view has been dropping it ever since, which
--      is why every Surface in the corpus so far has had to call itself an
--      `spa`. This ticket is the first with eight topics that are about a
--      browser rendering a document, so the kind stops being silently
--      discarded.
--
--   3. Six new Property classes. Two of these eight topics land on leaves 018
--      already named -- `injection.markup` and `transport.header_policy` -- and
--      the other six do not exist in that vocabulary at all, because 018 split
--      injection by the interpreter and named none of the interpreters that
--      live in a browser.
--
--   4. The eight Playbooks, as rows. Every one is `draft` for 049's reason:
--      `playbooks_stable_is_promoted` and 036's promotion guard make `stable`
--      unreachable until the evaluator has run the exact text against the
--      fixture catalogue, and no evaluation has happened yet.
--
--   5. The eight fixtures, as rows.
--
-- A new file rather than an edit to 051: a recorded migration whose file has
-- changed is schema drift and `rk db migrate` refuses the whole corpus for it.
-- ---------------------------------------------------------------------------


-- ===========================================================================
-- 1. One relationship type: one document loads another
-- ===========================================================================

-- `redirects_to` says a caller who asked here is sent there. `embeds` says a
-- document that was fetched here fetches there itself, with no caller in
-- between, which is a different fact about a different mechanism: the second
-- endpoint runs inside the first one's page and can be spoken to across the
-- frame boundary.
--
-- The CHECK and `relationship_directions` are both amended, because they are
-- two halves of one vocabulary and the recon slice's trigger reads the second
-- while the planner and a restore read the first.
ALTER TABLE relationships DROP CONSTRAINT relationships_type_check;
ALTER TABLE relationships ADD CONSTRAINT relationships_type_check CHECK (type IN (
                      'resolves_to',    -- domain  -> host
                      'serves',         -- host    -> application
                      'runs',           -- host|application -> technology
                      'owns',           -- identity -> entity (resource ownership)
                      'member_of',      -- identity -> identity (tenant/org)
                      'redirects_to',   -- endpoint -> endpoint
                      'embeds',         -- endpoint -> endpoint
                      'same_as'));      -- dedup merge

INSERT INTO relationship_directions (type, src_type, dst_type, note) VALUES
    ('embeds', 'endpoint', 'endpoint', 'one document loads another into itself')
ON CONFLICT (type, src_type, dst_type) DO NOTHING;


-- ===========================================================================
-- 2. Three facts, and the branches that compute them
-- ===========================================================================

-- `web_surface` is the Application kind 003 has always admitted and the view
-- has always dropped. Six of this ticket's eight Playbooks trigger on it, which
-- is the whole reason it is here: a reading about what a browser does with a
-- document has no business firing on a gRPC route.
--
-- `embedded_document` is `embeds` read from the far end, the same way `flow_step`
-- is `redirects_to` read from the far end. It is a precondition rather than
-- evidence: it says this endpoint is loaded by another document, which is what
-- makes a cross-document channel reachable at all.
--
-- `tech_cdn` is a caching front end having been identified. It is the one fact
-- in this ticket that a recon pass records about the machinery rather than about
-- the route, and it is what separates a cache question from a question about the
-- application behind it.
INSERT INTO surface_facts (id, scope, description) VALUES
 ('web_surface','application','the application serves browser-rendered documents'),
 ('embedded_document','endpoint','another endpoint embeds this one, so it is loaded by a document rather than by a person'),
 ('tech_cdn','application','a caching front end or CDN was identified')
ON CONFLICT (id) DO NOTHING;

-- The view, restated whole because `CREATE OR REPLACE VIEW` has no way to add a
-- branch to a UNION without restating the rest. Three branches have moved and
-- every other one is 051's, verbatim, with the column list unchanged so the
-- replacement is legal.
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
UNION ALL SELECT DISTINCT ep.program_id, ep.entity_id, 'redirect_target'
  FROM ep JOIN relationships r ON r.src_entity_id = ep.entity_id AND r.type = 'redirects_to'
UNION ALL SELECT DISTINCT ep.program_id, ep.entity_id, 'flow_step'
  FROM ep JOIN relationships r ON r.dst_entity_id = ep.entity_id AND r.type = 'redirects_to'
-- The first new branch, and the same shape as `flow_step` over the type section
-- 1 added: an endpoint something else embeds is loaded inside another document,
-- which is where a cross-document channel exists to be spoken to.
UNION ALL SELECT DISTINCT ep.program_id, ep.entity_id, 'embedded_document'
  FROM ep JOIN relationships r ON r.dst_entity_id = ep.entity_id AND r.type = 'embeds'
-- application shape. `web` is added to both the CASE and the filter: 003 has
-- admitted the kind since it was written and this view has been dropping it,
-- which is why the corpus before this ticket has no browser Surface that says
-- so.
UNION ALL SELECT ep.program_id, ep.entity_id,
       CASE a.kind WHEN 'graphql' THEN 'graphql_surface' WHEN 'spa' THEN 'spa_surface'
                   WHEN 'api' THEN 'api_surface' WHEN 'web' THEN 'web_surface'
                   ELSE 'websocket_surface' END
  FROM ep JOIN applications a ON a.entity_id = ep.application_id
 WHERE a.kind IN ('graphql','spa','api','web','websocket')
-- Spelled out rather than 'tech_' || lower(t.name), for the reason 049, 050 and
-- 051 give at this same branch. Six names map onto `tech_cdn` because a caching
-- front end is one fact however it was fingerprinted, and the reading that keys
-- on it does not care which vendor answered.
UNION ALL SELECT DISTINCT ep.program_id, ep.entity_id, known.fact
  FROM ep JOIN relationships r ON r.src_entity_id = ep.application_id AND r.type = 'runs'
          JOIN technologies t ON t.entity_id = r.dst_entity_id
          JOIN (VALUES ('jwt',        'tech_jwt'),
                       ('oauth',      'tech_oauth'),
                       ('saml',       'tech_saml'),
                       ('soap',       'tech_soap'),
                       ('graphql',    'tech_graphql'),
                       ('grpc',       'tech_grpc'),
                       ('llm',        'tech_llm'),
                       ('webauthn',   'tech_webauthn'),
                       ('cdn',        'tech_cdn'),
                       ('cloudflare', 'tech_cdn'),
                       ('cloudfront', 'tech_cdn'),
                       ('fastly',     'tech_cdn'),
                       ('akamai',     'tech_cdn'),
                       ('varnish',    'tech_cdn')) AS known(name, fact)
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
-- 3. Six Property classes
-- ===========================================================================

-- 018 split injection by the interpreter, "because the interpreter is the test",
-- and then named only the interpreters that live on a server: a database, a
-- shell, a template engine, a document parser, a filesystem. `injection.markup`
-- is the one browser leaf it has, and it covers the parser. The three added here
-- are the browser's other interpreters, and they are separate leaves for exactly
-- 018's stated reason -- the test is different in each.
--
--   `client_channel`   the page's own message and event handling. Nothing is
--                      sent to the server at all, so no response differencing
--                      can reach it.
--   `client_path`      the URL builder in the page. The request that carries the
--                      input is one the page makes, not one the caller makes.
--   `foreign_resource` the resource loader. The input names a host, and what
--                      executes is whatever that host serves.
--
-- The other three sit in families 018 already has and add the leaf that family
-- was missing for a browser: a credential that reached client storage, a
-- response that was stored under a key that does not identify its caller, and a
-- subscription granted at a handshake.
INSERT INTO property_classes (id, family_id, name, description) VALUES
 ('injection.client_channel','injection','Client channel injection',
  'input reaches a sink through the page''s own message or event handling, without a request'),
 ('injection.client_path','injection','Client path injection',
  'input reaches the path of a request the page itself builds and sends'),
 ('injection.foreign_resource','injection','Foreign resource loading',
  'input decides which external host supplies script, style or markup to the page'),
 ('authorization.channel_subscription','authorization','Channel subscription',
  'a caller can subscribe to a stream or topic they are not entitled to'),
 ('information_disclosure.client_storage','information_disclosure','Client storage exposure',
  'a credential or secret is placed where page script can read it'),
 ('information_disclosure.cached_response','information_disclosure','Cached response exposure',
  'a response is stored under a key that does not identify the caller it was rendered for')
ON CONFLICT (id) DO NOTHING;


-- ===========================================================================
-- 4. Eight Playbooks, as rows
-- ===========================================================================

-- `version` is the digest of the projection -- what the model is handed --
-- beside `source_sha256`, which is the document.
--
-- All eight are `constrained` and `read_only`, which is the first ticket where
-- that pairing appears across the whole set. It is what these topics are: every
-- one of them is answered by loading a document and reading what the browser or
-- the analyst then sees. Nothing here registers, cancels, spends or edits
-- anything the target owns, so `mutates_object` would be describing an intention
-- these documents do not have -- and `autonomous` is refused for the other
-- reason, that each of them puts a payload or a second Identity somewhere and
-- that is an act a Program's rules of engagement bound.
--
-- Three are `stable_session` and five are `none`. The split is whether the
-- reading needs the same caller to persist across the requests it compares:
-- `browser-storage`, `browser-realtime` and `web-cache` each difference one
-- caller against another or against themselves later, and a session that rotated
-- underneath would make the difference a statement about two sessions.
INSERT INTO playbooks (path, source_sha256, version, category, status, stale_after,
                       risk, effects, baseline, specificity, provenance) VALUES
 ('playbooks/browser-framing/playbook.md',
  'f53284cda3c03c81294e6834bb38a829f3602bc89417c1cfd01b007c10459c38',
  '02c79b2779af0a7b50d67a16b467601d5a3a7bd3777319f8bd99ed0dc3d2da2d',
  'transport', 'draft', '2027-03-15T00:00:00Z',
  'constrained', 'read_only', 'none', 3,
  'Written for ticket 52 as the v2 replacement for v1''s clickjacking and CORS/XSSI pages, against the header-policy leaf of the ticket 18 vocabulary; both v1 texts are attached as maintainer references and both describe headers step 1 and step 2 read.'),
 ('playbooks/browser-messaging/playbook.md',
  '292b877886d038ad7dabd5ff0deb1b0149b8bf4928f86f344573215327a60b97',
  'ccaa992bb13367824ee6f1b2d5719459d33807ae91539849db4f360d0fdb8b97',
  'injection', 'draft', '2027-03-15T00:00:00Z',
  'constrained', 'read_only', 'none', 3,
  'Written for ticket 52 as the v2 replacement for v1''s dom-vulnerabilities and prototype-pollution pages, against a new client-channel leaf added by ticket 52; both v1 texts are attached as maintainer references and both describe sources step 3 names and cannot drive.'),
 ('playbooks/browser-realtime/playbook.md',
  '1f016d1c2475d48832019857b002acf7e5703aae1e0f43baa1a8a0e83a330536',
  '09fb9c5d4061a6ec8b87a837ead2df24fa124585fee5434129dc11ba5834c243',
  'authorization', 'draft', '2027-03-15T00:00:00Z',
  'constrained', 'read_only', 'stable_session', 3,
  'Written for ticket 52 against a new channel-subscription leaf added by ticket 52; the v1 websocket text is attached as a maintainer reference and step 5''s limit is where this Playbook and the v1 page part company.'),
 ('playbooks/browser-script/playbook.md',
  'cef82956b251e6ede97ab393a198dabaabb0f6a87273dcaa83a62b84d22cc403',
  '0fd4dc33f2953f6bfb130014b33231980de5c73a8cd7ef32fec4afded933031a',
  'injection', 'draft', '2027-03-15T00:00:00Z',
  'constrained', 'read_only', 'none', 3,
  'Written for ticket 52 as the v2 replacement for v1''s xss and dangling-markup pages, against the markup leaf of the ticket 18 vocabulary; both v1 texts are attached as maintainer references and the second is where step 4''s contexts come from.'),
 ('playbooks/browser-storage/playbook.md',
  'b19d1b0f489bee6da5eed7f699e5efdd97206f99f68f63e15c4a2497aaf62129',
  'f163e0c7a8f774b1702015ffed53f6000c8fd00510cef681a68671d099998db7',
  'information_disclosure', 'draft', '2027-03-15T00:00:00Z',
  'constrained', 'read_only', 'stable_session', 3,
  'Written for ticket 52 against a new client-storage leaf added by ticket 52; v1 had no page on this topic, so nothing is attached rather than a placeholder.'),
 ('playbooks/client-side-path-traversal/playbook.md',
  '753c058fbdc51091400adafe8729f6bc24d23482b219f96c5a1b1d0148827534',
  '8394500c227610d680771b3ca9b9adc65e0ce37fd24ec76fa4f2873833cc3a8c',
  'injection', 'draft', '2027-03-15T00:00:00Z',
  'constrained', 'read_only', 'none', 3,
  'Written for ticket 52 against a new client-path leaf added by ticket 52; v1 covered this topic in prose under its client-side pack and shipped no reference text for it, so nothing is attached rather than a placeholder.'),
 ('playbooks/external-resources/playbook.md',
  '373c869e15e4c4366f370d10b5e052a640230aebafe69fe0f65064137d909091',
  '6d46a352a277f44187442211a4e592af228166e629e33fa9e6ab93d431d32060',
  'injection', 'draft', '2027-03-15T00:00:00Z',
  'constrained', 'read_only', 'none', 3,
  'Written for ticket 52 as the v2 replacement for v1''s broken-link-hijacking page, against a new foreign-resource leaf added by ticket 52; the v1 text is attached as a maintainer reference and step 5''s refusal is where this Playbook and that page part company.'),
 ('playbooks/web-cache/playbook.md',
  '53b5dc366a985802db5293b659cc233f2701b038a5fb9912cde4bf225c551014',
  'ce80e58e14d8caa3ac32a68b2d61ae5869cf0258743a5089dfd50a03650c4ce4',
  'information_disclosure', 'draft', '2027-03-15T00:00:00Z',
  'constrained', 'read_only', 'stable_session', 3,
  'Written for ticket 52 as the v2 replacement for v1''s cache-poisoning page, against a new cached-response leaf added by ticket 52; the v1 text is attached as a maintainer reference and step 2''s unique key is where this Playbook and that page part company.')
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
-- ticket declares an `any` arm, for 050's reason, and all eight carry exactly
-- three facts.
--
-- Six of the eight trigger on `web_surface` and are told apart by the two facts
-- beside it: what the route carries and what it does. `browser-realtime` is on
-- the socket instead, and it is separated from 049's `realtime` by wanting a
-- query parameter -- the topic is which channel was asked for, and a socket that
-- takes no argument has no channel to ask for.
INSERT INTO playbook_triggers (playbook_id, mode, fact)
SELECT p.id, v.mode, v.fact
  FROM playbooks p, (VALUES
        ('playbooks/browser-framing/playbook.md',            'all', 'form_request'),
        ('playbooks/browser-framing/playbook.md',            'all', 'state_changing_method'),
        ('playbooks/browser-framing/playbook.md',            'all', 'web_surface'),
        ('playbooks/browser-messaging/playbook.md',          'all', 'embedded_document'),
        ('playbooks/browser-messaging/playbook.md',          'all', 'read_method'),
        ('playbooks/browser-messaging/playbook.md',          'all', 'web_surface'),
        ('playbooks/browser-realtime/playbook.md',           'all', 'multiple_test_identities'),
        ('playbooks/browser-realtime/playbook.md',           'all', 'query_parameter'),
        ('playbooks/browser-realtime/playbook.md',           'all', 'websocket_surface'),
        ('playbooks/browser-script/playbook.md',             'all', 'query_parameter'),
        ('playbooks/browser-script/playbook.md',             'all', 'reflected_parameter'),
        ('playbooks/browser-script/playbook.md',             'all', 'web_surface'),
        ('playbooks/browser-storage/playbook.md',            'all', 'authenticated_endpoint'),
        ('playbooks/browser-storage/playbook.md',            'all', 'read_method'),
        ('playbooks/browser-storage/playbook.md',            'all', 'web_surface'),
        ('playbooks/client-side-path-traversal/playbook.md', 'all', 'path_parameter'),
        ('playbooks/client-side-path-traversal/playbook.md', 'all', 'read_method'),
        ('playbooks/client-side-path-traversal/playbook.md', 'all', 'web_surface'),
        ('playbooks/external-resources/playbook.md',         'all', 'read_method'),
        ('playbooks/external-resources/playbook.md',         'all', 'url_valued_parameter'),
        ('playbooks/external-resources/playbook.md',         'all', 'web_surface'),
        ('playbooks/web-cache/playbook.md',                  'all', 'read_method'),
        ('playbooks/web-cache/playbook.md',                  'all', 'tech_cdn'),
        ('playbooks/web-cache/playbook.md',                  'all', 'web_surface'))
        AS v(path, mode, fact)
 WHERE p.path = v.path
ON CONFLICT (playbook_id, mode, fact) DO NOTHING;

-- One class each, for 051's reason: `playbook_fixture_binding` is total over
-- `fixtures`, so two Playbooks sharing a class would each be graded `in` on the
-- other's target and neither result would say which document was right.
--
-- `browser-script` is the one that claims a leaf 018 already had.
-- `injection.markup` was unclaimed until now because no document in the corpus
-- was about a browser parser.
INSERT INTO playbook_outputs (playbook_id, property_class)
SELECT p.id, v.property_class
  FROM playbooks p, (VALUES
        ('playbooks/browser-framing/playbook.md',            'transport.header_policy'),
        ('playbooks/browser-messaging/playbook.md',          'injection.client_channel'),
        ('playbooks/browser-realtime/playbook.md',           'authorization.channel_subscription'),
        ('playbooks/browser-script/playbook.md',             'injection.markup'),
        ('playbooks/browser-storage/playbook.md',            'information_disclosure.client_storage'),
        ('playbooks/client-side-path-traversal/playbook.md', 'injection.client_path'),
        ('playbooks/external-resources/playbook.md',         'injection.foreign_resource'),
        ('playbooks/web-cache/playbook.md',                  'information_disclosure.cached_response'))
        AS v(path, property_class)
 WHERE p.path = v.path
ON CONFLICT (playbook_id, property_class) DO NOTHING;

-- `skill_sha256_at_promotion` stays NULL on every row, for 050's reason.
--
-- Three Skill sets across the eight, and each one names the lane the reading
-- actually runs in. `browser-evidence` alone is the three that cannot be
-- answered without a browser at all: what the parser built, what a message
-- handler did, which URL the page then fetched. `compare-responses` with
-- `use-identity` is the four that difference one caller's response against
-- another's or against a control. `analyse-source` with
-- `handle-untrusted-content` is `external-resources`, which reads a document for
-- what it points at and never executes it -- and it is the only Playbook in this
-- ticket that `web_hunter` cannot load.
INSERT INTO playbook_skills (playbook_id, skill_name)
SELECT p.id, v.skill_name
  FROM playbooks p, (VALUES
        ('playbooks/browser-framing/playbook.md',            'compare-responses'),
        ('playbooks/browser-framing/playbook.md',            'use-identity'),
        ('playbooks/browser-messaging/playbook.md',          'browser-evidence'),
        ('playbooks/browser-realtime/playbook.md',           'compare-responses'),
        ('playbooks/browser-realtime/playbook.md',           'use-identity'),
        ('playbooks/browser-script/playbook.md',             'browser-evidence'),
        ('playbooks/browser-storage/playbook.md',            'compare-responses'),
        ('playbooks/browser-storage/playbook.md',            'use-identity'),
        ('playbooks/client-side-path-traversal/playbook.md', 'browser-evidence'),
        ('playbooks/external-resources/playbook.md',         'analyse-source'),
        ('playbooks/external-resources/playbook.md',         'handle-untrusted-content'),
        ('playbooks/web-cache/playbook.md',                  'compare-responses'),
        ('playbooks/web-cache/playbook.md',                  'use-identity'))
        AS v(path, skill_name)
 WHERE p.path = v.path
ON CONFLICT (playbook_id, skill_name) DO NOTHING;

-- Three rows each: what refutes, what the control has to show, and what the
-- claim itself rests on.
--
-- The supported kinds are what separate these eight from every earlier ticket,
-- and they are four different kinds because these readings are answered in four
-- different places.
--
--   `header_policy_observed`  `browser-framing`. The finding is the declaration,
--                             on both roles, because the vulnerable target
--                             behaves identically to the secure one and only its
--                             headers differ.
--   `reflected_input`         `browser-script` and `browser-messaging`. What is
--                             claimed is that a value arrived at an interpreter,
--                             which is a reflection with a verdict attached
--                             rather than a difference in a body.
--   `response_differential`   `client-side-path-traversal` and `web-cache`. Both
--                             are about a request that was made: which one the
--                             page sent, and which stored copy came back.
--   `credential_effect`       `browser-storage` and `browser-realtime`. Both end
--                             by presenting something as a credential and
--                             recording that it worked.
--   `content_match`           `external-resources`, and it is the one kind here
--                             whose only allowed provenance is a tool run. That
--                             is the honest source, and it is the only one this
--                             Playbook can have: `js_analyst` is the sole role
--                             whose Skills load it, that role holds no
--                             `net.request`, and a Receipt is therefore
--                             unreachable from it. It is also the only Playbook
--                             in the ticket whose refutation is not a
--                             `response_invariant`, for the same reason.
--
-- `browser-storage` is the one whose refutation control is not a variant row.
-- Refuting there means showing the credential never left the cookie, and the
-- observation that says so is the cookie's own attributes, which is a header
-- policy observation on the control leg.
INSERT INTO playbook_evidence
        (playbook_id, to_status, role, observation_kind, polarity, min_count)
SELECT p.id, v.to_status, v.role, v.kind, v.polarity, v.min_count
  FROM playbooks p, (VALUES
        ('playbooks/browser-framing/playbook.md',            'refuted',   'variant',  'header_policy_observed', 'refutes',  1),
        ('playbooks/browser-framing/playbook.md',            'supported', 'control',  'header_policy_observed', 'supports', 1),
        ('playbooks/browser-framing/playbook.md',            'supported', 'variant',  'header_policy_observed', 'supports', 1),
        ('playbooks/browser-messaging/playbook.md',          'refuted',   'variant',  'reflected_input',        'refutes',  1),
        ('playbooks/browser-messaging/playbook.md',          'supported', 'control',  'response_invariant',     'supports', 1),
        ('playbooks/browser-messaging/playbook.md',          'supported', 'variant',  'reflected_input',        'supports', 1),
        ('playbooks/browser-realtime/playbook.md',           'refuted',   'variant',  'response_invariant',     'refutes',  1),
        ('playbooks/browser-realtime/playbook.md',           'supported', 'control',  'credential_effect',      'supports', 1),
        ('playbooks/browser-realtime/playbook.md',           'supported', 'variant',  'credential_effect',      'supports', 1),
        ('playbooks/browser-script/playbook.md',             'refuted',   'variant',  'reflected_input',        'refutes',  1),
        ('playbooks/browser-script/playbook.md',             'supported', 'control',  'response_invariant',     'supports', 1),
        ('playbooks/browser-script/playbook.md',             'supported', 'variant',  'reflected_input',        'supports', 1),
        ('playbooks/browser-storage/playbook.md',            'refuted',   'control',  'header_policy_observed', 'refutes',  1),
        ('playbooks/browser-storage/playbook.md',            'supported', 'control',  'credential_effect',      'supports', 1),
        ('playbooks/browser-storage/playbook.md',            'supported', 'variant',  'credential_effect',      'supports', 1),
        ('playbooks/client-side-path-traversal/playbook.md', 'refuted',   'variant',  'response_invariant',     'refutes',  1),
        ('playbooks/client-side-path-traversal/playbook.md', 'supported', 'control',  'response_differential',  'supports', 1),
        ('playbooks/client-side-path-traversal/playbook.md', 'supported', 'variant',  'response_differential',  'supports', 1),
        ('playbooks/external-resources/playbook.md',         'refuted',   'variant',  'content_match',          'refutes',  1),
        ('playbooks/external-resources/playbook.md',         'supported', 'control',  'content_match',          'supports', 1),
        ('playbooks/external-resources/playbook.md',         'supported', 'variant',  'content_match',          'supports', 1),
        ('playbooks/web-cache/playbook.md',                  'refuted',   'variant',  'response_invariant',     'refutes',  1),
        ('playbooks/web-cache/playbook.md',                  'supported', 'control',  'response_differential',  'supports', 1),
        ('playbooks/web-cache/playbook.md',                  'supported', 'variant',  'response_differential',  'supports', 1))
        AS v(path, to_status, role, kind, polarity, min_count)
 WHERE p.path = v.path
ON CONFLICT (playbook_id, to_status, role, observation_kind) DO NOTHING;

-- The material the model never gets. Nine files behind six Playbooks;
-- `browser-storage` and `client-side-path-traversal` have nothing attached
-- because v1 shipped no page on either topic, and a placeholder would be a
-- reference to nothing. Recorded so a maintainer can find them and hashed so a
-- maintainer can tell whether they moved.
INSERT INTO playbook_references (playbook_id, name, path, sha256)
SELECT p.id, v.name, v.path, v.sha256
  FROM playbooks p, (VALUES
        ('playbooks/browser-framing/playbook.md', 'clickjacking.md',
         'playbooks/browser-framing/references/clickjacking.md',
         '17856bf47336559b1918c7dd395ed7848bdf0d99b52daefdd9a988fe0a030a32'),
        ('playbooks/browser-framing/playbook.md', 'cors-xssi.md',
         'playbooks/browser-framing/references/cors-xssi.md',
         '8f154c18eb32dfda0ebd362962384474f80ba10011c021ce1f95037b6fe48b91'),
        ('playbooks/browser-messaging/playbook.md', 'dom-vulnerabilities.md',
         'playbooks/browser-messaging/references/dom-vulnerabilities.md',
         'bd37f0c8d9137fcb70474d895fb0c48794ebd14060cda5e0ef15f53e30ade9cd'),
        ('playbooks/browser-messaging/playbook.md', 'prototype-pollution.md',
         'playbooks/browser-messaging/references/prototype-pollution.md',
         '5c9b7675053988d6a168fe817836e4b5214348547fc2932026206aee274a5180'),
        ('playbooks/browser-realtime/playbook.md', 'websocket-attacks.md',
         'playbooks/browser-realtime/references/websocket-attacks.md',
         'c572e83f60ee212bf23337ae41464145d4ac4e6aa90c853b628d2d7c81d61d95'),
        ('playbooks/browser-script/playbook.md', 'dangling-markup.md',
         'playbooks/browser-script/references/dangling-markup.md',
         '0ccf91ba241b07c39a857edd3aa1a9665552c3f8ed4be06f2cea3e2b5a1f5730'),
        ('playbooks/browser-script/playbook.md', 'xss.md',
         'playbooks/browser-script/references/xss.md',
         'e6b039b86c98ad4ec7c5d9964a6a495f1e2a3fa189c4cbb2e4c1ed398c8c1913'),
        ('playbooks/external-resources/playbook.md', 'broken-link-hijacking.md',
         'playbooks/external-resources/references/broken-link-hijacking.md',
         '27c8c1f0061470250c5e9030e3140cfce9a0f78337c5e3a661a87fdd99250002'),
        ('playbooks/web-cache/playbook.md', 'cache-poisoning.md',
         'playbooks/web-cache/references/cache-poisoning.md',
         'aae94e0402603f82df20d9930cf367f0094f354dbf6004fd2c644116a114ad67'))
        AS v(playbook_path, name, path, sha256)
 WHERE p.path = v.playbook_path
ON CONFLICT (playbook_id, name) DO NOTHING;


-- ===========================================================================
-- 5. Eight targets, as rows
-- ===========================================================================

-- One positive per topic, each written from the class description rather than
-- from the Playbook's steps. `playbook_fixture_binding()` is total over this
-- table, so every one of these is also an out-of-class negative for the other
-- twenty-seven Playbooks -- which is why nothing here declares a class it does
-- not hold, and why each ground truth spends most of its length saying which
-- neighbouring class is deliberately absent and what in the source keeps it out.
--
-- Two of them are graded on something no response body carries.
-- `client-channel-pair` never sends the value to the server at all, and
-- `client-path-pair` differs only in the second request the page makes, so both
-- are pairs whose two halves serve identical bytes to identical requests. That
-- is the honest shape of those classes rather than a gap in the fixtures, and it
-- is why the Playbooks that grade them need a browser.
--
-- `cached-response-pair` and `channel-subscription-pair` are the two with two
-- Identities, because neither disclosure exists with one caller: what crosses is
-- one caller receiving what was rendered or published for another.
INSERT INTO fixtures (id, kind, path, source_sha256, ground_truth_sha256) VALUES
 ('cached-response-pair', 'own_pair',
  'fixtures/cached-response-pair/fixture.md',
  'aab33e4afafbecfa703af1c420ca46bf4d2a7ba33738a06cb43a616b3bc627f5',
  '6a5edfef0fa0bd2196fd78a6a4dbd861b6afa35854e27109da51c728c8ae3a3b'),
 ('channel-subscription-pair', 'own_pair',
  'fixtures/channel-subscription-pair/fixture.md',
  'ac5af589eec64af35a64bf53af7f9271c8b650cf9e354b43beb4091d82bbc45b',
  'b8077a5d7d6a9b98f2c3198f5780614364503c26df20c00a1f62d7a5359d1d33'),
 ('client-channel-pair', 'own_pair',
  'fixtures/client-channel-pair/fixture.md',
  'a9885bca99ba39600c0ad94826a67d095acad2c90d880ab7bb06e854ea152941',
  '8e805d4fbe81cbfb558768a07bf7c52667e7a8855979529e4f7a15dc68d31554'),
 ('client-path-pair', 'own_pair',
  'fixtures/client-path-pair/fixture.md',
  '27ea909b89f1ff678b7c392ba30e68610848a63cde6e7de9068677b3a720c98a',
  'ea5184ea05e5b964e7162d0920650c1e75351cb02aed6c65ab0da580c6b6092c'),
 ('client-storage-pair', 'own_pair',
  'fixtures/client-storage-pair/fixture.md',
  'a584c08ce82929ea9b66f8a4306f3dc0997d75da0a4657c9353e73a52549b9ed',
  'f615f51b431f37f97d964a8c6c434736f3564abfbaa94fc879531c5d91566980'),
 ('foreign-resource-pair', 'own_pair',
  'fixtures/foreign-resource-pair/fixture.md',
  '7c9b8caf05191b37be3e5fb3560f94598ad5d026084a03153ea34211715d77e2',
  'a76959027e6949efd32cc835cfb9d34af520b570b12b1b5525fbad51ba9ed429'),
 ('header-policy-pair', 'own_pair',
  'fixtures/header-policy-pair/fixture.md',
  '5a53d8e86c81435d7eb551bd402dd268147da83bcbe0a178cdaad484ee70f349',
  'cca35a69ff2ea8cd960dae56a26eab867212ad537516afdaba81328dea79da4c'),
 ('markup-pair', 'own_pair',
  'fixtures/markup-pair/fixture.md',
  '530360bd335d07f07bb334618d9db4a45f54b4eae16bd4736e879f86653d399f',
  '48c79f549184120a7b43fcf9ef1f883bbd303b2de90c751032f0b70c805ad2de')
ON CONFLICT (id) DO UPDATE SET
    kind                = excluded.kind,
    path                = excluded.path,
    source_sha256       = excluded.source_sha256,
    ground_truth_sha256 = excluded.ground_truth_sha256;

-- One class each, for 050's reason.
INSERT INTO fixture_classes (fixture_id, property_class) VALUES
 ('cached-response-pair',      'information_disclosure.cached_response'),
 ('channel-subscription-pair', 'authorization.channel_subscription'),
 ('client-channel-pair',       'injection.client_channel'),
 ('client-path-pair',          'injection.client_path'),
 ('client-storage-pair',       'information_disclosure.client_storage'),
 ('foreign-resource-pair',     'injection.foreign_resource'),
 ('header-policy-pair',        'transport.header_policy'),
 ('markup-pair',               'injection.markup')
ON CONFLICT (fixture_id, property_class) DO NOTHING;
