---
type: Playbook
title: "exceptional-conditions"
description: "Ask whether a route's failures describe the process that had them, by sending two arms whose values violate a parameter's type in two different ways beside one value the route's own rule rejects, and differencing the two failures against each other and against a baseline that was itself invariant."
resource: ../../../src/redkraken/playbooks/exceptional-conditions/playbook.md
tags: [information_disclosure, constrained, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-04-15T00:00:00Z
bb:category: information_disclosure
bb:outputs: [information_disclosure.error_detail]
bb:triggers_all: [authenticated_endpoint, quantity_valued_parameter, read_method]
bb:skills: [compare-responses, use-identity]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:version: d4644ed68b3f928f0eb639971e6102c62abcb8693d178eed5e5186057b1caf7f
bb:sha256: c6674e7bd53eb17c264f287ab31d9aa10b9ba44bf90728c513ecd2e0fc5dbaad
---

# Ask whether a route's failures describe the process that had them, by sending two arms whose values violate a parameter's type in two different ways beside one value the route's own rule rejects, and differencing the two failures against each other and against a baseline that was itself invariant.

## What it concludes about

- `information_disclosure.error_detail`

## When it is selected

A subject carrying every one of these facts:

- `authenticated_endpoint`
- `quantity_valued_parameter`
- `read_method`

Risk `constrained`, effects `read_only`, baseline `stable_session`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `response_invariant` observation(s) from a `variant`
- to `supported`: at least 1 supports `response_invariant` observation(s) from a `control`
- to `supported`: at least 1 supports `error_detail` observation(s) from a `variant`

## Provenance

Written for ticket 54 as the v2 replacement for v1's exceptional-conditions page against the error_detail leaf of the ticket 18 vocabulary; the v1 page carried no attachments, and its fuzzing lists and its overlong-input advice are refused by step 7.

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/exceptional-conditions/playbook.md`](../../../src/redkraken/playbooks/exceptional-conditions/playbook.md). This concept describes that document and never replaces it.
