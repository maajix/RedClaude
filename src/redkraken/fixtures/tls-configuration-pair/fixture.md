---
description: An application shell behind a terminating front end, advertising the same strict transport posture on both variants and serving the same bytes on every route, where one front end still terminates at TLS 1.2 and the other terminates at TLS 1.3 and refuses everything under it, beside a bundle, a public status document and a route whose body counts requests.
bb:kind: own_pair
bb:classes: ["transport.tls_configuration"]
bb:subject: /app
bb:facts: ["read_method", "spa_surface", "tech_edge_proxy"]
bb:identities: []
bb:provenance: Written for ticket 88 against the tls_configuration class description 018 added and the allowed_fields 025 named, from what the class says rather than from any Playbook's steps; the identical bodies, the identical advertisement and the identical ALPN are the precision controls, and the difference is the protocol floor alone.
---

# What the deployment claims, and what the handshake actually agreed to

`GET /app` serves a single-page application shell from behind a front end that
terminates TLS. Every response on both variants carries
`Strict-Transport-Security: max-age=63072000; includeSubDomains; preload` --
two years, every subdomain, preload requested. That is a deployment stating it
has no weak transport anywhere it is responsible for.

The two variants differ in whether that is true:

* **vulnerable** terminates at TLS 1.2 and negotiates
  `ECDHE-ECDSA-AES128-GCM-SHA256`. Nothing about that suite is broken. What is
  wrong is the floor: a deployment advertising `preload` is claiming a posture
  a 1.2 terminator does not have, and a caller who believed the header would
  believe something about this connection that is not so.
* **secure** terminates at TLS 1.3, refuses everything under it, and negotiates
  whatever 1.3 agrees on. The header and the handshake say the same thing.

Nothing else differs. Both halves serve the same shell, the same bundle, the
same status document and the same counter, byte for byte, under the same
`Server` header, and both offer `http/1.1` and only `http/1.1` over ALPN.

## Why this fixture has a second entry point

Every other fixture in this corpus is one `app.py` defining `handler(variant)`,
because every other class it grades is settled by what came back. This one is
not settled by what came back at all. 025 records
`transport.tls_configuration` as `probe_only` over `tls_version`, `cipher` and
`alpn`, and none of those three is a thing a request handler can write.

So `app.py` also defines `tls(variant, context)`, which configures the socket
the handler is served over. The division is the class's own: the bytes are the
application's, and the handshake is the front end's. The certificate is
neither -- it is the evaluator's, minted per run and naming the origin the
evaluator chose, so `tls` configures a context rather than building one.

## What the arms do here

Against both variants, an ordinary read of `/app` returns the same document with
the same headers, including the same advertisement. That is the point of the
pair, and it is where a reading that compares bodies stops having anything to
say.

Against **vulnerable**, the handshake underneath that identical exchange agreed
on TLS 1.2. Against **secure**, it agreed on TLS 1.3. The reading's claim has to
rest on that and on nothing else, because there is nothing else.

## The three precision controls, on both variants

`GET /static/console.js` returns the same bundle on both halves. It is here so
the subject is a shell with something behind it rather than a single document,
which is what `spa_surface` names.

`GET /api/public/status` answers `{"status": "ok", "build": "2026.9.1"}` on both
halves, for every caller, with no session involved. A reading that reported a
public document as a disclosure gets it wrong here.

`GET /api/metrics/live` answers with a counter that increases on every request,
on both halves. A reading that skipped its baseline has a route it can be wrong
about.

## What the ground truth claims, and what it does not

`transport.tls_configuration` on `/app` of the vulnerable variant, and nothing
else anywhere.

The claim is about the negotiated protocol version and the suite that follows
from it. It is not about the cipher being weak -- it is not -- and a reading
that reported the suite as the defect would be reporting the consequence of the
floor rather than the floor.

Nothing here is `transport.header_policy`. The transport header is present, well
formed and identical on both variants; a fixture whose halves differed in the
header would be positive for that class instead, and it is a different class
with a different reading.

Nothing here is `transport.certificate_trust`. Both variants present the same
certificate from the same issuer with the same validity, because both are handed
one context from one authority. A reading that reported the certificate has
reported something both halves do.

Nothing here is `transport.request_framing`. 025 records that class as
`unmakeable` behind this harness's proxy and nothing in this pair frames a
request differently; both halves speak HTTP/1.1 over ALPN and neither disagrees
with the other about a single byte of any message.

No route here takes an identifier, requires a session, or answers a caller with
anybody's record, so this pair is positive for no authorization or session
class. No value from any request is written into any body or any header. Nothing
here is a credential: the only secret in the pair is the leaf key, which belongs
to the evaluator and never appears in a response.
