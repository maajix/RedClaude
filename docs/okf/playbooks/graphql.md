---
type: Playbook
title: "graphql"
description: "Ask whether a GraphQL endpoint answers a caller more than the caller is entitled to, by sending one application operation as two people and closing on a single-Identity pair that differences the disputed selection against the same selection naming an object that does not exist."
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
bb:version: 837fa46d50f9ba0f3b26c075b25874c80128a1f3350923051f34c2fe9fd0552b
bb:sha256: b42bcea4f537027985c704fce79bc60a1bdc992a9854c1caaf077297dc478ee9
sources:
  - id: graphql--api-graphql
    resource: /references/graphql--api-graphql.md
    title: "GraphQL, and the four claims a maintainer keeps confusing"
    author: human:maintainer
---

# Ask whether a GraphQL endpoint answers a caller more than the caller is entitled to, by sending one application operation as two people and closing on a single-Identity pair that differences the disputed selection against the same selection naming an object that does not exist.

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

- to `refuted`: at least 1 refutes `response_differential` observation(s) from a `variant`
- to `supported`: at least 1 supports `credential_effect` observation(s) from a `control`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `variant`

## Provenance

Written for ticket 49 as the v2 replacement for v1's graphql pack, against the excess-field leaf of the ticket 18 vocabulary; the v1 api-graphql text is attached as a maintainer reference and is not the source of this class. Rewritten for ticket 101 against the merged ledger, which carries three procedures, one lead and two refusals for this slug. Two keys moved. The refuted variant leg moves from response_invariant to response_differential, the kind the supported leg of the same role names, because close_test_replay derives a kind from the specification rather than from the outcome and a refuted leg naming a second kind is one nothing writes. The description now names the single-Identity closing pair, because the cross-Identity comparison the shipped text was written around cannot itself settle a Test -- one replay run leases one Identity for its length -- and a reader following the old description would build a specification the run refuses.

## Maintainer references

- [api-graphql.md](/references/graphql--api-graphql.md)[^graphql--api-graphql]

[^graphql--api-graphql]: GraphQL, and the four claims a maintainer keeps confusing

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/graphql/playbook.md`](../../../src/redkraken/playbooks/graphql/playbook.md). This concept describes that document and never replaces it.
