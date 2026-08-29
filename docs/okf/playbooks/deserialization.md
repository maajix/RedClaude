---
type: Playbook
title: "deserialization"
description: "Ask whether a serialised parameter lets the caller choose which type the route reconstructs, by classifying the blob offline, by telling a parse-level failure apart from a validation failure, and by sending two arms whose blobs differ only in the type name they carry against a baseline that was itself invariant."
resource: ../../../src/redkraken/playbooks/deserialization/playbook.md
tags: [injection, constrained, mutates_object]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-04-15T00:00:00Z
bb:category: injection
bb:outputs: [injection.object_graph]
bb:triggers_all: [authenticated_endpoint, serialized_object_parameter, state_changing_method]
bb:skills: [compare-responses, use-identity]
bb:risk: constrained
bb:effects: mutates_object
bb:baseline: stable_session
bb:version: 040d82671c6f502196da20bb014f9dba1637873bee3a7d839334f6262901fc08
bb:sha256: e5e4df90a64f3d1fbde3e249ecce99a3df11ff9a5d338697d28183d16415f53c
sources:
  - id: deserialization--deserialization-attacks
    resource: /references/deserialization--deserialization-attacks.md
    title: "Deserialization attacks: the gadget chain, and why the reading stops before it"
    author: human:maintainer
---

# Ask whether a serialised parameter lets the caller choose which type the route reconstructs, by classifying the blob offline, by telling a parse-level failure apart from a validation failure, and by sending two arms whose blobs differ only in the type name they carry against a baseline that was itself invariant.

## What it concludes about

- `injection.object_graph`

## When it is selected

A subject carrying every one of these facts:

- `authenticated_endpoint`
- `serialized_object_parameter`
- `state_changing_method`

Risk `constrained`, effects `mutates_object`, baseline `stable_session`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `response_differential` observation(s) from a `variant`
- to `supported`: at least 1 supports `response_invariant` observation(s) from a `control`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `variant`

## Provenance

Written for ticket 54 as the v2 replacement for v1's deserialization pack against a new object_graph leaf added by ticket 54; the pack's gadget page is attached as a maintainer reference and every chain, every payload generator and every proof-by-execution in it stays refused. Rewritten for ticket 101 against the merged ledger, which carries three readings that reach a Finding, three that stop at an Observation, and two refusals. Two keys moved. bb:effects leaves read_only for mutates_object because section 5 writes a property every route the same worker serves reads afterwards and no client action takes it back; bb:risk stays constrained, which is the floor mutates_object allows. The old reason, that a read_only selection could not carry a body, was never true of this tree. The refuted variant row leaves response_invariant for response_differential, the kind the supported row of that same role names, because one role writes one kind whichever way the reading goes.

## Maintainer references

- [deserialization-attacks.md](/references/deserialization--deserialization-attacks.md)[^deserialization--deserialization-attacks]

[^deserialization--deserialization-attacks]: Deserialization attacks: the gadget chain, and why the reading stops before it

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/deserialization/playbook.md`](../../../src/redkraken/playbooks/deserialization/playbook.md). This concept describes that document and never replaces it.
