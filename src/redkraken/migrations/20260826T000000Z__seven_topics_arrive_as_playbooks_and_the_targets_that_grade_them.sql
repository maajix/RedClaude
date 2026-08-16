-- ---------------------------------------------------------------------------
-- 20260826T000000Z__seven_topics_arrive_as_playbooks_and_the_targets_that_grade_them.sql
--                                                                   (ticket 49)
--
-- Ticket 49 migrates the v1 recon, API and protocol topics -- agentic-ai, api,
-- attack-surface, graphql, grpc, realtime, webhooks -- into authored v2
-- Playbooks, and gives each of them a positive fixture. The corpus is the
-- statement; this file is the database's copy of it, existing so the copy can
-- be checked rather than trusted.
--
-- Four things happen, and the first three are vocabulary rather than corpus.
--
--   1. Two surface facts, `tech_grpc` and `tech_llm`, and the branch of
--      `subject_facts` that computes each. A registered fact with no branch is
--      a hard `check_playbook_integrity` error, and it has to be spelled out
--      literally: that rule reads the view's own definition text, which 032
--      records after all five `tech_` atoms were falsely reported by a version
--      that built the name by concatenation.
--
--   2. One Property class, `injection.model_instruction`. The injection family
--      splits by the interpreter -- 018 says so in the comment above its own
--      leaves, "because the interpreter is the test" -- and a language model is
--      an interpreter with no grammar. Filing it under `injection.template`
--      would have hidden the one property that makes it hard to test: the same
--      input does not produce the same output.
--
--   3. Nothing is added to `property_class_vulnerability_classes` for it. That
--      table is advisory and 034 seeded it "for the leaves whose expected
--      outcome is actually determinate"; a leaf with no row asks no question,
--      and inventing a CWE for this one would be answering a question ticket 19
--      did not ask.
--
--   4. The seven Playbooks and the seven fixtures, as rows. Every Playbook is
--      `draft`: `playbooks_stable_is_promoted` and 036's promotion guard make
--      `stable` unreachable until the evaluator has run the exact text against
--      the fixture catalogue, and no evaluation has happened yet. Draft is the
--      honest state and selection admits it -- only `deprecated` is excluded.
--
-- A new file rather than an edit to 045 or 046: a recorded migration whose file
-- has changed is schema drift and `rk db migrate` refuses the whole corpus for
-- it.
-- ---------------------------------------------------------------------------


-- ===========================================================================
-- 1. Two facts, and the branches that compute them
-- ===========================================================================

-- Both are application-scoped technology observations, the same shape as the
-- five 032 registered: `technology_identified` is non-evidential, it settles
-- nothing on its own, and what it does is decide which Playbooks are selectable
-- against a subject. That is exactly the weight a stack banner should carry.
INSERT INTO surface_facts (id, scope, description) VALUES
 ('tech_grpc','application','a gRPC or gRPC-Web service was identified'),
 ('tech_llm','application','the application was identified as passing input to a language model')
ON CONFLICT (id) DO NOTHING;

-- The view, restated whole because `CREATE OR REPLACE VIEW` has no way to add
-- a branch to a UNION without restating the rest. Only the technology CASE has
-- changed: two `WHEN` arms and two names in the `IN` list beneath it. Every
-- other branch is 032's, verbatim, and the column list is unchanged so the
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
UNION ALL SELECT DISTINCT ep.program_id, ep.entity_id, 'redirect_target'
  FROM ep JOIN relationships r ON r.src_entity_id = ep.entity_id AND r.type = 'redirects_to'
-- application shape
UNION ALL SELECT ep.program_id, ep.entity_id,
       CASE a.kind WHEN 'graphql' THEN 'graphql_surface' WHEN 'spa' THEN 'spa_surface'
                   WHEN 'api' THEN 'api_surface' ELSE 'websocket_surface' END
  FROM ep JOIN applications a ON a.entity_id = ep.application_id
 WHERE a.kind IN ('graphql','spa','api','websocket')
