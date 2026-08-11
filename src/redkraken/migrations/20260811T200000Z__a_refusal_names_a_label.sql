-- Origin: ticket 09, "Send HTTP through the capability proxy". The door answers
-- every request with the name of the record it wrote, and on a refusal that name
-- was the row's uuid.
--
-- A label is the only identifier an agent is ever given for anything: counted by
-- `next_label` in `0002_programs.sql` and put on the row by the `assign_label`
-- trigger in `0015_epistemic_corrections.sql`. `rk state --label` resolves those
-- and nothing else, so the answer to a refused request named a record the caller
-- it was handed to could not look up:
--
--     X-RedKraken-Receipt: 019ff1b6-965e-7c6a-8ff1-a7876e6603d6
--     $ rk state --label 019ff1b6-965e-7c6a-8ff1-a7876e6603d6
--       record: ... is not a record of this Program
--     receipts: id=019ff1b6-965e-7c6a-8ff1-a7876e6603d6  label=R20  blocked
--
-- The served path already answers with `label`, so the two answers to the same
-- caller disagreed about what an identifier is: an exchange it could cite, and a
-- refusal it could not. That is the wrong way round. A served request has a
-- response to reason about; a refused one has nothing but its record, and an
-- agent that cannot open the record cannot tell "refused and filed" from
-- "refused and lost" -- which is precisely the distinction `_spend` treats as an
-- integrity failure when the name is missing altogether.
--
-- The fix is one word of the writer: the insert returns the label the
-- `assign_label` trigger just put on the row instead of the uuid the function
-- generated. Nothing else about the receipt changes, and the argument types do
-- not change either, so every privilege check that names
-- `write_blocked_receipt(uuid,jsonb,text)` still names this function. The return
-- type does change, which `CREATE OR REPLACE` cannot do, hence the drop and the
-- grant restated after it.
--
-- `v_receipt.label := ''` stays. It is what makes the trigger assign at all, and
-- it is what stops a caller from choosing the name its own refusal is filed
-- under: the label is now the value the proxy reads back and shows to the agent,
-- so a caller that could set it could make two refusals answer with one name.
--
-- The body is otherwise verbatim from
-- `20260811T170000Z__egress_budget_at_the_door.sql`, which last wrote it.

DROP FUNCTION write_blocked_receipt(uuid,jsonb,text);

