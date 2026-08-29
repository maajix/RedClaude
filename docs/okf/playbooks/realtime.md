---
type: Playbook
title: "realtime"
description: "Ask whether a state-changing request is accepted without proof that the caller's own page asked for it, by replaying one guarded submission with the anti-forgery token absent, emptied, mutated and borrowed from a second session, under a changed verb, under Referer and Origin shapes an allow list may mismatch, and under a content type that provokes no preflight."
resource: ../../../src/redkraken/playbooks/realtime/playbook.md
tags: [session_handling, constrained, mutates_object]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-02-15T00:00:00Z
bb:category: session_handling
bb:outputs: [session_handling.csrf]
bb:triggers_all: [authenticated_endpoint, form_request]
bb:triggers_any: [state_changing_method, websocket_surface]
bb:skills: [compare-responses, use-identity]
bb:risk: constrained
bb:effects: mutates_object
bb:baseline: stable_session
bb:version: 78d551577dfb305e2cf10719b34e2aadcf9d35ae9344162fa4b3d853e3dab421
bb:sha256: cfab2e671840e4bd31bdb06cfabae6677215f290cf24d9003b195048598963fe
---

# Ask whether a state-changing request is accepted without proof that the caller's own page asked for it, by replaying one guarded submission with the anti-forgery token absent, emptied, mutated and borrowed from a second session, under a changed verb, under Referer and Origin shapes an allow list may mismatch, and under a content type that provokes no preflight.

## What it concludes about

- `session_handling.csrf`

## When it is selected

A subject carrying every one of these facts:

- `authenticated_endpoint`
- `form_request`

and at least one of:

- `state_changing_method`
- `websocket_surface`

Risk `constrained`, effects `mutates_object`, baseline `stable_session`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `response_differential` observation(s) from a `variant`
- to `supported`: at least 1 supports `credential_effect` observation(s) from a `control`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `variant`

## Provenance

Written for ticket 49 as the v2 replacement for v1's realtime pack, against the csrf leaf of ticket 18's vocabulary. Rewritten for ticket 101 under decision D1, which found the shipped websocket reading cannot execute on any lane and gave this Playbook a truthful form-CSRF scope. Four keys moved. bb:triggers_all becomes authenticated_endpoint and form_request, admitting state_changing_method and websocket_surface. D1 asked for authenticated_endpoint alone; measured, that one fact reaches seventeen of the other forty-nine subjects and takes rank 1 from five under a constrained ceiling, while form_request is what all five form readings are about and leaves two overlaps. bb:effects rises to mutates_object because every reading submits a state change on an object the test Identity owns and restores; bb:risk stays constrained, the floor mutates_object asks for. The supported variant row leaves response_invariant for response_differential; that framing belonged to the blocked handshake reading.

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/realtime/playbook.md`](../../../src/redkraken/playbooks/realtime/playbook.md). This concept describes that document and never replaces it.
