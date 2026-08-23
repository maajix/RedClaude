# 173 — A ranked view of a tool stream instead of its first bytes

**What to build:** In two phases, and the second one only if the first earns
it. Phase one is a measurement and changes no code: on a real stream from a
tool this registry actually admits, the first N bytes a child is handed today
against the highest-scoring N lines of the same bytes, counted in facts kept,
facts dropped and tokens spent. Phase two is the schema change that would make
a ranked view admissible evidence -- the full stream stays the Artifact, the
view is derived from it and reproducible, the ranker's identity goes on the
Tool run, and the model is told the count of what it is not being shown -- and
it is not started unless phase one reports a win.

**Blocked by:** nothing for phase one. Phase two is blocked by criterion 8 of
this ticket and by ticket 168's ADR, which is the decision about whether
anything from Cybermes is adopted at all; this ticket is the one named idea
that decision could say yes to, promoted out of 168 section 3 at the
operator's instruction.

**Status:** ready-for-agent

- [ ] **Nothing from Cybermes is copied, and the ticket is worked as if its
      source were unreadable.** Cybermes is PolyForm Noncommercial 1.0.0 over a
      vendored `knowledge/` tree its own `ATTRIBUTION.md` puts under
      GPL-2.0-or-later and CC BY-NC 4.0, and this repository ships no LICENSE
      file of its own, so any copying would be into an unlicensed tree. No
      Cybermes source code and no Cybermes text enters this tree: not one line,
      not a scoring table, not a regex, not a threshold, not a comment. What is
      being implemented is an idea described in English by a reader who was told
      not to copy -- raw kept whole, ranked subset shown, count of the remainder
      stated -- and every constant in whatever is written here is derived from
      the measurement in criterion 4 rather than transcribed. `tools/smart_pipe.py`
      is not opened during this ticket, and nothing from that repository is
      executed on this machine.
- [ ] **The two truncations are written down separately before anything is
      measured, because the ticket is about one of them and must not touch the
      other.** The first is the bound on the process: `isolation.py:689` declares
      `max_output_bytes` as one of the five ceilings, `isolation.py:968-976` is
      the read loop that applies it while the process is still running
      (`:973` counts every byte produced, `:974` computes the room left, `:976`
      keeps only what fits), `isolation.py:977-979` breaks and marks `overflowed`
      when the tool has printed past it, and `isolation.py:705` is the
      `truncated` property that reports the difference. `tool.py:20-21` states
      why it is there: `isolation.run_tool` enforces the ceilings "while the
      process is still running, because a bound applied to output already read is
      not a bound". The second is the head handed to the model: `tool.py:533-534`
      cuts `answer.stdout.data[:excerpt]` and the same for stderr, and
      `agent.py:1537` passes `excerpt=packet_module.DEFAULT_EXCERPT`, which is
      `4096` at `packet.py:90`. Only the second is this ticket's subject.
- [ ] **The measurement's subject is a stream a registered tool really
      produced.** Not a synthesised file and not a stream from a tool this
      registry does not admit. The registry is `offline_tools`
      (`src/redkraken/migrations/20260814T030000Z__an_offline_tool_becomes_evidence.sql:119`),
      and the rows in it are `jq` (`:159-164`), `js_parse`, `js_routes` and
      `js_map`
      (`src/redkraken/migrations/20260814T050000Z__source_becomes_a_grounded_conclusion.sql:436-450`)
      and `compare_responses` and `extract_paths`
      (`src/redkraken/migrations/20260922T030000Z__a_skill_script_is_a_program_the_harness_ships.sql:443-455`).
      The stream is captured by running one of them for real, its bytes are the
      Artifact the run filed, and the Artifact's hash is recorded in this ticket
      so the measurement can be re-run over the same bytes.
- [ ] **The comparison is the shape ticket 90's criterion 6 used, so the two
      results can be read side by side.** A ground truth is hand-authored first:
      the list of facts a reader of the whole stream would want, written before
      either view is computed, in the way ticket 90 wrote its route list by hand
      and then found its own list had missed one. Then two views over the same
      bytes at the same token budget: the first-4096-bytes head the child gets
      today, and the highest-scoring lines that fit the same budget. Reported per
      side: facts kept, facts dropped, tokens spent, token counts in
      `cl100k_base` as ticket 90 counted them. A win is a number, not an
      impression.
