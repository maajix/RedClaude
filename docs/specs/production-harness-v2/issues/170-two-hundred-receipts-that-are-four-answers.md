# 170 -- Two hundred Receipts that are four answers

The two hundred in the title is HuntProxy's number for a fuzzer's output. It is
not this tree's number and this ticket no longer assumes it is. Phase zero is
what replaces it with a measured one.

**What to build:** Nothing, until a throwaway prototype says there is something
to build. Phase zero is a read-only query and a short script that measures
whether this tree's Receipts collapse at all, and what that collapse is worth in
bytes at the ceiling that actually binds. If it does not clear the thresholds
named in phase zero, this ticket closes with the numbers written into it and no
code is written. A negative phase zero is a result, not a failure.

What is built if -- and only if -- phase zero clears a threshold: a grouping over
Receipts, so that a child reading a run's exchanges is handed the classes they
fall into and the count in each, and can still get back to any individual row it
names. It is a read over rows this tree already holds. It sends nothing, stores
nothing, and adds no table, no column and no Artifact.

**Where this came from:** HuntProxy groups a fuzzer's responses into classes,
and reading that description is what made us look at our own Receipts at all
(`docs/specs/production-harness-v2/issues/167-evaluate-huntproxy-against-the-door.md:247-250`).
That is the whole of the borrowing. Everything below is our own read over our
own rows, derived from this tree's `receipts` columns, and it stands or falls on
this tree's own measurement. No source file is read into this tree, nothing is
translated from Rust or from SQL, and the migration filename 167 cites is cited
the way a book title is cited.

**Blocked by:** nothing. Ticket 167 is the reading this came out of and it is a
reading, not a dependency: 167 changes no code and this ticket does not wait on
its ADR.

**Status:** ready-for-agent

## Phase zero -- the prototype that is allowed to close this ticket

Four criteria, and they come before every criterion in the next section. The
criterion this section replaces is the one that used to read "the measurement
comes first and it is allowed to end the ticket": that sentence was right and it
was one bullet among ten, which is how a ticket ends up built anyway. It is now
the gate.

- [ ] **The prototype changes nothing and is thrown away.** No schema change, no
      migration, no verb, no column, no `state_read_surface` row, no `Contract`,
      no edit under `src/redkraken/`. What phase zero is allowed to be is one
      read-only SQL query and one short script that imports `redkraken.packet`
      to weigh the two views in the encoder the ceiling is actually enforced in
      -- `packet.encode` (`src/redkraken/packet.py:148`), reached through
      `Packet.document_bytes` (`packet.py:339`) and `document_tokens`
      (`packet.py:353`). The script does not survive the ticket. The table it
      produces does, appended to this file under a `## Phase zero: the
      measurement` heading, with the database name, the Program slug and the
      date on it. If the ticket closes negative, that table is the entire
      deliverable and the ticket is done.

- [ ] **It runs against a real Program, and the census that bounds the result is
      stated before the result.** A row census of every database on the local
      harness, 2026-08-24, keyed on `(decision, status_code, artifacts.byte_size)`
      and grouped per Program:

      ```
      database          | Program                     | rows | agent-visible | classes | largest
      ------------------|-----------------------------|------|---------------|---------|--------
      rk2_full54a       | selftest-validate           |   49 |            48 |       4 |      31
      rk2_scratch_106   | selftest-campaign-replay    |   20 |            20 |       6 |       8
      rk2hunt17         | yekta-it                    |   18 |            16 |       9 |       4
      rk2hunt21         | yekta-it-h21                |   14 |            12 |      10 |       4
      rk2_scratch_106   | selftest-campaign-control   |   11 |            11 |       1 |      11
      ```

      Two limits on any result phase zero produces, and both are in that table.
      The largest *real* Program in this tree holds eighteen Receipts, sixteen of
      which an agent read role can see at all -- `proxy_internal` rows are hidden
      from it by migration 0020's restrictive policy, which is why the
      agent-visible column is separate. Eighteen rows is under `DEFAULT_ROWS`
      (`packet.py:87`) and, at the 1,367 bytes an exchange this module measured
      for itself (`packet.py:103-104`), under the 32,768-byte ceiling as well. On
      a Program that shape there are no rows left over for a class to stand for,
      and the compile-side saving this ticket was written around has nothing to
      buy. The larger numbers in the table are all `selftest-*` Programs whose
      bodies are fixture bytes between six and two hundred and ten bytes long,
      so their collapse is the fixture's and not a target's: `selftest-campaign-control` putting eleven
      rows in one class is a statement about the fixture. If the prototype wants
      a bigger populated Program it builds one the way the suite does --
      `tests/test_vertical.py:50` names the slug, `tests/test_database.py:162-166`
      names the two environment variables that point the harness at a disposable
      superuser, and `tests/test_database.py:293-302` is why a default run leaves
      nothing behind: `tearDownModule` drops the database. A synthetic Program
      cannot settle the question and the write-up must say so where it reports
      one.

