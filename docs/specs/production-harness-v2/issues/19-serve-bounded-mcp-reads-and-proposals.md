# 19 — Serve bounded MCP reads and Mission proposals

**What to build:** Give an executing role compact Program-scoped context and one structured outbound proposal path without granting direct authority over canonical state.

**Blocked by:** 05 — Prove Program isolation and bounded reads; 18 — Compile and enforce the six-role roster.

**Status:** resolved

- [x] State read tools expose only the current Program's labelled Surface, Hypotheses, evidence, Receipts and reachable Artifacts under explicit bounds.
- [x] Every bounded response carries revisions, digests, counts and omission markers so truncation cannot look complete.
- [x] The single Mission-result operation accepts structured proposed Entities, Relationships, Observations, Hypotheses, evidence edges, suggested Tasks and a completion claim.
- [x] Mission results write only staging rows; no executing role can promote, validate, report or set Task lifecycle directly.
- [x] Observation proposals referencing absent, foreign or incompatible provenance are retained as rejected staging outcomes rather than canonical truth.
- [x] Closed schemas reject unexpected free text and Program identifiers before handler execution.

## Comments

Implemented on branch `worktree-bridge-cse_01UqqG8vnWAE2yE3JVCiLqm6` on
2026-08-12.

Two new modules, and the split between them is the ticket. `packet.py` is
everything the child may read: a compile that runs once, on the `rk2_state`
connection, before the container starts, and a reader that answers the five
state tools out of the document it produced. `proposal.py` is everything the
child may write: one structured result, reviewed against provenance the
database can confirm, written as staging rows. Neither module imports the SDK
and neither takes a Program identifier, so both are testable without a
container and neither can be asked about a Program it was not bound to.

### The packet is compiled outside and read inside

The child has no database. `packet.compile` runs in the supervisor on a
connection held by `rk2_state`, and the whole scope of that compile is the
connection: no statement names a Program, no parameter carries one, and the
function has no such argument to pass. What makes that safe rather than
optimistic is ticket 05's work -- row level security scopes every relation to
`rk2_program()`, and the role holds per-column grants only -- so a compile that
tried to read another Program's rows would return nothing rather than more.
`tests/test_packet.py` asserts the absence directly, over every statement the
compile issues.

The document that crosses the process boundary is `Packet`: five sections, a
revision, the limits it was compiled under, and the staged head of each
readable Artifact. `Reader` answers `get_attack_surface`, `get_hypotheses`,
`get_evidence`, `get_receipts` and `get_artifact` from it and from nothing
else. A read the packet cannot answer is an omission marker, never a query, so
there is no path from a tool call to a statement -- which is what makes "the
process that owns the session is the boundary" true of the reads as well as of
the network.

### Bounds that state their own subtraction

Four ceilings, in `Limits`: rows per section, serialized bytes, an equivalent
token budget, and how much of an Artifact's head is staged. The byte and token
ceilings are not two policies -- `byte_ceiling` is the smaller of the two, so
a configuration that satisfies one and not the other binds on the one that
binds. The row limit is a `LIMIT` sent to the database; the byte ceiling is
applied after, by `fit`, which drops from the largest section first so that a
crowded Surface cannot spend the whole budget and answer with a Program that
has entities and no hypotheses.

Every response carries four counts rather than one: `total` is what the Program
holds, `staged` is what survived the compile, `matched` is what the caller's
filter selected, `returned` is what the page carried. The two gaps have
different causes and a single "omitted" would hide which, so each gets its own
marker -- `packet_bound` for rows the compile never staged, `limit` for rows
this page left behind, `not_staged` for an Artifact whose bytes the runtime
could not load, `excerpt_only` and `range_beyond_excerpt` for a window that
asks past the head. Revisions and digests come from the database:
`rk2_revision()` and the `sha256` `v_records` computes over the record's own
jsonb text. A second implementation of that hash in Python would be a second
answer to the question "is this still the row I cited".

### One result, and it is staging data

`mcp__rk2__submit_mission_result` is the only outbound verb an executing role
holds. It takes all six element lists Spec section 13 names -- Observations,
Entities, Relationships, Hypotheses, evidence edges and suggested Tasks --
beside the completion claim, and `proposal.stage` writes them to `proposals`
and `proposal_drops` inside one transaction. Nothing else moves:
`MissionPacketTest.test_a_mission_result_writes_a_staging_row_and_moves_nothing_canonical`
takes a ten-column snapshot of the canonical half of the database -- including
the Task status vector, the validation queue and the report queue -- either
side of a staged result, and asserts the two are identical. Criterion 4 is that
assertion rather than the absence of a promote verb, though the absence is also
compiled: `roster.CANONICAL` names every canonical relation and the roster
compile refuses a contract that writes one.

Provenance is reviewed before anything is staged, and a failed review is
recorded rather than raised. Eight reasons, each a row in `proposal_drops` with
the element path and the label that was cited: `no_such_receipt`,
`receipt_other_program`, `receipt_proxy_internal`, `receipt_other_run`,
`no_such_tool_run`, `no_such_label`, `label_other_program`, `no_provenance`. A
proposal whose every element was dropped is still a `staged` proposal with
drops, because "the agent claimed this and it did not check out" is a fact
about the run and deleting it would make a refusal look like silence.

