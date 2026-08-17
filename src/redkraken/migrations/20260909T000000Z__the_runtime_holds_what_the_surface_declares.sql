-- ph2-66 -- Narrow the runtime role's privilege surface
--
-- What the runtime connection may do is decided today by one statement in
-- `0029_roles_and_grants.sql`:
--
--     ALTER DEFAULT PRIVILEGES FOR ROLE rk2_owner IN SCHEMA public
--           GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO rk2_runtime;
--     ALTER DEFAULT PRIVILEGES FOR ROLE rk2_owner IN SCHEMA public
--           GRANT EXECUTE ON FUNCTIONS TO rk2_runtime;
--
-- Every table and every function the corpus has created since has arrived with
-- those grants already on it. That is why a later migration writing
-- `REVOKE ALL ON FUNCTION f() FROM PUBLIC` does not close `f()`: PUBLIC loses
-- the grant and `rk2_runtime` keeps the one it was handed at creation. The
-- author reads the revoke and believes the verb is gated; the catalogue says
-- otherwise.
--
-- The ticket's own account of the damage is worth correcting, because the
-- measurement disagrees with it. `answer_decision(text,text,text,interval)` was
-- named as the example and is not one: `20260814T020000Z` closed it, and the
-- catalogue now grants it to `rk2_human` and `rk2_restore` only. What the
-- default privileges actually leave open is six verbs, every one of them gated
-- to `rk2_proxy` and every one of them called from `proxy.py` alone:
--
--     authorize_identity_egress_address(text,text,text,integer,text)
--     authorize_identity_egress_request(text,text,text,text,integer,text,text)
--     confirm_required_headers_open(text,uuid,text)
--     ensure_proxy_wire_keying(text,bytea,bytea)
--     open_required_headers(text)
--     write_blocked_receipt(uuid,jsonb,text)
--
-- Six is not the interesting number. The interesting number is that the corpus
-- holds 251 functions revoked from PUBLIC and `rk2_runtime` can execute 231 of
-- them, so the next gated verb somebody writes will be open to the runtime for
-- the same reason these are, and the revoke in its own migration will read as
-- though it were not. The same holds one level up: 172 of 196 tables are
-- SELECT/INSERT/UPDATE/DELETE to the runtime, including every registry that
-- decides what the checks check.
--
-- So this file does two things and they are not the same thing. It closes what
-- is open, once. And it replaces the rule that opened them -- a default grant,
-- applied at creation, invisible at the call site -- with two registries that
-- name the surface, a finalizer that grants exactly what they name, and a
-- standing check that fails on anything held beyond them. After this file a new
-- object is closed to the runtime when it is created; opening it means writing
-- the row that says so.
--
-- Sections:
--   1. The default grants go
--   2. The two registries, and the two views that define the surface
--   3. What the runtime holds today, written down
--   4. The narrowings: registries, key tables, the event log
--   5. The sweep: take away everything the registries do not name
--   6. apply_runtime_grants(), the finalizer
--   7. check_runtime_privileges(), the standing check
--   8. check_runtime_connection() asks the registry instead of every table
--   9. The one write `secret_kek` still needs
--  10. Wiring
--  11. The invariants this file must not have broken


-- ---------------------------------------------------------------------------
-- 1. The default grants go
-- ---------------------------------------------------------------------------
--
-- Sequences keep theirs. A sequence is reachable only through the column that
-- defaults from it, so its grant adds no surface beyond the table's, and the
-- alternative is a third registry that would never say anything the second one
-- did not already say.
--
-- Tables and functions lose theirs, and this happens first so that the four
-- objects below are born closed. Default privileges apply at creation and never
-- afterwards: nothing already in the database changes because of these two
-- statements, which is why sections 3 to 5 exist.

ALTER DEFAULT PRIVILEGES FOR ROLE rk2_owner IN SCHEMA public
    REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM rk2_runtime;
