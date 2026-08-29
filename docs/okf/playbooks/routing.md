---
type: Playbook
title: "routing"
description: "Ask whether a step enforces the steps before it, by completing the flow once in order and then reaching the same step from a session that never took them -- spelled a different way, or entered from a second flow whose steps the step's own guard may be reading."
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
bb:version: 46a4d7e055e554f8cc4bb43734dbf4a439842c328245c14be9234cfdef254ca7
bb:sha256: 69a07b3fe2f7026ec39ea62edb8e0567bc24f39b37cb139f5a18831354e65d3e
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

# Ask whether a step enforces the steps before it, by completing the flow once in order and then reaching the same step from a session that never took them -- spelled a different way, or entered from a second flow whose steps the step's own guard may be reading.

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

- to `refuted`: at least 1 refutes `response_differential` observation(s) from a `variant`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `control`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `variant`

## Provenance

Written for ticket 51 as the v2 replacement for v1's routing pack, against the workflow-order leaf of the ticket 18 vocabulary; two v1 texts are attached as maintainer references and both describe the spellings section 3 sends. Rewritten for ticket 101 against the merged ledger's six readings for this slug. Three close a Test, one is a selector that closes nothing, and two are named in the closing section, one as another Playbook's reading and one as blocked by the method enum; the dot-segment spelling is split off from the spellings Test as a lead of its own, because the specification checker refuses that path. The declared bar is response_differential in all three entries rather than state_change, because the outcome read that sees the effect is itself an action of the same Test and an evidence edge cannot be added once the claim is past proposed, so the kind the settling assertions derive is the only kind the bar can name.

## Maintainer references

- [http-attacks-verb-tampering.md](/references/routing--http-attacks-verb-tampering.md)[^routing--http-attacks-verb-tampering]
- [status-code-bypass.md](/references/routing--status-code-bypass.md)[^routing--status-code-bypass]

[^routing--http-attacks-verb-tampering]: Verb tampering: the same route, spelled with a different method
[^routing--status-code-bypass]: Status-code bypasses: which of them belong to this corpus, and which do not

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/routing/playbook.md`](../../../src/redkraken/playbooks/routing/playbook.md). This concept describes that document and never replaces it.
