-- ---------------------------------------------------------------------------
-- 20260814T010000Z__rotate_the_orchestrator_and_resume.sql          (PH2-28)
--
-- 000000Z opened one orchestrator session per pass and closed it at the end of
-- the same pass. That is a session with nothing to rotate: it never reaches a
-- ceiling, never has to hand anything on, and never has to survive a restart --
-- and it is also not the session ADR 0003 describes, which decides repeatedly
-- inside one long-lived context. 27's own comments say so and name this file.
--
-- What a long-lived session needs is three things the corpus does not have:
--
--   * ceilings that are settings rather than prose. A model told in its prompt
--     to stop after so many decisions is a model that stops when it agrees;
--     a runtime that will not start another turn in a spent session is a bound.
--   * one durable row per campaign, so that "which session is this pass part
--     of" survives the supervisor dying between passes. `rk run` performs one
--     slice attempt per invocation, so every pass is already a restart, and a
--     session held in memory would be a session that lasts exactly as long as
--     the weakest thing in the process.
--   * a close that says what it cost and why it ended, and a successor that
--     points back at it. Rotation without a link is two sessions; rotation with
--     one is a campaign.
--
-- The fourth thing -- the bounded capsule the successor resumes from -- is
-- compiled in Python out of the state this file makes durable, because it is a
-- fitting problem (rows, bytes, tokens, omission markers) and `packet.py`
-- already solves that one. What belongs here is the ceilings the capsule is
-- fitted to, which are settings for the same reason the others are.
--
-- Usage is derived and never counted. Turns are the session's Agent runs,
-- tokens are what those runs recorded, decisions are the `scheduler.chose`
-- Events they wrote. A counter column would be a second copy of all three, and
-- the first thing a standing check would have to assert is that the copy still
-- agrees with the rows it was copied from.
-- ---------------------------------------------------------------------------


-- ---------------------------------------------------------------------------
-- 1. The ceilings, as settings
-- ---------------------------------------------------------------------------
-- On the weights row, with the rest of the numbers the scheduler runs on: a
-- ceiling an operator can change is one row and one `active` flag away, and a
-- session that opened under version 1 keeps version 1's ceilings because it
-- copies them (section 2). Criterion 1 in one sentence -- "hard runtime
-- settings rather than prompt guidance" -- is the copy plus section 5's refusal
-- to start a turn in a session that has reached one.
--
-- Version 1's numbers are deliberately small. A campaign that rotates too often
-- pays for a capsule it did not need; a campaign that rotates too rarely
-- discovers the ceiling was never real. The first is measurable and the second
-- is not, so the defaults err at the first.
ALTER TABLE scheduler_weights
    -- A turn is one orchestrator Agent run: `rk run` invokes a child once per
    -- pass, so the campaign's turn is the pass, and the child's own per-turn
    -- ceiling is `roles.max_turns`, which bounds a different thing inside one
    -- invocation.
    ADD COLUMN session_max_turns     integer NOT NULL DEFAULT 100
        CHECK (session_max_turns > 0),
    -- Five times `cost_reference_tokens`, which is one agent run's envelope.
    -- The session is planning and not work, so what it may spend before it
    -- hands on is a small multiple of what one piece of work may spend.
    ADD COLUMN session_max_tokens    bigint  NOT NULL DEFAULT 1000000
        CHECK (session_max_tokens > 0),
    -- Fewer than the turns, because a turn that recorded no choice still cost
    -- a startup, and a session that spends its turns without deciding anything
    -- should rotate on the turns rather than wait for decisions it is not
    -- making.
    ADD COLUMN session_max_decisions integer NOT NULL DEFAULT 80
        CHECK (session_max_decisions > 0),
    -- Criterion 6's two limits. The numbers are `packet.py`'s own defaults,
    -- because the capsule is fitted by the same fitter the mission packet is
    -- and a second pair of numbers would be a second answer to one question.
    ADD COLUMN capsule_max_bytes     integer NOT NULL DEFAULT 65536
        CHECK (capsule_max_bytes > 0),
    ADD COLUMN capsule_max_tokens    integer NOT NULL DEFAULT 8192
        CHECK (capsule_max_tokens > 0);

COMMENT ON COLUMN scheduler_weights.session_max_turns IS
  'How many orchestrator Agent runs one session may hold before the runtime rotates it. One turn is one pass, because `rk run` starts one child per invocation.';
