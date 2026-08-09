-- ---------------------------------------------------------------------------
-- 022_ticket13_hooks_and_receipts.sql   (ticket 13; Q4, Q9, Q13, Q19, Q24)
--
-- Applies on top of 001-017 (ticket 35, `prototype/program-isolation` 6579365),
-- 019 (ticket 34, `prototype/role-kind` a4bcfa9), 020 (ticket 12,
-- `prototype/state-access` 2f236f3) and 021 (ticket 26, `prototype/scope-policy`
-- 2aa206c). 018 is ticket 27's and has not landed, so the numbering skips it.
--
-- The hook layer does not get a table of its own. `tool_runs` (005) already IS
-- the hook-side receipt -- id, program, agent run, tool, args, start, finish,
-- status -- and `receipts.tool_run_id` (005) already IS the reconciliation edge
-- between the hook receipt and the proxy receipt. This migration finishes both
-- rather than adding a parallel table that would have to be kept in sync.
--
-- Shape of the guarantee:
--   PreToolUse  INSERTs the receipt (status 'running') and then, in the SAME
--               transaction, settles it if policy says deny/ask.
--   PostToolUse / PostToolUseFailure UPDATE it to a terminal status.
--   A receipt still 'running' when the program resumes is swept to 'abandoned'
--               -- an open receipt is a fact, not a gap.
--
-- The hook writes ROWS. Events come from the 013/016 trigger, off the same
-- session GUCs, so a hook cannot write a receipt without writing its events and
-- cannot write an event type outside `event_types`.
--
-- Two things here are new relative to the ticket's own framing, and both come
-- from running the composed schema rather than reading it:
--
--   * `receipts` gets a NOT NULL-shaped constraint: an agent-lane receipt with
--     `decision='allowed'` must name a `tool_run`. Before this line the schema
--     permitted served egress with no hook receipt behind it -- which is
--     precisely the hole "no tool call completes without producing a receipt"
--     claims does not exist -- and the canonical seed does it four times.
--   * `tool_runs.egress_token_sha256`. The proxy authenticates the TOOL RUN,
--     not the container, which is what makes the constraint above satisfiable
--     for `run_tool` (ffuf, nuclei, ...) and unsatisfiable for a shell that
--     holds no token.
-- ---------------------------------------------------------------------------

SET client_min_messages = warning;


-- ===========================================================================
-- 1. Risk classes as rows (Q4)
-- ===========================================================================

-- Q4 named three classes. A fourth, `forbidden`, exists because the map's
-- "one egress path" constraint has to be expressible: `WebFetch` and
-- `WebSearch` are not risky-but-approvable, they are the CLI reaching the
-- network without traversing the scope proxy, and no human approval can make
-- that produce a proxy receipt.
CREATE TABLE risk_classes (
    risk_class  text PRIMARY KEY,
    decision    text NOT NULL CHECK (decision IN ('allow','deny','ask')),
    description text NOT NULL
);

INSERT INTO risk_classes (risk_class, decision, description) VALUES
    ('autonomous',        'allow',
        'read-only or local-only; no state leaves the container, no target is touched'),
    ('constrained',       'allow',
        'state-changing but bounded by another enforcement layer (proxy scope, container FS, budget)'),
    ('approval_required', 'ask',
        'a human must answer before it runs; the hook parks the task (Q9) and the run ends (ticket 08)'),
    ('forbidden',         'deny',
        'no approval can make this safe: it would produce an action with no runtime provenance record');

-- Longest matching pattern wins; `*` is the fallback and is deliberately
-- `approval_required` rather than `forbidden`. An unlisted tool is not proven
-- dangerous, but it must not run unattended -- and because parking ends the
-- run, an unlisted tool costs a human round trip, which is the pressure that
-- keeps this table current.
CREATE TABLE tool_risk_classes (
    tool_pattern text PRIMARY KEY,
    risk_class   text NOT NULL REFERENCES risk_classes(risk_class),
    rationale    text NOT NULL
);

