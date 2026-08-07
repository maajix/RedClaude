-- ===========================================================================
-- Group C -- ticket 33. The four defects consolidation had to fix, and the
-- standing checks that make a fifth instance fail the run instead of shipping.
--
-- Every case here is adversarial in the same shape: put the hole back, show
-- the check name it, take it away, show the check silent. A check that has
-- only ever been seen passing has not been seen working.
-- ===========================================================================

-- ---- C1/C2 defect 1: the fixture and migration 018 ------------------------
-- Before: the fixture wrote 'authz.horizontal' and 'http.response', which are
-- not in the vocabulary 018 defines, so the corpus and the fixture could not
-- both be applied -- FK in one order, 018's immutability guard in the other.

SELECT t.expect_raise('M01 a property_class outside the vocabulary is refused',
  $$INSERT INTO hypotheses (program_id, subject_entity_id, property_class, statement)
    VALUES ('11111111-1111-7111-8111-111111111111',
            'aaaaaaaa-0000-7000-8000-000000000002','authz.horizontal','x')$$,
  'violates foreign key constraint');

SELECT t.expect_raise('M02 an observation kind outside the vocabulary is refused',
  $$INSERT INTO observations (program_id, agent_run_id, subject_entity_id, kind,
                              summary, provenance_kind, receipt_id)
    VALUES ('11111111-1111-7111-8111-111111111111',
            'ffffffff-0000-7000-8000-000000000001',
            'aaaaaaaa-0000-7000-8000-000000000002','http.response','x','receipt',
            'dddddddd-0000-7000-8000-000000000001')$$,
  'violates foreign key constraint');

SELECT t.expect_true('M03 the seeded fixture is inside the vocabulary',
  $$SELECT (SELECT count(*) FROM hypotheses h
             WHERE NOT EXISTS (SELECT 1 FROM property_classes p WHERE p.id = h.property_class)) = 0
        AND (SELECT count(*) FROM observations o
             WHERE NOT EXISTS (SELECT 1 FROM observation_kinds k WHERE k.id = o.kind)) = 0
        AND (SELECT count(*) FROM hypotheses) > 0$$);

-- ---- C4/C5 defect 3: immutability that blocked the purge ------------------
-- 021's own guard raised on every DELETE, with no `app.purging` exemption, so
-- a program that had ever had a scope version could not be purged -- and a
-- program with no scope version is one nothing may be sent to.

DO $outer$
DECLARE p uuid := '4c000000-0000-7000-8000-00000000c001';
BEGIN
    BEGIN
        INSERT INTO programs (id, slug, name) VALUES (p, 'c4', 'C4 purge probe');
        INSERT INTO program_scope_versions (program_id, version, policy, policy_sha256)
        VALUES (p, 1, '{}'::jsonb, repeat('a',64));
        PERFORM set_config('app.purging', 'on', true);
        DELETE FROM programs WHERE id = p;
        INSERT INTO t.results (id, kind, pass, note)
        VALUES ('M04 a program carrying a scope version can be purged', 'probe', true,
                'purged with a scope version present');
        RAISE EXCEPTION 'T_ROLLBACK';
    EXCEPTION WHEN OTHERS THEN
        IF SQLERRM <> 'T_ROLLBACK' THEN
            INSERT INTO t.results (id, kind, pass, note)
            VALUES ('M04 a program carrying a scope version can be purged', 'probe', false, SQLERRM);
        END IF;
    END;
END $outer$;

-- The same probe with 021's guard put back: the purge fails and
-- check_purge_reachability() names the trigger. This is the check going from
-- silent to raising.
DO $outer$
DECLARE p uuid := '4c000000-0000-7000-8000-00000000c002';
        blocked boolean := false; named boolean := false;
BEGIN
    BEGIN
        CREATE FUNCTION t.scope_versions_are_immutable_v021() RETURNS trigger
        LANGUAGE plpgsql AS $f$ BEGIN
            RAISE EXCEPTION 'program_scope_versions is append-only'; END $f$;
        DROP TRIGGER scope_versions_immutable ON program_scope_versions;
        CREATE TRIGGER scope_versions_immutable
            BEFORE UPDATE OR DELETE ON program_scope_versions
            FOR EACH ROW EXECUTE FUNCTION t.scope_versions_are_immutable_v021();

        SELECT count(*) > 0 INTO named FROM check_purge_reachability()
         WHERE object = 'program_scope_versions.scope_versions_immutable';

        INSERT INTO programs (id, slug, name) VALUES (p, 'c5', 'C5 purge probe');
        INSERT INTO program_scope_versions (program_id, version, policy, policy_sha256)
        VALUES (p, 1, '{}'::jsonb, repeat('a',64));
        PERFORM set_config('app.purging', 'on', true);
        BEGIN
            DELETE FROM programs WHERE id = p;
        EXCEPTION WHEN OTHERS THEN blocked := true;
        END;

        INSERT INTO t.results (id, kind, pass, note)
        VALUES ('M05 the 021 guard blocks the purge and the check names it', 'probe',
                blocked AND named,
                'purge blocked=' || blocked || ' check named it=' || named);
        RAISE EXCEPTION 'T_ROLLBACK';
    EXCEPTION WHEN OTHERS THEN
        IF SQLERRM <> 'T_ROLLBACK' THEN
            INSERT INTO t.results (id, kind, pass, note)
            VALUES ('M05 the 021 guard blocks the purge and the check names it', 'probe', false, SQLERRM);
        END IF;
    END;
