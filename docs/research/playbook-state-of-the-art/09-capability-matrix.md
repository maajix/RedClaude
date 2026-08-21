# 09 - Capability matrix

What the 131 techniques in files `01`-`08` need from the harness, cut against
what `src/redkraken/roster.py` actually offers a child. Everything here was
read in this repository; every claim about our code carries a file:line, and
where a thing was looked for and not found it says so.

Two rules were applied throughout. Claims the research files make about the
outside world are taken as given and were not re-verified. Where two files ask
for the same capability under different names they are merged into one
capability and both names are kept.

## Corrections to `00-todo-and-harness-gaps.md`

`00` was written before the last vocabulary migrations landed and its counts
are stale. Counted from the migrations at this commit:

* **57 property classes**, not 47. `0018_vocabularies.sql:83-170` ships 33;
  `0025_transport_claims.sql`, `20260826T000000Z`, `20260829T000000Z`,
  `20260901T000000Z`, `20260902T000000Z`, `20260903T000000Z` and
  `20260904T000000Z` add the other 24.
* **16 observation kinds**, not 14, of which **11 are evidential**, not 9.
  `0018_vocabularies.sql:216-249` ships 14; `0025_transport_claims.sql:249-254`
  adds `transport_parameters_observed` and
  `20260812T040000Z__a_callback_arrives_on_a_declared_channel.sql:348-350` adds
  `callback_interaction`.
* **55 surface facts**, not 33. `0032_playbooks.sql:38-81` ships 33; eight
  later migrations add 22 more, including `tech_grpc`, `tech_llm`, `tech_orm`,
  `tech_sql`, `tech_template`, `tech_webauthn`, `tech_orchestrator`,
  `tech_openapi`, `xml_request`, `serialized_object_parameter`,
  `path_valued_parameter`, `repeated_parameter_name` and `web_surface`.

One further correction, to a reading I made before checking the schema: the
second-tenant model is **already there**. `identities` carries
`tenant_entity_id` and a `class` in `('anonymous','user','privileged','service')`
at `0003_entities.sql:101-113`, the relationship type `member_of` exists at
`20260813T090000Z__a_recon_run_becomes_typed_surface.sql:218`, and
`0032_playbooks.sql:78-81` already ships `multiple_test_identities`,
`privileged_identity_available`, `anonymous_identity_available` and
`tenant_boundary`. What is missing for `04` is not the model. It is the ability
for a step to say which of them a request runs as, which is capability C.

## The capabilities, ranked by how many techniques they unblock

### A. A request body on `mcp__rk2__http_request` - 61 techniques

**What it is.** One more argument on the one egress contract, carrying the
bytes of a request entity, with whatever content-type discipline the door needs
to keep a receipt honest. Every technique whose reading is "send this document
and see what comes back" is downstream of it: GraphQL, gRPC-transcoded, SOAP,
SCIM, token endpoints, multipart upload, JSON injection, the whole prompt-
injection corpus.

**What exists today.** **Absent.** `roster.py:738-767` declares
`mcp__rk2__http_request` with exactly three arguments - `method` (enum
`GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS`), `url` (`^https?://`) and `headers`.
The schema is closed (`additionalProperties: false`), so a body is refused by
name rather than ignored. The comment at `roster.py:758-765` states the reason
it was removed: "the child has no store, so it cannot name a body the door
could send". The state-changing methods are already in the enum, so today the
child can send a `POST` and can never say what it is posting. The surface fact
`body_parameter` already exists (`0032_playbooks.sql:52`) and describes
endpoints no step can exercise.

**Techniques it unblocks.** 01 #4, #5, #7, #8, #9, #10, #11, #12, #13, #18;
02 #6; 03 #1, #2, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, #16, #17, #18,
#20; 04 #2, #4, #7, #9, #10, #11, #13, #16; 05 #1, #3, #4, #6, #7, #8, #10,
#11, #12, #15, #16; 06 #2; 07 #3, #8, #9, #10; 08 #1, #2, #3, #4, #5, #6, #7,
#8, #9, #10. Sixty-one.

**What it would touch.** `roster.py:738-767` (the contract), `_launch.py:600-637`
(the handler that builds the request) and `_launch.py:680-735` (the result),
the proxy's request path and its `request_agent_sha` / `request_wire_sha`
columns (`0005_artifacts_and_provenance.sql:39-65`), the agent-view redaction in
`proxy.py:645-656`, and a decision about whether a body counts toward the egress
budget added by `20260811T170000Z__egress_budget_at_the_door.sql`. No new
vocabulary: `json_request`, `form_request`, `multipart_request`, `xml_request`
and `body_parameter` all already exist.

**Risk it introduces.** This is the single largest widening in the list. A
body-carrying request, an out-of-band channel and a second tenant each widen
what the agent can do, and each needs its own limit: for the body that limit is
a size ceiling, a content-type set, and the same scope decision the door
already applies to the URL, because a POST the door allows is a state change on
someone's production system.

**Size: medium.** The contract and handler change is small. The bounded part is
deciding what a body does to the receipt, the seal and the budget, and writing
the refusal for a body the door will not carry.

### B. Response headers in the tool result - 18 techniques

**What it is.** Give the child the target's response header names and values,
subject to the same redaction the body already gets, and make at least the
security-relevant ones citable from a receipt.

