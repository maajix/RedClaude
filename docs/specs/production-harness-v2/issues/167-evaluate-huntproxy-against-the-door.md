# 167 -- Evaluate HuntProxy against the door and the evidence chain

**What to build:** An answer, on record, to whether
[HuntProxy](https://github.com/BehiSecc/HuntProxy) -- an Apache-2.0 Rust web
security workbench that serves an MCP surface to an agent over a TLS-intercepting
proxy, a Chromium worker and a SQLite store -- can be integrated into this
harness, or whether some named part of its design is worth copying while the
program itself is declined. It changes no code either way; it ends in a
recommendation and an ADR.

**Blocked by:** nothing. This is a reading and a measurement.

**Status:** ready-for-agent

- [ ] **The metadata this ticket could not fetch is fetched.** Every call to
      `api.github.com/repos/BehiSecc/HuntProxy` during this reading returned
      `504 Gateway Time-out`, so repository size in KB, total commit count,
      contributor count, release and tag history, and whether any published
      binary is reproducible from the source tree are all unmeasured here.
      The star and fork counts below came off the rendered repository page and
      are a single reading, not a series.
- [ ] **Its MCP surface is enumerated from source, not from the README.** The
      README names capabilities and never names a tool. `src/mcp/mod.rs` is the
      only file in `src/mcp/`. Read it for the tool names, their arguments, and
      specifically whether any tool takes a free-form URL or a free-form request
      -- that is the argument that decides whether its surface could ever be
      compiled into `CONTRACTS` (`src/redkraken/roster.py:1184`).
- [ ] **The scope claim is checked against `src/policy/` rather than the FAQ.**
      Its own FAQ says capture scope is not an outbound allowlist. Establish
      from source what `src/policy/` actually decides, where it is consulted,
      and whether `src/proxy/`, `src/browser/`, `src/reply/` and `src/fuzzer/`
      share one egress chokepoint or own four. A single chokepoint is the only
      shape under which a Fence could ever be spliced in; four is a decline.
- [ ] **Its evidence model is read as a schema.** `migrations/004_findings.sql`
      and `001_init.sql`: what a finding cites, whether a finding can exist with
      no exchange behind it, and whether any table is writable by anything but
      its own daemon. Set that against `receipts`, `observations`,
      `hypotheses` and the citation failure modes at `CONTEXT.md:640-647`.
- [ ] **The containment question is answered with a run or a named reason it
      cannot be.** A daemon that auto-starts on MCP connect, holds a Chromium
      profile and exits after an hour of idle is answered against per-run
      containment, the Halt gate and the request budget -- the same bar
      ticket 89 set for a daemon and ticket 77 set for a browser. Specifically:
      put it on an `--internal` network whose only peer is the door, with DNS
      blackholed, and record what it does.
- [ ] **The two things it does that this tree does not are measured in facts
      per token, not in features.** One WebSocket conversation and one fuzz
      response group, against what a hunter reading Receipts through
      `mcp__rk2__get_receipts` pays for the same conclusion. If the answer is
      that this tree cannot produce the conclusion at all, that is the result.
- [ ] **The plugin contract is read on its own merits and the parts worth
      keeping are quoted**, so that "adopt the shape, not the binary" is a
      decision with content behind it rather than a compliment. Ten plugins ship
      in `BehiSecc/HuntProxy-Plugins`, Apache-2.0, JavaScript under QuickJS.
- [ ] **The licence question is answered in both directions.** HuntProxy is
      unmodified Apache-2.0. This repository ships no `LICENSE` file and
      `pyproject.toml`'s `[project]` table (lines 11-26) declares no `license`,
      so there is no outbound licence here to check an inbound one against.
      Say what copying a file in would oblige and what reading one obliges
      (nothing).
- [ ] **A decision is recorded** -- adopt, adopt for one named job, adopt the
      shape only, or decline -- with the reason, as an ADR under `docs/adr/` at
      `0007`. Declining is a result and closes this ticket, the way `0004`,
      `0005` and `0006` closed tickets 77, 89 and 90.
- [ ] **No production code path depends on HuntProxy unless the decision is
      adopt.** A spike lives under `/tmp` or is deleted, and nothing from
      `~/.huntproxy` enters this repository.

## Why this is asked

The operator found it and asked. The premise worth testing is that somebody
built, in the open and recently, the thing this repository has been building for
a hundred and sixty tickets: a proxy that captures every exchange, a browser
that shares the capture, a replayer, a findings model that attaches evidence to
the exchange that proves it, and an MCP surface that hands all of it to a model.
If that is true, the honest question is not "should we use it" but "what did
they get right that we did not, and what does our version buy that theirs does
not".

The premise worth doubting is in its own FAQ, quoted in full below, and it is
the single sentence that decides most of this ticket.

## What HuntProxy is, measured rather than assumed

Read on 2026-08-23, from the repository page, `README.md` at `master`, the
`LICENSE` file, the `src/` and `migrations/` trees, and the
`BehiSecc/HuntProxy-Plugins` page. Nothing was cloned, installed, built or run.

- **Licence:** Apache License 2.0, the standard unmodified text, with the
  template `Copyright [yyyy] [name of copyright owner]` boilerplate left in the
  appendix. `HuntProxy-Plugins` is Apache-2.0 as well.
- **Language and shape:** Rust. `src/` holds `api`, `app`, `browser`, `codec`,
  `config`, `crawler`, `domain`, `fuzzer`, `history`, `mcp`, `page_analyzer`,
  `plugins`, `policy`, `proxy`, `reply`, `storage`, `transport` and `websocket`,
  plus `compare.rs`, `cookies.rs`, `copy_as.rs`, `get_words.rs`, `har.rs`,
  `lib.rs`, `main.rs`, `page_title.rs`, `request_rules.rs`, `transfer.rs` and
  `update.rs`. Beside it: `browser-worker/` (Chromium), `web/` (a UI),
  `migrations/`, `spikes/transport_spike/`, a `Dockerfile` and a
  `rust-toolchain.toml`.
- **Store:** SQLite. Fourteen migrations, `001_init.sql` through
  `014_named_cookie_profiles.sql`, and the names are the feature list:
  `004_findings`, `005_javascript_provenance`, `009_websockets`,
  `010_request_rules`, `011_fuzz_response_groups`, `013_ip_rotation`.
  Everything lives under `~/.huntproxy` -- "database, configuration, browser
  profiles, CA, logs, plugins, and exports" -- redirectable with
  `HUNTPROXY_DATA_DIR` or `--data-dir`.
- **How an agent reaches it:** MCP over stdio. The bridge auto-starts a local
  daemon on connect and the daemon exits after an hour of inactivity. The CLI
  is `init`, `serve`, `mcp`, `doctor`, `status`, `stop`, `project`, `har`,
  `backup`, `history clear` and `browser cdp`. A web UI answers on
  `127.0.0.1:17890` under Docker.
- **Install:** `curl -fsSL .../install.sh | bash`. The repository added
  "verified binary self-update" and a "release-only binary installer" on
  2026-08-16.
- **Plugins:** JavaScript, loaded from `~/.huntproxy/plugins`, run under
  QuickJS. The contract, quoted from the plugins repository: *"A plugin plans a
  bounded test and analyzes the result. HuntProxy performs the requests, applies
  scope and resource limits, and saves the traffic and evidence. Plugin
  JavaScript runs inside QuickJS and cannot open sockets, read files, launch
  processes, use Node.js modules, or call `fetch()` directly."* Ten enabled
  plugins ship.
- **Activity and size:** last commits 2026-08-17 ("Update README"), with
  substantial work on 2026-08-13 through 2026-08-16 -- "Harden plugin URL
  execution", "Scope plugin replays to selected exchanges", "Bound plugin
  analysis observations", "Add isolated browser CSRF probes". The rendered page
  showed 59 stars and 1 fork. It is alive and it is small.

## What is already here, so the comparison is against the real thing

- The door is the one peer a contained child has, and it is on two networks
  whose difference is the whole boundary (`CONTEXT.md:837-848`). The scope
  policy, the Halt and the capability check are all enforced there.
- `proxy.Fence` (`src/redkraken/proxy.py:1196`) decides before the connection --
  `authorize` (`:1240`), `authorize_address` (`:1315`), `reserve` (`:1351`) --
  and records after it. `allowed_receipt` (`:1425`) writes one exchange,
  `blocked_receipt` (`:1744`) writes the ones it refused, and `measurement`
  (`:1491`) files a handshake the door took on its own behalf. A blocked request
  is still a Receipt; there is no request the door saw and did not record.
- A Receipt carries the hashes of what the agent saw and what crossed the wire,
  "which differ by exactly the injected credentials" (`CONTEXT.md:650-653`).
  `proxy.project_identity_request` (`:719`) is the one rewrite this tree
  performs, and `proxy._scrubbed` (`:766`) is what keeps the credential out of
  what the model reads.
- The model-facing surface is closed. `Contract` (`roster.py:744`) declares the
  tables each tool reads and writes so "the one tool that reaches a canonical
  table is visible as the one tool that does"; `CONTRACTS` (`:1184`) is the
  whole list; `mcp__rk2__http_request` (`:1719`) is the only member of
  `net.request` (`:943`) and declares `writes=("receipts", "artifacts",
  "artifact_refs")`. Every schema is `additionalProperties: false` (`:762-767`).
- The gate is default-deny on the tool name. `Gate._decide`
  (`roster.py:2253-2262`) returns `UNLISTED_TOOL` for anything not in the
  caller's compiled set, and that is the boundary rather than the SDK's own
  `allowed_tools`, because the permission mode is `bypassPermissions`
  (`roster.py:15-23`).
- The model never promotes. `roster.py:930-936`: *"There is no `promote` here at
  all: promotion is the runtime step that turns a raw result into canonical
  rows, and a model-facing verb for it would be the agent promoting its own
  conclusions."*
- Canonical state has one writer role. `GRANT SELECT, INSERT, UPDATE, DELETE ON
  ALL TABLES IN SCHEMA public TO rk2_runtime`
  (`src/redkraken/migrations/0017_program_isolation.sql:487-489`), and nothing
  else holds it.
- The scope policy is per-Program and versioned, and it is a compiled rule set
  rather than a filter: `scope.parse_pattern` (`:616`), `scope.Rule.matches`
  (`:684`), `scope.canonical_request` (`:466`), with the Channel, Header and
  Permission declarations beside it (`:765`, `:868`, `:885`).
- The browser is driven over raw CDP by `src/redkraken/browser_driver.py`
  through the same door, and `pyproject.toml:27` is `dependencies = []` with a
  startup assertion holding it there.

## 1. What HuntProxy does that this harness does not

- **A fuzzer.** Sniper, battering ram, pitchfork, cluster bomb, with response
  grouping (`migrations/011_fuzz_response_groups.sql`). This tree has none:
  `fuzz` appears nowhere under `src/redkraken/`, in `CONTEXT.md`, or in the
  spec. A hunter sends one request per `mcp__rk2__http_request` call.
- **WebSocket capture and inspection** (`src/websocket/`,
  `migrations/009_websockets.sql`). The only `websocket` in this tree is a
  Program application kind (`roster.py:225`). The door cannot carry one on
  purpose: `tls.ALPN = ["http/1.1"]` (`src/redkraken/tls.py:81`) is offered
  explicitly so "a client that would have negotiated HTTP/2 with the door speaks
  HTTP/1.1 instead: the alternative is a handshake that succeeds and a tunnel
  that then carries frames nothing here can read" (`tls.py:77-80`). Same line
  refuses HTTP/2 replay.
- **HAR export** (`har.rs`, the `har` subcommand). `har` matches nothing under
  `src/redkraken/` or in `CONTEXT.md`.
- **Request rewrite rules across components** (`migrations/010_request_rules.sql`,
  `request_rules.rs`). This tree rewrites exactly one thing, and it is the
  Identity (`proxy.py:719`).
- **Upstream proxy chaining and IP rotation**
  (`migrations/013_ip_rotation.sql`, `~/.huntproxy/config.toml`) as a stated
  answer to CAPTCHAs and bot detection on a VPS.
- **A human-facing web UI and a browser handoff.** `browser cdp` hands the live
  session to a person when an interactive challenge appears. This tree's
  equivalent is `park_for_human` (`roster.py:1687`), which parks a Task -- it
  does not hand over a session.
- **A crawler** (`src/crawler/`) and a page analyser (`src/page_analyzer/`,
  `page_title.rs`, `get_words.rs`).

## 2. What it does that this harness already does

Every one of these would be a second implementation of an existing authority,
not an addition to it:

- **A TLS-intercepting proxy with its own CA that stores every exchange.** Its
  `history` against `receipts`. Two proxies, two stores, two answers to "what
  did we send".
- **A Chromium worker driven over CDP** (`browser-worker/`) against
  `browser_driver.py` and the loopback shim that puts the door's control headers
  on the hop.
- **Replay with modification** against `src/redkraken/replay.py` and the Test /
  Lane model, where a replay's Receipts carry `replay` without the runtime
  saying the word (`CONTEXT.md:161-165`).
- **Findings attached to the exchange that proves them** against Observations,
  Receipts and Hypotheses, and against the six-way citation check at
  `CONTEXT.md:640-647`.
- **A JavaScript discovery pass** (`migrations/005_javascript_provenance.sql`)
  against `src/redkraken/jsscan.py`, `js_routes`, `js_map` and
  `extract_paths.py`, whose limits ticket 92 already owns.
- **A sitemap built from captured exchanges** against `entities`,
  `relationships` and `mcp__rk2__get_attack_surface` -- the same ground ADR 0006
  already covered when it declined CodeGraph.
- **A sandboxed extension that plans rather than performs.** Its QuickJS plugin
  is, in one sentence, this tree's whole separation of proposal from promotion.
- **An MCP tool surface.** Adopting it means a second MCP server beside `rk2`,
  and every tool on it is denied by `Gate._decide` (`roster.py:2260`) until
  somebody compiles it into a role -- at which point the roster is describing
  authority it does not enforce, because the enforcement would be in the Rust
  daemon.

## 3. Which ideas are worth copying, and what each costs

- **The plugin contract sentence, applied to Playbooks.** "A plugin plans a
  bounded test and analyzes the result. HuntProxy performs the requests, applies
  scope and resource limits, and saves the traffic and evidence." This tree
  ships fifty Playbooks (`src/redkraken/playbooks/`, `playbook.py:267`) and they
  are prose a model reads, with Expectations and Projections but no steps the
  runtime performs. Migration
  `20261023T000000Z__fifty_playbooks_and_not_one_has_ever_been_selected.sql` and
  ticket 164 record what that has cost. Tickets 98 and 99 are already walking a
  Playbook step toward the OOB channel and the browser. The idea worth copying
  is the QuickJS boundary as a *shape*: a step vocabulary the runtime executes,
  with the analysis running somewhere that cannot open a socket. **Cost:** a
  step vocabulary, a performer, and a decision about whether the analysis half
  is a model or a sandbox. This is the largest and the only one that is
  arguably a design change rather than a feature.
- **Fuzz response grouping** (`011_fuzz_response_groups.sql`). Not the fuzzer --
  the grouping. Two hundred responses that collapse into four classes is a token
  argument, and it applies to Receipts this tree already has. **Cost:** a
  grouping function over `receipts`, no new egress, no new store.
- **HAR as an export format.** It is the one interchange format the rest of the
  industry reads, and an evidence bundle that could emit one would be readable
  by a triager with Burp and no harness. **Cost:** one writer over existing
  Receipt columns. Nothing about the evidence chain moves.
- **"Sensitive headers are redacted from inspection tools but available locally
  for authenticated work; explicit reveals are audited."** This tree already
  scrubs (`proxy._scrubbed:766`) and already differs the two hashes
  (`CONTEXT.md:650-653`). The half worth checking we have is the *audited
  explicit reveal*.

Not worth copying: the fuzzer itself, IP rotation, the upstream proxy chain, the
web UI, and the self-updater.

## 4. What integrating it would break or widen

- **Its own FAQ says its scope is not an outbound allowlist.** Verbatim:
  *"Does project scope stop out-of-scope requests? No. Capture scope is not a
  general outbound allowlist: Proxy, Browser, Reply, and Fuzzer can send
  requests that are not saved to History."* That is the inverse of this
  harness's door, where `Fence.authorize` decides before the connection and a
  refusal is itself a Receipt (`proxy.py:1744`). Adopting HuntProxy's transport
  would put four request paths outside the scope decision, and one of them --
  the fuzzer -- is the highest-volume one.
- **Requests that are not saved to History are, in this harness's terms,
  requests with no Receipt.** The FAQ sentence above is not only a scope
  finding; it is an evidence finding. A hunt whose egress can send bytes that no
  row records has lost the property that the Receipts of a run are the whole of
  what it reached (`CONTEXT.md:593-594`), and a Finding composed on top of it
  cites a chain with a hole in it.
- **A second SQLite store is a second canonical state, written by something
  other than the runtime.** `rk2_runtime` is the only role granted write on this
  schema (`0017_program_isolation.sql:487-489`) and every model-facing tool
  declares its tables (`roster.py:744`). A `findings` table under
  `~/.huntproxy` that a daemon fills is evidence this runtime did not observe,
  promoted by nobody, citing nothing this tree can check.
- **A daemon that auto-starts on MCP connect and reaches the network itself is a
  second egress.** The door is defined as the one process a contained child can
  reach (`CONTEXT.md:837-843`). A HuntProxy daemon on the operator's loopback
  that speaks to targets is a route around the fence, and no Receipt can be
  written for a request the door never saw. Any adoption that is not "the daemon
  runs contained with the door as its only peer" is this finding.
- **Verified binary self-update defeats the build manifest.** The Door refuses
  to listen unless the modules on disk match the revision they were cut from,
  "because a Door running code that is in no commit writes Receipts that are
  honest about the request and wrong about the harness"
  (`CONTEXT.md:858-868`). A component that replaces its own binary between runs
  is exactly that state, one process over.
- **`curl | bash` is not an install this tree can attest.** Nothing here is
  installed that way; `rk doctor` verifies an install against a manifest.
- **`dependencies = []`.** `pyproject.toml:27`, held by a startup assertion. A
  Rust daemon is not a Python dependency, so the letter of that line survives --
  and its reason does not.

## 5. Licence

HuntProxy and HuntProxy-Plugins are both Apache License 2.0, the unmodified
text. That is permissive and imposes nothing on reading it: an idea taken from
a README is not a derivative work, and this whole ticket is a reading.

Copying source is a different question and the answer has two halves. Apache-2.0
would oblige this repository to keep the licence and copyright notices, state
what was changed, and carry a `NOTICE` if the upstream ships one -- and it would
bring a patent grant with it, which is a benefit. The half that is not upstream's
problem is ours: **this repository ships no `LICENSE` file and `pyproject.toml`
declares no `license`**, so there is no stated outbound licence for an inbound
one to be compatible with. Apache-2.0 code copied in would be the first licensed
code in the tree, and settling this repository's own licence is a prerequisite
to that rather than a detail of it. That is not this ticket's job, but this
ticket is where it was noticed.

## What "no" looks like, and why it is fine

The likely answer is decline-the-program, copy-two-things, and the shape of it
is one paragraph: HuntProxy is a good workbench for a human's agent and this is
not a workbench, it is a harness with an authority model, and the two disagree
on the one question that matters -- whether the egress may send a request
nothing recorded. HuntProxy's own FAQ says it may. This tree's door says it may
not, and every Receipt, Observation and Finding downstream is built on that
answer.

A partial yes is also a real result. **Adopt the shape for one named job** --
the plugin contract as the model for an executable Playbook step -- is a smaller
claim, has fifty unselected Playbooks behind it as motivation, and would sit
next to tickets 98 and 99 rather than next to the door.

## Answer, 2026-08-24: the audited-reveal bullet is already satisfied

The fourth bullet of section 3 -- *"Sensitive headers are redacted from
inspection tools but available locally for authenticated work; explicit reveals
are audited"* -- was promoted into ticket 172 as a measurement before it could
become a build. The measurement is done, and the answer is that this tree
already satisfies the sentence and satisfies it more strictly than the sentence
asks. Nothing is copied, and the bullet is closed rather than pending.

- **One reveal path exists and it is the operator's.** `rk artifact open`,
  declared at `src/redkraken/cli.py:1032-1038` -- *"decrypt one wire artifact to
  a file, deliberately and audited"* -- adapted at `src/redkraken/cli.py:3002`,
  implemented by `artifact.open_wire` at `src/redkraken/artifact.py:768`. It is
  not a Contract and not a tool: `roster.py`, `evidence.py` and `replay.py`
  contain no occurrence of `artifact_seal`, `request_wire_sha` or
  `response_wire_sha`. The evidence export (`src/redkraken/cli.py:2847-2853`)
  and the legacy import (`:2881-2886`) each say why they hold no key.
- **The scrubbing half was already verified in section 3 and holds.**
  `proxy._scrubbed` (`src/redkraken/proxy.py:766`), reached from
  `project_identity_request` (`:719`) and `project_identity_response` (`:677`)
  over `_renderings` (`:780`), with `response_for_agent` (`:663`) dropping the
  wire-only headers first and `proxy.wire_view` (`:880`) hashing the sealed view
  separately, which is what makes `CONTEXT.md:650-653` true.
- **Authorization is demanded before the lookup**, so a refused caller learns
  nothing about which labels have a seal behind them
  (`src/redkraken/artifact.py:822-838`), and the refusal is itself an audit row
  (`:824-831`).
- **Refusals are recorded as loudly as successes**
  (`src/redkraken/artifact.py:1228-1234`), which is the half the sentence does
  not ask for: a trail with only the successes answers *"who opened this"* and
  cannot answer *"who tried"*.
- **The audit row is written before the bytes are released**, and the comment at
  `src/redkraken/artifact.py:942-948` says which failure state that ordering
  chooses; the release row is at `:949-959`.
- **The record carries no secret**: `value_len` and a four-byte keyed
  fingerprint, never the value
  (`src/redkraken/migrations/0024_secret_keying.sql:105-109`, `:130-131`), with
  the report carrying the path, length, hash, fingerprint and the operator's
  stated reason and nothing else (`src/redkraken/artifact.py:977-989`) and the
  plaintext going to a file opened `O_EXCL` at mode `0o600` (`:1268-1276`).
- **The row names the exchange it was opened out of**, since ticket 123, found
  by joining the plaintext hash back to the Receipt rather than carried down
  from a caller (`src/redkraken/artifact.py:290-305`, `:873`, and
  `src/redkraken/migrations/20260925T030000Z__a_secret_read_names_the_exchange.sql:58-69`).

No criterion above is ticked by this. None of this ticket's criteria covered the
fourth bullet -- it lives in section 3's prose, which is a list of ideas and not
a deliverable -- so this section closes the bullet and leaves the criteria as
they were. Ticket 172 keeps the number and has been rewritten around the three
gaps the measurement turned up on the way, all of which are this tree's own and
none of which came from HuntProxy: the peer columns of `secret_access_log` that
nothing writes and no comment explains, the trail that no operator verb reads,
and rules 3 and 4 of `check_wire_artifact_secrecy` having no negative control.
