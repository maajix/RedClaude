-- ---------------------------------------------------------------------------
-- 20270103T000000Z__a_route_grant_names_the_decision_it_widens.sql
--
-- Ticket 228 wall 2, the defect its own first call found. `20270102T000000Z`
-- gave the gate a second lookup and returned the ROUTE GRANT's label in
-- `approval`. `authorize_tool_run` resolves that label against
-- `pending_decisions` and nothing else (`20260812T020000Z:94-97`), so `RG1`
-- resolved to no row, `pending_decision_id` stayed NULL, and the receipt said
-- a call whose class asks a human was allowed while naming nobody who said so.
--
-- Measured on `rk2here`, 2026-08-30. TR792 is the first and only call RG1 ever
-- admitted, and it is the one row `check_receipt_integrity` arm (e) refuses:
--
--     decision_disagrees_with_risk_class  TR792 mcp__rk2__net_request
--                                         approval_required/allow  1
--
-- Every lap after it exited 9 with `refused` and the supervisor stood down.
-- The seven `approval_required/allow` rows before TR792 all point at a
-- decision; TR792 is the only one that does not, because it is the only one
-- rule 5's route branch admitted.
--
-- WHAT THIS FIXES AND WHAT IT DELIBERATELY DOES NOT TOUCH. The standing check
-- is not touched. Arm (e) is right as written: a call on a class whose policy
-- is to ask, allowed anyway, must name the human decision that authorises it,
-- and that is what the column's own comment says it is for. A route grant is a
-- widening of exactly one approved decision -- `grant_route` refuses to write
-- one from anything else, and `route_grants.granted_from` is the evidence --
-- so the decision the grant widens IS the authority behind every call the
-- grant admits. The gate now says so.
--
-- The other way out was a third exemption in arm (e) for a live route grant.
-- Rejected: `tool_runs` has no `route_grant_id`, so such an exemption would
-- pass rows that name no authority at all, and making it honest costs a new
-- column plus its `runtime_table_surface` registration -- a schema change,
-- bought so that a row could say less than it can say today. A check widened
-- to admit our own defect is the wrong direction whatever it costs.
--
-- WHY `approval` AND NOT A SECOND COLUMN. `approval` has always meant "the
-- human decision this call was admitted under" -- `authorize_tool_run` writes
-- it to `pending_decision_id`, the proxy reports it as `facts["decision"]`
-- (`proxy.py:4150`). A grant label in that key was the mistake. The grant is
-- not lost: it travels beside it as `route_grant` and lands in
-- `decision_reason`, so the row answers both "who authorised this" and "which
-- standing grant admitted it" -- which is the difference between a call the
-- exact lookup answered and one the route lookup did.
-- ---------------------------------------------------------------------------


-- ===========================================================================
-- The gate names the decision, and says which grant reached it
-- ===========================================================================
-- Reproduced whole from `20270102T000000Z`, which is what a `CREATE OR REPLACE`
-- of a plpgsql function is. The narrow lookup, its order, the risk-rule guard
-- and `verdict ->> 'rule'` are all untouched: D-09's dead branch was read off
-- this line and it stays exactly as it was left.

CREATE OR REPLACE FUNCTION gate_tool_call(p_tool_run_id uuid) RETURNS jsonb
LANGUAGE plpgsql STABLE AS $fn$
DECLARE
    tr      tool_runs%ROWTYPE;
    digest  jsonb;
    verdict jsonb;
    grant_l text;
    route_l text;
