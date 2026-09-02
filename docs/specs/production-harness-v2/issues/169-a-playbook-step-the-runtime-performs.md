# 169 -- A Playbook step the runtime performs

**What to build:** First a throwaway prototype and a measurement, and only if
that measurement comes back positive, a design and one worked case behind it.
The measurement asks exactly one question: can a Playbook's numbered prose steps
be hand-written as a `tests.spec` the verbs this tree already serves accept and
the replay this tree already ships performs? If most of them cannot, the ticket
ends at the measurement and records why, and that is a result rather than a
failure. If they can, the design says what a Playbook step is when it is a thing
the runtime performs rather than a paragraph a model reads, where the analysis
half runs, and what the analysis half is allowed to reach. Ticket 167 called
this candidate "arguably a design change rather than a feature" and it is right,
which is why the prototype comes before the design and not after it.

**Blocked by:** nothing. Ticket 98 is resolved and shipped
`mcp__rk2__mint_callback` into `state.propose` (`roster.py:902-907`); ticket 99
is still `ready-for-agent` and it does not block this, because the first step
here is the request step, whose performer already exists in `replay.py`, and the
browser step is the second kind rather than the first.

**Status:** ready-for-agent

## What this is, and what it is not

HuntProxy is the thing that made us look, and ticket 167 -- which read it,
declined the program and named this as the largest of four ideas worth taking --
is the whole of the credit it is owed here and holds the quotation this ticket
no longer needs to carry.

What 167's reading actually found, once it was measured against this tree, is
that this is not an import. The boundary it describes is a road this repository
already opened, three times over, and never finished:

- **The performer is here.** `replay.py` performs a plan and decides nothing
  about it. Its own words: "A browser mission or a subagent's request is
  somebody deciding what to send; a replay sends what a Test specification
  already said, in the order it said it, and reports which Receipt answered
  which planned action. Nothing here chooses a url, a method or a role -- all
  three come out of the plan `open_test_replay` hands back" (`replay.py:4-9`).
- **The step vocabulary is here.** `tests.spec` is JSONB because "it is a
  program, read whole by the replay engine, never filtered on by field"
  (`0008_tests.sql:9-10`, table at `:11-22`), and its five parts are served as a
  schema at `roster.py:1112-1182`.
- **The socketless analysis half is here.** `offline_tools.network = 'none'` is
  "a container with no interface but loopback"
  (`20260814T030000Z__an_offline_tool_becomes_evidence.sql:148-152`), enforced
  by `isolation.run_tool` (`isolation.py:725`), on a process whose output the
  supervisor already bounds while it is still running (`isolation.py:18-26`).
- **The closed action set is here.** `browser_actions`
  (`20260814T040000Z__a_browser_mission_runs_behind_the_door.sql:150`) is ten
  rows inserted at `:186-207`, each declaring whether it reaches the network,
  whether it submits, and the outcome keys the digest is computed over, changed
  only by migration (`:168-171`).

**QuickJS specifically is not wanted, and this is the reason.** What a QuickJS
plugin sandbox buys is one property: a place to run analysis that cannot open a
socket. `network = 'none'` already is that property, stated in a column with two
legal values and no third, so that "there is no way to spell 'the host's
network'"
(`20260814T030000Z__an_offline_tool_becomes_evidence.sql:148-152`). Buying it a
second time would mean putting a JavaScript engine into a runtime whose
`pyproject.toml` declares `dependencies = []` and says the runtime is standard
library only (`:18-27`), to obtain a guarantee one existing column already
makes. No part of this ticket reaches for it, and a design document that
proposes it is refused by this paragraph without further argument.

And the one recorded reason this road was left unfinished has since been
retired. `roster.py:1424-1426` says a Playbook-derived Test specification "is
not available" because "`playbook_selections` has never held a row in this
tree". Ticket 164 fixed exactly that. The obstacle in the comment is gone; what
is left is the work.

So the gap is narrow, specific and ours. Measured across
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
  `sends four requests`, and so on). Nothing reads any of them.

`playbook.py:267` is where a compiled `Playbook` is defined, and what it holds
is the document, what selects it, and what it projects. `Projection`
(`playbook.py:190-208`) has nine fields and the last of them is `instructions:
str`. `Projection.text()` (`:231-263`) renders every field and ends by appending
`self.instructions.strip()` (`:262`). `execution.py:1136-1147` joins those
strings and appends them to the prompt with a sentence saying the Playbooks "are
how to ask the question, not what to report" (`:1144-1146`). That is the whole
delivery path, and its terminal is a model's context window. There is no other
consumer.

The runtime already performs plans. What it performs is a plan a model authored
per claim from scratch, having read a Playbook's prose and reconstructed the
steps in its head. The Playbook -- the document that already knows the steps,
already knows the roles, already knows the ceiling -- contributes nothing to the
plan except by being read.

## Phase zero: prototype it, measure it, and let the measurement decide

The operator's standing rule, recorded here because it is general and not
specific to this ticket: before building anything of this shape, prototype it
and measure whether it is actually efficient, interesting and working. A
negative prototype closes the ticket.

