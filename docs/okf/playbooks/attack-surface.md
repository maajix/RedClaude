---
type: Playbook
title: "attack-surface"
description: "Ask whether a document the application never meant to publish is reachable, by requesting candidate artifact paths and differencing each answer against a path that certainly does not exist."
resource: ../../../src/redkraken/playbooks/attack-surface/playbook.md
tags: [information_disclosure, constrained, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-02-15T00:00:00Z
bb:category: information_disclosure
bb:outputs: [information_disclosure.artifact_exposure]
bb:triggers_all: [read_method, unauthenticated_endpoint]
bb:skills: [enumerate-surface, handle-untrusted-content]
bb:risk: constrained
bb:effects: read_only
bb:baseline: none
bb:version: 996a2a777ec1be2b26b4fc8ce7efd2b5598861a6a67e76d3150482c547442878
bb:sha256: 3dee75e495645aebef9ce68ed2b65263c3d2b815575ebd8cdd21ab6e12aa57a7
sources:
  - id: attack-surface--auto-scanners
    resource: /references/attack-surface--auto-scanners.md
    title: "Automated scanners, and why this harness is not one"
    author: human:maintainer
  - id: attack-surface--cves
    resource: /references/attack-surface--cves.md
    title: "Known vulnerabilities, versions, and what this corpus does with them"
    author: human:maintainer
  - id: attack-surface--ffuf
    resource: /references/attack-surface--ffuf.md
    title: "Content discovery, and what it costs to be wrong about it"
    author: human:maintainer
---

# Ask whether a document the application never meant to publish is reachable, by requesting candidate artifact paths and differencing each answer against a path that certainly does not exist.

## What it concludes about

- `information_disclosure.artifact_exposure`

## When it is selected

A subject carrying every one of these facts:

- `read_method`
- `unauthenticated_endpoint`

Risk `constrained`, effects `read_only`, baseline `none`.

## Skills it loads

- [enumerate-surface](/skills/enumerate-surface.md)
- [handle-untrusted-content](/skills/handle-untrusted-content.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `response_differential` observation(s) from a `variant`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `control`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `variant`

## Provenance

Written for ticket 49 as the v2 replacement for v1's attack-surface pack, against the artifact-exposure leaf of the ticket 18 vocabulary; the three v1 texts are attached as maintainer references and none of them is the source of this class. Rewritten for ticket 101 against the merged ledger, which carries eleven readings, one lead and seven refusals for this slug. No frontmatter key moved, because all three evidence rows already name response_differential and so the refuted row is reachable as written.

## Maintainer references

- [auto-scanners.md](/references/attack-surface--auto-scanners.md)[^attack-surface--auto-scanners]
- [cves.md](/references/attack-surface--cves.md)[^attack-surface--cves]
- [ffuf.md](/references/attack-surface--ffuf.md)[^attack-surface--ffuf]

[^attack-surface--auto-scanners]: Automated scanners, and why this harness is not one
[^attack-surface--cves]: Known vulnerabilities, versions, and what this corpus does with them
[^attack-surface--ffuf]: Content discovery, and what it costs to be wrong about it

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/attack-surface/playbook.md`](../../../src/redkraken/playbooks/attack-surface/playbook.md). This concept describes that document and never replaces it.