ALTER DEFAULT PRIVILEGES FOR ROLE rk2_owner IN SCHEMA public
    REVOKE EXECUTE ON FUNCTIONS FROM rk2_runtime;


-- ---------------------------------------------------------------------------
-- 2. The two registries, and the two views that define the surface
-- ---------------------------------------------------------------------------

-- One row per privilege rather than one row per table with a privilege string:
-- the checks below are set differences, and a set difference over rows is a
-- join, while a set difference over 'SIUD' is string parsing.
CREATE TABLE runtime_table_surface (
    table_name text NOT NULL,
    privilege  text NOT NULL
        CHECK (privilege IN ('SELECT','INSERT','UPDATE','DELETE')),
    added_by   text NOT NULL DEFAULT '66',
    PRIMARY KEY (table_name, privilege)
);

COMMENT ON TABLE runtime_table_surface IS
  'What the runtime connection may do to each relation in `public`, one row per privilege. This table is the grant: `apply_runtime_grants()` grants what it names and `check_runtime_privileges()` fails on anything `rk2_runtime` holds beyond it. TRUNCATE and REFERENCES are absent by construction -- there is no row shape that could name them.';

-- Identified by name and argument types rather than by oid, because an oid does
-- not survive the dump and restore this surface has to hold across, and rather
-- than by name alone, because the corpus overloads.
CREATE TABLE runtime_verb_surface (
    verb     text PRIMARY KEY,
    added_by text NOT NULL DEFAULT '66',
    note     text NOT NULL
);

COMMENT ON TABLE runtime_verb_surface IS
  'The functions revoked from PUBLIC that the runtime connection may still execute, written as `name(argument types)`. A function open to PUBLIC needs no row: the rule this registry states is that closing a function to PUBLIC now closes it to the runtime as well, and this names the exceptions.';

-- Both registries and both checks read the surface through these, so what
-- "the surface" means is written once.
--
-- `oidvectortypes` rather than `pg_get_function_identity_arguments`, which
-- renders parameter names as well as types and would make a row here depend on
-- what somebody called an argument. Type names render the way `regprocedure`
-- renders them, through the caller's search_path, so a corpus type outside it
-- would render qualified on one side of a comparison and bare on the other --
-- which is a loud failure rather than a quiet one: every row would fail
-- `runtime_verb_surface_names_missing_function` at once.
CREATE VIEW runtime_verbs AS
    SELECT p.oid,
           p.proname || '(' || pg_catalog.oidvectortypes(p.proargtypes) || ')' AS verb,
           NOT has_function_privilege('public', p.oid, 'EXECUTE') AS closed,
           has_function_privilege('rk2_runtime', p.oid, 'EXECUTE') AS held
      FROM pg_proc p
     WHERE p.pronamespace = 'public'::regnamespace
       AND p.prokind = 'f'
       AND NOT EXISTS (SELECT 1 FROM pg_depend d
                        WHERE d.classid = 'pg_proc'::regclass
                          AND d.objid = p.oid AND d.deptype = 'e');

COMMENT ON VIEW runtime_verbs IS
  'Every function in `public` the corpus owns, whether it is closed to PUBLIC, and whether rk2_runtime can execute it. Extension functions are excluded: pgcrypto and vector are not the corpus''s to gate.';

-- Views and materialized views are in scope alongside tables: a view is a read
-- grant on whatever it selects, and 029's default privileges handed the runtime
-- all four verbs on every one of them.
CREATE VIEW runtime_relations AS
    SELECT c.oid, c.relname AS table_name, p.priv AS privilege,
           has_table_privilege('rk2_runtime', c.oid, p.priv) AS held
      FROM pg_class c
      CROSS JOIN (VALUES ('SELECT'),('INSERT'),('UPDATE'),('DELETE')) AS p(priv)
     WHERE c.relnamespace = 'public'::regnamespace
       AND c.relkind IN ('r','p','v','m')
       AND NOT EXISTS (SELECT 1 FROM pg_depend d
                        WHERE d.classid = 'pg_class'::regclass
                          AND d.objid = c.oid AND d.deptype = 'e');

