-- ---------------------------------------------------------------------------
-- 20260903T000000Z__five_platform_and_supply_chain_topics_arrive_as_playbooks_and_the_targets_that_grade_them.sql
--                                                                   (ticket 55)
--
-- Ticket 55 migrates the v1 packs that reason about the thing an application is
-- deployed ON rather than about the application -- the content platform under
-- it, the proxy in front of it, the orchestrator running it, the telemetry
-- collecting from it, and the build that assembled it. Five readings, and what
-- they share is a temptation: each is selected by a fingerprint, and a
-- fingerprint is the weakest thing in this system.
--
-- Four things happen.
--
--   1. Five surface facts -- `tech_cms`, `tech_edge_proxy`,
--      `tech_orchestrator`, `tech_telemetry`, `tech_build_manifest` -- and the
--      technology names that compute them. Spelled out literally for 049's
--      reason: the `fact_not_computed` rule reads the view's own definition
--      text, and a name assembled by concatenation is invisible to it.
--
--   2. Five new Property classes. None of this ticket's five lands on a leaf
--      018 already named, and each split is argued below where it is made.
--
--   3. The five Playbooks, as rows. Every one is `draft` for 049's reason:
--      `playbooks_stable_is_promoted` and 036's promotion guard make `stable`
--      unreachable until the evaluator has run the exact text against the
--      fixture catalogue, and no evaluation has happened yet.
--
--   4. Five fixtures, as rows.
--
-- Criterion 2 of the ticket is the one thing this file cannot state and does not
-- need to: 018 already records `technology_identified` with `is_evidential =
-- false`, so a fingerprint cannot appear on a Hypothesis transition however
-- badly a reading wants it to. What the five documents add is the discipline
-- above the schema -- each names, in its own step 1, what its fingerprint bought
-- and what it did not.
--
-- A new file rather than an edit to 054: a recorded migration whose file has
-- changed is schema drift and `rk db migrate` refuses the whole corpus for it.
-- ---------------------------------------------------------------------------


-- ===========================================================================
-- 1. Five facts, and the names that compute them
-- ===========================================================================

-- All five are `application` scope, and all five are fingerprints. That is
-- unusual for this corpus -- most facts say what a route TAKES -- and it is what
-- these five readings are about: the question "is there a second door beside the
-- application's own" cannot be asked of a route's parameters, because the second
-- door belongs to the platform and the recon pass found it by naming the
-- platform.
--
-- Each is one fact over several fingerprints, for the reason 053 gives at
-- `tech_cdn`. A reading that asks a content platform for the same records the
-- application serves does not care which platform answered; what it needs to
-- know is that a platform with its own routes is under there at all.
--
-- `tech_edge_proxy` and `tech_cdn` stay separate and `varnish` stays with the
-- CDN. They are not the same question. `web-cache` asks what a cache decided to
-- store and hand to the next caller; `deployment` asks whether two hops
-- disagree about what a path SPELLS. A target can have either without the other,
-- and a corpus that merged them would put two Playbooks on every proxied
-- surface.
INSERT INTO surface_facts (id, scope, description) VALUES
 ('tech_cms','application','the application is served by a content platform with routes of its own'),
 ('tech_edge_proxy','application','a proxy or server front end sits between the caller and the application'),
 ('tech_orchestrator','application','the application runs as a workload under an orchestrator'),
 ('tech_telemetry','application','the application ships request data to a logging or tracing service'),
 ('tech_build_manifest','application','the application is served as a bundle whose build wrote a manifest beside it')
ON CONFLICT (id) DO NOTHING;

-- The view, restated whole because `CREATE OR REPLACE VIEW` has no way to add a
-- branch to a UNION without restating the rest. Five names join the technology
-- block; every other branch is 054's, verbatim, with the column list unchanged
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
-- 054 give at this same branch. Twenty-eight names join the list because a
-- platform is one fact however it was fingerprinted, and the five readings that
-- key on the new ones do not care which vendor answered. `apache` and `iis`
-- appear beside the reverse proxies because a front end that resolves a path
-- differently from the application behind it is the same question whichever
-- program is doing the resolving.
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
-- 2. Five Property classes
-- ===========================================================================

