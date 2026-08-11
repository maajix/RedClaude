-- Origin: ticket 03, "Run production migrations and the integrity gate".
-- Corrects `check_receipt_integrity` arm (b), last written by
-- `20260811T160000Z__egress_integrity_after_contact.sql`, which fixed arm (a)
-- for the same reason and left its neighbour holding the same mistake.
--
-- The arm asks whether the gate refused a tool call and the network happened
-- anyway. It read `tool_runs.status`, which cannot answer that question, for two
-- independent reasons.
--
-- The first is that `status` is not the gate's verdict. `decision` is -- it is
-- the column arm (e) checks against `risk_classes`, the column
-- `tool_runs_egress_token_ck` requires to be `allow` before a proxy credential
-- may exist at all. `status` is the outcome, and `denied` is what the runtime
-- writes when the *door* refused a request the *gate* allowed. Every limit
-- ticket 13 put at the door produces exactly that pair: a blocked Receipt, and a
-- Tool run closed as denied because a refused request must not close as success.
-- So a Program that enforced its own rate limit failed the standing gate, five
-- times, permanently -- blocked Receipts are insert-only evidence, so nothing
-- could clear it and `rk run` refused to start the Program again.
--
-- The second is that the premise was evaluated against a column that changes
-- after the fact. A Receipt is written while its Tool run is `running`;
-- `resolve_egress_capability` requires that, so no other status can be true at
-- the moment egress is authorized. Whatever `status` says when the gate is run
-- is therefore always a later fact than the egress it was being asked about, and
-- a later fact cannot be a premise about what was authorized earlier.
--
-- Both halves of the corrected predicate are load-bearing. `decision` names what
-- the gate said, including saying nothing: a Receipt carrying egress on a Tool
-- run the gate never ruled on is the same hole as one the gate refused, so null
-- is counted rather than excused. `ts_egress` names what actually left, which is
-- arm (a)'s distinction reused here -- a refusal made before contact is the door
-- working and is counted by reading `receipts`, not by failing a gate.
--
-- What the old arm also detected, and this one does not, is egress recorded
-- against a Tool run that had already closed. That is not lost: the capability
-- does not resolve once the run leaves `running`, arm (h) fails the gate for a
-- token that outlived its Receipt, and arm (a) counts bytes with no Tool run
-- behind them at all.

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
END $$;

COMMENT ON FUNCTION check_receipt_integrity(uuid, interval) IS
  'Receipt-side integrity. Arms (a) and (b) both turn on `ts_egress`: a refusal made before contact is the door working, and only bytes that left can have left without authority. Arm (b) reads the gate''s verdict (`decision`), never the Tool run''s outcome.';
