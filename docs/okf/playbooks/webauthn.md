---
type: Playbook
title: "webauthn"
description: "Ask whether a step-up route enforces the factor it asks for or merely offers it, by completing the sensitive action while withholding, downgrading and replaying the second factor the client was told to present."
resource: ../../../src/redkraken/playbooks/webauthn/playbook.md
tags: [authentication, approval_required, mutates_account]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-03-15T00:00:00Z
bb:category: authentication
bb:outputs: [authentication.factor_enforcement]
bb:triggers_all: [state_changing_method, tech_webauthn]
bb:skills: [compare-responses, use-identity]
bb:risk: approval_required
bb:effects: mutates_account
bb:baseline: stable_session
bb:version: 0522c44ac3bab244b81447660943e223808c16a2560737b52568df0dadb7e5c3
bb:sha256: 5bc566683b6822c4cc73305484fcac13ded4091b6f6f0eae3569b3b054101748
---

# Ask whether a step-up route enforces the factor it asks for or merely offers it, by completing the sensitive action while withholding, downgrading and replaying the second factor the client was told to present.

## What it concludes about

- `authentication.factor_enforcement`

## When it is selected

A subject carrying every one of these facts:

- `state_changing_method`
- `tech_webauthn`

Risk `approval_required`, effects `mutates_account`, baseline `stable_session`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `response_invariant` observation(s) from a `variant`
- to `supported`: at least 1 supports `credential_effect` observation(s) from a `control`
- to `supported`: at least 1 supports `state_change` observation(s) from a `variant`

## Provenance

Written for ticket 50 as the v2 replacement for v1's webauthn pack, against the factor-enforcement leaf of the ticket 18 vocabulary; v1 shipped a README for this topic and no reference text, so nothing is attached.

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/webauthn/playbook.md`](../../../src/redkraken/playbooks/webauthn/playbook.md). This concept describes that document and never replaces it.
