---
type: Playbook
title: "identity-lifecycle"
description: "Ask whether a session survives the event that was supposed to end it, by driving one leased session across a logout or a credential change and replaying a request that only a live session answers, and by re-presenting a kept token after further authentications on a Task that leases no Identity."
resource: ../../../src/redkraken/playbooks/identity-lifecycle/playbook.md
tags: [session_handling, constrained, mutates_session]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-03-15T00:00:00Z
bb:category: session_handling
bb:outputs: [session_handling.lifetime]
bb:triggers_all: [cookie_parameter, state_changing_method]
bb:skills: [compare-responses, use-identity]
bb:risk: constrained
bb:effects: mutates_session
bb:baseline: stable_session
bb:version: cb333ad8a436e6a844ea196eb7bb489c48d91dbdc4595637917e6f3d3f00a5f6
bb:sha256: 50a1de5c6a347236e7fe397d542edd7b0ed97304f4996a8a28457595770703d3
---

# Ask whether a session survives the event that was supposed to end it, by driving one leased session across a logout or a credential change and replaying a request that only a live session answers, and by re-presenting a kept token after further authentications on a Task that leases no Identity.

## What it concludes about

- `session_handling.lifetime`

## When it is selected

A subject carrying every one of these facts:

- `cookie_parameter`
- `state_changing_method`

Risk `constrained`, effects `mutates_session`, baseline `stable_session`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `response_invariant` observation(s) from a `variant`
- to `supported`: at least 1 supports `response_invariant` observation(s) from a `control`
- to `supported`: at least 1 supports `response_invariant` observation(s) from a `variant`

## Provenance

Written for ticket 50 as the v2 replacement for v1's identity-lifecycle pack, against the session-lifetime leaf of the ticket 18 vocabulary; v1 shipped a README for this topic and no reference text, so nothing is attached. Rewritten for ticket 101 against the merged technique ledger, which carries three readings for this slug. One frontmatter key moved and it is a repair, not a widening. The three legs asked for credential_effect, which close_test_replay never writes, and every Test below is an equality specification whose actions no differencing assertion names, so the kind each of its arms produces is response_invariant and the old bar was one no run could clear. All three legs now carry that kind, the refuted leg carries the kind its own role carries on supported, and the credential_effect readings the body still takes are filed in the context role beside the bar.

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/identity-lifecycle/playbook.md`](../../../src/redkraken/playbooks/identity-lifecycle/playbook.md). This concept describes that document and never replaces it.
