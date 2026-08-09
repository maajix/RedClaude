-- ---------------------------------------------------------------------------
-- 20260807T191200Z__roles_and_grants.sql   (ticket 33)
--
-- Ticket 07 closed the `session_replication_role = 'replica'` hole with
-- `ENABLE ALWAYS` on every trigger, and could not close the foreign-key half of
-- it the same way. It handed the rest here: "The real role catalogue, the grant
-- set, and how the two connection strings are configured and kept apart are
-- this ticket's."
--
-- FOUR ROLES, TWO CONNECTION STRINGS.
--
--   rk2_owner    NOLOGIN group. Owns the database and every object in it. Not a
--                connection string -- nothing logs in as the owner; the runner
--                SET ROLEs to it, so object ownership does not depend on which
--                login happened to apply a migration.
--   rk2_migrate  LOGIN, member of rk2_owner, NOSUPERUSER.
--                  => RK2_MIGRATE_URL, held by ./migrate.sh and nothing else.
--   rk2_runtime  LOGIN, NOSUPERUSER, member of nothing, owns nothing.
--                  => RK2_DATABASE_URL, held by the agent runtime.
--   rk2_restore  LOGIN, member of rk2_owner, plus GRANT SET ON PARAMETER
--                session_replication_role. The one role that can turn
--                enforcement off, existing so the restore procedure has a door
--                that is not "become superuser". Used by one script, never by a
--                running system.
--
-- Roles are cluster-global and CREATE ROLE needs superuser, so the four are
-- created by `./migrate.sh provision` (superuser, once per database) together
-- with the database and the `vector` extension -- which is also superuser-only,
-- because pgvector's control file has no `trusted` line on this image. This
-- migration owns everything a non-superuser owner can do: the grants, the
-- DEFAULT privileges, and the assertions.
--
-- WHY THE SPLIT IS ASSERTED FROM BOTH ENDS. A swapped pair of connection
-- strings is silent: the runtime would work perfectly on RK2_MIGRATE_URL, with
-- the ability to DISABLE TRIGGER and no reason to. So migrate.sh refuses a
-- connection that is *not* the owner, and assert_runtime_connection() refuses
-- one that *is*. Neither check can pass on the other's string.
-- ---------------------------------------------------------------------------

DO $$
DECLARE missing text;
BEGIN
    SELECT string_agg(r, ', ') INTO missing
      FROM unnest(ARRAY['rk2_owner','rk2_migrate','rk2_runtime','rk2_restore']) r
     WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r);
    IF missing IS NOT NULL THEN
        RAISE EXCEPTION 'roles missing: %', missing
              USING HINT = 'run `rk db provision` (superuser) before `rk db migrate`';
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- The grant set
-- ---------------------------------------------------------------------------

-- PUBLIC keeps CREATE on `public` on nothing since PG15, but CONNECT on the
-- database is still PUBLIC by default: revoke it so membership is explicit.
REVOKE ALL ON SCHEMA public FROM PUBLIC;
DO $$ BEGIN
    EXECUTE format('REVOKE ALL ON DATABASE %I FROM PUBLIC', current_database());
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO rk2_runtime, rk2_migrate, rk2_restore',
                   current_database());
END $$;

GRANT USAGE ON SCHEMA public TO rk2_runtime;

-- DML and EXECUTE, no DDL, no ownership, no TRUNCATE (TRUNCATE fires no row
-- trigger, so it is a hole in the event log that no privilege the runtime has
-- should be able to open) and no REFERENCES (a new FK is a new cascade edge,
-- and 016 made the cascade set a reviewed table).
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO rk2_runtime;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO rk2_runtime;

-- Not `GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public`: pgvector installs ~90
-- functions into public that rk2_owner does not own, and that form emits a
-- WARNING per function while granting nothing. Extension functions are already
-- EXECUTE-to-PUBLIC from CREATE EXTENSION, so only ours need naming.
DO $$
DECLARE r record;
BEGIN
    FOR r IN SELECT p.oid::regprocedure AS sig
               FROM pg_proc p
              WHERE p.pronamespace = 'public'::regnamespace
                AND p.proowner = 'rk2_owner'::regrole
                AND NOT EXISTS (SELECT 1 FROM pg_depend d
                                 WHERE d.classid = 'pg_proc'::regclass
                                   AND d.objid = p.oid AND d.deptype = 'e') LOOP
        EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO rk2_runtime', r.sig);
    END LOOP;
