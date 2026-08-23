# 171 -- An evidence bundle a triager can open

**What to build:** One more file inside the bundle `rk evidence export` already
writes: `traffic.har`, the exchanges the Finding or chain cites, in the HTTP
Archive interchange format, projected from bytes the bundle already carries. A
triager with Burp and no harness can then open the evidence rather than read
about it. No new command, no new store, no new egress, no new bytes.

**Blocked by:** nothing. `rk evidence export` shipped with ticket 43 and every
part this needs is already in the tree.

**Status:** ready-for-agent

This is the third of the four ideas ticket 167
(`docs/specs/production-harness-v2/issues/167-evaluate-huntproxy-against-the-door.md`)
named as worth copying from HuntProxy, promoted into its own implementation
ticket at the operator's instruction. 167 section 3 states the cost as "one
writer over existing Receipt columns. Nothing about the evidence chain moves."
That is still the cost, and the whole of this ticket is holding it there.

## The criteria

The first four are about one thing. A HAR file carries request headers, cookies
and bodies. It is the highest-risk export in this tree, and the way this ticket
fails is not that a field is wrong, it is that a bundle leaves with a
credential in it.

- [ ] **The HAR carries no byte the bundle does not already carry in another
      file.** This is the whole safety argument and every other criterion is
      downstream of it. `_artifacts` (`src/redkraken/evidence.py:471`) already
      loads each cited Agent-view artifact, runs `redact`
      (`src/redkraken/evidence.py:103`) over it against every row of
      `redaction_rules` (`src/redkraken/migrations/0034_reports.sql:328`), and
      writes the result to `artifacts/<sha256>`. The HAR writer reads those
      redacted bytes and the rows `evidence_receipts` already returned. It does
      not open the store a second time, it does not call
      `store.Store.load` (`src/redkraken/store.py:201`) itself, and it does not
      reach any column `evidence_receipts` does not select. A reviewer must be
      able to establish that by reading the writer's arguments, not by reading
      its body.
- [ ] **The unscrubbed form is unreachable from here and stays unreachable.**
      The Agent view is what was already scrubbed twice before it was ever
      stored: `response_for_agent` (`src/redkraken/proxy.py:663`) drops
      target-issued authentication headers, `project_identity_response`
      (`:677`) and `project_identity_request` (`:719`) replace every rendering
      of a leased credential with `REDACTION` (`:364`) through `_scrubbed`
      (`:766`), and `evidence_artifacts`
      (`src/redkraken/migrations/20260821T000000Z__evidence_leaves_with_what_can_be_checked.sql:326`)
      selects only `visibility = 'agent_visible' AND NOT encrypted AND
      purged_at IS NULL`, so a sealed wire artifact cannot come out of it. The
      HAR writer must sit downstream of all of that and must not be given a
      path to the wire view. Adding a parameter that could select the wire side
      is the failure this criterion exists to prevent.
- [ ] **There is a test that seeds a credential-shaped value and asserts it is
      absent from `traffic.har`.** Not a test that the redaction function
      works, which `tests/test_evidence.py` already has. A test that puts a
      value matching a shipped rule -- a `Bearer` token of sixteen or more
      characters, or a three-segment `eyJ...` JWT, both of which
      `redaction_rules` carries -- into an artifact behind a cited Receipt,
      runs the export, reads the emitted `traffic.har` back off disk, and
      asserts the value does not appear in it in any spelling the file could
      hold it in: literal, JSON-escaped, or percent-encoded inside a URL.