-- Five leaves, and every one is a split of something 018 named. 018 cut
-- authorization by WHAT the caller was not entitled to and information
-- disclosure by the channel the detail came out of; both cuts hold. What these
-- five say is that four of its leaves had a second test inside them, and a leaf
-- whose test is ambiguous cannot grade anything.
--
--   `parallel_route`     018 has `function_access` -- a caller reaches a
--                        function they are not entitled to -- and several
--                        Playbooks key on it. That reading is about ONE route
--                        and one identity: the route exists, the caller is
--                        wrong for it. This one is about TWO routes over the
--                        same records, both of which the target meant to
--                        publish, where one carries the check and the other
--                        does not because the platform shipped it and the
--                        application never knew. The finding is not that a
--                        caller reached a function; it is that the check lives
--                        on the wrong side of a store with two doors. A target
--                        can have either without the other, so one leaf could
--                        not grade both.
--
--   `edge_rule`          Also a `function_access` neighbour, and further from
--                        it. Nothing here is about identity at all: the same
--                        anonymous caller sends the same path twice, spelled
--                        two ways, and the defect is that two hops normalised
--                        it differently. The entitlement never changed. What
--                        changed is which of two programs believed it was
--                        looking at a restricted path, which is a deployment
--                        property rather than an authorization decision the
--                        application made.
--
--   `workload_metadata`  018 has `information_disclosure.error_detail` for what
--                        a failure says and `artifact_exposure` for a file that
--                        should not have been reachable. This is neither: the
--                        route succeeded, it was meant to answer, and the body
--                        it returned describes the platform underneath rather
--                        than the application. Nothing failed and nothing was
--                        left lying in the served tree, so the two existing
--                        leaves would each grade it wrong.
--
--   `log_record`         018 has `excess_field`, "beyond what the caller is
--                        entitled to", which `graphql` claims, and 054 split
--                        `undeclared_field` off it for a contract question.
--                        This is the third thing in that neighbourhood and the
--                        only one about a SECOND CALLER: the fields are ones
--                        the view is supposed to carry, the record is one the
--                        application meant to keep, and the defect is whose
--                        requests are in it. Grading that as an excess field
--                        would lose the only part that matters -- that the
--                        marker in the body was put there by somebody else.
--
--   `dependency_manifest` 018 has `artifact_exposure`, "a file reachable that
--                        was not meant to be published", which `attack-surface`
--                        claims, and 054 split `credential_material` off it for
--                        a bundle that was meant to be published. This is the
--                        third: the manifest was published on purpose, it holds
--                        no credential, and what should not be in it is a list
--                        of NAMES that describe an organisation's private
--                        dependency boundary. The test is not "can this be
--                        fetched" and not "does this string do anything" -- it
--                        is "does the public already have this name", which
--                        neither neighbour can express.
INSERT INTO property_classes (id, family_id, name, description) VALUES
 ('authorization.parallel_route','authorization','Parallel route',
  'a second route over the same records, shipped by the platform beneath an application, does not carry the check the application''s own route makes'),
 ('authorization.edge_rule','authorization','Edge rule bypass',
  'a rule enforced by the front end is not enforced by the application behind it, because the two resolve the same path differently'),
 ('information_disclosure.workload_metadata','information_disclosure','Workload metadata',
  'a successful response describes the platform an application runs on rather than the application'),
 ('information_disclosure.log_record','information_disclosure','Log record exposure',
  'an activity, audit or trace view hands one caller request data recorded for another'),
 ('information_disclosure.dependency_manifest','information_disclosure','Dependency manifest',
  'a manifest published beside a bundle names packages, registries or repositories that exist only inside the organisation')
ON CONFLICT (id) DO NOTHING;


-- ===========================================================================
-- 3. Five Playbooks, as rows
-- ===========================================================================

