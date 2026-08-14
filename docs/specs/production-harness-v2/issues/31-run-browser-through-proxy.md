# 31 — Run a browser entirely through the proxy

**What to build:** Execute one browser Mission against a synthetic SPA and capture attributable navigation, request, DOM and screenshot evidence without creating a second egress path.

**Blocked by:** 11 — Close direct-egress, DNS, redirect and subresource bypasses; 12 — Use an Identity without exposing credentials; 20 — Run one Task to a canonical Observation.

**Status:** resolved

- [x] Browser navigation, XHR, fetch, websocket initiation and subresources use the production proxy and independently checked Receipts.
- [x] The browser process cannot resolve or reach the target or internet directly from its network namespace.
- [x] Identity selection uses the proxy-side slot and no cookie, authorization value or client credential is exposed to the Agent.
- [x] DOM, screenshot, console and declared probe outputs become content-addressed Artifacts linked to the producing Receipts and Tool run.
- [x] Canonical step outcomes and assertion results produce a stable digest that excludes timestamps, nonces, generated identifiers and screenshot bytes.
- [x] Secure and vulnerable fixture twins prove that replay distinguishes behavior rather than merely reproducing a recording.

## How each is met

1. The plan is compiled by `open_browser_run` before any container starts, and
   the browser is launched by `isolation.run_tool(network="proxy")`, which gives
   it a fresh `--internal` network whose only peer is the door and blackholed
   DNS. Every request the page makes is therefore the door's to admit or refuse.
   `check_browser_runs` holds the count the browser reported against the
   Receipts the door wrote, in the one direction that is a fault: fewer Receipts
   than counted requests is bytes that left another way. Proven end to end in
   `BrowserCommandTest`, where a real Chrome walks a plan against two containers
   and the only rows behind it are Receipts the production fence wrote.
2. The namespace is the seam `isolation` owns, and it is proven at that seam by
   `test_a_tool_on_the_proxy_adapter_gets_its_own_network_and_gives_it_back`:
   the adapter is created per run, holds exactly one peer, and is removed
   afterwards. `BrowserCommandTest` runs over it with the twins on a network the
   browser is not attached to.
3. The Identity slot is named in the plan and resolved at the door, never in the
   container. `BrowserCommandTest` provisions the Program's required header
   value under a root secret only the door holds, and the fixture twins answer
   403 without it — so a mission that saw a page is a mission whose door opened
   a credential the browser never had, and the two assertions on the marker show
   it is in no Artifact and no Receipt the Agent can read.
4. `tool_run_artifacts` carries the producing step's ordinal for the three
   per-step streams and none for the console, which belongs to the mission. The
   bytes are filed by content hash through the same `artifact.filed` every other
   Artifact goes through. The join to the Receipts is the Tool run, because a
   captured document is what a navigation and its subresources became rather
   than the product of one request.
5. `browser_run_digest` digests each step's ordinal, action and outcome. The
   outcome keys are the registry's, per action, and the values are canonical, so
   a timestamp or an identifier cannot enter one — it is excluded by what a row
   may contain rather than by filtering. `check_browser_runs` holds each stored
   digest against a recomputation.
6. The twins differ in one line: one writes back what was typed and the other
   escapes it. Both missions walk one plan and agree on `plan_sha256`; their
   `result_digest` values differ, and the differing step is the probe verdict —
   `reflected` against one twin and `escaped` against the other. The verdict is
   read off the rendered page by the probe's own script, so it is a measurement
   of behaviour and not a replayed recording.
