---
description: A bearer-token route served twice from one source, both verifying the same signature, one of them honouring any token the issuer signed and the other checking the audience, the scope and the expiry the token itself carries.
bb:kind: own_pair
bb:classes: ["authorization.token_scope"]
bb:subject: /api/v1/profile
bb:facts: ["authenticated_endpoint", "tech_jwt"]
bb:identities: ["alice"]
bb:provenance: Written for ticket 50 against the ticket 18 class description, from what the class says rather than from any Playbook's steps; no upstream corpus.
---

# The signature checks out, and that is all one of them checks

`GET /tokens` hands out three tokens, the same three on both variants:

* `profile` -- `aud: profile`, `scope: profile:read`, unexpired
* `reports` -- `aud: reports`, `scope: reports:read`, unexpired
* `expired` -- the `profile` claims with an `exp` an hour in the past

`GET /api/v1/profile` is the subject. It wants the first one.

* **vulnerable** verifies the signature and stops. All three tokens answer
  `200`.
* **secure** verifies the signature, then the expiry (`401`) and then the
  audience and scope (`403`). Only the first token answers `200`.

## Nothing here is forged

The issuing key never leaves the fixture and there is no JWKS endpoint, so
`alg: none`, a re-signed payload and a `kid` swap are all refused by both
variants. That is on purpose: those are `credential_verification` readings, and
a pair that let them through would be graded for a class it does not declare.

What is left is the class itself -- a genuine token honoured beyond what it says
it is for -- and the only material a run needs is what `GET /tokens` gave it.

## The expiry is an offset, not a timestamp

`exp` is minted relative to now, an hour either side. A fixed timestamp would
age: the corpus would keep the file and the "valid" tokens would quietly become
expired ones, and the pair would stop differing for the reason it says it does.

## The control

A tampered signature, refused `401` by both variants. Without it, "the reports
token answered `200`" is a sentence about a route nobody proved reads tokens at
all.

## What is not here

No second tenant and no second user: whose *data* comes back is
`tenant_isolation` and `object_ownership`, and both have their own pairs. This
one stops at the acceptance, which is where the class stops.

## Ground truth

* **vulnerable** holds `authorization.token_scope`. The `reports` token and the
  `expired` token both answer `200` at `GET /api/v1/profile`.
* **secure** holds nothing this catalogue declares. The `reports` token is
  `403`, the expired one is `401`, and the `profile` token is `200`.
