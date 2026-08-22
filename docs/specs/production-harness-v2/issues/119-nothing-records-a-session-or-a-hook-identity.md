# 119 — Nothing records a session or a hook identity

**What to build:** A decision about migration 022's hook-provenance design,
which is declared in three places and written by nobody, and then either the
writer that fills it or the migration that removes it.

**Blocked by:** nothing.

**Status:** ready-for-agent

- [ ] The state of the design is written down before anything moves. 022 adds
      seven hook-identity columns to `tool_runs`
      (`0022_hooks_and_receipts.sql:187-218`: `tool_use_id`, `session_id`,
      `sdk_agent_id`, `sdk_agent_type`, `mcp_server`, `args_sha256`,
      `result_sha256`, alongside `transport`), and creates `agent_sessions`
      (`:151-175`) to carry the SDK session a run was bound to. Neither has a
      writer.
- [ ] The mechanism by which they became unreachable is stated, because it is
      not simply an omission. `0022:235` adds
      `tool_runs_hook_identity_ck CHECK ((transport = 'runtime') = (tool_use_id
      IS NULL))`, and every writer of `tool_runs` passes the literal
      `'runtime'`: `src/redkraken/execution.py:355-359`,
      `src/redkraken/proxy.py:3647-3651` (`OPEN_TOOL_RUN`),
      and the seven SQL openers
      (`20260814T030000Z...:688`, `20260814T040000Z...:979`,
      `20260814T050000Z...:661`, `20260815T000000Z...:1268`,
      `20260816T000000Z...:834`, `20260922T030000Z...:373`,
      `20260923T000000Z...:378`). So `transport IN ('builtin','mcp')` is
      unreachable, the check then forces `tool_use_id` NULL, and
      `tool_runs_tool_use_id_uq` (`0022:254`) -- the SDK idempotency key, whose whole purpose
      is that a re-delivered hook callback cannot open a second receipt --
      indexes a column that is always NULL.
- [ ] The hook layer that exists is described as what it is. `gate_hooks`
      (`src/redkraken/_launch.py:968`) registers all four of
      `agent.GATE_EVENTS` (`src/redkraken/agent.py:98`) and has both the
      `tool_use_id` and the delegated `agent_id`/`agent_type` in hand in its
      `before`, `started` and `finished` callbacks. It passes them to an in-process `roster.Gate` and
      writes none of them anywhere. The decision the gate takes is real and is
      not recorded, which is the same defect 022's own prose says it exists to
      prevent: "a hook-layer table outside the event log is the exact thing this
      ticket exists to prevent" (`0022:149-150`).
- [ ] The cost on the `agent_sessions` side is named. Eight SQL statements
      `UPDATE agent_sessions SET unbound_at` (`0041_refusal_lifecycle.sql:49`,
      `20260813T190000Z...:456`, `20260814T020000Z...:286`,
      `20260816T000000Z...:1410`, `20260913T000000Z...:403` among them) and
      three views compute over the table (`orchestrator_session_usage`,
      `lane_budget`, `program_capacity`), two of which `capsule.py` and
      `panels.py` read. With no row ever inserted,
      `orchestrator_session_usage` is permanently empty, so the orchestrator
      rotation ceiling that `check_orchestrator_rotation`,
      `open_orchestrator_session` and `orchestrator_session_spent` all consult
      is never reached by anything, and arms 2 and 3 of
      `check_hook_provenance` (`0022:487`) assert over a table with no rows.
- [ ] Whichever way the decision goes, the agent's read surface follows it.
      Seven `tool_runs` hook columns are granted to `rk2_state` and are always
      NULL; `v_records` publishes `mcp_server`, `args_sha256` and
      `result_sha256` as `null` on every row. If the design is deferred, those
      grants come off with it, because a granted always-NULL column tells the
      model the harness knows something it does not.
- [ ] `agent_runs.parent_run_id` is decided in the same pass. It has an FK, no
      writer and no reader: the subagent parent edge is never recorded, and
      `gate_hooks`'s `SubagentStart` callback is exactly where it would be.

## Why

`docs/research/wiring/23-database-wiring.md` section 1.3(b) grades the block
"structurally unreachable" and section 3.1 grades `agent_sessions`
load-bearing. They are one design: the SDK reports what it ran, the harness
records it as a receipt, and the session ceiling is enforced against rows that
exist.

