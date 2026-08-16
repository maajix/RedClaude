---
description: Ask whether a GraphQL selection returns fields the caller is not entitled to, by requesting the same selection under two leased Identities and differencing the two stored documents field by field.
bb:category: information_disclosure
bb:outputs: ["information_disclosure.excess_field"]
bb:triggers_all: ["graphql_surface", "multiple_test_identities"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-02-15
bb:provenance: Written for ticket 49 as the v2 replacement for v1's graphql pack, against the excess-field leaf of the ticket 18 vocabulary; the v1 api-graphql text is attached as a maintainer reference and is not the source of this class.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_invariant", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "credential_effect", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "response_differential", "polarity": "supports", "min_count": 1}]
bb:references: ["api-graphql.md"]
---

# Ask the same question as two people and read the difference

A GraphQL endpoint answers the selection it is given. Authorisation in these
stacks is usually written per resolver rather than per response, so the
interesting question is not whether a type is reachable but whether one field on
a reachable type comes back for a caller who should not have it.

That is a difference between two documents, and the only thing that produces it
is the same selection sent twice under two Identities.

## 1. Name the selection and the two Identities

Read the recorded surface for the operation this subject carries. The selection
this Playbook sends is the application's own -- the one the client sends -- and
not one written here: an invented query tests the schema, and the schema is not
what the application authorises against.

Name two Identity labels the mission packet supplies. Label A is the one the
data belongs to. Label B is the one that should see less of it.

If the operation is a mutation, this Playbook does not apply to the subject: it
reads, and a mutation sent twice is two writes.

## 2. Establish the baseline and the control

Send the selection as label A through `mcp__rk2__http_request` with
`identity_slot` set. That is the baseline: the full document, for the caller it
belongs to.

Send label B's own equivalent selection as label B. That is the control, and it
is what tells a refusal apart from a session that was never valid. Follow
`use-identity` for both; a GraphQL endpoint that answers `200` with an
`errors` array to an unauthenticated caller is exactly the shape that reads as
success to anything counting statuses.

## 3. Send the variant

Label A's selection, unchanged, as label B. One variable: the session. Same
operation name, same variables, same document.

If the selection has to be edited to be accepted under label B -- a different
identifier in a variable, a field removed -- then two things moved and the
difference is about neither. Stop and record that.

## 4. Difference the two documents

Run `compare-responses` over the baseline and the variant Artifacts. Cite the
fields the script reports as present in both. A GraphQL response nulls what a
resolver refused and keeps the key, so "the field is in the response" and "the
field carries a value" are different findings and only the second is this class.

## 5. State the claim, and state what would refute it

The Hypothesis is `information_disclosure.excess_field` on the operation. It is
supported when the variant carries a populated field that belongs to label A and
the control shows label B's session working correctly on its own data. It is
refuted when the variant is invariant -- every field label B should not have is
absent or null against a control that succeeded.

Introspection is not this claim. A schema that answers `__schema` tells you what
fields exist, which is surface: record it as surface, and let the scheduler
decide what to ask about it. Reporting the introspection response itself is
reporting a configuration, not a document a caller was not entitled to.

Batching and aliasing are likewise a different question -- how much one request
can cost is `rate_limiting.resource_cost`, and this Playbook may not claim it.

## 6. Leave the session as you found it

This Playbook reads. It sends no mutation, it does not log out, and it does not
retry the variant with a rotated token. Its baseline is `stable_session`, so the
runtime drops it beside anything that moves one.
