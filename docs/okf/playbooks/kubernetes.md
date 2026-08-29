---
type: Playbook
title: "kubernetes"
description: "Ask whether an operational endpoint meant for the platform that runs an application answers callers of the application's own ingress, by reading with a tool whether the unauthenticated body describes the workload rather than the application, and by asking at most three of that platform's convention route names against a fabricated name of the same shape."
resource: ../../../src/redkraken/playbooks/kubernetes/playbook.md
tags: [information_disclosure, constrained, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-05-15T00:00:00Z
bb:category: information_disclosure
bb:outputs: [information_disclosure.workload_metadata]
bb:triggers_all: [read_method, tech_orchestrator, unknown_auth_endpoint]
bb:skills: [browser-evidence, compare-responses, handle-untrusted-content]
bb:risk: constrained
bb:effects: read_only
bb:baseline: none
bb:version: b33a38c5f26278de2548341609525366158cedb20dba3e979f545a4b21dbfbce
bb:sha256: 588a9f513e5f1c0c9d73801ec006046a09112176e3b2fa75a83025b33dce1cb3
---

# Ask whether an operational endpoint meant for the platform that runs an application answers callers of the application's own ingress, by reading with a tool whether the unauthenticated body describes the workload rather than the application, and by asking at most three of that platform's convention route names against a fabricated name of the same shape.

## What it concludes about

- `information_disclosure.workload_metadata`

## When it is selected

A subject carrying every one of these facts:

- `read_method`
- `tech_orchestrator`
- `unknown_auth_endpoint`

Risk `constrained`, effects `read_only`, baseline `none`.

## Skills it loads

- [browser-evidence](/skills/browser-evidence.md)
- [compare-responses](/skills/compare-responses.md)
- [handle-untrusted-content](/skills/handle-untrusted-content.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `content_match` observation(s) from a `variant`
- to `supported`: at least 1 supports `response_invariant` observation(s) from a `control`
- to `supported`: at least 1 supports `content_match` observation(s) from a `variant`

## Provenance

Written for ticket 55 as the v2 replacement for v1's kubernetes page against a new workload_metadata leaf added by ticket 55; the v1 page carried no attachments, and its cluster enumeration, its service-account theft and its node reconnaissance are refused by the closing section. Rewritten for ticket 101 against the merged ledger's four readings for this slug. One is a procedure, one is a lead that stops at an Observation because content_match is agent-filed, and two are named in the closing section as refused. browser-evidence joins the skills because the non-JSON reader is a browse mission and a browse run is the tool_run that content_match cites.

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/kubernetes/playbook.md`](../../../src/redkraken/playbooks/kubernetes/playbook.md). This concept describes that document and never replaces it.