**What exists today.** **Present on the wire, discarded on the way out.** The
door already hands headers back to the child: `proxy.py:3124-3128` calls
`self._answer(..., body=agent_returned, headers=agent_back)`. They die in
`_launch.py:680-735`, whose returned dict is exactly `served`, `status`,
`receipt`, `decision`, `detail`, `byte_size`, `truncated`, `body`. No header
appears. They are also absent from the agent-visible receipt projection in
`v_records` at
`20260813T090000Z__a_recon_run_becomes_typed_surface.sql:1449-1475`, which
carries lane, purpose, decision, reason, method, scheme, host, port, path,
`status_code`, `identity_label`, `tool_run_label`, `scope_class`, `intercepted`,
`transport_citable`, `request_agent_sha`, `response_agent_sha`, `waited_ms` and
`ts_arrival` - and no header, no `ts_egress`, no `query_sha256`. So the
observation kind `header_policy_observed`
(`0018_vocabularies.sql:216-249`, evidential, provenance `{receipt,tool_run}`)
exists and there is no way for a child to fill it from a receipt.

**Techniques it unblocks.** 01 #1, #15, #17; 02 #1, #2, #3, #4, #5, #9, #10,
#11, #14; 03 #3, #18; 06 #4, #9, #10; 07 #1. Eighteen. The cache cluster is
the bulk of it: without `Age`, `X-Cache`, `Vary` and `Cache-Control` there is
no cache technique at all, and 02 proposes fifteen.

**What it would touch.** `_launch.py:680-735` only, for the tool result. If the
header is to be *cited* rather than merely read, also a projected column on the
receipt view at `20260813T090000Z...:1449-1475` and the redaction split in
`proxy.py:645-656` / `659-698`, which is where `Set-Cookie` and any identity
material has to stay behind. No new vocabulary.

**Risk it introduces.** Headers are where credentials live. `Set-Cookie`,
`Authorization` echoes and `WWW-Authenticate` challenges must go through the
same seal that already keeps auth headers out of `response_for_agent`
(`proxy.py:645-656`), or this quietly becomes a credential exfiltration path
out of the sealed wire view.

**Size: small.** One dictionary in one handler, plus a name allowlist or a
redaction pass and a byte bound. This is the cheapest large win in the file.

### C. The identity question settled - 9 techniques, and 29 of 50 playbooks

**What it is.** Either an argument that names which Identity a request runs as,
or a written answer that one Tool run is one Identity and the playbooks must
say so. Today the corpus says the first thing and the code does the second.

**What exists today.** **Absent as an argument; present as a run-level
binding.** `roster.py:738-767` has no `identity_slot`. The identity is chosen
when the capability is minted, not when the request is sent:
`0039_proxy_capabilities.sql:7,39` mints with `p_identity text DEFAULT ''` and
stores `'identity_slot', coalesce(p_identity,'')` in the capability, and
`20260811T150000Z__encrypted_identity_slots.sql:506,528` refuses to open a slot
whose label differs from the one the capability names. So identity is a
property of the Tool run, and a per-request argument would contradict the mint.
Meanwhile `src/redkraken/skills/use-identity/SKILL.md:24` instructs "Call
`mcp__rk2__http_request` with `identity_slot` set to the chosen label" and gives
a JSON example at line 29 using an argument that does not exist, and 29 of the
50 playbooks repeat it. Worse: `identity_slot` was searched for in
`src/redkraken/packet.py` and **not found**, so the child is not told which
Identity it is running as either - it can only learn the label afterwards from
`identity_label` on its own receipt projection.

**Techniques it unblocks.** 03 #2, #9; 04 #1, #3, #4, #5, #16, #17; 08 #4.
Nine. Its real weight is elsewhere: it is the reason 29 playbooks are prose.

**What it would touch.** If it stays a run-level binding: 29 playbook files,
`skills/use-identity/SKILL.md:24-29`, and one field in the mission packet so
the child knows its own identity. If it becomes an argument: `roster.py:738`,
the mint at `0039_proxy_capabilities.sql:7`, and the lease clamp that
`roster.py:893-988` applies to `web_hunter` (`clamp_to_identity_leases=True`).

**Risk it introduces.** A per-request identity argument would let one Tool run
straddle two Identities, which is exactly the thing the mint currently
prevents; the safe reading is the run-level one.

**Size: small** as a documentation and packet-field change. **Medium** if it
becomes a real argument, because the capability mint has to change with it.

### D. A browser mission startable from a playbook step - 22 techniques

**What it is.** An MCP contract that lets a step open a browser run with a plan
built from the registered actions, instead of an operator typing a CLI command
with a JSON file.

