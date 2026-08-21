# 12 - Out-of-band interaction as evidence

Every Observation this harness holds today is keyed to a request we made. The
Receipt is the door's record of our own exchange; the Tool run is our own
analysis of bytes we already had. Neither can carry the one claim a blind class
turns on: *the target reached out on its own, to a place we were watching*.

This file is about that gap: what the tree already builds, what it does not,
what the corpus is waiting on, how serious tools solve it, and what a phase-1
design for us looks like.

Framing throughout: an out-of-band channel is a host **we** run, contacted by a
target **we are authorised to test**, under a Program that declared the channel.
Nothing here is about reaching a host somebody else runs.

---

## What we have today

**Verdict: partial. The channel and the evidence record exist and are sound. The
agent-facing half does not exist at all, so today no playbook step can cite an
arrival without an operator standing in the middle.**

### Present: the record

* `callback_correlators` — `src/redkraken/migrations/20260812T040000Z__a_callback_arrives_on_a_declared_channel.sql:150`.
  Stores the **SHA-256** of the correlator, never the plaintext
  (`:156-157`, and the column comment at `:196-198`). Carries
  `subject_entity_id`, an optional `tool_run_id` **or** `test_run_id` (never
  both, `:185-186`), `issued_at`, `expires_at`, `cleared_at`, and a composite FK
  to `program_callback_channels (program_id, version, name)` at `:177-178` so a
  correlator names the channel declaration *as it existed when minted*.
* `callback_interactions` — same file, `:208`. One inbound arrival:
  `arrival_kind` constrained to `('dns','http')` (`:217`), `observed_host` as
  received and lower-cased (`:218`), `peer_class` in
  `('unknown','resolver','client')` (`:219-220`), `received_at`, and
  `body_sha256` pointing into the content-addressed store (`:222`). Immutable
  (`:243-247`). Off the agent read surface by design — the table comment says so
  at `:235`.
* Arrival identity / replay safety —
  `src/redkraken/migrations/20260910T000000Z__an_arrival_resolves_to_one_interaction.sql:56-62`:
  `UNIQUE (program_id, correlator_id, arrival_kind, observed_host, body_sha256,
  received_at)`. Handing the same recording over twice is one interaction.
* A **third provenance kind**. `observations.callback_interaction_id` at
  `20260812T040000Z…:297-301`; `provenance_kind IN ('receipt','tool_run','callback')`
  with an exactly-one-record CHECK at `:319-334`.
* **The observation kind exists.** `callback_interaction`, evidential, backed by
  `{callback}` alone, inserted at `20260812T040000Z…:348-350`.
  *The vocabulary does not need a new kind.* The "REJECTED" note in
  `src/redkraken/migrations/0018_vocabularies.sql:251-267` — which says an
  out-of-band kind cannot exist because its `allowed_provenance` would be empty
  — is **stale**. It was written before the third provenance record existed and
  is superseded by `20260812T040000Z…:336-350`, which widens
  `observation_kinds_allowed_provenance_closed` to admit `'callback'`. The 0018
  comment still ships the outdated sentence and reads as a live refusal; it is
  the single most misleading line in the schema on this subject.
* The writer — `record_callback_interaction`, `20260812T040000Z…:659-773`. One
  transaction: resolve the correlator, register the bytes, insert the arrival,
  promote it to an immutable Observation of kind `callback_interaction`. It
  re-asks attribution itself at `:711-716` (`callback_correlator_label(host,
  channel_host)` must equal the claimed correlator), and an `ENABLE ALWAYS`
  trigger re-asks beneath it (`enforce_callback_attribution`, `:456`;
  `enforce_callback_observation_program`, `:536-557`).
* Program isolation — `resolve_callback_correlator`
  (`20260912T000000Z__an_out_of_band_host_is_bound_not_declared.sql:310`) puts
  `rk2_program()` in the predicate, so a session bound to one Program cannot
  resolve another's correlator however it was obtained.
* Event surface — `callback.observed` (`20260812T040000Z…:253-255`), with
  `observed_host` **redacted** from the event log (`:262-265`) because the name
  carries the correlator.

### Present: the HTTP channel we run end to end

* `src/redkraken/oob.py:604` `serve` — publishes one directory over loopback
  only (`LISTEN_HOST = "127.0.0.1"`, `:287`; the comment at `:284-286` says a
  bindable address is a knob somebody sets to `0.0.0.0`). Directory contents are
  read and checked **once at startup** (`publishable`, `:163`; `Published`,
  `:144-160`), so there is no path to resolve and traversal has nowhere to go
  (`_requested`, `:568-589`).
* Every request is evidence, not just the ones that hit a file. `_answer`
  (`:432`) records the arrival after answering, and records a 404 for a
  published-name miss too (`:478-480`). Methods the host does not serve are
  recorded *then* refused with 405 (`_arrived_by_another_method`, `:387-416`) —
  a forged POST is still an arrival.
* What it files: `arrival_kind: "http"`, `peer_class: "client"`, `path` = the
  request target, `host` with the port stripped (`:521-536`), plus the exact
  request bytes as a transcript (`proxy.transcript`, `:537`), through the same
  writer `rk callback accept` uses (`callback.record`, `src/redkraken/callback.py:415`).
