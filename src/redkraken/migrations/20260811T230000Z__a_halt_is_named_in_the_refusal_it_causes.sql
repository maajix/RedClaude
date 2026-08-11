-- Origin: ticket 11, "Program Halt", read back through the Receipt it produces.
-- A Halt stops egress by making `resolve_egress_capability` return no row, which
-- is the same thing an expired token, a closed Tool run and a lapsed task lease
-- do. Every one of them reaches the door as `23514: egress capability refused`,
-- and the door files them all under one word:
--
--     $ psql -c "SELECT halt_program(:program, 'F7 validation')"
--     $ rk proxy request https://yekta-it.de/
--       exit 3, receipt R28
--     R28 | blocked | capability refused
--
-- The Program was halted by a human thirty seconds earlier and the record does
-- not say so. That is the one refusal in the set an operator caused deliberately
-- and the one they can lift, and it reads exactly like a lease running out.
-- An agent that reads its own Receipt learns "try again with a fresh
-- capability", which is the one remedy that cannot work: nothing this Program
-- mints will be spent until somebody clears the Halt.
--
-- Named in the writer rather than at each RAISE. Fifteen call sites raise that
-- message and the three the door reaches -- `authorize_identity_egress_request`,
-- `authorize_identity_egress_address`, `reserve_egress_slot` -- would each have
-- to be re-created to carry the distinction, leaving twelve that still say
-- `capability refused` for a Halt. `write_blocked_receipt` is where all of them
-- converge, it already holds the Program, and it already derives the fields a
-- caller must not choose -- the lane, the decision, the scope class. The reason
-- joins them, and does so for the refusal paths this migration has never seen.
--
-- The rewrite is narrow on purpose. Only the exact string `capability refused`
-- is replaced, only on the agent lane, and only while a Halt is active on the
-- Program the row is filed under: a refusal that already named a smaller thing
-- -- an address, a budget, a required header, an Identity -- keeps its own name,
-- because those are true during a Halt as well and are the more specific fact.
--
-- What it means for a capability that was ALSO expired, or fabricated, is
-- `program halted`, and that is the honest answer rather than an approximation:
-- while a Halt stands, no capability of that Program can be spent whatever else
-- is wrong with it, and the remedy for every one of them is the same person.

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

    -- Which of the things that resolve to no capability this one was. The door
    -- cannot tell -- it holds no read on `program_halts`, deliberately, and the
    -- refusal it caught carries one SQLSTATE and one message for all of them --
    -- so the answer is written here, where the Program is already known and the
    -- Halt is one row away. The control plane is excluded because it presents no
    -- capability: a Halt is not what refused it, whatever it says.
    v_receipt.reason := coalesce(v_receipt.reason, 'capability refused');
    IF v_receipt.lane = 'agent' AND v_receipt.reason = 'capability refused'
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
  'Writes only blocked receipts, on the agent lane or the harness''s own control-plane purpose; authority fields and the name of a Halt are derived, a valid capability is used only for agent attribution, and the return value is the Receipt label the agent may cite.';


-- ===========================================================================
-- The gate says which one it is
-- ===========================================================================
-- Re-created only for the last arm. Everything above it is verbatim from
-- `20260811T170000Z__egress_budget_at_the_door.sql`, which last wrote this check.
--
-- The arm is the pair of the one above it. `allowed_receipt_during_halt` says a
-- Halt let nothing through; this says the refusals it caused admit to being its
-- refusals. Bounded the same way -- from `changed_at`, while the status is still
-- `halted` -- so clearing a Halt closes the window rather than leaving every row
-- it ever produced under permanent inspection.

CREATE OR REPLACE FUNCTION check_program_halt()
RETURNS TABLE(problem text, detail text)
LANGUAGE sql STABLE AS $fn$
    SELECT 'human_cannot_connect', 'rk2_human cannot connect to this database'
     WHERE NOT has_database_privilege('rk2_human', current_database(), 'CONNECT')
    UNION ALL
    SELECT 'human_cannot_use_schema', 'rk2_human cannot use the public schema'
     WHERE NOT has_schema_privilege('rk2_human', 'public', 'USAGE')
    UNION ALL
    SELECT 'human_cannot_change_halt', 'rk2_human cannot execute both Halt verbs'
     WHERE NOT has_function_privilege('rk2_human', 'halt_program(uuid,text)', 'EXECUTE')
        OR NOT has_function_privilege(
               'rk2_human', 'clear_program_halt(uuid,text)', 'EXECUTE')
    UNION ALL
    SELECT 'runtime_can_halt', 'rk2_runtime can execute halt_program'
     WHERE has_function_privilege('rk2_runtime', 'halt_program(uuid,text)', 'EXECUTE')
    UNION ALL
    SELECT 'runtime_can_clear_halt', 'rk2_runtime can execute clear_program_halt'
     WHERE has_function_privilege('rk2_runtime', 'clear_program_halt(uuid,text)', 'EXECUTE')
    UNION ALL
    SELECT 'proxy_can_change_halt', 'rk2_proxy can change Program Halt state'
     WHERE has_function_privilege('rk2_proxy', 'halt_program(uuid,text)', 'EXECUTE')
        OR has_function_privilege('rk2_proxy', 'clear_program_halt(uuid,text)', 'EXECUTE')
    UNION ALL
    -- The row itself. DELETE above all: the actor-kind guard is a BEFORE INSERT
    -- OR UPDATE trigger, so it never sees a delete, and a deleted Halt is an
    -- absent Halt -- which is what `resolve_egress_capability` reads.
    --
    -- INSERT is not asked, and is not revoked either: the guard does fire on it,
    -- one Program has one Halt row, and an insert cannot lift a Halt that is
    -- already there.
    SELECT 'halt_row_writable',
           h.grantee || ' holds ' || h.privilege_type || ' on program_halts'
      FROM (
        SELECT g.grantee, v.privilege_type
          FROM (VALUES ('UPDATE'), ('DELETE')) AS v(privilege_type),
               (VALUES ('rk2_runtime'), ('rk2_proxy'), ('rk2_state')) AS g(grantee)
         WHERE has_table_privilege(g.grantee, 'program_halts', v.privilege_type)
      ) h
    UNION ALL
    SELECT 'allowed_receipt_during_halt', r.label
      FROM receipts r JOIN program_halts h ON h.program_id = r.program_id
     WHERE h.status = 'halted' AND r.decision = 'allowed' AND r.ts_arrival >= h.changed_at
    UNION ALL
    SELECT 'halt_refusal_reads_as_a_lapsed_capability', r.label
      FROM receipts r JOIN program_halts h ON h.program_id = r.program_id
     WHERE h.status = 'halted' AND r.decision = 'blocked' AND r.lane = 'agent'
       AND r.ts_arrival >= h.changed_at AND r.reason = 'capability refused';
$fn$;

UPDATE standing_checks
   SET note = 'only an operator changes Halt state, by verb or by row; a current Halt admits no later allowed Receipt, and the refusals it causes say so by name'
 WHERE name = 'program_halt';


DO $$
DECLARE n integer; d text;
BEGIN
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_program_halt();
    IF n > 0 THEN
        RAISE EXCEPTION 'program halt broken (% problems): %', n, d;
    END IF;
END $$;
