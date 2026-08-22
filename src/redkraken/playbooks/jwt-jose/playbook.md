---
description: Ask whether a token is honoured beyond what it was issued for, by presenting one real token to a second audience, a second scope and a second key and reading which of those the server still answers as the caller.
bb:category: authorization
bb:outputs: ["authorization.token_scope"]
bb:triggers_all: ["authenticated_endpoint", "tech_jwt"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 50 as the v2 replacement for v1's jwt-jose pack, against the token-scope leaf of the ticket 18 vocabulary; the v1 jwt text is attached as a maintainer reference and supplies the header and claim edits this Playbook sends.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_invariant", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "credential_effect", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "credential_effect", "polarity": "supports", "min_count": 1}]
bb:references: ["jwt.md"]
---

# A token says what it is for; ask whether anyone reads that part

A signed token carries two kinds of statement. One is *who*: the subject, the
identity the session belongs to. The other is *what for*: the audience, the
scope, the issuer, the expiry, the key that signed it. Verification libraries
check the signature by default and leave the second kind to the application,
which is why the second kind is so often unchecked.

This Playbook does not ask whether the signature can be forged. It asks whether
a token that is entirely genuine is accepted somewhere it never claimed to be
valid.

## 1. Get a token the target handed out, not one a slot is holding

Every variant below is one token with one edit, so this Playbook needs the bytes,
and there is one place they may come from: a route the run drove itself from a Task
opened with no Identity -- an issuance, refresh or exchange endpoint the target
answers for a caller who has not leased anything. That token is material the target
published, and editing it is a statement about the target.

A token that exists only inside a leased Identity is not available and is not to
be worked around. `use-identity` seals the response bytes of an Identity call and
keeps authentication out of request fields, so a run whose only copy sits in a
slot has no variants to send: record the reading as inconclusive and name the
issuance route that would have supplied one.

Decode the header and payload of the token you were given, and write down only
the field *names* and the decision they should drive: `aud`, `scope` or `scp`,
`iss`, `exp`, `kid`, `alg`.

Do not print claim values into a Hypothesis. A token is a credential and its
payload is the Program's, not the transcript's.

## 2. Establish both ends of the scale

Send one authenticated read with the token as issued and store the answer.

Send the same read with the last character of the signature changed and store
that answer. Those two are the scale and the second is the control: a
`credential_effect` that says this endpoint verifies the signature at all. An
endpoint that answers both the same way is not scoping anything, it is not
authenticating, and the claim belongs to
`authentication.credential_verification`.

## 3. Send one re-scoping variant at a time

Every variant below presents a token we already hold, unchanged, somewhere or
somehow it was not issued for. Nothing here forges:

* the token sent to a second endpoint of the same application whose recorded
  surface says it requires a different scope
* the token sent to a second application in the Program's scope that shares the
  issuer, when `aud` names only the first
* the token presented after its own `exp`, where the run held one long enough
* a token the same route issues for a lower-privilege principal, sent to a route
  the higher one uses

Then, and only where the target's own material provides the key, the header
edits the v1 text is attached for: `alg` set to `none`, a symmetric `alg` over a
published public key, `kid` pointed at another key the target itself serves.
Each of those is one request and each needs the key to have come from the
target, not from us.

## 4. Read each answer against both ends

Run `compare-responses` over each variant and the two stored answers. The
variant that is answered the way the intact token is means the endpoint read the
signature and stopped. The variant that is answered the way the broken signature
is means the scope decision ran.

An answer that is neither -- a `403` with a different body, a `500` out of a
claim parser -- is inconclusive for this class and is recorded as such.

## 5. Propose the claim, and say what would refute it

The Hypothesis is `authorization.token_scope` on the endpoint that accepted the
token. It is supported when a token issued for one audience, scope, lifetime or
key was honoured under another, against a control that shows a broken signature
being refused. It is refuted when every variant is answered the way the broken
signature is.

Which *data* came back is a separate question. A token accepted out of scope
that then returns another tenant's records is `authorization.tenant_isolation`
and its own reading; this Playbook stops at the acceptance.

## 6. Read only, and only with tokens the target issued to this run

Effects are `read_only`: every request here is a read and no variant writes. The
tokens come from an issuance route this run drove, the keys come from the
target's own published material, and a token taken from anywhere else -- a log,
a metadata service, a bundle, another party's session -- is somebody else's
credential and out of bounds.
