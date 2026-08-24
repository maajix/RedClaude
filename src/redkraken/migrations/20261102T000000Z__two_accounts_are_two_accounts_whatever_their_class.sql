-- Ticket 133: a privileged slot silently disarms seven Playbooks
--
-- The decision, and the reason it is this one:
--
-- `multiple_test_identities` is the surface fact that says "this Program holds
-- two accounts a differential can be taken between". 0032 computed it as
-- `count(*) WHERE class = 'user' >= 2`, which was right when it was written --
-- `program._project_identities` classed every configured slot `user`, so the
-- filter was decoration. Ticket 112 made the class real, and the filter became
-- a trap: an operator who correctly labels one of two slots `privileged` drops
-- the count to one, and seven Playbooks stop being offered without a word being
-- said. That is the exact failure the 112 header argues against, one branch
-- away from where it argued it.
--
-- Of the three shapes the ticket named, this file takes the second: the fact is
-- restated as two or more distinct accounts of any class but `anonymous`. The
-- first -- add `privileged` to the list -- reaches the same rows today and is a
-- list to keep in step with a CHECK constraint forever. The third -- the count
-- stands and the Playbooks are right to go quiet -- is refused by what those
-- Playbooks actually ask for: `object-ownership` wants a second account to read
-- the first one's objects with, and an admin account is a second account. A
-- user/admin pair is the sharper differential, not a missing precondition.
--
-- `anonymous` stays out, and that is the one class this branch is really about:
-- an unauthenticated caller is not an account, and the difference between an
-- account and nobody is `anonymous_identity_available`, which already exists.
-- Since ticket 131 every Program mints an anonymous Identity for its first
-- Task, so counting it would hand this fact to every Program with one slot.
--
-- The second half of the ticket is section 2: whatever is decided, an operator
-- can see it. `playbook_near_misses` says which fact a Playbook lacked; nothing
-- said why the Program lacks it, which for an identity fact is always a
-- configuration an operator could change.


-- ===========================================================================
-- 1. Two accounts are two accounts, whatever their class
-- ===========================================================================
--
-- Restated whole because a view cannot be amended in place. Every line is
-- 20261023T000000Z's except the `multiple_test_identities` branch, which is the
-- one this file is about.
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
) computed;;

COMMENT ON VIEW subject_facts IS
    'Ticket 45 criterion 1, ticket 164 and ticket 133: the surface facts one '
    'subject carries, computed from the canonical rows and never stored. A '
    'subject is an Endpoint or the Application it sits under: 032 keyed this '
    'view on the Endpoint alone, and every hunt Task carries the subject of the '
    'Hypothesis that derived it, which is the Application. An Application reads '
    'the union of its Endpoints'' facts and its own. multiple_test_identities '
    'counts accounts of any class but anonymous, because a user/admin pair is a '
    'differential and not a missing precondition.';


-- ===========================================================================
-- 2. Why a Program lacks an identity fact, in words that are a closed set
-- ===========================================================================
--
-- Four of the surface facts are about the Program's identity configuration
-- rather than about any subject, and they are the four an operator can do
-- something about: every other fact is something recon has to find. So when one
-- is missing there is always a reason, the reason is always a configuration,
-- and it is worth naming.
--
-- Typed rather than prose, because the caller is a log line and the reader is
-- an operator at three in the morning: `one_account_configured` is a thing to
-- act on, "not enough identities" is not. The set is closed and small, and each
-- row carries the Playbooks that fact gates, so the news is what it costs.
--
-- Reasons, by fact:
--   multiple_test_identities       no_account_configured, one_account_configured
--   privileged_identity_available  no_privileged_identity
--   anonymous_identity_available   no_anonymous_identity
--   tenant_boundary                no_tenant_membership, one_tenant_only
--
-- An invalidated Identity is not counted and is not a reason of its own: a slot
-- whose credential was withdrawn is a slot to re-provision, which is the same
-- instruction as configuring one.
CREATE FUNCTION program_identity_gaps(p_program uuid)
RETURNS TABLE (fact text, reason text, gated_playbooks text[])
LANGUAGE sql STABLE AS $fn$
    WITH live AS (
        SELECT i.class, count(DISTINCT i.entity_id) AS n
          FROM identities i
         WHERE i.program_id = p_program AND i.invalidated_at IS NULL
         GROUP BY i.class
    ),
    counted AS (
        SELECT coalesce((SELECT sum(n) FROM live WHERE class <> 'anonymous'), 0) AS accounts,
               coalesce((SELECT sum(n) FROM live WHERE class = 'privileged'), 0) AS privileged,
               coalesce((SELECT sum(n) FROM live WHERE class = 'anonymous'), 0) AS anonymous,
               coalesce((SELECT count(DISTINCT r.dst_entity_id)
                           FROM identities i
                           JOIN relationships r ON r.src_entity_id = i.entity_id
                                               AND r.type = 'member_of'
                          WHERE i.program_id = p_program), 0) AS tenants
    ),
    gap AS (
        SELECT 'multiple_test_identities'::text AS fact,
               CASE WHEN c.accounts = 0 THEN 'no_account_configured'
                    ELSE 'one_account_configured' END::text AS reason
          FROM counted c WHERE c.accounts < 2
        UNION ALL
        SELECT 'privileged_identity_available', 'no_privileged_identity'
          FROM counted c WHERE c.privileged = 0
        UNION ALL
        SELECT 'anonymous_identity_available', 'no_anonymous_identity'
          FROM counted c WHERE c.anonymous = 0
        UNION ALL
        SELECT 'tenant_boundary',
               CASE WHEN c.tenants = 0 THEN 'no_tenant_membership'
                    ELSE 'one_tenant_only' END
          FROM counted c WHERE c.tenants < 2
    )
    SELECT g.fact, g.reason,
           coalesce((SELECT array_agg(DISTINCT p.path)
                       FROM playbook_triggers t JOIN playbooks p ON p.id = t.playbook_id
                      WHERE t.fact = g.fact AND p.status <> 'deprecated'),
                    '{}'::text[])
      FROM gap g
     ORDER BY g.fact;
