---
type: Playbook
title: "payment-workflows"
description: "Ask whether a payment conserves the amount and state the target publishes, by changing one price, discount, credit, currency, idempotency key or transition at a time and comparing the target's authoritative order, provider and ledger views with a legitimate control."
resource: ../../../src/redkraken/playbooks/payment-workflows/playbook.md
tags: [business_logic, approval_required, mutates_object]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-09-01T00:00:00Z
bb:category: business_logic
bb:outputs: [business_logic.quantity_or_price, business_logic.replay, business_logic.workflow_order]
bb:triggers_all: [authenticated_endpoint, quantity_valued_parameter, state_changing_method]
bb:skills: [compare-responses, use-identity]
bb:risk: approval_required
bb:effects: mutates_object
bb:baseline: pristine_surface
bb:version: 7dacc053a4995e4c4cb9109da8edab59270995f351b1805e0c5d82492d8a7204
bb:sha256: f7a7ec6e71b3f8bb26f74cd51325d75c951ff0076c22c6ca1696b208e0f9046e
sources:
  - id: payment-workflows--payment-process-contracts
    resource: /references/payment-workflows--payment-process-contracts.md
    title: "Payment process contracts"
    author: human:maintainer
---

# Ask whether a payment conserves the amount and state the target publishes, by changing one price, discount, credit, currency, idempotency key or transition at a time and comparing the target's authoritative order, provider and ledger views with a legitimate control.

## What it concludes about

- `business_logic.quantity_or_price`
- `business_logic.replay`
- `business_logic.workflow_order`

## When it is selected

A subject carrying every one of these facts:

- `authenticated_endpoint`
- `quantity_valued_parameter`
- `state_changing_method`

Risk `approval_required`, effects `mutates_object`, baseline `pristine_surface`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `response_differential` observation(s) from a `variant`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `control`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `variant`

## Provenance

Written for ticket 51 as the v2 replacement for v1's payment-workflows pack and rewritten for ticket 101 against the mined ledger. Ticket 231 turns the amount-only reading into a quality and integrity method for amount authority, discounts, credits, refunds, currency arithmetic, idempotency and reconciliation; workflow_order and replay are declared because those procedures settle those existing business-logic classes rather than relabelling every payment defect as quantity_or_price.

## Maintainer references

- [payment-process-contracts.md](/references/payment-workflows--payment-process-contracts.md)[^payment-workflows--payment-process-contracts]

[^payment-workflows--payment-process-contracts]: Payment process contracts

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/payment-workflows/playbook.md`](../../../src/redkraken/playbooks/payment-workflows/playbook.md). This concept describes that document and never replaces it.
