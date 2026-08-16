-- ---------------------------------------------------------------------------
-- 20260827T000000Z__eight_identity_topics_arrive_as_playbooks_and_the_targets_that_grade_them.sql
--                                                                   (ticket 50)
--
-- Ticket 50 migrates the v1 authentication and identity topics -- authentication,
-- cookies, identity-lifecycle, identity-parsing, jwt-jose, oauth, webauthn,
-- workload-identities -- into authored v2 Playbooks, and gives each of them a
-- positive fixture. The corpus is the statement; this file is the database's
-- copy of it, existing so the copy can be checked rather than trusted. Same
-- shape as 049, one ticket later.
--
-- Three things happen.
--
--   1. One surface fact, `tech_webauthn`, and the branch of `subject_facts`
--      that computes it. Spelled out literally for 049's reason: the
--      `fact_not_computed` rule reads the view's own definition text, and a
--      name assembled by concatenation is invisible to it.
--
--   2. No new Property classes. All eight leaves these Playbooks output are
--      018's, which is the point of migrating against a vocabulary rather than
--      beside one: `credential_verification`, `factor_enforcement`,
--      `federation_trust`, `cookie_scope`, `lifetime`, `fixation`,
--      `token_scope` and `tenant_isolation` were all named there, and this
--      ticket is the first to have documents that ask for them.
--
--   3. The eight Playbooks and the eight fixtures, as rows. Every Playbook is
--      `draft` for 049's reason: `playbooks_stable_is_promoted` and 036's
--      promotion guard make `stable` unreachable until the evaluator has run
--      the exact text against the fixture catalogue, and no evaluation has
--      happened yet.
--
-- A new file rather than an edit to 049: a recorded migration whose file has
-- changed is schema drift and `rk db migrate` refuses the whole corpus for it.
-- ---------------------------------------------------------------------------


-- ===========================================================================
-- 1. One fact, and the branch that computes it
-- ===========================================================================

-- Application-scoped, the same shape as the seven `tech_` atoms before it. What
-- it says is that a step-up flow exists to read, which is the precondition the
-- `webauthn` Playbook needs and not evidence of anything on its own.
INSERT INTO surface_facts (id, scope, description) VALUES
 ('tech_webauthn','application','a WebAuthn or step-up authentication flow was identified')
ON CONFLICT (id) DO NOTHING;

-- The view, restated whole because `CREATE OR REPLACE VIEW` has no way to add a
-- branch to a UNION without restating the rest. Only the technology branch has
-- changed: `webauthn` is added to it, and the branch itself becomes a join over
-- a table of pairs instead of a CASE plus a matching `IN` list. Every other
-- branch is 049's, verbatim, and the column list is unchanged so the
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
-- Spelled out rather than 'tech_' || lower(t.name), for the reason 049 gives at
-- this same branch: `check_playbook_integrity`'s fact_not_computed rule reads
-- the view definition looking for the atom's name, and a name built by
-- concatenation is invisible to it.
--
-- 049 wrote this as a CASE with a matching IN list beneath it, which spelled
-- every technology twice and made adding one a two-line edit where one line
-- silently does nothing. The pairs are a join table here instead: each name and
-- each atom appears exactly once, the join is what restricts the rows, and the
-- literals are still in the view's definition text where the rule reads them.
-- Tickets 51 to 56 add their technologies as one row each.
UNION ALL SELECT DISTINCT ep.program_id, ep.entity_id, known.fact
  FROM ep JOIN relationships r ON r.src_entity_id = ep.application_id AND r.type = 'runs'
          JOIN technologies t ON t.entity_id = r.dst_entity_id
          JOIN (VALUES ('jwt',      'tech_jwt'),
                       ('oauth',    'tech_oauth'),
                       ('saml',     'tech_saml'),
                       ('soap',     'tech_soap'),
                       ('graphql',  'tech_graphql'),
                       ('grpc',     'tech_grpc'),
                       ('llm',      'tech_llm'),
                       ('webauthn', 'tech_webauthn')) AS known(name, fact)
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
-- 2. Eight Playbooks, as rows
-- ===========================================================================

