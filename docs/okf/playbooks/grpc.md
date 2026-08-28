---
type: Playbook
title: "grpc"
description: "Ask whether a gRPC method checks who is calling it, by invoking the same method under two leased Identities and reading the status code the server answers each with."
resource: ../../../src/redkraken/playbooks/grpc/playbook.md
tags: [authorization, constrained, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-02-15T00:00:00Z
bb:category: authorization
bb:outputs: [authorization.function_access]
bb:triggers_all: [multiple_test_identities, tech_grpc]
bb:skills: [compare-responses, use-identity]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:version: a01fef7e904c8180f824cedb9b47a62454dea940cb005da6162280911881c34c
bb:sha256: 24e7e87f9e965802a85ea35faad867a1378ce4aa76b1cbfdfa8f2da3665375c6
---

# Ask whether a gRPC method checks who is calling it, by invoking the same method under two leased Identities and reading the status code the server answers each with.

## What it concludes about

- `authorization.function_access`

## When it is selected

A subject carrying every one of these facts:

- `multiple_test_identities`
- `tech_grpc`

Risk `constrained`, effects `read_only`, baseline `stable_session`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `response_invariant` observation(s) from a `variant`
- to `supported`: at least 1 supports `credential_effect` observation(s) from a `control`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `variant`

## Provenance

Written for ticket 49 as the v2 replacement for v1's grpc pack, against the function-access leaf of the ticket 18 vocabulary; v1 shipped a README for this topic and no reference text, so nothing is attached.

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/grpc/playbook.md`](../../../src/redkraken/playbooks/grpc/playbook.md). This concept describes that document and never replaces it.
