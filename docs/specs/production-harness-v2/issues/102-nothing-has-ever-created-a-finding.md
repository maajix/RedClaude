# 102 — Nothing in this tree has ever created a Finding

**What to build:** The caller for `open_finding`. This is the orchestrator
dispatch ticket that tickets 37, 38, 39 and 40 each deferred their model-facing
verb to and that has never existed, and it is the highest-priority finding in
the four wiring audits: without it there is no report at the end of a hunt.

**Blocked by:** nothing.

**Status:** resolved

- [x] `open_finding(uuid, uuid, text, text, uuid)` acquires a caller in
      `src/redkraken/`. It is defined at
      `src/redkraken/migrations/20260815T120000Z__a_supported_claim_becomes_a_candidate.sql:758`,
      granted to `rk2_runtime` at `:917`, and it contains the only
      `INSERT INTO findings` in the corpus, at `:839`. `grep -rn open_finding
      src/redkraken/*.py` returns nothing. Every other mention of the name in
      the migrations is a comment, a `COMMENT ON`, a grant, or a standing check
      asserting a property of the function.
- [x] The consequence is stated in the ticket in the form that makes the
      priority arguable rather than asserted. No `F` label has ever been minted,
      so: the `validate.judge` tool group is two Contracts
      (`src/redkraken/roster.py:855` and `:867`), a blind-validator role and a
      whole migration with no subject it can be handed; `rk finding validate`
      (`src/redkraken/cli.py:1278`) has nothing to queue; `rk report finding`
      (`cli.py:1497`) has nothing to project; and `rk evidence export`
      (`cli.py:1531`) has nothing to bundle. Tickets 36 through 43 all rest on a
      row this tree cannot produce.
- [x] The shape of the caller is decided by a human before the work starts, and
      the decision is written into this ticket. Three shapes are available and
      the audits do not settle between them: a served Contract in a new tool
      group, on the pattern `sched.pick` already uses for a request the runtime
      fulfils; a CLI verb the operator runs, on the pattern
      `rk finding validate` already uses; or a runtime step in
      `src/redkraken/execution.py` taken when a Hypothesis reaches `supported`
      with a holding Test run. Whichever it is, the ticket says which and why,
      because the reason four tickets closed over this gap is that each named
      a fifth ticket rather than a mechanism.
