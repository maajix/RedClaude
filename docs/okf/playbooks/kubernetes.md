---
type: Playbook
title: "kubernetes"
description: "Ask whether an operational endpoint meant for the platform that runs an application answers callers of the application's own ingress, by requesting the endpoint with nothing presented and reading whether what comes back describes the workload rather than the application."
resource: ../../../src/redkraken/playbooks/kubernetes/playbook.md
tags: [information_disclosure, constrained, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-05-15T00:00:00Z
bb:category: information_disclosure
bb:outputs: [information_disclosure.workload_metadata]
bb:triggers_all: [read_method, tech_orchestrator, unknown_auth_endpoint]
bb:skills: [compare-responses, handle-untrusted-content]
bb:risk: constrained
bb:effects: read_only
bb:baseline: none
bb:version: cc9fe1b123c3cb821dfc9bc3db166aa4a5011545d1061df8e846db4690896cf3
bb:sha256: f4539409f24e4d1200d6dd2ff7f7b26f85387de8e778440f4714df5b50c2ba5e
---

# Ask whether an operational endpoint meant for the platform that runs an application answers callers of the application's own ingress, by requesting the endpoint with nothing presented and reading whether what comes back describes the workload rather than the application.

## What it concludes about

- `information_disclosure.workload_metadata`

## When it is selected

A subject carrying every one of these facts:

- `read_method`
- `tech_orchestrator`
- `unknown_auth_endpoint`

Risk `constrained`, effects `read_only`, baseline `none`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)
- [handle-untrusted-content](/skills/handle-untrusted-content.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `content_match` observation(s) from a `variant`
- to `supported`: at least 1 supports `response_invariant` observation(s) from a `control`
- to `supported`: at least 1 supports `content_match` observation(s) from a `variant`

## Provenance

Written for ticket 55 as the v2 replacement for v1's kubernetes page against a new workload_metadata leaf added by ticket 55; the v1 page carried no attachments, and its cluster enumeration, its service-account theft and its node reconnaissance are refused by step 6.

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/kubernetes/playbook.md`](../../../src/redkraken/playbooks/kubernetes/playbook.md). This concept describes that document and never replaces it.
