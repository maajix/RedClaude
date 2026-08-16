---
description: A login endpoint served twice from one source, one variant comparing the password only when the client sent a truthy value and the other refusing every request whose password is not a non-empty string.
bb:kind: own_pair
bb:classes: ["authentication.credential_verification"]
bb:subject: /session
bb:facts: ["email_valued_parameter", "state_changing_method"]
bb:identities: ["alice"]
bb:provenance: Written for ticket 50 against the ticket 18 class description, from what the class says rather than from any Playbook's steps; no upstream corpus.
---

# One account, five shapes of secret, and the guard that only sees one of them

`POST /session` takes `{"email": ..., "password": ...}`. Both variants hold one
account, answer `200` with a session for the right password, and answer `401`
for a wrong one.

The difference is the guard:

* **vulnerable** compares the secret only when the client sent something truthy.
  An omitted `password`, `""`, `false`, `0` and `[]` all skip the comparison and
  come back with the session.
* **secure** requires a non-empty string and compares it. Every one of those
  shapes is answered exactly the way a wrong password is.

`true`, `1` and `"wrong"` are refused by both. That is deliberate: a run that
sends one type variant and stops has not distinguished the variants, and the
Playbook's instruction to send each shape once is what this fixture rewards.

## The control is a wrong password, not a missing account

An address the fixture does not hold is answered `401` with the same body as a
wrong password, on both variants. Two reasons.

Enumeration is a different class -- `information_disclosure.identifier_oracle` --
and a fixture that leaked it would let a run report this pair for something it
does not declare, which is how a graded corpus stops measuring what it says it
measures.

And it keeps the control honest. The wrong-password answer is what proves the
endpoint reaches an authentication decision at all, and it has to be reachable
without knowing whether the account exists.

## What is not here

No lockout, no rate limit, no captcha. A real login defends itself and the
Playbook says a `429` ends the sequence; this fixture answers every request the
same way so that the reading is about the comparison rather than about the
defence.

No registration, no reset, no second factor. Those are `recovery_flow` and
`factor_enforcement`, they have their own leaves in the vocabulary, and one of
them has its own pair in this catalogue.

## Ground truth

* **vulnerable** holds `authentication.credential_verification`. A `POST` with
  no `password` key returns `200` and a session.
* **secure** holds nothing this catalogue declares. Every request that is not
  the correct non-empty string is `401`.