- [ ] **Both loci are measured, separately, because the numbers are what choose
      between them.** 167 named two places this can live and could not pick one.
      Phase zero picks, and it picks with two different measurements because the
      two loci buy two different things.
      **Compile side**, `packet.compile`: a class can stand for rows that never
      fit, so what changes is how many exchanges the packet *reaches*. Measure
      the count of exchanges represented under identical `Limits`
      (`byte_limit=65536`, `token_limit=8192`, so `byte_ceiling` is 32,768 --
      `packet.py:88-89` and `Limits.byte_ceiling` at `packet.py:179-181`),
      grouped against ungrouped.
      **Reader side**, `packet.Reader.receipts` (`packet.py:1133-1169`): the rows
      are already staged, so grouping cannot increase reach and the only thing it
      can change is what one answer costs. Measure the serialized bytes of
      `Answer.as_dict()` (`packet.py:1070-1082`) for the same staged rows,
      grouped against ungrouped, in `packet.encode`.
      Record both in the same table, in bytes and in the tokens
      `document_tokens` derives from them. Neither number substitutes for the
      other and the write-up may not report one and call it the result.

- [ ] **The gate, with both thresholds named on 2026-08-24, before any encoder
      measurement was taken.** They are written here so that a number arriving
      later cannot be argued into passing.
      **Gate A, compile side: the grouped view must stand for at least twice the
      exchanges the ungrouped view carries under the same 32,768-byte ceiling,
      AND the absolute difference must be at least 25 exchanges.** Both halves,
      not either. Twenty-five because 32,768 / 1,367 is 23.9, so twenty-three
      exchanges is a whole packet spent on Receipts and nothing else, and a
      saving smaller than that is one a hunter already buys today by asking for a
      single refresh at `REFRESH_BYTES = 8192` (`packet.py:108`), which costs no
      code at all. Twice because below that the same reach is available by moving
      a section's share of a constant ceiling, and moving a constant is not a
      feature.
      **Gate B, reader side: the grouped answer must serialize to at most half
      the bytes of the ungrouped answer over the identical staged rows.** Half is
      where a hunter gets a second read out of the budget that bought one.
      **What each outcome does.** Both gates fail: the ticket closes, the table
      stays, nothing is built, and the closing note says which number missed by
      how much. Only A passes: the compile version is built and the reader
      version is not. Only B passes: the reader version is built and the compile
      version is not. Both pass: the reader version is built first, because it is
      the smaller one and because a compile-side change that has not been tried
      at the reader is a bigger diff bought on a guess. In no outcome is the
      losing locus built speculatively.
      Said plainly, so the prototype is not run as a formality: on the census
      above Gate A cannot be reached by any Program this tree currently holds,
      because eighteen rows already fit and a class can only pay for rows that do
      not. Phase zero's job on the compile side is to say that in the encoder's
      own numbers, or to find that this reading of the census is wrong.

## After phase zero

Every criterion below is conditional on phase zero clearing a gate, and each one
applies only to the locus that gate selected. If phase zero closes the ticket,
none of them is a criterion at all -- they are the description of a thing that
was measured and not built, kept so the measurement has something to be about.

- [ ] **Conditional on phase zero. Nothing here is copied from HuntProxy, and
      the ticket says so on the record.** The credit is the one sentence at the
      top of this file and the borrowing goes no further than it: no HuntProxy
      source file is read into this tree, no HuntProxy text is quoted into a
      docstring, a comment or a migration, and nothing is translated from Rust or
      from SQL. 167's licence section
      (`docs/specs/production-harness-v2/issues/167-evaluate-huntproxy-against-the-door.md:304-319`)
      is why that is worth writing down rather than assuming: this repository
      ships no `LICENSE` file, so it has no outbound licence for an inbound one
      to be checked against, and the cheapest way to keep that from mattering is
      to copy nothing.