- [ ] **No body is base64-encoded in a way that hides it from the residue
      scan.** The shipped verifier rescans every listed file except itself
      against every redaction rule in the manifest (`_residue`,
      `src/redkraken/verifier.py:282`; `_scanned`, `:270`; called at `:158`),
      and `_verified` (`src/redkraken/evidence.py:564`) runs it over the bundle
      before the export reports success. That scan is a regular expression over
      text. HAR permits `content.encoding: "base64"`, and a token inside a
      base64 body is invisible to every rule. So: either the body is emitted as
      text the scan can read, or it is omitted and the omission is stated. The
      same reasoning applies to any JSON escaping the writer chooses -- the
      emitted file must be the text the scan reads, not an encoding of it. A
      test that asserts a bundle carrying a base64-encoded HAR body is refused
      or has that body omitted is what closes this.
- [ ] **The export refuses rather than emitting a secret it could not
      redact.** The refusal already exists and must be inherited rather than
      rebuilt: `_verified` runs the shipped verifier and a
      `redaction_incomplete` problem fails the export. The criterion is that
      `traffic.har` is in `manifest.json`'s `files` list like every other file
      -- written into the `files` dict in `_written`
      (`src/redkraken/evidence.py:338`) before `_manifest`
      (`:510`) indexes it -- so that the rescan covers it automatically and no
      second check has to be remembered. A HAR written outside that dict, or
      written after the manifest, is this criterion failing silently.
- [ ] **No reveal of a scrubbed value is built here.** 167 section 3 names the
      audited explicit reveal as a separate idea worth checking, and it is the
      subject of ticket 172
      (`docs/specs/production-harness-v2/issues/172-a-reveal-of-a-scrubbed-header-that-is-audited.md`),
      not of this one. `traffic.har` emits `[redacted]` where the tree already
      put `[redacted]`, and offers no flag, no argument and no environment
      variable that would change that. If 172 later builds an audited reveal it
      changes what the Agent view contains upstream of here, and this writer
      needs no edit.

- [ ] **It is a projection and the evidence chain does not move.** No migration
      to `receipts` or `artifacts`
      (`src/redkraken/migrations/0005_artifacts_and_provenance.sql:39` and
      `:9`), no new table, no new column, no new writer role, no request sent,
      no artifact stored. The only schema change permitted is two rows in
      `evidence_bundle_files`
      (`.../20260821T000000Z__evidence_leaves_with_what_can_be_checked.sql:181`),
      one for `finding` and one for `chain`, giving the file its `purpose`
      string. `traffic.har` satisfies that table's `path ~ '^[a-z0-9_.]+$'`
      check (`:183`) as written.
- [ ] **Every emitted field is filled from something recorded, or it is
      omitted.** A HAR that fabricates a value to satisfy a schema is worse than
      one that leaves the field out, because a triager reads a filled field as
      a measurement. Where the format demands a member this tree has no fact
      for, the writer emits the format's own "not available" value and nothing
      else. The two sections below say exactly which members those are; the
      implementer checks that list against the published HAR 1.2 field
      definitions rather than against this ticket, because this ticket is not
      the spec.
- [ ] **A blocked Receipt is an entry and not an omission.** `blocked_receipt`
      (`src/redkraken/proxy.py:1744`) writes a Receipt for a request the door
      refused, and `evidence_receipts`
      (`.../20260821T000000Z__evidence_leaves_with_what_can_be_checked.sql:350`)
      returns its `decision` and `lane` alongside the allowed ones. A HAR that
      dropped those rows would tell a triager the run made only the requests
      that succeeded. It is emitted with no response bytes, and the harness
      facts the format has no member for -- Receipt label, `lane`, `decision`,
      `query_sha256` -- go in custom members, which HAR reserves by requiring a
      leading underscore on them.
- [ ] **One writer and no new command.** The writer is a function in
      `src/redkraken/evidence.py` beside `_artifacts`, called from `_written`,
      and its output joins the `files` dict. `rk evidence export`
      (`src/redkraken/cli.py:1560`, dispatched by `_evidence_export`,
      `src/redkraken/cli.py:2847`) gains no flag and no subcommand. This is not
      a viewer, not a UI, and not a second export path.
