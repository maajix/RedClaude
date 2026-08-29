---
type: Playbook
title: "supply-chain"
description: "Ask whether the build published the application's dependency boundary alongside its bundles, by reading the shell for the bundles it actually loads, following each bundle's own source-map pointer, and sorting the manifest's names into the ones the public already has and the ones that exist only inside the organisation."
resource: ../../../src/redkraken/playbooks/supply-chain/playbook.md
tags: [information_disclosure, constrained, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-05-15T00:00:00Z
bb:category: information_disclosure
bb:outputs: [information_disclosure.dependency_manifest]
bb:triggers_all: [read_method, spa_surface, tech_build_manifest]
bb:skills: [analyse-source, handle-untrusted-content]
bb:risk: constrained
bb:effects: read_only
bb:baseline: none
bb:version: d7540365eaa504272a1c506f23ce69323f6038144d4423f5188e828a6d45dff9
bb:sha256: c8d5c69284f731bf9133b464f4a36237b627983266f04460c296dbf915368cc7
---

# Ask whether the build published the application's dependency boundary alongside its bundles, by reading the shell for the bundles it actually loads, following each bundle's own source-map pointer, and sorting the manifest's names into the ones the public already has and the ones that exist only inside the organisation.

## What it concludes about

- `information_disclosure.dependency_manifest`

## When it is selected

A subject carrying every one of these facts:

- `read_method`
- `spa_surface`
- `tech_build_manifest`

Risk `constrained`, effects `read_only`, baseline `none`.

## Skills it loads

- [analyse-source](/skills/analyse-source.md)
- [handle-untrusted-content](/skills/handle-untrusted-content.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `content_match` observation(s) from a `variant`
- to `supported`: at least 1 supports `content_match` observation(s) from a `control`
- to `supported`: at least 1 supports `content_match` observation(s) from a `variant`

## Provenance

Written for ticket 55 as the v2 replacement for v1's supply-chain page against a new dependency_manifest leaf added by ticket 55, and rewritten for ticket 101 against the merged ledger's three readings for this slug. The change of substance is that content_match now names the binary that produces it -- js_parse for a bundle's pointer, js_map for a manifest index, jq where the manifest is plain JSON, all with tool_run provenance. Repaired again in review, where the body named a fetch verb and a park verb the executing role does not hold -- analyse-source is granted to js_analyst alone, which holds state.read, state.propose and exec.tool_run and nothing else, so every byte read here is now an Artifact an earlier run stored, the one reading that needs a request is proposed as a Test the replay lane performs, and a halt is written into the Task's own record. The v1 page's dependency-confusion publishing, its registry probing and its version-to-CVE tables stay refused.

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/supply-chain/playbook.md`](../../../src/redkraken/playbooks/supply-chain/playbook.md). This concept describes that document and never replaces it.
