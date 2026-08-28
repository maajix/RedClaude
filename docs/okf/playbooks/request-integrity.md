---
type: Playbook
title: "request-integrity"
description: "Ask whether a response that only exists because the caller holds a session is made readable to an origin the application never meant to trust, by sending the same authenticated read three times under three origins and comparing the two headers that decide who may read the answer."
resource: ../../../src/redkraken/playbooks/request-integrity/playbook.md
tags: [session_handling, constrained, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-05-15T00:00:00Z
bb:category: session_handling
bb:outputs: [session_handling.cross_origin_read]
bb:triggers_all: [authenticated_endpoint, header_parameter, read_method]
bb:skills: [compare-responses, use-identity]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:version: 88f5cdb95d370edb5708d326402a63e41de2b094c2169e65e9613220d1804e92
bb:sha256: a4d76f94d7805718cc34a47e24957f69d5cff144bb0364d7e1ade99a5ee8474f
sources:
  - id: request-integrity--cors
    resource: /references/request-integrity--cors.md
    title: "CORS: kept almost whole, and narrowed to the pair of headers that decides"
    author: human:maintainer
  - id: request-integrity--csrf
    resource: /references/request-integrity--csrf.md
    title: "CSRF: the class survives, the proof does not, and neither lives here"
    author: human:maintainer
---

# Ask whether a response that only exists because the caller holds a session is made readable to an origin the application never meant to trust, by sending the same authenticated read three times under three origins and comparing the two headers that decide who may read the answer.

## What it concludes about

- `session_handling.cross_origin_read`

## When it is selected

A subject carrying every one of these facts:

- `authenticated_endpoint`
- `header_parameter`
- `read_method`

Risk `constrained`, effects `read_only`, baseline `stable_session`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `response_invariant` observation(s) from a `variant`
- to `supported`: at least 1 supports `response_invariant` observation(s) from a `control`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `variant`

## Provenance

Written for ticket 56 as the v2 replacement for v1's request-integrity pack against a new cross_origin_read leaf added by ticket 56; the pack's two pages are attached as maintainer references, its forged-write proofs are refused by step 7, and the write half of its subject stays 018's session_handling.csrf, which `realtime` outputs.

## Maintainer references

- [cors.md](/references/request-integrity--cors.md)[^request-integrity--cors]
- [csrf.md](/references/request-integrity--csrf.md)[^request-integrity--csrf]

[^request-integrity--cors]: CORS: kept almost whole, and narrowed to the pair of headers that decides
[^request-integrity--csrf]: CSRF: the class survives, the proof does not, and neither lives here

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/request-integrity/playbook.md`](../../../src/redkraken/playbooks/request-integrity/playbook.md). This concept describes that document and never replaces it.