- [ ] **Conditional on phase zero. The key is not assumed, and the obvious
      candidate is already known to be weak.** `response_agent_sha`
      (`src/redkraken/migrations/0005_artifacts_and_provenance.sql:61`) looks like
      a free collapse key and is not one: it is the sha256 of the whole
      agent-visible message, built by `transcript()` (`src/redkraken/proxy.py:868-877`)
      from the status line, every header and the body, hashed at `proxy.py:3093`
      and `proxy.py:3094`. The only headers removed on the way are the six in
      `WIRE_RESPONSE_HEADERS` (`proxy.py:366-375`, applied by `response_for_agent`
      at `proxy.py:663-674`), all of them target-issued authentication material.
      `Date` survives. That is not a prediction any more -- `rk2hunt17` holds
      eighteen Receipts and thirteen distinct `response_agent_sha` values across
      the sixteen that carry one, and two of its classes are exactly the failure:
      three rows at 200 with a 43,923-byte body and three distinct hashes, three
      rows at 301 with a 519-byte body and three distinct hashes. The key this
      ticket therefore starts from is `(decision, status_code, response
      transcript byte size)`, with `response_agent_sha` used only as an
      exact-identity refinement inside a class -- in the same Program the four
      rows at 200 with a 41,077-byte body share one hash, so the refinement is
      real and it is a refinement, not the key. `decision` is
      `0005_artifacts_and_provenance.sql:45`, `status_code` is `:55`, and the
      transcript byte size is `artifacts.byte_size` (`:11`, written at
      `proxy.py:3290`), reachable by the `response_agent_sha` foreign key the
      receipts table already declares.

- [ ] **Conditional on phase zero. The grouping is a read and the criterion is
      stated as a prohibition.** No new egress: nothing in this ticket reaches a
      target, and the door is not called. No new store: no table, no column, no
      view that materialises, no Artifact, no file. Nothing writes. The
      `Contract` for the read that answers this declares `reads` and no `writes`,
      and its `reads` tuple does not grow past the tables the state read surface
      already registers -- `v_records` and `receipts` are already on
      `mcp__rk2__get_receipts` (`src/redkraken/roster.py:1233-1241`), and
      `v_artifacts` is already registered per column
      (`src/redkraken/migrations/20260810T151500Z__program_scoped_artifacts.sql:187-195`,
      with `byte_size` at `:191` and its surface row at `:218`). If the
      implementation finds itself adding a `state_read_surface` row, it has left
      the ground this ticket claimed.

- [ ] **Conditional on phase zero. The model is told what it is not seeing, in
      numbers.** Every grouped answer states the class count and, per class, the
      member count. That is not a decoration on the answer, it is the answer: a
      child shown four classes and no counts has been told that four kinds of
      thing happened and not that one of them happened a hundred and ninety-six
      times, and the second sentence is the one a hunter acts on. The four counts
      `Answer` already carries -- `total`, `staged`, `matched`, `returned`
      (`src/redkraken/packet.py:1050-1082`) -- stay exactly as they are and the
      class counts sit beside them, because they answer a different subtraction:
      those say how many rows the packet never had, these say how many rows this
      class stands for.

- [ ] **Conditional on phase zero. Every class is re-expandable, and the labels
      are how.** A class carries the labels of its members, not just a
      representative. A summary a child cannot walk back into rows is evidence
      loss, and this tree already has both verbs that walk it back:
      `mcp__rk2__get_receipts` takes `receipt_labels` for rows the packet staged
      (`roster.py:1238`), and `refresh_packet` takes them for rows it did not,
      because `receipts` is one of the three refreshable sections
      (`packet.py:67`, mapped at `packet.py:76`). Nothing new is needed to make
      the expansion work and nothing new should be written for it. A class whose
      member list would not fit is bounded and says it was bounded, in the
      `packet_bound` and `limit` words `_page` already uses
      (`packet.py:1296-1316`), rather than in a new vocabulary.

