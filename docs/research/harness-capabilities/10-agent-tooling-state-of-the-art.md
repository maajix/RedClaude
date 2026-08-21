# 10 - What a modern security agent can do, and what ours can

Written against this worktree at the commit this file was added. Every claim
about our own code carries `file:line` and was read there. Every external claim
carries a URL that was fetched; where a page would not fetch it says so.

Framing throughout is authorized testing of a Program's own scope. Nothing here
proposes a primitive whose only use is against a target nobody authorized.

## Our capability set today

The model-facing surface is exactly the fourteen `Contract` entries in
`src/redkraken/roster.py:592-845`. There is no fifteenth: `_check_contracts`
(`roster.py:1719`) refuses a tool group whose members and contracts disagree,
and `_launch.server` (`src/redkraken/_launch.py:530`) builds one handler per
contract and nothing else.

| # | Capability | Where | What it cannot express |
| --- | --- | --- | --- |
| 1 | `get_attack_surface` - typed entity rows the packet reached | `roster.py:593` | cannot read anything outside the packet compiled before the container started |
| 2 | `get_hypotheses` - hypotheses by subject/status | `roster.py:603` | cannot see another Program, another run's reasoning, or a hypothesis nobody staged |
| 3 | `get_evidence` - evidence edges for one H or F | `roster.py:613` | cannot reach the raw bytes; it returns edges, not documents |
| 4 | `get_receipts` - list/fetch Receipts by label | `roster.py:629` | cannot search receipts by host, status or time; no query language |
| 5 | `get_artifact` - list/fetch an Artifact by label, byte range | `roster.py:648` | cannot address by hash, cannot grep; large bodies must go through a tool run |
| 6 | `submit_mission_result` - the one proposal | `roster.py:670` | writes staging only; nothing it says is canonical until the runtime promotes it |
| 7 | `get_slate` - the Tasks this decision may choose between | `roster.py:686` | orchestrator only; cannot see Tasks the runtime did not offer |
| 8 | `pick_task` | `roster.py:696` | a request, not a claim; the runtime re-decides |
| 9 | `request_validation` | `roster.py:702` | cannot validate anything itself |
| 10 | `request_report` | `roster.py:713` | no arguments at all; cannot shape a report |
| 11 | `park_for_human` - one of five question codes | `roster.py:718` | cannot converse; one question, five codes, no reply channel |
| 12 | `http_request` - **method, url, headers** | `roster.py:738` | **no body, no identity selection, no raw request line, no HTTP version control, no repetition, no timing, no redirect policy, no cookie jar** (`roster.py:761-766` records that body and identity were declared and removed) |
| 13 | `run_tool` - one of four registered binaries | `roster.py:768`, enum at `roster.py:781-784` | the closed set is `jq`, `js_map`, `js_parse`, `js_routes`. Offline only. No scanner, no fuzzer, no browser |
| 14 | `run_skill_script` - a script shipped inside a granted Skill | `roster.py:799` | input is stored Artifacts only (`skill.py` `envelope`); no network, no argv, no filesystem |
| 15 | `get_validation_packet` / `submit_verdict` | `roster.py:814`, `roster.py:826` | validator only; the packet is its whole world |

Plus two built-ins: `Task` (orchestrator only, three arguments,
`roster.py:100`) and `Skill` (`roster.py:103`, granted per role by the corpus).

The six Skills, which are instructions and obtain nothing:

| Skill | Roles | File |
| --- | --- | --- |
| `enumerate-surface` | recon | `src/redkraken/skills/enumerate-surface/SKILL.md:3` |
| `use-identity` | web_hunter | `src/redkraken/skills/use-identity/SKILL.md:3` |
| `compare-responses` | web_hunter | `src/redkraken/skills/compare-responses/SKILL.md:3` |
| `browser-evidence` | web_hunter | `src/redkraken/skills/browser-evidence/SKILL.md:4` |
| `analyse-source` | js_analyst | `src/redkraken/skills/analyse-source/SKILL.md:3` |
| `handle-untrusted-content` | js_analyst, recon, web_hunter | `src/redkraken/skills/handle-untrusted-content/SKILL.md:3` |

And the explicit refusals, which are as much of the capability set as the
grants: `Bash`, `Read`, `Write`, `Edit`, `WebFetch`, `WebSearch` and sixteen
others are forbidden to every role with a stated reason each
(`roster.py:866-891`). `WebFetch` is refused as "a second egress path whose
output carries no proxy receipt" (`roster.py:872`) - which is the sentence the
rest of this document has to be read against.

### Three findings from reading our own tree

1. **The corpus already instructs calls the gate would refuse.**
   `use-identity/SKILL.md:24,29` tells the hunter to call
   `mcp__rk2__http_request` with `identity_slot` set. That argument does not
   exist (`roster.py:753-766`), and the closed schema refuses it before the
   handler. `docs/research/playbook-state-of-the-art/00-todo-and-harness-gaps.md`
   records the same defect across 29 playbooks.
2. **The browser exists and is unreachable from an agent.**
   `browser-evidence/SKILL.md:63` says to start the mission through
   `mcp__rk2__run_tool`; that tool's enum is four offline binaries
   (`roster.py:781-784`). The driver is real and implements the ten actions
   (`src/redkraken/browser_driver.py:502-660`), and `src/redkraken/browser.py:1`
   documents `rk browser run` as an operator command that mints a capability and
   goes through the door. So a browser mission is an operator verb today, not an
   agent one.
3. **The wire layer has no body either.** `_launch._spend`
   (`_launch.py:680`) calls `proxy.spend`, whose signature carries no body
   (`src/redkraken/proxy.py:3897`), and the underlying call is
   `client.request(method, url, headers=...)`. But the evidence layer is
   already ready for one: `receipts` carries `request_agent_sha` and
   `request_wire_sha` (`src/redkraken/migrations/0005_artifacts_and_provenance.sql:59-60`),
   so a request body has a place to be stored and hashed the day it exists.

Two pieces of ground the proposals below have to respect:

* **Scope denies by default and excludes discovery from the grammar.**
  `src/redkraken/scope.py:1-31`: "Adjacent-host expansion, DNS enumeration,
  certificate-transparency search, reverse-IP lookup and virtual-host probing
  are excluded by the spec, so no configuration key enables them". A wildcard
  authorizes requests, never the enumeration that would find hosts.
* **The door already meters.** `reserve_egress_slot`
  (`src/redkraken/migrations/20260811T170000Z__egress_budget_at_the_door.sql:235`)
  takes one request's worth of a shared budget under a row lock and refuses with
  a reason and a time, and `program_egress_budget` counts `throttled` (same
  file, `:76`). Any primitive that sends more requests spends the same budget
  and is refused by the same lock.

## The primitives other systems expose

Each section names the primitive, who exposes it, the bug class it unlocks, and
what it would cost us to have. Sources are listed per section; the full list is
at the end.

### 1. A request with a body, and arbitrary request bytes

**What it is.** The unit of work in every serious tool is a *message*, not a
tuple. Burp's Repeater edits a request in Pretty, Raw or **Hex** view - "edit
individual bytes, 16-byte lines" - and offers "Change request method" and
"Change body encoding" (form URL-encoded / multipart / JSON) as explicit
operations. Burp's own MCP server exposes this to an LLM as
`SendHttp1Request(content, targetHostname, targetPort, usesHttps)`: the request
is one opaque byte string. Its HTTP/2 sibling `SendHttp2Request` takes
`pseudoHeaders`, `headers` and `requestBody` as three separate fields.