* The name in front of it — `up`/`status`/`down` (`oob.py:716`, `:844`, `:896`).
  A Cloudflare quick tunnel (`TUNNEL_BINARY = "cloudflared"`, `:112`;
  `QUICK_PROVIDER = "cloudflare-quick"`, `:131`), whose hostname is scraped out
  of the tunnel's own log (`QUICK_TUNNEL`, `:108`) and stored as the binding's
  evidence bytes (`:797-802`). The name lives in `callback_channel_bindings`
  (`20260912T000000Z…:105`) and nowhere else; `status` is the only supported way
  to read it (`oob.py:844-855`).
* Lifecycle is by construction, not by cleanup: a released binding makes every
  correlator minted against it resolve to nothing (`down`, `:896-907`), and
  `_reap` (`:1036`) releases bindings whose tunnel pid is gone before `up` binds
  anything.
* Anti-cross-talk: `_serves` (`oob.py:482-511`) refuses a correlator that is
  live on **another** channel of the same Program and counts it separately
  (`misdirected`, `:327-332`), because the publisher holds the Program's files,
  not that channel's.

### Present: the operator verbs

* `rk callback provision` (`callback.py:92`) — mints one correlator for one
  subject on one declared channel, 128 bits of hex (`CORRELATOR_BYTES = 16`,
  `:59`), default lifetime one hour (`:65`), ceiling 30 days (`:70`). Prints the
  address once: `https://<endpoint>/<correlator>/` for a `path` channel or
  `<correlator>.<endpoint>` for a `label` channel (`_address`, `:220-231`).
* `rk callback accept` (`callback.py:234`) — admits an arrival some **other**
  listener recorded. Reads the correlator from the label or the first path
  segment per the channel's placement (`_correlator`, `:656-728`), refuses a
  timestamp with no UTC offset (`_moment`, `:599-635`), and refuses empty or
  over-size bodies (`_arrival`, `:731-766`).
* `rk callback clear` (`callback.py:453`) — ends a canary early by the id
  `provision` printed, and reports how many arrivals it already caught.
* Channel vocabulary — `src/redkraken/config.py:87` `CALLBACK_KINDS = ("dns",
  "http")`, `:93` `CALLBACK_PLACEMENTS = ("label", "path")`, `:94`
  `CALLBACK_PROVIDERS = ("cloudflare-quick", "static")`. Validated in
  `src/redkraken/scope.py:683-745`; a non-HTTP kind must be `label` +
  `static` (`scope.py:733-742`).

### Absent

* **A DNS listener.** The schema admits `arrival_kind = 'dns'` and the config
  admits `kind = dns`, but nothing in the tree listens on 53 — *not found*
  anywhere under `src/redkraken/`. A DNS arrival can only enter through
  `rk callback accept` from a listener an operator ran themselves
  (`callback.py:234`).
* **SMTP, LDAP, FTP, SMB.** `CALLBACK_KINDS` is two words (`config.py:87`) and
  `callback_interactions.arrival_kind` is a two-value CHECK
  (`20260812T040000Z…:217`).
* **A channel that can answer under our control.** `oob.py` serves a fixed
  mapping read at startup (`:144-160`, `:462-476`) with `GET`/`HEAD` only
  (`:363-366`). No redirect, no per-request body, no TTL control. A DTD can be
  published; a redirect chain or a rebinding answer cannot be produced.
* **Any agent-facing verb.** `rk callback provision` is CLI-only
  (`src/redkraken/cli.py:571-631`). There is no `mcp__rk2__*` contract for it —
  `src/redkraken/roster.py:592-845` holds the closed contract set and none of
  the fifteen mentions a correlator or an interaction; the only occurrence of
  `callback` in that file is the label prefix `"callback_interactions": "CB"` at
  `roster.py:176`. Nothing in `src/redkraken/packet.py` or
  `src/redkraken/execution.py` hands a correlator address to a child — *not found*.
* **A positive control.** `_listening` (`oob.py:1080-1099`) proves *our own*
  publisher answers `/health` on loopback before a name is bound. Nothing proves
  the bound public name is reachable from the outside, and no proof-of-life
  arrival is ever recorded. Silence today is indistinguishable from a dead
  tunnel.

### Can an agent read a callback interaction through any Contract?

**Not found.** No Contract in `src/redkraken/roster.py:592-845` reads
`callback_interactions`. What an agent can reach is strictly downstream:

* `mcp__rk2__get_evidence` (`roster.py:613-628`) reads `v_evidence`,
  `hypothesis_evidence`, `finding_evidence`, `observations`. `v_evidence`'s
  registered columns are listed at
  `src/redkraken/migrations/20260812T063000Z__the_evidence_view_the_agent_reads.sql:71-81`:
  `provenance_kind`, `receipt_label`, `tool_run_label` — **and no
  callback-interaction label**. So an agent sees `provenance_kind = 'callback'`
  and a dead end where the other two provenance kinds have a label.
* The one bridge is the Observation's own `summary`, composed at
  `20260812T040000Z…:759-771`: it names the channel, the arrival kind, the byte
  count and the **artifact reference label**, and deliberately omits the host
  (`:756-758`, "The host carries the correlator"). From that label
  `mcp__rk2__get_artifact` (`roster.py:648-667`) can fetch the stored inbound
  bytes.
