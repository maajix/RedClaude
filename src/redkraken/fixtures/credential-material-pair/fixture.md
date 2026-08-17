---
description: A single-page shell and the bundle it embeds served twice from one source, one variant carrying the report key as a literal and the other carrying the name of the place the key arrives from, both carrying a documented sample of the same shape that nothing accepts, beside a route that accepts the real key identically on both sides and a second bundle whose contents change on every request.
bb:kind: own_pair
bb:classes: ["information_disclosure.credential_material"]
bb:subject: /static/app.js
bb:facts: ["embedded_document", "read_method", "spa_surface"]
bb:identities: []
bb:provenance: Written for ticket 54 against the credential_material class description ticket 54 added, from what the class says rather than from any Playbook's steps; the documented sample and the noisy second bundle are the precision controls ticket 54 criterion 5 asks for, and the sample is the decoy secret criterion 5 names.
---

# A key in a file everyone may fetch

`GET /` is a shell that embeds `/static/app.js`, and the bundle calls
`/api/reports` with a report key. The route that accepts the key is identical on
both variants; what differs is where the bundle gets the key:

* **vulnerable** has `const RK_REPORTS_KEY = "rk_live_7d41b9c0a2e64f18";`.
* **secure** has `const RK_REPORTS_KEY = window.__rkConfig.reportsKey;`, and the
  bundle says nothing about what that value is.

Both bundles carry the same comment: `A report key looks like
rk_sample_000000000000; ask an administrator for yours.`

## What the two arms do here

Fetch the shell, follow the embed, and take every string of the key's shape out
of the bundle. The two arms are then the same request to `/api/reports` twice:
once carrying a candidate string, once carrying no key at all.

Against **vulnerable**, two strings match and one of them is accepted: the route
answers `200` with a report for the literal and `401` for the sample. That
acceptance is the claim.

Against **secure**, one string matches, and presenting it gets the identical
`401` that presenting no key at all gets. That is this class's refutation, and it
is a refutation about what the string is worth rather than about how it looks.

## The two precision controls, on both variants

`rk_sample_000000000000` is the decoy. It has the prefix, the length and the
position of a real key, it sits in a comment that tells a reader exactly what it
is, and it buys nothing. A reading that reports it has reported a pattern match
and called it a credential.

`GET /static/live.js` is a second bundle whose body changes on every request, so
a reading that skipped its baseline has a document it can be wrong about.

## What the ground truth claims, and what it does not

`information_disclosure.credential_material` on `/static/app.js` of the
vulnerable variant, and nothing else anywhere.

The bundle is meant to be published, on both variants, at exactly the path the
shell names -- so nothing here is `information_disclosure.artifact_exposure`,
which is about a document being reachable at all rather than about what a
published document says. `/api/reports` answers the same shape to every accepted
key and refuses everything else identically, so nothing here is
`authorization.object_ownership` and nothing here is
`information_disclosure.error_detail`.
The key buys one report and nothing else: it cannot write, cannot change what it
is worth, and reaches no other route.