- [ ] **Two exports of unchanged rows produce the same `traffic.har`.** Ticket
      43's criterion 5 already holds for the rest of the bundle: everything
      outside `manifest.json`'s `packaging` key is deterministic. Header order
      is the transcript's order, entry order is `evidence_receipts`'s
      `ORDER BY r.ts_arrival, r.label`, and no wall clock, no iteration over an
      unordered mapping and no absolute path enters the file.
- [ ] **No HuntProxy source is copied, and the ticket says so where a reader
      will find it.** HAR is a published interchange format with a W3C and
      Chrome DevTools origin, implemented independently by Burp, Firefox,
      Charles, Fiddler and others. Implementing it from the format definition
      is not copying HuntProxy, and `har.rs` is not read, vendored, translated
      or consulted. 167 section 5 records that HuntProxy is Apache-2.0 and that
      this repository has no outbound licence for an inbound one to sit against
      -- which is exactly why this ticket copies an idea and not a file.

## Why this is asked

167 section 3, in full: *"HAR as an export format. It is the one interchange
format the rest of the industry reads, and an evidence bundle that could emit
one would be readable by a triager with Burp and no harness. Cost: one writer
over existing Receipt columns. Nothing about the evidence chain moves."*

167 also recorded that `har` matches nothing under `src/`. That claim was
re-checked before this ticket was written: a word-boundary, case-insensitive
search for `har` across `src/` returns nothing, and every apparent hit in a
plain substring search is `charset`, `charged`, `sharing`, `char` or
`character`. The only `.har` anywhere in the repository is one table cell in
`docs/adr/0005-agent-browser-is-not-adopted-but-its-skill-text-is-kept.md:111`,
listing `.har` files among the evidence forms Agent Browser produces and this
tree does not. Nothing here reads or writes HAR today.

The argument for doing it is not that the format is good. It is that the
recipient of a bundle is a triager on a bug bounty program who has Burp open
and has never heard of this harness, and the bundle currently hands them
`receipts.json` in a shape only this repository defines plus a directory of
raw HTTP transcripts named by hash. Both are honest and neither is loadable.
One more file makes the same evidence openable in the tool the reader already
has, and it costs no new authority because the bytes are the bytes the bundle
already decided may leave.

## What already exists, so this is a file and not a bundle

The instruction was to grep for whatever already produces an evidence bundle
and, if one exists, make HAR a format for it rather than a new bundle. One
exists.

- `rk evidence export` (`src/redkraken/cli.py:1560`) packs one Finding or one
  chain into a directory: the rendered document, the projection it came from,
  the replay specification, the Receipt metadata, the content hashes, the
  redacted Agent-view artifact bytes, and the verifier itself. `evidence.export`
  (`src/redkraken/evidence.py:174`) is the entry point and `_written` (`:338`)
  is where the `files` dict is assembled.
- Which files a bundle owes is a database fact, not a literal in Python:
  `evidence_bundle_files`
  (`.../20260821T000000Z__evidence_leaves_with_what_can_be_checked.sql:181`)
  registers a path and a purpose per subject, `_written` fails the export if
  the registry names a file the export does not write, and
  `check_evidence_export` (`:509`) asks the inverse question as an invariant.
  Giving a bundle a new file is therefore two rows and one writer, which is why
  this shape is cheaper than any command would be.
- Everything packed is redacted once and rescanned. `redact`
  (`src/redkraken/evidence.py:103`) splices all rules in one pass over the
  original text, `_manifest` (`:510`) carries the rules into the bundle so the
  recipient can re-run them, and `_residue`
  (`src/redkraken/verifier.py:282`) does re-run them over every listed file
  before `_verified` (`src/redkraken/evidence.py:564`) lets the export report
  success.