COMMENT ON COLUMN scheduler_weights.session_max_tokens IS
  'What every run of one orchestrator session may cost together before the runtime rotates it. Compared against what the runs recorded, so the last turn may finish above it -- a ceiling to stop at, not one to stay under.';
COMMENT ON COLUMN scheduler_weights.session_max_decisions IS
  'How many choices one orchestrator session may record before the runtime rotates it. A turn that recorded nothing still spent a turn, which is why this is not the same ceiling as session_max_turns.';
COMMENT ON COLUMN scheduler_weights.capsule_max_bytes IS
  'The serialized ceiling a resume capsule is fitted to. Shares `packet.py`''s default, because the capsule is fitted by the same fitter as the mission packet.';
COMMENT ON COLUMN scheduler_weights.capsule_max_tokens IS
  'The estimated-token ceiling a resume capsule is fitted to, at the same four bytes per token the mission packet estimates with.';


-- ---------------------------------------------------------------------------
-- 2. The campaign as a row
-- ---------------------------------------------------------------------------
-- One open session per Program, many Agent runs inside it, and a chain back
-- through the sessions it replaced. The ceilings are copied and not joined for
-- the reason `budget_reservations.kind` is copied: they are what this session
-- was admitted under, and a weights row an operator edits mid-campaign must not
-- retroactively rotate or un-rotate a session that has already run.
CREATE TABLE orchestrator_sessions (
    id              uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id      uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    label           text NOT NULL,
    -- Which numbers this session copied, so an operator reading a rotation can
    -- see that two sessions of one campaign ran under different settings.
    weights_version integer NOT NULL REFERENCES scheduler_weights(version),
    max_turns       integer NOT NULL CHECK (max_turns > 0),
    max_tokens      bigint  NOT NULL CHECK (max_tokens > 0),
    max_decisions   integer NOT NULL CHECK (max_decisions > 0),
    -- The session this one replaced, and how many replacements deep the
    -- campaign is. Generation is not derivable cheaply from the chain and is
    -- what an operator reads first, so it is a column with a check on it
    -- rather than a recursive walk.
    rotated_from    uuid,
    generation      integer NOT NULL DEFAULT 1 CHECK (generation >= 1),
    opened_at       timestamptz NOT NULL DEFAULT now(),
    closed_at       timestamptz,
    close_reason    text CHECK (close_reason IN ('turns','tokens','decisions')),
    -- Closed is one state. A row with a reason and no moment is a session that
    -- says why it ended and never did.
    CHECK ((closed_at IS NULL) = (close_reason IS NULL)),
    CHECK ((rotated_from IS NULL) = (generation = 1)),
    UNIQUE (program_id, label),
    -- The composite the Agent run and the chain both point through, so neither
    -- can name a session of another Program.
    UNIQUE (id, program_id),
    FOREIGN KEY (rotated_from, program_id)
        REFERENCES orchestrator_sessions (id, program_id)
);

-- The whole of "one campaign at a time". Every other rule in this file is about
-- when to close one and what to write down; that there is never a second one
-- open is the index's, because two open sessions would make "resume" a question
-- with two answers.
CREATE UNIQUE INDEX orchestrator_sessions_one_open
    ON orchestrator_sessions (program_id) WHERE closed_at IS NULL;

CREATE INDEX orchestrator_sessions_chain_idx
    ON orchestrator_sessions (rotated_from) WHERE rotated_from IS NOT NULL;

COMMENT ON TABLE orchestrator_sessions IS
  'One logical orchestrator campaign: the ceilings it was admitted under, the sessions it replaced, and when and why it ended. The Agent runs inside it are its turns, and everything the successor needs is compiled out of durable state rather than handed over in memory.';
COMMENT ON COLUMN orchestrator_sessions.weights_version IS
  'The weights row the ceilings were copied from. Copied and not joined: the ceilings are what this session was admitted under, and an operator editing the active row mid-campaign must not move a ceiling a running session is being measured against.';
COMMENT ON COLUMN orchestrator_sessions.rotated_from IS
  'The session this one replaced, NULL for the first of a campaign. The chain is what makes a rotation a continuation rather than two unrelated sessions.';
COMMENT ON COLUMN orchestrator_sessions.close_reason IS
  'Which ceiling ended it. Only the three ceilings: a session is closed by the runtime reaching one of them and by nothing else, so a fourth word here would be a close nobody can act on.';

