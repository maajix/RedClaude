---
type: Playbook
title: "orm"
description: "Ask whether a query parameter names a stored field or a relation to the ORM that builds the statement, by sending one request with a field the caller was never offered and differencing the response against a request naming a field that does not exist."
resource: ../../../src/redkraken/playbooks/orm/playbook.md
tags: [injection, constrained, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-03-15T00:00:00Z
bb:category: injection
bb:outputs: [injection.query_field]
bb:triggers_all: [authenticated_endpoint, query_parameter, tech_orm]
bb:skills: [compare-responses, use-identity]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:version: fcb36f805ace0a76a8e9363f5b19155d6ef3cbfdd0dda51b054a0ccf07f92503
bb:sha256: cb456b677ac45005b7026cc2eed7f8f20e5f9d2a99d72f5d06aa4c2b549e6593
---

# Ask whether a query parameter names a stored field or a relation to the ORM that builds the statement, by sending one request with a field the caller was never offered and differencing the response against a request naming a field that does not exist.

## What it concludes about

- `injection.query_field`

## When it is selected

A subject carrying every one of these facts:

- `authenticated_endpoint`
- `query_parameter`
- `tech_orm`

Risk `constrained`, effects `read_only`, baseline `stable_session`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `response_invariant` observation(s) from a `variant`
- to `supported`: at least 1 supports `response_invariant` observation(s) from a `control`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `variant`

## Provenance

Written for ticket 53 as the v2 replacement for v1's orm page, against a new query_field leaf added by ticket 53 because an ORM injection changes which column the query names rather than what the query says; no upstream card.

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/orm/playbook.md`](../../../src/redkraken/playbooks/orm/playbook.md). This concept describes that document and never replaces it.