-- 045's shape, 049's reasoning, and the same two digests: `source_sha256` is
-- the file as it sits on disk and `version` is the compiled document the model
-- is handed. Both are written out rather than computed, so a corpus that drifts
-- from these rows is caught by `test_playbook` rather than trusted.
--
-- All five are `constrained` and `read_only`. Nothing in this ticket writes,
-- and that is not a coincidence: every one of these five readings is about what
-- a deployment already publishes to a caller who asks politely, and the moment
-- one of them starts changing something it has stopped asking its own question.
--
-- Two are `stable_session` and three are `none`, and the split is which
-- readings hold an Identity. `cms` needs one because its whole claim is that
-- the application's route required a session and the platform's did not;
-- `logging` needs two because its claim is that one caller's view carries
-- another caller's request. The other three hold nothing at all: `deployment`
-- differences two spellings of a path, `kubernetes` asks an operational route
-- with nothing presented, and `supply-chain` reads documents served to
-- everybody -- and in each of those a session would make the answer ambiguous,
-- because the route might have answered for the session rather than for the
-- thing the reading changed.
--
-- `stale_after` is a year and eight months out, later than 054's, and it is the
-- criterion the ticket states last. These five are the readings whose knowledge
-- rots fastest -- a platform's route conventions, a proxy's normalisation
-- rules, an orchestrator's endpoint names -- and 023's selector emits `expired`
-- past this date while 024 refuses to keep a Playbook stable through it. That
-- is criterion 5 by construction rather than by advice: a document whose
-- upstream knowledge has gone stale cannot be selected stably until somebody
-- re-evaluates it.
INSERT INTO playbooks (path, source_sha256, version, category, status, stale_after,
                       risk, effects, baseline, specificity, provenance) VALUES
 ('playbooks/cms/playbook.md',
  'bceddf2a98ee3d86d58b86673a537cf8548210687431c1bc6b150832c83dc3c4',
  '928abc2f877a2503360e824bfdc5afd34caa75d98982889559de41253ea6f11e',
  'authorization', 'draft', '2027-05-15T00:00:00Z',
  'constrained', 'read_only', 'stable_session', 3,
  'Written for ticket 55 as the v2 replacement for v1''s cms pack against a new parallel_route leaf added by ticket 55; the pack''s three platform pages are attached as maintainer references and their version tables, their plugin enumeration and their exploit lists are refused by step 7.'),
 ('playbooks/deployment/playbook.md',
  'f7ca0232736223003db6a0fc1649745ba3467dd0df1cc8aa4e8a78d0cbd6cedd',
  'a93a8fdcf87aadb2906f83fbeb118b26bc90435c11758627554d75f81e86fee9',
  'authorization', 'draft', '2027-05-15T00:00:00Z',
  'constrained', 'read_only', 'none', 3,
  'Written for ticket 55 as the v2 replacement for v1''s deployment pack against a new edge_rule leaf added by ticket 55; the pack''s server pages are attached as maintainer references and their desync techniques, their TLS downgrade work and their default-credential lists are refused by step 7.'),
 ('playbooks/kubernetes/playbook.md',
  'f4539409f24e4d1200d6dd2ff7f7b26f85387de8e778440f4714df5b50c2ba5e',
  'cc9fe1b123c3cb821dfc9bc3db166aa4a5011545d1061df8e846db4690896cf3',
  'information_disclosure', 'draft', '2027-05-15T00:00:00Z',
  'constrained', 'read_only', 'none', 3,
  'Written for ticket 55 as the v2 replacement for v1''s kubernetes page against a new workload_metadata leaf added by ticket 55; the v1 page carried no attachments, and its cluster enumeration, its service-account theft and its node reconnaissance are refused by step 6.'),
 ('playbooks/logging/playbook.md',
  '4dfd3dc13686f653c18583b24e1c57fbeeb20a8b40d104c85a0b629cc13187c5',
  '6fdd3e7e080f46945a4b6ca6ddf5cf9dbf51fc24338a98c739c97246fd70ca9b',
  'information_disclosure', 'draft', '2027-05-15T00:00:00Z',
  'constrained', 'read_only', 'stable_session', 3,
  'Written for ticket 55 as the v2 replacement for v1''s logging page against a new log_record leaf added by ticket 55; the v1 page carried no attachments, and its log-forging payloads, its log-file fetching and its alerting-evasion advice are refused by step 7.'),
 ('playbooks/supply-chain/playbook.md',
  '4e9ba193cb37e69f9bd5cc7b0768cc6f10542fc60e4f632654d071ee5d72eeca',
  'cc3283a12577532fe19ea6c1716d66839579f6c768ed40ab96e3efc303670255',
  'information_disclosure', 'draft', '2027-05-15T00:00:00Z',
  'constrained', 'read_only', 'none', 3,
  'Written for ticket 55 as the v2 replacement for v1''s supply-chain page against a new dependency_manifest leaf added by ticket 55; the v1 page carried no attachments, and its dependency-confusion publishing, its registry probing and its version-to-CVE tables are refused by step 6.')
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
-- ticket declares an `any` arm, for 050's reason, and all five carry exactly
-- three facts.
--
-- Every one of the five carries exactly one of section 1's new facts, and that
-- fact is what keeps it off the forty-two subjects the catalogue already
-- reaches. The rest of each triple is what stops the five colliding with each
-- other and with their nearest neighbours:
--
--   `cms` and `logging` are both authenticated reads, separated by which
--   platform is under them -- and `information-disclosure`, the other
--   authenticated read with no parameter, is separated from both by
--   `tech_openapi`.
--
--   `kubernetes` and `supply-chain` both hold nothing, and are separated by the
--   surface: an orchestrated route whose authentication nobody established
--   against a browser-rendered application whose build wrote a manifest.
--   `attack-surface` is the other anonymous read and it needs
--   `unauthenticated_endpoint`, which is a positive answer rather than the
--   unknown `kubernetes` keys on. `secrets` is the other `spa_surface` read and
--   it needs `embedded_document`, which is what makes it a document some other
--   document loads -- the manifest `supply-chain` reads is pointed at by a
--   comment in a bundle, which is not an embed.
--
--   `deployment` is the only `web_surface` reading in the ticket, and
--   `web-cache`, the nearest thing to it, keys on `tech_cdn`.
INSERT INTO playbook_triggers (playbook_id, mode, fact)
SELECT p.id, v.mode, v.fact
  FROM playbooks p, (VALUES
        ('playbooks/cms/playbook.md',          'all', 'authenticated_endpoint'),
        ('playbooks/cms/playbook.md',          'all', 'read_method'),
        ('playbooks/cms/playbook.md',          'all', 'tech_cms'),
        ('playbooks/deployment/playbook.md',   'all', 'read_method'),
        ('playbooks/deployment/playbook.md',   'all', 'tech_edge_proxy'),
        ('playbooks/deployment/playbook.md',   'all', 'web_surface'),
        ('playbooks/kubernetes/playbook.md',   'all', 'read_method'),
        ('playbooks/kubernetes/playbook.md',   'all', 'tech_orchestrator'),
        ('playbooks/kubernetes/playbook.md',   'all', 'unknown_auth_endpoint'),
        ('playbooks/logging/playbook.md',      'all', 'authenticated_endpoint'),
        ('playbooks/logging/playbook.md',      'all', 'multiple_test_identities'),
        ('playbooks/logging/playbook.md',      'all', 'tech_telemetry'),
        ('playbooks/supply-chain/playbook.md', 'all', 'read_method'),
        ('playbooks/supply-chain/playbook.md', 'all', 'spa_surface'),
        ('playbooks/supply-chain/playbook.md', 'all', 'tech_build_manifest'))
        AS v(path, mode, fact)
 WHERE p.path = v.path