Phase zero is a throwaway. It changes no schema, adds no verb, adds no column
and writes no migration. It exists to produce four numbers and a verdict.
Nothing in the criteria section below begins until every phase-zero criterion is
met and the gate is passed.

- [ ] **The Playbook is named, and it is
      `src/redkraken/playbooks/file-resolution/playbook.md`.** It is the honest
      first case and every reason is readable in the file. Its three
      `bb:evidence` rows (`:13`) ask only for `response_invariant` and
      `response_differential`, which per ticket 166 are the only two kinds any
      replay can write, so it is one of the thirteen Playbooks 166 lists as
      satisfiable today and is **not** one of the thirty-three that gate
      `supported` on a kind no verb can write. It names `mcp__rk2__http_request`
      in its prose (`:58`), which only 23 of the 50 do. It uses the words
      "baseline", "variant" and "control" the way `TEST_ACTION_ROLES`
      (`roster.py:399`) uses them. It states its ceiling as six requests
      (`:163`), one of the twelve English budgets. It is `bb:risk: constrained`,
      `bb:effects: read_only` and nothing it sends writes (`:40-41`), so the
      prototype needs no impact block and no cleanup. Its eight steps split the
      way this whole ticket is about, already drawn by the author: steps 2, 3
      and 4 (`:56`, `:68`, `:92`) are nothing but requests, steps 1, 5, 7 and 8
      (`:28`, `:106`, `:131`, `:160`) are the analysis half, and step 6 (`:120`)
      is both -- "One more request settles it" (`:126`) sits inside an otherwise
      analytic paragraph, which makes it the most interesting step in the file
      to translate. If a different Playbook is chosen, the ticket says why
      against these same readings, and it says whether the substitute is one of
      166's thirty-three. One of the thirty-three is not admissible as the
      prototype, because its result could not become an Observation whatever the
      translation achieved.
- [ ] **Its steps are hand-written as a Test specification and filed through the
      verb that already exists.** By hand, by the person or agent doing phase
      zero, into `mcp__rk2__propose_test` (`roster.py:1469-1477`) and its five
      parts (`_TEST_SPEC_PARTS`, `:1112-1182`). No derivation, no generator, no
      new key on the Playbook document, no schema change, no new verb, no new
      column, no migration. The shape rule is the thing being tested and it is
      already written down: 3 to 32 actions
      (`20260817T000000Z__a_pivot_is_stamped_from_the_run_that_showed_it.sql:348-357`),
      every action numbered in order (`:370-372`), at least one action in each
      of the three roles (`:387-391`), `kind` equal to `request` because that is
      "the only kind of action this runtime performs" (`:378-379`), and exactly
      five keys per action -- `ordinal`, `role`, `kind`, `method`, `url`
      (`:366`). That last one is where the translation is most likely to break,
      and finding out is the point.
- [ ] **It runs end to end against the synthetic target the vertical walk
      already uses.** `tests/test_vertical.py` is the precedent and phase zero
      reads it before writing anything. Its exchange is synthetic and says so:
      TEST-NET-3 at `203.0.113.10` for `app.example.com`
      (`tests/test_vertical.py:85-88`). It files its Test through `propose_test`
      at `:396-402` with a specification built by `specification()`
      (`tests/test_database.py:29017-29047`), and performs it through
      `ReplayFixture.performed` (`tests/test_database.py:29290`), which opens
      the plan with `open_test_replay`, writes one Receipt per answered ordinal
      through `receipted` (`:29210`), records each through `record_test_action`
      and closes with `close_test_replay` (constants at `:29067-29070`, the walk
      at `:29308-29318`). Phase zero answers six ordinals where that walk
      answers three. No socket is opened, which is the same thing the vertical
      walk does and is exactly what "against the synthetic target" means here.
- [ ] **The measurement is written down, in this ticket, in four answers.**
      One: how many of `file-resolution`'s eight numbered prose steps survived
      the translation into the specification, counted honestly, with a step that
      half-survived counted as not surviving and said so. Two: which steps could
      not be expressed at all and why, named one by one against the rule that
      refused them. Three: how many requests the specification costs, against
      the six the prose states in English at `:163` -- the same number, more, or
      fewer, and what the difference means. Four: whether the result is an
      Observation this tree can actually write, confirmed by reading what
      `close_test_replay` derived: its kind comes only from the assertions that
      name the action, `THEN 'response_differential' ELSE 'response_invariant'`
      (`20260816T000000Z__impact_is_authorized_before_it_is_proved.sql:1063-1070`,
      the decisive line at `:1069`), which is the whole set of kinds any replay
      can produce and is the measurement ticket 166 made.
- [ ] **The gate: a majority that cannot be expressed closes this ticket, and
      that is a good outcome.** If five or more of the eight steps cannot be
      expressed through the verbs that already exist, phase zero stops there.
      The ticket records the four answers above, records which rule refused
      which step, and is resolved by that measurement. It is resolved, not
      failed: a measured "the existing vocabulary cannot carry a Playbook's
      steps, here is exactly where it stops" is a more useful thing to hold than
      a design written against an assumption nobody checked. No ADR is written,
      no schema moves, no vocabulary widens, and no criterion below is attempted
      after a negative prototype. Only a passing prototype opens the section
      that follows.

