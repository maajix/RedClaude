---
type: Playbook
title: "webhooks"
description: "Ask whether a URL the caller supplies is one the server itself will fetch, by pointing a URL-typed parameter, a request header or a subresource of a submitted document at a correlator the runtime minted, and treating the arrival on the declared channel as the only proof."
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
bb:version: fe3b6352039879edb45fe62e635a4480b478e0a05ac0bc70e3102a79ac57c4dc
bb:sha256: b040cf29af8e5448404ebf9e90c34a7ba37ff7b8d5381abff2299dcc646e3bc3
---

# Ask whether a URL the caller supplies is one the server itself will fetch, by pointing a URL-typed parameter, a request header or a subresource of a submitted document at a correlator the runtime minted, and treating the arrival on the declared channel as the only proof.

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

- to `refuted`: at least 1 refutes `response_differential` observation(s) from a `variant`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `control`
- to `supported`: at least 1 supports `callback_interaction` observation(s) from a `variant`

## Provenance

Written for ticket 49 as the v2 replacement for v1's webhooks pack, against the request-forgery leaf of the ticket 18 vocabulary; v1 shipped a README for this topic and no reference text, so nothing is attached. Rewritten for ticket 101 against the merged ledger, which carries three readings that reach a Finding and one block. One key moved. The refuted variant row leaves response_invariant for response_differential, the kind close_test_replay writes for either leg of a differencing assertion whichever way the run came out; the supported row of that role keeps callback_interaction, which is the arrival and is filed by record_callback_interaction rather than by the replay lane, so copying it onto the refuted row would grade a refutation on an arrival that by definition did not happen. Ticket 211 made the body-borne reading of section 3 a Test; section 2 stops at an Observation, because its arms differ only by a header name and no differencing assertion over them holds.

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/webhooks/playbook.md`](../../../src/redkraken/playbooks/webhooks/playbook.md). This concept describes that document and never replaces it.
