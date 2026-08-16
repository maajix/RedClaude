---
description: A static bundle served beside the source map it was built from, served twice from one source, one variant shipping the map and the credential inside it and the other answering 404 for it.
bb:kind: own_pair
bb:classes: ["information_disclosure.artifact_exposure"]
bb:subject: /static/app.js.map
bb:facts: ["read_method", "unauthenticated_endpoint"]
bb:identities: []
bb:provenance: Written for ticket 49 against the ticket 18 class description, from what the class says rather than from any Playbook's steps; no upstream corpus.
---

# A build that shipped its own source

`GET /static/app.js` returns the deployed bundle on both variants, and the last
line of that bundle names `app.js.map`. The variants differ in one thing:

* **vulnerable** serves `/static/app.js.map`, and the map carries
  `sourcesContent`: the pre-build module, a cluster-internal hostname and a
  deploy key.
* **secure** answers `404` for the map. Nothing else changes.

## Why the bundle is on both variants

A `404` for a map is not evidence of anything on its own -- most paths are 404.
It is evidence that a build was stripped only if the artifact the map belongs to
is there, reachable, and pointing at it. Both variants therefore serve the same
bundle with the same `sourceMappingURL` comment, so a run that reports the
secure variant as stripped has to have established that there was something to
strip, and a run that reports the vulnerable variant as exposed can say which
build the map belongs to.

That is the control, and it is a property of the fixture rather than an
instruction to whoever tests it.

## What the ground truth claims

`information_disclosure.artifact_exposure` on the vulnerable variant, and
nothing else.

The credential inside `sourcesContent` is what makes the class true rather than
a matter of taste: a map that carried only minified names would be a build
choice, and this one carries a value that still works and a hostname that names
a network the caller was never on.

The route is anonymous by design, so `authorization.function_access` and
`authorization.object_ownership` are not merely absent -- there is no caller
here to check anything against. The bundle is static bytes, no parameter reaches
anything, and both variants' failure body is one fixed sentence, so
`information_disclosure.error_detail`, `injection.path` and
`information_disclosure.identifier_oracle` against this fixture are false
positives rather than gaps in this file.

## Why one artifact and not a directory of them

A fixture that also shipped a `.env`, a `.git` directory and a backup would be
four fixtures wearing one name, and a Playbook that found any of them would
score against all four. One artifact, one comparison, one claim.