INSERT INTO tool_risk_classes (tool_pattern, risk_class, rationale) VALUES
    ('*',            'approval_required', 'fallback: an unenumerated tool has no analysed blast radius'),
    ('Read',         'autonomous',        'local filesystem read inside the agent container'),
    ('Glob',         'autonomous',        'local filesystem enumeration'),
    ('Grep',         'autonomous',        'local filesystem search'),
    ('TodoWrite',    'autonomous',        'agent-local scratch state, no external effect'),
    ('BashOutput',   'autonomous',        'reads a shell already receipted by its Bash call'),
    ('KillShell',    'autonomous',        'terminates a shell already receipted by its Bash call'),
    ('EndConversation','autonomous',      'CLI-internal terminator; hook-EXEMPT in CLI 2.1.224 (VFb set) and safe only because it has no external effect'),
    -- Ticket 13 moves these four from `constrained` to `forbidden`. The reason
    -- is in section 8: each of them is an effect the roster forbids under a
    -- different name, and a receipt naming the tool does not bind the effect.
    ('Write',        'forbidden',         'ticket 11 forbids Write; granting it under another name is the same grant'),
    ('Edit',         'forbidden',         'ticket 11 forbids Edit'),
    ('NotebookEdit', 'forbidden',         'ticket 11 forbids NotebookEdit'),
    ('Bash',         'forbidden',         'union of three separate denials: unbounded binary (run_tool has an enum), file write (Write/Edit are denied), and a process that outlives its own receipt. exec.tool_run is the receipted form and every Bash-holding role already has it'),
    ('Task',         'constrained',       'subagent spawn; the child inherits these hooks (old tool name, still used in init/denial payloads)'),
    ('Agent',        'constrained',       'subagent spawn; the child inherits these hooks'),
    ('Skill',        'constrained',       'records skill name and SKILL.md hash on the task row (ticket 09)'),
    ('WebFetch',     'forbidden',         'network egress that does not traverse the scope proxy: no receipt can exist'),
    ('WebSearch',    'forbidden',         'network egress that does not traverse the scope proxy: no receipt can exist'),
    ('mcp__rk2__*',  'constrained',       'first-party MCP tools; every network verb inside them goes through the proxy');

-- Exact match, then longest glob prefix, then `*`. No regex: a policy table an
-- operator cannot read at a glance is not a policy table. The pattern is
-- returned as well as the class so a receipt can cite the ROW that decided it,
-- not just the verdict.
CREATE FUNCTION resolve_risk_class_pattern(p_tool text) RETURNS text
LANGUAGE sql STABLE AS $$
    SELECT tool_pattern FROM tool_risk_classes
     WHERE tool_pattern = p_tool
        OR (tool_pattern LIKE '%*' AND p_tool LIKE replace(tool_pattern,'*','%'))
     ORDER BY (tool_pattern = p_tool) DESC, length(tool_pattern) DESC
     LIMIT 1;
$$;

CREATE FUNCTION resolve_risk_class(p_tool text) RETURNS text
LANGUAGE sql STABLE AS $$
    SELECT risk_class FROM tool_risk_classes
     WHERE tool_pattern = resolve_risk_class_pattern(p_tool);
$$;

-- Ticket 35 rule 1: a table is program-scoped unless it says why not.
INSERT INTO program_global_tables (table_name, reason) VALUES
    ('risk_classes',      'the risk vocabulary; one blast-radius model for the whole runtime, not per program'),
    ('tool_risk_classes', 'the tool policy; per-program tool risk would let a program grant itself a tool the roster forbids');


-- ===========================================================================
-- 2. The session binding the SDK does not give the hook (Q24)
-- ===========================================================================

