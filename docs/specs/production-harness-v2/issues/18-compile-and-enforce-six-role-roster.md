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
checked against. The effort levels are the five the SDK's own type declares. The
model is the one measurement that had to be added during review: the probe now
starts a child per alias and records what the init frame says it resolved to --
`opus` to `claude-opus-5`, `sonnet` to `claude-sonnet-5`, `haiku` to
`claude-haiku-4-5-20251001` -- because what a role names is a request and what
it runs is the resolution, and a role naming an alias this pair does not know
would still start, on some other model, without saying which.

### Two divergences from the prototype roster, and why

The prototype roster -- `prototype/agent-roster/roles.yaml`, which lived in the
tree until the documentation consolidation and is still readable at `2fc3354`
-- granted `Bash` and `Read` to the hunting roles and `Read` to the analyst.
This roster forbids both, to every role.

*`Bash`* is arbitrary process creation, which criterion 4 names directly. The
enumerated form that replaces it is `mcp__rk2__run_tool`, whose `tool` argument
is an enum of six binaries rather than a name -- an open binary name is an
unbounded set of programs, and an unbounded set on a tool that starts a process
is the thing the criterion prohibits. The enum is enforced at the gate, not
described there: `R-ARGVALUE` refuses a call that does not fit its contract.

*`Read`* takes a path, and the paths inside an Agent container include the
child's own home. The credential the harness mounts there, the settings
document the launch writes, and the Skills the roster grants are all files a
role with `Read` could read. Its legitimate use -- looking at a downloaded
artifact -- is served by `mcp__rk2__get_artifact`, which takes a label and no
path. (It took a content hash when this was written; ticket 19 moved it to a
label, because a hash is a key the caller can construct for bytes it was never
told about. The argument here is unaffected: neither shape takes a path.)

### The gate's rules, and what each is for

Nine, each with an identifier a denial carries so an operator learns which
property was violated and not merely that one was. `R-ROLE` for a call the
runtime cannot attribute to exactly one role -- an `agent_id` without an
`agent_type` or the reverse, a type that is not a role this runtime delegates
to, or an identity the runtime never saw start. `R-AGENTID` for an identity that
was started as one role and later calls as another, checked against what
`SubagentStart` recorded rather than against what the call claims. `R-TOOL` for
a tool the attributed role does not hold. `R-AGENTTYPE` for a delegation to
something that is not a roster role -- which is where the pair's own five agent
types land -- or to a role this role may not start. `R-SESSIONROLE` for
delegating to a role the runtime starts itself. `R-CAP` for a delegation past
the target's ceiling or the session's. `R-ARGNAME` for an argument named after
program selection, a credential or raw SQL, at any depth up to eight.
`R-ARGVALUE` for a call that does not fit its tool's contract -- an argument the
contract does not declare, a required one missing, a value of the wrong shape,
outside an enum, off a pattern or out of bounds. `R-SKILL` for a Skill the role
was not granted.

The third of those is fail-closed on purpose. A delegated call whose `agent_id`
carries no `SubagentStart` record is refused rather than believed: an
attribution the runtime did not witness is a claim, and a hook this runtime
stopped receiving should close the gate rather than open it. Nothing in `src/`
delegates yet, so the cost of that choice today is zero and the property is in
place before the first caller.

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

`orchestrator` runs as a session, holds `Task`, `state.read` and `sched.pick`,
and has no `net.request`, no `exec.tool_run` and no `Skill` -- it picks tasks
and never holds one, which migration 0019 says the same way with an empty
`role_task_kinds`. `recon`, `web_hunter` and `js_analyst` are subagents
reachable only through delegation, each holding one task kind, `Skill` with a
named skill list, and `state.propose`; `js_analyst` has no `net.request`,
because an analyst that fetches is a hunter with the wrong quota. `validator`
runs as a session with no built-in tool at all and exactly `validate.judge` --
the packet is its whole world, and its channel in takes one finding label, so
there is no field on its surface a hunter's sentence would fit in. `reporter` is
a `renderer`: no model, no effort, no turn, no tool.

Two invariants run across them and are compile checks rather than comments. No
role holds both `state.propose` and `sched.pick`, so nothing schedules the work
its own results justify; and no role that executes a task holds `sched.pick`, so
the choosing stays with the one role that never holds a task.

The six rows are the schema's rows. `tests/test_roster.py` reads migration
0019's `INSERT` statements as text and holds this file to them field by field --
`runs_as`, `invocable_by`, `executes_tasks`, `max_concurrent`,
`clamp_to_identity_leases` and the whole role-to-kind mapping -- because the
migration is generated from a roster and two documents that drift apart are a
scheduler admitting a role this file would refuse. That check found one: the
roster had `web_hunter`'s identity-lease clamp as a comment where 0019 has it as
a column, and it is a field now.

### Verification

`tests/test_roster.py` is 67 tests. The compile rules are tested by breaking
exactly the property each rule is about and recompiling -- a hand-written
roster in the test would be a second roster, and a rule that passed on it would
say nothing about the first. Every gate rule has its own test, criteria 3 and 4
are stated as assertions over the compiled roster, the concurrency rules are
exercised in both directions including the release path, and the six rows are
read back off migration 0019. `tests/test_agent.py` is 52 tests and carries the
canary.

