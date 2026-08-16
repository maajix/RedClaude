---
description: A transfer form behind a session cookie, served twice from one source, one variant declaring no framing policy and handing any origin a credentialed read and the other refusing framing outright and offering no cross-origin read at all.
bb:kind: own_pair
bb:classes: ["transport.header_policy"]
bb:subject: /transfer
bb:facts: ["form_request", "state_changing_method", "web_surface"]
bb:identities: ["alice"]
bb:provenance: Written for ticket 52 against the ticket 18 class description, from what the class says rather than from any Playbook's steps; no upstream corpus.
---

# Same bytes, different declaration

`POST /session` issues a session cookie. `GET /transfer` serves a form carrying a
per-session token, and `POST /transfer` performs the transfer if that token comes
back with it.

Everything above is identical on both variants: same routes, same status lines,
same bodies, same cookie with the same attributes, same token check on the write.
The difference is the policy the response declares:

* **vulnerable** declares nothing about framing -- no `Content-Security-Policy`,
  no `X-Frame-Options` -- and reflects whatever `Origin` asked, alongside
  `Access-Control-Allow-Credentials: true`.
* **secure** sends `Content-Security-Policy: frame-ancestors 'none'` and
  `X-Frame-Options: DENY`, and sends no cross-origin headers at all.

## What the ground truth claims, and what it does not

`transport.header_policy` on the vulnerable variant, and nothing else.

The token check is on both halves and it is there to keep
`session_handling.csrf` out of this pair. A fixture that dropped the token on the
vulnerable side would hold two classes and a run that reported either one would
be right, which is not a pair that grades anything.

The cookie is byte-for-byte the same on both halves, `HttpOnly; Path=/;
SameSite=Lax`, for the same reason one directory over:
`session_handling.cookie_scope` is a different pair's question and varying an
attribute here would answer it twice.

There is no `Strict-Transport-Security` on either half. The class names HSTS
first, and this fixture is served over plain HTTP on loopback where a browser
ignores that header, so grading it here would be grading a header nothing
honours. What is left is the half of the class this transport can carry
honestly: framing and cross-origin reads.

## Why the finding is a header rather than a consequence

The vulnerable variant transfers exactly what the secure one transfers, refuses
exactly what it refuses, and returns the same bytes to the same request. Nothing
about the money moves differently. The finding is the declaration itself, which
is what the class says -- a channel policy absent or permissive -- and it is why
every evidence row behind this fixture is a header observation rather than a
response difference.

A reading that framed the vulnerable page and reported that it framed has
observed the policy. A reading that reported a transfer it performed with a
token it was given has reported the fixture working.
