---
type: Playbook
title: "workload-identities"
description: "Ask whether a machine-to-machine credential is confined to the tenant it was issued in, by sending one workload token to a route while naming a second tenant in the header that selects one."
resource: ../../../src/redkraken/playbooks/workload-identities/playbook.md
tags: [authorization, constrained, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-03-15T00:00:00Z
bb:category: authorization
bb:outputs: [authorization.tenant_isolation]
bb:triggers_all: [header_parameter, tenant_boundary, unknown_auth_endpoint]
bb:skills: [compare-responses, use-identity]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:version: a188b7048dc012a67047b7f8321d8fde82194d4b89e5ff4c15c6ae9943d46e1b
bb:sha256: c676ed51a5f3bad650855ea4d9069df84a836ec598a954cd8ad1cf321a7742d8
---

# Ask whether a machine-to-machine credential is confined to the tenant it was issued in, by sending one workload token to a route while naming a second tenant in the header that selects one.

## What it concludes about

- `authorization.tenant_isolation`

## When it is selected

A subject carrying every one of these facts:

- `header_parameter`
- `tenant_boundary`
- `unknown_auth_endpoint`

Risk `constrained`, effects `read_only`, baseline `stable_session`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `response_invariant` observation(s) from a `variant`
- to `supported`: at least 1 supports `credential_effect` observation(s) from a `control`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `variant`

## Provenance

Written for ticket 50 as the v2 replacement for v1's workload-identities pack, against the tenant-isolation leaf of the ticket 18 vocabulary; v1 shipped a README for this topic and no reference text, so nothing is attached.

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/workload-identities/playbook.md`](../../../src/redkraken/playbooks/workload-identities/playbook.md). This concept describes that document and never replaces it.