**Who exposes it.** Burp Repeater and the official Burp MCP server; Caido
Replay; mitmproxy addons (`flow.request.urlencoded_form`, `flow.request.content`);
every agent in the literature that has `curl` or a Python runtime (MAPTA's
`run_command`/`run_python`, Strix's "Python runtime for custom exploit
development", CAI's Python execution).

**What it unlocks.** Everything whose reading is a POST with a document:
GraphQL, JSON APIs, SOAP/XML and therefore XXE, mass assignment, deserialization,
SSTI in a body field, file upload, webhook delivery, and most of the injection
corpus. Below the body, byte-level control unlocks a second tier: HTTP request
smuggling requires "ability to compose raw HTTP/1 requests with both
`Content-Length` and `Transfer-Encoding` headers", "manual protocol switching",
and "disabling of automatic Content-Length updates" (PortSwigger Web Security
Academy). Burp's HTTP/2 stack goes further and lets you "inject colons into
header names" and "inject arbitrary spaces or newlines within the method and
path", producing requests it calls **kettled** because they cannot be written in
HTTP/1 syntax at all.

**Against ours.** `roster.py:738` has `method` (7-value enum), `url` and
`headers` (name pattern `^[A-Za-z][A-Za-z0-9-]{0,63}\Z`, value pattern
`^[\x20-\x7e]{0,1024}\Z`). The value pattern deliberately ends at `\Z` so a
header cannot carry a newline - which is exactly the byte a kettled request
needs. So the body is a gap; raw bytes are a *decision*, and the door reinforces
it: `_body` refuses a chunked request body outright because "a proxy that
re-chunks is recording bytes that differ from the ones it read"
(`src/redkraken/proxy.py:2394-2409`).

Sources:
- https://portswigger.net/burp/documentation/desktop/tools/message-editor (last updated 2026-08-20)
- https://portswigger.net/burp/documentation/desktop/http2/performing-http2-exclusive-attacks (last updated 2026-08-20)
- https://github.com/PortSwigger/mcp-server (tool definitions in `src/main/kotlin/net/portswigger/mcp/tools/Tools.kt`; no version stated in README)
- https://portswigger.net/web-security/request-smuggling (fetched 2026-08-21)
- https://docs.mitmproxy.org/stable/addons/examples/ (fetched 2026-08-21)

### 2. Repetition, ordering and parallelism on one connection

**What it is.** Control over *how many* requests, *in what order*, and *on which
connection*. Burp's Repeater "Send group" offers three modes: send in sequence
on a single connection, send in sequence on separate connections, and send in
parallel. In parallel over HTTP/1 it uses last-byte synchronization; over
HTTP/2 it uses the single-packet attack, which "enables you to completely
neutralize interference from network jitter by using a single TCP packet to
complete 20-30 requests simultaneously". PortSwigger states plainly that
practical race-condition testing needs "Burp Suite 2023.9 or later".

**Who exposes it.** Burp (Repeater send group, Intruder resource pools with
"maximum concurrent requests" and fixed/random/increasing delays and automatic
throttling on chosen response codes); Caido Automate (rate limiting and
concurrency); Turbo Intruder for scripted variants.

**What it unlocks.** Race conditions and TOCTOU: limit-overrun (coupon reuse,
balance transfer), multi-endpoint races, single-endpoint state machines,
partial-construction races. Also connection-state attacks and client-side
desync, which are a property of the connection rather than of any one request.

**Against ours.** `http_request` is one request per call with no connection
object and no timing control. Turn-by-turn LLM calls cannot be closer together
than a model turn, so "parallel" is not expressible at any level of our stack.
The door's `reserve_egress_slot` also takes the budget one request at a time
(`migrations/20260811T170000Z__egress_budget_at_the_door.sql:235`), so a burst
primitive is a scheduling question as well as a tool question.

Sources:
- https://portswigger.net/web-security/race-conditions (fetched 2026-08-21)
- https://portswigger.net/burp/documentation/desktop/tools/repeater/send-group (last updated 2026-08-20)
- https://portswigger.net/burp/documentation/desktop/tools/intruder/configure-attack/resource-pool (last updated 2026-08-20)
- https://docs.caido.io/app/guides/automate_rate_limiting (no date shown)

### 3. Fuzzing with a wordlist, and payload combinatorics

**What it is.** Positions in a message, payload sets bound to them, and a
combination rule. Burp Intruder's four attack types are sniper (one set, one
position at a time), battering ram (one payload into all positions at once),
pitchfork (a set per position, in lockstep) and cluster bomb (a set per
position, every combination). Caido Automate has the same shape under different
names: All, Sequential, Parallel, Matrix. Payloads are then *processed*: prefix,
suffix, regex match-replace, substring, case, encode/decode chains, hash, skip-if-regex,
a `{base}` placeholder, and a placeholder that inserts a fresh Collaborator
payload per request.

**Who exposes it.** Burp Intruder; Caido Automate; ffuf and feroxbuster on the
command line; Nuclei's fuzzing templates; MAPTA's agents reach for `ffuf` inside
their container.

**What it unlocks.** Hidden content and endpoints, parameter discovery, IDOR
enumeration over identifiers, credential stuffing checks, cache-key probing, and
the whole "try 500 variants and look at what differs" class that a
one-request-per-turn agent cannot afford in tokens.

**Against ours.** Not expressible. `run_tool`'s enum is `jq`, `js_map`,
`js_parse`, `js_routes` (`roster.py:781-784`), none of which touch the network,
and `http_request` sends one request per call. Note the constraint this must
respect: `src/redkraken/scope.py:26-30` excludes discovery from the grammar -
"a wildcard inclusion authorises *requests* to hosts beneath it; it never
authorises the enumeration that would find them". Path fuzzing within an
authorized host is requests; host or subdomain fuzzing is discovery and stays
denied.

Sources:
- https://portswigger.net/burp/documentation/desktop/tools/intruder/configure-attack/attack-types (last updated 2026-08-20)
- https://portswigger.net/burp/documentation/desktop/tools/intruder/configure-attack/processing (last updated 2026-08-20)
- https://docs.caido.io/app/guides/automate_multiple (no date shown)
- https://arxiv.org/abs/2508.20816 (MAPTA, submitted 2025-08-28)

### 4. Response diffing and match/extract as a tool, not as reading

**What it is.** The tool, not the model, decides what changed. Burp Intruder has
"Grep - match" (flag responses matching a string or regex), "Grep - extract"
(capture a region into a results column) and "Grep - payloads" (reflection
detection), plus auto-pause when an expression appears or disappears, and a
baseline request to compare against. Caido Automate has extractors that become
custom result columns. Nuclei expresses the same idea as matchers and extractors
inside a template.

**Who exposes it.** Burp Intruder; Caido Automate; Nuclei; every scanner.

**What it unlocks.** Cheap detection at scale, and - more relevant to us -
*evidence that is a number rather than a sentence*. Authorization findings live
or die on a controlled two-response comparison.

**Against ours.** We have half of this already and it is the better half:
`compare-responses` runs `compare.py` over two stored Artifacts and returns
`identical`, `only_in_first`, `only_in_second`, `shared_lines`, `lengths`
(`src/redkraken/skills/compare-responses/SKILL.md:6`). What is missing is the
loop around it: matching over *many* responses without each one passing through
the model's context (the handler returns 4096 bytes of body per call,
`src/redkraken/packet.py:60`).

Sources:
- https://portswigger.net/burp/documentation/desktop/tools/intruder/configure-attack/settings (last updated 2026-08-20)
- https://docs.caido.io/app/guides/automate_extractors (no date shown)

