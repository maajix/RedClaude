-- Group B: ticket 07's re-resolution -- what survives an operator who is
-- actively trying to write history, and what the integrity check really proves.
--
-- Same harness as group A: B01..B14 run inside rolled-back subtransactions and
-- do not contaminate each other. B20..B23 are different -- they need writes in
-- one transaction to be visible to a check in a later one, so they run at top
-- level on a throwaway program that the last check purges.

SET client_min_messages = warning;
SELECT set_config('app.actor_kind', 'runtime', false);

-- ---- helpers that assert from inside a function, so expect_ok can roll the
-- ---- whole thing back -----------------------------------------------------

CREATE OR REPLACE FUNCTION t.b_write_under(p_role text, p_key text)
RETURNS void LANGUAGE plpgsql AS $$
DECLARE v_id uuid; n int; lbl text;
BEGIN
    IF p_role IS NOT NULL THEN
        EXECUTE format('SET ROLE %I', p_role);
    END IF;
    PERFORM set_config('app.actor_kind', 'runtime', true);
    -- ticket 33: 021 made a selector mandatory on every addressable type, so
    -- the helper carries one. A host entity with no selector is a row the
    -- scope grammar cannot decide, which is what the constraint refuses.
    INSERT INTO entities (program_id, type, dedup_key,
                          scope_selector_kind, scope_selector)
    VALUES ('11111111-1111-7111-8111-111111111111', 'host', p_key,
            'host', 'acme.test')
    RETURNING id INTO v_id;
    SELECT count(*) INTO n FROM events WHERE subject_id = v_id;
    SELECT label INTO lbl FROM entities WHERE id = v_id;
    IF n <> 1 THEN RAISE EXCEPTION 'no event emitted (got %)', n; END IF;
    IF lbl = ''  THEN RAISE EXCEPTION 'no label assigned'; END IF;
END $$;

CREATE OR REPLACE FUNCTION t.b_replica(p_sql text)
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    PERFORM set_config('app.actor_kind', 'runtime', true);
    PERFORM set_config('session_replication_role', 'replica', true);
    EXECUTE p_sql;
END $$;

GRANT USAGE ON SCHEMA t TO rk2_runtime;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA t TO rk2_runtime;
GRANT INSERT ON t.results TO rk2_runtime;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA t TO rk2_runtime;

-- ---- N1: the enforcement layer survives session_replication_role ----------

SELECT t.expect_true('B01 every user trigger is ENABLE ALWAYS',
  $$SELECT NOT EXISTS (
      SELECT 1 FROM pg_trigger tg JOIN pg_class c ON c.oid = tg.tgrelid
       WHERE NOT tg.tgisinternal
         AND c.relnamespace = 'public'::regnamespace
         AND tg.tgenabled <> 'A')$$);

SELECT t.expect_ok('B02 replica mode still emits, still labels',
  $$SELECT t.b_replica($x$SELECT t.b_write_under(NULL, 'b02-replica')$x$)$$);

SELECT t.expect_raise('B03 replica mode does not defeat immutability',
  $$SELECT t.b_replica($x$UPDATE observations SET kind = 'forged'
                           WHERE id = '99999999-0000-7000-8000-000000000001'$x$)$$,
  'observations rows are immutable');

SELECT t.expect_raise('B04 replica mode does not defeat the status hinge',
  $$SELECT t.b_replica($x$UPDATE hypotheses SET status = 'refuted'
                           WHERE id = 'bbbbbbbb-0000-7000-8000-000000000001'$x$)$$,
  'maintained by hypothesis_transitions');

SELECT t.expect_raise('B05 replica mode does not defeat the events envelope',
  $$SELECT t.b_replica($x$UPDATE events SET payload = '{}'::jsonb
                           WHERE id = (SELECT id FROM events LIMIT 1)$x$)$$,
  'immutable');

-- ---- N1: the privilege split ---------------------------------------------

SELECT t.expect_raise('B06 runtime role cannot disable a trigger',
  $$SET ROLE rk2_runtime;
    ALTER TABLE entities DISABLE TRIGGER entities_emit_event$$,
  'must be owner');

