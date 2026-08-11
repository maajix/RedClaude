-- Origin: ticket 09, "The capability proxy", read against ticket 11's own
-- vocabulary. Issue 11 states it plainly: `target unreachable` is "a socket that
-- failed after the request was authorised, which is the target's state and not
-- the fence's verdict". The Receipt's `reason` column says exactly that. Nothing
-- else did.
--
-- On the live rig, a name in scope that has no address:
--
--     $ rk proxy request https://oob.yekta-it.de/
--       exit 3, X-RedKraken-Decision: capability-refused, HTTP 407
--       violation: invalid_configuration / the proxy refused this request as
--                  capability-refused: target unresolved
--     R30 | blocked | target unresolved | TR36 | denied | allow
--
-- Three statements about one fact, and only the first is true. The row reads
-- `TR36 | denied | allow`: the gate allowed this Tool run and its outcome says
-- the harness denied it. `capability-refused` and a 407 tell the caller to
-- present a capability, which is the one thing that was not missing -- the
-- capability was minted, resolved and spent. And `invalid_configuration` sends
-- an operator to fix a scope file that is correct: `*.yekta-it.de:443` is in
-- scope, and the target simply has no address today.
--
-- The distinction matters beyond tidiness. A harness pointed at a deliberately
-- broken application meets unreachable targets constantly -- a hostname in a
-- certificate that does not resolve, a service that is down, a TLS layer that
-- will not come up -- and every one of those is a finding about the target. Read
-- back as capability refusals they are indistinguishable from the fence doing
-- its job, so the record cannot be mined for them, and an agent told its
-- capability was refused retries with a fresh one forever.
--
-- The proxy now answers `target-unreachable` under a 502, derived in `_refuse`
-- from the reason the Receipt was filed under so the answer and the record
-- cannot drift, and the runtime closes such a Tool run as `error` -- the outcome
-- word for a run that was authorised and did not complete -- under its own
-- `target_unreachable` violation class. This migration is the half that keeps
-- it true: a check that fails the standing gate if the two words disagree
-- again, and the correction of the rows the old writer already mislabelled.


-- ===========================================================================
-- The gate says which one it is
-- ===========================================================================
-- Re-created only for arm (i). Everything above it is verbatim from
-- `20260811T180000Z__egress_after_denial_reads_the_gate.sql`, which last wrote
-- this check -- and wrote it for the neighbouring confusion between the gate's
-- verdict and the run's outcome. This is that same pair read the other way
-- round: there, an outcome was mistaken for a verdict; here, a verdict nobody
-- gave was written as an outcome.

CREATE OR REPLACE FUNCTION check_receipt_integrity(
        p_program uuid DEFAULT NULL,
        p_open_after interval DEFAULT interval '1 hour')
