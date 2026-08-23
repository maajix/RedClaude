# 169 -- A Playbook step the runtime performs

**What to build:** A design, and the smallest first step that proves it. The
design says what a Playbook step is when it is a thing the runtime performs
rather than a paragraph a model reads, where the analysis half runs, and what
the analysis half is allowed to reach. The first step converts exactly one
Playbook onto it. Not fifty. Ticket 167 called this candidate "arguably a design
change rather than a feature" and it is right, so the deliverable is the design
first and one worked case behind it.

**Blocked by:** nothing. Ticket 98 is resolved and shipped
`mcp__rk2__mint_callback` into `state.propose` (`roster.py:902-907`); ticket 99
is still `ready-for-agent` and it does not block this, because the first step
here is the request step, whose performer already exists in `replay.py`, and the
browser step is the second kind rather than the first. Ticket 167 does not block
it either: the operator has accepted the idea, and this ticket is that
acceptance promoted into work.

**Status:** ready-for-agent

- [ ] **The design exists as one document and it is an ADR at `0008`.** It
      answers four questions and no others: what a step is, who performs it,
      where the analysis half runs, and what a Playbook document has to grow to
      carry one. `0007` is reserved by ticket 167. Declining any of the four
      with a reason is a result, the way `0004`, `0005` and `0006` were results.
- [ ] **No HuntProxy source and no HuntProxy text enters the tree, and the diff
      proves it.** This ticket copies a described boundary shape and nothing
      else: no Rust, no JavaScript, no QuickJS, no plugin manifest, no copied
      sentence. `grep -ril huntproxy` over the working tree returns only ticket
      files -- 167, this one, and the siblings 171 and 172 that came out of the
      same reading -- plus the ADR that cites them. Nothing under `src/`,
      `tests/` or `skills/` names it. **Precondition, stated so it is not rediscovered
      later:** HuntProxy and HuntProxy-Plugins are Apache-2.0, this repository
      ships no `LICENSE` file, and `pyproject.toml`'s `[project]` table
      (`:11-27`) declares no `license`, so there is no outbound licence for an
      inbound one to sit against. Ticket 167 section 5 records that as an open
      question. Settling this repository's own licence is a precondition for
      copying any actual source and is *not* a precondition for this ticket,
      because this ticket copies none.
- [ ] **A step is a row in a closed set a migration owns, on the precedent that
      already exists.** `browser_actions`
      (`20260814T040000Z__a_browser_mission_runs_behind_the_door.sql:150`) is
      ten rows inserted at `:186-207`, each declaring whether it reaches the
      network, whether it submits, and the outcome keys the digest is computed
      over, and its table comment says why it is a table: "Changed only by
      migration: an action the runtime could add is an action the plan could
      invent, and the plan is written by a model" (`:168-171`). A Playbook step
      vocabulary that is anything looser than that is refused by this criterion.
      `offline_tools` carries the same sentence for the same reason
      (`20260814T030000Z__an_offline_tool_becomes_evidence.sql:140-145`).
- [ ] **The first step kind is `request` and it widens the vocabulary in the one
      place that was left open for it.** `TEST_ACTION_KINDS = ("request",)`
      (`roster.py:411`) is a tuple of one word, and the comment above it
      (`:407-410`) says it is a vocabulary rather than a constant "so that the
      set widens in one place on the day an offline tool can be performed under
      a Tool run that already exists". Any second kind lands there or the design
      says why it does not.
- [ ] **Every request a step causes still goes through the door, and a refusal
      is still a Receipt.** No second egress path, no direct socket, no bypass
      for a "performed" step. `Fence.authorize` (`proxy.py:1240`),
      `authorize_address` (`:1315`) and `reserve` (`:1351`) decide before the
      connection; `allowed_receipt` (`:1425`) records the exchange and
      `blocked_receipt` (`:1744`) records the ones refused. `replay.py` already
      behaves this way and states it: a door refusal is recorded as a hold and
      leaves the run inconclusive rather than failing the command
      (`replay.py:397-406`). Measured by a test that drives a converted
      Playbook's steps and asserts one Receipt per performed action and a
      `blocked_receipt` row for one deliberately out-of-scope action.
- [ ] **No scope widening and no authority widening.** Concretely: no new
      `tool_groups` member on any existing role unless it is a narrow group held
      by exactly one role, following `state.conclude`
      (`roster.py:924-928`), whose comment is the rule to follow --
      "A GROUP OF ITS OWN AND NOT THREE MORE MEMBERS OF `state.propose`"
      (`:915-923`) -- and which only `web_hunter` holds (`:2042-2044`). Nothing
      here adds a member to `net.request` (`:943`), which is one tool
      (`mcp__rk2__http_request`) and stays one tool.
