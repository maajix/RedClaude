---
type: Playbook
title: "routing"
description: "Ask whether a step enforces the steps before it, by completing the flow once in order and then reaching the same step from a session that never took them, including where the step is spelled a different way."
resource: ../../../src/redkraken/playbooks/routing/playbook.md
tags: [business_logic, constrained, mutates_object]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-03-15T00:00:00Z
bb:category: business_logic
bb:outputs: [business_logic.workflow_order]
bb:triggers_all: [flow_step, state_changing_method]
bb:skills: [compare-responses, use-identity]
bb:risk: constrained
bb:effects: mutates_object
bb:baseline: pristine_surface
bb:version: c4de9c1ba1721f073063f267a84f7ff2df1d868d3adf8638c313c34f072f5f8e
bb:sha256: 2368d25030a3f5b4ab4bbe6118269fe8f1f3e62b43b938474398b705048b2d45
sources:
  - id: routing--http-attacks-verb-tampering
    resource: /references/routing--http-attacks-verb-tampering.md
    title: "Verb tampering: the same route, spelled with a different method"
    author: human:maintainer
  - id: routing--status-code-bypass
    resource: /references/routing--status-code-bypass.md
    title: "Status-code bypasses: which of them belong to this corpus, and which do not"
    author: human:maintainer
---

# Ask whether a step enforces the steps before it, by completing the flow once in order and then reaching the same step from a session that never took them, including where the step is spelled a different way.

## What it concludes about

- `business_logic.workflow_order`

## When it is selected

A subject carrying every one of these facts:

- `flow_step`
- `state_changing_method`

Risk `constrained`, effects `mutates_object`, baseline `pristine_surface`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `response_invariant` observation(s) from a `variant`
- to `supported`: at least 1 supports `state_change` observation(s) from a `control`
- to `supported`: at least 1 supports `state_change` observation(s) from a `variant`

## Provenance

Written for ticket 51 as the v2 replacement for v1's routing pack, against the workflow-order leaf of the ticket 18 vocabulary; two v1 texts are attached as maintainer references and both describe the spellings step 4 sends.

## Maintainer references

- [http-attacks-verb-tampering.md](/references/routing--http-attacks-verb-tampering.md)[^routing--http-attacks-verb-tampering]
- [status-code-bypass.md](/references/routing--status-code-bypass.md)[^routing--status-code-bypass]

[^routing--http-attacks-verb-tampering]: Verb tampering: the same route, spelled with a different method
[^routing--status-code-bypass]: Status-code bypasses: which of them belong to this corpus, and which do not

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/routing/playbook.md`](../../../src/redkraken/playbooks/routing/playbook.md). This concept describes that document and never replaces it.
