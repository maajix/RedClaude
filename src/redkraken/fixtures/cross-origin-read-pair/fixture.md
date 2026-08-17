---
description: An authenticated account view served twice from one source, one variant writing back whichever origin asked beside the credentials line and the other writing back only the one origin the deployment was configured for, beside a public route shared with a wildcard and no credentials, a write defended by a request token on both variants, and a route whose body counts requests.
bb:kind: own_pair
bb:classes: ["session_handling.cross_origin_read"]
bb:subject: /api/account
bb:facts: ["authenticated_endpoint", "header_parameter", "read_method"]
bb:identities: ["alice"]
bb:provenance: Written for ticket 56 against the cross_origin_read class description ticket 56 added, from what the class says rather than from any Playbook's steps; the wildcard public route, the configured partner origin honoured on both halves, the token-defended write and the counting route are the precision controls.
---

# Who may read the answer, decided per request

`GET /api/account` answers with the caller's own record: their address, their
plan, the identifier their invoices carry. It requires a session, and this
deployment shares it with one partner site by name, which is a decision somebody
made rather than a defect.

The two variants differ in what they do with every *other* origin:

* **vulnerable** writes the asking origin back into
  `Access-Control-Allow-Origin`, whatever it was, beside
  `Access-Control-Allow-Credentials: true`. Any page anywhere can read the
  record of whoever visits it while signed in.
* **secure** writes that header only when the origin is
  `https://partner.acme.com`, the one this deployment was configured for, and
  says nothing at all to any other. The browser keeps the answer to itself.

The record is byte-stable across repeated requests on both variants, and the
counting route below is deliberately somewhere else: a subject that moved
between two sends would make every comparison a reading performs ambiguous.

## What the arms do here

The reading holds `alice`'s session throughout. A first read carrying no
`Origin` at all establishes what the route answers and returns the same document
on both variants with no sharing headers on either -- that is not a cross-origin
request, so there is nothing for either variant to say about it.

Against **vulnerable**, the same read carrying
`Origin: https://unrelated.example` comes back with
`Access-Control-Allow-Origin: https://unrelated.example` and
`Access-Control-Allow-Credentials: true`. So does the near miss,
`Origin: https://partner.acme.com.evil.example`, which is the spelling a
deployment that anchored its check badly would also return and this one returns
because it does not check at all.

Against **secure**, both of those come back with no
`Access-Control-Allow-Origin` at all. The document is identical; what changed is
that nothing in the answer permits another origin to read it. That is this
class's refutation, and it is why the reading's claim has to rest on the headers
rather than on the body.

## The four precision controls, on both variants

`GET /api/public/status` answers `{"status": "ok", "build": "2026.8.3"}` under
`Access-Control-Allow-Origin: *` with no credentials line, on both variants. It
is the same string for every caller and no session is involved, so the wildcard
is correct there. A reading that reports a permissive sharing header as though
the header were the finding gets it wrong here.

`Origin: https://partner.acme.com` is honoured on both variants -- header for
header, including the credentials line. It is the configured partner, and a
reading that reports the arrangement somebody chose has reported something the
secure variant does too.

`POST /api/account/email` requires the session *and* an `X-CSRF-Token` header
carrying the value the `csrf` cookie carries, on both variants, and answers
`403` without it identically on both. `session_handling.csrf` is a different
class with a different fixture, and this pair holds no forgeable write for it to
be positive for.

`GET /api/metrics/live` answers with a counter that increases on every request,
on both variants. A reading that skipped its baseline has a route it can be
wrong about.

## What the ground truth claims, and what it does not

`session_handling.cross_origin_read` on `/api/account` of the vulnerable
variant, and nothing else anywhere.

The two variants serve identical bodies. The whole difference is two response
headers on one route, which is deliberate: a reading that establishes this class
from what a body said has established it from the wrong evidence.

Nothing here is `session_handling.csrf`: the one write on either variant is
defended by a token no other origin can read, and it is defended that way on
both halves. Both variants require the session on `/api/account` and both refuse
without it, so no route answers a caller who presented nothing and this is not
`authorization.function_access`. One user exists, every route answers with that
user's own record, and no route takes an identifier that selects somebody
else's, so this is not `authorization.object_ownership`. No
value from any request is written into any body, and the only request value that
reaches a response header is the origin itself, into the header that exists to
carry it. Nothing here is a credential: the session and request tokens are the
reading's own, issued to it, and no key, secret or bearer string belonging to
the application appears on either variant.
