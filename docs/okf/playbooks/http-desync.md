---
type: Playbook
title: "http-desync"
description: "Ask what a deployment advertises about its own transport and whether the advertisement is the deployment's policy or one fleet member's, by reading the subject twice unchanged and differencing the pair against a route on the same origin the front end serves differently."
resource: ../../../src/redkraken/playbooks/http-desync/playbook.md
tags: [transport, constrained, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-05-15T00:00:00Z
bb:category: transport
bb:outputs: [transport.header_policy]
bb:triggers_all: [read_method, spa_surface, tech_edge_proxy]
bb:skills: [compare-responses]
bb:risk: constrained
bb:effects: read_only
bb:baseline: none
bb:version: aa8147bb07ad841e5fba1bfb4e51198996aba3f749c6c3f850f6ab94fffbdf74
bb:sha256: e80023c5beabddf9b8129ee5c927baa4747fe533368dc20ae92e26eb58dc6ba1
sources:
  - id: http-desync--http-attacks-http-2-downgrading
    resource: /references/http-desync--http-attacks-http-2-downgrading.md
    title: "HTTP/2 downgrading: the one half that survives, and where it went"
    author: human:maintainer
  - id: http-desync--http-attacks-request-smuggling-and-http-desync
    resource: /references/http-desync--http-attacks-request-smuggling-and-http-desync.md
    title: "Request smuggling and desync: refused, and the refusal is in the schema"
    author: human:maintainer
  - id: http-desync--proxy-tunnels
    resource: /references/http-desync--proxy-tunnels.md
    title: "Proxy tunnels: refused, and the reason is the egress rule rather than a technique"
    author: human:maintainer
---

# Ask what a deployment advertises about its own transport and whether the advertisement is the deployment's policy or one fleet member's, by reading the subject twice unchanged and differencing the pair against a route on the same origin the front end serves differently.

## What it concludes about

- `transport.header_policy`

## When it is selected

A subject carrying every one of these facts:

- `read_method`
- `spa_surface`
- `tech_edge_proxy`

Risk `constrained`, effects `read_only`, baseline `none`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `response_differential` observation(s) from a `variant`
- to `supported`: at least 1 supports `response_invariant` observation(s) from a `control`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `variant`

## Provenance

Written for ticket 56 as the v2 replacement for v1's http-desync pack against the tls_configuration leaf 018 already named; the pack's three pages are attached as maintainer references and its smuggling, desync, coalescing and tunnelling techniques are refused by section 4, because 025 records request framing as unmakeable and enforces that in a trigger. Rewritten for ticket 101 against the merged ledger; the one reading that executes is a header-policy reading, so bb:outputs gained transport.header_policy, the evidence rows moved off transport_parameters_observed and the roles swapped -- the repeat is the control, the sibling the variant. That move was right about the writer and wrong about the class -- on a probe_only claim transport_evidence_guard admits that kind and no other, so the tls_configuration half was unsatisfiable. Ticket 233 took transport.tls_configuration off bb:outputs instead, because one bar is read against every class a Playbook names; the reading that would support it is owed to 237.

## Maintainer references

- [http-attacks-http-2-downgrading.md](/references/http-desync--http-attacks-http-2-downgrading.md)[^http-desync--http-attacks-http-2-downgrading]
- [http-attacks-request-smuggling-and-http-desync.md](/references/http-desync--http-attacks-request-smuggling-and-http-desync.md)[^http-desync--http-attacks-request-smuggling-and-http-desync]
- [proxy-tunnels.md](/references/http-desync--proxy-tunnels.md)[^http-desync--proxy-tunnels]

[^http-desync--http-attacks-http-2-downgrading]: HTTP/2 downgrading: the one half that survives, and where it went
[^http-desync--http-attacks-request-smuggling-and-http-desync]: Request smuggling and desync: refused, and the refusal is in the schema
[^http-desync--proxy-tunnels]: Proxy tunnels: refused, and the reason is the egress rule rather than a technique

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/http-desync/playbook.md`](../../../src/redkraken/playbooks/http-desync/playbook.md). This concept describes that document and never replaces it.
