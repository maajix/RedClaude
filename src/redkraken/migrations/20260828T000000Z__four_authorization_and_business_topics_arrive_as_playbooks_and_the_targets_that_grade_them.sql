-- ---------------------------------------------------------------------------
-- 20260828T000000Z__four_authorization_and_business_topics_arrive_as_playbooks_and_the_targets_that_grade_them.sql
--                                                                   (ticket 51)
--
-- Ticket 51 migrates the v1 authorization and business-logic topics --
-- api-authorization, payment-workflows, race-conditions, routing -- into
-- authored v2 Playbooks, and gives each of them a positive fixture. Same shape
-- as 049 and 050, one ticket later.
--
-- Three things happen.
--
--   1. Two surface facts, `flow_step` and `quantity_valued_parameter`, and the
--      branches of `subject_facts` that compute them. Spelled out literally for
--      049's reason: the `fact_not_computed` rule reads the view's own
--      definition text, and a name assembled by concatenation is invisible to
--      it.
--
--   2. No new Property classes. All four leaves these Playbooks output are
--      018's: `state_transition`, `workflow_order`, `quantity_or_price` and
--      `replay` were named there, and this ticket is the first to have
--      documents that ask for them.
--
--   3. The four Playbooks and the four fixtures, as rows. Every Playbook is
--      `draft` for 049's reason: `playbooks_stable_is_promoted` and 036's
--      promotion guard make `stable` unreachable until the evaluator has run
--      the exact text against the fixture catalogue, and no evaluation has
--      happened yet.
--
-- The ticket's own framing was object ownership, function access, workflow
-- invariants and concurrency. Two of those four classes were already claimed
-- when this ticket arrived -- `object_ownership` by 045's Playbook and
-- `function_access` by 049's `grpc` -- and the house rule below is that a class
-- has one Playbook, so `api-authorization` claims `state_transition` and
-- `routing` claims `workflow_order` instead. Both are the reading the v1 pack
-- actually described: v1's "IDOR" page covered ownership and state together,
-- and its routing pack was about reaching a step of a flow rather than reaching
-- a route the flow does not contain.
--
-- A new file rather than an edit to 050: a recorded migration whose file has
-- changed is schema drift and `rk db migrate` refuses the whole corpus for it.
-- ---------------------------------------------------------------------------


-- ===========================================================================
-- 1. Two facts, and the branches that compute them
-- ===========================================================================

-- Both endpoint-scoped, and both are preconditions rather than evidence.
--
-- `flow_step` is `redirect_target` read from the other end. That one says this
-- endpoint sends a caller somewhere; this one says something else sends a
-- caller here, which is what makes a route a step in a sequence rather than a
-- route that happens to come later in the screens.
--
-- `quantity_valued_parameter` is the numeric sibling of `url_valued_parameter`
-- and `email_valued_parameter`. `numeric_identifier` already covers the
-- integers that name objects; this covers the numbers that are counted or
-- charged, which is a different question about a different parameter.
INSERT INTO surface_facts (id, scope, description) VALUES
 ('flow_step','endpoint','another endpoint redirects to this one, so it is a step in a flow'),
 ('quantity_valued_parameter','endpoint','a parameter carries a quantity or an amount')
ON CONFLICT (id) DO NOTHING;

-- The view, restated whole because `CREATE OR REPLACE VIEW` has no way to add a
-- branch to a UNION without restating the rest. Two branches have been added and
-- every other one is 050's, verbatim, with the column list unchanged so the
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
-- The new parameter branch. `number` is what a recon pass records for a value
-- that is counted or charged rather than one that names something, and the
-- `payment-workflows` reading needs exactly that parameter: the number it edits
-- has to be one the target computes a total from.
UNION ALL SELECT DISTINCT ep.program_id, ep.entity_id, 'quantity_valued_parameter'
  FROM ep JOIN parameters p ON p.endpoint_id = ep.entity_id WHERE p.value_class = 'number'
UNION ALL SELECT DISTINCT ep.program_id, ep.entity_id, 'redirect_target'
  FROM ep JOIN relationships r ON r.src_entity_id = ep.entity_id AND r.type = 'redirects_to'
