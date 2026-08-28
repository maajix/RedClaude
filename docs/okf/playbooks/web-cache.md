---
type: Playbook
title: "web-cache"
description: "Ask whether a response that varies by caller is stored under a cache key that does not, by storing and reading one response on a unique path nobody else will ever request and never touching a key a real user shares."
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
bb:version: a80884fae11c952df96be677e682dd284354e2476732b9818ce9e0c7a706f264
bb:sha256: fe5a82176664b8246caf3c40799851e39955746ae1c8f1141706cc5e195922b2
sources:
  - id: web-cache--cache-poisoning
    resource: /references/web-cache--cache-poisoning.md
    title: "Cache poisoning and cache deception: the key, and who else asks for it"
    author: human:maintainer
---

# Ask whether a response that varies by caller is stored under a cache key that does not, by storing and reading one response on a unique path nobody else will ever request and never touching a key a real user shares.

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

- to `refuted`: at least 1 refutes `response_invariant` observation(s) from a `variant`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `control`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `variant`

## Provenance

Written for ticket 52 as the v2 replacement for v1's cache-poisoning page, against a new cached-response leaf added by ticket 52; the v1 text is attached as a maintainer reference and step 2's unique key is where this Playbook and that page part company.

## Maintainer references

- [cache-poisoning.md](/references/web-cache--cache-poisoning.md)[^web-cache--cache-poisoning]

[^web-cache--cache-poisoning]: Cache poisoning and cache deception: the key, and who else asks for it

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/web-cache/playbook.md`](../../../src/redkraken/playbooks/web-cache/playbook.md). This concept describes that document and never replaces it.
