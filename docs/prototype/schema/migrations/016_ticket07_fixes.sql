-- ---------------------------------------------------------------------------
-- 016_ticket07_fixes.sql   (ticket 07, reopened by ticket 32)
--
-- Closes the three divergences ticket 32 charged to ticket 07, the one it
-- charged to ticket 08 that is really ticket 07's function, and one divergence
-- ticket 32 did not find because it used the mechanism as a probe tool rather
-- than asking whether it was a hole.
--
--   D1  `reject_mutation()` still exists and ticket 08's migration attaches it,
--       so a program that ever suppressed a hypothesis cannot be purged. The
--       function is ticket 07's; it stops existing here.
--   D2  `reject_mutation_unless_purging()` exempts DELETE only, so any
--       `ON DELETE SET NULL` into an immutable table is fatal even under the
--       purge flag. Not fixed by widening the exemption -- fixed by deleting
--       every `SET NULL` and every non-purge `CASCADE`, so no cascade action
--       into an immutable table exists to fire.
--   D3  `events.task_id ON DELETE CASCADE` destroys unrelated history. Same
--       fix. `task_id` is correlation -- "written during this task" -- which is
--       the only definition a trigger can implement; ticket 32 read it as
--       "about this task" and called the stamping a defect. It is not.
--   D5  `check_event_log_integrity()` is green through a lost mutation and
--       green through a row created and deleted while the emitter was off.
--       Check (a) reads `pg_trigger` existence and ignores `tgenabled`.
--   N1  (new) `SET session_replication_role = 'replica'` skips all 38 user
--       triggers at once -- emission, immutability, ticket 06's re-resolved
--       causal `status` guard, and label assignment -- plus every foreign key.
--       CHECK constraints are the only thing that survives.
--
-- The unit of deletion was settled by ticket 06's re-resolution: one whole
-- program, or one artifact blob. The blob unit is a `purged_at` write, not a
-- row delete. So `DELETE FROM programs` is the only row delete the model has,
-- and this migration makes the schema say that instead of leaving it to the
-- order Postgres happens to queue cascade actions in.
-- ---------------------------------------------------------------------------


-- ===========================================================================
-- D1 -- one immutability function, not two
-- ===========================================================================

DROP TRIGGER hypothesis_near_matches_immutable ON hypothesis_near_matches;
CREATE TRIGGER hypothesis_near_matches_immutable
    BEFORE UPDATE OR DELETE ON hypothesis_near_matches
    FOR EACH ROW EXECUTE FUNCTION reject_mutation_unless_purging();

-- The footgun stops existing rather than being documented.
DROP FUNCTION reject_mutation();


-- ===========================================================================
-- D5 -- what the emitter suppresses, recorded
-- ===========================================================================

-- Decision 10 writes no event when every changed column is ignored, which is
-- what keeps `entities.last_seen_at` from burying the log. That leaves a row
-- whose `xmin` advanced with no event to account for it -- indistinguishable,
-- after the fact, from a mutation made with the emitter switched off.
--
-- One row per (program, table, transaction), not per row written: a recon pass
-- that refreshes ten thousand `last_seen_at` values in one transaction writes
-- one row here.
CREATE TABLE suppressed_writes (
    program_id uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    table_name text NOT NULL REFERENCES event_table_config(table_name),
    xact_id    xid8 NOT NULL,
    at         timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (program_id, table_name, xact_id)
);

CREATE TRIGGER suppressed_writes_immutable
    BEFORE UPDATE OR DELETE ON suppressed_writes
    FOR EACH ROW EXECUTE FUNCTION reject_mutation_unless_purging();

CREATE OR REPLACE FUNCTION emit_event() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    cfg      event_table_config%ROWTYPE;
    new_j    jsonb := to_jsonb(NEW);
    old_j    jsonb;
    before_j jsonb := '{}'::jsonb;
    after_j  jsonb := '{}'::jsonb;
    k        text;
    changed  boolean := false;
    v_actor  text;
    v_type   text;
