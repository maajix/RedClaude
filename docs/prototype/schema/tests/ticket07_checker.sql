-- The check_event_log_integrity() body exactly as ticket 07 shipped it in
-- 013_events.sql, under a second name. It exists so the hole demonstrations in
-- ../prove_holes.sh are a real before/after and not a claim: for each hole this
-- function is asked the same question at the same moment as the ticket-33 one,
-- and the interesting rows are the ones where it says nothing.
--
-- Not a migration. Loaded by the test harness only.
--
-- Deliberately NOT named check_something: check_check_registration() requires
-- every public check_% function to have a standing_checks row, and this one is
-- a museum piece, not a corpus invariant. Loading it under its original name
-- made `migrate.sh verify` exit 1 for the rest of the run -- which is the
-- registry doing its job, and the reason the name is ticket07_ instead.

CREATE OR REPLACE FUNCTION ticket07_event_log_integrity(p_program uuid DEFAULT NULL)
RETURNS TABLE (problem text, detail text, count bigint)
LANGUAGE plpgsql AS $$
DECLARE c event_table_config%ROWTYPE;
BEGIN
    -- (a) "the failure mode that actually happens: a migration adds a table or
    -- rewrites one and its trigger is silently gone"
    RETURN QUERY
    SELECT 'config_row_without_trigger', etc.table_name, 1::bigint
      FROM event_table_config etc
     WHERE NOT EXISTS (
           SELECT 1 FROM pg_trigger t
             JOIN pg_class r ON r.oid = t.tgrelid
            WHERE r.relname = etc.table_name
              AND t.tgname  = etc.table_name || '_emit_event'
              AND NOT t.tgisinternal);

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
    END LOOP;
END $$;