RETURNS TABLE (problem text, detail text, count bigint)
LANGUAGE plpgsql AS $$
BEGIN
    -- (a) egress that happened with no hook receipt behind it, observed from
    -- the side the model cannot forge, plus any receipt naming a tool run that
    -- is not there.
    RETURN QUERY
    SELECT 'egress_without_tool_run',
           r.host || ' ' || coalesce(r.method,'?') || ' ' || coalesce(r.path,''),
           count(*)::bigint
      FROM receipts r
     WHERE r.lane = 'agent'
       AND (p_program IS NULL OR r.program_id = p_program)
       AND ((r.tool_run_id IS NULL AND r.ts_egress IS NOT NULL)
            OR (r.tool_run_id IS NOT NULL
                AND NOT EXISTS (SELECT 1 FROM tool_runs t WHERE t.id = r.tool_run_id)))
     GROUP BY 1,2;

    -- (b) the hook said no -- or was never asked -- and the network happened
    -- anyway. The gate's verdict is `decision`; `status` is the outcome, and a
    -- Tool run closed as denied because the door enforced a budget is the door
    -- working.
    RETURN QUERY
    SELECT 'egress_after_denial', t.label, count(*)::bigint
      FROM tool_runs t JOIN receipts r ON r.tool_run_id = t.id AND r.lane = 'agent'
     WHERE t.decision IS DISTINCT FROM 'allow'
       AND r.ts_egress IS NOT NULL
       AND (p_program IS NULL OR t.program_id = p_program)
     GROUP BY 1,2;

    -- (c) opened and never closed. Expected transiently; a standing count means
    -- PostToolUse is not firing, or the sweep is not running.
    RETURN QUERY
    SELECT 'receipt_open_past_deadline', t.label, count(*)::bigint
      FROM tool_runs t
     WHERE t.status = 'running'
       AND t.started_at < now() - p_open_after
       AND (p_program IS NULL OR t.program_id = p_program)
     GROUP BY 1,2;

    -- (d) a tool call attributed to nothing. The runtime carries the
    -- correlation; a receipt without it cannot answer "which task did this".
    RETURN QUERY
    SELECT 'receipt_without_attribution', t.label, count(*)::bigint
      FROM tool_runs t
     WHERE t.transport <> 'runtime'
       AND (t.agent_run_id IS NULL OR t.task_id IS NULL)
       AND (p_program IS NULL OR t.program_id = p_program)
     GROUP BY 1,2;

    -- (e) a decision that did not come from the policy table.
    RETURN QUERY
    SELECT 'decision_disagrees_with_risk_class',
           t.label || ' ' || t.tool || ' ' || t.risk_class || '/' || t.decision,
           count(*)::bigint
      FROM tool_runs t JOIN risk_classes rc ON rc.risk_class = t.risk_class
     WHERE t.decision IS DISTINCT FROM rc.decision
       AND (p_program IS NULL OR t.program_id = p_program)
     GROUP BY 1,2;

    -- (f) a hook failure with no receipt on either side of it. PostToolUse
    -- failing open is tolerable; PreToolUse failing without leaving the attempt
    -- on the record is not.
    RETURN QUERY
    SELECT 'hook_failure_without_receipt',
           e.payload ->> 'hook_event', count(*)::bigint
      FROM events e
     WHERE e.type = 'hook.failed'
       AND (p_program IS NULL OR e.program_id = p_program)
       AND e.payload ->> 'tool_use_id' IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM tool_runs t
                        WHERE t.program_id = e.program_id
                          AND t.tool_use_id = e.payload ->> 'tool_use_id')
     GROUP BY 1,2;

    -- (g) the hook-side detector for the load-bearing claim: a tool that
    -- finished without a PreToolUse receipt behind it. The close path writes
    -- these rather than dropping the call, so the count is the direct measure
    -- of "tool calls that completed without producing a receipt first".
    RETURN QUERY
    SELECT 'completed_without_pretooluse', t.label, count(*)::bigint
      FROM tool_runs t
     WHERE t.decision IS NULL
       AND t.transport <> 'runtime'
       AND t.closed_by IN ('PostToolUse','PostToolUseFailure')
       AND (p_program IS NULL OR t.program_id = p_program)
     GROUP BY 1,2;

    -- (h) a live egress credential on a receipt that is no longer running. The
    -- proxy refuses it (resolve_egress_token requires 'running'), but a token
    -- left behind means the runtime's revoke path did not run.
    RETURN QUERY
    SELECT 'egress_token_outlives_receipt', t.label, count(*)::bigint
      FROM tool_runs t
     WHERE t.egress_token_sha256 IS NOT NULL
       AND t.status <> 'running'
       AND (p_program IS NULL OR t.program_id = p_program)
     GROUP BY 1,2;

    -- (i) a run closed with the word for a refusal when nothing refused it.
    -- `denied` is what the runtime writes when the door turned a request away;
    -- a target that did not answer is the target's state, and this run's own
    -- `decision` column still says the gate allowed it.
    --
    -- Read from the Receipts and not from the status alone, because one run may
    -- make several requests: a run that really was refused, and separately met
    -- an unreachable target, closed as denied for a reason that is on the
    -- record. What this counts is a `denied` with no refusal anywhere under it.
    RETURN QUERY
    SELECT 'denied_without_a_refusal', t.label, count(*)::bigint
      FROM tool_runs t
     WHERE t.status = 'denied'
       AND t.decision = 'allow'
       AND (p_program IS NULL OR t.program_id = p_program)
       AND EXISTS (SELECT 1 FROM receipts r
                    WHERE r.tool_run_id = t.id AND r.lane = 'agent'
                      AND r.decision = 'blocked'
                      AND r.reason IN ('target unresolved','target unreachable'))
       AND NOT EXISTS (SELECT 1 FROM receipts r
                        WHERE r.tool_run_id = t.id AND r.lane = 'agent'
                          AND r.decision = 'blocked'
                          AND r.reason NOT IN ('target unresolved','target unreachable'))
     GROUP BY 1,2;
END $$;

COMMENT ON FUNCTION check_receipt_integrity(uuid, interval) IS
  'Receipt-side integrity. Arms (a) and (b) both turn on `ts_egress`: a refusal made before contact is the door working, and only bytes that left can have left without authority. Arm (b) reads the gate''s verdict (`decision`), never the Tool run''s outcome; arm (i) refuses the reverse, an outcome that claims a verdict nobody gave.';


-- ===========================================================================
-- The runs already closed with the wrong word
-- ===========================================================================
-- Corrected rather than left standing, for the reason arm (i) exists: the rows
-- say a Program's own harness refused requests it in fact authorised, and every
-- later reading of that Program's record -- an operator's, a report's, the
-- standing gate's -- inherits the claim.
--
-- This is a correction of bookkeeping, not of evidence. `receipts` are
-- insert-only and nothing here touches them; the Receipt is what the corrected
-- value is read *from*, and `tool_runs.status` is the runtime's own note about
-- how a run it opened ended. The predicate is arm (i)'s, so a row this
-- statement changes is exactly a row the check would otherwise name.
--
-- `set_actor` because `tool_runs` emits on UPDATE, and a settled event with no
-- actor behind it is the failure ticket 13 refuses.

SELECT set_actor('runtime', 'target-fault outcome correction');

UPDATE tool_runs t
   SET status = 'error'
 WHERE t.status = 'denied'
   AND t.decision = 'allow'
   AND EXISTS (SELECT 1 FROM receipts r
                WHERE r.tool_run_id = t.id AND r.lane = 'agent'
                  AND r.decision = 'blocked'
                  AND r.reason IN ('target unresolved','target unreachable'))
   AND NOT EXISTS (SELECT 1 FROM receipts r
                    WHERE r.tool_run_id = t.id AND r.lane = 'agent'
                      AND r.decision = 'blocked'
                      AND r.reason NOT IN ('target unresolved','target unreachable'));


DO $$
DECLARE n integer; d text;
BEGIN
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_receipt_integrity(NULL, interval '1 hour')
     WHERE problem = 'denied_without_a_refusal';
    IF n > 0 THEN
        RAISE EXCEPTION 'a target fault is still filed as a refusal (%): %', n, d;
    END IF;
END $$;
