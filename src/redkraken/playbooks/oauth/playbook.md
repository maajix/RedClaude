---
description: Ask whether an authorisation callback binds the code it receives to the browser that started the flow, by completing one flow, holding its callback, and delivering it to a second browser that never asked.
bb:category: session_handling
bb:outputs: ["session_handling.fixation"]
bb:triggers_all: ["query_parameter", "tech_oauth"]
bb:skills: ["browser-evidence", "use-identity"]
bb:risk: approval_required
bb:effects: mutates_session
bb:baseline: none
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 50 as the v2 replacement for v1's oauth pack, against the session-fixation leaf of the ticket 18 vocabulary; two v1 texts are attached as maintainer references and both describe the callback delivery this Playbook performs.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_invariant", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "credential_effect", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "state_change", "polarity": "supports", "min_count": 1}]
bb:references: ["oauth2-attack-via-google-oauth2-playground.md", "oauth2.md"]
---

# The flow that ends in a browser that never started one

An authorisation flow is a round trip: a browser sends the user to an issuer,
the issuer sends a code back to a callback, and the callback turns that code
into a session. The binding that holds the two halves together is a value the
client generated before it left -- the `state` parameter, the PKCE verifier, a
cookie set on the way out.

Where that binding is absent, or present and never compared, a callback is just
a URL that mints a session in whichever browser opens it. That is the class, and
it is read in a browser because it is a browser behaviour.

## 1. Record the outbound half

Follow `use-identity` and start the flow in a browser under `browser-evidence`.
Before following the redirect, record from the authorisation URL: whether
`state` is present, whether `code_challenge` is present, and what `redirect_uri`
names. Record any cookie the client set on the same response.

A flow with no `state` and no verifier is already the interesting shape, but it
is not yet the finding: an application can bind the flow with a cookie it never
put in the URL.

## 2. Complete the flow once, honestly

Let the flow finish in that browser. Record the callback URL exactly as the
issuer produced it, and record the session that came back. This is the control
and it is a `credential_effect`: it says the callback exchanges a code for a
session at all.

The account on the issuer side is the leased Identity's. This Playbook consents
on behalf of nobody else.

## 3. Ask whether the binding is compared

Two variants, each one flow, each read in a browser:

* replay the recorded callback in a second, clean browser profile that never
  started a flow. Nothing in that profile holds the `state` or the cookie
* start a fresh flow, then open the callback with `state` changed by one
  character

The first asks whether the binding is required. The second asks whether it is
compared. A callback that answers the second with an error and the first with a
session is checking `state` against a cookie the browser still had.

## 4. Read what the second browser ended up with

A redirect to a dashboard is not a session. In the second browser, follow the
callback with one authenticated read of the identity route and record which
account answered. That is the `state_change`: a browser that never authorised
anything now holds a session, and whose it is decides the report.

Where the target's flow is an account *linking* rather than a login, the same
reading applies to the link: an identity attached to an account that never asked
for it is the same defect and the same class.

## 5. Propose the claim, and say what would refute it

The Hypothesis is `session_handling.fixation` on the application. It is
supported when a browser that did not start the flow ended it holding a session,
against a control that shows the honest flow producing one. It is refuted when
the callback refuses the delivered code -- no session, and the identity route
answers as it does when nobody is logged in.

`redirect_uri` handling is a neighbouring question this Playbook does not
answer. Where the callback accepts a redirect target the client never
registered, that is an open redirect and belongs to its own class and reading.

## 6. Two browsers, one issuer, no third parties surprised

Effects are `mutates_session` and risk is `approval_required`. The flow touches
an identity provider that is not the Program's target: this Playbook completes
it once with a leased Identity, replays only the callback it already holds, and
sends nothing further to the issuer. The second browser profile is ours, so the
session it ends up holding is one nobody else has to clean up.