COMMENT ON VIEW runtime_relations IS
  'Every relation in `public` crossed with the four privileges a row of runtime_table_surface can name, and whether rk2_runtime holds each.';


-- ---------------------------------------------------------------------------
-- 3. What the runtime holds today, written down
-- ---------------------------------------------------------------------------
--
-- The seed is the catalogue, not a list. A list written here would be a second
-- copy of 196 tables and 231 functions, wrong the first time somebody added the
-- 197th, and the whole point of the registry is that it stops being possible to
-- be wrong about this quietly. What section 4 narrows is written as a deletion
-- from the seed, so the diff between "what the corpus grew" and "what the
-- runtime should have" is the only thing this file states by hand.

INSERT INTO runtime_table_surface (table_name, privilege, added_by)
SELECT r.table_name, r.privilege, '66-seed' FROM runtime_relations r WHERE r.held;

INSERT INTO runtime_verb_surface (verb, added_by, note)
SELECT v.verb, '66-seed',
       'granted at creation by 029''s default privileges, before this file made the grant explicit'
  FROM runtime_verbs v
 WHERE v.closed AND v.held;

-- Criterion 1, the keyholder side. Arm 4 of check_runtime_privileges() is the
-- standing half of the criterion: a verb the runtime holds that no row declares
-- is a leak, and stays one. There is deliberately no mirror arm for "a declared
-- verb a keyholder also holds", because holding is not leaking. Twenty-eight of
-- the verbs seeded just above are executable by a keyholder too: twenty-six
-- read-only reporting and analysis verbs shared with rk2_human (read_kill_chain,
-- the rk2_chain_* family, rk2_finding_cell, ...), state_severity -- a VOLATILE
-- verb the runtime and rk2_human both write state through -- and run_contacts,
-- shared with rk2_proxy. A mechanical check on co-grant would fail on all
-- twenty-eight true shares, so which of the runtime's verbs a keyholder may also
-- reach is a measurement this seed records, not a rule a check can derive.
-- What criterion 1 forbids is the runtime reaching a keyholder's gated WRITE,
-- and that holds because the write verbs are revoked from the role, not shared
-- with it: answer_decision and the three operator verbs are rk2_human's alone
-- (20260814's operator-answer migration revoked them from rk2_runtime; the seed
-- above never held them, so nothing here deletes them), asserted by
-- test_no_connection_a_model_reaches_may_execute_an_operator_verb. The six write
-- verbs on the proxy's side are what section 4 removes next.

-- The four objects section 2 created are not in either seed: section 1 ran
-- first, so they arrived with no runtime grant at all. Read-only, and stated
-- rather than inherited.
INSERT INTO runtime_table_surface (table_name, privilege) VALUES
    ('runtime_table_surface', 'SELECT'),
    ('runtime_verb_surface',  'SELECT'),
    ('runtime_relations',     'SELECT'),
    ('runtime_verbs',         'SELECT');


-- ---------------------------------------------------------------------------
-- 4. The narrowings: registries, key tables, the event log
-- ---------------------------------------------------------------------------
--
-- Criterion 3. Each of these tables decides what some check checks, and the
-- runtime is the connection that check runs on. A runtime that can edit
-- `standing_checks` is a runtime that can stop being checked; a runtime that can
-- edit `event_table_config` can stop a table from emitting and then satisfy the
-- coverage check about the table it silenced. None of them is written outside a
-- migration -- every INSERT into all seven is in a `.sql` file in this directory
-- and there is none in `src/redkraken/*.py` -- so read-only costs nothing and
-- says what is true.
--
-- `cross_program_exempt_fks` joins the six the ticket names, because it is the
-- declared sibling of `program_global_tables`: the two together are what
-- `check_program_isolation()` reads to decide whether a foreign key crossing
-- programs is a defect.

