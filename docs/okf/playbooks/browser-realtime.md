---
type: Playbook
title: "browser-realtime"
description: "Ask whether a socket handshake accepts a subscription to a channel the caller does not own, by naming a second Identity's channel in the handshake and comparing what the upgrade answers against the owner's own handshake for the same channel."
resource: ../../../src/redkraken/playbooks/browser-realtime/playbook.md
tags: [authorization, constrained, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-03-15T00:00:00Z
bb:category: authorization
bb:outputs: [authorization.channel_subscription]
bb:triggers_all: [multiple_test_identities, query_parameter, websocket_surface]
bb:skills: [compare-responses, use-identity]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:version: 23c1a0f66654b4cb76e457c78ac9366c086c761c127c3dc8e13bb4e871d7def6
bb:sha256: f491247c11bdde2b7efc9a7391253da724197814f114de0f661da9ad610707be
sources:
  - id: browser-realtime--websocket-attacks
    resource: /references/browser-realtime--websocket-attacks.md
    title: "WebSocket attacks: the handshake is where this harness stops"
    author: human:maintainer
---

# Ask whether a socket handshake accepts a subscription to a channel the caller does not own, by naming a second Identity's channel in the handshake and comparing what the upgrade answers against the owner's own handshake for the same channel.

## What it concludes about

- `authorization.channel_subscription`

## When it is selected

A subject carrying every one of these facts:

- `multiple_test_identities`
- `query_parameter`
- `websocket_surface`

Risk `constrained`, effects `read_only`, baseline `stable_session`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `response_invariant` observation(s) from a `variant`
- to `supported`: at least 1 supports `credential_effect` observation(s) from a `control`
- to `supported`: at least 1 supports `credential_effect` observation(s) from a `variant`

## Provenance

Written for ticket 52 against a new channel-subscription leaf added by ticket 52; the v1 websocket text is attached as a maintainer reference and step 5's limit is where this Playbook and the v1 page part company.

## Maintainer references

- [websocket-attacks.md](/references/browser-realtime--websocket-attacks.md)[^browser-realtime--websocket-attacks]

[^browser-realtime--websocket-attacks]: WebSocket attacks: the handshake is where this harness stops

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/browser-realtime/playbook.md`](../../../src/redkraken/playbooks/browser-realtime/playbook.md). This concept describes that document and never replaces it.
