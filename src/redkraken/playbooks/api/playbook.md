---
description: Ask whether repetition against one account is bounded at all, by sending a small declared number of identical requests under one leased Identity and reading whether the answers ever change.
bb:category: rate_limiting
bb:outputs: ["rate_limiting.per_identity"]
bb:triggers_all: ["api_surface", "multiple_test_identities"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: approval_required
bb:effects: read_only
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-02-15
bb:provenance: Written for ticket 49 as the v2 replacement for v1's api pack, against the per-identity leaf of the ticket 18 vocabulary; the rate-limit-bypass text is the only one of the three v1 files that named a defect, and this is the class it named.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_differential", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "credential_effect", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "response_invariant", "polarity": "supports", "min_count": 1}]
bb:references: ["api-soap.md", "api.md", "rate-limit-bypass.md"]
---

# Ask whether anything counts

One API endpoint, one leased Identity, the same request several times. The
question is whether the server keeps a count against that Identity, and the
answer is the shape of the answers over the sequence rather than the content of
any one of them.

This is the one Playbook here that spends requests on purpose, which is why its
risk floor is `approval_required`. The number below is small because the claim
does not need a large one: a limit that exists is almost always well under it,
and a limit that does not exist is not more absent after a thousand requests
than after a dozen.

## 1. Fix the request and the budget before sending anything

Name the endpoint, the one Identity label, and the exact count you will send.
Write the count down before the first request. A sequence that keeps going until
something happens is a sequence with no refuting outcome, and it is also the
shape that gets a Program's access withdrawn.

Twelve is the default. Raise it only against a documented published limit that
is higher, and record the document.

## 2. Establish the control: the Identity is working

Send the request once under the Identity through `mcp__rk2__http_request` with
`identity_slot` set, and confirm the response is the authenticated one -- not a
redirect to a login, not an anonymous view of the same route.

This is the control, and without it the whole sequence is unreadable. A run of
identical `401`s is invariant, and invariance is what this Playbook reads as
"nothing is counting". An expired lease would therefore produce the finding.

## 3. Send the sequence

The same request, unchanged, the declared number of times, under the same
Identity. One variable moves: how many have been sent. Not the body, not a
header, not the path.

Send them one at a time and stop early on the first answer that differs. A limit
that has engaged has already answered the question, and continuing past it is
spending a Program's goodwill on a result already in hand.

## 4. Difference the sequence against its own first answer

Run `compare-responses` over the first stored response and each later one. What
matters is any change the server made: a different status, a `Retry-After`, a
`RateLimit-` header appearing, a body that says the quota is spent, a latency
that steps.

Cite the difference the script returns. A sequence summarised as "all 200" is a
claim about what the runner remembers.

## 5. State the claim, and state what would refute it

The Hypothesis is `rate_limiting.per_identity` on the endpoint. It is supported
when every answer in the sequence is invariant against the first and the control
shows the Identity was authenticated throughout -- the server took the whole
sequence and never counted it. It is refuted when any answer differs in a way
that is the limit engaging.

Two things are inconclusive and are recorded as such. A sequence that changed
for a reason that is not a limit -- a deploy, an unrelated error, a session that
expired mid-run -- says nothing either way. And a limit keyed on the caller's
origin rather than on the account is a different class: this Playbook holds the
Identity fixed, so it cannot tell the two apart, and `rate_limiting.per_origin`
is not a claim it may make.

## 6. Leave the account as you found it

This Playbook reads. It does not create objects to count, it does not retry
against a second Identity to see whether the counter is shared, and it does not
send its sequence again to check. Its baseline is `stable_session` because a
Playbook that rotated the session underneath it would turn one account's
sequence into several.
