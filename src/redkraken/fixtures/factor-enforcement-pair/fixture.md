---
description: A step-up route served twice from one source, both issuing the same factor receipts, one of them changing the recovery address for a request that carries no receipt, a weaker factor's receipt or a spent one, and the other requiring the enrolled authenticator once.
bb:kind: own_pair
bb:classes: ["authentication.factor_enforcement"]
bb:subject: /account/recovery-email
bb:facts: ["state_changing_method", "tech_webauthn"]
bb:identities: ["alice"]
bb:provenance: Written for ticket 50 against the ticket 18 class description, from what the class says rather than from any Playbook's steps; no upstream corpus.
---

# The prompt happened; ask whether the action needed it

`POST /session` logs in. `POST /factor/verify` completes one of the account's two
enrolled factors -- `webauthn` or `backup_code` -- and returns a receipt.
`POST /account/recovery-email` is the subject, and `GET /account` reads back what
the address actually is.

Both variants issue both receipts and both refuse a receipt this fixture never
issued. The difference is what the sensitive route insists on:

* **vulnerable** checks the receipt only when the client sent one, accepts
  either factor's receipt, and never spends it. A request with no `receipt` key
  changes the address; so does a `backup_code` receipt; so does the same
  `webauthn` receipt used a second time.
* **secure** requires the `webauthn` receipt, once. Anything else is `401` and
  the address is unchanged.

## The reading is the address, not the status

`GET /account` is here because a `200` from a step-up route that changed nothing
is not a bypass. Every claim against this pair has to be able to say what the
recovery address was before and what it is afterwards, which is the `state_change`
the Playbook asks for.

## Why the weaker factor is real

`backup_code` is enrolled on the account and completing it is a legitimate
thing to do. The defect is not that the factor exists, it is that the sensitive
route lets the client's choice decide which one counted -- so the account's real
second factor is its weakest one.

A fixture that only modelled the omitted receipt would grade a run that sent one
variant, and the Playbook asks for four.

## The control

A receipt of the right shape that was never issued: `401` on both variants. It
is what says the route reaches a factor decision at all, and without it the
vulnerable variant's `200` would be indistinguishable from a route that reads
nothing.

## What is not here

No second Identity. Whether somebody else can drive this route is
`authorization.function_access`, and it has its own pair.

No enrolment and no authenticator registration: those change what the account
holds rather than what one action requires, and a pair declares one class.

## Ground truth

* **vulnerable** holds `authentication.factor_enforcement`. `POST
  /account/recovery-email` with a session and no receipt returns `200` and
  `GET /account` shows the new address.
* **secure** holds nothing this catalogue declares. That request is `401`, the
  address is unchanged, and only a fresh `webauthn` receipt moves it.
