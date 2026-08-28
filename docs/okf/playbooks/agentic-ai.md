---
type: Playbook
title: "agentic-ai"
description: "Ask whether text the caller supplies is read by a language model as instructions rather than as data, by asking one question twice with an instruction planted in the channel under test and once with it planted where the model cannot see it."
resource: ../../../src/redkraken/playbooks/agentic-ai/playbook.md
tags: [injection, constrained, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-02-15T00:00:00Z
bb:category: injection
bb:outputs: [injection.model_instruction]
bb:triggers_all: [tech_llm]
bb:triggers_any: [body_parameter, query_parameter, reflected_parameter]
bb:skills: [compare-responses, handle-untrusted-content]
bb:risk: constrained
bb:effects: read_only
bb:baseline: none
bb:version: 813143285c97ad8825870626850ddcf0561bd64c2d3ce09309edcd4fa96a3b51
bb:sha256: f4ad285994a5cb10fa5d665fef48fb29eb4b12513880576bdec54b8d94ca4f80
sources:
  - id: agentic-ai--llm
    resource: /references/agentic-ai--llm.md
    title: "Language models as targets, and what makes a claim about one checkable"
    author: human:maintainer
---

# Ask whether text the caller supplies is read by a language model as instructions rather than as data, by asking one question twice with an instruction planted in the channel under test and once with it planted where the model cannot see it.

## What it concludes about

- `injection.model_instruction`

## When it is selected

A subject carrying every one of these facts:

- `tech_llm`

and at least one of:

- `body_parameter`
- `query_parameter`
- `reflected_parameter`

Risk `constrained`, effects `read_only`, baseline `none`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)
- [handle-untrusted-content](/skills/handle-untrusted-content.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `response_invariant` observation(s) from a `variant`
- to `supported`: at least 1 supports `response_invariant` observation(s) from a `control`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `variant`

## Provenance

Written for ticket 49 as the v2 replacement for v1's agentic-ai pack; the class it outputs is new in this ticket, because no injection leaf in the ticket 18 vocabulary named a language model as the interpreter.

## Maintainer references

- [llm.md](/references/agentic-ai--llm.md)[^agentic-ai--llm]

[^agentic-ai--llm]: Language models as targets, and what makes a claim about one checkable

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/agentic-ai/playbook.md`](../../../src/redkraken/playbooks/agentic-ai/playbook.md). This concept describes that document and never replaces it.