-- `version` is the digest of the projection -- what the model is handed --
-- beside `source_sha256`, which is the document.
--
-- Three of the eight are not `constrained`, and each for a reason the risk floor
-- would enforce anyway. `identity-parsing` and `oauth` are `approval_required`
-- because both drive a flow whose other end is an identity provider the Program
-- did not authorise: one honest login there, and everything after it works from
-- material already held. `webauthn` is `approval_required` and `mutates_account`
-- because a successful variant changes something on an account -- a recovery
-- address, an enrolled authenticator -- and RISK_FLOOR admits nothing lower for
-- that effect.
--
-- `jwt-jose` and `workload-identities` are `read_only` on purpose. Both are
-- questions about which caller a route answers, and neither needs a write to
-- settle one; a write into a second tenant would be damage rather than evidence.
INSERT INTO playbooks (path, source_sha256, version, category, status, stale_after,
                       risk, effects, baseline, specificity, provenance) VALUES
 ('playbooks/authentication/playbook.md',
  '672be5520107fc3c27208d0f7cb0e90ae9ca8dc3c9374a9b94489549dc573085',
  '618e9fe7d2211c45d13ee53c127dbc1393af30e2aba7f3977cdee545f0f80f77',
  'authentication', 'draft', '2027-03-15T00:00:00Z',
  'constrained', 'mutates_session', 'none', 2,
  'Written for ticket 50 as the v2 replacement for v1''s authentication pack, against the credential-verification leaf of the ticket 18 vocabulary; four v1 texts are attached as maintainer references and the type-juggling one is the only one that named this defect.'),
 ('playbooks/cookies/playbook.md',
  '82989ea85adcef5215cf5c51c7821ecfdccf1fe86670f5dfbb2fa0ab784313fc',
  'a1e83aad3901f34c7886f042dd4f8fc2a8585fb0d36fdc179ee165ddcad6fdc5',
  'session_handling', 'draft', '2027-03-15T00:00:00Z',
  'constrained', 'read_only', 'stable_session', 2,
  'Written for ticket 50 as the v2 replacement for v1''s cookies pack, against the cookie-scope leaf of the ticket 18 vocabulary; v1 shipped a README for this topic and no reference text, so nothing is attached.'),
 ('playbooks/identity-lifecycle/playbook.md',
  '8d5728df82ee37d25af597d316f68e1f5f9fe13df02f05268b3198a22d42acf8',
  '12a83bea89ab48f45d919e96f4e87e494c0f8d790a4a5912b7e1779493e0015d',
  'session_handling', 'draft', '2027-03-15T00:00:00Z',
  'constrained', 'mutates_session', 'stable_session', 2,
  'Written for ticket 50 as the v2 replacement for v1''s identity-lifecycle pack, against the session-lifetime leaf of the ticket 18 vocabulary; v1 shipped a README for this topic and no reference text, so nothing is attached.'),
 ('playbooks/identity-parsing/playbook.md',
  '97b512dbfd7d99bc85bef5fd634cb2bee127619a1029dc60942e2c9ac8cad9a7',
  '4cfb89d49f800c002e10604eb33045f265fcadf78118a11ff0585898803eee08',
  'authentication', 'draft', '2027-03-15T00:00:00Z',
  'approval_required', 'mutates_session', 'none', 2,
  'Written for ticket 50 as the v2 replacement for v1''s identity-parsing pack, against the federation-trust leaf of the ticket 18 vocabulary; the v1 saml text is attached as a maintainer reference and is the source of the wrapping technique this Playbook uses.'),
 ('playbooks/jwt-jose/playbook.md',
  '909a6534b74ef05592838ec921f1649ab1e550f1a85fb5f683b57218261a72c2',
  'f1886d761ed1500108c328d1199863ec1ba7264d5e0358d62353f9b14b66147e',
  'authorization', 'draft', '2027-03-15T00:00:00Z',
  'constrained', 'read_only', 'stable_session', 2,
  'Written for ticket 50 as the v2 replacement for v1''s jwt-jose pack, against the token-scope leaf of the ticket 18 vocabulary; the v1 jwt text is attached as a maintainer reference and supplies the header and claim edits this Playbook sends.'),
 ('playbooks/oauth/playbook.md',
  'ce6862413632fe459aaf257de9b5f325f2fde44c06c33bfa026abe2a09d9d245',
  '48c6f4393e6b531e20bbd9a7ddfb453d267be00667d3913cdeb208ad2d5e8af0',
  'session_handling', 'draft', '2027-03-15T00:00:00Z',
  'approval_required', 'mutates_session', 'none', 2,
  'Written for ticket 50 as the v2 replacement for v1''s oauth pack, against the session-fixation leaf of the ticket 18 vocabulary; two v1 texts are attached as maintainer references and both describe the callback delivery this Playbook performs.'),
 ('playbooks/webauthn/playbook.md',
  '5bc566683b6822c4cc73305484fcac13ded4091b6f6f0eae3569b3b054101748',
  '0522c44ac3bab244b81447660943e223808c16a2560737b52568df0dadb7e5c3',
  'authentication', 'draft', '2027-03-15T00:00:00Z',
  'approval_required', 'mutates_account', 'stable_session', 2,
  'Written for ticket 50 as the v2 replacement for v1''s webauthn pack, against the factor-enforcement leaf of the ticket 18 vocabulary; v1 shipped a README for this topic and no reference text, so nothing is attached.'),
 ('playbooks/workload-identities/playbook.md',
  'c676ed51a5f3bad650855ea4d9069df84a836ec598a954cd8ad1cf321a7742d8',
  'a188b7048dc012a67047b7f8321d8fde82194d4b89e5ff4c15c6ae9943d46e1b',
  'authorization', 'draft', '2027-03-15T00:00:00Z',
  'constrained', 'read_only', 'stable_session', 3,
  'Written for ticket 50 as the v2 replacement for v1''s workload-identities pack, against the tenant-isolation leaf of the ticket 18 vocabulary; v1 shipped a README for this topic and no reference text, so nothing is attached.')
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
-- ticket declares an `any` arm: each of these eight is a question about one kind
-- of surface, and the fact that names it is a requirement rather than one of
-- several ways in.
--
-- Two pairs share a family and are separated by method on purpose. `cookies`
-- fires on a read and `identity-lifecycle` on a state change, so a cookie-bearing
-- route selects the one whose reading it can actually support; `jwt-jose` wants
-- an endpoint that already authenticates and `workload-identities` one whose
-- authentication nobody has established, which is where a machine-to-machine
-- route sits before an Identity has been leased for it.
INSERT INTO playbook_triggers (playbook_id, mode, fact)
SELECT p.id, v.mode, v.fact
  FROM playbooks p, (VALUES
        ('playbooks/authentication/playbook.md',       'all', 'email_valued_parameter'),
        ('playbooks/authentication/playbook.md',       'all', 'state_changing_method'),
        ('playbooks/cookies/playbook.md',              'all', 'cookie_parameter'),
        ('playbooks/cookies/playbook.md',              'all', 'read_method'),
        ('playbooks/identity-lifecycle/playbook.md',   'all', 'cookie_parameter'),
        ('playbooks/identity-lifecycle/playbook.md',   'all', 'state_changing_method'),
        ('playbooks/identity-parsing/playbook.md',     'all', 'state_changing_method'),
        ('playbooks/identity-parsing/playbook.md',     'all', 'tech_saml'),
        ('playbooks/jwt-jose/playbook.md',             'all', 'authenticated_endpoint'),
        ('playbooks/jwt-jose/playbook.md',             'all', 'tech_jwt'),
        ('playbooks/oauth/playbook.md',                'all', 'query_parameter'),
        ('playbooks/oauth/playbook.md',                'all', 'tech_oauth'),
        ('playbooks/webauthn/playbook.md',             'all', 'state_changing_method'),
        ('playbooks/webauthn/playbook.md',             'all', 'tech_webauthn'),
        ('playbooks/workload-identities/playbook.md',  'all', 'header_parameter'),
        ('playbooks/workload-identities/playbook.md',  'all', 'tenant_boundary'),
        ('playbooks/workload-identities/playbook.md',  'all', 'unknown_auth_endpoint'))
        AS v(path, mode, fact)
 WHERE p.path = v.path
