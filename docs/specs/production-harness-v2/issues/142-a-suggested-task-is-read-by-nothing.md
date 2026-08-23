# 142 — A suggested Task is read by nothing

**What to build:** A promotion pass over `suggested_tasks`, so that a Task an
Agent proposed becomes a real Task or becomes a `proposal_drops` row saying why,
and a Program that has finished its seeded recon has somewhere for its next
recon Task to come from.

**Blocked by:** nothing. Ticket 83 built `open_task` and this uses it unchanged.

**Status:** ready-for-agent

- [x] **`suggested_tasks` is read at all.** It is declared in the
      `submit_mission_result` Contract (`roster.py:800`, `roster.py:1057`),
      lands in `proposals.payload`, and before this ticket no SQL and no Python
      read it: those two declarations were the only mentions of the name in the
      source tree. Not promoted, not dropped, not counted -- which is the one
      thing 0020 says promotion may not do, *"a silent drop is indistinguishable
      from a thing the agent never proposed"*.
- [x] **Every element ends in exactly one of two states.** A `tasks` row opened
      through `open_task`, or a `proposal_drops` row naming the reason. There is
      no third outcome.
- [x] **The walk lives beside the other five.** `rk2_promote_tasks`, called last
      from `promote_proposal`, in the shape `rk2_promote_hypotheses` established.
      It resolves `subject_ref` through the caller's own ref map rather than
      through a second resolution that could drift from it, spends the same
      `proposal_drops.ordinal` sequence, and runs inside the transaction that
      already called `set_actor` and `set_cause` for it.
- [x] **The kinds this runtime cannot dispatch are refused at promotion.** Under
      `unopenable_kind`, with the sentence that refuses each one. `hunt` and
      `validate` are structural -- the element has no field that could name a
      Hypothesis or a Finding -- and `analyze` and `report` are facts about which
      role the roster gives the kind to.
- [x] **A subject that carries no address is refused under its own reason.**
      `no_address`, not folded into `no_subject`: the subject is fine as a
      subject and the agent that named a Domain should name the Application
      under it, whereas an agent told `no_subject` sends the same handle back.
- [x] **Breadth is bounded.** The ceiling is the Program's live queue depth
      against `scheduler_weights.slate_size`, read from the active weights row,
      recounted per element. A suggestion refused by it is told that it was the
      moment and not the suggestion.
- [x] **The account survives.** `open_task` writes the model's own sentence
      prefixed with the proposal that carried it, so 83's `check_opened_tasks`
      standing check still returns no rows over Tasks this walk opened.
- [x] **A model can learn from a drop.** The `submit_mission_result` description
      names the fields the walk reads and what it refuses, which is the rule
      `_launch.py` already states for every other element list: *"A field name a
      child has to guess is a `malformed_field` drop with no way for the model to
      learn the spelling."*
- [x] **The pass says what it opened.** `execution._promote` reports the Task
      labels, so "the run suggested nothing" and "everything it suggested was
      refused" do not read the same way to an operator watching the queue.
- [ ] **Reviewed and committed.** The implementation is in the tree uncommitted,
      on `worktree-bridge-cse_01KiwRdMnYkG1mJfM1GnDp5G`.
- [ ] **Checked by something that would go red.** Measured by hand against a
      scratch database copied from a finished hunt: every branch of the walk was
      exercised and `check_opened_tasks()` returned no rows. It is not yet a
      `tests/test_database.py` class, because that module rotates cluster-global
      role passwords at `:313` and the live engagement at
      `/home/majix/engagements/yekta-first-hunt-2026-08-22` was in flight while
      this was built.

## Why

Found during authorised live validation on 2026-08-22, the same six hunts ticket
140 was raised from. Every one ended after exactly two recon Tasks:

```
run 01 -> task_attempted
run 02 -> task_attempted
run 03 -> nothing_to_execute
```

The recon Agent proposed between two and five follow-up Tasks in every single
run -- naming Drupal paths, a contact form, a truncated body worth re-fetching
-- and every one of them was discarded in silence.

### The loop it closes, and the one it does not

