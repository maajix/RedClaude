-- Origin: ticket 11 again, from the other end of the loop the previous
-- migration opened. With `ask` reaching a human, the two verdicts ticket 11
-- produces finally occur on the live rig -- and the standing gate refused both:
--
--     $ rk db verify
--       standing:receipt_integrity: 2 problem(s)
--       decision_disagrees_with_risk_class TR41 approval_required/deny
--       decision_disagrees_with_risk_class TR42 approval_required/allow
--
-- TR41 is the parked run: `park_authorized_tool_run` writes `deny`, because a
-- request that stopped at a question did not go out. TR42 is the same request
-- after a human approved it: rule 5 found the live grant and answered `allow`.
-- Both are ticket 11 working exactly as written, and both are counted as
-- decisions that did not come from the policy table.
--
-- Arm (e) is right to be suspicious and wrong about what it reads. Its subject
-- is a decision with no authority behind it, and it tests that by comparing the
-- Tool run's decision to the risk class's default. For `forbidden`, `autonomous`
-- and `constrained` the default is the whole story. For `approval_required` it
-- is not: the default is the question, and the answer is somewhere else -- in
-- the decision a human gave. So the check has to read that instead, and until
-- now the row did not say which decision it was.
--
-- Which is a gap on its own account. `rule 5` turns an approval into an `allow`
-- for any equivalent request while the grant is live; a Tool run admitted that
-- way carried no reference to the approval that admitted it, and the only way to
-- recover it was to recompute the equivalence key -- against today's scope
-- version, which is deliberately not the one the approval was given under. "Who
-- authorised this request" was not answerable from the record.
--
-- `tool_runs.pending_decision_id` is where that belongs and it is already there:
-- ticket 13 added it, parking writes the question it opened into it, and its
-- foreign key is program-scoped. A grant writes the answer it relied on into the
-- same column, which reads the same way in both directions -- the human decision
-- this Tool run is bound to -- and lets arm (e) test the exemption against a
-- named row rather than against a computation.


-- ===========================================================================
-- The approval is recorded where the run can be read from
-- ===========================================================================
-- Verbatim from `0038_receipt_capabilities.sql`, plus the one column. The
-- approval label comes from `gate_tool_call`, which returns it as `approval` and
-- has always done so; nothing here re-decides anything. `coalesce` rather than a
-- plain assignment because this column is also parking's, and an authorisation
-- that names no approval must not erase one that is already recorded.
--
-- SECURITY DEFINER and `search_path` are restated because `CREATE OR REPLACE`
-- resets what it is not told; the grants and the owner survive it.

