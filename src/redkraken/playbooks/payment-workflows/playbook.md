---
description: Ask whether an amount the rules forbid is accepted, by stating the invariant and the pristine total first, sending one order with the quantity or price edited, and reading the total the target itself computes.
bb:category: business_logic
bb:outputs: ["business_logic.quantity_or_price"]
bb:triggers_all: ["authenticated_endpoint", "quantity_valued_parameter", "state_changing_method"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: constrained
bb:effects: mutates_object
bb:baseline: pristine_surface
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 51 as the v2 replacement for v1's payment-workflows pack, against the quantity-or-price leaf of the ticket 18 vocabulary; v1 shipped a README for this topic and no reference text, so nothing is attached.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_invariant", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "response_invariant", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "response_differential", "polarity": "supports", "min_count": 1}]
---

# Ask which number the server believes

A price is computed twice: once by the client, which is a convenience, and once
by the server, which is the only one that means anything. The defect this
Playbook asks about is the two being the same computation, so a number the
client sent is a number the server charges.

The reading is one order carried to the point where the target states a total,
with exactly one number edited, and the finding is the total rather than the
response to the edit.

## 1. State the invariant before anything is sent

Write down, before the first call, the rule this reading would break. It has to
be a number the target itself publishes: the unit price it lists, the quantity
range the form accepts, the quota the plan states. "A negative total is wrong"
is an invariant. "This price looks low" is a guess, and a run that cannot say
what the price should have been cannot say the one it got is wrong.

Complete this step with: the invariant, the parameter that carries the number,
and the route that states the authoritative total.

## 2. Record the pristine total

Read the cart, order or account before anything is sent, and store the answer.
The read runs as whichever Identity the Task was opened under; the step does not
choose it and there is no argument for it. Everything below is measured against
this. A run that starts by writing has nothing to compare its total to and is
reporting a number rather than a change.

`pristine_surface` is the baseline for this reason, and it is also why this
Playbook is never scheduled beside one that writes: two writers and the total is
about both.

## 3. Make the allowed mutation, and watch it land

Send the operation once with a value the rules admit -- one item, the listed
quantity, the price the target published. Read the authoritative total again.

The send is one call: `method`, `url`, `headers` and the `body` the route takes,
through `mcp__rk2__http_request`. The body goes in the call rather than in a
sentence describing it, because a total that moved is only evidence beside the
bytes that moved it, and both are stored.

This is the control and it is a `state_change`: it says the route accepts work,
that the number reaches the total, and by how much. Without it, a total that
does not move under the variant is equally well explained by a route that
refused, a session that was not valid, or a cart that was never touched.

## 4. Send the variant, one number moved

Repeat step 3 with exactly one number edited to a value the invariant forbids: a
negative quantity, a quantity above the stated maximum, a price the client
should not be sending at all, a currency the account does not hold.

One edit per reading. Two numbers moved together and neither is the answer.

Send it once. This Playbook does not sweep values to find the one that sticks --
that is a different activity, it is noisy on a live target, and the finding
needs one order rather than forty.

## 5. Read the total, and difference it

Read the authoritative total again and run `compare-responses` over this answer
and the one from step 3. Cite what the script returns.

The status of the variant call is not the claim. An application that answers
`200` to a negative quantity and stores nothing has been sloppy in its
messaging; an application that answers `400` and still moves the total has the
defect. The total is the only place this reading lives.

Where the total is not readable -- no route states it, or the response body is
in the sealed wire view -- there is nothing to difference and the reading is
inconclusive.

## 6. State the claim, and state what would refute it

The Hypothesis is `business_logic.quantity_or_price` on the route. It is
supported when the authoritative total moves to a value the invariant from step
1 forbids, against a control showing the same route moving it correctly. It is
refuted when the total after the variant is exactly the total after step 3, or
unchanged from step 2, with the control having landed.

A discount that applies, a coupon that stacks the way the terms say it may, a
price that is simply lower than expected: none of these is this claim. The claim
needs the target's own published rule and the target's own computed total to
disagree.

## 7. Clean up what you ordered

This Playbook's effects are `mutates_object`. It leaves one cart or one draft
order behind and it removes both before it finishes: the item added in step 3
and the item added in step 4, through the target's own removal route, read back
to confirm the total returned to step 2's.

Nothing here completes a purchase. Where the invariant can only be shown by
placing an order that charges an instrument, captures funds or notifies a
merchant, the reading stops and says so. The evidence for this class is a
computed total, and a total is available before the money moves.
