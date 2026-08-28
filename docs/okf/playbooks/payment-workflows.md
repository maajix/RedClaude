---
type: Playbook
title: "payment-workflows"
description: "Ask whether an amount the rules forbid is accepted, by stating the invariant and the pristine total first, sending one order with the quantity or price edited, and reading the total the target itself computes."
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
bb:version: 494358c628fd4077226815d8419a471a1d22e0600361418d287b15f73094dbb3
bb:sha256: ff2341884cfdf4ca0f3358d67fbb739a8c0503a3e6993ea90e130c440e3f9648
---

# Ask whether an amount the rules forbid is accepted, by stating the invariant and the pristine total first, sending one order with the quantity or price edited, and reading the total the target itself computes.

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

Written for ticket 51 as the v2 replacement for v1's payment-workflows pack, against the quantity-or-price leaf of the ticket 18 vocabulary; v1 shipped a README for this topic and no reference text, so nothing is attached.

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/payment-workflows/playbook.md`](../../../src/redkraken/playbooks/payment-workflows/playbook.md). This concept describes that document and never replaces it.