- [ ] **If the analysis half is a sandbox it has no socket, and that is a row
      rather than a promise.** The precedent is `offline_tools.network`, whose
      comment says "`none` is a container with no interface but loopback;
      `proxy` is the one-peer boundary an Agent gets ... There is no third
      value, so there is no way to spell 'the host's network'"
      (`20260814T030000Z__an_offline_tool_becomes_evidence.sql:147-151`), and
      the enforcement is `isolation.run_tool` (`isolation.py:725`), described at
      `isolation.py:18-26`. An analysis sandbox is `network = 'none'` or the
      design says which of the two existing values it is and why. **If the
      analysis half is a model instead**, it holds a Contract already in
      `CONTRACTS` (`roster.py:1184`) or one narrow new group per the criterion
      above, and it never promotes: `roster.py:933-935` is the standing rule --
      "There is no `promote` here at all: promotion is the runtime step that
      turns a raw result into canonical rows, and a model-facing verb for it
      would be the agent promoting its own conclusions."
- [ ] **The Playbook document grows at most one key, and the two digests still
      mean what they meant.** `REQUIRED_KEYS` and `OPTIONAL_KEYS`
      (`playbook.py:123-137`) are the whole grammar and `FORBIDDEN_KEYS`
      (`:141-149`) is the list of keys refused with a reason each. A step block
      is a new optional key or it is not a Playbook change at all. Whichever it
      is, `Projection` (`playbook.py:190-208`) and `Projection.text()`
      (`:231-263`) either carry it or deliberately do not, and the ticket says
      which: `sha256` is the document and `version` is the projection digest, so
      the choice decides whether adding steps to a Playbook invalidates every
      `playbook_selections.playbook_version` already recorded.
- [ ] **The prose request ceiling becomes a number something enforces, or the
      design says plainly that it does not.** Twelve places in the corpus state
      a budget in English -- `grep -rhoE 'sends (at most )?[a-z]+ requests'
      src/redkraken/playbooks/*/playbook.md` returns twelve lines, "sends six
      requests" four times among them -- and nothing reads any of them.
      `Fence.reserve` counts per Program and says why: "Rate, burst and
      concurrency are properties of a Program, not of a process"
      (`proxy.py:1354-1367`). A step vocabulary is the first thing in this tree
      that could make a Playbook's own stated ceiling a real one. Whether it
      should is a design answer this ticket owes; leaving it prose with a stated
      reason is an acceptable answer, leaving it unmentioned is not.
- [ ] **Exactly one Playbook is converted, and it is
      `playbooks/file-resolution/playbook.md`.** It is the honest first case and
      the reasons are all readable in the file. Its three `bb:evidence` rows
      (`:13`) ask only for `response_invariant` and `response_differential`,
      which per ticket 166 are the only two kinds any replay can write, so it is
      one of the thirteen Playbooks that is satisfiable today. Its steps 2, 3
      and 4 (`:56`, `:68`, `:92`) are nothing but requests to one endpoint, it
      names `mcp__rk2__http_request` in the prose, it uses the words
      "baseline", "variant" and "control" the way `TEST_ACTION_ROLES`
      (`roster.py:399`) uses them, and its ceiling states six requests
      (`:163`). Its steps 1 and 5 through 8 are the analysis half, which is the
      split this whole ticket is about, already drawn by the author. If a
      different Playbook is chosen, the ticket says why against these same
      readings.
- [ ] **The converted Playbook produces a specification through the verb that
      already exists, not a second one.** `roster.py:1420-1429` records the
      shape decision ticket 141 took and names this ticket's approach as the
      road not taken *at that time*: "Ticket 141 named two candidates: this --
      the model that holds the claim authors the specification through a
      Contract shaped like `propose_finding` -- or the runtime derives one from
      the Playbook the Task was selected under. The second is not available.
      `playbook_selections` has never held a row in this tree (ticket 101) ...
      The two are not exclusive: a derivation can be added later and will write
      the same rows through the same verb, because what decides whether a
      `tests` row exists is `propose_test` and not its caller." Ticket 164
      removed the stated obstacle. So a derived plan goes through
      `mcp__rk2__propose_test` (`roster.py:1469-1477`) and its five parts
      (`_TEST_SPEC_PARTS`, `:1112-1182`), or the ticket explains what those five
      parts cannot express.
- [ ] **Checked by something that would go red.** One test that takes the
      converted Playbook, derives a plan from its step block, and asserts three
      things that all fail today: that the derived plan validates against the
      same shape rule a model-authored one does, that performing it files one
      Receipt per action, and that the analysis half was handed no argument
      through which it could name a URL. A test that only asserts the step block
      parses is not this criterion.