ON CONFLICT (playbook_id, mode, fact) DO NOTHING;

-- One class each, and each inside the Playbook's own family. Eight distinct
-- leaves for eight Playbooks, which is what keeps `playbook_fixture_binding`
-- readable: the binding is total over `fixtures`, so two Playbooks sharing a
-- class would each be graded `in` on the other's target and neither result would
-- say which document was right.
INSERT INTO playbook_outputs (playbook_id, property_class)
SELECT p.id, v.property_class
  FROM playbooks p, (VALUES
        ('playbooks/authentication/playbook.md',      'authentication.credential_verification'),
        ('playbooks/cookies/playbook.md',             'session_handling.cookie_scope'),
        ('playbooks/identity-lifecycle/playbook.md',  'session_handling.lifetime'),
        ('playbooks/identity-parsing/playbook.md',    'authentication.federation_trust'),
        ('playbooks/jwt-jose/playbook.md',            'authorization.token_scope'),
        ('playbooks/oauth/playbook.md',               'session_handling.fixation'),
        ('playbooks/webauthn/playbook.md',            'authentication.factor_enforcement'),
        ('playbooks/workload-identities/playbook.md', 'authorization.tenant_isolation'))
        AS v(path, property_class)
 WHERE p.path = v.path
ON CONFLICT (playbook_id, property_class) DO NOTHING;

