---
type: Skill
title: "browser-evidence"
description: "Take evidence through a scripted browser mission that runs behind the proxy. Use when the behaviour under test needs a rendered page, a script-driven request, or a stored session that a raw exchange cannot produce."
resource: ../../../src/redkraken/skills/browser-evidence/SKILL.md
tags: [skill, browser_run_evidence]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: stable
stale_after: 2027-08-28T00:00:00Z
bb:roles: [web_hunter]
bb:evidence_profile: browser_run_evidence
bb:version: ed4b8fce0ca80c16777d3cfbb18ff66d24ec010299e772f921313f806f7192aa
bb:sha256: 2bd89d68d635be315c870de85e6a1007ec819c0ebcf38d7d3d1fbc07c138ea26
---

# Take evidence through a scripted browser mission that runs behind the proxy. Use when the behaviour under test needs a rendered page, a script-driven request, or a stored session that a raw exchange cannot produce.

## Which roles may load it

- `web_hunter`

## What it may call

- `Skill`
- `mcp__rk2__browse`
- `mcp__rk2__get_artifact`
- `mcp__rk2__get_attack_surface`
- `mcp__rk2__get_evidence`
- `mcp__rk2__get_hypotheses`
- `mcp__rk2__get_receipts`
- `mcp__rk2__run_skill_script`
- `mcp__rk2__submit_mission_result`

## Playbooks that load it

- [browser-framing](/playbooks/browser-framing.md)
- [browser-messaging](/playbooks/browser-messaging.md)
- [browser-script](/playbooks/browser-script.md)
- [browser-storage](/playbooks/browser-storage.md)
- [client-side-path-traversal](/playbooks/client-side-path-traversal.md)
- [cookies](/playbooks/cookies.md)
- [file-upload](/playbooks/file-upload.md)
- [kubernetes](/playbooks/kubernetes.md)
- [logging](/playbooks/logging.md)
- [oauth](/playbooks/oauth.md)
