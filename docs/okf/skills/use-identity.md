---
type: Skill
title: "use-identity"
description: "Authenticated target requests through a named RedKraken Identity. Use when testing logged-in reachability, comparing two leased Identities, or following redirects and subresources within an authenticated session."
resource: ../../../src/redkraken/skills/use-identity/SKILL.md
tags: [skill, identity_differential]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: stable
stale_after: 2027-08-28T00:00:00Z
bb:roles: [web_hunter]
bb:evidence_profile: identity_differential
bb:version: 8e864dc7a95028781e85484d5c840304d1c069d8ab14ffb59c46c35ba56f7585
bb:sha256: c5a93f0c5a17fb057d7e8791b229b4b723e36b529991600fdacdae89545b9e5f
---

# Authenticated target requests through a named RedKraken Identity. Use when testing logged-in reachability, comparing two leased Identities, or following redirects and subresources within an authenticated session.

## Which roles may load it

- `web_hunter`

## What it may call


## Playbooks that load it

- [api](/playbooks/api.md)
- [api-authorization](/playbooks/api-authorization.md)
- [authentication](/playbooks/authentication.md)
- [browser-framing](/playbooks/browser-framing.md)
- [browser-realtime](/playbooks/browser-realtime.md)
- [browser-storage](/playbooks/browser-storage.md)
- [cms](/playbooks/cms.md)
- [command-directory-injection](/playbooks/command-directory-injection.md)
- [cookies](/playbooks/cookies.md)
- [deserialization](/playbooks/deserialization.md)
- [exceptional-conditions](/playbooks/exceptional-conditions.md)
- [file-resolution](/playbooks/file-resolution.md)
- [file-upload](/playbooks/file-upload.md)
- [graphql](/playbooks/graphql.md)
- [grpc](/playbooks/grpc.md)
- [identity-lifecycle](/playbooks/identity-lifecycle.md)
- [identity-parsing](/playbooks/identity-parsing.md)
- [information-disclosure](/playbooks/information-disclosure.md)
- [jwt-jose](/playbooks/jwt-jose.md)
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
- [spreadsheet-injection](/playbooks/spreadsheet-injection.md)
- [sql-injection](/playbooks/sql-injection.md)
- [ssrf-url-routing](/playbooks/ssrf-url-routing.md)
- [ssti](/playbooks/ssti.md)
- [structured-injection](/playbooks/structured-injection.md)
- [web-cache](/playbooks/web-cache.md)
- [webauthn](/playbooks/webauthn.md)
- [workload-identities](/playbooks/workload-identities.md)
