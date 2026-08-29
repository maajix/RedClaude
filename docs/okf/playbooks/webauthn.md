---
type: Playbook
title: "webauthn"
description: "Ask whether a step-up route enforces the factor it asks for or merely offers it, by driving the action honestly once and then reaching it with the factor withheld, renamed, replayed, or its subject taken from a value the caller writes."
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
bb:version: 681c72cf2ce9de3a42f610513642e2a053ff6b6b59ed28d069d14738bad5e657
bb:sha256: 0e145baf966155543d2a13ce81f765ee86be8af01fcf1f4df792065fa4417ced
---

# Ask whether a step-up route enforces the factor it asks for or merely offers it, by driving the action honestly once and then reaching it with the factor withheld, renamed, replayed, or its subject taken from a value the caller writes.

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

- to `refuted`: at least 1 refutes `state_change` observation(s) from a `variant`
- to `supported`: at least 1 supports `credential_effect` observation(s) from a `control`
- to `supported`: at least 1 supports `state_change` observation(s) from a `variant`

## Provenance

Written for ticket 50 as the v2 replacement for v1's webauthn pack, against the factor-enforcement leaf of the ticket 18 vocabulary; v1 shipped a README for this topic and no reference text, so nothing is attached. Rewritten for ticket 101 against the merged ledger, which carries four readings and one refusal for this slug. One key moved. The refuted variant row moves from response_invariant to state_change, the kind the supported row of that same role names, because close_test_replay derives the kind from the specification and one role writes one kind whichever way the reading goes.

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/webauthn/playbook.md`](../../../src/redkraken/playbooks/webauthn/playbook.md). This concept describes that document and never replaces it.