INSERT INTO label_prefixes (kind, prefix) VALUES ('orchestrator_sessions', 'OS');

CREATE TRIGGER orchestrator_sessions_assign_label BEFORE INSERT ON orchestrator_sessions
    FOR EACH ROW EXECUTE FUNCTION assign_label();

-- Bookkeeping, for 25's reason: the rotation writes its own occurrence Event
-- with the usage and the reason in it, and every turn of the session is an
-- Agent run that emits already. A row event per session would put a third copy
-- of the same life in the log.
INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
    ('orchestrator_sessions', 'bookkeeping',
     'the campaign one pass is a turn of; scheduler.rotated and the Agent runs are the events', '28');

INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
    ('orchestrator_sessions', 'program_id', 'program-scoped: the purge root');

GRANT SELECT, INSERT, UPDATE ON orchestrator_sessions TO rk2_runtime;


-- ---------------------------------------------------------------------------
-- 3. The turn as a link
-- ---------------------------------------------------------------------------
-- Which session a pass was a turn of, written where the turn is. No delete
-- action, which is 016's rule for every key that is not a purge edge: the
-- Program is the one root a cascade runs from, and a second cascade path is a
-- second way for a narrow delete to half-succeed. The column is nullable
-- because most Agent runs are not turns of a campaign -- every run before this
-- file, and every worker run after it.
ALTER TABLE agent_runs
    ADD COLUMN orchestrator_session_id uuid,
    ADD CONSTRAINT agent_runs_orchestrator_session_fk
        FOREIGN KEY (orchestrator_session_id, program_id)
        REFERENCES orchestrator_sessions (id, program_id),
    -- A worker run is not a turn of a planning campaign, and neither is the
    -- operator's own request that `rk send` records as an orchestrator run.
    -- Both would count against ceilings they have nothing to do with.
    ADD CONSTRAINT agent_runs_session_is_planning_ck
        CHECK (orchestrator_session_id IS NULL
               OR (role = 'orchestrator' AND task_id IS NULL));

CREATE INDEX agent_runs_orchestrator_session_idx
    ON agent_runs (orchestrator_session_id) WHERE orchestrator_session_id IS NOT NULL;

COMMENT ON COLUMN agent_runs.orchestrator_session_id IS
  'The campaign this run is one turn of, for planning runs the runtime opened. NULL for work, for subagents, and for the operator request `rk send` records as an orchestrator run -- none of the three is a turn anything is bounded by.';


-- ---------------------------------------------------------------------------
-- 4. What a session has spent
-- ---------------------------------------------------------------------------
-- Three sums over rows that exist for their own reasons. Nothing here is
-- written by the rotation, which is what makes a restart mid-campaign
-- indistinguishable from no restart at all: the numbers are in the runs and the
-- Events, and the supervisor holds none of them.
CREATE VIEW orchestrator_session_usage AS
    SELECT s.id AS session_id,
           s.program_id,
           s.label,
           s.generation,
           s.max_turns,
           s.max_tokens,
           s.max_decisions,
           s.closed_at,
           u.turns,
           u.tokens,
           d.decisions
      FROM orchestrator_sessions s
      CROSS JOIN LATERAL (
          -- A turn is counted the moment it starts, not when it finishes: a
          -- pass that opened a child and died is a turn the session spent.
          SELECT count(*)::integer AS turns,
                 coalesce(sum(coalesce(ar.input_tokens, 0)
                            + coalesce(ar.output_tokens, 0)), 0)::bigint AS tokens
            FROM agent_runs ar
           WHERE ar.orchestrator_session_id = s.id) u
      CROSS JOIN LATERAL (
          -- Decisions are the choices the session recorded, in every one of the
          -- five words 27 writes: a session that answered `no_choice` eighty
          -- times has decided eighty times and learned something each time.
          SELECT count(*)::integer AS decisions
            FROM events e
            JOIN agent_runs ar ON ar.id = e.agent_run_id
           WHERE ar.orchestrator_session_id = s.id
             AND e.type = 'scheduler.chose') d;

COMMENT ON VIEW orchestrator_session_usage IS
  'What one orchestrator session has spent against what it was admitted with, derived from the runs it holds and the choices they recorded. Nothing increments it, so a supervisor that died mid-campaign resumes to the same numbers it would have had.';

