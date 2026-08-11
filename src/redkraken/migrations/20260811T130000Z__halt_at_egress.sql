-- PH2-11: an operator Halt is re-evaluated at the egress door on every
-- exchange, including a subresource using an already-minted capability.

-- The operator role was deliberately kept off the model-reachable role graph,
-- but that must not make the operator console unusable.  Database CONNECT and
-- schema USAGE reveal no Program data by themselves; table/function grants
-- below remain the enumerated authority surface.
DO $$ BEGIN
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO rk2_human', current_database());
END $$;
GRANT USAGE ON SCHEMA public TO rk2_human;

CREATE TABLE program_halts (
    id          uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id  uuid NOT NULL UNIQUE REFERENCES programs(id) ON DELETE CASCADE,
    status      text NOT NULL CHECK (status IN ('halted', 'cleared')),
    reason      text NOT NULL CHECK (btrim(reason) <> ''),
    revision    bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    actor_kind  text NOT NULL CHECK (actor_kind = 'human'),
    changed_by  text NOT NULL,
    changed_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (program_id, id)
);

INSERT INTO purge_cascade_edges(table_name, column_name, rationale) VALUES
    ('program_halts', 'program_id', 'program-scoped: the purge root');

INSERT INTO event_types(id, family, subject_table, description) VALUES
    ('program.halted', 'row', 'program_halts',
     'an operator halted all target egress for a Program'),
    ('program.halt_changed', 'row', 'program_halts',
     'an operator cleared or reasserted a Program Halt');

INSERT INTO event_table_config(
    table_name, created_type, updated_type, ignored_columns, redacted_columns
) VALUES (
    'program_halts', 'program.halted', 'program.halt_changed', '{}', '{}'
);

CREATE FUNCTION halt_program(p_program uuid, p_reason text)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE h program_halts%ROWTYPE;
BEGIN
    IF NOT human_actor_session() THEN
        RAISE EXCEPTION 'only an operator may Halt a Program' USING ERRCODE = '42501';
    END IF;
    IF p_reason IS NULL OR btrim(p_reason) = '' THEN
        RAISE EXCEPTION 'a Program Halt needs an operator reason' USING ERRCODE = '22023';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM programs WHERE id = p_program AND closed_at IS NULL) THEN
        RAISE EXCEPTION 'no open Program %', p_program USING ERRCODE = '23514';
    END IF;

    PERFORM set_actor('human', session_user);
    INSERT INTO program_halts(program_id, status, reason, actor_kind, changed_by)
    VALUES (p_program, 'halted', p_reason, 'human', session_user)
    ON CONFLICT (program_id) DO UPDATE
       SET status = 'halted', reason = EXCLUDED.reason,
           revision = program_halts.revision + 1,
           actor_kind = 'human', changed_by = session_user, changed_at = now()
     WHERE program_halts.status <> 'halted'
        OR program_halts.reason IS DISTINCT FROM EXCLUDED.reason
    RETURNING * INTO h;

    IF NOT FOUND THEN
        SELECT * INTO h FROM program_halts WHERE program_id = p_program;
    END IF;
    RETURN jsonb_build_object(
        'program_id', h.program_id,
        'status', h.status,
        'revision', h.revision,
        'changed_at', h.changed_at
    );
END $fn$;

CREATE FUNCTION clear_program_halt(p_program uuid, p_reason text)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE h program_halts%ROWTYPE;
BEGIN
    IF NOT human_actor_session() THEN
        RAISE EXCEPTION 'only an operator may clear a Program Halt' USING ERRCODE = '42501';
    END IF;
    IF p_reason IS NULL OR btrim(p_reason) = '' THEN
        RAISE EXCEPTION 'clearing a Program Halt needs an operator reason'
            USING ERRCODE = '22023';
    END IF;

    PERFORM set_actor('human', session_user);
    UPDATE program_halts
       SET status = 'cleared', reason = p_reason, revision = revision + 1,
           actor_kind = 'human', changed_by = session_user, changed_at = now()
     WHERE program_id = p_program AND status = 'halted'
    RETURNING * INTO h;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Program % has no active Halt', p_program USING ERRCODE = '23514';
    END IF;

    RETURN jsonb_build_object(
        'program_id', h.program_id,
        'status', h.status,
        'revision', h.revision,
        'changed_at', h.changed_at
    );
END $fn$;

