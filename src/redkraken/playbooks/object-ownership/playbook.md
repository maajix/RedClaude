---
description: Ask whether the object named in a request is checked against the caller, by sending one request twice under two leased Identities and differencing the two stored responses.
bb:category: authorization
bb:outputs: ["authorization.object_ownership"]
bb:triggers_all: ["multiple_test_identities", "object_identifier"]
bb:triggers_any: ["body_parameter", "path_parameter", "query_parameter"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-02-15
bb:provenance: Written for ticket 45 against the object-ownership leaf of the ticket 18 vocabulary; no upstream card, no third-party list.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_invariant", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "credential_effect", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "response_differential", "polarity": "supports", "min_count": 1}]
bb:references: ["why-two-identities.md"]
---

# Ask who the object belongs to

One endpoint names an object. Two Identities are leased. The question is whether
the server checks the second against the first, and the only thing that answers
it is the same request sent twice with one variable changed.

## 1. Name the object and the two Identities

The subject is an endpoint carrying an object identifier -- in the path, the
query or the body. Read the identifier's parameter from the state view; do not
guess which parameter names the object from the URL alone.

Name two Identity labels the mission packet already supplies. Label A is the one
whose object this is. Label B is the one that should not reach it.

Complete this step with: the endpoint, the one parameter that names the object,
and the two labels. If only one Identity is leased, the comparison has no second
side and this Playbook does not apply to the subject.

## 2. Establish the baseline and the control

Send the request as label A. That is the baseline: it says what the answer looks
like when the caller does own the object.

Send the same request as label B against an object label B does own. That is the
control, and it is the step most runs skip. Without it, a refusal under label B
is equally well explained by a session that was never valid, a route that
rejects everything, or a rate limit -- and none of those is an authorization
answer. The control is what makes the variant mean anything.

Both exchanges go through `mcp__rk2__http_request`, and neither chooses who makes
it: a call goes out as whichever Identity its Task was opened under and there is
no argument for it. A reading that needs two Identities is two Tasks -- label A's
baseline in the Task opened under label A, label B's control and the variant
below in the Task opened under label B -- and the differential is made by
comparing the Receipts they produced. Hold URL, method, headers and body shape
constant; the Identity the Task was opened under is the only thing that moves.

## 3. Send the variant

Send label A's request, unchanged, from label B's Task. One variable: the
Identity that Task was opened under. Not the object identifier, not the method,
not a header.

If the identifier has to be re-encoded to travel under a different session, the
comparison has two variables and the answer is about neither. Stop and record
that instead.

## 4. Difference the stored bytes

Run `compare-responses` over the baseline and the variant Artifacts. Cite the
difference the script returns, not a description of it. A summary of two
responses is a claim about them; the script's output is the thing itself.

## 5. State the claim, and state what would refute it

The Hypothesis is `authorization.object_ownership` on the endpoint. It is
supported when the variant returns the object's content under the wrong session
and the control shows the session working correctly on its own object. It is
refuted when the variant is invariant against a control that succeeded --
meaning the session is good and the server still refused.

Anything else is inconclusive, and inconclusive is the honest answer for a
response that differs in ways the difference cannot attribute: a generic error
page, a redirect to a login the control did not hit, a rate limit.

## 6. Leave the session as you found it

This Playbook reads. It does not log out, rotate a token, change a password or
write to an object. Its baseline is a session that stays stable, so it cannot be
run beside anything that mutates one -- the runtime computes that and drops the
conflicting Playbook rather than asking.
