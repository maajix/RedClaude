# 119 — Nothing records a session or a hook identity

**What to build:** A decision about migration 022's hook-provenance design,
which is declared in three places and written by nobody, and then either the
writer that fills it or the migration that removes it.

**Blocked by:** nothing.

**Status:** needs-triage

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
