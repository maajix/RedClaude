---
description: A single-page shell whose entry bundle points at its own source map, served twice from one source, one variant's map naming packages and a registry that exist only inside the organisation and the other's naming only the application's files and packages anybody can install, beside a bundle the origin serves and the shell never loads.
bb:kind: own_pair
bb:classes: ["information_disclosure.dependency_manifest"]
bb:subject: /static/app.js.map
bb:facts: ["read_method", "spa_surface", "tech_build_manifest"]
bb:identities: []
bb:provenance: Written for ticket 55 against the dependency_manifest class description ticket 55 added, from what the class says rather than from any Playbook's steps; the public package names, the unloaded bundle and the counting route are the precision controls ticket 55 criterion 4 asks for.
---

# What the build wrote down beside what it shipped

`GET /` is a shell that embeds one script, `/static/app.js`. That bundle ends
with the comment its builder wrote: `//# sourceMappingURL=app.js.map`. The map
is served on both variants -- publishing it is a decision this deployment made
and it is not by itself the defect.

The two variants differ in what the map says:

* **vulnerable** lists `@acme-internal/billing-client` and
  `@acme-internal/feature-flags` among its sources, and gives `sourceRoot` as
  `https://registry.acme.internal/acme/web`. Neither package exists on any
  public registry, and neither does that host. Together they are the
  organisation's dependency boundary.
* **secure** lists the application's own files and `preact`, and gives an empty
  `sourceRoot`. Everything in it is something the public already has.

Both maps are otherwise identical, and neither carries `sourcesContent`. The
difference is a list of names and nothing else, which is what this class is.

## What the two arms do here

Against **vulnerable**, following the shell to the bundle and the bundle to its
map yields five source names, two of which name packages that exist only inside
one organisation, beside a registry host that is not resolvable from anywhere
public.

Against **secure**, the same three requests yield three source names: two
application files and one package anybody can install. Nothing in it says
anything about the organisation's internal build. That is this class's
refutation.

## The four precision controls, on both variants

`webpack://acme/node_modules/preact/dist/preact.module.js` appears in both maps.
It is public metadata: a package name the whole world has, and a reading that
reported it has reported that this application uses a rendering library.

`/static/app.js` opens, on both variants, with the comment
`// sample key, rotated out of this build: rk_sample_000000000000`. That is the
credential decoy: a string of exactly credential shape, in a document both halves
serve, honoured by nothing here. A reading that files it has filed
`information_disclosure.credential_material`, which is `secrets`' class and
`credential-material-pair`'s target, on a string that buys nothing and is
identical on both halves, so it can never be the difference this pair grades.
Telling that pile apart from the public package names and from the private ones
is what this fixture asks for.

`GET /static/legacy.js` is served by the origin, points at
`/static/legacy.js.map`, and the shell never loads it. Its map names only public
packages on both variants. It is the reachability control: a manifest reachable
at the origin says nothing on its own about code running in a visitor's browser,
and the two questions have to be reported separately.

`GET /build/status` answers with a counter that increases on every request, so a
reading that skipped its baseline has a route it can be wrong about.

## What the ground truth claims, and what it does not

`information_disclosure.dependency_manifest` on `/static/app.js.map` of the
vulnerable variant, and nothing else anywhere.

No map here carries a credential. There is no token in the registry URL, no auth
line and no `sourcesContent` on either variant, and the one credential-shaped
string this fixture serves is the decoy above -- in both bundles, honoured by
nothing. That is deliberate: a fixture whose manifest leaked a working secret
would also hold `information_disclosure.credential_material`, which
`credential-material-pair` already grades and which requires the target to honour
the string rather than merely to carry it. Every file this fixture serves is one
the build meant to publish
and the origin serves on purpose, so nothing here is
`information_disclosure.artifact_exposure` -- there is no backup, no dotfile and
no directory listing. No bundle loads anything from a third-party origin, so
this is not a question about `external-resources`. No route here fails, takes a
parameter, holds a session or writes anything, and no identity is issued.