The three cross-Program refusals are proven on real rows, and getting there
turned up something worth writing down: labels are per-Program counters, so two
Programs seeded alike hold the same labels, and "another Program's R1" is also
this Program's R1. That collision is correct -- it is what makes a foreign
label indistinguishable from an unknown one to the agent -- and it makes the
refusal untestable against identical halves. `MissionPacketTest._exclusive`
seeds one Receipt and one Entity in the second Program only, so the cited label
is one the first Program has genuinely never reached.

### Closed schemas, and where they bind

`Contract.schema()` renders each contract as JSON Schema with
`additionalProperties: false`. The CLI validates a call against the served
schema before `PreToolUse` runs, so an invented field is refused before the
gate and long before a handler -- and `FORBIDDEN_ARGUMENTS`, which is where
`program_id` lives, is refused at compile time from ever appearing in
`properties`. The gate checks the same properties again afterwards. Two checks
of one statement, which is the arrangement rather than two statements.

### Three defects the live tests found that the seam tests could not

The seam tests use a recording connection, so they hold the module to its own
SQL rather than to the schema. `MissionPacketTest` runs the real compile on the
real `rk2_state` connection, and it found all three.

*`v_evidence` was unreadable.* Migration 030 turned relation grants into a
per-column registry: it revoked every relation grant `rk2_state` held on
relkind `r`, `v` and `m`, and seeded `state_read_surface` from `relkind = 'r'`
only. Tables kept their privileges through the registry and all six agent-facing
views silently lost theirs. The artifact migration noticed for `v_artifacts`;
nothing noticed for the rest, because ticket 05 recorded that none of them had a
reader yet and left the question to this ticket. `20260812T063000Z` is the
answer: `v_evidence` is registered column by column, and `v_surface`,
`v_hypotheses` and `v_receipts` are dropped. `v_records` answers all three with
the revision and digest a bounded read has to report and those views have no
column for, so keeping them would leave three relations that look like the
agent read surface, are granted to nobody, and return a shape no handler
serves. `v_validation_packet` is untouched: it is the validator's read and
`validate.judge` is not a group this runtime serves yet.

*The Artifact section selected a column that no longer exists.* `v_artifacts`
was redefined by the ticket-06 migration and has no `ref_count` -- deliberately:
that count answers "how many other things hold these bytes", which for one
shared content-addressed namespace is a question about other Programs.

*And an Artifact was addressed by hash.* The same migration states the rule on
the view itself -- "the hash is reported and is never an argument: a verb taking
one would read across Programs whenever the caller could guess the bytes" --
and `mcp__rk2__get_artifact` had taken `artifact_hash` since the roster was
written. It takes `artifact_label` now, matching `AF[0-9]+`, and the hash comes
back in the record where a caller that already holds bytes can check them
against it. The asymmetry is the point: the supervisor compiling the packet
loads by hash, because it is the side that may; the child addresses by label,
because it is the side that may not. Ticket 18's note that this verb "takes a
content hash and no path" was corrected in place -- its argument, that a verb
with no path replaces `Read`, is unaffected.

Which left a label the child had no way to learn, and the code review caught
it: a Receipt record carries `request_agent_sha` and `response_agent_sha`, and
a hash is exactly what this surface will not take as an argument. So the same
verb lists. Called with no label it returns the Artifacts this packet reached,
metadata only, through the same `_page` every other section is bounded by --
which means the list is subject to the same `packet_bound` and `limit` markers
and stops at this Program's own references. Nothing is required by the schema
now, because listing is how a fetch becomes possible.

### What is served, and what is only compiled

`_launch.server` serves six tools: the five reads and the one proposal.
`runtime.ready` is gone -- it existed to report that the tool surface opened,
which the state reads now do by answering -- and `agent.SERVED` is the
intersection of the roster with what the launch actually serves, so a role
holding `sched.pick` or `net.request` holds nothing until the ticket that
implements those groups. `_launch.Submission` accumulates the child's one
result and counts the tries; it returns an acknowledgement and writes nothing.

What this ticket does not do is call either half. `packet.compile` and
`proposal.stage` have no caller in `src/` yet: the seam they meet at is
`AgentRunRequest.packet` going in and `AgentRunResult.mission_result` coming
back, and the loop that fills one and drains the other is ticket 20, which is
the ticket that runs one Task from a compiled packet to a promoted
Observation. So the six criteria here are measured on the modules and on the
live database rather than on a run: what exists is a compile that can only see
one Program, a reader that can only answer from what it was given, and a write
path that can only reach staging.

### What the code review changed

The two-axis review against `1d52a32` found four things worth the patch, all
applied here:

- **`relationships` was not accepted.** Section 13 names six element lists and
  the contract declared five, and because the schema is closed that is not a
  deferral -- a child proposing a Relationship was denied `R-ARGVALUE`. Added
  to the contract, to `OPEN_ARGUMENTS` and to the served description. It is not
  provenance-checked, for the reason the other four are not: its endpoints may
  both be Entities proposed beside it.
