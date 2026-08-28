---
type: Playbook
title: "external-resources"
description: "Ask which origins a served document grants authority to run inside it, by reading the stored document and the stored variant a URL-valued parameter produced, listing every reference that carries executable authority, and naming the ones the Program's scope does not claim."
resource: ../../../src/redkraken/playbooks/external-resources/playbook.md
tags: [injection, constrained, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-03-15T00:00:00Z
bb:category: injection
bb:outputs: [injection.foreign_resource]
bb:triggers_all: [read_method, url_valued_parameter, web_surface]
bb:skills: [analyse-source, handle-untrusted-content]
bb:risk: constrained
bb:effects: read_only
bb:baseline: none
bb:version: 6d46a352a277f44187442211a4e592af228166e629e33fa9e6ab93d431d32060
bb:sha256: 373c869e15e4c4366f370d10b5e052a640230aebafe69fe0f65064137d909091
sources:
  - id: external-resources--broken-link-hijacking
    resource: /references/external-resources--broken-link-hijacking.md
    title: "Broken link hijacking: find the name, do not take it"
    author: human:maintainer
---

# Ask which origins a served document grants authority to run inside it, by reading the stored document and the stored variant a URL-valued parameter produced, listing every reference that carries executable authority, and naming the ones the Program's scope does not claim.

## What it concludes about

- `injection.foreign_resource`

## When it is selected

A subject carrying every one of these facts:

- `read_method`
- `url_valued_parameter`
- `web_surface`

Risk `constrained`, effects `read_only`, baseline `none`.

## Skills it loads

- [analyse-source](/skills/analyse-source.md)
- [handle-untrusted-content](/skills/handle-untrusted-content.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `content_match` observation(s) from a `variant`
- to `supported`: at least 1 supports `content_match` observation(s) from a `control`
- to `supported`: at least 1 supports `content_match` observation(s) from a `variant`

## Provenance

Written for ticket 52 as the v2 replacement for v1's broken-link-hijacking page, against a new foreign-resource leaf added by ticket 52; the v1 text is attached as a maintainer reference and step 5's refusal is where this Playbook and that page part company.

## Maintainer references

- [broken-link-hijacking.md](/references/external-resources--broken-link-hijacking.md)[^external-resources--broken-link-hijacking]

[^external-resources--broken-link-hijacking]: Broken link hijacking: find the name, do not take it

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/external-resources/playbook.md`](../../../src/redkraken/playbooks/external-resources/playbook.md). This concept describes that document and never replaces it.
