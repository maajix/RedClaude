# Request smuggling and desync: refused, and the refusal is in the schema

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

The desync canon. Send one request that two hops disagree about the length of --
`Content-Length` beside `Transfer-Encoding`, a chunked body with a trailing
length, an obfuscated `Transfer-Encoding` header one hop parses and the other
does not -- so that the front end forwards more bytes than the back end consumes.
The remainder sits at the head of the connection and prefixes whoever is next.
Then the standard variants: CL.TE, TE.CL, TE.TE, the H2.CL and H2.TE forms once a
front end downgrades HTTP/2 to HTTP/1.1, and client-side desync where the victim's
own browser supplies the poisoning request.

Then the yields, which are the reason the page existed: capture another user's
request wholesale, prefix a response with markup of the attacker's choosing,
reach an internal path the front end would have refused, and poison a shared
cache.

## Why the Playbook refuses all of it

**It is unmakeable here, and that is recorded rather than argued.** 025 registers
`transport.request_framing` as `unmakeable`, with the mechanism attached: the
interception proxy parses and re-serialises every request, so the byte framing
the target sees is the proxy's rather than the reading's. A smuggling result
obtained through this harness is a statement about the proxy. The refusal is a
trigger on the hypothesis table -- `ENABLE ALWAYS`, so a restore cannot skip it --
which means the class cannot be written down at all, however convincing the
observation looked. Pinning ALPN does not help: the re-serialisation is above the
protocol, not below it.

A real test needs a raw socket. The one-egress-path rule denies it, deliberately,
because a harness with a second way out has no enforceable scope.

**Every yield lands on somebody else.** The remainder prefixes the next request on
that connection, and the next request belongs to a person who is not part of this
engagement. There is no bounded version of that and no undo. Nothing in this
corpus is allowed to have an effect whose blast radius is "whoever connects
next", which is separately why the Playbook's ceiling names it even though the
schema already refuses it.

**The cache half belongs somewhere else anyway.** What a front end stored and
handed to the next caller is `information_disclosure.cached_response`, and
`web-cache` is the Playbook that asks it -- by requesting a document and asking
who it was for, which is a read that reaches nobody else.

## What the Playbook kept

The framing question, moved one layer down to where it is answerable. The one
thing about the front end that is measurable without composing bytes is what it
negotiated: version, cipher, protocol. That is `transport.tls_configuration`, it
comes from the measurement lane rather than from the proxy path, and it is what
the Playbook under this name now asks.

The rest is the ceiling, and step 6 states it in the negative because that is the
form a reading can check itself against: no second length header, no chunked body
with a trailing length, no request line the front end would rewrite.

## If a desync genuinely matters

Say so and stop. A verdict of `inconclusive` naming the missing capability --
"the interception proxy re-serialises every request, so framing cannot be
observed" -- routes to an operator who can decide whether a raw-socket test
against a target they have confirmed is in scope, in a window they have arranged,
is worth running outside this harness.

That is the whole of what this Playbook can honestly do with the subject.
