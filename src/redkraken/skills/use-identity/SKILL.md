---
description: Authenticated target requests through a named RedKraken Identity. Use when testing logged-in reachability, comparing two leased Identities, or following redirects and subresources within an authenticated session.
bb:roles: ["web_hunter"]
bb:tool_groups: ["net.request", "state.propose", "state.read"]
bb:evidence_profile: identity_differential
---

# Use an Identity

Run an authenticated differential without handling credentials. The runtime
owns leases; the proxy owns headers, cookies, session state, and wire evidence.

## 1. Fix the differential

Choose an Identity label already supplied in the mission packet or state view.
Hold the URL, method, query shape, and body constant across the comparison.

Complete this step with the label and the one authorization dimension being
tested. Use labels only; leave slot references and credential values outside
the request.

## 2. Spend the lease

Call `mcp__rk2__http_request` with `identity_slot` set to the chosen label. Send
only target semantics in the request headers and body; authentication fields
belong to the proxy.

```json
{"url":"https://target.example/path","method":"GET","identity_slot":"member-a"}
```

Treat every redirect and subresource as a new call through the same proxy with
the same label. Complete this step when every exchange has its own allowed
Receipt.

## 3. Read the evidence

Bind each observation to its Receipt. Check that the Receipt attributes the
selected Identity, status, and agent-view hashes. For an Identity call, all
target-controlled response headers, reason text, and body bytes stay in the
sealed wire view; status is the only target response semantic available to the
Agent.

The immutable Receipt keeps request/response wire-view hashes and, for mTLS, a
public-certificate hash for operator audit. When those fields are not in the
Agent's bounded projection, cite the Receipt label and report them as withheld,
not absent.

For a two-Identity differential, compare status and Receipt evidence one
variable at a time and cite both Receipts. Treat the encrypted wire view as
evidence named by hash, not content available to the Agent.

## 4. Stop on a fence refusal

A missing, expired, or already-held lease and an unprovisioned slot are control
conditions. Preserve the refusal, report the requested label, and return the
Task for operator or scheduler action. Complete the run without substituting a
different label or moving authentication into request fields; the authenticated
comparison remains inconclusive.
