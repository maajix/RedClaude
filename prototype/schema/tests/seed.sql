-- NOTE (ticket 33): the vocabulary values below are the ones migration 018
-- defines. They used to be 'authz.horizontal', 'authz.vertical',
-- 'injection.sql' and 'http.response', and with the whole corpus applied the
-- fixture and 018 were mutually unapplicable: seeded first, 018's guard refuses
-- to start because `observations` is immutable and carries kinds outside the
-- vocabulary; seeded second, hypotheses_property_class_fk and
-- observations_kind_fk reject the rows. 018 says "the vocabulary is the
-- decision; the fixture follows it", so the fixture follows it. The three
-- observations are the baseline/variant/control legs of one differential, which
-- is what `response_differential` names.
-- Seed one small but complete program: surface, provenance, an investigation
-- chain that reaches `supported`, and a finding that reaches `validated`.
-- Everything runs through the session helper contract (app.actor_kind).

SET client_min_messages = warning;
SELECT set_config('app.actor_kind', 'runtime', false);

INSERT INTO programs (id, slug, name, platform) VALUES
    ('11111111-1111-7111-8111-111111111111', 'acme', 'Acme BB', 'hackerone'),
    ('22222222-2222-7222-8222-222222222222', 'other', 'Other BB', 'bugcrowd');

INSERT INTO vulnerability_classes (id, cwe_id, name) VALUES
    ('idor', 'CWE-639', 'Insecure direct object reference');

-- ticket 33: from migration 021 on, a program's scope is a versioned document
-- and a compiled rule set, and every non-control receipt names the version that
-- authorised it. The fixture therefore has to publish a policy before it can
-- record a single request. One target rule per program is enough; the rule
-- shape is the compiler's (effect_rank ascending = exclude, egress_support,
-- target, so min() wins), not a second parser.
INSERT INTO program_scope_versions
       (program_id, version, policy, policy_sha256, default_tier, reason) VALUES
    ('11111111-1111-7111-8111-111111111111', 1,
     '{"targets":["acme.test"]}'::jsonb, repeat('e',64), 'standard', 'fixture'),
    ('22222222-2222-7222-8222-222222222222', 1,
     '{"targets":["other.test"]}'::jsonb, repeat('f',64), 'standard', 'fixture');

INSERT INTO program_scope_rules
       (program_id, version, ord, effect, effect_rank, pattern_kind,
        pattern_text, match_key, spec_kind, spec_len) VALUES
    ('11111111-1111-7111-8111-111111111111', 1, 1, 'target', 2, 'exact',
     'acme.test',  'acme.test',  2, length('acme.test')),
    ('22222222-2222-7222-8222-222222222222', 1, 1, 'target', 2, 'exact',
     'other.test', 'other.test', 2, length('other.test'));

-- ---- surface -------------------------------------------------------------
-- ticket 33: migration 021 requires every entity that is not an identity or a
-- technology to carry the scope selector it was reached through, so the
-- fixture carries it. Without this the fixture stops being applicable to the
-- corpus at migration 021, three migrations before it stops being applicable
-- at 018 -- the vocabulary was the second reason, not the first.
INSERT INTO entities (id, program_id, type, label, dedup_key,
                      scope_selector_kind, scope_selector) VALUES
    ('aaaaaaaa-0000-7000-8000-000000000001','11111111-1111-7111-8111-111111111111','application','APP1','https://acme.test','host','acme.test'),
    ('aaaaaaaa-0000-7000-8000-000000000002','11111111-1111-7111-8111-111111111111','endpoint','EP1','GET /api/orders/{id}','host','acme.test'),
    ('aaaaaaaa-0000-7000-8000-000000000003','11111111-1111-7111-8111-111111111111','identity','ID1','identity:anon',NULL,NULL),
    ('aaaaaaaa-0000-7000-8000-000000000004','11111111-1111-7111-8111-111111111111','identity','ID2','identity:userA',NULL,NULL),
    ('aaaaaaaa-0000-7000-8000-000000000005','11111111-1111-7111-8111-111111111111','endpoint','EP2','GET /api/profile','host','acme.test');

