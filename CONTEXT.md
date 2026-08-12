# redKrakenV2

An autonomous bug-bounty hunting harness for web and API targets. The vocabulary
below is the ubiquitous language of the whole system: the same words name the
tables, the MCP tools, and the things agents are told about.

## Surface

**Program**:
A bounty engagement with one scope policy and one lifecycle. The root of every
other record; nothing exists outside a program.
_Avoid_: Bounty, engagement, target (target is a kind of entity, not the program)

**Entity**:
A node in the attack surface — a Domain, Host, Service, Application, Endpoint,
Parameter, Technology, or Identity. Entities have identity and history; they are
discovered, not created.
_Avoid_: Asset, node, object

**Relationship**:
A typed, directed edge between two entities that is not a containment
(`resolves_to`, `serves`, `runs`, `owns`, `member_of`, `redirects_to`,
`same_as`). Containment is a foreign key and is not a relationship.
_Avoid_: Edge, link, association

**Identity**:
An entity representing a way of being someone against the target — a proxy
upstream slot the agent names, never credential material the agent holds. Also a
graph node, because identities own resources.
_Avoid_: User, account, credential, session

**Lease**:
An exclusive, expiring hold taken by one agent run — on an identity, and on the
task it is executing. At most one unreleased lease per identity, so two hunters
cannot mix sessions. Both leases of one run share a single clock and a single
heartbeat: a run whose task lease is alive always holds live identity leases.
_Avoid_: Lock, reservation, checkout

**Surface fingerprint**:
A value summarising an application's observable surface, recomputed after recon
and compared against itself over time. A change is what makes a refuted
hypothesis due again.
_Avoid_: Hash, version, snapshot, signature

## Epistemics

**Observation**:
An immutable fact derived from a runtime-generated provenance record. Has a
subject entity and no status: it exists or it does not. Never produced by a model
alone.
_Avoid_: Fact, result, output

**Evidence**:
The *role* an observation plays for a claim, carried on the edge between them
with a polarity (supports/refutes) and a role (baseline/variant/control).
Evidence is never a record of its own.
_Avoid_: Proof, artefact, exhibit

**Hypothesis**:
A proposed security property of one subject entity, usually about a pair of
identities, moving through `proposed -> testable -> testing -> supported |
refuted | inconclusive`. Only the runtime may start it testing.
_Avoid_: Theory, idea, lead, suspicion

**Property class**:
The security property a hypothesis is about, and the component that decides
whether two hypotheses are the same one.
_Avoid_: Category, bug type, vuln type (a vulnerability class is what a *finding*
has)

**Test**:
An immutable executable specification for settling one hypothesis:
preconditions, setup, actions, assertions, cleanup. Actions are structured
request specs, never shell strings. A changed test is a new test.
_Avoid_: Check, scan, probe, PoC

**Test run**:
One execution of a test, producing receipts and an outcome. Replaying a test run
is what makes a finding validated.
_Avoid_: Execution, attempt, trial

**Finding**:
A claimed vulnerability resting on one or more hypotheses, moving through
`candidate -> validating -> validated | rejected -> reported`. It cannot be
validated without the test run that reproduced it, and only a human moves it to
reported.
_Avoid_: Vulnerability, issue, bug, report (the report is the document a finding
renders into)

**Negative knowledge**:
Refuted hypotheses kept as first-class records with the conditions under which
they were refuted and the surface deltas that would make them worth retesting.
_Avoid_: Dead end, ruled out, noise

## Execution

**Task**:
A unit of schedulable work, ranked against other tasks and claimed by one worker.
Survives its own retries.
_Avoid_: Job, work item, ticket

**Ranking pass**:
One recomputation of every pending task's runtime factors and priority for a
program. Deterministic given the rows and the weights version; it never reads the
clock.
_Avoid_: Scoring, sort, tick, cycle

**Slate**:
The bounded set of tasks the runtime offers the orchestrator to choose from. The
runtime decides what may be chosen; the orchestrator decides which; the runtime
commits the claim.
_Avoid_: Queue, candidates, shortlist, options

**Roster**:
The closed statement of every role this harness runs and what each one may call,
compiled against a measured inventory of the SDK/CLI pair's own tools. One
document, so the schema, the launch and the gate cannot each hold a different
answer.
_Avoid_: Registry, config, agent list, manifest

**Role**:
One row of the roster: how it runs, who may start it, which task kinds it
executes, its model, effort and turn ceiling, its tools, its skills and how many
of it may run at once. Not a persona and not a prompt — a bound.
_Avoid_: Agent type, persona, profile, worker

**Tool group**:
The unit of authority a role holds, naming a class of tool rather than one tool.
Moving a tool between groups changes what every role holding either can do,
which is why the group is what a role is granted.
_Avoid_: Scope, permission set, namespace, capability

**Pre-tool gate**:
The runtime's decision on one tool call, taken before the call runs and from the
roster alone. It is the enforcement point: what the model is shown and what the
permission mode allows are context management, and this is the boundary.
_Avoid_: Filter, middleware, hook, policy engine

