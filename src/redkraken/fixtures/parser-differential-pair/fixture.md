---
description: An order route behind a spending policy, served twice from one source, one variant letting a scanner and a JSON decoder read different amounts out of one body and the other refusing a body that names the amount twice.
bb:kind: own_pair
bb:classes: ["injection.parser_differential"]
bb:subject: /orders
bb:facts: ["authenticated_endpoint", "body_parameter", "json_request", "state_changing_method"]
bb:identities: ["alice"]
bb:provenance: Written for ticket 100 against the class description this migration adds, from what the class says rather than from any Playbook's steps; no upstream corpus.
---

# One body, two readers, two numbers

`POST /orders` places an order for an authenticated caller. Two components read
the amount out of the body:

* the **spending policy** scans the raw bytes and takes the first `"amount"` it
  matches, and refuses anything above `100`;
* the **route** decodes the body with a JSON parser, where a repeated key is
  legal and the last one wins.

The variants differ in whether those two readings can be made to disagree:

* **vulnerable** keeps both readers. A body of
  `{"amount": 1, "amount": 9999}` is approved at `1` and charged at `9999`, and
  the `201` reports both numbers.
* **secure** refuses a body naming `amount` more than once, before either reader
  runs, with `400`.

## Why the response reports both numbers

Because the alternative is a fixture that can only be graded by reading a ledger
this catalogue does not model. `approved` and `charged` in one answer is what
lets a run state the differential as a difference between two values it was
handed, rather than as an inference from a balance it cannot see.

## The control

A body naming `amount` once. Both variants take it, both approve it under the
ceiling, both charge exactly it, and both refuse it above the ceiling with the
same `403`. That is what says the policy is real and the route works, so a
differing pair of numbers is a disagreement and not an absent check.

## What is not here

`injection.parameter_precedence` is which of two *spellings* of one name wins --
query versus body, or a repeated query key -- and it is a statement about one
parser's rules. This class is two parsers reading one representation and
answering differently, which is why the fixture keeps both answers in view.

`business_logic.quantity_or_price` is the nearest business reading, and it is
about a number a workflow should not have accepted. Here the workflow's own
policy did not accept it: something else did.

`transport.request_framing` is the same idea at the message boundary and 025
records it as unmakeable through this door, so it is not what this pair serves.

Nothing here smuggles a request, splits a header, or reaches a second component
over the network. Both readers are in one process, because the class is the
disagreement rather than the topology.

## Ground truth

* **vulnerable** holds `injection.parser_differential`. The policy approved one
  amount and the order was placed for another, out of the same bytes.
* **secure** holds nothing this catalogue declares. One body, one reading, and a
  repeated key refused.
