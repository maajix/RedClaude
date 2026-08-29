---
type: Playbook
title: "exceptional-conditions"
description: "Ask whether a route's failure describes the process that had it rather than the input that caused it, and whether the same route tells an identifier that exists apart from one that does not, by moving one value at a time across three arms and closing on a Test whose own assertions carry the difference."
resource: ../../../src/redkraken/playbooks/exceptional-conditions/playbook.md
tags: [information_disclosure, constrained, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-04-15T00:00:00Z
bb:category: information_disclosure
bb:outputs: [information_disclosure.error_detail, information_disclosure.identifier_oracle]
bb:triggers_all: [authenticated_endpoint, quantity_valued_parameter, read_method]
bb:skills: [compare-responses, enumerate-surface, use-identity]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:version: 723d1ed499834295a7db6447d08eba5d5a4e1b42009f33bb5ac5af52ce0a456c
bb:sha256: 3bea7a47e86d94c4cc4781212c35f17d5bae9b92dd93a374f309ff26b53a0970
---

# Ask whether a route's failure describes the process that had it rather than the input that caused it, and whether the same route tells an identifier that exists apart from one that does not, by moving one value at a time across three arms and closing on a Test whose own assertions carry the difference.

## What it concludes about

- `information_disclosure.error_detail`
- `information_disclosure.identifier_oracle`

## When it is selected

A subject carrying every one of these facts:

- `authenticated_endpoint`
- `quantity_valued_parameter`
- `read_method`

Risk `constrained`, effects `read_only`, baseline `stable_session`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)
- [enumerate-surface](/skills/enumerate-surface.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `error_detail` observation(s) from a `variant`
- to `supported`: at least 1 supports `response_invariant` observation(s) from a `control`
- to `supported`: at least 1 supports `error_detail` observation(s) from a `variant`

## Provenance

Written for ticket 54 as the v2 replacement for v1's exceptional-conditions page against the error_detail leaf of the ticket 18 vocabulary, and rewritten for ticket 101 against the merged ledger's nine readings for this slug. The identifier_oracle leaf is added as a second output under operator decision D3, which puts the missing emitter inside this ticket; bb:triggers_all is unchanged, so the pre-auth readings are named for the surface they need rather than selected by it. Effects stay read_only and risk stays constrained, which is why the two readings that change the target are parked for a person before they run.

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/exceptional-conditions/playbook.md`](../../../src/redkraken/playbooks/exceptional-conditions/playbook.md). This concept describes that document and never replaces it.
