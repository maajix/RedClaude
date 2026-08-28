---
type: Playbook
title: "supply-chain"
description: "Ask whether the build published the application's dependency boundary alongside its bundles, by reading the shell for the bundles it actually loads, following each bundle's own source-map pointer, and sorting the manifest's names into the ones the public already has and the ones that only exist inside the organisation."
resource: ../../../src/redkraken/playbooks/supply-chain/playbook.md
tags: [information_disclosure, constrained, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-05-15T00:00:00Z
bb:category: information_disclosure
bb:outputs: [information_disclosure.dependency_manifest]
bb:triggers_all: [read_method, spa_surface, tech_build_manifest]
bb:skills: [analyse-source, handle-untrusted-content]
bb:risk: constrained
bb:effects: read_only
bb:baseline: none
bb:version: cc3283a12577532fe19ea6c1716d66839579f6c768ed40ab96e3efc303670255
bb:sha256: 4e9ba193cb37e69f9bd5cc7b0768cc6f10542fc60e4f632654d071ee5d72eeca
---

# Ask whether the build published the application's dependency boundary alongside its bundles, by reading the shell for the bundles it actually loads, following each bundle's own source-map pointer, and sorting the manifest's names into the ones the public already has and the ones that only exist inside the organisation.

## What it concludes about

- `information_disclosure.dependency_manifest`

## When it is selected

A subject carrying every one of these facts:

- `read_method`
- `spa_surface`
- `tech_build_manifest`

Risk `constrained`, effects `read_only`, baseline `none`.

## Skills it loads

- [analyse-source](/skills/analyse-source.md)
- [handle-untrusted-content](/skills/handle-untrusted-content.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `content_match` observation(s) from a `variant`
- to `supported`: at least 1 supports `content_match` observation(s) from a `control`
- to `supported`: at least 1 supports `content_match` observation(s) from a `variant`

## Provenance

Written for ticket 55 as the v2 replacement for v1's supply-chain page against a new dependency_manifest leaf added by ticket 55; the v1 page carried no attachments, and its dependency-confusion publishing, its registry probing and its version-to-CVE tables are refused by step 6.

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/supply-chain/playbook.md`](../../../src/redkraken/playbooks/supply-chain/playbook.md). This concept describes that document and never replaces it.
