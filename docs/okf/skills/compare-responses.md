---
type: Skill
title: "compare-responses"
description: "Difference two stored responses deterministically and cite the difference rather than describe it. Use when a baseline and a variant exchange have both been recorded and the claim depends on what changed between them."
resource: ../../../src/redkraken/skills/compare-responses/SKILL.md
tags: [skill, identity_differential]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: stable
stale_after: 2027-08-28T00:00:00Z
bb:roles: [web_hunter]
bb:evidence_profile: identity_differential
bb:version: 310522bf12380535f5741d8feaa76c75e2dfe66a68936d0fbced8290b09b5fa2
bb:sha256: 5f0b023bd866c91f580d0db1ca6107abc0f5e41a9d1502d65020ef1ad47f1429
---

# Difference two stored responses deterministically and cite the difference rather than describe it. Use when a baseline and a variant exchange have both been recorded and the claim depends on what changed between them.

## Which roles may load it

- `web_hunter`

## What it may call


## Scripts it owns

- `compare.py`

## Playbooks that load it

- [agentic-ai](/playbooks/agentic-ai.md)
- [api](/playbooks/api.md)
- [api-authorization](/playbooks/api-authorization.md)
- [authentication](/playbooks/authentication.md)
- [browser-framing](/playbooks/browser-framing.md)
- [browser-realtime](/playbooks/browser-realtime.md)
- [browser-script](/playbooks/browser-script.md)
- [browser-storage](/playbooks/browser-storage.md)
- [client-side-path-traversal](/playbooks/client-side-path-traversal.md)
- [cms](/playbooks/cms.md)
- [command-directory-injection](/playbooks/command-directory-injection.md)
- [deployment](/playbooks/deployment.md)
- [deserialization](/playbooks/deserialization.md)
- [exceptional-conditions](/playbooks/exceptional-conditions.md)
- [external-resources](/playbooks/external-resources.md)
- [file-resolution](/playbooks/file-resolution.md)
- [file-upload](/playbooks/file-upload.md)
- [graphql](/playbooks/graphql.md)
- [grpc](/playbooks/grpc.md)
- [http-desync](/playbooks/http-desync.md)
- [identity-lifecycle](/playbooks/identity-lifecycle.md)
- [identity-parsing](/playbooks/identity-parsing.md)
- [information-disclosure](/playbooks/information-disclosure.md)
- [jwt-jose](/playbooks/jwt-jose.md)
- [kubernetes](/playbooks/kubernetes.md)
- [logging](/playbooks/logging.md)
- [nosql-injection](/playbooks/nosql-injection.md)
- [oauth](/playbooks/oauth.md)
- [object-ownership](/playbooks/object-ownership.md)
- [orm](/playbooks/orm.md)
- [payment-workflows](/playbooks/payment-workflows.md)
- [race-conditions](/playbooks/race-conditions.md)
- [realtime](/playbooks/realtime.md)
- [request-integrity](/playbooks/request-integrity.md)
- [request-parsing](/playbooks/request-parsing.md)
- [routing](/playbooks/routing.md)
- [secrets](/playbooks/secrets.md)
- [spreadsheet-injection](/playbooks/spreadsheet-injection.md)
- [sql-injection](/playbooks/sql-injection.md)
- [ssrf-url-routing](/playbooks/ssrf-url-routing.md)
- [ssti](/playbooks/ssti.md)
- [structured-injection](/playbooks/structured-injection.md)
- [web-cache](/playbooks/web-cache.md)
- [webauthn](/playbooks/webauthn.md)
- [webhooks](/playbooks/webhooks.md)
- [workload-identities](/playbooks/workload-identities.md)
