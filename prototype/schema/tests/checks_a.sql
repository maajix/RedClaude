-- Group A: the constraints and triggers the three tickets claim to enforce.
-- Every check runs in a rolled-back subtransaction, so order does not matter.
-- UUIDs are written out because psql does not interpolate :variables inside
-- dollar-quoted strings.
--
--   P1  11111111-1111-7111-8111-111111111111   program acme
--   P2  22222222-2222-7222-8222-222222222222   program other
--   APP aaaaaaaa-0000-7000-8000-000000000001   application, program A
--   EP1 aaaaaaaa-0000-7000-8000-000000000002
--   ID1 aaaaaaaa-0000-7000-8000-000000000003   identity anon
--   ID2 aaaaaaaa-0000-7000-8000-000000000004   identity userA
--   APPB aaaaaaaa-0000-7000-8000-0000000000b1  application, program B
--   H1/H2/H3 bbbbbbbb-...-000000000001/2/3     supported / testable / testing
--   TR1 cccccccc-0000-7000-8000-000000000001
--   R1/R9 dddddddd-...-000000000001 / ...009   agent / proxy_internal
--   RB  dddddddd-0000-7000-8000-0000000000b1   agent receipt, program B
--   T1  eeeeeeee-0000-7000-8000-000000000001
--   A1  ffffffff-0000-7000-8000-000000000001
--   O1/O2/O3 99999999-...-000000000001/2/3
--   F1/F2 55555555-...-000000000001/2          validated / candidate
--   TRUN 66666666-0000-7000-8000-000000000001  test run of H1's test

SET client_min_messages = warning;
SELECT set_config('app.actor_kind', 'runtime', false);

-- ---- status cache is not writable ----------------------------------------

SELECT t.expect_raise('C01 hypotheses.status direct write',
  $$UPDATE hypotheses SET status = 'refuted'
     WHERE id = 'bbbbbbbb-0000-7000-8000-000000000001'$$,
  'maintained by the transition table');

SELECT t.expect_raise('C02 findings.status direct write',
  $$UPDATE findings SET status = 'rejected'
     WHERE id = '55555555-0000-7000-8000-000000000001'$$,
  'maintained by the transition table');

-- ---- the provenance hinge: testable -> testing ---------------------------

SELECT t.expect_raise('C03 testable->testing as llm',
  $$INSERT INTO hypothesis_transitions
      (program_id, hypothesis_id, from_status, to_status, actor_kind, receipt_id)
    VALUES ('11111111-1111-7111-8111-111111111111',
            'bbbbbbbb-0000-7000-8000-000000000002',
            'testable', 'testing', 'llm',
            'dddddddd-0000-7000-8000-000000000001')$$,
  'requires actor_kind runtime');

SELECT t.expect_raise('C04 testable->testing without receipt',
  $$INSERT INTO hypothesis_transitions
      (program_id, hypothesis_id, from_status, to_status, actor_kind)
    VALUES ('11111111-1111-7111-8111-111111111111',
            'bbbbbbbb-0000-7000-8000-000000000002',
            'testable', 'testing', 'runtime')$$,
  'requires a tool receipt');

SELECT t.expect_ok('C05 testable->testing as runtime with receipt',
  $$INSERT INTO hypothesis_transitions
      (program_id, hypothesis_id, from_status, to_status, actor_kind, receipt_id)
    VALUES ('11111111-1111-7111-8111-111111111111',
            'bbbbbbbb-0000-7000-8000-000000000002',
            'testable', 'testing', 'runtime',
            'dddddddd-0000-7000-8000-000000000001')$$);

SELECT t.expect_raise('C06 stale from_status is refused',
  $$INSERT INTO hypothesis_transitions
      (program_id, hypothesis_id, from_status, to_status, actor_kind)
    VALUES ('11111111-1111-7111-8111-111111111111',
            'bbbbbbbb-0000-7000-8000-000000000002',
            'proposed', 'testable', 'llm')$$,
  'stale transition');

