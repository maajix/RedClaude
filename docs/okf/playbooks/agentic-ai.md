---
type: Playbook
title: "agentic-ai"
description: "Ask whether text the caller supplies is read by a language model as instructions rather than as data, by asking one question three ways -- plain, with the instruction planted in the channel under test, and with it planted where the model cannot see it."
resource: ../../../src/redkraken/playbooks/agentic-ai/playbook.md
tags: [injection, constrained, mutates_object]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-02-15T00:00:00Z
bb:category: injection
bb:outputs: [injection.model_instruction]
bb:triggers_all: [tech_llm]
bb:triggers_any: [body_parameter, query_parameter, reflected_parameter]
bb:skills: [compare-responses, handle-untrusted-content]
bb:risk: constrained
bb:effects: mutates_object
bb:baseline: none
bb:version: 077fadd3e4ba819e9729b3f2e7367bff6ca356551ff730a485009e2279c71254
bb:sha256: 0c46d4fc5558251fc985f860086d363c985ef40b0054f6e58cd6a26397d66620
sources:
  - id: agentic-ai--llm
    resource: /references/agentic-ai--llm.md
    title: "Language models as targets, and what makes a claim about one checkable"
    author: human:maintainer
---

# Ask whether text the caller supplies is read by a language model as instructions rather than as data, by asking one question three ways -- plain, with the instruction planted in the channel under test, and with it planted where the model cannot see it.

## What it concludes about

- `injection.model_instruction`

## When it is selected

A subject carrying every one of these facts:

- `tech_llm`

and at least one of:

- `body_parameter`
- `query_parameter`
- `reflected_parameter`

Risk `constrained`, effects `mutates_object`, baseline `none`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)
- [handle-untrusted-content](/skills/handle-untrusted-content.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `response_differential` observation(s) from a `variant`
- to `supported`: at least 1 supports `response_invariant` observation(s) from a `control`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `variant`

## Provenance

Written for ticket 49 as the v2 replacement for v1's agentic-ai pack, against the model-instruction leaf of the ticket 18 vocabulary; rewritten for ticket 101 against the merged ledger, which carries five readings and one refusal for this class. Two keys moved. bb:effects rises from read_only to mutates_object because three of the five readings store a record on the subject and read it back, and a Playbook that stores must say so; bb:risk stays constrained, which is the floor that admits it. The refuted variant row moves from response_invariant to response_differential, because close_test_replay derives the kind from the specification and one role writes one kind whichever way the reading goes. Repaired again in review -- vulnerability_class names code_injection, the closest standing id, because ticket 49 seeded no property_class_vulnerability_classes row for this class.

## Maintainer references

- [llm.md](/references/agentic-ai--llm.md)[^agentic-ai--llm]

[^agentic-ai--llm]: Language models as targets, and what makes a claim about one checkable

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/agentic-ai/playbook.md`](../../../src/redkraken/playbooks/agentic-ai/playbook.md). This concept describes that document and never replaces it.
