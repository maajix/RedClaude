---
type: Playbook
title: "browser-messaging"
description: "Ask whether a document something else embeds writes a value it never fetched into its own DOM as markup, by planting one registered probe in the page and showing that no request left the browser between the planting and the verdict."
resource: ../../../src/redkraken/playbooks/browser-messaging/playbook.md
tags: [injection, constrained, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-03-15T00:00:00Z
bb:category: injection
bb:outputs: [injection.client_channel]
bb:triggers_all: [embedded_document, read_method, web_surface]
bb:skills: [browser-evidence]
bb:risk: constrained
bb:effects: read_only
bb:baseline: none
bb:version: ccaa992bb13367824ee6f1b2d5719459d33807ae91539849db4f360d0fdb8b97
bb:sha256: 292b877886d038ad7dabd5ff0deb1b0149b8bf4928f86f344573215327a60b97
sources:
  - id: browser-messaging--dom-vulnerabilities
    resource: /references/browser-messaging--dom-vulnerabilities.md
    title: "DOM vulnerabilities: the sources this harness can drive, and the ones it cannot"
    author: human:maintainer
  - id: browser-messaging--prototype-pollution
    resource: /references/browser-messaging--prototype-pollution.md
    title: "Prototype pollution: why this one is read and not triggered"
    author: human:maintainer
---

# Ask whether a document something else embeds writes a value it never fetched into its own DOM as markup, by planting one registered probe in the page and showing that no request left the browser between the planting and the verdict.

## What it concludes about

- `injection.client_channel`

## When it is selected

A subject carrying every one of these facts:

- `embedded_document`
- `read_method`
- `web_surface`

Risk `constrained`, effects `read_only`, baseline `none`.

## Skills it loads

- [browser-evidence](/skills/browser-evidence.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `reflected_input` observation(s) from a `variant`
- to `supported`: at least 1 supports `response_invariant` observation(s) from a `control`
- to `supported`: at least 1 supports `reflected_input` observation(s) from a `variant`

## Provenance

Written for ticket 52 as the v2 replacement for v1's dom-vulnerabilities and prototype-pollution pages, against a new client-channel leaf added by ticket 52; both v1 texts are attached as maintainer references and both describe sources step 3 names and cannot drive.

## Maintainer references

- [dom-vulnerabilities.md](/references/browser-messaging--dom-vulnerabilities.md)[^browser-messaging--dom-vulnerabilities]
- [prototype-pollution.md](/references/browser-messaging--prototype-pollution.md)[^browser-messaging--prototype-pollution]

[^browser-messaging--dom-vulnerabilities]: DOM vulnerabilities: the sources this harness can drive, and the ones it cannot
[^browser-messaging--prototype-pollution]: Prototype pollution: why this one is read and not triggered

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/browser-messaging/playbook.md`](../../../src/redkraken/playbooks/browser-messaging/playbook.md). This concept describes that document and never replaces it.
