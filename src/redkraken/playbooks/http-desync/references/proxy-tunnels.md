# Proxy tunnels: refused, and the reason is the egress rule rather than a technique

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

Getting a forwarder to forward somewhere it was not meant to. Send `CONNECT
internal.host:22` and see whether a tunnel opens. Send an absolute-form request
line -- `GET http://internal.host/ HTTP/1.1` -- to a front end that still honours
one. Rewrite the authority a hop routes on: `Host`, `X-Forwarded-Host`,
`X-Forwarded-Server`, `Forwarded`. Chain two front ends so the second believes
the first vouched for the destination. Then the yields: reach a service that has
no route from the internet, use the deployment's own address as the source of a
request, and pivot.

## Why the Playbook refuses all of it

**The destination is the whole point, and it is out of scope by construction.**
Every one of these techniques succeeds by causing a request to arrive somewhere
the Program did not grant. That is the definition of leaving scope, and it does
not become acceptable because the request left from inside the target rather than
from here. The scope policy is a statement about which hosts may be reached, not
about which socket reached them.

**There is one egress path and it is pinned.** This harness resolves a name once,
decides about every address it answered with, and dials the address it decided
about. A tunnel is a second way out with no policy in front of it, which is
exactly the shape the one-egress-path rule exists to prevent. A reading that
opened one would have made every scope decision in the engagement unenforceable
for the duration.

**`CONNECT` is not a read.** Even a tunnel that goes nowhere has established a
connection the Program did not authorise, and this Playbook is `read_only`
against scoped ingress.

## What the Playbook kept

The authority question, in two places, and neither of them is here.

Where a hop routes on an authority the caller supplied and a second component
builds a URL from a different one, that is a parsing disagreement inside one
scoped application: the class is `injection.parameter_precedence` and the
Playbook is `request-parsing`, whose fixture holds `X-Forwarded-Host` as a
control on both variants for exactly this reason.

Where a parameter the caller supplies decides what the server fetches, that is
`injection.request_forgery` and the Playbook is `ssrf-url-routing`, which asks it
against a route the Program scoped rather than by getting a forwarder to
volunteer.

What is left for this Playbook is the ceiling, and step 6 names it in the
negative: no `CONNECT`, no absolute-form request line, and no request whose
authority names a host other than the one the Task scoped.

## If a forwarder genuinely looks open

Say so, name the observation that suggested it, and stop. An operator can decide
whether the destination is in scope and arrange a test that starts from a grant
rather than from a tunnel. A reading that establishes the tunnel first and asks
afterwards has already done the thing the answer was supposed to authorise.