- **An Artifact label was unlearnable**, which is the listing above.
- **`get_receipts` reported `matched` as the number of labels asked for**, so a
  read for three labels the packet held one of answered `matched: 3` against
  `staged: 2`. It is the number matched now, which is what `Answer`'s own
  docstring says it is.
- **`mission_attempts` crossed the process boundary and was dropped** on the
  supervisor side. It is a field on `AgentRunResult` now: one result and three
  attempts is a model that argued with its own output and was refused twice.

Three more were style rather than behaviour: `class Mission` is `Submission`,
because `CONTEXT.md` reserves "Mission" for the packet and calls it "a payload,
not a lifecycle" while that class is the lifecycle side; `proposal.ELEMENTS`
was a second copy of the element names that `roster.CONTRACTS` already
declares, and is gone; and both new modules use `from redkraken import ...`
like every other module.

Two findings were considered and not taken. `state.bound` delegating to
`packet.fit` reads oddly -- the operator's compact read importing the Agent's
packet module -- but the alternative is two implementations of "which row goes
first", and an operator and an Agent reading the same Program should not
eventually disagree about that. And `proposals` has no `CONTEXT.md` glossary
entry, which by `docs/agents/domain.md` is a gap to note for `/domain-modeling`
rather than one to fill in passing: the runtime now has a staging record with
its own module, and "Promotion" is the only term that currently points at it.

### Verification

`tests/test_packet.py` is 43 tests and `tests/test_proposal.py` is 30, both
against a recording connection, and both hold the module to its own statements:
the compile's SQL is matched exactly rather than by substring, because two of
its queries read `v_records` and differ only in what they select.
`MissionPacketTest` in `tests/test_database.py` is 19 tests against the live
database with two Programs open at once, and it is where every criterion is
measured rather than argued -- the cross-Program reads, the proxy-internal lane
that is absent rather than refused, the digests checked against `v_records`, the
canonical snapshot, the eight drop reasons on real rows, and the read role's
lack of any write privilege anywhere.

The full suite is 1047 tests: three failures and one error, all four
pre-existing and environmental, identical on a clean tree at `876a486` --
`test_identity`, `test_proxy` and two `ProxyEgressTest` cases need a platform
that loads a client key without a plaintext file, which the uv CPython builds on
this machine are not.

### What the combined review changed

The review above was of this ticket alone against `1d52a32`. A second pass took
eighteen and nineteen together against `876a486...main`, because the pair is
what a run meets and neither review had seen the other's surface. Its findings
on the roster and the door are recorded in ticket 18; four landed here.

- **A Receipt label was unlearnable, the same way an Artifact label was.**
  `get_receipts` required `receipt_labels`, so the only way to name a Receipt
  was to already know its label -- and an Observation's provenance has to cite
  one. With no labels it lists what the packet reached now, paged by a `limit`
  the contract bounds like the other reads. Named labels still answer as they
  did, with `not_staged` for what the packet lacks; the listing path put those
  answers through `_page`, so they carry the section's `packet_bound` marker as
  well, which is the honest reading -- six Receipts this Program has did not fit
  the packet, so a label that is missing may be one of those rather than one
  that does not exist.
- **`_size` was written twice.** `packet._size` and `state._size` had the same
  docstring and differed only in the projection -- `row.as_dict()` against
  `item.summary()`. One `packet.sent_bytes(items, project)` now, called by both;
  the projection stays the caller's because only the caller knows the shape it
  sends.
- **`Result.from_dict` was dead.** Nothing constructed a `Result` that way. It
  is gone rather than kept for a caller that does not exist.
- **A docstring had gone false.** `Result.completion` said `completion_claim`
  is free text and pointed at `OPEN_ARGUMENTS` for why; ticket 18's patch closed
  it to `status` and `note`. The clamp is still right and its reason is now the
  real one: the contract closes the keys, not what the status says.

The contracts' `reads` also stopped naming only canonical tables. The compile
reads `v_records`, `v_evidence`, `v_artifacts` and `events`, and four contracts
named the tables behind those views instead -- so the roster described reads
that no longer happened. Each names the view first and then what stands behind
it, which keeps `tests/test_roster.py`'s check that every named relation exists
meaningful.

Two prose fixes rather than behaviour: `CONTEXT.md` reserves "Mission" for the
packet, and this ticket's modules still used it bare for the result -- an agent
run's result is what the glossary calls it, and the wire names
`submit_mission_result`, `mission_result` and `mission_attempts` keep the word
because renaming half a pair leaves a key nothing is called.

Three earlier findings stay defended rather than patched. Dropping
`v_surface`, `v_hypotheses` and `v_receipts` was deliberate and is argued
above -- they were granted to nobody and served no handler. `state.bound`
delegating to `packet.fit` is still the lesser of two evils. And the missing
glossary entries are still a note for `/domain-modeling` rather than something
to fill in passing.