* And the evidence gate: `callback_interaction` is evidential
  (`20260812T040000Z…:348-350`), so `hypothesis_evidence` will accept it with
  `role != context` under `enforce_evidential_kind`
  (`0018_vocabularies.sql:448-470`).

**So: an arrival is citable in principle, and unreachable in practice.** The
Observation only exists if an operator already ran `provision`, handed the agent
an address out of band, and the payload fired. The agent cannot mint, cannot
list arrivals, and cannot name the interaction record.

---

## What the corpus is waiting on

### Playbooks

50 playbook directories under `src/redkraken/playbooks/`. 12 of them touch
out-of-band ground (`callback` / `out-of-band` / `collaborator` / `blind` /
`exfiltrat`): `browser-messaging`, `browser-script`, `cms`,
`command-directory-injection`, `jwt-jose`, `oauth`, `orm`, `race-conditions`,
`sql-injection`, `ssrf-url-routing`, `structured-injection`, `webhooks`.

Two name the evidence kind directly:

* `src/redkraken/playbooks/webhooks/playbook.md:13` — `bb:evidence` gates
  `supported` on `{"role": "variant", "kind": "callback_interaction",
  "min_count": 1}`. The whole playbook is built around the arrival: `:36` "Ask
  the runtime for a correlator for this subject", `:61` "An arrival is the
  finding." **This playbook cannot reach `supported` at all today**, and the
  grading migration says so on purpose:
  `src/redkraken/migrations/20260826T000000Z__seven_topics_arrive_as_playbooks_and_the_targets_that_grade_them.sql:319-324`
  — "this Playbook cannot reach `supported` against a fixture, because a
  loopback evaluator has no callback channel to register. The alternative was to
  accept a response differential as proof that a request was made, which is the
  shape of the classic invalid SSRF report."
* `src/redkraken/playbooks/jwt-jose/references/jwt.md:40-43` — `jku`/`x5u`
  pointed at a URL under our control "is a `callback_interaction` and belongs to
  a blind-validation reading rather than this one."

Three more state the gap as a refusal rather than a technique:

* `src/redkraken/playbooks/sql-injection/references/sqli-out-of-band-dns.md:1`
  is an entire note on why the channel stays shut, ending at `:63-72` with the
  two problems this design has to answer: "A callback that arrives late is
  uncorrelatable" and "callbacks arrive from Programs you are not testing …
  Attribution requires a token per request and discipline nobody maintains."
* `src/redkraken/playbooks/command-directory-injection/references/xxe.md:62-65` —
  the OOB DTD chain "is out because it requires standing up external
  infrastructure inside a reading".
* `src/redkraken/playbooks/command-directory-injection/references/os-command-injection.md:28-30` —
  a callback lookup ranks third "because it proves reachability rather than
  execution".

`src/redkraken/playbooks/ssrf-url-routing/playbook.md:34` already assumes "the
Program's configured callback host, and a second label under it" — a `label`
placement the publisher cannot serve (`oob.py:642-650` refuses any placement but
`path`).

### Techniques from `docs/research/playbook-state-of-the-art/`

Six of the nine files carry blocked work: `00`, `01`, `03`, `04`, `05`, `08`.
`02-http-parsing-cache.md` and `06-client-side-browser.md` do not (their
blockers are request framing and second-origin hosting), and `07`'s
dangling-record work needs outbound *resolution*, not an inbound listener.

Sixteen distinct techniques are blocked on this channel:

| # | Technique | Cited at |
|---|---|---|
| 1 | XXE with an external `SYSTEM` entity | `05-injection-server-side.md:186-189`, `:701-702` |
| 2 | XXE parameter-entity / OOB DTD chain | `05:701-702` |
| 3 | Blind SSRF with no returned body | `05:703-704`, `01-recon-api-protocol.md:306-307` |
| 4 | SSRF redirect-loop status-cycling oracle — needs a channel that **answers** | `01:327-329`, `05:198-199` |
| 5 | DNS-rebinding TOCTOU — needs a TTL-0 authoritative record | `01:329-330`, `05:706` |
| 6 | SOAP/WSDL client-proxy construction | `05:490-492`, `05:705` |
| 7 | SMTP header injection to an unreadable mailbox | `05:709` |
| 8 | Remote-staged deserialization gadget chains (also refused on scope) | `05:707-708` |
| 9 | Blind SQLi out-of-band exfiltration (also refused on policy) | `05:423` |
| 10 | JWT `jku`/`x5u`/`jwk`/`kid` key-source forgery | `03-authentication-identity.md:193-199`, `:446-449` |
| 11 | OIDC dynamic client registration SSRF (`request_uri`, `logo_uri`, `jwks_uri`, `sector_identifier_uri`) | `03:288-290` |
| 12 | Host-header password-reset poisoning | `03:80-81`, `03:546-548`, `03:566-568` |
| 13 | Webhook arrival window + the silence rule | `01:306-307`, `01:892-895`, `00-todo-and-harness-gaps.md:111-113` |
| 14 | Reset / invite / referral flows needing a program-controlled mailbox | `04-authorization-business-logic.md:668-670`, `:738-739` |
| 15 | AI output-channel exfiltration via rendered markdown image/link | `08-ai-targets-and-methodology.md:70-76` |
| 16 | AI model-tool SSRF and server-side fetch | `08:237-239` |

