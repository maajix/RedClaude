-- ---------------------------------------------------------------------------
-- fifty_playbooks_and_not_one_has_ever_been_selected.sql   (ticket 164)
--
-- `playbook_selections` is empty in every database this tree has produced.
-- Fifty Playbooks were compiled, gated by `check_wiring`, seeded into every
-- Program, and handed to nobody. `rk2hunt17` said it nine times:
--
--     T8 runs under no Playbook: nothing in the corpus is about this subject
--
-- Two causes, and neither is the corpus. The first is that `subject_facts` has
-- only ever answered about an Endpoint -- 032's `ep` CTE joins `endpoints` and
-- every branch below it is keyed on that row -- while every hunt Task carries
-- the subject of the Hypothesis that derived it, and a Hypothesis a recon child
-- writes is about the Application. So the selection asked about a row the view
-- has no branch for and got the honest answer: nothing. That is section 1.
--
-- The second is that a Playbook missing by one fact and a Playbook about
-- something else entirely are the same output today. `playbook_candidates`
-- filters on `playbooks_by_trigger` before it can report anything, so an
-- operator asking "why did the CMS Playbook not run against a Drupal site" has
-- no row to read. Section 2 gives them one.
--
-- Section 3 states the thing an operator reading "0 selections, 50 drafts"
-- reaches for first, because it is not the cause and the column should say so.
--
-- Not here: `applications.kind`, `endpoints.auth_required` and the `parameters`
-- table are NULL and empty because the child was never told to fill them, and
-- that is a sentence in `_launch.py`, not a schema change. It ships with this
-- ticket and leaves no trace in the corpus.
-- ---------------------------------------------------------------------------