-- The other new branch, and the same relationship read backwards: `dst` rather
-- than `src`. An endpoint something else redirects to was arrived at from
-- somewhere, which is the precondition `routing` needs and is not evidence that
-- the order is enforced.
UNION ALL SELECT DISTINCT ep.program_id, ep.entity_id, 'flow_step'
  FROM ep JOIN relationships r ON r.dst_entity_id = ep.entity_id AND r.type = 'redirects_to'
-- application shape
UNION ALL SELECT ep.program_id, ep.entity_id,
       CASE a.kind WHEN 'graphql' THEN 'graphql_surface' WHEN 'spa' THEN 'spa_surface'
                   WHEN 'api' THEN 'api_surface' ELSE 'websocket_surface' END
  FROM ep JOIN applications a ON a.entity_id = ep.application_id
 WHERE a.kind IN ('graphql','spa','api','websocket')
-- Spelled out rather than 'tech_' || lower(t.name), for the reason 049 and 050
-- give at this same branch: `check_playbook_integrity`'s fact_not_computed rule
-- reads the view definition looking for the atom's name, and a name built by
-- concatenation is invisible to it. This ticket adds no technology: all four of
-- its topics are questions about what a route does rather than about what it is
-- built from.
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
-- 2. Four Playbooks, as rows
-- ===========================================================================

-- `version` is the digest of the projection -- what the model is handed --
-- beside `source_sha256`, which is the document.
--
-- All four are `constrained` and `mutates_object`, which is the first ticket
-- where that pairing appears and is what these four topics are. Each of them
-- changes something the target owns on purpose: an order is cancelled, a cart
-- gains a line, a coupon is spent, a checkout advances. `mutates_object` is the
-- honest effect for that, `playbooks_risk_matches_effects` forbids `autonomous`
-- beside it, and each Playbook's last section names the one object it moves and
-- how it is put back.
--
-- All four are `pristine_surface`, which is stronger than any baseline 050 used
-- and is the same fact from the other side: every one of these readings is
-- arithmetic on a number or a state the target keeps, so a second Playbook
-- writing underneath turns the difference into a statement about two runs.
-- `playbooks_conflict` therefore keeps all four apart from each other and from
-- every writer, which is intended rather than tolerated.
INSERT INTO playbooks (path, source_sha256, version, category, status, stale_after,
                       risk, effects, baseline, specificity, provenance) VALUES
 ('playbooks/api-authorization/playbook.md',
  '8fcf59cef4883012ae1d8099386c37f4af829a5c27c0880213e6aecec0d44805',
  'cc6ae2735216458bcf6eb0994cefdd74dca03a1eae181a3d968404ac173b4caf',
  'authorization', 'draft', '2027-03-15T00:00:00Z',
  'constrained', 'mutates_object', 'pristine_surface', 3,
  'Written for ticket 51 as the v2 replacement for v1''s api-authorization pack, against the state-transition leaf of the ticket 18 vocabulary; two v1 texts are attached as maintainer references and both describe the identifier work step 1 rests on.'),
 ('playbooks/payment-workflows/playbook.md',
  '9c5dfb932fe95dd11917d42412c97953e503c0f5459922e5733d8fe02b7d5ce4',
  '4d40c0f0b08b27c16a5b1b480a42d0cf894fddac180603416ae5b03ad46f8792',
  'business_logic', 'draft', '2027-03-15T00:00:00Z',
  'constrained', 'mutates_object', 'pristine_surface', 3,
  'Written for ticket 51 as the v2 replacement for v1''s payment-workflows pack, against the quantity-or-price leaf of the ticket 18 vocabulary; v1 shipped a README for this topic and no reference text, so nothing is attached.'),
 ('playbooks/race-conditions/playbook.md',
  'aa118d25f5e6a6394f0d39a7802b1c2d86a3bda9cccbaf7bc3b57b03678a4771',
  'd467ca2d636d688b2e661a1c281dcc7918a0371d242401ee238cb73917480446',
  'business_logic', 'draft', '2027-03-15T00:00:00Z',
  'constrained', 'mutates_object', 'pristine_surface', 3,
  'Written for ticket 51 as the v2 replacement for v1''s race-conditions pack, against the replay leaf of the ticket 18 vocabulary; the v1 race-conditions text is attached as a maintainer reference and is where the sequential control this Playbook insists on comes from.'),
 ('playbooks/routing/playbook.md',
  '92c500bdaf997087ab263fb668b0dd8ed11d4e23aadc759ae7355928ad0ff9a1',
  '03361c6597cf424dcfad39ffb5c5b78440e527b94d79dd7b56cdbb3312601361',
  'business_logic', 'draft', '2027-03-15T00:00:00Z',
  'constrained', 'mutates_object', 'pristine_surface', 2,
  'Written for ticket 51 as the v2 replacement for v1''s routing pack, against the workflow-order leaf of the ticket 18 vocabulary; two v1 texts are attached as maintainer references and both describe the spellings step 4 sends.')
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
-- ticket declares an `any` arm, for 050's reason.
--
-- `routing` is the least specific document in the corpus at two triggers, and
-- that is what the topic is: any step something else leads to, whatever it is
-- built from. The other three each carry a third fact that says which number or
-- which object the reading is about.
--
-- None of the four triggers on `object_identifier`, which 045's Playbook
-- effectively reserves, and none of them triggers on the same three facts as
-- another: `api-authorization` wants a second Identity and a path segment,
-- `payment-workflows` a number, `race-conditions` a JSON body.
INSERT INTO playbook_triggers (playbook_id, mode, fact)
SELECT p.id, v.mode, v.fact
  FROM playbooks p, (VALUES
        ('playbooks/api-authorization/playbook.md',  'all', 'multiple_test_identities'),
        ('playbooks/api-authorization/playbook.md',  'all', 'path_parameter'),
        ('playbooks/api-authorization/playbook.md',  'all', 'state_changing_method'),
        ('playbooks/payment-workflows/playbook.md',  'all', 'authenticated_endpoint'),
        ('playbooks/payment-workflows/playbook.md',  'all', 'quantity_valued_parameter'),
        ('playbooks/payment-workflows/playbook.md',  'all', 'state_changing_method'),
        ('playbooks/race-conditions/playbook.md',    'all', 'authenticated_endpoint'),
        ('playbooks/race-conditions/playbook.md',    'all', 'json_request'),
        ('playbooks/race-conditions/playbook.md',    'all', 'state_changing_method'),
        ('playbooks/routing/playbook.md',            'all', 'flow_step'),
        ('playbooks/routing/playbook.md',            'all', 'state_changing_method'))
        AS v(path, mode, fact)
 WHERE p.path = v.path