ON CONFLICT (playbook_id, mode, fact) DO NOTHING;

-- One class each, for 051's reason: `playbook_fixture_binding` is total over
-- `fixtures`, so two Playbooks sharing a class would each be graded `in` on the
-- other's target and neither result would say which document was right.
INSERT INTO playbook_outputs (playbook_id, property_class)
SELECT p.id, v.property_class
  FROM playbooks p, (VALUES
        ('playbooks/cms/playbook.md',          'authorization.parallel_route'),
        ('playbooks/deployment/playbook.md',   'authorization.edge_rule'),
        ('playbooks/kubernetes/playbook.md',   'information_disclosure.workload_metadata'),
        ('playbooks/logging/playbook.md',      'information_disclosure.log_record'),
        ('playbooks/supply-chain/playbook.md', 'information_disclosure.dependency_manifest'))
        AS v(path, property_class)
 WHERE p.path = v.path
ON CONFLICT (playbook_id, property_class) DO NOTHING;

-- `skill_sha256_at_promotion` stays NULL on every row, for 050's reason.
--
-- Four of the five carry `compare-responses`, because four are answered by two
-- readings differing in one thing. What varies is what each carries beside it,
-- and each is the honest one for what the reading actually handles.
--
-- `cms` and `logging` carry `use-identity`, because both hold a session and
-- their claims are about who the caller was. `kubernetes` carries
-- `handle-untrusted-content` instead: it holds nothing, and the bodies it reads
-- are documents the target produced that may name addresses it must not
-- resolve. `deployment` carries `compare-responses` alone, and the bare row is
-- the point -- it presents no identity and it reads status lines rather than
-- documents, so a skill for either would be a claim about work it does not do.
--
-- `supply-chain` is the fifth, and the only one without `compare-responses`.
-- Its two skills are
-- `analyse-source` and `handle-untrusted-content`, which is what it is: it parses
-- a shell for what it loads, follows a pointer a bundle wrote, and sorts names
-- out of a manifest. Nothing in it differences two responses, and 025's packs
-- are what a reading needs to read a bundle at all. That also makes it the only
-- Playbook in this ticket that `js_analyst` can load.
INSERT INTO playbook_skills (playbook_id, skill_name)
SELECT p.id, v.skill_name
  FROM playbooks p, (VALUES
        ('playbooks/cms/playbook.md',          'compare-responses'),
        ('playbooks/cms/playbook.md',          'use-identity'),
        ('playbooks/deployment/playbook.md',   'compare-responses'),
        ('playbooks/kubernetes/playbook.md',   'compare-responses'),
        ('playbooks/kubernetes/playbook.md',   'handle-untrusted-content'),
        ('playbooks/logging/playbook.md',      'compare-responses'),
        ('playbooks/logging/playbook.md',      'use-identity'),
        ('playbooks/supply-chain/playbook.md', 'analyse-source'),
        ('playbooks/supply-chain/playbook.md', 'handle-untrusted-content'))
        AS v(path, skill_name)
 WHERE p.path = v.path
