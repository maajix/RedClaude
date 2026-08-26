-- ---------------------------------------------------------------------------
-- 20261114T000000Z__a_target_that_did_not_answer_is_still_not_a_refusal.sql
--
-- The rows arm (i) named again, and the writer that kept making them.
--
-- What was measured. Database `rk2here`, 2026-08-25, an eight-hour hunt over
-- 108 concrete hosts. The hunt stopped at lap 14 and again at lap 04 of the
-- next sitting, both times on the standing gate `rk run` verifies before it
-- writes anything:
--
--     1 of 78 check(s) failed; nothing was written
--     standing:receipt_integrity | 1 problem(s): (denied_without_a_refusal,TR25,1)
--
-- TR25 and TR26 were the same request, `GET https://spot.account.here.com/`.
-- The host resolves to two addresses and answers on neither. Both runs carry
-- `decision = 'allow'` and Receipts reading `blocked / target unreachable`,
-- and both closed `denied`.
--
-- 20260812T000000Z corrected the rows that existed and installed arm (i). It
-- did not reach the writer. `execution._exchange` read the newest Receipt and
-- closed the Tool run `denied` for any decision that was not `allowed`, so
-- every unreachable host produced a fresh row for arm (i) to name, and one
-- dead host in a hundred stopped the campaign until somebody corrected it by
-- hand. That is fixed in `execution._exchange`, which now reads every Receipt
-- under the run and closes `error` where nothing refused it -- the same word
-- 20260812T000000Z chose. This file is for the rows written in between.
--
-- Bookkeeping and not evidence, exactly as before: `receipts` are insert-only
-- and nothing here touches them. The Receipt is what the corrected value is
-- read *from*, and `tool_runs.status` is the runtime's own note about how a
-- run it opened ended. The predicate is arm (i)'s, so a row this statement
-- changes is exactly a row the check would otherwise name.
--
-- `set_actor` because `tool_runs` emits on UPDATE, and a settled event with no
-- actor behind it is the failure ticket 13 refuses.
-- ---------------------------------------------------------------------------

SELECT set_actor('runtime', 'target-fault outcome correction');

UPDATE tool_runs t
   SET status = 'error'
 WHERE t.status = 'denied'
   AND t.decision = 'allow'
   AND EXISTS (SELECT 1 FROM receipts r
                WHERE r.tool_run_id = t.id
                  AND r.lane IN ('agent', 'replay')
                  AND r.decision = 'blocked'
                  AND r.reason IN ('target unresolved', 'target unreachable'))
   AND NOT EXISTS (SELECT 1 FROM receipts r
                    WHERE r.tool_run_id = t.id
                      AND r.lane IN ('agent', 'replay')
                      AND r.decision = 'blocked'
                      AND r.reason NOT IN ('target unresolved', 'target unreachable'));


-- The same guard 20260812T000000Z left behind: this migration is only correct
-- if it leaves nothing for arm (i) to find. Arm (i) carries no time bound of
-- its own, so the default second argument reaches the whole record.
DO $$
DECLARE n integer; d text;
BEGIN
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_receipt_integrity(NULL)
     WHERE problem = 'denied_without_a_refusal';
    IF n > 0 THEN
        RAISE EXCEPTION 'a target fault is still filed as a refusal (%): %', n, d;
    END IF;
END $$;