SELECT t.expect_raise('B07 runtime role cannot enter replica mode',
  $$SET ROLE rk2_runtime;
    SET session_replication_role = 'replica'$$,
  'permission denied');

SELECT t.expect_ok('B08 runtime role writes normally and emits',
  $$SELECT t.b_write_under('rk2_runtime', 'b08-runtime')$$);

-- ---- D2, D3: the unit of deletion is one whole program -------------------

SELECT t.expect_raise('B09 a single entity cannot be deleted',
  $$SELECT set_config('app.purging', 'on', true);
    DELETE FROM entities WHERE id = 'aaaaaaaa-0000-7000-8000-000000000005'$$,
  'violates foreign key constraint');

-- D2 as ticket 32 reported it: `events.agent_run_id ON DELETE SET NULL` used to
-- rewrite the log's attribution instead of refusing. Now it refuses.
SELECT t.expect_raise('B10 a single agent run cannot be deleted',
  $$SELECT set_config('app.purging', 'on', true);
    DELETE FROM agent_runs WHERE id = 'ffffffff-0000-7000-8000-000000000001'$$,
  'violates foreign key constraint');

-- D3 as ticket 32 reported it: deleting a task must not take unrelated
-- history with it. It now cannot delete anything at all.
SELECT t.expect_raise('B11 a single task cannot be deleted',
  $$SELECT set_config('app.purging', 'on', true);
    DELETE FROM tasks WHERE id = 'eeeeeeee-0000-7000-8000-000000000001'$$,
  'violates foreign key constraint');

SELECT t.expect_raise('B12 a finding cannot be deleted out from under its events',
  $$SELECT set_config('app.purging', 'on', true);
    DELETE FROM findings WHERE id = '55555555-0000-7000-8000-000000000001'$$,
  'violates foreign key constraint');

-- ---- the FK rule, as an invariant a later migration cannot quietly break --

SELECT t.expect_true('B13 no FK outside purge_cascade_edges has a delete action',
  $$SELECT NOT EXISTS (
      SELECT 1 FROM pg_constraint con JOIN pg_class src ON src.oid = con.conrelid
       WHERE con.contype = 'f'
         AND src.relnamespace = 'public'::regnamespace
         AND con.confdeltype IN ('c','n','d')
         AND NOT EXISTS (
               SELECT 1 FROM purge_cascade_edges e
                WHERE e.table_name = src.relname
                  AND e.column_name = (SELECT a.attname FROM pg_attribute a
                                        WHERE a.attrelid = con.conrelid
                                          AND a.attnum = con.conkey[1])))$$);

-- D1: the function that made a suppressed hypothesis unpurgeable is gone.
SELECT t.expect_true('B14 reject_mutation() no longer exists',
  $$SELECT NOT EXISTS (SELECT 1 FROM pg_proc
                        WHERE proname = 'reject_mutation'
                          AND pronamespace = 'public'::regnamespace)$$);


-- ==========================================================================
-- D5: what the integrity check catches, on committed state
--
-- These cannot run inside the harness -- a lost mutation is only visible as
-- one if the write and the check are in different transactions. They run on
-- program B-PROBE and the last of them purges it, which is also the proof
-- that a whole-program delete still succeeds under the new FK rules.
-- ==========================================================================

INSERT INTO programs (id, slug, name, platform)
VALUES ('33333333-3333-7333-8333-333333333333', 'b-probe', 'B probe', 'hackerone');

SELECT set_config('app.actor_kind', 'runtime', false);
INSERT INTO entities
    (program_id, type, dedup_key, scope_selector_kind, scope_selector)
VALUES
    ('33333333-3333-7333-8333-333333333333', 'host', 'b20-lost-mutation',
     'host', 'b20.test'),
    ('33333333-3333-7333-8333-333333333333', 'host', 'b21-suppressed',
     'host', 'b21.test');

INSERT INTO t.results (id, kind, pass, note)
SELECT 'B20 checker is silent on honest state', 'probe',
       count(*) = 0, coalesce(string_agg(problem || ' ' || detail, '; '), 'silent')
  FROM check_event_log_integrity('33333333-3333-7333-8333-333333333333');

