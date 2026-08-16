# CORS and XSSI: two ways to read a response you were not supposed to

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

Two topics under one heading, because both end with another origin reading the
target's authenticated response.

The CORS half: send `Origin: https://evil.example`, look for it reflected back in
`Access-Control-Allow-Origin` beside `Access-Control-Allow-Credentials: true`,
plus a list of the parser mistakes that produce that -- suffix matching that
accepts `target.com.evil.example`, prefix matching that accepts
`evil-target.com`, a null origin allowed for sandboxed frames, a regex missing
its anchors.

The XSSI half: a JSON or JavaScript response served without an anti-framing
prefix that another origin can load with `<script src>` and read through a
redefined constructor or an array setter.

## The half the Playbook uses

The CORS half, entirely, and it is read rather than exploited. Four header values
off two requests -- one without an `Origin` and one with a foreign one:

```
Access-Control-Allow-Origin:      absent | * | <echoed> | <allowlist>
Access-Control-Allow-Credentials: absent | true
Vary:                             does it name Origin
```

The pairing is the whole thing. `*` alone is a public resource. An echoed origin
alone is sloppy and harmless while credentials are refused. An echoed origin plus
`Allow-Credentials: true` is another site reading this session's answers.

The second request is why the first exists. A header that appears only when a
foreign `Origin` was sent is a reflection; a header that is always there is a
policy. Grepping one response cannot tell them apart, and both look identical in
a report that took one.

## The half that stays out, and why

* **XSSI.** Reading a script-loaded response cross-origin needs a page at another
  origin to do the loading, which is the same hosting problem the clickjacking
  note describes, and the constructor tricks it depends on were removed from
  every current engine. Where a JSON route is genuinely readable by anyone, the
  claim is that it is unauthenticated -- which is a different Playbook's -- rather
  than that it is loadable as a script.
* **Actually reading the cross-origin body.** The Playbook shows the target
  granting permission. Exercising the permission means being another origin.
* **`null` origin acceptance.** Real, and it needs a sandboxed frame served from
  somewhere to demonstrate. Record it as an observation on the header value; do
  not build the frame.
* **Preflight-only findings.** An `OPTIONS` that allows a method the actual
  handler refuses is a preflight that lies, not access. Read the real request.

## The trap in the whole technique

`Access-Control-Allow-Origin` describes what a *browser* will let a script read.
It has nothing to do with whether a request succeeds. A server that answers
`200` with the caller's data to a request bearing a foreign `Origin` and sends no
CORS headers at all is behaving correctly -- the browser discards the response,
and `curl` never cared in the first place.

So a reading taken outside a browser can only ever say what the target permits,
never what a page achieved. That is the honest ceiling of this technique in this
harness, and the Playbook states it rather than blurring it.
