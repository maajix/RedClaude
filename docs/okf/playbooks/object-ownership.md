---
type: Playbook
title: "object-ownership"
description: "Ask whether the object named in a request is checked against the caller, by sending one request twice under two leased Identities and differencing the two stored responses."
resource: ../../../src/redkraken/playbooks/object-ownership/playbook.md
tags: [authorization, constrained, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-02-15T00:00:00Z
bb:category: authorization
bb:outputs: [authorization.object_ownership]
bb:triggers_all: [multiple_test_identities, object_identifier]
bb:triggers_any: [body_parameter, path_parameter, query_parameter]
bb:skills: [compare-responses, use-identity]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:version: c8c808bc2dc083ec637ec7a2b90005072cf5e8db6ca8850229ad48d47bed99d5
bb:sha256: c4fb1ec47b89e431a65a796e28b367a43705d8a9e2b3304e1d067ba95ae261bb
sources:
  - id: object-ownership--why-two-identities
    resource: /references/object-ownership--why-two-identities.md
    title: "Why this Playbook insists on a control"
    author: human:maintainer
---

# Ask whether the object named in a request is checked against the caller, by sending one request twice under two leased Identities and differencing the two stored responses.

## What it concludes about

- `authorization.object_ownership`

## When it is selected

A subject carrying every one of these facts:

- `multiple_test_identities`
- `object_identifier`

and at least one of:

- `body_parameter`
- `path_parameter`
- `query_parameter`

Risk `constrained`, effects `read_only`, baseline `stable_session`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `response_differential` observation(s) from a `variant`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `control`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `variant`

## Provenance

Written for ticket 45 against the object-ownership leaf of the ticket 18 vocabulary; no upstream card, no third-party list.

## Maintainer references

- [why-two-identities.md](/references/object-ownership--why-two-identities.md)[^object-ownership--why-two-identities]

[^object-ownership--why-two-identities]: Why this Playbook insists on a control

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/object-ownership/playbook.md`](../../../src/redkraken/playbooks/object-ownership/playbook.md). This concept describes that document and never replaces it.