BEGIN
    SELECT * INTO cfg FROM event_table_config WHERE table_name = TG_TABLE_NAME;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'emit_event is attached to % with no event_table_config row',
            TG_TABLE_NAME;
    END IF;

    v_actor := nullif(current_setting('app.actor_kind', true), '');
    IF v_actor IS NULL THEN
        RAISE EXCEPTION
            'app.actor_kind is unset: every write must go through the runtime session helper';
    END IF;

    IF TG_OP = 'INSERT' THEN
        v_type  := cfg.created_type;
        after_j := new_j;
        FOREACH k IN ARRAY cfg.redacted_columns LOOP
            IF after_j ? k THEN
                after_j := jsonb_set(after_j, ARRAY[k], '"[redacted]"'::jsonb);
            END IF;
        END LOOP;
        FOREACH k IN ARRAY cfg.ignored_columns LOOP
            after_j := after_j - k;
        END LOOP;
        changed := true;
    ELSE
        v_type := cfg.updated_type;
        IF v_type IS NULL THEN
            RAISE EXCEPTION '% is declared immutable in event_table_config', TG_TABLE_NAME;
        END IF;
        old_j := to_jsonb(OLD);
        FOR k IN SELECT jsonb_object_keys(new_j) LOOP
            CONTINUE WHEN k = ANY (cfg.ignored_columns);
            CONTINUE WHEN new_j -> k IS NOT DISTINCT FROM old_j -> k;
            changed := true;
            IF k = ANY (cfg.redacted_columns) THEN
                before_j := before_j || jsonb_build_object(k, '[redacted]');
                after_j  := after_j  || jsonb_build_object(k, '[redacted]');
            ELSE
                before_j := before_j || jsonb_build_object(k, old_j -> k);
                after_j  := after_j  || jsonb_build_object(k, new_j -> k);
            END IF;
        END LOOP;
    END IF;

    -- D5: every changed column was ignored. Still nothing anyone asking "why
    -- did it think this" would care about, so still no event -- but the
    -- transaction is now on the record, which is what lets the integrity check
    -- tell a deliberate silence from a disabled trigger.
    IF NOT changed THEN
        INSERT INTO suppressed_writes (program_id, table_name, xact_id)
        VALUES ((new_j ->> 'program_id')::uuid, TG_TABLE_NAME, pg_current_xact_id())
        ON CONFLICT DO NOTHING;
        RETURN NEW;
    END IF;

    INSERT INTO events (
        program_id, type, subject_table, subject_id,
        actor_kind, agent_run_id, task_id, caused_by_event_id, trace_id, payload)
    VALUES (
        (new_j ->> 'program_id')::uuid,
        v_type, TG_TABLE_NAME, (new_j ->> 'id')::uuid,
        v_actor,
        nullif(current_setting('app.agent_run_id',       true), '')::uuid,
        nullif(current_setting('app.task_id',            true), '')::uuid,
        nullif(current_setting('app.caused_by_event_id', true), '')::uuid,
        nullif(current_setting('app.trace_id',           true), ''),
        CASE WHEN TG_OP = 'INSERT'
             THEN jsonb_build_object('after', after_j)
             ELSE jsonb_build_object('before', before_j, 'after', after_j)
        END);

    RETURN NEW;
END $$;


-- ===========================================================================
-- D2, D3 -- the unit of deletion, stated by the schema
-- ===========================================================================

-- Every cascade edge the whole-program purge is allowed to travel, as
-- reviewable rows rather than as forty scattered `ON DELETE` clauses. Anything
-- not listed here is `NO ACTION`, which is what makes `DELETE FROM programs`
-- the only row delete that can succeed.
--
-- `NO ACTION` and not `RESTRICT`: NO ACTION is checked at the end of the
-- statement, by which time the program cascade has already removed the
-- referencing rows, so the purge passes. RESTRICT is checked immediately and
-- would break it. That difference is the whole design.
CREATE TABLE purge_cascade_edges (
    table_name  text NOT NULL,
    column_name text NOT NULL,
    rationale   text NOT NULL,
    PRIMARY KEY (table_name, column_name)
);

-- Every program-scoped table reaches the purge root directly.
INSERT INTO purge_cascade_edges (table_name, column_name, rationale)
SELECT src.relname, 'program_id', 'program-scoped: the purge root'
  FROM pg_constraint con
  JOIN pg_class src ON src.oid = con.conrelid
  JOIN pg_class tgt ON tgt.oid = con.confrelid
 WHERE con.contype = 'f'
   AND tgt.relname = 'programs'
   AND src.relnamespace = 'public'::regnamespace
   AND (SELECT a.attname FROM pg_attribute a
         WHERE a.attrelid = con.conrelid AND a.attnum = con.conkey[1]) = 'program_id';

