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
  'maintained by hypothesis_transitions');

SELECT t.expect_raise('C02 findings.status direct write',
  $$UPDATE findings SET status = 'rejected'
     WHERE id = '55555555-0000-7000-8000-000000000001'$$,
  'maintained by finding_transitions');

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
  'requires validated_by_test_run_id to be set first');

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

-- ---- closed by 015 (were C23/C27/C28 holes) ------------------------------

SELECT t.expect_raise('C23 transition may not cite a proxy_internal receipt',
  $$INSERT INTO hypothesis_transitions
      (program_id, hypothesis_id, from_status, to_status, actor_kind, receipt_id)
    VALUES ('11111111-1111-7111-8111-111111111111',
            'bbbbbbbb-0000-7000-8000-000000000002',
            'testable', 'testing', 'runtime',
            'dddddddd-0000-7000-8000-000000000009')$$,
  'lane proxy_internal and cannot back a transition');

-- ---- claims the schema does NOT make: these pass, and each one is a hole --
-- All three are cross-program citation, which is ticket 35's scope.

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

SELECT t.expect_raise('C27 validated may not cite a test run of an unrelated test',
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
              'dddddddd-0000-7000-8000-000000000001')$$,
  'is not a run of a test of any hypothesis of finding');

SELECT t.expect_raise('C28 a failing test run cannot validate a finding',
  $$INSERT INTO test_runs (id, program_id, test_id, agent_run_id, lane, outcome,
                           assertion_results)
      VALUES ('66666666-0000-7000-8000-000000000002',
              '11111111-1111-7111-8111-111111111111',
              '77777777-0000-7000-8000-000000000001',
              'ffffffff-0000-7000-8000-000000000001', 'replay', 'fails', '{}');
    UPDATE findings
       SET validated_by_test_run_id = '66666666-0000-7000-8000-000000000002'
     WHERE id = '55555555-0000-7000-8000-000000000001'$$,
  'findings_validated_run_holds_fk');

-- ---- 015: what the reopened decisions now enforce -------------------------

-- D6. The old guard gated on pg_trigger_depth(), so this exact payload set H1 to
-- `refuted` with no transition row. The new guard is causal, so the forged write
-- is refused however deep the stack is.
SELECT t.expect_raise('C29 a trigger cannot forge hypotheses.status',
  $$CREATE FUNCTION forge_status() RETURNS trigger LANGUAGE plpgsql AS
      'BEGIN UPDATE hypotheses SET status = ''refuted''
              WHERE id = ''bbbbbbbb-0000-7000-8000-000000000001'';
        RETURN NEW; END';
    CREATE TRIGGER programs_forge AFTER UPDATE ON programs
      FOR EACH ROW EXECUTE FUNCTION forge_status();
    UPDATE programs SET name = 'Acme BB 2'
     WHERE id = '11111111-1111-7111-8111-111111111111'$$,
  'maintained by hypothesis_transitions');

SELECT t.expect_raise('C30 a trigger cannot forge findings.status',
  $$CREATE FUNCTION forge_fstatus() RETURNS trigger LANGUAGE plpgsql AS
      'BEGIN UPDATE findings SET status = ''rejected''
              WHERE id = ''55555555-0000-7000-8000-000000000001'';
        RETURN NEW; END';
    CREATE TRIGGER programs_forge_f AFTER UPDATE ON programs
      FOR EACH ROW EXECUTE FUNCTION forge_fstatus();
    UPDATE programs SET name = 'Acme BB 2'
     WHERE id = '11111111-1111-7111-8111-111111111111'$$,
  'maintained by finding_transitions');

-- The other half of D6: a legitimate transition still moves the cache, now from
-- an AFTER trigger. The seed walked H1 to `supported` and stranded H3 at
-- `testing`; if the cache had stopped being written, both would read `proposed`.
SELECT t.expect_true('C31 a transition still updates the status cache',
  $$SELECT (SELECT status FROM hypotheses
             WHERE id = 'bbbbbbbb-0000-7000-8000-000000000001') = 'supported'
       AND (SELECT status FROM hypotheses
             WHERE id = 'bbbbbbbb-0000-7000-8000-000000000003') = 'testing'
       AND (SELECT status FROM findings
             WHERE id = '55555555-0000-7000-8000-000000000001') = 'validated'$$);

