---
type: Playbook
title: "file-resolution"
description: "Ask whether a path-valued parameter resolves outside the directory a route serves, by sending two arms that name two different documents outside it and one that normalises back inside, and differencing the stored responses against a baseline that was itself invariant."
resource: ../../../src/redkraken/playbooks/file-resolution/playbook.md
tags: [injection, constrained, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-04-15T00:00:00Z
bb:category: injection
bb:outputs: [injection.path]
bb:triggers_all: [authenticated_endpoint, path_valued_parameter, read_method]
bb:skills: [compare-responses, use-identity]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:version: 7894e144fa1bb026b37312ca22d1d1bb3081c7ddaedd64081b9ccd98af8f29ce
bb:sha256: 2a78322dda9c1bc24824ecd7d20b662bf09fa821458ceede20517d5705f8c51a
sources:
  - id: file-resolution--lfi
    resource: /references/file-resolution--lfi.md
    title: "Local file inclusion: the read that becomes an execution, and the line before it"
    author: human:maintainer
  - id: file-resolution--path-traversal-encoding-variants
    resource: /references/file-resolution--path-traversal-encoding-variants.md
    title: "Encoding variants: the bypass table, and the one line of it the reading uses"
    author: human:maintainer
  - id: file-resolution--php-filter-chain-lfi-rce
    resource: /references/file-resolution--php-filter-chain-lfi-rce.md
    title: "PHP filter chains: turning a read into an execution, and why that is the end"
    author: human:maintainer
---

# Ask whether a path-valued parameter resolves outside the directory a route serves, by sending two arms that name two different documents outside it and one that normalises back inside, and differencing the stored responses against a baseline that was itself invariant.

## What it concludes about

- `injection.path`

## When it is selected

A subject carrying every one of these facts:

- `authenticated_endpoint`
- `path_valued_parameter`
- `read_method`

Risk `constrained`, effects `read_only`, baseline `stable_session`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `response_invariant` observation(s) from a `variant`
- to `supported`: at least 1 supports `response_invariant` observation(s) from a `control`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `variant`

## Provenance

Written for ticket 54 as the v2 replacement for v1's file-resolution pack against the path leaf of the ticket 18 vocabulary; the pack's three pages are attached as maintainer references and their wrapper chains, their filter chains and their read-until-you-find-a-key advice are refused by step 7.

## Maintainer references

- [lfi.md](/references/file-resolution--lfi.md)[^file-resolution--lfi]
- [path-traversal-encoding-variants.md](/references/file-resolution--path-traversal-encoding-variants.md)[^file-resolution--path-traversal-encoding-variants]
- [php-filter-chain-lfi-rce.md](/references/file-resolution--php-filter-chain-lfi-rce.md)[^file-resolution--php-filter-chain-lfi-rce]

[^file-resolution--lfi]: Local file inclusion: the read that becomes an execution, and the line before it
[^file-resolution--path-traversal-encoding-variants]: Encoding variants: the bypass table, and the one line of it the reading uses
[^file-resolution--php-filter-chain-lfi-rce]: PHP filter chains: turning a read into an execution, and why that is the end

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/file-resolution/playbook.md`](../../../src/redkraken/playbooks/file-resolution/playbook.md). This concept describes that document and never replaces it.
