---
type: Playbook
title: "request-parsing"
description: "Ask whether two components that both act on one request resolve the same parameter name to different values, by sending the route's own request once with the name in one carrier and once with it in two, and comparing what the application said it accepted against what it actually produced."
resource: ../../../src/redkraken/playbooks/request-parsing/playbook.md
tags: [injection, constrained, mutates_object]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-05-15T00:00:00Z
bb:category: injection
bb:outputs: [injection.parameter_precedence]
bb:triggers_all: [repeated_parameter_name, state_changing_method, web_surface]
bb:skills: [compare-responses]
bb:risk: constrained
bb:effects: mutates_object
bb:baseline: pristine_surface
bb:version: 1bd54787c410fd568677c21a085a8806bff891fbf01f6ac2fb24b279cd338a23
bb:sha256: 491befb5f68018ecf7cd6e8c324c08aab640d0ff55e47cea7d85340da50b6078
sources:
  - id: request-parsing--http-attacks-crlf-injection-and-response-splitting
    resource: /references/request-parsing--http-attacks-crlf-injection-and-response-splitting.md
    title: "CRLF injection and response splitting: refused, and the blast radius is why"
    author: human:maintainer
  - id: request-parsing--http-attacks-host-header
    resource: /references/request-parsing--http-attacks-host-header.md
    title: "Host header attacks: the observation is kept, the rewrite is refused"
    author: human:maintainer
  - id: request-parsing--parameter-pollution
    resource: /references/request-parsing--parameter-pollution.md
    title: "Parameter pollution: kept, narrowed to one name and one arm"
    author: human:maintainer
  - id: request-parsing--waf-bypasses
    resource: /references/request-parsing--waf-bypasses.md
    title: "Filter bypasses: the whole page is refused, and the argument is about what a bypass proves"
    author: human:maintainer
---

# Ask whether two components that both act on one request resolve the same parameter name to different values, by sending the route's own request once with the name in one carrier and once with it in two, and comparing what the application said it accepted against what it actually produced.

## What it concludes about

- `injection.parameter_precedence`

## When it is selected

A subject carrying every one of these facts:

- `repeated_parameter_name`
- `state_changing_method`
- `web_surface`

Risk `constrained`, effects `mutates_object`, baseline `pristine_surface`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `response_invariant` observation(s) from a `variant`
- to `supported`: at least 1 supports `response_invariant` observation(s) from a `control`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `variant`

## Provenance

Written for ticket 56 as the v2 replacement for v1's request-parsing pack against a new parameter_precedence leaf added by ticket 56; the pack's four pages are attached as maintainer references, and its response-splitting payloads, its host-header rewrites and its filter-evasion catalogue are refused by step 7.

## Maintainer references

- [http-attacks-crlf-injection-and-response-splitting.md](/references/request-parsing--http-attacks-crlf-injection-and-response-splitting.md)[^request-parsing--http-attacks-crlf-injection-and-response-splitting]
- [http-attacks-host-header.md](/references/request-parsing--http-attacks-host-header.md)[^request-parsing--http-attacks-host-header]
- [parameter-pollution.md](/references/request-parsing--parameter-pollution.md)[^request-parsing--parameter-pollution]
- [waf-bypasses.md](/references/request-parsing--waf-bypasses.md)[^request-parsing--waf-bypasses]

[^request-parsing--http-attacks-crlf-injection-and-response-splitting]: CRLF injection and response splitting: refused, and the blast radius is why
[^request-parsing--http-attacks-host-header]: Host header attacks: the observation is kept, the rewrite is refused
[^request-parsing--parameter-pollution]: Parameter pollution: kept, narrowed to one name and one arm
[^request-parsing--waf-bypasses]: Filter bypasses: the whole page is refused, and the argument is about what a bypass proves

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/request-parsing/playbook.md`](../../../src/redkraken/playbooks/request-parsing/playbook.md). This concept describes that document and never replaces it.