-- The stronger form of the provenance hinge: a conclusion must cite a receipt
-- that this hypothesis's own test run produced. R2 is a real agent receipt in
-- the same program, and it is still not admissible here.
SELECT t.expect_raise('C32 testing->supported citing a receipt from no test run',
  $$INSERT INTO hypothesis_evidence (hypothesis_id, observation_id, polarity, role)
      VALUES ('bbbbbbbb-0000-7000-8000-000000000003',
              '99999999-0000-7000-8000-000000000001', 'supports', 'baseline'),
             ('bbbbbbbb-0000-7000-8000-000000000003',
              '99999999-0000-7000-8000-000000000003', 'supports', 'variant'),
             ('bbbbbbbb-0000-7000-8000-000000000003',
              '99999999-0000-7000-8000-000000000002', 'supports', 'control');
    INSERT INTO hypothesis_transitions
      (program_id, hypothesis_id, from_status, to_status, actor_kind, receipt_id)
    VALUES ('11111111-1111-7111-8111-111111111111',
            'bbbbbbbb-0000-7000-8000-000000000003',
            'testing', 'supported', 'runtime',
            'dddddddd-0000-7000-8000-000000000002')$$,
  'must cite a receipt produced by a test run of hypothesis');

SELECT t.expect_ok('C33 testing->supported citing its own test run''s receipt',
  $$INSERT INTO hypothesis_evidence (hypothesis_id, observation_id, polarity, role)
      VALUES ('bbbbbbbb-0000-7000-8000-000000000003',
              '99999999-0000-7000-8000-000000000001', 'supports', 'baseline'),
             ('bbbbbbbb-0000-7000-8000-000000000003',
              '99999999-0000-7000-8000-000000000003', 'supports', 'variant'),
             ('bbbbbbbb-0000-7000-8000-000000000003',
              '99999999-0000-7000-8000-000000000002', 'supports', 'control');
    INSERT INTO hypothesis_transitions
      (program_id, hypothesis_id, from_status, to_status, actor_kind, receipt_id)
    VALUES ('11111111-1111-7111-8111-111111111111',
            'bbbbbbbb-0000-7000-8000-000000000003',
            'testing', 'supported', 'runtime',
            'dddddddd-0000-7000-8000-000000000001')$$);

-- C28's other half: the outcome cannot be rewritten after the fact either.
SELECT t.expect_raise('C34 test_runs are immutable',
  $$UPDATE test_runs SET outcome = 'fails'
     WHERE id = '66666666-0000-7000-8000-000000000001'$$,
  'test_runs rows are immutable');

-- D4. There is no narrow delete: the unit of deletion is one whole program
-- (purge_program) or one artifact blob. RESTRICT is that statement, not an
-- oversight, and it holds even with the purge flag set.
SELECT t.expect_raise('C35 a cited test run cannot be deleted',
  $$SELECT set_config('app.purging', 'on', true);
    DELETE FROM test_runs WHERE id = '66666666-0000-7000-8000-000000000001'$$,
  'findings_validated_run_holds_fk');

-- D9. Both inserts omit the label. The seed already took EP1 and EP2 by hand, so
-- passing means the collision loop advanced past both.
SELECT t.expect_ok('C36 unlabelled rows get distinct DB-assigned labels',
  $$INSERT INTO entities (id, program_id, type, dedup_key)
      VALUES ('aaaaaaaa-0000-7000-8000-0000000000e1',
              '11111111-1111-7111-8111-111111111111', 'endpoint', 'GET /api/a'),
             ('aaaaaaaa-0000-7000-8000-0000000000e2',
              '11111111-1111-7111-8111-111111111111', 'endpoint', 'GET /api/b');
    DO $c36$
    DECLARE n integer; ok boolean;
    BEGIN
        SELECT count(DISTINCT label),
               bool_and(label ~ '^EP[0-9]+$' AND label NOT IN ('EP1','EP2'))
          INTO n, ok
          FROM entities
         WHERE id IN ('aaaaaaaa-0000-7000-8000-0000000000e1',
                      'aaaaaaaa-0000-7000-8000-0000000000e2');
        IF n <> 2 THEN
            RAISE EXCEPTION 'labels collided';
        END IF;
        IF NOT ok THEN
            RAISE EXCEPTION 'wrong prefix or reused a taken label';
        END IF;
    END $c36$;
  $$);

SELECT t.expect_true('C37 the seed''s unlabelled rows were labelled',
  $$SELECT (SELECT count(*) FROM entities
             WHERE id IN ('aaaaaaaa-0000-7000-8000-0000000000c1',
                          'aaaaaaaa-0000-7000-8000-0000000000c2')
               AND label ~ '^TEC[0-9]+$') = 2
       AND (SELECT next_val FROM label_counters
             WHERE program_id = '11111111-1111-7111-8111-111111111111'
               AND prefix = 'TEC') = 3$$);