ON CONFLICT (playbook_id, mode, fact) DO NOTHING;

-- One class each, and each inside the Playbook's own family. Four distinct
-- leaves for four Playbooks, which is what keeps `playbook_fixture_binding`
-- readable: the binding is total over `fixtures`, so two Playbooks sharing a
-- class would each be graded `in` on the other's target and neither result would
-- say which document was right. That rule is also why neither of these four
-- outputs `authorization.object_ownership` or `authorization.function_access`,
-- which 045 and 049 already claim.
INSERT INTO playbook_outputs (playbook_id, property_class)
SELECT p.id, v.property_class
  FROM playbooks p, (VALUES
        ('playbooks/api-authorization/playbook.md', 'authorization.state_transition'),
        ('playbooks/payment-workflows/playbook.md', 'business_logic.quantity_or_price'),
        ('playbooks/race-conditions/playbook.md',   'business_logic.replay'),
        ('playbooks/routing/playbook.md',           'business_logic.workflow_order'))
        AS v(path, property_class)
 WHERE p.path = v.path
ON CONFLICT (playbook_id, property_class) DO NOTHING;

-- `skill_sha256_at_promotion` stays NULL on every row, for 050's reason.
--
-- The same two Skills on all four, and both are needed by all four. Every one of
-- these readings holds an Identity for a sequence of calls, which is
-- `use-identity`; and every one of them ends by differencing an authoritative
-- state against a control, which is `compare-responses`. That combination makes
-- all four loadable by `web_hunter` and by nothing else, which is criterion 6's
-- first half and a hard `playbook_unloadable` error otherwise.
INSERT INTO playbook_skills (playbook_id, skill_name)
SELECT p.id, v.skill_name
  FROM playbooks p, (VALUES
        ('playbooks/api-authorization/playbook.md', 'compare-responses'),
        ('playbooks/api-authorization/playbook.md', 'use-identity'),
        ('playbooks/payment-workflows/playbook.md', 'compare-responses'),
        ('playbooks/payment-workflows/playbook.md', 'use-identity'),
        ('playbooks/race-conditions/playbook.md',   'compare-responses'),
        ('playbooks/race-conditions/playbook.md',   'use-identity'),
        ('playbooks/routing/playbook.md',           'compare-responses'),
        ('playbooks/routing/playbook.md',           'use-identity'))
        AS v(path, skill_name)
 WHERE p.path = v.path
