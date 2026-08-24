-- Ticket 119, the half that gets built: the binding
--
-- `agent_sessions` has had eleven statements retiring a binding that nothing
-- ever made. Eight `UPDATE agent_sessions SET unbound_at` and three
-- `DELETE FROM agent_sessions` across the corpus, an event registration
-- (`0022:346`, `:368`), a live-binding partial index (`0030`), and no
-- `INSERT INTO agent_sessions` anywhere in `src/`. The supervisor's own prose
-- lists "unbinds its session" among the things a finishing run does, and every
-- one of those statements is a no-op on an empty table.
--
-- This is the missing half. The SDK reports its session identifier in the init
-- `SystemMessage` -- the same dict `_corroborate` already reads `apiKeySource`
-- out of -- and the child, which holds no database connection, sends it back up
-- the supervisor channel it was launched on. This verb is what the supervisor
-- calls with it.
--
-- Named `open_agent_session` and deliberately not `bind_agent_session`: that
-- name is taken in this tree by `state.py`, where it means binding a *Postgres*
-- session to a Program. Two different sessions, and one name for both would be
-- a name that reads wrong wherever it is not being written.
--
-- The hook-side half of 022 -- `tool_runs`'s seven hook-identity columns,
-- `agent_runs.parent_run_id`, a receipt per hook event -- is not built here and
-- is not built by this ticket. It specifies a gate this harness placed
-- in-process instead (`roster.Gate`, decided inside the child without a round
-- trip because it is on the critical path of every tool call), and a receipt
-- opened from a hook would collide with the `tool_runs` row the runtime already
-- opens for the same call. Which of those two rows a served call is supposed to
-- produce is a question 022's prose never answers, and answering it is ticket
-- 120's, not this one's.


-- ===========================================================================
-- 1. One live binding per run
-- ===========================================================================
--
-- Idempotent, because the caller is a supervisor reading a stream: a session
-- that announces itself twice is a startup this runtime already counts and
-- refuses on its own terms, and a second bind of the same identifier must not
-- be the thing that fails the run. The conflict target is 0030's partial index,
-- which is what makes "one live binding" mean live rather than ever.
--
-- The Task comes off the run rather than from the caller. A run knows which
-- Task it is for; a caller that could name a different one could file a
-- binding that attributes this session's tool calls to somebody else's work.
--
-- A finished run is refused. The binding exists so that a tool call can be
-- attributed to a live session, and a run that has already been closed has
-- nothing left to attribute -- so this is a refusal rather than a row, in the
-- same words `claim_task` refuses with.
CREATE FUNCTION open_agent_session(
        p_agent_run uuid,
        p_session_id text,
        p_sdk_agent_id text DEFAULT '',
        p_sdk_agent_type text DEFAULT NULL) RETURNS uuid
LANGUAGE plpgsql AS $fn$
DECLARE
    p       uuid := rk2_program_required();
    v_agent text := coalesce(p_sdk_agent_id, '');
    v_id    uuid;
BEGIN
    IF coalesce(p_session_id, '') = '' THEN
        RAISE EXCEPTION 'an agent session binding needs the session identifier the SDK reported'
            USING ERRCODE = 'check_violation';
    END IF;

    PERFORM set_actor('runtime', 'the SDK named the session this run is speaking on');

    INSERT INTO agent_sessions (program_id, session_id, sdk_agent_id,
                                sdk_agent_type, agent_run_id, task_id)
    SELECT p, p_session_id, v_agent, p_sdk_agent_type, r.id, r.task_id
      FROM agent_runs r
     WHERE r.id = p_agent_run AND r.program_id = p AND r.finished_at IS NULL
    ON CONFLICT (program_id, session_id, sdk_agent_id) WHERE unbound_at IS NULL
    DO NOTHING
    RETURNING id INTO v_id;

    IF v_id IS NOT NULL THEN
        RETURN v_id;
    END IF;

    -- Nothing was written, and the two reasons are different facts. An existing
    -- live binding is this call having already been made; no binding at all is
    -- a run that is not live, which is the only other way the INSERT selects no
    -- row.
    SELECT s.id INTO v_id FROM agent_sessions s
     WHERE s.program_id = p AND s.session_id = p_session_id
       AND s.sdk_agent_id = v_agent AND s.unbound_at IS NULL;
    IF v_id IS NOT NULL THEN
        RETURN v_id;
    END IF;

    RAISE EXCEPTION 'agent run % is not a live run of this Program to bind a session to',
        p_agent_run USING ERRCODE = 'check_violation';
END $fn$;

COMMENT ON FUNCTION open_agent_session(uuid, text, text, text) IS
    'Ticket 119: binds the SDK session identifier a child reported at init to '
    'the Agent run the supervisor launched it as. The write half of a '
    'lifecycle whose unbind half has shipped since 0022 -- eleven statements '
    'retire a binding, and until this verb nothing made one. Idempotent on the '
    'live binding, because a supervisor reading a stream may report the same '
    'session twice; refused for a run that has already finished, because a '
    'binding exists to attribute a live session''s calls.';

REVOKE ALL ON FUNCTION open_agent_session(uuid, text, text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION open_agent_session(uuid, text, text, text) TO rk2_runtime;

INSERT INTO runtime_verb_surface (verb, added_by, note) VALUES
    ('open_agent_session(uuid, text, text, text)', '119',
     'what the supervisor calls when a child reports its SDK session id at init; the first and only writer of agent_sessions');


-- ===========================================================================
-- 2. What would have to be true
-- ===========================================================================

DO $$
DECLARE n integer;
BEGIN
    -- The conflict target this file names has to be the index 0030 wrote, or
    -- the idempotence above is a syntax error waiting for the second call.
    SELECT count(*) INTO n FROM pg_indexes
     WHERE schemaname = 'public' AND indexname = 'agent_sessions_live_binding_idx';
    IF n <> 1 THEN
        RAISE EXCEPTION '119 has no live-binding index to make the bind idempotent on';
    END IF;

    -- And the event registration, because a row written outside the log is the
    -- thing 0022's own prose says this table exists to prevent.
    SELECT count(*) INTO n FROM event_table_config
     WHERE table_name = 'agent_sessions' AND created_type = 'session.bound';
    IF n <> 1 THEN
        RAISE EXCEPTION '119 would write agent_sessions rows that emit no event';
    END IF;
END $$;
