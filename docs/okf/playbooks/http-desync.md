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
bb:outputs: [transport.header_policy, transport.tls_configuration]
bb:triggers_all: [read_method, spa_surface, tech_edge_proxy]
bb:skills: [compare-responses]
bb:risk: constrained
bb:effects: read_only
bb:baseline: none
bb:version: 654d8598e80b7b5e5fe1fc9526b1daaf06dfc05b9a6da61a0a4341c3520c0c15
bb:sha256: 60b1df9528d191bc601b20221f2fad3e82fcaa9f503cb559c0b9af1db270aeff
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
- `transport.tls_configuration`

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

Written for ticket 56 as the v2 replacement for v1's http-desync pack against the tls_configuration leaf 018 already named; the pack's three pages are attached as maintainer references and its smuggling, desync, coalescing and tunnelling techniques are refused by the last section, because 025 records request framing as unmakeable behind the interception proxy and enforces that refusal in a trigger. Rewritten for ticket 101 against the merged technique ledger, which holds one executable reading, two blocked ones and two refusals for this slug. The one that executes is a header-policy reading, and bb:outputs gains transport.header_policy under D3 so that this Playbook has a step its own harness can perform -- the alternative leaves it describing only readings the harness refuses. The evidence rows move off transport_parameters_observed, which the ledger established has no agent-reachable writer by any path. The repair swapped the roles -- the identical repeat is the control, the differing sibling the variant.

## Maintainer references

- [http-attacks-http-2-downgrading.md](/references/http-desync--http-attacks-http-2-downgrading.md)[^http-desync--http-attacks-http-2-downgrading]
- [http-attacks-request-smuggling-and-http-desync.md](/references/http-desync--http-attacks-request-smuggling-and-http-desync.md)[^http-desync--http-attacks-request-smuggling-and-http-desync]
- [proxy-tunnels.md](/references/http-desync--proxy-tunnels.md)[^http-desync--proxy-tunnels]

[^http-desync--http-attacks-http-2-downgrading]: HTTP/2 downgrading: the one half that survives, and where it went
[^http-desync--http-attacks-request-smuggling-and-http-desync]: Request smuggling and desync: refused, and the refusal is in the schema
[^http-desync--proxy-tunnels]: Proxy tunnels: refused, and the reason is the egress rule rather than a technique

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/http-desync/playbook.md`](../../../src/redkraken/playbooks/http-desync/playbook.md). This concept describes that document and never replaces it.