INSERT INTO applications (entity_id, base_url, kind) VALUES
    ('aaaaaaaa-0000-7000-8000-000000000001','https://acme.test','api');
INSERT INTO endpoints (entity_id, application_id, method, path_template) VALUES
    ('aaaaaaaa-0000-7000-8000-000000000002','aaaaaaaa-0000-7000-8000-000000000001','GET','/api/orders/{id}'),
    ('aaaaaaaa-0000-7000-8000-000000000005','aaaaaaaa-0000-7000-8000-000000000001','GET','/api/profile');
INSERT INTO identities (entity_id, slot_name, class, secret_ref) VALUES
    ('aaaaaaaa-0000-7000-8000-000000000003','anon','anonymous',NULL),
    ('aaaaaaaa-0000-7000-8000-000000000004','userA','user','op://BugBounty Dynamic/userA/password');

-- ---- provenance ----------------------------------------------------------
INSERT INTO artifacts (sha256, byte_size, visibility, encrypted) VALUES
    (repeat('a',64), 100, 'agent_visible', false),
    (repeat('b',64), 100, 'credential_bearing', true);

INSERT INTO tool_runs (id, program_id, label, tool, status) VALUES
    ('cccccccc-0000-7000-8000-000000000001','11111111-1111-7111-8111-111111111111','TR1','js_analyze','success'),
    ('cccccccc-0000-7000-8000-0000000000b1','22222222-2222-7222-8222-222222222222','TR1','js_analyze','success');

INSERT INTO receipts (id, program_id, label, lane, decision, reason, ts_arrival,
                      identity_entity_id, method, host, path, status_code,
                      request_agent_sha, response_agent_sha,
                      scope_version, scope_class, tool_run_id) VALUES
    ('dddddddd-0000-7000-8000-000000000001','11111111-1111-7111-8111-111111111111','R1','agent','allowed','in scope', now(),
     'aaaaaaaa-0000-7000-8000-000000000004','GET','acme.test','/api/orders/1',200, repeat('a',64), repeat('a',64), 1, 'target', 'cccccccc-0000-7000-8000-000000000001'),
    ('dddddddd-0000-7000-8000-000000000002','11111111-1111-7111-8111-111111111111','R2','agent','allowed','in scope', now(),
     'aaaaaaaa-0000-7000-8000-000000000003','GET','acme.test','/api/orders/1',403, repeat('a',64), repeat('a',64), 1, 'target', 'cccccccc-0000-7000-8000-000000000001'),
    ('dddddddd-0000-7000-8000-000000000003','11111111-1111-7111-8111-111111111111','R3','agent','allowed','in scope', now(),
     'aaaaaaaa-0000-7000-8000-000000000004','GET','acme.test','/api/orders/2',200, repeat('a',64), repeat('a',64), 1, 'target', 'cccccccc-0000-7000-8000-000000000001'),
    ('dddddddd-0000-7000-8000-000000000009','11111111-1111-7111-8111-111111111111','R9','proxy_internal','allowed','csrf fetch', now(),
     NULL,'GET','acme.test','/login',200, repeat('a',64), repeat('a',64), 1, 'target', 'cccccccc-0000-7000-8000-000000000001');

-- ---- tasks and runs ------------------------------------------------------
INSERT INTO tasks (id, program_id, label, kind, subject_entity_id,
                   expected_information_gain, potential_impact) VALUES
    ('eeeeeeee-0000-7000-8000-000000000001','11111111-1111-7111-8111-111111111111','T1','recon',
     'aaaaaaaa-0000-7000-8000-000000000001', 0.8, 0.1);

INSERT INTO agent_runs (id, program_id, label, task_id, role, model, effort, mission_packet,
                        input_tokens, output_tokens, stop_reason, finished_at) VALUES
    ('ffffffff-0000-7000-8000-000000000001','11111111-1111-7111-8111-111111111111','A1',
     'eeeeeeee-0000-7000-8000-000000000001','recon','claude-opus-5','high','{"goal":"map"}',
     1000, 500, 'completed', now());