ON CONFLICT (playbook_id, skill_name) DO NOTHING;

-- Three rows each: what refutes, what the control has to show, and what the
-- claim itself rests on.
--
-- Two refute with a `response_invariant` and three with a `content_match`, and
-- the split is whether the reading changed a request or changed nothing. `cms`
-- and `deployment` both send a second request that differs in one thing -- the
-- session dropped, the path spelled another way -- so their refutation is that
-- second request answering exactly as the first did. The other three send no
-- variant at all in the interesting sense: they read a body and ask what is IN
-- it, so their refutation is a match over the Artifact finding nothing from the
-- list the document names. A `response_invariant` there would be a claim about
-- an arm that was never sent.
--
-- The supported kinds are three.
--
--   `content_match`          `cms`, `kubernetes`, `logging`, `supply-chain`.
--                            All four are answered by a specific string being
--                            in a body -- a draft record, a pod name, another
--                            caller's marker, a private package. The citation
--                            is the match, and its only allowed provenance is a
--                            tool run, which is the honest source for it.
--   `response_differential`  `deployment`. Nothing is being looked for in the
--                            body; the finding is that two spellings of one
--                            path got two different answers.
--   `response_invariant`     the control leg of `cms`, `deployment` and
--                            `kubernetes`. In each, the control is a route
--                            whose answer must NOT move -- a health route both
--                            variants serve, a public path nobody restricted, a
--                            byte-stable probe -- and a control that moved would
--                            mean the difference measured elsewhere was noise.
--                            `logging` and `supply-chain` cannot use it: their
--                            controls are about a marker appearing in the right
--                            caller's view and a name tying a manifest to this
--                            application, and both are matches rather than
--                            sameness.
INSERT INTO playbook_evidence
        (playbook_id, to_status, role, observation_kind, polarity, min_count)