SELECT t.expect_raise('C07 unlisted transition is refused',
  $$INSERT INTO hypothesis_transitions
      (program_id, hypothesis_id, from_status, to_status, actor_kind, receipt_id)
    VALUES ('11111111-1111-7111-8111-111111111111',
            'bbbbbbbb-0000-7000-8000-000000000002',
            'testable', 'supported', 'runtime',
            'dddddddd-0000-7000-8000-000000000001')$$,
  'illegal transition');

-- ---- evidence gates ------------------------------------------------------

SELECT t.expect_raise('C08 testing->supported without evidence',
  $$INSERT INTO hypothesis_transitions
      (program_id, hypothesis_id, from_status, to_status, actor_kind, receipt_id)
    VALUES ('11111111-1111-7111-8111-111111111111',
            'bbbbbbbb-0000-7000-8000-000000000003',
            'testing', 'supported', 'runtime',
            'dddddddd-0000-7000-8000-000000000001')$$,
  'needs 2 evidence rows');

SELECT t.expect_raise('C09 testing->supported without a control',
  $$INSERT INTO hypothesis_evidence (hypothesis_id, observation_id, polarity, role)
      VALUES ('bbbbbbbb-0000-7000-8000-000000000003',
              '99999999-0000-7000-8000-000000000001', 'supports', 'baseline'),
             ('bbbbbbbb-0000-7000-8000-000000000003',
              '99999999-0000-7000-8000-000000000003', 'supports', 'variant');
    INSERT INTO hypothesis_transitions
      (program_id, hypothesis_id, from_status, to_status, actor_kind, receipt_id)
    VALUES ('11111111-1111-7111-8111-111111111111',
            'bbbbbbbb-0000-7000-8000-000000000003',
            'testing', 'supported', 'runtime',
            'dddddddd-0000-7000-8000-000000000001')$$,
  'needs a control observation');

SELECT t.expect_raise('C10 validated->reported needs a human',
  $$INSERT INTO finding_transitions
      (program_id, finding_id, from_status, to_status, actor_kind)
    VALUES ('11111111-1111-7111-8111-111111111111',
            '55555555-0000-7000-8000-000000000001',
            'validated', 'reported', 'runtime')$$,
  'requires actor_kind human');

SELECT t.expect_raise('C11 finding cannot be validated with no test run',
  $$INSERT INTO finding_evidence (finding_id, observation_id, ordinal)
      VALUES ('55555555-0000-7000-8000-000000000002',
              '99999999-0000-7000-8000-000000000001', 1),
             ('55555555-0000-7000-8000-000000000002',
              '99999999-0000-7000-8000-000000000002', 2);
    INSERT INTO finding_transitions
      (program_id, finding_id, from_status, to_status, actor_kind)
      VALUES ('11111111-1111-7111-8111-111111111111',
              '55555555-0000-7000-8000-000000000002',
              'candidate', 'validating', 'runtime');
    INSERT INTO finding_transitions
      (program_id, finding_id, from_status, to_status, actor_kind, receipt_id)
      VALUES ('11111111-1111-7111-8111-111111111111',
              '55555555-0000-7000-8000-000000000002',
              'validating', 'validated', 'runtime',
              'dddddddd-0000-7000-8000-000000000001')$$,
  'findings_check');

-- ---- observations --------------------------------------------------------

SELECT t.expect_raise('C12 observation backed by a proxy_internal receipt',
  $$INSERT INTO observations (program_id, label, agent_run_id, subject_entity_id,
                              kind, summary, provenance_kind, receipt_id)
    VALUES ('11111111-1111-7111-8111-111111111111', 'OX',
            'ffffffff-0000-7000-8000-000000000001',
            'aaaaaaaa-0000-7000-8000-000000000002',
            'http.response', 'x', 'receipt',
            'dddddddd-0000-7000-8000-000000000009')$$,
  'lane proxy_internal');

