-- ---------------------------------------------------------------------------
-- 20261122T000000Z__a_capability_that_lapsed_mid_connect_still_names_its_run.sql
--
-- The writer behind `egress_without_tool_run`, and the one row it made.
--
-- What was measured. Database `rk2here`, 2026-08-25. The hunt stopped on the
-- standing gate `rk run` verifies before it writes anything:
--
--     standing:receipt_integrity
--     1 problem(s): (egress_without_tool_run,"stg.spot.account.here.com OPTIONS /",1)
--
-- R453 is `OPTIONS https://stg.spot.account.here.com/`, `blocked / target
-- unreachable`, `scope_class = 'target'`, both pinned addresses on the row,
-- `ts_egress` set, `waited_ms = 30059`, and no Tool run. Its nine siblings to
-- the same host under TR104 all carry the run. TR104 is the only run whose
-- window covers R453's arrival, it closed `error` under `decision = 'allow'`,
-- and it closed at 23:57:07 -- while R453, which left at 23:56:54, was still
-- waiting out its connect timeout. The refusal was written at about 23:57:24.
--
-- So this is a race and not an escape. `write_blocked_receipt` attributed the
-- row by resolving the capability a second time, at write time, and
-- `resolve_egress_capability` answers only for a run that is still `running`
-- with an unexpired token. A host that never answers holds the request for the
-- whole timeout, which is long enough for the run that authorised it to close
-- underneath it, and the refusal that finally lands names nothing. Arm (a)
-- then reads the row as egress with no hook receipt behind it -- the one thing
-- it exists to catch -- and one dead host stops the campaign.
--
-- Recovering the run from the capability afterwards is not available: the
-- runtime clears `egress_token_sha256` when it closes a run, and arm (h)
-- requires exactly that. So the door says which run it authorised the attempt
-- under. It already holds the answer -- `Authorization.tool_run_id`, resolved
-- when the capability was still live -- and `proxy._refuse` now puts it on the
-- Receipt. This is the door describing its own decision, not the caller
-- describing itself: the agent never reaches this field, and the value is used
-- only when the capability no longer resolves, only for a run in this Program,
-- and only for a run this Program allowed. That last condition is what keeps
-- arm (b) honest -- a stated run that was denied could otherwise be given an
-- egress it never had.
--
-- `receipts` are insert-only and the correction below writes `tool_run_id`
-- alone, on the single row arm (a) names, to the run the record already shows
-- it belongs to. `set_actor` because `receipts` emit on write.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION write_blocked_receipt(
    p_program uuid,
    p_receipt jsonb,
    p_capability text DEFAULT NULL
) RETURNS text LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE
    v_receipt receipts%ROWTYPE;
    v_label   text;
    v_tool_run_id uuid;
    v_purpose text;