$fn$;

COMMENT ON FUNCTION program_identity_gaps(uuid) IS
    'Ticket 133: the identity-shaped surface facts this Program does not carry, '
    'why in one word from a closed set, and the Playbooks each one gates. The '
    'other side of playbook_near_misses -- that says which fact a Playbook '
    'wanted, this says what an operator would have to configure for the Program '
    'to have it. An invalidated Identity is not counted and is not a reason of '
    'its own: a withdrawn credential is a slot to re-provision.';

REVOKE ALL ON FUNCTION program_identity_gaps(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION program_identity_gaps(uuid) TO rk2_runtime, rk2_human;

INSERT INTO runtime_verb_surface (verb, added_by, note) VALUES
    ('program_identity_gaps(uuid)', '133',
     'the second half of the sentence execution._near prints: a Playbook one identity fact short says which configuration would have given the Program that fact');


-- ===========================================================================
-- 3. What would have to be true
-- ===========================================================================

DO $$
DECLARE n integer;
BEGIN
    -- Section 1, asked of the view the server holds rather than of the text
    -- above: the new class filter is there.
    IF position('<> ''anonymous''' IN pg_get_viewdef('subject_facts'::regclass)) = 0 THEN
        RAISE EXCEPTION '133 rebuilt subject_facts without the new account count';
    END IF;

    -- 164's own guard, re-asked because this file rebuilt the view it guards:
    -- every registered surface fact still has a branch that computes it.
    SELECT count(*) INTO n FROM surface_facts f
     WHERE position(('''' || f.id || '''') IN pg_get_viewdef('subject_facts'::regclass)) = 0
       AND position((f.id) IN pg_get_viewdef('subject_facts'::regclass)) = 0;
    IF n > 0 THEN
        RAISE EXCEPTION '133 left % registered surface fact(s) with no branch', n;
    END IF;

    -- Section 2 against a Program that does not exist, which is the shape of a
    -- Program that has configured nothing: all four facts missing, each with the
    -- reason that says nothing is there rather than that one thing is.
    SELECT count(*) INTO n
      FROM program_identity_gaps('00000000-0000-0000-0000-000000000000'::uuid)
     WHERE reason IN ('no_account_configured', 'no_privileged_identity',
                      'no_anonymous_identity', 'no_tenant_membership');
    IF n <> 4 THEN
        RAISE EXCEPTION '133 reported % of 4 gaps for a Program holding nothing', n;
    END IF;

    -- And that the news is worth printing: the fact this file widened gates
    -- Playbooks, so a Program without it is told what it is missing out on.
    SELECT cardinality(gated_playbooks) INTO n
      FROM program_identity_gaps('00000000-0000-0000-0000-000000000000'::uuid)
     WHERE fact = 'multiple_test_identities';
    IF n < 1 THEN
        RAISE EXCEPTION '133 named no Playbook gated by multiple_test_identities';
    END IF;
END $$;
