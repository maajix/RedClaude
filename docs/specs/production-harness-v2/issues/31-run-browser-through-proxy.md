# 31 — Run a browser entirely through the proxy

**What to build:** Execute one browser Mission against a synthetic SPA and capture attributable navigation, request, DOM and screenshot evidence without creating a second egress path.

**Blocked by:** 11 — Close direct-egress, DNS, redirect and subresource bypasses; 12 — Use an Identity without exposing credentials; 20 — Run one Task to a canonical Observation.

**Status:** ready-for-agent

- [ ] Browser navigation, XHR, fetch, websocket initiation and subresources use the production proxy and independently checked Receipts.
- [ ] The browser process cannot resolve or reach the target or internet directly from its network namespace.
- [ ] Identity selection uses the proxy-side slot and no cookie, authorization value or client credential is exposed to the Agent.
- [ ] DOM, screenshot, console and declared probe outputs become content-addressed Artifacts linked to the producing Receipts and Tool run.
- [ ] Canonical step outcomes and assertion results produce a stable digest that excludes timestamps, nonces, generated identifiers and screenshot bytes.
- [ ] Secure and vulnerable fixture twins prove that replay distinguishes behavior rather than merely reproducing a recording.