The corpus already names the shape of the answer:

* `00-todo-and-harness-gaps.md:111-113` — "`src/redkraken/oob.py` exists; what
  the research asks for is evidence keyed to an interaction we did not initiate,
  **with a positive control so that silence means something**."
* `08:394-397` — "Not one of our six Skills has any concept of an interaction we
  did not initiate." (Six: `analyse-source`, `browser-evidence`,
  `compare-responses`, `enumerate-surface`, `handle-untrusted-content`,
  `use-identity`, under `src/redkraken/skills/`.)
* `08:473-491` proposes a seventh Skill, `observe-out-of-band`, with the rule
  this design must implement: "**absence of a callback is evidence only if the
  channel was proven live by a positive control in the same run.**"
* `01:902-903` names the capability precisely: "a callback channel that can
  answer as well as record."

One inconsistency worth flagging: `05:699-709` lists six bullets under "Needs an
out-of-band interaction channel", while `05:746-748` concludes "only two
genuinely require the callback channel". The prose undercounts its own list.

---

## How other systems do it

### Burp Collaborator (PortSwigger)

**Design.** "The Burp Collaborator server runs on the public web (by default). It
uses its own dedicated domain name, and the server is registered as the
authoritative DNS server for this domain." It answers any DNS lookup and serves
HTTP/HTTPS behind a CA-signed wildcard certificate. A private deployment needs
three records: an A/AAAA for the Collaborator subdomain, an **NS record for the
subdomain pointing at the Collaborator name server**, and an A/AAAA for that
name server. Default listeners: DNS UDP/53, HTTP 80, HTTPS 443, SMTP 25 and 587,
SMTPS 465.

**Correlation.** Two layers, and they are separable:

1. *Payload → interaction.* "Every Collaborator payload that Burp sends to the
   target includes a unique, one-time random identifier, so when a deferred
   interaction occurs, Burp can use the identifier to pinpoint exactly where the
   payload originated, including the original request, the insertion point and
   the full payload." The identifier rides "in the subdomain of a DNS lookup, or
   the Host header of an HTTP request."
2. *Interaction → tenant.* "Each Collaborator payload includes a random
   identifier that is derived from a one-way hash (cryptographic checksum) of the
   secret." The secret never leaves Burp except to poll. "When the Collaborator
   server receives a polling request, it performs the one-way hash of the
   submitted secret. It then retrieves the details of any interactions with
   identifiers that are derived from that hash." A tenant can therefore only
   read interactions on subdomains it could itself have generated.

**Retention.** "Details of interactions are typically retrieved shortly after
they occur. They are then discarded by the server. Details of old interactions
that haven't been retrieved are discarded after a fixed interval." The 2022
elastic redesign (Matt Atkinson, 21 January 2022) puts numbers on it: "Once your
data has been returned, it is immediately deleted from the database", and
"should an instance of Burp Suite not request stored interaction data within 14
days of creation, then that data will be deleted from the database as stale."
Interaction data is encrypted at rest under a user secret combined with a
service master secret.

**Positive control, as a shipped feature.** Burp has a "Run health check"
button: "Burp verifies whether it is possible to interact with the server using
various network services, and whether it can retrieve the details of these
interactions via polling. Based on these tests, you can determine whether Burp
is likely to be able to make use of the Collaborator's features." That is
exactly the proof-of-life this design needs, run against the operator's own
infrastructure.

**Why the public domain rotates.** The default domain moved from
`burpcollaborator.net` to `oastify.com` because the older name was widely
blocked; PortSwigger periodically adds new names to reduce WAF blacklisting,
"which results in false negatives."

### interactsh (ProjectDiscovery)

**Design.** A client/server pair. The server runs protocol listeners on DNS
(TCP/UDP 53), HTTP (80), HTTPS (443), SMTP (25), SMTPS (587, 465) and LDAP
(389), with FTP/FTPS (21, 990), SMB (445) and Responder services available only
on self-hosted instances. Self-hosting requires delegating a domain: create
`ns1`/`ns2` host records pointing at the server IP, then set the domain's
nameservers to them.

**Correlation.** The payload is a single string, 33 characters by default: a
20-character correlation-id preamble plus a 13-character nonce
(`-cidl` / `-cidn`, minimum 3 each; client and server must agree). The server
reads the subdomain (or the HTTP `Host` header) to recover the correlation id
and files the interaction against it. The nonce is what distinguishes two
payloads that share a correlation id — Nuclei's integration mixes
microsecond-precision timing into it so simultaneous requests still get distinct
ids.

**Confidentiality.** RSA for key transmission, AES for the interaction data:
clients register a public key, the server encrypts stored interactions to it and
returns them in a poll response containing an AES key envelope. Self-hosted
servers can require a token (`-a`/`-t`).

**Retention.** `-e, -eviction int` — "number of days to persist interaction data
in memory (default 30)", with `-ne` disabling periodic cleanup entirely.