-- Spelled out rather than 'tech_' || lower(t.name).  check_playbook_integrity's
-- fact_not_computed rule reads the view definition looking for the atom's name,
-- and a name assembled by concatenation is invisible to it: all five tech_ atoms
-- were reported as uncomputed while the view was computing them correctly.  The
-- rule is right to be textual (it must catch an atom no branch produces), so the
-- view is what changes.
UNION ALL SELECT DISTINCT ep.program_id, ep.entity_id,
       CASE lower(t.name) WHEN 'jwt'     THEN 'tech_jwt'
                          WHEN 'oauth'   THEN 'tech_oauth'
                          WHEN 'saml'    THEN 'tech_saml'
                          WHEN 'soap'    THEN 'tech_soap'
                          WHEN 'graphql' THEN 'tech_graphql'
                          WHEN 'grpc'    THEN 'tech_grpc'
                          WHEN 'llm'     THEN 'tech_llm' END
  FROM ep JOIN relationships r ON r.src_entity_id = ep.application_id AND r.type = 'runs'
          JOIN technologies t ON t.entity_id = r.dst_entity_id
 WHERE lower(t.name) IN ('jwt','oauth','saml','soap','graphql','grpc','llm')
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
-- 2. One Property class
-- ===========================================================================

-- The leaf answers "what test would settle this", which is 018's rule for the
-- whole vocabulary. Here the answer is: plant an instruction in the channel
-- under test, plant the same instruction where the pipeline cannot carry it,
-- and difference the two sets of answers. That test does not settle any other
-- injection leaf and no other injection leaf's test settles this one, which is
-- what makes it a leaf rather than a note under `injection.template`.
INSERT INTO property_classes (id, family_id, name, description) VALUES
 ('injection.model_instruction','injection','Model instruction injection',
  'input reaches a language model as instructions it then acts on')
ON CONFLICT (id) DO NOTHING;


-- ===========================================================================
-- 3. Seven Playbooks, as rows
-- ===========================================================================

