# 21 — The agent surface: what the runtime can do versus what an agent can invoke

Sweep axis: the agent surface. Read-only audit. Every claim carries `file:line`;
where nothing was found the entry says **not found** rather than guessing.

Vocabulary used throughout:

- **Contract** — an entry in `CONTRACTS`, `src/redkraken/roster.py:601-854`. The
  complete declared model-facing surface. Sixteen entries.
- **Served** — a Contract for which `_launch.server` actually builds an MCP tool,
  `src/redkraken/_launch.py:530-578`. Thirteen tools.
- **Capability** — a function, CLI verb or SQL function that performs a whole
  action an engagement would want (send a request, open a Finding, read a
  canary, compose a chain), as opposed to a helper or a check.

Headline counts:

| Measure | Count | Where |
|---|---|---|
| Contracts declared | 16 | `src/redkraken/roster.py:601-854` |
| Contracts served with a handler | 13 | `src/redkraken/_launch.py:569-577` |
| Contracts declared and never served | **3** | `sched.pick` remainder, `src/redkraken/agent.py:151` |
| Distinct SQL functions in the corpus | 509 | `src/redkraken/migrations/*.sql` |
| SQL functions granted to a role | 215 | explicit `GRANT EXECUTE ON FUNCTION` |
| Granted verbs with a `src/redkraken/*.py` caller | 76 | — |
| Granted verbs with **no** production caller | **12** | §3.2 table B |
| Relations on the agent read surface (`state_read_surface`) | 30 inserted, **28 live** | §2.4 |
| Live agent-readable relations named by a Contract's `reads` | **7** | §2.4 |
| Contract arguments consumed end to end | 32 of 36 | §4 |
| Contract arguments that reach nothing | **4** (all on the 3 unserved Contracts) | §4 |
| CLI leaf verbs | 50 | `src/redkraken/cli.py`, §6 |
| CLI verbs with a direct agent equivalent | **2** (`rk tool run`, `rk proxy request`) | §6 |
| Python capabilities with no production caller | **3** | §2.8 |

---

## 0. What changed while this sweep ran