- `rk report finding` and `rk report chain` (`src/redkraken/cli.py:1492`,
  built by `_report_form` at `:2030`) render prose for a human, and
  `rk report soundness` (`:1531`, added by ticket 103) answers a question
  without rendering anything. That precedent was read and it does not fit: a
  HAR is bytes for a tool, not a document for a reader, and the place bytes
  already leave from is the bundle. Putting a second HAR writer behind
  `rk report` would create a second path to the same material with its own
  redaction, and the migration itself already makes the argument against that
  at `.../20260821T000000Z__evidence_leaves_with_what_can_be_checked.sql:385`:
  "the copy that drifts first is always the copy that decides what may leave".

## Which HAR members this tree can fill honestly

Two sources, and no third. `evidence_receipts`
(`.../20260821T000000Z__evidence_leaves_with_what_can_be_checked.sql:350`)
returns exactly `receipt`, `lane`, `decision`, `method`, `scheme`, `host`,
`port`, `path`, `query_sha256`, `status_code`, `arrival`, `request_sha`,
`response_sha`. `evidence_artifacts` (`:326`) returns `receipt`, `direction`,
`sha256`, `byte_size`, `content_type`, and the redacted bytes behind each
`sha256` are what `_artifacts` already packed.

The artifact bytes are a whole HTTP message, not a body. `transcript`
(`src/redkraken/proxy.py:868`) writes the start line, then `name: value` CRLF
per header, then a blank line, then the body. The request start line is
`{method} {origin_form(url)} HTTP/1.1` (`src/redkraken/proxy.py:2897`) and the
response start line is `HTTP/1.1 {status} {reason}`
(`src/redkraken/proxy.py:3078`). So a parse of the packed bytes yields headers,
body and reason phrase; that parse is the writer's main job.

- `log.version`, `log.creator` -- constants. `reporting.VERSION`
  (`src/redkraken/reporting.py:81`) is `rk2-report/1` and `verifier.SCHEMA`
  (`src/redkraken/verifier.py:40`) is `rk2-evidence/1`; either is an honest
  creator version and the manifest already carries both.
- `entry.startedDateTime` -- `evidence_receipts.arrival`, already formatted as
  `YYYY-MM-DDTHH:MM:SSZ` by the function itself. Second resolution, no
  fractional part. That is what was recorded.
- `request.method` -- the `method` column.
- `request.url` -- `scheme`, `host`, `port` and `path` from the row. Whether
  the query belongs on it is decided below.
- `request.httpVersion` and `response.httpVersion` -- `HTTP/1.1`, and it is a
  measurement rather than a default: `tls.ALPN` is `["http/1.1"]`
  (`src/redkraken/tls.py:81`), offered explicitly so nothing else can be
  negotiated, and both transcript start lines say so literally.
- `request.headers` and `response.headers` -- parsed from the packed redacted
  transcript, in the order the transcript holds them.
- `request.headersSize`, `request.bodySize`, `response.headersSize`,
  `response.bodySize` -- computed exactly from the packed bytes, as the length
  of the head up to and including the blank line and the length of what
  follows. These describe the file's own bytes, so they are true of what the
  triager is looking at. Where no artifact was packed for a direction they are
  the format's not-available value.
- `request.postData` -- the request transcript's body, with `mimeType` from its
  own `Content-Type`. Present only when a request artifact was packed.
- `response.status` -- the `status_code` column, and the format's zero for a
  Receipt that has none, which is every blocked and deferred one.
- `response.statusText` -- the reason phrase off the response start line.
  Note it is empty for an exchange made under a leased Identity: `agent_reason`
  is set to the empty string on that path (`src/redkraken/proxy.py:3070-3074`),
  so an empty `statusText` there is the record and not a gap in the writer.
- `response.content.mimeType` -- `evidence_artifacts.content_type`, falling
  back to the transcript's own `Content-Type`.
- `response.content.size` and `response.content.text` -- the packed redacted
  body and its length. `size` must be the length of what the file carries, not
  `evidence_artifacts.byte_size`, which is the pre-redaction Agent-view length
  and is already reported per artifact in `artifacts.json`.
