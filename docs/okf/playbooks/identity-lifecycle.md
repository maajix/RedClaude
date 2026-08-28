---
type: Playbook
title: "identity-lifecycle"
description: "Ask whether a session survives the event that was supposed to end it, by driving one leased session across a logout, a password change or a revocation and replaying a request that only a live session answers."
resource: ../../../src/redkraken/playbooks/identity-lifecycle/playbook.md
tags: [session_handling, constrained, mutates_session]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-03-15T00:00:00Z
bb:category: session_handling
bb:outputs: [session_handling.lifetime]
bb:triggers_all: [cookie_parameter, state_changing_method]
bb:skills: [compare-responses, use-identity]
bb:risk: constrained
bb:effects: mutates_session
bb:baseline: stable_session
bb:version: 355490848b42305377eb52a5be8c7dec129191047cf52ceb313a37fb5420a7ac
bb:sha256: 0c027ddcce6aefddc562692785d4f7560d9a462cad14483d14f4829759027777
---

# Ask whether a session survives the event that was supposed to end it, by driving one leased session across a logout, a password change or a revocation and replaying a request that only a live session answers.

## What it concludes about

- `session_handling.lifetime`

## When it is selected

A subject carrying every one of these facts:

- `cookie_parameter`
- `state_changing_method`

Risk `constrained`, effects `mutates_session`, baseline `stable_session`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `response_invariant` observation(s) from a `variant`
- to `supported`: at least 1 supports `credential_effect` observation(s) from a `control`
- to `supported`: at least 1 supports `credential_effect` observation(s) from a `variant`

## Provenance

Written for ticket 50 as the v2 replacement for v1's identity-lifecycle pack, against the session-lifetime leaf of the ticket 18 vocabulary; v1 shipped a README for this topic and no reference text, so nothing is attached.

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/identity-lifecycle/playbook.md`](../../../src/redkraken/playbooks/identity-lifecycle/playbook.md). This concept describes that document and never replaces it.