BEGIN
    IF p_program IS DISTINCT FROM rk2_program()
       OR coalesce(jsonb_typeof(p_receipt), 'null') <> 'object' THEN
        RAISE EXCEPTION 'blocked receipt refused' USING ERRCODE = '23514';
    END IF;
    IF p_capability IS NOT NULL
       AND position(p_capability IN p_receipt::text) > 0 THEN
        RAISE EXCEPTION 'receipt payload contains protected capability'
            USING ERRCODE = '23514';
    END IF;
    IF p_capability IS NOT NULL THEN
        SELECT a.tool_run_id INTO v_tool_run_id
          FROM resolve_egress_capability(p_capability) a;
    END IF;

    v_receipt := jsonb_populate_record(NULL::receipts, p_receipt);

    -- The changed part. Only reached when the capability answered nothing, so a
    -- live capability still settles attribution by itself and nothing the door
    -- states can move a row away from the run that presented it. What is left
    -- is the case above: the run closed while its last request was on the wire.
    -- The three conditions are the whole of the trust in it -- the run must
    -- exist, it must be this Program's, and it must have been allowed.
    IF v_tool_run_id IS NULL AND v_receipt.tool_run_id IS NOT NULL THEN
        SELECT tr.id INTO v_tool_run_id
          FROM tool_runs tr
         WHERE tr.id = v_receipt.tool_run_id
           AND tr.program_id = p_program
           AND tr.decision = 'allow';
    END IF;

    v_receipt.id := uuidv7();
    v_receipt.program_id := p_program;
    v_receipt.label := '';
    v_receipt.tool_run_id := v_tool_run_id;
    -- The caller states a purpose, never a lane: who acted is derived from what
    -- the request was for. A capability is the agent's, so it settles both.
    v_purpose := CASE WHEN p_capability IS NULL
                           AND p_receipt ->> 'purpose' = 'control_plane'
                      THEN 'control_plane' ELSE 'target_traffic' END;
    v_receipt.purpose := v_purpose;
    -- Both Lanes a request may be made in, from 20260815T000000Z.
    v_receipt.lane := CASE WHEN v_purpose = 'control_plane'
                           THEN 'proxy_internal'
                           ELSE rk2_capability_lane(v_tool_run_id) END;
    v_receipt.decision := 'blocked';
    v_receipt.scope_version := CASE WHEN v_purpose = 'control_plane' THEN NULL
        ELSE (SELECT scope_version FROM programs WHERE id=p_program) END;
    v_receipt.scope_class := CASE WHEN v_purpose = 'control_plane'
        THEN 'control_plane' ELSE coalesce(v_receipt.scope_class, 'denied') END;
    v_receipt.ts_arrival := coalesce(v_receipt.ts_arrival, clock_timestamp());
    v_receipt.intercepted := coalesce(v_receipt.intercepted, true);

    -- Which of the things that resolve to no capability this one was. The door
    -- cannot tell -- it holds no read on `program_halts`, deliberately, and the
    -- refusal it caught carries one SQLSTATE and one message for all of them --
    -- so the answer is written here, where the Program is already known and the
    -- Halt is one row away. The control plane is excluded because it presents no
    -- capability: a Halt is not what refused it, whatever it says.
    --
    -- A Halt lands mid-run as readily as between runs, and the replay whose next
    -- request it refuses is owed the same name for it -- also 20260815T000000Z.
    v_receipt.reason := coalesce(v_receipt.reason, 'capability refused');
    IF v_receipt.lane IN ('agent', 'replay')
       AND v_receipt.reason = 'capability refused'
       AND EXISTS (SELECT 1 FROM program_halts h
                    WHERE h.program_id = p_program AND h.status = 'halted') THEN
        v_receipt.reason := 'program halted';
    END IF;

    PERFORM set_actor('runtime');
    INSERT INTO receipts (
        id, program_id, label, tool_run_id, lane, purpose, decision, reason,
        identity_entity_id, method, scheme, host, port, path, query_sha256,
        pinned_ips, status_code, ts_arrival, ts_egress, waited_ms, notes,
        retry_after, scope_version, scope_class, intercepted
    ) VALUES (
        v_receipt.id, v_receipt.program_id, v_receipt.label,
        v_receipt.tool_run_id, v_receipt.lane, v_receipt.purpose,
        v_receipt.decision, v_receipt.reason,
        v_receipt.identity_entity_id, v_receipt.method, v_receipt.scheme,
        v_receipt.host, v_receipt.port, v_receipt.path,
        v_receipt.query_sha256, v_receipt.pinned_ips, v_receipt.status_code,
        v_receipt.ts_arrival, v_receipt.ts_egress, v_receipt.waited_ms,
        v_receipt.notes, v_receipt.retry_after, v_receipt.scope_version,
        v_receipt.scope_class, v_receipt.intercepted
    )
    -- The trigger's word for the row, not the function's. Read back rather than
    -- recomputed: `free_label` may skip a taken name, so the only value certain
    -- to be on the row is the one the insert returns.
    RETURNING label INTO v_label;
    RETURN v_label;
END $fn$;

COMMENT ON FUNCTION write_blocked_receipt(uuid,jsonb,text) IS
  'Writes only blocked receipts, on the Lane of the capability that was '
  'presented or the harness''s own control-plane purpose; authority fields and '
  'the name of a Halt are derived, a capability is used for attribution while '
  'it resolves and the door''s own allowed Tool run once it no longer does, '
  'and the return value is the Receipt label the agent may cite.';


-- The rows the old writer made. The predicate is arm (a)'s own first limb, so
-- a row this touches is exactly a row the check would otherwise name, and the
-- run it is given is the only one whose window covers the attempt, that this
-- Program allowed, and that reached the same host in the same lane.
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


-- The guard every correcting migration here carries: this file is only correct
-- if it leaves nothing for the arm to find. Arm (a) carries no time bound, so
-- the defaults reach the whole record.
DO $$
DECLARE n integer; d text;
BEGIN
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_receipt_integrity(NULL)
     WHERE problem = 'egress_without_tool_run';
    IF n > 0 THEN
        RAISE EXCEPTION 'egress is still filed under no Tool run (%): %', n, d;
    END IF;
END $$;


-- And the arm the fallback could have loosened, checked in the same breath: a
-- run that was not allowed must still hold no egress.
DO $$
DECLARE n integer; d text;
BEGIN
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_receipt_integrity(NULL)
     WHERE problem = 'egress_after_denial';
    IF n > 0 THEN
        RAISE EXCEPTION 'egress is filed under a run that was not allowed (%): %', n, d;
    END IF;
END $$;
