---
type: Playbook
title: "request-integrity"
description: "Ask who is allowed to read an answer that only exists because the caller holds a session, by sending the same authenticated read under a trusted origin, an untrusted one and a near miss and reading the two headers that decide it, by asking whether the allow list recognises names the scope never published, and by asking whether the route will hand the same answer to a script tag."
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
bb:version: 131b4fc4485f9c2eb554198659e11e44a3b70c8d63b898260d361ed50708df06
bb:sha256: 5357136785bbf08fbdfe79884d586613b0240170a289cb43ec409a13fd70aaad
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

# Ask who is allowed to read an answer that only exists because the caller holds a session, by sending the same authenticated read under a trusted origin, an untrusted one and a near miss and reading the two headers that decide it, by asking whether the allow list recognises names the scope never published, and by asking whether the route will hand the same answer to a script tag.

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

- to `refuted`: at least 1 refutes `response_differential` observation(s) from a `variant`
- to `supported`: at least 1 supports `response_invariant` observation(s) from a `control`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `variant`

## Provenance

Written for ticket 56 as the v2 replacement for v1's request-integrity pack against a new cross_origin_read leaf added by ticket 56; the pack's two pages are attached as maintainer references, its forged-write proofs are refused by the closing section, and the write half of its subject stays the csrf leaf that realtime outputs. Rewritten for ticket 101 against the merged ledger, which carries five procedures, one lead and one refusal. One key moved. The refuted variant row leaves response_invariant for response_differential, the kind the supported row of that same role names, because close_test_replay derives the kind from the specification and one role writes one kind whichever way the reading goes. Every closing assertion names its variant against the baseline and leaves the control named by no differing assertion, which is what keeps the declared control row an invariant. Ticket 211 turned four of these readings from Observations into procedures, because an action now states the header it varies.

## Maintainer references

- [cors.md](/references/request-integrity--cors.md)[^request-integrity--cors]
- [csrf.md](/references/request-integrity--csrf.md)[^request-integrity--csrf]

[^request-integrity--cors]: CORS: kept almost whole, and narrowed to the pair of headers that decides
[^request-integrity--csrf]: CSRF: the class survives, the proof does not, and neither lives here

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/request-integrity/playbook.md`](../../../src/redkraken/playbooks/request-integrity/playbook.md). This concept describes that document and never replaces it.
