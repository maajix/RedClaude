---
description: A cart API that publishes its unit prices and its quantity rule and computes its own total, served twice from one source, one variant enforcing the published rule before it stores a line and the other not.
bb:kind: own_pair
bb:classes: ["business_logic.quantity_or_price"]
bb:subject: /cart/items
bb:facts: ["authenticated_endpoint", "quantity_valued_parameter", "state_changing_method"]
bb:identities: ["alice"]
bb:provenance: Written for ticket 51 against the ticket 18 vocabulary, from the class description rather than from any Playbook; no upstream corpus.
---

# One published rule, one computed total

`GET /cart` returns the lines, the total the server computes, and the rule the
cart states: a quantity is a whole number between 1 and 10. `POST /cart/items`
adds `{"sku": ..., "quantity": ...}`, and `DELETE /cart/items/{sku}` removes a
line again.

Both variants answer `401` to a session nobody issued, `404` to a sku the
catalogue does not hold, and `400` to a quantity that is not a whole number.
The only difference between them is one comparison:

* **vulnerable** stores whatever whole number arrived, so a quantity of `-3`
  gives a total of `-66000`.
* **secure** answers `400` unless the quantity is inside the published range,
  and the total does not move.

## What the ground truth claims, and what it does not

`business_logic.quantity_or_price` is the whole of it. The vulnerable variant
computes a total the rule it publishes forbids, which is the class's description,
and nothing else here is a defect.

The prices are the server's throughout. No route accepts a price, a discount or
a currency from the client, so a reading that reports a client-supplied price
against this pair has reported something the fixture does not contain.

There is one cart and one Identity. `authorization.object_ownership` and
`authorization.tenant_isolation` need a second owner to be about anything, and
this pair does not have one.

## Why the total is recomputed on every read

`GET /cart` sums the lines each time rather than returning a stored figure. A
total carried beside the quantities could drift from them, and a fixture whose
total disagreed with its own lines would hold a second defect nobody declared --
and the reading this pair grades would then have two explanations.

## Why the type check is on both variants

A body carrying `"three"`, `null` or `3.5` is a malformed request rather than a
quantity the rules forbid, and both variants refuse it identically. What the
class is about is a well-formed number the published rule excludes, so the
vulnerable variant has to reach its own arithmetic to be wrong. Booleans go with
the malformed ones: `True` is an integer in Python and is not a quantity anybody
meant to send.