**What exists today.** **Present but unreachable from a playbook step.** The
lane is fully built: ten actions in `browser_driver.py:502-661`, the registry in
`20260814T040000Z__a_browser_mission_runs_behind_the_door.sql:150-260`,
`browser.py:56-57` and `browser.py:129-140`. The only entry point is the
operator CLI - `cli.py:2629-2686` with the parser at `cli.py:1135-1201`, which
requires `--plan` (a JSON file on disk), `--agent-run`, `--image` and
`--authority`. **No browser contract exists in `roster.CONTRACTS`**; it was
searched for and not found. And `skills/browser-evidence/SKILL.md:63` tells the
agent "Start the mission through `mcp__rk2__run_tool`", which is false:
`roster.py:784` closes that tool's enum to `("jq", "js_map", "js_parse",
"js_routes")`. Every one of the sixteen techniques in `06` is written for a
Skill whose first instruction cannot be followed.

**Techniques it unblocks.** All of 06 (#1-#16), plus 01 #6, #17; 02 #8;
03 #4, #13, #14. Twenty-two.

**What it would touch.** A new Contract in `roster.py`, a plan-shape schema
that has to be at least as narrow as `browser_action_arguments`
(`20260814T040000Z...:210-260`), the plan-digest-vs-result-digest check, the
`ROLES` table at `roster.py:893-988` to say which roles may open one, and
`skills/browser-evidence/SKILL.md:63` which is currently wrong.

**Risk it introduces.** The browser is the widest capability in the system:
`navigate` and `click` both carry `reaches_network=true` and `click` carries
`submits=true`, which is, per
`20260814T040000Z...:176-181`, "the whole of how a mission acquires POST".
Handing plan authorship to a model means the scope compiler and the derived
method set are the only thing between a plan and a form submission.

**Size: large.** A new contract, a plan schema, a scope pass and a role
decision, on a lane whose entire design premise so far has been that a human
wrote the plan.

### E. A wider browser action and probe set - 19 techniques

**What it is.** New rows in `browser_actions` and `browser_probes` for the
things `06` needs and the current ten cannot express: reading client-side state
(`localStorage`, `sessionStorage`, service-worker and Cache API registrations),
sending a `postMessage`, enumerating message and event listeners, navigating to
a fragment, and structured probe verdicts richer than one word.

**What exists today.** **Absent, and absent by construction.** The ten actions
are `navigate`, `wait_for`, `fill`, `inject`, `click`, `assert_text`,
`assert_absent`, `probe`, `capture_dom`, `screenshot`
(`20260814T040000Z...:189-208`; the driver methods at
`browser_driver.py:502-661`). `outcome_keys` is capped at 8 lowercase words per
action and the table comment at `20260814T040000Z...:183-188` says a value
outside `rk2_browser_outcome_word` has "nowhere to put" itself, so a structured
verdict is not a configuration change. There is no path by which a plan supplies
JavaScript: `inject` types a registered probe's own payload
(`browser_driver.py:565-568`), and `probe` runs the registry's source and checks
the verdict against the probe's own declared set (`browser_driver.py:609-646`).
The registry is a global table by design
(`20260814T040000Z...:265-269`): "an action the runtime could add is an action
the plan could invent, and the plan is written by a model."

**Techniques it unblocks.** 06 #1, #2, #3, #5, #6, #7, #8, #9, #10, #11, #12,
#13, #14, #15, #16 (all but #4, which is a response header and belongs to B);
plus 01 #6, #17; 03 #4, #14. Nineteen.

**What it would touch.** A migration adding rows to `browser_actions`,
`browser_action_arguments` and `browser_probes`; matching driver methods in
`browser_driver.py:502-661`; possibly the outcome-word vocabulary if a verdict
needs more than one word; `ARTIFACT_FILES` in `browser.py:109-113` if new
evidence is captured.

**Risk it introduces.** `read_client_state` reads exactly the place session
tokens live, and `send_message` is the first action that lets a plan originate
a message the page did not ask for. Both need their own limit; neither is
covered by the existing `reaches_network` / `submits` pair.

**Size: large.** Each action is a migration row plus a driver method plus a
digest decision, and the probes have to be written by us because the design says
a probe owns both halves of its own question.

### F. Out-of-band observation an agent can reach, with a positive control - 14 techniques

**What it is.** A way for a step to obtain a correlator, plant it, and then ask
whether an interaction arrived on it - with a control interaction the runtime
itself triggers, so that silence is evidence of absence rather than evidence of
a broken collector. `08` calls this "the highest-leverage single addition in
this document."

**What exists today.** **Present as an operator capability, unreachable from a
step.** `src/redkraken/oob.py:56-60` exposes `oob serve/up/status/down` and
`src/redkraken/callback.py:52-55` exposes `callback provision/accept/clear`,
both CLI verbs. **No OOB or callback contract exists in `roster.CONTRACTS`**;
searched for and not found. The evidence side is already built:
`20260812T040000Z__a_callback_arrives_on_a_declared_channel.sql:297-303` adds
`observations.callback_interaction_id`, `:319-321` widens `provenance_kind` to
include `'callback'`, and `:348-350` inserts the evidential observation kind
`callback_interaction`. `0018_vocabularies.sql:251-269` records why this had to
wait - `out_of_band_interaction` was rejected because "its `allowed_provenance`
would be empty", and goes back in "when the collector that generates its
provenance exists". The collector now exists. The agent still cannot use it.
There is no positive control anywhere: searched for, not found.

**Techniques it unblocks.** 01 #7, #12; 03 #1, #3, #7, #12; 04 #9; 05 #5, #15;
06 #8; 08 #1, #2, #3, #7. Fourteen.

**What it would touch.** A new Contract in `roster.py`, the `observe-out-of-band`
Skill `08` proposes, the correlator mint that is currently in the operator CLI
(`callback.py:52-55`), the `ROLES` table, and a positive-control mechanism that
does not exist in any form today.

**Risk it introduces.** A correlator planted in a target's system is a durable
artefact we do not control the lifetime of, and a channel that records arrivals
is a channel a third party can also reach. It needs its own limit: one channel
per Program, a label the runtime mints rather than the model, and an expiry.

**Size: medium to large.** Medium if it is a read-only contract over channels an
operator provisions. Large if the agent may mint its own, which is what a
per-technique correlator implies.

### G. An out-of-band channel that can answer - 3 techniques

**What it is.** A collaborator that returns a chosen response rather than only
recording an arrival: a redirect chain to a chosen `Location`, a TTL-0 DNS
answer, a chosen status code. It is what turns a blind SSRF into a graded one.

**What exists today.** **Absent.** `oob.py:56-60` and `callback.py:52-55` record
arrivals; nothing in either takes a response to serve. This is stated in `08`
and confirmed here by the absence of any response argument on those verbs.

**Techniques it unblocks.** 01 #7 (webhook SSRF, beating the allowlist);
03 #7 (a `jku` that has to resolve to something we control); 05 #5 (SSRF
response oracles: redirect loops and status escalation). Three. 01 #7 and 05 #5
are the same technique described twice - "webhook SSRF: making the blind case
visible" and "SSRF response oracles: redirect loops and status-code
escalation" - and are merged here.

**Risk it introduces.** A responder that follows the model's instructions is a
server we operate on the model's behalf, pointed at a third party. The limit is
that the response set must be closed and small.

**Size: medium.** Separable from F and should be a later ticket than F.

### H. In-run readback of one's own receipts and artifacts - 6 techniques

**What it is.** A step being able to read the receipt or artifact its own
earlier step in the same run produced, so a two-request differential can be
computed and decided inside one mission rather than across two.

**What exists today.** **Absent by design.** The child has no database and the
packet is frozen before the container starts - `roster.py:586-591` says
"`packet.compile` runs these on the supervisor's `rk2_state` connection before
the container starts". `packet.py:873-909` returns `{"reason": "not_staged", ...}`
for a receipt label the packet does not carry, and `packet.py:911-954` returns
`{"reason": "no_such_artifact"}` and notes "By label, never by hash", matching
`roster.py:638-657`. So a receipt minted at step 3 is unreadable at step 4 of
the same run.

**Techniques it unblocks.** 03 #11 (code single-use, which is by definition two
uses of one code), #16 (revocation propagation); 04 #5 (blind and second-order
IDOR verified through the owner's view), #10, #17 (the audit view as an
oracle - write, then read the log); 08 #8 (persistence: poison memory, then
observe it in a later turn). Six.

**What it would touch.** `packet.py:873-954`, and the question of whether the
child gets a live read path at all - which is an architectural decision, not a
handler change.

**Risk it introduces.** A live read path is a second channel into `rk2_state`
from inside the container. It reopens a boundary the design closed deliberately.

**Size: medium**, and it is the one item here that may be answered "no" on
principle, with the two-run pattern kept instead.

### K. Time, concurrency and connection identity on the receipt - 8 techniques

**What it is.** Enough of a request's timing and connection facts on the agent
side to grade a coarse timing differential, plus a stated answer on whether two
requests can be issued concurrently.

**What exists today.** **Partial.** `waited_ms` is on the receipt
(`0005_artifacts_and_provenance.sql:39-65`) and is projected to the agent
(`20260813T090000Z...:1449-1475`). `ts_arrival` is projected; **`ts_egress` is
not**. There is no connection identity on the receipt at all - searched for, not
found. `timing_differential` exists as an evidential observation kind
(`0018_vocabularies.sql:216-249`) with provenance `{receipt}`, so the kind is
fillable from `waited_ms` today. No concurrency control was found on any
contract; `roster.py:738-767` describes one request per call and says nothing
about issuing two at once.

**Techniques it unblocks.** 01 #20; 02 #5, #11, #13; 04 #6, #12, #18; 08 #10.
Eight. Note that 01 #20 and 02 #13 both say most of this is out of reach and
should be scoped to the coarse end.

**What it would touch.** The receipt projection at
`20260813T090000Z...:1449-1475`, and a documented answer on concurrency.

**Risk it introduces.** Concurrency is a rate-limit question. Anything that
issues N requests at once has to be counted by the egress budget at the door
(`20260811T170000Z__egress_budget_at_the_door.sql:146`) before it is offered.

**Size: medium**, mostly because the race half is a genuine design question and
the projection half is a column.

### L. A vocabulary migration - 8 techniques

**What it is.** New property-class leaves, and at least one new surface fact,
for readings the 57 shipped classes cannot express.

**What exists today.** **Partial.** Much of what earlier notes assumed was
missing is present: `injection.object_graph`, `injection.query_operator`,
`injection.parameter_precedence`, `information_disclosure.cached_response`,
`information_disclosure.undeclared_field`, `session_handling.cross_origin_read`,
`authorization.edge_rule`, `authorization.channel_subscription` and
`authorization.parallel_route` all exist in the post-`0018` migrations. What is
genuinely absent: a cookie-parser-differential leaf (02 #4 - `session_handling.cookie_scope`
is the nearest and is about scope, not parsing); a takeability leaf for a
dangling resource (07 #1); a general parser-differential leaf (05 #8). And
`authentication.recovery_flow` exists at `0018_vocabularies.sql:83-170` and is
emitted by no playbook's `bb:outputs` - confirmed in `00` section C.

**Techniques it unblocks.** 02 #4; 03 #1, #10, #15; 05 #8; 07 #1, #5, #11.
Eight.

**Risk it introduces.** None to the runtime. The catalogue is loaded by
migration with foreign keys, so an unknown class fails at INSERT rather than
degrading - which is the safe direction.

**Size: small.** One migration. It must land after the capability work, because
a class with no emitter is what `authentication.recovery_flow` already is.

### J. A few more offline tools - 7 techniques

**What it is.** Three additions to the closed binary enum at `roster.py:784`:
a config-file selector for INI / YAML / dotenv (01 #19), a protobuf
encoder-decoder (01 #11, 01 #10), and a set-versus-set comparison mode.

**What exists today.** **Absent; the enum is closed.** `roster.py:784` is
`enum=("jq", "js_map", "js_parse", "js_routes")`. `compare.py` in the
`compare-responses` Skill does pairwise line diff only; `08` notes there is no
set-versus-set mode, and none was found.

**Techniques it unblocks.** 01 #10, #11, #19; 03 #19; 07 #6, #13, #14. Seven.
01 #19 and 03 #19 are the same ask under two names - "artefact exposure classes
our candidate list does not name" and "secret exposure beyond the served SPA
bundle" - and are merged here.

**Risk it introduces.** Each tool is another parser running over attacker-
influenced bytes inside our container. Small, but not zero.

**Size: small**, per tool, and they are independent of each other.

### I. Two identities that differ by more than a label - 3 techniques

**What it is.** Being able to say that identity A and identity B sit in
different tenants or at different privilege, and having a step act as each.

**What exists today.** **Mostly present.** `identities.tenant_entity_id` and
`identities.class` exist at `0003_entities.sql:101-113`; `member_of` exists at
`20260813T090000Z...:218`; `tenant_boundary`, `multiple_test_identities` and
`privileged_identity_available` exist at `0032_playbooks.sql:78-81`;
`authorization.tenant_isolation` exists at `0018_vocabularies.sql:83-170`. The
gap is entirely capability C - a step cannot name which of them it is.

**Techniques it unblocks.** 03 #2, #9; 04 #1. Three, and all three are also
blocked on C.

**Size: small.** Fold into C.

## The matrix

One row per technique proposed across all eight research files: 20 + 15 + 20 +
18 + 18 + 16 + 14 + 10 = **131**. Capability codes are the letters above; `-`
means nothing new is needed. "Present today" is about the *harness*, not about
whether a playbook currently says it.

| Technique | File | Capability needed | Present today | Vocabulary needed |
| --- | --- | --- | --- | --- |
| 1. Framework internal-trust headers (`x-middleware-subrequest`, `x-now-route-matches`) | 01 | B | partial (headers send; none read back) | none - `authorization.edge_rule` |
| 2. Double-decoding across a proxy hop (403 bypass) | 01 | - | yes | none - `injection.path` |
| 3. Grounded route inventory from the bundle, then unauthenticated replay | 01 | - | yes | none - `endpoint_discovered` |
| 4. GraphQL batching and aliasing as a rate-limit primitive | 01 | A | no | none - `rate_limiting.per_identity` |
| 5. GraphQL schema recovery without introspection | 01 | A | no | none - `information_disclosure.undeclared_field` |
| 6. GraphQL-over-WebSocket subscription auth bypass | 01 | D, E | no | none - `authorization.channel_subscription` |
| 7. Webhook SSRF: blind case made visible, allowlist beaten | 01 | A, F, G | no | none - `injection.request_forgery` |
| 8. Platform batch and alternate-spelling routes (`/wp-json/batch/v1`) | 01 | A | partial (`?rest_route=` is a GET) | none |
| 9. Headless CMS as the CMS surface (Strapi, Directus) | 01 | A | partial | none - `tech_cms` |
| 10. gRPC reflection, transcoded-vs-binary authorization differential | 01 | A, J | no | none - `tech_grpc` |
| 11. Protobuf without a schema: field-number confusion, unknown-field passthrough | 01 | A, J | no | none - `information_disclosure.undeclared_field` |
| 12. Webhook signature schemes: empty secrets, unsigned metadata, replay windows | 01 | A, F | no | none - `business_logic.replay` |
| 13. Outbound-webhook CRLF into custom header names | 01 | A | no; sending CRLF ourselves is refused by `roster.py:738-767` header patterns | none |
| 14. RSC / hydration payload as a second copy of server state | 01 | - | yes | none - `information_disclosure.excess_field` |
| 15. Cache deception by delimiter and normalisation discrepancy | 01 | B | no | none - `information_disclosure.cached_response` |
| 16. Shadow and zombie API versions, `.well-known` as a seed | 01 | - | yes | none - `endpoint_discovered` |
| 17. Cross-Site WebSocket Hijacking preconditions | 01 | B, D, E | no | none - `session_handling.cross_origin_read` |
| 18. Realtime transports below the SDK: raw Engine.IO, pub/sub signing oracles | 01 | A | no | none |
| 19. Artefact exposure classes our candidate list does not name | 01 | J | partial | none - `information_disclosure.artifact_exposure` |
| 20. Timing as a discovery oracle | 01 | K | partial (`waited_ms` projected) | none - `timing_differential` |
| 1. Web cache deception through path confusion | 02 | B | no | none - `information_disclosure.cached_response` |
| 2. Cache poisoning of an unkeyed input, on a key this run owns | 02 | B | no | none - `information_disclosure.cached_response` |
| 3. Framework-internal header cache poisoning (the Next.js class) | 02 | B | no | none - `authorization.edge_rule` (merged with 01 #1, 04 #14) |
| 4. Cookie parser differentials: `$Version`, cookie sandwich, prefix bypass | 02 | B, L | no | **new**: a cookie-parser-differential leaf under `session_handling` |
| 5. Hidden caches - the ones that publish no header | 02 | B, K | no | none - `information_disclosure.cached_response` |
| 6. Ambiguity inside the structured body, not between carriers | 02 | A | no | none - `injection.parameter_precedence` |
| 7. Encoding and Unicode normalization differentials in the path | 02 | - | yes | none (merged with 05 #9) |
| 8. Cookie tossing and cookie injection from a sibling origin | 02 | B, D, E | no; the second-origin half is refused (see below) | none - `session_handling.cookie_scope` (merged with 01 #17, 06 #9) |
| 9. Cacheable error responses (CPDoS), and which layer answered | 02 | B | no | none - `information_disclosure.cached_response` |
| 10. CORS arms we do not send: `null`, scheme downgrade, preflight-free writes | 02 | B | partial (`OPTIONS` is in the method enum) | none - `session_handling.cross_origin_read` |
| 11. Desync *exposure surface* reading, without any framing | 02 | B, K | no | none - `transport.header_policy` |
| 12. The error message as an oracle, not only as a disclosure | 02 | - | yes | none - `information_disclosure.error_detail` |
| 13. Timing as an observable, at the coarse end only | 02 | K | partial | none - `timing_differential` |
| 14. Response-size and header-limit side channels | 02 | B | partial (`byte_size` at `_launch.py:726-735`) | none |
| 15. Raw-framing techniques listed for completeness | 02 | none - refused | no, and unmakeable by design | none |
| 1. Password reset and email-change flow attacks | 03 | A, F, L | no | `authentication.recovery_flow` exists with **no emitter** |
| 2. Mutable-claim identity binding (the nOAuth class) | 03 | A, C, I | no | none - `authentication.federation_trust` |
| 3. `redirect_uri` validation flaws and code/token exfiltration | 03 | B, F | no | none - `authentication.federation_trust` |
| 4. Non-happy-path token retention, third-party gadget leakage | 03 | D, E | no | none - `information_disclosure.credential_material` |
| 5. Scope upgrade and client confusion at token and userinfo | 03 | A | no | none - `authorization.token_scope` |
| 6. SAML parser differentials, attribute pollution, void canonicalization | 03 | A | no | none - `injection.document_parser`, `tech_saml` |
| 7. JWT key-sourcing forgery: `jku`, `x5u`, embedded `jwk`, `kid` injection | 03 | A, F, G | no | none - `authentication.federation_trust`, `tech_jwt` |
| 8. OTP and MFA enforcement beyond an assertion-shaped factor | 03 | A | no | none - `authentication.factor_enforcement` |
| 9. Cross-IdP impersonation and unverified second SSO method | 03 | A, C, I | no | none - `authentication.federation_trust` |
| 10. SCIM and just-in-time provisioning abuse | 03 | A, L | no | **new**: a SCIM / provisioning surface fact |
| 11. PKCE enforcement, code single-use, authorization code injection | 03 | A, H | no | none - `authentication.credential_verification` |
| 12. OIDC dynamic client registration and request-by-reference SSRF | 03 | A, F | no | none - `injection.request_forgery` |
| 13. Device code grant and cross-device flows | 03 | A, D | no | none - `authentication.federation_trust` |
| 14. WebAuthn relying-party ceremony validation | 03 | A, D, E | no | none - `tech_webauthn` |
| 15. CI-to-cloud OIDC federation trust policies | 03 | L | no; largely out of scope | **new**: a pipeline / workload subject (merged with 07 #11) |
| 16. Refresh tokens, revocation propagation, sender-constrained tokens | 03 | A, H | no | none - `session_handling.lifetime` |
| 17. Legacy or parallel identity API divergence | 03 | A | partial | none - `endpoint_discovered` |
| 18. Long-input truncation and cache-key collisions in credential handling | 03 | A, B | no | none - `authentication.credential_verification` |
| 19. Secret exposure beyond the served SPA bundle | 03 | J | partial | none - `information_disclosure.credential_material` (merged with 07 #2, #6) |
| 20. Agent and MCP OAuth proxies | 03 | A | no | none - `authorization.token_scope` |
| 1. Cross-tenant BOLA with a second tenant rather than a second user | 04 | C, I | partial - the model exists, the step cannot name it | none - `tenant_boundary`, `authorization.tenant_isolation` |
| 2. Mass assignment / BOPLA on the write side | 04 | A | no | none - `injection.object_graph` |
| 3. Broken function-level authorization: verb swap, admin siblings | 04 | C | partial (methods exist) | none - `authorization.function_access` |
| 4. Carrier and shape variation of the object identifier after a refusal | 04 | A, C | partial (query and header carriers only) | none - `authorization.object_ownership` |
| 5. Blind and second-order IDOR, verified through the owner's view | 04 | C, H | no | none - `authorization.object_ownership` |
| 6. Multi-endpoint races, and the payment TOCTOU | 04 | K | no - no concurrency control found | none - `business_logic.workflow_order` |
| 7. GraphQL alias and array batching as a network-free limit overrun | 04 | A | no | none - `rate_limiting.resource_cost` (merged with 01 #4) |
| 8. ORM operator injection and relation traversal, as a bounded oracle | 04 | - | yes over the query string | none - `injection.query_operator` (merged with 05 #2) |
| 9. Payment provider webhook forgery and replay | 04 | A, F | no | none - `business_logic.replay` |
| 10. Coupon, discount and credit logic beyond a single number | 04 | A, H | no | none - `business_logic.quantity_or_price` |
| 11. Currency, rounding and unit confusion | 04 | A | no | none - `business_logic.quantity_or_price` |
| 12. Single-endpoint races with differing values, partial construction | 04 | K | no | none - `business_logic.workflow_order` |
| 13. GraphQL relation traversal, global-node access, mutation-side gaps | 04 | A | no | none - `authorization.object_ownership` |
| 14. Framework and edge authorization bypass via internal headers and URL spelling | 04 | - | yes | none - `authorization.edge_rule` (merged with 01 #1, 02 #3) |
| 15. Predictable identifiers as the enabling step | 04 | - | yes | none - `information_disclosure.identifier_oracle` |
| 16. Unrestricted access to sensitive business flows, at bounded scale | 04 | A, C | no | none - `rate_limiting.resource_cost` |
| 17. The audit view as a discovery oracle, the unlogged action as a finding | 04 | C, H | no | none - `information_disclosure.log_record` |
| 18. Race hygiene: warming, session locks, retry distribution | 04 | K | no | none - `timing_differential` |
| 1. Error-based and boolean-error-based SSTI / code injection | 05 | A | partial (query string only) | none - `injection.template`, `tech_template` |
| 2. ORM leak: relational filter traversal and operator injection over query strings | 05 | - | yes | none - `injection.query_operator`, `tech_orm` (merged with 04 #8) |
| 3. Argument injection without shell metacharacters | 05 | A | partial | none - `injection.command` |
| 4. XXE, which we currently refuse outright | 05 | A + a policy reversal | no; refused in `playbooks/structured-injection/playbook.md:142-144` | none - `injection.document_parser`, `xml_request` |
| 5. SSRF response oracles: redirect loops and status-code escalation | 05 | G | no | none - `injection.request_forgery` (merged with 01 #7) |
| 6. Deserialization severity by runtime (Marshal, pickle, unserialize) | 05 | A | no | none - `injection.object_graph`, `serialized_object_parameter` |
| 7. Filename and handler confusion on upload and retrieval | 05 | A (multipart) | no | none - `injection.stored_file`, `multipart_request` |
| 8. Parser differentials as a first-class class | 05 | A, L | partial | **new**: a general parser-differential leaf |
| 9. Unicode normalization and best-fit as a shared filter-bypass layer | 05 | A for the body half | partial (path and query yes) | none (merged with 02 #7) |
| 10. Server-side prototype pollution, detected from response shape | 05 | A | no | none - `injection.object_graph` |
| 11. XSLT injection | 05 | A | no | none - `injection.document_parser` |
| 12. Archive extraction: Zip Slip, symlink entries, TOCTOU | 05 | A (multipart) | no | none - `injection.stored_file` |
| 13. Error/oracle-based SQL injection without sleeping or extraction | 05 | - | yes | none - `injection.query_language`, `tech_sql` |
| 14. The single-packet timing attack | 05 | none - refused | no; needs framing control we do not have | none |
| 15. SOAP / WSDL-driven client proxies (.NET) | 05 | A, F | no | none - `tech_soap`, `injection.request_forgery` |
| 16. PHP filter-chain sinks, error oracle as a no-collaborator channel | 05 | A | partial | none - `injection.path` |
| 17. CRLF injection into headers, and its desync consequence | 05 | partial - observation only | no; `roster.py:738-767` header value pattern excludes CR and LF | none - `transport.header_policy` |
| 18. Template-engine sandboxes are not a mitigation | 05 | - | n/a - a grading rule, not a step | none |
| 1. postMessage and cross-document messaging | 06 | D, E (`send_message`) | no | none - `injection.client_channel` |
| 2. CSPT with a write sink (CSPT2CSRF), stored and DOM-based sources | 06 | A, D, E | no | none - `injection.client_path` |
| 3. DOM clobbering | 06 | D, E | no | none - `injection.object_graph` |
| 4. CSP as a graded artefact, and CSP bypass by allowlist, gadget, nonce | 06 | B, D | no | none - `transport.header_policy` |
| 5. Prototype pollution: source detection, then gadget | 06 | D, E | no | none - `injection.object_graph` |
| 6. Sanitiser fingerprinting and mutation XSS | 06 | D, E | no | none - `injection.markup` |
| 7. Sink context taxonomy: URL-scheme and function-construction sinks | 06 | D, E | no | none - `injection.markup` |
| 8. CSS injection as a complete attack class | 06 | D, E, F | no | none - `injection.markup` |
| 9. Cookie tossing, cookie prefix bypass, cookie-forced self-XSS | 06 | B, D, E | no; second-origin half refused | none - `session_handling.cookie_scope` (merged with 01 #17, 02 #8) |
| 10. Clickjacking that survives the framing headers | 06 | B, D, E | no | none - `transport.header_policy`, `embedded_document` |
| 11. Service workers and the Cache API | 06 | D, E (`read_client_state`) | no | none - `information_disclosure.client_storage` |
| 12. Self-XSS escalation | 06 | D, E | no; second-origin half refused | none - `injection.markup` |
| 13. WebSocket beyond the handshake | 06 | D, E | no | none - `injection.client_channel`, `websocket_surface` (merged with 01 #6) |
| 14. XS-Leaks / cross-site side channels | 06 | D, E | no; second-origin half refused | none - `session_handling.cross_origin_read` |
| 15. Third-party widget and browser-extension permission surface | 06 | D, E | no | none - `injection.foreign_resource` |
| 16. Holding a redirect open to steal an OAuth code | 06 | D, E | no | none - `authentication.federation_trust` |
| 1. Dangling DNS on an in-scope hostname, read to the provider fingerprint | 07 | B, L | partial (resolution yes, fingerprint needs the `Server` header) | **new**: a takeability leaf; claiming the resource is refused |
| 2. Live credential triage at scale, with proof-of-existence | 07 | none - out of scope | n/a - calls a vendor, not the target | none (merged with 03 #19) |
| 3. SSRF reaching a metadata or container-credential endpoint | 07 | A | no; credential *retrieval* is refused | none - `information_disclosure.workload_metadata` |
| 4. Workflow injection reachable from a fork (pwn requests) | 07 | unmapped | no - needs write access to a repository we do not own | none |
| 5. Abandoned storage the application itself still fetches from | 07 | L | yes for the read | **new**: a takeability leaf, shared with #1 |
| 6. Public workflow artifacts and CI logs that carry tokens | 07 | J | partial; host is usually out of scope | none - `information_disclosure.credential_material` (merged with 03 #19) |
| 7. Self-hosted runner exposure on a public repository | 07 | unmapped | no - the subject is a repository, not an application | none |
| 8. Presigned URL and SAS token over-scope | 07 | A for the write half | partial (the read half is a GET) | none - `authorization.token_scope` |
| 9. Public and writable object storage, S3-compatible included | 07 | A | partial; the write half is a state change on a third party | none - `information_disclosure.artifact_exposure` |
| 10. Kubernetes control surfaces on a scoped host | 07 | A | partial | none - `information_disclosure.workload_metadata`, `tech_orchestrator` |
| 11. CI-to-cloud OIDC trust conditions | 07 | L | no | **new**: a pipeline subject (merged with 03 #15) |
| 12. Registry namespace claimability: dependency confusion, repojacking | 07 | none for the read - claiming is refused | partial | **new**: the takeability leaf, for the read half only |
| 13. Container images the target publishes | 07 | J | no | none - `information_disclosure.dependency_manifest` |
| 14. Unpinned mutable references, and manifest confusion | 07 | J | partial | none - `information_disclosure.dependency_manifest`, `tech_build_manifest` |
| 1. Output-channel exfiltration: markdown images, links, active content | 08 | A, F | no | none - `injection.model_instruction`, `tech_llm` |
| 2. Second-order indirect injection: the channel nobody thought was a channel | 08 | A, F | no | none - `injection.model_instruction` |
| 3. Tool and function-calling abuse (excessive agency, confused deputy) | 08 | A, F | no | none - `injection.model_instruction` |
| 4. Retrieval scope and RAG store permissions | 08 | A, C | no | none - `authorization.object_ownership` |
| 5. MCP and tool-surface poisoning, agent-to-agent chains | 08 | A | no | none - `injection.model_instruction` |
| 6. Invisible and obfuscated payload encodings | 08 | A | no | none - `injection.model_instruction` |
| 7. Server-side fetch and file access through model-held tools | 08 | A, F | no | none - `injection.request_forgery` |
| 8. Persistence: memory and configuration poisoning | 08 | A, H | no | none - `state_change` |
| 9. System prompt, tool schema and configuration extraction | 08 | A | no | none - `information_disclosure.excess_field` |
| 10. Cost and quota abuse | 08 | A, K | no | none - `rate_limiting.resource_cost` |

Four rows are marked **unmapped** or out of scope rather than assigned a
capability: 07 #2, #4, #7 and #12's claiming half. The reason in each case is
that the subject is not an application the Program's scope covers - it is a
source repository, a CI runner, or a vendor's own API - and no harness change
makes it in scope.

## What is already reachable and simply unused

Steps that need only `method`, `url` and `headers` from `roster.py:738-767`, or
only the ten browser actions already registered at
`20260814T040000Z...:189-208`. Nothing below needs a ticket; they need a
playbook edit.

* **01 #2** double-decoding across a proxy hop. Two GETs with different path
  encodings; the differential is status and body, both returned.
* **01 #3** grounded route inventory from the client bundle. `js_routes` is
  already in the `run_tool` enum at `roster.py:784`, and the replay sweep is
  GETs.
* **01 #14** the RSC / hydration payload. A GET, an Artifact, and `jq`.
* **01 #16** shadow and zombie API versions, `.well-known` as a seed. GETs.
* **02 #7 / 05 #9** encoding and Unicode normalization differentials in the
  path and query. The `url` argument carries whatever spelling the step wants.
* **02 #12** the error message as an oracle. `information_disclosure.error_detail`
  and the evidential kind `error_detail` both already exist.
* **04 #8 / 05 #2** ORM operator injection over the query string. The whole
  technique is query-string shaped; `injection.query_operator` and `tech_orm`
  both exist.
* **04 #14** framework and edge authorization bypass via internal headers. The
  `headers` argument sends any name matching `^[A-Za-z][A-Za-z0-9-]{0,63}\Z`.
* **04 #15** predictable identifiers as the enabling step. GETs and a
  comparison.
* **05 #13** error/oracle-based SQL injection without sleeping. Query string.
* **07 #5** abandoned storage the application still fetches from, for the read
  half.
* The `OPTIONS` method is in the enum at `roster.py:738-767` and no playbook
  sends one, so the preflight half of **02 #10** is available today.

## What we should not build

Kept with the reason the research file gave, because a refusal without its
reason gets re-proposed.

* **All raw-framing and desync classes** - 02 #15 and 02's unreachable list;
  the CL.TE / TE.CL / H2 downgrade family. Structurally refused, not merely
  unproven: `0025_transport_claims.sql:222-234` records
  `transport.request_framing` and `transport.datagram_transport` as
  `unmakeable`, and `transport_claim_guard()` at
  `0025_transport_claims.sql:262-280` raises where such a claim is first
  written. The proxy re-frames every request, so no evidence this design can
  produce settles it.
* **The single-packet timing attack** - 05 #14, and the byte-level race note in
  04. It needs control of when the last byte of two requests leaves, which is
  the same framing control `0025` refuses. 01 #20 and 02 #13 already concede
  this and scope timing to the coarse end, which is what capability K covers.
* **Sending CRLF in our own header names or values** - the consequence half of
  05 #17 and 01 #13. `roster.py:738-767` constrains header names to
  `^[A-Za-z][A-Za-z0-9-]{0,63}\Z` and values to `^[\x20-\x7e]{0,1024}\Z`,
  which excludes CR and LF by construction. Observing that a *target* emits
  CRLF into an outbound header is still in scope; smuggling a request on a
  stranger's connection is not, because the blast radius lands on a third party
  who never consented.
* **Opossum and anything needing a machine-in-the-middle position** - it
  requires sitting between the target and a real client. Refused on principle,
  not on difficulty.
* **Registering or claiming any third-party resource** - 07 #12's claiming
  half, and the takeover half of 07 #1. Reading a dangling record to a
  provider fingerprint is a finding; taking the name is an action against a
  registrar on a hunch. 07's own safety list says so.
* **Credential validity checks at a vendor** - 07 #2. Proof-of-existence is the
  reading; authenticating to a third party with a credential we found is not
  ours to do.
* **Retrieving cloud metadata credentials** - the second half of 07 #3.
  Reaching the endpoint and reading the response shape is the finding;
  retrieving and holding the credential is not.
* **Hosting a second origin** - required by 01 #17, 02 #8, 06 #9, 06 #12 and
  06 #14. The browser lane navigates; it does not serve. `browser_actions`
  (`20260814T040000Z...:189-208`) has no action that hosts anything, and adding
  one would make us a web host on the model's instruction. These techniques go
  in with their cross-origin half described and their preconditions checked,
  not executed.
* **Model-authored JavaScript in the page** - not asked for by any research
  file, but worth restating here because capability E will be tempted by it.
  `20260814T040000Z...:275-290` gives the reason: an expression the model wrote
  "could read `document.cookie`, it could fetch whatever it liked from the
  page's own origin, and it could return whatever verdict it wanted the run to
  record", making every other control decorative.