SELECT t.expect_raise('C13 observations are immutable',
  $$UPDATE observations SET summary = 'rewritten'
     WHERE id = '99999999-0000-7000-8000-000000000001'$$,
  'observations rows are immutable');

SELECT t.expect_raise('C14 row write with app.actor_kind unset',
  $$SELECT set_config('app.actor_kind', '', true);
    INSERT INTO entities (program_id, type, label, dedup_key)
    VALUES ('11111111-1111-7111-8111-111111111111', 'technology', 'TX', 'nginx')$$,
  'app.actor_kind is unset');

-- ---- scheduler uniqueness ------------------------------------------------

SELECT t.expect_raise('C15 second live recon task, NULL hypothesis_id',
  $$INSERT INTO tasks (program_id, label, kind, subject_entity_id)
    VALUES ('11111111-1111-7111-8111-111111111111', 'T2', 'recon',
            'aaaaaaaa-0000-7000-8000-000000000001')$$,
  'tasks_live_dedup_idx');

SELECT t.expect_ok('C16 same task again once the first is done',
  $$UPDATE tasks SET status = 'done'
     WHERE id = 'eeeeeeee-0000-7000-8000-000000000001';
    INSERT INTO tasks (program_id, label, kind, subject_entity_id)
    VALUES ('11111111-1111-7111-8111-111111111111', 'T2', 'recon',
            'aaaaaaaa-0000-7000-8000-000000000001')$$);

SELECT t.expect_raise('C17 second active scheduler_weights row',
  $$INSERT INTO scheduler_weights
      (version, w_gain, w_impact, cost_reference_tokens, cost_floor, cost_prior,
       confidence_prior, shrinkage_n0, near_match_high, near_match_low,
       slate_size, lease_ttl, max_attempts, active)
    VALUES (2, 0.5, 0.5, 200000, 0.01, '{}', 0.5, 5, 0.9, 0.8, 5,
            interval '30 minutes', 3, true)$$,
  'scheduler_weights_one_active');

SELECT t.expect_ok('C18 second inactive scheduler_weights row',
  $$INSERT INTO scheduler_weights
      (version, w_gain, w_impact, cost_reference_tokens, cost_floor, cost_prior,
       confidence_prior, shrinkage_n0, near_match_high, near_match_low,
       slate_size, lease_ttl, max_attempts, active)
    VALUES (2, 0.5, 0.5, 200000, 0.01, '{}', 0.5, 5, 0.9, 0.8, 5,
            interval '30 minutes', 3, false)$$);

SELECT t.expect_raise('C19 second default lane for one kind',
  $$INSERT INTO scheduler_lanes (program_id, kind, min_slots, max_slots)
    VALUES (NULL, 'recon', 0, 9)$$,
  'scheduler_lanes_program_id_kind_key');

-- ---- surface uniqueness --------------------------------------------------

SELECT t.expect_raise('C20 identity slot name reused by another program',
  $$INSERT INTO entities (id, program_id, type, label, dedup_key)
      VALUES ('aaaaaaaa-0000-7000-8000-0000000000b2',
              '22222222-2222-7222-8222-222222222222', 'identity', 'ID1',
              'identity:userA');
    INSERT INTO identities (entity_id, slot_name, class, secret_ref)
      VALUES ('aaaaaaaa-0000-7000-8000-0000000000b2', 'userA', 'user',
              'op://x/y/z')$$,
  'identities_slot_idx');

SELECT t.expect_raise('C21 detail row pinned to the wrong entity type',
  $$INSERT INTO endpoints (entity_id, application_id, method, path_template)
    VALUES ('aaaaaaaa-0000-7000-8000-000000000003',
            'aaaaaaaa-0000-7000-8000-000000000001', 'GET', '/whatever')$$,
  'endpoints_entity_id_entity_type_fkey');

SELECT t.expect_raise('C22 second live lease on one identity',
  $$INSERT INTO identity_leases (program_id, identity_entity_id,
                                 holder_agent_run_id, expires_at)
    VALUES ('11111111-1111-7111-8111-111111111111',
            'aaaaaaaa-0000-7000-8000-000000000004',
            'ffffffff-0000-7000-8000-000000000001',
            now() + interval '5 minutes')$$,
  'identity_leases_exclusive_idx');

