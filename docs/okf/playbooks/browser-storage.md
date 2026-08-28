---
type: Playbook
title: "browser-storage"
description: "Ask whether the target delivers its session where page script can hold it rather than in a cookie the browser keeps closed, by reading how the credential arrives and replaying the script-readable half of it on its own."
resource: ../../../src/redkraken/playbooks/browser-storage/playbook.md
tags: [information_disclosure, constrained, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-03-15T00:00:00Z
bb:category: information_disclosure
bb:outputs: [information_disclosure.client_storage]
bb:triggers_all: [authenticated_endpoint, read_method, web_surface]
bb:skills: [compare-responses, use-identity]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:version: f4f43b26446df6591e6feb1eabb049875ecfe1f0445cbdf28fa17fe61d1d03fe
bb:sha256: b969edec2994ff8859f7017cb82489ffd6a8783281f044ff3d689578dbfbecd9
---

# Ask whether the target delivers its session where page script can hold it rather than in a cookie the browser keeps closed, by reading how the credential arrives and replaying the script-readable half of it on its own.

## What it concludes about

- `information_disclosure.client_storage`

## When it is selected

A subject carrying every one of these facts:

- `authenticated_endpoint`
- `read_method`
- `web_surface`

Risk `constrained`, effects `read_only`, baseline `stable_session`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `header_policy_observed` observation(s) from a `control`
- to `supported`: at least 1 supports `credential_effect` observation(s) from a `control`
- to `supported`: at least 1 supports `credential_effect` observation(s) from a `variant`

## Provenance

Written for ticket 52 against a new client-storage leaf added by ticket 52; v1 had no page on this topic, so nothing is attached rather than a placeholder.

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/browser-storage/playbook.md`](../../../src/redkraken/playbooks/browser-storage/playbook.md). This concept describes that document and never replaces it.