- [ ] **The case that decides it is in the measurement explicitly: a stream
      whose interesting line is past the head.** A ranked view and a head are the
      same answer on a stream that fits in 4,096 bytes, so a measurement made
      only on short streams measures nothing. `jq`'s bound is 1,048,576 bytes and
      the three `js*` tools' is 4,194,304, against a 4,096-byte head, so the
      shape of the gap is real; what has to be shown is that a registered tool
      produces a stream of that shape carrying a fact worth having at the far
      end of it. If no registered tool does, that is the result of this ticket
      and it is recorded as one rather than worked around by inventing an input.
- [ ] **Which tools this could buy anything for is answered from the registry
      rather than from Cybermes's toolchain, because a scoring heuristic is what
      one falls back to when no parser exists.** This harness does not read a raw
      stream where it can read a parser: `js_parse`, `js_routes` and `js_map` are
      three readings of one tokeniser shipped as `jsscan.py` and file structured
      answers, `extract_paths.py` and `compare.py` are the deterministic halves
      of two Skills, and every one of those rows names an `analyser`
      (`20260814T050000Z:121-122` adds the column; `20260922T030000Z:55` and
      `:74` make it mandatory for a Skill script and for a stdin-fed tool). A
      run of an analyser is even held to its own answer: the database refuses a
      recorded path from a tool whose registry row names no analyser
      (`20260814T050000Z:386-389`). Reading the six rows, exactly one has no
      analyser: `jq`, whose stdout is JSON the caller already shaped with a
      filter it chose, which is a projection and not a raw stream. State this
      finding plainly in the result: as the registry stands there is no
      registered tool with an unparsed stream, so what phase one is really
      measuring is whether the idea is worth having ready for a scanner-shaped
      tool that does not exist here yet, and adding one is a migration and
      another ticket.
- [ ] **The alternative already in this tree is measured as the third column,
      not argued against.** Reading past the head is already somebody's job:
      `packet.py:1329-1337` says reading past `DEFAULT_EXCERPT` of any Artifact
      is a Tool run rather than a packet read, and names the route --
      "`run_skill_script` hands the program the whole thing untruncated" --
      which `_launch.py:1211-1218` states to the child in the same words. So the
      honest comparison has three columns: the head, a ranked view of the same
      stream, and a purpose-written analyser run over the whole Artifact through
      `run_skill_script`. If the third column wins on the measured stream, the
      answer to this ticket is to write an analyser for that tool and stop, and
      that is a result worth having.
- [ ] **The gate is a number recorded in this file, and phase two does not open
      until it is met.** Phase one closes by writing its table into this ticket
      and stating one of two sentences: either the ranked view kept strictly more
      ground-truth facts than the head at equal tokens on the named stream, with
      the margin and the stream's hash, in which case phase two is unblocked; or
      it did not, in which case this ticket is resolved as a decline, phase two
      is never started, and no schema migration is written. A ranked view that
      ties with the head is a decline, because a selection over evidence that
      buys nothing still costs a reproducibility obligation forever.
- [ ] **Phase two, if it opens: the byte bound is untouched and the view is
      computed over what the bound already admitted.** This is the easiest thing
      to get wrong and it is worth stating twice. Nothing in phase two moves,
      raises, softens or replaces `max_output_bytes`, and nothing ranks a stream
      while it is being read. The ranker runs after the run has closed, over the
      bytes already filed as an Artifact, and its input is exactly what
      `isolation.run_tool` kept. A ranker that reads the live pipe would be a
      bound applied to output already read, which `tool.py:20-21` says is not a
      bound, and it would make the ceiling a function of a scoring function.
- [ ] **Phase two: the full stream is the Artifact and is never the thing that
      gets thinned.** `_keep_stream` (`tool.py:829-849`) files each stream with
      `artifact.filed` (`tool.py:838`, `artifact.py:349`) and links it through
      `LINK` (`tool.py:141-144`) into `tool_run_artifacts`
      (`20260814T030000Z:340`), whose `produced_bytes` (`:351`) and `truncated`
      (`:352`) exist so a reader knows it is holding a prefix of something
      longer. Those rows keep meaning exactly what they mean now. The ranked
      view is an additional Artifact derived from that one, filed the same way
      and linked the same way, and it is never substituted for the stream it was
      derived from anywhere a citation could reach.
