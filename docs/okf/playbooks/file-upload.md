---
type: Playbook
title: "file-upload"
description: "Ask whether the name a caller gives an upload decides how the server later serves it back, by storing identical bytes twice under names that differ only in extension, retrieving both, and differencing the two stored retrievals against a retrieval that was itself invariant."
resource: ../../../src/redkraken/playbooks/file-upload/playbook.md
tags: [injection, approval_required, mutates_object]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-04-15T00:00:00Z
bb:category: injection
bb:outputs: [injection.stored_file]
bb:triggers_all: [file_parameter, path_valued_parameter, state_changing_method]
bb:skills: [compare-responses, use-identity]
bb:risk: approval_required
bb:effects: mutates_object
bb:baseline: stable_session
bb:version: 05304b9dff594779248593a53079acaac9d3f99d8112db5210e2baf73ddb5a8a
bb:sha256: 0c40be4e29de6c84c8f599105a5f9dac77c587a4e6f84f5fd5a059cc719f8f63
sources:
  - id: file-upload--file-upload
    resource: /references/file-upload--file-upload.md
    title: "File upload: the shell, and the two bytes that prove it without one"
    author: human:maintainer
---

# Ask whether the name a caller gives an upload decides how the server later serves it back, by storing identical bytes twice under names that differ only in extension, retrieving both, and differencing the two stored retrievals against a retrieval that was itself invariant.

## What it concludes about

- `injection.stored_file`

## When it is selected

A subject carrying every one of these facts:

- `file_parameter`
- `path_valued_parameter`
- `state_changing_method`

Risk `approval_required`, effects `mutates_object`, baseline `stable_session`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `response_invariant` observation(s) from a `variant`
- to `supported`: at least 1 supports `response_invariant` observation(s) from a `control`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `variant`

## Provenance

Written for ticket 54 as the v2 replacement for v1's file-upload page against a new stored_file leaf added by ticket 54; the v1 text is attached as a maintainer reference and its shells, its polyglots and its overwrite techniques are refused by step 7.

## Maintainer references

- [file-upload.md](/references/file-upload--file-upload.md)[^file-upload--file-upload]

[^file-upload--file-upload]: File upload: the shell, and the two bytes that prove it without one

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/file-upload/playbook.md`](../../../src/redkraken/playbooks/file-upload/playbook.md). This concept describes that document and never replaces it.
