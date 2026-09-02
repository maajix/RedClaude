---
type: Playbook
title: "payment-webhooks"
description: "Ask whether an incoming payment event is authenticated and applied once, by replaying one Program-supplied test or sandbox delivery beside an unsigned, body-modified, stale and duplicate arm and reading the target's authoritative payment state after each."
resource: ../../../src/redkraken/playbooks/payment-webhooks/playbook.md
tags: [authentication, approval_required, mutates_object]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-09-01T00:00:00Z
bb:category: authentication
bb:outputs: [authentication.credential_verification]
bb:triggers_all: [json_request, state_changing_method, unauthenticated_endpoint]
bb:skills: [compare-responses, handle-untrusted-content]
bb:risk: approval_required
bb:effects: mutates_object
bb:baseline: pristine_surface
bb:version: 8bf660ca60a8d7b7262c6f553cc56a7a546ab8fe5555dda4547f91c558de7fa3
bb:sha256: da19536cc2702f347c0bff14ded4bce39b60e5261981fde99bf4567d0ed38b07
sources:
  - id: payment-webhooks--provider-webhook-contracts
    resource: /references/payment-webhooks--provider-webhook-contracts.md
    title: "Provider webhook contracts"
    author: human:maintainer
---

# Ask whether an incoming payment event is authenticated and applied once, by replaying one Program-supplied test or sandbox delivery beside an unsigned, body-modified, stale and duplicate arm and reading the target's authoritative payment state after each.

## What it concludes about

- `authentication.credential_verification`

## When it is selected

A subject carrying every one of these facts:

- `json_request`
- `state_changing_method`
- `unauthenticated_endpoint`

Risk `approval_required`, effects `mutates_object`, baseline `pristine_surface`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)
- [handle-untrusted-content](/skills/handle-untrusted-content.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `response_differential` observation(s) from a `variant`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `control`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `variant`

## Provenance

Written for ticket 231 from the current official Stripe, Adyen and PayPal webhook verification contracts. Kept separate from webhooks because that Playbook asks whether caller input controls an outbound server request and concludes injection.request_forgery; this one asks whether a credential on an incoming provider event is verified and concludes authentication.credential_verification.

## Maintainer references

- [provider-webhook-contracts.md](/references/payment-webhooks--provider-webhook-contracts.md)[^payment-webhooks--provider-webhook-contracts]

[^payment-webhooks--provider-webhook-contracts]: Provider webhook contracts

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/payment-webhooks/playbook.md`](../../../src/redkraken/playbooks/payment-webhooks/playbook.md). This concept describes that document and never replaces it.
