---
type: Playbook
title: "spreadsheet-injection"
description: "Ask whether the export writer emits a caller-chosen value into a cell without the leading apostrophe that would make it text, by fetching the export before anything is written, storing one record whose value begins with a formula character and one whose value does not, fetching the export twice more, and differencing the files so both new rows come back whole with the character before each still attached."
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
bb:version: 0d427bbfbd8b2971ac34bdce34a7fa3642176b9669d5fd77049ae6eaf82ffa05
bb:sha256: 5c820e1870f1186e4986f434b7ad8e15bd9535d2b71e10f939ce204e9248cd9d
---

# Ask whether the export writer emits a caller-chosen value into a cell without the leading apostrophe that would make it text, by fetching the export before anything is written, storing one record whose value begins with a formula character and one whose value does not, fetching the export twice more, and differencing the files so both new rows come back whole with the character before each still attached.

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

Written for ticket 53 as the v2 replacement for v1's spreadsheet-injection page, against a new formula leaf added by ticket 53 because the interpreter is the spreadsheet application on a reader's machine rather than anything the target runs; no upstream card. Rewritten for ticket 101 against the merged ledger, which carries one reading, one blocked container and one refusal for this slug and no row that reaches a Finding, which is why this document says so at the top. No mining shard targeted the slug, so the reading comes from this Playbook's own body and the OWASP page; a sweep of all 665 mined rows by text matched one, the OOXML importer, which is the blocked container named in the closing section. The shipped step 4 said the export is examined by a registered tool run and named none, and no registered tool matches a declared pattern inside one text Artifact, so the reading becomes a difference of two exports over compare-responses. Nothing in the frontmatter moved but the description and this line.

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/spreadsheet-injection/playbook.md`](../../../src/redkraken/playbooks/spreadsheet-injection/playbook.md). This concept describes that document and never replaces it.