DELETE FROM runtime_table_surface
 WHERE privilege <> 'SELECT'
   AND table_name IN ('standing_checks', 'event_table_config', 'event_table_exempt',
                      'program_global_tables', 'cross_program_exempt_fks',
                      'state_read_surface', 'purge_cascade_edges');

-- The key tables, and the reason they are read-only rather than unreachable.
-- `secret_kek` holds a salt and an HMAC check value and no key material, and
-- two things the runtime does need to read it: `artifact.py` derives the wire
-- key from the generation in force, and `check_wire_artifact_secrecy()` -- a
-- standing check, SECURITY INVOKER, run by the runtime -- asserts `secret_dek`
-- is empty, which it cannot assert about a table it cannot see. The one write
-- the runtime made here moves to a SECURITY DEFINER function in section 9.
DELETE FROM runtime_table_surface
 WHERE privilege <> 'SELECT'
   AND table_name IN ('secret_kek', 'secret_dek');

-- Criterion 4. The log is what everything else is checked against; a role that
-- can rewrite it can make any other check pass. Nothing in `src/redkraken`
-- updates or deletes an event -- the emitting triggers INSERT, and the purge
-- path that deletes rows runs as the owner -- so append-only is a description of
-- what the runtime already does, not a new restriction on it.
DELETE FROM runtime_table_surface
 WHERE table_name = 'events' AND privilege IN ('UPDATE', 'DELETE');

-- Criterion 1. The six verbs the measurement found: gated to `rk2_proxy`,
-- called from `proxy.py` and nowhere else, and executable by the runtime only
-- because of the default grant section 1 removed.
--
-- The row count is asserted because this is the one list in the file written by
-- hand. A name that matched nothing would mean the identity text here has
-- drifted from the identity text `runtime_verbs` builds -- a renamed argument
-- type, an overload -- and the file would go on to revoke nothing and declare
-- itself finished.
DO $$
DECLARE
    proxy_verbs text[] := ARRAY[
        'authorize_identity_egress_address(text, text, text, integer, text)',
        'authorize_identity_egress_request(text, text, text, text, integer, text, text)',
        'confirm_required_headers_open(text, uuid, text)',
        'ensure_proxy_wire_keying(text, bytea, bytea)',
        'open_required_headers(text)',
        'write_blocked_receipt(uuid, jsonb, text)'];
    n integer;
BEGIN
    DELETE FROM runtime_verb_surface WHERE verb = ANY(proxy_verbs);
    GET DIAGNOSTICS n = ROW_COUNT;
    IF n <> array_length(proxy_verbs, 1) THEN
        RAISE EXCEPTION
            'ph2-66 refuses to finish: % of % proxy verbs were not declared for the runtime',
            array_length(proxy_verbs, 1) - n, array_length(proxy_verbs, 1)
          USING HINT = 'the identity text in section 4 has drifted from runtime_verbs';
    END IF;
END $$;


-- ---------------------------------------------------------------------------
-- 5. The sweep: take away everything the registries do not name
-- ---------------------------------------------------------------------------
--
-- Sections 3 and 4 wrote down the intended surface. This is the one place the
-- database is changed to match it. Everything after this point is machinery
-- that keeps it matching.

DO $$
DECLARE r record; n integer := 0;
BEGIN
    FOR r IN
        SELECT rel.table_name, rel.privilege FROM runtime_relations rel
         WHERE rel.held
           AND NOT EXISTS (SELECT 1 FROM runtime_table_surface s
                            WHERE s.table_name = rel.table_name
                              AND s.privilege = rel.privilege)
         ORDER BY rel.table_name, rel.privilege
    LOOP
        EXECUTE format('REVOKE %s ON TABLE public.%I FROM rk2_runtime', r.privilege, r.table_name);
        n := n + 1;
    END LOOP;
    RAISE NOTICE 'ph2-66: % table privilege(s) revoked from rk2_runtime', n;

    n := 0;
    FOR r IN
        SELECT v.oid FROM runtime_verbs v
         WHERE v.closed AND v.held
           AND NOT EXISTS (SELECT 1 FROM runtime_verb_surface s WHERE s.verb = v.verb)
         ORDER BY v.verb
    LOOP
        EXECUTE format('REVOKE EXECUTE ON FUNCTION %s FROM rk2_runtime', r.oid::regprocedure);
        n := n + 1;
    END LOOP;
    RAISE NOTICE 'ph2-66: % verb(s) revoked from rk2_runtime', n;