-- `version` is the digest of the projection -- what the model is handed --
-- beside `source_sha256`, which is the document. Editing a maintainer reference
-- moves neither; editing the review date moves the document and not the
-- projection; editing the body moves both.
--
-- Two of the seven are not `constrained`. `api` is `approval_required` because
-- its method is to spend a declared sequence of requests rather than to send a
-- handful and read the difference, and that is the activity a Program's rules
-- of engagement bound. `webhooks` is `approval_required` and `mutates_object`
-- because its trigger is `state_changing_method` and it registers something on
-- the target: RISK_FLOOR admits nothing lower for that effect, and a Playbook
-- that called itself `read_only` there would be describing its intention rather
-- than its requests.
INSERT INTO playbooks (path, source_sha256, version, category, status, stale_after,
                       risk, effects, baseline, specificity, provenance) VALUES
 ('playbooks/agentic-ai/playbook.md',
  'f4ad285994a5cb10fa5d665fef48fb29eb4b12513880576bdec54b8d94ca4f80',
  '813143285c97ad8825870626850ddcf0561bd64c2d3ce09309edcd4fa96a3b51',
  'injection', 'draft', '2027-02-15T00:00:00Z',
  'constrained', 'read_only', 'none', 1,
  'Written for ticket 49 as the v2 replacement for v1''s agentic-ai pack; the class it outputs is new in this ticket, because no injection leaf in the ticket 18 vocabulary named a language model as the interpreter.'),
 ('playbooks/api/playbook.md',
  'c192888cab13e86275fd2fe0f369e1db34caf3e3cd321dfd8bd92ac961e326a4',
  'b3e1607d771185c6ea4d7ea87ffdd637520156d0e36eef82600a69a1ced9c753',
  'rate_limiting', 'draft', '2027-02-15T00:00:00Z',
  'approval_required', 'read_only', 'stable_session', 2,
  'Written for ticket 49 as the v2 replacement for v1''s api pack, against the per-identity leaf of the ticket 18 vocabulary; the rate-limit-bypass text is the only one of the three v1 files that named a defect, and this is the class it named.'),
 ('playbooks/attack-surface/playbook.md',
  '8a2ab26e9fcc4216408a307a018dba528bc3518e8386330d3ac717294370c9ef',
  'b06e188624e1a78239d772a09d37b11adb82a74f43cb41eed294885f36f39056',
  'information_disclosure', 'draft', '2027-02-15T00:00:00Z',
  'constrained', 'read_only', 'none', 2,
  'Written for ticket 49 as the v2 replacement for v1''s attack-surface pack, against the artifact-exposure leaf of the ticket 18 vocabulary; the three v1 texts are attached as maintainer references and none of them is the source of this class.'),
 ('playbooks/graphql/playbook.md',
  '82323cce723057e5c672f7ce7adc699b5b43ab97fd5defda012b6ba64e89516c',
  'e30e220ea7dc8e657732683f0632d80f2337641c60679d8af15ef99d7056803a',
  'information_disclosure', 'draft', '2027-02-15T00:00:00Z',
  'constrained', 'read_only', 'stable_session', 2,
  'Written for ticket 49 as the v2 replacement for v1''s graphql pack, against the excess-field leaf of the ticket 18 vocabulary; the v1 api-graphql text is attached as a maintainer reference and is not the source of this class.'),
 ('playbooks/grpc/playbook.md',
  '0767a0c15b33b7e957a193a41d9e0fcb8f71ed0281515213c1c87862b9a6fa57',
  '10f65565bd4e88a89d96c79a82d54b014726d1ddfb35719314fde9baa296e418',
  'authorization', 'draft', '2027-02-15T00:00:00Z',
  'constrained', 'read_only', 'stable_session', 2,
  'Written for ticket 49 as the v2 replacement for v1''s grpc pack, against the function-access leaf of the ticket 18 vocabulary; v1 shipped a README for this topic and no reference text, so nothing is attached.'),
 ('playbooks/realtime/playbook.md',
  '631533297beff08d564ccb93b0a72269987733e2931e71d1f2712a1bbe764227',
  '4c2c715592b875583b1c9466f527578795e83dd9200c4e6bb10581b443fe4c1c',
  'session_handling', 'draft', '2027-02-15T00:00:00Z',
  'constrained', 'read_only', 'stable_session', 2,
  'Written for ticket 49 as the v2 replacement for v1''s realtime pack, against the csrf leaf of the ticket 18 vocabulary; v1 shipped a README for this topic and no reference text, so nothing is attached.'),
 ('playbooks/webhooks/playbook.md',
  '0488c50279c0679588cc0671020a8e1e5cff372468fd180157d8b399d698877c',
  '3745dd926b01f67144f1f38abea3e398e8543a39949f8697373cdce4fc24e674',
  'injection', 'draft', '2027-02-15T00:00:00Z',
  'approval_required', 'mutates_object', 'none', 2,
  'Written for ticket 49 as the v2 replacement for v1''s webhooks pack, against the request-forgery leaf of the ticket 18 vocabulary; v1 shipped a README for this topic and no reference text, so nothing is attached.')
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
-- `specificity_disagrees` is the database recomputing it. `agentic-ai` is the
-- one with a single required fact and three optional ones: a language model
-- behind an endpoint is the whole precondition, and which parameter carries the
-- text into it is a disjunction rather than a second requirement.
INSERT INTO playbook_triggers (playbook_id, mode, fact)
SELECT p.id, v.mode, v.fact
  FROM playbooks p, (VALUES
        ('playbooks/agentic-ai/playbook.md',     'all', 'tech_llm'),
        ('playbooks/agentic-ai/playbook.md',     'any', 'body_parameter'),
        ('playbooks/agentic-ai/playbook.md',     'any', 'query_parameter'),
        ('playbooks/agentic-ai/playbook.md',     'any', 'reflected_parameter'),
        ('playbooks/api/playbook.md',            'all', 'api_surface'),
        ('playbooks/api/playbook.md',            'all', 'multiple_test_identities'),
        ('playbooks/attack-surface/playbook.md', 'all', 'read_method'),
        ('playbooks/attack-surface/playbook.md', 'all', 'unauthenticated_endpoint'),
        ('playbooks/graphql/playbook.md',        'all', 'graphql_surface'),
        ('playbooks/graphql/playbook.md',        'all', 'multiple_test_identities'),
        ('playbooks/grpc/playbook.md',           'all', 'multiple_test_identities'),
        ('playbooks/grpc/playbook.md',           'all', 'tech_grpc'),
        ('playbooks/realtime/playbook.md',       'all', 'authenticated_endpoint'),
        ('playbooks/realtime/playbook.md',       'all', 'websocket_surface'),
        ('playbooks/webhooks/playbook.md',       'all', 'state_changing_method'),
        ('playbooks/webhooks/playbook.md',       'all', 'url_valued_parameter'))
        AS v(path, mode, fact)
 WHERE p.path = v.path
ON CONFLICT (playbook_id, mode, fact) DO NOTHING;

