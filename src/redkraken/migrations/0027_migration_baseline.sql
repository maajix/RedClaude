-- ---------------------------------------------------------------------------
-- 20260807T191000Z__migration_baseline.sql   (ticket 33)
--
-- Three things this migration adds, all of them enforcement rather than data:
--
--   1. event_table_exempt — every table in `public` must be *classified*.
--      Ticket 07's check_event_log_integrity() can only see tables that already
--      have an event_table_config row, so a migration that adds a table and
--      forgets the config row is invisible to it: no config row, no trigger, no
--      complaint. Classification closes that by making "this table emits
--      nothing" an explicit, reviewed row instead of an absence.
--
--   2. check_event_coverage() — the config/trigger agreement checks ticket 07's
--      integrity function does not make: disabled triggers, triggers pointing at
--      the wrong function, triggers firing on the wrong events, exempt tables
--      that grew a trigger, config rows whose table is gone.
--      check_event_log_integrity() is redefined to include them, so its callers
--      inherit the fix without changing.
--
--   3. check_server_baseline() / assert_server_baseline() — the startup
--      assertion. Ticket 32 pinned Postgres 18 and measured the HNSW build
--      blowing past maintenance_work_mem; both of those are asserted here rather
--      than documented.
--
-- Numbering: the first migration written under the ticket-33 rule. 001..015 are
-- the frozen ticket-32 baseline; everything after it is
-- <UTC timestamp>__<slug>.sql so two sessions authoring at once cannot collide.
-- See ../README.md, "Migration identity and ordering".
-- ---------------------------------------------------------------------------


-- ---------------------------------------------------------------------------
-- 1. Classification
-- ---------------------------------------------------------------------------

-- A table is either in event_table_config (it emits) or in event_table_exempt
-- (it does not, for a stated reason). Being in neither is a defect, not a
-- default. `undecided` is a legal kind precisely so that "nobody has decided"
-- is a row someone can query, rather than silence.
CREATE TABLE event_table_exempt (
    table_name  text PRIMARY KEY,
    exempt_kind text NOT NULL CHECK (exempt_kind IN
                    ('bookkeeping',   -- runner/runtime state, not epistemic state
                     'reference',     -- policy or vocabulary, changed only by migration
                     'derived',       -- recomputable from rows that do emit
                     'log',           -- the event log itself; an event about an event loops
                     'undecided')),   -- charged to a ticket, listed by the checker
    reason      text NOT NULL,
    owner_ticket text
);

INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
    -- the log and its own policy
    ('events',                'log',         'the event log; emitting an event about an event loops', '07'),
    ('event_types',           'reference',   'vocabulary, changed only by migration', '07'),
    ('event_table_config',    'reference',   'emission policy, changed only by migration', '07'),
    ('event_table_exempt',    'reference',   'this classification, changed only by migration', '33'),
    -- (the runner's own schema_migrations is deliberately NOT here: it lives in
    --  schema rk2_meta, outside public, because 017's check_program_isolation()
    --  refuses an unscoped table in public and runner bookkeeping is not
    --  application state. One schema boundary instead of three exception rows.)
    -- added by 016 with no classification of their own -- which is the defect
    -- this table exists to make visible. Classified here because 016 is frozen.
    ('purge_cascade_edges',   'reference',   'the cascade allow-list, changed only by migration', '07'),
    ('suppressed_writes',     'log',         'the record of writes the emitter deliberately did not log; an event about a non-event loops', '07'),
    ('label_prefixes',        'reference',   'label vocabulary, changed only by migration', '06'),
    ('label_counters',        'bookkeeping', 'label allocation counter; the label itself rides on the parent row event', '06'),
    -- policy / vocabulary
    ('transition_rules',      'reference',   'state machine definition, changed only by migration', '06'),
    ('vulnerability_classes', 'reference',   'vocabulary, changed only by migration', '06'),
    ('evidence_profiles',     'reference',   'evidence policy, changed only by migration', '09'),
    -- derived
    ('hypothesis_embeddings', 'derived',     'recomputable from hypotheses; bulk vector, never epistemic content', '06'),
    ('observation_embeddings','derived',     'recomputable from observations; bulk vector, never epistemic content', '06'),

    -- ------------------------------------------------------------------
    -- undecided: ticket 07 gave these no event type and no config row, so
    -- today they are silently outside the completeness claim. Listing them is
    -- the point of this table; deciding them is ticket 07's, not ticket 33's.
    -- ------------------------------------------------------------------
    ('programs',            'undecided', 'no program.created event type exists; the root row emits nothing', '07'),
    ('receipts',            'undecided', 'the provenance record the whole design rests on emits no event', '07'),
    ('tool_runs',           'undecided', 'local-analysis provenance; no tool_run event type exists', '07'),
    ('artifacts',           'undecided', 'content-addressed blob store; no artifact event type exists', '07'),
    ('test_run_receipts',   'undecided', 'edge binding a test run to the receipts it produced', '07'),
    ('finding_evidence',    'undecided', 'ticket 06 makes evidence an edge rather than a node; the edge emits nothing', '07'),
    ('hypothesis_evidence', 'undecided', 'same, on the hypothesis side', '07'),
    ('finding_hypotheses',  'undecided', 'edge from a finding to the hypotheses it aggregates', '07'),
    ('hypothesis_near_matches','undecided','ticket 08 added it so suppression leaves a trace; it leaves no event', '07'),
    ('hypothesis_retest_triggers','undecided','retest scheduling state', '07'),
    ('surface_fingerprints','undecided', 'ticket 29 owns the contents; emission undecided', '07'),
    ('identities',          'undecided', 'secret-adjacent; needs a redaction decision before it can emit', '07'),
    ('scheduler_lanes',     'undecided', 'lane occupancy changes on every claim; volume vs value undecided', '07'),
    ('scheduler_weights',   'undecided', 'weights_version changes are exactly what ticket 08 replay needs', '07'),
    -- class-table detail rows. The parent entities row emits entity.created,
    -- but the detail row holds the data (method, path, port), so the parent
    -- event does not cover a change to it.
    ('hosts',          'undecided', 'class-table detail row; the entities event does not carry its columns', '07'),
    ('domains',        'undecided', 'same', '07'),
    ('services',       'undecided', 'same', '07'),
    ('endpoints',      'undecided', 'same', '07'),
    ('parameters',     'undecided', 'same', '07'),
    ('applications',   'undecided', 'same', '07'),
    ('technologies',   'undecided', 'same', '07');


-- ---------------------------------------------------------------------------
-- 2. Coverage
-- ---------------------------------------------------------------------------

-- Every table in `public` that is not owned by an extension. Partitioned tables
-- ('p') count; the test harness lives in schema t and is out of scope.
CREATE VIEW managed_tables AS
    SELECT c.oid, c.relname AS table_name
      FROM pg_class c
     WHERE c.relnamespace = 'public'::regnamespace
       AND c.relkind IN ('r','p')
       AND NOT EXISTS (SELECT 1 FROM pg_depend d
                        WHERE d.classid = 'pg_class'::regclass
                          AND d.objid = c.oid AND d.deptype = 'e');

