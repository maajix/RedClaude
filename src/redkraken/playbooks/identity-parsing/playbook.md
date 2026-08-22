---
description: Ask whether the identity an assertion is trusted for is the identity its signature actually covers, by submitting one signed document whose subject is stated twice and reading which of the two the relying party logged in.
bb:category: authentication
bb:outputs: ["authentication.federation_trust"]
bb:triggers_all: ["state_changing_method", "tech_saml"]
bb:skills: ["compare-responses", "handle-untrusted-content", "use-identity"]
bb:risk: approval_required
bb:effects: mutates_session
bb:baseline: none
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 50 as the v2 replacement for v1's identity-parsing pack, against the federation-trust leaf of the ticket 18 vocabulary; the v1 saml text is attached as a maintainer reference and is the source of the wrapping technique this Playbook uses.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_invariant", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "credential_effect", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "credential_effect", "polarity": "supports", "min_count": 1}]
bb:references: ["saml.md"]
---

# Two readers, one document, and the identity they disagree about

A relying party that consumes a signed assertion runs two readers over the same
bytes. One verifies a signature over some region of the document. The other
pulls out the subject and logs somebody in. Nothing in the format guarantees
those two regions are the same region, and every classic defect in this family
is that gap: a second assertion added beside the signed one, an element moved
under a wrapper, a `NameID` the verifier never covered.

The question is not whether the signature is valid. It is whether the identity
the application acted on is inside what the signature covered.

## 1. Get one real assertion, from the route that mints it

Every variant below is one signed document with one edit, so this Playbook needs
the document. Drive the issuer's own assertion route once from a Task
opened with no Identity, using the federated account the Program provisioned for
this engagement. What comes back was minted for us, for this relying party, and it is
the only material this Playbook works from.

An assertion that exists only inside a leased Identity's exchange is not
available: `use-identity` seals those response bytes, and a run that has no other
copy has no variants to send. Record the reading as inconclusive and name the
route that would have minted one. An assertion collected from anywhere else is
somebody else's credential.

## 2. Read the document as untrusted content

Follow `handle-untrusted-content` before quoting anything out of it. A signed
assertion carries attacker-influenceable text in the same envelope as the parts
that matter, and a run that pastes an attribute value into a claim is quoting
whatever the issuer was told.

Write down, from the document itself: which element carries the subject, which
region the signature references, and whether that reference is by identifier or
by position.

## 3. Establish the control

Post the captured assertion back, unchanged, and record the answer. That is one
end of the scale: the relying party accepts what it should accept.

Then post it with one byte of the signature changed. Record that answer too.
This is the control the claim rests on, and it is a `credential_effect`: it says
the consumer verifies something. A relying party that logs us in with a broken
signature is not a wrapping finding, it is
`authentication.credential_verification`, and this Playbook hands it over rather
than claiming it.

## 4. Send one wrapping variant at a time

Each variant states the subject twice and changes nothing else:

* the signed assertion left intact, with a second unsigned assertion carrying a
  different subject placed before it
* the signed assertion moved into a wrapper element, with a copy carrying a
  different subject left where the original stood
* the subject element duplicated inside the signed assertion, once with the
  subject it was minted for and once with the other name

The other name is a subject the Program controls -- a second leased Identity, or
a name the operator confirmed is ours. Never a real user of the target: a
successful variant creates a session, and creating a session as somebody who did
not ask is the line this Playbook does not cross.

## 5. Read which subject came back

Run `compare-responses` over each variant's answer and the two ends of the
scale, and read *who* the session belongs to rather than whether one exists.
Follow the answer with one read of the identity route carrying the session the
variant produced -- that session is the consumer's answer to us and not a lease,
so it is carried in the request headers of a Task opened with no Identity --
because a `302` to a dashboard is not a statement about which account is behind
it.

## 6. Propose the claim, and say what would refute it

The Hypothesis is `authentication.federation_trust` on the application. It is
supported when a variant produced a session for the subject that was outside the
signed region, against a control that shows a broken signature being refused. It
is refuted when every variant is answered the way the broken signature is, or
when the session that comes back is the leased Identity's own -- the consumer
read the subject from inside what it verified.

Assertion replay is a different question. The same unmodified document accepted
twice is `business_logic.replay`, and this Playbook does not test it: one edit,
one reading, one class.

## 7. Leave the sessions you made, and nothing else

Effects are `mutates_session` and risk is `approval_required`, because this
Playbook posts to a route that mints identity and the issuer on the other side
of the flow is a third party. It sends nothing to the identity provider beyond
the one real assertion request in step 1, and it does not enumerate subjects: a
variant
naming an account nobody controls is an unauthorised login attempt against a
person.
