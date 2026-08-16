---
description: A cookie-authenticated WebSocket that takes the topic to subscribe to in its handshake, served twice from one source, one variant attaching any authenticated caller to any topic and the other refusing a topic the caller is not entitled to.
bb:kind: own_pair
bb:classes: ["authorization.channel_subscription"]
bb:subject: /socket
bb:facts: ["authenticated_endpoint", "multiple_test_identities", "query_parameter", "websocket_surface"]
bb:identities: ["alice", "bob"]
bb:provenance: Written for ticket 52 against the class description ticket 52 added, from what the class says rather than from any Playbook's steps; no upstream corpus.
---

# Who is calling is settled; what they may listen to is not

`GET /socket?channel=<topic>` with an upgrade handshake returns `101` and one
frame carrying that topic's events. The server publishes two topics, `orders` and
`payouts`, and holds a list of what each account may subscribe to: `alice` may
have `orders`, `bob` may have `orders` and `payouts`.

Both variants read the session cookie, both answer `401` without one, both refuse
a handshake whose `Origin` is not the host it was sent to, and both answer `404`
for a topic that does not exist. The difference is one check:

* **vulnerable** completes the handshake for any topic the caller names, so
  `alice` receives `payouts`.
* **secure** answers `403` unless the topic is on the caller's list.

## What the ground truth claims, and what it does not

`authorization.channel_subscription` on the vulnerable variant, and nothing else.

A topic here is a stream, not an object. There is no owner column, no identifier
to substitute and no per-row record: what the caller asks for is delivery of a
named feed, and what the server decides is whether to attach them to it. That is
what separates this from `authorization.object_ownership`, which another pair
grades on an HTTP read of a numbered object, and from
`authorization.tenant_isolation`, which is about a boundary between organisations
rather than a list of feeds.

The origin check is on both halves and it is there to keep
`session_handling.csrf` out of this pair, exactly as the other socket fixture
puts it on neither. Two socket fixtures that both varied their origin check would
be two fixtures grading one class.

The entitlement list is published in the source rather than implied, so a run
that reports the secure variant as vulnerable, or reports the vulnerable one for
the wrong topic, is wrong against a stated rule instead of against a rule the
grader had to infer.

The decision is made once. That is the whole reason this class is not the same
question as a route-by-route authorization check: the handshake is the only place
the server gets to say no, and every frame after it inherits whatever it said.
This fixture writes one frame and closes, because everything after the first
frame would be a different fixture.

Nothing here echoes what the caller sent, stores anything, accepts a message, or
answers with a detail from an exception.
