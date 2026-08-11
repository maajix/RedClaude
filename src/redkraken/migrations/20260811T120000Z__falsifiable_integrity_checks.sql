-- PH2-03: every hard integrity claim has an executable negative control.
--
-- Four baseline facts belong to the running binary or installed extension, so
-- a transaction cannot alter their subjects and roll back afterwards.  Keep
-- observation in check_server_baseline(), but put the verdict in this pure
-- evaluator so the exact production predicate can be exercised with one bad
-- observation at a time.  Missing runtime/proxy roles used to abort their
-- family through pg_has_role(name,...); the role checks below instead return
-- named false rows for an absent role.

CREATE FUNCTION evaluate_server_runtime(
    p_server_version_num integer,
    p_uuidv7_oids bigint[],
    p_pgvector_version text,
    p_hnsw_cosine_opclass boolean
) RETURNS TABLE(check_name text, ok boolean, detail text)
LANGUAGE plpgsql IMMUTABLE AS $fn$
DECLARE
    v_vector_ok boolean := false;
BEGIN
    IF coalesce(p_pgvector_version, '') ~ '^[0-9]+\.[0-9]+\.[0-9]+$' THEN
        v_vector_ok := string_to_array(p_pgvector_version, '.')::integer[]
                       >= ARRAY[0,8,0];
    END IF;

    RETURN QUERY VALUES
        ('server_major'::text,
         p_server_version_num BETWEEN 180000 AND 189999,
         'server_version_num = ' || coalesce(p_server_version_num::text, '<absent>')),
        ('uuidv7_is_builtin'::text,
         cardinality(coalesce(p_uuidv7_oids, '{}'::bigint[])) = 1
             AND p_uuidv7_oids[1] < 16384,
         'uuidv7 oid = ' || coalesce(array_to_string(p_uuidv7_oids, ', '), '<absent>')),
        ('pgvector_version'::text,
         v_vector_ok,
         'pgvector = ' || coalesce(p_pgvector_version, '<absent>')),
        ('hnsw_cosine_opclass'::text,
         coalesce(p_hnsw_cosine_opclass, false),
         'hnsw / vector_cosine_ops');
END $fn$;

CREATE OR REPLACE FUNCTION check_server_baseline(p_expected_migrations text[] DEFAULT NULL)
RETURNS TABLE (check_name text, ok boolean, detail text)
LANGUAGE plpgsql STABLE AS $fn$
DECLARE
    v_mwm bigint;
    v_src text;
    v_pgv text;
    v_uuidv7_oids bigint[];
    v_hnsw_cosine boolean;
    v_n int;
