---
type: Playbook
title: "logging"
description: "Ask whether an activity, audit or trace view hands one caller the request data of another, by having a second Identity send one marked read and then looking for that marker in the view the first Identity is served, with the second Identity's own view as the control that says the marker was recorded at all."
resource: ../../../src/redkraken/playbooks/logging/playbook.md
tags: [information_disclosure, constrained, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-05-15T00:00:00Z
bb:category: information_disclosure
bb:outputs: [information_disclosure.log_record]
bb:triggers_all: [authenticated_endpoint, multiple_test_identities, tech_telemetry]
bb:skills: [compare-responses, use-identity]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:version: 7c5ec989d51361aa873316f4cc2e3342d783139c604f7b4bf7f9496493b18989
bb:sha256: ad2a91b737b7e0346231a4e053bd0bdf741a3bcd1e979b7e8d107102d15bdafd
---

# Ask whether an activity, audit or trace view hands one caller the request data of another, by having a second Identity send one marked read and then looking for that marker in the view the first Identity is served, with the second Identity's own view as the control that says the marker was recorded at all.

## What it concludes about

- `information_disclosure.log_record`

## When it is selected

A subject carrying every one of these facts:

- `authenticated_endpoint`
- `multiple_test_identities`
- `tech_telemetry`

Risk `constrained`, effects `read_only`, baseline `stable_session`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `content_match` observation(s) from a `variant`
- to `supported`: at least 1 supports `content_match` observation(s) from a `control`
- to `supported`: at least 1 supports `content_match` observation(s) from a `variant`

## Provenance

Written for ticket 55 as the v2 replacement for v1's logging page against a new log_record leaf added by ticket 55; the v1 page carried no attachments, and its log-forging payloads, its log-file fetching and its alerting-evasion advice are refused by step 7.

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/logging/playbook.md`](../../../src/redkraken/playbooks/logging/playbook.md). This concept describes that document and never replaces it.
