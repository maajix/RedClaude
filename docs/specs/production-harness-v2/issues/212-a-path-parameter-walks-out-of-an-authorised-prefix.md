# 212 — A path parameter walks out of an authorised prefix

**What to build:** `scope.path_variants` folds the `;`-parameter segment the way
it already folds percent-encoding and backslashes, so a path classed under an
authorised prefix is the path the target resolves.

**Blocked by:** nothing.

**Status:** resolved

## What was measured

Found while repairing the ticket-101 source ledger. A repair agent claimed three
traversal spellings keep a Finding path because `rk2_test_request_problem` does
not refuse them. Two of the three were refuted at the door. The third was not.

`src/redkraken/scope.py`, `path_variants`, run against the candidates:

```
/public/../admin           raw=/public/../admin           norm=/admin
/public/..%2fadmin         raw=/public/..%2fadmin         norm=/admin
/public/..%5cadmin         raw=/public/..%5cadmin         norm=/admin
/public/%252e%252e/admin   raw=/public/%252e%252e/admin   norm=/admin
/public/..;/admin          raw=/public/..;/admin          norm=/public/..;/admin
```

The first four normalise to where they land, which is the function's whole
purpose and it works. The fifth does not move.

## Why that is a scope gap

`scope_class_of` (`20260929T030000Z__a_range_is_scope_and_a_tier_never_was.sql:152`)
is given two spellings, and the polarities differ on purpose — `path_variants`
states it in its own docstring: an exclusion fires if **either** spelling is
under its prefix, an inclusion needs **both**. That is what stops
`/public/../admin` from being admitted under a `/public/` inclusion.

For `/public/..;/admin` the two spellings are identical and both sit under
`/public/`, so the inclusion admits it. The door then sends the path verbatim —
`origin_form` takes `urlsplit(url).path` and removes nothing
(`proxy.py:818-828`).

Servlet containers and several frameworks strip `;`-delimited path parameters
before resolving, which is what makes `..;/` a known traversal spelling rather
than a curiosity. On such a target the request classed as `/public/` arrives at
`/admin`.

The blast radius is path-level scope inside an already-authorised host and port,
not a new destination: host, port and protocol are checked separately and are
unaffected. It matters because engagement scopes routinely authorise a prefix
and exclude a sibling, and because the receipt would cite the inclusion.

## Acceptance criteria

- [x] **`path_variants` folds the parameter segment when building `norm`.**
      Each `;`-delimited parameter is removed from every segment before
      `posixpath.normpath` runs, in the same fixpoint loop that already handles
      repeated percent-decoding. `raw` is untouched — it is what was asked for,
      and the exclusion polarity depends on it staying verbatim.
- [x] **`/public/..;/admin` normalises to `/admin`,** and so do
      `/public/..;a=b/admin` and `/public/%2e%2e;/admin`.
- [x] **A legitimate parameter does not change where a path lands.**
      `/a/b;jsessionid=x/c` normalises to `/a/b/c`, and `/a/b;x` to `/a/b`.
- [x] **A negative control per spelling.** `tests/test_scope.py` asserts the
      inclusion refuses each of them under a `/public/` grant and a `/admin`
      exclusion, for `tests/test_database.py`'s stated reason: a check nobody has
      seen fail is a check nobody knows is wired up.
- [x] **The plan-time checker is left alone, and the reason is written down.**
      `rk2_test_request_problem`
      (`20260815T000000Z__a_test_runs_through_the_replay_lane.sql:217-226`)
      refuses dot segments and `%2e` and does not model this; it is a
      convenience refusal and the door is the enforcement point. Ticket 211
      touches that function and must not be read as owning this.

## What this does not change

Ticket 211 stays as written. The dot-segment refusal it names is still the
reason a traversal reading cannot be **closed by a Test**; this ticket is about
what the **door admits**, which is a different question and a different function.