-- The tables with no `program_id` of their own. Each gets exactly one edge --
-- its owning parent -- because a second cascade path is a second way for a
-- narrow delete to half-succeed.
INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
    -- class-table detail rows hang off their entity
    ('domains',      'entity_id', 'entity detail row'),
    ('hosts',        'entity_id', 'entity detail row'),
    ('services',     'entity_id', 'entity detail row'),
    ('applications', 'entity_id', 'entity detail row'),
    ('endpoints',    'entity_id', 'entity detail row'),
    ('parameters',   'entity_id', 'entity detail row'),
    ('technologies', 'entity_id', 'entity detail row'),
    ('identities',   'entity_id', 'entity detail row'),
    -- edge tables hang off the side that owns the relationship
    ('hypothesis_evidence',        'hypothesis_id', 'evidence edge, hypothesis side'),
    ('hypothesis_retest_triggers', 'hypothesis_id', 'retest edge, hypothesis side'),
    ('hypothesis_embeddings',      'hypothesis_id', 'derived vector'),
    ('observation_embeddings',     'observation_id','derived vector'),
    ('finding_evidence',           'finding_id',    'evidence edge, finding side'),
    ('finding_hypotheses',         'finding_id',    'rollup edge, finding side'),
    ('test_run_receipts',          'test_run_id',   'receipt edge, run side');

-- Rewrite everything else. RESTRICT is left alone: it is strictly stronger
-- than NO ACTION, and ticket 06 chose it deliberately for
-- `findings.validated_by_test_run_id` (D4, asserted by C35).
DO $$
DECLARE r record;
BEGIN
    FOR r IN
        SELECT con.conname, src.relname AS tbl, pg_get_constraintdef(con.oid) AS def
          FROM pg_constraint con
          JOIN pg_class src ON src.oid = con.conrelid
         WHERE con.contype = 'f'
           AND src.relnamespace = 'public'::regnamespace
           AND con.confdeltype IN ('c','n','d')          -- CASCADE / SET NULL / SET DEFAULT
           AND NOT EXISTS (
                 SELECT 1 FROM purge_cascade_edges e
                  WHERE e.table_name  = src.relname
                    AND e.column_name = (SELECT a.attname FROM pg_attribute a
                                          WHERE a.attrelid = con.conrelid
                                            AND a.attnum = con.conkey[1]))
    LOOP
        EXECUTE format('ALTER TABLE %I DROP CONSTRAINT %I', r.tbl, r.conname);
        EXECUTE format('ALTER TABLE %I ADD CONSTRAINT %I %s', r.tbl, r.conname,
                       regexp_replace(r.def,
                           '\s+ON DELETE (CASCADE|SET NULL|SET DEFAULT)', '', 'g'));
        RAISE NOTICE 'purge rule: %.% -> NO ACTION', r.tbl, r.conname;
    END LOOP;
END $$;


-- ===========================================================================
-- D5 -- what the integrity check actually proves
-- ===========================================================================

-- Renamed in intent, not just in comment. This function does NOT prove
-- completeness. It proves four things:
--
--   1. every configured emitter is attached AND enabled ALWAYS      (a)
--   2. every surviving row was created under an event               (b)
--   3. no event points at a row that is gone                        (c)
--   4. every surviving row's most recent write is accounted for,
--      by an event in the same transaction or by a recorded
--      deliberate suppression                                       (d)
--   5. no foreign key outside `purge_cascade_edges` can cascade      (e)
--
-- What it cannot prove, and no query over surviving state can: that a row was
-- never created and deleted inside a window where enforcement was off. There
-- is no surviving state to ask. That case is closed by the privilege split
-- below, not by detection.
CREATE OR REPLACE FUNCTION check_event_log_integrity(p_program uuid DEFAULT NULL)
RETURNS TABLE (problem text, detail text, count bigint)
LANGUAGE plpgsql AS $$
DECLARE c event_table_config%ROWTYPE;
BEGIN
    -- (a) the failure mode that actually happens: a migration adds a table or
    -- rewrites one and its trigger is silently gone -- or still attached and
    -- switched off, which the previous version of this check could not see.
    RETURN QUERY
    SELECT 'emitter_missing', etc.table_name, 1::bigint
      FROM event_table_config etc
     WHERE NOT EXISTS (
           SELECT 1 FROM pg_trigger t
             JOIN pg_class r ON r.oid = t.tgrelid
            WHERE r.relname = etc.table_name
              AND t.tgname  = etc.table_name || '_emit_event'
              AND NOT t.tgisinternal);

    RETURN QUERY
    SELECT 'emitter_not_always_enabled',
           etc.table_name || ' tgenabled=' || t.tgenabled::text, 1::bigint
      FROM event_table_config etc
      JOIN pg_class r ON r.relname = etc.table_name
      JOIN pg_trigger t ON t.tgrelid = r.oid
                       AND t.tgname = etc.table_name || '_emit_event'
                       AND NOT t.tgisinternal
     WHERE t.tgenabled <> 'A';

    FOR c IN SELECT * FROM event_table_config LOOP
        -- (b) a row with no creation event
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

        -- (c) an event pointing at nothing (no FK enforces this, by decision 2)
        RETURN QUERY EXECUTE format($q$
            SELECT 'event_without_row', %L, count(*)::bigint
              FROM events e
             WHERE e.subject_table = %L
               AND (%L::uuid IS NULL OR e.program_id = %L::uuid)
               AND NOT EXISTS (SELECT 1 FROM %I r WHERE r.id = e.subject_id)
            HAVING count(*) > 0 $q$,
            c.table_name, c.table_name, p_program, p_program, c.table_name);

        -- (d) the row's LAST write, not just its first. `xmin` is the
        -- transaction that produced the live tuple; an event or a recorded
        -- suppression from that same transaction must exist. Frozen tuples
        -- report xmin = 2 and are excluded -- VACUUM has destroyed the
        -- evidence, so they degrade to (b) and that is stated rather than
        -- silently passed.
        --
        -- The modulus converts xid8 (64-bit, epoch-carrying) to the 32-bit
        -- space `xmin` reports in, so the comparison survives wraparound.
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

    -- (e) the purge rule itself. A later migration that adds an
    -- `ON DELETE CASCADE` re-opens D2 and D3 silently; this is what notices.
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