-- No hook payload in SDK 0.2.132 carries a task id, a mission id or a program
-- id. What a tool-lifecycle hook sees is: session_id, cwd, transcript_path,
-- tool_use_id, tool_name, tool_input, and -- inside a subagent -- agent_id and
-- agent_type. The SDK's own docstring on `_SubagentContextMixin` says agent_id
-- is "the only reliable way to attribute each one to the correct sub-agent"
-- when parallel subagents interleave over the one control channel.
--
-- So the runtime carries the correlation, not the hook. It binds
-- (session_id, sdk_agent_id) to an agent_run BEFORE the session is allowed to
-- make a tool call, and the hook resolves through this table. A tool call from
-- an unbound (session, agent) pair is a call the runtime cannot attribute, and
-- the hook denies it -- that is the whole reason this table exists.
--
-- Both foreign keys carry `program_id`, appended last (ticket 35 rule 3, and
-- `conkey[1]` has to stay the column `purge_cascade_edges` reads).
-- `id` is a surrogate the natural key does not need, and it is not decoration:
-- ticket 07's `emit_event()` resolves a row event's subject as
-- `(new_j ->> 'id')::uuid` and RAISEs on a table without one. A table that
-- cannot name its own subject cannot appear in the event log, and a hook-layer
-- table outside the event log is the exact thing this ticket exists to prevent.
CREATE TABLE agent_sessions (
    id             uuid NOT NULL DEFAULT uuidv7(),
    program_id     uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    session_id     text NOT NULL,
    sdk_agent_id   text NOT NULL DEFAULT '',   -- '' = main thread, else SubagentStart agent_id
    sdk_agent_type text,
    agent_run_id   uuid NOT NULL,
    task_id        uuid,
    trace_id       text,
    bound_at       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (id),
    -- the real key: one binding per (program, SDK session, SDK agent)
    UNIQUE (program_id, session_id, sdk_agent_id),
    -- NO ACTION, not CASCADE. Ticket 07's `check_event_log_integrity` refuses a
    -- cascading delete on anything but a purge edge, and it is right to: a
    -- cascade removes rows without an event, so the log would stop accounting
    -- for them. Only `program_id` cascades, because a program purge is the one
    -- deletion the design has.
    CONSTRAINT agent_sessions_agent_run_id_fkey
        FOREIGN KEY (agent_run_id, program_id)
        REFERENCES agent_runs (id, program_id),
    CONSTRAINT agent_sessions_task_id_fkey
        FOREIGN KEY (task_id, program_id)
        REFERENCES tasks (id, program_id)
);

CREATE INDEX agent_sessions_run_idx ON agent_sessions (agent_run_id);

INSERT INTO purge_cascade_edges (table_name, column_name, rationale)
VALUES ('agent_sessions','program_id','program-scoped: the purge root');


-- ===========================================================================
-- 3. `tool_runs` becomes the hook-side receipt
-- ===========================================================================

ALTER TABLE tool_runs
    ADD COLUMN task_id             uuid,
    -- the SDK's own idempotency key. UNIQUE per program: a retried or
    -- duplicated hook callback cannot open a second receipt, and the sweep can
    -- tell a re-delivery from a new call.
    ADD COLUMN tool_use_id         text,
    ADD COLUMN session_id          text,
    ADD COLUMN sdk_agent_id        text,
    ADD COLUMN sdk_agent_type      text,
    -- DEFAULT 'runtime', not 'builtin': a row that does not say a hook wrote it
    -- was not written by a hook. The hook layer always sets this explicitly, so
    -- the default only ever applies to rows the runtime writes itself -- and
    -- getting that backwards would let a forgotten column silently claim hook
    -- provenance for a row no hook ever saw.
    ADD COLUMN transport           text NOT NULL DEFAULT 'runtime'
                                   CHECK (transport IN ('builtin','mcp','runtime')),
    ADD COLUMN mcp_server          text,
    ADD COLUMN risk_class          text REFERENCES risk_classes(risk_class),
    ADD COLUMN decision            text CHECK (decision IN ('allow','deny','ask')),
    ADD COLUMN decision_reason     text,
    -- FK deliberately absent: `pending_decisions` is ticket 12's table but
    -- ticket 28 owns its lifecycle. Ticket 13 records the pointer; 28 adds the
    -- constraint, once it says who may resolve one.
    ADD COLUMN pending_decision_id uuid,
    ADD COLUMN args_sha256         text REFERENCES artifacts(sha256),
    ADD COLUMN result_sha256       text REFERENCES artifacts(sha256),
    -- The proxy credential minted for THIS tool run, stored as a hash so the
    -- table is not itself a secret. See section 5.
    ADD COLUMN egress_token_sha256 text,
    ADD COLUMN closed_by           text CHECK (closed_by IN
                                   ('PostToolUse','PostToolUseFailure','PreToolUse','sweep')),
    ADD COLUMN hook_error          text;

-- Also NO ACTION, and here it matters more than tidiness: ON DELETE CASCADE
-- would mean deleting a task erases the receipts of everything that task did.
-- A receipt outlives the work it describes or it is not evidence.
ALTER TABLE tool_runs ADD CONSTRAINT tool_runs_task_id_fkey
    FOREIGN KEY (task_id, program_id) REFERENCES tasks (id, program_id);