- [ ] **Phase two: the view is reproducible, and the ranker's identity is on the
      Tool run.** The precedent is already here twice. `tool_runs.analyser_sha256`
      (`20260814T050000Z:162-163`, comment at `:168-177`) records "the exact
      analyser bytes that ran", so "two runs of one tool over one Artifact are
      comparable"; and a Playbook's `version` is "the digest of the projection,
      which is what the model actually read" (`playbook.py:36`), built from one
      canonical byte sequence so "the digest is a fact about it"
      (`playbook.py:210-211`). The ranked view follows both: the same ranker
      bytes over the same Artifact produce the same view byte for byte, the
      ranker is a file the harness ships and hashes rather than a function
      chosen at runtime, and the hash of the ranker that produced the view is
      recorded on the Tool run that carries it. A view whose producer cannot be
      named later is a selection over evidence with no attribution, and the run
      cannot be re-read.
- [ ] **Phase two: the model is told the count of what it is not being shown,
      in the subtraction shape this harness already uses.** `packet.py:17-21`
      states the rule -- what the model gets instead of the omitted rows is "the
      subtraction, stated" -- and `packet.py:1197-1202` is its concrete shape,
      `total`, `staged`, `matched` and `returned`. The packet's Artifact reader
      already emits an `excerpt_only` marker carrying `staged_bytes` and
      `byte_size` (`packet.py:1344-1347`). What a child gets back from a tool run
      today is weaker than either: `tool.py:547-548` hands it the head and a bare
      boolean `truncated`, and the `outputs` list (`tool.py:544`) carries only
      `stream`, `output_name`, `kind`, `label` and `byte_size`. A ranked view
      must carry lines scored, lines shown and lines dropped as numbers in the
      answer. Stating the subtraction on the existing head costs one field and
      no schema change, and is worth doing whichever way the gate falls.
- [ ] **Phase two: no new egress, and no path out for bytes that did not have
      one.** The ranker is an offline computation over an Artifact this Program
      already holds. It opens no socket, reads no file outside the store, and
      adds no network row to any registry entry. It reads only bytes already
      filed as `agent_visible` (`0005_artifacts_and_provenance.sql:9-18` is where
      that column and its constraint live) and never a `credential_bearing`
      Artifact, and the view it writes is filed through `artifact.filed` with the
      same kind as its source, so whatever redaction the evidence export already
      applies to an Artifact (`evidence.py:103`, applied at `evidence.py:493`)
      applies to the view for the same reason and by the same code. A ranker that
      scored lines and then wrote them somewhere the raw stream does not already
      go would be a leak invented by a summariser, and that is a thing to refuse
      in review.
- [ ] **Phase two: a ranker never competes with a parser.** A ranked view is
      offered only for a tool whose registry row names no analyser. If a tool has
      an analyser, or gains one later, the analyser's structured answer is what
      the child reads and the ranked view is not produced for it at all. This is
      stated as a rule in the code that decides, not as a convention, so a later
      tool cannot quietly acquire a heuristic in place of a parser somebody
      should have written.
- [ ] **Phase two leaves one runnable check behind.** The smallest thing that
      fails if the logic breaks: the same ranker bytes over the same stored bytes
      produce the same view twice, the view is a subset of the lines of its
      source, the stated dropped count plus the shown count equals the scored
      count, and a tool whose row names an analyser gets no view. No fixtures, no
      framework.

## Why this is asked

Ticket 168 read Cybermes end to end and found one idea worth copying, and this
is it, promoted into its own ticket because the operator asked for it as a
build rather than as a paragraph in an evaluation. 168 section 3 states it and
states its cost in the same breath: "Raw to disk in full, ranked subset to the
model, with the count of what was dropped stated ... the cost is not the
scorer, which is under 200 lines; the cost is that a ranked subset is a
*selection over evidence*, and a selection has to be reproducible and
attributable or the run cannot be re-read later."

That is the whole of why this ticket has two phases. The scorer is a weekend.
The obligation it creates is permanent: from the moment a model is handed a
subset of a stream, every conclusion drawn from that stream depends on which
subset, and "which subset" has to be answerable a month later from rows rather
than from memory. This tree already pays that price twice, deliberately, for the
analyser (`tool_runs.analyser_sha256`) and for the Playbook projection
(`playbook.py:36`), and both times the thing being versioned was doing work no
cheaper mechanism could do. A ranked view has to earn the same standing before
it gets the same machinery, and the only way to earn it is a number.

## What is actually there today

There are two truncations and they are commonly confused, including by the
sentence in 168 that started this ticket.

