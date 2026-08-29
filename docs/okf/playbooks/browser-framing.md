---
type: Playbook
title: "browser-framing"
description: "Ask whether a state-changing page tells the browser, in the headers a browser enforces, that another origin may neither frame it nor read what it answers, by differencing the policy the target serves against a sibling route of the same deployment and against the same request carrying a foreign Origin."
resource: ../../../src/redkraken/playbooks/browser-framing/playbook.md
tags: [transport, constrained, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-03-15T00:00:00Z
bb:category: transport
bb:outputs: [transport.header_policy]
bb:triggers_all: [form_request, state_changing_method, web_surface]
bb:skills: [browser-evidence, compare-responses, use-identity]
bb:risk: constrained
bb:effects: read_only
bb:baseline: none
bb:version: 1467146b0f0e73872cefbf190a4d45d5d9cfa7043a352cb7603a0c4062563996
bb:sha256: d36a909ae7985b0f7154b4e4a24be4ff7e0788aa13f19c190adc09cabcbdc91b
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

# Ask whether a state-changing page tells the browser, in the headers a browser enforces, that another origin may neither frame it nor read what it answers, by differencing the policy the target serves against a sibling route of the same deployment and against the same request carrying a foreign Origin.

## What it concludes about

- `transport.header_policy`

## When it is selected

A subject carrying every one of these facts:

- `form_request`
- `state_changing_method`
- `web_surface`

Risk `constrained`, effects `read_only`, baseline `none`.

## Skills it loads

- [browser-evidence](/skills/browser-evidence.md)
- [compare-responses](/skills/compare-responses.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `header_policy_observed` observation(s) from a `variant`
- to `supported`: at least 1 supports `header_policy_observed` observation(s) from a `control`
- to `supported`: at least 1 supports `header_policy_observed` observation(s) from a `variant`

## Provenance

Written for ticket 52 as the v2 replacement for v1's clickjacking and CORS/XSSI pages, against the header-policy leaf of the ticket 18 vocabulary; rewritten for ticket 101 against the merged technique ledger, which carries four readings and one standing refusal for this slug. One frontmatter key moved -- browser-evidence joins bb:skills, because the cookie attribute set in section 5 is readable in the browser lane and on no other. bb:evidence is unchanged -- header_policy_observed is agent-filed on all three legs, so the refuted leg already asks for the kind its own role asks for on supported. Repaired in review, where every Test in the file was found to settle on a formality no assertion could read; the file now proposes no Test, opens no Finding, and treats its bar's variant and control as Observation roles. Repaired again in round 3, where section 3 listed six Origin values under a stated budget of four -- the literal null is out, since a hosted document produces it, and the budget is the five left.

## Maintainer references

- [clickjacking.md](/references/browser-framing--clickjacking.md)[^browser-framing--clickjacking]
- [cors-xssi.md](/references/browser-framing--cors-xssi.md)[^browser-framing--cors-xssi]

[^browser-framing--clickjacking]: Clickjacking: the header is the claim, the frame is the demo
[^browser-framing--cors-xssi]: CORS and XSSI: two ways to read a response you were not supposed to

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/browser-framing/playbook.md`](../../../src/redkraken/playbooks/browser-framing/playbook.md). This concept describes that document and never replaces it.