BEGIN
    SELECT * INTO tr FROM tool_runs WHERE id = p_tool_run_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'no tool_run %', p_tool_run_id; END IF;

    digest  := current_request_digest(p_tool_run_id);
    verdict := assess_call_risk(tr.tool, digest);

    IF (SELECT decision FROM risk_classes
         WHERE risk_class = verdict ->> 'risk_class') <> 'ask' THEN
        RETURN verdict || jsonb_build_object(
            'decision', (SELECT decision FROM risk_classes
                          WHERE risk_class = verdict ->> 'risk_class'),
            'digest', digest, 'approval', NULL, 'route_grant', NULL);
    END IF;

    -- rule 5: a live grant answers the question instead of re-asking it, and
    -- since ticket 228 there are two kinds. The exact one first and unchanged.
    -- The route grant second, and only for the rule it was granted under: a
    -- body-bearing call carries a nonce it did not choose the bytes for, so its
    -- key matches nothing and the narrow lookup can never answer it.
    --
    -- `verdict ->> 'rule'`, because that is what `assess_call_risk` names it
    -- (`0026:310`). `risk_rule` is the COLUMN the rule is stored in once
    -- `park_for_human` has written it down, and reading the verdict under the
    -- column's name is a NULL that quietly refuses every grant this file
    -- writes -- the table would be filled, audited and never read.
    --
    -- A branch and no longer a `coalesce`, because the two lookups now answer
    -- with different things: the narrow one returns the decision itself, the
    -- route one returns a grant that has to be resolved back to the decision it
    -- widens before the receipt can name anybody.
    grant_l := live_grant_for(tr.program_id, equivalence_key(digest));

    IF grant_l IS NULL THEN
        route_l := (SELECT live_route_grant_for(tr.program_id, digest)
                     WHERE verdict ->> 'rule' IS NOT NULL
                       AND EXISTS (SELECT 1 FROM route_grants g
                                    WHERE g.program_id = tr.program_id
                                      AND g.risk_rule = verdict ->> 'rule'
                                      AND g.revoked_at IS NULL
                                      AND g.expires_at > now()));

        -- The decision the grant widens, which is the authority the receipt
        -- will name. Read through `granted_from` rather than recomputed:
        -- `grant_route` writes the label of a decision it has just checked is
        -- approved, and that column exists to be the evidence of it.
        --
        -- The two conditions on the decision are arm (e)'s own, quoted rather
        -- than assumed: an approval with no standing grant on it is not one
        -- the check will accept as an authority, so the gate must not allow a
        -- call it could only record as a violation. Nothing resolves, nothing
        -- is granted, and the call is asked about -- which is what the operator
        -- would have been asked anyway.
        SELECT d.label INTO grant_l
          FROM route_grants g
          JOIN pending_decisions d
            ON d.program_id = g.program_id AND d.label = g.granted_from
         WHERE g.program_id = tr.program_id
           AND g.label = route_l
           AND d.status = 'approved'
           AND d.grant_expires_at IS NOT NULL;

        IF grant_l IS NULL THEN route_l := NULL; END IF;
    END IF;

    RETURN verdict || jsonb_build_object(
        'decision', CASE WHEN grant_l IS NULL THEN 'ask' ELSE 'allow' END,
        'digest', digest, 'approval', grant_l, 'route_grant', route_l);
END $fn$;

COMMENT ON FUNCTION gate_tool_call(uuid) IS
  'Ticket 11 rules 1-5 for one Tool run. `approval` is the human decision that admits the call -- the one whose exact key matched, or the one a route grant widens -- and `route_grant` is the standing grant that reached it, when a route grant is what answered.';


-- ===========================================================================
-- The receipt records both
-- ===========================================================================
-- Verbatim from `20260812T020000Z`, plus the grant on `decision_reason`. The
-- approval lookup is untouched and now finds a row for a route-admitted call
-- for the first time, because the label it is handed is a decision's again.
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
           -- the rule that classified it, and the standing grant that admitted
           -- it under that rule when one did. Concatenated rather than a second
           -- column: the grant is provenance for this one authorisation, and
           -- `pending_decision_id` is already carrying the part a check reads.
           decision_reason = coalesce(v_gate ->> 'rule', 'gate')
                             || coalesce(' via ' || (v_gate ->> 'route_grant'), ''),
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
  'Evaluates gate_tool_call, stamps its decision -- the human decision behind it, and the standing route grant that reached that decision, when a live grant is what admitted the call -- and returns a short-lived plaintext capability only for an active allow. Canonical state stores only SHA-256.';


