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

-- ---- surface -------------------------------------------------------------
INSERT INTO entities (id, program_id, type, label, dedup_key) VALUES
    ('aaaaaaaa-0000-7000-8000-000000000001','11111111-1111-7111-8111-111111111111','application','APP1','https://acme.test'),
    ('aaaaaaaa-0000-7000-8000-000000000002','11111111-1111-7111-8111-111111111111','endpoint','EP1','GET /api/orders/{id}'),
    ('aaaaaaaa-0000-7000-8000-000000000003','11111111-1111-7111-8111-111111111111','identity','ID1','identity:anon'),
    ('aaaaaaaa-0000-7000-8000-000000000004','11111111-1111-7111-8111-111111111111','identity','ID2','identity:userA'),
    ('aaaaaaaa-0000-7000-8000-000000000005','11111111-1111-7111-8111-111111111111','endpoint','EP2','GET /api/profile');

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
    ('cccccccc-0000-7000-8000-000000000001','11111111-1111-7111-8111-111111111111','TR1','js_analyze','success');

INSERT INTO receipts (id, program_id, label, lane, decision, reason, ts_arrival,
                      identity_entity_id, method, host, path, status_code,
                      request_agent_sha, response_agent_sha) VALUES
    ('dddddddd-0000-7000-8000-000000000001','11111111-1111-7111-8111-111111111111','R1','agent','allowed','in scope', now(),
     'aaaaaaaa-0000-7000-8000-000000000004','GET','acme.test','/api/orders/1',200, repeat('a',64), repeat('a',64)),
    ('dddddddd-0000-7000-8000-000000000002','11111111-1111-7111-8111-111111111111','R2','agent','allowed','in scope', now(),
     'aaaaaaaa-0000-7000-8000-000000000003','GET','acme.test','/api/orders/1',403, repeat('a',64), repeat('a',64)),
    ('dddddddd-0000-7000-8000-000000000003','11111111-1111-7111-8111-111111111111','R3','agent','allowed','in scope', now(),
     'aaaaaaaa-0000-7000-8000-000000000004','GET','acme.test','/api/orders/2',200, repeat('a',64), repeat('a',64)),
    ('dddddddd-0000-7000-8000-000000000009','11111111-1111-7111-8111-111111111111','R9','proxy_internal','allowed','csrf fetch', now(),
     NULL,'GET','acme.test','/login',200, repeat('a',64), repeat('a',64));

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
     'authz.horizontal','userA can read another tenant order via /api/orders/{id}');

INSERT INTO observations (id, program_id, label, agent_run_id, subject_entity_id, kind, summary,
                          provenance_kind, receipt_id) VALUES
    ('99999999-0000-7000-8000-000000000001','11111111-1111-7111-8111-111111111111','O1',
     'ffffffff-0000-7000-8000-000000000001','aaaaaaaa-0000-7000-8000-000000000002',
     'http.response','200 with order body as userA','receipt','dddddddd-0000-7000-8000-000000000001'),
    ('99999999-0000-7000-8000-000000000002','11111111-1111-7111-8111-111111111111','O2',
     'ffffffff-0000-7000-8000-000000000001','aaaaaaaa-0000-7000-8000-000000000002',
     'http.response','403 as anonymous','receipt','dddddddd-0000-7000-8000-000000000002'),
    ('99999999-0000-7000-8000-000000000003','11111111-1111-7111-8111-111111111111','O3',
     'ffffffff-0000-7000-8000-000000000001','aaaaaaaa-0000-7000-8000-000000000002',
     'http.response','200 for a foreign order id','receipt','dddddddd-0000-7000-8000-000000000003');

INSERT INTO hypothesis_evidence (hypothesis_id, observation_id, polarity, role) VALUES
    ('bbbbbbbb-0000-7000-8000-000000000001','99999999-0000-7000-8000-000000000001','supports','baseline'),
    ('bbbbbbbb-0000-7000-8000-000000000001','99999999-0000-7000-8000-000000000003','supports','variant'),
    ('bbbbbbbb-0000-7000-8000-000000000001','99999999-0000-7000-8000-000000000002','supports','control');

