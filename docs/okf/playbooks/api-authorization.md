---
type: Playbook
title: "api-authorization"
description: "Ask whether an operation is refused when the object's own state forbids it, by sending the same operation against an object that may still take it, an object somebody else owns and an identifier that names nothing, and reading the owner's own view of what changed."
resource: ../../../src/redkraken/playbooks/api-authorization/playbook.md
tags: [authorization, constrained, mutates_object]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-03-15T00:00:00Z
bb:category: authorization
bb:outputs: [authorization.state_transition]
bb:triggers_all: [multiple_test_identities, path_parameter, state_changing_method]
bb:skills: [compare-responses, use-identity]
bb:risk: constrained
bb:effects: mutates_object
bb:baseline: pristine_surface
bb:version: e27f0c2e62a2160fd1ff949a9204fd9865c8595004ffe590f0b43272e5619330
bb:sha256: e7d0c7c4dbe310550def00fd6c53fe7b988d4da6aa8cc6f900ffb65325b49647
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

# Ask whether an operation is refused when the object's own state forbids it, by sending the same operation against an object that may still take it, an object somebody else owns and an identifier that names nothing, and reading the owner's own view of what changed.

## What it concludes about

- `authorization.state_transition`

## When it is selected

A subject carrying every one of these facts:

- `multiple_test_identities`
- `path_parameter`
- `state_changing_method`

Risk `constrained`, effects `mutates_object`, baseline `pristine_surface`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `response_invariant` observation(s) from a `variant`
- to `supported`: at least 1 supports `credential_effect` observation(s) from a `control`
- to `supported`: at least 1 supports `state_change` observation(s) from a `variant`

## Provenance

Written for ticket 51 as the v2 replacement for v1's api-authorization pack, against the state-transition leaf of the ticket 18 vocabulary; two v1 texts are attached as maintainer references and both describe the identifier work step 1 rests on.

## Maintainer references

- [idor.md](/references/api-authorization--idor.md)[^api-authorization--idor]
- [uuids.md](/references/api-authorization--uuids.md)[^api-authorization--uuids]

[^api-authorization--idor]: Direct object references: where the identifier comes from, and what it proves
[^api-authorization--uuids]: UUIDs: what the version tells you, and what it does not

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/api-authorization/playbook.md`](../../../src/redkraken/playbooks/api-authorization/playbook.md). This concept describes that document and never replaces it.