### Common ground

* **Protocols.** DNS is the detection floor because outbound DNS is allowed far
  more often than outbound anything else; every serious tool answers it first.
  HTTP/HTTPS is what turns "resolved" into "fetched" and is what carries a DTD,
  a JWKS or a WSDL. SMTP matters for mail-flow classes. LDAP earns its place
  from JNDI/Log4Shell-class payloads. FTP/SMB are Windows-flavoured extras.
* **The polling asymmetry.** Both tools separate the host that *receives* from
  the client that *reads*, and both make reading require a secret the payload
  never carried. That is what stops a bystander who saw a subdomain from
  enumerating the engagement.

---

## The false-positive problem

An interaction arriving at a host we run is not, on its own, proof that our
payload caused it. Five distinct ways it can lie:

1. **Somebody else's scanner, on a shared domain.** GreyNoise's weekly OAST
   report for 17-23 January 2026 recorded "9,004 honeypot sessions from 313
   unique IP addresses conducting coordinated vulnerability scanning" and
   decoded 5,171 unique callback domains across six Interactsh providers
   (`oast.site` 42.3%, `oast.live` 16.6%, plus `oast.me`, `oast.pro`,
   `oast.fun`, `oast.online`). A shared OOB domain is a namespace thousands of
   unrelated actors are writing into. Our own corpus says the same from the
   receiving end: "callbacks arrive from Programs you are not testing … lookups
   from crawlers, from sandboxes, from a payload somebody else planted on a
   shared platform months ago"
   (`src/redkraken/playbooks/sql-injection/references/sqli-out-of-band-dns.md:67-72`).
2. **A resolver is not the target.** A DNS query reaches an authoritative server
   from a recursive resolver, which may be nowhere near the target and carries
   none of the target's identity. `callback.py:73-75` already encodes this
   honesty: `PEERS = ("unknown", "resolver", "client")`, with `unknown` as the
   default because "a DNS query arrives from a resolver that is not the target".
3. **DNS caching suppresses the second lookup.** Reusing one name across
   attempts means a resolver answers the second attempt from cache and the
   authoritative server never sees it — a false *negative* that reads as a
   refutation. The standing rule is one name per attempt: "Due to DNS records
   caching add unique value to URL for each request" (NotSoSecure OOB
   cheatsheet). Negative caching does the mirror-image damage: an NXDOMAIN for a
   name minted before the channel was live stays cached past the moment it
   became live.
4. **Something on the path resolves what it sees.** A WAF, a logging pipeline or
   a detonation sandbox that resolves hostnames found in request bodies produces
   the exact signal the technique reads as proof. Our own note calls this out:
   the callback "proves reachability, not execution"
   (`sqli-out-of-band-dns.md:22-28`; `os-command-injection.md:28-30`).
5. **DNS without HTTP.** PortSwigger: it is "common when testing for SSRF
   vulnerabilities to observe a DNS look-up for the supplied Collaborator
   domain, but no subsequent HTTP request", because the request was blocked by
   network-level filtering after the lookup. A DNS-only arrival and an HTTP
   arrival are different claims and must not collapse into one.

### What a correlation token must look like

For an arrival to be attributable **only** to our payload, the token has to
satisfy all of these:

* **Unguessable.** Enough entropy that an arrival at that name cannot be
  coincidence. Ours is 128 bits of hex (`callback.py:59`) — comfortably past
  interactsh's 33 characters and in the same class as Collaborator's
  hash-derived identifier.
* **Unique per attempt, never reused.** One name per request, so DNS caching
  cannot swallow the second lookup and two attempts can never be confused. Ours
  is minted per call and its plaintext is stored nowhere (`callback.py:104-110`,
  digest-only column at `20260812T040000Z…:156-157`).
* **Bound to a subject before the payload is sent.** Ours carries
  `subject_entity_id` and at most one of `tool_run_id` / `test_run_id`
  (`20260812T040000Z…:163-165`, `:185-186`), so the arrival lands on a named
  entity and a named run rather than "the engagement".
* **Time-boxed.** An arrival outside the window is not this reading's evidence.
  Ours defaults to one hour with a 30-day ceiling (`callback.py:65`, `:70`) and
  a live-only resolver (`resolve_callback_correlator`,
  `20260912T000000Z…:310`), so yesterday's canary answers nothing today.
* **On a namespace only this engagement uses.** A per-Program endpoint, not a
  shared public OOB domain — which is what `webhooks/playbook.md:38` already
  forbids ("A URL pointing anywhere else -- a public interaction service, a host
  you control personally -- is out of scope").
* **Checked on the way in, not assumed.** The observed name must be re-derived
  and compared to the claimed correlator rather than trusted. Ours does this
  twice: in the writer (`20260812T040000Z…:711-716`) and again in an
  `ENABLE ALWAYS` trigger (`:456`).
* **Recorded with what could not be attributed.** The publisher counts arrivals
  it refused (`refused`, `oob.py:325-326`), arrivals belonging to another
  channel (`misdirected`, `:327-332`) and writes the writer refused (`lost`,
  `:322-324`). Noise that is counted is noise an operator can reason about.

And the claim itself has to stay narrow. An arrival proves *a request left the
target's side carrying our token*. It does not prove execution, and it does not
prove impact — Shubham Shah's blind-SSRF chain glossary (Assetnote, 13 January
2021) is the standing argument that impact needs the chain, not the callback,
and PortSwigger says plainly that "simply identifying a blind SSRF vulnerability
that can trigger out-of-band HTTP requests doesn't in itself provide a route to
exploitability." `webhooks/playbook.md:88-91` already draws that line.

