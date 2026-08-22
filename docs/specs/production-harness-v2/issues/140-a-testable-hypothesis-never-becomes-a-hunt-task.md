# 140 — A testable Hypothesis never becomes a hunt Task

**What to build:** The derivation that opens a hunt Task against a Hypothesis
the runtime has already graded `testable`, so that the first Test of a Program
is reachable from recon rather than only from a Finding that no Program can
reach without one.

**Blocked by:** 139 — A recon mission never asks for the Hypothesis it may propose; 144 — Every Hypothesis a run files is dropped for the shape of its rationale.

Nothing on the capability side: this was built against a Hypothesis inserted by
hand. Both blockers are what give it something to derive from in a live hunt
rather than in a fixture.

**Status:** resolved

- [x] **The closed loop is stated in the ticket that closes it.** Exactly two
      statements in the corpus create a Task of kind `hunt`:
      `20260819T000000Z__a_chain_unlock_earns_its_place_in_the_queue.sql:375`,
      whose `rk2_chain_unlock_frontier` requires a sound chain, a standing pivot
      stamp and a Finding; and
      `20260816T000000Z__impact_is_authorized_before_it_is_proved.sql:1267`,
      which takes a Finding as its argument. A Finding is opened from a
      Hypothesis at `supported`; a Hypothesis reaches `supported` through a Test;
      a Test is what a hunt Task runs. Every entrance to the loop is inside it.
      The loop has a second break in it, one step earlier, and the criterion
      below names it: a promoted claim never leaves `proposed`.
- [x] **The step before this one is answered first: nothing ever makes a claim
      testable.** `hypotheses.status` defaults to `proposed`
      (`0007_epistemics.sql:65`) and `rk2_promote_hypotheses` never transitions
      it. A status change is an `INSERT INTO hypothesis_transitions`, and of the
      nineteen statements in the corpus that write one, not a single one names
      `proposed` as its `from_status`. The rule exists and is legal:
      `transition_rules` carries `proposed -> testable` with
      `required_actor_kind = 'runtime'`, `requires_receipt = false` and no
      evidence minimum. 007 wrote that row as `llm` and one of the two 20260814
      migrations narrowed it to `runtime`, which settles the shape -- this is a
      runtime judgement about a claim the runtime has already graded, not a verb
      a model asks for, so it belongs beside `derive_chain_unlocks` in the
      ranking pass rather than on the roster. Measured on a copy of `rk2hunt5`:
      a well-formed Hypothesis promotes cleanly to `H1`, `hypothesis_transitions`
      holds zero rows, and `H1.status` is `proposed` and stays there. Without
      this step the frontier below is empty by construction.
- [x] **`open_task` is read before a second door is cut.**
      `20260831T000000Z__a_program_opens_the_first_task_of_its_own_scope.sql`
      takes a kind and a subject and nothing else, so it cannot set
      `hypothesis_id`, and `ready_for` at `0023_scheduler_ranking.sql:468`
      refuses a hunt Task that has none. Whether this derivation calls
      `open_task`, widens it, or sits beside it as `derive_chain_unlocks` does is
      the shape decision this ticket makes. Beside it is the obvious reading:
      `derive_chain_unlocks` already mints Tasks with a `hypothesis_id` inside
      the ranking pass and is the closest thing in the corpus to what this needs.
      Measured rather than reasoned: on a copy of `rk2hunt5` with `H1` moved to
      `testable` by hand, `rank_pass('probe')` answers `"unlock_candidates": 0`
      and `"ranked": 0`, and the Task table still holds the two finished recon
      Tasks and nothing else. The ranking pass sees a testable claim and has
      nothing to do with it.
- [x] **The frontier is defined by what a Test needs, not by what exists.** A
      candidate is a Hypothesis of this Program at `testable`, whose subject is
      still on the Surface and still a target of the live scope, and that no hunt
      Task already names in any status. `derive_chain_unlocks` guards on any
      status rather than a live one for a reason it writes down -- *"A Task that
      ran and finished is an answer; deriving it again next pass because the
      answer was disappointing is a loop with a database behind it"* -- and the
      same reasoning applies here unchanged.
- [x] **Breadth is bounded before it is measured in production.** A recon run
      proposing five claims would open five hunt Tasks, each of which may propose
      more. The `[budgets]` block already bounds requests, tokens and
      concurrency, and `novelty_for` and the ranking already decide order. What
      is missing is a ceiling on how many claims one pass may turn into work.
      Decide where it belongs and say why.
- [x] **The recorded decision this contradicts is answered, not stepped over.**
      The 20260831 preamble states: *"Every production `INSERT INTO tasks` in
      this schema is downstream of a Finding or a Hypothesis, and a Program that
      has just been opened has neither."* This ticket is the second half of that
      sentence being made true -- downstream of a Hypothesis is a case the
      sentence names and the corpus never built. Write that where the next reader
      meets it.
- [x] **Checked by something that would go red.** A derivation with no Hypothesis
      to derive from returns zero and looks correct, which is how this gap
      survived. The test has to stage a `testable` Hypothesis, run the pass, and
      assert both the Task that appears and the second pass that does not
      duplicate it.

