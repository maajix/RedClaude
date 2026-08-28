---
type: Playbook
title: "secrets"
description: "Ask whether a string of credential shape in a served document is worth anything, by taking every candidate out of the stored document, presenting each once to the route it names, and comparing what the target said against what it says to a request carrying no credential at all."
resource: ../../../src/redkraken/playbooks/secrets/playbook.md
tags: [information_disclosure, constrained, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-04-15T00:00:00Z
bb:category: information_disclosure
bb:outputs: [information_disclosure.credential_material]
bb:triggers_all: [embedded_document, read_method, spa_surface]
bb:skills: [compare-responses, handle-untrusted-content]
bb:risk: constrained
bb:effects: read_only
bb:baseline: none
bb:version: 7281778511516cdb2304881d23cdc85e27a0c5196d4a5e16c8ed3d425b9e976b
bb:sha256: a9e423196f35f7e5f846baeaf1c4fc409b3edf5b5b843e4a25704f336f4c4820
---

# Ask whether a string of credential shape in a served document is worth anything, by taking every candidate out of the stored document, presenting each once to the route it names, and comparing what the target said against what it says to a request carrying no credential at all.

## What it concludes about

- `information_disclosure.credential_material`

## When it is selected

A subject carrying every one of these facts:

- `embedded_document`
- `read_method`
- `spa_surface`

Risk `constrained`, effects `read_only`, baseline `none`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)
- [handle-untrusted-content](/skills/handle-untrusted-content.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `credential_effect` observation(s) from a `variant`
- to `supported`: at least 1 supports `content_match` observation(s) from a `control`
- to `supported`: at least 1 supports `credential_effect` observation(s) from a `variant`

## Provenance

Written for ticket 54 as the v2 replacement for v1's secrets page against a new credential_material leaf added by ticket 54; the v1 page carried no attachments, and its advice to enumerate what a found key reaches is refused by step 6.

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/secrets/playbook.md`](../../../src/redkraken/playbooks/secrets/playbook.md). This concept describes that document and never replaces it.
