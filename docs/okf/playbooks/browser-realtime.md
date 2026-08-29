---
type: Playbook
title: "browser-realtime"
description: "Ask whether a socket route reaches an authorization decision about a channel name before it reaches the protocol, and whether the ticket a realtime stack mints over ordinary https is scoped to the channel the caller asked for, by carrying a second Identity's channel name in the query of an ordinary GET and differencing the answer against a name nobody owns."
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
bb:version: 3a8ea60a2625e66505abe11825e08691c8fb84f3fbedb14665574b698b4eb4c1
bb:sha256: 5aca8628ad7ef84e1dfed4cff1a89f2be7c5e919284f9088b90111b406abdae8
sources:
  - id: browser-realtime--websocket-attacks
    resource: /references/browser-realtime--websocket-attacks.md
    title: "WebSocket attacks: the handshake is where this harness stops"
    author: human:maintainer
---

# Ask whether a socket route reaches an authorization decision about a channel name before it reaches the protocol, and whether the ticket a realtime stack mints over ordinary https is scoped to the channel the caller asked for, by carrying a second Identity's channel name in the query of an ordinary GET and differencing the answer against a name nobody owns.

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

- to `refuted`: at least 1 refutes `credential_effect` observation(s) from a `variant`
- to `supported`: at least 1 supports `credential_effect` observation(s) from a `control`
- to `supported`: at least 1 supports `credential_effect` observation(s) from a `variant`

## Provenance

Written for ticket 52 against the channel-subscription leaf ticket 52 added, with the v1 websocket text attached as a maintainer reference. Rewritten for ticket 101 against the merged technique ledger, which holds two readings and two refusals for this slug. Every step of the shipped text was an upgrade handshake, and our own egress drops connection and upgrade before the wire, which is why this was the only Playbook of fifty with no executable reading. The two readings that replace them are ordinary GETs differing in the query, so bb:effects stays read_only and bb:risk stays constrained. The refuted leg moves from response_invariant to credential_effect, which is the kind its own role already asked for on the supported leg. Repaired again in review -- the caller's own channel is the baseline and the name nobody owns the control, which is the shape section 3 already had, and the second Task leaves through suggested_tasks rather than standing as a requirement with no verb.

## Maintainer references

- [websocket-attacks.md](/references/browser-realtime--websocket-attacks.md)[^browser-realtime--websocket-attacks]

[^browser-realtime--websocket-attacks]: WebSocket attacks: the handshake is where this harness stops

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/browser-realtime/playbook.md`](../../../src/redkraken/playbooks/browser-realtime/playbook.md). This concept describes that document and never replaces it.