ON CONFLICT (playbook_id, skill_name) DO NOTHING;

-- Three rows each: what refutes, what the control has to show, and what the
-- claim itself rests on.
--
-- Every supported row here is `state_change`, on both roles, and that is what
-- separates this ticket from 050. The identity family's readings are about which
-- caller a route answers, so a credential taking effect is the reading. These
-- four are about what the target did to itself: an order that is cancelled, a
-- total that moved, a balance that moved twice, a checkout that says it is
-- confirmed. A status line is not that, and each Playbook says so in its own
-- words at step 5.
--
-- The control row is the harder half. `payment-workflows` has to show the
-- allowed quantity reaching the total, `race-conditions` the action landing once
-- with the second sequential attempt refused, `routing` the flow completing in
-- order. Without that, a variant that moved nothing is equally well explained by
-- a route that was never working.
--
-- `api-authorization`'s control row is the one exception and it is
-- `credential_effect` rather than `state_change`, because that reading's control
-- is a refusal: the same request under a second Identity and against an object
-- that does not exist, which is the ticket's second criterion and is a
-- credential having an effect rather than a state moving.
INSERT INTO playbook_evidence
        (playbook_id, to_status, role, observation_kind, polarity, min_count)
SELECT p.id, v.to_status, v.role, v.kind, v.polarity, v.min_count
  FROM playbooks p, (VALUES
        ('playbooks/api-authorization/playbook.md', 'refuted',   'variant', 'response_invariant', 'refutes',  1),
        ('playbooks/api-authorization/playbook.md', 'supported', 'control', 'credential_effect',  'supports', 1),
        ('playbooks/api-authorization/playbook.md', 'supported', 'variant', 'state_change',       'supports', 1),
        ('playbooks/payment-workflows/playbook.md', 'refuted',   'variant', 'response_invariant', 'refutes',  1),
        ('playbooks/payment-workflows/playbook.md', 'supported', 'control', 'state_change',       'supports', 1),
        ('playbooks/payment-workflows/playbook.md', 'supported', 'variant', 'state_change',       'supports', 1),
        ('playbooks/race-conditions/playbook.md',   'refuted',   'variant', 'response_invariant', 'refutes',  1),
        ('playbooks/race-conditions/playbook.md',   'supported', 'control', 'state_change',       'supports', 1),
        ('playbooks/race-conditions/playbook.md',   'supported', 'variant', 'state_change',       'supports', 1),
        ('playbooks/routing/playbook.md',           'refuted',   'variant', 'response_invariant', 'refutes',  1),
        ('playbooks/routing/playbook.md',           'supported', 'control', 'state_change',       'supports', 1),
        ('playbooks/routing/playbook.md',           'supported', 'variant', 'state_change',       'supports', 1))
        AS v(path, to_status, role, kind, polarity, min_count)
 WHERE p.path = v.path
ON CONFLICT (playbook_id, to_status, role, observation_kind) DO NOTHING;

