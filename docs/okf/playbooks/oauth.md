---
type: Playbook
title: "oauth"
description: "Ask whether an authorisation callback binds the code it receives to the browser that started the flow, by completing one flow, holding its callback, and delivering it to a second browser that never asked."
resource: ../../../src/redkraken/playbooks/oauth/playbook.md
tags: [session_handling, approval_required, mutates_session]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-03-15T00:00:00Z
bb:category: session_handling
bb:outputs: [session_handling.fixation]
bb:triggers_all: [query_parameter, tech_oauth]
bb:skills: [browser-evidence, use-identity]
bb:risk: approval_required
bb:effects: mutates_session
bb:baseline: none
bb:version: 48c6f4393e6b531e20bbd9a7ddfb453d267be00667d3913cdeb208ad2d5e8af0
bb:sha256: ce6862413632fe459aaf257de9b5f325f2fde44c06c33bfa026abe2a09d9d245
sources:
  - id: oauth--oauth2-attack-via-google-oauth2-playground
    resource: /references/oauth--oauth2-attack-via-google-oauth2-playground.md
    title: "The playground technique, and the line it sits on"
    author: human:maintainer
  - id: oauth--oauth2
    resource: /references/oauth--oauth2.md
    title: "OAuth 2: the bindings, and which half of the flow is in scope"
    author: human:maintainer
---

# Ask whether an authorisation callback binds the code it receives to the browser that started the flow, by completing one flow, holding its callback, and delivering it to a second browser that never asked.

## What it concludes about

- `session_handling.fixation`

## When it is selected

A subject carrying every one of these facts:

- `query_parameter`
- `tech_oauth`

Risk `approval_required`, effects `mutates_session`, baseline `none`.

## Skills it loads

- [browser-evidence](/skills/browser-evidence.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `response_invariant` observation(s) from a `variant`
- to `supported`: at least 1 supports `credential_effect` observation(s) from a `control`
- to `supported`: at least 1 supports `state_change` observation(s) from a `variant`

## Provenance

Written for ticket 50 as the v2 replacement for v1's oauth pack, against the session-fixation leaf of the ticket 18 vocabulary; two v1 texts are attached as maintainer references and both describe the callback delivery this Playbook performs.

## Maintainer references

- [oauth2-attack-via-google-oauth2-playground.md](/references/oauth--oauth2-attack-via-google-oauth2-playground.md)[^oauth--oauth2-attack-via-google-oauth2-playground]
- [oauth2.md](/references/oauth--oauth2.md)[^oauth--oauth2]

[^oauth--oauth2-attack-via-google-oauth2-playground]: The playground technique, and the line it sits on
[^oauth--oauth2]: OAuth 2: the bindings, and which half of the flow is in scope

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/oauth/playbook.md`](../../../src/redkraken/playbooks/oauth/playbook.md). This concept describes that document and never replaces it.
