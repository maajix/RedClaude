---
description: An authenticated article list served twice from one source beside the content platform's own read route, one variant serving that route to a caller holding nothing and the other putting it behind the same session and the same filter, with a platform route that answers but carries no records and a platform route whose body counts requests.
bb:kind: own_pair
bb:classes: ["authorization.parallel_route"]
bb:subject: /api/articles
bb:facts: ["authenticated_endpoint", "read_method", "tech_cms"]
bb:identities: ["alice"]
bb:provenance: Written for ticket 55 against the parallel_route class description ticket 55 added, from what the class says rather than from any Playbook's steps; the empty platform route and the counting platform route are the precision controls, and the drafted record is what makes the leak more than a duplicate of a public page.
---

# One store, two doors

`GET /api/articles` is the application's own list. It needs the session cookie
this fixture issues to `alice`, and it answers with the articles whose status is
`published` -- one record, `quarterly-outlook`. The second record,
`pricing-change-2027`, is a draft, and the application's route never shows it to
anybody.

Behind the same origin sits the content platform's own read route,
`/cms/rest/content`, over the same two records. The two variants differ in what
that route requires:

* **vulnerable** answers it to a caller holding nothing, with both records --
  the published one and the draft.
* **secure** requires the same session cookie and applies the same
  `status = published` filter, so a caller holding nothing gets `401` and a
  caller holding the session gets exactly what the application's route gave.

Nothing about the application's own route differs between the variants. That is
the shape of this class: the check is not missing, it is bypassed, because the
platform shipped a second way to the store and only one of the two doors was
part of the conversation about who may read what.

## What the two arms do here

Against **vulnerable**, `/api/articles` without the cookie is `401` on both
variants, and `/cms/rest/content` without the cookie is `200` carrying
`quarterly-outlook` -- the identifier the session read -- beside
`pricing-change-2027`, which no authenticated read ever returned.

Against **secure**, the same request is `401`, and the two refusals are byte-for-
byte the same document. That invariance is this class's refutation.

## The two precision controls, on both variants

`GET /cms/rest/health` answers `200` to a caller holding nothing, with
`{"platform": "cms", "items": []}`. It is a platform route that exists, is
reachable and carries no records, and it is the decoy for a reading that treats
a platform route answering at all as the finding.

`GET /cms/rest/status` answers `200` to a caller holding nothing with a counter
that increases on every request, so a reading that skipped its baseline has a
route it can be wrong about.

## What the ground truth claims, and what it does not

`authorization.parallel_route` on `/api/articles` of the vulnerable variant, and
nothing else anywhere.

No route here takes a record identifier from the caller, so nothing in this
fixture is `authorization.object_ownership`: both list routes are asked for by
themselves and decide their own contents. Only one Identity exists, so no
response anywhere carries a second caller's data. Nothing is served that was not
meant to be published as a document -- the draft is a record in a list, not a
file left in the tree -- so this is not
`information_disclosure.artifact_exposure`. No version, banner or generator
string appears in any response on either variant, which is deliberate: a fixture
that leaked a platform version would reward a reading that reported a
fingerprint. Nothing here writes, and nothing here is served to a second caller.
