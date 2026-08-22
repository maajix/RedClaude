---
description: Ask whether a socket handshake accepts a subscription to a channel the caller does not own, by naming a second Identity's channel in the handshake and comparing what the upgrade answers against the owner's own handshake for the same channel.
bb:category: authorization
bb:outputs: ["authorization.channel_subscription"]
bb:triggers_all: ["multiple_test_identities", "query_parameter", "websocket_surface"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 52 against a new channel-subscription leaf added by ticket 52; the v1 websocket text is attached as a maintainer reference and step 5's limit is where this Playbook and the v1 page part company.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_invariant", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "credential_effect", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "credential_effect", "polarity": "supports", "min_count": 1}]
bb:references: ["websocket-attacks.md"]
---

# A socket that opens is a socket that was allowed to

A realtime surface multiplexes. One connection carries many channels -- a room, a
document, an order, a tenant -- and which channel a connection is entitled to is
decided once, at the handshake, from a name the caller supplied. That name is a
query parameter, which is what this Surface says it has.

The question is whether the name is checked against the caller, or only parsed.

## 1. Fix the channel names, and whose they are

Two Identities and one channel each, which here is two Tasks: a run acts as
whichever Identity its Task was opened under, the step does not choose it and
there is no argument for it. Establish each session in its own Task, hold it, and
record the channel name that Identity is entitled to and where in the handshake
the name goes. The claim below is made by comparing what the two Tasks'
Receipts hold.

A reading with one Identity cannot make this claim. A channel name that the
second Identity was also entitled to is a name that proves nothing, so the name
has to be one the first Identity owns and the second does not -- and that has to
be established from the target's own answers rather than assumed from the
spelling.

`stable_session` is the baseline: both sessions live across every step below.

## 2. Open the owner's channel, as the owner

Send the upgrade for the first Identity's channel under the first Identity, and
record the handshake response whole: status line, `Upgrade`, `Connection`,
`Sec-WebSocket-Accept`, and every header the target added.

That is the control and it is a `credential_effect`: this target accepts this
channel for this caller, so an acceptance means something. Without it, a later
acceptance cannot be told from a target that accepts every handshake it is sent.

## 3. Ask for the same channel as the other Identity

Send the same upgrade, byte for byte, with the second Identity's session and the
first Identity's channel name. Then send it a third time with no session at all.

Three handshakes, one difference each. `compare-responses` over the three is the
reading:

* the owner is accepted and the other two are refused: the name is checked
* all three are accepted: the name is parsed and not checked, which is the claim
* the anonymous one is refused and the second Identity is accepted: the target
  authenticates the connection and then authorises nothing, which is the same
  claim and the more common shape

## 4. Say what the handshake did not tell you

An accepted upgrade is a connection, not a message. This harness stops there and
says so rather than implying more.

The proxy every request goes through terminates the exchange it understands, and
a socket upgrade is not one: the connection does not continue past the door, so
no application frame is sent, none is received, and nothing here reads a payload
off the wire. What the evidence holds is a handshake the target accepted for a
channel the caller does not own.

That is a real claim and a bounded one. What it does not establish is that data
flowed, that the channel was busy, or that anything the other Identity sent would
have arrived. A reading tempted to say "and then the messages were readable" has
left the evidence behind, and reports `inconclusive` on that half.

Where the question is whether an *origin* is checked at the handshake rather than
whether a *caller* is, the class is `session_handling.csrf` and belongs to the
Playbook holding it. That one stops at the same door for the same reason; this
one differs from it by asking about the channel name instead of the origin.

## 5. State the claim, and state what would refute it

The Hypothesis is `authorization.channel_subscription` on the handshake. It is
supported when the target accepts a subscription to the first Identity's channel
under the second Identity's session, against a control showing acceptance means
something and a refusal for the anonymous case. It is refuted when the variant
handshake is invariant against a control that opened -- meaning the second
session is good and the server still refused it that channel.

An upgrade refused with a `4xx` that also refuses the owner is not a refutation.
It is a route that is not working, and it is reported as inconclusive.

## 6. Two Identities, one channel, no traffic

This Playbook's effects are `read_only`. It sends three handshakes against one
recorded route and reads three answers.

It does not reconnect in a loop to see whether a limit exists -- that is
`rate_limiting.per_identity` -- does not iterate channel names to discover which
ones exist, does not hold a connection open, and does not send an application
message over any socket it opened. Both Identities are the tester's own, both
channels are the tester's own, and the second Identity's own channel is never
handed to the first.
