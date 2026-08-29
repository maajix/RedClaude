---
type: Playbook
title: "web-cache"
description: "Ask whether a front end hands one caller's answer to another, by storing and reading a response on a key this reading invented, and by asking through the path where the origin thinks a route ends, whether the path is resolved before it is routed, and which shape the classifier files as a static asset."
resource: ../../../src/redkraken/playbooks/web-cache/playbook.md
tags: [information_disclosure, constrained, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-03-15T00:00:00Z
bb:category: information_disclosure
bb:outputs: [information_disclosure.cached_response]
bb:triggers_all: [read_method, tech_cdn, web_surface]
bb:skills: [compare-responses, use-identity]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:version: 87fea961dbf957c56d7f938da7410bd5f43ad7b706a66015d7bd7ef9964ea53f
bb:sha256: 5c5da1076d5dfa276b1cc5b114bf19f10c45cd75ac3bc455a664783aa6811150
sources:
  - id: web-cache--cache-poisoning
    resource: /references/web-cache--cache-poisoning.md
    title: "Cache poisoning and cache deception: the key, and who else asks for it"
    author: human:maintainer
---

# Ask whether a front end hands one caller's answer to another, by storing and reading a response on a key this reading invented, and by asking through the path where the origin thinks a route ends, whether the path is resolved before it is routed, and which shape the classifier files as a static asset.

## What it concludes about

- `information_disclosure.cached_response`

## When it is selected

A subject carrying every one of these facts:

- `read_method`
- `tech_cdn`
- `web_surface`

Risk `constrained`, effects `read_only`, baseline `stable_session`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `response_differential` observation(s) from a `variant`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `control`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `variant`

## Provenance

Written for ticket 52 as the v2 replacement for v1's cache-poisoning page, against a new cached-response leaf added by ticket 52; the v1 text is attached as a maintainer reference and the invented key is where this Playbook and that page part company. Rewritten for ticket 101 against the merged ledger, which carries six procedures, one lead and three refusals for this slug. One key moved. The refuted variant row leaves response_invariant for response_differential, the kind the supported row of that same role names, because close_test_replay derives the kind from the specification and one role writes one kind whichever way the reading goes. Every closing assertion below names its variant against a control arm rather than against the baseline, which is what keeps the declared control row reachable.

## Maintainer references

- [cache-poisoning.md](/references/web-cache--cache-poisoning.md)[^web-cache--cache-poisoning]

[^web-cache--cache-poisoning]: Cache poisoning and cache deception: the key, and who else asks for it

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/web-cache/playbook.md`](../../../src/redkraken/playbooks/web-cache/playbook.md). This concept describes that document and never replaces it.