### What a triager accepts

From the published triage guidance surveyed: a report is accepted when it gives
reproduction steps, a unique identifier a triager can tie to the attempt, and a
statement of impact — not a bare screenshot of a callback. Programs also
constrain *where* the callback may go: "PoCs should use no third-party callbacks
beyond program-approved out-of-band servers." So the bar is: our own host, a
per-attempt token, the raw inbound record, the request that carried the token,
and an impact argument that does not rest on the arrival alone.

---

## The silence problem

Today, "no callback arrived" and "the tunnel died an hour ago" produce identical
records: nothing. `webhooks/playbook.md:61-62` is honest about this — "No
arrival inside the declared window is not a refutation on its own -- it is the
absence of one" — and that honesty is a permanent ceiling until a positive
control exists.

**A positive control must be an arrival we caused, on the same channel, inside
the same reading, recorded the same way.** Concretely:

* **Same channel, same binding.** Proving channel A is live says nothing about
  channel B, and proving it before `rk oob up` rebound the name says nothing at
  all.
* **Same window.** Fired at the start of the declared wait and, ideally, again
  at the end. A tunnel that died mid-reading is the failure mode this exists to
  catch, and only a bracketing pair catches it.
* **Same protocol as the payload.** A DNS proof-of-life does not establish that
  HTTP arrives. Given the DNS-without-HTTP asymmetry above, the control has to
  match the channel the payload used.
* **From outside.** `_listening` (`oob.py:1080-1099`) asks our own publisher on
  loopback with a `Host` the tunnel cannot forge — a real check, and a check of
  the wrong half. A control has to traverse the same public path the target's
  request would: resolve the bound name, reach the edge, come back through the
  tunnel.
* **Recorded, not asserted.** It has to produce a row an auditor can read, with
  its own correlator, marked as ours so it is never mistaken for the target's.
  Burp's health check is the shipped precedent for the idea; it is a UI verdict,
  not a citable artifact, and ours has to be the latter.
* **Distinguishable from a target arrival.** Same table, different flag. If the
  control shared a correlator with the reading, the control would satisfy the
  reading's own evidence gate.

With that in place, three outcomes become three different facts:

| Control | Target arrival | Verdict |
|---|---|---|
| arrived | arrived | the target reached us — `callback_interaction` |
| arrived | none | **the channel was live and nothing came** — a real negative, citable toward `refuted` alongside the response-invariant control |
| none | — | the channel was not live; the reading is `inconclusive` and says why |

Today only rows 1 and 3 can be told apart, and only by an operator looking at a
terminal.

---

## Proposed design for us

### Phase 1 — make what exists citable, and make silence mean something

Nothing here needs a new observation kind. `callback_interaction` exists
(`20260812T040000Z…:348-350`) and is backed by `{callback}` provenance. Five
pieces of work:

1. **A `provision` verb on the agent surface.** A new Contract in
   `src/redkraken/roster.py:592` — group `state.read` is wrong; this mints
   state, so it belongs with the request-shaped verbs. Arguments: the channel
   name and the subject entity label; it returns the address to embed and the
   correlator id, and it binds the correlator to the calling run
   (`mint_callback_correlator` already takes `tool_run_id` / `test_run_id`,
   `callback.py:82-84`). Without this, `webhooks/playbook.md:36` names a
   capability that does not exist.
2. **A callback-interaction label on the evidence view.** Add a
   `callback_label` column beside `receipt_label` and `tool_run_label` in
   `v_evidence` and register it in `state_read_surface`
   (pattern at `20260812T063000Z…:71-81`), so provenance `callback` has a name
   the way the other two do. The interaction table itself stays off the read
   surface — `observed_host` carries the correlator
   (`20260812T040000Z…:235`, `:262-265`) and must not become readable.
3. **The positive control, as a recorded arrival.** `rk oob probe --channel X`:
   mint a correlator flagged as a control, resolve the bound public name, fetch
   `https://<endpoint>/<correlator>/` from outside, and let the ordinary
   publisher path record it (`oob.py:432-480`). Schema: one boolean or an
   enum on `callback_correlators` (`purpose IN ('reading','control')`) and the
   arrival inherits it. Then:
   * a control correlator's Observation is **non-evidential for the target** and
     must be excluded from `hypothesis_evidence` gates, or given its own
     non-evidential kind;
   * `rk callback provision` refuses to mint against a channel with no control
     arrival inside a freshness window;
   * the reading cites the control alongside the negative, which is what turns
     `webhooks/playbook.md:61` from a caveat into a finding.
4. **Fix the stale vocabulary comment.** `0018_vocabularies.sql:251-267` reads
   as a live refusal of an out-of-band kind that has existed since
   `20260812T040000Z…`. A comment-only migration that supersedes it, so nobody
   re-litigates a decision that was already reversed.