-- `skill_sha256_at_promotion` stays NULL on every row: nothing here has been
-- promoted, and a promotion hash written at ingest would be a drift baseline
-- taken at a moment no promotion happened.
--
-- Every one of these eight is loadable by `web_hunter` and by nothing else,
-- which is criterion 6's first half and a hard `playbook_unloadable` error
-- otherwise. That is not an accident of authoring: each of them leases an
-- Identity, and `use-identity` is a capability the recon and analyst roles do
-- not carry. A Playbook here that named `enumerate-surface` or `analyse-source`
-- would be pointing at a file its own role cannot open.
INSERT INTO playbook_skills (playbook_id, skill_name)
SELECT p.id, v.skill_name
  FROM playbooks p, (VALUES
        ('playbooks/authentication/playbook.md',      'compare-responses'),
        ('playbooks/authentication/playbook.md',      'use-identity'),
        ('playbooks/cookies/playbook.md',             'browser-evidence'),
        ('playbooks/cookies/playbook.md',             'use-identity'),
        ('playbooks/identity-lifecycle/playbook.md',  'compare-responses'),
        ('playbooks/identity-lifecycle/playbook.md',  'use-identity'),
        ('playbooks/identity-parsing/playbook.md',    'compare-responses'),
        ('playbooks/identity-parsing/playbook.md',    'handle-untrusted-content'),
        ('playbooks/identity-parsing/playbook.md',    'use-identity'),
        ('playbooks/jwt-jose/playbook.md',            'compare-responses'),
        ('playbooks/jwt-jose/playbook.md',            'use-identity'),
        ('playbooks/oauth/playbook.md',               'browser-evidence'),
        ('playbooks/oauth/playbook.md',               'use-identity'),
        ('playbooks/webauthn/playbook.md',            'compare-responses'),
        ('playbooks/webauthn/playbook.md',            'use-identity'),
        ('playbooks/workload-identities/playbook.md', 'compare-responses'),
        ('playbooks/workload-identities/playbook.md', 'use-identity'))
        AS v(path, skill_name)
 WHERE p.path = v.path
ON CONFLICT (playbook_id, skill_name) DO NOTHING;