INSERT INTO identity_leases (program_id, identity_entity_id, holder_agent_run_id, expires_at) VALUES
    ('11111111-1111-7111-8111-111111111111','aaaaaaaa-0000-7000-8000-000000000004',
     'ffffffff-0000-7000-8000-000000000001', now() + interval '30 minutes');

-- ---- investigation chain -------------------------------------------------
INSERT INTO hypotheses (id, program_id, label, subject_entity_id,
                        identity_a_entity_id, identity_b_entity_id,
                        property_class, statement) VALUES
    ('bbbbbbbb-0000-7000-8000-000000000001','11111111-1111-7111-8111-111111111111','H1',
     'aaaaaaaa-0000-7000-8000-000000000002',
     'aaaaaaaa-0000-7000-8000-000000000004','aaaaaaaa-0000-7000-8000-000000000003',
     'authorization.object_ownership','userA can read another tenant order via /api/orders/{id}');

INSERT INTO observations (id, program_id, label, agent_run_id, subject_entity_id, kind, summary,
                          provenance_kind, receipt_id) VALUES
    ('99999999-0000-7000-8000-000000000001','11111111-1111-7111-8111-111111111111','O1',
     'ffffffff-0000-7000-8000-000000000001','aaaaaaaa-0000-7000-8000-000000000002',
     'response_differential','200 with order body as userA','receipt','dddddddd-0000-7000-8000-000000000001'),
    ('99999999-0000-7000-8000-000000000002','11111111-1111-7111-8111-111111111111','O2',
     'ffffffff-0000-7000-8000-000000000001','aaaaaaaa-0000-7000-8000-000000000002',
     'response_differential','403 as anonymous','receipt','dddddddd-0000-7000-8000-000000000002'),
    ('99999999-0000-7000-8000-000000000003','11111111-1111-7111-8111-111111111111','O3',
     'ffffffff-0000-7000-8000-000000000001','aaaaaaaa-0000-7000-8000-000000000002',
     'response_differential','200 for a foreign order id','receipt','dddddddd-0000-7000-8000-000000000003');

INSERT INTO hypothesis_evidence (hypothesis_id, observation_id, polarity, role) VALUES
    ('bbbbbbbb-0000-7000-8000-000000000001','99999999-0000-7000-8000-000000000001','supports','baseline'),
    ('bbbbbbbb-0000-7000-8000-000000000001','99999999-0000-7000-8000-000000000003','supports','variant'),
    ('bbbbbbbb-0000-7000-8000-000000000001','99999999-0000-7000-8000-000000000002','supports','control');

-- The test and its run come before the conclusion, because `testing -> supported`
-- now requires the cited receipt to be one the run produced.
INSERT INTO tests (id, program_id, label, hypothesis_id, spec, spec_sha256, created_by_run_id) VALUES
    ('77777777-0000-7000-8000-000000000001','11111111-1111-7111-8111-111111111111','TS1',
     'bbbbbbbb-0000-7000-8000-000000000001','{"steps":[]}', repeat('c',64),
     'ffffffff-0000-7000-8000-000000000001');

INSERT INTO test_runs (id, program_id, test_id, agent_run_id, lane, outcome, assertion_results) VALUES
    ('66666666-0000-7000-8000-000000000001','11111111-1111-7111-8111-111111111111',
     '77777777-0000-7000-8000-000000000001','ffffffff-0000-7000-8000-000000000001',
     'replay','holds','{"all":true}');

INSERT INTO test_run_receipts (test_run_id, receipt_id, ordinal) VALUES
    ('66666666-0000-7000-8000-000000000001','dddddddd-0000-7000-8000-000000000001',1),
    ('66666666-0000-7000-8000-000000000001','dddddddd-0000-7000-8000-000000000003',2);

-- proposed -> testable -> testing -> supported
INSERT INTO hypothesis_transitions (program_id, hypothesis_id, from_status, to_status, actor_kind) VALUES
    ('11111111-1111-7111-8111-111111111111','bbbbbbbb-0000-7000-8000-000000000001','proposed','testable','llm');
