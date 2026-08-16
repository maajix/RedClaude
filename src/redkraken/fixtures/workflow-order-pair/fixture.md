---
description: A three-step checkout that publishes its own order and redirects from payment to confirmation, served twice from one source, one variant requiring the payment step before it confirms and the other not.
bb:kind: own_pair
bb:classes: ["business_logic.workflow_order"]
bb:subject: /checkout/confirm
bb:facts: ["flow_step", "state_changing_method"]
bb:identities: ["alice"]
bb:provenance: Written for ticket 51 against the ticket 18 vocabulary, from the class description rather than from any Playbook; no upstream corpus.
---

# Three steps, one of them optional by accident

`POST /checkout/cart`, `POST /checkout/pay` and `POST /checkout/confirm` are the
flow, in that order. `GET /checkout` is the authoritative outcome: the flow the
target publishes, the steps this checkout has taken, and whether it is
confirmed. `DELETE /checkout` unwinds it again.

Both variants answer `401` to a session nobody issued, `409` to a payment before
there is a cart, and `303` to `/checkout/confirm` when a payment succeeds. Both
normalise a doubled separator, a `.` segment, a trailing slash and a mixed-case
segment to the same route. The only difference between them is one comparison:

* **vulnerable** confirms a checkout whatever has happened before it, so a
  session that has taken no steps at all ends with `confirmed` true.
* **secure** answers `409` unless the payment step was taken, and nothing moves.

## What the ground truth claims, and what it does not

`business_logic.workflow_order` is the whole of it. The vulnerable variant lets
the last step of a published sequence run without the step before it, which is
the class's description, and nothing else here is a defect.

Path spelling is not a defect this pair holds. `/checkout//confirm`,
`/checkout/./confirm`, `/checkout/confirm/` and `/Checkout/Confirm` reach the
same route on both variants, so a reading that reports a status-code bypass
against this fixture has reported the normaliser both halves share.

Neither is verb tampering. The confirmation route answers `POST` and nothing
else on both variants, and a `HEAD` or a `PUT` gets the same refusal from each,
so a run claiming `authorization.function_access` here is claiming something the
fixture does not contain.

There is one checkout and one Identity, so the ownership and tenant classes have
nothing to be about.

## Why the payment step is enforced on both variants

The flow has two ordering rules -- pay needs a cart, confirm needs a payment --
and only one of them can be the subject. Both variants enforce the first, so a
run that skips straight to payment is refused identically on each and the only
difference between the two halves sits at the step this fixture names as its
subject. A pair that broke both rules on one side would be grading how many
rules a variant enforces rather than whether the reading found one.

## Why payment answers a redirect

The `303` to `/checkout/confirm` is the flow naming its own next step, which is
what a recon pass reads as `flow_step` on the confirmation route. It carries the
outcome body with it on both variants: a redirect that also carries the step's
own answer is the ordinary case, and a Playbook reading redirects has to see one
that is not evidence of anything.