BEGIN
    SELECT array_agg(oid::bigint ORDER BY oid) INTO v_uuidv7_oids
      FROM pg_proc WHERE proname = 'uuidv7' AND pronargs = 0;
    SELECT extversion INTO v_pgv FROM pg_extension WHERE extname = 'vector';
    SELECT EXISTS (
        SELECT 1 FROM pg_opclass o JOIN pg_am a ON a.oid = o.opcmethod
         WHERE a.amname = 'hnsw' AND o.opcname = 'vector_cosine_ops'
    ) INTO v_hnsw_cosine;

    RETURN QUERY SELECT * FROM evaluate_server_runtime(
        current_setting('server_version_num')::integer,
        v_uuidv7_oids,
        v_pgv,
        v_hnsw_cosine
    );

    -- Loading pgvector turns its placeholder GUCs into settings with a source.
    -- The corpus cannot exist without the extension, but condition the cast so
    -- a missing extension has already produced its named false row rather than
    -- aborting before any result can be read.
    IF v_pgv IS NOT NULL THEN
        EXECUTE 'SELECT ''[1]''::vector';
    END IF;

    SELECT setting::bigint, source INTO v_mwm, v_src
      FROM pg_settings WHERE name = 'maintenance_work_mem';
    RETURN QUERY SELECT 'maintenance_work_mem'::text,
        coalesce(v_mwm >= 262144 AND v_src = 'database', false),
        'maintenance_work_mem = ' || v_mwm || 'kB, source = ' || v_src;

    RETURN QUERY SELECT 'hnsw_iterative_scan'::text,
        coalesce((SELECT setting = 'relaxed_order' AND source = 'database'
                    FROM pg_settings WHERE name = 'hnsw.iterative_scan'), false),
        'hnsw.iterative_scan = ' || coalesce((SELECT setting || ' (' || source || ')'
                    FROM pg_settings WHERE name='hnsw.iterative_scan'), '<absent>');

    RETURN QUERY SELECT 'hnsw_max_scan_tuples'::text,
        coalesce((SELECT setting::int >= 40000
                    FROM pg_settings WHERE name = 'hnsw.max_scan_tuples'), false),
        'hnsw.max_scan_tuples = ' || coalesce((SELECT setting
                    FROM pg_settings WHERE name='hnsw.max_scan_tuples'), '<absent>');

    IF to_regclass('hnsw_headroom') IS NULL THEN
        RETURN QUERY SELECT 'hnsw_headroom'::text, false, 'hnsw_headroom is absent'::text;
    ELSE
        RETURN QUERY SELECT 'hnsw_headroom'::text,
            (SELECT bool_and(headroom_rows > 0) FROM hnsw_headroom),
            (SELECT string_agg(table_name || ' ' || rows || '/' || capacity_rows, ', ')
               FROM hnsw_headroom);
    END IF;

    RETURN QUERY SELECT 'session_replication_role'::text,
        current_setting('session_replication_role') = 'origin',
        'session_replication_role = ' || current_setting('session_replication_role');

    RETURN QUERY SELECT 'default_transaction_isolation'::text,
        current_setting('default_transaction_isolation') = 'read committed',
        'default_transaction_isolation = ' || current_setting('default_transaction_isolation');

    RETURN QUERY SELECT 'schema_migrations_present'::text,
        to_regclass('rk2_meta.schema_migrations') IS NOT NULL,
        'schema_migrations'::text;

    IF to_regclass('rk2_meta.schema_migrations') IS NOT NULL THEN
        SELECT count(*) INTO v_n FROM (
            SELECT id, applied_seq, lag(id) OVER (ORDER BY applied_seq) AS prev_id
              FROM rk2_meta.schema_migrations
        ) s WHERE prev_id IS NOT NULL AND id < prev_id;
        RETURN QUERY SELECT 'migrations_in_declared_order'::text, v_n = 0,
            v_n || ' migration(s) applied out of filename order';

        IF p_expected_migrations IS NOT NULL THEN
            SELECT count(*) INTO v_n FROM (
                SELECT id FROM rk2_meta.schema_migrations
                EXCEPT SELECT unnest(p_expected_migrations)
            ) s;
            RETURN QUERY SELECT 'no_unknown_migrations'::text, v_n = 0,
                v_n || ' migration(s) in the database with no file';
            SELECT count(*) INTO v_n FROM (
                SELECT unnest(p_expected_migrations)
                EXCEPT SELECT id FROM rk2_meta.schema_migrations
            ) s;
            RETURN QUERY SELECT 'no_pending_migrations'::text, v_n = 0,
                v_n || ' migration file(s) not applied';
        END IF;
    END IF;

    SELECT count(*) INTO v_n FROM check_event_coverage()
     WHERE problem NOT LIKE 'undecided\_%';
    RETURN QUERY SELECT 'event_coverage'::text, v_n = 0,
        v_n || ' coverage problem(s)';
END $fn$;

CREATE FUNCTION rk2_role_has_usage(p_member text, p_role text)
RETURNS boolean LANGUAGE sql STABLE AS $fn$
    SELECT coalesce((
        SELECT pg_has_role(member.oid, target.oid, 'USAGE')
          FROM pg_roles member CROSS JOIN pg_roles target
         WHERE member.rolname = p_member AND target.rolname = p_role
    ), false);
$fn$;

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

    SELECT count(*), min(m.table_name) INTO v_n, v_tbl
      FROM managed_tables m
     WHERE v_role IS NULL
        OR NOT has_table_privilege(v_role, m.oid, 'SELECT')
        OR NOT has_table_privilege(v_role, m.oid, 'INSERT');
    RETURN QUERY SELECT 'readwrite_on_every_managed_table'::text,
        v_role IS NOT NULL AND v_n = 0,
        v_n || ' table(s) not readable/writable' || coalesce(', e.g. ' || v_tbl, '');

    SELECT count(*) INTO v_n FROM managed_tables m
     WHERE v_role IS NOT NULL AND has_table_privilege(v_role, m.oid, 'TRUNCATE');
    RETURN QUERY SELECT 'no_truncate_anywhere'::text,
        v_role IS NOT NULL AND v_n = 0,
        v_n || ' table(s) truncatable';
END $fn$;

CREATE OR REPLACE FUNCTION base_role_catalogue()
RETURNS TABLE (check_name text, ok boolean, detail text)
LANGUAGE plpgsql STABLE AS $fn$
DECLARE
    v_n int;
    v_owner oid;
