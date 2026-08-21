# 22 -- Corpus instruction wiring: the shipped text against the tool surface

Axis: every instruction in the shipped corpus that names something the harness
does not provide. Scope: the 50 playbook bodies (`src/redkraken/playbooks/*/playbook.md`),
the six `SKILL.md` bodies (`src/redkraken/skills/*/SKILL.md`), and the 84 reference
pages.

The authority against which every claim below is checked is `roster.CONTRACTS`
(`src/redkraken/roster.py:592-838`), the handlers that serve those contracts
(`src/redkraken/_launch.py`), the answer shape the door returns
(`src/redkraken/proxy.py:3577`), the frozen mission packet
(`src/redkraken/packet.py:43`), and the offline-tool registry migrations.

## Reference pages: out of instruction scope

84 reference pages exist: 74 under `playbooks/*/references/` and 10 under
`skills/*/references/`. All 74 playbook pages and 1 skills page open with an
explicit maintainer / not-projected marker, so they are background. The 9
unmarked pages are `skills/analyse-source/references/sinks-*.md`, which are
target-language sink catalogues. No reference page anywhere in the corpus names
an `mcp__rk2__*` tool. The single harness instruction in the unmarked set is
`skills/analyse-source/references/sinks-js.md:10-12` -- `jq` over `.sources` and
`.sourcesContent` -- and it is valid: `jq` is registered
(`migrations/20260814T030000Z__an_offline_tool_becomes_evidence.sql:159`) and
granted to `js_analyst` (`:239-241`).

Everything in sections 1-6 is therefore confined to the 50 playbook bodies and
the 6 `SKILL.md` bodies.

## 1. Tool names

43 `mcp__rk2__*` mentions across the corpus. **Every name exists in
`roster.CONTRACTS`. Zero nonexistent names.** There are also zero unprefixed
mentions of a tool's bare name presented as a callable.

| Name | Mentions | Files | Exists |
| --- | --- | --- | --- |
| `mcp__rk2__http_request` | 27 | 26 | yes, `roster.py:747` |
| `mcp__rk2__run_tool` | 5 | 3 | yes, `roster.py:777` |
| `mcp__rk2__run_skill_script` | 3 | 3 | yes, `roster.py:808` |
| `mcp__rk2__get_attack_surface` | 2 | 2 | yes, `roster.py:593` |
| `mcp__rk2__get_artifact` | 2 | 2 | yes, `roster.py:657` |
| `mcp__rk2__submit_mission_result` | 1 | 1 | yes, `roster.py:670` |
| `mcp__rk2__get_receipts` | 1 | 1 | yes, `roster.py:629` |
| `mcp__rk2__get_hypotheses` | 1 | 1 | yes, `roster.py:603` |
| `mcp__rk2__get_evidence` | 1 | 1 | yes, `roster.py:613` |

Seven contracts are never named by the corpus: `get_slate`, `pick_task`,
`request_validation`, `request_report`, `park_for_human`,
`get_validation_packet`, `submit_verdict`. All seven belong to the orchestrator
or the validator (`roster.py:893-985`), and the corpus is subagent-facing text,
so the silence is correct rather than a gap.

**The defect is not in the names.** Every failure below is a real tool asked to
do a thing it was not given.

## 2. Arguments and fields

### 2.1 `identity_slot` on `mcp__rk2__http_request` -- does not exist

`roster.py:747-776` declares `method`, `url`, `headers` and nothing else. The
omission is deliberate and documented in the contract itself
(`roster.py:767-774`):

> No body and no identity. Both were declared here and neither was ever
> reachable [...] the runtime opens the Tool run with the identity already
> chosen and the capability already minted, so an identity named at call time
> would be naming a decision that has been taken.

`Contract` is served with `additionalProperties: false`, so the call is refused
at the gate before it reaches a handler.

**39 occurrences across 30 files.** 29 playbooks plus
`skills/use-identity/SKILL.md:24` and `:29`, the latter a literal worked example
the model is meant to copy:

```
{"url":"https://target.example/path","method":"GET","identity_slot":"member-a"}
```

