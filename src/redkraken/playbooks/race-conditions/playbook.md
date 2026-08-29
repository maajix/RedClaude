---
description: Ask whether a single-use action stays single, by reading the count a target keeps before anything is sent and then spending one value twice inside a Test whose own assertions difference that counter.
bb:category: business_logic
bb:outputs: ["business_logic.replay"]
bb:triggers_all: ["authenticated_endpoint", "json_request", "state_changing_method"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: constrained
bb:effects: mutates_object
bb:baseline: pristine_surface
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 51 as the v2 replacement for v1's race-conditions pack against the replay leaf of the ticket 18 vocabulary, and rewritten for ticket 101 against the merged ledger's four readings for this slug. Ticket 211 is what moved the sequential reading onto the Finding path, because a Test action now states the body it plans and the single-use value this Playbook's triggers declare rides one. All three evidence rows now name response_differential, because the counter reads are actions of the Test and close_test_replay writes their Observations from the specification, while an agent-filed state_change citing a counter read cannot be added once the first recorded action has moved the claim past proposed; the concurrent pair the shipped step 4 asked for is blocked and the single-packet forms are refused, and both are named at the end rather than dropped.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_differential", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "response_differential", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "response_differential", "polarity": "supports", "min_count": 1}]
bb:references: ["race-conditions-and-timing-attacks.md"]
---

# Ask whether once really means once

A single-use action is a check and a write with a gap between them. The gap is
usually a database round trip, and the applications that are correct hold a
lock, a unique constraint or a conditional update across it. The finding is
never that two requests were fast. It is that the target's own count says the
action happened twice.

A live read is sent with `mcp__rk2__http_request`, and the spend is an action
of a Test proposed with `mcp__rk2__propose_test`, so the replay lane performs
it once under a Receipt rather than once here and once again there. The writer
of a settlement is close_test_replay, which derives the transition and the
Observation kind from the Test's own assertions alone. The counter reads are
actions of that Test, so the Observations this Playbook's bar names are the
lane's own -- response_differential for a read a differing assertion names --
and an agent-filed edge citing one of those Receipts cannot be added, because
the first recorded action moves the claim past proposed. Since ticket 211 an
action states the body
it plans, which is what puts the reading below on the Finding path at all,
while a setup or cleanup step still carries a method and a url and nothing
else. Every Test here performs at least three actions and fills all three roles
-- baseline, variant and control.

## 1. Name the action, the counter and the identity

Read the route and the counter from the state view with
`mcp__rk2__get_attack_surface`. The subject is a state-changing route that
spends something once -- a coupon, an invitation, a seat, a one-time token --
beside a route that states the count afterwards, a balance, a redemption list,
a remaining quota. Without a counter this Playbook has nothing to read and does
not apply to the subject.

One Identity label, held through `use-identity` for every call below. Two
labels would make this a question about two accounts, which is a different
class. The step does not choose that Identity and there is no argument for it:
the Task was opened under one, and every action inherits it.

Where the only single-use action on the subject moves money, pays out, or
notifies somebody who is not the Program, do not spend it. Park the Task with
`mcp__rk2__park_for_human`, whose call carries that Task's label in
`task_label` and third_party_impact in `question_code`, naming the action and
what it would send, and let a person decide.

Nothing in this step is graded. Naming is what makes the Test below proposable.

## 2. Read the pristine count

Read the counter before anything is sent and keep the answer with its Receipt.
That number is pristine_surface in the frontmatter and the arithmetic
everywhere below, and a number another Playbook moved in between is one this
reading cannot use.

Read it a second time, unchanged. A counter that disagrees with itself before
any spend is one no later difference can be attributed to, and that verdict is
inconclusive and names the counter rather than the route.

This step sends live reads with `mcp__rk2__http_request`, files them with the
proposal through `mcp__rk2__submit_mission_result`, and closes no Test, so it
grades nothing.

## 3. Spend it once, then again, inside one Test

Propose one Test with `mcp__rk2__propose_test` holding seven actions in order,
which is all three roles. Action 1, role baseline, reads the counter before
anything is spent. Action 2, role baseline, submits the single-use value,
stating the JSON body ticket 211 admits. Action 3, role control, reads the
counter again and has to show the action landed exactly once. Action 4, role
variant, submits the identical value a second time, after the first has
answered. Action 5, role variant, reads the counter again. Action 6, role
control, submits a value of the same shape that was never issued, and action 7,
role control, reads the counter once more, without which a second success is
consistent with a route that accepts anything at all.

The Test names body_differs on action 5 against action 3, and body_equals on
action 7 against action 5. The first assertion is the claim, that the count
moved twice for one value. The second says the movement belongs to the value
that was replayed rather than to any value of that shape. The lane writes
response_differential for the reads a differing assertion names and
response_invariant for the arms none does, and those are the Observations this
bar asks for. No agent-filed edge cites a counter read here, because a counter
read is an action of the Test and its Receipt arrives after the claim has left
proposed; what the agent files with the proposal is section 2's pristine pair.

Where the target takes the single-use value in the path or the query instead,
spell it there and the same Test closes unchanged. No arm spells a dot segment
or a percent-encoded dot: the replay lane refuses a specification url carrying
either, so an arm spelled that way is performable and ungradeable.

## 4. Difference the counter, and state the claim

Run `compare-responses` over the two counter Artifacts with
`mcp__rk2__run_skill_script`, whose `first` and `second` are the read before
the second submission and the read after it, and cite what the script returns
rather than an impression of two bodies.

Response codes from the two submissions are not the claim. Two answers of 200
prove nothing on their own, because a correct application may well answer both
and apply one, and a 500 from the loser is not evidence either. The count is
the evidence.

This section proposes no Test of its own and grades nothing. Propose the claim
with `mcp__rk2__propose_finding`. The Hypothesis is `business_logic.replay` on
the route. It is supported when the count after the second submission moved
again, which is what the Test asserted. It is refuted when the count is unmoved
between the two reads, whatever the two responses said, and that refutation
carries the same response_differential the supported leg does, because
close_test_replay reads the kind off the specification and one role writes one
kind either way. Anything else is
inconclusive: a counter not readable afterwards, a submission that never
completed, a route that rate-limited the second copy before it arrived.

## 5. The clock rides beside this and stops at an Observation

A route whose duration varies with the value under test is a real reading and
it is not this one. Receipts carry ts_arrival, ts_egress and waited_ms, so the
measurement exists, and timing_differential is evidential from a Receipt, which
the agent files through `mcp__rk2__submit_mission_result`.

It stops there, and this step cannot become a Finding. No assertion kind is
time-shaped -- the four are status_equals, status_differs, body_equals and
body_differs -- so no Test can close on a duration, and a Finding is refused
without a closed Test joined to the very run it cites. Take the reading as a
lead and say so in the record: the baseline is the route answered for a value
certain not to exist, sent repeatedly because a duration is noisy; the variant
is the same route for a value certain to exist; the control is a syntactically
invalid value, which separates unknown from bad input. Hand it to the Playbook
that owns information_disclosure.identifier_oracle, which is
`exceptional-conditions` since ticket 101, and record that no Test closed.

## 6. What is spent, and what this Playbook cannot send

Effects are mutates_object and the cleanup is that there is none, which is
worth stating before execution rather than after. A spent coupon does not come
back, which is what makes it single-use and therefore worth reading, so what is
bounded instead is the spend: two items at most, both named in the report, and
a reading that has spent its second does not go looking for a third. Where the
target offers a route that restores the item, use it and record that the count
was restored.

Two readings are named here and performed nowhere. The concurrent pair -- two
identical copies released in one window, against a control of two simultaneous
submissions of DISTINCT valid items, which must legitimately credit twice -- is
blocked, because no primitive releases two requests at once.
`mcp__rk2__http_request` is one call returning one response and has no batch
argument, `mcp__rk2__browse` is an ordered list of steps, and the roster's
concurrency is run scheduling, clamped to free Identity leases on purpose, so
two runs cannot stand in for one slot's pair either. A passed sequential Test
is not a passed race test and is not reported as one, and failing with two
requests does not show a target is safe. The single-packet form, with its
HTTP/1.1 last-byte and HTTP/3 last-frame relatives, is refused by decision: it
needs control over frame flushing and the last-byte write that no argument
expresses, and a burst wide enough to be indistinguishable from load is the
thing most likely to have an engagement stopped.

This section performs nothing and grades nothing.

5 of 6 steps cannot be graded.
