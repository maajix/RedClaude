---
type: Playbook
title: "client-side-path-traversal"
description: "Ask whether a page builds the path of a request it makes out of a segment the caller supplied, by reading the served bundle for a route the code composes, loading the page with an encoded traversing segment, and differencing the request lines the browser's own Receipts recorded; every reading here stops at an Observation, because the differential lives in a mission or a tool run and the only kind of Test action is a request."
resource: ../../../src/redkraken/playbooks/client-side-path-traversal/playbook.md
tags: [injection, constrained, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-03-15T00:00:00Z
bb:category: injection
bb:outputs: [injection.client_path]
bb:triggers_all: [path_parameter, read_method, web_surface]
bb:skills: [browser-evidence, compare-responses]
bb:risk: constrained
bb:effects: read_only
bb:baseline: none
bb:version: c5fe9d370ca0bfe6e6dfbbc6625e8a38b37140383166d91f3160ee57f1b16fc0
bb:sha256: 7f2a72208952fcd9445bf59b09bb6e483590158549a1f38ed10ab1efb65b22c8
---

# Ask whether a page builds the path of a request it makes out of a segment the caller supplied, by reading the served bundle for a route the code composes, loading the page with an encoded traversing segment, and differencing the request lines the browser's own Receipts recorded; every reading here stops at an Observation, because the differential lives in a mission or a tool run and the only kind of Test action is a request.

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
- [compare-responses](/skills/compare-responses.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `response_differential` observation(s) from a `variant`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `control`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `variant`

## Provenance

Written for ticket 52 against a new client-path leaf added by ticket 52; v1 covered this topic in prose under its client-side pack and shipped no reference text for it, so nothing is attached rather than a placeholder. Rewritten for ticket 101 against the merged ledger, whose three readings for this slug are all observation_only -- the differential lives in a browse mission or in a tool run and TEST_ACTION_KINDS admits a request alone, so no section closes a Test and none promises a Finding. One key moved. bb:skills gains compare-responses, which the two-request half of the cache-key lead needs and which the executing role already holds; the source-reading Skill the bundle census would otherwise name is not one that role loads, so the census is written as the two granted programs and nothing else. bb:outputs is unchanged, the census producing a precondition rather than a class. The refuted variant row moves from response_invariant to response_differential, the kind the supported row of that same role names.

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/client-side-path-traversal/playbook.md`](../../../src/redkraken/playbooks/client-side-path-traversal/playbook.md). This concept describes that document and never replaces it.