-- Same return shape as check_event_log_integrity, so the two compose.
-- `problem` values whose name starts with 'undecided_' are informational; every
-- other row is a defect and assert_event_coverage() raises on it.
CREATE FUNCTION check_event_coverage()
RETURNS TABLE (problem text, detail text, count bigint)
LANGUAGE sql STABLE AS $$
    -- (1) THE HOLE ticket 07's checker cannot see: a migration adds a table and
    -- never says whether it emits. No config row means no trigger means nothing
    -- to compare, so the old checker stays green.
    SELECT 'table_not_classified', m.table_name, 1::bigint
      FROM managed_tables m
     WHERE NOT EXISTS (SELECT 1 FROM event_table_config c WHERE c.table_name = m.table_name)
       AND NOT EXISTS (SELECT 1 FROM event_table_exempt x WHERE x.table_name = m.table_name)

    UNION ALL
    SELECT 'table_classified_twice', c.table_name, 1::bigint
      FROM event_table_config c JOIN event_table_exempt x USING (table_name)

    UNION ALL
    SELECT 'config_row_missing_table', c.table_name, 1::bigint
      FROM event_table_config c
     WHERE NOT EXISTS (SELECT 1 FROM managed_tables m WHERE m.table_name = c.table_name)

    UNION ALL
    SELECT 'exempt_row_missing_table', x.table_name, 1::bigint
      FROM event_table_exempt x
     WHERE NOT EXISTS (SELECT 1 FROM managed_tables m WHERE m.table_name = x.table_name)

    -- (2) ticket 07's original check (a), kept under its original name so its
    -- callers and ticket 32's probes still recognise the row.
    UNION ALL
    SELECT 'config_row_without_trigger', c.table_name, 1::bigint
      FROM event_table_config c
     WHERE EXISTS (SELECT 1 FROM managed_tables m WHERE m.table_name = c.table_name)
       AND NOT EXISTS (
           SELECT 1 FROM pg_trigger t JOIN managed_tables m ON m.oid = t.tgrelid
            WHERE m.table_name = c.table_name
              AND t.tgname = c.table_name || '_emit_event'
              AND NOT t.tgisinternal)

    -- (3) the three states ticket 07's existence test cannot distinguish from
    -- healthy: the trigger is there but off, calls something else, or fires on
    -- fewer events than the config declares.
    -- tgenabled: O = origin (fires normally, skipped under
    -- session_replication_role='replica'), D = disabled, A = always, R = replica
    -- only. 016 made ALWAYS the required state for every enforcement trigger,
    -- because one `SET session_replication_role='replica'` switches all 39 user
    -- triggers off at once. So 'O' is not healthy here -- it is exactly the N1
    -- hole 016 closed, silently reopened. An existence test cannot tell the two
    -- apart and neither could this check before the 016 corpus was applied to it.
    UNION ALL
    SELECT 'trigger_disabled', c.table_name || ' tgenabled=' || t.tgenabled::text, 1::bigint
      FROM event_table_config c
      JOIN managed_tables m ON m.table_name = c.table_name
      JOIN pg_trigger t ON t.tgrelid = m.oid AND t.tgname = c.table_name || '_emit_event'
     WHERE t.tgenabled = 'D'

    UNION ALL
    SELECT 'trigger_not_always', c.table_name || ' tgenabled=' || t.tgenabled::text ||
           ' expected=A', 1::bigint
      FROM event_table_config c
      JOIN managed_tables m ON m.table_name = c.table_name
      JOIN pg_trigger t ON t.tgrelid = m.oid AND t.tgname = c.table_name || '_emit_event'
     WHERE t.tgenabled IN ('O','R')

    UNION ALL
    SELECT 'trigger_wrong_function', c.table_name || ' -> ' || t.tgfoid::regproc::text, 1::bigint
      FROM event_table_config c
      JOIN managed_tables m ON m.table_name = c.table_name
      JOIN pg_trigger t ON t.tgrelid = m.oid AND t.tgname = c.table_name || '_emit_event'
     WHERE t.tgfoid <> 'emit_event'::regproc

    -- tgtype bits: ROW=1, BEFORE=2, INSERT=4, DELETE=8, UPDATE=16.
    -- AFTER INSERT FOR EACH ROW = 5; AFTER INSERT OR UPDATE FOR EACH ROW = 21.
    -- updated_type IS NULL declares the table immutable, so 5 is correct there
    -- and 21 everywhere else. A trigger recreated as INSERT-only on a mutable
    -- table loses every update and looks fine to an existence test.
    UNION ALL
    SELECT 'trigger_wrong_events',
           c.table_name || ' tgtype=' || t.tgtype::text || ' expected=' ||
               CASE WHEN c.updated_type IS NULL THEN 5 ELSE 21 END, 1::bigint
      FROM event_table_config c
      JOIN managed_tables m ON m.table_name = c.table_name
      JOIN pg_trigger t ON t.tgrelid = m.oid AND t.tgname = c.table_name || '_emit_event'
     WHERE t.tgtype <> (CASE WHEN c.updated_type IS NULL THEN 5 ELSE 21 END)::smallint

    -- (3b) the same question asked of EVERY enforcement trigger, not just the
    -- emitters. 016 swept `ENABLE ALWAYS` across the 39 triggers that existed
    -- when it ran; it is a one-shot, so the fortieth -- written by any migration
    -- after it, the ordinary way -- lands at 'O' and is skipped by the same one
    -- `SET session_replication_role='replica'` that 016 was written to survive.
    UNION ALL
    SELECT 'enforcement_trigger_not_always',
           m.table_name || '.' || t.tgname || ' tgenabled=' || t.tgenabled::text, 1::bigint
      FROM pg_trigger t JOIN managed_tables m ON m.oid = t.tgrelid
     WHERE NOT t.tgisinternal AND t.tgenabled <> 'A'
       AND t.tgname <> m.table_name || '_emit_event'   -- reported above, once

    -- (4) drift the other way: a table declared exempt that emits anyway.
    UNION ALL
    SELECT 'exempt_table_has_emit_trigger', x.table_name, 1::bigint
      FROM event_table_exempt x
      JOIN managed_tables m ON m.table_name = x.table_name
      JOIN pg_trigger t ON t.tgrelid = m.oid AND t.tgname = x.table_name || '_emit_event'

    -- (5) informational: not a defect, a debt with a ticket on it.
    UNION ALL
    SELECT 'undecided_emission', 'tables classified undecided, owner ticket ' ||
           coalesce(string_agg(DISTINCT owner_ticket, '/'), '-'), count(*)
      FROM event_table_exempt WHERE exempt_kind = 'undecided'
    HAVING count(*) > 0