END $$;


-- ---------------------------------------------------------------------------
-- 6. apply_runtime_grants(), the finalizer
-- ---------------------------------------------------------------------------
--
-- Additive and idempotent, and deliberately not a revoke -- the same shape, and
-- for the same reason, as `apply_state_grants()`: a finalizer that revoked would
-- quietly undo an over-grant, and an over-grant is precisely what has to be
-- seen. So the finalizer grants what the registry names, and section 7 raises on
-- anything held beyond it.
--
-- The verb half grants nothing. A function is closed to the runtime by being
-- revoked from PUBLIC, which section 1 made sufficient, and a registry row for a
-- closed function records a grant its own migration wrote; regranting here would
-- mean this finalizer could resurrect a verb somebody deliberately revoked
-- between runs. What it does instead is refuse to be the reason a row is
-- unenforced -- section 7's `runtime_verb_surface_names_a_closed_verb` arm.

CREATE FUNCTION apply_runtime_grants() RETURNS integer
LANGUAGE plpgsql AS $$
DECLARE r record; n integer := 0;
BEGIN
    FOR r IN
        SELECT s.table_name,
               string_agg(s.privilege, ', ' ORDER BY s.privilege) AS privileges
          FROM runtime_table_surface s
          JOIN runtime_relations rel ON rel.table_name = s.table_name
                                    AND rel.privilege = s.privilege
         WHERE NOT rel.held
         GROUP BY s.table_name
    LOOP
        EXECUTE format('GRANT %s ON TABLE public.%I TO rk2_runtime',
                       r.privileges, r.table_name);
        n := n + 1;
    END LOOP;
    RETURN n;
END $$;

COMMENT ON FUNCTION apply_runtime_grants() IS
    'Grants rk2_runtime what runtime_table_surface names and nothing else. Run '
    'at the end of every `rk db migrate`, because a migration that adds a table '
    'and a row now has to be granted rather than inheriting a default privilege.';


-- ---------------------------------------------------------------------------
-- 7. check_runtime_privileges(), the standing check
-- ---------------------------------------------------------------------------