5. **A `label` placement for the HTTP publisher, or an explicit refusal.**
   `oob.py:642-650` refuses any placement but `path`, while
   `ssrf-url-routing/playbook.md:34` assumes a label. One of the two has to
   move; a quick tunnel serves one hostname, so the honest phase-1 answer is
   probably to correct the playbook.

**How a step cites it, once phase 1 lands.** The chain is already sound; phase 1
only makes each link reachable by a tool call:

```
provision(channel, subject)      -> address + correlator id      [new Contract]
  embed the address in the payload; send it through http_request  [Receipt]
  wait the declared window
get_evidence(hypothesis_label=H) -> observation O, kind=callback_interaction,
                                    provenance_kind=callback,
                                    summary naming artifact AF-…
get_artifact(artifact_label=AF-…)-> the exact inbound request bytes
```

and the playbook's `bb:evidence` gate does the rest —
`webhooks/playbook.md:13` already requires exactly this shape.

### Later — the channels and capabilities we do not have

* **A DNS listener** (`arrival_kind = 'dns'` is already legal,
  `20260812T040000Z…:217`). This is the biggest single unlock: DNS is the
  detection floor for XXE, blind SSRF, Log4Shell-class JNDI and blind command
  injection, and outbound DNS survives egress filtering that stops HTTP. It also
  costs the most: a delegated domain, NS records, an authoritative server, a
  static IP — not a quick tunnel. The `static` provider already exists in the
  vocabulary (`config.py:94`) for exactly this.
* **A channel that answers.** Redirect chains (`01:327-329`), TTL-0 answers for
  rebinding (`01:329-330`, `05:706`). Both are a different publisher: today the
  mapping is fixed at startup by design (`oob.py:144-160`), and per-request
  answers reopen the isolation question that design closed.
* **SMTP and LDAP.** Would widen `CALLBACK_KINDS` (`config.py:87`) and the
  `arrival_kind` CHECK. SMTP unlocks the mailbox requirement at
  `04:668-670`; LDAP unlocks JNDI-class detection.
* **The `observe-out-of-band` Skill** proposed at `08:473-491`, once the verbs
  exist for it to teach.

---

## Scope and safety

An out-of-band channel inverts the harness's usual posture: it is a host **we**
run that a **target** contacts, on the public internet, under a name we hand out
in a payload. The existing module already takes most of the hard positions; they
should be treated as load-bearing.

**What must never be served from it.**

* Only an allowlist of engagement file types: `.dtd .html .js .json .svg .txt
  .xml .xsl` (`oob.py:71`), each with a declared content type (`:76-85`) rather
  than a sniffed one. Anything else in the directory is a **refusal to start**,
  not a 404 (`publishable`, `:163-255`) — "an operator who put something else in
  there is an operator who does not know what is published" (`:18-20`).
* No symlinks, no subdirectories, no dotfiles (`_unpublishable`, `:269-281`);
  never `$HOME`, never a directory holding a `.git`, never the directory holding
  the configuration (`_forbidden`, `:258-266`).
* **No directory listing** (`Request` docstring, `:334-341`) — an index would
  name the other canaries' files to a target.
* Never another channel's canary: `_serves` (`:482-511`) refuses a correlator
  live on a different channel, because answering it "would hand the engagement's
  payloads to whoever learned a name we never pointed here".
* Never bound to a public interface directly: loopback only (`:284-287`), with
  the tunnel as the sole path in.
* This is where the industry has been burned. ProjectDiscovery's own guidance on
  interactsh's dynamic-response feature is that it "lets anyone run client-side
  code / redirects using your interactsh domain / server" and that an isolated
  domain should be used. Our channel must never become an open redirector, an
  open HTML host or a place a third party's script can be served from. If a
  channel that answers is ever built, this is the constraint it has to satisfy
  first.
* And the domain must be isolated from anything else the engagement or the
  operator owns, for the same reason.

**What must be logged.**

* Every arrival, attributable or not — including 404s, unpublished names and
  methods the host refuses (`oob.py:387-416`, `:478-480`). The refusal is part
  of the record.
* The exact inbound bytes, content-addressed (`proxy.transcript`, `:537`;
  `Store.put` inside `callback.record`, `callback.py:439-450`), so a citation
  points at what arrived rather than at a summary of it.
* The counters an operator reads to know what the host saw: `answered`,
  `recorded`, `refused`, `misdirected`, `lost` (`oob.py:319-332`, reported at
  `:694-712`).
* Binding lifecycle with its evidence: the tunnel's own output bytes are stored
  and cited by the binding (`oob.py:797-802`), because "a binding whose endpoint
  nobody can check against anything is a claim about what happened rather than a
  record of it" (`:735-737`).
* And the event log deliberately **redacts** `observed_host`
  (`20260812T040000Z…:262-265`): the name carries the correlator, the event log
  is the widest-read surface in the installation, and the label, the channel and
  the digest are what an auditor actually needs.

**How a target's data reaching it is handled.**

