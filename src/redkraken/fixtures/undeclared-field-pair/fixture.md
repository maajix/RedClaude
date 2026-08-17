---
description: An authenticated orders route served twice from one source beside the OpenAPI contract that says what an order is, one variant serialising the stored record whole and shipping two fields the contract never declared and the other projecting onto the declared list, with a declared field that reads like an internal name as the decoy and a counter that changes on every read.
bb:kind: own_pair
bb:classes: ["information_disclosure.undeclared_field"]
bb:subject: /api/v2/orders
bb:facts: ["authenticated_endpoint", "read_method", "tech_openapi"]
bb:identities: ["alice"]
bb:provenance: Written for ticket 54 against the undeclared_field class description ticket 54 added, from what the class says rather than from any Playbook's steps; the declared `_links` field and the noisy counter are the precision controls ticket 54 criterion 5 asks for.
---

# Fields the contract never mentioned

`GET /api/v2/orders` answers with orders for a caller holding a session, and
`GET /api/v2/openapi.json` says what an order is. The contract is identical on
both variants; only one side keeps to it:

* **vulnerable** serialises the stored record, so `internal_margin` and
  `fraud_score` travel with every order.
* **secure** projects each record onto the five fields the contract declares.

The claim is against the contract, not against another principal. One identity
exists here and every caller sees the same document, so nothing in this fixture
is a field one caller may see and another may not.

## What the two arms do here

The two arms are two documents rather than two requests: the contract and the
response. The reading fetches both and compares the field names.

Against **secure**, every name in the response is a name in the contract, and
that is this class's refutation: not a missing field, but a set difference that
came out empty.

Against **vulnerable**, the difference is `internal_margin` and `fraud_score`,
named. The same comparison also finds all five declared names present in both
directions, which is the control that says the comparison ran against the right
contract and the right route -- an empty difference means nothing if the matcher
also fails to find `status`.

## The two precision controls, on both variants

`GET /api/v2/live` returns a body carrying a counter that increases on every
request, so a reading that skipped its baseline has a route it can be wrong
about.

`_links` is declared in the contract and present in every response on both
variants. It is a decoy for the reading that scores field names that look
internal: leading underscore, a nested object, no business meaning, and entirely
legitimate. What makes a field undeclared here is the contract, and only the
contract.

## What the ground truth claims, and what it does not

`information_disclosure.undeclared_field` on `/api/v2/orders` of the vulnerable
variant, and nothing else anywhere.

Nothing here is a second identity's data, so nothing here is
`information_disclosure.excess_field`: the extra fields belong to the same orders
this caller is entitled to, and the only thing they exceed is the published
shape. Neither extra field is a credential, a token or a key. No route serves the
record store by any other name, refusals are fixed, and nothing writes.
