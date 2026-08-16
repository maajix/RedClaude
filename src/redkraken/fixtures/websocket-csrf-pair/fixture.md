---
description: A cookie-authenticated WebSocket handshake served twice from one source, one variant completing the upgrade for a handshake from any origin and the other answering 403 unless the Origin matches the host it was served from.
bb:kind: own_pair
bb:classes: ["session_handling.csrf"]
bb:subject: /socket
bb:facts: ["authenticated_endpoint", "websocket_surface"]
bb:identities: ["alice", "bob"]
bb:provenance: Written for ticket 49 against the ticket 18 class description, from what the class says rather than from any Playbook's steps; no upstream corpus.
---

# A socket the browser will open for anybody

`GET /socket` with an upgrade handshake returns `101` and one frame carrying the
session's inbox. The session comes from a cookie, which means a page on any
origin can open this socket and the browser will attach the cookie for it. That
is the class, and the variants differ in whether the server notices:

* **vulnerable** completes the handshake whatever `Origin` says, or says
  nothing.
* **secure** answers `403` unless `Origin` matches the host the request was
  sent to.

The allowed origin is computed from the request's own `Host` header rather than
written into the fixture, so the check holds wherever the evaluator serves it.
A handshake carrying no `Origin` at all is not a browser's, and the secure
variant refuses it too.

## Why the finding is an invariance

For most classes the finding is a difference. Here it is the absence of one: the
vulnerable variant answers the same `101` to a same-origin handshake and to a
foreign one, and that sameness is the defect. The secure variant is the one that
differs across origins.

A run that only sends a same-origin handshake sees `101` on both variants and
has measured nothing.

## Why the 401 is on both variants

Same reason as the other paired fixtures. A refused handshake is evidence about
origin policy only if the session was working at the time, so both variants
answer `401` to a cookie nobody issued and `101` to a working session from the
right origin.

## What the ground truth claims

`session_handling.csrf` on the vulnerable variant, and nothing else.

The frame carries the caller's own inbox and nobody else's, so
`authorization.object_ownership` and `information_disclosure.excess_field` are
not gaps in this file -- both variants scope the push by session and there is no
identifier to substitute. Nothing the caller sends is echoed, nothing is stored,
the refusal bodies are fixed strings and the socket accepts no messages at all
-- the server writes one frame and closes -- so the injection family,
`information_disclosure.error_detail` and `business_logic.replay` against this
fixture are false positives.

## What the handshake does not do

One frame, then the connection closes. There is no read loop, no message
protocol and no second frame, because the class is decided at the handshake and
everything after it would be a different fixture.
