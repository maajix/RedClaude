---
description: A logout route served twice from one source, both variants clearing the client's cookie and only one of them ending the session on the server, so the token held across the logout still answers as a live session on the other.
bb:kind: own_pair
bb:classes: ["session_handling.lifetime"]
bb:subject: /session/logout
bb:facts: ["cookie_parameter", "state_changing_method"]
bb:identities: ["alice"]
bb:provenance: Written for ticket 50 against the ticket 18 class description, from what the class says rather than from any Playbook's steps; no upstream corpus.
---

# The logout that is a Set-Cookie and nothing else

`POST /session` logs in and issues `session=s-alice-3ce8`. `GET /account` reads
it. `POST /session/logout` ends the session, or says it does.

Both variants answer the logout `200` and both clear the client's copy with
`session=; Max-Age=0`. Only one of them touches the server:

* **vulnerable** leaves the record live. The same value, replayed at
  `GET /account` after the logout, answers `200`.
* **secure** discards the record. The same replay answers `401`, with the same
  body as a value that was never issued.

## The control is an invented cookie

Both variants answer `401` to a session value nobody minted. That reading is
what makes the rest legible: a route that answered `200` to anything would be a
route that never authenticates, which is `credential_verification` and a
different pair.

## Why the value is fixed

`s-alice-3ce8` is the same on every login and in both variants. A run's whole
method here is to hold one token across an event and send it again, and a
fixture that re-minted a value per request would be measuring the run's
bookkeeping rather than the server's.

It also keeps two repeats of an evaluation identical, which is what the
evaluator's repeat count is for.

## What is not here

No credential change and no administrative revocation. The Playbook names three
endings and this pair holds the one that can be caused with a request the
fixture already serves; the other two would need an account mutation and a
device list, and modelling them would put two more classes into a pair that
declares one.

No absolute expiry either. A token that ages out is a different reading -- it
needs a clock, not an event -- and a fixture that expired sessions on a timer
would make the repeats disagree with each other.

## Ground truth

* **vulnerable** holds `session_handling.lifetime`. The token that worked before
  `POST /session/logout` still answers `200` at `GET /account` after it.
* **secure** holds nothing this catalogue declares. After the logout the token
  is answered exactly the way an invented one is.