## Why

Six live hunts against a real target on 2026-08-22 (`rk2hunt` through
`rk2hunt5`) each ended the same way after exactly the two recon Tasks a Program
opens for itself:

```
run 01 -> task_attempted
run 02 -> task_attempted
run 03 -> nothing_to_execute
```

Every one of the seven defects found on the way there was in the first stretch:
the door refusing the model's own control plane, the Agent home the child could
not write, a token ceiling below the cost of a bare turn, the unreachable `kind`
enum, Observations with no subject, elements citing no Receipt, and a role that
holds no `net.request` being handed a Task that needs one. All of them were
found because something ran. Nothing past the recon Task has ever run, so
nothing past it has ever been measured: zero Tests, zero Findings, zero kill
chains, in this tree, ever.

This is the one gap that makes the rest unmeasurable. Ticket 103 builds callers
for the six verbs between a validated Finding and a sound kill chain, and ticket
101 rewrites the Playbook corpus that tells a hunting role how to ask; neither
can be exercised while no hunting role is ever dispatched. The harness maps a
surface competently and cannot yet look for anything on it.

## What was built, 2026-08-22

`src/redkraken/migrations/20261012T000000Z__a_proposed_claim_becomes_work.sql`.
Three functions and one replacement.

`rk2_gradable_claims(program)` is the five conditions a proposed claim has to
meet before a Test could settle it: on the Surface, not superseded, all three
keys of `rk2_rationale_keys()` answered non-emptily, at least one supporting
Observation, and not a property class `transport_makeability` grades
`probe_only` or `unmakeable`. That last one is the exception list rather than
the allow list -- five transport classes are graded there and the other
fifty-two classes are makeable by a role holding `net.request`. Grading a
`probe_only` claim testable would dispatch a hunt run that cannot form the
request, which is the same defect as the `analyze` Task handed to a role holding
no `net.request` that abandoned a live run earlier the same day.

`rk2_hypothesis_hunt_frontier(program)` is the testable claims no hunt Task
names in **any** status, guarded the way 20260819 guards the same thing and for
the reason it wrote down.

`derive_hypothesis_hunts()` grades, then opens Tasks oldest-claim-first up to
`scheduler_weights.max_hunts_derived_per_pass`. `actor_kind` is the literal
`runtime`, which the rule requires and which is what the judgement actually is.

The ceiling bounds the Tasks and not the grading. `testable` is a statement
about the claim -- that a Test could settle it -- not about the schedule, and a
ceiling on grading would make a claim's status depend on how busy the pass was.
It lives in `scheduler_weights` because that row is immutable and versioned:
changing the ceiling inserts a version and activates it, and a Task keeps the
`ranked_weights_version` it was ranked under.

`rank_pass` calls it at step (3c), after the chain unlocks and before the
ranking, so a Task derived from a claim is ranked in the pass that derived it.

### Measured

Against a copy of `rk2hunt5` carrying one promoted, well-formed claim at
`proposed`:

```
rank_pass('probe')  ->  "claims_graded": 1, "hunts_derived": 1, "ranked": 1
```

Before this migration the same call answered `"unlock_candidates": 0,
"ranked": 0` and the Task table held the two finished recon Tasks and nothing
else. T3 is now `hunt`, `pending`, and `ready_for` answers NULL.

Idempotence: a second pass answers `"graded": 0, "derived": 0`. The three
refusal arms were exercised one at a time -- a claim with no supporting
Observation and a claim with an empty `falsifier` both stay `proposed` while a
complete claim beside them is graded. With `max_hunts_derived_per_pass = 1` and
four gradable claims, four passes answer `derived: 1` each and `deferred` counts
down 3, 2, 1, 0.

### The test that would go red

`tests/test_database.HypothesisHuntTest`, six tests on live rows, beside
`ChainUnlockTest` because it is the sibling derivation. Three Programs, each one
an arranged reason for the answer: a whole claim that must become work, broken
claims that must not, and a ceiling that must defer rather than drop. Ran 6
tests, OK.

Two of the refusal arms could not be staged, and finding out why was worth more
than the cases would have been. A fenced Program cannot hold a transport claim
of either graded kind: `transport_hypothesis_guard` refuses an `unmakeable`
claim at INSERT, and a `probe_only` claim can exist but can never be supported,
because `transport_evidence_guard` demands a `transport_parameters_observed`
Observation and `transport_observation_guard` refuses one citing an intercepted
agent-lane Receipt -- which is every Receipt a fenced Program has.

So the makeability arm refuses nothing that reaches it today. It stays, because
ticket 93 takes the unintercepted transport measurement, and the moment a
Program holds one a `probe_only` claim can carry real support and the arm is
what keeps it in the probe lane where it belongs. Written into the test's own
docstring rather than left for the next reader to rediscover.

### Not yet reachable from a live hunt

Ticket 144. A live hunt on 2026-08-22 (`rk2hunt6`) filed four Hypotheses -- the
first this tree has ever seen a model propose after ticket 139 asked for them --
and all four were dropped `malformed_field` for writing `rationale` as a
paragraph rather than an object. Until that is fixed this derivation is correct
and has nothing to derive from.