-- 'parked'    : PreToolUse asked, a pending_decision exists, the run ends.
-- 'abandoned' : the receipt was open when the program resumed. The tool may or
--               may not have run; the log says only that nothing closed it.
ALTER TABLE tool_runs DROP CONSTRAINT tool_runs_status_check;
ALTER TABLE tool_runs ADD CONSTRAINT tool_runs_status_check
    CHECK (status IN ('running','success','error','denied','parked','abandoned'));

-- A receipt opened by a hook must carry the SDK identity. A receipt opened by
-- the runtime itself (transport 'runtime') must not pretend to have one.
ALTER TABLE tool_runs ADD CONSTRAINT tool_runs_hook_identity_ck
    CHECK ((transport = 'runtime') = (tool_use_id IS NULL));

-- Every hook-opened receipt names what closed it. A runtime-opened row is
-- exempt: the runtime closing its own row has no hook event to cite, and
-- inventing one would make `closed_by` unusable as evidence.
ALTER TABLE tool_runs ADD CONSTRAINT tool_runs_terminal_close_ck
    CHECK (status = 'running' OR transport = 'runtime' OR closed_by IS NOT NULL);

ALTER TABLE tool_runs ADD CONSTRAINT tool_runs_parked_ck
    CHECK (status <> 'parked' OR pending_decision_id IS NOT NULL);

-- An egress token may only exist on a receipt the runtime allowed to run. A
-- denied or parked call must not be able to hand a live proxy credential to the
-- process it just refused.
ALTER TABLE tool_runs ADD CONSTRAINT tool_runs_egress_token_ck
    CHECK (egress_token_sha256 IS NULL
           OR (decision = 'allow' AND egress_token_sha256 ~ '^[0-9a-f]{64}$'));

CREATE UNIQUE INDEX tool_runs_tool_use_id_uq
    ON tool_runs (program_id, tool_use_id) WHERE tool_use_id IS NOT NULL;

CREATE UNIQUE INDEX tool_runs_egress_token_uq
    ON tool_runs (program_id, egress_token_sha256) WHERE egress_token_sha256 IS NOT NULL;

CREATE INDEX tool_runs_open_idx
    ON tool_runs (program_id, started_at) WHERE status = 'running';