140 is the other half of this and the two do not overlap. That ticket makes a
testable Hypothesis reach a hunt Task, which is the entrance to the Test,
Finding and chain machinery that has never run. This one makes a recon run reach
another recon Task, which is what keeps a Program alive long enough to produce a
claim worth grading. Neither is a substitute for the other: without 140 the
harness maps competently and never hunts, and without this one it stops mapping
after the configuration's own subjects are spent.

### What ticket 83 decided, and why this does not contradict it

83's preamble reads the schema as it then stood -- *"`promote_proposal` promotes
Observations, Surface and Hypotheses and not Tasks"* -- as the reason a fresh
Program needed a verb the runtime calls from the configuration. The decision it
took is its section 5, and it is one sentence: a model that could call
`open_task` would be a model minting its own work. That revoke is untouched
here. A suggested Task arrives as staging data on a payload the child cannot
promote, is read after the child has exited, and is decided by the runtime with
the gauntlet `open_task` already applies -- this Program's Entity, a target of
the live scope, no live duplicate, and a row `ready_for` would let the scheduler
act on. What the model contributed is a subject and a sentence.

83 also predicted the shape of the answer: its section 4 opens `recon` and
nothing else, *"because it is the one kind whose input is the configuration and
nothing else"*. A suggestion carries a subject and a sentence, and `recon` is the
one kind whose whole input that is.

The one place the two do pull against each other is growth, and it is real: a
Task is the only promoted element that is work rather than a record, and work
that ends in another payload of suggestions. The ceiling is not a safeguard
bolted onto the feature, it is the half of it that keeps the rest consistent
with 83.

### The two hazards, both measured

**An undispatchable Task refuses the whole pass.** An `analyze` Task opened by
hand against an Application in `rk2hunt4` did not run; the next `rk run` refused
the entire pass, `ok: false`, exit 3:

```json
{"code": "invalid_configuration", "source": "roster",
 "detail": "a js_analyst run holds no net.request; this slice serves one target request and T3 needs a role that may make it"}
```

`reporter` fails one step earlier as a renderer with no served surface. Both are
`ledger.fail` and `_pass` claims one Task per pass, so one such Task at the top
of the ranking is every later pass refused. Refusing the kind at promotion is
83's own move applied one step further out; fixing the routing would reverse a
roster decision taken on purpose, and making the refusal skip the Task rather
than the pass is a defect that predates this walk and is not this walk's to
hide. Ticket 143.

There is a second way to be undispatchable and the live payloads are full of it.
Of the twenty-four suggestions the six hunts made, eleven named an Application,
three named an Endpoint, seven named a Domain and three named nothing that
resolves. `execution.STARTED` resolves a target URL from an Application or an
Endpoint under one and from nothing else, so those seven would each have reached
the target step and been refused there -- again the whole pass.

**Unbounded growth.** Every recon run proposed two to five Tasks and each Task
opens a run that proposes more. Total spend is already bounded, and bounded
where it belongs: `[budgets]` states `requests = 1200` and `tokens = 2000000`
for the campaign against `run_requests = 40` and `run_tokens = 250000` for one
run, so a campaign affords between eight and thirty runs and then `_rotate`
closes it. What is unbounded is the queue, and a campaign whose budget goes on a
breadth-first sweep of everything anybody mentioned has spent it as surely as
one that overran. 140's fifth criterion asks the same question of hunt Tasks and
should reach the same answer or say why not.

## Notes

The walk is `rk2_promote_tasks` in
`src/redkraken/migrations/20261008T000000Z__a_suggested_task_becomes_a_task_or_a_drop.sql`,
and the whole of the reasoning above is written into that file's preamble
because that is where the change lands.

Three reasons are added to `proposal_drops.reason`: `unopenable_kind`,
`no_address` and `queue_at_ceiling`. Each names a different thing for the agent
to do next, which is the test tickets 021 and 33 applied when they widened that
vocabulary. Everything `open_task` itself refuses arrives as
`refused_by_invariant` carrying that function's own sentence, which is what the
Entity and Relationship walks already do with a raised invariant.

`tools/check_wiring.py:1288` has mapped `suggested_tasks` to `tasks` since it
was written. The gate has been asserting a promotion that did not exist.
