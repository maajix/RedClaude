---
type: Playbook
title: "information-disclosure"
description: "Ask whether a route returns fields its own published contract never declared, by storing the contract and the response as Artifacts and differencing the two sets of field names in both directions, so that the names found and the names missing are read at the same time."
resource: ../../../src/redkraken/playbooks/information-disclosure/playbook.md
tags: [information_disclosure, constrained, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-04-15T00:00:00Z
bb:category: information_disclosure
bb:outputs: [information_disclosure.undeclared_field]
bb:triggers_all: [authenticated_endpoint, read_method, tech_openapi]
bb:skills: [compare-responses, handle-untrusted-content, use-identity]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:version: b4e4ca78ea1a7e65baf3fa6c30f6526eb9d81f4a087fd31e85634d3a28e32b45
bb:sha256: fd6c61f33029fd01f8f52cf9cef9fa9fbc4f073a8d3947743c4faf8a82bbf023
---

# Ask whether a route returns fields its own published contract never declared, by storing the contract and the response as Artifacts and differencing the two sets of field names in both directions, so that the names found and the names missing are read at the same time.

## What it concludes about

- `information_disclosure.undeclared_field`

## When it is selected

A subject carrying every one of these facts:

- `authenticated_endpoint`
- `read_method`
- `tech_openapi`

Risk `constrained`, effects `read_only`, baseline `stable_session`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)
- [handle-untrusted-content](/skills/handle-untrusted-content.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `content_match` observation(s) from a `variant`
- to `supported`: at least 1 supports `content_match` observation(s) from a `control`
- to `supported`: at least 1 supports `content_match` observation(s) from a `variant`

## Provenance

Written for ticket 54 as the v2 replacement for v1's information-disclosure page against a new undeclared_field leaf added by ticket 54; the v1 page carried no attachments, and its advice to harvest whatever the extra fields contain is refused by step 7.

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/information-disclosure/playbook.md`](../../../src/redkraken/playbooks/information-disclosure/playbook.md). This concept describes that document and never replaces it.
