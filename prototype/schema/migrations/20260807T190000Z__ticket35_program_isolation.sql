-- ---------------------------------------------------------------------------
-- 017_ticket35_program_isolation.sql   (ticket 35)
--
-- The isolation model, stated once:
--
--   1. ONE DATABASE FOR ALL PROGRAMS. Not one per program. `program_id` is
--      already on 20 tables, the unit of deletion is `DELETE FROM programs`,
--      ticket 08 takes `pg_advisory_lock(program_id)` for one scheduler loop
--      per program, and ten tables are deliberately global -- `artifacts` is
--      content-addressed and refcounted across programs by
--      `artifacts_due_for_purge`, `transition_rules` and `scheduler_weights`
--      are one shared policy. A database per program would have to fork all
--      ten. Isolation here is a constraint problem, not a deployment one.
--
--   2. EVERY TABLE IS PROGRAM-SCOPED UNLESS DECLARED GLOBAL. "Program-scoped"
--      is decidable, not curated: the table has a `program_id` column. The
--      fifteen derived tables that were scoped only by inheritance from their
--      owner (the eight entity-detail tables and the seven edge tables) now
--      carry one too, derived from that owner and verified against it.
--      `program_global_tables` names the exceptions and says why.
--
--   3. EVERY FOREIGN KEY BETWEEN TWO PROGRAM-SCOPED ROWS CARRIES `program_id`
--      ON BOTH SIDES. A total rule, not a list of the places someone thought
--      of. Ticket 32's C24/C25/C26 are three of roughly forty edges that were
--      open; a hand-picked list is exactly what produced those three.
--      `cross_program_exempt_fks` is the escape hatch and is empty.
--
--   4. NO UNIQUE NAMESPACE ON A PROGRAM-SCOPED TABLE IS GLOBAL.
--      `identities_slot_idx` was `UNIQUE (slot_name)`: two programs could
--      never both have a `userA`. It becomes `UNIQUE (program_id, slot_name)`.
--      This is the one the ticket names, and a catalog sweep says it was the
--      only one -- every other global unique key is on genuine reference data.
--
--   5. THE SCHEDULER NEVER RANKS ACROSS PROGRAMS. It already could not:
--      `tasks_queue_idx` is `(program_id, priority DESC ...)`, the loop is one
--      asyncio task per program under `pg_advisory_lock(program_id)`, and
--      `scheduler_lanes` is keyed `(program_id, kind)`. After this migration
--      it also *cannot*: a task pointing at another program's hypothesis,
--      finding or entity is a foreign key violation. The shared Claude rate
--      budget is admission control, not ordering.
--
-- `check_program_isolation()` is rules 2, 3 and 4 as a query -- checks (a),
-- (b), (c) -- so a later migration cannot quietly reopen any of them. Same
-- shape as `purge_cascade_edges` + `check_event_log_integrity()` from ticket
-- 07. Checks (d) and (e) are two mechanical invariants rule 3 itself can
-- destroy: the order two foreign keys fire in, and the NULL that switches a
-- MATCH SIMPLE composite key off. (d) is not a hypothetical -- rewriting 70
-- keys in name order broke the whole-program purge on the first run.
--
-- The migration ends by requiring `check_program_isolation()` to be silent, so
-- applying it is itself the proof, not just the checks that follow it.
-- ---------------------------------------------------------------------------

SET client_min_messages = notice;


-- ===========================================================================
-- Rule 2 -- program-scoped is a column, so it can be tested
-- ===========================================================================

CREATE OR REPLACE FUNCTION is_program_scoped(p_rel regclass) RETURNS boolean
LANGUAGE sql STABLE AS $$
    SELECT EXISTS (SELECT 1 FROM pg_attribute
                    WHERE attrelid = p_rel AND attname = 'program_id'
                      AND attnum > 0 AND NOT attisdropped)
$$;