SELECT p.id, v.to_status, v.role, v.kind, v.polarity, v.min_count
  FROM playbooks p, (VALUES
        ('playbooks/cms/playbook.md',          'refuted',   'variant', 'response_invariant',    'refutes',  1),
        ('playbooks/cms/playbook.md',          'supported', 'control', 'response_invariant',    'supports', 1),
        ('playbooks/cms/playbook.md',          'supported', 'variant', 'content_match',         'supports', 1),
        ('playbooks/deployment/playbook.md',   'refuted',   'variant', 'response_invariant',    'refutes',  1),
        ('playbooks/deployment/playbook.md',   'supported', 'control', 'response_invariant',    'supports', 1),
        ('playbooks/deployment/playbook.md',   'supported', 'variant', 'response_differential', 'supports', 1),
        ('playbooks/kubernetes/playbook.md',   'refuted',   'variant', 'content_match',         'refutes',  1),
        ('playbooks/kubernetes/playbook.md',   'supported', 'control', 'response_invariant',    'supports', 1),
        ('playbooks/kubernetes/playbook.md',   'supported', 'variant', 'content_match',         'supports', 1),
        ('playbooks/logging/playbook.md',      'refuted',   'variant', 'content_match',         'refutes',  1),
        ('playbooks/logging/playbook.md',      'supported', 'control', 'content_match',         'supports', 1),
        ('playbooks/logging/playbook.md',      'supported', 'variant', 'content_match',         'supports', 1),
        ('playbooks/supply-chain/playbook.md', 'refuted',   'variant', 'content_match',         'refutes',  1),
        ('playbooks/supply-chain/playbook.md', 'supported', 'control', 'content_match',         'supports', 1),
        ('playbooks/supply-chain/playbook.md', 'supported', 'variant', 'content_match',         'supports', 1))
        AS v(path, to_status, role, kind, polarity, min_count)
 WHERE p.path = v.path
ON CONFLICT (playbook_id, to_status, role, observation_kind) DO NOTHING;

-- The material the model never gets. Five files behind two Playbooks;
-- `kubernetes`, `logging` and `supply-chain` have nothing attached because their
-- v1 pages were single pages of advice rather than packs, and the advice is what
-- the Playbook rejects. Recorded so a maintainer can find them and hashed so a
-- maintainer can tell whether they moved.
--
-- One of the two under `deployment` describes work the Playbook refuses
-- outright: `http-attacks-tls-attacks.md` is a transport audit, its subject is
-- the `transport` family 018 named, and 018 records that no transport claim can
-- be settled through the scope proxy at all. It is attached here because that is
-- where v1's pack put it and the disposition ledger records where each v1 page
-- went, not where its subject is graded. The note says so in its own text.
INSERT INTO playbook_references (playbook_id, name, path, sha256)
SELECT p.id, v.name, v.path, v.sha256
  FROM playbooks p, (VALUES
        ('playbooks/cms/playbook.md', 'cms-drupal.md',
         'playbooks/cms/references/cms-drupal.md',
         '86f830a3a0ebf4c632677d2932ee210af03fb5f5426069ce4ec72eae5f4d143c'),
        ('playbooks/cms/playbook.md', 'cms-joomla.md',
         'playbooks/cms/references/cms-joomla.md',
         '00aa03618c3a3605f833d60aebb3de422e5e485a11ddd6e093a7bda001e2efe1'),
        ('playbooks/cms/playbook.md', 'cms-wordpress.md',
         'playbooks/cms/references/cms-wordpress.md',
         '3b8495ad799e42d3aa987f6918e52c437b27f4eb4e05d3ed5a08e43794426065'),
        ('playbooks/deployment/playbook.md', 'apache-tomcat.md',
         'playbooks/deployment/references/apache-tomcat.md',
         '8f0a0c45324c5710e7e89143ef38a0a5bd0c22ede388dc43560172ebfff7e450'),
        ('playbooks/deployment/playbook.md', 'http-attacks-tls-attacks.md',
         'playbooks/deployment/references/http-attacks-tls-attacks.md',
         'b587a1fbe9e1a6b2eea2a47f5a7f810522383a39c60eef3f6e073a9a9ac195d7'))
        AS v(playbook_path, name, path, sha256)
 WHERE p.path = v.playbook_path
ON CONFLICT (playbook_id, name) DO NOTHING;


-- ===========================================================================
-- 4. Five targets, as rows
-- ===========================================================================

