---
type: Playbook
title: "api"
description: "Ask whether repetition against one account is bounded at all, by sending a small declared number of identical requests under one leased Identity and reading whether the answers ever change."
resource: ../../../src/redkraken/playbooks/api/playbook.md
tags: [rate_limiting, approval_required, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-02-15T00:00:00Z
bb:category: rate_limiting
bb:outputs: [rate_limiting.per_identity]
bb:triggers_all: [api_surface, multiple_test_identities]
bb:skills: [compare-responses, use-identity]
bb:risk: approval_required
bb:effects: read_only
bb:baseline: stable_session
bb:version: e95cdb2be4b8b3d7beb5f0748bd283f970f84a06229766549c01c7dcc2684f11
bb:sha256: fb9b71cd4384b6b8341938e98eabe6ff31994d14335efa64b65585afe082d4e7
sources:
  - id: api--api-soap
    resource: /references/api--api-soap.md
    title: "SOAP surfaces, and the three places they differ from the rest"
    author: human:maintainer
  - id: api--api
    resource: /references/api--api.md
    title: "Reading an API surface, and why this Playbook claims one class"
    author: human:maintainer
  - id: api--rate-limit-bypass
    resource: /references/api--rate-limit-bypass.md
    title: "Bypassing a limit, and why that is not what the Playbook does"
    author: human:maintainer
---

# Ask whether repetition against one account is bounded at all, by sending a small declared number of identical requests under one leased Identity and reading whether the answers ever change.

## What it concludes about

- `rate_limiting.per_identity`

## When it is selected

A subject carrying every one of these facts:

- `api_surface`
- `multiple_test_identities`

Risk `approval_required`, effects `read_only`, baseline `stable_session`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `response_differential` observation(s) from a `variant`
- to `supported`: at least 1 supports `credential_effect` observation(s) from a `control`
- to `supported`: at least 1 supports `response_invariant` observation(s) from a `variant`

## Provenance

Written for ticket 49 as the v2 replacement for v1's api pack, against the per-identity leaf of the ticket 18 vocabulary; the rate-limit-bypass text is the only one of the three v1 files that named a defect, and this is the class it named.

## Maintainer references

- [api-soap.md](/references/api--api-soap.md)[^api--api-soap]
- [api.md](/references/api--api.md)[^api--api]
- [rate-limit-bypass.md](/references/api--rate-limit-bypass.md)[^api--rate-limit-bypass]

[^api--api-soap]: SOAP surfaces, and the three places they differ from the rest
[^api--api]: Reading an API surface, and why this Playbook claims one class
[^api--rate-limit-bypass]: Bypassing a limit, and why that is not what the Playbook does

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/api/playbook.md`](../../../src/redkraken/playbooks/api/playbook.md). This concept describes that document and never replaces it.
