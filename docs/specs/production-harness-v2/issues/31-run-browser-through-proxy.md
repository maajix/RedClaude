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
   and the only rows behind it are Receipts the production fence wrote. The
   fixture page is more than a navigation on purpose: it pulls a script
   subresource, calls `fetch`, and opens a websocket, on each of its two
   renders, and `test_the_subresources_the_fetch_and_the_socket_are_receipts_too`
   holds each of the eight requests against the Receipt behind it by path. The
   websocket is an initiation and stays one — the door drops the upgrade header,
   so the handshake reaches the twin as an ordinary GET and the page settles it
   as refused. That is the criterion met rather than dodged: a websocket the
   door could not read would be exactly the second egress path this forbids, and
   the initiation is receipted either way.
2. The namespace is the seam `isolation` owns, and it is proven at that seam by
   `test_a_tool_on_the_proxy_adapter_gets_its_own_network_and_gives_it_back`:
   the adapter is created per run, holds exactly one peer, and is removed
   afterwards. Both halves are probed there — no TCP to the target's address or
   to the internet, and no name resolving for the target or for a public host —
   because the browser reaches the network through `run_tool(network="proxy")`
   and nothing else, so that is the seam the claim has to hold at.
   `BrowserCommandTest` runs over it with the twins on a network the browser is
   not attached to.
3. The Identity slot is named in the plan and resolved at the door, never in the
   container. `BrowserCommandTest` provisions the Program's required header
   value under a root secret only the door holds, and the fixture twins answer
   403 without it — so a mission that saw a page is a mission whose door opened
   a credential the browser never had, and the two assertions on the marker show
   it is in no Artifact and no Receipt the Agent can read. The slot itself is
   held both ways in `BrowserMissionTest`: a slot the run does not lease is
   refused before a container exists, and a slot it does lease is written to
   `tool_runs.args`, which is the one place `resolve_egress_identity` looks. It
   is inside `plan_sha256` as well, so the same steps under a different Identity
   are a different mission.
4. `tool_run_artifacts` carries the producing step's ordinal for the three
   per-step streams and none for the console, which belongs to the mission. The
   bytes are filed by content hash through the same `artifact.filed` every other
   Artifact goes through. The join to the Receipts is the Tool run and the step
   ordinal rather than a `receipts.id` column, and deliberately: a captured
   document is what a navigation and every subresource under it became, so there
   is no one Receipt to name — the run here has eight for two captures — and a
   screenshot has none at all. A column would have to hold one of the eight or
   nothing, and either answer is worse than the honest join. What the criterion
   asks is that evidence and requests be attributable to each other, and
   `test_what_it_kept_and_what_the_door_let_through_meet_on_one_run` is that
   attribution: every Artifact and every Receipt this Program holds hangs off
   one of the two missions and nothing else.
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