REVOKE ALL ON TABLE program_halts FROM PUBLIC;
REVOKE ALL ON FUNCTION halt_program(uuid,text), clear_program_halt(uuid,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION halt_program(uuid,text), clear_program_halt(uuid,text)
    FROM rk2_runtime, rk2_state, rk2_proxy;
GRANT EXECUTE ON FUNCTION halt_program(uuid,text), clear_program_halt(uuid,text)
    TO rk2_human;

CREATE OR REPLACE FUNCTION resolve_egress_capability(p_capability text)
RETURNS TABLE (
    program_id uuid,
    tool_run_id uuid,
    agent_run_id uuid,
    task_id uuid,
    decision text,
    capability_expires_at timestamptz
)
LANGUAGE sql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
    SELECT tr.program_id, tr.id, tr.agent_run_id, tr.task_id, tr.decision,
           tr.egress_token_expires_at
      FROM tool_runs tr
      JOIN programs p
        ON p.id = tr.program_id AND p.closed_at IS NULL
      JOIN agent_runs ar
        ON ar.id = tr.agent_run_id AND ar.program_id = tr.program_id
      LEFT JOIN tasks t
        ON t.id = tr.task_id AND t.program_id = tr.program_id
     WHERE p_capability IS NOT NULL
       AND tr.program_id = rk2_program()
       AND NOT EXISTS (
           SELECT 1 FROM program_halts h
            WHERE h.program_id = tr.program_id AND h.status = 'halted'
       )
       AND tr.egress_token_sha256 = encode(digest(p_capability, 'sha256'), 'hex')
       AND tr.egress_token_expires_at > clock_timestamp()
       AND tr.status = 'running'
       AND tr.decision = 'allow'
       AND ar.finished_at IS NULL
       AND ((tr.task_id IS NULL AND ar.task_id IS NULL)
            OR (tr.task_id IS NOT NULL AND ar.task_id = tr.task_id
                AND t.status IN ('claimed', 'running')
                AND t.lease_expires_at > clock_timestamp()));
$fn$;

CREATE OR REPLACE FUNCTION enforce_allowed_receipt_capability() RETURNS trigger
LANGUAGE plpgsql AS $fn$
BEGIN
    IF NEW.lane = 'agent' AND NEW.decision = 'allowed'
       AND NOT EXISTS (
           SELECT 1
             FROM tool_runs tr
             JOIN programs p
               ON p.id = tr.program_id AND p.closed_at IS NULL
             JOIN agent_runs ar
               ON ar.id = tr.agent_run_id AND ar.program_id = tr.program_id
             LEFT JOIN tasks t
               ON t.id = tr.task_id AND t.program_id = tr.program_id
            WHERE tr.id = NEW.tool_run_id
              AND tr.program_id = NEW.program_id
              AND NOT EXISTS (
                  SELECT 1 FROM program_halts h
                   WHERE h.program_id = tr.program_id AND h.status = 'halted'
              )
              AND tr.status = 'running'
              AND tr.decision = 'allow'
              AND tr.egress_token_sha256 IS NOT NULL
              AND tr.egress_token_expires_at > clock_timestamp()
              AND ar.finished_at IS NULL
              AND ((tr.task_id IS NULL AND ar.task_id IS NULL)
                   OR (tr.task_id IS NOT NULL AND ar.task_id = tr.task_id
                       AND t.status IN ('claimed', 'running')
                       AND t.lease_expires_at > clock_timestamp()))
       ) THEN
        RAISE EXCEPTION 'allowed agent receipt lacks a live authorized capability'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $fn$;

CREATE FUNCTION check_program_halt()
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
    SELECT 'allowed_receipt_during_halt', r.label
      FROM receipts r JOIN program_halts h ON h.program_id = r.program_id
     WHERE h.status = 'halted' AND r.decision = 'allowed' AND r.ts_arrival >= h.changed_at;
$fn$;

REVOKE ALL ON FUNCTION check_program_halt() FROM PUBLIC;
INSERT INTO standing_checks(name, query, owner_ticket, note) VALUES
    ('program_halt', 'SELECT * FROM check_program_halt()', '11',
     'only an operator changes Halt state, and a current Halt admits no later allowed Receipt');

SELECT attach_event_triggers();
SELECT attach_actor_kind_guards();

COMMENT ON TABLE program_halts IS
  'Current durable operator Halt state. Revisions are row events; every egress capability is re-resolved against the current status.';