The 29 playbooks, with the first occurrence line: `api:43`,
`api-authorization:56`, `authentication:33`, `browser-framing:30`,
`browser-realtime:29`, `browser-storage:28`, `cms:52`,
`command-directory-injection:42`, `deserialization:71`,
`exceptional-conditions:44`, `file-resolution:59`, `graphql:43`, `grpc:50`,
`identity-lifecycle:29`, `identity-parsing:33`, `information-disclosure:49`,
`jwt-jose:33`, `logging:46`, `nosql-injection:47`, `object-ownership:48`,
`orm:49`, `payment-workflows:40`, `routing:30`, `spreadsheet-injection:50`,
`sql-injection:47`, `ssrf-url-routing:50`, `ssti:45`,
`structured-injection:45`, `web-cache:30`.

A further 7 playbooks inherit the instruction transitively: 36 playbooks list
`use-identity` in `bb:skills`, and the Skill body carries the bad argument.

**This is worse than a schema mismatch.** `agent.Egress`
(`src/redkraken/agent.py:293-313`) carries exactly one capability for the whole
child. The door then refuses any mismatch:

```sql
-- migrations/0039_proxy_capabilities.sql:54-59
AND coalesce(p_identity, '') IS DISTINCT FROM
    coalesce(v_args ->> 'identity_slot', '') THEN
    RAISE EXCEPTION 'egress identity does not match authorized tool run'
```

Because the contract has no `identity_slot`, the authorising tool run's args
carry `''`, so the only identity the door will accept is the empty one. Every
playbook whose reading is "label A versus label B" -- the entire authorization
family -- has no mechanism at all, not merely a mis-spelled one.

### 2.2 A request body -- does not exist

Same contract, same comment (`roster.py:767-774`): "the child has no store, so
it cannot name a body the door could send". `_launch._spend`
(`_launch.py:680`, call at `:706-714`) passes only `url`, `capability`,
`program_id`, `method`, `headers`, `trust` to `proxy.spend`. There is no
parameter through which bytes could travel.

