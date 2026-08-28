---
type: Playbook
title: "structured-injection"
description: "Ask whether a value in an XML body becomes structure rather than content, by sending one field carrying a structural character beside the same field carrying an inert character of the same length and reading the parser's own error."
resource: ../../../src/redkraken/playbooks/structured-injection/playbook.md
tags: [injection, constrained, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-03-15T00:00:00Z
bb:category: injection
bb:outputs: [injection.document_parser]
bb:triggers_all: [body_parameter, state_changing_method, xml_request]
bb:skills: [compare-responses, handle-untrusted-content, use-identity]
bb:risk: constrained
bb:effects: read_only
bb:baseline: none
bb:version: 12c672544ce12616af9122fa251031f10123dd8a9e89517e3cb1df38edaa821c
bb:sha256: 19b07f9230d480fea28fadd645db8860c5dce6d852f0281625898e0a3101f817
sources:
  - id: structured-injection--smtp-header-injection
    resource: /references/structured-injection--smtp-header-injection.md
    title: "SMTP header injection: the newline that ends a field"
    author: human:maintainer
  - id: structured-injection--xpath-injections
    resource: /references/structured-injection--xpath-injections.md
    title: "XPath injection: the query half of the document parser"
    author: human:maintainer
---

# Ask whether a value in an XML body becomes structure rather than content, by sending one field carrying a structural character beside the same field carrying an inert character of the same length and reading the parser's own error.

## What it concludes about

- `injection.document_parser`

## When it is selected

A subject carrying every one of these facts:

- `body_parameter`
- `state_changing_method`
- `xml_request`

Risk `constrained`, effects `read_only`, baseline `none`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)
- [handle-untrusted-content](/skills/handle-untrusted-content.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `response_invariant` observation(s) from a `variant`
- to `supported`: at least 1 supports `response_invariant` observation(s) from a `control`
- to `supported`: at least 1 supports `error_detail` observation(s) from a `variant`

## Provenance

Written for ticket 53 as the v2 replacement for v1's structured-injection pack against the document_parser leaf of the ticket 18 vocabulary; the pack's two pages are attached as maintainer references, and the XXE material the class also covers is attached to command-directory-injection because that is the v1 pack it shipped in.

## Maintainer references

- [smtp-header-injection.md](/references/structured-injection--smtp-header-injection.md)[^structured-injection--smtp-header-injection]
- [xpath-injections.md](/references/structured-injection--xpath-injections.md)[^structured-injection--xpath-injections]

[^structured-injection--smtp-header-injection]: SMTP header injection: the newline that ends a field
[^structured-injection--xpath-injections]: XPath injection: the query half of the document parser

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/structured-injection/playbook.md`](../../../src/redkraken/playbooks/structured-injection/playbook.md). This concept describes that document and never replaces it.