-- The material the model never gets. Five files behind three Playbooks;
-- payment-workflows shipped a README in v1 and no reference text, so it has
-- nothing attached rather than a placeholder. Recorded so a maintainer can find
-- them and hashed so a maintainer can tell whether they moved.
INSERT INTO playbook_references (playbook_id, name, path, sha256)
SELECT p.id, v.name, v.path, v.sha256
  FROM playbooks p, (VALUES
        ('playbooks/api-authorization/playbook.md', 'idor.md',
         'playbooks/api-authorization/references/idor.md',
         '0a5d50869bb504dd2497001652af93720ab14253912e2a736906c9341c5a86b6'),
        ('playbooks/api-authorization/playbook.md', 'uuids.md',
         'playbooks/api-authorization/references/uuids.md',
         '15e4c85f0d02a212649ca528d8f93dce48cbf18418f32dafd36585d46cd2a9da'),
        ('playbooks/race-conditions/playbook.md', 'race-conditions-and-timing-attacks.md',
         'playbooks/race-conditions/references/race-conditions-and-timing-attacks.md',
         'eddd54501c6d61993e457c15b7b1ddadf5bfc03ce8c8380952296fa19cef234e'),
        ('playbooks/routing/playbook.md', 'http-attacks-verb-tampering.md',
         'playbooks/routing/references/http-attacks-verb-tampering.md',
         'd211c0b84f6d8194238a703e9bdbc7ad144647c035413518610b76fd32a01b61'),
        ('playbooks/routing/playbook.md', 'status-code-bypass.md',
         'playbooks/routing/references/status-code-bypass.md',
         '58435d189c6c6c3a00bc2e275ad41a7dea37a50e229b340efa123379c9fafc10'))
        AS v(playbook_path, name, path, sha256)
 WHERE p.path = v.playbook_path
ON CONFLICT (playbook_id, name) DO NOTHING;


-- ===========================================================================
-- 3. Four targets, as rows
-- ===========================================================================

-- One positive per topic, each written from the class description rather than
-- from the Playbook's steps. `playbook_fixture_binding()` is total over this
-- table, so every one of these is also an out-of-class negative for the other
-- nineteen Playbooks -- which is the second half of criterion 4 and the reason
-- nothing here declares a class it does not hold.
--
-- All four check a credential they are not grading, for 050's reason, and all
-- four publish the rule they are graded against: the states a cancellation is
-- allowed from, the quantity range the cart accepts, the coupons that exist and
-- what they are worth, the order the checkout walks. A fixture whose invariant
-- had to be guessed would be a fixture where a correct refutation and a run that
-- guessed wrong look the same.
--
-- `state-transition-pair` is the one with two Identities. Its foreign-owner and
-- nonexistent controls are identical on both variants, so the ownership question
-- is settled the same way on each and the only difference between the halves is
-- the state check -- which is what keeps `authorization.object_ownership` out of
-- a fixture that would otherwise hold it.
INSERT INTO fixtures (id, kind, path, source_sha256, ground_truth_sha256) VALUES
 ('quantity-or-price-pair', 'own_pair',
  'fixtures/quantity-or-price-pair/fixture.md',
  '78eaa20e84f9096c6679fad4fe0c553d8ea147951ac1d37734776c414ddcc208',
  '61a984689fec5ceff03fb5feb3204f0884243c981dd9ac266b583c1e4f62ae7b'),
 ('replay-pair', 'own_pair',
  'fixtures/replay-pair/fixture.md',
  '61556668542f8d4f6742efce0984585f67158f6121668a87a7b59d5f77d4618d',
  'bbb7606d15a57031732d84877239363623c7d3fb5ba2a93881c395ed0047ad68'),
 ('state-transition-pair', 'own_pair',
  'fixtures/state-transition-pair/fixture.md',
  '2e2eb282f86a03bacc92727fc83b3f60c58da46d4c353f5fe904b661087d4279',
  '23ba9bef12e65d7ef2123a7606ccf3324bc552ecb9f78c7b4a617edda8a014bc'),
 ('workflow-order-pair', 'own_pair',
  'fixtures/workflow-order-pair/fixture.md',
  'dc0519a3bfc78edea8d8ebd332943e55d61af7f1ac79c7ad8702bab4e327cfcf',
  '11e727218e541f6f535a8c79802c9ccedce78c5f91815d7c4aebf795dccb15c0')
ON CONFLICT (id) DO UPDATE SET
    kind                = excluded.kind,
    path                = excluded.path,
    source_sha256       = excluded.source_sha256,
    ground_truth_sha256 = excluded.ground_truth_sha256;

-- One class each, for 050's reason.
INSERT INTO fixture_classes (fixture_id, property_class) VALUES
 ('quantity-or-price-pair', 'business_logic.quantity_or_price'),
 ('replay-pair',            'business_logic.replay'),
 ('state-transition-pair',  'authorization.state_transition'),
 ('workflow-order-pair',    'business_logic.workflow_order')
ON CONFLICT (fixture_id, property_class) DO NOTHING;
