---
type: Playbook
title: "secrets"
description: "Ask whether a string of credential shape in a served document is worth anything, by grounding the candidate list with an offline reader rather than by eye and then presenting each candidate once to the route the document itself names, paired against the identical request carrying no credential at all."
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
bb:version: 033edaf1132486dede4f6e205fda4d3437dc1371af42caee635f68ced2b394e3
bb:sha256: a3b8760281a090648ca97f21341605ffa27f0c44609f81c1f2a90f83f02b5cac
---

# Ask whether a string of credential shape in a served document is worth anything, by grounding the candidate list with an offline reader rather than by eye and then presenting each candidate once to the route the document itself names, paired against the identical request carrying no credential at all.

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

Written for ticket 54 as the v2 replacement for v1's secrets page against a new credential_material leaf added by ticket 54; the v1 page carried no attachments, and its advice to enumerate what a found key reaches is refused by the closing section. Rewritten for ticket 101 against the merged ledger, which carries one procedure, one lead, one blocked half and two refusals for this slug. No frontmatter key moved and the evidence bar is reachable, because the refuted and supported legs of the variant role name one kind. Four things the shipped text left a hunter to discover are now written down. The grounding step names which binary produces the content_match its bar requires. The pair is planned without a leased Identity wherever the candidate is presented as an Authorization header, which a leased Identity owns and would replace. Each pair carries its own control action, a control drawn from another pair being an action of another Test. And the closing section carries every refusal with its reason.

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/secrets/playbook.md`](../../../src/redkraken/playbooks/secrets/playbook.md). This concept describes that document and never replaces it.