-- ===========================================================================
-- 1. A subject that is an Application has facts
-- ===========================================================================
--
-- Which subject a hunt Task is about, settled: the one the Hypothesis names,
-- whichever type that is. The alternative -- rewriting the Task's subject to
-- the Endpoint the claim is "really" about -- has no rule that could pick the
-- Endpoint, because a claim about an Application ("this deployment runs Drupal
-- and exposes a login") is about the Application and about none of its routes
-- in particular. So the view learns to answer for both, and nothing upstream of
-- it moves.
--
-- An Application's facts are the union of its Endpoints' facts plus its own.
-- That is the reading a Playbook trigger already wants: `tech_cms` was never an
-- Endpoint's property, it was the Application's, and 032 attributed it to the
-- Endpoint only because the Endpoint was the one row the view had a key for.
--
-- Three CTEs where there was one:
--
--   `endpoint`  032's `ep`, renamed, and it keeps the Endpoint's own entity id
--               in a column of its own -- the parameter and relationship
--               branches join on it and must keep reaching the Endpoint even
--               when the subject is the Application.
--   `ep`        one row per (subject, Endpoint under it). The Endpoint answers
--               for itself; the Application answers for what it serves.
--   `subj`      every subject and the Application behind it, including an
--               Application with no Endpoint at all. The branches about the
--               Application and about the Program read this one, so a site that
--               recon found before it found a route still reads `web_surface`
--               rather than nothing.
--
-- `SELECT DISTINCT` on the outside because an Application now collects the same
-- fact from each of its Endpoints. 032 spelled DISTINCT on the branches that
-- needed it and `UNION ALL` on the rest; that split stops being right the
-- moment one subject has two Endpoints, and one DISTINCT at the top is the
-- version that cannot drift.
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
UNION ALL SELECT subj.program_id, subj.entity_id, 'multiple_test_identities'
  FROM subj WHERE (SELECT count(*) FROM entities ie JOIN identities i ON i.entity_id = ie.id
                    WHERE ie.program_id = subj.program_id AND i.class = 'user'
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
    'Ticket 45 criterion 1 and ticket 164: the surface facts one subject '
    'carries, computed from the canonical rows and never stored. A subject is '
    'an Endpoint or the Application it sits under: 032 keyed this view on the '
    'Endpoint alone, and every hunt Task carries the subject of the Hypothesis '
    'that derived it, which is the Application. An Application reads the union '
    'of its Endpoints'' facts and its own.';


-- ===========================================================================
-- 2. A Playbook that misses by one fact is reported as missing by one
-- ===========================================================================
--
-- `playbooks_by_trigger` answers yes or no and `playbook_candidates` starts
-- from its yes set, so a Playbook that holds two of three trigger facts leaves
-- no row anywhere. That is the one output this machinery could give that an
-- operator cannot get any other way: the corpus is fifty documents and the
-- question "what would I have had to know for this one to run" is a query, not
-- a reading exercise.
--
-- Counted the way `playbooks_by_trigger` decides, so the two cannot disagree:
-- every `all` fact the subject lacks, plus one for an `any` group that nothing
-- satisfied. A Playbook whose `any` group is unsatisfied is one fact short even
-- when that fact could be any of six, and reporting six would rank it behind
-- eight Playbooks that are further away.
--
-- `deprecated` is excluded and nothing else is. A deprecated Playbook can never
-- be selected however many facts arrive, so its near miss is noise; every other
-- metadata reason is about this Program and this role, which is a question the
-- caller has already asked `playbook_candidates` and is not asking here.
CREATE FUNCTION playbook_near_misses(
        p_program uuid, p_subject uuid, p_max_missing integer DEFAULT 1)
RETURNS TABLE (playbook_id uuid, path text, missing_count integer,
               missing_facts text[])
LANGUAGE sql STABLE AS $$
    WITH f AS (SELECT fact FROM subject_facts
                WHERE program_id = p_program AND subject_entity_id = p_subject),
    short AS (
        SELECT p.id, p.path,
               coalesce((SELECT array_agg(t.fact ORDER BY t.fact)
                           FROM playbook_triggers t
                          WHERE t.playbook_id = p.id AND t.mode = 'all'
                            AND NOT EXISTS (SELECT 1 FROM f WHERE f.fact = t.fact)),
                        '{}'::text[]) AS lacks_all,
               CASE WHEN NOT EXISTS (SELECT 1 FROM playbook_triggers t
                                      WHERE t.playbook_id = p.id AND t.mode = 'any')
                      OR EXISTS (SELECT 1 FROM playbook_triggers t JOIN f ON f.fact = t.fact
                                  WHERE t.playbook_id = p.id AND t.mode = 'any')
                    THEN '{}'::text[]
                    ELSE coalesce((SELECT array_agg(t.fact ORDER BY t.fact)
                                     FROM playbook_triggers t
                                    WHERE t.playbook_id = p.id AND t.mode = 'any'),
                                  '{}'::text[])
               END AS lacks_any
          FROM playbooks p
         WHERE p.status <> 'deprecated'
    ),
    counted AS (
        SELECT s.id, s.path,
               (cardinality(s.lacks_all)
                + CASE WHEN cardinality(s.lacks_any) > 0 THEN 1 ELSE 0 END)::int AS n,
               s.lacks_all || s.lacks_any AS facts
          FROM short s
    )
    SELECT c.id, c.path, c.n, c.facts
      FROM counted c
     WHERE c.n BETWEEN 1 AND greatest(p_max_missing, 1)
     ORDER BY c.n, c.path;
$$;

COMMENT ON FUNCTION playbook_near_misses(uuid, uuid, integer) IS
    'Ticket 164: the Playbooks this subject nearly matched, and the facts it '
    'would have had to carry. Missing is counted the way playbooks_by_trigger '
    'decides -- every unheld `all` fact, plus one for an unsatisfied `any` '
    'group -- so a Playbook this returns with a count of zero would be a '
    'Playbook that function should have admitted. Deprecated Playbooks are '
    'left out: no fact makes one of those selectable.';

REVOKE ALL ON FUNCTION playbook_near_misses(uuid, uuid, integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION playbook_near_misses(uuid, uuid, integer)
    TO rk2_runtime, rk2_human;

INSERT INTO runtime_verb_surface (verb, added_by, note) VALUES
    ('playbook_near_misses(uuid, uuid, integer)', '164',
     'the sentence `execution._playbooks` prints when the selection kept nothing, so "nothing in the corpus is about this subject" names the Playbooks it nearly was');


-- ===========================================================================
-- 3. Draft is selectable, and the column says so
-- ===========================================================================
--
-- An operator reading "0 selections, 50 drafts" reaches for this first, and it
-- is not the cause. 045 admitted `draft` deliberately and said why in a comment
-- on a migration nobody reads at three in the morning; PH2-64 narrowed the
-- exclusion to a Playbook edited after it was graded and left the rest. The
-- rule has never been written on the column itself, so the column carries it
-- now: `stable` is unreachable until a fixture pair has run against the exact
-- text, so a funnel that excluded drafts would exclude the whole catalogue.
COMMENT ON COLUMN playbooks.status IS
    'draft until a fixture pair has been run against this exact text, stable '
    'once it has, deprecated when it is retired. Selection excludes only '
    'deprecated: draft is selectable and merely sorts behind stable, because '
    'every Playbook this corpus ships is draft and a funnel that dropped them '
    'would select nothing. A Playbook edited after it was graded is dropped by '
    'playbook_candidates on the ledger rather than on this column.';


-- ===========================================================================
-- 4. What would have to be true
-- ===========================================================================

DO $$
DECLARE n integer;
BEGIN
    -- Section 1's own claim, asked of the catalogue rather than of the text:
    -- every registered surface fact still has a branch that computes it. 032
    -- and 045 ask this after every rebuild of the view and the rebuild above is
    -- the largest one this corpus has had.
    SELECT count(*) INTO n FROM surface_facts f
     WHERE position(('''' || f.id || '''') IN pg_get_viewdef('subject_facts'::regclass)) = 0
       AND position((f.id) IN pg_get_viewdef('subject_facts'::regclass)) = 0;
    IF n > 0 THEN
        RAISE EXCEPTION '164 left % registered surface fact(s) with no branch', n;
    END IF;

    -- And the direction the rebuild could break silently: a subject that is an
    -- Application must be able to appear. Asked as "is there a branch keyed on
    -- something other than the Endpoint", which is what `subj` is.
    IF position('subj' IN pg_get_viewdef('subject_facts'::regclass)) = 0 THEN
        RAISE EXCEPTION '164 rebuilt subject_facts without the Application key';
    END IF;

    -- Section 2 against the corpus as it stands: a near miss is a real number
    -- and not a function that returns nothing whatever it is asked. Every
    -- Playbook has at least one trigger -- 032's own constraint -- so a subject
    -- with no facts at all is short by at least one on every one of them, and
    -- a cap of fifty must therefore return the whole catalogue.
    SELECT count(*) INTO n
      FROM playbook_near_misses('00000000-0000-0000-0000-000000000000'::uuid,
                                '00000000-0000-0000-0000-000000000000'::uuid, 50);
    IF n <> (SELECT count(*) FROM playbooks WHERE status <> 'deprecated') THEN
        RAISE EXCEPTION
            '164 near-miss over an empty subject returned % of % playbook(s)',
            n, (SELECT count(*) FROM playbooks WHERE status <> 'deprecated');
    END IF;
END $$;