-- One class each, and each inside the Playbook's own family -- which is what
-- `output_outside_category` reports and what the compiler already refuses. A
-- Playbook claiming a second family would be two Playbooks sharing a document,
-- and the fixture binding could not say which of them a result was about.
INSERT INTO playbook_outputs (playbook_id, property_class)
SELECT p.id, v.property_class
  FROM playbooks p, (VALUES
        ('playbooks/agentic-ai/playbook.md',     'injection.model_instruction'),
        ('playbooks/api/playbook.md',            'rate_limiting.per_identity'),
        ('playbooks/attack-surface/playbook.md', 'information_disclosure.artifact_exposure'),
        ('playbooks/graphql/playbook.md',        'information_disclosure.excess_field'),
        ('playbooks/grpc/playbook.md',           'authorization.function_access'),
        ('playbooks/realtime/playbook.md',       'session_handling.csrf'),
        ('playbooks/webhooks/playbook.md',       'injection.request_forgery'))
        AS v(path, property_class)
 WHERE p.path = v.path
ON CONFLICT (playbook_id, property_class) DO NOTHING;

-- `skill_sha256_at_promotion` stays NULL on every row: nothing here has been
-- promoted, and a promotion hash written at ingest would be a drift baseline
-- taken at a moment no promotion happened.
--
-- Each set is loadable by exactly one production role, which is criterion 5's
-- first half and a hard `playbook_unloadable` error otherwise. `attack-surface`
-- is the recon one and it is the reason its steps name no differencing Skill:
-- recon does not carry `compare-responses`, so a step that told the model to
-- run it would be a step pointing at a file that role cannot open.
INSERT INTO playbook_skills (playbook_id, skill_name)
SELECT p.id, v.skill_name
  FROM playbooks p, (VALUES
        ('playbooks/agentic-ai/playbook.md',     'compare-responses'),
        ('playbooks/agentic-ai/playbook.md',     'handle-untrusted-content'),
        ('playbooks/api/playbook.md',            'compare-responses'),
        ('playbooks/api/playbook.md',            'use-identity'),
        ('playbooks/attack-surface/playbook.md', 'enumerate-surface'),
        ('playbooks/attack-surface/playbook.md', 'handle-untrusted-content'),
        ('playbooks/graphql/playbook.md',        'compare-responses'),
        ('playbooks/graphql/playbook.md',        'use-identity'),
        ('playbooks/grpc/playbook.md',           'compare-responses'),
        ('playbooks/grpc/playbook.md',           'use-identity'),
        ('playbooks/realtime/playbook.md',       'browser-evidence'),
        ('playbooks/realtime/playbook.md',       'compare-responses'),
        ('playbooks/webhooks/playbook.md',       'compare-responses'),
        ('playbooks/webhooks/playbook.md',       'handle-untrusted-content'))
        AS v(path, skill_name)
 WHERE p.path = v.path
ON CONFLICT (playbook_id, skill_name) DO NOTHING;

-- Three rows each: what refutes, what the control has to show, and what the
-- claim itself rests on.
--
-- Two of them invert the usual shape, and deliberately. For `api` and
-- `realtime` the supported evidence is `response_invariant`: a sequence that
-- was never counted and a handshake that was answered the same way from any
-- origin are both findings whose signal is that nothing changed. Their
-- `refuted` row is the differential, which is the limit engaging and the origin
-- check working.
--
-- `webhooks` requires `callback_interaction` for a supported claim, and that
-- kind is backed by `{callback}` provenance alone. The consequence is stated
-- rather than worked around: this Playbook cannot reach `supported` against a
-- fixture, because a loopback evaluator has no callback channel to register.
-- The alternative was to accept a response differential as proof that a request
-- was made, which is the shape of the classic invalid SSRF report.
--
-- `attack-surface` requires `content_match`, backed by `{tool_run}` alone, so
-- its identification step runs through a registered tool rather than a reading.
-- Today that means `jq` over the stored Artifact, which the fixture's source map
-- and any other JSON satisfy; an Artifact `jq` cannot parse has no tool behind
-- it and ends inconclusive. The Playbook body states that limit instead of
-- leaving a model to improvise past it.
INSERT INTO playbook_evidence
        (playbook_id, to_status, role, observation_kind, polarity, min_count)