## Why this is asked

Ticket 167 evaluated HuntProxy against the door and declined the program while
naming four ideas worth copying. This is the first and the largest of the four,
promoted into its own ticket at the operator's instruction. The idea, quoted in
167 from HuntProxy's own plugin contract:

> A plugin plans a bounded test and analyzes the result. HuntProxy performs the
> requests, applies scope and resource limits, and saves the traffic and
> evidence. Plugin JavaScript runs inside QuickJS and cannot open sockets, read
> files, launch processes, use Node.js modules, or call `fetch()` directly.

What is worth copying is the boundary in that sentence and nothing else. Not the
code, not QuickJS, not JavaScript, not a plugin directory. The shape is: a step
vocabulary the runtime performs, with the analysis half running somewhere that
cannot open a socket.

The reason it is worth copying here is that this tree ships fifty Playbooks and
none of them contains a step anything performs. Measured across
`src/redkraken/playbooks/*/playbook.md`:

- 50 Playbooks, 331 numbered prose steps between them, between five and eight
  per Playbook. Every one of them is a heading and a paragraph.
- 23 Playbooks name `mcp__rk2__http_request` in that prose. 2 name
  `mcp__rk2__mint_callback`, which ticket 98 shipped. No Playbook names any
  other verb on the surface. That is the whole of the corpus's
  machine-readable content: two tool names, spelled inside English sentences.
- 27 Playbooks end a step with the words "Complete this step with ...", which is
  an instruction to a reader about when a paragraph is finished, and is the
  closest thing in the corpus to a step boundary a machine could find.
- 12 lines state a request budget in English (`sends six requests`,
  `sends four requests`, and so on). Nothing reads them.

`playbook.py:267` is where a compiled `Playbook` is defined, and what it holds
is the document, what selects it, and what it projects. `Projection`
(`playbook.py:190-208`) has nine fields and the last of them is `instructions:
str`. `Projection.text()` (`:231-263`) renders every field and ends by appending
`self.instructions.strip()` (`:262`). `execution.py:1136-1147` joins those
strings and appends them to the prompt with a sentence saying the Playbooks "are
how to ask the question, not what to report" (`:1144-1146`). That is the whole
delivery path, and its terminal is a model's context window. There is no other
consumer.

## What is already here, so the design is not proposed against a blank page

Half of the boundary already exists in this tree, and the design's first job is
to notice that rather than build a second one.

**The performer exists.** `replay.py` opens with the distinction this ticket is
about, in the tree's own words: "A browser mission or a subagent's request is
somebody deciding what to send; a replay sends what a Test specification already
said, in the order it said it, and reports which Receipt answered which planned
action. Nothing here chooses a url, a method or a role -- all three come out of
the plan `open_test_replay` hands back" (`replay.py:4-9`). `_perform`
(`:375-429`) walks `plan["actions"]` in order (`:395`), files each Receipt
against its ordinal through `record_test_action` (`:77`, called at `:410-412`),
and treats a door refusal as a hold rather than a failure (`:397-406`). The
`test_replay_actions` table is one row per action naming the Receipt that
answered it, unique on the Receipt so a run "could [not] cite the same exchange
as its baseline and its variant and produce a differential against itself"
(`20260815T000000Z__a_test_runs_through_the_replay_lane.sql:550-574`).

**The vocabulary exists.** `tests.spec` is JSONB because "it is a program, read
whole by the replay engine, never filtered on by field"
(`0008_tests.sql:9-10`, table at `:11-22`). Its five parts are served as a
schema at `roster.py:1112-1182`: `preconditions` from `TEST_PRECONDITION_KINDS`
(`:392-398`), `setup`, `actions` with `TEST_ACTION_ROLES` (`:399`) and
`TEST_ACTION_KINDS` (`:411`) and `TEST_REQUEST_METHODS` (`:419`), `assertions`
from `TEST_ASSERTION_KINDS` (`:400-405`), and `cleanup`.

**The sandbox exists.** An offline tool is "a registry-described process with no
network at all unless its registry row says it uses the proxy adapter"
(`isolation.py:18-21`), enforced by `isolation.run_tool` (`:725`), with the
value in a column that has exactly two legal values
(`20260814T030000Z...:147-151`). A component that plans and analyses but cannot
open a socket is not a thing this tree would have to invent. It is a row.

**A closed action registry exists.** `browser_actions` (`20260814T040000Z...:150`,
rows at `:186-207`) is ten actions, each declaring `reaches_network`, `submits`
and its `outcome_keys`, changed only by migration.

