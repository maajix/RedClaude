# WebSocket attacks: the handshake is where this harness stops

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

Everything that can be done to a socket, in one list. Cross-site WebSocket
hijacking. Missing origin checks at the upgrade. Subscribing to a channel that
belongs to somebody else. Injection inside a frame's payload once the connection
is up. Authentication that happens at the handshake and never again, so a token
that expires mid-connection keeps working. Message-level authorisation that does
not exist because the developer assumed the connection was the boundary.

All of it is real. Most of it needs a connection that carries frames.

## The half the Playbook uses

The subscription question, asked at the handshake and answered there.

A multiplexed socket takes a channel name in the upgrade -- a query parameter, a
path segment, a subprotocol -- and decides once whether the caller may have it.
That decision is a normal authorisation check written in an unusual place, and it
can be read the same way any other authorisation check is read: send the same
upgrade under two Identities and compare.

Three handshakes make the reading, and the third one is the part that is usually
skipped:

```
owner's session, owner's channel      -> must be accepted, or nothing means anything
second session, owner's channel       -> the claim
no session, owner's channel           -> tells apart "authenticates and does not
                                         authorise" from "checks nothing at all"
```

The control matters more here than in most classes, because a target that answers
`101` to everything looks exactly like a target with a broken channel check until
the owner's own handshake is in the evidence.

## The half that stays out, and why

* **Everything after the upgrade.** The proxy every request in this harness goes
  through speaks HTTP. A socket upgrade does not continue past it, so no
  application frame is sent or received, and the corpus has no action that would.
  A reading cannot say what the channel carried.
* **Message-level injection.** Needs frames.
* **Token expiry across a live connection.** Needs a connection held open for the
  lifetime of a token.
* **Cross-site WebSocket hijacking.** That is the origin question rather than the
  channel question, it is `session_handling.csrf`, and a different Playbook holds
  it -- one which stops at the same door for the same reason.
* **Channel-name enumeration.** Sending candidate names until one is accepted is
  a wordlist against a live surface, and it is recon work with a different
  Playbook and a different budget.

## The trap in the whole technique

`101 Switching Protocols` is a status line, and the temptation to write "and the
attacker then receives all messages on that channel" after it is enormous.
Nothing in the evidence supports the second clause. The connection may be
accepted and immediately closed, the channel may be empty, the server may filter
per message despite having accepted the subscription, and none of that is
visible from the handshake.

So the claim is exactly what was measured: the target accepted a subscription to
a channel this caller does not own. That is worth reporting on its own, and the
Playbook's step 4 says plainly which half is inconclusive rather than letting a
reader supply the rest.
