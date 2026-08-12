# 18 — Compile and enforce the six-role roster

**What to build:** Run the production orchestrator, recon, web hunter, JS analyst, validator and deterministic reporter through one closed roster whose declared authority is enforced at every tool call and delegation.

**Blocked by:** 03 — Run production migrations and the integrity gate; 15 — Replay auth-resolution evidence in production.

**Status:** resolved

- [x] One roster compiles role kind, invocation authority, task kinds, model, effort, turns, builtin tools, MCP groups, Skills and concurrency.
- [x] The pre-tool gate denies unattributed calls, unlisted tools, wrong role bindings, built-in agent types, session-role delegation and concurrency overflow.
- [x] The orchestrator has scheduling and state reads but no target network or technique Skill; validator has only its closed judgement surface; reporter runs no model.
- [x] No model-facing tool accepts Program selection, credentials, raw SQL, arbitrary canonical writes or unrestricted process creation.
- [x] Tool visibility and permission mode cannot widen the enforced allowlist, proven through an executed deny canary.
- [x] The roster validates against the observed SDK/CLI tool inventory and fails on unknown, misspelled or newly unclassified builtin tools.

## Comments

Implemented on branch `worktree-bridge-cse_01UqqG8vnWAE2yE3JVCiLqm6` on
2026-08-12.

`src/redkraken/roster.py` is the roster and the gate, in that order, and the
separation between the two halves is the design. The first half is a statement:
six `Role` rows carrying every property that distinguishes one role from
another -- how it runs, who may start it, which task kinds it executes, its
model, effort and turn ceiling, its built-in tools, its capability groups, its
Skills and how many of it may run at once -- plus the capability groups
themselves, a `Contract` for every model-facing tool in them, and the list of
built-in tools no role holds with the reason each is refused. The second half is
`Gate.decide`, which takes one call and returns either nothing or a `Denial`.
Nothing in the module imports the SDK, reads the environment or touches the
network, so the same decision is reachable from a test, from a review and from
the running child, and `tests/test_agent.py` can keep asserting that `_launch`
is the only module that constructs an SDK session.

The reason the gate exists at all, rather than an allowlist in the options
value, is that `ClaudeAgentOptions.allowed_tools` and `AgentDefinition.tools`
narrow what a model is *shown*. This runtime runs at `bypassPermissions`,
where a visible tool is a tool that runs, so visibility is context management
and not a boundary. `Gate.decide` is wired to `PreToolUse` and returns
`permissionDecision: "deny"`, which is the one decision the permission mode
does not overrule.

### The inventory is measured, not written

Criterion 6 asks the roster to validate against "the observed SDK/CLI tool
inventory", and the thing that makes that a real check is that the inventory is
an observation. `tools/probe_tool_inventory.py` runs a real SDK query offline
against `tests.fixtures.ControlUpstream`, stops at the init frame, and requires
two identical observations before it will write anything. Its output is
`src/redkraken/measurements/tool-inventory-sdk-0.2.132-cli-2.1.224.json`,
pinned in `roster.py` by SHA-256: 26 built-in tools, 5 built-in agent types,
the effort and permission-mode vocabularies, and the default model the pair
resolves to. A file that no longer matches its digest is an import error, so
the measurement cannot be quietly edited into agreement with the roster.

What the check buys is specific. `tools=["Nonexistent"]` was measured to
produce an empty tool list rather than an error, so a typo in a grant is a role
silently missing a capability, and a typo in a *prohibition* is worse -- it
reads as a closed door and is a door that was never in the wall. The compile
therefore requires the partition to be exact in both directions: granted and
forbidden are disjoint, their union is a subset of the observed inventory, and
every observed tool is in one of them. A CLI upgrade that adds a tool is a
roster that has not classified it, and this refuses to start rather than
defaulting the new tool either way.

The same measurement is what the roster's `model` and `effort` values are
checked against: `opus` was observed to resolve to `claude-opus-5`, and the
five effort levels are the ones the SDK actually accepts.

### Two divergences from the prototype roster, and why

The prototype roster -- `prototype/agent-roster/roles.yaml`, which lived in the
tree until the documentation consolidation and is still readable at `2fc3354`
-- granted `Bash` and `Read` to the hunting roles and `Read` to the analyst.
This roster forbids both, to every role.

*`Bash`* is arbitrary process creation, which criterion 4 names directly. The
enumerated form that replaces it is `mcp__rk2__run_tool`, whose `tool` argument
is an enum of six binaries rather than a name -- an open binary name is an open
allowlist, and an open allowlist on a tool that starts a process is the thing
the criterion prohibits.

*`Read`* takes a path, and the paths inside an Agent container include the
child's own home. The credential the harness mounts there, the settings
document the launch writes, and the Skills the roster grants are all files a
role with `Read` could read. Its legitimate use -- looking at a downloaded
artifact -- is served by `mcp__rk2__get_artifact`, which takes a content hash
and no path.

### The gate's rules, and what each is for

Eight, each with an identifier a denial carries so an operator learns which
property was violated and not merely that one was. `R-ROLE` for a call the
runtime cannot attribute to exactly one role -- an `agent_id` without an
`agent_type` or the reverse, or a type that is not a role this runtime
delegates to. `R-AGENTID` for an identity that was started as one role and
later calls as another, checked against what `SubagentStart` recorded rather
than against what the call claims. `R-TOOL` for a tool the attributed role does
not hold. `R-AGENTTYPE` for a delegation to something that is not a roster role
-- which is where the pair's own five agent types land -- or to a role this
role may not start. `R-SESSIONROLE` for delegating to a role the runtime starts
itself. `R-CAP` for a delegation past the target's ceiling or the session's.
`R-PROGRAM` for an argument named after program selection, a credential or raw
SQL, at any depth up to eight. `R-SKILL` for a Skill the role was not granted.

