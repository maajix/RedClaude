---
type: Playbook
title: "deserialization"
description: "Ask whether a serialised parameter lets the caller choose which type the route reconstructs, by sending one request as two arms whose blobs differ only in the type name they carry and differencing the two stored responses against a baseline that was itself invariant."
resource: ../../../src/redkraken/playbooks/deserialization/playbook.md
tags: [injection, constrained, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-04-15T00:00:00Z
bb:category: injection
bb:outputs: [injection.object_graph]
bb:triggers_all: [authenticated_endpoint, serialized_object_parameter, state_changing_method]
bb:skills: [compare-responses, use-identity]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:version: 3c95d087ad634748d88b3780b09fd07b5d92cb3f3c73aadf1b3a0dcdc0c37a4a
bb:sha256: d0d4f3b17b6a3a31d9a5c6f156ac566eb5596b5b5ef6113b34d66b92934afce2
sources:
  - id: deserialization--deserialization-attacks
    resource: /references/deserialization--deserialization-attacks.md
    title: "Deserialization attacks: the gadget chain, and why the reading stops before it"
    author: human:maintainer
---

# Ask whether a serialised parameter lets the caller choose which type the route reconstructs, by sending one request as two arms whose blobs differ only in the type name they carry and differencing the two stored responses against a baseline that was itself invariant.

## What it concludes about

- `injection.object_graph`

## When it is selected

A subject carrying every one of these facts:

- `authenticated_endpoint`
- `serialized_object_parameter`
- `state_changing_method`

Risk `constrained`, effects `read_only`, baseline `stable_session`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `response_invariant` observation(s) from a `variant`
- to `supported`: at least 1 supports `response_invariant` observation(s) from a `control`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `variant`

## Provenance

Written for ticket 54 as the v2 replacement for v1's deserialization pack against a new object_graph leaf added by ticket 54; the pack's gadget page is attached as a maintainer reference and every chain, every payload generator and every proof-by-execution in it is refused by step 6.

## Maintainer references

- [deserialization-attacks.md](/references/deserialization--deserialization-attacks.md)[^deserialization--deserialization-attacks]

[^deserialization--deserialization-attacks]: Deserialization attacks: the gadget chain, and why the reading stops before it

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/deserialization/playbook.md`](../../../src/redkraken/playbooks/deserialization/playbook.md). This concept describes that document and never replaces it.
