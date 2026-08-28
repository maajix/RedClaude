---
type: Playbook
title: "realtime"
description: "Ask whether a websocket handshake requires proof of same-origin intent, by opening the same authenticated handshake once from the application's own origin and once from an origin it has never seen."
resource: ../../../src/redkraken/playbooks/realtime/playbook.md
tags: [session_handling, constrained, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-02-15T00:00:00Z
bb:category: session_handling
bb:outputs: [session_handling.csrf]
bb:triggers_all: [authenticated_endpoint, websocket_surface]
bb:skills: [browser-evidence, compare-responses]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:version: 4c2c715592b875583b1c9466f527578795e83dd9200c4e6bb10581b443fe4c1c
bb:sha256: 631533297beff08d564ccb93b0a72269987733e2931e71d1f2712a1bbe764227
---

# Ask whether a websocket handshake requires proof of same-origin intent, by opening the same authenticated handshake once from the application's own origin and once from an origin it has never seen.

## What it concludes about

- `session_handling.csrf`

## When it is selected

A subject carrying every one of these facts:

- `authenticated_endpoint`
- `websocket_surface`

Risk `constrained`, effects `read_only`, baseline `stable_session`.

## Skills it loads

- [browser-evidence](/skills/browser-evidence.md)
- [compare-responses](/skills/compare-responses.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `response_differential` observation(s) from a `variant`
- to `supported`: at least 1 supports `credential_effect` observation(s) from a `control`
- to `supported`: at least 1 supports `response_invariant` observation(s) from a `variant`

## Provenance

Written for ticket 49 as the v2 replacement for v1's realtime pack, against the csrf leaf of the ticket 18 vocabulary; v1 shipped a README for this topic and no reference text, so nothing is attached.

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/realtime/playbook.md`](../../../src/redkraken/playbooks/realtime/playbook.md). This concept describes that document and never replaces it.
