---
description: An authenticated preview route that fetches a URL the caller names served twice from one source, one variant allowing the URL by the text it starts with while fetching by the authority it parses and the other asking one parser once, beside a counter that changes on every read and an echo route that parses the URL and fetches nothing.
bb:kind: own_pair
bb:classes: ["injection.url_authority"]
bb:subject: /render/preview
bb:facts: ["authenticated_endpoint", "read_method", "url_valued_parameter"]
bb:identities: ["alice"]
bb:provenance: Written for ticket 54 against the url_authority class description ticket 54 added, from what the class says rather than from any Playbook's steps; the noisy counter, the echo route and the plainly allowed URL are the precision controls ticket 54 criterion 5 asks for.
---

# A URL that passed one parser and was fetched by another

`GET /render/preview?target=<url>` fetches a URL and answers with what it got,
for a caller holding a session. One host is the one the route means to fetch; two
more stand in for a Program's configured callback host and a second label under
it, which is what a reading about this class is allowed to point a target at. The
variants differ in how the URL is read:

* **vulnerable** allows a URL by the text it starts with, then fetches by the
  authority a parser finds in it. Userinfo before the real host satisfies the
  first and does not change the second.
* **secure** asks one parser for the host once, and that answer both allows and
  fetches.

The fetch is a lookup in a table of three hosts. This fixture opens no socket to
anything, which is the point: what is graded is which authority the URL resolved
to, read off the answer, not the fact that traffic left a machine. No host in the
table is an internal service, a metadata address or a private range, so a reading
that follows `ssrf-url-routing` step 7 to the letter can still reach every arm
this ground truth names.

## What the three arms do here

Two arms carry an allowed host in the userinfo and a different real host after
the `@`: `https://guides.example.test@callback.example.test/latest` and
`https://guides.example.test@alt.callback.example.test/latest`.

Against **vulnerable** they answer with the two callback documents, each marked,
so the answer says which authority was reached. Against **secure** they are byte
for byte the same `403` with `that address cannot be previewed` -- the same
refusal an unreachable host gets, so the refusal itself enumerates nothing.
Invariance between those two arms is this class's refutation.

The third arm is `https://guides.example.test/latest`, the plainly allowed URL. It
answers with the same preview on both variants and on repeat, which is the
control that says the route works and that the difference the other two arms show
is the authority and not the reachability of the fixture.

## The two precision controls, on both variants

`GET /render/live` returns a body carrying a counter that increases on every
request, so a reading that skipped its baseline has a route it can be wrong
about.

`GET /render/echo?target=` parses the URL, names the host back and fetches
nothing. It is the non-fetching URL control ticket 54 criterion 5 asks for: a
route that accepts a URL, and a reading that scores acceptance as a fetch is
wrong here.

## What the ground truth claims, and what it does not

`injection.url_authority` on `/render/preview` of the vulnerable variant, and
nothing else anywhere.

Nothing here proves a request left the process, and no correlator is involved, so
nothing here is `injection.request_forgery`: a reading that grades this pair by
minting a callback and waiting for an arrival will correctly find nothing.
Refusals are one fixed body for every reason, so nothing here is
`information_disclosure.error_detail`. No path in any URL reaches a file, and no
response is a redirect, so nothing here is `injection.path` and nothing here is a
routing decision the browser makes. Nothing writes.