### 5. Out-of-band interaction

**What it is.** A name the tester controls, embedded in a payload, plus a
listener that records who resolved or fetched it. Burp Collaborator generates
subdomains of the Collaborator server and filters recorded interactions by
protocol - **DNS**, **HTTP**, **SMTP**. Its MCP surface is exactly two verbs:
`GenerateCollaboratorPayload(customData?)` and
`GetCollaboratorInteractions(payloadId?)`. A private server listens on DNS/53,
HTTP/80, HTTPS/443, SMTP/25 and 587, SMTPS/465 and needs NS delegation.

**What it unlocks.** Every blind class. PortSwigger's academy: "The most
reliable way to detect blind SSRF vulnerabilities is using out-of-band (OAST)
techniques", and it teaches reading a DNS lookup with no subsequent HTTP request
as its own signal. Same for blind SQLi, blind XXE, blind command injection,
SSTI, and log4shell-style lookups.

**Against ours.** We own this channel end to end and it is not on the agent
surface. `src/redkraken/oob.py:1-35` describes a file host plus the lifecycle of
the name in front of it, and gives the reason we host rather than rent: "an XXE
against a target that resolves external entities needs a DTD the target can
fetch, and a canary that answers a fixed string cannot carry one". The database
asserts the boundary directly: accepting an interaction "is the runtime's verb
alone, a correlator is nobody's to rewrite, neither it nor the name it arrived
at is on the agent surface"
(`migrations/20260812T040000Z__a_callback_arrives_on_a_declared_channel.sql:935`).
Correlators are minted by `callback.py:102` for one subject on one declared
channel. So the design question is not "may the agent have OOB" but "does the
mission packet carry a minted correlator the agent may spend".

Sources:
- https://portswigger.net/burp/documentation/collaborator (last updated 2026-08-20)
- https://portswigger.net/burp/documentation/collaborator/deploying (last updated 2026-08-20)
- https://portswigger.net/web-security/ssrf/blind (fetched 2026-08-21)
- https://github.com/PortSwigger/mcp-server

### 6. Crawling and content discovery

**What it is.** Walking an application to produce the set of things that exist,
as a job rather than as a sequence of the agent's own requests. ZAP's Automation
Framework has `spider`, `spiderAjax` and `spiderClient` as first-class job types
alongside `import`, `openapi`, `graphql`, `soap` and `postman` importers.
feroxbuster extracts links from responses (`--extract-links`) and recurses with
`--depth`. Nuclei's `-as/-automatic-scan` maps technologies to templates.

**Who exposes it.** ZAP; feroxbuster/ffuf with `-recursion`; Playwright-driven
crawlers; MAPTA's container has `ffuf` and `nmap` available.

**What it unlocks.** Coverage. Every later finding is bounded by the surface
that was found, and a crawl is the cheapest way to find endpoints that no link
in the first page names.

**Against ours.** Our recon role calls `mcp__rk2__http_request` "per root. One
exchange per URL" (`src/redkraken/skills/enumerate-surface/SKILL.md:25`).
There is no crawl job; a crawl is N model turns. This is the primitive whose
absence is most expensive in tokens and the one most constrained by
`scope.py:26-30`, which excludes discovery of *hosts* while leaving paths under
an authorized host as ordinary requests.

Sources:
- https://www.zaproxy.org/docs/automate/automation-framework/ (job list; no publication date shown)
- https://github.com/epi052/feroxbuster
- https://github.com/ffuf/ffuf

### 7. Browser control