-- ---- claims the schema does NOT make: these pass, and each one is a hole --

SELECT t.expect_ok('C23 HOLE transition may cite a proxy_internal receipt',
  $$INSERT INTO hypothesis_transitions
      (program_id, hypothesis_id, from_status, to_status, actor_kind, receipt_id)
    VALUES ('11111111-1111-7111-8111-111111111111',
            'bbbbbbbb-0000-7000-8000-000000000002',
            'testable', 'testing', 'runtime',
            'dddddddd-0000-7000-8000-000000000009')$$);

SELECT t.expect_ok('C24 HOLE transition may cite another program''s receipt',
  $$INSERT INTO hypothesis_transitions
      (program_id, hypothesis_id, from_status, to_status, actor_kind, receipt_id)
    VALUES ('11111111-1111-7111-8111-111111111111',
            'bbbbbbbb-0000-7000-8000-000000000002',
            'testable', 'testing', 'runtime',
            'dddddddd-0000-7000-8000-0000000000b1')$$);

SELECT t.expect_ok('C25 HOLE transition program_id may disagree with its hypothesis',
  $$INSERT INTO hypothesis_transitions
      (program_id, hypothesis_id, from_status, to_status, actor_kind, receipt_id)
    VALUES ('22222222-2222-7222-8222-222222222222',
            'bbbbbbbb-0000-7000-8000-000000000002',
            'testable', 'testing', 'runtime',
            'dddddddd-0000-7000-8000-000000000001')$$);

SELECT t.expect_ok('C26 HOLE hypothesis may point at another program''s entity',
  $$INSERT INTO hypotheses (program_id, label, subject_entity_id, property_class,
                            statement)
    VALUES ('11111111-1111-7111-8111-111111111111', 'HX',
            'aaaaaaaa-0000-7000-8000-0000000000b1', 'authz.horizontal',
            'cross-program subject')$$);

SELECT t.expect_ok('C27 HOLE validated may cite a test run of an unrelated test',
  $$INSERT INTO finding_evidence (finding_id, observation_id, ordinal)
      VALUES ('55555555-0000-7000-8000-000000000002',
              '99999999-0000-7000-8000-000000000001', 1),
             ('55555555-0000-7000-8000-000000000002',
              '99999999-0000-7000-8000-000000000002', 2);
    INSERT INTO finding_transitions
      (program_id, finding_id, from_status, to_status, actor_kind)
      VALUES ('11111111-1111-7111-8111-111111111111',
              '55555555-0000-7000-8000-000000000002',
              'candidate', 'validating', 'runtime');
    UPDATE findings
       SET validated_by_test_run_id = '66666666-0000-7000-8000-000000000001'
     WHERE id = '55555555-0000-7000-8000-000000000002';
    INSERT INTO finding_transitions
      (program_id, finding_id, from_status, to_status, actor_kind, receipt_id)
      VALUES ('11111111-1111-7111-8111-111111111111',
              '55555555-0000-7000-8000-000000000002',
              'validating', 'validated', 'runtime',
              'dddddddd-0000-7000-8000-000000000001')$$);

SELECT t.expect_ok('C28 HOLE a failing test run can still validate a finding',
  $$INSERT INTO test_runs (id, program_id, test_id, agent_run_id, lane, outcome,
                           assertion_results)
      VALUES ('66666666-0000-7000-8000-000000000002',
              '11111111-1111-7111-8111-111111111111',
              '77777777-0000-7000-8000-000000000001',
              'ffffffff-0000-7000-8000-000000000001', 'replay', 'fails', '{}');
    UPDATE findings
       SET validated_by_test_run_id = '66666666-0000-7000-8000-000000000002'
     WHERE id = '55555555-0000-7000-8000-000000000001'$$);