The full suite is 739 tests: one failure and one error, both pre-existing and
environmental, identical on a clean tree at `876a486` -- `test_identity` and
`test_proxy` need a platform that loads a client key without a plaintext file,
which the uv CPython builds on this machine are not.
`tools/check_baseline.py` reports `classifications=10 regressions=7
artifacts=223`. With `RK_TEST_CONTAINERS=1` the `ContainedChildTest` group is
four tests green.

### Three limitations, stated rather than worked around

*The gate cannot see a credential in a header value.* `R-ARGNAME` matches
argument *names* and `R-ARGVALUE` matches a header's *name* against the shape
the contract bounds it to, so `mcp__rk2__http_request` with
`headers: {"Authorization": "..."}` is denied, but a bearer token spelled into
a header the roster does not name is a value in a well-named field, and no rule
here reaches it. The enforcement point for that is the capability proxy, which
is the only thing that sees the request as bytes; tickets 12 and 35 own it.

*The contracts describe tools that do not exist yet.* `TOOL_GROUPS` and
`CONTRACTS` fix which class of tool a role may hold and what shape each tool's
arguments have, and the gate already enforces the argument shapes -- so when
ticket 19 builds the handlers, the handler's own validation is a second line
rather than the only one. The one tool served today is `mcp__rk2__ready`, which
is why `runtime.ready` is a group: the enforced list is the role's tools
intersected with what the launch actually serves, so a tool nobody serves is not
an entry that can never be exercised, and the intersection shrinks to nothing
rather than lying when ticket 19 lands.

*Nothing in `src/` starts a role other than the orchestrator yet.* The roster
states all six and the gate enforces all six, but `agent.agent_run` is the only
caller and ticket 20 is what gives it a task to run. The validator and reporter
rows are enforced today only in the sense that a launch naming them is assessed
against them -- and a launch naming `reporter` is refused outright, because a
renderer is not a thing this runtime starts a model for.

### One thing the CLI spells two ways

The pair announces the delegation tool as `Task` in its init frame and has been
observed to name the same tool `Agent` when it reports a denial. The gate
resolves the alias before deciding, rather than holding a list that half the
CLI's spellings miss, and the compile checks that the alias resolves to an
observed tool and that the alias itself is *not* separately served -- otherwise
`Agent` would be a tool in its own right and the resolution would be hiding it.

### What the review axes changed

The Spec axis found the roster had given the model a verb the spec reserves for
the runtime. `sched.commit` held `mcp__rk2__promote` and `mcp__rk2__claim_task`,
which reads against three independent statements of the same rule: spec.md's
"the runtime alone claims Tasks, promotes proposals", ADR-0003, and CONTEXT.md's
**Promotion** -- "the runtime step that turns an agent's raw result into
canonical rows. Nothing an agent returns is true before it." The group is
`sched.pick` now, `promote` is gone rather than narrowed, and `claim_task` is
`pick_task`, which writes the orchestrator's choice and leaves the claim
transaction where **Slate** puts it: "the runtime decides what may be chosen;
the orchestrator decides which; the runtime commits the claim." A compile rule
holds the line -- no contract may write a canonical table at all, and `verdicts`
is writable only under the `judge` direction, which is the validator's own
output row rather than an edit to the Finding it is about.

The Standards axis found four things worth fixing. `Argument.kind` and
`required` were declared and never read, so the contracts were documentation
that looked like enforcement; the gate validates a call against its contract now
and `R-ARGVALUE` is the rule. Two module-level functions, `visible_tools(role)`
and `allowed_tools(role, served)`, took a role name only to look the role up
again -- they are `Role.visible_tools` and `Role.allowed_tools(served)`, on the
data they were envious of. The impersonation denial was built twice, in `bind`
and in `_caller`, with two wordings and two answers for the `role` field; it is
one `_impersonation` builder. And `_admit` keyed a ticketless delegation by the
current outstanding count, so an admission either side of a release could take a
released key and two running hunters would be counted as one -- it is a
monotonic counter now, with a test that admits across a release.

Both axes reached the same missing measurement from different directions, and it
is the probe change described above: the ticket claimed `opus` resolves to
`claude-opus-5` and nothing had observed it.

Three findings were drift between this roster and the scheduler that will read
it, which is code neither this ticket nor its blockers own, and they are filed
rather than fixed here. Ticket 71: `claim_task()` writes `claude-opus-5` and
`high` for every non-renderer role, where the roster says `medium` for `recon`,
`xhigh` for the orchestrator and `max` for the validator -- and the model string
is a literal copy of a value the measured manifest is version-bound to. Ticket
72: the identity-lease clamp is enforced only for a Task that names a
hypothesis, so a hunt Task without one starts leaseless, and
`effective_lane_capacity` publishes the flag without bounding anything by it.
Ticket 73: the cross-role subagent cap is written twice, as
`roster.GLOBAL_SUBAGENTS` and as `scheduler_weights.max_concurrent_subagents`,
equal today only because both are 3.