**What it is.** A real browser the agent drives, and - equally important - reads
back. The official Playwright MCP server exposes `browser_navigate`,
`browser_click`, `browser_type`, `browser_fill_form`, `browser_file_upload`,
`browser_snapshot` (an accessibility snapshot, which its README calls "better
than screenshot"), `browser_take_screenshot`, `browser_console_messages`,
`browser_network_requests`, `browser_evaluate` (arbitrary JS), `browser_tabs`
and `browser_handle_dialog`, with opt-in capability groups for network
interception (`browser_route`), storage (`browser_cookie_*`,
`browser_localstorage_*`, `browser_storage_state`), devtools tracing and
pixel-coordinate "vision" mouse control. Chrome DevTools MCP adds
`performance_start_trace`, `list_network_requests`, `evaluate_script`,
`list_console_messages` and `lighthouse_audit`. Nuclei has the same idea as a
template protocol: `headless:` with `steps:` over `navigate`, `waitload`,
`click`, `text`, `script`, `extract`, `screenshot`, plus request manipulation
actions `setmethod`, `addheader`, `setheader`, `deleteheader`, `setbody`.
XBOW's platform page calls its equivalent a "steerable headless browser" and its
top-1 post uses it to confirm that a JS payload actually executed. HPTSA states
that "all agents had access to Playwright ... the terminal, and file management
tools".

**What it unlocks.** DOM XSS and any sink reached only after script runs; SPA
routes that never appear in raw HTML; client-side prototype pollution;
postMessage handlers; CSP violations and JS errors visible only in the console;
tokens in localStorage/sessionStorage; the network waterfall a page produces on
its own; and proof-of-execution evidence for XSS that a raw response body cannot
give.

**Against ours.** We have a browser, and an agent cannot start it.
`src/redkraken/browser_driver.py:502-660` implements the actions,
`src/redkraken/browser.py:1-24` documents `rk browser run` minting a capability
and going through the door, `browser-evidence/SKILL.md:63` tells the hunter to
"Start the mission through `mcp__rk2__run_tool`", and `run_tool`'s enum is four
offline binaries (`roster.py:781-784`). Two ADRs already settled that we build
this ourselves rather than adopt a CLI: `docs/adr/0004` (carbonyl declined) and
`docs/adr/0005` (agent-browser declined, its Skill text kept).

Sources:
- https://github.com/microsoft/playwright-mcp
- https://github.com/ChromeDevTools/chrome-devtools-mcp
- https://docs.projectdiscovery.io/templates/protocols/headless
- https://xbow.com/platform (no date shown) and https://xbow.com/blog/top-1-how-xbow-did-it (2025-06-24)
- https://arxiv.org/html/2406.01637v1 (HPTSA, 2024-06-02)

### 8. JS and source analysis

**What it is.** Reading the client bundle, the source map or the repository
rather than the response. Vulnhuntr is LLM-plus-static-call-chain tracing from
remote input to sink and explicitly "does not execute code or run exploits".
Project Zero's Naptime work gives its model a Code Browser and a Python tool
rather than a network client. Param Miner harvests candidate parameter names
from in-scope traffic and "combines advanced diffing logic ... with a binary
search technique to guess up to 65,000 param names per request".

**What it unlocks.** Endpoints and parameters nothing links to; hardcoded keys;
feature flags; the difference between what the API accepts and what the UI
sends.

**Against ours.** This is the one primitive where we are already at the state of
the art in kind, if not in breadth. `js_analyst` holds `exec.tool_run` and no
network (`roster.py:942-957`), and `analyse-source` runs `extract_paths.py` over
a stored Artifact with declared, checked cases
(`src/redkraken/skills/analyse-source/SKILL.md:6`). The registered binaries
`js_map`, `js_parse`, `js_routes` (`roster.py:781-784`) are exactly the shape
other systems reach for. What is missing is breadth of language and a parameter
name-mining pass, not a new kind of authority.

Sources:
- https://github.com/protectai/vulnhuntr
- https://github.com/PortSwigger/param-miner
- https://github.com/s0md3v/Arjun

### 9. Session and identity handling

**What it is.** Being logged in, staying logged in, and being two people at once.
ZAP's context environment declares `authentication.method` from
`manual|http|form|json|script|autodetect|browser|client`, a verification method
(`response|request|both|poll` with `loggedInRegex`/`loggedOutRegex` and polling),
`sessionManagement.method` from `cookie|http|script`, and `users` with
credentials including TOTP (`secret`, `period`, `digits`, `algorithm`). Nuclei
keeps cookies across requests in a template by default (`disable-cookie` to turn
it off). MAPTA gives its agent a mailbox - `get_registered_emails`,
`list_account_messages`, `get_message_by_id` - so it can complete signup and
password-reset flows. Playwright MCP can save and set whole storage states.

**What it unlocks.** Everything behind a login, which is most of what is worth
finding: broken access control, IDOR, tenant isolation, privilege escalation,
session fixation, and the account-recovery flows that need an inbox.

**Against ours.** The runtime owns leases and the proxy injects credentials -
`use-identity/SKILL.md:11-12`: "The runtime owns leases; the proxy owns headers,
cookies, session state, and wire evidence" - and the receipt keeps the agent-side
and wire-side bytes apart precisely so credential material never enters a
model's context (`migrations/0005_artifacts_and_provenance.sql:34-38`). That
design is stronger than ZAP's, and it currently has a hole in the middle: the
Skill tells the model to pass `identity_slot` (`use-identity/SKILL.md:24,29`) and
the argument does not exist (`roster.py:753-766`). There is no mailbox primitive
and no way to complete a signup or reset flow.

Sources:
- https://www.zaproxy.org/docs/desktop/addons/automation-framework/environment/
- https://docs.projectdiscovery.io/templates/protocols/http/basic-http
- https://arxiv.org/abs/2508.20816 (MAPTA, 2025-08-28)

### 10. Template-driven and declarative checks

**What it is.** A check written once, as data, and run by an engine rather than
by a model. A Nuclei template is `id` + `info` + a protocol block + `matchers` +
`extractors`; matchers are `status|size|word|regex|binary|dsl|xpath` over parts
`body|header|all_headers|content_length|status_code|raw`; requests can be `raw:`
full request text with helper-function interpolation; `fuzzing:` blocks declare
`part` (`query|path|header|cookie|body|request`), `type`
(`replace|prefix|postfix|infix|replace-regex`), `mode`, key/value filters and a
`pre-condition`; `analyzer: time_delay` confirms a timing payload with
regression rather than one slow response. Workflows chain templates so a
subtemplate runs only if its parent matched. ZAP's equivalents are scan policies,
alert filters and Zest scripts.

**What it unlocks.** Known-CVE and known-misconfiguration checks at near-zero
marginal cost, and reproducible detection logic that does not vary run to run.

**Against ours.** We have the *evidence* half of this and none of the execution
half. Our Playbooks are prose with typed frontmatter, and our Tests have declared
assertions (`status_equals`, `status_differs`, `body_equals`, `body_differs` -
`migrations/20260815T000000Z__a_test_runs_through_the_replay_lane.sql:185`)
replayed deterministically by `src/redkraken/replay.py`. That is a template
engine with four matchers and no request body. Nuclei's matcher vocabulary is
the obvious thing to grow ours towards.

Sources:
- https://docs.projectdiscovery.io/templates/structure
- https://docs.projectdiscovery.io/templates/reference/matchers
- https://docs.projectdiscovery.io/templates/protocols/http/fuzzing-overview
- https://docs.projectdiscovery.io/templates/protocols/http/raw-http
- https://docs.projectdiscovery.io/templates/workflows/overview

### 11. Scope enforcement as a primitive of the agent system

**What it is.** Where "may I touch this" is answered. XBOW's safety post
describes an egress MITM proxy with DNS-layer classification into
attackable/restricted/blocked, scope "locked at launch", out-of-bounds DNS
answered `BLOCKED`, per-user routing, rate limiting and every packet logged, plus
a Guardian model reviewing actions before execution and deterministic health
monitors that auto-pause on WAF, captcha, lockout or target downtime. ZAP puts
scope in the context (`includePaths`/`excludePaths` regex). Playwright MCP has
`--allowed-hosts`, `--allowed-origins`, `--blocked-origins`.

**What it unlocks.** Nothing offensive - it is what makes the rest safe to
automate, and it is the thing the bug bounty platforms now demand. HackerOne's
Code of Conduct requires compliance with each program's "limits on automation,
request volume, and rate limiting" and prohibits "generating large volumes of
low-signal or non-actionable reports". Bugcrowd's March 2026 policy adds a
30-day suspension after ten consecutive invalid reports attributable to
"automated or AI-generated activity without sufficient validation prior to
submission", plus dynamic rate limiting and mandatory identity verification.

**Against ours.** This is where we are ahead of everything surveyed.
`src/redkraken/scope.py:10-31` states four properties as refusals: deny by
default, precedence by effect rather than document order, canonicalisation
before matching, and discovery excluded from the grammar entirely. The door
re-decides every request that arrives under a capability, including redirects
and subresources (`src/redkraken/agent.py:303-307`), and meters with
`reserve_egress_slot`. Nothing proposed below may weaken any of that.

Sources:
- https://xbow.com/blog/autonomous-agent-safety-guardrails (2026-08-12)
- https://www.hackerone.com/policies/code-of-conduct (no last-updated date shown on the page)
- https://www.bugcrowd.com/blog/bugcrowd-policy-changes-to-address-ai-slop-submissions/ (2026-03-10)
- https://github.com/microsoft/playwright-mcp

### 12. Validation as a separate, executing step

**What it is.** A second agent or program that re-runs the finding end to end
before a human sees it. XBOW describes "automated peer reviewers that confirm
each vulnerability", either LLM-based or custom programmatic checks per
vulnerability class. MAPTA has a validation agent that "executes the PoC
end-to-end and returns pass/fail with evidence". Strix "validates via actual PoC
execution".

**What it unlocks.** Not a bug class - a submission that survives triage. The
platform data is the argument: curl's confirmation rate fell from "north of 15%"
to "below 5%" and the bounty ended on 2026-01-31; Bugcrowd reports a 334% rise
in triage queue volume.

**Against ours.** We have this and it is architecturally stronger: the validator
is a separate session whose "packet is its whole world", holds no free-text
argument at all - `_check_argument` refuses one (`roster.py:1776`), and the runtime replays the Finding's own Test
before deciding (`roster.py:826-844`, `src/redkraken/replay.py`). The weakness
is upstream: a Test can only assert status/body equality and cannot send a body,
so most findings cannot be expressed as a replayable Test in the first place.

Sources:
- https://xbow.com/blog/top-1-how-xbow-did-it (2025-06-24)
- https://arxiv.org/abs/2508.20816 (MAPTA, 2025-08-28)
- https://docs.strix.ai/ (no date shown)
- https://daniel.haxx.se/blog/2026/01/26/the-end-of-the-curl-bug-bounty/ (2026-01-26)
- https://www.bugcrowd.com/blog/sloptimism-is-breaking-any-system-built-on-human-validation/ (2026-04-23)

### 13. What the security literature says about handing an agent these primitives

This is not a primitive, it is the constraint every primitive above has to be
built under, and the sources are unusually consistent.

**The trifecta.** Simon Willison's formulation: private data, exposure to
untrusted content, and the ability to communicate externally. Any two are
survivable; all three are exploitable, and his stated conclusion is that
guardrails are not sufficient - the protection is not assembling the trifecta.
A web-hunting agent is the trifecta by construction: it reads attacker-
controlled response bodies, it works inside a Program's scope data, and its
whole job is to make outbound requests.

**Constrain what happens after untrusted input, not the input.** "Design
Patterns for Securing LLM Agents against Prompt Injections" (arXiv 2506.08837,
v1 2025-06-10, v3 2025-06-27) states the principle as constraining what the
agent can do once untrusted input is in context, and names six patterns:
Action-Selector, Plan-Then-Execute, LLM Map-Reduce, Dual LLM, Code-Then-Execute,
Context-Minimization. CaMeL (arXiv 2503.18813, v1 2025-03-24, v2 2025-06-24)
implements the strongest form: control and data flow are extracted from the
*trusted* query into a program, a custom interpreter runs it so untrusted data
"can never impact the program flow", and capabilities tag data provenance and
gate each tool call.