-- proposed -> testable -> testing -> supported
INSERT INTO hypothesis_transitions (program_id, hypothesis_id, from_status, to_status, actor_kind) VALUES
    ('11111111-1111-7111-8111-111111111111','bbbbbbbb-0000-7000-8000-000000000001','proposed','testable','llm');
INSERT INTO hypothesis_transitions (program_id, hypothesis_id, from_status, to_status, actor_kind, receipt_id) VALUES
    ('11111111-1111-7111-8111-111111111111','bbbbbbbb-0000-7000-8000-000000000001','testable','testing','runtime','dddddddd-0000-7000-8000-000000000001'),
    ('11111111-1111-7111-8111-111111111111','bbbbbbbb-0000-7000-8000-000000000001','testing','supported','runtime','dddddddd-0000-7000-8000-000000000003');

INSERT INTO tests (id, program_id, label, hypothesis_id, spec, spec_sha256, created_by_run_id) VALUES
    ('77777777-0000-7000-8000-000000000001','11111111-1111-7111-8111-111111111111','TS1',
     'bbbbbbbb-0000-7000-8000-000000000001','{"steps":[]}', repeat('c',64),
     'ffffffff-0000-7000-8000-000000000001');

INSERT INTO test_runs (id, program_id, test_id, agent_run_id, lane, outcome, assertion_results) VALUES
    ('66666666-0000-7000-8000-000000000001','11111111-1111-7111-8111-111111111111',
     '77777777-0000-7000-8000-000000000001','ffffffff-0000-7000-8000-000000000001',
     'replay','holds','{"all":true}');

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
     'authz.vertical','userA reaches an admin-only field on /api/profile');
INSERT INTO hypothesis_transitions (program_id, hypothesis_id, from_status, to_status, actor_kind) VALUES
    ('11111111-1111-7111-8111-111111111111','bbbbbbbb-0000-7000-8000-000000000002','proposed','testable','llm');

-- H3: left at `testing`, which is what a crash strands.
INSERT INTO hypotheses (id, program_id, label, subject_entity_id, property_class, statement) VALUES
    ('bbbbbbbb-0000-7000-8000-000000000003','11111111-1111-7111-8111-111111111111','H3',
     'aaaaaaaa-0000-7000-8000-000000000005','injection.sql','id parameter concatenated into SQL');
INSERT INTO hypothesis_transitions (program_id, hypothesis_id, from_status, to_status, actor_kind) VALUES
    ('11111111-1111-7111-8111-111111111111','bbbbbbbb-0000-7000-8000-000000000003','proposed','testable','llm');
INSERT INTO hypothesis_transitions (program_id, hypothesis_id, from_status, to_status, actor_kind, receipt_id) VALUES
    ('11111111-1111-7111-8111-111111111111','bbbbbbbb-0000-7000-8000-000000000003','testable','testing','runtime','dddddddd-0000-7000-8000-000000000001');

-- F2: a candidate finding with no evidence.
INSERT INTO findings (id, program_id, label, subject_entity_id, class_id, title, severity) VALUES
    ('55555555-0000-7000-8000-000000000002','11111111-1111-7111-8111-111111111111','F2',
     'aaaaaaaa-0000-7000-8000-000000000005','idor','Second candidate','low');

-- Program B, so cross-program citation can be tested.
INSERT INTO entities (id, program_id, type, label, dedup_key) VALUES
    ('aaaaaaaa-0000-7000-8000-0000000000b1','22222222-2222-7222-8222-222222222222','application','APP1','https://other.test');
INSERT INTO applications (entity_id, base_url, kind) VALUES
    ('aaaaaaaa-0000-7000-8000-0000000000b1','https://other.test','web');
INSERT INTO receipts (id, program_id, label, lane, decision, reason, ts_arrival) VALUES
    ('dddddddd-0000-7000-8000-0000000000b1','22222222-2222-7222-8222-222222222222','R1','agent','allowed','in scope', now());
