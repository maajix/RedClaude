---
type: Playbook
title: "ssti"
description: "Ask whether a reflected parameter becomes part of a template's source rather than a value passed into it, by sending an arithmetic expression whose result cannot be confused with its input beside a one-character-shorter twin the engine cannot evaluate."
resource: ../../../src/redkraken/playbooks/ssti/playbook.md
tags: [injection, constrained, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-03-15T00:00:00Z
bb:category: injection
bb:outputs: [injection.template]
bb:triggers_all: [authenticated_endpoint, reflected_parameter, tech_template]
bb:skills: [compare-responses, use-identity]
bb:risk: constrained
bb:effects: read_only
bb:baseline: none
bb:version: b365058a2dd42d5824d4790eac4dd6859e782994ee216113faddb233626dbf11
bb:sha256: e6a480a3a88aa734eeff5027844a84b93400cf09fc1f03a335c3ba6c6b9810ee
sources:
  - id: ssti--ssti
    resource: /references/ssti--ssti.md
    title: "Server-side template injection: the arithmetic probe and nothing past it"
    author: human:maintainer
---

# Ask whether a reflected parameter becomes part of a template's source rather than a value passed into it, by sending an arithmetic expression whose result cannot be confused with its input beside a one-character-shorter twin the engine cannot evaluate.

## What it concludes about

- `injection.template`

## When it is selected

A subject carrying every one of these facts:

- `authenticated_endpoint`
- `reflected_parameter`
- `tech_template`

Risk `constrained`, effects `read_only`, baseline `none`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `reflected_input` observation(s) from a `variant`
- to `supported`: at least 1 supports `reflected_input` observation(s) from a `control`
- to `supported`: at least 1 supports `reflected_input` observation(s) from a `variant`

## Provenance

Written for ticket 53 as the v2 replacement for v1's ssti page against the template leaf of the ticket 18 vocabulary; the v1 text is attached as a maintainer reference and every sandbox escape and context read in it is refused by step 6.

## Maintainer references

- [ssti.md](/references/ssti--ssti.md)[^ssti--ssti]

[^ssti--ssti]: Server-side template injection: the arithmetic probe and nothing past it

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/ssti/playbook.md`](../../../src/redkraken/playbooks/ssti/playbook.md). This concept describes that document and never replaces it.
