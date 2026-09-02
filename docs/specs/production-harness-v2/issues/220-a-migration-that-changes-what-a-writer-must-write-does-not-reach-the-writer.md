# 220 — A migration that changes what a writer must write does not reach the writer

**What to build:** A `NULL` on the door's side of a receipt comparison must
name the door, not the headers. Today `record_test_action` reads a column the
running door never wrote and reports it as a mismatch, and the campaign it
stopped ran three days before anyone read the word.

**Blocked by:** nothing.

**Status:** resolved

## What happened

Ticket 214 added `receipts.request_headers_sha256` and one writer for it,
`proxy.py:3314`. The same release added the reader,
`20261217T000000Z__a_receipt_answers_the_arm_it_was_planned_for.sql:279-283`:

```sql
    IF v_receipt.request_headers_sha256 IS DISTINCT FROM
           rk2_planned_headers_sha256(v_action -> 'headers') THEN
        RAISE EXCEPTION 'receipt % carries different headers than action % states',
            p_receipt, p_ordinal USING ERRCODE = '23514';
```

`rk db migrate` moved the reader. Nothing moved the writer: the door runs as a
container with `src/` bind-mounted, so the file on disk was new and the Python
process holding the old module was not. It had been up since before the
release and stayed up for three days.

Measured on `rk2here`, 2026-08-29:

```
receipts, all four days           2494
  with request_headers_sha256        0
"carries different headers"         86   (in the lap reports)
test_replay_actions, 2026-08-29      0
assertions evaluated, 2026-08-29  0 of 44
```

The chain, end to end: every receipt carries `NULL`;
`rk2_planned_headers_sha256` is never `NULL` and its own comment says so
(`:132-133` -- "a NULL here would be a comparison that fails for every
ordinary request"); so every `record_test_action` raises; so
`test_replay_actions` stays empty; so `close_test_replay` reads
`WHEN v_left.id IS NULL THEN NULL`
(`20260815T000000Z__a_test_runs_through_the_replay_lane.sql:1489`); so every
assertion grades `held: null`; so every test is `inconclusive`; so no
`hypothesis_transitions` row is ever written and no Finding above `info` can
exist. Three days of hunting, 56 to 160 actions a day falling to zero, and the
only word the operator ever saw was "carries different headers", which is true
of nothing that happened.

`docker restart rk2here-door` fixed it in one command. The same measurement
after:

```
receipts since the restart          6
  with request_headers_sha256       4   (the two without are a refused wire response and a transport measurement)
test_replay_actions                 4
assertions evaluated              6 of 8
```

## The wall, priced

```
WALL    check_server_baseline (`20261003T000000Z:402`) checks
        `no_pending_migrations` at `:470` -- whether the schema has caught up
        with the files. Nothing checks whether the processes writing to that
        schema have. Read in source 2026-08-29; both ends read -- the check
        that would catch it, and `door.py`, whose only statement against the
        database is `PROGRAM_VISIBLE` (`:574`), so the door announces no
        version to anything.
PRICE   Two lines, and they are not the version handshake. The reader already
        distinguishes the case: `IS DISTINCT FROM` collapses "the door wrote a
        different digest" and "the door wrote no digest", and only the first
        is a header mismatch. A `NULL` branch raising `receipt % carries no
        header digest; the door predates ticket 214 -- restart it` costs one
        `IF` in `record_test_action` and one test. The version handshake is
        the bigger fix and is not needed to make this outage a one-command
        one.
PURPOSE This ticket exists so the next migration that changes what a writer
        writes is survivable, not so the door reports a version. An operator
        who reads the right word restarts the door in a minute. One who reads
        "carries different headers" reads a fact about headers and goes
        looking at headers, which is where three days went.
RULE    Capability before catalogue. Telling the two failures apart is the
        capability; a door-version registry is the catalogue, and it is not
        what was missing here.
```

## Acceptance criteria

- [x] **A receipt with no header digest raises a message naming the door.**
      Not "carries different headers". A test inserts a receipt with
      `request_headers_sha256 IS NULL` and asserts on the word.
- [x] **The same holds for the body digest.** `:284-288` is the identical
      comparison against `rk2_planned_body_sha256` and has the identical hole.
- [x] **The query digest is checked and left alone, or fixed with them.**
      `:274-278` compares `query_sha256`, which the door has written since
      long before 214; if it can be `NULL` too, it belongs in the same branch.
- [x] **`rk doctor` reports a door older than the newest applied migration.**
      Deferred to its own ticket if the handshake is the price; named here so
      the deferral is a decision and not an omission.
- [x] **The engagement runbook says to restart the door after `rk db
      migrate`.** The operator-side half. Free, and it is what would have cost
      nothing on 2026-08-26.

## What this does not change

The comparison itself. A receipt that answers a different arm than the action
planned is a receipt that must not grade a test, and ticket 214 is right about
that. This is about which of two failures the operator is told they have.

## What was built, 2026-08-30

`20261226T000000Z__a_receipt_with_no_digest_names_the_door.sql`. One
`CREATE OR REPLACE FUNCTION record_test_action`, verbatim from
`20261217T000000Z` except for two branches.

**Headers.** `rk2_planned_headers_sha256` is never NULL and says so in its own
comment, so a Receipt holding no header digest can only be a door that wrote the
row without the column. The NULL is refused before the comparison, with
`receipt % carries no header digest; the door that wrote it predates the column,
so restart the door and replay`.

**Body.** The same fault with one difference, and the difference is why the
branch is nested rather than placed first: `rk2_planned_body_sha256` *is* NULL
for a plan that states no body and the door writes NULL for a request that
carried none, so NULL against NULL is a match and never reaches the branch at
all. What reaches it is a plan that states a body against a Receipt with no
digest of one, and that is the same old door.

**Query, left alone, and that is criterion 3's answer.** `rk2_test_query`
answers NULL for a url with no query, and `proxy.query_sha256` writes NULL for a
request with none -- "absence stays absence", in its own words. NULL against
NULL matches on both sides, so there is no third reading to separate. Measured
on `rk2here`: 2681 Receipts, 68 with a query digest, and this comparison has
never been the one that raised.

A blocked Receipt already holds three nulls and is already refused one branch
earlier, on `decision <> 'allowed'`, so nothing here changes what it says.

**Criterion 4 is deferred, as a decision.** `rk doctor` still does not compare
the door's version against the newest applied migration, because the door
announces no version to anything (`door.py:574` is its only statement against
the database). That is ticket 225, which names the two shapes and their prices.

**Criterion 5 is done.** The engagement README gained an `## After
`rk db migrate`` section: both commands, in order, with what the three days
cost and a pointer to 225.

## What was verified

`tests/test_database.py::ReplayTestRunTest` gains
`test_a_receipt_with_no_digest_at_all_names_the_door_and_not_the_headers` and
the fixture behind it. The Receipt is written by the same helper every other
case uses and the digest is nulled afterwards, because a helper that could write
a Receipt the current door cannot write would be a second door. Both axes assert
three words present -- the axis, `predates the column`, `restart the door` -- and
one word absent: `different`, which is what sent the operator to the headers.

57 tests in that class, all pass. `rk db migrate` on `rk2here` applied it with
`violations: []`.