**Denial**:
One refusal by the pre-tool gate, carrying the rule it violated so a run's
evidence distinguishes a call the model never made from one it made and lost.
_Avoid_: Error, rejection, block, violation

**Agent run**:
One invocation of one subagent role, carrying the mission packet in and its raw,
unpromoted result out.
_Avoid_: Session, mission, conversation, turn

**Mission packet**:
The compiled input to an agent run — objective, scope, budget, identity leases,
allowed skills, stop conditions. A payload, not a lifecycle.
_Avoid_: Mission, brief, prompt

**Promotion**:
The runtime step that turns an agent's raw result into canonical rows. Nothing an
agent returns is true before it.
_Avoid_: Ingestion, commit, acceptance

**Event**:
An immutable record that something happened, appended in the same transaction as
the row it describes. A *row event* mirrors one write and names its row; an
*occurrence event* records something with no row at all, like a refusal or a
resume. The log proves the state changes are complete and says why the system
thought what it thought — it is never the path state is rebuilt from.
_Avoid_: Log entry, message, audit record, projection

**Tool run**:
The runtime's record of invoking one tool, with its arguments and status.
_Avoid_: Call, invocation, action

**Receipt**:
The proxy's authoritative record of one network exchange, including the ones it
blocked. Carries the hashes of what the agent saw and what actually crossed the
wire, which differ by exactly the injected credentials.
_Avoid_: Log entry, trace, request record

**Callback channel**:
One out-of-band endpoint the harness operates, declared by a Program under a
name, a kind and a host. Never a target and never evidence about one: an arrival
at it is evidence that something reached out. Declared per scope version, so a
withdrawn channel stops admitting the moment the next version is live. One
endpoint is one channel: a second name for the same host would make which
channel admitted an arrival a question about declaration order.
_Avoid_: Canary domain, collaborator, listener, OOB server

**Correlator**:
The runtime-minted label a canary is addressed by, and the whole of what makes
an inbound arrival attributable to one Program and one subject. One lower-case
DNS label, because that is the only shape it can arrive in. Not a credential:
holding one authorises no read, no write and no request. Canonical state keeps
only its digest, and it binds nothing once it expires.
_Avoid_: Token, secret, canary token, callback id

**Lane**:
Which party caused a request: `agent` (a subagent acted), `replay` (the runtime
re-executed a test), or `proxy_internal` (the proxy acted as a client of the
target on its own behalf). Only the first two can back an observation.
_Avoid_: Channel, source, origin

**Artifact**:
A content-addressed blob of raw evidence, identified by the hash of its
plaintext. Credential-bearing artifacts are encrypted and never shown to an
agent.
_Avoid_: Blob, file, attachment, evidence

**Standing grant**:
A predicate over requests, issued by an operator, pre-authorising a class of
call a human would otherwise be asked about one at a time. Never a bypass: a
request no grant admits still parks, and parking with nobody present ends the
run.
_Avoid_: Permission, allowlist, autonomy flag, approval (an approval answers one
question about one call)

**Review gate**:
A registered blocker code holding a finding or a chain unrenderable until an
operator clears it. It blocks rendering only; scheduling never waits on a
reviewer.
_Avoid_: Sign-off, hold, lock, approval

**Halt**:
An operator's stop on a whole program, enforced at the egress door rather than
in the runtime loop, and cleared only by its own operator verb. Distinct from an
abort, which is unplanned and reconciles from current authoritative rows. Events
audit that reconciliation; they are never replayed to rebuild state.
_Avoid_: Pause, kill, stop, abort

**Credential vector**:
An environment variable, settings key or provider switch that replaces,
prevents, reroutes or redirects the CLI's subscription-authenticated request
path. Each one is measured against a running version rather than inferred, and
the set is bound to that runtime version.
_Avoid_: API key, credential, auth source (an auth source is what the CLI
reports having resolved, after the fact)

**Agent boundary**:
The container one agent run's process lives in: attached to a single internal
network whose only peer is the capability proxy, external DNS blackholed, and
holding only what the runtime mounts — the application, the SDK the startup
assertion measures, the home a credential is resolved from, and the run's trust
root. It is what makes "no direct path to a target" a property of the network
rather than a request made of a cooperative client. Required to start an agent
run and never defaulted: a default would be the operator's own machine, with the
operator's own home.
_Avoid_: Sandbox, jail, isolation layer, VM

**Startup assertion**:
The runtime's version-bound refusal to begin an agent run while any credential
vector is present or the effective launch configuration cannot be verified,
made before the SDK transport is constructed and corroborated once from the
CLI's own report. It enforces the subscription-only constraint. It never
establishes that a request did bill the subscription, which only a receipt can.
_Avoid_: Guard, preflight, health check, validation

## Knowledge

**Skill**:
An executable capability that lives in the repo, is versioned with the code, and
is testable in CI. A playbook references skills; a skill never references a
playbook.
_Avoid_: Tool, capability, module

**Playbook**:
An investigation strategy in the knowledge base, versioned with knowledge rather
than code, carrying provenance and an expiry.
_Avoid_: Strategy, recipe, methodology, technique
