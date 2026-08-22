# 157 — The address of a subject is answered twice

**What to build:** One function that answers "where does a request for this
Entity go", read by the readiness predicate and by the dispatch slice, so the
two cannot disagree — and, because it is written once, an answer for the Entity
types that carry a name rather than a URL.

**Blocked by:** nothing.

**Status:** resolved

- [x] **One definition, two readers.** `rk2_subject_addressable`
      (143) tests `applications` and `endpoints`; `execution.STARTED`
      (`src/redkraken/execution.py`) resolves the URL from `applications` and
      `endpoints` in an inline `CASE`. Two copies of one rule, in two
      languages, either of which can be changed without the other. After this
      there is one, and `rk2_subject_addressable` is defined in terms of it.
- [x] **A name that carries an Application resolves to it.** A `domain` and a
      `host` are addressable when the Program holds an Application whose base
      URL names them. `rk2hunt16` promoted claim `H1` against `DOM1`
      (`www.yekta-it.de`), and `https://www.yekta-it.de` was sitting in
      `applications` the whole time.
- [x] **The pick is deterministic and stated.** One name can carry more than
      one Application — `http` and `https` are two subjects on one host, which
      is 20260813's own rule. The order is written in the `COMMENT` and not
      left to the planner: `https` first, then the lower port, then the base
      URL ascending.
- [x] **A name that carries none still has no address.** An `identity` and a
      wildcard `domain` resolve to NULL, `rk2_subject_addressable` stays false
      for them, and `ready_for` still answers `recon.no_address`. A wildcard is
      the honest case to hold this with: it is a name, so it reaches the new
      arms rather than falling past them, and `*.app.example.com` names a set
      of hosts this build enumerates none of.
- [x] **Checked by something that would go red.** The covering
      `tests/test_database.py` classes are named and run under `flock` with
      `CleanCreationTest` in the same invocation, and the case asserts the
      resolved URL for an Application, an Endpoint under one, a Domain
      carrying one, and NULL for an Entity carrying none.

## Why

Split out of what `rk2hunt16` measured on 22 August. The run reached
`hypothesis_evidence = 8`, one Test authored, one Test performed and one claim
at `supported` — the whole chain 140/141/152/154/155 was built for. Two Tasks
did not run, and one of them is this:

```
H1  testable   subject DOM1  (domain www.yekta-it.de)
T3  hunt       pending       ready_for -> hunt.no_address
```

143 put the address question in `ready_for` so a Task the runtime cannot serve
never reaches the slate. That worked: the pass survived, exit 0 on all five
laps, where `rk2hunt4` had died. It also froze a Task that a request could
perfectly well have been aimed at, because the predicate was written from the
dispatch slice's two joins rather than from the question those joins are
asking.

The question is "where does a request for this Entity go". Answering it in two
places is the defect; the domain arm is what answering it once makes obvious.

## Notes

`rk2_parse_base_url(text)` (20260813) already splits a base URL into scheme,
host, port and path and refuses what it cannot spell canonically. It is
`IMMUTABLE`, still `EXECUTE` to PUBLIC, and is the right way to ask what host
an Application is on — a `LIKE` against `base_url` would match
`https://not-www.yekta-it.de` for `www.yekta-it.de`.

Ticket 158 is the other half of what T3 exposed: this ticket makes T3 ready,
158 makes a Task that never becomes ready end. Neither replaces the other.

## How it was paid

`20261020T000000Z__the_address_of_a_subject_is_answered_once.sql`. Two new
functions: `rk2_application_on(uuid, text)` is "the one Application this
Program holds on that name", ordered `https` first, then the lower port, then
the base URL ascending, asked through `rk2_parse_base_url` rather than by
pattern. `rk2_subject_url(uuid)` is the four arms -- Endpoint, Application,
non-wildcard Domain, Host -- and `rk2_subject_addressable` becomes
`rk2_subject_url(...) IS NOT NULL`, which is what it always meant. `ready_for`
is not touched: its two `no_address` arms ask the same predicate and now get a
better answer from it.

`execution.STARTED` (`src/redkraken/execution.py`) drops its inline `CASE` and
its two `applications` joins and calls `rk2_subject_url(e.id)`. That is the
whole point of the ticket: the predicate and the dispatch are one function now,
so they cannot disagree.

Covered by `tests/test_database.py::FirstTaskTest`. Three Entities in the
second Program stand beside the configured Application --- a `domain` on the
name it is served on, an `endpoint` under it, and a wildcard `domain` --- and
`test_the_address_of_a_subject_has_one_answer` asserts all four arms in one
row. `test_an_entity_nothing_is_served_on_carries_no_address` and
`test_a_recon_task_whose_subject_has_no_address_is_never_ready` keep 143's
sentences, now written against a subject that has no address for a reason 157
did not remove.

Run: `CleanCreationTest FirstTaskTest TaskRankingTest SlateClaimTest`, 102
tests, OK. `tests.test_execution`, 163 tests, OK.