This is `needs-triage` because both answers are large. Filling it means the hook
callbacks acquire a database connection and a write path, which is a change to
what runs inside the child process. Removing it means dropping columns that
several checks and three views are written against. Neither is a
change a single agent should pick on its own, and the present state -- declared,
constrained, granted, indexed, empty -- is the one state that is definitely
wrong.

## The decision, taken 2026-08-22

**022 is not one design, it is two, and they get opposite answers. The session
binding is built: it is the missing half of a lifecycle whose other half already
ships in eleven statements. The hook-side receipt is deferred, with the reason
written into the migration that defers it, and its always-NULL columns come off
the agent's read surface. `agent_runs.parent_run_id` goes with the deferred
half, because it has nothing to point at until that half exists.**

### Build the binding

The unbind side is finished and the bind side was never written. Eleven
statements retire a binding that is never made: eight `UPDATE agent_sessions SET
unbound_at` (`0041_refusal_lifecycle.sql:49`,
`20260814T020000Z...:286`, `20260816T000000Z...:1410` among them) and three
`DELETE FROM agent_sessions` (`0022_hooks_and_receipts.sql:610`,
`0026_human_control.sql:774` and `:896`). `0030_corpus_corrections.sql:183` even
records the rule the deletes were later corrected into -- "Set instead of
deleting the row: the row is the subject of a `session.bound` event, and deleting
it orphans the event." The supervisor's own prose is written as though the row
exists: `src/redkraken/agent.py:222-225` lists "the session binding" among the
five things one refusal cleanup closes, and `agent.py:665-667` says a finishing
run "releases its Task and Identity Leases, **unbinds its session** and emits the
one redacted `startup.refused` Event". Every one of those is a no-op today.

**The write is small and it is on a path that already parses the message it
needs.** `_corroborate` (`src/redkraken/_launch.py`, at the time of writing
`:1491-1514`) already blocks on the SDK's init `SystemMessage` and reads one key
out of `message.data` -- `apiKeySource` at `:1508`. The session id is a sibling
key on that same dict. The child holds no database connection, so the row is
written by the supervisor, and the transport for that is the one ticket 102 just
proved is extensible: `Channel.call` writes one JSON line and blocks on one back
(`_launch.py:399-467`), and `agent._Tools.__call__` is a closed dispatch on
`verb` that answers `unknown_call` for anything else and that ticket 102 grew a
third arm on. One `bind_session` verb sent once, immediately after
`_corroborate` returns, is the whole of it.

**Rejected: dropping `agent_sessions`.** It would mean deleting eleven live
statements, the event registration (`0022:346`, `:368`), the live-binding partial
index (`0030:...agent_sessions_live_binding_idx`) and two catalogue assertions,
in order to avoid writing one row per run.

### Defer the hook receipt

The hook half is not merely unimplemented; it specifies a gate this harness
decided to place elsewhere, and filling it now would produce two receipts for one
call.

022's premise is a hook that consults the database: "A tool call from an unbound
(session, agent) pair is a call the runtime cannot attribute, and **the hook
denies it** -- that is the whole reason this table exists" (`0022:139-142`). That
gate shipped in-process instead. `roster.Gate` decides inside the child
(`_launch.gate_hooks`, at the time of writing `:1130-1177`, registering all four
of `agent.GATE_EVENTS` at `src/redkraken/agent.py:98`), and it decides without a
round trip because it is on the critical path of every single tool call. Moving
that decision back into the database means a synchronous `Channel.call` inside
`PreToolUse`, which is a change to what runs inside the child process on every
call, not a new column.

And the receipt would collide with a receipt that already exists. The runtime
opens a `tool_runs` row itself for the work it serves -- `OPEN_TOOL_RUN` in
`src/redkraken/execution.py` (at the time of writing `:416-418`) and in
`src/redkraken/proxy.py:3647-3651`, both passing the literal `'runtime'`. A hook
firing on that same MCP call would open a second row with `transport = 'mcp'` and
a `tool_use_id`. `tool_runs_hook_identity_ck` (`0022:233-235`) partitions the two
kinds of row; it does not say whether a served call is supposed to produce one row
or two, and 022's prose never answers that either. **That unanswered question is
what makes this a deferral rather than a task**, and the deferring migration
should say it in one sentence so the next reader does not re-derive it.

