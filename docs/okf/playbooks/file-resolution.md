---
type: Playbook
title: "file-resolution"
description: "Ask where a path-valued parameter's read landed rather than what its string contained, by naming two different documents outside the directory a route serves, climbing to find where it roots the path, asking whether its guard strips once or to a fixed point, and asking whether the resolved name reaches a stream API at all."
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
bb:version: a0111faf2cdae546d1c124a9b8547aeb30fa990d774996354af8ae0869ff4396
bb:sha256: 66dbf368e80a82be8178c5324f217dacae4a092887334d21d4d57e921e35a9b2
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

# Ask where a path-valued parameter's read landed rather than what its string contained, by naming two different documents outside the directory a route serves, climbing to find where it roots the path, asking whether its guard strips once or to a fixed point, and asking whether the resolved name reaches a stream API at all.

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

- to `refuted`: at least 1 refutes `response_differential` observation(s) from a `variant`
- to `supported`: at least 1 supports `response_invariant` observation(s) from a `control`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `variant`

## Provenance

Written for ticket 54 as the v2 replacement for v1's file-resolution pack against the path leaf of the ticket 18 vocabulary; the pack's three pages are attached as maintainer references and their chains and their read-until-you-find-a-key advice are refused by the last section. Rewritten for ticket 101 against the merged ledger, which carries five readings and three refusals for this slug; three of the five are new. One key moved. The refuted variant row named response_invariant while the supported row of the same role names response_differential, and one role writes one kind whichever way a reading goes, so the refuted row now names response_differential too. The stored-path reading keeps bb:effects read_only by parking before its write rather than performing it.

## Maintainer references

- [lfi.md](/references/file-resolution--lfi.md)[^file-resolution--lfi]
- [path-traversal-encoding-variants.md](/references/file-resolution--path-traversal-encoding-variants.md)[^file-resolution--path-traversal-encoding-variants]
- [php-filter-chain-lfi-rce.md](/references/file-resolution--php-filter-chain-lfi-rce.md)[^file-resolution--php-filter-chain-lfi-rce]

[^file-resolution--lfi]: Local file inclusion: the read that becomes an execution, and the line before it
[^file-resolution--path-traversal-encoding-variants]: Encoding variants: the bypass table, and the one line of it the reading uses
[^file-resolution--php-filter-chain-lfi-rce]: PHP filter chains: turning a read into an execution, and why that is the end

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/file-resolution/playbook.md`](../../../src/redkraken/playbooks/file-resolution/playbook.md). This concept describes that document and never replaces it.
