# 170 -- Two hundred Receipts that are four answers

**What to build:** A grouping over Receipts, so that a child reading a run's
exchanges is handed the classes they fall into and the count in each, and can
still get back to any individual row it names. It is a read over rows this tree
already holds. It sends nothing, stores nothing, and adds no table, no column
and no Artifact.

**Blocked by:** nothing. Ticket 167 is the reading this came out of and it is a
reading, not a dependency: 167 changes no code and this ticket does not wait on
its ADR.

**Status:** ready-for-agent

- [ ] **Nothing here is copied from HuntProxy, and the ticket says so on the
      record.** No HuntProxy source file is read into this tree, no HuntProxy
      text is quoted into a docstring, a comment or a migration, and nothing is
      translated from Rust or from SQL. What 167 took from that repository is
      one sentence of description in its own words
      (`docs/specs/production-harness-v2/issues/167-evaluate-huntproxy-against-the-door.md:247-250`):
      *"Fuzz response grouping (`011_fuzz_response_groups.sql`). Not the fuzzer
      -- the grouping. Two hundred responses that collapse into four classes is
      a token argument, and it applies to Receipts this tree already has."* The
      migration filename is cited the way a book title is cited. It is a
      pointer to where somebody else solved a problem, not a file to port, and
      this implementation is derived from this tree's own `receipts` columns and
      from nothing else. 167's licence section (`:304-319`) is why that
      distinction is worth writing down rather than assuming: this repository
      ships no `LICENSE` file, so it has no outbound licence for an inbound one
      to be checked against, and the cheapest way to keep that from mattering is
      to copy nothing.

- [ ] **The measurement comes first and it is allowed to end the ticket.** On a
      real Program's Receipts -- `rk2hunt8` and `rk2hunt9` are the two ticket
      150 measured against and are named here for that reason
      (`docs/specs/production-harness-v2/issues/150-nothing-records-which-verbs-a-child-reached-for.md:10-12`)
      -- record three numbers before any code is written: how many `receipts`
      rows the Program holds, how many classes the candidate key puts them in,
      and what the records for those rows weigh against what the classes would
      weigh, in `packet`'s own encoder rather than in an estimate. If the answer
      is that a real Program holds forty Receipts and they fall into thirty-nine
      classes, that is the result, it is written into this ticket, and nothing
      is built. No saving may be asserted anywhere in the implementation, the
      docstrings or the commit message that this measurement did not produce.

- [ ] **The key is not assumed, and the obvious candidate is already known to be
      weak.** `response_agent_sha`
      (`src/redkraken/migrations/0005_artifacts_and_provenance.sql:61`) looks
      like a free collapse key and is not one: it is the sha256 of the whole
      agent-visible message, built by `transcript()`
      (`src/redkraken/proxy.py:868-877`) from the status line, every header and
      the body, hashed at `proxy.py:3078` and `proxy.py:3094`. The only headers
      removed on the way are the six in `WIRE_RESPONSE_HEADERS`
      (`proxy.py:366-375`, applied by `response_for_agent` at
      `proxy.py:663-674`), all of them target-issued authentication material.
      `Date` survives. So two byte-identical 404 bodies one second apart hash
      differently, and a grouping keyed on that hash alone would report two
      hundred classes for two hundred rows. The key this ticket starts from is
      therefore `(decision, status_code, response transcript byte size)`, with
      `response_agent_sha` used only as an exact-identity refinement inside a
      class, and the measurement above is what says whether that holds.
      `decision` is `receipts:45`, `status_code` is `receipts:55`, and the
      transcript byte size is `artifacts.byte_size`
      (`0005_artifacts_and_provenance.sql:11`, written at `proxy.py:3290`),
      reachable by the `response_agent_sha` foreign key the receipts table
      already declares.

- [ ] **The grouping is a read and the criterion is stated as a prohibition.**
      No new egress: nothing in this ticket reaches a target, and the door is
      not called. No new store: no table, no column, no view that materialises,
      no Artifact, no file. Nothing writes. The `Contract` for the read that
      answers this declares `reads` and no `writes`, and its `reads` tuple does
      not grow past the tables the state read surface already registers --
      `v_records` and `receipts` are already on
      `mcp__rk2__get_receipts` (`src/redkraken/roster.py:1233-1241`), and
      `v_artifacts` is already registered per column
      (`src/redkraken/migrations/20260810T151500Z__program_scoped_artifacts.sql:187-196`,
      with `byte_size` at `:191` and its surface row at `:218`). If the
      implementation finds itself adding a `state_read_surface` row, it has left
      the ground this ticket claimed.

