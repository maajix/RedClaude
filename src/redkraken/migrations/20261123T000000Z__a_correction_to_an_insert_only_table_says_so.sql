-- ---------------------------------------------------------------------------
-- 20261123T000000Z__a_correction_to_an_insert_only_table_says_so.sql
--
-- The other half of 20261122T000000Z, which the gate found for us.
--
-- `receipts` is insert-only, and its trigger says so: `receipts_emit_event` is
-- AFTER INSERT. Every other table's trigger also fires on UPDATE, and when a
-- write changes nothing anyone would ask about it registers a
-- `suppressed_writes` row instead of an event -- which is what lets
-- `check_event_log_integrity` arm (d) tell a deliberate silence from a
-- disabled trigger.
--
-- 20261122T000000Z corrected one column on one Receipt. The trigger did not
-- fire, nothing registered the transaction, and the next gate said so:
--
--     standing:event_log_integrity
--     1 problem(s): (row_last_write_unaccounted,receipts,1)
--
-- Which is the check working. The write was deliberate and is described in
-- that file; what was missing is the row that says a person meant it. It is
-- written here rather than by relaxing the arm, because an unaccounted write to
-- `receipts` is exactly the shape this harness must never learn to ignore.
--
-- The predicate is arm (d)'s own, narrowed to `blocked` -- the only Receipts
-- 20261122T000000Z could have touched. `xact_id` is reconstructed in the
-- current epoch, because arm (d) compares the low 32 bits and `xmin` is all
-- the row keeps.
--
-- Anyone writing a future correction to an insert-only table owes the same
-- registration in the same transaction as the write.
-- ---------------------------------------------------------------------------

INSERT INTO suppressed_writes (program_id, table_name, xact_id)
SELECT DISTINCT r.program_id, 'receipts',
       (pg_current_xact_id()::text::numeric
        - (pg_current_xact_id()::text::numeric % 4294967296)
        + r.xmin::text::numeric)::text::xid8
  FROM receipts r
 WHERE r.decision = 'blocked'
   AND r.xmin::text::bigint <> 2
   AND NOT EXISTS (
         SELECT 1 FROM events e
          WHERE e.subject_table = 'receipts' AND e.subject_id = r.id
            AND ((e.xact_id::text::numeric % 4294967296)::bigint
                     = r.xmin::text::bigint
              OR e.xmin::text::bigint = r.xmin::text::bigint))
   AND NOT EXISTS (
         SELECT 1 FROM suppressed_writes s
          WHERE s.table_name = 'receipts'
            AND s.program_id = r.program_id
            AND (s.xact_id::text::numeric % 4294967296)::bigint
                = r.xmin::text::bigint)
ON CONFLICT DO NOTHING;


-- The guard: nothing is left for arm (d) to name, on any table. Written wide
-- on purpose -- if this file registered a `receipts` transaction and some other
-- table is unaccounted for its own reason, that is not something to discover
-- on the next lap.
DO $$
DECLARE n integer; d text;
BEGIN
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_event_log_integrity(NULL)
     WHERE problem = 'row_last_write_unaccounted';
    IF n > 0 THEN
        RAISE EXCEPTION 'a last write is still unaccounted (%): %', n, d;
    END IF;
END $$;
