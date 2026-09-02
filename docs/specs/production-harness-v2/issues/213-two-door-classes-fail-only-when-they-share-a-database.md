# 213 — Two door classes fail only when they share a database

**What to build:** The isolation that lets `ReplayCommandTest` and
`ProxyEgressTest` pass in a run that also holds the other `test_database.py`
classes, rather than only in a run of their own.

**Blocked by:** nothing.

**Status:** resolved

## What was measured

Found while landing ticket 211, and measured against a clean tree rather than
assumed: this is not that ticket's regression.

Both runs used PostgreSQL 18.6 and the same `RK_TEST_DATABASE`:

```
tests.test_database.CleanCreationTest ReplayTestRunTest ReplayCommandTest
CandidateFindingTest ImpactProofTest ProxyEgressTest FindingClaimTest
ScopedSpecificationTest ContainedDoorTest
  -> Ran 149 tests, FAILED (errors=2, skipped=20)

tests.test_database.ReplayCommandTest ProxyEgressTest
  -> Ran 74 tests, OK
```

Both errors are in `setUpClass` and both are the same violation:

```
tests/test_database.py:31366  assert sealed.ok, sealed.violations
tests/test_database.py:8277   assert sealed.ok, (name, sealed.violations)

Violation(code='invalid_configuration', source='program_header_slots',
          detail='the key does not match this installation')
```

The nine-class run was performed twice, once with ticket 211's migration and
edits in the tree and once with them stashed. The two results are identical --
same 149 tests, same two errors -- so the class set is the variable and ticket
211 is not.

## Where the mechanism is

`header.py:145-156` compares `root.check(salt, generation=number)` against the
`root_check` stored beside the slot and fails with exactly this sentence when
they differ. `root` comes from a key file through `seal.load_root`
(`header.py:91`), so nothing in the schema or in the migration set can move it.

`setUpModule` builds one `Harness`, which is one database, shared by every class
in the run (`tests/test_database.py:329-346`). So the two classes are reading
header-slot state some earlier class in the same run wrote under different key
material. Which class, and whether the right answer is per-class key material or
a per-class Program, is the open question this ticket is for.

## Why it is worth a ticket rather than a note

`docs/research/playbook-state-of-the-art/00-todo-and-harness-gaps.md` section D
records a full-suite run with "5 failures and 1 error", names two of them as the
leased client certificate, and leaves a TODO to identify the remaining four.
These two are candidates for that TODO, and they are cheap to reproduce because
the class list above is the whole repro.

It also costs real coverage today: a contributor running the covering classes
for a change to the replay lane either runs them alone and sees green, or runs
them with their neighbours and sees two errors that have nothing to do with the
change. Both readings are wrong in a way that is easy to act on.

## Acceptance criteria

- [x] **The nine-class command above passes.** Same classes, same order, one
      database, no errors and no new skips.
- [x] **The two-class command still passes.** Whatever isolates them must not
      work only in company.
- [x] **The mechanism is named in the fix.** Which class writes the conflicting
      root check, and why the two later classes read it, stated where the fix
      is -- not "flushed state" or "ordering".
- [x] **The remaining full-suite failures are counted again.** Section D of
      `00-todo-and-harness-gaps.md` is updated with what is left after this,
      because a TODO that names four unknown failures and is never re-counted is
      a TODO nobody can close.

## What this does not change

Ticket 211 stays as landed. Its own coverage is proved by
`ReplayTestRunTest` (54 tests, including the eleven refusals it adds) and by the
two door classes run alone (74 tests), both green.

## Verification, 2026-09-02

The mechanism fixed in `tests/test_database.py` is the installation-wide
`secret_kek` generation: `ReplayTestRunTest` and `EvidenceBundleTest` could
establish generation 1 with filler `root_check` bytes no `seal.Root` could
derive. `ReplayCommandTest` and `ProxyEgressTest` then read that generation and
correctly refused it as belonging to another installation. `ESTABLISH_KEK` now
derives the check from `seal.Root('selftest', SECRET)` at the salt it records,
so all four classes describe the same key material.

Against PostgreSQL 18 on the isolated `rk2-test-pg` instance, with the suite's
own exclusive `/tmp/rk2-db.lock`:

- the nine named classes ran 231 tests in 109.535 seconds: `OK`, with the same
  20 container-only skips;
- `ReplayCommandTest` plus `ProxyEgressTest` ran 77 tests in 83.668 seconds:
  `OK`, with no skips;
- the complete DB module ran 1542 tests in 1580.667 seconds and left four
  errors, none in either class above. Section D records their names.

The old 149/74 counts grew because the same classes acquired tests after this
ticket was written; the class sets and their order did not change.