- [x] Whatever shape is chosen, the guard stays where it is.
      `rk2_finding_refusal` answers with a sentence rather than raising
      (ticket 36's criterion 6), so the caller files what it hears; a caller
      that turns that sentence into an exception would throw away the
      auditability ticket 36 built.
- [x] Nothing is added to the schema. `open_finding`, its cell lock, its merge
      rule and its eight refusal arms all exist and are tested: `open_finding`
      appears eleven times in `tests/test_database.py`, including
      `OPEN_FINDING = "SELECT open_finding($1::uuid, $2::uuid, $3, $4)"`. What
      is missing is a line of Python, and the ticket says so rather than
      re-opening a settled design.
- [x] Ticket 36 is amended with a dated correction note naming this ticket, and
      its `**Status:** resolved` is left alone. The work ticket 36 describes was
      built; what was never true is that anything reaches it.

## Why

`docs/research/wiring/21-agent-surface-wiring.md` section 3.2 calls this "the
worst finding in this sweep" and section 3.4 explains how it survived: four
tickets each deferred the model-facing verb to an "orchestrator dispatch
ticket", and each was then marked `resolved`. That fifth ticket is not in the
tree. This is it.

Ticket 36 is the one of the four with no such note at all. Report 21 section 3.4
says so directly: its "What is not covered" section discusses severity above
`info` and `duplicate_of_finding_id` and says nothing about a caller, which is
why this one is purely accidental rather than deferred.

The repo already names this defect class for the SQL side, at
`src/redkraken/integrity.py:4-8`: "The defect that registry exists to prevent is
a checker with no caller: nine of the prototype's twelve had none, and four live
defects survived in the gap." That gate looks at `check_*` functions and at
nothing else. Ticket 130 is the gate that would look here.

## The decision, taken 2026-08-21

**The model asks and the runtime writes.** Of the three shapes the criterion
offered, the served Contract is the one chosen, on the pattern the request
Contracts already use: a child proposes a Finding and the runtime is what calls
`open_finding`. It is not a CLI verb, because a hunt that needs an operator at
the keyboard to record what it found is not a hunt that runs; and it is not an
automatic runtime step on `supported`, because the judgement of what is worth
reporting is the one judgement in this path that belongs to the party that did
the hunting.

The Contract may not declare `findings` in `writes`. `findings` is a canonical
table and the roster refuses a Contract that names one, which is the rule that
makes this a request rather than a write in the first place. The child names a
Hypothesis, the Test run that settled it, a vulnerability class and a title; the
runtime calls `open_finding` with them and answers what it heard back.

## What stops a child spamming the claim

Most of it is already built, and the ticket says so rather than building it
twice.

**A child cannot invent a Finding.** `rk2_finding_refusal`
(`20260815T120000Z:580-663`) is eight rules deep and every one of them is about
a row the runtime itself wrote. The Hypothesis has to exist in this Program, be
`supported`, and not be superseded. The Test run has to exist in this Program,
be a run of a Test of that same claim, have concluded `holds`, and be lane
`replay`. And it has to be *the* run that settled the claim: the transition from
`testing` to `supported` cites a Receipt, that Receipt has to be one of this
run's, and the transition's actor has to be `runtime`. A child that has not
actually demonstrated anything cannot get past rule two.

**A second claim on the same cell merges rather than multiplying.**
`open_finding` takes an advisory lock on the cell and returns the existing row
with `outcome = 'merged'` when one is there (`:825-838`). Ten proposals about
one finding are one `findings` row.

**Every attempt is recorded beside `findings` and not inside it.** A refusal
writes a `finding_proposals` row and returns a sentence rather than raising
(`:800-806`), which is what keeps the record of the attempt.

**What is left to build is the ceiling on refused attempts.** The one surface a
loop can still fill is `finding_proposals`, and the one cost it can still spend
is the run's own context. So: a bounded number of refused proposals per agent
run, after which the tool answers a refusal token like every other refusal in
this runtime rather than reaching the function at all. A merged or created
proposal does not count against it, because that is a child that got it right.

## What the Finding unblocks, which is criterion 2 stated forward

Every consequence the criterion lists is a consumer waiting on an `F` label, and
each of them has one for the first time once a proposal is answered. The
`validate.judge` group stops being two Contracts and a role with nothing to
judge: `mcp__rk2__get_validation_packet` takes a `finding_label` and
`rk2_validation_packet` builds a document out of a `findings` row, and neither
has ever had a row to build one from. `rk finding validate` (`cli.py:1278`)
queues a Finding for that session. `rk report finding` (`cli.py:1497`) projects
one. `rk evidence export` (`cli.py:1531`) bundles the Observations a Finding
cites, which is the `finding_evidence` edge set `open_finding` writes in the
same statement that creates the row. Tickets 36 through 43 all rest on the same
row, which is why one missing caller reads as eleven dead verbs in the audits
rather than as one.

## What was built

**The Contract, at `src/redkraken/roster.py`.**
`mcp__rk2__propose_finding` is a `REQUEST` in the `state.propose` group, writing
`finding_proposals`. It is in `state.propose` and not in `sched.pick` because
deciding that something is worth reporting belongs to the party that did the
hunting, and `_check_authority` already keeps those two groups off one role --
so the three executing roles hold it and the orchestrator, the validator and the
reporter do not. `findings` is not in `writes` and could not be: it is a
canonical table, the compile refuses a contract that names one, and that refusal
is the rule that made this a request rather than a write.

Three arguments rather than the four the decision names. The proposal carries
`hypothesis_label`, `vulnerability_class` and `title`, and it does not carry the
Test run that settled the claim, because there is no name for one: `test_runs`
has no label column and a packet publishes Entities, Hypotheses, evidence edges,
Receipts and Artifacts and no Test at all, so a run argument would be a field no
child could fill. Nothing is given up. The settling run is pinned by the claim --
the transition from `testing` to `supported` cites one Receipt and that Receipt
belongs to one run -- so naming the Hypothesis names the run, and arm seven of
`rk2_finding_refusal` would refuse a proposal that named any other.

The class is a pattern and not an enum, which is the opposite of the choice
`run_tool` makes about its own binaries and right for the same reason that one
is. A binary is a program this harness starts and the closed list is the
authority; a vulnerability class is a word from a seeded table later tickets add
rows to, and an enum here would be a second copy of that table which goes stale
the first time somebody extends it. Arm eight of `rk2_finding_refusal` answers an
unknown class by naming it, so the vocabulary refuses out of the table that
declares it.

**The ask, at `src/redkraken/_launch.py`.** `Proposal` is the child's half and
`_finding` is the tool. It is the one request on this surface that is answered
while the run is still going, and the difference from a pick or a verdict is the
reason it is: those two are preferences the runtime re-decides afterwards
against state that moved while the model was thinking, and this is a question
about rows that have already settled it. So the proposal goes down the same pipe
a tool run goes down -- one object out, one object back, on the two file
descriptors the launch already has -- and what comes back is what `open_finding`
said.

Nothing on the child's side decides whether the Finding may be opened. The
handler carries the three fields and reports what came back, including a
refusal, which is reported as a refusal rather than as a tool that failed. That
is criterion 4: `rk2_finding_refusal` answers with a sentence so that the caller
can file what it hears, and a caller that turned that sentence into an exception
would throw away the auditability ticket 36 built.

## The ceiling, and why a refused attempt counts and a successful one does not

`_launch.REFUSED_PROPOSALS` is three. The number comes from the refusal rather
than from taste: `rk2_finding_refusal` is eight arms deep and exactly two of them
are about the proposal rather than about the evidence behind it -- the word is
not in the vocabulary, and the title is empty. Those two are the only refusals a
child can do anything about by asking again; the other six describe rows the
runtime wrote and the child cannot change by re-sending. Three attempts is one
more than the number of correctable mistakes, and a fourth refusal is a run
repeating itself.

Refused attempts are counted and created and merged ones are not, because they
are different acts. A refusal costs the Program a `finding_proposals` row and the
run a turn's worth of its own context and leaves behind nothing anybody wanted. A
merge is a second claim landing on a cell a Finding is already open on, which is
the outcome that records that two independent claims about one cell both held --
a hunter that got it right twice. Counting a merge against the ceiling would make
the run that found the most into the run that is cut off first, which is a
ceiling on how much a hunt may find rather than on how long it may argue.

Past the ceiling the tool answers `proposals_spent` and asks nobody, which is
the ticket's "rather than reaching the function at all": the refusal is a token
like `no_capability` and `no_tooling`, so the model reads one of these and the
runtime reads the same one out of the transcript. A supervisor that could not be
reached, or that would not serve the verb, is not charged against the ceiling: a
ceiling on refusals is a ceiling on what the run got wrong, and nobody looked at
that proposal at all.

## The half that closes it, at `agent.py` and in one migration

`propose_finding(text, text, text, uuid)` is the verb, and
`_Tools.__call__` is the third arm of a dispatch that was a closed two-tuple.
The supervisor is where the call has to land because it is the only side
holding an `rk2_runtime` connection: a child's one network reaches the
capability proxy, so a proposal a child could file itself would be a row filed
by the party the row is about.

The label resolution is a verb rather than three queries in Python, and the
reason is that it is a join and not a lookup. The run that settled a claim is
named nowhere on the claim: it is reached through the transition from `testing`
to `supported` that the runtime recorded, the Receipt that transition cites and
the Test run that Receipt belongs to -- which is the path arm seven of
`rk2_finding_refusal` already walks to refuse a proposal naming the wrong run.
Written in Python it would be a second copy of arm seven in a second language,
free to drift from the arm it has to agree with; written beside it, the two are
read together by anybody changing either.

The latest such transition is taken and not the first, because a claim that
went back to `testing` and forward again is settled by the second passage, and
the Finding rests on the settlement in force.

One refusal is the wrapper's own and the rest are `open_finding`'s. A label this
Program does not hold is answered by naming the label, because handed a null
uuid `open_finding` would answer "<NULL> is not a Hypothesis of this Program",
which tells a child nothing about the word it actually said; and the record of
that attempt is filed in `finding_proposals` like every other refusal rather
than skipped for having failed early. A claim with no settling run is passed
through as a null run instead, so `open_finding` answers out of its own arms in
their own order -- which puts the honest reason first, since a child whose claim
is still `proposed` should be told that and not told a run is missing.

Nothing new is in the schema, which is criterion 5: `propose_finding` writes one
row on one path and otherwise only resolves and calls. Its grant carries a
`runtime_verb_surface` row, because 066's `check_runtime_privileges` refuses a
verb the runtime can execute that no row declares -- and it refused this one
until the row was written, which is that registry doing its job on the first new
grant since it was seeded.

## What was measured

Against a scratch database with the whole corpus applied, using ticket 36's own
`CandidateFindingTest` arrangement -- a Test stored, replayed through the door
and closed, so the transition the guard reads is one the runtime wrote:

    propose_finding('H1', <class>, 'reached through the label', NULL)
      -> {"outcome": "merged", "finding": "F1", "hypothesis": "H1", ...}

    propose_finding('H9999', <class>, 'a claim of nobody', NULL)
      -> {"outcome": "refused",
          "refusal": "H9999 is not a Hypothesis of this Program"}

and the refused attempt left one more `finding_proposals` row than it found. The
first line is the first `F` label this tree has ever minted through a caller.

The migration applies clean and re-applies clean with the ninety-six standing
checks green, which is the corpus's own answer to whether the new grant is
declared.

## What is owed to `tests/test_database.py`

The two measurements above as permanent cases, on `CandidateFindingTest`'s
fixture: a label reaching `open_finding` and answering the Finding it opened,
and an unknown label refused by name with the proposal still on file. They are
not written here because that file was another agent's for the length of this
pass. The migration's own `DO` block asserts the grant, the registry row and
that a proposal naming no claim can still be filed, which is the part a file
reader can hold on its own.
