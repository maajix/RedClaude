---
description: An account route behind a session cookie, served twice from one source, one variant scoping the cookie to the registrable parent and honouring it from any host and the other scoping it to one host, one path and HTTPS and refusing it elsewhere.
bb:kind: own_pair
bb:classes: ["session_handling.cookie_scope"]
bb:subject: /account
bb:facts: ["cookie_parameter", "read_method"]
bb:identities: ["alice"]
bb:provenance: Written for ticket 50 against the ticket 18 class description, from what the class says rather than from any Playbook's steps; no upstream corpus.
---

# What the server declared, and where it honours what it declared

`POST /session` takes an email and a password, checks both, and issues a session
cookie. `GET /account` and `GET /account/preferences` read it.

The variants differ in two places at once, because the class is both of them:

* **vulnerable** issues `session=...; Domain=localhost; Path=/; SameSite=None`
  -- every sibling host under the registrable parent, every path, plain HTTP,
  and cross-site requests -- and answers `200` to that cookie no matter which
  host the request was addressed to.
* **secure** issues `session=...; Path=/account; Secure; HttpOnly; SameSite=Lax`
  and answers `401` when the cookie arrives at any host other than the one that
  issued it.

## Why both halves are here

A pair that differed only in the `Set-Cookie` line would grade a run for reading
a header, and the whole point of the class is that a missing flag is a
configuration rather than a finding.

A pair that differed only in enforcement would be unreadable: nothing would say
the cookie was ever supposed to reach the second host, so a run could not tell
an exposure from a normal request.

So the vulnerable variant declares a scope it should not have *and* honours the
credential inside that scope, which is what a report has to show. The `Host`
header is how the fixture models arriving somewhere else: the evaluator serves
one origin, and a request addressed to another name is the same thing a browser
would do after attaching the cookie at a sibling.

## The control

The declared attributes, read off the response that issued the cookie. Both
variants set them, they differ, and neither of them is a verdict on its own.

## What is not here

`HttpOnly` is present on the secure variant and absent from the vulnerable one,
and it is not the difference this pair grades. A cookie readable from script
matters where script runs, which is `injection.markup` and a class this fixture
does not hold.

Nothing here logs out, rotates or expires a session. That is
`session_handling.lifetime` and it has its own pair in this catalogue.

## Ground truth

* **vulnerable** holds `session_handling.cookie_scope`. The cookie is scoped to
  the registrable parent and the session is honoured at any host presenting it.
* **secure** holds nothing this catalogue declares. The cookie is host-only and
  path-scoped and the session is refused anywhere else.