-- Three rows each: what refutes, what the control has to show, and what the
-- claim itself rests on.
--
-- Seven of the eight take `credential_effect` as the control, and that is the
-- family's own shape rather than a copied line. Every question here is asked of
-- a route that is supposed to make an authentication or authorisation decision,
-- so the reading that has to come first is the route refusing something: a wrong
-- secret, an invented token, a broken signature, a code nobody minted. Without
-- it a `200` from a variant is indistinguishable from a route that never
-- checked, which is a different class and somebody else's claim.
--
-- `cookies` is the exception. Its control is `header_policy_observed`, because
-- what a scope claim rests on is what the server declared the scope to be, and
-- that is a header on the response that issued the cookie rather than a refusal.
-- Its supported row is still `credential_effect`: the finding is the credential
-- being honoured where its own scope should not have carried it.
--
-- Three take `state_change` as the supported reading rather than
-- `credential_effect`. For `oauth` and `webauthn` the claim is that something
-- happened -- a session exists in a browser that never asked, an account's
-- recovery address moved -- and a status line is not that. For
-- `workload-identities` the supported row is `response_differential`, because
-- the finding is another tenant's rows in a body that the caller's own tenant
-- does not return.
INSERT INTO playbook_evidence
        (playbook_id, to_status, role, observation_kind, polarity, min_count)
SELECT p.id, v.to_status, v.role, v.kind, v.polarity, v.min_count
  FROM playbooks p, (VALUES
        ('playbooks/authentication/playbook.md',      'refuted',   'variant', 'response_invariant',    'refutes',  1),
        ('playbooks/authentication/playbook.md',      'supported', 'control', 'credential_effect',     'supports', 1),
        ('playbooks/authentication/playbook.md',      'supported', 'variant', 'credential_effect',     'supports', 1),
        ('playbooks/cookies/playbook.md',             'refuted',   'variant', 'response_invariant',    'refutes',  1),
        ('playbooks/cookies/playbook.md',             'supported', 'control', 'header_policy_observed','supports', 1),
        ('playbooks/cookies/playbook.md',             'supported', 'variant', 'credential_effect',     'supports', 1),
        ('playbooks/identity-lifecycle/playbook.md',  'refuted',   'variant', 'response_invariant',    'refutes',  1),
        ('playbooks/identity-lifecycle/playbook.md',  'supported', 'control', 'credential_effect',     'supports', 1),
        ('playbooks/identity-lifecycle/playbook.md',  'supported', 'variant', 'credential_effect',     'supports', 1),
        ('playbooks/identity-parsing/playbook.md',    'refuted',   'variant', 'response_invariant',    'refutes',  1),
        ('playbooks/identity-parsing/playbook.md',    'supported', 'control', 'credential_effect',     'supports', 1),
        ('playbooks/identity-parsing/playbook.md',    'supported', 'variant', 'credential_effect',     'supports', 1),
        ('playbooks/jwt-jose/playbook.md',            'refuted',   'variant', 'response_invariant',    'refutes',  1),
        ('playbooks/jwt-jose/playbook.md',            'supported', 'control', 'credential_effect',     'supports', 1),
        ('playbooks/jwt-jose/playbook.md',            'supported', 'variant', 'credential_effect',     'supports', 1),
        ('playbooks/oauth/playbook.md',               'refuted',   'variant', 'response_invariant',    'refutes',  1),
        ('playbooks/oauth/playbook.md',               'supported', 'control', 'credential_effect',     'supports', 1),
        ('playbooks/oauth/playbook.md',               'supported', 'variant', 'state_change',          'supports', 1),
        ('playbooks/webauthn/playbook.md',            'refuted',   'variant', 'response_invariant',    'refutes',  1),
        ('playbooks/webauthn/playbook.md',            'supported', 'control', 'credential_effect',     'supports', 1),
        ('playbooks/webauthn/playbook.md',            'supported', 'variant', 'state_change',          'supports', 1),
        ('playbooks/workload-identities/playbook.md', 'refuted',   'variant', 'response_invariant',    'refutes',  1),
        ('playbooks/workload-identities/playbook.md', 'supported', 'control', 'credential_effect',     'supports', 1),
        ('playbooks/workload-identities/playbook.md', 'supported', 'variant', 'response_differential', 'supports', 1))
        AS v(path, to_status, role, kind, polarity, min_count)
 WHERE p.path = v.path