**Deterministic enforcement below the model.** Google's agent-security paper
(Díaz, Kern, Olive, 2025) names three principles - well-defined human
controllers, limited agent powers scoped and dynamically constrained to the
current task, and observable actions and planning - and a hybrid defence where
Layer 1 is deterministic runtime policy enforcement intercepting each action,
and Layer 2 is reasoning-based defences that are "non-deterministic and cannot
provide absolute guarantees".

**Network as the chokepoint.** Anthropic's agent-SDK deployment guidance is
explicit: run the agent with no network and route egress through a host-side
proxy that enforces domain allowlists, **injects credentials rather than exposing
them to the agent**, and logs all traffic for audit - "Even if the agent is
compromised via prompt injection, it cannot exfiltrate data to arbitrary
servers." It also names the weakness of naive allowlists: a proxy that allowlists
on the client-supplied hostname "does not terminate or inspect encrypted
traffic".

**Untrusted content belongs in tool results.** Anthropic's prompt-injection
guidance: put untrusted content only in `tool_result` blocks, never in the
system prompt or a plain user turn; do not put your own instructions in tool
results; JSON-encode untrusted strings so an attacker cannot break out of the
data context; screen tool outputs before returning them. Their browser-extension
measurement is the honest ceiling on model-level defence: a 1% attack success
rate under an adaptive Best-of-N attacker, described as still meaningful risk.

**Vulnerability-research agents specifically are given local tools, not network
tools.** Project Zero's Naptime (2024-06-20) gives the model a Code Browser, a
sandboxed Python tool, a Debugger and a Reporter, and names Perfect Verification
as the property that makes the domain tractable - the loop is closed by a crash
oracle, not by the model's judgement. Big Sleep's SQLite find (2024-11-01) uses
the same local set. CodeMender (2025-10-06) adds fuzzing, differential testing
and SMT solvers, and states that "all patches generated by CodeMender are
reviewed by human researchers before they're submitted upstream".

**And the platforms now require the human step by rule.** HackerOne's Code of
Conduct: hackbots must not run fully autonomously, a human must investigate,
validate and confirm findings before submission, and all AI-assisted activity
must respect each program's "limits on automation, request volume, and rate
limiting". Bugcrowd's Code of Conduct (updated 2025-11-25): "Manually review and
validate any vulnerability report you've created with the help of GenAI tools
before submitting it."

**Against ours.** Our answers already exist and are structural rather than
advisory: untrusted content arrives as tool results only, `handle-untrusted-content`
states the rule as a Skill three roles load
(`src/redkraken/skills/handle-untrusted-content/SKILL.md:10`), egress is a
container with one peer and a capability proxy that injects credentials
(`src/redkraken/agent.py:293-307`), every packet earns a Receipt with four
hashes (`migrations/0005_artifacts_and_provenance.sql:34-38`), and the gate is a
deterministic pre-tool decision that `bypassPermissions` cannot overrule
(`roster.py:14-22`). The plan is fixed before target content is read: the mission
packet is compiled on the supervisor's connection before the container starts
(`roster.py:586-591`), which is Plan-Then-Execute by construction.

Sources:
- https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/ (2025-06-16)
- https://arxiv.org/abs/2506.08837 (v1 2025-06-10, v3 2025-06-27)
- https://arxiv.org/abs/2503.18813 (CaMeL, v1 2025-03-24, v2 2025-06-24)
- https://research.google/pubs/an-introduction-to-googles-approach-for-secure-ai-agents/ (2025)
- https://code.claude.com/docs/en/agent-sdk/secure-deployment (no date shown)
- https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/mitigate-jailbreaks (no date shown)
- https://www.anthropic.com/research/prompt-injection-defenses (2025-11-24)
- https://projectzero.google/2024/06/project-naptime.html (2024-06-20)
- https://projectzero.google/2024/10/from-naptime-to-big-sleep.html (2024-11-01)
- https://deepmind.google/discover/blog/introducing-codemender-an-ai-agent-for-code-security/ (2025-10-06)
- https://www.hackerone.com/policies/code-of-conduct (no last-updated date shown)
- https://www.bugcrowd.com/resources/hacker-resources/code-of-conduct/ (updated 2025-11-25)

## Ranked proposal for us

Ordered by bugs unlocked over build cost. Each entry says where it lives and,
because this is a harness whose point is an auditable receipt, what it must not
be allowed to do.

### 1. A request body on `http_request`

**Why first.** Highest ratio in the list by a wide margin. It unlocks GraphQL,
JSON APIs, XXE, mass assignment, deserialization, SSTI, file upload and most of
the injection corpus - and the harness gap file already records that 29 of 50
playbooks are prose because of it. The build is small because every layer except
one already handles bodies: the door reads, bounds and hashes a request body
today (`proxy.py:2394-2409`, ceiling 32 MiB at `proxy.py:328`), and `receipts`
already has `request_agent_sha` and `request_wire_sha`
(`migrations/0005_artifacts_and_provenance.sql:59-60`).

**Where.** A `body` argument on `roster.CONTRACTS["mcp__rk2__http_request"]`
(`roster.py:738`); a `body` parameter threaded through `proxy.spend`
(`proxy.py:3897`) and `_through`; `_launch._spend` passing it (`_launch.py:680`).

**Must not.** It must not be free text under `OPEN_ARGUMENTS` - the roster's
own rule is that an unconstrained argument states why it is one
(`roster.py:1774`), and a body is put on a wire. Constrain it as bytes with a
declared ceiling and a character class, keep `Content-Length` the runtime's to
compute, and keep the chunked refusal. It must not accept a `Transfer-Encoding`
header from the model, and it must not be the place `identity_slot` sneaks back
in as a free-form field.

### 2. Identity selection on the request, spelled the way the runtime already decided

**Why second.** Cheap, and it is the difference between a harness that can test
authorization and one that cannot. The lease machinery exists; only the naming
is missing. Broken access control is the largest paying bug class on both
platforms and needs exactly one thing: the same request as two identities.

**Where.** Either an `identity_slot` argument on `http_request` constrained to
the `IDN` label pattern (`roster._label(LABEL_PREFIXES["identity"])`), or - if
the "identity is chosen when the Tool run opens" decision stands - a correction
to `use-identity/SKILL.md:24,29` and the 29 playbooks so the corpus stops
instructing a refused call. Decide one; today the corpus and the gate disagree.

**Must not.** It must never name a credential, a slot reference or a header
value. `FORBIDDEN_INSTRUCTIONS` (`roster.py:229-244`) already refuses
`credential`, `token`, `authorization` and friends in every interpreted
argument, and the label indirection is what keeps that true.

