-- ---------------------------------------------------------------------------
-- 20261215T000000Z__four_readings_the_vocabulary_could_not_spell.sql
--                                                                  (ticket 100)
--
-- Four Property classes and two surface facts, each class arriving with the
-- fixture that grades it.
--
-- The counts this file works from were read back out of a database with every
-- migration applied and all fifty Playbooks loaded, not from the migration that
-- first declares each vocabulary: 57 property classes, 16 observation kinds of
-- which 11 are evidential, 55 surface facts, 55 fixtures. An earlier reading
-- counted from `0018_vocabularies.sql` and `0032_playbooks.sql` alone and
-- reported 47, 14 and 33; eight later migrations extend all three, because
-- every Playbook batch since has added the vocabulary it needed.
--
-- Most of what earlier notes called missing is present, and is recorded here as
-- present rather than added a second time:
--
--   `authentication.recovery_flow`               0018, and `recovery-flow-pair`
--                                                already grades it. What it
--                                                lacks is an emitter, which is
--                                                ticket 101's work.
--   `authorization.tenant_isolation`             0018, and emitted:
--                                                `playbooks/workload-identities`
--                                                declares it and
--                                                `tenant-isolation-pair` grades
--                                                it. The claim that there is no
--                                                class for tenant isolation
--                                                over HTTP does not check out.
--   `information_disclosure.cached_response`     20260829, emitted by
--                                                `playbooks/web-cache`. Cache
--                                                deception is covered.
--
-- What is genuinely absent is these four, and the list is short on purpose. A
-- class with no emitter is what `authentication.recovery_flow` already is, and
-- adding six more would multiply that failure rather than fix it -- which is
-- why this file lands after the capability work and not before it.
--
--   `injection.unclaimed_reference`              07 #1, #5 and the read half of
--                                                07 #12. The string `takeab`
--                                                appeared nowhere under `src/`.
--   `authorization.object_property_write`        the write half of mass
--                                                assignment. 04 #541 records
--                                                the gap: `object_ownership` is
--                                                the object named by the
--                                                request, `excess_field` is the
--                                                read half, and `object_graph`
--                                                is which type a route
--                                                reconstructs.
--   `session_handling.cookie_parsing`            02 #4. `cookie_scope` is the
--                                                nearest and is about scope.
--   `injection.parser_differential`              05 #8.
--
-- Every one of the four arrives with its fixture in this same file. That is the
-- rule this ticket exists to enforce and not a nicety: a class no fixture
-- declares gives `playbook_fixture_binding` an empty in-pair side, and
-- `playbook_test_verdict` then stops at `untested` however many runs are spent.
--
-- The two surface facts do not, and the reason is stated rather than skipped.
-- `scim_surface` and `pipeline_surface` are preconditions for 03 #10, 03 #15
-- and 07 #11, and the Playbooks that would fire on them are ticket 101's. A
-- fact no fixture presents is a trigger no evaluation exercises, which is the
-- same unused-vocabulary shape as an emitterless class -- smaller, because a
-- fact cannot be a verdict, and recorded here so it is inherited deliberately.
--
-- No new observation kind. `callback_interaction` exists, is evidential and is
-- backed by `{callback}` alone; the stale refusal that says otherwise is ticket
-- 98's to supersede.
--
-- Nothing here degrades quietly. The catalogue is loaded by migration into
-- `playbooks` and `fixtures` plus their child tables with foreign keys, so an
-- unknown class, trigger, kind or skill fails at INSERT rather than being
-- ignored. That is the safe direction, and it is why a vocabulary migration
-- carries no runtime risk.
-- ---------------------------------------------------------------------------


-- ===========================================================================
-- 1. The four classes
-- ===========================================================================

INSERT INTO property_classes (id, family_id, name, description) VALUES
 ('injection.unclaimed_reference','injection','Unclaimed reference',
  'a reference the target still publishes resolves to a provider slot that reports itself unheld, and the reading is the reference plus the provider''s own answer rather than a claim on it'),
 ('authorization.object_property_write','authorization','Object property write',
  'a caller sets a property of an object it does own that the application, not the caller, is meant to decide'),
 ('session_handling.cookie_parsing','session_handling','Cookie parsing differential',
  'two components read different values out of one Cookie header, so the request admitted and the request served are not the same request'),
 ('injection.parser_differential','injection','Parser differential',
  'two components parse one representation differently, and the value a check approved is not the value the target acted on')
ON CONFLICT (id) DO NOTHING;


-- ===========================================================================
-- 2. Two surface facts
-- ===========================================================================