CREATE FUNCTION check_runtime_privileges()
RETURNS TABLE (problem text, object text, detail text)
LANGUAGE sql STABLE AS $$
    -- 1. held and undeclared: what a new table used to arrive with, and what a
    --    hand-written GRANT in some later migration would leave behind.
    SELECT 'runtime_holds_undeclared_table_privilege',
           rel.table_name || '.' || rel.privilege,
           'rk2_runtime holds ' || rel.privilege || ' on ' || rel.table_name
           || ' with no runtime_table_surface row'
      FROM runtime_relations rel
     WHERE rel.held
       AND NOT EXISTS (SELECT 1 FROM runtime_table_surface s
                        WHERE s.table_name = rel.table_name
                          AND s.privilege = rel.privilege)
  UNION ALL
    -- 2. declared and not held: the finalizer did not run, or something revoked
    --    behind the registry's back.
    SELECT 'runtime_missing_declared_table_privilege',
           rel.table_name || '.' || rel.privilege,
           'runtime_table_surface names it and rk2_runtime does not hold it;'
           || ' run `rk db migrate`'
      FROM runtime_table_surface s
      JOIN runtime_relations rel ON rel.table_name = s.table_name
                                AND rel.privilege = s.privilege
     WHERE NOT rel.held
  UNION ALL
    -- 3. a row naming nothing: a rename, a drop, or a typo.
    SELECT 'runtime_table_surface_names_missing_object', s.table_name, 'no such relation in public'
      FROM runtime_table_surface s
     WHERE NOT EXISTS (SELECT 1 FROM runtime_relations rel WHERE rel.table_name = s.table_name)
     GROUP BY s.table_name
  UNION ALL
    -- 4. criterion 1, standing: a function closed to PUBLIC that the runtime can
    --    still execute and no row admits to.
    SELECT 'runtime_holds_undeclared_verb', v.verb,
           'closed to PUBLIC and executable by rk2_runtime with no runtime_verb_surface row'
      FROM runtime_verbs v
     WHERE v.closed AND v.held
       AND NOT EXISTS (SELECT 1 FROM runtime_verb_surface s WHERE s.verb = v.verb)
  UNION ALL
    -- 5. a declared verb the runtime cannot execute. Not an error of privilege
    --    but of bookkeeping: the row claims the runtime calls it, and it cannot,
    --    so either the caller is broken or the row outlived its reason.
    SELECT 'runtime_verb_surface_names_a_closed_verb', s.verb,
           'runtime_verb_surface names it and rk2_runtime cannot execute it'
      FROM runtime_verb_surface s
      JOIN runtime_verbs v ON v.verb = s.verb
     WHERE NOT v.held
  UNION ALL
    -- 6. a verb row naming no function.
    SELECT 'runtime_verb_surface_names_missing_function', s.verb, 'no such function in public'
      FROM runtime_verb_surface s
     WHERE NOT EXISTS (SELECT 1 FROM runtime_verbs v WHERE v.verb = s.verb)
  UNION ALL
    -- 7. the mechanism itself. Every arm above is about one object; this one is
    --    about the rule, because restoring either default grant would put the
    --    corpus back where it started one object at a time and each of those
    --    would look like an ordinary missing row.
    SELECT 'runtime_holds_a_default_grant',
           CASE d.defaclobjtype WHEN 'r' THEN 'new tables' WHEN 'f' THEN 'new functions'
                                ELSE d.defaclobjtype::text END,
           'ALTER DEFAULT PRIVILEGES grants ' || a.privilege_type
           || ' to rk2_runtime at creation; the surface is the two registries'
      FROM pg_default_acl d
      CROSS JOIN LATERAL aclexplode(d.defaclacl) a
     WHERE d.defaclobjtype IN ('r', 'f')
       AND a.grantee = 'rk2_runtime'::regrole
$$;

REVOKE ALL ON FUNCTION check_runtime_privileges() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION check_runtime_privileges() TO rk2_runtime, rk2_restore;

-- Closed to PUBLIC and granted to the runtime, which is exactly the shape arm 4
-- fails on without a row. The row is here rather than in the seed because the
-- seed ran in section 3 and this function did not exist yet -- which is the
-- mechanism working on its own author.
INSERT INTO runtime_verb_surface (verb, note) VALUES
    ('check_runtime_privileges()',
     'the standing check itself; run_standing_checks() is SECURITY INVOKER and the runtime is what runs the standing family');

COMMENT ON FUNCTION check_runtime_privileges() IS
    'What the runtime''s privilege surface can get wrong: a privilege held that '
    'no registry row declares, a row nothing enforces, and the default grant '
    'coming back. Executable by rk2_runtime because run_standing_checks() is '
    'SECURITY INVOKER and the runtime is what runs the standing family.';

INSERT INTO standing_checks (name, query, owner_ticket, note) VALUES
    ('runtime_privileges', 'SELECT * FROM check_runtime_privileges()', '66',
     'rk2_runtime holds exactly what runtime_table_surface and runtime_verb_surface declare, and nothing arrives granted by default');


