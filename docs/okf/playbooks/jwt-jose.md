---
type: Playbook
title: "jwt-jose"
description: "Ask whether anything reads the part of a token that says what it is for, by presenting one genuine token at a second audience and a second scope, by editing one claim under a preserved signature, and by reading which failure the server reaches first when the key identifier or the payload is altered under a signature that is deliberately wrong."
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
bb:version: d1e3e3ae749c531491455c9f477f8afd5f585e5ffaf4014f99d3ff8dfa90af04
bb:sha256: fd17cb10c27d42555467594122239b0b348be267fed347804a34b913286f4493
sources:
  - id: jwt-jose--jwt
    resource: /references/jwt-jose--jwt.md
    title: "JWT and JOSE: the header edits, and why decoding one is not a finding"
    author: human:maintainer
---

# Ask whether anything reads the part of a token that says what it is for, by presenting one genuine token at a second audience and a second scope, by editing one claim under a preserved signature, and by reading which failure the server reaches first when the key identifier or the payload is altered under a signature that is deliberately wrong.

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

- to `refuted`: at least 1 refutes `credential_effect` observation(s) from a `variant`
- to `supported`: at least 1 supports `credential_effect` observation(s) from a `control`
- to `supported`: at least 1 supports `credential_effect` observation(s) from a `variant`

## Provenance

Written for ticket 50 as the v2 replacement for v1's jwt-jose pack, against the token-scope leaf of the ticket 18 vocabulary; the v1 jwt text is attached as a maintainer reference and supplies the header and claim edits this Playbook sends. Rewritten for ticket 101 against the merged ledger, which carries eight readings, one lead, one block and one refusal for this slug. One key moved. The refuted variant row leaves response_invariant for credential_effect, the kind the supported row of that same role names, because close_test_replay derives the kind from the specification and one role writes one kind whichever way the reading goes. bb:effects stays read_only and bb:risk stays constrained; the one section that mints a credential does so for this run's own account under a registration the Program supplied, and parks for a person where it has neither. Ticket 211 is what turned six of these readings from Observations into Tests, because an action now states the header the token rides in.

## Maintainer references

- [jwt.md](/references/jwt-jose--jwt.md)[^jwt-jose--jwt]

[^jwt-jose--jwt]: JWT and JOSE: the header edits, and why decoding one is not a finding

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/jwt-jose/playbook.md`](../../../src/redkraken/playbooks/jwt-jose/playbook.md). This concept describes that document and never replaces it.