The first is the bound on the process. Every tool's row carries
`max_output_bytes` (`20260814T030000Z:136`), the runtime holds the process to it
while it runs (`isolation.py:968-976`), and it kills a tool that runs past it
(`isolation.py:977-979`). What is kept becomes the Artifact, `produced_bytes`
records what the stream actually reached, and `truncated` records that the two
differ (`20260814T030000Z:351-352`). The migration says why in its own comment:
a stream that overruns "is stored up to the bound and the Artifact row says so,
because a truncated record that admits it is evidence and a silently clipped one
is not" (`:154-157`). None of this is this ticket's business, and phase two must
leave every line of it alone.

The second is the head. `serve` cuts the stored stdout to `excerpt` bytes
(`tool.py:533`) and the child is handed that string plus a boolean
(`tool.py:547-548`). The excerpt is `DEFAULT_EXCERPT`, 4,096 bytes
(`packet.py:90`, passed at `agent.py:1537`). So for a `jq` run that filled its
bound, the model reads 4,096 of 1,048,576 bytes, and what it is told about the
other 1,044,480 is `true`. That is the number this ticket is actually about, and
it is a bigger gap than the one 168 described.

It is not an unnoticed gap. `packet.py:1329-1337` decided it on purpose:
"Reading past `DEFAULT_EXCERPT` of any Artifact is a Tool run, not a packet
read", and "the route that reads all of an Artifact exists and answers a bounded
summary instead of a window". That route is `run_skill_script`, which hands a
harness-shipped program the Artifact whole (`_launch.py:1211-1218`,
`roster.py:1855-1869`). The harness's existing answer to "the interesting line
is line 40,000" is therefore not the head. It is: write a program that reads all
40,000 lines and answers a question about them. A ranked view is the generic
version of that program, for the case where nobody has written the specific one.

## Which tools this buys anything for

Six rows are in `offline_tools`. Five name an analyser and one does not.

`js_parse`, `js_routes` and `js_map` are three readings of one tokeniser
(`jsscan.py`), and the file's own docstring says why it is a parser and not a
scanner: "this file never reports a path because it looks like one. It reports a
path because a call to something that makes requests was given it as an
argument". `extract_paths` and `compare_responses` are the deterministic halves
of two Skills. For all five, ranking their output would be ranking an answer
that is already structured, and the database goes further: a recorded path from
a tool whose row names no analyser is refused outright
(`20260814T050000Z:386-389`).

The one row with no analyser is `jq`. Its stdout is JSON produced by a filter
the caller wrote, which means the caller already selected, and a scorer over it
would be a second selection over the first. So as the registry stands, the
number of registered tools a ranked view would help is zero, and the ticket
should say that out loud rather than smuggle it past the reader. The tools the
idea was invented for -- the subfinder, httpx, katana, ffuf, nuclei and nmap
shapes 168 lists from the other project -- are not in this registry, and none of
them arrives without a migration, a version pattern, a network decision and an
argument grammar. That is the honest scope of this ticket: it prepares an answer
for a tool class this harness has not admitted yet, and phase one is where that
either becomes worth doing or does not.

## What phase two would look like if the gate opens

Three rows and one file, and none of it invents a new concept.

The file is a ranker the harness ships and hashes, in the shape an analyser is
already shipped and hashed (`tool.py:640-683` reads the file off this
installation's disk and carries path, bytes and hash together so a caller cannot
record a run of something it did not stage). The rows are: the derived view as
an Artifact linked to the run like any other stream, the hash of the ranker on
the run, and the three counts in the answer. Nothing about the stream's own
storage changes, nothing about the process bound changes, and the child's answer
gains a field rather than losing one.

The part worth arguing about in review is not the scorer. It is whether an
Observation may ever cite the view rather than the stream. The answer this tree
already implies is no: the view is a reading aid, the Artifact is the evidence,
and a citation resolves to the bytes the run produced. Any design that lets a
claim rest on a subset without naming the ranker that chose it is the thing
criterion 11 exists to prevent.

## Licence, again, because it is the easiest criterion to fail quietly

The constraint is not "attribute Cybermes". It is "copy nothing". PolyForm
Noncommercial 1.0.0 governs the repository, `ATTRIBUTION.md` puts the vendored
`knowledge/` tree under GPL-2.0-or-later and CC BY-NC 4.0 among others, and this
repository ships no LICENSE file of its own, so there is no licence here for any
of those terms to be compatible with. A scoring table is code. A regular
expression is code. A threshold lifted from a file is code. What may be carried
across is what 168 already carried across in English: keep the raw, show a
ranked subset, state the count of the remainder. Anything more specific than
that sentence has to come out of the measurement in criterion 4.