**Measured against commit `63f05dd` ("DOCS: cut the capability gap into eight
tickets").** Every line number in this document is that commit's. The working
tree was dirty while the sweep ran — `src/redkraken/_launch.py`,
`src/redkraken/proxy.py` and `tests/test_proxy.py` carry an in-progress
implementation of ticket 94 — and `77f8bda` ("FIX: say maxLength when the bound
is on a string") shifted every line in `roster.py` after `Argument.schema` by
nine. Anything read before those landed has been re-derived.

Eight tickets (94-101) were opened at `63f05dd`. Five of them cover findings in
this document, and that overlap is stated up front so the rest is read as the
residue:

| Ticket | Status | Covers |
|---|---|---|
| `94-hand-the-response-headers-to-the-caller.md` | ready-for-agent, **being implemented in the working tree now** | §5.1 |
| `95-a-bounded-string-argument-must-say-maxlength.md` | resolved at `77f8bda` | prerequisite for 96 |
| `96-carry-a-request-body.md` | ready-for-agent | §4.1 |
| `97-settle-what-an-identity-slot-is.md` | ready-for-agent | the identity half of `roster.py:766-771` |
| `98-let-a-playbook-step-reach-the-out-of-band-channel.md` | ready-for-agent | §2.2 (the minting and evidence halves) |
| `99-let-a-playbook-step-drive-the-browser.md` | ready-for-agent | §2.1 |
| `100`, `101` | ready-for-agent | corpus and vocabulary, not this axis |

Ticket 99 states the finding in §2.1 in its own words: "The lane is built and
paid for; no model can reach it." Ticket 98 states §2.2's: "this is the half
neither of them owned."

**What this sweep found that those eight tickets do not cover:**

1. Three declared Contracts with no handler — §1.3, §2.7. Only
   `request_validation` has a written reason, and it defers to a ticket that
   does not exist in the tree.
2. `open_finding` has no caller, so **no Finding is ever created**, so the whole
   `validate.judge` tool group, the reporting path and the evidence bundle have
   no subject — §2.3, §3.2, §3.4.
3. Eleven further granted SQL verbs with no production caller — §3.2.
4. Twenty-one relations the agent's database role may read that no tool reads,
   including `negative_knowledge` and the three browser evidence tables — §2.4.
5. Every label an act tool returns after launch is unresolvable by the read
   tools, because the packet is a pre-launch snapshot — §5.4. **Tickets 98 and
   99 will each mint more such labels, so this defect gets worse before it is
   noticed.**
6. `stderr` from a tool run is filed and never returned — §5.3.
7. `http_request` returns no artifact label, so `net.request` and
   `exec.tool_run` cannot compose — §5.2. Ticket 94 hands back headers and not
   this.
8. `Store.holds`, `skill.check`, `skill.check_all` — dead Python, one of them
   claiming a caller it does not have — §2.8.

---

## 1. The full agent surface

Every `Contract`, its arguments, and the runtime verb or function it reaches.
`Served by` is the handler that builds the MCP tool; `Reaches` is the first
runtime function or SQL verb the call arrives at.

### 1.1 `state.read` — five reads, all answered from the pre-compiled packet

| Contract | Declared at | Arguments | Served by | Reaches |
|---|---|---|---|---|
| `mcp__rk2__get_attack_surface` | `roster.py:602` | `entity_type` (enum `ENTITY_TYPES`), `limit` (1-200) | `_launch.py:561`, `_launch.py:581` | `packet.Reader.attack_surface`, `packet.py:834` |
| `mcp__rk2__get_hypotheses` | `roster.py:612` | `subject_label` (`^(prefix)[0-9]{1,9}$`), `status` (enum), `limit` | `_launch.py:562` | `packet.Reader.hypotheses`, `packet.py:841` |
| `mcp__rk2__get_evidence` | `roster.py:622` | `hypothesis_label` (`H\d+`), `finding_label` (`F\d+`), `limit` | `_launch.py:563` | `packet.Reader.evidence`, `packet.py:855` |
| `mcp__rk2__get_receipts` | `roster.py:638` | `receipt_labels` (array of `R\d+`), `limit` | `_launch.py:564` | `packet.Reader.receipts`, `packet.py:873` |
| `mcp__rk2__get_artifact` | `roster.py:657` | `artifact_label` (`A\d+`), `range` (`^[0-9]+-[0-9]+$`, renamed to `span` at `_launch.py:594`) | `_launch.py:565` | `packet.Reader.artifact`, `packet.py:911` |

None of the five touches a database. The packet is built once, on the
supervisor's `rk2_state` connection, by `packet.compile`, `packet.py:587`, and
handed across as a job document read at `_launch.py:1017`. Consequence in §5.4.

### 1.2 `state.propose` — one write, latched in the child process

| Contract | Declared at | Arguments | Served by | Reaches |
|---|---|---|---|---|
| `mcp__rk2__submit_mission_result` | `roster.py:679` | `observations` (required, free), `new_entities`, `relationships`, `hypotheses`, `evidence`, `suggested_tasks` (all free arrays), `completion_claim` (required object, keys `^(status\|note)$`) | `_launch.py:573`, `_launch.py:854` | `Submission.submit`, `_launch.py:202` → latched → returned in the run result at `_launch.py:1113` → `agent.py:1139` → `proposal.Result`, `proposal.py:319` → SQL `promote_proposal`, called from `execution.py` |

### 1.3 `sched.pick` — five declared, two served

| Contract | Declared at | Arguments | Served by | Reaches |
|---|---|---|---|---|
| `mcp__rk2__get_slate` | `roster.py:695` | none | `_launch.py:574`, `_launch.py:780` | `Choice.entries`, `_launch.py:242`; entries come from the capsule at `_launch.py:1029` |
| `mcp__rk2__pick_task` | `roster.py:705` | `task_label` (required, `T\d+`) | `_launch.py:575`, `_launch.py:799` | `Choice.pick`, `_launch.py:249` → run result `choice` at `_launch.py:1122` → SQL `record_choice`, called from `execution.py` |
| `mcp__rk2__request_validation` | `roster.py:711` | `finding_label` (required, `F\d+`) | **not served** | **nothing** |
| `mcp__rk2__request_report` | `roster.py:722` | none | **not served** | **nothing** |
| `mcp__rk2__park_for_human` | `roster.py:727` | `task_label` (required), `question_code` (required, 5-value enum), `question` (free text) | **not served** | **nothing** |

The three unserved members are named as unserved at `src/redkraken/agent.py:151`:

> `SERVED_MEMBERS = {"sched.pick": ("mcp__rk2__get_slate", "mcp__rk2__pick_task")}`

with the reason at `src/redkraken/agent.py:143-146`:

> "`sched.pick` is five tools built by four tickets: the two here are the Slate the
> orchestrator is offered and the choice it makes on it, and the other three --
> validation, a report and parking for a human -- are requests their own
> tickets serve."

Verdict: **deliberate but unfinished**. The comment states a plan, not a
decision not to build. See §2.7 and §6 for what each of the three would have
reached.

### 1.4 `net.request` — one exchange

| Contract | Declared at | Arguments | Served by | Reaches |
|---|---|---|---|---|
| `mcp__rk2__http_request` | `roster.py:747` | `method` (required, enum of 7), `url` (required, `^https?://`), `headers` (object, name `^[A-Za-z][A-Za-z0-9-]{0,63}\Z`, value `^[\x20-\x7e]{0,1024}\Z`) | `_launch.py:570`, `_launch.py:600` | `_launch._spend`, `_launch.py:680` → `proxy.spend`, `proxy.py:3897` → `proxy._through`, `proxy.py:3937` → the door's `_answer`, `proxy.py:3244` |

### 1.5 `exec.tool_run` — two programs

| Contract | Declared at | Arguments | Served by | Reaches |
|---|---|---|---|---|
| `mcp__rk2__run_tool` | `roster.py:777` | `tool` (required, enum `("jq","js_map","js_parse","js_routes")`, `roster.py:793`), `arguments` (required object, names `^[a-z][a-z0-9_]{0,31}$`, values `^[^\x00]{0,512}$`) | `_launch.py:571`, `_launch.py:640` | `Channel.call`, `_launch.py:386` → pipe → `isolation` line reader, `isolation.py:576` → `agent._Tools.__call__`, `agent.py:1195` → `tool.serve`, `tool.py:416` → SQL `open_offline_tool_run` |
| `mcp__rk2__run_skill_script` | `roster.py:808` | `skill_name` (required), `script` (required), `arguments` (required object) | `_launch.py:572` | same chain; the pair is resolved by `tool.script`, `tool.py:551`, at `agent.py:1207` |

The four enum names and the two skill scripts together are exactly the six rows
in `offline_tools`: `20260814T030000Z__an_offline_tool_becomes_evidence.sql:159`
(`jq`), `20260814T050000Z__source_becomes_a_grounded_conclusion.sql:436`
(`js_map`, `js_parse`, `js_routes`), and
`20260922T030000Z__a_skill_script_is_a_program_the_harness_ships.sql:443`
(`compare_responses`, `extract_paths`, reached only through `run_skill_script`).
No registered binary is unreachable through this pair.

### 1.6 `validate.judge` — one read, one write

| Contract | Declared at | Arguments | Served by | Reaches |
|---|---|---|---|---|
| `mcp__rk2__get_validation_packet` | `roster.py:823` | `finding_label` (required, `F\d+`) | `_launch.py:576`, `_launch.py:817` | `Judgement.read`, `_launch.py:318`; packet from the job at `_launch.py:1034` |
| `mcp__rk2__submit_verdict` | `roster.py:835` | `finding_label` (required), `verdict` (required, enum of 3), `failed_assertion_ids` (array, `^[a-z][a-z0-9-]{2,62}$`) | `_launch.py:577`, `_launch.py:836` | `Judgement.judge`, `_launch.py:327` → run result `verdict` at `_launch.py:1126` → `validation.py:365` → SQL `record_verdict`, `20260815T180000Z__a_blind_validator_answers_from_the_packet.sql:1548` |

### 1.7 What the compile does and does not assert about this surface

`roster._check_contracts`, `roster.py:1728`, checks group membership, direction,
write class, canonical-table exclusion and every argument's shape. It **never
checks that a Contract has a handler**. `agent._check_served_members`,
`agent.py:164`, checks that a partially-served group's members belong to that
group — it does not check that a served name has a tool built for it in
`_launch.server`. Nothing anywhere asserts `set(agent.SERVED) == {the 13 names
_launch.server builds}`. That is the hole §1.3 fell through.

---
## 2. Runtime capabilities with no agent path

Twelve findings, ordered by how much of an engagement they cost. Each says what
the capability does, where it lives, and what would have to exist for an agent
to reach it.

### 2.1 The browser driver — ten complete actions, no contract, and a Skill that lies about it

**What it does.** A full CDP-driven browser mission behind the capability
proxy: navigate, wait, fill, inject a registered probe, click, assert text
present or absent, run a registered JavaScript probe and record its verdict,
capture the DOM, take a screenshot — plus a per-step network request count and a
full console/log JSONL artifact.

**Where it lives.**

| Action | Driver method | Registry row |
|---|---|---|
| `navigate` | `browser_driver.py:502` | `20260814T040000Z__a_browser_mission_runs_behind_the_door.sql:188` |
| `wait_for` | `browser_driver.py:531` | `:190` |
| `fill` | `browser_driver.py:562` | `:192` |
| `inject` | `browser_driver.py:565` | `:194` |
| `click` | `browser_driver.py:570` | `:196` |
| `assert_text` | `browser_driver.py:594` | `:198` |
| `assert_absent` | `browser_driver.py:597` | `:200` |
| `probe` | `browser_driver.py:609` | `:202` |
| `capture_dom` | `browser_driver.py:648` | `:204` |
| `screenshot` | `browser_driver.py:655` | `:206` |

Dispatch is reflective — `browser_driver.py:668`, `action = getattr(self,
step["action"], None)`, refusal at `:670`. The host side is `browser.run`,
`browser.py:129`, whose only caller in the entire repo is `cli.py:2674` (plus
`tests/test_database.py:26224`, `:44770`). `agent.py` does not import `browser`;
the only `import browser` in `src/` is `cli.py:21`.

**Agent path: none.** Four independent confirmations:

1. No browser Contract exists. All sixteen are at `roster.py:601-854`.
2. `run_tool.tool` is a closed enum of four binaries, `roster.py:793`.
3. The supervisor's tool dispatch is closed to two verbs and routes to
   `tool.serve`, not `browser.run` — `agent.py:1196`, `agent.py:1221`.
4. `browser.run` opens `open_browser_run`, `browser.py:193`, which is where an
   unregistered action name is refused — reached only from the operator's
   `--plan` file, validated at `cli.py:2829` as "readable JSON array" and
   nothing more.

**Deliberate or accidental: accidental, and actively contradicted.** The shipped
Skill `src/redkraken/skills/browser-evidence/SKILL.md` tells the agent, at
`:63`:

> "Start the mission through `mcp__rk2__run_tool`."

and again at `:167`:

> "It is a Tool run through `mcp__rk2__run_tool`, or a Skill script over..."

and lists all ten action names at `:21-24`, ending "There is no eleventh". Its
own `allowed-tools` line, `SKILL.md:3`, grants `mcp__rk2__run_tool` — whose enum
(`roster.py:793`) admits no browser name. An agent that loads this Skill and
follows it has no argument value that reaches `browser.run`. Nothing in the code
states this as intentional, and
`docs/specs/production-harness-v2/issues/99-let-a-playbook-step-drive-the-browser.md`
now says the same thing this section does: "The lane is built and paid for; no
model can reach it."

The only nearby comment explains something else — `browser_driver.py:3-6`
explains why the *driver file* has no Python importer ("It is staged into
`/input` and run by the container's own interpreter"), which is correct and
unrelated to the missing contract.

**What would have to exist.** Either a `browser.mission` Contract in a new tool
group whose arguments are `{steps: array-of-{action, ...}}` closed against
`browser_actions`, served by a handler that crosses `Channel.call`
(`_launch.py:386`) like `run_tool` does and lands in a supervisor branch beside
`agent.py:1203`; or a `browser` row in `offline_tools` plus its name in the
`run_tool` enum. The second is smaller and matches what the Skill already
promises. Also required: `browser_runs`, `browser_steps` and
`browser_step_results` are already on the agent read surface
(`20260814T040000Z:519`, `:523`, `:527`) and no Contract reads them (§2.4), so a
mission the agent started would still be a mission it could not read back.

### 2.2 The out-of-band channel and the callback canary — recorded and unreadable

**What they do.** `oob.serve`, `oob.py:604`, publishes one Program's payload
directory over loopback and **records every arrival as a `callback_interaction`**
(`oob.py:539` calls `callback.record`), including arrivals on methods the
publisher answers 405 to (`oob.py:387`, `:412-416` — recorded first, refused
second, deliberately). `oob.up`, `oob.py:716`, binds a public hostname through a
tunnel. `callback.provision`, `callback.py:92`, mints a correlator and prints the
address to embed. `callback.accept`, `callback.py:234`, admits an arrival an
operator's own listener caught.

**Where the reading stops.** There is **no reader of `callback_interactions`
anywhere in `src/`**. The nearest thing is the count `clear_callback_correlator`
returns, surfaced at `callback.py:507` — and you only get it by *ending* the
canary (`callback.clear`, `callback.py:453`, `cli.py:2465`). `oob.status`,
`oob.py:844`, reads the *binding* (hostname, id, `bound_at`, tunnel pid, a count
of live correlators at `oob.py:873`), not the interactions. `oob.serve` reports
in-process counters, `oob.py:694-712`, which die with the publisher.

**Agent path: none, in either direction.** No Contract lists
`callback_interactions` in `reads=`; the label prefix exists
(`roster.py:176`, `"callback_interactions": "CB"`) and nothing issues it to a
model. An agent can neither mint a canary, nor learn the hostname to embed, nor
read what came back. Arrivals do become Observations via
`record_callback_interaction`, so an agent could see one through
`mcp__rk2__get_evidence` (`roster.py:622-630`) — but only if an evidence edge
already cites it, and only if it was staged before the packet compiled (§5.4).

**Deliberate or accidental: split.**

- Learning the hostname is **deliberately** operator-only, `oob.py:850-854`:
  > "The only supported way to learn the name. Nothing in a configuration file
  > holds it, no agent composes it, and this reads it from the binding rather
  > than from anything remembered: a name that was released this morning is
  > absent here, which is the answer that stops it being embedded in a payload."
- Stopping the tunnel is **deliberately** operator-only, `cli.py:863`: "The
  tunnel process is the operator's to stop."
- **Having no reader for what a canary caught is accidental.** No comment
  anywhere explains it. An SSRF or blind-XXE finding is exactly the arrival this
  machinery records and exactly the thing no agent can cite. Now ticketed:
  `docs/specs/production-harness-v2/issues/98-let-a-playbook-step-reach-the-out-of-band-channel.md`
  — "a verb that mints a correlator for the run that will plant it, a name for
  the interaction on the evidence surface, and a positive control that makes
  silence mean something [...] tickets 14 and 69 are resolved and they built the
  recording half; this is the half neither of them owned."

**What would have to exist.** A `get_callback_interactions` Contract in
`state.read` taking `{correlator_label, limit}`, plus `callback_interactions` on
`state_read_surface`, plus a packet section — or, because the packet is a
pre-launch snapshot (§5.4), a live read path. The hostname stays operator-only
by the quoted decision; provisioning a correlator could reasonably become a
`sched.pick`-class request the runtime fulfils.

### 2.3 The Finding lifecycle — the verb that creates a Finding has no caller at all

`open_finding`, `20260815T120000Z__a_supported_claim_becomes_a_candidate.sql:758`,
contains the corpus's only `INSERT INTO findings` (`:839`). It is granted to
`rk2_runtime` (`:917`) and **nothing in `src/redkraken/*.py` calls it**. Details
and ticket evidence in §3.2 and §3.4. Downstream, `open_impact_task`,
`issue_pivot_stamp`, `build_kill_chain`, `read_kill_chain` and `state_severity`
are all likewise uncalled — the first three with tickets explicitly deferring the
model-facing verb to an "orchestrator dispatch ticket" that has not landed.

Effect on the agent surface: `validate.judge` — two Contracts, `roster.py:823`
and `:826`, a whole tool group, a blind-validator role
(`roster._check_authority`, `roster.py:1808-1810`) and a migration
(`20260815T180000Z`) — has no subject it can ever be handed, because no `F`
label is ever minted.

### 2.4 The declared agent read surface versus the declared agent read tools

`state_read_surface` is the registry of what the `rk2_state` role may read.
Twenty-eight relations are live in it (thirty inserted, minus `playbooks` and
`playbook_selections` removed by
`20260922T000000Z__the_agent_connection_cannot_read_the_playbook_catalogue.sql:34-36`).

Seven are named by a Contract's `reads=` tuple: `artifact_references`,
`entities`, `findings`, `hypotheses`, `v_artifacts`, `v_evidence`, `v_records`.

**Twenty-one are readable by the agent's own database role and reached by no
tool:**

| Relation | Declared at | What an agent loses |
|---|---|---|
| `browser_runs` | `20260814T040000Z:519` | the result of any browser mission |
| `browser_steps` | `20260814T040000Z:523` | the plan that ran |
| `browser_step_results` | `20260814T040000Z:527` | per-step outcome, incl. `scope_class` |
| `tool_runs` | `20260814T030000Z:429` | its own tool runs, incl. ones from earlier Tasks |
| `tool_run_artifacts` | `20260814T030000Z:422` | which artifact a tool run produced |
| `tool_run_inputs` | `20260814T050000Z:243` | what a tool run was fed |
| `tool_run_paths` | `20260814T050000Z:364` | the path literals a source analysis found |
| `test_run_receipts` | `20260815T000000Z:2018` | which exchanges a replayed Test made |
| `negative_knowledge` | `20260814T080000Z:1128` | what has already been refuted — the single highest-value read for not repeating work |
| `negative_knowledge_retests` | `20260814T080000Z:1134` | when a refutation is due to be retried |
| `relationships` | `20260813T090000Z:408` | the graph edges between entities |
| `entity_provenance` | `20260813T090000Z:407` | where a known entity came from |
| `surface_facts` | `0032_playbooks.sql:700` | the typed surface summary |
| `events` | `20260810T094500Z:366` | the append-only log |
| `report_templates` / `report_blocks` / `report_effects` | `20260820T000000Z:939`, `:938`, `0034_reports.sql:1089` | what a report must contain |
| `redaction_rules` | `20260821T000000Z:595` | what will be redacted from its evidence |
| `program_required_headers` | `20260810T193000Z:175` | which headers the door will stamp |
| `artifact_refs` | `20260810T151500Z:211` | — reached indirectly through `v_artifacts` |
| `rk2_state` | `0030_corpus_corrections.sql:263` | — role/bookkeeping row |

`get_attack_surface` declares `reads=("v_records", "entities", "domains", ...,
"identities")` at `roster.py:604-605` and `relationships` is not among them,
even though `mcp__rk2__submit_mission_result` accepts a `relationships` element
list (`roster.py:686`). **An agent may propose relationships it can never read
back.**

**Deliberate or accidental.** The playbook removal is deliberate and has its own
migration. `negative_knowledge` is the loudest accidental one: an entire
migration (`20260814T080000Z__a_refutation_is_kept_and_made_due.sql`) exists to
keep refutations and make them due for retest, it puts both tables on the agent
read surface at `:1128` and `:1134`, and no tool reads either.

**What would have to exist.** Each is a `state.read` Contract plus a packet
section in `packet.SECTIONS` (`packet.py:43`) and a `_records`-style compile
step (`packet.py:609-612`) — the mechanism is already generic; the missing piece
is the declaration.

### 2.5 The evidence bundle

`evidence.export`, `evidence.py:174`, and `evidence.verify`, `evidence.py:662`,
produce and check the bundle that leaves the harness. Callers: `cli.py:2791` and
`cli.py:2806`, and nothing else in `src/`. No Contract reaches either.
`redaction_rules` — what will be stripped from that bundle — is on the agent read
surface (`20260821T000000Z:595`) and reached by no tool. Nothing states this as
a decision. Reasonably operator-only (a bundle leaving is a human act), but the
absence is undocumented, so: **accidental by the repo's own standard**
(`roster.py:771-774`).

### 2.6 The replay lane

`replay.run`, `replay.py:101`, runs a Test through the replay lane. Callers:
`cli.py:2705` and `validation.py:207`. No agent path. `test_run_receipts` is on
the agent read surface and unread (§2.4). Plausibly deliberate — replay is the
runtime's proof lane and ADR 0003 puts commitment with the runtime — but **not
found**: no comment says so.

### 2.7 Three declared Contracts with no handler

`mcp__rk2__request_validation`, `mcp__rk2__request_report` and
`mcp__rk2__park_for_human` (§1.3). Each writes a table that exists and is
serviced from elsewhere:

| Contract | Table it declares | Who fills that table today |
|---|---|---|
| `request_validation` | `validation_queue`, `roster.py:714` | `rk finding validate`, `cli.py:1278` — ticket 37 says so explicitly |
| `request_report` | `report_queue`, `roster.py:725` | `rk report finding`/`chain`, `cli.py:1497`/`:1517` |
| `park_for_human` | `pending_decisions`, `roster.py:730` | the door, `proxy.py:3552`, `SELECT park_for_human($1::uuid)` |

The third is the sharpest: an agent that hits a scope ambiguity or a destructive
action has a declared question_code enum for exactly that
(`roster.py:735-742`) and no way to ask. The runtime can park it from the
network side; the model cannot ask to be parked.

`request_validation` is **deliberate and documented**
(`docs/specs/production-harness-v2/issues/37-validate-finding-blindly.md:94-97`).
The other two are covered only by the plan-shaped note at `agent.py:143-146`.

### 2.8 Python capabilities with no production caller at all

Three, none with a comment explaining the absence:

| Capability | Lives at | What it does | Callers | Verdict |
|---|---|---|---|---|
| `Store.holds` | `store.py:162` | Whether bytes are already filed, without reading them back | `tests/test_database.py:35967`, `:42286`, `:42316`, `:42334` only | **Accidental, and self-contradicting.** Its docstring (`store.py:163-168`) names the proxy as its caller — "which is what the proxy asks before deciding whether withholding a wire view would withhold anything at all". The proxy asks the database instead: `proxy.py:1061`, `READS = "SELECT program_reads_artifact($1, $2)"`. Superseded and never removed |
| `skill.check_all` | `skill.py:477` | Run every declared synthetic case in the Skill corpus | `tests/test_skill.py:372`, `:380`, `:388`, `:516` only | Accidental. Its docstring (`skill.py:478`) says "so a caller can count" and there is none. `doctor.diagnose` compiles all three corpora (`doctor.py:103-105`) and never checks the Skill scripts, so shipped Skill scripts are never executed outside the test suite |
| `skill.check` | `skill.py:430` | Run one Skill script case twice under a bare env and refuse any answer but the declared one | `skill.py:483` only, inside `check_all` — the whole subtree is production-dead | Accidental |

`jsscan.py`'s entire public surface (`tokenize` `:156`, `calls` `:531`, `parse`
`:769`, `routes` `:826`, `sourcemap` `:856`, `answer` `:918`, `main` `:938`)
looks orphaned to a Python cross-reference and is **not** a defect: it is mounted
into a tool container and executed as a subprocess — `tool.py:118`
(`ANALYSERS = Path(__file__).parent`), `tool.py:653`, `tool.py:666`. Same shape as
`browser_driver.py`. Do not confuse the two: `jsscan.py` has a live invoker;
`browser_driver.py` has one only through an operator command.

One deliberately uncalled function, quoted because it is the model of how this
should be documented —
`src/redkraken/skills/analyse-source/scripts/extract_paths.py:151-157`:

> "Not called by `extract`, and here on purpose: the method reaches the analyst
> inside `literals`, which carries the string as the build wrote it. This is the
> other half of `jsscan.method_of`, which does report it as its own key, and the
> test named in the module docstring holds the two answers equal."

### 2.9 Known-stale documentation of this exact defect class

`docs/specs/production-harness-v2/issues/19-serve-bounded-mcp-reads-and-proposals.md:173-178`
says `packet.compile` and `proposal.stage` "have no caller in `src/` yet".
That is now **stale** — `execution.py:1794` and `execution.py:2235` call them.
Recorded so it is not re-reported as a live gap.

The repo already names this defect class for the SQL side, `integrity.py:4-8`:

> "The defect that registry exists to prevent is a checker with no caller: nine
> of the prototype's twelve had none, and four live defects survived in the gap.
> So there is one gate, it runs everything registered, and every command that
> changes the database ends by running it."

That gate exists for `check_*` functions and for nothing else. Every finding in
this document is the same defect in a place that gate does not look.

---
## 3. Database verbs versus what is reachable

### 3.1 What `runtime_verb_surface` actually is

`runtime_verb_surface` is created at
`src/redkraken/migrations/20260909T000000Z__the_runtime_holds_what_the_surface_declares.sql:103-107`:

```
CREATE TABLE runtime_verb_surface (
    verb     text PRIMARY KEY,
    added_by text NOT NULL DEFAULT '66',
    note     text NOT NULL
);
```

Its stated meaning, `:109-110`:

> 'The functions revoked from PUBLIC that the runtime connection may still
> execute, written as `name(argument types)`. A function open to PUBLIC needs no
> row: the rule this registry states is that closing a function to PUBLIC now
> closes it to the runtime as well, and this names the exceptions.'

It is **not a hand-written list of verbs somebody intended the runtime to
call**. It is seeded from the live catalogue at `:169-173`:

```
INSERT INTO runtime_verb_surface (verb, added_by, note)
SELECT v.verb, '66-seed', 'granted at creation by 029''s default privileges, ...'
  FROM runtime_verbs v
 WHERE v.closed AND v.held;
```

The seed comment says so at `:159-164`: "The seed is the catalogue, not a list.
A list written here would be a second copy of 196 tables and 231 functions".

Consequences for this audit:

- The registry answers **"may `rk2_runtime` execute this"**. It does not, and
  was never meant to, answer "does anything call it". A verb registered and
  never called is invisible to it by construction.
- The only hand-written narrowings are the six proxy verbs deleted at `:256-275`
  and the later per-migration `INSERT`s at
  `20260912T000000Z__an_out_of_band_host_is_bound_not_declared.sql:1018`,
  `20260913T000000Z__recovery_ends_what_the_crash_left_open.sql:459`,
  `20260914T000000Z__a_fixture_is_reached_by_address_not_by_name.sql:771`,
  `20260916T000000Z__a_wave_is_counted_and_its_duplicate_refused.sql:350`,
  `20260922T030000Z__a_skill_script_is_a_program_the_harness_ships.sql:151`,
  `20260923T000000Z__the_runtime_takes_its_own_transport_measurement.sql:289-292`.
- The four objects section 2 creates are read-only to the runtime, `:197-201`.

So the question "for every registered verb, say who may call it and whether
anything does" is answered below against the real registry: the set of SQL
functions that carry an explicit `GRANT EXECUTE ... TO <role>`, cross-referenced
against every call site in `src/redkraken/*.py` and every non-definitional
reference in `src/redkraken/migrations/*.sql`.

### 3.2 The measurement

Method: parse every `CREATE [OR REPLACE] FUNCTION` in
`src/redkraken/migrations/*.sql` (509 distinct names, 81 of them `RETURNS
trigger`), every `GRANT EXECUTE ON FUNCTION ... TO <role>` (215 names) and every
`REVOKE ... FROM PUBLIC` (267 names); then resolve reachability from three kinds
of root — a call in `src/redkraken/*.py`, a `CREATE TRIGGER ... EXECUTE FUNCTION`,
and a `standing_checks.query` string — propagating through the SQL call graph.

Table A — the granted surface by who calls it:

| Caller class | Count | Meaning |
|---|---|---|
| Called from `src/redkraken/*.py` | 76 | a Python entry point reaches it |
| Called only from another SQL function / trigger / standing check | 128 | reachable, but never named by Python |
| Called only from `tests/` | 8 | **implemented, granted, exercised only by the test suite** |
| Called by nothing at all | 3 | **dead on arrival** |

The automated pass put `state_severity` in the second row (128) because comments
in the corpus name it five times; hand-verification of every reference moved it
to the orphan list, which is why Table B has twelve entries and the automated
rows sum to eleven. Every candidate in Table B was verified this way.

Table B — the twelve granted verbs with no production caller. Every one of them
is a complete engagement action, not a helper.

| Verb | Granted to | Defined at | What it does | Anything call it? | Verdict |
|---|---|---|---|---|---|
| `open_finding(uuid, uuid, text, text, uuid)` | `rk2_runtime` (`20260815T120000Z:917`) | `20260815T120000Z__a_supported_claim_becomes_a_candidate.sql:758` | Turns a supported Hypothesis into a Finding candidate. **It contains the only `INSERT INTO findings` in the corpus** (`:839`) | No. Zero hits in `src/redkraken/*.py`; every other mention in the migrations (`:258`, `:666`, `:909`, `:1010`, `:1039`, `:1084`) is a comment, a `COMMENT ON`, a grant or a check that asserts a property of the function | **Accidental. The worst finding in this sweep.** No running code path can create a Finding |
| `open_impact_task(uuid, jsonb, uuid)` | `rk2_runtime` (`20260816T000000Z:2033`) | `20260816T000000Z__impact_is_authorized_before_it_is_proved.sql:1209` | Turns a validated Finding into impact work: one immutable Test and one Task | No | Accidental |
| `build_kill_chain(uuid[], jsonb, uuid)` | `rk2_runtime` (`20260818T000000Z:924`) | `20260818T000000Z__a_chain_is_composed_and_stays_sound.sql:538` | Composes a kill chain from member Findings and keeps it sound | No | Accidental. No chain can ever be built, yet `reporting.py` ships a `read_chain_report($1)` reader and `rk report chain` (`cli.py:1517`) is a live verb |
| `read_kill_chain(uuid)` | `rk2_runtime`, `rk2_human` (`20260818T000000Z:925`) | `20260818T000000Z__a_chain_is_composed_and_stays_sound.sql:797` | Reads one composed chain back | No | Accidental (follows the above) |
| `issue_pivot_stamp(uuid, uuid)` | `rk2_runtime` (`20260817T000000Z:1121`) | `20260817T000000Z__a_pivot_is_stamped_from_the_run_that_showed_it.sql:931` | Stamps a pivot from the Tool run that demonstrated it | No | Accidental |
| `apply_computed_cvss(uuid)` | `rk2_runtime` (`20260816T000000Z:2037`) | `20260816T000000Z__impact_is_authorized_before_it_is_proved.sql:1851` | Recomputes a Finding's CVSS from its vector | No | **Deliberate and documented.** `20260819T000000Z__a_chain_unlock_earns_its_place_in_the_queue.sql:440-443`: "038 dropped `apply_computed_severity` and left `apply_computed_cvss` behind it, and nothing in this corpus calls that function: `findings.cvss_vector` is NULL on every Finding this harness has ever produced." Known dead, not removed |
| `find_in_database(text)` | `rk2_runtime` (`20260810T173000Z:221`) | `20260814T020000Z__the_operator_answers_and_the_work_resumes.sql:759` (first at `20260810T173000Z__sealed_wire_artifacts.sql:184`) | Searches every text column for a needle — the leak hunt | No production caller; only `tests/test_database.py:7308` | Accidental. A leak-detection verb nothing runs |
| `evidence_profile_allowed_receipt_only(uuid)` | `rk2_runtime`, `rk2_human` (`20260822T000000Z:461`) | `20260822T000000Z__a_skill_teaches_what_the_role_may_already_do.sql:52` | Says whether one run's evidence is receipt-only | Nothing anywhere. Not even a test | **Dead on arrival** |
| `evidence_profile_identity_differential(uuid)` | `rk2_runtime`, `rk2_human` (`:463`) | `20260822T000000Z:69` | Identity-differential evidence profile | Nothing anywhere | **Dead on arrival** |
| `evidence_profile_successful_tool_run(uuid)` | `rk2_runtime`, `rk2_human` (`:464`) | `20260822T000000Z:101` | Successful-tool-run evidence profile | Nothing anywhere | **Dead on arrival** |
| `evidence_profile_browser_run_evidence(uuid)` | `rk2_runtime`, `rk2_human` (`:462`) | `20260822T000000Z:86` | Browser-run evidence profile | Only `tests/test_database.py:1772` | Accidental |
| `state_severity(uuid, text, text, text)` | `rk2_runtime`, `rk2_human` (`20260816T000000Z:2036`) | `20260816T000000Z__impact_is_authorized_before_it_is_proved.sql:1725` | **The verb that sets a Finding's severity band**, recording the basis and the reason (`20260816T000000Z:1809`) | No. Zero Python hits; every migration mention (`:1830`, `:1848`, `:1865`, `:1869`, `:2177`) is a comment or a check | Accidental. Ticket 38 claims it is "called by the CLI" — see §3.4 |

Four unreachable functions carry **no** grant at all — owner-only, so nobody but
`rk2_owner` could call them even if something wanted to:

| Verb | Defined at | Status |
|---|---|---|
| `resolve_egress_token(...)` | `0022_hooks_and_receipts.sql:322` | Superseded by `resolve_egress_capability`. Six surviving references are all comments repeating "the proxy refuses it (resolve_egress_token requires 'running')", e.g. `0022_hooks_and_receipts.sql:471`, `20260815T000000Z:2251` — the comments describe a function the code no longer calls |
| `compose_finding_report(...)` | `20260820T000000Z__a_report_is_a_projection_of_what_holds.sql:461` | `reporting.py` calls `read_finding_report($1)`, not this. One surviving reference, a comment at `20260820T000000Z:980` |
| `eval_comparable`, `eval_family_coverage_of` | `0033_eval_store.sql:307`, `:286` | Zero references anywhere |
| `mcp_enum_described` | `0018_vocabularies.sql:546` | Zero references anywhere |

### 3.3 What is reachable, correctly

For completeness, the verbs the harness does reach, so the negative result above
is read against a positive one. `park_for_human(uuid, interval)` is granted to
`rk2_runtime` at `0038_receipt_capabilities.sql:261` and **is** called, from
`proxy.py:3552` (`PARK_TOOL_RUN = "SELECT park_for_human($1::uuid)"`). Its
inner definer half, `park_authorized_tool_run(uuid, interval)`
(`20260814T020000Z__the_operator_answers_and_the_work_resumes.sql:226`), is revoked from `rk2_runtime` at
`0038_receipt_capabilities.sql:247` and reached only through the wrapper at
`0038_receipt_capabilities.sql:257` — correct, and the pattern the twelve above
do not follow.

Note the asymmetry this creates: the **door** can park a Tool run for a human
(`proxy.py:3552`), but the **agent** cannot ask to be parked, because
`mcp__rk2__park_for_human` has no handler (§1.3). The human-decision loop is
reachable from the network side and not from the model side.

### 3.4 Deliberate versus accidental, from the tickets

Four of the twelve orphans in Table B are **documented as unserved on purpose**,
each deferring to the same unbuilt ticket:

- `docs/specs/production-harness-v2/issues/38-authorize-and-prove-impact-separately.md`:
  "**No verb is served to a model.** `open_impact_task`, `open_impact_replay` and
  `state_severity` are called by the CLI and by the tests. Which Finding is worth
  proving impact on is the orchestrator's decision, and the tool it makes that
  decision through belongs to the orchestrator dispatch ticket."
- `docs/specs/production-harness-v2/issues/39-stamp-demonstrated-pivot.md`:
  "**No verb is served to a model, and there is no CLI.** `issue_pivot_stamp` is
  called by the tests."
- `docs/specs/production-harness-v2/issues/40-build-and-evaluate-sound-kill-chain.md`:
  "**No verb is served to a model, and there is no CLI.** `build_kill_chain` and
  `read_kill_chain` are called by the tests."
- `docs/specs/production-harness-v2/issues/37-validate-finding-blindly.md:94-97`:
  "**`mcp__rk2__request_validation` is not served to anybody.** The verb exists
  and the CLI calls it [...] the tool it makes that step through belongs to the
  orchestrator dispatch ticket."

All four issues carry `**Status:** resolved`. So the pattern is not "somebody
forgot"; it is "four tickets each deferred the wiring to a fifth ticket that has
not landed", and each was then closed. That fifth ticket is the single missing
piece behind most of Table B.

**Ticket 38's factual claim is wrong.** `open_impact_task` and `state_severity`
are *not* called by the CLI: zero hits in `src/redkraken/*.py` for either. Only
`open_impact_replay` is, at `src/redkraken/replay.py:96`. A closed ticket
asserting a caller that does not exist is how a gap survives review.

**`open_finding` has no such note.** `docs/specs/production-harness-v2/issues/36-create-candidate-finding.md`
is `**Status:** resolved` and its "What is not covered" section (severity above
`info`, `duplicate_of_finding_id`) says nothing about a caller. This is the
purely accidental one, and it is the root: no Finding is ever created, so the
subjects of tickets 37 through 42 — validation packets, verdicts, impact tasks,
pivot stamps, kill chains, reports, evidence bundles — have nothing to operate
on. The declared surface `validate.judge` (`roster.py:823`, `:826`) can never be
exercised for want of an `F`-labelled row.

Every `check_*` function reported as unreachable by a naive call-graph walk is in
fact reached through its `standing_checks.query` row — e.g. `check_test_replays`
at `20260815T000000Z:2091` (`'SELECT * FROM check_test_replays()'`),
`check_evidence_export` at `20260821T000000Z:599`. Those are **not** defects and
are excluded from Table B.

---

## 4. Contract arguments that go nowhere

Every argument of every Contract, traced to the line that reads it.

| Contract.argument | Read at | Acted on at | Verdict |
|---|---|---|---|
| `get_attack_surface.entity_type` | `packet.py:837` | filter predicate, `packet.py:837` | consumed |
| `get_attack_surface.limit` | `packet.py:836` | `packet.Reader._page`, `packet.py:961-962` | consumed |
| `get_hypotheses.subject_label` | `packet.py:846` | `packet.py:846-847` | consumed |
| `get_hypotheses.status` | `packet.py:848` | `packet.py:848` | consumed |
| `get_hypotheses.limit` | `packet.py:853` | `packet.py:961-962` | consumed |
| `get_evidence.hypothesis_label` | `packet.py:862` | `packet.py:863` | consumed |
| `get_evidence.finding_label` | `packet.py:865` | `packet.py:866` | consumed |
| `get_evidence.limit` | `packet.py:870` | `packet.py:961-962` | consumed |
| `get_receipts.receipt_labels` | `packet.py:898` | `packet.py:899-907` incl. `not_staged` marker | consumed |
| `get_receipts.limit` | `packet.py:896` | `packet.py:961-962` | consumed |
| `get_artifact.artifact_label` | `packet.py:911` | `packet.py:933` | consumed |
| `get_artifact.range` | renamed to `span` at `_launch.py:594-595` | `packet.py:950` `_window(row, excerpt, span)` | consumed |
| `submit_mission_result.observations` | `_launch.py:213` | `proposal.py:176` (`result.elements("observations")`) | consumed |
| `submit_mission_result.new_entities` | `_launch.py:213` | `proposal.Result.elements`, `proposal.py` | consumed |
| `submit_mission_result.relationships` | `_launch.py:213` | ditto | consumed |
| `submit_mission_result.hypotheses` | `_launch.py:213` | ditto | consumed |
| `submit_mission_result.evidence` | `_launch.py:213` | ditto | consumed |
| `submit_mission_result.suggested_tasks` | `_launch.py:213` | ditto | consumed |
| `submit_mission_result.completion_claim` | `_launch.py:213` | `proposal.Result.completion`, `proposal.py:95-104`, written to `proposals.completion` at `proposal.py:364` | consumed |
| `pick_task.task_label` | `_launch.py:251` | `_launch.py:258`, `_launch.py:1122` | consumed |
| `http_request.method` | `_launch.py:631` | `proxy._through`, `proxy.py:3967` / `:3986` | consumed |
| `http_request.url` | `_launch.py:630` | `proxy.py:3967` / `:3986` | consumed |
| `http_request.headers` | `_launch.py:632`, cast at `_launch.py:768` | `proxy._carried`, `proxy.py:3994`, merged onto the wire at `proxy.py:3967` / `:3986` | consumed |
| `run_tool.tool` | `agent.py:1204` | `tool.serve(offline_tool=...)`, `tool.py:451` | consumed |
| `run_tool.arguments` | `agent.py:1219` | `tool.py:475` (into `open_offline_tool_run`) | consumed |
| `run_skill_script.skill_name` | `agent.py:1208` | `tool.script`, `tool.py:551` | consumed |
| `run_skill_script.script` | `agent.py:1209` | `tool.script`, `tool.py:551` | consumed |
| `run_skill_script.arguments` | `agent.py:1219` | `tool.py:475` | consumed |
| `get_validation_packet.finding_label` | `_launch.py:320` | `_launch.py:322-324` | consumed |
| `submit_verdict.finding_label` | `_launch.py:333` | `_launch.py:333`, `_launch.py:340` | consumed |
| `submit_verdict.verdict` | `_launch.py:341` | `validation.py`, then `record_verdict` at `20260815T180000Z:1548` | consumed |
| `submit_verdict.failed_assertion_ids` | `_launch.py:338` | `validation.py:365`, then `verdicts.failed_assertion_ids` (`0020_state_access.sql:129`), asserted at `20260815T180000Z:1291` | consumed |
| `request_validation.finding_label` | **nowhere** | **nowhere** | **the tool has no handler (§1.3)** |
| `park_for_human.task_label` | **nowhere** | **nowhere** | **no handler** |
| `park_for_human.question_code` | **nowhere** | **nowhere** | **no handler** |
| `park_for_human.question` | **nowhere** | **nowhere** | **no handler**, and it is one of only two entries in `OPEN_ARGUMENTS` (`roster.py:555`) — an argument granted an exemption from the constraint rule for a tool that does not exist |

**Result: 32 of 36 arguments are consumed end to end. The four that are not all
belong to the three unserved Contracts.** Within the served thirteen there is no
argument the runtime accepts and drops. The roster's own rule
(`roster.py:771-774`) is being kept for arguments and broken for tools:

> "A declared argument the runtime drops is a promise the schema cannot keep,
> and the honest form of 'not yet' is not to declare it."

### 4.1 The inverse defect: an argument set that cannot express what its enum promises

`mcp__rk2__http_request` declares `method` with
`enum=("GET","POST","PUT","PATCH","DELETE","HEAD","OPTIONS")` at
`roster.py:752-756` and declares **no body argument**, deliberately, with the
reason at `roster.py:766-774`:

> "No body and no identity. Both were declared here and neither was ever
> reachable: the child has no store, so it cannot name a body the door could
> send [...]"

But `proxy._through` sends no body on either branch — `proxy.py:3967`
(`client.request(method.upper(), url, headers={**carried, **control})`) and
`proxy.py:3986` — so `POST`, `PUT` and `PATCH` are four enum members that always
put an empty body on the wire. The enum promises a class of request the argument
set cannot compose. The comment explains the missing body; **nothing explains
why the enum still admits the methods that need one**. Accidental — now covered
by `docs/specs/production-harness-v2/issues/96-carry-a-request-body.md`, which
declares `body` as a bounded string and is why ticket 95 (`maxLength`) had to
land first.

---

## 5. Results that lose information

What the runtime held at the moment it answered, versus the shape the agent got.

### 5.1 `http_request` — every response header (the known case, with its real origin)

The door builds the agent-visible response header list and puts **all of it** on
the wire:

- `proxy.response_for_agent`, `proxy.py:645`, strips target-issued auth material
  and returns the rest.
- `proxy.project_identity_response`, `proxy.py:659`, redacts reflected secrets
  from names and values.
- `RequestHandler._answer`, `proxy.py:3244-3270`, writes every surviving header
  out: `for name, value in headers or []: ... self.send_header(name, value)`
  (`:3258-3260`), called with `headers=agent_back` at `proxy.py:3128`.

The client then throws them away. `proxy._answered`, `proxy.py:3595-3603`, reads
exactly five fields off an `HTTPResponse` that holds every header:

```
return Answer(
    status=answer.status,
    body=answer.read(CEILING + 1),
    receipt=answer.headers.get(RECEIPT),
    decision=answer.headers.get(DECISION),
    detail=answer.headers.get(DETAIL),
)
```

`Answer`, `proxy.py:3577-3592`, has no header field at all. `_launch._spend`,
`_launch.py:726-735`, then returns eight keys, none of them a header.

Net effect on an engagement: an agent doing web security testing never sees
`Location`, `Set-Cookie`, `Content-Type`, `WWW-Authenticate`, `Access-Control-Allow-Origin`,
`X-Frame-Options`, `Strict-Transport-Security`, `Server`, or any cache header.
Redirect chains, cookie flags, CORS policy and every security-header finding are
invisible to the model even though the harness measured them and sealed them.

The loss is **two layers deep**: fixing `_launch._spend` alone is not enough,
because `proxy.Answer` never carried them. Nothing in either file says why.
Accidental — and **now ticketed and in flight**:
`docs/specs/production-harness-v2/issues/94-hand-the-response-headers-to-the-caller.md`
("The bytes are already in this process and already hashed; what is missing is
the one statement that hands them over"), whose implementation is uncommitted in
the working tree and adds `headers: tuple[tuple[str, str], ...]` to `Answer` and
fills it in `_answered` from every name `describes_this_hop` does not claim.

The same `_answered` is on the operator path — `proxy.send`, `proxy.py:3936`,
reached from `cli.py:3016` — so `rk proxy request` loses them too.

### 5.2 `http_request` — the artifact labels for the exchange it just filed

`CONTRACTS["mcp__rk2__http_request"]` declares
`writes=("receipts", "artifacts", "artifact_refs")`, `roster.py:750`. The door
does write them: `register_proxy_artifacts(...)`,
`0040_receipt_contract.sql:13-36`, inserts four rows (request agent view, request
wire view, response agent view, response wire view). The result hands back
**only** `receipt` (`_launch.py:730`). No artifact label crosses back.

Consequence: `net.request` and `exec.tool_run` are designed to compose — `jq`,
`js_parse`, `js_map`, `js_routes` and both skill scripts all take an
`artifact`-kind argument (`20260814T030000Z:179`,
`20260922T030000Z:464-470`) — and an agent that has just fetched a JavaScript
bundle has no label to hand to `js_parse`. The composition the two tool groups
exist to support cannot be performed in one run. Nothing says why. Accidental.

### 5.3 `run_tool` / `run_skill_script` — stderr, and every artifact the run produced

`tool._streams`, `tool.py:790-806`, files **both** streams, deliberately:

> "Stdout and stderr are always kept, empty or not. An empty stream is a fact
> about the run" (`tool.py:793-794`)

`tool.serve`, `tool.py:521-537`, returns `stdout` (head, `excerpt` bytes) and an
`outputs` list carrying only `("stream", "output_name", "kind", "label",
"byte_size")` per item. **The stderr bytes are never returned in any form.** The
agent is handed a label for them and, per §5.4, cannot resolve it. A tool that
failed tells the model its exit code and its (possibly empty) stdout, and hides
the diagnostic it wrote.

### 5.4 The structural loss: every label minted after launch is unresolvable

`packet.compile`, `packet.py:587`, is run once, before the container starts
(`roster.py:594-599`: "The child has no database: `packet.compile` runs these on
the supervisor's `rk2_state` connection before the container starts"). The child
reads that document at `_launch.py:1017` and every `state.read` handler answers
out of it (`_launch.py:581-597`).

So for any label the runtime mints **during** the run:

| Label handed to the agent | Handed at | Read verb that should resolve it | What it returns |
|---|---|---|---|
| `receipt` from an HTTP exchange | `_launch.py:730` | `get_receipts` | `{"reason": "not_staged", ...}`, `packet.py:907` — the Receipt was written after the packet was compiled |
| `tool_run` label | `tool.py:527` | none — no Contract reads `tool_runs` | nothing |
| stdout/stderr/declared-output artifact labels | `tool.py:531-534` | `get_artifact` | `{"reason": "no_such_artifact", ...}`, `packet.py:950` |

This is one defect, not three: the agent's read surface is a snapshot and the
agent's act surface mints new rows into a database the read surface cannot see.
Every observation the runtime asks a model to ground on a Receipt
(`packet.py:879-883` describes exactly this dependency) is grounded on a label
the model was told about and cannot read back.

`packet.py:621-623` acknowledges half of the problem for a different reason —

> "An Artifact whose bytes were not staged is still an Artifact the child knows
> about and can hand to `exec.tool_run`"

— which is true for artifacts that were in the packet's row set. It is not true
for artifacts created after compile: those are in no section at all.

Nothing states this as a decision. Accidental.

### 5.5 `http_request` — the scope classification and the identity

The door resolves the request's scope class and writes it on the Receipt; it is
the value `browser.py:454` later reads back out of Receipts to fill
`browser_step_results.scope_class`, and the driver is forbidden from computing
its own (`browser_driver.py:525-528`: "`scope_class` is not here on purpose.
What class a URL belongs to is the door's answer"). The agent's `http_request`
result carries no scope class, so a model cannot tell an in-scope 404 from an
out-of-scope one without a second read it cannot make (§5.4). Similarly the
Identity the exchange was made as — chosen by the runtime, per
`roster.py:766-771` — is never named in the answer, so an identity-differential
test cannot tell the model which of two runs was which.

### 5.6 What does **not** lose information

For contrast, and so the list above is read as specific rather than general:

- `Judgement.read`, `_launch.py:318-325`, hands the validation packet over whole
  (`"packet": self.packet`) — no narrowing.
- The bounded reads report what they dropped and why:
  `{"reason": "packet_bound", "count": ...}` and `{"reason": "limit", "count": ...}`,
  `packet.py:964-969`.
- `_spend` reports `byte_size` and `truncated` beside the excerpt,
  `_launch.py:733-734`, so a truncated body is legible as truncated.
- Gate denials reach the model as a reason string, `_launch.py:900-902`.
- `Submission.submit`, `Choice.pick` and `Judgement.judge` each return an
  explicit note that the runtime step has not happened yet
  (`_launch.py:216-218`, `:170-172`, `:249-252`) rather than overclaiming.

---

## 6. CLI-only capabilities

The CLI is `rk` (`pyproject.toml:30`), rooted at `cli.py:156`, dispatched by
argparse subparsers with `set_defaults(run=...)` on each leaf and invoked at
`cli.py:1981-1983`. **50 leaf verbs across 24 top-level commands.** No verb is
hidden (`argparse.SUPPRESS` appears zero times), no handler is orphaned and no
registration lacks a handler.

Eight verbs have an agent-reachable equivalent. Forty-two do not. The table
below covers every verb that is a **capability an engagement would want**, i.e.
excluding pure database/administration verbs, which are listed at the end.

| Capability | Lives at | Reachable by agent? | Reachable by operator? | Deliberate? |
|---|---|---|---|---|
| `rk browser run` — a full browser mission behind the door | `cli.py:1139` → `_browser_run` `cli.py:2629` → `browser.run` `browser.py:129` | **No** | Yes | **Accidental.** See §2.1 — a shipped Skill instructs the agent to start it through `mcp__rk2__run_tool`, whose enum cannot name it |
| `rk oob serve` — publish a Program's payload directory and record every arrival | `cli.py:738` → `oob.serve` `oob.py:604` | **No** | Yes | Accidental (no statement) |
| `rk oob up` — bind a public name via a tunnel | `cli.py:781` → `oob.up` `oob.py:716` | **No** | Yes | Partly deliberate: `oob.py:30-33` says the tunnel is not supervised on purpose; nothing says an agent may not ask for one |
| `rk oob status` — **the only way to learn the channel's live hostname** | `cli.py:830` → `oob.status` `oob.py:844` | **No** | Yes | **Deliberate**, `oob.py:850-854`: "The only supported way to learn the name. Nothing in a configuration file holds it, no agent composes it" |
| `rk oob down` | `cli.py:856` → `oob.down` `oob.py:896` | **No** | Yes | **Deliberate**, `cli.py:863`: "The tunnel process is the operator's to stop." |
| `rk callback provision` — mint a canary correlator and print its address | `cli.py:571` → `callback.provision` `callback.py:92` | **No** | Yes | Accidental (no statement) |
| `rk callback accept` — admit one recorded arrival | `cli.py:633` → `callback.accept` `callback.py:234` | **No** | Yes | Accidental |
| `rk callback clear` — end a correlator and report what it caught | `cli.py:700` → `callback.clear` `callback.py:453` | **No** | Yes | Accidental. This count (`callback.py:507`) is the only read of what a canary caught anywhere in `src/` |
| `rk test replay` — run a Test through the replay lane | `cli.py:1208` → `replay.run` | **No** | Yes | Plausibly deliberate (replay is the runtime's proof lane) but **no comment says so** |
| `rk finding validate` | `cli.py:1278` → `validation.run` | Partly — `validate.judge` gives a validator the packet and the verdict, but the *runtime* step is here | Yes | Deliberate by design (ADR 0003, runtime commits) |
| `rk report finding` / `rk report chain` | `cli.py:1497` / `:1517` → `_report` `cli.py:2746` → `reporting.run` | **No** — `mcp__rk2__request_report` exists as a Contract but is unserved (§1.3) | Yes | **Unfinished**, `agent.py:143-146` |
| `rk evidence export` — the bundle that leaves | `cli.py:1531` → `evidence.export` | **No** | Yes | Accidental (no statement) |
| `rk evidence verify` | `cli.py:1588` → `evidence.verify` | **No** | Yes | Accidental |
| `rk artifact put/get/audit/seal/open` | `cli.py:887/925/972/990/1032` | Partly — `get_artifact` reads the packet only (§5.4) | Yes | The narrowing is deliberate (`roster.py:649-656`, by label not hash); the snapshot problem is not stated |
| `rk tool run` | `cli.py:1083` → `tool.run` `tool.py:178` | **Yes** — `mcp__rk2__run_tool` | Yes | Correctly paired |
| `rk proxy request` | `cli.py:1733` → `proxy.send` `proxy.py:3936` | **Yes** — `mcp__rk2__http_request` → `proxy.spend` `proxy.py:3897` | Yes | Correctly paired; `proxy.py:3908-3915` explains the split |
| `rk identity provision` | `cli.py:489` → `identity.provision` | **No** | Yes | **Deliberate**, `roster.py:766-771`: the runtime chooses the Identity before the run opens |
| `rk header provision` | `cli.py:528` → `header.provision` | **No** | Yes | Deliberate, same reasoning (`program_required_headers` is the door's) |
| `rk decision list / answer / supersede` | `cli.py:1806/1823/1863` → `operator.queue/answer/supersede` | **No** | Yes, as `rk2_human` | **Deliberate**, `cli.py:66-69`: "It is the only role that may answer a question or lift a Halt, and it is deliberately not reachable from `RK_DATABASE_URL`: a control verb the runtime could execute is a control verb a model's tool call can reach through the runtime." |
| `rk halt` / `rk resume` | `cli.py:1878` / `:1889` → `operator.halt/resume` | **No** | Yes, `rk2_human` | Deliberate, same quote |
| `rk finding report` | `cli.py:1327` → `operator.report_finding` | **No** | Yes, `rk2_human` | **Deliberate**, `cli.py:1331-1332`: "The last step, and the only one no part of the runtime may take: `validated -> reported` is reserved for a human actor." |
| `rk finding clear-gate` | `cli.py:1378` → `operator.clear_gate` | **No** | Yes, `rk2_human` | Deliberate, `cli.py:1386-1387` |
| `rk decision sweep` | `cli.py:1787` → `decisions.sweep` | **No** | Yes | Deliberate (expiry is the runtime's clock) |
| `rk playbook evaluate` / `cost` | `cli.py:1425` / `:1481` → `evaluation.evaluate/cost` | **No** | Yes | **Deliberate**, `20260922T000000Z__the_agent_connection_cannot_read_the_playbook_catalogue.sql:34-36` removes the whole playbook catalogue from the agent read surface |
| `rk scope` | `cli.py:240` → `scope.diagnose` | **No** | Yes | Deliberate (scope is policy the door enforces) |
| `rk state` | `cli.py:313` → `state.read` | Partly — the five `state.read` tools cover part of it | Yes | Deliberate |
| `rk ui serve/read/forms` | `cli.py:368/426/467` → `ui.serve` / `panels.read` / `panels.forms` | **No** | Yes | Deliberate (operator console) |
| `rk run` — start a Program | `cli.py:200` → `program.run` | **No** | Yes | Deliberate (the runtime owns the lifecycle; `roster.py:885-890` forbids `TaskCreate`/`TaskUpdate` for the same reason) |
| `rk import` | `cli.py:1605` → `legacy.run` | **No** | Yes | Deliberate |
| `rk proxy serve` / `rk proxy door` | `cli.py:1658` / `:1704` | **No** | Yes | Deliberate (infrastructure) |
| `rk doctor`, `rk version`, `rk db provision/migrate/verify/status/dump/restore` | `cli.py:176`, `:163`, `:1906-1964` | **No** | Yes | Deliberate (administration) |

Two incidental CLI defects found while enumerating, both outside this axis but
recorded so they are not lost:

- `cli.py:3296` — `_key` is annotated `-> seal.Location | None` but `seal` is
  never imported (`cli.py:18-45`). Survives only because of
  `from __future__ import annotations` at `cli.py:9`.
- `cli.py:1840` — `--deny` is registered in a required mutually-exclusive group
  but `_decision_answer` (`cli.py:3084`) reads only `arguments.approve`
  (`cli.py:3091`). Behaviour is correct; the flag is write-only.

---
## What a gate would have to assert

Each check below is stated so it can be written as a test or a standing check,
names the finding class it would have caught, and says where it belongs. They
are ordered by how much of this document each one closes.

### G1. Every Contract is served, and every served tool exists

```
set(agent.SERVED) == {name for each tool _launch.server() builds}
set(roster.CONTRACTS) - set(agent.SERVED) == set(DECLARED_UNSERVED)
```

`DECLARED_UNSERVED` must be an explicit dict of `name -> reason`, in the shape
of `roster.FORBIDDEN_BUILTINS` (`roster.py:875-899`) — which already proves the
pattern works: every built-in a role does not hold states why, and the compile
refuses an unclassified one (`roster.py:1518`).

Catches: §1.3, §2.7 — three Contracts with no handler.
Belongs in: `roster._compile`, `roster.py:1821`, or `agent._check_served_members`,
`agent.py:164`. `_launch.server` must expose the names it builds; today it
returns an opaque SDK server object and nothing can ask.

Why the existing checks miss it: `_check_contracts` (`roster.py:1728`) checks
shape, group and direction and never asks whether a handler exists;
`_check_served_members` (`agent.py:164`) checks group membership of the served
list and never compares it to what `_launch.server` builds.

### G2. Every declared argument is read by the code that fulfils the tool

For each `Contract.arguments` key, assert a reader exists on the path from the
handler to the runtime — mechanically, by asserting the handler's fulfilment
function accepts the name, or by a recorded trace test that calls each tool with
each optional argument set to a distinguishable value and asserts it changes the
answer or the row.

Catches: §4 (nothing today, which is the point — it would make §4's result a
standing guarantee rather than a one-off audit), and §4.1's inverse if extended
to "every enum member is expressible": assert that for each `method` enum member
requiring a body, a body argument exists.

Belongs in: `tests/`, driven off `roster.CONTRACTS` so a new argument is covered
the day it is declared.

### G3. Every registered runtime verb has a caller

```
for verb in {SQL functions with an explicit GRANT EXECUTE TO a role}:
    assert reachable_from(verb, roots = python_call_sites
                                  | trigger_bindings
                                  | standing_checks_queries)
       or verb in DECLARED_UNCALLED   # name -> ticket that will call it
```

Reachability must propagate through the SQL call graph, and the roots must
include `standing_checks.query` strings and `CREATE TRIGGER ... EXECUTE FUNCTION`
— otherwise every `check_*` is a false positive (§3.3).

Catches: §3.2's twelve verbs, including `open_finding` — the single worst
finding here. It would also have caught ticket 38's false claim that
`open_impact_task` and `state_severity` "are called by the CLI" (§3.4), because
the assertion is measured, not asserted in prose.

Belongs in: `src/redkraken/integrity.py`, which already owns exactly this idea
for SQL checkers (`integrity.py:4-8`: "The defect that registry exists to
prevent is a checker with no caller"). The registry it needs is a
`runtime_verb_callers` table beside `runtime_verb_surface`
(`20260909T000000Z:103`): one row per granted verb naming its caller, or naming
the ticket that owes one. Note that `runtime_verb_surface` **cannot** be that
registry — it is catalogue-seeded (`20260909T000000Z:169-173`) and answers "may
execute", not "does execute".

### G4. Every table the agent role may read is read by some tool, or declared unread

```
live(state_read_surface.table_name)
  == {relations named in some Contract.reads}
   | DECLARED_UNREAD          # table -> why no tool reads it
```

Catches: §2.4's twenty-one relations, and therefore the browser evidence tables,
`negative_knowledge`, `relationships` and the tool-run link tables.

Belongs in: a standing check, since both sides are database state
(`state_read_surface` and a materialised copy of `Contract.reads`). The precedent
is `check_role_catalogue` / `base_role_catalogue`, `0040_receipt_contract.sql:193`.

### G5. Every element list a proposal accepts has a read verb that returns it

```
for element in CONTRACTS["mcp__rk2__submit_mission_result"].arguments:
    assert some Contract reads the canonical table that element promotes into
```

Catches: §2.4's `relationships` case — proposable, unreadable. This is a
narrower, cheaper version of G4 that needs no database.

### G6. A result names no handle its read verbs cannot resolve

For every key in a tool result that is a label (`receipt`, `tool_run`,
`outputs[].label`, and any artifact label), assert the read verb for that label
class can resolve it **in the same run**.

Catches: §5.4 in full — the `not_staged` Receipt, the `no_such_artifact` tool
output, the `tool_run` label with no reader at all.

Implementation shape: an integration test that runs one child through
`http_request`, then `get_receipts` with the returned label, and asserts
`counts.matched == 1`; and one that runs `run_tool`, then `get_artifact` on each
returned `outputs[].label`. Both fail today.

This is the check that forces the design question the audit exposes: either the
packet gains a refresh path, or the act tools stop returning labels the read
tools cannot honour. Either answer satisfies the gate; silence does not.

### G7. A result is not narrower than the value it was built from

For each boundary where a rich runtime value becomes a model-facing dict, assert
field coverage explicitly:

- `proxy._answered` (`proxy.py:3595`) against `http.client.HTTPResponse`: every
  header the door sent is either carried on `Answer` or named in a
  `DROPPED_HEADERS` constant with a reason.
- `_launch._spend` (`_launch.py:726-735`) against `proxy.Answer`: every field
  carried or declared dropped.
- `tool.serve` (`tool.py:521-537`) against `isolation.ToolProcess`: `stderr` is
  either returned or its absence is declared.

Catches: §5.1 (response headers — the known case, and note the gate must be at
`proxy._answered`, not at `_launch._spend`, because `Answer` never carried them),
§5.2 (artifact labels), §5.3 (stderr), §5.5 (scope class, identity).

Belongs in: a test parameterised over a hand-written
`{boundary -> (source fields, carried fields, declared drops)}` table, so adding
a field to `Answer` without deciding about it fails.

### G8. Skill text names only tools that exist and arguments that are expressible

```
for skill in skills.SKILLS:
    for tool_name in tool names mentioned in the skill body:
        assert tool_name in roster.CONTRACTS
    for value in values the skill tells the model to pass:
        assert value satisfies the argument's schema
```

`roster._check_skills` (`roster.py:1588`) already does the first half for the
frontmatter — `allowed-tools` and `bb:runtime-tools` are checked against
`TOOL_GROUPS` and `RUN_TOOL_NAMES` (`roster.py:1620`, `:1631`). It does not read
the **body**, which is where `skills/browser-evidence/SKILL.md:63` tells the
model to start a browser mission through `mcp__rk2__run_tool` (§2.1).

Catches: §2.1's contradiction, which is the one place the harness actively
instructs an agent to do something impossible.

### G9. Every closed ticket's "no caller" claim is measured, not asserted

A ticket whose "What is not covered" section says a verb is "called by the CLI"
must be checked against the code at the moment it is marked resolved.

Catches: §3.4 — ticket 38 claims two callers that do not exist, and that claim is
why the gap survived review. Cheapest form: a test that parses each
`docs/specs/*/issues/*.md` for backticked identifiers in sentences containing
"called by the CLI" / "called by the tests" and asserts the claim.

### G10. A migration that creates a granted verb declares who will call it

The narrowest and most preventive of the ten: extend the pattern
`20260909T000000Z` already established for privileges to callers. A `GRANT
EXECUTE ON FUNCTION x TO rk2_runtime` with no accompanying `runtime_verb_callers`
row fails the migration, exactly as an object arriving with an undeclared runtime
grant fails today (`20260909T000000Z:175-192`, arm 4 of
`check_runtime_privileges()`).

Catches: every future instance of §3.2 at the moment it is written, rather than
in an audit like this one.

---

## Appendix: how the numbers in this document were measured

- Contracts and their arguments: read directly from `roster.py:601-854`.
- Served tools: `_launch.server`, `_launch.py:530-578`, cross-checked against
  `DESCRIPTIONS`, `_launch.py:428` (13 keys, 13 tools built).
- SQL inventory: every `CREATE [OR REPLACE] FUNCTION` in
  `src/redkraken/migrations/*.sql` — 509 distinct names, 81 `RETURNS trigger`.
- Grants: every `GRANT EXECUTE ON FUNCTION ... TO <role>` — 215 names; revocations
  from `PUBLIC` — 267 names.
- Reachability: propagated through the SQL call graph from three root classes —
  a call in `src/redkraken/*.py`, a `CREATE TRIGGER ... EXECUTE FUNCTION`
  binding, and a `standing_checks.query` string — then every candidate hand-
  verified against its non-definitional references, because comments in this
  corpus mention function names constantly and a naive grep scores them as calls.
- Agent read surface: every `INSERT INTO state_read_surface` and every
  `DELETE FROM state_read_surface` in the migrations, applied in file order.
- CLI verbs: `build_parser()` walked via `_name_parser_map`; 50 leaves confirmed.