So the gap is narrow and specific. The runtime already performs plans. What it
performs is a plan a model authored per claim from scratch, having read a
Playbook's prose and reconstructed the steps in its head. The Playbook -- the
document that already knows the steps, already knows the roles, already knows
the ceiling -- contributes nothing to the plan except by being read.

## The design questions, and what an answer has to survive

1. **What a step is.** A row in a migration-owned vocabulary, on the
   `browser_actions` precedent, or a shape inside the Playbook document checked
   by `playbook.py`, or both. An answer that lets a Playbook author invent an
   action the runtime then performs is refused by the `browser_actions` comment
   at `:168-171` and does not need further argument.
2. **Who performs it.** The default answer is `replay.py`, because it already
   does exactly this and adding a second performer would be two answers to "what
   did we send". An answer that adds a performer says what `replay.py` cannot do.
3. **Where the analysis runs.** Sandbox (`offline_tools`-shaped, `network =
   'none'`) or model (a Contract in `CONTRACTS`). Both are available and they
   are not the same trade: a sandbox is deterministic, hashable and cheap and
   can only do what somebody wrote down; a model can read a body it has never
   seen and costs tokens and a Gate decision. The ADR picks one for the first
   step and says what would move it.
4. **What the Playbook document grows.** One optional key, or a sidecar file in
   the Playbook directory, or nothing at all with the steps living in the
   database. Whichever it is, `sha256` and `version` (`playbook.py` module
   docstring, "Two digests, because two things can change independently") have
   to keep meaning what they mean, and `playbook_selections.playbook_version` is
   the row that would be invalidated by getting this wrong.

## How this relates to the four tickets it is next to

- **164 (`resolved`) is why this is possible now.** It measured that
  `playbook_selections` held zero rows in every database this tree had produced
  and fixed the trigger stage:
  `20261023T000000Z__fifty_playbooks_and_not_one_has_ever_been_selected.sql`
  rebuilt `subject_facts` (`:69`) so an Application subject has facts, and added
  `playbook_near_misses` (`:320`). This ticket does not touch selection, the
  near-miss report or `subject_facts`. It starts one stage later, at what
  happens after a Playbook is selected. The roster comment at
  `roster.py:1424-1426` cites "playbook_selections has never held a row in this
  tree" as the reason a Playbook-derived Test specification "is not available";
  164 is what retired that reason.
- **166 (`ready-for-agent`) is the stage after this one and it is not fixed
  here.** 166 is the evidence bar: 33 of 50 Playbooks gate `supported` on an
  Observation kind no verb can write, 37 if the test widens to kinds the replay
  path cannot write. This ticket deliberately picks `file-resolution`, one of
  the thirteen 166 lists as satisfiable, precisely so the first step is not
  blocked on 166's decision. If 166 is fixed first, the number of Playbooks this
  design can carry grows; if it is not, thirteen is enough to prove a shape.
  Neither ticket needs the other to land.
- **98 (`resolved`) and 99 (`ready-for-agent`) are the two other step kinds.**
  98 shipped `mcp__rk2__mint_callback` into `state.propose`
  (`roster.py:902-907`), which is a step reaching the out-of-band channel. 99
  would ship a browser Contract over the ten registered `browser_actions`. Both
  are "let a Playbook step reach X" and both answer it by giving a *model* a
  verb, which is the right answer for a model-driven step and does not by itself
  make the step a thing the runtime performs. This ticket is the other half:
  once a step is a row rather than a paragraph, 98's correlator and 99's browser
  actions are the second and third entries in the vocabulary. It does not
  duplicate either and it must not re-specify either verb.
- **101 (`ready-for-agent`) owns the corpus rewrite and this ticket does not.**
  101 is fifty Playbooks rewritten against the capabilities tickets 94 through
  100 deliver. This ticket converts one Playbook and only to prove the design.
  If both land, 101 writes prose against the shape this one settles. Nothing
  here should be read as authorising fifty conversions.

## Notes

The four ideas ticket 167 named were this one, fuzz response grouping, HAR
export, and the audited explicit reveal. Tickets 171 and 172 are two of the
other three and they are features that each cost a function; this one is a
design change, and that is why it is separated and why it is scoped the way it
is.
167's own words: "This is the largest and the only one that is arguably a design
change rather than a feature." Scope accordingly. A branch that ends with an ADR
and one converted Playbook has closed this ticket. A branch that ends with fifty
converted Playbooks and no ADR has not.

One stale anchor observed while reading, not fixed here and not this ticket's
job: tickets 99 and 101 both cite `roster.py:784` for the `run_tool` tool enum.
That enum is now at `roster.py:1837-1841` and `:784` is the `name: str` field of
`Role`. Whoever picks up 99 or 101 should re-verify before quoting.