-- `application` scope for both: each is a statement about what the subject is,
-- answerable once per application, rather than about one endpoint or about
-- which Identities a Program holds.
INSERT INTO surface_facts (id, scope, description) VALUES
 ('scim_surface','application',
  'a SCIM or just-in-time user-provisioning surface was identified on this application'),
 ('pipeline_surface','application',
  'a build pipeline, repository or workload-identity federation surface was identified on this application')
ON CONFLICT (id) DO NOTHING;


-- ===========================================================================
-- 2b. The branch that computes them
-- ===========================================================================

-- A registered fact with no branch in `subject_facts` is
-- `check_playbook_integrity()`'s `fact_not_computed`, and the rule is textual:
-- it reads the view's own definition looking for the atom's name, which is why
-- 049 through 055 spell every name out instead of assembling it. So the two new
-- atoms are two rows in the same `VALUES` map the `tech_` atoms use, and the
-- view is restated whole because `CREATE OR REPLACE VIEW` has no other option.
--
-- The technology names are the ones recon actually files. A SCIM endpoint is
-- identified as `scim`; a pipeline is identified by the runner that serves it.
-- Neither fact invents a shape the graph cannot already hold, which is the
-- point of deriving them here rather than adding an `applications.kind`.

CREATE OR REPLACE VIEW subject_facts AS
WITH endpoint AS (
    SELECT e.id AS endpoint_id, e.program_id, ep.application_id, ep.method,
           ep.auth_required, ep.request_content_type
      FROM entities e JOIN endpoints ep ON ep.entity_id = e.id
     WHERE e.in_scope
),
ep AS (
    SELECT endpoint_id AS entity_id, endpoint_id, program_id, application_id,
           method, auth_required, request_content_type
      FROM endpoint
    UNION ALL
    -- `in_scope` on the Application as well as on the Endpoint: an Endpoint may
    -- be a target under an Application the live scope has since stopped
    -- admitting, and a fact filed against that Application would be a fact
    -- about a subject no Task may be opened against.
    SELECT en.application_id, en.endpoint_id, en.program_id, en.application_id,
           en.method, en.auth_required, en.request_content_type
      FROM endpoint en
      JOIN entities ae ON ae.id = en.application_id AND ae.in_scope
),
subj AS (
    SELECT entity_id, program_id, application_id FROM ep
    UNION
    SELECT e.id, e.program_id, e.id
      FROM entities e JOIN applications a ON a.entity_id = e.id
     WHERE e.in_scope
)
SELECT DISTINCT program_id, subject_entity_id, fact FROM (
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
UNION ALL SELECT ep.program_id, ep.entity_id,
       CASE p.location WHEN 'path' THEN 'path_parameter' WHEN 'query' THEN 'query_parameter'
                       WHEN 'body' THEN 'body_parameter' WHEN 'header' THEN 'header_parameter'
                       ELSE 'cookie_parameter' END
  FROM ep JOIN parameters p ON p.endpoint_id = ep.endpoint_id
UNION ALL SELECT ep.program_id, ep.entity_id, 'object_identifier'
  FROM ep JOIN parameters p ON p.endpoint_id = ep.endpoint_id
 WHERE p.value_class IN ('uuid','integer_id','opaque_id')
UNION ALL SELECT ep.program_id, ep.entity_id, 'numeric_identifier'
  FROM ep JOIN parameters p ON p.endpoint_id = ep.endpoint_id WHERE p.value_class = 'integer_id'
UNION ALL SELECT ep.program_id, ep.entity_id, 'reflected_parameter'
  FROM ep JOIN parameters p ON p.endpoint_id = ep.endpoint_id WHERE p.reflected IS TRUE
UNION ALL SELECT ep.program_id, ep.entity_id, 'url_valued_parameter'
  FROM ep JOIN parameters p ON p.endpoint_id = ep.endpoint_id WHERE p.value_class = 'url'
UNION ALL SELECT ep.program_id, ep.entity_id, 'file_parameter'
  FROM ep JOIN parameters p ON p.endpoint_id = ep.endpoint_id WHERE p.value_class = 'file'
UNION ALL SELECT ep.program_id, ep.entity_id, 'email_valued_parameter'
  FROM ep JOIN parameters p ON p.endpoint_id = ep.endpoint_id WHERE p.value_class = 'email'
UNION ALL SELECT ep.program_id, ep.entity_id, 'quantity_valued_parameter'
  FROM ep JOIN parameters p ON p.endpoint_id = ep.endpoint_id WHERE p.value_class = 'number'
UNION ALL SELECT ep.program_id, ep.entity_id, 'path_valued_parameter'
  FROM ep JOIN parameters p ON p.endpoint_id = ep.endpoint_id WHERE p.value_class = 'path'
UNION ALL SELECT ep.program_id, ep.entity_id, 'serialized_object_parameter'
  FROM ep JOIN parameters p ON p.endpoint_id = ep.endpoint_id WHERE p.value_class = 'serialized'
-- 056's branch. A self-join on the name with the carriers required to differ,
-- which is the only shape 020's uniqueness admits.
UNION ALL SELECT ep.program_id, ep.entity_id, 'repeated_parameter_name'
  FROM ep JOIN parameters p ON p.endpoint_id = ep.endpoint_id
          JOIN parameters q ON q.endpoint_id = ep.endpoint_id
                           AND q.name = p.name
                           AND q.location <> p.location
UNION ALL SELECT ep.program_id, ep.entity_id, 'redirect_target'
  FROM ep JOIN relationships r ON r.src_entity_id = ep.endpoint_id AND r.type = 'redirects_to'
UNION ALL SELECT ep.program_id, ep.entity_id, 'flow_step'
  FROM ep JOIN relationships r ON r.dst_entity_id = ep.endpoint_id AND r.type = 'redirects_to'
UNION ALL SELECT ep.program_id, ep.entity_id, 'embedded_document'
  FROM ep JOIN relationships r ON r.dst_entity_id = ep.endpoint_id AND r.type = 'embeds'
-- application shape. Read off `subj` rather than `ep`, so an Application that
-- has no Endpoint yet still says what sort of surface it is.
UNION ALL SELECT subj.program_id, subj.entity_id,
       CASE a.kind WHEN 'graphql' THEN 'graphql_surface' WHEN 'spa' THEN 'spa_surface'
                   WHEN 'api' THEN 'api_surface' WHEN 'web' THEN 'web_surface'
                   ELSE 'websocket_surface' END
  FROM subj JOIN applications a ON a.entity_id = subj.application_id
 WHERE a.kind IN ('graphql','spa','api','web','websocket')
-- Spelled out rather than 'tech_' || lower(t.name), for the reason 049 through
-- 055 give at this same branch. The list is 055's unchanged.
UNION ALL SELECT subj.program_id, subj.entity_id, known.fact
  FROM subj JOIN relationships r ON r.src_entity_id = subj.application_id AND r.type = 'runs'
          JOIN technologies t ON t.entity_id = r.dst_entity_id
          JOIN (VALUES ('jwt',           'tech_jwt'),
                       -- Ticket 100. Two names the vocabulary could not
                       -- spell, spelled out here for the reason 049
                       -- through 055 give above: the fact_not_computed
                       -- rule reads this text for the atom's name.
                       ('scim',          'scim_surface'),
                       ('github-actions','pipeline_surface'),
                       ('gitlab-ci',     'pipeline_surface'),
                       ('jenkins',       'pipeline_surface'),
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
-- Ticket 133: two accounts are two accounts, whatever their class. 032 counted
-- `class = 'user'` at a time when every configured slot projected as one, so
-- the count was "how many slots are configured" wearing a class filter. Ticket
-- 112 made `privileged` sayable and the filter started meaning what it says: an
-- operator who correctly labelled one of two slots dropped this fact and seven
-- Playbooks with it. `anonymous` is still excluded, and that is the whole of
-- what the class is asked here -- a differential between an account and nobody
-- is what `anonymous_identity_available` is for.
UNION ALL SELECT subj.program_id, subj.entity_id, 'multiple_test_identities'
  FROM subj WHERE (SELECT count(DISTINCT i.entity_id)
                     FROM entities ie JOIN identities i ON i.entity_id = ie.id
                    WHERE ie.program_id = subj.program_id
                      AND i.class <> 'anonymous'
                      AND i.invalidated_at IS NULL) >= 2
UNION ALL SELECT subj.program_id, subj.entity_id, 'privileged_identity_available'
  FROM subj WHERE EXISTS (SELECT 1 FROM entities ie JOIN identities i ON i.entity_id = ie.id
                           WHERE ie.program_id = subj.program_id AND i.class = 'privileged'
                             AND i.invalidated_at IS NULL)
UNION ALL SELECT subj.program_id, subj.entity_id, 'anonymous_identity_available'
  FROM subj WHERE EXISTS (SELECT 1 FROM entities ie JOIN identities i ON i.entity_id = ie.id
                           WHERE ie.program_id = subj.program_id AND i.class = 'anonymous'
                             AND i.invalidated_at IS NULL)
UNION ALL SELECT subj.program_id, subj.entity_id, 'tenant_boundary'
  FROM subj WHERE (SELECT count(DISTINCT r.dst_entity_id)
                     FROM entities ie JOIN identities i ON i.entity_id = ie.id
                     JOIN relationships r ON r.src_entity_id = ie.id AND r.type = 'member_of'
                    WHERE ie.program_id = subj.program_id) >= 2
) computed;

COMMENT ON VIEW subject_facts IS
 'The trigger stage input. One row per (subject, fact). Registered facts with no '
 'branch here are caught by check_playbook_integrity() rule fact_not_computed.';

-- ===========================================================================
-- 3. One fixture per class
-- ===========================================================================

-- Both digests, for the reason 050 gives: `source_sha256` is what was served
-- and `ground_truth_sha256` is how it was graded, and they move separately. An
-- edit to either without an edit to a migration is drift, and the catalogue
-- test in `tests/test_database.py` is what catches it.
INSERT INTO fixtures (id, kind, path, source_sha256, ground_truth_sha256) VALUES
 ('cookie-parsing-pair', 'own_pair',
  'fixtures/cookie-parsing-pair/fixture.md',
  '999c285e611ce376f8181d5ad026dc61710b3eba05071cccd2b130c80159755f',
  '7c132634ef1eea91f100217a89296c859a63961aa6bf686e2ce4abb80e5a8229'),
 ('object-property-write-pair', 'own_pair',
  'fixtures/object-property-write-pair/fixture.md',
  'e2fd732f12b777481439beaf1a96ad59741e8b091bd80b64471e714d12e42056',
  '675c38eea752e8726be21eb33cd206729b238e3c22b367f89dd6b3d3f45e4d84'),
 ('parser-differential-pair', 'own_pair',
  'fixtures/parser-differential-pair/fixture.md',
  '75a4ae24f0079ec4c436951015bd0fc0c6501c98d09b9d205f33ec566edc33af',
  'a52a4d7a33cb892d695b2ef88ea139ff1dc55472f33bf73bf3941238542067b9'),
 ('unclaimed-reference-pair', 'own_pair',
  'fixtures/unclaimed-reference-pair/fixture.md',
  '89bf3424e5c3994b4d79469685b0281f60d054993bdd08c02165e4ca921e3967',
  '6c9a7fa4758a02612bc443df4882841574a74f6a4606c2f007924f54131a00d2')
ON CONFLICT (id) DO UPDATE SET
    kind                = excluded.kind,
    path                = excluded.path,
    source_sha256       = excluded.source_sha256,
    ground_truth_sha256 = excluded.ground_truth_sha256;

-- One class each, for 050's reason: a fixture claiming two classes cannot say
-- which of them a Playbook that fired on it read. Each fixture document argues
-- in its own words why the neighbouring classes are not merely absent from its
-- ground truth but could not be true of what it serves.
INSERT INTO fixture_classes (fixture_id, property_class) VALUES
 ('cookie-parsing-pair', 'session_handling.cookie_parsing'),
 ('object-property-write-pair', 'authorization.object_property_write'),
 ('parser-differential-pair', 'injection.parser_differential'),
 ('unclaimed-reference-pair', 'injection.unclaimed_reference')
ON CONFLICT (fixture_id, property_class) DO NOTHING;


-- ===========================================================================
-- 4. The counts this file claims to have moved
-- ===========================================================================

-- An INSERT that conflicted away is a vocabulary that did not grow, and the
-- whole ticket is the growth. Checked here rather than in a test, because a
-- corpus that applied and did nothing should not be a corpus that applied.
DO $$
DECLARE n integer;
BEGIN
    SELECT count(*) INTO n FROM property_classes;
    IF n <> 61 THEN
        RAISE EXCEPTION 'ticket 100: % property classes, expected 61', n;
    END IF;

    SELECT count(*) INTO n FROM surface_facts;
    IF n <> 57 THEN
        RAISE EXCEPTION 'ticket 100: % surface facts, expected 57', n;
    END IF;

    SELECT count(*) INTO n FROM fixtures;
    IF n <> 59 THEN
        RAISE EXCEPTION 'ticket 100: % fixtures, expected 59', n;
    END IF;

    -- And the rule the ticket exists to enforce, as a statement rather than as
    -- a count: each of the four new classes has a fixture that declares it.
    SELECT count(*) INTO n
      FROM property_classes p
     WHERE p.id IN ('injection.unclaimed_reference',
                    'authorization.object_property_write',
                    'session_handling.cookie_parsing',
                    'injection.parser_differential')
       AND NOT EXISTS (SELECT 1 FROM fixture_classes f WHERE f.property_class = p.id);
    IF n <> 0 THEN
        RAISE EXCEPTION 'ticket 100: % of the new classes arrived without a fixture', n;
    END IF;
END $$;