-- ---------------------------------------------------------------------------
-- 8. check_runtime_connection() asks the registry instead of every table
-- ---------------------------------------------------------------------------
--
-- The arm this replaces asked whether the connecting role could read and write
-- *every* managed table, which was a fair question while the answer was meant to
-- be yes for all 196 of them. Section 4 makes the answer no for nine, so the
-- question has to become the registry's: can the role do what the surface says
-- it does. Kept, because the fault it was written for is real -- a runtime
-- missing a grant fails at the first write of a run, hours in, with a permission
-- error instead of a refusal at connect time.
--
-- The read half still asks `has_any_column_privilege`, for the reason
-- `20260814T020000Z` gave: `pending_decisions` is readable column by column and
-- a table-level question answers false about it. The write halves stay
-- table-level, because a partial INSERT grant is a table the runtime cannot
-- write a row to.
--
-- The arm is renamed with it: `readwrite_on_every_managed_table` would now be
-- describing a set it no longer means. `CREATE OR REPLACE` rather than a drop,
-- so the function keeps the privileges 029 gave it -- it is open to PUBLIC, and
-- a recreated one would be closed by section 1 and would need a registry row to
-- say what its own migration already said.

CREATE OR REPLACE FUNCTION check_runtime_connection(p_role text DEFAULT current_user)
RETURNS TABLE (check_name text, ok boolean, detail text)
LANGUAGE plpgsql STABLE AS $fn$
DECLARE
    v_role oid;
    v_n int;
    v_tbl text;
BEGIN
    SELECT oid INTO v_role FROM pg_roles WHERE rolname = p_role;

    RETURN QUERY SELECT 'role_exists'::text, v_role IS NOT NULL, 'role = ' || p_role;
    RETURN QUERY SELECT 'not_superuser'::text,
        v_role IS NOT NULL AND NOT coalesce(
            (SELECT rolsuper FROM pg_roles WHERE oid = v_role), true),
        p_role || ' rolsuper = ' || coalesce(
            (SELECT rolsuper::text FROM pg_roles WHERE oid = v_role), '<absent>');
    RETURN QUERY SELECT 'not_bypassrls'::text,
        v_role IS NOT NULL AND NOT coalesce(
            (SELECT rolbypassrls FROM pg_roles WHERE oid = v_role), true),
        p_role || ' rolbypassrls';
    RETURN QUERY SELECT 'not_owner'::text,
        v_role IS NOT NULL AND NOT rk2_role_has_usage(p_role, 'rk2_owner'),
        p_role || ' member of rk2_owner = '
            || rk2_role_has_usage(p_role, 'rk2_owner')::text;

    SELECT count(*), min(m.table_name) INTO v_n, v_tbl
      FROM managed_tables m JOIN pg_class c ON c.oid = m.oid
     WHERE v_role IS NULL OR pg_has_role(v_role, c.relowner, 'USAGE');
    RETURN QUERY SELECT 'owns_no_managed_table'::text,
        v_role IS NOT NULL AND v_n = 0,
        v_n || ' table(s) owned' || coalesce(', e.g. ' || v_tbl, '');

    RETURN QUERY SELECT 'cannot_set_replication_role'::text,
        v_role IS NOT NULL AND NOT has_parameter_privilege(
            v_role, 'session_replication_role', 'SET'),
        p_role || ' SET on session_replication_role';

    SELECT count(*), min(s.table_name || '.' || s.privilege) INTO v_n, v_tbl
      FROM runtime_table_surface s
      JOIN pg_class c ON c.relname = s.table_name
                     AND c.relnamespace = 'public'::regnamespace
     WHERE v_role IS NULL
        OR CASE WHEN s.privilege = 'SELECT'
                THEN NOT has_any_column_privilege(v_role, c.oid, 'SELECT')
                ELSE NOT has_table_privilege(v_role, c.oid, s.privilege) END;
    RETURN QUERY SELECT 'holds_the_declared_table_surface'::text,
        v_role IS NOT NULL AND v_n = 0,
        v_n || ' declared privilege(s) missing' || coalesce(', e.g. ' || v_tbl, '');

    SELECT count(*) INTO v_n FROM managed_tables m
     WHERE v_role IS NOT NULL AND has_table_privilege(v_role, m.oid, 'TRUNCATE');
    RETURN QUERY SELECT 'no_truncate_anywhere'::text,
        v_role IS NOT NULL AND v_n = 0,
        v_n || ' table(s) truncatable';
