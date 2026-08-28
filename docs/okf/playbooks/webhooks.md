---
type: Playbook
title: "webhooks"
description: "Ask whether a URL the caller supplies is one the server itself will fetch, by pointing it at a correlator the runtime minted and waiting for the interaction to arrive out of band."
resource: ../../../src/redkraken/playbooks/webhooks/playbook.md
tags: [injection, approval_required, mutates_object]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-02-15T00:00:00Z
bb:category: injection
bb:outputs: [injection.request_forgery]
bb:triggers_all: [state_changing_method, url_valued_parameter]
bb:skills: [compare-responses, handle-untrusted-content]
bb:risk: approval_required
bb:effects: mutates_object
bb:baseline: none
bb:version: ae4fc32557c157437efa26c02fa16dd737aeaff2c75539fd3a3b511d76bce276
bb:sha256: 2e4ab6e4fae677ee6a6c0849d55014f9b6965b1cb243f2f2799d05a56d402428
---

# Ask whether a URL the caller supplies is one the server itself will fetch, by pointing it at a correlator the runtime minted and waiting for the interaction to arrive out of band.

## What it concludes about

- `injection.request_forgery`

## When it is selected

A subject carrying every one of these facts:

- `state_changing_method`
- `url_valued_parameter`

Risk `approval_required`, effects `mutates_object`, baseline `none`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)
- [handle-untrusted-content](/skills/handle-untrusted-content.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `response_invariant` observation(s) from a `variant`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `control`
- to `supported`: at least 1 supports `callback_interaction` observation(s) from a `variant`

## Provenance

Written for ticket 49 as the v2 replacement for v1's webhooks pack, against the request-forgery leaf of the ticket 18 vocabulary; v1 shipped a README for this topic and no reference text, so nothing is attached.

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/webhooks/playbook.md`](../../../src/redkraken/playbooks/webhooks/playbook.md). This concept describes that document and never replaces it.
