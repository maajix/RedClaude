---
type: Playbook
title: "nosql-injection"
description: "Ask whether a value reaches a document store as a query fragment rather than as a scalar, by sending the same field once as a string, once as a one-key operator object and once as a one-key object whose key is not an operator, and differencing the last two."
resource: ../../../src/redkraken/playbooks/nosql-injection/playbook.md
tags: [injection, constrained, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-03-15T00:00:00Z
bb:category: injection
bb:outputs: [injection.query_operator]
bb:triggers_all: [tech_document_store]
bb:triggers_any: [body_parameter, query_parameter]
bb:skills: [compare-responses, use-identity]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:version: c40ac9e72a6ac77e52c476ddae201fa84f01d7594aaf330b8e33e62cb1e59d25
bb:sha256: 32c0e66d54ff5ccf93075112a787920600e053acafe9bb5c1864c2b19260c9be
---

# Ask whether a value reaches a document store as a query fragment rather than as a scalar, by sending the same field once as a string, once as a one-key operator object and once as a one-key object whose key is not an operator, and differencing the last two.

## What it concludes about

- `injection.query_operator`

## When it is selected

A subject carrying every one of these facts:

- `tech_document_store`

and at least one of:

- `body_parameter`
- `query_parameter`

Risk `constrained`, effects `read_only`, baseline `stable_session`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `response_differential` observation(s) from a `variant`
- to `supported`: at least 1 supports `response_invariant` observation(s) from a `control`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `variant`

## Provenance

Written for ticket 53 as the v2 replacement for v1's nosql-injection page, against a new query_operator leaf added by ticket 53 because the injected thing here is a type rather than a string; no upstream card. Rewritten for ticket 101 against the merged ledger, which carries three procedures and one refusal for this slug. Two keys moved. bb:triggers_all narrows to tech_document_store and bb:triggers_any takes body_parameter and query_parameter, because the shipped set demanded json_request and state_changing_method together and so selected for exactly one of the three readings -- the parser-built and regex-anchor readings both ride a query string on a read, and a trigger set that never fires for them hides two thirds of the Playbook. The refuted variant leg moves from response_invariant to response_differential, the kind the supported leg of the same role names, because close_test_replay derives a kind from the specification and one role writes one kind whichever way the reading comes out.

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/nosql-injection/playbook.md`](../../../src/redkraken/playbooks/nosql-injection/playbook.md). This concept describes that document and never replaces it.