- [ ] **The model is told what it is not seeing, in numbers.** Every grouped
      answer states the class count and, per class, the member count. That is
      not a decoration on the answer, it is the answer: a child shown four
      classes and no counts has been told that four kinds of thing happened and
      not that one of them happened a hundred and ninety-six times, and the
      second sentence is the one a hunter acts on. The four counts `Answer`
      already carries -- `total`, `staged`, `matched`, `returned`
      (`src/redkraken/packet.py:1050-1081`) -- stay exactly as they are and the
      class counts sit beside them, because they answer a different subtraction:
      those say how many rows the packet never had, these say how many rows this
      class stands for.

- [ ] **Every class is re-expandable, and the labels are how.** A class carries
      the labels of its members, not just a representative. A summary a child
      cannot walk back into rows is evidence loss, and this tree already has
      both verbs that walk it back: `mcp__rk2__get_receipts` takes
      `receipt_labels` for rows the packet staged (`roster.py:1238`), and
      `refresh_packet` takes them for rows it did not, because `receipts` is one
      of the three refreshable sections (`packet.py:67`, mapped at `packet.py:76`).
      Nothing new is needed to make the expansion work and nothing new should be
      written for it. A class whose member list would not fit is bounded and
      says it was bounded, in the `packet_bound` and `limit` words `_page`
      already uses (`packet.py:1296-1316`), rather than in a new vocabulary.

- [ ] **The run records which grouping produced the view.** Two acceptable
      shapes and the ticket must pick one rather than leaving it implied. Either
      the grouping is singular -- one key, no argument, no choice -- in which
      case which grouping ran is answered by the build manifest, since the Door
      refuses to listen unless the modules on disk match the revision they were
      cut from (`CONTEXT.md:858-868`); or the key becomes an argument the child
      chooses, in which case the chosen key is recorded on the run beside
      `facts["agent_run"]["tools_called"]`
      (`src/redkraken/execution.py:2278`), because `Surface.serve` collects verb
      names and nothing else (`src/redkraken/_launch.py:2265`) and a run that
      grouped two different ways would otherwise leave one indistinguishable
      record. The singular shape is the smaller one and is the default; the
      argument shape has to earn itself against the measurement.

- [ ] **No secret leak, and the check is that the key adds nothing.** Every
      component of the grouping key is already a field of the receipt record a
      child reads: `decision` at
      `src/redkraken/migrations/20260929T030000Z__a_range_is_scope_and_a_tier_never_was.sql:500`,
      `status_code` at `:507`, `response_agent_sha` at `:514`, in the live
      `v_records` definition that starts at `:375`. A size read off
      `artifacts.byte_size` is a number the model already sees on any Artifact
      record it holds (`packet.py:620-635`) and that `http_request` already
      hands back for its own exchange (`_launch.py:1641`). Nothing derived from
      body content goes into a class label, a class name or a class key. The
      door redacts what a target issued as a credential before the agent-side
      transcript is ever hashed (`proxy.py:663-674`, `proxy.py:677-701`) and
      `_scrubbed` (`proxy.py:766-777`) is what takes a reflected secret out of a
      header on that side; a grouping that put a substring of a body into a key
      would be reaching around all of it.

- [ ] **Where the grouping runs is decided by the measurement, not before it.**
      There are exactly two places it can live and they buy different things.
      In `packet.Reader`, over the rows the packet staged: no SQL, no new query,
      no surface row, and bounded by what the compile already kept -- fifty rows
      per section (`packet.py:87`) fitted against a 32,768-byte ceiling
      (`packet.py:85`, `:88-89`, and `Limits.byte_ceiling` at `packet.py:179-181`).
      Or at compile, so a class can stand for rows that never fit, which is the
      version that delivers the sentence 167 wrote: `packet.py:103-107` records
      that one `authentication` run's rows weigh 10 x 1,367 + 16 x 1,269 =
      33,974 bytes, already over the whole packet's ceiling. The reader version
      is smaller and is where to start; the compile version is what the
      measurement either justifies or does not. Whichever is built, the other is
      not built speculatively.