-- A derived row's program is not an independent fact; it is a consequence of
-- its owner. Making the runtime restate it invites it to state it wrong, so
-- the database derives it when the caller leaves it NULL -- and the composite
-- foreign key added below checks it either way. Supplying a wrong one is a
-- constraint violation, not a silent overwrite.
CREATE OR REPLACE FUNCTION derive_program_id() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE v_key uuid; v_pid uuid;
BEGIN
    IF NEW.program_id IS NOT NULL THEN RETURN NEW; END IF;
    v_key := (to_jsonb(NEW) ->> TG_ARGV[0])::uuid;
    EXECUTE format('SELECT program_id FROM %I WHERE %I = $1', TG_ARGV[1], TG_ARGV[2])
       INTO v_pid USING v_key;
    IF v_pid IS NULL THEN
        RAISE EXCEPTION '%.% = % has no owning row in %: program_id cannot be derived',
              TG_TABLE_NAME, TG_ARGV[0], v_key, TG_ARGV[1];
    END IF;
    NEW.program_id := v_pid;
    RETURN NEW;
END $$;

-- Which owner each derived table hangs off is already recorded: it is exactly
-- the column ticket 07 registered in `purge_cascade_edges`, because "the row
-- the purge deletes me with" and "the row I get my program from" are the same
-- row. Reading it from there keeps the two mechanisms in step by construction.
DO $$
DECLARE r record; v_parent text; v_key text;
BEGIN
    FOR r IN SELECT e.table_name, e.column_name
               FROM purge_cascade_edges e
              WHERE NOT is_program_scoped(e.table_name::regclass)
              ORDER BY e.table_name
    LOOP
        SELECT tgt.relname,
               (SELECT a.attname FROM pg_attribute a
                 WHERE a.attrelid = con.confrelid AND a.attnum = con.confkey[1])
          INTO v_parent, v_key
          FROM pg_constraint con
          JOIN pg_class tgt ON tgt.oid = con.confrelid
         WHERE con.contype = 'f'
           AND con.conrelid = r.table_name::regclass
           AND array_length(con.conkey, 1) = 1
           AND (SELECT a.attname FROM pg_attribute a
                 WHERE a.attrelid = con.conrelid AND a.attnum = con.conkey[1])
               = r.column_name;

        IF v_parent IS NULL THEN
            RAISE EXCEPTION 'no single-column FK on %.% to derive program_id from',
                  r.table_name, r.column_name;
        END IF;

        EXECUTE format('ALTER TABLE %I ADD COLUMN program_id uuid', r.table_name);
        EXECUTE format('UPDATE %I d SET program_id = p.program_id
                          FROM %I p WHERE p.%I = d.%I',
                       r.table_name, v_parent, v_key, r.column_name);
        EXECUTE format('ALTER TABLE %I ALTER COLUMN program_id SET NOT NULL',
                       r.table_name);
        EXECUTE format('CREATE TRIGGER %I BEFORE INSERT ON %I FOR EACH ROW
                        EXECUTE FUNCTION derive_program_id(%L, %L, %L)',
                       r.table_name || '_derive_program_id', r.table_name,
                       r.column_name, v_parent, v_key);
        RAISE NOTICE 'isolation: %.program_id derived from %.% via %',
                     r.table_name, v_parent, v_key, r.column_name;
    END LOOP;
END $$;

-- No `REFERENCES programs(id)` on the derived tables. The composite key to the
-- owner pins the program already, and a second edge would put a sixteenth
-- delete action into the purge graph that `purge_cascade_edges` and check B13
-- would then have to carry for nothing.


-- ===========================================================================
-- Rule 3 -- every cross-row citation carries the program
-- ===========================================================================

