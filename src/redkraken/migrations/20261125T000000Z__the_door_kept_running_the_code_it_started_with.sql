-- ---------------------------------------------------------------------------
-- 20261125T000000Z__the_door_kept_running_the_code_it_started_with.sql
--
-- The last rows the old door wrote, and why there were more of them.
--
-- 20261122T000000Z corrected R453 and changed `proxy._refuse` so that a
-- refusal-after-contact names the Tool run it was authorised under even when
-- the capability has stopped resolving. The database half took effect at once.
-- The Python half did not: `rk2here-door` is a long-lived container that had
-- been running since 18:19, and although it bind-mounts `src` read-only, the
-- module it is running is the one it imported at start. Two more rows were
-- written by the old code before anyone noticed --
--
--     standing:receipt_integrity
--     1 problem(s): (egress_without_tool_run,"care.account.here.com GET /",1)
--
-- -- and the hunt stopped on the third non-zero lap in a row, which is the
-- loop working. R711 and R722 are the same shape as R453 in every field that
-- matters: `blocked / target unreachable`, `scope_class = 'target'`,
-- `ts_egress` set, `waited_ms` just over 30000, and a Tool run that closed
-- while the connect was still waiting out its timeout.
--
-- The door has been taken away and started again, so the code that writes the
-- attribution is now the code that is running. This file is for the rows in
-- between, and it carries its own `suppressed_writes` registration rather than
-- leaving it to a follow-up, which is what 20261123T000000Z had to be.
--
-- The predicate is 20261122T000000Z's, unchanged: arm (a)'s own first limb,
-- and a run that is this Program's, that it allowed, whose window covers the
-- arrival, and that reached the same host in the same Lane.
-- ---------------------------------------------------------------------------

SELECT set_actor('runtime', 'lapsed-capability attribution correction');

UPDATE receipts r
   SET tool_run_id = (
       SELECT t.id FROM tool_runs t
        WHERE t.program_id = r.program_id
          AND t.decision = 'allow'
          AND t.started_at <= r.ts_arrival
          AND coalesce(t.finished_at, now()) >= r.ts_arrival
          AND EXISTS (SELECT 1 FROM receipts s
                       WHERE s.tool_run_id = t.id
                         AND s.lane = r.lane
                         AND s.host = r.host)
        ORDER BY t.started_at DESC
        LIMIT 1)
 WHERE r.lane IN ('agent', 'replay')
   AND r.tool_run_id IS NULL
   AND r.ts_egress IS NOT NULL
   AND EXISTS (
       SELECT 1 FROM tool_runs t
        WHERE t.program_id = r.program_id
          AND t.decision = 'allow'
          AND t.started_at <= r.ts_arrival
          AND coalesce(t.finished_at, now()) >= r.ts_arrival
          AND EXISTS (SELECT 1 FROM receipts s
                       WHERE s.tool_run_id = t.id
                         AND s.lane = r.lane
                         AND s.host = r.host));


-- `receipts_emit_event` is AFTER INSERT, because `receipts` are insert-only, so
-- the correction above emits nothing and arm (d) of the event-log check would
-- report the transaction as an unaccounted last write. Registering it here says
-- the silence was deliberate. 20261123T000000Z is where this is explained; it
-- is in the same file as the write this time, which is where it belongs.
INSERT INTO suppressed_writes (program_id, table_name, xact_id)
SELECT DISTINCT r.program_id, 'receipts', pg_current_xact_id()
  FROM receipts r
 WHERE r.decision = 'blocked'
   AND r.xmin::text::bigint = (pg_current_xact_id()::text::numeric
                               % 4294967296)::bigint
ON CONFLICT DO NOTHING;


-- Both guards, over the whole record: nothing left for arm (a) to name, and
-- nothing the correction could have handed an egress a denied run never had.
DO $$
DECLARE n integer; d text;
BEGIN
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_receipt_integrity(NULL)
     WHERE problem IN ('egress_without_tool_run', 'egress_after_denial');
    IF n > 0 THEN
        RAISE EXCEPTION 'the Receipt record is still not whole (%): %', n, d;
    END IF;

    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_event_log_integrity(NULL)
     WHERE problem = 'row_last_write_unaccounted';
    IF n > 0 THEN
        RAISE EXCEPTION 'a last write is still unaccounted (%): %', n, d;
    END IF;
END $$;