**The read surface follows the deferral now, not later.** Seven hook columns
reach `rk2_state` by construction rather than by enumeration: `0022:664-672`
computes the column list as every attribute of `tool_runs` except
`egress_token_sha256` and grants that. So removing them is a change from "all but
one" to a written-out list, and it is worth doing on its own merits -- ticket 129
measured `tool_runs` as one of the twenty-seven relations on the agent surface
that no tool reads at all, so today the grant is unused twice over. The
`v_records` payload publishing `mcp_server`, `args_sha256` and `result_sha256` as
`null` on every row goes with it.

### `parent_run_id` is part of the deferred half

`grep -rn "INSERT INTO agent_runs" src/` returns **nine** statements and none of
them sets it. That is not an omission that a writer could close on its own:
`agent_runs.role` is closed to the six roster roles (`0006_tasks_and_runs.sql:39-40`),
an SDK subagent is not one of them, and so a delegated agent has no `agent_runs`
row to be the child of. The column can only be filled by the same design that
opens a receipt per hook event, and it is deferred with it. `0017_program_isolation.sql:215`
already names it as one of the columns the isolation check skips, so nothing
breaks by leaving it NULL and nothing is gained by dropping it.

## What was measured

Every `agent_sessions` reference in the migration corpus was read. There is **no
`INSERT INTO agent_sessions` anywhere in `src/`**. Eight `UPDATE agent_sessions
SET unbound_at` and three `DELETE FROM agent_sessions`. Six statements read the
table, all of them those same cleanup writers plus 022's own assertions. Nine
`INSERT INTO agent_runs`, zero setting `parent_run_id`.

## Correction: none of the three views computes over `agent_sessions`

The ticket's fourth criterion says "three views compute over the table
(`orchestrator_session_usage`, `lane_budget`, `program_capacity`) ... With no row
ever inserted, `orchestrator_session_usage` is permanently empty, so the
orchestrator rotation ceiling that `check_orchestrator_rotation`,
`open_orchestrator_session` and `orchestrator_session_spent` all consult is never
reached by anything." **This is a conflation of two different tables and it is
wrong in every part.** `orchestrator_session_usage`
(`20260814T010000Z__rotate_the_orchestrator_and_resume.sql:210-238`) computes over
`orchestrator_sessions`, `agent_runs` and `events` -- a table that is written on
every planning pass, by `open_orchestrator_session` itself
(`20260814T010000Z...:392-398`), which `execution.py:169` calls as `OPEN_SESSION`.
`lane_budget` and `program_capacity`
(`20260813T230000Z__reserve_the_worst_case_and_reconcile_it.sql`) read `programs`,
`agent_runs`, `budget_reservations` and `scheduler_lanes`. None of the three
mentions `agent_sessions`. **The rotation ceiling is enforced today**, and the
cost of the missing binding is smaller than the ticket claims -- which is worth
knowing, because it is what makes deferring the hook half affordable.

## Correction: `check_hook_provenance` is deliberately row-free

The same criterion says "arms 2 and 3 of `check_hook_provenance` (`0022:487`)
assert over a table with no rows". They do not, and by design. The function's own
header is explicit (`0022:482-486`): "The static half. `check_receipt_integrity`
reads rows; **this reads the catalog, so it holds on an empty database** and a
later migration cannot quietly undo the guarantee." Arm 2 reads `pg_trigger` for
an `ENABLE ALWAYS` emitter; arm 3 reads `information_schema.table_privileges` for
a grant that must not exist. Both pass today and both go on passing whichever way
this ticket is decided. Nothing in `check_hook_provenance` is evidence for the
defect.

## Correction: three cited line numbers have moved, and one name collides

`gate_hooks` is at `src/redkraken/_launch.py:1130`, not `:968`; the `tool_runs`
opener in `execution.py` is `OPEN_TOOL_RUN` at `:416-418`, not `:355-359`. Both
files are under concurrent edit, so an implementer should grep for the symbol
rather than trust either number. And `bind_agent_session` already exists in this
tree at `src/redkraken/state.py:338` meaning something else entirely -- it binds a
**Postgres** session to a Program with `set_config('rk2.program_id', ...)` -- so
the verb that binds an **SDK** session must not be given that name.
