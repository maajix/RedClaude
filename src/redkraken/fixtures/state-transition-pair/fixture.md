---
description: An order API where cancelling is allowed while an order is open and forbidden once it has shipped, served twice from one source, one variant consulting the order's state before it cancels and the other not.
bb:kind: own_pair
bb:classes: ["authorization.state_transition"]
bb:subject: /orders/ord-3b91/cancel
bb:facts: ["multiple_test_identities", "path_parameter", "state_changing_method"]
bb:identities: ["alice", "bob"]
bb:provenance: Written for ticket 51 against the ticket 18 vocabulary, from the class description rather than from any Playbook; no upstream corpus.
---

# Two orders, two states, one check

`POST /orders/{reference}/cancel` cancels an order. `GET /orders` lists the
caller's own orders with each one's state and the states a cancellation is
allowed from, and `GET /orders/{reference}` is the authoritative after-state.

`alice` owns `ord-7c2a`, which is open, and `ord-3b91`, which has shipped.
`bob` owns `ord-5e08`. Both variants answer `401` to a session nobody issued,
`404` to a reference no order has and `403` to an order belonging to somebody
else. The only difference between them is one comparison:

* **vulnerable** cancels any order the caller owns, whatever state it is in.
* **secure** answers `409` unless the order's state is one of
  `cancellable_from`, and the state does not move.

## What the ground truth claims, and what it does not

`authorization.state_transition` is the whole of it. The vulnerable variant
cancels a shipped order for its owner, which is the class's description -- the
object is in a state that should forbid the operation -- and nothing else here
is a defect.

`authorization.object_ownership` in particular is not present: both variants
compare the order's owner against the session before anything else happens, and
`bob`'s order answers `403` to `alice` on each of them. A pair whose vulnerable
half failed both checks would be two fixtures under one name, and a run against
it could not say which class it was right about.

`business_logic.workflow_order` is the near neighbour and it is not this. That
class is a step taken without the steps before it. Here the sequence was walked
correctly and the order arrived where it was supposed to arrive; what the
vulnerable variant permits is an operation out of a state that is meant to be
the end of the line.

## Why the 404 and the 403 differ

The three controls the class needs -- the caller's own object, another
Identity's object, and no object at all -- are only distinguishable if the
target answers them differently, so both variants do. That difference is a
deliberate property of this fixture rather than a defect in it: the references
are sequential-looking labels, `GET /orders` hands the caller their own, and a
claim of `information_disclosure.identifier_oracle` against this pair is a
false positive.

## Why the refusal names no state

`NOT_CANCELLABLE` is a fixed string. An error body that quoted the order's
current state would put `information_disclosure.error_detail` into the fixture
beside the class it declares, and the ground truth would then be understating
what it holds. What a caller may learn about their own order is what
`GET /orders/{reference}` returns to them.
