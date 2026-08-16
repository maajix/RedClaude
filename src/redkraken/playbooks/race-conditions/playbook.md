---
description: Ask whether a single-use action stays single when two copies arrive together, by establishing sequentially that the second copy is refused and then reading the count the target keeps after a concurrent pair.
bb:category: business_logic
bb:outputs: ["business_logic.replay"]
bb:triggers_all: ["authenticated_endpoint", "json_request", "state_changing_method"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: constrained
bb:effects: mutates_object
bb:baseline: pristine_surface
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 51 as the v2 replacement for v1's race-conditions pack, against the replay leaf of the ticket 18 vocabulary; the v1 race-conditions text is attached as a maintainer reference and is where the sequential control this Playbook insists on comes from.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_invariant", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "state_change", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "state_change", "polarity": "supports", "min_count": 1}]
bb:references: ["race-conditions-and-timing-attacks.md"]
---

# Ask whether once really means once

A single-use action is a check and a write with a gap between them. The gap is
usually a database round trip, and two requests that arrive inside it both read
"not used yet". Every application has this shape somewhere; the ones that are
correct hold a lock, a unique constraint or a conditional update across the gap.

The finding is never that two requests were fast. It is that the target's own
count says the action happened twice.

## 1. Name the action, the counter and the identity

The subject is a state-changing route that spends something once: a coupon, an
invitation, a withdrawal, a seat, a one-time token. Name the route that states
the count afterwards -- a balance, a redemption list, a remaining quota. Without
a counter this Playbook has nothing to read and does not apply to the subject.

One Identity label, held through `use-identity` for every call below. Two
labels would make this a question about two accounts, which is a different
class.

## 2. Record the pristine count

Read the counter before anything is sent and store the answer. `pristine_surface`
is the baseline because the whole claim is arithmetic on this number, and a
number another Playbook moved in between is a number this one cannot use.

## 3. Establish the invariant sequentially

Send the action once. Read the counter. Send the identical action a second time,
after the first has answered, and read the counter again.

That is the sequential control and this Playbook does not proceed without it. It
has to show two things: the action landed once (a `state_change` against step 2)
and the second, separate attempt was refused with the count unmoved. An
application that happily accepts the same action twice in sequence has no
single-use rule to break, and what looks like a race there is
`business_logic.workflow_order` or nothing at all.

If the control shows the action is repeatable by design, stop. There is no
invariant, so there is nothing for a concurrent pair to break.

## 4. Send the concurrent pair

Reset to the state step 3 started from, where the target offers a way -- a second
coupon of the same kind, a second invitation. Where it does not, say so: this
reading needs one unspent action and it cannot manufacture one.

Send two identical copies of the action at once through the same slot. Two, not
twenty. A burst large enough to be load is a different activity that this
Playbook does not authorise, and two is enough: the claim is that the count
moved twice, and two requests are what shows it with the smallest footprint on a
live target.

## 5. Read the count, and difference it

Read the counter and run `compare-responses` over this answer and the one step 3
ended with. Cite what the script returns.

Response codes from the pair are not the claim. Two `200`s prove nothing on
their own, because a correct application may well answer both and apply one. A
`500` from the loser is not evidence either. The count is the evidence.

A timing difference between the two answers is not this claim and is not
reported as it. That is `timing_differential`, it belongs to a different reading,
and treating it as a replay finding is the mistake this Playbook exists to
prevent.

## 6. State the claim, and state what would refute it

The Hypothesis is `business_logic.replay` on the route. It is supported when the
count after the concurrent pair shows the action applied more times than the
sequential control allowed. It is refuted when the count after the pair moves
exactly as far as the control's single success, whatever the two responses said.

Anything else is inconclusive: a counter that is not readable afterwards, a pair
where one call never completed, a target that rate-limited the second copy
before it reached the route.

## 7. Spend one thing, once, and say what it was

This Playbook's effects are `mutates_object`. It spends one single-use item on
purpose and the report names it, so an operator can see exactly what was
consumed. It does not race a withdrawal, a payout, a transfer or anything else
that moves money or notifies a third party; where the only single-use action on
the subject is one of those, the reading stops at step 3 and reports the
sequential control.

The cleanup is that there is none, and saying so is the point of stating it
before execution rather than after. A spent coupon does not come back, which is
what makes it single-use and therefore what makes it worth reading, so what is
bounded instead is the spend: two items at most, one for the sequential control
and one for the concurrent pair, both named in the report. A reading that has
already spent its second item does not go looking for a third. Where the target
does offer a route that restores the item, use it and say that the count was
restored, because an operator who can see the surface put back as it was is
being told something a Playbook cannot claim on its own.
