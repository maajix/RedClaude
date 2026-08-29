---
type: Playbook
title: "structured-injection"
description: "Ask whether a value in a document the target assembles becomes structure rather than content, by sending one field carrying a structural character beside the same field carrying an inert character of the same length, by asking which parser the route hands the body to, and by asking on a declared channel whether the parser resolves an identifier it was handed."
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
bb:version: 83691efa238328d5304ad65dc37fd36db2c886b13189b399dc2f6fba1788a9b8
bb:sha256: 5ddf11651084ff8de95b6073356c32e09d45873aa304b003ecf01fa1b79a47db
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

# Ask whether a value in a document the target assembles becomes structure rather than content, by sending one field carrying a structural character beside the same field carrying an inert character of the same length, by asking which parser the route hands the body to, and by asking on a declared channel whether the parser resolves an identifier it was handed.

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

- to `refuted`: at least 1 refutes `error_detail` observation(s) from a `variant`
- to `supported`: at least 1 supports `response_invariant` observation(s) from a `control`
- to `supported`: at least 1 supports `error_detail` observation(s) from a `variant`

## Provenance

Written for ticket 53 as the v2 replacement for v1's structured-injection pack against the document_parser leaf of the ticket 18 vocabulary; the pack's two pages are attached as maintainer references. Rewritten for ticket 101 against the merged ledger, which carries nine readings and two blocks for this slug. One key moved. The refuted variant row leaves response_invariant for error_detail, the kind the supported row of that same role names, because close_test_replay derives the kind from the specification and one role writes one kind whichever way the reading goes. bb:triggers_all is left alone and the closing section names its gap instead, because four of the nine readings establish xml_request rather than requiring it, while widening the trigger to a body parameter on a state-changing route would make this Playbook match every write in the catalogue. The blanket refusal of every entity declaration is superseded there too. The two out-of-band readings merge into one section that stops at an arrival.

## Maintainer references

- [smtp-header-injection.md](/references/structured-injection--smtp-header-injection.md)[^structured-injection--smtp-header-injection]
- [xpath-injections.md](/references/structured-injection--xpath-injections.md)[^structured-injection--xpath-injections]

[^structured-injection--smtp-header-injection]: SMTP header injection: the newline that ends a field
[^structured-injection--xpath-injections]: XPath injection: the query half of the document parser

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/structured-injection/playbook.md`](../../../src/redkraken/playbooks/structured-injection/playbook.md). This concept describes that document and never replaces it.
