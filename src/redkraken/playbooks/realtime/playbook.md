---
description: Ask whether a websocket handshake requires proof of same-origin intent, by opening the same authenticated handshake once from the application's own origin and once from an origin it has never seen.
bb:category: session_handling
bb:outputs: ["session_handling.csrf"]
bb:triggers_all: ["authenticated_endpoint", "websocket_surface"]
bb:skills: ["browser-evidence", "compare-responses"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-02-15
bb:provenance: Written for ticket 49 as the v2 replacement for v1's realtime pack, against the csrf leaf of the ticket 18 vocabulary; v1 shipped a README for this topic and no reference text, so nothing is attached.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_differential", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "credential_effect", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "response_invariant", "polarity": "supports", "min_count": 1}]
---

# Ask what the handshake checks besides the cookie

A websocket connection begins as an ordinary HTTP request that the browser sends
with the origin's cookies attached, and the same-origin policy does not stop a
page on another origin from making it. The only thing that can stop it is the
server checking the `Origin` header on the handshake.

So the question is narrow and answerable: does the handshake succeed when the
session is right and the origin is wrong. Note the direction of the evidence
here -- the *invariance* is the finding, because a server that treats both
origins identically is a server that is not looking.

## 1. Name the handshake and what authenticates it

The subject is an endpoint the recorded surface has identified as a websocket
upgrade. Read from the surface: the path, and how the session travels -- a
cookie, a bearer token in a subprotocol, or a ticket in the query string.

If the session travels as a ticket the page mints per connection, this Playbook
does not apply to the subject. A per-connection ticket is proof of intent, which
is the thing being asked about, and the answer is already no.

## 2. Establish the baseline from the application's own origin

Follow `browser-evidence` and open the connection the way the application does:
its own page, its own origin, the leased session. Store the handshake exchange.

That is the baseline. It says what a handshake that should succeed looks like --
status `101`, the accept header, the negotiated subprotocol.

## 3. Establish the control: the session is what is doing the work

Open the same handshake from the same origin with the session removed. It should
fail. Store the exchange.

This is the control and it is the step that makes the rest readable. A server
that accepts every handshake from anyone, authenticated or not, is a public
endpoint: the variant below will succeed and it will mean nothing. A run without
this control cannot tell that case from the finding.

## 4. Send the variant from an origin the application has never seen

Open the same handshake, with the session, from a page served on a different
origin. One variable: the `Origin` header the browser attaches. Not the path,
not the subprotocol, not the session.

Set it by serving the page from a different origin rather than by writing the
header, and do it through `browser-evidence`. A header written by hand is a
claim about what a browser would send; a browser sending it is the thing itself.

## 5. Difference the three exchanges

Run `compare-responses` over the baseline and the variant, and again over the
control and the variant. Cite what the script returns.

## 6. State the claim, and state what would refute it

The Hypothesis is `session_handling.csrf` on the endpoint. It is supported when
the variant is invariant against the baseline -- the foreign origin got the same
`101` -- and the control shows the session was what authenticated it. It is
refuted when the variant differs from the baseline in the direction of refusal:
a `403`, a close frame immediately after the upgrade, an error message naming
the origin.

Inconclusive covers the rest, and two cases are worth naming. A handshake that
succeeded and then received nothing is inconclusive about this class and worth
recording: the connection is open and it may carry no data a caller was not
entitled to. And a server that answered both origins with a refusal has told you
about the control, not about the origin check.

Cookie flags are a different class. A `SameSite=Strict` cookie that never reached
the handshake is why the variant failed, and that is
`session_handling.cookie_scope` being right rather than this claim being wrong;
record it as an observation and do not restate it as this class.

## 7. Leave the session as you found it

This Playbook reads. It opens connections and closes them, sends no application
message over the socket, and does not reconnect to see whether the first refusal
was transient. Its baseline is `stable_session` because the whole comparison is
about one session's authority at one moment.