-- An ignored-column write: `last_seen_at` only. Decision 10 emits no event,
-- so `xmin` advances past every event the row has. Before this ticket that was
-- indistinguishable from a lost mutation; `suppressed_writes` is what tells
-- them apart.
UPDATE entities SET last_seen_at = now() WHERE dedup_key = 'b21-suppressed';

INSERT INTO t.results (id, kind, pass, note)
SELECT 'B21 an ignored-column write is not a false positive', 'probe',
       count(*) = 0, coalesce(string_agg(problem || ' ' || detail, '; '), 'silent')
  FROM check_event_log_integrity('33333333-3333-7333-8333-333333333333');

INSERT INTO t.results (id, kind, pass, note)
SELECT 'B22 the suppression was recorded', 'probe', count(*) = 1, count(*)::text
  FROM suppressed_writes
 WHERE program_id = '33333333-3333-7333-8333-333333333333'
   AND table_name = 'entities';

-- Now the real thing: an operator with owner rights turns the emitter off and
-- edits a row. Nothing in the event log records it. The row's `xmin` does.
ALTER TABLE entities DISABLE TRIGGER entities_emit_event;
UPDATE entities SET in_scope = false WHERE dedup_key = 'b20-lost-mutation';
ALTER TABLE entities ENABLE ALWAYS TRIGGER entities_emit_event;

INSERT INTO t.results (id, kind, pass, note)
SELECT 'B23 checker catches a mutation made with the emitter off', 'probe',
       count(*) = 1, coalesce(string_agg(problem || ' ' || detail, '; '), 'silent')
  FROM check_event_log_integrity('33333333-3333-7333-8333-333333333333')
 WHERE problem = 'row_last_write_unaccounted';

-- And the case it cannot catch, recorded as a test rather than as a footnote:
-- a row created and deleted inside the disabled window leaves no state to ask.
-- Detection is not the control here -- privilege is (B06, B07).
ALTER TABLE entities DISABLE TRIGGER entities_emit_event;
BEGIN;
SET LOCAL app.actor_kind = 'runtime';
SET LOCAL app.purging = 'on';
INSERT INTO entities
    (program_id, type, dedup_key, scope_selector_kind, scope_selector)
VALUES ('33333333-3333-7333-8333-333333333333', 'host', 'b24-ghost',
        'host', 'b24.test');
DELETE FROM entities WHERE dedup_key = 'b24-ghost';
COMMIT;
ALTER TABLE entities ENABLE ALWAYS TRIGGER entities_emit_event;

INSERT INTO t.results (id, kind, pass, note)
SELECT 'B24 a create-and-delete in the same disabled window is undetectable',
       'probe', count(*) = 0,
       'by design: no surviving state to check; closed by B06/B07, not by detection'
  FROM check_event_log_integrity('33333333-3333-7333-8333-333333333333')
 WHERE problem = 'row_last_write_unaccounted'
   AND detail LIKE '%b24%';

-- The purge: still one statement, still succeeds, still takes everything.
BEGIN;
SET LOCAL app.purging = 'on';
DELETE FROM programs WHERE id = '33333333-3333-7333-8333-333333333333';
COMMIT;

INSERT INTO t.results (id, kind, pass, note)
SELECT 'B25 the whole-program purge still succeeds under NO ACTION', 'probe',
       (SELECT count(*) FROM programs
         WHERE id = '33333333-3333-7333-8333-333333333333') = 0
   AND (SELECT count(*) FROM events
         WHERE program_id = '33333333-3333-7333-8333-333333333333') = 0
   AND (SELECT count(*) FROM entities
         WHERE program_id = '33333333-3333-7333-8333-333333333333') = 0
   AND (SELECT count(*) FROM suppressed_writes
         WHERE program_id = '33333333-3333-7333-8333-333333333333') = 0,
       'program, entities, events and suppressed_writes all gone';

INSERT INTO t.results (id, kind, pass, note)
SELECT 'B26 checker is silent on the seeded programs after all of it', 'probe',
       count(*) = 0, coalesce(string_agg(problem || ' ' || detail, '; '), 'silent')
  FROM check_event_log_integrity();
