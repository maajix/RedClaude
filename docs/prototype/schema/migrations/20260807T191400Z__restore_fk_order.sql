-- ===========================================================================
-- 33: the purge's firing order survives a restore
--
-- Ticket 35's check (d) asserts that when a parent row is deleted, the
-- ON DELETE CASCADE key that removes the child fires BEFORE the NO ACTION key
-- that would find the child still there. Postgres fires AFTER-row triggers in
-- alphabetical order of trigger name, and an RI trigger's name embeds its
-- constraint OID, so the order is a side effect of the order the keys were
-- created in.
--
-- MEASURED, and the reason this file exists: a full `pg_restore` into a freshly
-- provisioned database recreates every constraint in dump order, which is not
-- creation order, and check (d) then reports 8 pairs on this corpus --
--
--   cascade_fires_after_noaction  applications -> entities:
--       RI_ConstraintTrigger_a_136457 fires before RI_ConstraintTrigger_a_136463
--
-- -- on a database that had been green a minute earlier. The consequence is not
-- cosmetic: in that order a program purge raises a foreign-key violation
-- instead of cascading, so the restored database cannot forget a program. That
-- is a restore turning a working purge into a broken one, silently, and the
-- only reason it is visible at all is that 017 wrote the assertion.
--
-- It cannot be fixed by writing the migrations more carefully, because the
-- author of a migration does not control what pg_restore does years later. So
-- it is repaired instead of asserted: the runner calls enforce_fk_fire_order()
-- in the same finalizer block as attach_event_triggers() and apply_state_rls().
--
-- The repair rebuilds the NO ACTION key, not the CASCADE one, because the name
-- comparison is TEXTUAL: a re-added constraint takes the highest OID in the
-- database, and within one database every OID in this range has the same digit
-- width, so the rebuilt key sorts LAST. Rebuilding the cascade key would move
-- it later too, which is the wrong direction.
-- ===========================================================================

CREATE OR REPLACE FUNCTION fk_fire_order_violations()
RETURNS TABLE (child text, parent text, last_cascade text, first_noaction text)
LANGUAGE sql STABLE AS $$
    SELECT x.child, x.parent, x.last_cascade, x.first_noaction
      FROM (SELECT src.relname::text AS child, tgt.relname::text AS parent,
                   max(tg.tgname::text) FILTER (WHERE con.confdeltype = 'c') AS last_cascade,
                   min(tg.tgname::text) FILTER (WHERE con.confdeltype = 'a') AS first_noaction
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
$$;

COMMENT ON FUNCTION fk_fire_order_violations() IS
    'ticket 35 check (d), as a relation so the repair and the assertion read the '
    'same definition instead of two copies that can drift apart';

CREATE OR REPLACE FUNCTION enforce_fk_fire_order() RETURNS int
LANGUAGE plpgsql AS $$
DECLARE r record; n int := 0; pass int := 0;
BEGIN
    -- Bounded: each pass strictly raises the OID of every offending NO ACTION
    -- key, so one pass is enough in practice (MEASURED: 9 constraints, 1 pass,
    -- on a restore of the full corpus). The bound is here so a schema this
    -- function cannot fix fails the standing check rather than looping.
    LOOP
        pass := pass + 1;
        FOR r IN
            SELECT DISTINCT con.conname::text AS conname, src.relname::text AS child,
                   pg_get_constraintdef(con.oid) AS def
              FROM pg_constraint con
              JOIN pg_class src ON src.oid = con.conrelid
              JOIN pg_class tgt ON tgt.oid = con.confrelid
             WHERE con.contype = 'f' AND con.confdeltype = 'a'
               AND src.relnamespace = 'public'::regnamespace
               AND (src.relname::text, tgt.relname::text) IN
                   (SELECT v.child, v.parent FROM fk_fire_order_violations() v)
        LOOP
            EXECUTE format('ALTER TABLE %I DROP CONSTRAINT %I', r.child, r.conname);
            EXECUTE format('ALTER TABLE %I ADD CONSTRAINT %I %s', r.child, r.conname, r.def);
            n := n + 1;
        END LOOP;
        EXIT WHEN NOT EXISTS (SELECT 1 FROM fk_fire_order_violations()) OR pass >= 5;
    END LOOP;
    RETURN n;
END $$;

COMMENT ON FUNCTION enforce_fk_fire_order() IS
    'finalizer: rebuilds NO ACTION foreign keys that a restore reordered ahead '
    'of the cascade that has to fire first. Returns the number rebuilt, 0 on a '
    'database that never left the order its migrations created.';

-- The corpus as it stands is already in the right order, so this is a no-op
-- here and the number it returns on a fresh build is 0. It is not a no-op after
-- pg_restore, which is the case it exists for.
SELECT enforce_fk_fire_order();
