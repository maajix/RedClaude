---
type: Playbook
title: "grpc"
description: "Ask whether a callable is anyone's to invoke, by putting a name the application never publishes where the published one goes -- in a path segment, in a request field, or in a gRPC-Web method path called under a second leased Identity -- and reading whether the answer parts from the router's own refusal."
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
bb:version: 4d5fa743fcc21f64f310d749d127a3bafafb5b4ed35d948134259c07653ea4ee
bb:sha256: f4b799a7b89228df8ed9e70027f45fe4ca799ec8db630efa49ecc302cd51f60a
---

# Ask whether a callable is anyone's to invoke, by putting a name the application never publishes where the published one goes -- in a path segment, in a request field, or in a gRPC-Web method path called under a second leased Identity -- and reading whether the answer parts from the router's own refusal.

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

- to `refuted`: at least 1 refutes `response_differential` observation(s) from a `variant`
- to `supported`: at least 1 supports `response_invariant` observation(s) from a `control`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `variant`

## Provenance

Written for ticket 49 as the v2 replacement for v1's grpc pack, against the function-access leaf of the ticket 18 vocabulary; v1 shipped a README for this topic and no reference text, so nothing is attached. Rewritten for ticket 101 against the merged ledger, which carries four readings here, three reachable and one blocked. The trigger set is unchanged. A first pass moved it onto path_parameter and was wrong to -- that fact is recorded for a parameter recon classified inside the path, not for the path itself, so it misses this Playbook's own subject and selects on every route that has one. tech_grpc stays required. bb:evidence keeps response_differential on both variant legs and moves the supported control leg from credential_effect to response_invariant, because two of the three readings present no credential at all and the ledger asks for credential_effect in role variant on the third rather than in role control; it survives as a named mechanism edge in section 3 and is no longer a bar no section can meet.

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/grpc/playbook.md`](../../../src/redkraken/playbooks/grpc/playbook.md). This concept describes that document and never replaces it.
