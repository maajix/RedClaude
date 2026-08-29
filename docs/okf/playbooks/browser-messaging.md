---
type: Playbook
title: "browser-messaging"
description: "Ask whether a document something else embeds turns a value it never fetched into its own markup, by inventorying what the page listens for and then planting one registered probe through a field, a fragment or a polluted property path while the Receipt list shows no request carried the value."
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
bb:version: d7b0e99ffdb7f789836b8d31445da1ea9c1012ade49a9a82d7f6805e3fafd6fb
bb:sha256: bb7b5d293278c7629f889bfe56e50fe1e44a38427354d5d3d8f62b359b4fa308
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

# Ask whether a document something else embeds turns a value it never fetched into its own markup, by inventorying what the page listens for and then planting one registered probe through a field, a fragment or a polluted property path while the Receipt list shows no request carried the value.

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

Written for ticket 52 as the v2 replacement for v1's dom-vulnerabilities and prototype-pollution pages, against a new client-channel leaf added by ticket 52; both v1 texts are attached as maintainer references and both describe sources this Playbook now drives. Rewritten for ticket 101 against the merged ledger, which carries four readings and one refusal for this slug. No frontmatter key moved and the evidence bar is already reachable, because the refuted and supported legs of the variant role name one kind. Two shipped paragraphs were false rather than cautious and are replaced. The fragment refusal is lifted -- ticket 99 widened the navigate url pattern so a browser-local fragment is admissible -- and the claim that no action sends a cross-document message is superseded by the listener inventory and the registry-owned dispatch, whose boundary is that a dispatch is reported as dispatched and never as matched. The whole ceiling is now stated in the preamble rather than discovered after a mission.

## Maintainer references

- [dom-vulnerabilities.md](/references/browser-messaging--dom-vulnerabilities.md)[^browser-messaging--dom-vulnerabilities]
- [prototype-pollution.md](/references/browser-messaging--prototype-pollution.md)[^browser-messaging--prototype-pollution]

[^browser-messaging--dom-vulnerabilities]: DOM vulnerabilities: the sources this harness can drive, and the ones it cannot
[^browser-messaging--prototype-pollution]: Prototype pollution: why this one is read and not triggered

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/browser-messaging/playbook.md`](../../../src/redkraken/playbooks/browser-messaging/playbook.md). This concept describes that document and never replaces it.
