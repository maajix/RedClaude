# 215 — A dead correlator is graded against the transaction's clock

**What to build:** An expiry arm that answers the same way whichever statement
asks it, so that
`CallbackAdmissionTest.test_an_arrival_cannot_backdate_itself_into_a_dead_correlator`
stops depending on how many round trips happened before it.

**Blocked by:** nothing.

**Status:** ready-for-agent

## What was measured

Found while landing ticket 214, and measured against a clean tree rather than
assumed: this is not that ticket's regression.

A worktree was cut at `8810e7c4` with no working-tree changes in it, and the one
test was named six times in a single process:

```
tests.test_database.CallbackAdmissionTest
    .test_an_arrival_cannot_backdate_itself_into_a_dead_correlator  x6
  -> Ran 6 tests, FAILED (failures=5)

tests.test_database.CallbackAdmissionTest
  -> Ran 25 tests, OK
```

Same commit, same database, same session: five failures out of six when the test
is asked on its own, and a pass when it is asked after its twenty-four
neighbours. The failure is always the same sentence:

```
tests/test_database.py:6161  with self.assertRaises(pg.DatabaseError) as refused:
AssertionError: DatabaseError not raised
```

The correlator the test needs dead was still live.

## Where the mechanism is

Three lines, and they do not use one clock.

- `20260912T000000Z__an_out_of_band_host_is_bound_not_declared.sql:542` mints
  with `clock_timestamp() + p_lifetime` -- the wall clock, read part way into the
  minting transaction.
- `20260812T040000Z__a_callback_arrives_on_a_declared_channel.sql:166` defaults
  `issued_at` to `now()` -- the *start* of that same transaction, which is
  earlier.
- `20260912T000000Z__an_out_of_band_host_is_bound_not_declared.sql:396` grades
  the arrival with `t.expires_at <= now()` -- the start of the *refusing*
  transaction.

`tests/test_database.py:6532` mints with `seconds=0.001`, so the test passes only
when the refusing transaction begins later than `mint_clock + 1 ms`. Between
those two instants there is one COMMIT, one `self.counts()` query and one BEGIN.
That is the whole margin.

It was measured by adding a single `SELECT` to the test, in its own transaction,
between the mint and the refusal:

```
extract(epoch from (t.expires_at - t.issued_at))  = 0.004536
extract(epoch from (now()        - t.expires_at)) = 0.001288
```

`expires_at` sits 4.5 ms after `issued_at` although the lifetime asked for is
1 ms, because `clock_timestamp()` is read 3.5 ms into the minting transaction
while `issued_at` was stamped at its start. And with that one extra round trip in
place the same six runs were green:

```
    ... x6  -> Ran 6 tests, OK
```

So the passing runs and the failing runs have the same cause: the test is a race
whose margin is a fraction of a millisecond, and anything that changes how many
statements precede it decides the outcome. The twenty-four neighbours are enough;
one extra `SELECT` is enough; a longer `test_database.py` is enough.

## Why it is worth a ticket rather than a note

The comment above the guard says the arm reads the clock "rather than
`NEW.received_at`", and names `resolve_callback_correlator` as reading
`clock_timestamp()` "for the same reason". `now()` is not the clock. It is the
transaction's start, so inside a long transaction a correlator that expired
half-way through is still admitted -- which is the case the arm exists to refuse.
`resolve_callback_correlator` already disagrees with it at
`20260912T000000Z...:347`, `:919` and `:991`, all three of which read
`clock_timestamp()`.

So the flake and the gap are one thing, and fixing the arm fixes both. The
alternative -- keeping `now()` and making the test wait -- leaves the arm
disagreeing with the three statements next to it.

## Acceptance criteria

- [ ] **The one test passes six times in a row in one process.** The command in
      "What was measured", unchanged, with no extra statement added to the test
      to buy it time.
- [ ] **`CallbackAdmissionTest` still passes whole.** 25 tests, no new skips.
- [ ] **The two clocks are named where the fix is.** Which arm reads which, and
      why the arm that grades an arrival is not the arm that stamps `issued_at`
      -- not "flaky timing".
- [ ] **The long-transaction case is asserted.** A correlator that expires while
      the reading transaction is open is refused. Without it the fix is graded
      only by the race it removes, and the gap it closes goes unrecorded.
