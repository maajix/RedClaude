---
type: Playbook
title: "oauth"
description: "Ask whether an authorisation server binds the credential it issues to the request that asked for it, by mutating the registered callback, the response encoding, the redeemed code and the state value one arm at a time and differencing each against a control the server must refuse."
resource: ../../../src/redkraken/playbooks/oauth/playbook.md
tags: [session_handling, approval_required, mutates_object]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-03-15T00:00:00Z
bb:category: session_handling
bb:outputs: [session_handling.fixation]
bb:triggers_all: [query_parameter, tech_oauth]
bb:skills: [browser-evidence, compare-responses, enumerate-surface, use-identity]
bb:risk: approval_required
bb:effects: mutates_object
bb:baseline: none
bb:version: 08b59967531540462f86a73ea22796f2cc089956b3085a8d51bd55a876f3822c
bb:sha256: 424a0ce69e72fe32762b781fab85296080d3a962da46fc305e53ab48a26fcc35
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

# Ask whether an authorisation server binds the credential it issues to the request that asked for it, by mutating the registered callback, the response encoding, the redeemed code and the state value one arm at a time and differencing each against a control the server must refuse.

## What it concludes about

- `session_handling.fixation`

## When it is selected

A subject carrying every one of these facts:

- `query_parameter`
- `tech_oauth`

Risk `approval_required`, effects `mutates_object`, baseline `none`.

## Skills it loads

- [browser-evidence](/skills/browser-evidence.md)
- [compare-responses](/skills/compare-responses.md)
- [enumerate-surface](/skills/enumerate-surface.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `response_differential` observation(s) from a `variant`
- to `supported`: at least 1 supports `credential_effect` observation(s) from a `control`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `variant`

## Provenance

Written for ticket 50 as the v2 replacement for v1's oauth pack, against the session-fixation leaf of the ticket 18 vocabulary; two v1 texts are attached as maintainer references and both describe the callback delivery this Playbook performs. Rewritten for ticket 101 against the merged ledger, which carries eight readings, one lead and two refusals for this slug. Three keys moved. bb:effects rises from mutates_session to mutates_object because section 2 registers a client on the subject and a Playbook that writes state must say so; bb:risk stays approval_required, which is above the floor that effects asks for. bb:skills gains compare-responses and enumerate-surface, both already held by the role that executes this text. Both variant rows move from state_change to response_differential, the kind every grading section's differing assertion writes, because the only state_change the ledger records for this slug sits in the observation_only lead section 6 carries, which reaches no Finding.

## Maintainer references

- [oauth2-attack-via-google-oauth2-playground.md](/references/oauth--oauth2-attack-via-google-oauth2-playground.md)[^oauth--oauth2-attack-via-google-oauth2-playground]
- [oauth2.md](/references/oauth--oauth2.md)[^oauth--oauth2]

[^oauth--oauth2-attack-via-google-oauth2-playground]: The playground technique, and the line it sits on
[^oauth--oauth2]: OAuth 2: the bindings, and which half of the flow is in scope

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/oauth/playbook.md`](../../../src/redkraken/playbooks/oauth/playbook.md). This concept describes that document and never replaces it.