END $outer$;

-- ---- C6 defect 4: resume no longer orphans session.bound -----------------

DO $outer$
DECLARE p uuid := '4c000000-0000-7000-8000-00000000c006';
        r uuid := '4c000000-0000-7000-8000-00000000c106';
        s uuid;
        orphans bigint;
BEGIN
    BEGIN
        INSERT INTO programs (id, slug, name) VALUES (p, 'c6', 'C6 resume probe');
        INSERT INTO agent_runs (id, program_id, role, model, effort, mission_packet, runs_as)
        SELECT r, p, ar.role, ar.model, ar.effort, ar.mission_packet, ar.runs_as
          FROM agent_runs ar LIMIT 1;
        INSERT INTO agent_sessions (program_id, session_id, agent_run_id, task_id)
        VALUES (p, 'sess-c6', r, NULL) RETURNING id INTO s;
        UPDATE agent_runs SET finished_at = now() WHERE id = r;

        PERFORM resume_program(p);

        SELECT count(*) INTO orphans FROM check_event_log_integrity(p);

        INSERT INTO t.results (id, kind, pass, note)
        VALUES ('M06 resume unbinds the session instead of orphaning session.bound', 'probe',
                orphans = 0
                AND EXISTS (SELECT 1 FROM agent_sessions x WHERE x.id = s AND x.unbound_at IS NOT NULL)
                AND EXISTS (SELECT 1 FROM events e WHERE e.subject_id = s AND e.type = 'session.bound'),
                'integrity problems after resume = ' || orphans);
        RAISE EXCEPTION 'T_ROLLBACK';
    EXCEPTION WHEN OTHERS THEN
        IF SQLERRM <> 'T_ROLLBACK' THEN
            INSERT INTO t.results (id, kind, pass, note)
            VALUES ('M06 resume unbinds the session instead of orphaning session.bound', 'probe', false, SQLERRM);
        END IF;
    END;
END $outer$;

SELECT t.expect_true('M07 one live binding per (program, session, sdk agent) still holds',
  $$SELECT count(*) = 1 FROM pg_indexes
     WHERE tablename = 'agent_sessions' AND indexname = 'agent_sessions_live_binding_idx'$$);

SELECT t.expect_true('M08 no function deletes an agent_sessions row',
  $$SELECT count(*) = 0 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname = 'public' AND p.prosrc LIKE '%DELETE FROM agent_sessions%'$$);

-- ---- C9..M12 defect 2: the read surface is a registry ---------------------

SELECT t.expect_true('M09 rk2_state holds no relation-level privilege anywhere',
  $$SELECT count(*) = 0 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public' AND c.relkind IN ('r','v','m')
       AND has_table_privilege('rk2_state', c.oid, 'SELECT')$$);

-- The concrete instance: 021 added programs.scope_version to a table 020 had
-- granted whole, so it reached the agent connection without a decision.
SELECT t.expect_true('M10 a column added after the grant is not readable by the agent',
  $$SELECT NOT has_column_privilege('rk2_state','programs','scope_version','SELECT')
        AND has_column_privilege('rk2_state','programs','slug','SELECT')$$);

-- Migration 029, simulated: a new column reaches nothing and the check stays
-- silent; a relation-level grant is named immediately.
DO $outer$
DECLARE reach boolean; before bigint; after_grant bigint;
BEGIN
    BEGIN
        SELECT count(*) INTO before FROM check_state_grants();
        ALTER TABLE receipts ADD COLUMN ticket33_probe text;
        reach := has_column_privilege('rk2_state','receipts','ticket33_probe','SELECT');
        GRANT SELECT ON receipts TO rk2_state;
        SELECT count(*) INTO after_grant FROM check_state_grants()
         WHERE problem = 'state_holds_relation_grant' AND object = 'receipts';

        INSERT INTO t.results (id, kind, pass, note)
        VALUES ('M11 a new column is unreadable and a relation grant is caught', 'probe',
                before = 0 AND NOT reach AND after_grant > 0,
                'silent before=' || before || ' new column readable=' || reach
                  || ' relation grant reported=' || after_grant);
        RAISE EXCEPTION 'T_ROLLBACK';
    EXCEPTION WHEN OTHERS THEN
        IF SQLERRM <> 'T_ROLLBACK' THEN
            INSERT INTO t.results (id, kind, pass, note)
            VALUES ('M11 a new column is unreadable and a relation grant is caught', 'probe', false, SQLERRM);
        END IF;
    END;