-- The candidate set, once: a foreign key whose source and target are both
-- program-scoped and whose key does not already mention `program_id`.
-- MATCH FULL is excluded here and handled separately below.
CREATE OR REPLACE VIEW program_isolation_candidates AS
SELECT con.oid                AS conoid,
       con.conname            AS conname,
       src.relname            AS src_tbl,
       tgt.relname            AS tgt_tbl,
       (SELECT array_agg(a.attname ORDER BY k.ord)
          FROM unnest(con.conkey) WITH ORDINALITY k(attnum, ord)
          JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k.attnum)
                              AS srccols,
       (SELECT array_agg(a.attname ORDER BY k.ord)
          FROM unnest(con.confkey) WITH ORDINALITY k(attnum, ord)
          JOIN pg_attribute a ON a.attrelid = con.confrelid AND a.attnum = k.attnum)
                              AS tgtcols,
       CASE con.confdeltype WHEN 'c' THEN ' ON DELETE CASCADE'
                            WHEN 'n' THEN ' ON DELETE SET NULL'
                            WHEN 'd' THEN ' ON DELETE SET DEFAULT'
                            WHEN 'r' THEN ' ON DELETE RESTRICT'
                            ELSE '' END AS del_clause,
       CASE con.confupdtype WHEN 'c' THEN ' ON UPDATE CASCADE'
                            WHEN 'n' THEN ' ON UPDATE SET NULL'
                            WHEN 'd' THEN ' ON UPDATE SET DEFAULT'
                            WHEN 'r' THEN ' ON UPDATE RESTRICT'
                            ELSE '' END AS upd_clause
  FROM pg_constraint con
  JOIN pg_class src ON src.oid = con.conrelid
  JOIN pg_class tgt ON tgt.oid = con.confrelid
 WHERE con.contype = 'f'
   AND src.relnamespace = 'public'::regnamespace
   AND tgt.relnamespace = 'public'::regnamespace
   AND is_program_scoped(src.oid::regclass)
   AND is_program_scoped(tgt.oid::regclass)
   AND con.confmatchtype <> 'f'
   AND NOT EXISTS (SELECT 1 FROM unnest(con.conkey) ck
                     JOIN pg_attribute a ON a.attrelid = con.conrelid
                                        AND a.attnum = ck
                    WHERE a.attname = 'program_id');

-- 3a: every target needs a unique key that includes program_id.
DO $$
DECLARE v_set jsonb; r record; v_cols text; v_name text;
BEGIN
    SELECT coalesce(jsonb_agg(x), '[]'::jsonb) INTO v_set
      FROM (SELECT DISTINCT tgt_tbl, tgtcols FROM program_isolation_candidates) x;

    FOR r IN SELECT * FROM jsonb_to_recordset(v_set)
                          AS y(tgt_tbl text, tgtcols text[])
    LOOP
        SELECT string_agg(quote_ident(c), ', ' ORDER BY o) INTO v_cols
          FROM unnest(r.tgtcols || 'program_id'::text) WITH ORDINALITY u(c, o);
        v_name := r.tgt_tbl || '_' || array_to_string(r.tgtcols, '_') || '_program_key';

        IF NOT EXISTS (SELECT 1 FROM pg_constraint
                        WHERE conname = v_name
                          AND conrelid = r.tgt_tbl::regclass) THEN
            EXECUTE format('ALTER TABLE %I ADD CONSTRAINT %I UNIQUE (%s)',
                           r.tgt_tbl, v_name, v_cols);
            RAISE NOTICE 'isolation: UNIQUE %(%)', r.tgt_tbl, v_cols;
        END IF;
    END LOOP;
END $$;