- `entry.cache` -- an empty object. Nothing here records a cache decision and
  the format requires the member, so the empty object is the honest filling.
- Custom `_`-prefixed members -- Receipt label, `lane`, `decision`,
  `query_sha256`, and the Agent-view `sha256` of each direction, so an entry in
  the HAR can be tied back to a row in `receipts.json` and a file under
  `artifacts/`. HAR reserves underscore-prefixed members for exactly this.

## Which HAR members it must omit or leave empty, and why

- `entry.time`, and every member of `entry.timings`. `receipts.waited_ms` is
  recorded (`src/redkraken/proxy.py:3260`) and `ts_egress` with it, but
  `evidence_receipts` selects neither, so no timing reaches this writer.
  Emit the format's not-available value for each required timing member. Do
  not add the columns to `evidence_receipts` to fill them: that widens what
  may leave a bundle in order to populate a field nobody triaging a Finding
  reads, and it is a separate decision from this one.
- `request.queryString`, and the query on `request.url`. This is the sharpest
  one and it has two halves that disagree. `receipts` records `query_sha256`
  and never the query text (`query_sha256`, `src/redkraken/proxy.py:822`), and
  `evidence_exclusions`
  (`.../20260821T000000Z__evidence_leaves_with_what_can_be_checked.sql:389`)
  states that exclusion in every bundle whose exchanges carried one. But the
  packed request transcript's start line is built from `origin_form`
  (`src/redkraken/proxy.py:810`), which does include the query. So the query
  text is already in the bundle, inside `artifacts/<sha256>`, redacted. The
  writer must not reconstruct a query from `query_sha256`, which is impossible
  anyway, and must not silently move query text from the artifact into a
  structured `queryString` array where a reader would take it for a recorded
  field. Emit `queryString` as an empty array, carry `_query_sha256`, and let
  the URL be whatever the packed request line already says. State the decision
  in the file's own comment member so a triager who notices the empty array
  knows why it is empty.
- `request.cookies` and `response.cookies`. Emit empty arrays. A `Cookie` or
  `Set-Cookie` header that survived `response_for_agent` and the two
  projections is already in `headers`; parsing it a second time into a
  structured array gives a leak a second place to hide from a reviewer reading
  the writer, and gives the residue scan a second spelling to miss. The bundle
  already states `identity_material` as an exclusion when any cited exchange
  leased an Identity.
- `response.redirectURL` -- the empty string unless a `Location` header
  survived into the packed response. It often will not: a response header
  carrying credential material is dropped rather than marked, for the reason
  `project_identity_response` gives at `src/redkraken/proxy.py:677`, and
  `/continue/[redacted]` is a `Location` something downstream would follow.
- `entry.serverIPAddress`. `receipts.pinned_ips` exists on the row but
  `evidence_receipts` does not select it, so this writer has no address.
  Omit the optional member rather than adding the column.
- `entry.connection`, `entry.pageref` and `log.pages`. Nothing here records a
  connection identifier or a page grouping. Omit.
- `content.compression`. Not recorded. Omit. Note that the door appends
  `Accept-Encoding: identity` when the caller sent none
  (`src/redkraken/proxy.py:2891-2895`), so the ordinary case has nothing to
  report anyway.
- Anything about a WebSocket. 167 section 1 records that the door cannot carry
  one on purpose, for the ALPN reason above. HAR has no WebSocket member in
  1.2 and this tree has no frames. Nothing to omit and nothing to fake.

## What this is not

It is not a new bundle, not a new command, not a viewer and not a UI. It is not
a replay format: a HAR entry is what one exchange looked like, and what would
have to be re-run to get the Finding again is `spec.json`, which the bundle
already carries. It is not an unsealing: the wire view stays sealed, the
exclusion line saying so stays in every manifest, and a bundle that emitted a
HAR from wire bytes would be the one export in this tree that undid the whole
reason the four hashes are four and not two.