-- ===========================================================================
-- The runs a route grant already admitted
-- ===========================================================================
-- One row on `rk2here` and the reason the hunt is down; written generally
-- because a label is a per-Program counter and `TR792` names a different row on
-- every other database.
--
-- The population is exact rather than approximate. A Tool run whose class asks
-- a human, allowed anyway, with no decision named, is a row only rule 5's route
-- branch can have produced: the narrow lookup has stamped the decision since
-- `20260812T020000Z`, and no other path writes `allow` onto a class whose
-- policy is to ask. The grant is then matched on what the gate itself matched
-- on -- the Program, the tool and the risk rule, which is the `decision_reason`
-- `authorize_tool_run` wrote -- inside the window the grant was live over the
-- call. The route is not re-derived: `canonical_request` normalises a host, a
-- port and a path template, and re-running it today would answer a question
-- about today's scope version rather than the one the call was admitted under.
-- That is the same recovery `20260812T020000Z` made for the narrow grant, and
-- the same reason.

SELECT set_actor('runtime', 'route grant provenance repair');

WITH admitted AS (
    SELECT t.id AS tool_run_id, w.decision_id, w.label
      FROM tool_runs t
      CROSS JOIN LATERAL (
           SELECT d.id AS decision_id, g.label
             FROM route_grants g
             JOIN pending_decisions d
               ON d.program_id = g.program_id AND d.label = g.granted_from
            WHERE g.program_id = t.program_id
              AND g.tool       = t.tool
              AND g.risk_rule  = t.decision_reason
              AND g.granted_at <= t.started_at
              AND g.expires_at  > t.started_at
              AND (g.revoked_at IS NULL OR g.revoked_at > t.started_at)
              AND d.status = 'approved'
              AND d.grant_expires_at IS NOT NULL
            ORDER BY g.granted_at DESC
            LIMIT 1) w
     WHERE t.decision = 'allow'
       AND t.pending_decision_id IS NULL
       AND EXISTS (SELECT 1 FROM risk_classes rc
                    WHERE rc.risk_class = t.risk_class AND rc.decision = 'ask'))
UPDATE tool_runs t
   SET pending_decision_id = a.decision_id,
       decision_reason = t.decision_reason || ' via ' || a.label
  FROM admitted a
 WHERE a.tool_run_id = t.id;


DO $$
DECLARE n integer; d text;
BEGIN
    -- The table is still read, which is `20270101T000000Z`'s lesson and the
    -- assertion `20270102T000000Z` left behind. Restated because this file
    -- rewrites the one function that reads it.
    IF (SELECT prosrc FROM pg_proc
         WHERE pronamespace = 'public'::regnamespace AND proname = 'gate_tool_call')
       NOT LIKE '%live_route_grant_for%' THEN
        RAISE EXCEPTION 'ticket 228: gate_tool_call does not read a route grant';
    END IF;

    -- And the narrow lookup, untouched, asserted against the text for the same
    -- reason `20270102T000000Z` asserted it: a file that widened it by accident
    -- would look exactly like this one.
    IF (SELECT prosrc FROM pg_proc
         WHERE pronamespace = 'public'::regnamespace AND proname = 'live_grant_for')
       NOT LIKE '%equivalence_key = p_key%' THEN
        RAISE EXCEPTION 'ticket 228: live_grant_for no longer matches on the exact key';
    END IF;

    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_receipt_integrity(NULL, interval '1 hour')
     WHERE problem = 'decision_disagrees_with_risk_class';
    IF n > 0 THEN
        RAISE EXCEPTION 'a decision still departs from its risk class unexplained (%): %', n, d;
    END IF;
END $$;
