---
type: Playbook
title: "race-conditions"
description: "Ask whether a single-use action stays single when two copies arrive together, by establishing sequentially that the second copy is refused and then reading the count the target keeps after a concurrent pair."
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
bb:version: d467ca2d636d688b2e661a1c281dcc7918a0371d242401ee238cb73917480446
bb:sha256: aa118d25f5e6a6394f0d39a7802b1c2d86a3bda9cccbaf7bc3b57b03678a4771
sources:
  - id: race-conditions--race-conditions-and-timing-attacks
    resource: /references/race-conditions--race-conditions-and-timing-attacks.md
    title: "Race conditions and timing attacks: one pack, two unrelated readings"
    author: human:maintainer
---

# Ask whether a single-use action stays single when two copies arrive together, by establishing sequentially that the second copy is refused and then reading the count the target keeps after a concurrent pair.

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

- to `refuted`: at least 1 refutes `response_invariant` observation(s) from a `variant`
- to `supported`: at least 1 supports `state_change` observation(s) from a `control`
- to `supported`: at least 1 supports `state_change` observation(s) from a `variant`

## Provenance

Written for ticket 51 as the v2 replacement for v1's race-conditions pack, against the replay leaf of the ticket 18 vocabulary; the v1 race-conditions text is attached as a maintainer reference and is where the sequential control this Playbook insists on comes from.

## Maintainer references

- [race-conditions-and-timing-attacks.md](/references/race-conditions--race-conditions-and-timing-attacks.md)[^race-conditions--race-conditions-and-timing-attacks]

[^race-conditions--race-conditions-and-timing-attacks]: Race conditions and timing attacks: one pack, two unrelated readings

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/race-conditions/playbook.md`](../../../src/redkraken/playbooks/race-conditions/playbook.md). This concept describes that document and never replaces it.
