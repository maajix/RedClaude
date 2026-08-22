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

This run acts as one Identity and does not choose which: whichever the Task was
opened under. The label is on the Receipt of every exchange the run makes --
`identity_label`, the `IDN` label of the Identity Entity -- so it is read after
the first call rather than named before it. Hold the URL, method, query shape,
and body constant across the comparison.

A comparison across two Identities is two Tasks, one opened under each, and the
differential is made by comparing their Receipts. The unauthenticated half is a
Task opened with no Identity at all, not a call that leaves a field out.

Complete this step with the label this run is acting as and the one
authorization dimension being tested. Use labels only; leave slot references and
credential values outside the request.

## 2. Spend the lease

Call `mcp__rk2__http_request`. There is no argument for the Identity and there
will not be one: the runtime chose the slot when it opened the Tool run, the
schema this tool is served with is closed, and a call naming one is refused
before a handler sees it. Send only target semantics in the request headers and
body; authentication fields belong to the proxy.

```json
{"url":"https://target.example/path","method":"GET"}
```

Treat every redirect and subresource as a new call through the same proxy, which
spends the same Identity: one Tool run authorises them all and resolves one slot
for every one of them. Complete this step when every exchange has its own
allowed Receipt.

## 3. Read the evidence

Bind each observation to its Receipt. Check that the Receipt attributes the
Identity this run was opened under, status, and agent-view hashes. For an
Identity call, all target-controlled response headers, reason text, and body
bytes stay in the sealed wire view; status is the only target response semantic
available to the Agent.

The immutable Receipt keeps request/response wire-view hashes and, for mTLS, a
public-certificate hash for operator audit. When those fields are not in the
Agent's bounded projection, cite the Receipt label and report them as withheld,
not absent.

For a two-Identity differential, compare status and Receipt evidence one
variable at a time and cite both Receipts. Treat the encrypted wire view as
evidence named by hash, not content available to the Agent.

## 4. Stop on a fence refusal

A missing, expired, or already-held lease and an unprovisioned slot are control
conditions. Preserve the refusal, report the label the Task was opened under,
and return the Task for operator or scheduler action. Complete the run without
substituting a different label or moving authentication into request fields; the
authenticated comparison remains inconclusive.