- [ ] **Nothing already groups Receipts, and the ticket states what was checked
      before it added one.** The only aggregate over `receipts` in this tree is
      `check_receipt_integrity`
      (`src/redkraken/migrations/0022_hooks_and_receipts.sql:385-402`), which
      groups agent-lane rows by host and path to count egress with no tool run
      behind it. That is an operator integrity check, it runs on the runtime's
      connection, and no model-facing verb reaches it. `hypotheses`, `reports`
      and the eval store each have a dedup key
      (`0007_epistemics.sql:75`, `0034_reports.sql:805`, `0033_eval_store.sql:174`)
      and none of them touches an exchange. If a re-check at implementation time
      finds a grouping this reading missed, this ticket becomes "extend that one"
      and the new code is deleted.

- [ ] **One runnable check.** A test that fixes a set of receipt records with a
      known collapse -- one class of many members, one class of one -- and
      asserts the class count, the per-class member count, and that the member
      labels of every class re-read as those rows. If the grouping breaks, that
      test fails. No fixture tree, no suite per function.

## Why this is asked

The operator read 167 and pulled this bullet out of it into a ticket of its own.
The premise is a token argument and it is worth stating in this tree's terms
rather than in the terms it arrived in. A hunter's context is bounded twice: the
packet it starts with is fitted against 32,768 bytes and fifty rows per section
before its container starts (`packet.py:85-91`, `packet.py:164-181`), and a
refresh is bounded again at 8,192 (`packet.py:108`, and the comment above it
at `packet.py:93-107` says why the second number is not the first). Receipts are
the section that grows fastest, because one `http_request` call mints one, and
`packet.py:103-107` is the module's own measurement of what that costs: one
exchange is 1,367 bytes of a ceiling that is 32,768 for everything the child
knows, including the attack surface and the hypotheses it is meant to be
reasoning about.

Against that, a hunter that sent forty requests and got thirty-eight identical
404s has spent most of a packet learning one fact. A grouping is the cheapest
possible answer to it, because it needs nothing this tree does not already have:
the rows exist, the columns exist, the labels that walk back to the rows exist,
and the counts vocabulary that says what was left out exists.

The reason it is a ticket rather than a patch is the second half of 167's
sentence. "Two hundred responses that collapse into four classes" is a claim
about a fuzzer's output, and this tree has no fuzzer -- `fuzz` appears nowhere
under `src/redkraken/` (`167:173-176`). Whether this tree's Receipts collapse at
all is an open question, and the honest order is to measure before building.

## What the tree already holds

- The receipts table and its columns: `0005_artifacts_and_provenance.sql:39-65`.
  `decision` (`:45`), `reason` (`:46`), `method` (`:48`), `scheme` (`:49`),
  `host` (`:50`), `path` (`:52`), `status_code` (`:55`), `waited_ms` (`:58`),
  `response_agent_sha` (`:61`), which is a foreign key into `artifacts(sha256)`
  and therefore into `artifacts.byte_size` (`:11`) and `content_type` (`:12`).
- The record a child actually reads, which is narrower than the table: the
  receipt branch of `v_records`, live at
  `20260929T030000Z__a_range_is_scope_and_a_tier_never_was.sql:493-517`. It
  carries label, lane, purpose, decision, reason, method, scheme, host, port,
  path, status_code, identity_label, tool_run_label, scope_class, intercepted,
  transport_citable, request_agent_sha, response_agent_sha, waited_ms and
  ts_arrival. It does not carry a body length, which is why a length key needs
  the `artifacts` join and why that join is worth naming rather than assuming.
- The read: `mcp__rk2__get_receipts`, contract at `roster.py:1233-1241`, member
  of `state.read` at `roster.py:868`, served from `_launch.py:1321` by
  `packet.Reader.receipts` (`packet.py:1133-1169`), page ceiling `_PAGE = (1, 200)`
  at `roster.py:1004` and a default page of 25 at `packet.py:91`.
- The answer shape: `Answer` at `packet.py:1050-1081`, four counts and a list of
  omission markers, produced by `_page` at `packet.py:1296-1316`.
- The way back: `receipt_labels` on the read itself (`roster.py:1238`) and
  `refresh_packet` for rows minted after the compile (`packet.py:67`, `:76`).
- The one aggregate that exists, and it is not this:
  `check_receipt_integrity` (`0022_hooks_and_receipts.sql:385-402`).

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

## Notes

Sibling of the other three ideas 167 named. The plugin-contract one
(`167:232-246`) is a design change and is not this. HAR export (`167:251-254`)
is a writer over the same columns and is a separate ticket. The audited explicit
reveal (`167:255-259`) is a question about what this tree already scrubs.

Not blocked by 167's ADR. 167 can decline HuntProxy entirely and this ticket is
unaffected, because nothing here depends on that program existing: the rows are
this tree's rows and the reason to group them was measurable before anyone read
a Rust repository.