$$;

CREATE FUNCTION assert_event_coverage() RETURNS void LANGUAGE plpgsql AS $$
DECLARE r record; n int := 0;
BEGIN
    FOR r IN SELECT * FROM check_event_coverage()
              WHERE problem NOT LIKE 'undecided\_%' LOOP
        RAISE WARNING 'event coverage: % (%)', r.problem, r.detail;
        n := n + 1;
    END LOOP;
    IF n > 0 THEN
        RAISE EXCEPTION 'event coverage check failed: % problem(s); run SELECT * FROM check_event_coverage()', n;
    END IF;
END $$;

-- Fold coverage into ticket 07's entry point. Same signature, same return
-- shape; the (b) row_without_event, (c) event_without_row, (d) last-write and
-- (e) purge-registration bodies are carried over verbatim from 016. Carrying
-- them is the point: CREATE OR REPLACE on a checker is how a check disappears
-- without anyone deleting a line, and the first draft of this file dropped (d)
-- and (e) exactly that way -- which is why check_b B13 went red and nothing
-- else did. A replacement of a checker may only ADD rows.
CREATE OR REPLACE FUNCTION check_event_log_integrity(p_program uuid DEFAULT NULL)
RETURNS TABLE (problem text, detail text, count bigint)
LANGUAGE plpgsql AS $$
DECLARE c event_table_config%ROWTYPE;
BEGIN
    RETURN QUERY SELECT * FROM check_event_coverage();

    FOR c IN SELECT * FROM event_table_config LOOP
        RETURN QUERY EXECUTE format($q$
            SELECT 'row_without_event', %L, count(*)::bigint
              FROM %I r
             WHERE (%L::uuid IS NULL OR r.program_id = %L::uuid)
               AND NOT EXISTS (SELECT 1 FROM events e
                                WHERE e.subject_table = %L
                                  AND e.subject_id = r.id
                                  AND e.type = %L)
            HAVING count(*) > 0 $q$,
            c.table_name, c.table_name, p_program, p_program,
            c.table_name, c.created_type);

        RETURN QUERY EXECUTE format($q$
            SELECT 'event_without_row', %L, count(*)::bigint
              FROM events e
             WHERE e.subject_table = %L
               AND (%L::uuid IS NULL OR e.program_id = %L::uuid)
               AND NOT EXISTS (SELECT 1 FROM %I r WHERE r.id = e.subject_id)
            HAVING count(*) > 0 $q$,
            c.table_name, c.table_name, p_program, p_program, c.table_name);

        -- (d) the row's LAST write, not just its first (016).
        RETURN QUERY EXECUTE format($q$
            SELECT 'row_last_write_unaccounted', %L, count(*)::bigint
              FROM %I r
             WHERE (%L::uuid IS NULL OR r.program_id = %L::uuid)
               AND r.xmin::text::bigint <> 2
               AND NOT EXISTS (
                     SELECT 1 FROM events e
                      WHERE e.subject_table = %L AND e.subject_id = r.id
                        AND (e.xact_id::text::numeric %% 4294967296)::bigint
                            = r.xmin::text::bigint)
               AND NOT EXISTS (
                     SELECT 1 FROM suppressed_writes s
                      WHERE s.table_name = %L
                        AND s.program_id = r.program_id
                        AND (s.xact_id::text::numeric %% 4294967296)::bigint
                            = r.xmin::text::bigint)
            HAVING count(*) > 0 $q$,
            c.table_name, c.table_name, p_program, p_program,
            c.table_name, c.table_name);
    END LOOP;

    -- (e) the purge rule (016): a delete action nobody registered.
    RETURN QUERY
    SELECT 'fk_delete_action_not_no_action',
           src.relname || '.' || con.conname, 1::bigint
      FROM pg_constraint con
      JOIN pg_class src ON src.oid = con.conrelid
     WHERE con.contype = 'f'
       AND src.relnamespace = 'public'::regnamespace
       AND con.confdeltype IN ('c','n','d')
       AND NOT EXISTS (
             SELECT 1 FROM purge_cascade_edges e
              WHERE e.table_name  = src.relname
                AND e.column_name = (SELECT a.attname FROM pg_attribute a
                                      WHERE a.attrelid = con.conrelid
                                        AND a.attnum = con.conkey[1]));