END $$;

-- THE HOLE IN 016. `GRANT ... ON ALL TABLES IN SCHEMA` is a snapshot taken at
-- the instant it runs, not a standing rule: every table created by a migration
-- after 016 is invisible to rk2_runtime, and the failure surfaces as a
-- permission denied on the first query in production rather than at apply time.
-- ALTER DEFAULT PRIVILEGES is the standing rule -- and it is keyed to the
-- creating role, which is the second reason the runner SET ROLEs to rk2_owner
-- instead of letting each login own what it happened to create.
ALTER DEFAULT PRIVILEGES FOR ROLE rk2_owner IN SCHEMA public
      GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO rk2_runtime;
ALTER DEFAULT PRIVILEGES FOR ROLE rk2_owner IN SCHEMA public
      GRANT USAGE, SELECT ON SEQUENCES TO rk2_runtime;
ALTER DEFAULT PRIVILEGES FOR ROLE rk2_owner IN SCHEMA public
      GRANT EXECUTE ON FUNCTIONS TO rk2_runtime;

-- The test harness schema, so checks_b can keep running as rk2_runtime.
DO $$ BEGIN
    IF to_regnamespace('t') IS NOT NULL THEN
        EXECUTE 'GRANT USAGE ON SCHEMA t TO rk2_runtime';
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- The assertion the runtime runs on its own connection at start
-- ---------------------------------------------------------------------------
--
-- Every row here is a property of the CONNECTION, not of the schema, so it
-- cannot live in check_server_baseline() -- that one is run by the runner, on
-- the owner's connection, where half of these are supposed to be false.
--
-- p_role defaults to whoever is asking, so the runtime calls it with no
-- argument and the runner calls it with 'rk2_runtime' to check the app's
-- privileges before the app has ever connected.
CREATE FUNCTION check_runtime_connection(p_role text DEFAULT current_user)
RETURNS TABLE (check_name text, ok boolean, detail text)
LANGUAGE plpgsql STABLE AS $$
DECLARE v_n int; v_tbl text;
BEGIN
    RETURN QUERY SELECT 'role_exists'::text,
        EXISTS (SELECT 1 FROM pg_roles WHERE rolname = p_role),
        'role = ' || p_role;

    RETURN QUERY SELECT 'not_superuser'::text,
        NOT coalesce((SELECT rolsuper FROM pg_roles WHERE rolname = p_role), true),
        p_role || ' rolsuper = ' ||
        coalesce((SELECT rolsuper::text FROM pg_roles WHERE rolname = p_role), '<absent>');

    RETURN QUERY SELECT 'not_bypassrls'::text,
        NOT coalesce((SELECT rolbypassrls FROM pg_roles WHERE rolname = p_role), true),
        p_role || ' rolbypassrls'::text;

    -- The whole point of the split. Membership in the owner is transitive and
    -- pg_has_role sees through it, so an accidental GRANT rk2_owner TO
    -- rk2_runtime three migrations from now fails here rather than nowhere.
    RETURN QUERY SELECT 'not_owner'::text,
        NOT pg_has_role(p_role, 'rk2_owner', 'USAGE'),
        p_role || ' member of rk2_owner = ' || pg_has_role(p_role, 'rk2_owner', 'USAGE')::text;

    -- ALTER TABLE ... DISABLE TRIGGER needs ownership, and ownership is what
    -- 016 could not take away from the FK half of the problem any other way.
    SELECT count(*), min(m.table_name) INTO v_n, v_tbl
      FROM managed_tables m JOIN pg_class c ON c.oid = m.oid
     WHERE pg_has_role(p_role, c.relowner, 'USAGE');
    RETURN QUERY SELECT 'owns_no_managed_table'::text, v_n = 0,
        v_n || ' table(s) owned' || coalesce(', e.g. ' || v_tbl, '');

    -- SET session_replication_role = 'replica' is superuser-or-granted. This is
    -- the check that says the ONE switch which turns 39 triggers and every
    -- foreign key off at once is out of reach of the connection the model's
    -- tool calls run on.
    RETURN QUERY SELECT 'cannot_set_replication_role'::text,
        NOT has_parameter_privilege(p_role, 'session_replication_role', 'SET'),
        p_role || ' SET on session_replication_role = ' ||
        has_parameter_privilege(p_role, 'session_replication_role', 'SET')::text;

    -- The 016 snapshot-grant hole, asserted. A migration that adds a table
    -- without a grant makes the runtime fail on first use; this fails at apply.
    SELECT count(*), min(m.table_name) INTO v_n, v_tbl
      FROM managed_tables m
     WHERE NOT has_table_privilege(p_role, m.oid, 'SELECT')
        OR NOT has_table_privilege(p_role, m.oid, 'INSERT');
    RETURN QUERY SELECT 'readwrite_on_every_managed_table'::text, v_n = 0,
        v_n || ' table(s) not readable/writable' || coalesce(', e.g. ' || v_tbl, '');

    -- TRUNCATE fires no row trigger: a row can leave without an event.
    SELECT count(*) INTO v_n FROM managed_tables m
     WHERE has_table_privilege(p_role, m.oid, 'TRUNCATE');
    RETURN QUERY SELECT 'no_truncate_anywhere'::text, v_n = 0,
        v_n || ' table(s) truncatable';
