---
type: Playbook
title: "external-resources"
description: "Ask which origins a served document grants authority to run inside it, by listing every reference that carries executable authority out of the stored bytes, naming the ones the Program's scope does not claim, and differencing a candidate host against a label nobody holds to see whether the reference points at a resource that was let go."
resource: ../../../src/redkraken/playbooks/external-resources/playbook.md
tags: [injection, constrained, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-03-15T00:00:00Z
bb:category: injection
bb:outputs: [injection.foreign_resource, injection.unclaimed_reference]
bb:triggers_all: [read_method, url_valued_parameter, web_surface]
bb:skills: [compare-responses, enumerate-surface, handle-untrusted-content]
bb:risk: constrained
bb:effects: read_only
bb:baseline: none
bb:version: 856d6ca0a1cc422be97ec56e027c7f1c7c0606975a3f4c6bdb83d1b7e0f0a146
bb:sha256: 5e98f93fb637cc3599537e5302b293e7952d4bc48d17ae4f5204f78a814fdfd2
sources:
  - id: external-resources--broken-link-hijacking
    resource: /references/external-resources--broken-link-hijacking.md
    title: "Broken link hijacking: find the name, do not take it"
    author: human:maintainer
---

# Ask which origins a served document grants authority to run inside it, by listing every reference that carries executable authority out of the stored bytes, naming the ones the Program's scope does not claim, and differencing a candidate host against a label nobody holds to see whether the reference points at a resource that was let go.

## What it concludes about

- `injection.foreign_resource`
- `injection.unclaimed_reference`

## When it is selected

A subject carrying every one of these facts:

- `read_method`
- `url_valued_parameter`
- `web_surface`

Risk `constrained`, effects `read_only`, baseline `none`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)
- [enumerate-surface](/skills/enumerate-surface.md)
- [handle-untrusted-content](/skills/handle-untrusted-content.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `content_match` observation(s) from a `variant`
- to `supported`: at least 1 supports `content_match` observation(s) from a `control`
- to `supported`: at least 1 supports `content_match` observation(s) from a `variant`

## Provenance

Written for ticket 52 as the v2 replacement for v1's broken-link-hijacking page, against a new foreign-resource leaf added by ticket 52; the v1 text is attached as a maintainer reference and section 6's refusal is where this Playbook and that page part company. Rewritten for ticket 101 against the merged technique ledger, which carries three readings and one standing refusal for this slug. One frontmatter key moves and it is a repair -- analyse-source is granted to js_analyst alone, js_analyst holds no request verb, and a Playbook naming that Skill is one no hunting role can be handed, so the three Skills web_hunter holds for this reading replace it and section 1 fetches its own bytes. The effects and the risk floor are the ones already declared, since the two readings added below are Tests this role proposes and the replay lane performs.

## Maintainer references

- [broken-link-hijacking.md](/references/external-resources--broken-link-hijacking.md)[^external-resources--broken-link-hijacking]

[^external-resources--broken-link-hijacking]: Broken link hijacking: find the name, do not take it

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/external-resources/playbook.md`](../../../src/redkraken/playbooks/external-resources/playbook.md). This concept describes that document and never replaces it.
