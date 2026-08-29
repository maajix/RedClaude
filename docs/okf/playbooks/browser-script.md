---
type: Playbook
title: "browser-script"
description: "Ask whether a reflected parameter reaches the browser as markup a parser builds an element from, and whether the filter and the parser agree about what they were handed, by naming the escaping context from two stored responses first and only then planting the one registered probe through a scripted browser mission."
resource: ../../../src/redkraken/playbooks/browser-script/playbook.md
tags: [injection, constrained, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-03-15T00:00:00Z
bb:category: injection
bb:outputs: [injection.markup, injection.parser_differential]
bb:triggers_all: [query_parameter, reflected_parameter, web_surface]
bb:skills: [browser-evidence, compare-responses]
bb:risk: constrained
bb:effects: read_only
bb:baseline: none
bb:version: 847a64a40212afb4d69ce8a696b147d04b54266a08485b68807a1d5ed63ec02a
bb:sha256: c05fdbe32df2f01c9427f7f6bf588fae9b54b6eca2dd4aa45dd2847e5512da83
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

# Ask whether a reflected parameter reaches the browser as markup a parser builds an element from, and whether the filter and the parser agree about what they were handed, by naming the escaping context from two stored responses first and only then planting the one registered probe through a scripted browser mission.

## What it concludes about

- `injection.markup`
- `injection.parser_differential`

## When it is selected

A subject carrying every one of these facts:

- `query_parameter`
- `reflected_parameter`
- `web_surface`

Risk `constrained`, effects `read_only`, baseline `none`.

## Skills it loads

- [browser-evidence](/skills/browser-evidence.md)
- [compare-responses](/skills/compare-responses.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `response_differential` observation(s) from a `variant`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `control`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `variant`

## Provenance

Written for ticket 52 as the v2 replacement for v1's xss and dangling-markup pages, against the markup leaf of the ticket 18 vocabulary; both v1 texts are attached as maintainer references. Rewritten for ticket 101 against the merged technique ledger, which holds nine executable readings, two capability asks and one refusal for this slug. Two of the nine ask whether a filter and a parser disagree about one normalisation, which is injection.parser_differential -- a class the vocabulary shipped with no emitter -- so bb:outputs gains it under D3. bb:skills gains compare-responses because two readings are ordinary response comparisons that need no browser at all. Repaired in review -- the file described Tests without naming mcp__rk2__propose_test, the only verb that files a specification, and section 5 named neither the verb that performs it nor the writer that records it. Recounted in round 3 -- the four browse-lane sections grade nothing, so the register reads 7 of 8 and not 3 of 8.

## Maintainer references

- [dangling-markup.md](/references/browser-script--dangling-markup.md)[^browser-script--dangling-markup]
- [xss.md](/references/browser-script--xss.md)[^browser-script--xss]

[^browser-script--dangling-markup]: Dangling markup: injection without execution
[^browser-script--xss]: XSS: what the corpus grades, and what the payload list is for

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/browser-script/playbook.md`](../../../src/redkraken/playbooks/browser-script/playbook.md). This concept describes that document and never replaces it.
