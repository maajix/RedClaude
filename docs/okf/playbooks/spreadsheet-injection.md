---
type: Playbook
title: "spreadsheet-injection"
description: "Ask whether a stored field is written into an exported spreadsheet without a leading apostrophe, by saving one record whose value begins with a formula character and one whose value does not and matching both inside the downloaded export."
resource: ../../../src/redkraken/playbooks/spreadsheet-injection/playbook.md
tags: [injection, approval_required, mutates_object]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-03-15T00:00:00Z
bb:category: injection
bb:outputs: [injection.formula]
bb:triggers_all: [form_request, reflected_parameter, state_changing_method]
bb:skills: [compare-responses, handle-untrusted-content, use-identity]
bb:risk: approval_required
bb:effects: mutates_object
bb:baseline: stable_session
bb:version: 17cb7128c9909a968f4d2cb1d86fef965a5615a67b5a6c64c5ee85da241710c8
bb:sha256: d807336891d7ed9b51dbb3c18e4873cabad919350671548214da971a11a521ca
---

# Ask whether a stored field is written into an exported spreadsheet without a leading apostrophe, by saving one record whose value begins with a formula character and one whose value does not and matching both inside the downloaded export.

## What it concludes about

- `injection.formula`

## When it is selected

A subject carrying every one of these facts:

- `form_request`
- `reflected_parameter`
- `state_changing_method`

Risk `approval_required`, effects `mutates_object`, baseline `stable_session`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)
- [handle-untrusted-content](/skills/handle-untrusted-content.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `content_match` observation(s) from a `variant`
- to `supported`: at least 1 supports `content_match` observation(s) from a `control`
- to `supported`: at least 1 supports `content_match` observation(s) from a `variant`

## Provenance

Written for ticket 53 as the v2 replacement for v1's spreadsheet-injection page, against a new formula leaf added by ticket 53 because the interpreter is the spreadsheet application on a reader's machine rather than anything the target runs; no upstream card.

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/spreadsheet-injection/playbook.md`](../../../src/redkraken/playbooks/spreadsheet-injection/playbook.md). This concept describes that document and never replaces it.
