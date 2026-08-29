# 214 — A Receipt answers the arm it was planned for

**What to build:** The columns and the comparison that bind a Receipt to the
query, the header block and the body its action planned, and the framing that
keeps an empty body different from no body all the way to the target.

**Blocked by:** 211 — A Test action carries the header and the body it plans.

**Status:** resolved

The implementation is in the working tree, uncommitted. Everything below was
measured against it. The status stays `ready-for-agent` because `resolved` in
this tracker means built, tested, reviewed **and committed**, and the commit has
not been made.

## What was measured

Ticket 211 let a Test action state `headers` and `body`. It also decided, in
writing, that `record_test_action` would keep comparing only the route:

> **The Receipt comparison stays at the route, and the reason is written down.**
> … `receipts` carries `query_sha256` and `request_agent_sha` and no header or
> body column, so there is nothing to compare against without a new one. … **No
> change to `record_test_action`.**

That reasoning holds for the state 211 shipped and stops holding the moment two
actions can differ below the route. This ticket reverses it, and the two reasons
211 gave are answered rather than ignored:

- *"the door injects identity headers"* — the digest is taken from the view the
  caller stated, before the injection. `proxy.py` copies `agent_headers` into
  `wire_headers` and injects afterwards; the two are separate lists.
- *"there is nothing to compare against without a new one"* — a new one is what
  this ticket adds.

The hole, stated as the run that reaches it: two actions to one route differing
only in a header, a body or a query record each other's Receipts and nothing
refuses. An assertion names an ordinal and is evaluated against whatever Receipt
sits under it, so such a run produces a differential between two requests nobody
planned to compare.

A second finding, measured while landing the first: a body-less request and a
request with an empty body were the same fact from `_launch` and `replay` all
the way to the Receipt. `authorize_egress_request` grades them apart, and until
this ticket nothing gave it the difference to grade.

## What has to hold

- [x] **Three columns on `receipts`, written by the allowed writer.**
      `request_headers_sha256`, `request_body_sha256`, `response_body_sha256`,
      each `CHECK (... ~ '^[0-9a-f]{64}$')` and nullable. In both the column list
      and the `VALUES` list of `write_allowed_receipt`, asserted by counting each
      name twice in `pg_get_functiondef` — once is the failure mode, because a
      column present in one list only is written null for every row and nothing
      raises.
- [x] **A null is not an empty value.** For the two body columns null means
      nothing was sent; for `request_headers_sha256` it means the Receipt
      predates the column, because after the `accept-encoding` defaulting every
      request carries at least one header.
- [x] **Three functions spell the same digest out of the plan.**
      `rk2_test_query`, `rk2_planned_headers_sha256`, `rk2_planned_body_sha256`,
      all immutable, one per name in `public`.
- [x] **The header digest defaults `accept-encoding: identity`, and only that
      one name.** `http.client` puts the header on the wire when the caller does
      not (`putrequest` defaults `skip_accept_encoding` to false;
      `_send_request` sets it only for a caller that spells the header). Without
      the same default on the plan side, a plan naming no `Accept-Encoding`
      could never match its own Receipt — for any request at all. One name is
      enough because every other header on the wire was either stated by the
      plan or stripped by `forwardable`.
- [x] **The two spellings are pinned to bytes, not to each other.** The SQL side
      asserts `sha256(b"accept-encoding: identity\n")` and
      `sha256(b"accept-encoding: gzip\n")` on apply; `tests/test_proxy.py` holds
      the Python side against the same two literals through the live door. Two
      spellings compared only against each other can be wrong together.
- [x] **`record_test_action` refuses on each axis by name.** Query, headers and
      body, three separate refusals, each naming the ordinal and the axis. A
      reader told only "refused" would have to diff two plans.
- [x] **A Receipt the door blocked is refused on what it is.** A blocked Receipt
      of a replay run carries lane `replay` and holds no request digests, so the
      three comparisons would report a request that was never sent as a
      differing one. Refused ahead of them, by `decision`.
- [x] **An empty body and no body are two requests, from the caller to the
      target.** `_body` returns `bytes | None`; `_launch._body` and
      `_Door.send` pass `None` through; the door asks
      `authorize_egress_request` `body is not None` and frames
      `Content-Length: 0` only for a body it was given.
- [x] **The sender frames what it was handed.** `_get_content_length` answers
      `0` for a `None` body on POST, PUT and PATCH — RFC 7230 §3.3.2, and the
      stdlib says so in its own comment — so `client.request` would frame an
      empty body on every body-less POST and the door would refuse the request
      of any Tool run not opened for one. `_through` writes the request header
      by header instead, and computes `skip_accept_encoding` itself: a caller
      that names `Accept-Encoding` and is not suppressed sends two, and the
      second is a header no plan can state.
- [x] **Negative tests with positive counterparts.** Three arms on one route
      differing by one axis each, the Receipt of arm 1 accepted as action 1 and
      refused as action 2. Plus the empty-body arm at the door and at the agent
      tool.

## What this ticket does not do

- `response_body_sha256` is written and read by nothing. It is the answer's own
  digest beside `response_agent_sha`, which names the whole message, and a
  body-level differential needs the body alone. Added now rather than with its
  reader because a column added later is null for every Receipt written in
  between and there is no backfill for bytes nobody kept.
- `write_blocked_receipt` is not extended. Two refusal paths do hold the
  headers, so this is a choice and not a limit; a blocked Receipt is refused by
  `decision` rather than compared.

## Comments

Ticket 96 declined a `request_body_sha256` in writing
(`20260924T000000Z__a_request_may_carry_a_body.sql`, "WHAT THIS FILE DOES NOT
ADD, AND WHY IT SAYS SO"): the body is already inside `request_agent_sha`, and
"two statements of one fact drift". That was right for the question 96 asked.
`request_agent_sha` digests the whole document — start line, headers, blank
line, body — and there is no operation that turns a plan's three stated parts
into it without rebuilding the exact bytes the door sent, including the headers
the door added. 96 asked what the door sent; this ticket asks whether the
Receipt answers the arm that was planned. The new migration says so where 96
said the opposite.