### 3. Make the browser reachable from an agent

**Why third.** The capability is built and paid for; what is missing is one enum
member. It unlocks DOM XSS with proof of execution, SPA surface, client-side
storage disclosure, console-visible errors, and the "did the payload actually
run" evidence that every published autonomous system uses its browser for.

**Where.** Add the browser mission to `roster.CONTRACTS["mcp__rk2__run_tool"]`'s
`tool` enum (`roster.py:781-784`) or give it its own contract in the
`exec.tool_run` group, with the plan expressed as the ten declared actions the
driver already implements (`browser_driver.py:502-660`) and the supervisor
running `browser.py`'s existing open/run/store path.

**Must not.** No eleventh action, and no free-form script step: the `inject` and
`probe` actions are the only script paths and they are declared plan steps whose
digest is taken before the run. It must not be able to choose its own capability
or identity, and `browser-evidence/SKILL.md:67-69` must keep holding - a browser
mission and a hand-made exchange in the same run produce Receipts that look
alike and are not.

### 4. A bounded repeat primitive: one request shape, a declared payload list

**Why fourth.** This is the fuzzing/Intruder primitive in the smallest form that
fits our evidence model. It unlocks IDOR enumeration, parameter discovery,
hidden-content discovery, and any "500 variants, tell me which differ" question
that is currently unaffordable in tokens. Cost is real but bounded: it is one
Tool run that emits N Receipts and one summary Artifact, and the door's
`reserve_egress_slot` meters it request by request without change.

**Where.** A new member of `exec.tool_run` - a registered runner, not a new
network verb - taking a base request, one declared insertion point, a payload
source that is a stored Artifact (so the wordlist is content-addressed and
citable), a hard ceiling on count and a declared delay. Returns a table of
status, length and the Receipt label per attempt, plus matcher results.

**Must not.** No wordlist by name and no wordlist the model composes freely - a
payload list is an Artifact with a hash, or it does not run. No host or subdomain
positions ever: `scope.py:26-30` excludes discovery from the grammar and this
must not become the way back in. No unbounded count, no concurrency the door has
not agreed to, and every attempt earns its own Receipt - a summary without N
receipts would be exactly the "N requests, one record" trade this harness exists
to refuse.

### 5. Out-of-band evidence the agent can spend and read

**Why fifth.** It unlocks every blind class - blind SSRF, blind SQLi, blind XXE,
blind command injection, log4shell-style lookups - which is otherwise
structurally undetectable for us. We already own the channel end to end
(`oob.py:1-35`), which is rarer than it sounds: a hosted canary cannot serve the
DTD an XXE needs, and ours can. The cost is in the plumbing, not the concept.

**Where.** A minted correlator carried *in the mission packet* rather than
requested by a tool (the database already asserts that neither the correlator nor
the name it arrived at is on the agent surface -
`migrations/20260812T040000Z__a_callback_arrives_on_a_declared_channel.sql:935`),
plus one read-side tool in `state.read` that answers "which interactions resolved
the correlator this run holds", modelled on Burp's two-verb split of generate and
poll.

**Must not.** The model must not mint, choose, extend or rewrite a correlator,
and must not learn the channel's hostname other than as the opaque address it was
handed. A read must be scoped to this run's own correlator - a read across
correlators is a read across Programs. And silence must be reported as silence
with a positive control, not as absence of the bug.

### 6. Matchers and extractors on stored responses

**Why sixth.** Low cost, and it multiplies #4. We have a two-response comparator
already (`compare-responses`); what is missing is a declared matcher vocabulary
over one or many stored Artifacts: `status`, `size`, `word`, `regex`, `dsl`,
over parts `body`, `header`, `status_code`, with `and`/`or`. Nuclei's vocabulary
is the model to copy because it is small, closed and already proven at scale.

**Where.** A Skill script beside `compare.py`, or a fifth registered binary in
`run_tool`'s enum. Inputs are stored Artifacts, so it inherits the existing
determinism check that runs each declared case twice under a bare environment.

**Must not.** It must not fetch anything, and its regex must be bounded - an
unbounded pattern over a 32 MiB Artifact is a denial of service against our own
supervisor.

### 7. A crawl job

**Why last of the build list.** Highest coverage gain per finding but the
largest surface-area risk and the largest build. Every later finding is bounded
by what recon found, and today recon is one model turn per URL
(`enumerate-surface/SKILL.md:25`).

**Where.** A registered runner in `exec.tool_run` that walks links under an
already-authorized application root, files each response as an Artifact and
proposes entities through the existing promotion path.

**Must not.** Paths under an authorized host only. No host expansion, no DNS
enumeration, no certificate-transparency search, no reverse-IP, no virtual-host
probing - `scope.py:26-30` names those five and denies them whatever policy it is
handed, and a crawler is the most natural place for one to reappear by accident.
It must not follow off-scope links, it must obey the same egress budget, and it
must not promote anything itself.

## What we should deliberately not have

The whole point of this harness is that every packet has a receipt somebody can
recompute. These primitives are all normal in other tools and all wrong here.

**A shell.** `roster.py:867` already says it: "a shell is arbitrary process
creation; exec.tool_run is the enumerated form". MAPTA, CAI, Strix, HPTSA and
Cybench's scaffolds all hand the agent a terminal, and it is why none of them can
tell you afterwards what was sent. An enumerated runner produces a Tool run row;
a shell produces a transcript.

**A second egress path.** `WebFetch` and `WebSearch` stay forbidden for the
reason already written at `roster.py:872-873`: "a second egress path whose output
carries no proxy receipt" and "egress that never enters the container's network
at all". This also happens to be exactly Anthropic's own deployment advice -
one proxy, allowlist, credential injection, full logging.

**Raw byte-level request construction.** Tempting, because it unlocks request
smuggling and HTTP/2 "kettled" requests, and wrong for us. Our door parses,
re-frames and hashes what it forwards, and it refuses a chunked body rather than
re-chunk because "a proxy that re-chunks is recording bytes that differ from the
ones it read" (`proxy.py:2394-2400`). A raw-bytes primitive would either bypass
the door - no receipt - or be silently normalised by it, which is worse: evidence
that says one thing was sent when another was. If desync classes are ever wanted,
they need a lane of their own with its own evidence model, not an argument on
this tool.

**Interception and rewriting of other traffic.** Burp Match & Replace, Caido
workflows, mitmproxy `request`/`response` hooks and Playwright's `browser_route`
all act on traffic the agent did not originate. In our model the proxy is the
authority that decides and records; an agent that could rewrite in flight would
be an agent editing its own evidence.

**Arbitrary in-page JavaScript as a general verb.** `browser_evaluate` and
`evaluate_script` are the most powerful tools in the browser MCP servers and the
least auditable. Our browser plan is ten declared actions whose digest is taken
before the run; an `eval` step would make the plan digest meaningless, since the
plan would no longer describe what ran.

**Model-chosen concurrency, parallelism and timing.** Race-condition testing
genuinely needs it (single-packet attack, last-byte sync), and it is the one
place where we should say no and mean it for now: it collides with the egress
budget's row lock, with per-Program rate limits both platforms require us to
respect, and with `clamp_to_identity_leases` (`roster.py:940`). If it ever
happens it is a runtime lane with its own reservation, never an argument a model
sets.

**Autonomous submission.** Not a tool but a temptation, and both platforms now
forbid it in text: HackerOne requires a human to investigate and confirm before
submission, Bugcrowd requires manual review and validation of any GenAI-assisted
report. Our reporter is a deterministic renderer with no model, no effort and no
turn (`roster.py:975-987`), which is the right shape; nothing should move
submission closer to a model.