-- Which ceiling a session has reached, or nothing. One function because three
-- callers ask it -- the rotation, the check and the open -- and three copies of
-- one comparison is how a ceiling comes to bind in one place and not another.
-- The order is the order they are reported in and is fixed so that a session
-- past two ceilings names the same one twice running.
CREATE FUNCTION orchestrator_session_spent(p_session uuid) RETURNS text
LANGUAGE sql STABLE AS $fn$
    SELECT CASE
             WHEN u.turns     >= u.max_turns     THEN 'turns'
             WHEN u.tokens    >= u.max_tokens    THEN 'tokens'
             WHEN u.decisions >= u.max_decisions THEN 'decisions'
           END
      FROM orchestrator_session_usage u
     WHERE u.session_id = p_session;
$fn$;

COMMENT ON FUNCTION orchestrator_session_spent(uuid) IS
  'The first ceiling this session has reached, or NULL while it may still take another turn. Greater-or-equal and not greater: the ceiling is how much the session may spend, so reaching it is having spent it.';


-- ---------------------------------------------------------------------------
-- 5. Rotation
-- ---------------------------------------------------------------------------
INSERT INTO event_types (id, family, subject_table, description) VALUES
    ('scheduler.rotated', 'occurrence', NULL,
     'one orchestrator session reached a ceiling and was closed: what it spent, against what it was admitted with, and which ceiling ended it (ticket 28)');

-- Criterion 2. Called at the end of a pass, so a session that reached a ceiling
-- is closed while the runtime is still awake and not left open until something
-- else happens to want one; called again at the start of the next open, so a
-- supervisor that died between the two does not leave a spent session to be
-- resumed. Idempotent by construction: the second call finds no open session
-- past a ceiling and answers nothing.
--
-- The Event carries usage and ceilings both, because "why did this campaign
-- rotate" is a comparison, and a reader holding only the reason would have to
-- go and find the numbers the decision was made on.
CREATE FUNCTION rotate_orchestrator_session() RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p         uuid := rk2_program_required();
    v_session orchestrator_sessions%ROWTYPE;
    v_usage   orchestrator_session_usage%ROWTYPE;
    v_reason  text;
    v_payload jsonb;
BEGIN
    SELECT * INTO v_session FROM orchestrator_sessions
     WHERE program_id = p AND closed_at IS NULL
       FOR UPDATE;
    IF NOT FOUND THEN
        RETURN NULL;
    END IF;

    v_reason := orchestrator_session_spent(v_session.id);
    IF v_reason IS NULL THEN
        RETURN NULL;
    END IF;

    SELECT * INTO v_usage FROM orchestrator_session_usage
     WHERE session_id = v_session.id;

    UPDATE orchestrator_sessions
       SET closed_at = now(), close_reason = v_reason
     WHERE id = v_session.id;

    v_payload := jsonb_build_object(
        'session',    v_session.label,
        'generation', v_session.generation,
        'reason',     v_reason,
        'usage',      jsonb_build_object('turns',     v_usage.turns,
                                         'tokens',    v_usage.tokens,
                                         'decisions', v_usage.decisions),
        'ceilings',   jsonb_build_object('turns',     v_session.max_turns,
                                         'tokens',    v_session.max_tokens,
                                         'decisions', v_session.max_decisions));

    -- The runtime's own finding and not a model's: nothing the session answered
    -- caused this, and a session is closed by arithmetic it does not perform.
    -- No `agent_run_id` either -- the session is many runs, and naming its last
    -- one would read as that run having ended the campaign.
    INSERT INTO events (program_id, type, actor_kind, payload)
    VALUES (p, 'scheduler.rotated', 'runtime', v_payload);

    RETURN v_payload;
END $fn$;

COMMENT ON FUNCTION rotate_orchestrator_session() IS
  'Closes this Program''s open orchestrator session if it has reached a ceiling, and writes one scheduler.rotated Event carrying what it spent, what it was admitted with and which ceiling ended it. Answers nothing when there is no open session or the open one may still take a turn, so the runtime may call it after every pass.';

