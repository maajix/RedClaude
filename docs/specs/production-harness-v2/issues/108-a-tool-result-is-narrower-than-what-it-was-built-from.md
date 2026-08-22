# 108 — A tool result is narrower than the value it was built from

**What to build:** The three fields a tool answer loses at the last hop --
`stderr`, the scope class of an exchange and the Identity it was made as -- and
the rule that a field is either carried or declared dropped.

**Blocked by:** nothing.

**Status:** resolved

- [x] `stderr` reaches the model. `tool._streams`
      (`src/redkraken/tool.py:790-806`) files both streams deliberately --
      "Stdout and stderr are always kept, empty or not. An empty stream is a
      fact about the run" -- and `tool.serve` (`tool.py:519-536`) returns
      `stdout` as a bounded head and an `outputs` list carrying only
      `("stream", "output_name", "kind", "label", "byte_size")` per item. The
      stderr bytes are never returned in any form. A tool that failed tells the
      model its exit code and its possibly empty stdout and hides the
      diagnostic it wrote.
- [ ] The exchange's scope class reaches the model. The door resolves it and
      writes it on the Receipt; it is the value `src/redkraken/browser.py:454`
      reads back out of Receipts to fill `browser_step_results.scope_class`, and
      the browser driver is forbidden from computing its own for a stated reason
      (`src/redkraken/browser_driver.py:525-528`: "`scope_class` is not here on
      purpose. What class a URL belongs to is the door's answer"). The agent's
      `http_request` answer carries no scope class, so a model cannot tell an
      in-scope 404 from an out-of-scope one.
- [ ] The Identity the exchange was made as is named in the answer. The runtime
      chooses it before the run opens, which `roster.py:800-805` gives as the
      reason there is no `identity_slot` argument, and the same paragraph is why
      the answer has to say which one was spent: an identity-differential
      reading cannot tell the model which of two runs was which. Ticket 97 owns
      what an identity slot is; this ticket owns naming the one that was used.
- [x] The rule is written down where it can be checked rather than restated per
      field. For each boundary where a rich runtime value becomes a
      model-facing dict, every field of the source is either carried or named in
      a constant with a reason: `proxy._answered` against
      `http.client.HTTPResponse`, `_launch._spend` against `proxy.Answer`,
      `tool.serve` against `isolation.ToolProcess`. Adding a field to one of
      those sources without deciding about it fails.
- [x] Ticket 94 owns the response headers at the same boundary and is not
      re-opened here. Its finding is that the loss is two layers deep --
      `proxy.Answer` never carried them, so fixing `_spend` alone is not enough
      -- and the same is true of the scope class, which is on the Receipt rather
      than on the response.

## Why

`docs/research/wiring/21-agent-surface-wiring.md` sections 5.3 and 5.5, and its
gate G7, which is the one that generalises them: "A result is not narrower than
the value it was built from." Section 5.6 lists what does not lose information,
so the finding is read as specific rather than as a general complaint: the
validation packet is handed over whole, the bounded reads report what they
dropped and why, and `_spend` already reports `byte_size` and `truncated` beside
the excerpt so a truncated body is legible as truncated.

`docs/research/wiring/22-corpus-instruction-wiring.md` section 2.4 counts the
corpus cost of the same boundary: twenty-six Playbook bodies tell the model to
read a response header, six tell it to measure timing, and the answer shape is
eight keys.

## What was built — 2026-08-22

`tool.serve` hands back both streams and both ceilings. The answer was ten keys
and is fourteen: `stderr` beside `stdout`, cut to the same `excerpt` and with
`stderr_truncated` when it was cut, and `timed_out` and `overflowed` beside the
status. The stderr head is read off `answer.stderr.data` the way the stdout head
is read off `answer.stdout.data`, so the bytes come from the same
`isolation.ToolProcess` `_streams` already files as an Artifact -- this reads
what was there rather than capturing anything new, and no schema, no verb and no
grant moved, so there is no migration.

The two ceilings are named rather than left inside the sentence `_verdict`
writes. A run the supervisor stopped kept a fragment of a run that was taken
away; a tool that exited non-zero ran to the end and said no. One is a bound an
operator has to raise and the other is the tool's own answer, and a model that
had to read the detail line to tell them apart would be parsing prose for a fact
the run already holds.

`truncated` stays the flag for `stdout` and the second stream gets the prefixed
one, which is `_spend`'s idiom at the neighbouring boundary: the primary reading
carries the bare name and the secondary carries its own.

The answer dict stays inside `serve` rather than moving to a helper. `W5` reads
the body of the function the boundary names, so a `serve` that delegated its
answer would mention none of these fields and the three gaps would reopen while
the answer stayed correct.

## Where the rule now lives

`tests/test_tool.py`. One hand-written table of the three boundaries, with the
field lists read out of the sources rather than restated: `tool.serve` against
`isolation.ToolProcess`, `_launch._spend` against `proxy.Answer`, and
`proxy._answered` against `http.client.HTTPResponse`. Every field of a source is
either mentioned by the function that narrows it or named in the table with the
reason it is not, and the two readings are `check_wiring`'s own -- `fields` and
`carried` -- so the gate and the table cannot drift into disagreeing about what
"carried" means.

Two drops are declared, both at `proxy._answered`: the response's `reason`,
because the phrase beside the status code is whatever the target typed there and
the transcript the Receipt names holds the start line byte for byte, and its
`version`, because that is the version the door spoke to this caller and not the
one the target answered the door in. Nothing is dropped at the other two.

The third boundary is here and not in `check_wiring` because its source is not
in this tree and is not a dataclass: what a response holds is written down once
and asserted against a live `HTTPResponse`, so a rename in the standard library
is a test that fails rather than a boundary that quietly stopped being measured.
The table also asserts that it names every boundary the gate names, so the two
lists cannot part.

`W5`'s three register rows are gone: `tool.serve.stderr`,
`tool.serve.timed_out` and `tool.serve.overflowed` are no longer gaps the gate
finds, and the rows that owed them are removed rather than re-pointed.

## What was measured

* `tests.test_tool` -- `Ran 6 tests`, `OK`. The rule was also asked to fail:
  a stale drop, an undeclared field, a key removed from the answer and a
  reading renamed out of `HTTPResponse` each turn the relevant test red.
* `tests.test_database.OfflineToolCommandTest` with `RK_TEST_CONTAINERS=1` --
  `Ran 15 tests`, `OK`, against a clean checkout of `HEAD` carrying only this
  change.
* One real served run of `rkgrep` with an unmatched `[`, read back as a child
  reads it: `exit_code` 2, `stdout` empty, `stderr` the first eight bytes of
  `/bin/grep: ...` with `stderr_truncated` true, `timed_out` and `overflowed`
  false, and the whole 38-byte diagnostic filed as the Artifact the `outputs`
  list already named. Before this ticket that answer was an exit code and an
  empty stdout.
* `check_audit`, `check_wiring`, `check_baseline` and `check_coverage` all 0.
  `W5` reports one owed row and it is ticket 107's; the three this ticket owed
  are no longer gaps the gate finds.

## The two criteria this did not pay

The scope class and the Identity are both `mcp__rk2__http_request`'s answer, and
that answer is written in `_launch._spend`. Neither is reachable from the files
this ticket was allowed to write:

* The scope class is on the Receipt and not on the response, which the fifth
  criterion already says. Carrying it means the door stating it on the answer it
  sends back -- a fourth control header beside `RECEIPT`, `DECISION` and
  `DETAIL` -- then a field on `proxy.Answer` filled by `proxy._answered`, then a
  key on `_spend`'s dict. The `Answer` `proxy._answered` builds is
  `src/redkraken/proxy.py:3735-3746`; the dict is the one `_spend` returns.
* The Identity is a property of the Tool run, which ticket 97 settled. Naming it
  means `agent.Egress` carrying the slot the runtime chose and `_spend` putting
  it on the answer. The door has no parameter to receive one and must not grow
  one, for every reason the `http_request` contract in `roster.py` gives; what
  is missing is the runtime saying which one it already spent.

Both are one ticket's worth of work at one boundary, and no open ticket owes
them today. The table in `tests/test_tool.py` will not catch either of them when
they land -- a field that was never on the source is not a field the source
dropped -- which is the same limit the wiring research states for the response
headers ticket 94 closed.

## Where criteria 2 and 3 went (2026-08-22)

Both are `mcp__rk2__http_request`'s answer rather than `tool.serve`'s, and both
need files this ticket's agent did not own. They are now ticket 136 — An HTTP
answer names neither its scope class nor its Identity, which carries the exact
sites: `proxy._answer` / `_answered` (`src/redkraken/proxy.py:3735-3746`), a
field on `proxy.Answer`, and a key in `_launch._spend`. The Identity half waits
on ticket 131, because `execution._authorize` still opens every egress Tool run
with `"identity_slot": ""`, so there is nothing yet to name.