END $$;


-- The other half of the finalizer. attach_event_triggers() (016) makes the
-- emitters ALWAYS; this makes everything else ALWAYS, so a migration author who
-- writes a plain CREATE TRIGGER gets the 016 property without knowing about it.
-- Idempotent, and run by ./migrate.sh at the end of every run, which is the only
-- place that can see the whole corpus at once.
CREATE FUNCTION enforce_always_triggers() RETURNS int LANGUAGE plpgsql AS $$
DECLARE r record; n int := 0;
BEGIN
    FOR r IN SELECT m.table_name AS tbl, t.tgname
               FROM pg_trigger t JOIN managed_tables m ON m.oid = t.tgrelid
              WHERE NOT t.tgisinternal AND t.tgenabled = 'O' LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ALWAYS TRIGGER %I', r.tbl, r.tgname);
        n := n + 1;
    END LOOP;
    RETURN n;   -- a deliberately DISABLEd trigger ('D') is left alone and
END $$;         -- reported by check_event_coverage() instead of being papered over.

-- ---------------------------------------------------------------------------
-- 3. The startup assertion
-- ---------------------------------------------------------------------------

-- Measured on pgvector/pgvector:pg18 (18.4 / pgvector 0.8.6), 20 000 rows of
-- vector(1536). pgvector reports "hnsw graph no longer fits into
-- maintenance_work_mem after N tuples" at N = maintenance_work_mem / this
-- constant. Three observations, three settings:
--
--     32MB  ->  4879 tuples  =>  6877 bytes/tuple
--     64MB  ->  9751 tuples  =>  6883 bytes/tuple
--    128MB  -> 19505 tuples  =>  6883 bytes/tuple
--
-- (./measure_hnsw.sh reproduces all three.) 4*dim + 750 = 6894 at dim 1536,
-- which is ~0.2% ABOVE the measured cost, so the predicted capacity errs low --
-- the check warns slightly early rather than slightly late. Only the
-- 1536-dimension case has been measured; the linear term is a guess that the
-- other dimensions have not tested.
CREATE FUNCTION hnsw_bytes_per_tuple(p_dim int DEFAULT 1536) RETURNS bigint
LANGUAGE sql IMMUTABLE AS $$ SELECT 4::bigint * p_dim + 750 $$;

