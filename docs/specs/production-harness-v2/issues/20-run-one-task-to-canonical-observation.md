# 20 — Run one Task to a canonical Observation

**What to build:** Make `rk run` execute one seeded Task through a real Agent run and network Tool run, then promote one grounded Observation and close every lifecycle row correctly.

**Blocked by:** 17 — Refuse every startup vector fatally and durably; 19 — Serve bounded MCP reads and Mission proposals.

**Status:** resolved

- [x] `rk run` claims one ready Task, starts one allowed role with a bounded Mission packet and serves one capability-backed target request.
- [x] The proxy Receipt, response Artifact, Tool run, Agent run, Task attempt and Mission proposal share the correct Program and causal identifiers.
- [x] Runtime promotion verifies provenance and creates exactly one immutable canonical Observation in one transaction with its Event.
- [x] Agent completion prose cannot close the Task until the runtime has accepted the structured result and reconciled execution.
- [x] Success leaves no live capability, open Tool run, open Agent run or unreleased Lease; failure and restart reconcile idempotently.
- [x] Running the slice twice from identical clean state yields the same decisions and relationships while generating only expected new run identifiers.

## Comments

Implemented on branch `worktree-bridge-cse_01UqqG8vnWAE2yE3JVCiLqm6` on
2026-08-12.

One new module, `execution.py`, and one migration. The module is the first
thing in the harness that is a *sequence*: everything before it answered a
question the caller asked, and this asks eleven of its own in order --- rank,
quota, offer, claim, read back, compile, mint, start, stage, promote, close.
So the shape is a ledger the whole way down. Every step holds or fails on the
same `Ledger` the CLI already prints, nothing raises past `attempt`, and the
closing runs in a `finally` because the one thing worse than a step failing is
a step failing with a capability still resolvable.

### The database decides what happened, not the runtime

`finish_task_attempt` settles the Task, and it settles it from what was
promoted rather than from what the runtime hoped for. That is the fourth
criterion, and it is a trigger and not a convention: `enforce_task_completion`
is `BEFORE UPDATE ... ENABLE ALWAYS` on `tasks`, so a Task cannot move to
`done` unless a proposal of it is `promoted` --- including by a superuser
session, including by a future runtime that decides it knows better. The
runtime's own report is the function's answer, which is why `_finish` returns
`closure` rather than a status this process assembled.

Promotion is the same idea one layer down. `promote_proposal` resolves each
staged element against the canonical tables it is about to become a row in,
which is the only place four of the twelve refusal reasons become provable ---
`no_subject`, `subject_not_of_program`, `receipt_not_of_subject`,
`already_canonical`. An element that fails one is refused individually and the
rest still promote, because a Mission that got three of four Observations
right is worth three Observations.

### Closing is revocation

`guard_tool_run_authorization` (038) clears `egress_token_sha256` on any update
that leaves `running`. That makes closing a Tool run the act that revokes its
capability, and it fixes an ordering: Tool runs close before the Agent run, in
`finish_task_attempt` and in the slice's own `_close`. A run that ended while a
capability of its own still resolved is exactly the leak criterion 5 names, and
`check_execution_closure` reports it as a row --- `live_capability_after_close`
--- rather than trusting the ordering to stay written.

Five row arms, not four. The four the criterion lists, plus
`open_agent_run_on_settled_task`: a Task can settle by a path that never
reached this closing (the lease sweep, an operator), and the run left behind is
a leak the other four cannot see. Two structural arms sit beside them, because
the first arm is only meaningful while the trigger is attached and the
promotion is only atomic while `observations` is a row-event table --- a check
whose subject had been detached would report nothing and mean nothing.

### The child is handed one capability and cannot mint another

`mcp__rk2__http_request` is served to the child; `authorize_tool_run` is not.
The capability is minted before the container starts, against a Tool run that
already names the Task, and the child's timeout is the smaller of the runtime
ceiling and what the capability has left --- a child outliving its own
capability would spend the rest of its turn being refused at the door.

Which makes the role check two questions rather than one. The launcher's rule
first (`roster.ROLES[role]` is known, unrendered, and has tools in the served
groups), then this slice's own: the role must hold `net.request`. `js_analyst`
passes the first and fails the second, deliberately --- it is startable and it
may not make requests, so an attempt that handed it the one capability this
slice mints would have minted something nothing it may call could spend.

### Two vocabularies for one word

`ResultMessage.stop_reason` speaks `end_turn`, `max_tokens`, `tool_use`,
`pause_turn`, `refusal`. `agent_runs.stop_reason` accepts `completed`,
`stop_condition`, `budget`, `refusal`, `error`, `aborted`, `parked`. Only
`refusal` is in both. `stopped_as` is the map between them, and it exists
because an unmapped word does not fail the statement that writes it --- it
fails the whole closing transaction, which is the one transaction that had to
run. Anything from neither vocabulary is recorded as `error`, which is the
honest reading of a child that stopped for a reason this runtime cannot name.

### What the review changed

The two-axis review ran against `main` and produced findings in both axes.
Applied: the duplicated `jsonb` decode is now one public `proxy.as_object`
rather than a copy in each module; `requested()` no longer treats
`RK_PROXY_CA_FILE` as a claim to a boundary, because `rk send --ca` falls back
to it and an operator who exported it to talk to the fence by hand has said
nothing about running children; the three `_close`-shaped blocks in `_run`,
`_authorize` and `_unauthorized` are one method; the inert `set_cause` before
staging is gone, since 0030 files `proposals` as an audit table and the write
emits no Event for a cause to name; and `finish_task_attempt` now raises on a
missing active `scheduler_weights` row, as 023's ranking pass does --- the row
is read for `attempts >= w.max_attempts`, and a missing one makes that NULL,
which is not an error but a false, and the Task would return to the queue after
every attempt forever with nothing saying why.

Two findings are rejected. Starting `recon`, `web_hunter` and `js_analyst` as
isolated children does not violate the roster: `tests/test_agent.py` asserts
those three and `orchestrator` launch and that `reporter` and `validator` are
refused, which is the rule this slice now asks in full. And
`mcp__rk2__http_request` beside `proxy.TOOL = "mcp__rk2__net_request"` is not an
inconsistency --- the first is the MCP tool served to the child, the second is
the `tool_runs.tool` value the gate rules match on.

One thing fixed in passing. `test_repeating_every_read_leaves_the_database_and_
the_leases_alone` compared `pg_database_size` across its own window, and
autovacuum reached the database mid-test during a full-module run and grew it
by twelve pages while every digest stayed identical. The size was also the one
column in that snapshot that could not have caught the write it was there to
catch, since a single row does not move a page count. The rows are compared
exactly; the size is only asserted not to shrink.
