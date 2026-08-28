---
type: Playbook
title: "client-side-path-traversal"
description: "Ask whether a page builds the path of a request it makes out of a segment the caller supplied, by loading the page with an encoded traversing segment and reading which route the browser's own Receipts show it asked for."
resource: ../../../src/redkraken/playbooks/client-side-path-traversal/playbook.md
tags: [injection, constrained, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-03-15T00:00:00Z
bb:category: injection
bb:outputs: [injection.client_path]
bb:triggers_all: [path_parameter, read_method, web_surface]
bb:skills: [browser-evidence]
bb:risk: constrained
bb:effects: read_only
bb:baseline: none
bb:version: 8394500c227610d680771b3ca9b9adc65e0ce37fd24ec76fa4f2873833cc3a8c
bb:sha256: 753c058fbdc51091400adafe8729f6bc24d23482b219f96c5a1b1d0148827534
---

# Ask whether a page builds the path of a request it makes out of a segment the caller supplied, by loading the page with an encoded traversing segment and reading which route the browser's own Receipts show it asked for.

## What it concludes about

- `injection.client_path`

## When it is selected

A subject carrying every one of these facts:

- `path_parameter`
- `read_method`
- `web_surface`

Risk `constrained`, effects `read_only`, baseline `none`.

## Skills it loads

- [browser-evidence](/skills/browser-evidence.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `response_invariant` observation(s) from a `variant`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `control`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `variant`

## Provenance

Written for ticket 52 against a new client-path leaf added by ticket 52; v1 covered this topic in prose under its client-side pack and shipped no reference text for it, so nothing is attached rather than a placeholder.

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/client-side-path-traversal/playbook.md`](../../../src/redkraken/playbooks/client-side-path-traversal/playbook.md). This concept describes that document and never replaces it.