SELECT p.id, v.to_status, v.role, v.kind, v.polarity, v.min_count
  FROM playbooks p, (VALUES
        ('playbooks/agentic-ai/playbook.md',     'refuted',   'variant', 'response_invariant',    'refutes',  1),
        ('playbooks/agentic-ai/playbook.md',     'supported', 'control', 'response_invariant',    'supports', 1),
        ('playbooks/agentic-ai/playbook.md',     'supported', 'variant', 'response_differential', 'supports', 1),
        ('playbooks/api/playbook.md',            'refuted',   'variant', 'response_differential', 'refutes',  1),
        ('playbooks/api/playbook.md',            'supported', 'control', 'credential_effect',     'supports', 1),
        ('playbooks/api/playbook.md',            'supported', 'variant', 'response_invariant',    'supports', 1),
        ('playbooks/attack-surface/playbook.md', 'refuted',   'variant', 'response_invariant',    'refutes',  1),
        ('playbooks/attack-surface/playbook.md', 'supported', 'control', 'response_differential', 'supports', 1),
        ('playbooks/attack-surface/playbook.md', 'supported', 'variant', 'content_match',         'supports', 1),
        ('playbooks/graphql/playbook.md',        'refuted',   'variant', 'response_invariant',    'refutes',  1),
        ('playbooks/graphql/playbook.md',        'supported', 'control', 'credential_effect',     'supports', 1),
        ('playbooks/graphql/playbook.md',        'supported', 'variant', 'response_differential', 'supports', 1),
        ('playbooks/grpc/playbook.md',           'refuted',   'variant', 'response_invariant',    'refutes',  1),
        ('playbooks/grpc/playbook.md',           'supported', 'control', 'credential_effect',     'supports', 1),
        ('playbooks/grpc/playbook.md',           'supported', 'variant', 'response_differential', 'supports', 1),
        ('playbooks/realtime/playbook.md',       'refuted',   'variant', 'response_differential', 'refutes',  1),
        ('playbooks/realtime/playbook.md',       'supported', 'control', 'credential_effect',     'supports', 1),
        ('playbooks/realtime/playbook.md',       'supported', 'variant', 'response_invariant',    'supports', 1),
        ('playbooks/webhooks/playbook.md',       'refuted',   'variant', 'response_invariant',    'refutes',  1),
        ('playbooks/webhooks/playbook.md',       'supported', 'control', 'response_differential', 'supports', 1),
        ('playbooks/webhooks/playbook.md',       'supported', 'variant', 'callback_interaction',  'supports', 1))
        AS v(path, to_status, role, kind, polarity, min_count)
 WHERE p.path = v.path
ON CONFLICT (playbook_id, to_status, role, observation_kind) DO NOTHING;

-- The material the model never gets. Eight files behind four Playbooks; the
-- other three topics shipped a README in v1 and no reference text, so they have
-- nothing attached rather than a placeholder. Recorded so a maintainer can find
-- them and hashed so a maintainer can tell whether they moved.
INSERT INTO playbook_references (playbook_id, name, path, sha256)
SELECT p.id, v.name, v.path, v.sha256
  FROM playbooks p, (VALUES
        ('playbooks/agentic-ai/playbook.md', 'llm.md',
         'playbooks/agentic-ai/references/llm.md',
         '3606dcbe4d44b4e1c87936c6c6cbee7a5c052e0e1ce6abb504399914a5fcd50f'),
        ('playbooks/api/playbook.md', 'api-soap.md',
         'playbooks/api/references/api-soap.md',
         'f72877212b5cc4968a0122a447ed44f129652ab4d181f2c47c404967756d59a4'),
        ('playbooks/api/playbook.md', 'api.md',
         'playbooks/api/references/api.md',
         '1c3308fe5728f2cc498a21731100a5855b06a2c54489bc92d0c75087e095e635'),
        ('playbooks/api/playbook.md', 'rate-limit-bypass.md',
         'playbooks/api/references/rate-limit-bypass.md',
         '7774a7768806695aa77f6ed670faebac494c13eeb225393139b8837ad93b9e73'),
        ('playbooks/attack-surface/playbook.md', 'auto-scanners.md',
         'playbooks/attack-surface/references/auto-scanners.md',
         'bec1c74068b45130ce4e0991d899c6f7ab2c0e288e80a6a84c6519575c5e9a12'),
        ('playbooks/attack-surface/playbook.md', 'cves.md',
         'playbooks/attack-surface/references/cves.md',
         'b5f2c3cdc19336ef14db435341bfcf314da5461b39d3d9a927a466b8baaf39e6'),
        ('playbooks/attack-surface/playbook.md', 'ffuf.md',
         'playbooks/attack-surface/references/ffuf.md',
         '323f5b0e6b4c59e2e28f3f1824f04af8083d608989916b3553ef4063c0846d6f'),
        ('playbooks/graphql/playbook.md', 'api-graphql.md',
         'playbooks/graphql/references/api-graphql.md',
         '6065d2b5f144a1d3fb8086deb9f723f9615d2b76df3d2dc9346d5a9d0ee85d4f'))
        AS v(playbook_path, name, path, sha256)
 WHERE p.path = v.playbook_path
