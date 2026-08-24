# 168 — Evaluate Cybermes as a second hunting harness

**What to build:** An answer, on record, to whether [Cybermes](https://github.com/Zyrexnn/Cybermes) -- an autonomous bug-bounty agent framework published four days before this ticket was written, with the same stated purpose as this repository -- can be integrated here, and if not, which of its ideas are worth copying and what each would cost. It changes no code. The recommendation and its evidence are the deliverable.

**Blocked by:** nothing. This is a reading and a measurement.

**Status:** ready-for-agent

- [ ] What Cybermes is, is written down before it is judged, from the repository rather than from its README: publisher, licence, age, commit count, contributor count, checkout size, what is vendored and what is a dependency. The README's claims and the repository's own numbers are recorded separately when they disagree, because at least one of them already does.
- [ ] `hermes-agent` on PyPI is identified: publisher, version, licence, what it actually is, and whether it is a model runtime, a wrapper around a vendor CLI, or a name with nothing behind it. Cybermes pins it at `hermes-agent>=0.1.0` in `requirements.txt` and every claim about the "reasoning loop" rests on it. Nothing else in this ticket is worth measuring until this is answered, because a wrapper around the same SDK `_launch.py` constructs is a very different subject from a second agent runtime.
- [x] `tools/smart_pipe.py` is measured against what this harness already does with a bounded stream, on the same input. The other side of the table is `isolation.py:689` `max_output_bytes`, `isolation.py:705` `truncated`, and the packet's stated subtraction (`packet.py:17-21`). Facts kept, facts dropped, tokens spent -- the same shape ticket 90's criterion 6 used, so the two results are comparable.
- [ ] The `skills/` corpus is counted exactly and sampled: how many directories, what a single one contains, and whether any of them is executable or graded. The other side is `src/redkraken/playbooks` (50 directories) and `src/redkraken/fixtures` (55), and the question is not how many but how many have ever been graded against a fixture that was authored without reference to them -- which is ticket 84's whole subject.
- [ ] The evidence chain is traced end to end on the other side and written down as a sentence: which process observes a fact, which process writes it, and whether anything stands between the model's assertion and the report. `tools/aggregate_reports.py` reads `reports/<target>/findings/*.md`; establish by reading it who writes those files and whether severity and CVSS are read off a wire record or off prose.
- [ ] The egress question is answered with the compose file open: `docker-compose.yml` declares `network_mode: host`. Confirm it, and state what a request made under it leaves behind. Set that against `isolation.py:1076` (`network create --internal`), `isolation.py:1329` (refusal unless the Agent network is internal), `isolation.py:786` (`--network none` for a tool with no network row) and `proxy.py:1`.
- [ ] The licence chain is resolved to a yes or a no, not to a summary: PolyForm Noncommercial 1.0.0 on the repository, plus what `ATTRIBUTION.md` says is vendored under GPL-2.0 and CC BY-NC 4.0. Whether any of it may be copied into this repository, and whether a bug bounty payout makes a use commercial, are two separate questions and both get answered.
- [ ] A decision is recorded as an ADR under `docs/adr/` at the next free number, in the form `0004`, `0005` and `0006` already use: adopt, adopt one named idea, or decline. Declining is a result and closes this ticket.
- [ ] No production code path depends on anything from Cybermes unless the decision is adopt, and nothing from it is executed on this machine. A spike lives under `/tmp` or is deleted. Nothing under `~/engagements/` is read into this repository.

## Why this is asked

Cybermes describes itself as an "autonomous security research agent framework"
for reconnaissance, vulnerability discovery and automated reporting, which is
this repository's sentence with different words. It is Python, it drives an LLM
in a loop over a security toolchain, it keeps an evidence directory, and it
gates a finding behind what it calls a zero-false-positive rule. If a project
with 241 stars solved a problem this tree has open, reading it is cheaper than
building it, and the operator asked.

The premise worth doubting is in the numbers. The repository was created
`2026-08-19T13:25:08Z` and last pushed `2026-08-23T16:46:09Z`: it is four days
old. The contributors endpoint returns three entries -- `Zyrexnn` at 46
contributions, `claude` at 1, `msarg44` at 1 -- and the commit list shows
`Zyrexnn & Claude` as the author pair on nearly every commit. The checkout is
168,210 KB, which is roughly 164 MB of mostly vendored knowledge base for
48 commits of history. So what is being evaluated is four days of one author and
a model, not a matured system, and the ticket should be measured against that
rather than against the star count.

## What was already read, so the ticket starts from facts

This section is what a first pass could establish from the public repository
without running anything. It is not the measurement; it is the reason the
measurement is worth making and the reason most of it will be short.

**It is in domain and it is a whole harness, not a component.** Six phases --
passive recon, active probing, authentication testing, vulnerability scanning,
proof validation, report generation -- driven by a `hermes` entrypoint that is a
17-line bash script exporting `HERMES_HOME` and `exec`ing a `hermes` binary out
of a venv. The toolchain named is subfinder, httpx, katana, ffuf, nuclei,
sqlmap, dalfox and nmap. The report engine is Playwright rendering PDF and HTML.
There is a Telegram bot gateway for remote control.

**Its authority model is the operator's word.** `scope.yaml` ships targets of
`*`, `http://127.0.0.1:8888` and `http://localhost:8888`, an
`authorization: AUTHORIZED` field, a `dynamic_override: true` field, and the
rule "All domains, URLs, and endpoints explicitly requested by the operator are
authorized." `AGENTS.md` says the same thing in its section 2: "Any target
domain, URL, IP range, or endpoint specified by the operator is explicitly
authorized." There is no scope grammar, no version, and no compiled policy --
the assertion is the policy.

That file is worth one further note as an artefact. Two attempts to retrieve
`AGENTS.md` through a summarising model returned a refusal on the first pass:
the model read the authorization clause as an attempt to override its own
constraints and declined to reproduce the document. The second attempt, framed
as a report about the file rather than a rendering of it, returned the section
headings and the quoted clause above. Whatever else is true of that file, a
model asked to read it plainly treated it as a jailbreak, and that is a fact
about adopting its text.

**Its evidence is prose the model wrote.** `tools/aggregate_reports.py` reads
`reports/<target>/findings/*.md` and extracts title, severity, CVSS, CWE and
affected endpoint with regular expressions over the markdown. There is no
cross-reference to a captured request, no wire record and no second writer.
The "zero-false-positive gate" is a rule stated in a prompt: the model is told
to produce an HTTP status and a Python PoC before writing a finding. Nothing
checks that it did.

**Its egress is the host's.** `docker-compose.yml` sets `network_mode: host`.
The container shares the host network namespace, so there is no boundary to
enforce anything at, and there is no proxy anywhere in the design. `AGENTS.md`
recommends 5 to 10 requests per second as a guideline with no mechanism named.

**The one mechanism that is genuinely a mechanism is `tools/smart_pipe.py`,**
5,801 bytes. It reads a tool's stdout on stdin, writes 100% of it to
`recon/<slug>/<tool>_raw.txt`, scores each line -- critical markers, secret
markers, HTTP status, presence of a query parameter, UUID shape, Shannon
entropy above 3.8, an extension noise filter that zeroes static assets -- and
prints only the top N by score, default 40, with a count of what it dropped.
The claim is 70 to 85 percent context reduction. That is a real idea, it is one
file, and it is the only part of the project that is not a prompt.

## 1. What it does that this harness does not

Three things, and the first two are the same thing twice.

**A signal-ranked stream instead of a truncated one.** This harness bounds an
offline tool's output by bytes: `isolation.py:689` declares `max_output_bytes`,
`isolation.py:705` reports `truncated`, and `tool.py:20` says the bound is
applied "while the process is still running, because a bound applied to output
already read is not a bound". What survives is the first N bytes. `smart_pipe.py`
keeps the highest-scoring N lines instead and says how many it dropped. On a
tool whose interesting line is line 40,000 those are different answers. The
counter-argument is already in this tree and belongs in the measurement: the
harness does not read a raw stream where it can read a parser instead --
`js_routes`, `js_map`, `js_parse` and `extract_paths.py` file structured
Artifacts -- and a scoring heuristic over a stream is what one falls back to
when no parser exists.

**A rendered PDF.** `reporting.py:1` renders a report as "a projection of what
holds", and its signature is deliberately "a mapping in, a string out" with no
connection, clock or environment (`reporting.py:14-19`). Cybermes ships
`tools/generate_pdf.py` at 15,130 bytes on Playwright. That is a downstream
formatting difference, not an architecture, and this harness's constraint on
narrative text -- checked token by token against the bundle's own scalars
(`reporting.py:27-29`) -- is a stronger property than a nicer stylesheet.

**A remote control channel.** A Telegram gateway. This harness has `rk` and a
local operator UI (ticket 60). A chat gateway is not a missing capability here;
it is an inbound control path with no gate in front of it.

Everything else in the list is a name for something below.

## 2. What it does that this harness already does, from a different authority

This is most of the project, and each line of it would be a second
implementation of an authority this tree spent tickets closing.

- **Scope.** `scope.py` compiles a versioned policy -- `GRAMMAR_VERSION = 2` at
  `scope.py:71`, `compile_policy` at `scope.py:980`, `decide` at
  `scope.py:1261`, `decide_request` at `scope.py:1270` -- and the door re-decides
  every request against the current compiled policy rather than against the URL
  the caller named (`proxy.py:16-23`). Cybermes has `targets: ["*"]` and a
  sentence. Adopting its scope handling is not adopting a weaker policy; it is
  adopting no policy.
- **Evidence.** `CONTEXT.md:80` defines an Observation as "an immutable fact
  derived from a runtime-generated provenance record ... Never produced by a
  model alone", and `CONTEXT.md:549` defines Promotion as the step after which
  "nothing an agent returns is true before it". Cybermes's findings are markdown
  the model wrote, aggregated by regular expression.
- **Egress.** `proxy.py:1` is "the one peer a Tool run may reach, and the only
  writer of an allowed Receipt"; `proxy.py:29-34` says an exchange the record
  does not carry is an exchange that did not happen, and a failed write is a 502
  rather than a 200; HTTPS is terminated at the door rather than tunnelled
  (`proxy.py:36-45`) precisely because a tunnel is egress with no Receipt.
  Cybermes has `network_mode: host`.
- **Tool authority.** `tool.py:1-9` puts which tools exist, which roles may run
  them, what arguments they take and what their ceilings are into a registry the
  module reads rather than holds an opinion about, and `tool.py:20` includes
  "whether the tool has a network at all" in that row. Cybermes invokes
  subfinder, ffuf and sqlmap from a prompt.
- **Role authority.** `roster.py:1` is "the seven roles, what each may call, and
  the gate that decides one call", compiled at import against a pinned inventory
  (`roster.py:49-50`), with `Gate.decide` as the boundary rather than the
  visible tool list (`roster.py:14-23`). Cybermes has one agent with a persona.
- **Knowledge.** 50 Playbook directories and 55 Fixture pairs ship here, with
  fixtures authored without reference to any Playbook and a grading route
  (tickets 78 and 84). Cybermes ships `SKILL.md` files -- `skills/hunt-idor`
  contains exactly one entry, `SKILL.md` at 21,457 bytes -- and nothing that
  grades one.
- **Corpus intake.** Ticket 79 already built the bounded intake for somebody
  else's published technique, with the constraint that retrieval is a maintainer
  act and "nothing under `src/redkraken/` gains a way to fetch a writeup".
  Cybermes's `knowledge/` is that intake with the ledger removed.

## 3. Which ideas are worth copying, and what each costs

**One, and it is `smart_pipe.py`'s shape rather than its code.** Raw to disk in
full, ranked subset to the model, with the count of what was dropped stated. The
last clause is the part this tree would insist on and Cybermes already does: the
model is told what it is not seeing. The cost here is not the scorer, which is
under 200 lines; the cost is that a ranked subset is a *selection over evidence*,
and a selection has to be reproducible and attributable or the run cannot be
re-read later. That means the ranking is versioned like a Playbook projection is
versioned, the full stream is the Artifact and the ranked view is derived from
it, and the Tool run records which ranker version produced the view. That is a
schema change, and it should not be started before the measurement in criterion
3 shows that ranking beats truncation on a real stream.

**A second, weaker candidate: the finding template as a checklist.** Cybermes's
finding files carry severity, CVSS, CWE and affected endpoint in a fixed shape.
This tree has that in the schema already. There is nothing to copy but the
field list, and the field list is not the hard part.

**Nothing else.** The skills are prose, the scope model is an assertion, the
report engine is a stylesheet, and the agent core is a dependency this ticket
has not yet identified.

## 4. What integrating it would break or widen

Stated in the terms this repository uses for the two things it will not trade.

**Its findings are evidence the runtime never observed.** A finding is a
markdown file the model wrote and `aggregate_reports.py` parses; severity and
CVSS are whatever the prose says. Every path in this harness that turns a
model's output into a row goes through Promotion (`CONTEXT.md:549`), and an
Observation is defined as never produced by a model alone (`CONTEXT.md:80`).
Bringing the Cybermes reporting pipeline in as-is would create a second writer
of findings with no provenance record behind it, and it would be indistinguishable
downstream from one that had.

**Its container reaches the network outside the door.** `network_mode: host` is
not a weaker fence, it is the absence of one. `isolation.py:1329` refuses to
start an Agent on a network that is not internal, `isolation.py:1076` creates
that network with `--internal`, and `isolation.py:786` gives a tool with no
network row `--network none`. Cybermes's compose file is the exact configuration
those three lines exist to refuse. Any adoption that carries its runtime carries
that, and a request made under it earns no Receipt, is attributable to no lane
(`CONTEXT.md:706`), and would make a Program's Receipt set silently incomplete.

Two further widenings, smaller but real. Its scope file admits `*` with
`dynamic_override: true`, so a policy version means nothing and a withdrawn
target is not withdrawn. And its Telegram gateway is an inbound control path
that no `Gate.decide` sees.

## 5. Licence

The repository ships PolyForm Noncommercial 1.0.0. GitHub's own metadata reports
`spdx_id: NOASSERTION`, `name: Other`, which is what GitHub returns for a licence
its detector does not recognise -- so the licence is the LICENSE file's text and
not an SPDX identifier a tool can check.

PolyForm Noncommercial permits use for personal, research and educational
purposes and prohibits commercial use. This repository ships no LICENSE file of
its own, which is a separate matter and not this ticket's to fix, but it means
there is no stated licence for a PolyForm term to be compatible or incompatible
with, and any copying would be into an unlicensed tree.

Two harder questions the measurement must actually answer rather than restate.
First, whether a bug bounty harness that produces payouts is a commercial use --
the operator's own answer to that decides whether Cybermes may be *run* here at
all, independently of whether anything is copied. Second, `ATTRIBUTION.md` lists
what is vendored: HackTricks under CC BY-NC 4.0, SQLMap under GPL-2.0-or-later,
PayloadsAllTheThings and Hack-Skills under MIT, Claude-BugHunter under MIT for
code and CC BY 4.0 for content, Strix under Apache-2.0. A file copied out of
`knowledge/` carries whichever of those it came from, not PolyForm, and the
GPL-2.0 and CC BY-NC components would each be a separate and worse answer. So
"can we copy from Cybermes" is not one question, it is one per directory.

## What "no" looks like, and why it is likely

The honest form of a decline is two sentences. Cybermes is a prompt corpus and a
tool wrapper with no boundary underneath it, and every boundary this harness has
-- the door, the roster, the scope grammar, Promotion -- is the thing it does
not have rather than the thing it does differently. The one file worth reading
twice is `tools/smart_pipe.py`, and what is worth taking from it is a ranking
strategy over an already-bounded stream, not a dependency and not a line of its
code.

A partial yes is a real result and has one named shape: **adopt the ranked-view
idea for offline tool output**, measured against byte truncation on a real
stream first, versioned and attributable if it wins, and dropped if it does not.
That is a smaller claim than adopting a framework and it is the only one in this
ticket that a measurement could turn into a build.

## Answer, 2026-08-24: the one candidate does not survive measurement

Section 3 named exactly one idea worth copying, and the operator promoted it out
of this ticket into 173 so that it could be built rather than argued about. The
first phase of 173 was a measurement and no code, and the measurement killed the
premise it was meant to test. 173 is deleted, no implementation ticket replaces
it, and what follows is everything 173 established, kept here because the ticket
that raised the idea is where the answer to it belongs.

**The registry has six rows, and five of them already name a parser.** The
registry is `offline_tools`
(`src/redkraken/migrations/20260814T030000Z__an_offline_tool_becomes_evidence.sql:119`),
and every row in it arrives through one of three inserts: `jq` at
`20260814T030000Z:159-164`, then `js_parse`, `js_routes` and `js_map` at
`src/redkraken/migrations/20260814T050000Z__source_becomes_a_grounded_conclusion.sql:436-450`,
then `compare_responses` and `extract_paths` at
`src/redkraken/migrations/20260922T030000Z__a_skill_script_is_a_program_the_harness_ships.sql:443-455`.
The `analyser` column is added at `20260814T050000Z:121-122`, and it is not
optional for the shapes that matter: `20260922T030000Z:55` makes it mandatory for
a Skill script and `:74` makes it mandatory for a stdin-fed tool. The three `js*`
rows all name `jsscan.py` and the two Skill halves name `compare.py` and
`extract_paths.py`. The database goes further than the registry does and refuses
a recorded path from a tool whose row names no analyser
(`20260814T050000Z:386-389`), so a run of an analyser is held to its own answer.

That leaves exactly one row with no analyser, `jq`, and `jq`'s stdout is JSON
produced by a filter the caller wrote. The caller has already selected; a scorer
over that output would be a second selection over the first. So the count of
registered tools a ranked view would buy anything for is zero, and it is zero not
by accident but because this harness reads a parser wherever a parser can be
written. A scoring heuristic over a raw stream is what one falls back to when no
parser exists, and here one always exists.

**There are two truncations, not one, and a ranked view could only ever replace
the smaller of them.** Section 1 above described a single truncation and that
description was imprecise, which is worth correcting on the record. The first
truncation is the bound on the process: `isolation.py:689` declares
`max_output_bytes` as one of the ceilings, `isolation.py:968-976` is the read loop
that applies it while the process is still running (`:973` counts every byte
produced, `:974` computes the room left, `:976` keeps only what fits),
`isolation.py:977-979` breaks and marks `overflowed` when the tool prints past it,
and `isolation.py:705` is the `truncated` property that reports the difference.
`tool.py:20-21` states why it is enforced there: the ceilings are held "while the
process is still running, because a bound applied to output already read is not a
bound". What survives that bound is the Artifact.

The second truncation is the head handed to the model: `tool.py:533-534` cuts
`answer.stdout.data[:excerpt]` and the same for stderr, `agent.py:1537` passes
`excerpt=packet_module.DEFAULT_EXCERPT`, and that constant is `4096` at
`packet.py:90`. What the child then receives is the head plus a bare boolean
(`tool.py:547-548`). For a `jq` run that filled its 1,048,576-byte bound, the
model reads 4,096 bytes and is told `true` about the other 1,044,480.

Only the second of those two is a thing a ranked view could ever have replaced.
The first cannot be, and the distinction is the whole safety of the design: a
ranker that read the live pipe would be a bound applied to output already read,
which `tool.py:20-21` says is not a bound at all, and it would make the process
ceiling a function of a scoring function. Any future proposal in this shape has to
start from that sentence.

**The case the idea was invented for is already answered by this tree.** The
motivating example is a stream whose interesting line is line 40,000, and reading
past the head is already somebody's job. `packet.py:1329-1337` decided it on
purpose: reading past `DEFAULT_EXCERPT` of any Artifact is a Tool run and not a
packet read, and "the route that reads all of an Artifact exists and answers a
bounded summary instead of a window -- `run_skill_script` hands the program the
whole thing untruncated". `_launch.py:1211-1218` states the same thing to the
child in the same words: the script "is handed each Artifact whole -- nothing is
truncated on the way in". So the harness's existing answer to line 40,000 is not a
better window over the first 4 KB. It is: write a program that reads all 40,000
lines and answers a question about them. A ranked view is the generic version of
that program, for the case where nobody has written the specific one, and this
registry has no tool in that case.

**Nothing may be copied, and there is still nowhere here to copy it to.**
Cybermes is PolyForm Noncommercial 1.0.0, and its `ATTRIBUTION.md` puts the
vendored `knowledge/` tree under GPL-2.0-or-later and CC BY-NC 4.0 among others.
This repository still ships no LICENSE file of its own, so any copying would be
into an unlicensed tree and there is no stated licence here for a PolyForm term to
be compatible with. A scoring table is code, a regular expression is code, and a
threshold lifted from a file is code. The only thing that ever crossed was the
English sentence already written in section 3 -- keep the raw, show a ranked
subset, state the count of the remainder -- and `tools/smart_pipe.py` was not
opened while 173 was worked. Nothing from that repository has been executed on
this machine.

**Conclusion: declined.** The candidate in section 3 is not adopted, no
implementation ticket exists for it, and no schema migration is written. A ranked
view that buys zero registered tools anything would still cost a reproducibility
obligation forever, because from the moment a model is handed a subset of a
stream, every conclusion drawn from that stream depends on which subset, and
"which subset" has to be answerable a month later from rows rather than from
memory. This tree pays that price twice already, for `tool_runs.analyser_sha256`
(`20260814T050000Z:162-177`) and for the Playbook projection digest
(`playbook.py:36`), and both times the versioned thing was doing work no cheaper
mechanism could do. This one is not.

The condition under which this is worth revisiting is narrow and nameable: **a
scanner-shaped tool with no parser is added to `offline_tools`** -- a subfinder,
httpx, katana, ffuf, nuclei or nmap shape, something that emits many lines of
which few matter and for which no analyser can reasonably be written. That
addition is a migration with a version pattern, a network decision and an argument
grammar, and it is the trigger. Until such a row exists, the measurement has no
subject and the idea has no beneficiary.

**What this discharges in the criteria above, and what it does not.** Criterion 3
is discharged, but as a refusal rather than as a table: the comparison it asked
for cannot be computed, because `tools/smart_pipe.py` may not be opened on licence
grounds and because no registered tool produces the unparsed stream the comparison
needs as its input. The other side of that table was measured anyway and is
written out above -- `isolation.py:689`, `isolation.py:705` and the stated
subtraction at `packet.py:17-21` -- and the answer to the question the criterion
served is that byte truncation is not the harness's answer to a long stream in the
first place. Criterion 2, the identification of `hermes-agent`, is untouched by
this and remains open. So do criteria 1, 4, 5, 6 and 9, and criterion 7's second
half: whether a bug bounty payout makes a use commercial, which decides whether
Cybermes may be run here at all, is a separate question from whether anything may
be copied and this answer settles only the copying. Criterion 8, the ADR, remains
open as well: a decline of one named idea is not yet the recorded decision about
the project as a whole, and that decision is what closes this ticket.