BEGIN
    SELECT oid INTO v_owner FROM pg_roles WHERE rolname = 'rk2_owner';
    SELECT count(*) INTO v_n FROM pg_roles
     WHERE rolname IN ('rk2_owner','rk2_migrate','rk2_runtime','rk2_restore',
                       'rk2_state','rk2_human');
    RETURN QUERY SELECT 'roles_present'::text, v_n = 6, v_n || ' of 6 roles';

    RETURN QUERY SELECT 'model_reachable_roles_are_not_human'::text,
        EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rk2_runtime')
        AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rk2_state')
        AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rk2_human')
        AND NOT (rk2_role_has_usage('rk2_runtime','rk2_human')
              OR rk2_role_has_usage('rk2_state','rk2_human')),
        'runtime=' || rk2_role_has_usage('rk2_runtime','rk2_human')::text
          || ' state=' || rk2_role_has_usage('rk2_state','rk2_human')::text;

    RETURN QUERY SELECT 'state_cannot_become_runtime_or_owner'::text,
        EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rk2_state')
        AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rk2_runtime')
        AND v_owner IS NOT NULL
        AND NOT (rk2_role_has_usage('rk2_state','rk2_runtime')
              OR rk2_role_has_usage('rk2_state','rk2_owner')),
        'state->runtime=' || rk2_role_has_usage('rk2_state','rk2_runtime')::text
          || ' state->owner=' || rk2_role_has_usage('rk2_state','rk2_owner')::text;

    RETURN QUERY SELECT 'no_role_has_createrole_or_bypassrls'::text,
        (SELECT count(*) = 0 FROM pg_roles
          WHERE rolname LIKE 'rk2\_%' AND (rolcreaterole OR rolbypassrls OR rolsuper)),
        coalesce((SELECT string_agg(rolname, ',' ORDER BY rolname) FROM pg_roles
          WHERE rolname LIKE 'rk2\_%' AND (rolcreaterole OR rolbypassrls OR rolsuper)), '<none>');

    RETURN QUERY SELECT 'only_restore_may_set_replication_role'::text,
        (SELECT coalesce(array_agg(rolname::text ORDER BY rolname), '{}') = ARRAY['rk2_restore']
           FROM pg_roles
          WHERE rolname LIKE 'rk2\_%' AND NOT rolsuper
            AND has_parameter_privilege(rolname, 'session_replication_role', 'SET')),
        'granted: ' || coalesce((SELECT string_agg(rolname, ',' ORDER BY rolname)
           FROM pg_roles WHERE rolname LIKE 'rk2\_%' AND NOT rolsuper
            AND has_parameter_privilege(rolname, 'session_replication_role', 'SET')), '<none>');

    RETURN QUERY SELECT 'owner_owns_every_managed_table'::text,
        v_owner IS NOT NULL AND (SELECT count(*) = 0
          FROM managed_tables m JOIN pg_class c ON c.oid = m.oid
         WHERE c.relowner <> v_owner),
        coalesce((SELECT string_agg(DISTINCT c.relowner::regrole::text, ',')
          FROM managed_tables m JOIN pg_class c ON c.oid = m.oid), '<none>');

    RETURN QUERY SELECT 'migrate_role_is_not_superuser'::text,
        NOT coalesce((SELECT rolsuper FROM pg_roles WHERE rolname='rk2_migrate'), true),
        'rk2_migrate rolsuper';

    RETURN QUERY SELECT 'runtime_' || c.check_name, c.ok, c.detail
      FROM check_runtime_connection('rk2_runtime') c;
END $fn$;

CREATE OR REPLACE FUNCTION check_role_catalogue()
RETURNS TABLE(check_name text, ok boolean, detail text)
LANGUAGE plpgsql STABLE AS $fn$
BEGIN
    RETURN QUERY SELECT * FROM base_role_catalogue();
    RETURN QUERY SELECT 'proxy_role_exists'::text,
        EXISTS (SELECT 1 FROM pg_roles WHERE rolname='rk2_proxy'),
        'role = rk2_proxy'::text;
    RETURN QUERY SELECT 'proxy_is_not_owner_or_human'::text,
        EXISTS (SELECT 1 FROM pg_roles WHERE rolname='rk2_proxy')
        AND NOT rk2_role_has_usage('rk2_proxy','rk2_owner')
        AND NOT rk2_role_has_usage('rk2_proxy','rk2_human'),
        'owner=' || rk2_role_has_usage('rk2_proxy','rk2_owner')::text
        || ' human=' || rk2_role_has_usage('rk2_proxy','rk2_human')::text;
END $fn$;

REVOKE ALL ON FUNCTION evaluate_server_runtime(integer,bigint[],text,boolean),
    rk2_role_has_usage(text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION evaluate_server_runtime(integer,bigint[],text,boolean),
    rk2_role_has_usage(text,text) TO rk2_runtime;

COMMENT ON FUNCTION evaluate_server_runtime(integer,bigint[],text,boolean) IS
  'Pure verdict half of the four immutable runtime baseline observations, so every hard check has an executable negative control.';
