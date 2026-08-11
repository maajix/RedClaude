-- Origin: ticket 11, "Human control", read against what the runtime actually
-- does with the third verdict. The gate answers `allow`, `deny` or `ask`, and
-- `ask` is the one decision this harness is not allowed to make alone. Ticket 11
-- gives it a whole apparatus: `park_for_human`, a queue only `rk2_human` can
-- answer, a deadline, a sweep, a grant that lets the approved request through
-- once. On the live rig, none of it ran:
--
--     $ rk proxy request --method POST https://www.yconlab.de/index.php
--       exit 3, violation invalid_configuration
--       "the gate answered ask for TR40: no capability was minted"
--     TR40 | denied | ask | approval_required | mcp__rk2__net_request
--     SELECT count(*) FROM pending_decisions;  ->  0
--
-- Three things are wrong with that row and only the third is cosmetic. The
-- question was never asked -- there is no pending decision, so no human can
-- answer it and no notification went out; the apparatus is inert on the one path
-- that reaches it. The run then closed `denied`, which says this harness refused
-- a request nobody has yet ruled on: `deny` and `ask` are different verdicts and
-- the row's own `decision` column says which one was given. And the violation
-- class sends an operator to fix a configuration file, when the configuration is
-- correct and what is missing is a person.
--
-- The cost is the whole of ticket 11 on the path an operator uses most. A
-- deliberately broken target answers a POST differently than a GET, and a
-- mutation is exactly the call that should reach a human rather than be silently
-- dropped by the caller that raised it.
--
-- The runtime now calls `park_for_human` when the gate answers `ask`, which
-- files the question, ends the Agent run and leaves the Tool run `parked`
-- naming the decision it opened. This migration is what that path needs:
-- somewhere to file a question that belongs to no task, and a check that fails
-- the standing gate if an `ask` is ever closed as a verdict again.


-- ===========================================================================
-- A question that belongs to no task
-- ===========================================================================
-- `pending_decisions.task_id` has been NOT NULL since ticket 12's stub, and for
-- an agent-driven call it is right: the call came from a task, the task parks
-- with it, and answering resumes that task. An operator-initiated call has no
-- task at all -- `rk proxy request` opens an Agent run in the `operator` role
-- and a Tool run under it, and `authorize_tool_run` explicitly admits that shape
-- (`tr.task_id IS NULL AND ar.task_id IS NULL`). Under the old column the only
-- way to ask about such a call was to invent a task to hang it on, which would
-- put a row on the work list that no agent should ever claim.
--
-- Nothing downstream needs it. `answer_decision` and `expire_due_decisions`
-- resume or retire `WHERE id = d.task_id`, which is a no-op for NULL; the queue
-- view selects from `pending_decisions` alone; and the resumption of an operator
-- call is the operator running the command again, which rule 5 turns into an
-- `allow` while the grant is live.

ALTER TABLE pending_decisions ALTER COLUMN task_id DROP NOT NULL;

COMMENT ON COLUMN pending_decisions.task_id IS
  'The task that parks with this question, when there is one. NULL for an operator-initiated call: its Agent run has no task, so there is nothing to resume -- the operator repeats the command and rule 5 admits it under the grant.';


-- ===========================================================================
-- An ask that closed as a verdict
-- ===========================================================================
-- Re-created only for arm (j). Everything above it is verbatim from
-- `20260812T000000Z__a_target_that_did_not_answer_is_not_a_refusal.sql`, which
-- last wrote this check. Arm (j) is the third reading of the same pair of
-- columns: (b) refuses an outcome mistaken for a verdict, (i) refuses a verdict
-- nobody gave written as an outcome, and this one refuses a verdict that
-- contradicts the one the gate actually gave.

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

    -- (j) the gate asked for a human and the run closed with a verdict anyway.
    -- `ask` is not a refusal and not a permission; it is the request this
    -- harness may not settle by itself. A `denied` under it claims a refusal
    -- nobody made, and a `success` under it says the request went out while the
    -- question was still open -- the graver of the two, and left standing here
    -- rather than corrected below, because only a human can say what should
    -- happen to a call that was made without them.
    --
    -- The parking path closes such a run as `parked`, which the table already
    -- requires to name the decision it opened, so it can never be a question
    -- nobody was asked.
    RETURN QUERY
    SELECT 'ask_closed_as_a_verdict', t.label || ' ' || t.status, count(*)::bigint
      FROM tool_runs t
     WHERE t.decision = 'ask'
       AND t.status IN ('denied','success')
       AND (p_program IS NULL OR t.program_id = p_program)
     GROUP BY 1,2;
END $$;

COMMENT ON FUNCTION check_receipt_integrity(uuid, interval) IS
  'Receipt-side integrity. Arms (a) and (b) both turn on `ts_egress`: a refusal made before contact is the door working, and only bytes that left can have left without authority. Arm (b) reads the gate''s verdict (`decision`), never the Tool run''s outcome; arm (i) refuses the reverse, an outcome that claims a verdict nobody gave; arm (j) refuses an outcome that contradicts the verdict the gate did give.';


-- ===========================================================================
-- The questions that were dropped instead of asked
-- ===========================================================================
-- `abandoned` and not `parked`: parking is opening a question, and these
-- questions cannot be opened now. The digest they would have been asked under is
-- the request's, the deadline would start today rather than when the call was
-- made, and the Agent runs behind them are long closed. What is true of these
-- rows is that they ended without completing and without anything ruling on
-- them, which is the word `abandoned` means.
--
-- Only the `denied` half is corrected, for the reason arm (j) states: a
-- `success` under an `ask` is a request that went out unruled, and rewriting its
-- status would be this harness settling exactly the question it is not allowed
-- to settle. Arm (b) already counts that case from the Receipt side.

SELECT set_actor('runtime', 'ask closed as a verdict');

UPDATE tool_runs SET status = 'abandoned'
 WHERE decision = 'ask' AND status = 'denied';


DO $$
DECLARE n integer; d text;
BEGIN
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_receipt_integrity(NULL, interval '1 hour')
     WHERE problem = 'ask_closed_as_a_verdict' AND detail LIKE '% denied';
    IF n > 0 THEN
        RAISE EXCEPTION 'a human decision is still filed as a refusal (%): %', n, d;
    END IF;
END $$;
