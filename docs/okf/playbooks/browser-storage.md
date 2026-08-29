---
type: Playbook
title: "browser-storage"
description: "Ask whether the target delivers its session where page script can hold it rather than in a cookie the browser keeps closed, by inventorying what the browser holds across the authentication boundary and replaying the script-readable half of the credential on a Task that leases no Identity of its own."
resource: ../../../src/redkraken/playbooks/browser-storage/playbook.md
tags: [information_disclosure, constrained, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-03-15T00:00:00Z
bb:category: information_disclosure
bb:outputs: [information_disclosure.client_storage]
bb:triggers_all: [authenticated_endpoint, read_method, web_surface]
bb:skills: [browser-evidence, compare-responses, handle-untrusted-content, use-identity]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:version: 1d65856b691d2c8ba8ede5359b2c296196b88c0709ee726dd701d664601828fc
bb:sha256: 18a4909c99a124d1266c81f19d309b276fa335e685aeacf9dce21ea1fa9dd94e
---

# Ask whether the target delivers its session where page script can hold it rather than in a cookie the browser keeps closed, by inventorying what the browser holds across the authentication boundary and replaying the script-readable half of the credential on a Task that leases no Identity of its own.

## What it concludes about

- `information_disclosure.client_storage`

## When it is selected

A subject carrying every one of these facts:

- `authenticated_endpoint`
- `read_method`
- `web_surface`

Risk `constrained`, effects `read_only`, baseline `stable_session`.

## Skills it loads

- [browser-evidence](/skills/browser-evidence.md)
- [compare-responses](/skills/compare-responses.md)
- [handle-untrusted-content](/skills/handle-untrusted-content.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `credential_effect` observation(s) from a `control`
- to `supported`: at least 1 supports `credential_effect` observation(s) from a `control`
- to `supported`: at least 1 supports `credential_effect` observation(s) from a `variant`

## Provenance

Written for ticket 52 against a new client-storage leaf added by ticket 52; v1 had no page on this topic, so nothing is attached rather than a placeholder. Rewritten for ticket 101 against the merged technique ledger, which carries four readings for this slug. Two frontmatter keys moved -- browser-evidence and handle-untrusted-content join bb:skills, because the client-state inventories the old step 4 declared impossible have been a registry-owned browser action since 20261210T000000Z and what they return is untrusted content. One bb:evidence leg moves and it is a repair -- the refuted leg of the control role asked for header_policy_observed while the supported leg of the same role asked for credential_effect, and one role carries one kind whichever way a reading goes, so the refuted leg now carries the kind its own role carries on supported. All three legs name agent-filed kinds, which close_test_replay does not derive, so each is filed with the proposal while the claim is still proposed.

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/browser-storage/playbook.md`](../../../src/redkraken/playbooks/browser-storage/playbook.md). This concept describes that document and never replaces it.
