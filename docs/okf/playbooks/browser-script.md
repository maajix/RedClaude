---
type: Playbook
title: "browser-script"
description: "Ask whether a parameter a recon pass saw reflected reaches the browser as markup the parser builds an element from, by planting one registered probe through a scripted browser mission and reading the verdict the probe returns."
resource: ../../../src/redkraken/playbooks/browser-script/playbook.md
tags: [injection, constrained, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-03-15T00:00:00Z
bb:category: injection
bb:outputs: [injection.markup]
bb:triggers_all: [query_parameter, reflected_parameter, web_surface]
bb:skills: [browser-evidence]
bb:risk: constrained
bb:effects: read_only
bb:baseline: none
bb:version: 0dd9f3ece33a4ec11a831b7ee3644ca8b777c528a42151caebe15de92014b2e8
bb:sha256: 3f4982af4dcf34a8875ae1912410da4888615f6bd2e467ee4a45d06af97ea2e0
sources:
  - id: browser-script--dangling-markup
    resource: /references/browser-script--dangling-markup.md
    title: "Dangling markup: injection without execution"
    author: human:maintainer
  - id: browser-script--xss
    resource: /references/browser-script--xss.md
    title: "XSS: what the corpus grades, and what the payload list is for"
    author: human:maintainer
---

# Ask whether a parameter a recon pass saw reflected reaches the browser as markup the parser builds an element from, by planting one registered probe through a scripted browser mission and reading the verdict the probe returns.

## What it concludes about

- `injection.markup`

## When it is selected

A subject carrying every one of these facts:

- `query_parameter`
- `reflected_parameter`
- `web_surface`

Risk `constrained`, effects `read_only`, baseline `none`.

## Skills it loads

- [browser-evidence](/skills/browser-evidence.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `response_differential` observation(s) from a `variant`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `control`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `variant`

## Provenance

Written for ticket 52 as the v2 replacement for v1's xss and dangling-markup pages, against the markup leaf of the ticket 18 vocabulary; both v1 texts are attached as maintainer references and the second is where step 4's contexts come from.

## Maintainer references

- [dangling-markup.md](/references/browser-script--dangling-markup.md)[^browser-script--dangling-markup]
- [xss.md](/references/browser-script--xss.md)[^browser-script--xss]

[^browser-script--dangling-markup]: Dangling markup: injection without execution
[^browser-script--xss]: XSS: what the corpus grades, and what the payload list is for

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/browser-script/playbook.md`](../../../src/redkraken/playbooks/browser-script/playbook.md). This concept describes that document and never replaces it.