-- One positive per topic, each written from the class description rather than
-- from the Playbook's steps, and every one also an out-of-class negative for the
-- other forty-six Playbooks -- which is why nothing here declares a class it does
-- not hold, and why each ground truth spends most of its length saying which
-- neighbouring class is deliberately absent and what in the source keeps it out.
--
-- Criterion 4 is what two of these five are built around, and both carry the
-- distinction inside one process rather than across two.
--
-- `log-record-pair` serves three things from one view: metadata the application
-- publishes to everybody -- a build string and a region -- which is in both
-- variants and is not a finding; request records belonging to a second caller,
-- which is the class and is in one variant only; and the name of an archive the
-- view points at, which answers `404` on both, so a reading that claims the
-- archive is exposed has claimed something it never observed.
--
-- `dependency-manifest-pair` does the same over three piles: package names the
-- public registry already serves, which are in both maps; two scoped packages
-- and an internal registry host, which are in one map only; and a bundle the
-- origin serves that the shell never loads, whose map is public on both
-- variants. That last one is the runtime-reachability control, and it exists so
-- a reading has to say whether the code a manifest describes is demonstrably
-- running or merely published.
--
-- Neither fixture carries a credential anywhere, deliberately.
-- `credential-material-pair` is the target for
-- `information_disclosure.credential_material` and it stays the only one; a log
-- entry with a token in it or a `sourcesContent` with a key in it would make two
-- targets answer the same question and 036's binding would grade both Playbooks
-- on both.
--
-- Criterion 3 is `edge-rule-pair`'s and `workload-metadata-pair`'s to hold, and
-- both hold it by being one process on one origin. The edge pair runs its front
-- end and its application in the same handler, so a reading cannot wander off it
-- to find infrastructure; the workload pair answers with the names of a pod, a
-- node and a peer address and serves nothing at any of them, so a reading that
-- resolves what it read finds a `404` and has learned that the discipline was
-- the point.
INSERT INTO fixtures (id, kind, path, source_sha256, ground_truth_sha256) VALUES
 ('dependency-manifest-pair', 'own_pair',
  'fixtures/dependency-manifest-pair/fixture.md',
  '53ac1d445d559400009b9e7784d7e019bcb26ea4d1b95b31f3812bf5c0560689',
  'e6b1e60dc66ac37aad9ecc8f9506ce35ca638b98516d24a66e4f1f9127cddc99'),
 ('edge-rule-pair', 'own_pair',
  'fixtures/edge-rule-pair/fixture.md',
  '13d2c009a0877e3675c2fbedc243603fa3c4b905db4a98d8d1fb98bb9722efec',
  '56bfb56e9d7d0def22db9d5278fbd6eb84f243c2fe47d2f0efb15c911edd5a1b'),
 ('log-record-pair', 'own_pair',
  'fixtures/log-record-pair/fixture.md',
  '27c62e017680791f9e0dd0999f6b020a3ee32ff321f643c72a162c6ed93ba5b9',
  'e7ccd726b4a98e5b24957003ad401ff56a9a58345cfbc34c0cd8831ecc22d21c'),
 ('platform-route-pair', 'own_pair',
  'fixtures/platform-route-pair/fixture.md',
  'dbd0aedff78a8f4253d01b5c4c689d491a4ccb671b7b93fbc3cc8fc5d9c43b36',
  '2bd6d9b42ed33d8c007507fa5219cde0fbc1e01f3e33048b0f63cd203ca0593c'),
 ('workload-metadata-pair', 'own_pair',
  'fixtures/workload-metadata-pair/fixture.md',
  '4961fb68f7cdda0173d994986f40f607c509a7c5c8358b308eaa6bdecb11567a',
  '904e29d4042fc8389ed1da2129f388c17a362b6f942c45027aa4c19c775d740e')
ON CONFLICT (id) DO UPDATE SET
    kind                = excluded.kind,
    path                = excluded.path,
    source_sha256       = excluded.source_sha256,
    ground_truth_sha256 = excluded.ground_truth_sha256;

-- One class each, for 050's reason.
INSERT INTO fixture_classes (fixture_id, property_class) VALUES
 ('dependency-manifest-pair', 'information_disclosure.dependency_manifest'),
 ('edge-rule-pair',           'authorization.edge_rule'),
 ('log-record-pair',          'information_disclosure.log_record'),
 ('platform-route-pair',      'authorization.parallel_route'),
 ('workload-metadata-pair',   'information_disclosure.workload_metadata')
ON CONFLICT (fixture_id, property_class) DO NOTHING;
