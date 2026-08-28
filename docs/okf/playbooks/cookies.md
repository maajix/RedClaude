---
type: Playbook
title: "cookies"
description: "Ask whether a session cookie is reachable outside the origin it was issued for, by reading the attributes it carries in the browser's own jar and then observing where that cookie is actually attached."
resource: ../../../src/redkraken/playbooks/cookies/playbook.md
tags: [session_handling, constrained, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-03-15T00:00:00Z
bb:category: session_handling
bb:outputs: [session_handling.cookie_scope]
bb:triggers_all: [cookie_parameter, read_method]
bb:skills: [browser-evidence, use-identity]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:version: fbdeeeffc6e3b6a5006bc16865334f5ead6a34823ba9882b6ff99bdd77eda750
bb:sha256: 2f4b70f1795d18d63f74617bc516282210938de2c792bcac7e23609a7c64820e
---

# Ask whether a session cookie is reachable outside the origin it was issued for, by reading the attributes it carries in the browser's own jar and then observing where that cookie is actually attached.

## What it concludes about

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

Written for ticket 50 as the v2 replacement for v1's cookies pack, against the cookie-scope leaf of the ticket 18 vocabulary; v1 shipped a README for this topic and no reference text, so nothing is attached.

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/cookies/playbook.md`](../../../src/redkraken/playbooks/cookies/playbook.md). This concept describes that document and never replaces it.