END $outer$;

SELECT t.expect_true('M12 the registry and the grants agree exactly',
  $$SELECT count(*) = 0 FROM check_state_grants()$$);

-- ---- M13..M15 defect 5: RLS coverage is an end-of-run invariant -----------

DO $outer$
DECLARE missing bigint; healed integer; after_heal bigint;
BEGIN
    BEGIN
        CREATE TABLE drift_probe (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            program_id uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE);
        SELECT count(*) INTO missing FROM check_rls_coverage() WHERE object = 'drift_probe';
        SELECT apply_state_rls() INTO healed;
        SELECT count(*) INTO after_heal FROM check_rls_coverage() WHERE object = 'drift_probe';

        INSERT INTO t.results (id, kind, pass, note)
        VALUES ('M13 a table added without RLS is named, then healed by the finalizer', 'probe',
                missing = 3 AND healed >= 3 AND after_heal = 0,
                'reported=' || missing || ' created=' || healed || ' after=' || after_heal);
        RAISE EXCEPTION 'T_ROLLBACK';
    EXCEPTION WHEN OTHERS THEN
        IF SQLERRM <> 'T_ROLLBACK' THEN
            INSERT INTO t.results (id, kind, pass, note)
            VALUES ('M13 a table added without RLS is named, then healed by the finalizer', 'probe', false, SQLERRM);
        END IF;
    END;
END $outer$;

DO $outer$
DECLARE n bigint;
BEGIN
    BEGIN
        ALTER TABLE observations DISABLE ROW LEVEL SECURITY;
        SELECT count(*) INTO n FROM check_rls_coverage()
         WHERE problem = 'rls_disabled' AND object = 'observations';
        INSERT INTO t.results (id, kind, pass, note)
        VALUES ('M14 RLS switched off on a scoped table is named', 'probe', n = 1,
                'reported ' || n);
        RAISE EXCEPTION 'T_ROLLBACK';
    EXCEPTION WHEN OTHERS THEN
        IF SQLERRM <> 'T_ROLLBACK' THEN
            INSERT INTO t.results (id, kind, pass, note)
            VALUES ('M14 RLS switched off on a scoped table is named', 'probe', false, SQLERRM);
        END IF;
    END;
END $outer$;

-- ---- M15/M16: the registry that keeps the registry honest ----------------

DO $outer$
DECLARE n bigint;
BEGIN
    BEGIN
        CREATE FUNCTION check_ticket33_unregistered()
        RETURNS TABLE (problem text, object text, detail text)
        LANGUAGE sql STABLE AS $f$ SELECT 'x','y','z' $f$;
        SELECT count(*) INTO n FROM check_check_registration()
         WHERE object = 'check_ticket33_unregistered';
        INSERT INTO t.results (id, kind, pass, note)
        VALUES ('M15 a new checker with no standing_checks row is named', 'probe', n = 1,
                'reported ' || n);
        RAISE EXCEPTION 'T_ROLLBACK';
    EXCEPTION WHEN OTHERS THEN
        IF SQLERRM <> 'T_ROLLBACK' THEN
            INSERT INTO t.results (id, kind, pass, note)
            VALUES ('M15 a new checker with no standing_checks row is named', 'probe', false, SQLERRM);
        END IF;
    END;
END $outer$;

INSERT INTO t.results (id, kind, pass, note)
SELECT 'M16 every standing check is silent on the seeded database', 'probe',
       coalesce(sum(problems), 0) = 0,
       coalesce(string_agg(name || '=' || problems, ', ') FILTER (WHERE problems > 0),
                (SELECT count(*)::text || ' checks, all silent' FROM standing_checks))
  FROM run_standing_checks();

-- ---- M17: the two roles are two connections, and neither is the other -----

SELECT t.expect_true('M17 rk2_state cannot write anywhere, at any granularity',
  $$SELECT count(*) = 0 FROM check_state_grants()
     WHERE problem IN ('state_holds_write_grant','state_holds_relation_grant')$$);

SELECT t.expect_true('M18 no rk2_ role can create a role or bypass RLS',
  $$SELECT count(*) = 0 FROM pg_roles
     WHERE rolname LIKE 'rk2\_%' AND (rolcreaterole OR rolbypassrls OR rolsuper)$$);

SELECT t.expect_true('M19 neither model-reachable connection is a member of rk2_human',
  $$SELECT NOT pg_has_role('rk2_runtime','rk2_human','USAGE')
        AND NOT pg_has_role('rk2_state','rk2_human','USAGE')$$);