CREATE FUNCTION write_blocked_receipt(
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
    v_receipt.lane := CASE WHEN v_purpose = 'control_plane'
                           THEN 'proxy_internal' ELSE 'agent' END;
    v_receipt.decision := 'blocked';
    v_receipt.scope_version := CASE WHEN v_purpose = 'control_plane' THEN NULL
        ELSE (SELECT scope_version FROM programs WHERE id=p_program) END;
    v_receipt.scope_class := CASE WHEN v_purpose = 'control_plane'
        THEN 'control_plane' ELSE coalesce(v_receipt.scope_class, 'denied') END;
    v_receipt.ts_arrival := coalesce(v_receipt.ts_arrival, clock_timestamp());
    v_receipt.intercepted := coalesce(v_receipt.intercepted, true);

    PERFORM set_actor('runtime');
    INSERT INTO receipts (
        id, program_id, label, tool_run_id, lane, purpose, decision, reason,
        identity_entity_id, method, scheme, host, port, path, query_sha256,
        pinned_ips, status_code, ts_arrival, ts_egress, waited_ms, notes,
        retry_after, scope_version, scope_class, intercepted
    ) VALUES (
        v_receipt.id, v_receipt.program_id, v_receipt.label,
        v_receipt.tool_run_id, v_receipt.lane, v_receipt.purpose,
        v_receipt.decision,
        coalesce(v_receipt.reason, 'capability refused'),
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

REVOKE ALL ON FUNCTION write_blocked_receipt(uuid,jsonb,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION write_blocked_receipt(uuid,jsonb,text) TO rk2_proxy;

COMMENT ON FUNCTION write_blocked_receipt(uuid,jsonb,text) IS
  'Writes only blocked receipts, on the agent lane or the harness''s own control-plane purpose; authority fields are derived, a valid capability is used only for agent attribution, and the return value is the Receipt label the agent may cite.';


-- ===========================================================================
-- The gate says which one it is
-- ===========================================================================
-- Re-created only for the last arm. Everything above it is verbatim from
-- `20260811T150000Z__encrypted_identity_slots.sql`, which last wrote this check.
--
-- The arm reads the writer's return type rather than a receipt, because there is
-- nothing wrong with any row this ever wrote: the label was always on it. What
-- was wrong was which column the door was handed, and a later migration
-- re-declaring this function is the only way that can come back.

CREATE OR REPLACE FUNCTION check_capability_receipt_fence()
RETURNS TABLE(problem text, detail text) LANGUAGE sql STABLE AS $fn$
    SELECT 'proxy_can_insert_receipts', 'rk2_proxy has direct INSERT'
     WHERE has_table_privilege('rk2_proxy', 'receipts', 'INSERT')
    UNION ALL
    SELECT 'allowed_receipt_trigger_missing', 'trigger absent or not ENABLE ALWAYS'
     WHERE NOT EXISTS (SELECT 1 FROM pg_trigger
                        WHERE tgrelid = 'receipts'::regclass
                          AND tgname = 'receipts_allowed_capability' AND tgenabled = 'A')
    UNION ALL
    SELECT 'proxy_identity_writer_missing', 'rk2_proxy cannot execute the Identity fence'
     WHERE NOT has_function_privilege(
               'rk2_proxy',
               'authorize_identity_egress_request(text,text,text,text,integer,text,text)',
               'EXECUTE')
        OR NOT has_function_privilege(
               'rk2_proxy', 'authorize_identity_egress_address(text,text,text,integer,text)',
               'EXECUTE')
        OR NOT has_function_privilege('rk2_proxy', 'open_identity_slot(text,text)', 'EXECUTE')
        OR NOT has_function_privilege(
               'rk2_proxy', 'confirm_identity_slot_open(text,text,uuid,text)', 'EXECUTE')
        OR NOT has_function_privilege(
               'rk2_proxy',
               'record_identity_proxy_exchange(text,jsonb,jsonb,jsonb,text,bigint,jsonb)',
               'EXECUTE')
        OR NOT has_function_privilege(
               'rk2_proxy', 'ensure_proxy_wire_keying(text,bytea,bytea)', 'EXECUTE')
        OR NOT has_function_privilege(
               'rk2_proxy', 'write_blocked_receipt(uuid,jsonb,text)', 'EXECUTE')
    UNION ALL
    SELECT 'proxy_bypasses_identity_writer', 'rk2_proxy retains an unchecked writer'
     WHERE has_function_privilege('rk2_proxy', 'write_allowed_receipt(text,jsonb)', 'EXECUTE')
        OR has_function_privilege(
               'rk2_proxy', 'record_proxy_exchange(text,jsonb,jsonb)', 'EXECUTE')
        OR has_function_privilege(
               'rk2_proxy', 'record_proxy_exchange(text,jsonb,jsonb,jsonb)', 'EXECUTE')
        OR has_function_privilege(
               'rk2_proxy',
               'authorize_egress_request(text,text,text,text,integer,text,text,text)',
               'EXECUTE')
        OR has_function_privilege(
               'rk2_proxy', 'authorize_egress_address(text,text,text,integer,text)', 'EXECUTE')
        OR has_function_privilege('rk2_proxy', 'provision_identity_slot(uuid,text,bigint,jsonb)',
                                  'EXECUTE')
        OR has_table_privilege('rk2_proxy', 'identity_slots', 'SELECT')
    UNION ALL
    SELECT 'state_can_reach_identity_slots', 'the agent-facing role can reach slot state'
     WHERE has_table_privilege('rk2_state', 'identity_slots', 'SELECT')
        OR has_function_privilege('rk2_state', 'open_identity_slot(text,text)', 'EXECUTE')
        OR has_function_privilege(
               'rk2_state', 'provision_identity_slot(uuid,text,bigint,jsonb)', 'EXECUTE')
    UNION ALL
    SELECT 'unsealed_zero_byte_wire_artifact', a.sha256
      FROM artifacts a
     WHERE a.encrypted AND a.byte_size = 0 AND a.purged_at IS NULL
       AND NOT EXISTS (SELECT 1 FROM artifact_seal s WHERE s.sha256 = a.sha256)
    UNION ALL
    SELECT 'blocked_receipt_answers_with_a_row_id',
           'a refusal would name its record with something no label resolves'
     WHERE pg_get_function_result(
               'write_blocked_receipt(uuid,jsonb,text)'::regprocedure) <> 'text'
$fn$;

UPDATE standing_checks
   SET note = 'the proxy reaches Identity slots and allowed Receipts only through lease-gated writers; hunter reads and provisioning remain separate; every wire transformation is sealed; a refusal names a Receipt the agent can cite'
 WHERE name = 'capability_receipt_fence';


DO $$
DECLARE n integer; d text;
BEGIN
    IF pg_get_function_result(
           'write_blocked_receipt(uuid,jsonb,text)'::regprocedure) <> 'text' THEN
        RAISE EXCEPTION 'the blocked-receipt writer still answers with a row id';
    END IF;
    IF NOT has_function_privilege(
           'rk2_proxy', 'write_blocked_receipt(uuid,jsonb,text)', 'EXECUTE') THEN
        RAISE EXCEPTION 'the door cannot file a refusal any more';
    END IF;
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_capability_receipt_fence();
    IF n > 0 THEN
        RAISE EXCEPTION 'capability receipt fence broken (% problems): %', n, d;
    END IF;
END $$;