-- One statement per transition: the status cache is written by an AFTER ROW
-- trigger, which fires at end of statement, so two chained transitions in one
-- INSERT would see a stale from_status. Each transition is its own commit point
-- in the runtime anyway.
INSERT INTO hypothesis_transitions (program_id, hypothesis_id, from_status, to_status, actor_kind, receipt_id) VALUES
    ('11111111-1111-7111-8111-111111111111','bbbbbbbb-0000-7000-8000-000000000001','testable','testing','runtime','dddddddd-0000-7000-8000-000000000001');
INSERT INTO hypothesis_transitions (program_id, hypothesis_id, from_status, to_status, actor_kind, receipt_id) VALUES
    ('11111111-1111-7111-8111-111111111111','bbbbbbbb-0000-7000-8000-000000000001','testing','supported','runtime','dddddddd-0000-7000-8000-000000000003');

-- ---- finding -------------------------------------------------------------
INSERT INTO findings (id, program_id, label, subject_entity_id, class_id, title, severity) VALUES
    ('55555555-0000-7000-8000-000000000001','11111111-1111-7111-8111-111111111111','F1',
     'aaaaaaaa-0000-7000-8000-000000000002','idor','IDOR on /api/orders/{id}','high');

INSERT INTO finding_hypotheses (finding_id, hypothesis_id) VALUES
    ('55555555-0000-7000-8000-000000000001','bbbbbbbb-0000-7000-8000-000000000001');
INSERT INTO finding_evidence (finding_id, observation_id, ordinal) VALUES
    ('55555555-0000-7000-8000-000000000001','99999999-0000-7000-8000-000000000001',1),
    ('55555555-0000-7000-8000-000000000001','99999999-0000-7000-8000-000000000003',2),
    ('55555555-0000-7000-8000-000000000001','99999999-0000-7000-8000-000000000002',3);

INSERT INTO finding_transitions (program_id, finding_id, from_status, to_status, actor_kind) VALUES
    ('11111111-1111-7111-8111-111111111111','55555555-0000-7000-8000-000000000001','candidate','validating','runtime');

-- validated needs validated_by_test_run_id, which is not a status column, so it
-- is a plain UPDATE before the transition row.
UPDATE findings SET validated_by_test_run_id = '66666666-0000-7000-8000-000000000001'
 WHERE id = '55555555-0000-7000-8000-000000000001';

INSERT INTO finding_transitions (program_id, finding_id, from_status, to_status, actor_kind, receipt_id) VALUES
    ('11111111-1111-7111-8111-111111111111','55555555-0000-7000-8000-000000000001','validating','validated','runtime','dddddddd-0000-7000-8000-000000000003');

-- ---- fixtures the checks need in specific states --------------------------

-- H2: parked at `testable`, the state the provenance hinge guards.
INSERT INTO hypotheses (id, program_id, label, subject_entity_id,
                        identity_a_entity_id, property_class, statement) VALUES
    ('bbbbbbbb-0000-7000-8000-000000000002','11111111-1111-7111-8111-111111111111','H2',
     'aaaaaaaa-0000-7000-8000-000000000005','aaaaaaaa-0000-7000-8000-000000000004',
     'authorization.function_access','userA reaches an admin-only field on /api/profile');
INSERT INTO hypothesis_transitions (program_id, hypothesis_id, from_status, to_status, actor_kind) VALUES
    ('11111111-1111-7111-8111-111111111111','bbbbbbbb-0000-7000-8000-000000000002','proposed','testable','llm');

-- H3: left at `testing`, which is what a crash strands. Its test ran to
-- completion and the conclusion was never written, so the run exists.
INSERT INTO hypotheses (id, program_id, label, subject_entity_id, property_class, statement) VALUES
    ('bbbbbbbb-0000-7000-8000-000000000003','11111111-1111-7111-8111-111111111111','H3',
     'aaaaaaaa-0000-7000-8000-000000000005','injection.query_language','id parameter concatenated into SQL');
INSERT INTO hypothesis_transitions (program_id, hypothesis_id, from_status, to_status, actor_kind) VALUES
    ('11111111-1111-7111-8111-111111111111','bbbbbbbb-0000-7000-8000-000000000003','proposed','testable','llm');
INSERT INTO hypothesis_transitions (program_id, hypothesis_id, from_status, to_status, actor_kind, receipt_id) VALUES
    ('11111111-1111-7111-8111-111111111111','bbbbbbbb-0000-7000-8000-000000000003','testable','testing','runtime','dddddddd-0000-7000-8000-000000000001');

