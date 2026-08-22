---
description: Ask whether a session survives the event that was supposed to end it, by driving one leased session across a logout, a password change or a revocation and replaying a request that only a live session answers.
bb:category: session_handling
bb:outputs: ["session_handling.lifetime"]
bb:triggers_all: ["cookie_parameter", "state_changing_method"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: constrained
bb:effects: mutates_session
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 50 as the v2 replacement for v1's identity-lifecycle pack, against the session-lifetime leaf of the ticket 18 vocabulary; v1 shipped a README for this topic and no reference text, so nothing is attached.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_invariant", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "credential_effect", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "credential_effect", "polarity": "supports", "min_count": 1}]
---

# Ask what the end of a session actually ends

Applications end sessions in three places and they are usually three different
pieces of code: the logout route, the credential change that is supposed to
invalidate every other device, and the administrative revocation. Each of them
can delete a cookie in the browser and leave the server side untouched, and the
browser is not where a stolen token is used.

The question is one probe repeated after each of those events: does the session
that answered a moment ago still answer?

## 1. Keep the probe in the slot

Follow `use-identity`: the run acts as whichever Identity the Task was opened
under -- the step does not choose it and there is no argument for it -- and the
proxy holds the session. This Playbook never reads the cookie or the bearer, and
it does not need to. A call through a slot is already a request no browser took
part in, so a session that still answers one after the client was told to forget
it is exactly the reading this Playbook is after: the server side does not care
what the browser deleted.

Send one authenticated read through the label and store the answer. That is the
probe, and the same request is what every step below repeats.

## 2. Establish what refusal looks like

The unauthenticated half of the differential is a Task opened with no Identity.
Send the same read there and store that answer.

This is the control, and it is a `credential_effect`: it says the route reaches
an authentication decision and refuses something. A route that answers `200` to
a caller holding nothing is not a route that keeps sessions alive too long, it is
a route that never checked, and that is
`authentication.credential_verification` and somebody else's claim.

## 3. Trigger one ending, and only one

Pick the event the subject supports and cause it once:

* `POST` the logout route through the same label
* change the credential through the account route, where the Program's rules of
  engagement admit an account mutation
* have the operator revoke the session, where the target offers a device list

One event per reading. Two endings at once and the answer says nothing about
either.

## 4. Replay the probe, and difference it

Send the probe again through the same label. Run `compare-responses` over this
answer, the answer from step 1 and the control from step 2:

* it matches step 1: the session outlived the ending
* it matches step 2: the ending took effect, and that is the refutation
* it matches neither: record it and stop. A `500` after a logout is a state the
  application did not expect and it is not evidence about session lifetime.

One condition has to hold before any of that means anything: the lease behind
the label has to be the one step 1 spent. A runtime that re-establishes a slot
after the application ended its session would have this step asking a fresh
session whether it was alive. Read the Receipts for the two calls before
differencing, and where the label was re-leased in between, the reading is
inconclusive and is reported as inconclusive.

Repeat the probe once after a short wait if the target is a cluster. A revocation
that propagates in seconds is a different finding from one that never happens,
and reporting the first as the second is how a valid report becomes an argument.

## 5. Propose the claim, and say what would refute it

The Hypothesis is `session_handling.lifetime` on the application. It is
supported when the probe is answered as a live session after the ending, against
a control that shows the same request refused with nothing attached. It is
refuted when the probe after the ending is answered exactly the way that control
is.

An absolute expiry is not this claim unless it was measured. "The token has a
long lifetime" read off a `JWT` payload is a statement about a claim in a
document; the finding is that the session still answered, which is a request and
an answer.

## 6. Leave one ended session behind

This Playbook's effects are `mutates_session`: it ends one on purpose. It does
not end another Identity's session, it does not revoke devices it did not
create, and where the ending it needs is a credential change it stops unless the
Program admits that mutation.

Its baseline is `stable_session` at the same time, which reads like a
contradiction and is not one. The baseline is the precondition: the probe in step
1 has to be a session nothing else is disturbing, or a refusal after the ending
says nothing about the ending. The effect is the consequence: step 3 ends that
session. Because conflict is derived from one Playbook's baseline against
another's effects, the pair is what keeps this Playbook alone on a subject --
nothing that moves a session is scheduled beside it, and it is scheduled beside
nothing that needs one held still. That is the right schedule for a reading whose
whole content is one session ending exactly once.
