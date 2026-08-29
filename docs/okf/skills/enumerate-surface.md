---
type: Skill
title: "enumerate-surface"
description: "Turn a scope root into typed, deduplicated Attack Surface. Use when a Program has hosts or roots nothing has been recorded against yet, or when a deploy changed and the recorded surface needs to be re-derived rather than trusted."
resource: ../../../src/redkraken/skills/enumerate-surface/SKILL.md
tags: [skill, allowed_receipt_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: stable
stale_after: 2027-08-28T00:00:00Z
bb:roles: [recon, web_hunter]
bb:evidence_profile: allowed_receipt_only
bb:version: 04c24c78373a98119d934e05295fe611647bee75656e332571be93b586162179
bb:sha256: b02ce721596b927984448d2503fd3a5e47db58263f5ebd389c112a40f6c86116
---

# Turn a scope root into typed, deduplicated Attack Surface. Use when a Program has hosts or roots nothing has been recorded against yet, or when a deploy changed and the recorded surface needs to be re-derived rather than trusted.

## Which roles may load it

- `recon`
- `web_hunter`

## What it may call


Runtime tools it reaches through `run_tool`:

- `jq`
- `js_map`
- `js_parse`
- `js_routes`

## Playbooks that load it

- [api](/playbooks/api.md)
- [api-authorization](/playbooks/api-authorization.md)
- [attack-surface](/playbooks/attack-surface.md)
- [authentication](/playbooks/authentication.md)
- [exceptional-conditions](/playbooks/exceptional-conditions.md)
- [external-resources](/playbooks/external-resources.md)
- [information-disclosure](/playbooks/information-disclosure.md)
- [oauth](/playbooks/oauth.md)
- [request-parsing](/playbooks/request-parsing.md)
