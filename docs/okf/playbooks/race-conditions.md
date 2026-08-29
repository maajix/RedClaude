---
type: Playbook
title: "race-conditions"
description: "Ask whether a single-use action stays single, by reading the count a target keeps before anything is sent and then spending one value twice inside a Test whose own assertions difference that counter."
resource: ../../../src/redkraken/playbooks/race-conditions/playbook.md
tags: [business_logic, constrained, mutates_object]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-03-15T00:00:00Z
bb:category: business_logic
bb:outputs: [business_logic.replay]
bb:triggers_all: [authenticated_endpoint, json_request, state_changing_method]
bb:skills: [compare-responses, use-identity]
bb:risk: constrained
bb:effects: mutates_object
bb:baseline: pristine_surface
bb:version: 5853faca7edc920973cdfa1b12700152d8c338bd8a5fbc7e2ce901b7e6400f84
bb:sha256: fd47c8dd7bf707139d6fd858d42b1e72ce9cad49fb5664860fcb93f9ef6ec5c4
sources:
  - id: race-conditions--race-conditions-and-timing-attacks
    resource: /references/race-conditions--race-conditions-and-timing-attacks.md
    title: "Race conditions and timing attacks: one pack, two unrelated readings"
    author: human:maintainer
---

# Ask whether a single-use action stays single, by reading the count a target keeps before anything is sent and then spending one value twice inside a Test whose own assertions difference that counter.

## What it concludes about

- `business_logic.replay`

## When it is selected

A subject carrying every one of these facts:

- `authenticated_endpoint`
- `json_request`
- `state_changing_method`

Risk `constrained`, effects `mutates_object`, baseline `pristine_surface`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `response_differential` observation(s) from a `variant`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `control`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `variant`

## Provenance

Written for ticket 51 as the v2 replacement for v1's race-conditions pack against the replay leaf of the ticket 18 vocabulary, and rewritten for ticket 101 against the merged ledger's four readings for this slug. Ticket 211 is what moved the sequential reading onto the Finding path, because a Test action now states the body it plans and the single-use value this Playbook's triggers declare rides one. All three evidence rows now name response_differential, because the counter reads are actions of the Test and close_test_replay writes their Observations from the specification, while an agent-filed state_change citing a counter read cannot be added once the first recorded action has moved the claim past proposed; the concurrent pair the shipped step 4 asked for is blocked and the single-packet forms are refused, and both are named at the end rather than dropped.

## Maintainer references

- [race-conditions-and-timing-attacks.md](/references/race-conditions--race-conditions-and-timing-attacks.md)[^race-conditions--race-conditions-and-timing-attacks]

[^race-conditions--race-conditions-and-timing-attacks]: Race conditions and timing attacks: one pack, two unrelated readings

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/race-conditions/playbook.md`](../../../src/redkraken/playbooks/race-conditions/playbook.md). This concept describes that document and never replaces it.
