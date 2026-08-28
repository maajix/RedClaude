---
type: Playbook
title: "jwt-jose"
description: "Ask whether a token is honoured beyond what it was issued for, by presenting one real token to a second audience, a second scope and a second key and reading which of those the server still answers as the caller."
resource: ../../../src/redkraken/playbooks/jwt-jose/playbook.md
tags: [authorization, constrained, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-03-15T00:00:00Z
bb:category: authorization
bb:outputs: [authorization.token_scope]
bb:triggers_all: [authenticated_endpoint, tech_jwt]
bb:skills: [compare-responses, use-identity]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:version: 55692f83eb499f2deea492c41a4bf0098b0a1cbfbc1b6531a7798d9cacc6b5fc
bb:sha256: a045ca99dab9c9144eb0071649842e2221edb038cde30fd71a4b5aebf77d6576
sources:
  - id: jwt-jose--jwt
    resource: /references/jwt-jose--jwt.md
    title: "JWT and JOSE: the header edits, and why decoding one is not a finding"
    author: human:maintainer
---

# Ask whether a token is honoured beyond what it was issued for, by presenting one real token to a second audience, a second scope and a second key and reading which of those the server still answers as the caller.

## What it concludes about

- `authorization.token_scope`

## When it is selected

A subject carrying every one of these facts:

- `authenticated_endpoint`
- `tech_jwt`

Risk `constrained`, effects `read_only`, baseline `stable_session`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `response_invariant` observation(s) from a `variant`
- to `supported`: at least 1 supports `credential_effect` observation(s) from a `control`
- to `supported`: at least 1 supports `credential_effect` observation(s) from a `variant`

## Provenance

Written for ticket 50 as the v2 replacement for v1's jwt-jose pack, against the token-scope leaf of the ticket 18 vocabulary; the v1 jwt text is attached as a maintainer reference and supplies the header and claim edits this Playbook sends.

## Maintainer references

- [jwt.md](/references/jwt-jose--jwt.md)[^jwt-jose--jwt]

[^jwt-jose--jwt]: JWT and JOSE: the header edits, and why decoding one is not a finding

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/jwt-jose/playbook.md`](../../../src/redkraken/playbooks/jwt-jose/playbook.md). This concept describes that document and never replaces it.
