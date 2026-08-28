---
type: Playbook
title: "browser-framing"
description: "Ask whether a state-changing page tells the browser, in the headers a browser enforces, that another origin may neither frame it nor read what it answers, by reading the policy the target serves rather than by putting the page in a frame."
resource: ../../../src/redkraken/playbooks/browser-framing/playbook.md
tags: [transport, constrained, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-03-15T00:00:00Z
bb:category: transport
bb:outputs: [transport.header_policy]
bb:triggers_all: [form_request, state_changing_method, web_surface]
bb:skills: [compare-responses, use-identity]
bb:risk: constrained
bb:effects: read_only
bb:baseline: none
bb:version: 1eded40c2e2891448d1e6d3ce5c7d020deb4b9176a825221949749fc40842539
bb:sha256: 6c8c696e024a59108b274eea08a73cb03c26e15eae4221056f47d7325b97642b
sources:
  - id: browser-framing--clickjacking
    resource: /references/browser-framing--clickjacking.md
    title: "Clickjacking: the header is the claim, the frame is the demo"
    author: human:maintainer
  - id: browser-framing--cors-xssi
    resource: /references/browser-framing--cors-xssi.md
    title: "CORS and XSSI: two ways to read a response you were not supposed to"
    author: human:maintainer
---

# Ask whether a state-changing page tells the browser, in the headers a browser enforces, that another origin may neither frame it nor read what it answers, by reading the policy the target serves rather than by putting the page in a frame.

## What it concludes about

- `transport.header_policy`

## When it is selected

A subject carrying every one of these facts:

- `form_request`
- `state_changing_method`
- `web_surface`

Risk `constrained`, effects `read_only`, baseline `none`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `header_policy_observed` observation(s) from a `variant`
- to `supported`: at least 1 supports `header_policy_observed` observation(s) from a `control`
- to `supported`: at least 1 supports `header_policy_observed` observation(s) from a `variant`

## Provenance

Written for ticket 52 as the v2 replacement for v1's clickjacking and CORS/XSSI pages, against the header-policy leaf of the ticket 18 vocabulary; both v1 texts are attached as maintainer references and both describe headers step 1 and step 2 read.

## Maintainer references

- [clickjacking.md](/references/browser-framing--clickjacking.md)[^browser-framing--clickjacking]
- [cors-xssi.md](/references/browser-framing--cors-xssi.md)[^browser-framing--cors-xssi]

[^browser-framing--clickjacking]: Clickjacking: the header is the claim, the frame is the demo
[^browser-framing--cors-xssi]: CORS and XSSI: two ways to read a response you were not supposed to

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/browser-framing/playbook.md`](../../../src/redkraken/playbooks/browser-framing/playbook.md). This concept describes that document and never replaces it.
