---
type: Playbook
title: "file-upload"
description: "Ask whether the name a caller gives an upload decides what the server later says the stored bytes are, by holding the bytes identical while one store-time signal moves at a time, and by differencing the retrievals of two objects that differ only in the name they were stored under."
resource: ../../../src/redkraken/playbooks/file-upload/playbook.md
tags: [injection, approval_required, mutates_object]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-04-15T00:00:00Z
bb:category: injection
bb:outputs: [injection.stored_file]
bb:triggers_all: [file_parameter, path_valued_parameter, state_changing_method]
bb:skills: [browser-evidence, compare-responses, handle-untrusted-content, use-identity]
bb:risk: approval_required
bb:effects: mutates_object
bb:baseline: stable_session
bb:version: 00d29c8be453335cb2982d6526ff20417e8e8b9d2ea76a5e24a66a1e98b19715
bb:sha256: 429b7ff50647d0fd6f6aeaf2e6a37cdf48b323fb5fd8ad03c34e59d0e069d6fb
sources:
  - id: file-upload--file-upload
    resource: /references/file-upload--file-upload.md
    title: "File upload: the shell, and the two bytes that prove it without one"
    author: human:maintainer
---

# Ask whether the name a caller gives an upload decides what the server later says the stored bytes are, by holding the bytes identical while one store-time signal moves at a time, and by differencing the retrievals of two objects that differ only in the name they were stored under.

## What it concludes about

- `injection.stored_file`

## When it is selected

A subject carrying every one of these facts:

- `file_parameter`
- `path_valued_parameter`
- `state_changing_method`

Risk `approval_required`, effects `mutates_object`, baseline `stable_session`.

## Skills it loads

- [browser-evidence](/skills/browser-evidence.md)
- [compare-responses](/skills/compare-responses.md)
- [handle-untrusted-content](/skills/handle-untrusted-content.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `response_differential` observation(s) from a `variant`
- to `supported`: at least 1 supports `response_invariant` observation(s) from a `control`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `variant`

## Provenance

Written for ticket 54 as the v2 replacement for v1's file-upload page against a new stored_file leaf added by ticket 54; the v1 text is attached as a maintainer reference and its shells, its polyglots and its overwrite techniques are refused by the closing section. Rewritten for ticket 101 against the merged ledger, which carries nine readings that settle a claim, three refusals and one block for this slug. Two keys moved. bb:skills gains handle-untrusted-content, which the stored vector document of section 6 needs, and browser-evidence, which the probe over the rendered listing in the same section needs; both are already held by the role that executes this text. The refuted variant row moves from response_invariant to response_differential, the kind the supported row of that same role names, because close_test_replay derives the kind from the specification and one role writes one kind whichever way the reading goes. Section 6's first reading stops at an Observation and settles nothing.

## Maintainer references

- [file-upload.md](/references/file-upload--file-upload.md)[^file-upload--file-upload]

[^file-upload--file-upload]: File upload: the shell, and the two bytes that prove it without one

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/file-upload/playbook.md`](../../../src/redkraken/playbooks/file-upload/playbook.md). This concept describes that document and never replaces it.
