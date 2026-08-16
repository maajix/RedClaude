---
description: One authenticated API route served twice from one source, one variant answering every request a session makes and the other refusing with 429 after five, counted per session.
bb:kind: own_pair
bb:classes: ["rate_limiting.per_identity"]
bb:subject: /api/v1/documents
bb:facts: ["api_surface", "multiple_test_identities"]
bb:identities: ["alice", "bob"]
bb:provenance: Written for ticket 49 against the ticket 18 class description, from what the class says rather than from any Playbook's steps; no upstream corpus.
---

# A route that counts, and a route that does not

`GET /api/v1/documents` returns two static rows to a caller holding a session.
Both variants issue the same two sessions and both answer `401` to a cookie
nobody issued. The difference is one counter:

* **vulnerable** answers every request the session makes.
* **secure** answers five and then refuses with `429` and a `Retry-After`.

The counter is keyed on the session's user, so `bob` is unaffected by whatever
`alice` spent. That is what makes the class `rate_limiting.per_identity` rather
than `per_origin`: a limit on the process would be visible as one caller's
requests changing another caller's answers, and this fixture deliberately does
not have that.

## Why the rows are static

The claim under test is about whether a sequence was counted, and the only thing
that may vary across that sequence is whether it was served. If the body changed
per request, a run could read its own pagination as the limit engaging.

## Why the 401 is on both variants

Same reason as the other paired fixtures. An unlimited sequence is only evidence
about an authenticated surface if the sequence was authenticated, so both
variants tell a working session from a broken one identically, and a run that
never established that cannot read twelve `200`s as "this account has no limit".

## What the ground truth claims

`rate_limiting.per_identity` on the vulnerable variant, and nothing else.

The rows are the same for both sessions and belong to nobody, so there is no
object to own and no field to withhold: `authorization.object_ownership` and
`information_disclosure.excess_field` are not gaps in this file, there is
nothing here that could make them true. The refusal bodies are fixed sentences,
no parameter reaches an interpreter, and the route is a single `GET`, so
`information_disclosure.error_detail`, the injection family and
`business_logic.replay` against this fixture are false positives.

## The bound this fixture puts on a run

Five is small on purpose. A run needs a handful of requests to see the secure
variant refuse, and the vulnerable variant is unlimited within any sequence a
run would spend -- so a Playbook that concludes "unlimited" here is making a
claim scoped to the sequence it sent, which is the only claim the evidence
supports and the only one this fixture can confirm.