END $fn$;

COMMENT ON FUNCTION check_runtime_connection(text) IS
    'Eight facts about the connecting role, asserted before a run starts. '
    'Ticket 66 turned the read/write arm from "every managed table" into "what '
    'runtime_table_surface declares", because nine tables are deliberately no '
    'longer writable.';


-- ---------------------------------------------------------------------------
-- 9. The one write `secret_kek` still needs
-- ---------------------------------------------------------------------------
--
-- `artifact.py` establishes generation 1 the first time an installation seals a
-- wire artifact, and it did that with an INSERT on the runtime connection.
-- Section 4 takes the INSERT away, so the write goes through the function that
-- already existed for the proxy's identical need: SECURITY DEFINER, owned by
-- rk2_owner, shape-checking its arguments, and handling the collision between
-- two processes that both find no generation. The runtime gets the verb and not
-- the table, which is the difference between "may establish the first
-- generation" and "may write key rows".

GRANT EXECUTE ON FUNCTION ensure_active_secret_kek(bytea, bytea) TO rk2_runtime;

INSERT INTO runtime_verb_surface (verb, note) VALUES
    ('ensure_active_secret_kek(bytea, bytea)',
     'the runtime''s only write to secret_kek: establishing generation 1 on an installation that has none, through a definer that checks the shape');


-- ---------------------------------------------------------------------------
-- 10. Wiring
-- ---------------------------------------------------------------------------

INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
    ('runtime_table_surface', 'reference',
     'the runtime''s declared table privileges, changed only by migration', '66'),
    ('runtime_verb_surface', 'reference',
     'the runtime''s declared verbs, changed only by migration', '66');

INSERT INTO program_global_tables (table_name, reason) VALUES
    ('runtime_table_surface', 'corpus-wide privilege surface'),
    ('runtime_verb_surface',  'corpus-wide privilege surface');

SELECT attach_event_triggers();

-- Section 1 means these are not inherited. The registries are read-only to the
-- runtime for the reason section 4 gives about every other registry, and
-- rk2_restore reads them because `check_runtime_privileges()` is in the restore
-- entitlement's reach and a check that cannot read its own registry is a check
-- that cannot run.
GRANT SELECT ON runtime_table_surface, runtime_verb_surface, runtime_relations, runtime_verbs
    TO rk2_runtime, rk2_restore;


-- ---------------------------------------------------------------------------
-- 11. The invariants this file must not have broken
-- ---------------------------------------------------------------------------

SELECT apply_runtime_grants();

DO $$
DECLARE n integer; d text;
BEGIN
    SELECT count(*), string_agg(problem || ': ' || object, '; ')
      INTO n, d FROM check_runtime_privileges();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-66 refuses to finish: % privilege violation(s): %', n, d;
    END IF;

    -- The connection the whole corpus runs on still passes its own gate. If this
    -- raises, section 8 narrowed something a run needs and the failure belongs
    -- here rather than at the first write of the next campaign.
    SELECT count(*), string_agg(c.check_name || ': ' || c.detail, '; ')
      INTO n, d FROM check_runtime_connection('rk2_runtime') c WHERE NOT c.ok;
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-66 refuses to finish: runtime connection fails % arm(s): %', n, d;
    END IF;

    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_check_registration();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-66 refuses to finish: % registration violation(s): %', n, d;
    END IF;

    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_program_isolation();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-66 refuses to finish: % isolation violation(s): %', n, d;
    END IF;
END $$;
