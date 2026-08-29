---
type: Playbook
title: "api-authorization"
description: "Ask whether a write is refused when the object's own state forbids it and whether it binds only the properties the interface offers, by sending one operation against a permitting object, a forbidding object, a retired version of the same route, a verb the route never advertises and a property the interface never sends, and taking every verdict from the owner's own read-back."
resource: ../../../src/redkraken/playbooks/api-authorization/playbook.md
tags: [authorization, constrained, mutates_object]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-03-15T00:00:00Z
bb:category: authorization
bb:outputs: [authorization.object_property_write, authorization.state_transition]
bb:triggers_all: [multiple_test_identities, path_parameter, state_changing_method]
bb:skills: [compare-responses, enumerate-surface, use-identity]
bb:risk: constrained
bb:effects: mutates_object
bb:baseline: pristine_surface
bb:version: 28a86bca4b81ca92c4f593525a3c00e088632f96eda95378484e570807a37291
bb:sha256: 5968e4ec338de01784176aa0a85d8a57f3ace876b44eb5b304ae35aac6de8738
sources:
  - id: api-authorization--idor
    resource: /references/api-authorization--idor.md
    title: "Direct object references: where the identifier comes from, and what it proves"
    author: human:maintainer
  - id: api-authorization--uuids
    resource: /references/api-authorization--uuids.md
    title: "UUIDs: what the version tells you, and what it does not"
    author: human:maintainer
---

# Ask whether a write is refused when the object's own state forbids it and whether it binds only the properties the interface offers, by sending one operation against a permitting object, a forbidding object, a retired version of the same route, a verb the route never advertises and a property the interface never sends, and taking every verdict from the owner's own read-back.

## What it concludes about

- `authorization.object_property_write`
- `authorization.state_transition`

## When it is selected

A subject carrying every one of these facts:

- `multiple_test_identities`
- `path_parameter`
- `state_changing_method`

Risk `constrained`, effects `mutates_object`, baseline `pristine_surface`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)
- [enumerate-surface](/skills/enumerate-surface.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `state_change` observation(s) from a `variant`
- to `supported`: at least 1 supports `credential_effect` observation(s) from a `control`
- to `supported`: at least 1 supports `state_change` observation(s) from a `variant`

## Provenance

Written for ticket 51 as the v2 replacement for v1's api-authorization pack, against the state-transition leaf of the ticket 18 vocabulary; two v1 texts are attached as maintainer references and both describe the identifier work section 1 rests on. Rewritten for ticket 101 against the merged ledger, which carries six readings for this slug and no refusal. Three keys moved. bb:outputs gains authorization.object_property_write, one of the nine leaves nothing emitted, because four readings ask which property a write binds rather than which transition it performs, and D3 settles that the emitter line closes inside this ticket. bb:skills gains enumerate-surface, which the retired-prefix reading needs to take a version prefix off a bundle rather than off a wordlist. The refuted variant leg moves from response_invariant to state_change, the kind the supported leg of the same role names, because close_test_replay derives a kind from the specification and one role writes one kind whichever way the reading comes out.

## Maintainer references

- [idor.md](/references/api-authorization--idor.md)[^api-authorization--idor]
- [uuids.md](/references/api-authorization--uuids.md)[^api-authorization--uuids]

[^api-authorization--idor]: Direct object references: where the identifier comes from, and what it proves
[^api-authorization--uuids]: UUIDs: what the version tells you, and what it does not

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/api-authorization/playbook.md`](../../../src/redkraken/playbooks/api-authorization/playbook.md). This concept describes that document and never replaces it.
