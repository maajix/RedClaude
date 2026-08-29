---
type: Playbook
title: "cookies"
description: "Ask which of two readers takes a Cookie header's value, by sending one header this reading authored under a second encoding and then one name stated twice, each differenced against an inert arm of the same shape, and separately read the browser's own jar for the scope the session cookie was actually given."
resource: ../../../src/redkraken/playbooks/cookies/playbook.md
tags: [session_handling, constrained, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-03-15T00:00:00Z
bb:category: session_handling
bb:outputs: [session_handling.cookie_parsing, session_handling.cookie_scope]
bb:triggers_all: [cookie_parameter, read_method]
bb:skills: [browser-evidence, use-identity]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:version: 60abbeedfa95b6e6886560ca43ffdead75c285355ec1e7e24c820a5a9a0e001a
bb:sha256: a9443adf149160bc10e363853f85df5769124d93e05194d5afe1de1deb2234c4
---

# Ask which of two readers takes a Cookie header's value, by sending one header this reading authored under a second encoding and then one name stated twice, each differenced against an inert arm of the same shape, and separately read the browser's own jar for the scope the session cookie was actually given.

## What it concludes about

- `session_handling.cookie_parsing`
- `session_handling.cookie_scope`

## When it is selected

A subject carrying every one of these facts:

- `cookie_parameter`
- `read_method`

Risk `constrained`, effects `read_only`, baseline `stable_session`.

## Skills it loads

- [browser-evidence](/skills/browser-evidence.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `response_differential` observation(s) from a `variant`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `control`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `variant`

## Provenance

Written for ticket 50 as the v2 replacement for v1's cookies pack, against the cookie-scope leaf of the ticket 18 vocabulary; v1 shipped a README for this topic and no reference text, so nothing is attached. Rewritten for ticket 101 against the merged ledger, which holds two readings that settle a claim, two that stop at an Observation and four refusals for this slug. One key moved. session_handling.cookie_parsing joins bb:outputs, because both settling readings are parsing readings and that class shipped with no emitter at all. The evidence bar is unchanged.

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/cookies/playbook.md`](../../../src/redkraken/playbooks/cookies/playbook.md). This concept describes that document and never replaces it.