-- ===========================================================================
-- 4. Reconciling the two receipt lanes (the ticket's last bullet)
-- ===========================================================================

-- The proxy and the hook both describe the same request, and until now nothing
-- said they had to agree. They reconcile on `receipts.tool_run_id`, and the
-- rule is asymmetric on purpose:
--
--   * the proxy MAY write a receipt for any request it saw, including one it
--     refused -- silence about an unattributable request is worse than a row;
--   * the proxy MAY NOT have SERVED an agent-lane request it could not attribute
--     to an open tool run.
--
-- So the constraint is on `decision='allowed'`, not on the lane alone. A raw
-- `curl` from a shell produces `lane='agent', decision='blocked'` with a null
-- tool run: recorded, refused, and visible to `check_receipt_integrity`.
--
-- Ticket 26's `control` lane and `proxy_internal` are exempt: neither has a
-- tool call behind it by construction (the CLI's own inference traffic; the
-- proxy fetching a CSRF token as a client of the target).
-- Measured before it is enforced, so the failure names the hole rather than a
-- constraint name. On the canonical fixture this reports 4.
DO $$
DECLARE n bigint; d text;
BEGIN
    SELECT count(*), string_agg(program_id::text || '/' || label, ', ')
      INTO n, d FROM receipts
     WHERE lane = 'agent' AND decision = 'allowed' AND tool_run_id IS NULL;
    IF n > 0 THEN
        RAISE EXCEPTION
            '% agent-lane receipt(s) were SERVED and name no tool run: %', n, d
        USING HINT = 'these are requests that reached a target with no hook receipt behind them; '
                     'repair or reclassify them before 022 can enforce the guarantee';
    END IF;
END $$;

ALTER TABLE receipts ADD CONSTRAINT receipts_served_agent_needs_tool_run
    CHECK (NOT (lane = 'agent' AND decision = 'allowed' AND tool_run_id IS NULL));


-- ===========================================================================
-- 5. The egress token: the proxy authenticates the tool run, not the container
-- ===========================================================================
--
-- Ticket 04 holds egress at the network layer: the agent container has no route
-- except the proxy. That answers "can bytes leave by another path" and does not
-- answer "which tool call do these bytes belong to". If the proxy serves
-- anything arriving from the container, then any process in the container --
-- a shell, a background job outliving its own receipt, a subagent whose
-- PreToolUse was denied -- reaches the target with a receipt the runtime cannot
-- attribute, and section 4's constraint would be unsatisfiable.
--
-- So the runtime mints a per-tool-run proxy credential at PreToolUse, injects it
-- only into the environment of the process it spawns for that tool run, and
-- stores its sha256 here. The proxy resolves the credential to the tool run and
-- writes `receipts.tool_run_id` from what it authenticated rather than from
-- anything the request claims. A token is a name, never a secret the agent
-- sees: the agent's own tools never take it as an argument.
CREATE FUNCTION resolve_egress_token(p_program uuid, p_token_sha text)
RETURNS uuid LANGUAGE sql STABLE AS $$
    SELECT id FROM tool_runs
     WHERE program_id = p_program
       AND egress_token_sha256 = p_token_sha
       AND status = 'running'
       AND decision = 'allow';
$$;

COMMENT ON FUNCTION resolve_egress_token(uuid, text) IS
  'The proxy''s attribution lookup. Returns NULL for an unknown, closed, denied or parked tool run, and the proxy refuses the request rather than serving it unattributed. `status = ''running''` is what makes a background process outlive nothing: once PostToolUse closes the receipt the token stops resolving.';


-- ===========================================================================
-- 6. Emission policy (ticket 07 decisions 10, 11, 17)
-- ===========================================================================

INSERT INTO event_types (id, family, subject_table, description) VALUES
    ('tool_run.proposed', 'row','tool_runs',
        'PreToolUse fired: the model proposed a tool call and the receipt was opened'),
    ('tool_run.settled',  'row','tool_runs',
        'the receipt reached a terminal status: success, error, denied, parked or abandoned'),
    ('receipt.recorded',  'row','receipts',
        'the proxy wrote a receipt for one request it saw'),
    ('session.bound',     'row','agent_sessions',
        'the runtime bound an SDK session or subagent to an agent run; nothing else can attribute a tool call'),
    -- The only occurrence event ticket 13 adds. A hook that raised is not a row
    -- state -- the receipt it was supposed to write may not exist.
    ('hook.failed',       'occurrence', NULL,
        'a hook callback raised or timed out; PreToolUse fails closed (tool not executed), PostToolUse fails open (tool already ran, receipt left open)');

INSERT INTO event_table_config
    (table_name, created_type, updated_type, ignored_columns, redacted_columns) VALUES
    -- `args` is a bulk JSONB column and is redacted per ticket 07's rule; the
    -- content travels as `args_sha256` into `artifacts`, which is the form the
    -- rest of the design already trusts. `egress_token_sha256` is ignored
    -- rather than redacted: an event announcing that a credential changed is
    -- still an oracle for when one exists.
    ('tool_runs', 'tool_run.proposed', 'tool_run.settled', '{egress_token_sha256}', '{args}'),
    -- OBLIGATION ON THE PROXY LANE (tickets 04, 24): `receipts` now has an
    -- ENABLE ALWAYS emitter, and `emit_event()` RAISEs when `app.actor_kind` is
    -- unset. The proxy's DB session must `SET LOCAL app.actor_kind = 'runtime'`
    -- before inserting, or every receipt insert fails. That is the correct
    -- failure: a receipt written outside the event log is a provenance record
    -- with no provenance.
    ('receipts',  'receipt.recorded', NULL, '{}', '{}'),
    ('agent_sessions', 'session.bound', NULL, '{}', '{}');

SELECT attach_event_triggers();


-- ===========================================================================
-- 7. What the receipt guarantee can actually be checked for
-- ===========================================================================

-- `check_event_log_integrity` proves the event log accounts for every surviving
-- row. It cannot see a tool call that never produced a row at all. This is the
-- companion check: it looks for the shadow such a call leaves in the OTHER
-- lane. (a) is the load-bearing one -- an agent-lane proxy receipt with no hook
-- receipt behind it means bytes left the container from a tool call the hook
-- never saw. Section 4 now makes the served form of (a) unwritable; (a) stays
-- because a refused attempt is still a fact and a standing count of them means
-- something in the container is trying.
CREATE FUNCTION check_receipt_integrity(
        p_program uuid DEFAULT NULL,
        p_open_after interval DEFAULT interval '1 hour')
RETURNS TABLE (problem text, detail text, count bigint)
LANGUAGE plpgsql AS $$
BEGIN
    -- (a) egress attempt with no hook receipt, observed from the side the model
    -- cannot forge.
    RETURN QUERY
    SELECT 'egress_without_tool_run',
           r.host || ' ' || coalesce(r.method,'?') || ' ' || coalesce(r.path,''),
           count(*)::bigint
      FROM receipts r
     WHERE r.lane = 'agent'
       AND (p_program IS NULL OR r.program_id = p_program)
       AND (r.tool_run_id IS NULL
            OR NOT EXISTS (SELECT 1 FROM tool_runs t WHERE t.id = r.tool_run_id))
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


-- The static half. `check_receipt_integrity` reads rows; this reads the
-- catalog, so it holds on an empty database and a later migration cannot
-- quietly undo the guarantee. Same shape as ticket 35's
-- `check_program_isolation()` and ticket 12's `check_state_access()`.
CREATE FUNCTION check_hook_provenance()
RETURNS TABLE (rule text, obj text, detail text)
LANGUAGE sql STABLE AS $$
    -- 1. served agent-lane egress must name a tool run, structurally.
    SELECT 'served_egress_unconstrained', 'receipts',
           'receipts_served_agent_needs_tool_run is missing'
     WHERE NOT EXISTS (SELECT 1 FROM pg_constraint
                        WHERE conname = 'receipts_served_agent_needs_tool_run'
                          AND conrelid = 'receipts'::regclass)

    UNION ALL
    -- 2. the two tables the hook layer writes must emit events. Ticket 07:
    --    completeness is a trigger, not a code convention.
    SELECT 'emitter_missing', t, 'no ENABLE ALWAYS event trigger'
      FROM unnest(ARRAY['tool_runs','receipts','agent_sessions']) t
     WHERE NOT EXISTS (
             SELECT 1 FROM pg_trigger g
              WHERE g.tgrelid = t::regclass
                AND NOT g.tgisinternal
                AND g.tgenabled = 'A'
                AND g.tgfoid = 'emit_event'::regproc)

    UNION ALL
    -- 3. the agent connection may not read or write the correlation table. An
    --    agent that can read `agent_sessions` can read another run's binding;
    --    one that can write it can attribute its own calls.
    SELECT 'agent_touches_correlation', table_name, privilege_type
      FROM information_schema.table_privileges
     WHERE grantee = 'rk2_state'
       AND table_name IN ('agent_sessions','tool_risk_classes','risk_classes')

    UNION ALL
    -- 4. and it may never see an egress credential, by column privilege.
    SELECT 'agent_reads_egress_token', 'tool_runs.egress_token_sha256', privilege_type
      FROM information_schema.column_privileges
     WHERE grantee = 'rk2_state'
       AND table_name = 'tool_runs' AND column_name = 'egress_token_sha256'

    UNION ALL
    -- 5. every risk class named by a tool pattern has a decision.
    SELECT 'tool_pattern_without_class', tool_pattern, risk_class
      FROM tool_risk_classes tc
     WHERE NOT EXISTS (SELECT 1 FROM risk_classes rc
                        WHERE rc.risk_class = tc.risk_class)

    UNION ALL
    -- 6. the fallback must exist and must not be `allow`. An unenumerated tool
    --    that runs unattended is the whole hole this table closes.
    SELECT 'fallback_is_permissive', '*', coalesce(resolve_risk_class('__no_such_tool__'), 'none')
     WHERE coalesce((SELECT decision FROM risk_classes
                      WHERE risk_class = resolve_risk_class('__no_such_tool__')), 'allow')
           = 'allow';
$$;


-- The resume-side half of the guarantee. Ticket 07 established that abort is
-- inferred on the next start; this is what that inference does to receipts that
-- were open when the process died. It does NOT guess whether the tool ran.
CREATE FUNCTION sweep_open_receipts(p_program uuid) RETURNS bigint
LANGUAGE plpgsql AS $$
DECLARE n bigint;
BEGIN
    -- The sweep IS the runtime, and says so. Transaction-local, so it cannot
    -- leak an actor onto whatever else the caller does with this session.
    PERFORM set_actor('runtime');
    WITH swept AS (
        UPDATE tool_runs
           SET status = 'abandoned',
               closed_by = 'sweep',
               finished_at = now(),
               -- the credential dies with the receipt, before anything resumes
               egress_token_sha256 = NULL,
               hook_error = coalesce(hook_error,
                   'receipt was open when the program resumed; whether the tool ran is unknown')
         WHERE program_id = p_program AND status = 'running'
        RETURNING 1)
    SELECT count(*) INTO n FROM swept;
    RETURN n;
END $$;


-- ===========================================================================
-- 8. Resume is one case, not four (the map's abort constraint)
-- ===========================================================================
--
-- Ticket 07's `resume_program()` already unclaims tasks, aborts runs, releases
-- identity leases and returns testing hypotheses. Rate limit, crash, kill and
-- operator stop differ only in what did NOT get written before they happened,
-- so the hook layer's two loose ends belong in the same function rather than in
-- a fifth code path someone has to remember to call:
--
--   * open tool receipts become 'abandoned' and lose their egress token;
--   * session bindings whose agent run is finished are dropped, so a
--     re-delivered hook callback for a dead session resolves to nothing and is
--     denied instead of being attributed to a run that already ended.
CREATE OR REPLACE FUNCTION resume_program(p_program uuid) RETURNS jsonb
LANGUAGE plpgsql AS $$
DECLARE
    n_tasks  bigint;
    n_runs   bigint;
    n_leases bigint;
    n_hyp    bigint;
    n_recs   bigint;
    n_bind   bigint;
BEGIN
    PERFORM set_actor('runtime');

    -- Receipts are swept BEFORE the runs are aborted: `sweep_open_receipts`
    -- keys on status, and an abandoned receipt still has to point at the run
    -- that opened it.
    n_recs := sweep_open_receipts(p_program);

    -- Q29: the ranking is recomputed from current rows, never continued.
    UPDATE tasks SET status = 'pending', claimed_at = NULL, priority = NULL
     WHERE program_id = p_program AND status IN ('claimed','running');
    GET DIAGNOSTICS n_tasks = ROW_COUNT;

    -- a session is not replayed, it is recompiled: the raw result dies unpromoted
    UPDATE agent_runs
       SET finished_at = now(), stop_reason = 'aborted', result = NULL
     WHERE program_id = p_program AND finished_at IS NULL;
    GET DIAGNOSTICS n_runs = ROW_COUNT;

    DELETE FROM agent_sessions s
     WHERE s.program_id = p_program
       AND EXISTS (SELECT 1 FROM agent_runs r
                    WHERE r.id = s.agent_run_id AND r.finished_at IS NOT NULL);
    GET DIAGNOSTICS n_bind = ROW_COUNT;

    UPDATE identity_leases SET released_at = now()
     WHERE program_id = p_program AND released_at IS NULL;
    GET DIAGNOSTICS n_leases = ROW_COUNT;

    -- correction 1 is what makes this legal
    INSERT INTO hypothesis_transitions
        (program_id, hypothesis_id, from_status, to_status, actor_kind, rationale)
    SELECT p_program, h.id, 'testing', 'testable', 'runtime',
           'runtime abort: test did not complete'
      FROM hypotheses h
     WHERE h.program_id = p_program AND h.status = 'testing';
    GET DIAGNOSTICS n_hyp = ROW_COUNT;

    RETURN jsonb_build_object('tasks_unclaimed', n_tasks,
                              'agent_runs_aborted', n_runs,
                              'leases_released', n_leases,
                              'hypotheses_returned_to_testable', n_hyp,
                              'tool_receipts_abandoned', n_recs,
                              'session_bindings_dropped', n_bind);
END $$;


-- ===========================================================================
-- 9. Privileges and RLS for what this migration added
-- ===========================================================================

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO rk2_runtime;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO rk2_runtime;

-- `rk2_state` is granted NOTHING here. Not on `agent_sessions` (the correlation
-- table), not on the risk tables (a policy an agent can read is a policy it can
-- aim at).
--
-- DEFECT IN 020, found by adding a column: ticket 12 granted `SELECT ON ...
-- tool_runs ... TO rk2_state` at TABLE level, and its comment reads "a table
-- absent from this list is unreadable by any handler". True of tables. NOT true
-- of columns: a table-level grant covers every column the table will EVER have,
-- so any later migration that adds a column to one of those 26 tables hands it
-- to the agent connection with no review. This migration adds a credential
-- column to exactly such a table, and the first run of `check_hook_provenance`
-- caught it -- `agent_reads_egress_token: tool_runs.egress_token_sha256
-- (SELECT)`.
--
-- Fixed the way 020 itself already handles `identities`: revoke the table-level
-- grant, re-grant the columns by name. That also flips the default for the
-- future -- a column added to `tool_runs` after this line is invisible to the
-- agent until someone names it, which is the direction a read surface should
-- fail in.
DO $$
DECLARE v_cols text;
BEGIN
    SELECT string_agg(quote_ident(attname), ', ' ORDER BY attnum) INTO v_cols
      FROM pg_attribute
     WHERE attrelid = 'tool_runs'::regclass AND attnum > 0 AND NOT attisdropped
       AND attname <> 'egress_token_sha256';
    EXECUTE 'REVOKE SELECT ON tool_runs FROM rk2_state';
    EXECUTE format('GRANT SELECT (%s) ON tool_runs TO rk2_state', v_cols);
    RAISE NOTICE 'hooks: tool_runs read surface is now column-enumerated for rk2_state';
END $$;
DO $$
DECLARE t text;
BEGIN
    FOR t IN
        SELECT c.relname FROM pg_class c
         WHERE c.relkind = 'r'
           AND c.relnamespace = 'public'::regnamespace
           AND EXISTS (SELECT 1 FROM pg_attribute a
                        WHERE a.attrelid = c.oid AND a.attname = 'program_id'
                          AND a.attnum > 0 AND NOT a.attisdropped)
           AND c.relname NOT IN (SELECT table_name FROM program_global_tables)
           AND NOT c.relrowsecurity
         ORDER BY c.relname
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format(
            'CREATE POLICY %I ON %I AS PERMISSIVE FOR ALL TO rk2_state '
            'USING (program_id = rk2_program()) '
            'WITH CHECK (program_id = rk2_program())', t || '_rk2_state', t);
        EXECUTE format(
            'CREATE POLICY %I ON %I AS PERMISSIVE FOR ALL TO rk2_runtime '
            'USING (true) WITH CHECK (true)', t || '_rk2_runtime', t);
        RAISE NOTICE 'hooks: RLS on %', t;
    END LOOP;
END $$;


-- ===========================================================================
-- 10. The migration refuses to finish unless it holds
-- ===========================================================================

DO $$
DECLARE v text; n bigint;
BEGIN
    SELECT string_agg(problem || ': ' || detail, '; ') INTO v
      FROM check_program_isolation();
    IF v IS NOT NULL THEN
        RAISE EXCEPTION 'ticket 35 isolation broken by 022: %', v;
    END IF;

    SELECT string_agg(rule || ': ' || obj || ' (' || detail || ')', '; ') INTO v
      FROM check_state_access();
    IF v IS NOT NULL THEN
        RAISE EXCEPTION 'ticket 12 state access broken by 022: %', v;
    END IF;

    SELECT string_agg(rule || ': ' || obj || ' (' || detail || ')', '; ') INTO v
      FROM check_hook_provenance();
    IF v IS NOT NULL THEN
        RAISE EXCEPTION 'ticket 13 hook provenance: %', v;
    END IF;

    SELECT count(*) INTO n FROM receipts
     WHERE lane = 'agent' AND decision = 'allowed' AND tool_run_id IS NULL;
    IF n > 0 THEN
        RAISE EXCEPTION 'ticket 13: % served agent-lane receipt(s) name no tool run', n;
    END IF;

    RAISE NOTICE 'hooks: isolation, state access and hook provenance are all silent';
END $$;
