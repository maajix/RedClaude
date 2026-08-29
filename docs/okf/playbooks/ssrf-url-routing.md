---
type: Playbook
title: "ssrf-url-routing"
description: "Ask whether the authority a route validates is the authority it fetches, by moving one thing at a time between two hosts the Program controls and closing on a Test whose own assertions carry the difference between what was checked and what was opened."
resource: ../../../src/redkraken/playbooks/ssrf-url-routing/playbook.md
tags: [injection, constrained, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-04-15T00:00:00Z
bb:category: injection
bb:outputs: [injection.url_authority]
bb:triggers_all: [authenticated_endpoint, read_method, url_valued_parameter]
bb:skills: [compare-responses, handle-untrusted-content, use-identity]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:version: a64a44b36567ba0291354c88294b7f502666bf1f66c36608d6487838a219139a
bb:sha256: 9b1972e4456216d9eab6a4ff6bcc7d889f218b097b53f76412e1abe4e98f9d61
sources:
  - id: ssrf-url-routing--dns-rebinding
    resource: /references/ssrf-url-routing--dns-rebinding.md
    title: "DNS rebinding: the race between the check and the fetch"
    author: human:maintainer
  - id: ssrf-url-routing--open-redirection
    resource: /references/ssrf-url-routing--open-redirection.md
    title: "Open redirection: the same parser bug, pointed at a browser"
    author: human:maintainer
  - id: ssrf-url-routing--pdf-generators
    resource: /references/ssrf-url-routing--pdf-generators.md
    title: "PDF generators: a headless browser somebody forgot was there"
    author: human:maintainer
  - id: ssrf-url-routing--ssrf
    resource: /references/ssrf-url-routing--ssrf.md
    title: "SSRF: the metadata endpoint, and the reason the reading never goes there"
    author: human:maintainer
---

# Ask whether the authority a route validates is the authority it fetches, by moving one thing at a time between two hosts the Program controls and closing on a Test whose own assertions carry the difference between what was checked and what was opened.

## What it concludes about

- `injection.url_authority`

## When it is selected

A subject carrying every one of these facts:

- `authenticated_endpoint`
- `read_method`
- `url_valued_parameter`

Risk `constrained`, effects `read_only`, baseline `stable_session`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)
- [handle-untrusted-content](/skills/handle-untrusted-content.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `response_differential` observation(s) from a `variant`
- to `supported`: at least 1 supports `response_invariant` observation(s) from a `control`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `variant`

## Provenance

Written for ticket 54 as the v2 replacement for v1's ssrf-url-routing pack against a new url_authority leaf added by ticket 54, and rewritten for ticket 101 against the merged ledger's fourteen readings for this slug. Six are procedures here and eight are named in the closing section with the reason each is out, which is the change of shape. The refuted variant kind is response_differential rather than an invariant, because close_test_replay reads the Observation kind off the Test specification and not off the outcome, so a Test that named a differing assertion writes that kind whichever way it went.

## Maintainer references

- [dns-rebinding.md](/references/ssrf-url-routing--dns-rebinding.md)[^ssrf-url-routing--dns-rebinding]
- [open-redirection.md](/references/ssrf-url-routing--open-redirection.md)[^ssrf-url-routing--open-redirection]
- [pdf-generators.md](/references/ssrf-url-routing--pdf-generators.md)[^ssrf-url-routing--pdf-generators]
- [ssrf.md](/references/ssrf-url-routing--ssrf.md)[^ssrf-url-routing--ssrf]

[^ssrf-url-routing--dns-rebinding]: DNS rebinding: the race between the check and the fetch
[^ssrf-url-routing--open-redirection]: Open redirection: the same parser bug, pointed at a browser
[^ssrf-url-routing--pdf-generators]: PDF generators: a headless browser somebody forgot was there
[^ssrf-url-routing--ssrf]: SSRF: the metadata endpoint, and the reason the reading never goes there

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/ssrf-url-routing/playbook.md`](../../../src/redkraken/playbooks/ssrf-url-routing/playbook.md). This concept describes that document and never replaces it.