-- ===========================================================================
-- N1 -- the enforcement layer survives session_replication_role
-- ===========================================================================

-- Every trigger in this schema enforces something: emission, immutability, the
-- causal `status` guard, transition legality, label assignment. `replica` skips
-- all of them at once, and skips every foreign key with them. ENABLE ALWAYS is
-- what makes a trigger fire in that mode.
--
-- Foreign keys cannot be protected this way -- `ENABLE ALWAYS TRIGGER ALL` is
-- not accepted syntax, and naming the internal RI triggers individually means
-- fifty OID-derived names per table that change on every rebuild. FK
-- enforcement under `replica` is held by privilege alone, below.
CREATE OR REPLACE FUNCTION attach_event_triggers() RETURNS void LANGUAGE plpgsql AS $$
DECLARE c event_table_config%ROWTYPE;
BEGIN
    FOR c IN SELECT * FROM event_table_config LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS %I ON %I',
                       c.table_name || '_emit_event', c.table_name);
        EXECUTE format('CREATE TRIGGER %I AFTER INSERT %s ON %I
                        FOR EACH ROW EXECUTE FUNCTION emit_event()',
                       c.table_name || '_emit_event',
                       CASE WHEN c.updated_type IS NULL THEN '' ELSE 'OR UPDATE' END,
                       c.table_name);
        EXECUTE format('ALTER TABLE %I ENABLE ALWAYS TRIGGER %I',
                       c.table_name, c.table_name || '_emit_event');
    END LOOP;
END $$;

SELECT attach_event_triggers();

-- The rest of them. Runs last so it catches every trigger this migration set
-- has created, including the ones above.
DO $$
DECLARE r record;
BEGIN
    FOR r IN
        SELECT c.relname AS tbl, t.tgname
          FROM pg_trigger t
          JOIN pg_class c ON c.oid = t.tgrelid
         WHERE NOT t.tgisinternal
           AND c.relnamespace = 'public'::regnamespace
           AND t.tgenabled <> 'A'
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ALWAYS TRIGGER %I', r.tbl, r.tgname);
    END LOOP;
END $$;


-- ===========================================================================
-- N1 -- the privilege split
-- ===========================================================================

-- `ALTER TABLE ... DISABLE TRIGGER` needs table ownership;
-- `SET session_replication_role` needs superuser or an explicit
-- `GRANT SET ON PARAMETER`. A runtime role that is neither can do neither,
-- and its ordinary writes still emit.
--
-- This is the prototype form. Ticket 33 owns the real thing, and inherits two
-- obligations with it:
--   - migrations run as the owner, never on the runtime connection;
--   - `pg_restore --disable-triggers` and logical-replication apply now hit
--     ENABLE ALWAYS triggers, so a restore must set `app.actor_kind` or run as
--     a role that is allowed to turn them off.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rk2_runtime') THEN
        CREATE ROLE rk2_runtime NOLOGIN;
    END IF;
END $$;

GRANT USAGE ON SCHEMA public TO rk2_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO rk2_runtime;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO rk2_runtime;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO rk2_runtime;