ON CONFLICT (playbook_id, to_status, role, observation_kind) DO NOTHING;

-- The material the model never gets. Eight files behind four Playbooks; the
-- other four topics shipped a README in v1 and no reference text, so they have
-- nothing attached rather than a placeholder. Recorded so a maintainer can find
-- them and hashed so a maintainer can tell whether they moved.
INSERT INTO playbook_references (playbook_id, name, path, sha256)
SELECT p.id, v.name, v.path, v.sha256
  FROM playbooks p, (VALUES
        ('playbooks/authentication/playbook.md', 'cloud-aws-cognito.md',
         'playbooks/authentication/references/cloud-aws-cognito.md',
         'b8edd1286ef62bc715f96677110189478be0bcb52d8f2641d7596423749f559b'),
        ('playbooks/authentication/playbook.md', 'http-attacks-password-reset.md',
         'playbooks/authentication/references/http-attacks-password-reset.md',
         'd433f5f3a2b5dd3131f1870bc47862ed539725b47a04cde39e9460725e584d24'),
        ('playbooks/authentication/playbook.md', 'sign-up-login-register.md',
         'playbooks/authentication/references/sign-up-login-register.md',
         'ddc017612dd9edd08a9a08caa750a15441f3073a556572c1a2d5764ff8473860'),
        ('playbooks/authentication/playbook.md', 'type-juggling.md',
         'playbooks/authentication/references/type-juggling.md',
         '5daa86363dca32321db0a161ed8d81226f2b2f75ad723a46c4aa145fd1fd6b96'),
        ('playbooks/identity-parsing/playbook.md', 'saml.md',
         'playbooks/identity-parsing/references/saml.md',
         '54f0f6b095211abc15dab356890f9fffcaafc693d8afa70fe414b0388312ea20'),
        ('playbooks/jwt-jose/playbook.md', 'jwt.md',
         'playbooks/jwt-jose/references/jwt.md',
         '022856ba8f180b937f61ee99eb5d236349befd502fc4040088eb566a629e1c1f'),
        ('playbooks/oauth/playbook.md', 'oauth2-attack-via-google-oauth2-playground.md',
         'playbooks/oauth/references/oauth2-attack-via-google-oauth2-playground.md',
         '40497d654b2da0e1202f114ee880d05b74c474d5b75b146a73aebdbc1e38ee8e'),
        ('playbooks/oauth/playbook.md', 'oauth2.md',
         'playbooks/oauth/references/oauth2.md',
         'f51aa426d1baa0336803bb77e97d56e94bfb6e0face34b01534f3e692cb4d9bf'))
        AS v(playbook_path, name, path, sha256)
 WHERE p.path = v.playbook_path
ON CONFLICT (playbook_id, name) DO NOTHING;


-- ===========================================================================
-- 3. Eight targets, as rows
-- ===========================================================================

