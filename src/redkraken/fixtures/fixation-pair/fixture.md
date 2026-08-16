---
description: An authorisation callback served twice from one source, both exchanging only codes the fixture minted, one of them minting a session for whoever opens the callback and the other requiring the browser to hold the flow value it left with.
bb:kind: own_pair
bb:classes: ["session_handling.fixation"]
bb:subject: /oauth/callback
bb:facts: ["query_parameter", "tech_oauth"]
bb:identities: ["alice"]
bb:provenance: Written for ticket 50 against the ticket 18 class description, from what the class says rather than from any Playbook's steps; no upstream corpus.
---

# A callback is a URL; the question is whether it is also a session

The whole round trip is inside this fixture, because the class is about the two
ends of it agreeing:

* `GET /oauth/start` mints `state`, sets it as a `flow` cookie, and returns the
  authorisation URL.
* `GET /oauth/authorize?state=...` mints a code for a flow that was started and
  redirects to the callback with it.
* `GET /oauth/callback?code=...&state=...` is the subject.
* `GET /whoami` says whose session a caller holds.

Both variants refuse a code nobody minted. The difference is what the callback
does with the browser:

* **vulnerable** exchanges the code and never reads `state` or the `flow`
  cookie. Opened anywhere, by anything, it returns a session.
* **secure** requires the `flow` cookie, requires it to equal `state`, and
  requires that to be the state the code was minted for. Anything else is `400`
  and no session.

## The second browser is a request without the cookie

On a real target the reading is two browser profiles, because the binding lives
in browser state. Here it is one request that carries the `flow` cookie and one
that does not, which is the same distinction with the profile machinery removed.

That is also why the fixture keeps the cookie rather than putting the whole
binding in the URL: a run that only compared query parameters could not tell an
application that binds with a cookie from one that binds with nothing, and
telling those apart is most of the Playbook.

## Counted values, not random ones

`st-0001`, `c-st-0001`, `s-c-st-0001`. Two repeats of an evaluation see the same
values, and a run can name exactly what it delivered. A random `state` would
make the pair's own behaviour unquotable without adding anything: the binding is
whether it is compared, not whether it is unguessable.

## What is not here

No identity provider. The Playbook is explicit that a real issuer is a third
party the Program did not authorise, and a fixture that modelled one would be
teaching a run to drive it.

No `redirect_uri` handling. An authorisation server that accepts an unregistered
redirect target is a real finding and a different class, and this fixture's
`authorize` only ever redirects to its own callback.

## Ground truth

* **vulnerable** holds `session_handling.fixation`. A callback URL replayed with
  no `flow` cookie returns a session, and `GET /whoami` answers with the
  subject.
* **secure** holds nothing this catalogue declares. The same request is `400`,
  and `GET /whoami` afterwards is `401`.