CREATE OR REPLACE FUNCTION authorize_tool_run(p_tool_run_id uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE
    v_run        tool_runs%ROWTYPE;
    v_gate       jsonb;
    v_capability text;
    v_expires_at timestamptz;
    v_approval   uuid;
BEGIN
    SELECT tr.* INTO v_run
      FROM tool_runs tr
      JOIN agent_runs ar
        ON ar.id = tr.agent_run_id AND ar.program_id = tr.program_id
      LEFT JOIN tasks t
        ON t.id = tr.task_id AND t.program_id = tr.program_id
     WHERE tr.id = p_tool_run_id
       AND tr.program_id = rk2_program()
       AND tr.status = 'running'
       AND ar.finished_at IS NULL
       AND ((tr.task_id IS NULL AND ar.task_id IS NULL)
            OR (tr.task_id IS NOT NULL AND ar.task_id = tr.task_id
                AND t.status IN ('claimed', 'running')
                AND t.lease_expires_at > clock_timestamp()))
     FOR UPDATE OF tr;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'tool run is not active in the current program'
            USING ERRCODE = '23514';
    END IF;

    v_gate := gate_tool_call(p_tool_run_id);
    IF v_gate ->> 'decision' IS NULL
       OR v_gate ->> 'decision' NOT IN ('allow', 'deny', 'ask') THEN
        RAISE EXCEPTION 'tool gate returned no valid decision'
            USING ERRCODE = '23514';
    END IF;

    IF v_gate ->> 'decision' = 'allow' THEN
        v_capability := encode(gen_random_bytes(32), 'hex');
        v_expires_at := clock_timestamp() + interval '5 minutes';
    END IF;

    SELECT d.id INTO v_approval
      FROM pending_decisions d
     WHERE d.program_id = v_run.program_id
       AND d.label = v_gate ->> 'approval';

    PERFORM set_actor('runtime');
    UPDATE tool_runs
       SET risk_class = v_gate ->> 'risk_class',
           decision = v_gate ->> 'decision',
           decision_reason = coalesce(v_gate ->> 'rule', 'gate'),
           pending_decision_id = coalesce(v_approval, pending_decision_id),
           egress_token_sha256 = CASE WHEN v_capability IS NULL THEN NULL
               ELSE encode(digest(v_capability, 'sha256'), 'hex') END,
           egress_token_expires_at = v_expires_at
     WHERE id = v_run.id;

    RETURN v_gate || jsonb_build_object(
        'capability', v_capability,
        'capability_expires_at', v_expires_at);
END $fn$;

COMMENT ON FUNCTION authorize_tool_run(uuid) IS
  'Evaluates gate_tool_call, stamps its decision -- and the human decision behind it, when a live grant is what admitted the call -- and returns a short-lived plaintext capability only for an active allow. Canonical state stores only SHA-256.';

COMMENT ON COLUMN tool_runs.pending_decision_id IS
  'The human decision this Tool run is bound to: the question it opened when it parked, or the approval whose live grant admitted it. Required for a parked run by tool_runs_parked_ck, and read by check_receipt_integrity arm (e) as the authority for a decision that departs from the risk class default.';


-- ===========================================================================
-- The policy check reads the answer, not only the question
-- ===========================================================================
-- Re-created only for arm (e). Everything else is verbatim from
-- `20260812T010000Z__an_ask_is_a_question_not_a_refusal.sql`.

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

    -- (e) a decision that did not come from the policy table -- and, for the one
    -- class whose policy is to ask, one that did not come from the human either.
    --
    -- `approval_required` resolves to `ask`, and both of ticket 11's outcomes
    -- move off it: parking writes `deny`, because a request that stopped at a
    -- question did not go out, and a live grant writes `allow` under rule 5.
    -- Neither is exempted on the shape of the row alone. Each must name the
    -- decision that authorises it -- the question it opened, or the approval it
    -- was admitted under -- which is the same column read the same way, and is
    -- what makes "who authorised this request" answerable from the row.
    RETURN QUERY
    SELECT 'decision_disagrees_with_risk_class',
           t.label || ' ' || t.tool || ' ' || t.risk_class || '/' || t.decision,
           count(*)::bigint
      FROM tool_runs t JOIN risk_classes rc ON rc.risk_class = t.risk_class
     WHERE t.decision IS DISTINCT FROM rc.decision
       AND (p_program IS NULL OR t.program_id = p_program)
       AND NOT (rc.decision = 'ask' AND t.decision = 'deny' AND t.status = 'parked'
                AND EXISTS (SELECT 1 FROM pending_decisions d
                             WHERE d.id = t.pending_decision_id
                               AND d.tool_run_id = t.id))
       AND NOT (rc.decision = 'ask' AND t.decision = 'allow'
                AND EXISTS (SELECT 1 FROM pending_decisions d
                             WHERE d.id = t.pending_decision_id
                               AND d.status = 'approved'
                               AND d.grant_expires_at IS NOT NULL))
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


-- ===========================================================================
-- The runs a grant already admitted
-- ===========================================================================
-- Recovered rather than recomputed. The equivalence key these were admitted
-- under is the one their scope version produced at the time, and re-deriving it
-- today would answer a different question -- which is the property ticket 26
-- gives the key on purpose. What the record does hold is unambiguous: a Tool run
-- whose class asks a human, allowed anyway, at a moment when exactly this
-- program held an approved grant for this tool. Rule 5 is the only path that
-- produces such a row, and the grant it can have used is the one that was live.
--
-- The latest grant is chosen where several overlap, which is the same row rule 5
-- itself picks (`ORDER BY d.grant_expires_at DESC LIMIT 1`).

SELECT set_actor('runtime', 'approval provenance backfill');

UPDATE tool_runs t
   SET pending_decision_id = (
       SELECT d.id FROM pending_decisions d
        WHERE d.program_id = t.program_id
          AND d.status = 'approved'
          AND d.tool = t.tool
          AND d.grant_expires_at IS NOT NULL
          AND d.answered_at <= t.started_at
          AND d.grant_expires_at > t.started_at
        ORDER BY d.grant_expires_at DESC LIMIT 1)
 WHERE t.decision = 'allow'
   AND t.pending_decision_id IS NULL
   AND EXISTS (SELECT 1 FROM risk_classes rc
                WHERE rc.risk_class = t.risk_class AND rc.decision = 'ask');


DO $$
DECLARE n integer; d text;
BEGIN
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_receipt_integrity(NULL, interval '1 hour')
     WHERE problem = 'decision_disagrees_with_risk_class';
    IF n > 0 THEN
        RAISE EXCEPTION 'a decision still departs from its risk class unexplained (%): %', n, d;
    END IF;
END $$;