## The criteria, and none of them begin until phase zero has passed

Every item below is conditional on the gate above being passed. A branch that
reaches any of them without the phase-zero measurement recorded in this file has
skipped the only step that was asked for first.

- [ ] **The design exists as one document and it is an ADR at `0008`.** It
      answers four questions and no others: what a step is, who performs it,
      where the analysis half runs, and what a Playbook document has to grow to
      carry one. It answers them against what phase zero measured rather than
      against what it expected. `0007` is reserved by ticket 167. Declining any
      of the four with a reason is a result, the way `0004`, `0005` and `0006`
      were results.
- [ ] **No HuntProxy source and no HuntProxy text enters the tree, and the diff
      proves it.** Nothing is copied here at all: no Rust, no JavaScript, no
      QuickJS, no plugin manifest, no copied sentence. `grep -ril huntproxy`
      over the working tree returns only ticket files -- 167, this one, and the
      siblings 170, 171 and 172 that came out of the same reading -- plus any
      ADR that cites them. Nothing under `src/`, `tests/` or `skills/` names it.
      **Precondition, stated so it is not rediscovered later:** HuntProxy and
      HuntProxy-Plugins are Apache-2.0, this repository ships no `LICENSE` file,
      and `pyproject.toml`'s `[project]` table (`:11-27`) declares no `license`,
      so there is no outbound licence for an inbound one to sit against. Ticket
      167 section 5 records that as an open question. Settling this
      repository's own licence is a precondition for copying any actual source
      and is *not* a precondition for this ticket, because this ticket copies
      none.
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
      (`20260814T030000Z__an_offline_tool_becomes_evidence.sql:141-146`).
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
      (`20260814T030000Z__an_offline_tool_becomes_evidence.sql:148-152`), and
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
      that could make a Playbook's own stated ceiling a real one. Phase zero's
      third answer is the evidence this criterion is decided on. Whether it
      should be enforced is a design answer this ticket owes; leaving it prose
      with a stated reason is an acceptable answer, leaving it unmentioned is
      not.
- [ ] **Exactly one Playbook is converted, and it is the one phase zero already
      hand-wrote.** Not a second one, and not fifty. The conversion is the
      prototype's specification arrived at by the design's own route instead of
      by hand, which is the only way to tell whether the design reproduces a
      result that is already known to work.
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
      parts cannot express -- and after phase zero it will already know.
- [ ] **Checked by something that would go red.** One test that takes the
      converted Playbook, derives a plan from its step block, and asserts three
      things that all fail today: that the derived plan validates against the
      same shape rule a model-authored one does, that performing it files one
      Receipt per action, and that the analysis half was handed no argument
      through which it could name a URL. A test that only asserts the step block
      parses is not this criterion. Phase zero's throwaway is not this test
      either: it proves the specification can be written by hand, and this one
      proves the runtime can derive it.

## The design questions, and what an answer has to survive

Read only after phase zero passes. Every one of them is a question the
prototype's measurement is evidence for.

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
   step and says what would move it. Neither answer is QuickJS.
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
  `playbook_near_misses` (`:280`). This ticket does not touch selection, the
  near-miss report or `subject_facts`. It starts one stage later, at what
  happens after a Playbook is selected. The roster comment at
  `roster.py:1424-1426` cites "playbook_selections has never held a row in this
  tree" as the reason a Playbook-derived Test specification "is not available";
  164 is what retired that reason.
- **166 is the stage after this one, and it turned out not to be a wall.** 166
  is the evidence bar. It was written as "33 of 50 Playbooks gate `supported` on
  an Observation kind no verb can write"; re-measured on 2026-09-02 it is 26 of
  51, and the reachability half is false. An evidence edge filed with the
  proposal, while the claim is still `proposed`, is counted by
  `playbook_evidence_unmet` at the `supported` transition, so every kind in the
  vocabulary is reachable and only the writer differs. Phase zero still picks
  `file-resolution` -- the kinds `close_test_replay` derives are still exactly
  `response_invariant` and `response_differential`, which is what this ticket's
  criteria rest on -- but it is not picked to dodge a wall any more. Neither
  ticket needs the other to land.
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
is. 167's own words: "This is the largest and the only one that is arguably a
design change rather than a feature." Scope accordingly. A branch that ends with
a recorded negative prototype has closed this ticket. A branch that ends with a
passing prototype, an ADR and one converted Playbook has closed it. A branch
that ends with fifty converted Playbooks and no ADR has not, and a branch that
ends with an ADR and no prototype behind it has not either.

One stale anchor observed while reading, not fixed here and not this ticket's
job: tickets 99 and 101 both cite an old line number for the `run_tool` tool
enum. That enum is now at `roster.py:1837-1841`. Whoever picks up 99 or 101
should re-verify before quoting.