**Anything that writes canonical state.** Already enforced -
`_check_contracts` refuses a contract writing any table in `CANONICAL`
(`roster.py:118-138`) - and worth restating here, because every primitive above
increases the pressure to let a runner promote its own results.

## Sources consulted

Ours (read in this worktree):
- `src/redkraken/roster.py` - the fourteen contracts, the roles, the forbidden built-ins.
- `src/redkraken/skill.py` and `src/redkraken/skills/*/SKILL.md` - the six Skills.
- `src/redkraken/_launch.py`, `src/redkraken/proxy.py`, `src/redkraken/agent.py` - what a request actually is on the wire.
- `src/redkraken/scope.py`, `src/redkraken/oob.py`, `src/redkraken/browser.py`, `src/redkraken/browser_driver.py`, `src/redkraken/callback.py`, `src/redkraken/replay.py`.
- `src/redkraken/migrations/0005_artifacts_and_provenance.sql`, `.../20260811T170000Z__egress_budget_at_the_door.sql`, `.../20260812T040000Z__a_callback_arrives_on_a_declared_channel.sql`, `.../20260815T000000Z__a_test_runs_through_the_replay_lane.sql`.
- `docs/adr/0004-carbonyl-is-not-adopted-as-a-terminal-browser.md`, `docs/adr/0005-agent-browser-is-not-adopted-but-its-skill-text-is-kept.md`, `docs/research/playbook-state-of-the-art/00-todo-and-harness-gaps.md`.

External, all fetched:

| URL | Date on page | Note |
| --- | --- | --- |
| https://xbow.com/blog/top-1-how-xbow-did-it | 2025-06-24 | XBOW's own account of the HackerOne ranking; validators, headless browser, SimHash/imagehash target dedup |
| https://xbow.com/blog/xbow-on-hackerone-whats-next | 2025-08-18 | says "#1 globally in Q2"; the June post says "top position in the US ranking" - the two do not agree |
| https://xbow.com/blog/autonomous-agent-safety-guardrails | 2026-08-12 | egress MITM proxy, DNS scope classes, Guardian model, health monitors |
| https://xbow.com/platform | none shown | "steerable headless browser", Python exploit scripting |
| https://xbow.com/blog/benchmarks | 2024-11-09 | 104 externally-commissioned challenges, 85% claimed |
| https://blog.raw.pm/en/about-the-hype-around-xbow/ | date not surfaced | independent critique; ranking was US, by reputation, Apr-Jun 2025 window. Treat as unverified-date |
| https://arxiv.org/abs/2508.20816 | submitted 2025-08-28 | MAPTA: `run_command`, `run_python`, sub-agents, mailbox tools, validation agent |
| https://arxiv.org/html/2406.01637v1 | 2024-06-02 | HPTSA: "Playwright ... the terminal, and file management tools", ZAP for one agent |
| https://arxiv.org/abs/2409.16165 | 2024-09-24, rev 2025-06-05 | EnIGMA: interactive agent tools - debugger, server connection tool |
| https://arxiv.org/abs/2308.06782 | 2023-08-13, rev 2024-06-02 | PentestGPT: three modules over a pentesting task tree |
| https://arxiv.org/html/2504.06017v1 | 2025-04-08 | CAI: shell, nmap, gobuster, hashcat, Python, MCP into Ghidra and Burp, Ctrl+C human-in-the-loop |
| https://docs.strix.ai/ | none shown | HTTP proxy, multi-tab browser, terminals, Python runtime, PoC validation |
| https://github.com/berylliumsec/nebula | n/a | isolated OCI execution, scope enforcement, content-addressed artifacts, append-only event log |
| https://github.com/protectai/vulnhuntr | n/a | static-only LLM call-chain tracing; does not execute |
| https://arxiv.org/abs/2408.08926 | 2024 | Cybench: four scaffolds incl. structured bash and pseudoterminal |
| https://portswigger.net/burp/documentation/desktop/tools/repeater | last updated 2026-08-20 | resend arbitrary HTTP or WebSocket messages, connection-state sequences |
| https://portswigger.net/burp/documentation/desktop/tools/message-editor | 2026-08-20 | Pretty/Raw/Hex, change method, change body encoding |
| https://portswigger.net/burp/documentation/desktop/http2/performing-http2-exclusive-attacks | 2026-08-20 | pseudo-headers, colon and newline injection, "kettled" |
| https://portswigger.net/burp/documentation/desktop/tools/repeater/send-group | 2026-08-20 | sequence/parallel, last-byte sync, single-packet attack |
| https://portswigger.net/burp/documentation/desktop/tools/intruder/configure-attack/attack-types | 2026-08-20 | sniper, battering ram, pitchfork, cluster bomb |
| https://portswigger.net/burp/documentation/desktop/tools/intruder/configure-attack/processing | 2026-08-20 | payload processing rules incl. Collaborator placeholder |
| https://portswigger.net/burp/documentation/desktop/tools/intruder/configure-attack/settings | 2026-08-20 | grep-match, grep-extract, grep-payloads, auto-pause, baseline |
| https://portswigger.net/burp/documentation/desktop/tools/intruder/configure-attack/resource-pool | 2026-08-20 | max concurrent requests, delays, automatic throttling |
| https://portswigger.net/burp/documentation/collaborator | 2026-08-20 | DNS, HTTP, SMTP interactions; polling |
| https://portswigger.net/burp/documentation/collaborator/deploying | 2026-08-20 | private server ports and NS delegation |
| https://portswigger.net/burp/documentation/desktop/extend-burp/bambdas | 2026-08-20 | Java scripts on the Montoya API; "can run arbitrary code" |
| https://portswigger.net/burp/documentation/desktop/burp-ai | 2026-08-20 | Explore Issue, Explainer, AI extensions |
| https://github.com/PortSwigger/mcp-server | no version in README | the official Burp MCP tool list, incl. `SendHttp1Request`, `SendHttp2Request`, `GenerateCollaboratorPayload`, `GetCollaboratorInteractions` |
| https://portswigger.net/web-security/race-conditions | fetched 2026-08-21 | "Burp Suite 2023.9 or later"; single-packet attack, 20-30 requests in one TCP packet |
| https://portswigger.net/web-security/request-smuggling | fetched 2026-08-21 | needs raw HTTP/1, both CL and TE, "Update Content-Length" unchecked |
| https://portswigger.net/web-security/ssrf/blind | fetched 2026-08-21 | OAST is "the most reliable way"; DNS without HTTP is its own signal |
| https://docs.caido.io/app/quickstart/automate | none shown | wordlists, preprocessing, rate limiting, extractors |
| https://docs.caido.io/app/guides/automate_multiple | none shown | All / Sequential / Parallel / Matrix |
| https://docs.caido.io/app/concepts/workflows_intro | none shown | passive/active/convert workflows, QuickJS, server-side |
| https://docs.caido.io/app/tutorials/mcp | none shown | the Caido MCP server is community-developed, "not officially affiliated with Caido" |
| https://developer.caido.io/reference/sdks/backend/ | none shown | backend plugin SDK can send requests, spawn processes, intercept |
| https://docs.mitmproxy.org/stable/api/events.html | none shown | HTTP/TCP/UDP/WebSocket/TLS/connection event hooks |
| https://docs.mitmproxy.org/stable/addons/examples/ | none shown | rewrite, short-circuit with a made response, inject WS messages, duplicate and replay |
| https://docs.mitmproxy.org/stable/overview/features/ | none shown | Map Local, Map Remote, client/server replay, sticky cookies, blocklist |
| https://www.zaproxy.org/docs/automate/automation-framework/ | none shown | the job vocabulary incl. spider, spiderAjax, requestor, replacer, script |
| https://www.zaproxy.org/docs/desktop/addons/automation-framework/environment/ | none shown | contexts, include/exclude regex, authentication and sessionManagement methods, TOTP |
| https://www.zaproxy.org/docs/desktop/addons/automation-framework/job-requestor/ | none shown | url, method, httpVersion, headers, data, responseCode |
| https://www.zaproxy.org/docs/api/ | none shown | daemon mode, API key, view/action/other |
| https://www.zaproxy.org/docs/desktop/addons/mcp-integration/ | n/a | official ZAP MCP add-on: ~15 tools, 8 resources, 2 prompts, localhost:8282 |
| https://www.zaproxy.org/blog/2026-04-02-zap-mcp-server/ | 2026-04-02 | announcement of the same |
| https://docs.projectdiscovery.io/templates/structure | none shown | template shape |
| https://docs.projectdiscovery.io/templates/reference/matchers | none shown | matcher types and parts |
| https://docs.projectdiscovery.io/templates/protocols/http/basic-http | none shown | headers, body, redirects, cookie persistence, response chaining |
| https://docs.projectdiscovery.io/templates/protocols/http/raw-http | none shown | full raw request text with helper interpolation |
| https://docs.projectdiscovery.io/templates/protocols/http/fuzzing-overview | none shown | fuzzing part/type/mode, pre-condition, `analyzer: time_delay` |
| https://docs.projectdiscovery.io/templates/reference/oob-testing | none shown | `{{interactsh-url}}`, `interactsh_protocol` dns/http/smtp |
| https://docs.projectdiscovery.io/templates/protocols/headless | none shown | headless steps and request-manipulation actions |
| https://docs.projectdiscovery.io/templates/protocols/code | none shown | the `code` protocol runs bash/python/go |
| https://docs.projectdiscovery.io/templates/workflows/overview | none shown | conditional subtemplates |
| https://github.com/projectdiscovery/interactsh | v1.0.7 shown | DNS/HTTP/SMTP/LDAP baseline; SMB, FTP with self-hosting |
| https://github.com/microsoft/playwright-mcp | n/a | the tool list, snapshot vs vision, `--caps` groups, `--allowed-hosts` |
| https://github.com/ChromeDevTools/chrome-devtools-mcp | n/a | performance traces, network list, `evaluate_script`, console, lighthouse |
| https://github.com/modelcontextprotocol/servers-archived/tree/main/src/puppeteer | archived 2025-05-29 | the older Puppeteer MCP, read-only now |
| https://github.com/ffuf/ffuf | n/a | FUZZ keyword in URL/headers/body, clusterbomb/pitchfork/sniper, matchers and filters, `-rate` |
| https://github.com/epi052/feroxbuster | n/a | recursion, link extraction, filters, `--rate-limit` |
| https://github.com/s0md3v/Arjun | n/a | parameter discovery, 25,890-name default dictionary, chunked probing |
| https://github.com/PortSwigger/param-miner | n/a | "up to 65,000 param names per request" via binary search plus diffing |
| https://projectzero.google/2024/06/project-naptime.html | 2024-06-20 | Code Browser, Python, Debugger, Reporter; Perfect Verification |
| https://projectzero.google/2024/10/from-naptime-to-big-sleep.html | 2024-11-01 | the SQLite `seriesBestIndex` find; local tools only |
| https://blog.google/technology/safety-security/cybersecurity-updates-summer-2025/ | 2025-07-15 | Big Sleep and CVE-2025-6965; human threat-intel targeting |
| https://deepmind.google/discover/blog/introducing-codemender-an-ai-agent-for-code-security/ | 2025-10-06 | fuzzing, SMT, critique tool; every patch human-reviewed |
| https://www.anthropic.com/research/building-ai-cyber-defenders | 2025-10-03 | Cybench/CyberGym numbers; deliberately avoided offensive enhancements |
| https://www.darpa.mil/news/2025/ai-cyber-challenge-winners-def-con-33 | 2025-07-08 | AIxCC prize pool; finalists' cyber reasoning systems open-sourced |
| https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/ | 2025-06-16 | private data + untrusted content + external communication |
| https://arxiv.org/abs/2506.08837 | v1 2025-06-10, v3 2025-06-27 | six design patterns; constrain what happens after untrusted input |
| https://arxiv.org/abs/2503.18813 | v1 2025-03-24, v2 2025-06-24 | CaMeL; capabilities gate each tool call |
| https://research.google/pubs/an-introduction-to-googles-approach-for-secure-ai-agents/ | 2025 | three principles; deterministic Layer 1, non-deterministic Layer 2 |
| https://code.claude.com/docs/en/agent-sdk/secure-deployment | none shown | `--network none` plus credential-injecting logging proxy; hostname allowlists are TLS-blind |
| https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/mitigate-jailbreaks | none shown | untrusted content belongs in `tool_result`; JSON-encode it; least privilege |
| https://www.anthropic.com/research/prompt-injection-defenses | 2025-11-24 | 1% attack success under adaptive Best-of-N, called meaningful risk |
| https://www.hackerone.com/policies/code-of-conduct | none shown | hackbots must not run fully autonomously; automation and rate limits |
| https://www.bugcrowd.com/resources/hacker-resources/code-of-conduct/ | updated 2025-11-25 | manually review and validate GenAI-assisted reports before submitting |
| https://www.bugcrowd.com/blog/bugcrowd-policy-changes-to-address-ai-slop-submissions/ | 2026-03-10 | 30-day suspension after 10 consecutive invalid AI-attributable reports |
| https://www.bugcrowd.com/blog/sloptimism-is-breaking-any-system-built-on-human-validation/ | 2026-04-23 | 334% triage queue increase |
| https://daniel.haxx.se/blog/2025/07/14/death-by-a-thousand-slops/ | 2025-07-14 | ~20% of 2025 curl submissions AI slop |
| https://daniel.haxx.se/blog/2026/01/26/the-end-of-the-curl-bug-bounty/ | 2026-01-26 | bounty ended 2026-01-31; confirmation rate fell from >15% to <5% |

### Would not fetch, or could not be verified

- https://openai.com/index/introducing-aardvark/ returned HTTP 403. Nothing about
  OpenAI's Aardvark is asserted here.
- https://genai.owasp.org/llmrisk/llm01-prompt-injection/ and
  https://genai.owasp.org/resource/agentic-ai-threats-and-mitigations/ both
  returned 403. LLM01's content was read from the project's own repository
  (https://raw.githubusercontent.com/OWASP/www-project-top-10-for-large-language-model-applications/main/2_0_vulns/LLM01_PromptInjection.md);
  the Agentic AI threats document could not be read and no threat IDs from it are
  quoted.
- Google's AI VRP pages on bughunters.google.com returned title-only content, so
  nothing about that program is asserted.
- Nuclei's payload/attack-mode documentation pages
  (`.../protocols/http/payloads`) returned 404, so the claim that Nuclei supports
  batteringram/pitchfork/clusterbomb attack modes is **not** made here.
- No official ProjectDiscovery MCP server was found; only third-party wrappers.
- AIxCC placings and per-team counts were not primary-verified and are not stated.
- The date on the raw.pm XBOW critique could not be established.
