-- Origin: ticket 03, "Run production migrations and the integrity gate".
-- Corrects `check_receipt_integrity` arm (a) from `0022_hooks_and_receipts.sql`.
--
-- The arm read every agent-lane Receipt with no tool run as an integrity
-- failure. A blocked Receipt written by the door when it refuses a capability
-- has exactly that shape and is the door working: the capability resolved to
-- nothing, so there is no tool run to attribute the attempt to, and inventing
-- one would be worse than filing it against nothing. One refused capability
-- therefore failed the standing gate for every Program, permanently, and the
-- only way back was to delete the audit row the refusal existed to leave.
--
-- What the arm is for is narrower than what it measured: bytes that left this
-- machine with no tool call accounting for them. `ts_egress` is what separates
-- the two -- it is set once a socket has been opened to the target and is null
-- on every refusal made before contact. The second half stays unconditional: a
-- Receipt citing a tool run that does not exist is corruption whether or not
-- anything was dialled.
--
-- A refusal before contact is still a fact and still countable; it is counted
-- by reading `receipts`, which is where it is recorded, rather than by failing
-- a gate that then cannot be cleared.

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

    -- (b) the hook said no and the network happened anyway.
    RETURN QUERY
    SELECT 'egress_after_denial', t.label, count(*)::bigint
      FROM tool_runs t JOIN receipts r ON r.tool_run_id = t.id AND r.lane = 'agent'
     WHERE t.status IN ('denied','parked')
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
  'Receipt-side integrity. Arm (a) counts egress that happened with nothing accounting for it: a refusal made before contact has no tool run by construction and is not a failure.';
