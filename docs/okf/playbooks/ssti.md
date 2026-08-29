---
type: Playbook
title: "ssti"
description: "Ask whether a reflected parameter becomes part of a template's source rather than a value passed into it, by sending an arithmetic expression whose result cannot be confused with its input beside a one-character-shorter twin the engine cannot evaluate, and, where the sink renders nothing at all, by gating an exception on the answer, reading the computed value out of an error message, and submitting a stylesheet whose only effect is a fetch at a minted correlator."
resource: ../../../src/redkraken/playbooks/ssti/playbook.md
tags: [injection, constrained, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-03-15T00:00:00Z
bb:category: injection
bb:outputs: [injection.template]
bb:triggers_all: [authenticated_endpoint, reflected_parameter, tech_template]
bb:skills: [compare-responses, handle-untrusted-content, use-identity]
bb:risk: constrained
bb:effects: read_only
bb:baseline: none
bb:version: a6985160c2a02fada424bd4b6eee58410c71405044efa2b9380870e49af6c494
bb:sha256: 5f57a22c9c0797608738cee12494a4f3aecc1f393cb023027527fdd328c7c6b4
sources:
  - id: ssti--ssti
    resource: /references/ssti--ssti.md
    title: "Server-side template injection: the arithmetic probe and nothing past it"
    author: human:maintainer
---

# Ask whether a reflected parameter becomes part of a template's source rather than a value passed into it, by sending an arithmetic expression whose result cannot be confused with its input beside a one-character-shorter twin the engine cannot evaluate, and, where the sink renders nothing at all, by gating an exception on the answer, reading the computed value out of an error message, and submitting a stylesheet whose only effect is a fetch at a minted correlator.

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
- [handle-untrusted-content](/skills/handle-untrusted-content.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `reflected_input` observation(s) from a `variant`
- to `supported`: at least 1 supports `reflected_input` observation(s) from a `control`
- to `supported`: at least 1 supports `reflected_input` observation(s) from a `variant`

## Provenance

Written for ticket 53 as the v2 replacement for v1's ssti page against the template leaf of the ticket 18 vocabulary; the v1 text is attached as a maintainer reference and every sandbox escape and context read in it is refused by the closing section. Rewritten for ticket 101 against the merged ledger, which carries seven readings and one refusal for this slug; the shipped arithmetic pair is one of the seven and the other six are new, four of them for sinks that render nothing at all. One key moved -- handle-untrusted-content is added, because section 6 submits a document and reads what a processor sends back. bb:evidence is unchanged, and all three rows already ask for reflected_input -- one kind for the variant role whichever way the reading goes, written by promote_proposal from the same Receipt the Test closes on. Two corrections came from source rather than from the earlier draft -- bb:effects does not decide whether a request may carry a body, and body_equals reads the response body digest alone.

## Maintainer references

- [ssti.md](/references/ssti--ssti.md)[^ssti--ssti]

[^ssti--ssti]: Server-side template injection: the arithmetic probe and nothing past it

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/ssti/playbook.md`](../../../src/redkraken/playbooks/ssti/playbook.md). This concept describes that document and never replaces it.
