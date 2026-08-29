---
type: Playbook
title: "payment-workflows"
description: "Ask which number the server believes, by stating the invariant the target itself publishes, reading the pristine total, sending one order with exactly one number edited, and differencing the total the target computes against the same order made legitimately."
resource: ../../../src/redkraken/playbooks/payment-workflows/playbook.md
tags: [business_logic, constrained, mutates_object]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-03-15T00:00:00Z
bb:category: business_logic
bb:outputs: [business_logic.quantity_or_price]
bb:triggers_all: [authenticated_endpoint, quantity_valued_parameter, state_changing_method]
bb:skills: [compare-responses, use-identity]
bb:risk: constrained
bb:effects: mutates_object
bb:baseline: pristine_surface
bb:version: ed98dce721b99c50a7baf9c73e26e5bfd5fe7edeea8b447d88c7b8640308fbda
bb:sha256: 39b7359c2735ff8c2bff4bf81194c7c02086fc231939fca8cae8c8c16f3e0a54
---

# Ask which number the server believes, by stating the invariant the target itself publishes, reading the pristine total, sending one order with exactly one number edited, and differencing the total the target computes against the same order made legitimately.

## What it concludes about

- `business_logic.quantity_or_price`

## When it is selected

A subject carrying every one of these facts:

- `authenticated_endpoint`
- `quantity_valued_parameter`
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

Written for ticket 51 as the v2 replacement for v1's payment-workflows pack, against the quantity-or-price leaf of the ticket 18 vocabulary; v1 shipped a README for this topic and no reference text, so nothing is attached. Rewritten for ticket 101 against the merged ledger, which carries four readings, one lead and two refusals for this slug. No frontmatter key moved, because all three evidence rows already name response_differential and the refuted row is reachable as written.

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/payment-workflows/playbook.md`](../../../src/redkraken/playbooks/payment-workflows/playbook.md). This concept describes that document and never replaces it.