Two of those need the other three hook events to be honest, which is why the
launch registers four rather than one. `SubagentStart` is what turns `agent_id`
into an attribution instead of a claim. `PostToolUse` and `PostToolUseFailure`
give an admitted delegation its slot back, so the concurrency ceiling is a
ceiling on what is running rather than on what has ever run. `agent.assess`
refuses a launch whose options value does not register all four with an
unnarrowed matcher: a gate some calls do not reach is not a gate.

### The deny canary

Criterion 5 is met by a run rather than an argument.
`ContainedChildTest.test_a_tool_the_child_can_see_and_run_is_still_refused_by_the_gate`
starts a real child in the real container boundary, against a scripted model
API that is a container peer, and everything that would let the call through is
deliberately left open: `Task` is in the role's own `tools`, so the model sees
it and the CLI will dispatch it; the permission mode is `bypassPermissions`, so
no prompt and no allowlist is consulted; and the `subagent_type` is `Explore`,
an agent type the pair genuinely ships and could start. The run comes back with
one denial -- `R-AGENTTYPE` on `Task` -- an empty `tools_served`, and a finished
turn, so what is asserted is a refused call inside a live session rather than a
session that failed to start. `AgentRunResult.denials` carries the records out,
so a run's evidence distinguishes "the model did not ask" from "the model asked
and was refused".

One thing that run taught: the CLI validates a tool's input against its schema
*before* the hook fires. A `Task` call missing `description` is rejected
upstream of the gate and produces a run with no denial in it, which looked at
first like a hook that never ran. The canary therefore sends a complete call,
and the note is in the test, because the next person to script one will hit the
same thing.

### The roles

`orchestrator` runs as a session, holds `Task`, `state.read` and
`sched.commit`, and has no `net.request`, no `exec.tool_run` and no `Skill` --
it picks tasks and never holds one, which migration 0019 says the same way with
an empty `role_task_kinds`. `recon`, `web_hunter` and `js_analyst` are
subagents reachable only through delegation, each holding one task kind,
`Skill` with a named grant list, and `state.propose`; `js_analyst` has no
`net.request`, because an analyst that fetches is a hunter with the wrong
quota. `validator` runs as a session with no built-in tool at all and exactly
`validate.judge` -- the packet is its whole world, and its channel in takes one
finding label, so there is no field on its surface a hunter's sentence would
fit in. `reporter` is a `renderer`: no model, no effort, no turn, no tool.

Two invariants run across them and are compile checks rather than comments. No
role holds both `state.propose` and `sched.commit`, so nothing promotes its own
proposals; and no role that executes a task holds `sched.commit`, so scheduling
authority stays with the one role that never holds a task.

### Verification

`tests/test_roster.py` is 53 tests. The compile rules are tested by breaking
exactly the property each rule is about and recompiling -- a hand-written
roster in the test would be a second roster, and a rule that passed on it would
say nothing about the first. Every gate rule has its own test, criteria 3 and 4
are stated as assertions over the compiled roster, and the concurrency rules
are exercised in both directions including the release path. `tests/test_agent.py`
is 51 tests and carries the canary.

The full suite is 725 tests: one failure and one error, both pre-existing and
environmental, identical on a clean tree at `876a486` -- `test_identity` and
`test_proxy` need a platform that loads a client key without a plaintext file,
which the uv CPython builds on this machine are not.
`tools/check_baseline.py` reports `classifications=10 regressions=7
artifacts=223`. With `RK_TEST_CONTAINERS=1` the `ContainedChildTest` group is
four tests green.

### Three limitations, stated rather than worked around

*The gate cannot see a credential in a header value.* `R-PROGRAM` matches
argument *names*, so `mcp__rk2__http_request` with
`headers: {"Authorization": "..."}` is denied, but a bearer token spelled into
a header the roster does not name is a value, and no name-based rule reaches
it. The enforcement point for that is the capability proxy, which is the only
thing that sees the request as bytes; tickets 12 and 35 own it.

*The contracts describe tools that do not exist yet.* `TOOL_GROUPS` and
`CONTRACTS` fix which class of capability a role may hold and what shape each
tool's arguments have. Ticket 19 builds the handlers behind those names. The
one served today is `mcp__rk2__ready`, which is why `runtime.ready` is a group:
`allowed_tools` is computed as the role's grants intersected with what the
launch actually serves, so a tool nobody serves is not an allowlist entry that
can never be exercised, and the intersection shrinks to nothing rather than
lying when ticket 19 lands.

*Nothing in `src/` starts a role other than the orchestrator yet.* The roster
states all six and the gate enforces all six, but `agent.agent_run` is the only
caller and ticket 20 is what gives it a task to run. The validator and reporter
rows are enforced today only in the sense that a launch naming them is assessed
against them -- and a launch naming `reporter` is refused outright, because a
renderer is not a thing this runtime starts a model for.

### One thing the CLI spells two ways

The pair announces the delegation tool as `Task` in its init frame and has been
observed to name the same tool `Agent` when it reports a denial. The gate
resolves the alias before deciding, rather than holding an allowlist that half
the CLI's spellings miss, and the compile checks that the alias resolves to an
observed tool and that the alias itself is *not* separately served -- otherwise
`Agent` would be a tool in its own right and the resolution would be hiding it.
