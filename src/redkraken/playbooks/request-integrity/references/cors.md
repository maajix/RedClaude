# CORS: kept almost whole, and narrowed to the pair of headers that decides

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

The cross-origin resource sharing checklist. Send `Origin` and read what comes
back. Try the reflection cases: the origin echoed verbatim, `null` echoed and
honoured, a wildcard, a regular expression anchored at the wrong end so
`evil-acme.com` and `acme.com.evil.net` both match, a scheme downgrade, a
subdomain trusted because a wildcard was written into the allow list. Note
whether `Access-Control-Allow-Credentials` is `true`, because without it the
browser sends no session and the whole thing is a document anybody could fetch.
Then the preflight: `OPTIONS` with `Access-Control-Request-Method` and
`Access-Control-Request-Headers`, and what `Access-Control-Max-Age` does to how
often it is asked. Finish with a hosted page that performs the read and prints
the answer, as proof.

## Why the Playbook kept most of it

Because it is a read, it is bounded, and the observable is a header the
application chose to send. Nothing on the list above changes state, and the
finding is legible without running anything on somebody else's machine.

What the Playbook keeps: the pair of headers as the claim, the verbatim
reflection and the near-miss origin as the two arms, the trusted origin as the
control, and the insistence that the answer be tied to the session. That last one
is the page's best sentence and the Playbook makes it step 1: a permissive header
over a document that says the same thing to everybody is a misconfiguration, not
a disclosure.

## What the Playbook narrowed

**Two arms rather than a list.** The v1 page's origin cases collapse into two
distinguishable outcomes: the application reflects whatever it is sent, or it
matches a pattern that is anchored wrongly. The near-miss origin -- the trusted
host with one character changed, or as a prefix of a longer name -- separates
them, and every further origin on the list produces one of the same two answers.
A hundred origins is a scan against a route.

**`null` is not one of the two.** It is worth reading if it comes back on its own,
and it is not worth an arm: producing a `null` origin means loading the request
from a sandboxed frame or a redirect chain, which is building a page, which is
below the ceiling.

**No preflight probing.** `OPTIONS` with request-method and request-headers is a
question about what a browser would be permitted to send, and this Playbook is
about what a browser would be permitted to read. The permission the reading cares
about is on the actual response.

## What the Playbook refuses

**The hosted proof.** A page on an origin the reading controls, opened in a
browser, performing the read and printing the answer, is the v1 page's finishing
move and it is out. The claim rests on the headers the application returned --
which is exactly what a browser would have acted on -- and a demonstration that
runs the browser has run somebody else's software to prove a thing the response
already said.

**Anything on the write side.** `Access-Control-Allow-Methods` naming `PUT` is
interesting and it is not evidence of anything until a write happens, which is the
other note in this directory and the other class.

## The one thing to get right in the write-up

Name whose data it is. A supported `session_handling.cross_origin_read` says a
browser will hand this response to another origin; it does not say a person was
affected. The fields the response carries, and whether they are the caller's own,
are what turns the first sentence into the second, and step 6 asks for that
explicitly rather than leaving it to the phrase "sensitive data".