-- The open, rewritten as resume-or-rotate. 27's version opened one session per
-- pass; this one finds the campaign's open session, closes it first if it is
-- spent, and opens a successor only when there is nothing to resume into.
--
-- The return grows by what the caller now needs to compile a capsule against:
-- which session this is, how deep the campaign is, and -- when the pass rotated
-- -- what the closed session spent, so the Ledger can say a campaign rotated
-- without going back to the Event log to find out.
--
-- The token ceiling the child is handed is the tighter of two: what the Program
-- allows one run to spend, and what the session has left before it rotates. A
-- child handed the first alone could spend a session's whole remaining envelope
-- in one turn and be inside its ceiling the whole time.
CREATE OR REPLACE FUNCTION open_orchestrator_session() RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p         uuid := rk2_program_required();
    v_model   text;
    v_effort  text;
    v_run     uuid;
    v_label   text;
    v_cap     integer;
    v_tokens  bigint;
    v_weights scheduler_weights%ROWTYPE;
    v_session orchestrator_sessions%ROWTYPE;
    v_prev    orchestrator_sessions%ROWTYPE;
    v_usage   orchestrator_session_usage%ROWTYPE;
    v_rotated jsonb;
BEGIN
    SELECT r.model, r.effort INTO v_model, v_effort
      FROM roles r WHERE r.role = 'orchestrator';
    IF NOT FOUND THEN
        RAISE EXCEPTION 'the roster has no orchestrator row to open a session as'
            USING ERRCODE = 'check_violation';
    END IF;

    -- Before anything is read about the campaign, because everything read after
    -- this is read about the session the pass will actually run in.
    v_rotated := rotate_orchestrator_session();

    SELECT * INTO v_session FROM orchestrator_sessions
     WHERE program_id = p AND closed_at IS NULL
       FOR UPDATE;

    IF v_session.id IS NULL THEN
        SELECT * INTO v_weights FROM scheduler_weights WHERE active;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'no active scheduler weights row to take session ceilings from'
                USING ERRCODE = 'check_violation';
        END IF;

        SELECT * INTO v_prev FROM orchestrator_sessions
         WHERE program_id = p
         ORDER BY generation DESC, opened_at DESC
         LIMIT 1;

        INSERT INTO orchestrator_sessions
            (program_id, weights_version, max_turns, max_tokens, max_decisions,
             rotated_from, generation)
        VALUES (p, v_weights.version, v_weights.session_max_turns,
                v_weights.session_max_tokens, v_weights.session_max_decisions,
                v_prev.id, coalesce(v_prev.generation, 0) + 1)
        -- Two passes opening a campaign at once is one campaign: the partial
        -- unique index is the rule, and the loser reads the winner's row rather
        -- than failing a pass over a race whose answer it agrees with.
        ON CONFLICT (program_id) WHERE closed_at IS NULL DO NOTHING
        RETURNING * INTO v_session;

        IF v_session.id IS NULL THEN
            SELECT * INTO v_session FROM orchestrator_sessions
             WHERE program_id = p AND closed_at IS NULL
               FOR UPDATE;
        END IF;
    END IF;

    INSERT INTO agent_runs (program_id, role, model, effort, mission_packet,
                            orchestrator_session_id)
    VALUES (p, 'orchestrator', v_model, v_effort, '{}', v_session.id)
    RETURNING id, label INTO v_run, v_label;

    -- Both ceilings travel with the session for the reason the claim carries
    -- them: the container's one network reaches the capability proxy and no
    -- database, so a number the child is bounded by is a number that was read
    -- here or not at all. The subagent cap is the same one active weights row
    -- the claim reads; the token ceiling is the Program's own per-run one held
    -- against what this session has left.
    SELECT w.max_concurrent_subagents INTO v_cap
      FROM scheduler_weights w WHERE w.active;
    SELECT c.run_tokens INTO v_tokens
      FROM program_capacity c WHERE c.program_id = p;
    SELECT * INTO v_usage FROM orchestrator_session_usage
     WHERE session_id = v_session.id;

    -- `least` ignores NULLs, which is what makes an unbudgeted Program fall to
    -- the session remainder rather than to no ceiling at all. The remainder is
    -- positive here: a session at or past its token ceiling was closed above.
    v_tokens := least(v_tokens, v_session.max_tokens - v_usage.tokens);

    RETURN jsonb_build_object(
        'agent_run', v_run::text, 'label', v_label,
        'model', v_model, 'effort', v_effort,
        'subagent_cap', v_cap, 'token_cap', v_tokens,
        'session', v_session.id::text, 'session_label', v_session.label,
        'generation', v_session.generation,
        'turns', v_usage.turns, 'decisions', v_usage.decisions,
        'max_turns', v_session.max_turns,
        'max_decisions', v_session.max_decisions,
        'capsule_bytes', (SELECT w.capsule_max_bytes FROM scheduler_weights w WHERE w.active),
        'capsule_tokens', (SELECT w.capsule_max_tokens FROM scheduler_weights w WHERE w.active),
        'rotated', v_rotated);