The corpus instructs a request body in 17 playbooks: `agentic-ai:53`
(instruction in a pipeline field), `api:53`, `api-authorization:56` ("same body
shape"), `browser-storage:56` (body-borne credential), `deserialization:70`
(serialised blob), `file-upload:61` (multipart store), `graphql:42-44`
(selection document), `grpc:50-51` (recorded call body), `identity-parsing:56`
(post the assertion back), `nosql-injection:46` (JSON operator), `payment-workflows:51`,
`race-conditions:46`, `request-parsing:31` (body as a carrier),
`spreadsheet-injection` (export payload), `ssti:78`,
`structured-injection:45` (XML), `webauthn:34` (factor field replaced).

The gate does not merely drop the body -- `additionalProperties: false` means
the call carrying one is refused outright.

### 2.3 `mcp__rk2__get_artifact` by hash -- wrong field

`roster.py:657-669` takes `artifact_label` with pattern `^AF[0-9]{1,9}$`, and
the contract's own comment says the hash "is reported and is never an argument".

`skills/analyse-source/SKILL.md:16` instructs: "Call `mcp__rk2__get_artifact`
with the hash the Task names". One file, one occurrence, and it is the first
call the js_analyst is told to make.

### 2.4 Fields the corpus tells the model to read out of an answer

`_launch._spend` returns exactly eight keys (`_launch.py:725-734`):
`served`, `status`, `receipt`, `decision`, `detail`, `byte_size`, `truncated`,
`body`. `proxy.Answer` (`proxy.py:3577`) carries five: `status`, `body`,
`receipt`, `decision`, `detail`. **No response headers. No timing. No artifact
label.**

Response headers the corpus tells the model to read, with the file and the
first line: `browser-framing:21` (the entire `header_policy_observed` claim,
:30-44 and :48-56), `browser-realtime:42-44` (`Upgrade`, `Connection`,
`Sec-WebSocket-Accept`), `browser-storage:29` (`HttpOnly`, `Secure`,
`SameSite`, `Domain`, `Path`, :43-48), `cookies:19` (`Set-Cookie`),
`web-cache:22` (`Cache-Control`, `Age`, `Vary`, `X-Cache`, :61-63),
`request-integrity:22` (ACAO / ACAC, :74-84), `api:54` (`Retry-After`,
`RateLimit-`, :63-64), `grpc:42-43` (`grpc-status` trailer),
`http-desync:58` (`Alt-Svc`, `HSTS`, :42-44), `request-parsing:37`
(`Location`), `supply-chain:44` (SourceMap header, :43-44),
`deployment:35` ("the header that says which program answered", :126-127),
`file-upload:70` (content type, disposition, length),
`realtime:21`, `structured-injection:20`, `workload-identities:22`,
`exceptional-conditions:56`, `secrets:44`, `object-ownership:49`,
`deserialization:107`, `jwt-jose:43`, `logging:96`, `cms:76`,
`sql-injection:76`, `agentic-ai:54`, `attack-surface:53`.

Timing the corpus tells the model to measure: `command-directory-injection:47`
(the whole `timing_differential` reading at :98-102), `api:64` ("a latency that
steps"), `sql-injection:74`, `ssrf-url-routing:118`, `web-cache:91`,
`race-conditions:80` (correctly told *not* to claim it).

Artifact labels for a response the run itself produced: see 3.6.

### 2.5 Header names and values the schema or the proxy will not carry

`headers` keys must match `^[A-Za-z][A-Za-z0-9-]{0,63}\Z` and values
`^[\x20-\x7e]{0,1024}\Z` (`roster.py:761-765`). `\Z` rather than `$` is
deliberate: a trailing newline is the character a smuggled request would ride
on. Separately `proxy.HOP_BY_HOP` (`proxy.py:288-301`) drops `connection`,
`content-length`, `host`, `keep-alive`, `proxy-authenticate`,
`proxy-authorization`, `proxy-connection`, `te`, `trailer`,
`transfer-encoding`, `upgrade` from whatever the caller wrote.

So `browser-realtime:42` and `realtime:48`, which ask for a WebSocket upgrade,
cannot send `Upgrade` or `Connection` -- both are stripped -- and cannot read
them back either. `http-desync` cannot set `Content-Length` or
`Transfer-Encoding`, which is the whole of its subject.

### 2.6 Skill-script argument names -- correct

`skills/compare-responses/SKILL.md:20-22` names `skill_name`, `script`,
`arguments`, matching `roster.py:808-813`. The names are right. What is wrong is
where the values come from -- see 3.6.

## 3. Actions and verbs

| Action the corpus instructs | Status | Evidence |
| --- | --- | --- |
| Send a GET/HEAD/OPTIONS with headers | possible today | `roster.py:747-776`, `_launch.py:680-734` |
| Send a request as a named identity | **impossible** | `roster.py:767-774`; `agent.py:293-313`; `0039_proxy_capabilities.sql:54-59` |
| Send a request body | **impossible** | `roster.py:767-774`; `_launch.py:706-714` |
| Read a response header | **impossible** | `proxy.py:3577`; `_launch.py:725-734` |
| Measure request latency | **impossible** | same |
| Send two requests at once | **impossible** | `_launch.py:395` -- every supervisor call is taken under one `threading.Lock` on one stdio channel, strictly one in flight |
| Open a WebSocket / send a frame | **impossible** | `Upgrade`/`Connection` in `proxy.py:288-301`; the door speaks one request/one answer |
| Start a browser mission | **impossible from the model** | no `offline_tools` row; the only entry point is the operator CLI `rk browser run` |
| Host a page the target fetches | **impossible** | no serving verb in any of the 16 contracts |
| Ask the runtime for a callback correlator | **impossible** | `mint_callback_correlator` is granted to `rk2_runtime` only, `20260812T040000Z__a_callback_arrives_on_a_declared_channel.sql:799-801` |
| Read a receipt or artifact produced mid-run | **impossible** | the packet is compiled once before the container starts, `execution.py:1794`, `_launch.py:1017` |
| Run `jq` over a document | possible only for `recon` and `js_analyst` | `20260814T030000Z...sql:239-241` |
| Run `compare-responses` | possible for `web_hunter`, over exactly 2 packet artifacts | `20260922T030000Z...sql:443`, `:477-479` |
| Chain one tool run into the next | possible today | `tool.py:521-535` returns `outputs`, each with a `label` |

### 3.1 Two identities in one mission

`agent.Egress` holds one capability. `0039_proxy_capabilities.sql:54-59` binds
the door's identity to the authorising tool run's args, and the contract cannot
put an identity there. The A/B design in `api-authorization:36`,
`graphql:34`, `object-ownership:30`, `browser-realtime:44`,
`workload-identities:43`, and the whole `use-identity` Skill, has no mechanism.

### 3.2 Concurrency

`race-conditions:65`: "Send two identical copies of the action at once through
the same slot." `_launch.py:395` takes a lock, writes one frame, and blocks for
its answer. There is no path by which two requests are in flight together, so
the playbook's only distinguishing step is unreachable -- and its sequential
control at `:46` is deliberately not the claim.

### 3.3 Browser missions

`skills/browser-evidence/SKILL.md:62` and `:166`: "Start the mission through
`mcp__rk2__run_tool`". `roster.py:793` fixes that argument to the enum
`("jq", "js_map", "js_parse", "js_routes")`, and `open_offline_tool_run` refuses
a name the registry does not hold. There is no browser row in `offline_tools`;
`browser_runs` / `open_browser_run` exist but are reached only by the operator
CLI `rk browser run`.

The failure is doubled: `SKILL.md:2` names `mcp__rk2__run_tool` in
`allowed-tools`, but `browser-evidence` is a `web_hunter` Skill, and
`offline_tool_roles` grants `web_hunter` only `compare_responses`. Every
`run_tool` call a web_hunter makes is refused by
`20260814T030000Z...sql:606-610`:

```sql
RAISE EXCEPTION 'the % role may not run %', v_run.role, p_tool
```

The Skill also names ten browser actions at `:20-22` -- navigate, wait_for,
fill, inject, click, assert_text, assert_absent, probe, capture_dom, screenshot
-- none of which any contract accepts. Six playbooks hold this Skill:
`browser-messaging`, `browser-script`, `client-side-path-traversal`, `cookies`,
`oauth`, `realtime`.

`browser-evidence` declares no `bb:runtime-tools`, which is exactly why
`roster._check_skills` never fires on it: the `RUN_TOOL_NAMES` check runs only
when `runtime_tools` is non-empty.

### 3.4 A callback correlator

`webhooks:36`: "Ask the runtime for a correlator for this subject." There is no
contract for it, no packet section carries one (`packet.py:43` --
`("surface", "hypotheses", "evidence", "receipts", "artifacts")`), and
`mint_callback_correlator` / `record_callback_interaction` are granted to
`rk2_runtime` alone. Even if a callback landed, `callback_interaction` has
`allowed_provenance '{callback}'`
(`20260812T040000Z...sql:348-350`) while `submit_mission_result` accepts exactly
one of `receipt_label` or `tool_run_label`
(`_launch.DESCRIPTIONS["submit_mission_result"]`). The claim cannot be filed.

### 3.5 Requests from a role with no egress

`supply-chain:30`: "One request: the application's own document, with nothing
presented", and `:41` "Up to three requests". `supply-chain`'s `bb:skills` are
`["analyse-source", "handle-untrusted-content"]`, which only `js_analyst` loads,
and `js_analyst` holds no `net.request` group (`roster.py:539`, `ROLES`). The
playbook instructs seven requests from a role that cannot make one.

### 3.6 The mid-run read gap -- the single largest break

The mission packet is compiled once, on a read-only connection, before the
container starts (`packet.compile()` at `packet.py:587`, called from
`execution.py:1794`; the reader is built at `_launch.py:1017`). `packet.Reader`'s
docstring states it: "The five state reads, answered from the packet and from
nothing else."

`_spend` returns a `receipt` label but **no artifact label**
(`_launch.py:725-734`). So an Artifact written by a request this run made can
never be named by this run.

Consequences:

* Every `compare-responses` call in the corpus -- **39 playbooks name it in the
  body** -- is told to difference two answers the run just fetched. Its
  arguments are `first` and `second`, both `artifact` kind
  (`20260922T030000Z...sql:443`). Neither label is obtainable.
* `attack-surface:76-79`: "the identification is a `jq` run over the stored
  Artifact". Same gap; `recon` holds `jq`, but not the label.
* `skills/compare-responses/SKILL.md:20-22` says "each value is the Artifact
  label the packet gave you" -- honest about the source, and that source
  predates every answer the mission produces.

Tool-run to tool-run chaining does work: `tool.py:521-535` returns `outputs`
each carrying a `label`. Exchange to tool-run does not.

### 3.7 `compare-responses` takes exactly two

`first` and `second`, both required. 11 playbooks instruct a difference over
three or more, or over "sets": `agentic-ai:75`, `authentication:74`,
`browser-storage:64`, `browser-realtime:55`, `identity-lifecycle:63`,
`routing:77`, `web-cache:71`, `workload-identities:68`, `jwt-jose:82`,
`request-integrity:73`, `webauthn:60`.

## 4. Offline tools and skill scripts

Registered programs, six in total:

| Program | Reachable by | Roles granted | Corpus names it |
| --- | --- | --- | --- |
| `jq` | `run_tool` | recon, js_analyst | `enumerate-surface/SKILL.md:35`, `analyse-source/SKILL.md:25`, `attack-surface:77`, `sinks-js.md:10-12` |
| `js_parse` | `run_tool` | js_analyst | `analyse-source` |
| `js_routes` | `run_tool` | js_analyst | `analyse-source` |
| `js_map` | `run_tool` | js_analyst | `analyse-source` |
| `compare_responses` | `run_skill_script` | web_hunter | 39 playbooks + its own Skill |
| `extract_paths` | `run_skill_script` | js_analyst | `analyse-source/SKILL.md:27-28` |

Registry lines: `20260814T030000Z...sql:159` (jq), `:203-208` (its args
`filter` and `input`, both required), `:239-241` (roles);
`20260814T050000Z...sql:436-450` (js_parse / js_routes / js_map), `:453-464`
(all three take an `artifact_kind` of `source`), `:472-475` (roles);
`20260922T030000Z...sql:443` (compare_responses and extract_paths), `:477-479`
(roles).

**Named but not registered:** the browser mission (section 3.3). That is the
only program the corpus names that the registry does not hold. There is no
misspelled tool name anywhere in the corpus.

**Named but not granted to the role that is told to use it:** `run_tool` in
`browser-evidence/SKILL.md:2` and `:62`, a `web_hunter` Skill. `web_hunter`
holds no `run_tool`-reachable program at all.

**Named for a document the tool cannot read:** `analyse-source` over an HTML
document, at `supply-chain:32` and `external-resources:31`. All three js tools
take an artifact of kind `source`, and `js_parse` reports "its size, its shape,
the source map it points at and the string literals it holds"
(`20260814T050000Z...sql:440-442`). Neither `<script src>` nor `integrity` nor
`crossorigin` is recoverable from that output, and `jq` does not parse HTML.

## 5. Evidence the corpus promises

`observation_kinds` fixes `allowed_provenance` per kind
(`migrations/0018_vocabularies.sql:216-249`). A step whose evidence cannot be
produced makes the playbook unable to reach `supported`.

### 5.1 `content_match` -- `{tool_run}` only

A quotation the model writes from the 4096-byte excerpt
(`packet.py:60`, `_launch.py:725`) is a reading, not a tool run. To file a
`content_match` the role must hold a tool that can parse the document. Playbooks
promising `content_match` where no such tool is reachable:

* `kubernetes:75` -- "Name in the observation which of the second list is
  present, and quote it. That quotation is the finding." `web_hunter` holds no
  `jq`. Frontmatter demands `content_match` for both `supported` and `refuted`
  (`kubernetes:13`).
* `external-resources:43` and `:59` -- `content_match` on the stored document,
  needing an HTML parse that does not exist.
* `spreadsheet-injection:68` -- "Request the export route and store what comes
  back. Do not read it as a response." No CSV or zip parser is registered, and
  `web_hunter` holds no `jq`.
* `supply-chain`, `logging`, `cms`, `information-disclosure`, `secrets` -- same
  shape: a document fetched over the wire, a claim about its contents, and no
  registered parser the role may run.

`attack-surface:74-86` is the one playbook that states the rule correctly and
then stops at the honest end: "An Artifact `jq` cannot parse has no registered
tool behind it today, and the honest end of that path is inconclusive."

### 5.2 `transport_parameters_observed` -- needs a measurement receipt

`migrations/0025_transport_claims.sql:250` defines the kind, and `:299-321`
`transport_observation_guard()` requires a receipt marked `transport_citable`,
which is set only for `receipts.purpose = 'transport_measurement'` (`:64`).
`http_request` produces `target_traffic`. `http-desync`'s only evidence kind is
therefore unreachable, and the playbook concedes it at `:170-177`.

### 5.3 `header_policy_observed` -- needs headers

`browser-framing:13` demands it for both `supported` and `refuted`. No response
header reaches the model (2.4). The same gap kills `request-integrity`'s CORS
reading (`:74-84`), `web-cache`'s cache reading (`:61-63`), `cookies`
(`Set-Cookie`), `browser-storage:43-48`, and `browser-realtime:42-44`.

### 5.4 `callback_interaction` -- provenance the submit tool does not accept

Section 3.4. `webhooks` cannot file its claim even in the hypothetical where a
callback arrived.

### 5.5 `timing_differential` -- needs a clock the answer does not carry

`command-directory-injection:98-102`. `_spend` returns no elapsed time.

### 5.6 `state_change` after a body-bearing write

Every playbook in 2.2 promises a `state_change` or `credential_effect` produced
by a request it cannot send.

## 6. Rank the damage

Verdicts. `not runnable` means the first evidential step cannot be taken at all.
`partial` means requests land but a named later step breaks.

| Playbook | Verdict | First step that breaks | Why |
| --- | --- | --- | --- |
| agentic-ai | not runnable | `:53` | instruction must ride in a request field; no body argument (`roster.py:767-774`) |
| api | not runnable | `:42` | `identity_slot` not a contract argument; later body `:53`, headers `:54`, latency `:64` |
| api-authorization | not runnable | `:56` | `identity_slot` plus "same body shape"; two identities unreachable (`0039:54-59`) |
| attack-surface | partial | `:77` | requests land; `jq` needs the Artifact label of a response, which `_spend` never returns |
| authentication | not runnable | `:43` | `identity_slot`; `:74` compares three answers with a two-argument script |
| browser-framing | not runnable | `:30` | `identity_slot`; whole `header_policy_observed` claim needs response headers (`:48-56`) |
| browser-messaging | not runnable | `:40` | "Plan a mission" -- no browser verb on the surface |
| browser-realtime | not runnable | `:29` | `identity_slot`; `Upgrade`/`Connection` stripped (`proxy.py:288-301`); `:55` compares three |
| browser-script | not runnable | `:40` | browser mission with `navigate`/`inject` |
| browser-storage | not runnable | `:28` | `identity_slot`; `:43-48` cookie attributes are response headers; `:56` body credential |
| client-side-path-traversal | not runnable | `:30` | browser mission |
| cms | not runnable | `:51` | `identity_slot`; `:76` response headers; `:88` compare needs response artifacts |
| command-directory-injection | not runnable | `:41` | `identity_slot`; multipart filename needs a body; `:98-102` timing |
| cookies | not runnable | `:28` | browser mission; `Set-Cookie` unreadable anyway |
| deployment | partial | `:89` | GETs at `:49` land; compare needs artifact labels; `:126-127` wants a response header |
| deserialization | not runnable | `:70` | `identity_slot` and a serialised body |
| exceptional-conditions | not runnable | `:43` | `identity_slot`; `:56` response headers |
| external-resources | partial | `:40` | packet Artifact readable; no tool extracts `<script src>`, `integrity`, `crossorigin` from HTML |
| file-resolution | not runnable | `:58` | `identity_slot` |
| file-upload | not runnable | `:61` | multipart store needs a body; `:70` wants disposition and length headers |
| graphql | not runnable | `:42` | `identity_slot` and the selection document as a body |
| grpc | not runnable | `:50` | `identity_slot` and the recorded call body; `:42-43` `grpc-status` trailer |
| http-desync | not runnable | `:95` | compare needs response artifacts; the only evidence kind needs `transport_measurement` (`:170-177`) |
| identity-lifecycle | not runnable | `:29` | `identity_slot`; `:41` "with no `identity_slot` at all" makes both arms the same call |
| identity-parsing | not runnable | `:33` | `identity_slot`; `:56` posts an assertion body; `:84` compares three |
| information-disclosure | not runnable | `:49` | `identity_slot`; the document/route difference needs a parser `web_hunter` may not run |
| jwt-jose | not runnable | `:33` | `identity_slot` (token variants would otherwise ride in a header); `:82` compares sets |
| kubernetes | partial | `:75` | unauthenticated GETs land; the quoted fact must be a `content_match`, and `web_hunter` holds no `jq` |
| logging | not runnable | `:45` | `identity_slot`; `:96` response headers |
| nosql-injection | not runnable | `:46` | `identity_slot` and a JSON operator body |
| oauth | not runnable | `:31` | "start the flow in a browser under `browser-evidence`" |
| object-ownership | not runnable | `:39` | "as label A" / `:42` "as label B" -- one capability per child |
| orm | not runnable | `:48` | `identity_slot` |
| payment-workflows | not runnable | `:40` | `identity_slot`; `:51` sends an operation value in a body |
| race-conditions | not runnable | `:65` | "two identical copies at once" -- `_launch.py:395` serialises every call |
| realtime | not runnable | `:48` | WebSocket handshake; `Upgrade`/`Connection` are hop-by-hop; also a browser mission |
| request-integrity | not runnable | `:73` | compares a baseline against each arm with a two-argument script; `:74-84` needs ACAO/ACAC |
| request-parsing | not runnable | `:31` | the body carrier does not exist; `:37` reads `Location` |
| routing | not runnable | `:30` | `identity_slot`; `:77` compares sets |
| secrets | partial | `:71` | packet Artifact and a header-borne candidate both work; compare needs the response's artifact label |
| spreadsheet-injection | not runnable | `:50` | `identity_slot`; `:68` needs a CSV/zip parser no role holds |
| sql-injection | not runnable | `:46` | `identity_slot`; `:74` timing; `:76` response headers |
| ssrf-url-routing | not runnable | `:49` | `identity_slot`; `:118` timing |
| ssti | not runnable | `:45` | `identity_slot`; `:78` template payload in a body |
| structured-injection | not runnable | `:45` | `identity_slot` and an XML body |
| supply-chain | not runnable | `:30` | "One request" from `js_analyst`, a role with no `net.request` group |
| webauthn | not runnable | `:34` | "the factor field replaced" needs a body; `:60` compares against "the two ends of the scale" |
| web-cache | not runnable | `:30` | `identity_slot`; `:61-63` reads `Cache-Control`, `Age`, `Vary`, `X-Cache` |
| webhooks | not runnable | `:36` | "Ask the runtime for a correlator" -- no verb, no packet section, runtime-only grant |
| workload-identities | not runnable | `:43` | credential plus "the caller's own" identity in one call; `:22` reads headers; `:68` compares sets |

**Tally: 0 runnable end to end, 5 partial, 45 not runnable.**

The five partial playbooks -- `attack-surface`, `deployment`,
`external-resources`, `kubernetes`, `secrets` -- share one property: they send
unauthenticated GETs, or read only packet-supplied Artifacts. They are exactly
the playbooks that never needed an identity, a body, or a response header. Each
still breaks at its evidence step, all five for the same reason: the run cannot
name an Artifact it produced.

Ticket 101's rewrite is therefore repair, not enhancement, for 45 of 50. The
three highest-leverage surface repairs, in order of playbooks unblocked:

1. Return an `artifact_label` from `http_request` -- unblocks the evidence step
   of 39 playbooks and all 5 partials.
2. Give `http_request` a body -- unblocks 17 playbooks' request step.
3. Give the child a way to spend more than one identity -- unblocks the whole
   authorization family, roughly 30 playbooks. This is the deepest: it needs a
   change at the door (`0039_proxy_capabilities.sql:54-59`), not only in the
   contract.

## What a gate would have to assert

Nothing today reads a playbook or Skill body. `playbook._playbook()`
(`playbook.py:399-513`) validates frontmatter -- name, category and outputs
family, triggers, risk floor, reference symmetry, evidence expectations -- and
then does `instructions=body` with no inspection beyond `if not body: raise`.
`roster._check_playbooks` (`roster.py:1694-1701`) checks that
`set(one.skills) - set(SKILLS)` is empty and that some single role loads them
all. `roster._check_skills` (`roster.py:1660-1730`) checks `bb:runtime-tools`
against `RUN_TOOL_NAMES` -- but only when that list is non-empty, which is why
`browser-evidence` slips through. The DB has `role_lacks_skill`
(`20260823T000000Z...sql:285-290`), also frontmatter-level.

The body is the only unchecked artefact in a system that checks everything else.
A gate over it would have to assert:

1. **Every `mcp__rk2__*` token in a body is a key of `roster.CONTRACTS`.** Cheap,
   and currently passing -- keep it as the floor.
2. **Every `mcp__rk2__*` token in a body names a tool the executing role holds.**
   The executing role is derivable: the unique role whose `skills` superset the
   playbook's `bb:skills`. This catches `browser-evidence/SKILL.md:2` naming
   `run_tool` for a `web_hunter`, and `supply-chain:30` instructing a request
   from `js_analyst`.
3. **Every backticked identifier adjacent to a tool mention is an argument that
   tool declares.** A body naming `identity_slot` within N tokens of
   `mcp__rk2__http_request` is the 39-occurrence defect, caught by one rule.
   Generalised: extract every `` `name` `` token from a body, and refuse any that
   collides with an argument name in `CONTRACTS` while not being an argument of
   the tool named nearest. This also catches the literal JSON example at
   `use-identity/SKILL.md:29`.
4. **Every `run_tool` / `run_skill_script` program named in a body is a row in
   `offline_tools` granted to the executing role.** Catches the browser mission
   and the `jq`-for-web_hunter class.
5. **Every argument name inside a skill-script instruction is a row in
   `offline_tool_arguments` for that program, and the count of values the body
   instructs does not exceed the count of arguments declared.** Catches the 11
   playbooks that difference three or more with a two-argument script.
6. **Every observation kind in `bb:evidence` has an `allowed_provenance` the
   executing role can actually produce.** A `content_match` requires
   `{tool_run}`, so the role must hold at least one program whose output could
   ground it; a `transport_parameters_observed` requires a
   `transport_measurement` receipt, which no model-facing tool produces. This is
   the check that would have caught `http-desync`, `kubernetes`,
   `spreadsheet-injection` and `browser-framing` at compile time.
7. **A body that instructs reading a field the answer shape does not carry is
   refused.** The answer shape is eight keys (`_launch.py:725-734`). A rule over
   a closed vocabulary of header names, plus the words for timing, would catch
   the 26-file response-header class and the 6-file timing class.
8. **A body that instructs an artifact-consuming tool must trace each artifact
   to the packet.** The strongest single check: no `run_tool` or
   `run_skill_script` instruction may take as input something the same body
   earlier described fetching over the wire. This is the 39-playbook defect and
   the one that survives every other repair.

Checks 1, 2, 4 and 6 are mechanical over frontmatter plus a token scan and could
land immediately. Checks 3, 5, 7 and 8 need a small grammar over the body -- a
list of the corpus's own imperative forms -- but that grammar is worth writing
once, because it is the same grammar the corpus already writes by convention.