-- How many more rows an HNSW build can take before it spills. Negative means
-- the next REINDEX or CREATE INDEX on that table already builds off-disk.
CREATE VIEW hnsw_headroom AS
    SELECT t.table_name,
           t.rows,
           -- pg_settings.setting for maintenance_work_mem is in kB
           ((SELECT setting::bigint FROM pg_settings WHERE name = 'maintenance_work_mem') * 1024)
               / hnsw_bytes_per_tuple(1536) AS capacity_rows,
           ((SELECT setting::bigint FROM pg_settings WHERE name = 'maintenance_work_mem') * 1024)
               / hnsw_bytes_per_tuple(1536) - t.rows AS headroom_rows
      FROM (SELECT 'hypothesis_embeddings'::text  AS table_name,
                   (SELECT count(*) FROM hypothesis_embeddings)  AS rows
            UNION ALL
            SELECT 'observation_embeddings',
                   (SELECT count(*) FROM observation_embeddings)) t;

-- One row per check. `ok=false` is what assert_server_baseline() raises on.
-- p_expected_migrations is the on-disk migration set: the database cannot see
-- the filesystem, so the caller passes it and this asserts set equality both
-- ways. NULL skips that check.
CREATE FUNCTION check_server_baseline(p_expected_migrations text[] DEFAULT NULL)
RETURNS TABLE (check_name text, ok boolean, detail text)
LANGUAGE plpgsql STABLE AS $$
DECLARE v_mwm bigint; v_src text; v_pgv text; v_n int;
BEGIN
    -- Force the pgvector library into this backend so its GUCs stop being
    -- unvalidated placeholders and appear in pg_settings with a real source.
    PERFORM '[1]'::vector;

    -- --- server major -----------------------------------------------------
    -- 18 is a floor and a ceiling: 18 is what uuidv7() needs, and 18 is the
    -- only major the corpus has ever been applied to.
    RETURN QUERY SELECT 'server_major'::text,
        current_setting('server_version_num')::int BETWEEN 180000 AND 189999,
        'server_version = ' || current_setting('server_version');

    -- The forcing feature itself, not a proxy for it. oid < 16384 means
    -- pg_catalog builtin rather than something an extension supplied.
    -- Aggregated rather than read as a scalar subquery: a second zero-argument
    -- uuidv7() in any schema would make the scalar form raise 21000, and a
    -- check that aborts the whole baseline is worse than the shadowing it found.
    RETURN QUERY SELECT 'uuidv7_is_builtin'::text,
        coalesce((SELECT bool_or(oid < 16384) FROM pg_proc WHERE proname = 'uuidv7' AND pronargs = 0), false),
        'uuidv7 oid = ' || coalesce(
            (SELECT string_agg(oid::text, ', ' ORDER BY oid) FROM pg_proc
              WHERE proname = 'uuidv7' AND pronargs = 0), '<absent>');

    -- --- pgvector ---------------------------------------------------------
    SELECT extversion INTO v_pgv FROM pg_extension WHERE extname = 'vector';
    -- 0.8.0 is the floor: hnsw.iterative_scan does not exist below it, and
    -- without it a filtered nearest-neighbour query silently under-returns.
    RETURN QUERY SELECT 'pgvector_version'::text,
        coalesce(string_to_array(v_pgv, '.')::int[] >= ARRAY[0,8,0], false),
        'pgvector = ' || coalesce(v_pgv, '<absent>');

    RETURN QUERY SELECT 'hnsw_cosine_opclass'::text,
        EXISTS (SELECT 1 FROM pg_opclass o JOIN pg_am a ON a.oid = o.opcmethod
                 WHERE a.amname = 'hnsw' AND o.opcname = 'vector_cosine_ops'),
        'hnsw / vector_cosine_ops'::text;

    -- --- shipped settings -------------------------------------------------
    -- source = 'database' proves the value came from the settings migration
    -- (ALTER DATABASE ... SET) rather than from a session that happened to SET
    -- it, or from a hand-edited postgresql.conf nobody has in git.
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
        coalesce((SELECT setting::int >= 40000 FROM pg_settings WHERE name = 'hnsw.max_scan_tuples'), false),
        'hnsw.max_scan_tuples = ' || coalesce((SELECT setting FROM pg_settings WHERE name='hnsw.max_scan_tuples'), '<absent>');

    RETURN QUERY SELECT 'hnsw_headroom'::text,
        (SELECT bool_and(headroom_rows > 0) FROM hnsw_headroom),
        (SELECT string_agg(table_name || ' ' || rows || '/' || capacity_rows, ', ')
           FROM hnsw_headroom);

    -- --- settings that must NOT have been changed -------------------------
    -- 'replica' makes every AFTER trigger stop firing, which is exactly how
    -- ticket 32 produced a row with no event. A session that leaves it set
    -- turns the event log's completeness claim off with no error anywhere.
    RETURN QUERY SELECT 'session_replication_role'::text,
        current_setting('session_replication_role') = 'origin',
        'session_replication_role = ' || current_setting('session_replication_role');

    -- The claim protocol is FOR UPDATE SKIP LOCKED; under repeatable read a
    -- skipped row becomes a serialization failure instead of a skip.
    RETURN QUERY SELECT 'default_transaction_isolation'::text,
        current_setting('default_transaction_isolation') = 'read committed',
        'default_transaction_isolation = ' || current_setting('default_transaction_isolation');

    -- --- migrations -------------------------------------------------------
    RETURN QUERY SELECT 'schema_migrations_present'::text,
        to_regclass('rk2_meta.schema_migrations') IS NOT NULL,
        'schema_migrations'::text;

    IF to_regclass('rk2_meta.schema_migrations') IS NOT NULL THEN
        -- The ordering rule, asserted rather than trusted: applied_seq (the
        -- order the runner actually applied them) must agree with id order
        -- (the order the filenames declare). They diverge when a migration from
        -- a concurrently authored branch lands after one that sorts later.
        SELECT count(*) INTO v_n FROM (
            SELECT id, applied_seq,
                   lag(id) OVER (ORDER BY applied_seq) AS prev_id
              FROM rk2_meta.schema_migrations) s
         WHERE prev_id IS NOT NULL AND id < prev_id;
        RETURN QUERY SELECT 'migrations_in_declared_order'::text, v_n = 0,
            v_n || ' migration(s) applied out of filename order';

        IF p_expected_migrations IS NOT NULL THEN
            SELECT count(*) INTO v_n FROM (
                SELECT id FROM rk2_meta.schema_migrations
                EXCEPT SELECT unnest(p_expected_migrations)) s;
            RETURN QUERY SELECT 'no_unknown_migrations'::text, v_n = 0,
                v_n || ' migration(s) in the database with no file';
            SELECT count(*) INTO v_n FROM (
                SELECT unnest(p_expected_migrations)
                EXCEPT SELECT id FROM rk2_meta.schema_migrations) s;
            RETURN QUERY SELECT 'no_pending_migrations'::text, v_n = 0,
                v_n || ' migration file(s) not applied';
        END IF;
    END IF;

    -- --- event coverage ---------------------------------------------------
    SELECT count(*) INTO v_n FROM check_event_coverage()
     WHERE problem NOT LIKE 'undecided\_%';
    RETURN QUERY SELECT 'event_coverage'::text, v_n = 0,
        v_n || ' coverage problem(s)';
END $$;

CREATE FUNCTION assert_server_baseline(p_expected_migrations text[] DEFAULT NULL)
RETURNS void LANGUAGE plpgsql AS $$
DECLARE r record; n int := 0;
BEGIN
    FOR r IN SELECT * FROM check_server_baseline(p_expected_migrations) WHERE NOT ok LOOP
        RAISE WARNING 'baseline: % FAILED -- %', r.check_name, r.detail;
        n := n + 1;
    END LOOP;
    IF n > 0 THEN
        RAISE EXCEPTION 'server baseline assertion failed: % check(s); run SELECT * FROM check_server_baseline()', n;
    END IF;
END $$;
