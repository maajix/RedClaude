---
description: Ask whether a step-up route enforces the factor it asks for or merely offers it, by completing the sensitive action while withholding, downgrading and replaying the second factor the client was told to present.
bb:category: authentication
bb:outputs: ["authentication.factor_enforcement"]
bb:triggers_all: ["state_changing_method", "tech_webauthn"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: approval_required
bb:effects: mutates_account
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 50 as the v2 replacement for v1's webauthn pack, against the factor-enforcement leaf of the ticket 18 vocabulary; v1 shipped a README for this topic and no reference text, so nothing is attached.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_invariant", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "credential_effect", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "state_change", "polarity": "supports", "min_count": 1}]
---

# A second factor the client can decline is not a second factor

A step-up flow has two halves that can disagree. The client is told which factor
to present -- an authenticator assertion, a code, a push -- and the server is
supposed to refuse the action until it sees one. Between them sits a request the
client composes, and the defect in this family is always the same: the server
took the client's word for which factor happened, or for whether one happened at
all.

The subject is the route behind the prompt, not the prompt. What is measured is
whether the *action* completed.

## 1. Establish that the factor is really asked for

Follow `use-identity` and drive the sensitive route once, honestly, with the
second factor completed. Record the request the client sent for the factor step
and the request it sent for the action, and record that the action took effect.

Then send the action request with the factor field replaced by a value of the
right shape that was never issued. Record that answer. That is the control and it
is a `credential_effect`: it says the route reaches a factor decision and refuses
something. A route that accepts an invented assertion is not enforcing anything,
and that claim is `authentication.credential_verification`.

## 2. Send one downgrade at a time

Each variant is the action request with a single change:

* the factor field omitted
* the factor field present and empty
* the step order broken: the action sent without the preceding factor step,
  using only the session
* the client's own statement about which factor ran changed -- a method name, a
  `type`, a list of allowed factors -- to one the account holds but the flow did
  not perform
* the factor material from the earlier successful step replayed against a second
  action

The last two are the ones that matter. A route that lets the client name the
factor is a route where the weakest enrolled factor is the real one, and a route
that accepts a replayed assertion has a factor that only has to happen once.

## 3. Read whether the action happened

Run `compare-responses` over each variant against the two ends of the scale, then
verify the state rather than the status. Read the account route back and record
whether the sensitive value changed. That is the `state_change` and it is the
evidence: a `200` from a step-up route that changed nothing is not a bypass, and
a `302` that changed the recovery address is.

## 4. Propose the claim, and say what would refute it

The Hypothesis is `authentication.factor_enforcement` on the endpoint. It is
supported when the action took effect without the factor the flow asked for --
omitted, downgraded, replayed or reordered -- against a control that shows an
invented factor being refused. It is refuted when every variant is answered the
way the invented factor is and the account is unchanged after each.

Whether a *second* Identity could drive this route is not this class. That is
`authorization.function_access` and it needs a second identity, not a missing
factor.

## 5. Change one thing, on our own account, and change it back

Effects are `mutates_account` and risk is `approval_required`: a successful
variant alters something on an account -- a recovery address, an enrolled
authenticator, a credential. It runs only against a leased Identity the Program
owns, it never runs against another user's account, and every value it changes
is recorded before the change and restored after the reading. Where the Program
grants no account mutation, this Playbook stops after step 1 and reports the
control alone.
