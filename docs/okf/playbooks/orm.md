---
type: Playbook
title: "orm"
description: "Ask which column, relation or comparison the caller chose, by sending one query parameter as a name the interface offers, as a real name it never offered, and as a fictional name of the same shape, and reading which pair the query builder tells apart."
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
bb:version: 8afb7a093765183abe6144bbd69f103cf9efaeac9b1f7896ba8c06f54df93c82
bb:sha256: 4d6ef4c89f84c03932ec9ebde1f0236f5ed9c11f79e75402d9e223513bbc6d74
---

# Ask which column, relation or comparison the caller chose, by sending one query parameter as a name the interface offers, as a real name it never offered, and as a fictional name of the same shape, and reading which pair the query builder tells apart.

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

- to `refuted`: at least 1 refutes `response_differential` observation(s) from a `variant`
- to `supported`: at least 1 supports `response_invariant` observation(s) from a `control`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `variant`

## Provenance

Written for ticket 53 as the v2 replacement for v1's orm page, against a new query_field leaf added by ticket 53 because an ORM injection changes which column the query names rather than what the query says; no upstream card. Rewritten for ticket 101 against the merged ledger, which carries four procedures and one refusal for this slug, and every procedure closes a Test because the whole differential is one parameter value in the request line. One key moved. The refuted variant leg moves from response_invariant to response_differential, the kind the supported leg of the same role names, because close_test_replay derives a kind from the specification rather than from the outcome, so one role writes one kind whichever way the reading comes out and a refuted leg naming a second kind is a leg nothing can ever write. The control role keeps response_invariant, which the unchanged repeat produces where sections 2 and 3 now plan that repeat as a control action rather than as a second baseline send.

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/orm/playbook.md`](../../../src/redkraken/playbooks/orm/playbook.md). This concept describes that document and never replaces it.