-- 3b: rewrite each key to carry program_id.
--
-- `program_id` is appended LAST, never prepended. `purge_cascade_edges`, check
-- B13 and `check_event_log_integrity()` check (e) all identify a foreign key
-- by `conkey[1]`, so the first column has to stay the one it was. The
-- definition is rebuilt from catalog columns rather than by editing the text
-- of `pg_get_constraintdef`, and MATCH SIMPLE means a NULL reference still
-- skips the check -- which is what `parent_run_id`, `superseded_by`,
-- `duplicate_of_finding_id` and `supersedes_test_id` need.
--
-- THE ORDER OF THIS LOOP IS LOAD-BEARING, and finding that out cost a run.
-- Dropping and re-adding a foreign key gives it a new OID, and Postgres fires
-- AFTER-row triggers in alphabetical order of trigger name -- RI trigger names
-- are `RI_ConstraintTrigger_a_<oid>`. Every entity-detail table has two keys to
-- `entities`: `X_entity_id_fkey` ON DELETE CASCADE, and the type-pinning
-- `X_entity_id_entity_type_fkey` with no action. Deleting a program only works
-- because the cascade removes the detail row before the NO ACTION check looks
-- for it. Rebuilding in name order put `..._entity_type_fkey` first and the
-- whole-program purge started failing with
-- `violates foreign key constraint "applications_entity_id_entity_type_fkey"`
-- -- but only for a program that actually had detail rows, which is why B25
-- still passed and C81 is the check that caught it. Rebuilding in the original
-- OID order reproduces the order the catalog already had. Rule (d) of
-- `check_program_isolation()` is that invariant, so it cannot go quiet again.
DO $$
DECLARE v_set jsonb; r record; v_src text; v_tgt text; n int := 0;
BEGIN
    SELECT coalesce(jsonb_agg(x ORDER BY x.conoid), '[]'::jsonb) INTO v_set
      FROM (SELECT conoid, conname, src_tbl, tgt_tbl, srccols, tgtcols,
                   del_clause, upd_clause
              FROM program_isolation_candidates) x;

    FOR r IN SELECT * FROM jsonb_to_recordset(v_set)
                          AS y(conoid oid, conname text, src_tbl text,
                               tgt_tbl text, srccols text[], tgtcols text[],
                               del_clause text, upd_clause text)
    LOOP
        SELECT string_agg(quote_ident(c), ', ' ORDER BY o) INTO v_src
          FROM unnest(r.srccols || 'program_id'::text) WITH ORDINALITY u(c, o);
        SELECT string_agg(quote_ident(c), ', ' ORDER BY o) INTO v_tgt
          FROM unnest(r.tgtcols || 'program_id'::text) WITH ORDINALITY u(c, o);

        EXECUTE format('ALTER TABLE %I DROP CONSTRAINT %I', r.src_tbl, r.conname);
        EXECUTE format('ALTER TABLE %I ADD CONSTRAINT %I
                        FOREIGN KEY (%s) REFERENCES %I (%s)%s%s',
                       r.src_tbl, r.conname, v_src, r.tgt_tbl, v_tgt,
                       r.del_clause, r.upd_clause);
        n := n + 1;
        RAISE NOTICE 'isolation: %.% now (%) -> %(%)',
                     r.src_tbl, r.conname, v_src, r.tgt_tbl, v_tgt;
    END LOOP;
    RAISE NOTICE 'isolation: % foreign keys now carry program_id', n;
END $$;

-- 3c: the one key that cannot be rewritten in place.
--
-- `findings_validated_run_holds_fk` is MATCH FULL by design (ticket 06): it is
-- what makes "validated by a run that did not hold" impossible, and MATCH FULL
-- is how a partly-NULL key is refused. Appending a NOT NULL `program_id` to it
-- would also make `validated_by_test_run_id` mandatory on every finding.
-- So it keeps its shape, and a MATCH SIMPLE sibling rooted at the same column
-- carries the program. `check_program_isolation()` knows about siblings.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conname = 'test_runs_id_program_key'
                      AND conrelid = 'test_runs'::regclass) THEN
        ALTER TABLE test_runs ADD CONSTRAINT test_runs_id_program_key
            UNIQUE (id, program_id);
    END IF;
END $$;

ALTER TABLE findings
    ADD CONSTRAINT findings_validated_run_program_fk
    FOREIGN KEY (validated_by_test_run_id, program_id)
    REFERENCES test_runs (id, program_id);


-- ===========================================================================
-- Rule 4 -- the slot namespace belongs to the program
-- ===========================================================================

-- Was `UNIQUE (slot_name)`, with a comment claiming slot names are
-- proxy-global. They are not global; the proxy is per program. Ticket 04's
-- addon carries no program dimension at all -- `receipts.py` writes an
-- `identity` column and nothing else -- so one listener already means one
-- program, and `X-RedKraken-Identity: userA` stays unambiguous inside it.
-- What changes is the proxy's lookup key: `(program_id, slot_name)`, with the
-- program coming from the listener's configuration, never from the agent.
CREATE UNIQUE INDEX identities_slot_program_idx
    ON identities (program_id, slot_name)
 INCLUDE (entity_id);

DROP INDEX identities_slot_idx;
ALTER INDEX identities_slot_program_idx RENAME TO identities_slot_idx;


-- ===========================================================================
-- The registries, and the rules as a query
-- ===========================================================================

CREATE TABLE program_global_tables (
    table_name text PRIMARY KEY,
    reason     text NOT NULL
);

