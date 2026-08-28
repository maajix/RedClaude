---
type: Playbook
title: "graphql"
description: "Ask whether a GraphQL selection returns fields the caller is not entitled to, by requesting the same selection under two leased Identities and differencing the two stored documents field by field."
resource: ../../../src/redkraken/playbooks/graphql/playbook.md
tags: [information_disclosure, constrained, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-02-15T00:00:00Z
bb:category: information_disclosure
bb:outputs: [information_disclosure.excess_field]
bb:triggers_all: [graphql_surface, multiple_test_identities]
bb:skills: [compare-responses, use-identity]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:version: af8bf6afab311cc1efa97193c75d4867b94c2c79f1010f573ed7469eda7829bd
bb:sha256: cdd8dcf6e262f0c1474c927853f6c6f96eb116da2dd1884742f8a70b6b1adf35
sources:
  - id: graphql--api-graphql
    resource: /references/graphql--api-graphql.md
    title: "GraphQL, and the four claims a maintainer keeps confusing"
    author: human:maintainer
---

# Ask whether a GraphQL selection returns fields the caller is not entitled to, by requesting the same selection under two leased Identities and differencing the two stored documents field by field.

## What it concludes about

- `information_disclosure.excess_field`

## When it is selected

A subject carrying every one of these facts:

- `graphql_surface`
- `multiple_test_identities`

Risk `constrained`, effects `read_only`, baseline `stable_session`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `response_invariant` observation(s) from a `variant`
- to `supported`: at least 1 supports `credential_effect` observation(s) from a `control`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `variant`

## Provenance

Written for ticket 49 as the v2 replacement for v1's graphql pack, against the excess-field leaf of the ticket 18 vocabulary; the v1 api-graphql text is attached as a maintainer reference and is not the source of this class.

## Maintainer references

- [api-graphql.md](/references/graphql--api-graphql.md)[^graphql--api-graphql]

[^graphql--api-graphql]: GraphQL, and the four claims a maintainer keeps confusing

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/graphql/playbook.md`](../../../src/redkraken/playbooks/graphql/playbook.md). This concept describes that document and never replaces it.