INSERT INTO tests (id, program_id, label, hypothesis_id, spec, spec_sha256, created_by_run_id) VALUES
    ('77777777-0000-7000-8000-000000000002','11111111-1111-7111-8111-111111111111','TS2',
     'bbbbbbbb-0000-7000-8000-000000000003','{"steps":[]}', repeat('d',64),
     'ffffffff-0000-7000-8000-000000000001');
INSERT INTO test_runs (id, program_id, test_id, agent_run_id, lane, outcome, assertion_results) VALUES
    ('66666666-0000-7000-8000-000000000003','11111111-1111-7111-8111-111111111111',
     '77777777-0000-7000-8000-000000000002','ffffffff-0000-7000-8000-000000000001',
     'replay','holds','{"all":true}');
INSERT INTO test_run_receipts (test_run_id, receipt_id, ordinal) VALUES
    ('66666666-0000-7000-8000-000000000003','dddddddd-0000-7000-8000-000000000001',1);

-- F2: a candidate finding with no evidence.
INSERT INTO findings (id, program_id, label, subject_entity_id, class_id, title, severity) VALUES
    ('55555555-0000-7000-8000-000000000002','11111111-1111-7111-8111-111111111111','F2',
     'aaaaaaaa-0000-7000-8000-000000000005','idor','Second candidate','low');

-- Program B, so cross-program citation can be tested.
INSERT INTO entities (id, program_id, type, label, dedup_key,
                      scope_selector_kind, scope_selector) VALUES
    ('aaaaaaaa-0000-7000-8000-0000000000b1','22222222-2222-7222-8222-222222222222','application','APP1','https://other.test','host','other.test');
INSERT INTO applications (entity_id, base_url, kind) VALUES
    ('aaaaaaaa-0000-7000-8000-0000000000b1','https://other.test','web');
-- ticket 33: 022 forbids a SERVED agent-lane receipt that names no tool run,
-- so program B gets its own tool run rather than an exemption.
INSERT INTO receipts (id, program_id, label, lane, decision, reason, ts_arrival,
                      scope_version, scope_class, tool_run_id) VALUES
    ('dddddddd-0000-7000-8000-0000000000b1','22222222-2222-7222-8222-222222222222','R1','agent','allowed','in scope', now(), 1, 'target', 'cccccccc-0000-7000-8000-0000000000b1');

-- ---- D9: rows inserted with no label get one from the database ------------
-- Every label above is explicit, which is how the seed reads as documentation.
-- These two are not, because that is the path the runtime actually uses.
INSERT INTO entities (id, program_id, type, dedup_key) VALUES
    ('aaaaaaaa-0000-7000-8000-0000000000c1','11111111-1111-7111-8111-111111111111','technology','nginx/1.25.3'),
    ('aaaaaaaa-0000-7000-8000-0000000000c2','11111111-1111-7111-8111-111111111111','technology','express/4.18.2');

-- ---- ticket 09: an evidence profile a skill could ship --------------------
-- Stricter than the transition_rules default of 2 supporting + 1 control, which
-- is the only direction a profile is allowed to move.
CREATE FUNCTION evidence_profile_strict_four(p_hypothesis uuid) RETURNS boolean
LANGUAGE sql STABLE AS $$
    SELECT count(*) >= 4 FROM hypothesis_evidence WHERE hypothesis_id = p_hypothesis
$$;

INSERT INTO evidence_profiles (id, description) VALUES
    ('strict_four', 'four evidence rows on the hypothesis, not two plus a control');

-- ---- ticket 33: publish the policy and project it ------------------------
-- `entities.in_scope` used to default to true; 021 flipped the default to false
-- and made the column projected, so the fixture has to run the projection or
-- every entity in it reads as denied. This is the last statement in the file
-- because it projects every entity, including the two program-B rows and the
-- two technologies added above.
SELECT set_scope_version('11111111-1111-7111-8111-111111111111', 1);
SELECT set_scope_version('22222222-2222-7222-8222-222222222222', 1);