INSERT INTO program_global_tables (table_name, reason) VALUES
    ('programs',              'the root: its own id is the program'),
    ('artifacts',             'content-addressed. A sha256 carries no program claim and the same bytes seen by two programs are one row; artifacts_due_for_purge already refcounts across programs'),
    ('vulnerability_classes', 'reference data: CWE'),
    ('transition_rules',      'one state machine for the whole system, not per program'),
    ('evidence_profiles',     'shipped with skills, not with programs'),
    ('event_types',           'the event vocabulary'),
    ('event_table_config',    'which tables emit; a property of the schema'),
    ('label_prefixes',        'the label vocabulary; label_counters is the per-program half'),
    ('purge_cascade_edges',   'the purge graph; a property of the schema'),
    ('scheduler_weights',     'one active policy version for the whole scheduler'),
    ('program_global_tables', 'this registry: the list of exceptions is itself one'),
    ('cross_program_exempt_fks', 'the escape-hatch registry, for the same reason');

CREATE TABLE cross_program_exempt_fks (
    table_name      text NOT NULL,
    constraint_name text NOT NULL,
    reason          text NOT NULL,
    PRIMARY KEY (table_name, constraint_name)
);

COMMENT ON TABLE cross_program_exempt_fks IS
  'Foreign keys allowed to link two program-scoped rows without carrying program_id. Empty. A row here is a decision to let one program cite another and should read like one.';

-- Rules 2, 3 and 4, as something a later migration has to survive.
CREATE OR REPLACE FUNCTION check_program_isolation()
RETURNS TABLE (problem text, detail text) LANGUAGE sql STABLE AS $$
    -- (a) rule 3: a citation between two program-scoped rows that does not
    --     carry the program, is not covered by a sibling key that does, and is
    --     not declared exempt.
    SELECT 'fk_not_program_carrying'::text,
           src.relname || '.' || con.conname || ' -> ' || tgt.relname
      FROM pg_constraint con
      JOIN pg_class src ON src.oid = con.conrelid
      JOIN pg_class tgt ON tgt.oid = con.confrelid
     WHERE con.contype = 'f'
       AND src.relnamespace = 'public'::regnamespace
       AND tgt.relnamespace = 'public'::regnamespace
       AND is_program_scoped(src.oid::regclass)
       AND is_program_scoped(tgt.oid::regclass)
       AND NOT EXISTS (SELECT 1 FROM unnest(con.conkey) ck
                         JOIN pg_attribute a ON a.attrelid = con.conrelid
                                            AND a.attnum = ck
                        WHERE a.attname = 'program_id')
       AND NOT EXISTS (SELECT 1 FROM pg_constraint sib
                        WHERE sib.contype = 'f'
                          AND sib.conrelid = con.conrelid
                          AND sib.confrelid = con.confrelid
                          AND sib.oid <> con.oid
                          AND sib.conkey[1] = con.conkey[1]
                          AND EXISTS (SELECT 1 FROM unnest(sib.conkey) sk
                                        JOIN pg_attribute a2
                                          ON a2.attrelid = sib.conrelid
                                         AND a2.attnum = sk
                                       WHERE a2.attname = 'program_id'))
       AND NOT EXISTS (SELECT 1 FROM cross_program_exempt_fks e
                        WHERE e.table_name = src.relname
                          AND e.constraint_name = con.conname)
UNION ALL
    -- (b) rule 2: a table that is neither program-scoped nor declared global.
    SELECT 'table_not_program_scoped', c.relname
      FROM pg_class c
     WHERE c.relkind = 'r'
       AND c.relnamespace = 'public'::regnamespace
       AND NOT is_program_scoped(c.oid::regclass)
       AND NOT EXISTS (SELECT 1 FROM program_global_tables g
                        WHERE g.table_name = c.relname)
UNION ALL
    -- (c) rule 4: a unique namespace on a program-scoped table that is global.
    --     A key column that is a uuid is already program-scoped -- every id in
    --     this schema is a uuidv7 and unique on its own -- so the rule only
    --     bites on human-meaningful keys like `slot_name`, which is the class
    --     of key that can collide between two programs by coincidence.
    SELECT 'unique_namespace_not_program_scoped',
           c.relname || '.' || i.relname
      FROM pg_index x
      JOIN pg_class i ON i.oid = x.indexrelid
      JOIN pg_class c ON c.oid = x.indrelid
     WHERE x.indisunique
       AND c.relnamespace = 'public'::regnamespace
       AND is_program_scoped(c.oid::regclass)
       AND NOT EXISTS (
             SELECT 1
               FROM unnest(x.indkey::int2[]) WITH ORDINALITY u(attnum, ord)
               JOIN pg_attribute a ON a.attrelid = x.indrelid
                                  AND a.attnum = u.attnum
              WHERE u.ord <= x.indnkeyatts
                AND (a.attname = 'program_id' OR a.atttypid = 'uuid'::regtype))