SELECT t.expect_raise('C38 an entity type with no registered prefix',
  $$DELETE FROM label_prefixes WHERE kind = 'host';
    INSERT INTO entities (program_id, type, dedup_key)
    VALUES ('11111111-1111-7111-8111-111111111111', 'host', '10.0.0.1')$$,
  'no label prefix registered for kind host');

-- Ticket 09. The profile is stricter than transition_rules, so the transition
-- that C33 accepts is refused once the skill that ran declares strict_four.
SELECT t.expect_raise('C39 a declared evidence profile is consulted',
  $$INSERT INTO tasks (id, program_id, kind, subject_entity_id, hypothesis_id,
                       skill_name, skill_sha256, evidence_profile_id)
      VALUES ('eeeeeeee-0000-7000-8000-0000000000f1',
              '11111111-1111-7111-8111-111111111111', 'hunt',
              'aaaaaaaa-0000-7000-8000-000000000005',
              'bbbbbbbb-0000-7000-8000-000000000003',
              'bb:test-sqli', repeat('7', 64), 'strict_four');
    INSERT INTO agent_runs (id, program_id, task_id, role, model, effort,
                            mission_packet)
      VALUES ('ffffffff-0000-7000-8000-0000000000f1',
              '11111111-1111-7111-8111-111111111111',
              'eeeeeeee-0000-7000-8000-0000000000f1', 'hunter', 'claude-opus-5',
              'high', '{}');
    INSERT INTO hypothesis_evidence (hypothesis_id, observation_id, polarity, role)
      VALUES ('bbbbbbbb-0000-7000-8000-000000000003',
              '99999999-0000-7000-8000-000000000001', 'supports', 'baseline'),
             ('bbbbbbbb-0000-7000-8000-000000000003',
              '99999999-0000-7000-8000-000000000003', 'supports', 'variant'),
             ('bbbbbbbb-0000-7000-8000-000000000003',
              '99999999-0000-7000-8000-000000000002', 'supports', 'control');
    INSERT INTO hypothesis_transitions
      (program_id, hypothesis_id, from_status, to_status, actor_kind,
       agent_run_id, receipt_id)
    VALUES ('11111111-1111-7111-8111-111111111111',
            'bbbbbbbb-0000-7000-8000-000000000003',
            'testing', 'supported', 'runtime',
            'ffffffff-0000-7000-8000-0000000000f1',
            'dddddddd-0000-7000-8000-000000000001')$$,
  'evidence profile strict_four is not satisfied');

SELECT t.expect_ok('C40 the same transition once the profile is satisfied',
  $$INSERT INTO tasks (id, program_id, kind, subject_entity_id, hypothesis_id,
                       skill_name, skill_sha256, evidence_profile_id)
      VALUES ('eeeeeeee-0000-7000-8000-0000000000f1',
              '11111111-1111-7111-8111-111111111111', 'hunt',
              'aaaaaaaa-0000-7000-8000-000000000005',
              'bbbbbbbb-0000-7000-8000-000000000003',
              'bb:test-sqli', repeat('7', 64), 'strict_four');
    INSERT INTO agent_runs (id, program_id, task_id, role, model, effort,
                            mission_packet)
      VALUES ('ffffffff-0000-7000-8000-0000000000f1',
              '11111111-1111-7111-8111-111111111111',
              'eeeeeeee-0000-7000-8000-0000000000f1', 'hunter', 'claude-opus-5',
              'high', '{}');
    INSERT INTO hypothesis_evidence (hypothesis_id, observation_id, polarity, role)
      VALUES ('bbbbbbbb-0000-7000-8000-000000000003',
              '99999999-0000-7000-8000-000000000001', 'supports', 'baseline'),
             ('bbbbbbbb-0000-7000-8000-000000000003',
              '99999999-0000-7000-8000-000000000003', 'supports', 'variant'),
             ('bbbbbbbb-0000-7000-8000-000000000003',
              '99999999-0000-7000-8000-000000000002', 'supports', 'control'),
             ('bbbbbbbb-0000-7000-8000-000000000003',
              '99999999-0000-7000-8000-000000000001', 'supports', 'context');
    INSERT INTO hypothesis_transitions
      (program_id, hypothesis_id, from_status, to_status, actor_kind,
       agent_run_id, receipt_id)
    VALUES ('11111111-1111-7111-8111-111111111111',
            'bbbbbbbb-0000-7000-8000-000000000003',
            'testing', 'supported', 'runtime',
            'ffffffff-0000-7000-8000-0000000000f1',
            'dddddddd-0000-7000-8000-000000000001')$$);

SELECT t.expect_raise('C41 an evidence profile with no function',
  $$INSERT INTO evidence_profiles (id, description)
    VALUES ('never_written', 'a profile whose predicate was never shipped')$$,
  'needs a function evidence_profile_never_written(uuid)');
