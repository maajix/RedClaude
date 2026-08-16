---
description: Turn a scope root into typed, deduplicated Attack Surface. Use when a Program has hosts or roots nothing has been recorded against yet, or when a deploy changed and the recorded surface needs to be re-derived rather than trusted.
bb:roles: ["recon"]
bb:tool_groups: ["exec.tool_run", "net.request", "state.propose", "state.read"]
bb:evidence_profile: allowed_receipt_only
bb:runtime-tools: ["jq"]
---

# Enumerate a surface

Produce entities and relationships that later work can be scheduled against.
This step decides what exists. It does not decide what is wrong with it.

## 1. Read what is already recorded

Call `mcp__rk2__get_attack_surface` first. Every entity already there is one you
must not propose again under a second label; the deduplication cell is shared,
and a second row for one host is a second queue of work against the same thing.

Complete this step holding the set of roots this Task is for and the set of
entities already recorded under them.

## 2. Reach each root once

Call `mcp__rk2__http_request` per root. One exchange per URL, and every redirect
and subresource is its own call: the Receipt is per exchange, and an entity you
cannot name a Receipt for is an entity you inferred.

Scope is the proxy's decision, not yours. A blocked or deferred Receipt is a
control condition and is reported as one -- it is evidence about the boundary,
not a reason to try a different spelling of the same host.

## 3. Type what came back

Every proposed entity carries the Receipt that showed it and the kind it is.
Where the response is JSON, run `jq` through `mcp__rk2__run_tool` over the
stored Artifact rather than reading the shape out of the body by eye: the run
is recorded, its output is an Artifact, and a route list nobody can re-derive
is a claim.

Complete this step when every proposed entity, relationship and observation
cites a Receipt or a Tool run that this Task actually produced.

## 4. Stop at the edge of enumeration

Do not test. A parameter that looks reflective, an endpoint that looks
unauthenticated and a header that looks stale are surface, and they are recorded
as surface. Proposing a hypothesis about one is the hunter's Task and the
scheduler's decision, and the evidence for it does not exist yet.
