---
description: Ask whether a response that only exists because the caller holds a session is made readable to an origin the application never meant to trust, by sending the same authenticated read three times under three origins and comparing the two headers that decide who may read the answer.
bb:category: session_handling
bb:outputs: ["session_handling.cross_origin_read"]
bb:triggers_all: ["authenticated_endpoint", "header_parameter", "read_method"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-05-15
bb:provenance: Written for ticket 56 as the v2 replacement for v1's request-integrity pack against a new cross_origin_read leaf added by ticket 56; the pack's two pages are attached as maintainer references, its forged-write proofs are refused by step 7, and the write half of its subject stays 018's session_handling.csrf, which `realtime` outputs.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_invariant", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "response_invariant", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "response_differential", "polarity": "supports", "min_count": 1}]
bb:references: ["cors.md", "csrf.md"]
---

# Ask who is allowed to read the answer, not who is allowed to ask

An authenticated read answers because the caller holds a session. A browser will
attach that session to a request another site made, and will then refuse to hand
the answer back to that site -- unless the application said otherwise. Two
response headers are the whole of "otherwise", and this reading is about what the
application puts in them and for whom.

The subject is an authenticated read on a route whose answer varies with a header
the caller controls. The whole reading is four requests and it changes nothing.

## 1. Hold the session, and read the subject once

Lease the Identity through `use-identity` and send the subject once, with no
`Origin` header at all.

This is the baseline, and it is here to establish two things before any origin is
involved. First, that the route answers for this session -- a route that answers
the same for nobody is not tied to a session and is not this reading's subject.
Second, what is in the answer: name the fields that are the caller's own rather
than the application's -- an address, a plan, an identifier, a balance. A
permissive header over a document that says the same thing to everybody is a
misconfiguration and not a disclosure, and step 5 is where that distinction is
spent.

Complete this step with the status, the fields that are the caller's, and the
absence or presence of the two headers when no origin was sent.

## 2. Send it again under an origin the application has a reason to trust

One request, identical, plus `Origin:` naming a site the application itself
points at -- its own scheme and host, or a partner origin named in something the
application published.

This is the control, and it is the arm that keeps the reading from reporting a
deliberate configuration. An application that answers a known origin with
`Access-Control-Allow-Origin` for that origin and
`Access-Control-Allow-Credentials: true` has been configured to do that. If the
arm in step 3 gets the same treatment as this one, the difference the reading is
looking for is not there.

## 3. Send it again under an origin the application has no reason to trust

One request, identical, plus `Origin:` naming an origin that has nothing to do
with this application. One arm, one changed header. Then a second arm, also one
request, whose origin is the trusted one from step 2 with one character changed
-- a different top-level domain, or the trusted host as a prefix of a longer name.

The second arm is not a duplicate. A reflection that accepts anything and a
reflection produced by a prefix or suffix match are different defects with
different fixes, and the answer to which one this is comes from whether the
near-miss origin came back in the header. Two arms, four requests in total with
steps 1 and 2, and no more: this reading does not enumerate origins.

## 4. Compare the three answers

Run `compare-responses` over the baseline and each arm, and cite what it returns.
Quote, verbatim, the two header lines from every arm that carried them:

* `Access-Control-Allow-Origin`, and whether its value is the origin that was
  sent, a fixed value, or `*`
* `Access-Control-Allow-Credentials`, and whether it is `true`

The pair is the claim, and neither half carries it alone. `*` with no credentials
line means a browser will send the request without the session and get a document
that is not the caller's. A reflected origin with `Access-Control-Allow-Credentials:
true` means a browser will send the session and hand the answer to whoever asked.
Only the second is this class.

Say also whether the body differed between the arms. It should not: this defect
is entirely in the headers, and an arm whose body changed as well is a route that
varies with `Origin` for some other reason and is a different question.

## 5. State the claim, and state what would refute it

The Hypothesis is `session_handling.cross_origin_read` on the subject. It is
supported when the untrusted origin came back in `Access-Control-Allow-Origin`
beside `Access-Control-Allow-Credentials: true`, the trusted-origin control was
answered the same way it was before this reading started, and the fields step 1
named are the caller's own rather than the application's. It is refuted when the
untrusted arms were answered exactly as the baseline was -- no header, or a fixed
value that is not what was sent -- which is what a correctly configured allow list
looks like.

Anything else is inconclusive: a route that answers the same to no session, a
wildcard with no credentials line over a document that is public anyway, an arm
whose body moved.

Three neighbours are close.

* Where the question is whether a state-changing request is accepted without proof
  of same-origin intent, the class is `session_handling.csrf`. It is a different
  claim and it is refused here for the reason step 7 gives.
* Where the question is which channel policy headers a page carries, the class is
  `transport.header_policy` and the Playbook is `browser-framing`.
* Where the answer carries fields belonging to another caller rather than to this
  one, the class is `authorization.object_ownership` or
  `information_disclosure.log_record`, and the header was never the point.

Cite the Artifacts, the difference the script returned, and the two header lines.

## 6. What makes this reportable, and what does not

A supported Hypothesis here says a browser will hand this response to another
origin. It does not by itself say anybody's data moved, and the write-up has to
carry the difference.

What raises it: the fields step 1 named are the caller's own; the origin that came
back is one anybody can obtain; the route is reachable with the session a normal
user holds.

What lowers it: the reflected origin is one the operator controls; the document is
the same for every caller; the credentials line is absent, so no session travels.

Say which of those this is, in the finding, from what was observed rather than
from what is usually true.

## 7. The ceiling

This Playbook is `read_only`, holds one session, and sends four requests to one
route.

It does not send the write. The v1 pack under this name spent half its length on
forging state-changing requests, and the proof it asked for is a state change on
somebody's account performed from an origin that had no business performing it. A
`read_only` Playbook does not do that. Where the subject is a write, the class is
`session_handling.csrf`, 018 named it, and it is graded by the target that grades
`realtime` -- this Playbook does not output it and does not test it by half.

It does not build the page. It does not host markup, does not open a browser
against an origin it controls, and does not ask a victim's browser to do anything.
The claim rests on the headers the application returned, which is what a browser
would have acted on, and a reading that instead demonstrates the browser acting
has run somebody else's browser.

It does not enumerate origins. Two arms, chosen for what they distinguish, and no
list. Sending a hundred origins to find one that reflects is a scan against a
route, and the answer it produces is the same answer the second arm produces.

It does not touch the session it is not holding. It sends no request under a
second Identity, does not log the leased session out, and does not clear a cookie.

Where the route answers every origin identically, the verdict is `refuted` and the
reading is over. Where the document turns out to be public, the verdict is
`inconclusive` and it says so in those words.