ON CONFLICT (playbook_id, name) DO NOTHING;


-- ===========================================================================
-- 4. Seven targets, as rows
-- ===========================================================================

-- One positive per topic, each written from the class description rather than
-- from the Playbook's steps. `playbook_fixture_binding()` is total over this
-- table, so every one of these is also an out-of-class negative for the other
-- eight Playbooks -- which is the second half of criterion 4 and the reason
-- nothing here declares a class it does not hold. Under-declaring moves a
-- fixture onto the `out` side and makes a Playbook that fires on it fail, which
-- is the direction that mistake should push.
--
-- Two of them deviate from what they model, and both say so in their own ground
-- truth. `request-forgery-pair` resolves the verification request against a
-- dict rather than opening a socket, because a fixture that really made
-- outbound requests would send traffic wherever a test pointed it.
-- `function-access-pair` speaks JSON over HTTP/1.1 with `grpc-status` as a
-- header, which is what a Trailers-Only response looks like, because what the
-- Playbook reads is the trailer value and not the wire codec.
INSERT INTO fixtures (id, kind, path, source_sha256, ground_truth_sha256) VALUES
 ('artifact-exposure-pair', 'own_pair',
  'fixtures/artifact-exposure-pair/fixture.md',
  '0151da8f83c10a8c70a2ded4fef5104cd02e09f72ddc13a6cb3310a0ebcfe2e7',
  '0c9e8edc22cc43c2f47295ab6f5dfb2afde3ad2cc5868182abc69618e796147a'),
 ('excess-field-pair', 'own_pair',
  'fixtures/excess-field-pair/fixture.md',
  'ac44f8146813e53655a614aef204e2de9d502a6299a612145367ec0dd240b0a5',
  '674a9222be0e724efc4a8dc3bf6416e477912ea7a45c25a2b377fc4ca9d28037'),
 ('function-access-pair', 'own_pair',
  'fixtures/function-access-pair/fixture.md',
  '6c121382d931f129d1140e89458ff55ee60b89d4fcd2849fb602105fae8876c6',
  '922bb581a1e88f1759c1cc75324ef80e559b140aaa9a472b7a7caeed424503ed'),
 ('model-instruction-pair', 'own_pair',
  'fixtures/model-instruction-pair/fixture.md',
  '40c9032fa0f8a2c6bb72c6045376c7e0cc57367e113eb30fc6b9b32efe8e75d8',
  'dc932e843318984dc5a637fc360c94e39e9bbbb073b6306548251b3fa5609ea0'),
 ('per-identity-limit-pair', 'own_pair',
  'fixtures/per-identity-limit-pair/fixture.md',
  '243a02431d7d4d1399d2f40cb48a561d08dc4a647758da818a8156d49655f9e2',
  'd29538c019bf209e5f01eb209a640c4317c412c6dd23e60de498d959ac0c0a69'),
 ('request-forgery-pair', 'own_pair',
  'fixtures/request-forgery-pair/fixture.md',
  '23c977877f42b7b3986ffe72d1540a5cf7fe9e2cd32306442dbbb9c7a5aaa49c',
  'c8c48bd1bd1bccf225f43971b661a64ebe2331fdd7033a2962be96e0df7b595b'),
 ('websocket-csrf-pair', 'own_pair',
  'fixtures/websocket-csrf-pair/fixture.md',
  'ecec46230ea9032f1ff9a6d96b0f9741a4824d88f5ae5ebce9c7e00d8d3c1e1a',
  '04d8a490e63fb9077a0d4c5f747c0dba197b6b47a29734226126c27976379070')
ON CONFLICT (id) DO UPDATE SET
    kind                = excluded.kind,
    path                = excluded.path,
    source_sha256       = excluded.source_sha256,
    ground_truth_sha256 = excluded.ground_truth_sha256;

-- One class each. A fixture carrying two would be two fixtures under one name,
-- and a run against it could not say which one a claim was right about.
INSERT INTO fixture_classes (fixture_id, property_class) VALUES
 ('artifact-exposure-pair',  'information_disclosure.artifact_exposure'),
 ('excess-field-pair',       'information_disclosure.excess_field'),
 ('function-access-pair',    'authorization.function_access'),
 ('model-instruction-pair',  'injection.model_instruction'),
 ('per-identity-limit-pair', 'rate_limiting.per_identity'),
 ('request-forgery-pair',    'injection.request_forgery'),
 ('websocket-csrf-pair',     'session_handling.csrf')
ON CONFLICT (fixture_id, property_class) DO NOTHING;