A payload can carry target data into our host — that is what the exfiltration
variants of these techniques *do*, and it is why the corpus refuses them
(`sqli-out-of-band-dns.md:38-41`: "Concatenating a password hash into a hostname
is the blind loop with a worse evidence trail: it is data taken from the target
and written into the global DNS"). The position to hold:

* **Detection, not extraction.** A correlator is a token that proves an
  interaction happened. It is not a carrier for target data, and a payload that
  concatenates target values into a name is a different technique with different
  rules of engagement.
* Whatever does arrive is program-scoped from the first write: the arrival cites
  a correlator that names one Program (`resolve_callback_correlator`,
  `20260912T000000Z…:310`), the observation FK is composite on `program_id`
  (`20260812T040000Z…:297-301`), and a cross-Program citation is a key violation
  before it is a trigger message (`:536-557`).
* It is bounded: 1 MiB per arrival (`callback.py:79`), 64 KiB of request body at
  the publisher (`oob.py:361`).
* It is purgeable by the ordinary route: `callback_correlators` and
  `callback_interactions` are both registered purge-cascade edges on
  `program_id` (`20260812T040000Z…:249-251`).
* It is bounded in time: correlators expire (`callback.py:65`, `:70`) and can be
  ended early by verb (`clear`, `callback.py:453`; `clear_callback_correlator`,
  `20260911T000000Z__a_canary_ends_by_verb.sql:37`) — which is the control an
  operator reaches for when a payload went somewhere it should not have.
* A retention policy for arrival bytes is **not** currently expressed as a
  number. Both reference implementations have one (Collaborator: deleted on
  retrieval, stale after 14 days; interactsh: 30 days by default). Ours inherits
  the Program's purge story and nothing narrower. That is a gap worth closing
  when the channel carries more than HTTP.
* No peer address is stored. `oob.py:526-533` explains why: the only address
  this process can see is the tunnel's own end of a loopback socket, and the
  fetcher's address exists only in a `Cf-Connecting-Ip` header the tunnel wrote
  — kept verbatim in the transcript as evidence a reader can weigh, rather than
  promoted to a schema field that would read as a fact about the peer.

---

## Sources consulted

Web (fetched and quoted):

* Burp Collaborator data security — https://portswigger.net/burp/documentation/collaborator/server/security
* Introducing Burp Collaborator (PortSwigger blog) — https://portswigger.net/blog/introducing-burp-collaborator
* A modern, elastic design for Burp Collaborator server, Matt Atkinson, 21 January 2022 — https://portswigger.net/blog/a-modern-elastic-design-for-burp-collaborator-server
* Deploying a private Burp Collaborator server — https://portswigger.net/burp/documentation/collaborator/server/private
* Collaborator settings (health check) — https://portswigger.net/burp/documentation/desktop/settings/project/collaborator
* Blind SSRF vulnerabilities, Web Security Academy — https://portswigger.net/web-security/ssrf/blind
* projectdiscovery/interactsh — https://github.com/projectdiscovery/interactsh
* Interactsh Server documentation — https://docs.projectdiscovery.io/opensource/interactsh/server
* GreyNoise Labs Weekly OAST Report, week ending 2026-01-24 — https://www.labs.greynoise.io/grimoire/2026-01-24-weekly-oast-report/
* A Glossary of Blind SSRF Chains, Shubham Shah, Assetnote, 13 January 2021 — https://blog.assetnote.io/2021/01/13/blind-ssrf-chains/
* Out-of-Band Exploitation (OOB) CheatSheet, NotSoSecure — https://notsosecure.com/out-band-exploitation-oob-cheatsheet

Web (search results only, not fetched — treat the specific claims as
second-hand): PortSwigger's rotation of the public Collaborator domain from
`burpcollaborator.net` to `oastify.com` to defeat WAF blocklisting; ZAP's
Log4Shell detection note that DNS is the most reliable JNDI signal because
outbound DNS is more often allowed than LDAP/RMI; bug-bounty triage guidance
that PoCs should use "no third-party callbacks beyond program-approved
out-of-band servers".

Repository:

* `src/redkraken/oob.py`, `src/redkraken/callback.py`
* `src/redkraken/config.py`, `src/redkraken/scope.py`, `src/redkraken/roster.py`,
  `src/redkraken/cli.py`
* `src/redkraken/migrations/0018_vocabularies.sql`
* `src/redkraken/migrations/20260812T040000Z__a_callback_arrives_on_a_declared_channel.sql`
* `src/redkraken/migrations/20260812T063000Z__the_evidence_view_the_agent_reads.sql`
* `src/redkraken/migrations/20260910T000000Z__an_arrival_resolves_to_one_interaction.sql`
* `src/redkraken/migrations/20260911T000000Z__a_canary_ends_by_verb.sql`
* `src/redkraken/migrations/20260912T000000Z__an_out_of_band_host_is_bound_not_declared.sql`
* `src/redkraken/migrations/20260826T000000Z__seven_topics_arrive_as_playbooks_and_the_targets_that_grade_them.sql`
* `src/redkraken/playbooks/` (50 directories), in particular `webhooks/`,
  `jwt-jose/`, `sql-injection/`, `ssrf-url-routing/`, `command-directory-injection/`
* `docs/research/playbook-state-of-the-art/00`, `01`, `03`, `04`, `05`, `08`
