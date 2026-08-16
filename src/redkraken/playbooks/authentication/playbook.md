---
description: Ask whether the server actually checks the secret it was sent, by presenting one credential three ways -- correct, wrong, and structurally absent -- and reading which of the three it answers as if it had verified something.
bb:category: authentication
bb:outputs: ["authentication.credential_verification"]
bb:triggers_all: ["email_valued_parameter", "state_changing_method"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: constrained
bb:effects: mutates_session
bb:baseline: none
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 50 as the v2 replacement for v1's authentication pack, against the credential-verification leaf of the ticket 18 vocabulary; four v1 texts are attached as maintainer references and the type-juggling one is the only one that named this defect.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_invariant", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "credential_effect", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "credential_effect", "polarity": "supports", "min_count": 1}]
bb:references: ["cloud-aws-cognito.md", "http-attacks-password-reset.md", "sign-up-login-register.md", "type-juggling.md"]
---

# Ask whether the check happens, not whether the password is right

The subject is the endpoint where a credential is presented: a login, a token
exchange, a step in a reset. Guessing a password is not this Playbook and never
becomes it. The question here is narrower and answerable: does the server reach
a decision by comparing what was sent against what it holds, or does some shape
of request reach a session without that comparison ever running?

Three answers decide it, and one of them is the control. A server that refuses
the wrong secret and accepts the right one is verifying. A server that also
accepts a third shape -- a missing field, a field of the wrong type, an empty
signature -- is answering a question it never asked.

## 1. Lease the credential rather than reading it

The correct credential is an Identity slot. Follow `use-identity`: name the
label in `identity_slot` and let the proxy attach it. Nothing in this Playbook
prints, echoes or copies the secret, and a step that needed the plaintext would
be a step that put a Program's account into a transcript.

If no slot holds a working credential for this endpoint, stop. Every reading
below is a comparison against a request that is known to succeed, and without
one there is nothing to compare against.

## 2. Establish both ends of the scale

Send the credential correctly through `mcp__rk2__http_request` with the slot
attached. Store the answer: status, the shape of the body, and whether a session
artifact came back.

Then send the same request with the secret replaced by a value of the same type
that is certainly wrong. Store that answer too.

Those two are the scale. They are also the control this Playbook's claim rests
on: a `credential_effect` on each end says the endpoint returns an authentication
decision at all. An endpoint that answers `200` to both is not a lenient
endpoint, it is an endpoint that does not authenticate here, and every reading
below would be measuring the wrong route.

## 3. Send the variants, one malformation at a time

Each variant changes exactly one thing about how the secret is presented, and
each is sent once:

* the field omitted entirely
* the field present and empty
* the field carrying a value of a different JSON type -- a boolean, a number, an
  empty array, an object
* where the credential is a signature or a MAC, the same body with the signature
  removed and with the signature present but empty

Nothing here iterates over values of the same type: that is guessing, it is
bounded by `rate_limiting` rather than by this class, and the Program's rules of
engagement decide whether it may happen at all.

## 4. Read each answer against both ends of the scale

Run `compare-responses` over the variant and the two stored answers. There are
three outcomes and only one of them is the class:

* the variant matches the wrong-secret answer: the check ran and refused, which
  is the refutation
* the variant matches the correct-secret answer: the check did not run, and a
  session came back for a credential that was never verified
* the variant matches neither: a `500`, a validation error, a third status. That
  is inconclusive here and it is worth recording as an `error_detail` question
  for somebody else, because a stack trace out of a parser is not a statement
  about whether the comparison happens.

## 5. Propose the claim, and say what would refute it

The Hypothesis is `authentication.credential_verification` on the endpoint. It
is supported when a variant is answered the way the correct credential is,
against a control that shows the wrong one being refused. It is refuted when
every variant is answered the way the wrong credential is.

An account lockout, a captcha or a `429` in the middle of this sequence ends it.
Those are the endpoint defending itself, and the readings after one are about
the defence rather than about the comparison.

## 6. Leave one session, and no accounts

This Playbook's effects are `mutates_session` because a successful login makes
one. It does not register, it does not reset, and it does not change a password:
the enrolment and recovery paths are their own class, `authentication.recovery_flow`,
and this Playbook may not claim them from a login reading.
