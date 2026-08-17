# HTTP/2 downgrading: the one half that survives, and where it went

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

Two claims joined by a mechanism.

The mechanism: a front end that speaks HTTP/2 to the caller and HTTP/1.1 to the
origin has to rewrite every message, and the rewrite is where the two hops stop
agreeing. HTTP/2 carries length in the frame layer, so a `content-length` header
inside a request is advisory; a front end that copies it into the HTTP/1.1
request it forwards has produced a message whose declared length is the caller's
choice. Hence H2.CL and H2.TE, which are the HTTP/2 spellings of the desync
family, plus header-name smuggling through characters HTTP/2 permits in a name
and HTTP/1.1 does not.

The other claim: find out whether the downgrade is happening at all. Compare what
ALPN negotiates against what the origin appears to speak, read `Alt-Svc`, look
for HTTP/2-specific behaviours in the answers, and note that a downgrading
deployment is a precondition for everything above.

## Why the Playbook refuses one half

The first claim is desync, and desync is refused for the reason the smuggling
note beside this one gives at length: 025 records `transport.request_framing` as
unmakeable behind the interception proxy, with a trigger rather than advice,
because the proxy parses and re-serialises every request. The framing a
downgrading front end would mishandle is not framing this harness can produce.

## What the Playbook kept

The second claim, in full, and it is what the Playbook under this name now is.

"Which protocol does this deployment actually negotiate" is a question with an
admissible answer, and 025 is the reason: `transport.tls_configuration` is
`probe_only` with `allowed_fields` of exactly `tls_version`, `cipher` and `alpn`,
answerable from a receipt taken on the measurement lane, which does not intercept.
That is not a technicality -- 025's own text records the case that made the
distinction necessary: version and cipher matched the origin in every measured
cell by coincidence, and ALPN did not, because an unpinned proxy told a client
`h2` while the origin spoke `http/1.1` only. The gap between what the caller is
told and what the origin does is precisely this page's second claim, and it is
measurable.

So the Playbook's steps are: write down what the deployment advertises from an
ordinary read, take a measurement on the lane whose receipt is citable, take it
twice so a negotiation becomes a property, and compare. The finding is a
disagreement between the advertisement and the wire.

## What is worth remembering about the downgrade itself

A supported `transport.tls_configuration` on a downgrading front end is worth
writing up as what it is -- an inconsistency between what callers are offered and
what the origin speaks -- and worth not writing up as what it is not. A downgrade
is a precondition for the desync family and never evidence of it. The finding
says the two hops speak different protocols; it does not say a message crossed
between them wrongly, and nothing available here could show that it did.