UNION ALL
    -- (d) the purge depends on the order two foreign keys fire in. On DELETE
    --     of a parent row the ON DELETE CASCADE that removes the child must
    --     run before the NO ACTION check that would find the child still
    --     there. Postgres fires AFTER-row triggers in alphabetical order of
    --     trigger name and RI trigger names embed the constraint OID, so
    --     rebuilding a key moves it in that order. Rewriting the keys is
    --     exactly what this migration does, so the invariant it can break is
    --     the one it has to assert.
    SELECT 'cascade_fires_after_noaction',
           x.child || ' -> ' || x.parent || ': ' || x.first_noaction
                   || ' fires before ' || x.last_cascade
      FROM (SELECT src.relname AS child, tgt.relname AS parent,
                   max(tg.tgname) FILTER (WHERE con.confdeltype = 'c')
                                                        AS last_cascade,
                   min(tg.tgname) FILTER (WHERE con.confdeltype = 'a')
                                                        AS first_noaction
              FROM pg_constraint con
              JOIN pg_class src ON src.oid = con.conrelid
              JOIN pg_class tgt ON tgt.oid = con.confrelid
              JOIN pg_trigger tg ON tg.tgconstraint = con.oid
                                AND tg.tgrelid = con.confrelid
             WHERE con.contype = 'f'
               AND src.relnamespace = 'public'::regnamespace
             GROUP BY 1, 2) x
     WHERE x.last_cascade IS NOT NULL
       AND x.first_noaction IS NOT NULL
       AND x.last_cascade > x.first_noaction
UNION ALL
    -- (e) rule 3 is written MATCH SIMPLE, which means a NULL anywhere in the
    --     key skips the entire check. That is deliberate for a nullable
    --     citation like `superseded_by`, but if `program_id` itself were
    --     nullable on a citing table, one NULL would switch off every guard on
    --     that row at once. So a program-scoped table that cites another one
    --     must have `program_id NOT NULL`. `scheduler_lanes` is the schema's
    --     only nullable `program_id` -- NULL there means the default lane --
    --     and it cites nothing program-scoped, so it needs no exemption.
    SELECT DISTINCT 'program_id_nullable_on_citing_table', src.relname
      FROM pg_constraint con
      JOIN pg_class src ON src.oid = con.conrelid
      JOIN pg_class tgt ON tgt.oid = con.confrelid
      JOIN pg_attribute a ON a.attrelid = src.oid AND a.attname = 'program_id'
     WHERE con.contype = 'f'
       AND src.relnamespace = 'public'::regnamespace
       AND is_program_scoped(tgt.oid::regclass)
       AND NOT a.attnotnull
       AND EXISTS (SELECT 1 FROM unnest(con.conkey) ck
                     JOIN pg_attribute b ON b.attrelid = con.conrelid
                                        AND b.attnum = ck
                    WHERE b.attname = 'program_id')
$$;

-- The migration refuses to finish leaving any of the five open.
DO $$
DECLARE v text;
BEGIN
    SELECT string_agg(problem || ' ' || detail, '; ' ORDER BY problem, detail)
      INTO v FROM check_program_isolation();
    IF v IS NOT NULL THEN
        RAISE EXCEPTION 'program isolation is not closed after 017: %', v;
    END IF;
    RAISE NOTICE 'isolation: check_program_isolation() is silent';
END $$;


-- ===========================================================================
-- Housekeeping: ticket 07's two standing obligations
-- ===========================================================================

-- Every trigger this migration created must fire under
-- `session_replication_role = replica` as well (check B01).
DO $$
DECLARE r record;
BEGIN
    FOR r IN SELECT c.relname AS tbl, t.tgname
               FROM pg_trigger t
               JOIN pg_class c ON c.oid = t.tgrelid
              WHERE NOT t.tgisinternal
                AND c.relnamespace = 'public'::regnamespace
                AND t.tgenabled <> 'A'
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ALWAYS TRIGGER %I', r.tbl, r.tgname);
    END LOOP;
END $$;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO rk2_runtime;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO rk2_runtime;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO rk2_runtime;