- [ ] **Conditional on phase zero. The run records which grouping produced the
      view.** Two acceptable shapes and the ticket must pick one rather than
      leaving it implied. Either the grouping is singular -- one key, no
      argument, no choice -- in which case which grouping ran is answered by the
      build manifest, since the Door refuses to listen unless the modules on disk
      match the revision they were cut from (`CONTEXT.md:858-868`); or the key
      becomes an argument the child chooses, in which case the chosen key is
      recorded on the run beside `facts["agent_run"]["tools_called"]`
      (`src/redkraken/execution.py:2278`), because `Surface.serve` collects verb
      names and nothing else (`src/redkraken/_launch.py:271-274`, read out into
      the run's facts at `_launch.py:2265`) and a run that grouped two different
      ways would otherwise leave one indistinguishable record. The singular shape
      is the smaller one and is the default; the argument shape has to earn
      itself against phase zero's numbers.

- [ ] **Conditional on phase zero. No secret leak, and the check is that the key
      adds nothing.** Every component of the grouping key is already a field of
      the receipt record a child reads: `decision` at
      `src/redkraken/migrations/20260929T030000Z__a_range_is_scope_and_a_tier_never_was.sql:500`,
      `status_code` at `:507`, `response_agent_sha` at `:514`, in the live
      `v_records` definition that starts at `:375`. A size read off
      `artifacts.byte_size` is a number the model already sees on any Artifact
      record it holds (`packet.py:620-635`, `byte_size` at `:630`) and that
      `http_request` already hands back for its own exchange (`_launch.py:1641`).
      Nothing derived from body content goes into a class label, a class name or
      a class key. The door redacts what a target issued as a credential before
      the agent-side transcript is ever hashed (`proxy.py:663-674`,
      `proxy.py:677-701`) and `_scrubbed` (`proxy.py:766-777`) is what takes a
      reflected secret out of a header on that side; a grouping that put a
      substring of a body into a key would be reaching around all of it.

- [ ] **Conditional on phase zero. Where the grouping runs was decided by phase
      zero and is not reopened.** The two loci and what each buys are set out in
      phase zero's third criterion, and the gate's outcome table is what
      selects. Whichever locus a gate selected is the one that is built; the
      other is not built speculatively, and it is not built later on the argument
      that the first one worked. Reopening the choice means running the
      prototype again against the numbers that changed.

- [ ] **Conditional on phase zero. Nothing already groups Receipts, and the
      ticket states what was checked before it added one.** The only aggregate
      over `receipts` in this tree is `check_receipt_integrity`
      (`src/redkraken/migrations/0022_hooks_and_receipts.sql:385-402`), which
      groups agent-lane rows by host and path to count egress with no tool run
      behind it. That is an operator integrity check, it runs on the runtime's
      connection, and no model-facing verb reaches it. `hypotheses`, `reports`
      and the eval store each have a dedup key (`0007_epistemics.sql:77-80`,
      `0034_reports.sql:805-813`, `0033_eval_store.sql:49`) and none of them
      touches an exchange. If a re-check at implementation time finds a grouping
      this reading missed, this ticket becomes "extend that one" and the new code
      is deleted.

- [ ] **Conditional on phase zero. One runnable check.** A test that fixes a set
      of receipt records with a known collapse -- one class of many members, one
      class of one -- and asserts the class count, the per-class member count,
      and that the member labels of every class re-read as those rows. If the
      grouping breaks, that test fails. No fixture tree, no suite per function.
      Phase zero's script is not this test and does not become it: the script is
      thrown away and this is written against whatever was built.

## Why this is asked

The operator read 167 and pulled one bullet out of it into a ticket of its own.
The premise is a token argument and it is worth stating in this tree's terms
rather than in the terms it arrived in. A hunter's context is bounded twice: the
packet it starts with is fitted against 32,768 bytes and fifty rows per section
before its container starts (`packet.py:85-91`, `packet.py:164-181`), and a
refresh is bounded again at 8,192 (`packet.py:108`, and the comment above it at
`packet.py:93-107` says why the second number is not the first). Receipts are
the section that grows fastest, because one `http_request` call mints one, and
`packet.py:100-107` is the module's own measurement of what that costs: one
exchange is 1,367 bytes of a ceiling that is 32,768 for everything the child
knows, including the attack surface and the hypotheses it is meant to be
reasoning about.

Against that, a hunter that sent forty requests and got thirty-eight identical
404s has spent most of a packet learning one fact. A grouping is the cheapest
possible answer to it, because it needs nothing this tree does not already have:
the rows exist, the columns exist, the labels that walk back to the rows exist,
and the counts vocabulary that says what was left out exists.

That is the argument, and phase zero exists because the argument has already
been dented twice by this tree's own numbers. The first dent is the key: the
hash that looked free groups nothing, because `Date` is inside it. The second is
the ceiling, and it is the larger one. The saving a grouping buys at compile is
the difference between the exchanges that fit and the exchanges there are, and
in this tree the largest real Program has eighteen Receipts. They all fit. The
model never sees two hundred Receipts because a Program that minted two hundred
has never existed here, and "two hundred responses that collapse into four
classes" is a claim about a fuzzer's output in another program -- this tree has
no fuzzer, `fuzz` appears nowhere under `src/redkraken/`
(`167:173-176`). Whether this tree's Receipts collapse enough to be worth code
is an open question with a real answer, and the honest order is to measure
before building.

## What the tree already holds

- The receipts table and its columns: `0005_artifacts_and_provenance.sql:39-65`.
  `decision` (`:45`), `reason` (`:46`), `method` (`:48`), `scheme` (`:49`),
  `host` (`:50`), `path` (`:52`), `status_code` (`:55`), `waited_ms` (`:58`),
  `response_agent_sha` (`:61`), which is a foreign key into `artifacts(sha256)`
  and therefore into `artifacts.byte_size` (`:11`) and `content_type` (`:12`).
- The record a child actually reads, which is narrower than the table: the
  receipt branch of `v_records`, live at
  `20260929T030000Z__a_range_is_scope_and_a_tier_never_was.sql:493-519`. It
  carries label, lane, purpose, decision, reason, method, scheme, host, port,
  path, status_code, identity_label, tool_run_label, scope_class, intercepted,
  transport_citable, request_agent_sha, response_agent_sha, waited_ms and
  ts_arrival. It does not carry a body length, which is why a length key needs
  the `artifacts` join and why that join is worth naming rather than assuming.
- The read: `mcp__rk2__get_receipts`, contract at `roster.py:1233-1241`, member
  of `state.read` at `roster.py:868`, served from `_launch.py:1321` by
  `packet.Reader.receipts` (`packet.py:1133-1169`), page ceiling `_PAGE = (1, 200)`
  at `roster.py:1004` and a default page of 25 at `packet.py:91`.
- The answer shape: `Answer` at `packet.py:1050-1082`, four counts and a list of
  omission markers, produced by `_page` at `packet.py:1296-1316`.
- The way back: `receipt_labels` on the read itself (`roster.py:1238`) and
  `refresh_packet` for rows minted after the compile (`packet.py:67`, `:76`).
- The one aggregate that exists, and it is not this:
  `check_receipt_integrity` (`0022_hooks_and_receipts.sql:385-402`).
- The Programs that exist to measure against, and how small they are: the census
  in phase zero's second criterion.

## What this ticket must not become

A summariser. The distinction is sharp and it is the whole reason the
re-expansion criterion is written the way it is. A grouping states a fact about
rows -- these forty share a status, a length and a decision -- and hands back
the labels, so a child that disagrees with the grouping can read the rows and be
right. A summary states a conclusion about rows, and a child that disagrees with
it has nothing to check. `CONTEXT.md:650-653` defines a Receipt as the proxy's
authoritative record of one exchange; a class is a statement about a set of
those records and never a replacement for one.

It must also not become a second answer to "what did we send". The grouping
computes and returns; it does not persist a class, does not label a class, and
does not let a class be cited. An Observation cites a Receipt, and it goes on
citing a Receipt.

And it must not become a ticket that was built because it was written down. The
gate in phase zero is the whole point of the ticket having been rewritten, and a
build that starts before those two numbers exist has skipped the only part of
this ticket that was ever load-bearing.

## Notes

Sibling of the other three ideas 167 named. The plugin-contract one
(`167:232-246`) is a design change and is not this. HAR export (`167:251-254`)
is a writer over the same columns and is a separate ticket. The audited explicit
reveal (`167:255-259`) is a question about what this tree already scrubs.

Not blocked by 167's ADR. 167 can decline HuntProxy entirely and this ticket is
unaffected, because nothing here depends on that program existing: the rows are
this tree's rows and the reason to group them was measurable before anyone read
a Rust repository -- which is exactly what phase zero does.
