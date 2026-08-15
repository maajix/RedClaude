# redKrakenV2

An autonomous bug-bounty hunting harness for web and API targets. The vocabulary
below is the ubiquitous language of the whole system: the same words name the
tables, the MCP tools, and the things agents are told about.

## Surface

**Surface**:
Everything this Program knows is out there: its Entities, the Relationships
between them and the containment that holds them. What an agent reads before it
acts and what promotion adds to. Not the code an agent can reach, which is the
tool surface.
_Avoid_: Inventory, graph, attack surface (the phrase is fine in prose; the
noun in this system is Surface)

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

**Origin**:
Who put a Surface row there: `configured` (an operator's scope), `imported` (a
handover from outside the harness), `observed` (the runtime's own instruments)
or `proposed` (a model's proposal the runtime promoted). One value on the row
for whoever first caused it, and the set of everyone who has since said the
same thing beside it. Not the lane of the request the evidence came over, and
not the evidence itself.
_Avoid_: Source, provenance (provenance is the row pointing at the evidence),
lane

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
hypothesis due again. The word for the value is the same as the word for the
record: a column, a payload key or a view column that calls it something else
is the same synonym problem with a new spelling.
_Avoid_: Hash, digest, version, snapshot, signature

**Surface delta**:
One named difference between two fingerprints of one Application: an Endpoint,
a Parameter, a Technology or an Identity relationship that appeared,
disappeared or changed, carrying the element on both sides, the row it is about
and the Property classes it puts back in question. It says what moved and what
is worth asking again; it never says a refutation was wrong.
_Avoid_: Diff, drift, regression, change event

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
refuted | inconclusive`. Every one of those moves is the runtime's, `proposed ->
testable` included, because a testable hypothesis is what a Task is ranked from
and an agent that could set it would be scheduling its own work. It becomes
canonical only by promotion, and only while something supports it. Two proposals
reaching the same subject, identity pair and Property class converge on the one
row, which keeps both proposals' evidence and records the collision. Once it has
moved past `proposed`, no proposal reaches it at all: adding evidence to a claim
whose Test is already running is the same authority as starting the Test.
_Avoid_: Theory, idea, lead, suspicion

**Rationale**:
The three named fields a proposed hypothesis carries beside its one-sentence
statement: the `mechanism` the defect would be, the `expectation` a correct
system meets instead, and the `falsifier` whose result would settle the claim
against the hunter. Closed, and all three required — a statement is prose two
hunters can write identically about different mechanisms, and a refutation is
only negative knowledge if something said in advance what one would be.
_Avoid_: Reasoning, justification, explanation, notes

**Property class**:
The security property a hypothesis is about, and the component that decides
whether two hypotheses are the same one.
_Avoid_: Category, bug type, vuln type (a vulnerability class is what a *finding*
has)

**Cell**:
What makes two claims, or two findings, the same one: the Program, the Property
class, the subject entity and the identity pair, read as a single key. Most
findings name no identity and share the anonymous half of it, which is why the
two identity columns count as equal when both are absent rather than as two
different cells. One live finding occupies a cell; a hypothesis that settles onto
an occupied one merges into what is there.
_Avoid_: Bucket, group, dedup key, fingerprint (a surface fingerprint is a
different thing)

**Test**:
An immutable executable specification for settling one hypothesis: the five
parts `preconditions`, `setup`, `actions`, `assertions`, `cleanup`, and nothing
else. Actions are structured request specs, never shell strings, and each carries
its own ordinal and one of the three roles. Preconditions are prose under a typed
word: what has to hold before the run is worth starting, stated for a reader
rather than evaluated, because the four conditions the runtime can decide — scope,
risk, the Identity lease, the budget — it decides against canonical state at the
moment the replay opens. A Test performs between 3 and 32 actions and at least
one of every role, because a specification that could never support the claim it
was written for is one nobody should be able to store. Identity is the digest of
the specification: a changed test is a new test.
_Avoid_: Check, scan, probe, PoC

**Test run**:
One execution of a test, producing receipts and an outcome. Replaying a test run
is what makes a finding validated. The outcome is `holds`, `refutes` or
`inconclusive`, derived from the run's own Receipts rather than reported by
whatever performed it: one assertion that cannot be answered makes the run
inconclusive, one that fails refutes, and the failed identifiers and the state of
the cleanup are recorded beside it. An inconclusive run files no Evidence and
settles nothing — an Observation is a statement about the target, and a run that
could not evaluate its own assertions has none to make. A run's outcome is not
by itself a claim's verdict: the close asks the epistemic machine whether the
transition it would make is admitted, and settles `inconclusive` with the
refusal recorded when it is not, because a run that held every assertion it
stated may still rest on too few Observations to support the claim — a control
the door blocked is an action that files none.
_Avoid_: Execution, attempt, trial

**Replay**:
The runtime performing one Test through the door, as a Tool run marked a replay
before its capability exists. That order is the whole of the guarantee: the mark
is what the Lane is derived from, so every Receipt the run produces carries
`replay` without the runtime ever saying the word, and a Receipt from any other
capability is refused rather than recorded under the wrong Lane. One claim has at
most one replay in flight. Nothing about a replay is a decision the process
makes: the urls, the methods and the roles all come out of the stored
specification, and what it contributes is only which actions it managed to
record.
_Avoid_: Rerun, reproduction, playback

**Finding**:
A claimed vulnerability resting on one or more hypotheses, moving through
`candidate -> validating -> validated | rejected -> reported`. It cannot be
validated without the test run that reproduced it, and only a human moves it to
reported. It is born a candidate and nothing else: at `info`, on no severity
basis, naming the Property class it rests on, the exact holding Test run that
settled the claim, and what that run demonstrated. The later states are reached
by transition, never by birth, so a Finding that is validated is one something
validated. The cell it occupies is the claim's cell -- Program, Property class,
subject and identity pair -- and one live Finding occupies it: a second proposal
onto the same cell merges into the first, adding its evidence and its claim
rather than opening a rival. Every proposal is kept either way, accepted or
refused with the sentence that refused it, beside the Findings and reachable
from none of them.
_Avoid_: Vulnerability, issue, bug, report (the report is the document a finding
renders into)

**Demonstrated behaviour**:
What a candidate says its holding run showed, read off that run rather than
written by anyone: the kinds of assertion that held, the roles of the exchanges
they were evaluated over, and how many Receipts are under it. Not a taxonomy --
a fifth vocabulary of behaviours would be model-authored, and the run has
already answered the question in the two vocabularies a Test is written in.
_Avoid_: Impact, severity, proof of concept

**Validation packet**:
The whole world one blind validator session is given: the candidate Finding's own
facts, the claim's label and status, the Test it rests on, the run it was born
from and the run that reproduced it just now, the Receipts of both, and the
Artifacts those name by hash and size. Built from an empty object upward by a
positive column allowlist, so a field is in it because a migration named it and
for no other reason -- the hunter's title, its reasoning and its prose are not
absent by filtering, they were never selected. It is served once and digested,
and it travels with the job: the session has no database, no network and no
second version to fetch.
_Avoid_: Evidence bundle, dossier, context, prompt

**Verdict**:
What one blind validator answered about one packet -- `confirmed`, `refuted` or
`insufficient` -- with the identifiers of the assertions it says did not hold.
Input, not a decision: the Finding moves because the rules rebuilt the packet,
found it digests the same, and admitted the transition that word implies. A word
answered about evidence that has moved since is not one of these: it is written
on the attempt that served the packet, where it records what that reading came
to, and it never becomes a verdict about the Finding itself. The
first answer stands, because a session that answers twice is arguing with itself
about a document that did not change in between.
_Avoid_: Decision, judgement, ruling, review

**Impact demonstration**:
What a validated detection was proved to be worth, and the only thing this
harness calls demonstrated impact: one holding replay of a Test that stated the
impact it would have, run under a live operator grant for that exact
specification, whose after-state action came back with a Receipt, and whose undo
was both reported done and sent -- every request the Test names as its cleanup
answered by a Receipt of its own, because the report is the supervisor's word and
the Receipts are what happened. All four or none of it -- a run that held and
could not undo itself demonstrates nothing, and neither does one nobody granted.
Whether the undo worked is not asked; only another Test could answer that. The
class is one of six, and the split is not a scale: three an operator may grant
(`read_other_data`, `write_target_state`, `escalate_privilege`) and three are
things nobody may, at any severity, on any Finding (`degrade_availability`,
`reach_third_party`, `pivot_out_of_scope`) -- the question is not asked, so no
answer to it exists. None of it reaches the claim underneath: an impact run
settles no hypothesis, writes no Observation and produces no Evidence, because
the detection was validated before it opened and this is the second question
about it.
_Avoid_: Exploit, proof of concept, weaponisation

**Severity basis**:
The ground a finding's severity stands on, stated with the severity and never
apart from it: `undetermined` while nothing has been demonstrated, and otherwise
one of `demonstrated_impact` (the harness performed it and has the receipts),
`constrained_inference` (it follows from what was demonstrated, and the step was
not performed) or `program_context` (the program says this class of thing matters
here). A candidate is born `undetermined` and stays `info` until one of the other
three is stated. Each is refused for its own reason, and the reasons are what
keep the three apart: no demonstration behind `demonstrated_impact`, a
demonstration already behind `constrained_inference` -- an inference is what is
made where there is no proof -- and `high` or `critical` on nothing but
`program_context`, which reads a document rather than the target.
_Avoid_: Confidence, likelihood, CVSS (a report renders one; the basis is not it)

**Capability**:
What holding a position gets you, as distinct from what a Finding is about, which
is a property class, and from what is wrong with the target, which is a
vulnerability class. A closed vocabulary of ten words owned by migrations,
because `session` and `authenticated_session` are one capability to their authors
and two to anything counting. The vocabulary is one value with one digest, and
every pivot stamp records which digest it was issued under -- so a word added,
removed or re-described later leaves old stamps saying what they said instead of
quietly meaning something new.
_Avoid_: Permission, privilege, access level, property class, vulnerability class

**Pivot stamp**:
The runtime's record that it saw a capability obtained: one immutable row per
body of evidence, naming the member Finding, its subject, the Identity the door
recorded, the Test and its digest, the run, the transition and the Receipt it is
read from, the capability provided, the capabilities required, the conditions --
one of which states the scope the claim is made in -- the scope version the run
ran under and the capability vocabulary. The claim is written before the run,
in the Test specification an operator's impact grant is over -- a pivot claim
authored beside a finished run is a claim fitted to its answer. Demonstrating it
is structural rather than rhetorical: the named transition assertion held, and
the request it reads is one the member's own validating Test never made, because
a transition drawn from that set demonstrates the member a second time and
nothing else. Its identity is the digest of everything it rests on, so issuing
twice from unchanged evidence is the same stamp and anything that moved
underneath is a different one. What a chain in a later ticket composes over is
these, never the word "so".
_Avoid_: Chain, escalation, link, exploit step

**Negative knowledge**:
Refuted hypotheses kept as first-class records with the conditions under which
they were refuted and the surface deltas that would make them worth retesting.
The conditions are copied, not joined: the claim as it read, the evidence as it
stood, the test run that settled it, and the surface fingerprint it was settled
against. One record is doing exactly one of four things, and only the first
suppresses work: `settled` (the settling test run is on file and nothing has
invalidated it), `due` (something invalidated it), `unverified` (nothing on file
settles it -- what an imported refutation is) or `superseded` (a later
refutation of the same claim replaced it). A record becomes due when a typed
delta of the right property class lands on the claim's own subject, under it, or
above it, against a newer fingerprint of the claim's own application -- or when
a retest trigger someone already recorded against the claim fires, which is a
relevance judgement made elsewhere and not re-decided here. That happens once
per record, and the claim goes back to `testable` through a transition naming
what reopened it.
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

**Task dependency**:
One claim that finishing a task would settle what another is waiting for, naming
the readiness predicate it settles and the basis it was derived from. Only a
sound basis moves a priority; a dependency nobody derived is worth zero, not a
guess, and one dependent's value is shared between the tasks that could settle
it rather than paid to each of them.
_Avoid_: Blocker, link, prerequisite, dependency edge (an edge between two
entities is a Relationship; the word is fine in prose about this table, the noun
in this system is Task dependency)

**Slate**:
The bounded set of tasks the runtime offers the orchestrator to choose from. The
runtime decides what may be chosen; the orchestrator decides which; the runtime
commits the claim.
_Avoid_: Queue, candidates, shortlist, options

**Choice**:
What one orchestrator answered over one Slate, made in a task-less agent run so
that choosing never competes for a lane slot with the work being chosen between.
Recorded whatever it turned out to be — a label, a label the Slate no longer
carries, or nothing — because a pass that claimed nothing still has to say why.
A request and not a decision: the claim re-asks every eligibility condition, and
a stale choice is refused rather than replaced.
_Avoid_: Selection, vote, assignment (a Choice is what was answered; the
Dispatch is what the runtime then does about it)

**Dispatch**:
The runtime's act of starting an agent run from a committed claim, with that
claim's Leases and reservations and no others. It is bounded on both sides: the
Task is the one the claim wrote, and the role is the one the roster gives that
Task's kind. Never the model's: a Choice asks for a Task, and this is the step
that either happens against exactly that Task or does not happen.
_Avoid_: Launch, schedule, assignment, handoff

**Campaign**:
One orchestrator's continuous line of decision for a program, made of the
orchestrator sessions that replaced each other. The campaign carries on in the
successor that points back at the session it replaced. Durable rather than held:
every pass is already a restart, so a campaign that lived in a process would last
exactly as long as the weakest thing in it.
_Avoid_: Conversation, thread, context window, run

**Orchestrator session**:
One stretch of a campaign, from the pass that opened it to the ceiling that
closed it. Its turns are the agent runs made inside it, and the three ceilings it
is measured against — turns, tokens and decisions — are copied onto it when it
opens, so an operator editing the settings cannot move a bound the session has
already been run against. One open at a time per program, because "what does this
campaign resume into" must have one answer. The word is reserved for this: an
agent run is not a session, and neither is a supervisor process.
_Avoid_: Context window, chat, thread, process

**Capsule**:
Everything a replacement session inherits, compiled from durable state at the
moment it starts: program lifecycle, budget, integrity, active work and the next
Slate, each row with its revision and the database's own digest, and each
section saying how much of itself it is not carrying. Bounded in bytes and
estimated tokens, and refused rather than sent when it cannot be fitted. Never a
transcript and never a model-authored summary — what a rotation preserves is
what can be recomputed.
_Avoid_: Summary, handoff, memory, snapshot

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
_Avoid_: Scope, permission set, namespace, capability (a Capability is what a run
obtains against a target, never what a role is granted here)

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
unpromoted result out. A planning run is additionally one _turn_ of the
orchestrator session it was opened inside, which is what that session's turn
ceiling counts — a relationship the run has, not a second name for it.
_Avoid_: Session, mission, conversation, invocation

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
*occurrence event* records something no single row stands for: a refusal, a
resume, or one act that wrote many rows, which it may still name. The
distinction is what the event mirrors, not whether a row exists. A ranking pass
and a fingerprint are each one thing that happened, whatever they
wrote. The log proves the state changes are complete and says why the system
thought what it thought — it is never the path state is rebuilt from.
_Avoid_: Log entry, message, audit record, projection

**Tool run**:
The runtime's record of invoking one tool, with its arguments and status.
_Avoid_: Call, invocation, action

**Offline tool**:
One row of the closed registry an offline analysis tool must be in to run: the
executable's path, the arguments it takes and the kind each one's value has, the
version its image must report, its five ceilings, whether it has a network, and
which roles may run it. The registry is the whole of what such a call may be, not
a list of suggestions — a tool nothing registered cannot run, and a value the
registry does not describe cannot be passed. Only the runtime reads it; the
connection the model reads the world through cannot see it at all.
_Avoid_: Binary, command, plugin, allowlist entry

**Offline tool run**:
One execution of a registered offline tool: a Tool run written and committed
before the process starts, carried out in a container with no route out unless
the registry row says otherwise, and closed with what became of it — success,
failure, timeout or an output bound reached. What leaves it is stdout, stderr and
the output files the registry declares, each stored as an Artifact against the
version the image reported. Distinct from a hook-opened Tool run, which records a
call the model made through the SDK and which the pre-tool gate decides.
_Avoid_: Shell command, job, subprocess, scan

**Browser mission**:
One walk of a compiled plan by a real browser: a sequence of registered actions
over one in-scope URL, written and committed as a Tool run before any container
starts, performed with the door as the process's only peer, and closed with what
each step became. Every request it makes is the door's to admit, so a mission is
a Tool run whose Receipts are the whole of what it reached. What it kept — the
document, the viewport, the console and each declared probe's answer — are
Artifacts of that run, each naming the step that produced it. Distinct from an
offline tool run, which has no page and no door.
_Avoid_: Crawl, browser session, headless run, scripted click-through

**Result digest**:
What one browser mission is compared by: the digest over each step's ordinal,
action and canonical outcome, and nothing else. Timestamps, nonces, generated
identifiers and the bytes of a screenshot are excluded by construction rather
than by filtering, because the outcome keys an action may report are the
registry's and the values they may hold are canonical. Two missions of one plan
that differ here differ in what the target did.
_Avoid_: Fingerprint, run hash, signature, checksum

**Probe**:
A registered piece of page-side script a browser mission may run, with its own
payload and the closed set of verdicts it may return. What makes a mission a
measurement rather than a recording: the verdict is read off the page the target
rendered, so the same plan against two targets that behave differently returns
different verdicts. A verdict outside the declared set is refused.
_Avoid_: Check, detector, payload, test case

**Analyser**:
A program this harness ships and mounts into an offline tool's container, named
by the registry row and hashed by the runtime, whose hash the Tool run records.
It is what makes an analysis reproducible without a second build: what ran is
named exactly, and a registry row and a runtime that disagree about whether
there is one open no run at all. One analyser answers several questions — the
tool's own name is the subcommand — so which analysis a run was is the registry
key rather than an argument.
_Avoid_: Script, plugin, helper, wrapper

**Source Artifact**:
An Artifact this Program holds as source: bytes an analysis may read, as
distinct from bytes a run produced or the runtime stored. The kind is a property
of how the Program came to hold them, so it cannot be claimed after the fact —
an offline tool's own output is `tool_output` unless its registry row declares
otherwise, which is what stops a tool laundering arbitrary bytes into source by
printing them. Only a source Artifact may be an analysis argument.
_Avoid_: Input file, JS file, asset, blob

**Source citation**:
What a proposed element about source must carry, in any of the four lists a
proposal has: the Artifact it came from, optionally the hash it was read at, and
the Tool run that read it. It is checked when the proposal is staged and re-asked
of everything promoted, and it fails in six distinguishable ways — the label is
not this Program's, the bytes are not held as source, they have changed under the
element, the cited run never read them, the element is grounded in a run that
read source and does not say which, or the element proposes a route the cited run
never reported. A failed citation is a dropped element, not a refused proposal.
The first five ask where a conclusion came from; the sixth asks whether the run
said it, against the request paths the runtime read out of that run's own answer
while it was filing it.
_Avoid_: Reference, provenance, attribution, link

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
target on its own behalf). Only the first two can back an observation, and every
standing rule about egress reads both of them: a rule that named `agent` alone
would be a rule a replay's requests are invisible to.
_Avoid_: Channel, source, origin (an origin is who put a Surface row there,
which is a different question about a different record)

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

**Question code**:
The stable classification a question is filed under -- risk, scope ambiguity,
third-party impact, credential need, policy uncertainty -- held as
program-global registry rows that the rule raising a question and the decision
recording it both point at by foreign key. An operator answers the code, not the
sentence: the sentence names one call, the code is what a standing grant and the
next revalidation are written against.
_Avoid_: Reason, category, tag, decision type

**Parked**:
A task interrupted by a question rather than finished or failed: its runs are
closed, its leases released and its claim dropped, and only an operator verb
moves it again. It costs no attempt, because nothing about the work was tried
and found wanting. Distinct from abandoned, which is terminal, and from pending,
which the scheduler may claim now.
_Avoid_: Blocked, paused, waiting, on hold

**Supersede**:
An operator's withdrawal of a question they will not answer, after changing the
configuration it was asked under. No grant is issued and the task goes back to
pending, so what resolves it next is a fresh gate verdict under the policy in
force then. Distinct from a denial, which ends the task on the operator's
authority.
_Avoid_: Cancel, dismiss, close, ignore

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
_Avoid_: Tool, capability (a Capability is what a run obtains against a target,
never what a Skill teaches), module

**Playbook**:
An investigation strategy in the knowledge base, versioned with knowledge rather
than code, carrying provenance and an expiry.
_Avoid_: Strategy, recipe, methodology, technique
