---
type: Playbook
title: "api"
description: "Ask what the limiter counts and what it counts against, by driving one declared sequence under one leased Identity and then re-driving it with a single key candidate moving -- the route as the caller spelled it, a forwarded address the caller writes, the account the attempt names, or the amount of work one legal request carries."
resource: ../../../src/redkraken/playbooks/api/playbook.md
tags: [rate_limiting, approval_required, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-02-15T00:00:00Z
bb:category: rate_limiting
bb:outputs: [rate_limiting.per_identity, rate_limiting.per_origin, rate_limiting.resource_cost]
bb:triggers_all: [api_surface, multiple_test_identities]
bb:skills: [compare-responses, enumerate-surface, use-identity]
bb:risk: approval_required
bb:effects: read_only
bb:baseline: stable_session
bb:version: 1d01746ca64c4ffce790b73e3bbe154c91f6180016def4024784537992262c21
bb:sha256: 9ee1d41d5e28555bcec2e363d32e8a8751ceb2345957e5b71c19754f8f94629f
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

# Ask what the limiter counts and what it counts against, by driving one declared sequence under one leased Identity and then re-driving it with a single key candidate moving -- the route as the caller spelled it, a forwarded address the caller writes, the account the attempt names, or the amount of work one legal request carries.

## What it concludes about

- `rate_limiting.per_identity`
- `rate_limiting.per_origin`
- `rate_limiting.resource_cost`

## When it is selected

A subject carrying every one of these facts:

- `api_surface`
- `multiple_test_identities`

Risk `approval_required`, effects `read_only`, baseline `stable_session`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)
- [enumerate-surface](/skills/enumerate-surface.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `response_invariant` observation(s) from a `variant`
- to `supported`: at least 1 supports `credential_effect` observation(s) from a `control`
- to `supported`: at least 1 supports `response_invariant` observation(s) from a `variant`

## Provenance

Written for ticket 49 as the v2 replacement for v1's api pack, against the per-identity leaf of the ticket 18 vocabulary; the rate-limit-bypass text is the only one of the three v1 files that named a defect. Rewritten for ticket 101 against the merged ledger, which carries nine readings, one blocked and one refused for this slug. bb:outputs gains rate_limiting.per_origin and rate_limiting.resource_cost, the two emitters ticket 101 owes and the classes six of the eleven rows read; this Playbook holds the only rate_limiting category, so no other slug could carry them. bb:skills gains enumerate-surface, already held by the executing role. bb:evidence moves its refuted variant leg from response_differential to response_invariant, the kind the supported leg of the same role names, because an equalities-only sequence closes response_invariant for every variant action whichever way it settles; every section now leaves a variant action no differing assertion names.

## Maintainer references

- [api-soap.md](/references/api--api-soap.md)[^api--api-soap]
- [api.md](/references/api--api.md)[^api--api]
- [rate-limit-bypass.md](/references/api--rate-limit-bypass.md)[^api--rate-limit-bypass]

[^api--api-soap]: SOAP surfaces, and the three places they differ from the rest
[^api--api]: Reading an API surface, and why this Playbook claims one class
[^api--rate-limit-bypass]: Bypassing a limit, and why that is not what the Playbook does

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/api/playbook.md`](../../../src/redkraken/playbooks/api/playbook.md). This concept describes that document and never replaces it.