-- One positive per topic, each written from the class description rather than
-- from the Playbook's steps. `playbook_fixture_binding()` is total over this
-- table, so every one of these is also an out-of-class negative for the other
-- fifteen Playbooks -- which is the second half of criterion 4 and the reason
-- nothing here declares a class it does not hold.
--
-- Every one of them checks a credential it is not grading. A fixture that let
-- anybody log in would hold `credential_verification` as well as the class it
-- declares, and a run that reported the undeclared one would be marked wrong for
-- being right. `credential-verification-pair` is the one that grades that class,
-- and it is the only one whose login is the subject.
--
-- Three of them serve both ends of a flow, and say so in their own ground truth.
-- `federation-trust-pair` mints its own assertion, `fixation-pair` plays client
-- and issuer, and `token-scope-pair` issues its own tokens: each of those is the
-- fixture standing in for an Identity slot, because a run's material has to be
-- something it was issued rather than something it forged.
INSERT INTO fixtures (id, kind, path, source_sha256, ground_truth_sha256) VALUES
 ('cookie-scope-pair', 'own_pair',
  'fixtures/cookie-scope-pair/fixture.md',
  '914e44d5158731d75936ef95f2099318d1bc66037105df38ff74560c84710090',
  '99a072c2f1843c7eb736dfafb37cacece4ea2099f93e1fd6b194bdc13fe15e7f'),
 ('credential-verification-pair', 'own_pair',
  'fixtures/credential-verification-pair/fixture.md',
  '24ed9d377e56ba16e1953054308503d0bb27cbf519062a4bd76709851e97baef',
  '1d547a36c82b608255b07f839cf2a395b05974b18d93fd4fa8a8bfe1a5d819ac'),
 ('factor-enforcement-pair', 'own_pair',
  'fixtures/factor-enforcement-pair/fixture.md',
  '43002f0e6a4e25a153f54d8c45d43dfa67646273c7822c09d0ae672fec57b45a',
  '9158d8d8137509390f0aac95bce60208293b36daf766437bd3e38059da01ce1f'),
 ('federation-trust-pair', 'own_pair',
  'fixtures/federation-trust-pair/fixture.md',
  '6e514639804a19d9c1cb131f12be547fd0aa0e28adb345626c3e314e3131065c',
  'f4e29c041c5ec5c4d54d54212a141c34f5b634754854061038aea390b732d4c3'),
 ('fixation-pair', 'own_pair',
  'fixtures/fixation-pair/fixture.md',
  '9e3c2ece3498da263ad9c642f76e0e6752b44f9e51ad22d608d9a362ea3a6fed',
  'f97a74f2b66fd27cb4dbd8b0d09d71841e2ff0e374d6a8f734bdbdbcd9e4f365'),
 ('lifetime-pair', 'own_pair',
  'fixtures/lifetime-pair/fixture.md',
  '121c32b45e51f398cf428bd2b8d4118bf2e53873c5857c83b3fc5abefd76fadc',
  '4897a7b661244aed6cec8e233e0d5b9416c2465e7f6813fc3db9aed32cf0ce8d'),
 ('tenant-isolation-pair', 'own_pair',
  'fixtures/tenant-isolation-pair/fixture.md',
  '9eca663e781d3172d00e8cf2fb2309ec0a66ca920116a4b22c6ac9b5d5025af3',
  'ed69705be6c71038657173b5a2c3909dae17690c786ae43e8689f9b4a75e3743'),
 ('token-scope-pair', 'own_pair',
  'fixtures/token-scope-pair/fixture.md',
  'fb3b65ad5811e43e1b34c4497a1d6ff58138ccf5d20e9a4c35ad163d8a188e92',
  '27cf0bab716f65819a47041a93fd7f4ef541397626ba81003bd919bb42db15e7')
ON CONFLICT (id) DO UPDATE SET
    kind                = excluded.kind,
    path                = excluded.path,
    source_sha256       = excluded.source_sha256,
    ground_truth_sha256 = excluded.ground_truth_sha256;

-- One class each. A fixture carrying two would be two fixtures under one name,
-- and a run against it could not say which one a claim was right about.
INSERT INTO fixture_classes (fixture_id, property_class) VALUES
 ('cookie-scope-pair',            'session_handling.cookie_scope'),
 ('credential-verification-pair', 'authentication.credential_verification'),
 ('factor-enforcement-pair',      'authentication.factor_enforcement'),
 ('federation-trust-pair',        'authentication.federation_trust'),
 ('fixation-pair',                'session_handling.fixation'),
 ('lifetime-pair',                'session_handling.lifetime'),
 ('tenant-isolation-pair',        'authorization.tenant_isolation'),
 ('token-scope-pair',             'authorization.token_scope')
ON CONFLICT (fixture_id, property_class) DO NOTHING;