END $fn$;

COMMENT ON FUNCTION open_orchestrator_session() IS
    'Opens one turn of this Program''s orchestrator campaign: rotates the open '
    'session first if it has reached a ceiling, resumes it otherwise, and '
    'starts one Task-less Agent run inside it at the model and effort the '
    'roster row states. Returns what the child has no database to read -- the '
    'cross-role subagent cap, a token ceiling that is the tighter of the '
    'Program''s per-run one and what the session has left, and the capsule '
    'limits the resume packet is fitted to -- together with the session it is a '
    'turn of and what that session has spent. It holds no lane slot and '
    'reserves no budget, because a planning session has no Task and therefore '
    'no lane to promise against.';


-- ---------------------------------------------------------------------------
-- 6. The scheduler surface is the runtime's, not the agent's
-- ---------------------------------------------------------------------------
-- 029's default privileges hand every new function to `rk2_runtime`, and
-- Postgres hands every new function to PUBLIC. The revoke is the load-bearing
-- half here too: a connection a model reaches through that could call
-- `rotate_orchestrator_session()` would be a model ending its own session and
-- choosing when its ceilings apply.
DO $$
DECLARE f text;
BEGIN
    FOREACH f IN ARRAY ARRAY[
        'rotate_orchestrator_session()', 'orchestrator_session_spent(uuid)']
    LOOP
        EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC', f);
        EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO rk2_runtime', f);
    END LOOP;
END $$;

GRANT SELECT ON orchestrator_session_usage TO rk2_runtime;


-- ---------------------------------------------------------------------------
-- 7. The standing check
-- ---------------------------------------------------------------------------
-- What rotation can get wrong, as rows. "One open session per Program" is not
-- among them: the partial unique index refuses it, and a check that re-asserted
-- an index would be asserting the database against itself.
CREATE FUNCTION check_orchestrator_rotation()
RETURNS TABLE (problem text, subject text, detail text)
LANGUAGE sql STABLE AS $fn$
    -- (a) criterion 1, as the thing that goes wrong when a ceiling is guidance:
    --     the session kept going. Turns and decisions are counted before the
    --     turn runs, so exceeding either means a pass started in a session that
    --     was already spent. Tokens are deliberately absent: a turn is admitted
    --     before it spends and what it spent is known only when it closes, so
    --     the last turn of a session may legitimately end above the ceiling
    --     that stopped it. Arm (b) is what catches tokens.
    SELECT 'session_ran_past_its_ceiling'::text, u.label,
           'turns ' || u.turns || '/' || u.max_turns ||
           ', decisions ' || u.decisions || '/' || u.max_decisions
      FROM orchestrator_session_usage u
     WHERE u.turns > u.max_turns OR u.decisions > u.max_decisions

UNION ALL
    -- (b) the same property where it is exact: a turn that started after its
    --     session was closed. Whatever the ceiling was, the runtime had already
    --     answered that this session takes no more turns.
    SELECT 'turn_started_in_a_closed_session', ar.label,
           ar.label || ' started after ' || s.label || ' closed'
      FROM agent_runs ar
      JOIN orchestrator_sessions s ON s.id = ar.orchestrator_session_id
     WHERE s.closed_at IS NOT NULL AND ar.started_at > s.closed_at

UNION ALL
    -- (c) criterion 2's Event half. A session closed for a reason and no record
    --     of it is a campaign whose history has a gap exactly where the
    --     interesting part is.
    SELECT 'rotation_not_recorded', s.label,
           s.label || ' closed on ' || s.close_reason || ' and wrote no scheduler.rotated'
      FROM orchestrator_sessions s
     WHERE s.closed_at IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM events e
                        WHERE e.program_id = s.program_id
                          AND e.type = 'scheduler.rotated'
                          AND e.payload ->> 'session' = s.label)

