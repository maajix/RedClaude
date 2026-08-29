---
type: Playbook
title: "logging"
description: "Ask whether an activity, audit or trace view hands one caller the request data of another, by having a second Identity send one marked read and then looking for that marker in the view the first Identity is served, with the second Identity's own view as the leg that says the marker was recorded at all."
resource: ../../../src/redkraken/playbooks/logging/playbook.md
tags: [information_disclosure, constrained, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-05-15T00:00:00Z
bb:category: information_disclosure
bb:outputs: [information_disclosure.log_record]
bb:triggers_all: [authenticated_endpoint, multiple_test_identities, tech_telemetry]
bb:skills: [browser-evidence, compare-responses, use-identity]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:version: 2910a5facc749b00b856b4f830296421f8041f7ce33595ad2effabee3fe618a0
bb:sha256: eb9410ba7be556c16e59d91efeb01585cab580c22b4a340fa1f3695718827996
---

# Ask whether an activity, audit or trace view hands one caller the request data of another, by having a second Identity send one marked read and then looking for that marker in the view the first Identity is served, with the second Identity's own view as the leg that says the marker was recorded at all.

## What it concludes about

- `information_disclosure.log_record`

## When it is selected

A subject carrying every one of these facts:

- `authenticated_endpoint`
- `multiple_test_identities`
- `tech_telemetry`

Risk `constrained`, effects `read_only`, baseline `stable_session`.

## Skills it loads

- [browser-evidence](/skills/browser-evidence.md)
- [compare-responses](/skills/compare-responses.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `content_match` observation(s) from a `variant`
- to `supported`: at least 1 supports `content_match` observation(s) from a `control`
- to `supported`: at least 1 supports `content_match` observation(s) from a `variant`

## Provenance

Written for ticket 55 as the v2 replacement for v1's logging page against a new log_record leaf added by ticket 55; the v1 page carried no attachments, and its log-forging payloads, its log-file fetching and its alerting-evasion advice are refused by the closing section. Rewritten for ticket 101 against the merged ledger, which carries four readings here and grades none of them as reaching a Finding -- two refused by this Playbook's own decision and two that stop at an Observation. One key moved. bb:skills gains browser-evidence, because the HTML view is read by a browse run and the shipped text named the kind that run produces without naming the run. bb:evidence is unchanged and stays content_match on all three legs, which is what both lanes actually file; it is also a bar no closing writer produces, and the rewrite states that in the body as a standing defect rather than swapping in a kind no step of this Playbook can reach.

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/logging/playbook.md`](../../../src/redkraken/playbooks/logging/playbook.md). This concept describes that document and never replaces it.
