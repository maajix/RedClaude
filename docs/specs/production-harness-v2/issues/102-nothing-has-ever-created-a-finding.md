# 102 — Nothing in this tree has ever created a Finding

**What to build:** The caller for `open_finding`. This is the orchestrator
dispatch ticket that tickets 37, 38, 39 and 40 each deferred their model-facing
verb to and that has never existed, and it is the highest-priority finding in
the four wiring audits: without it there is no report at the end of a hunt.

**Blocked by:** nothing.

**Status:** ready-for-agent

- [ ] `open_finding(uuid, uuid, text, text, uuid)` acquires a caller in
      `src/redkraken/`. It is defined at
      `src/redkraken/migrations/20260815T120000Z__a_supported_claim_becomes_a_candidate.sql:758`,
      granted to `rk2_runtime` at `:917`, and it contains the only
      `INSERT INTO findings` in the corpus, at `:839`. `grep -rn open_finding
      src/redkraken/*.py` returns nothing. Every other mention of the name in
      the migrations is a comment, a `COMMENT ON`, a grant, or a standing check
      asserting a property of the function.
- [ ] The consequence is stated in the ticket in the form that makes the
      priority arguable rather than asserted. No `F` label has ever been minted,
      so: the `validate.judge` tool group is two Contracts
      (`src/redkraken/roster.py:855` and `:867`), a blind-validator role and a
      whole migration with no subject it can be handed; `rk finding validate`
      (`src/redkraken/cli.py:1278`) has nothing to queue; `rk report finding`
      (`cli.py:1497`) has nothing to project; and `rk evidence export`
      (`cli.py:1531`) has nothing to bundle. Tickets 36 through 43 all rest on a
      row this tree cannot produce.
- [ ] The shape of the caller is decided by a human before the work starts, and
      the decision is written into this ticket. Three shapes are available and
      the audits do not settle between them: a served Contract in a new tool
      group, on the pattern `sched.pick` already uses for a request the runtime
      fulfils; a CLI verb the operator runs, on the pattern
      `rk finding validate` already uses; or a runtime step in
      `src/redkraken/execution.py` taken when a Hypothesis reaches `supported`
      with a holding Test run. Whichever it is, the ticket says which and why,
      because the reason four tickets closed over this gap is that each named
      a fifth ticket rather than a mechanism.
- [ ] Whatever shape is chosen, the guard stays where it is.
      `rk2_finding_refusal` answers with a sentence rather than raising
      (ticket 36's criterion 6), so the caller files what it hears; a caller
      that turns that sentence into an exception would throw away the
      auditability ticket 36 built.
- [ ] Nothing is added to the schema. `open_finding`, its cell lock, its merge
      rule and its eight refusal arms all exist and are tested: `open_finding`
      appears eleven times in `tests/test_database.py`, including
      `OPEN_FINDING = "SELECT open_finding($1::uuid, $2::uuid, $3, $4)"`. What
      is missing is a line of Python, and the ticket says so rather than
      re-opening a settled design.
- [ ] Ticket 36 is amended with a dated correction note naming this ticket, and
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