UNION ALL
    -- (d) the chain, which is what makes rotation a continuation. A successor
    --     of a session that is still open would be two live campaigns wearing
    --     one chain, and a generation that does not follow its predecessor's
    --     makes the depth an operator reads first a number about nothing.
    SELECT 'rotation_chain_broken', s.label,
           s.label || ' generation ' || s.generation || ' follows ' || prev.label ||
           ' generation ' || prev.generation ||
           CASE WHEN prev.closed_at IS NULL THEN ', which is still open' ELSE '' END
      FROM orchestrator_sessions s
      JOIN orchestrator_sessions prev ON prev.id = s.rotated_from
     WHERE prev.closed_at IS NULL OR s.generation <> prev.generation + 1

UNION ALL
    -- (e) 27's decisions, now that they belong to a campaign. A choice recorded
    --     against a session no campaign holds is a decision no ceiling counts,
    --     which is criterion 1 defeated one run at a time. Keyed on having
    --     recorded a choice for 27's reason: `rk send` records an operator's own
    --     request as an orchestrator run and that request is a person's turn,
    --     not a campaign's.
    SELECT 'choice_outside_a_campaign', ar.label,
           ar.label || ' recorded a choice and is no turn of any session'
      FROM events e
      JOIN agent_runs ar ON ar.id = e.agent_run_id
     WHERE e.type = 'scheduler.chose' AND ar.orchestrator_session_id IS NULL

UNION ALL
    -- (f) textual, for the reason 27's are: the property is a property of what
    --     the function is made of. A session is only ever opened through
    --     `open_orchestrator_session`, so an edit that drops the rotation from
    --     it drops every ceiling in this file, and the row arms above would
    --     stay silent until a campaign had already run past one.
    SELECT 'rotation_not_asked_on_open', asked.fn,
           'the open path decides whether to rotate without asking ' || asked.asks
      FROM (VALUES ('open_orchestrator_session'::text, 'rotate_orchestrator_session'::text),
                   ('rotate_orchestrator_session', 'orchestrator_session_spent')) AS asked(fn, asks)
      JOIN pg_proc p ON p.proname = asked.fn
                    AND p.pronamespace = 'public'::regnamespace
     WHERE p.prosrc !~ asked.asks

UNION ALL
    -- (g) and the surface half of it: the two verbs a model must not reach.
    SELECT 'rotation_verb_reachable_by_state', p.proname,
           'rk2_state may execute ' || p.proname || '; ending a session is the runtime''s'
      FROM pg_proc p
     WHERE p.pronamespace = 'public'::regnamespace
       AND p.proname IN ('rotate_orchestrator_session', 'open_orchestrator_session')
       AND has_function_privilege('rk2_state', p.oid, 'EXECUTE')
$fn$;

COMMENT ON FUNCTION check_orchestrator_rotation() IS
  'A campaign runs inside its ceilings, ends at one, says so once, and hands on to a successor that points back at it. Every decision it records belongs to a session, and the verbs that end one are the runtime''s alone.';

REVOKE ALL ON FUNCTION check_orchestrator_rotation() FROM PUBLIC;

INSERT INTO standing_checks (name, query, owner_ticket, note) VALUES
    ('orchestrator_rotation', 'SELECT * FROM check_orchestrator_rotation()', '28',
     'a session stops at its ceilings, records the rotation once, and hands on to a successor that points back at it');


-- ---------------------------------------------------------------------------
-- 8. Bring the corpus to true
-- ---------------------------------------------------------------------------
-- One new table, so the RLS finalizer has something to do this time:
-- `orchestrator_sessions` carries `program_id` and is not global, which is the
-- whole of what `apply_state_rls()` keys on.
SELECT apply_state_rls();
SELECT apply_state_grants();

DO $$
DECLARE n integer; d text;
BEGIN
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_orchestrator_rotation();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-28 refuses to finish: % rotation problem(s): %', n, d;
    END IF;

    -- The two neighbours this file reached into: the session the dispatch
    -- opens, and the isolation rules a new table has to satisfy. Event coverage
    -- is not asked here even though this file adds a table to it: the corpus
    -- makes its enforcement triggers ALWAYS at the end of provisioning, so
    -- `check_event_coverage()` is loud in the middle of a run and silent only
    -- where it is already asserted, which is after the last migration.
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_orchestrator_dispatch();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-28 breaks the orchestrator dispatch (% problems): %', n, d;
    END IF;

    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_program_isolation();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-28 breaks program isolation (% problems): %', n, d;
    END IF;
END $$;
