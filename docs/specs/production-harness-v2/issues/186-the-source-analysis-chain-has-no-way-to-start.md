# 186 — The source analysis chain has no way to start

**What to build:** a route from an exchange that fetched a JavaScript bundle to
a `js_routes` run over it. Every part of that route exists except the parts that
join them, and the measurement below is what a campaign looks like without it.

**Blocked by:** nothing.

**Status:** resolved

## What is already built

`jsscan.py` is 981 lines and answers three questions about a source Artifact:
what it is made of (`js_parse`), which request paths it actually calls with the
call site that grounds each one (`js_routes`), and what a source map carries
(`js_map`). It tokenises rather than pattern-matching, which is the distinction
the published tools in this area are separated by. `20260814T050000Z` registered
all three as offline tools, granted them to `js_analyst`, wrote the grounding
check that refuses a route claim with no run behind it, and `analyse-source`
teaches the technique.

Against a single-page application this is the whole of endpoint enumeration.
The routes are in the bundle; the bundle is one request away.

## What it produced

Database `rk2here`, 2026-08-25, 23 recon Tasks over 108 configured
applications. `SELECT count(*) FROM tool_runs WHERE offline_tool IS NOT NULL`
answers `0`. Eight applications were recorded as `spa_surface` and fourteen as
`api_surface`, so the surface where this technique applies was found and then
not read.

## The three joins that are missing

**1. Nothing opens the Task.** `20261008T000000Z` refuses a suggested `analyze`
Task as `unopenable_kind`, and says why in the row itself: *the roster gives
analyze to js_analyst, which holds no net.request, and the slice that dispatches
a Task serves one target request*. `STARTED` resolves a Task's target through
`rk2_subject_url(e.id)`, and an analysis has no target to resolve. So
`js_analyst` has a role, a model, a skill, three tools and no Task it can ever
be given.

**2. Nothing files the bytes as source.** `hold_receipt_transcripts()` files
both halves of every exchange as reference kind `runtime`.
`offline_tool_arguments` declares `artifact_kind = 'source'` for all three
analysers, and `check_source_citation` refuses a citation whose reference kind
is anything else. The only writer of a `source` reference is
`rk artifact put --kind source`, which is an operator at a terminal. In
`rk2here`: 44 references, all `runtime`, none `source`.

**3. The bytes are not the bundle.** Every Artifact the door stores is
`content_type = 'message/http'` -- the whole transcript, headers and body
together. A tokeniser pointed at that is reading a response, not a source file,
and the content type a rule would key on is the transcript's rather than the
body's.

## Why this is one ticket and not three

Any one of them alone leaves the capability dark, and each has more than one
possible answer, so choosing them separately would mean choosing twice. The
cheapest shape found so far, recorded here as a starting point rather than as a
decision:

- file the response body as its own Artifact with its own content type, which
  answers **3** and gives **2** something to key on;
- have `hold_receipt_transcripts()` add a second `source` reference for a body
  whose content type is a source type -- `artifact_references` is unique on
  `(program_id, sha256, kind)` and both descriptions are true of the same bytes;
- grant the three analysers to `recon` rather than opening `analyze`, which
  makes **1** moot: `recon` already dispatches against an application, already
  holds `exec.tool_run`, and the tools need no network.

The last one contradicts `20260814T050000Z`'s stated reason for granting them to
the analyst alone -- *a second role holding these tools would be a second place
a source conclusion could come from without the roster having said so*. That
reason was written before `analyze` was known to be unopenable, and the choice
between honouring it and reaching the capability is what this ticket has to
settle.

## What it is not

Not a wordlist and not a scanner. Every path this would recover is a path the
application's own build wrote down, cited to the bytes it was read from. See
`187` for the separate question of discovery against a list.


## Answer

Reachable as of `20261117T000000Z` and `20261118T000000Z`. Measured first, in
`/tmp/rk-186-prototype/`, because one of the three claims above was wrong.

**Join 2 was as described.** `receipts` now carries `response_content_type` --
the media type the target declared, parameters dropped and lowercased -- written
by the door, which is the only party that ever reads it. `hold_receipt_transcripts`
files a second reference of kind `source` over the response half when that type
is one the three analysers read. Two rows over one hash, both true: `runtime`
says this harness stored the bytes doing its work, `source` says what the bytes
are, and `artifact_references` being unique on `(program_id, sha256, kind)` is
what makes that expressible.

**Join 1 was sidestepped, not fixed.** `analyze` is still `unopenable_kind` and
that refusal is still correct. The three analysers are granted to `recon`
instead, which already fetched the bundle, already holds `exec.tool_run`, and
needs no network to read an Artifact. The contradiction with
`20260814T050000Z`'s *only the analyst* is stated in the migration: that reason
assumed the analyst could be scheduled, and it cannot. `js_analyst` remains a
role with no Task, which is worth its own ticket and is no longer in the way of
anything.

**Join 3 was not a join and the claim above is wrong.** Measured against
`jsscan.py` before any change, both `js_parse` and `js_routes` read a
transcript-wrapped bundle and returned exactly the routes they return for the
bare file: the tokeniser separates code from strings, and a header block is
neither.

What the measurement did find is narrower and worse than what was claimed.
Pointed at a response carrying

    X-Quote: he said "/api/fake" loudly

`js_parse` reported `/api/fake` among the file's path literals. `path_literals`
says what the *file* holds, so a target could write into the surface a Program
records about it by choosing a response header. `js_routes` was already immune,
because a header line is not a call -- which is the grounding rule earning its
keep, and the reason the Skill's new step names `js_routes` and not `js_parse`.

`rk2-jsscan 3` reads the body of an HTTP message when it is handed one and
reports `carrier_bytes`; `source_sha256` still names the bytes as read, because
that is what the Tool run recorded as its input and what `check_source_citation`
holds a citation against. `tests/test_jsscan.py::CarrierTest` keeps the
injection case.

**And the technique.** `enumerate-surface` step 4 runs `js_routes` over each
script the walk stored and proposes an Endpoint per grounded route.