END $$;

CREATE FUNCTION assert_runtime_connection(p_role text DEFAULT current_user)
RETURNS void LANGUAGE plpgsql AS $$
DECLARE r record; n int := 0;
BEGIN
    FOR r IN SELECT * FROM check_runtime_connection(p_role) WHERE NOT ok LOOP
        RAISE WARNING 'runtime connection: % FAILED -- %', r.check_name, r.detail;
        n := n + 1;
    END LOOP;
    IF n > 0 THEN
        RAISE EXCEPTION 'runtime connection assertion failed: % check(s); this connection is not the runtime connection', n;
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- Fold the role catalogue into the server baseline
-- ---------------------------------------------------------------------------
-- check_server_baseline() runs on the OWNER's connection, so what it can assert
-- about roles is the catalogue itself: that the four exist, that exactly one of
-- them can turn enforcement off, and that the runtime's privileges are right.
CREATE FUNCTION check_role_catalogue()
RETURNS TABLE (check_name text, ok boolean, detail text)
LANGUAGE plpgsql STABLE AS $$
DECLARE v_n int;
BEGIN
    SELECT count(*) INTO v_n FROM pg_roles
     WHERE rolname IN ('rk2_owner','rk2_migrate','rk2_runtime','rk2_restore',
                       'rk2_state','rk2_human');
    RETURN QUERY SELECT 'roles_present'::text, v_n = 6, v_n || ' of 6 roles';

    -- Ticket 28 makes MEMBERSHIP in rk2_human the thing that authorises
    -- `actor_kind = 'human'`. That is only worth anything if the two
    -- connections a model can reach through -- directly (rk2_state) or through
    -- a handler (rk2_runtime) -- cannot become a member, by grant or by
    -- inheritance. pg_has_role follows the whole membership graph, so a chain
    -- through a fifth role fails this too.
    RETURN QUERY SELECT 'model_reachable_roles_are_not_human'::text,
        NOT (pg_has_role('rk2_runtime','rk2_human','USAGE')
          OR pg_has_role('rk2_state','rk2_human','USAGE')),
        'runtime=' || pg_has_role('rk2_runtime','rk2_human','USAGE')::text
          || ' state=' || pg_has_role('rk2_state','rk2_human','USAGE')::text;

    -- The agent connection must not be able to reach the commit connection's
    -- privileges by SET ROLE. "LLM proposes, runtime commits" is a privilege
    -- boundary or it is a convention.
    RETURN QUERY SELECT 'state_cannot_become_runtime_or_owner'::text,
        NOT (pg_has_role('rk2_state','rk2_runtime','USAGE')
          OR pg_has_role('rk2_state','rk2_owner','USAGE')),
        'state->runtime=' || pg_has_role('rk2_state','rk2_runtime','USAGE')::text
          || ' state->owner=' || pg_has_role('rk2_state','rk2_owner','USAGE')::text;

    -- Every rk2_* role that is not the owner must be short of DDL. A role with
    -- CREATEROLE can mint itself a member of rk2_human; a role with BYPASSRLS
    -- reads every program.
    RETURN QUERY SELECT 'no_role_has_createrole_or_bypassrls'::text,
        (SELECT count(*) = 0 FROM pg_roles
          WHERE rolname LIKE 'rk2\_%' AND (rolcreaterole OR rolbypassrls OR rolsuper)),
        coalesce((SELECT string_agg(rolname, ',' ORDER BY rolname) FROM pg_roles
          WHERE rolname LIKE 'rk2\_%' AND (rolcreaterole OR rolbypassrls OR rolsuper)), '<none>');

    -- Exactly one role, and one that never runs anything, may enter replica
    -- mode. Written as a set comparison so a fifth role granted the parameter
    -- fails this instead of being invisible.
    RETURN QUERY SELECT 'only_restore_may_set_replication_role'::text,
        (SELECT coalesce(array_agg(rolname::text ORDER BY rolname), '{}') = ARRAY['rk2_restore']
           FROM pg_roles
          WHERE rolname LIKE 'rk2\_%' AND NOT rolsuper
            AND has_parameter_privilege(rolname, 'session_replication_role', 'SET')),
        'granted: ' || coalesce((SELECT string_agg(rolname, ',' ORDER BY rolname) FROM pg_roles
          WHERE rolname LIKE 'rk2\_%' AND NOT rolsuper
            AND has_parameter_privilege(rolname, 'session_replication_role', 'SET')), '<none>');

    RETURN QUERY SELECT 'owner_owns_every_managed_table'::text,
        (SELECT count(*) = 0 FROM managed_tables m JOIN pg_class c ON c.oid = m.oid
          WHERE c.relowner <> 'rk2_owner'::regrole),
        (SELECT coalesce(string_agg(DISTINCT c.relowner::regrole::text, ','), '<none>')
           FROM managed_tables m JOIN pg_class c ON c.oid = m.oid);

    RETURN QUERY SELECT 'migrate_role_is_not_superuser'::text,
        NOT coalesce((SELECT rolsuper FROM pg_roles WHERE rolname='rk2_migrate'), true),
        'rk2_migrate rolsuper'::text;

    -- Delegate the runtime's own eight checks, named so a failure says which.
    RETURN QUERY SELECT 'runtime_' || c.check_name, c.ok, c.detail
      FROM check_runtime_connection('rk2_runtime') c;
END $$;

CREATE FUNCTION assert_role_catalogue() RETURNS void LANGUAGE plpgsql AS $$
DECLARE r record; n int := 0;
BEGIN
    FOR r IN SELECT * FROM check_role_catalogue() WHERE NOT ok LOOP
        RAISE WARNING 'roles: % FAILED -- %', r.check_name, r.detail;
        n := n + 1;
    END LOOP;
    IF n > 0 THEN
        RAISE EXCEPTION 'role catalogue assertion failed: % check(s); run SELECT * FROM check_role_catalogue()', n;
    END IF;
END $$;

-- rk2_runtime must be able to run its own assertion, and check_role_catalogue
-- is the runner's. EXECUTE was granted ON ALL FUNCTIONS above, before these
-- three existed, so they are granted individually.
GRANT EXECUTE ON FUNCTION check_runtime_connection(text)  TO rk2_runtime;
GRANT EXECUTE ON FUNCTION assert_runtime_connection(text) TO rk2_runtime;
REVOKE EXECUTE ON FUNCTION check_role_catalogue() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION assert_role_catalogue() FROM PUBLIC;
