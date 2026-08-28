---
type: Playbook
title: "nosql-injection"
description: "Ask whether a JSON body's value is passed to a document store as a query fragment rather than as a scalar, by sending the same field once as a string and once as a one-key operator object and differencing the two stored responses."
resource: ../../../src/redkraken/playbooks/nosql-injection/playbook.md
tags: [injection, constrained, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-03-15T00:00:00Z
bb:category: injection
bb:outputs: [injection.query_operator]
bb:triggers_all: [json_request, state_changing_method, tech_document_store]
bb:skills: [compare-responses, use-identity]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:version: 7c8c2818904d5f03be26581ed7e5925dacdb784cf8452ebf65aa4ca653e222a5
bb:sha256: 59b8cd48f0af4145307abb62a6712a8aedd21783bf7c063c385169c64011c769
---

# Ask whether a JSON body's value is passed to a document store as a query fragment rather than as a scalar, by sending the same field once as a string and once as a one-key operator object and differencing the two stored responses.

## What it concludes about

- `injection.query_operator`

## When it is selected

A subject carrying every one of these facts:

- `json_request`
- `state_changing_method`
- `tech_document_store`

Risk `constrained`, effects `read_only`, baseline `stable_session`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `response_invariant` observation(s) from a `variant`
- to `supported`: at least 1 supports `response_invariant` observation(s) from a `control`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `variant`

## Provenance

Written for ticket 53 as the v2 replacement for v1's nosql-injection page, against a new query_operator leaf added by ticket 53 because a document store takes its query as a document and the injected thing is a type rather than a string; no upstream card.

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/nosql-injection/playbook.md`](../../../src/redkraken/playbooks/nosql-injection/playbook.md). This concept describes that document and never replaces it.
