---
type: Playbook
title: "information-disclosure"
description: "Ask whether a route returns fields its own published contract never declared, by differencing the two sets of field names in both directions over stored Artifacts, and then whether the declared shape is only the narrowest thing the route will hand back, by widening the projection, naming a parameter the contract omits, asking the route for a second serialization of itself, and asking a server function to stringify its own argument."
resource: ../../../src/redkraken/playbooks/information-disclosure/playbook.md
tags: [information_disclosure, constrained, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-04-15T00:00:00Z
bb:category: information_disclosure
bb:outputs: [information_disclosure.undeclared_field]
bb:triggers_all: [authenticated_endpoint, read_method, tech_openapi]
bb:skills: [compare-responses, enumerate-surface, handle-untrusted-content, use-identity]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:version: f27599a8a0848bab8efba55abcb34b07169804a02b08fd0209d90b657c1c04c0
bb:sha256: 75bc55d4f4575b1e7e887c40fcf85b2b50366684348e1a0cca57b1f6f8bfcaad
---

# Ask whether a route returns fields its own published contract never declared, by differencing the two sets of field names in both directions over stored Artifacts, and then whether the declared shape is only the narrowest thing the route will hand back, by widening the projection, naming a parameter the contract omits, asking the route for a second serialization of itself, and asking a server function to stringify its own argument.

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
- [enumerate-surface](/skills/enumerate-surface.md)
- [handle-untrusted-content](/skills/handle-untrusted-content.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `content_match` observation(s) from a `variant`
- to `supported`: at least 1 supports `content_match` observation(s) from a `control`
- to `supported`: at least 1 supports `content_match` observation(s) from a `variant`

## Provenance

Written for ticket 54 as the v2 replacement for v1's information-disclosure page against a new undeclared_field leaf added by ticket 54; the v1 page carried no attachments, and its advice to harvest whatever the extra fields contain is refused by the closing section. Rewritten for ticket 101 against the merged ledger, which carries five readings and one blocked family for this slug; four readings are new, one of them the second-serialization hand-off ticket 101 named as reachable and unused, and the shipped prose never named the tool run its own content_match bar requires. One key moved -- enumerate-surface is added, because section 3 harvests candidate names out of the served bundle with js_routes and js_parse.

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/information-disclosure/playbook.md`](../../../src/redkraken/playbooks/information-disclosure/playbook.md). This concept describes that document and never replaces it.
