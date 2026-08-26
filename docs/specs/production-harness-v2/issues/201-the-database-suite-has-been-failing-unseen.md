# 201 — The database suite has been failing unseen

**What to build:** the database suite back to green, and a reason it cannot go
red unnoticed again.

**Blocked by:** nothing.

**Status:** resolved

## What was measured

`tests.test_database`, run against a disposable server on 2026-08-26.

```
Ran 347 tests in 633.693s
FAILED (failures=30, errors=57, skipped=69)
```

Eighty-seven failures. Every single one names the same source:

```
$ grep -o "source='[^']*'" dbsuite.log | sort | uniq -c
     65 source='standing:identity_clamp'
```

The fifty-seven errors are `setUpClass` on classes that assert a clean gate
before they begin, so they are the same failure counted where it stops a class
rather than a test.

And the control that exists to say the gate is quiet on a clean database is one
of the failures:

```
FAIL: test_the_gate_holds_when_nothing_is_broken
AssertionError: Lists differ: [] != ['standing:identity_clamp']
```

## Why nobody saw it

The module skips itself whole without `RK_TEST_SUPERUSER_URL`:

```
Ran 2643 tests in 309.505s
OK (skipped=179)
```

The 179 skips are this file. Every gate this repository runs — `check_audit`,
`check_coverage`, `check_wiring` — passes without a server, and the suite the
whole schema is tested by has been standing down. Ticket 197 found the same
module doing the opposite kind of damage when it *was* run; this is what it was
doing the rest of the time.

## The mechanism

`check_identity_clamp()` arm (b), from `20260908T010000Z`:

```sql
    SELECT 'task_identity_not_held_by_its_run', t.label,
           'the run acts as ' || i.slot_name || ' and holds no lease on it'
      FROM tasks t
      JOIN task_identities ti ON ti.task_id = t.id
      JOIN identities i ON i.entity_id = ti.identity_entity_id
     WHERE lease_live_for(t)
       AND identity_clamped_for(t)
       AND NOT EXISTS (SELECT 1 FROM task_held_identities(t.id) hi
                        WHERE hi.identity_entity_id = ti.identity_entity_id)
```

Three facts make it fire now and not before.

1. **The population grew.** Before `20261120T000000Z` a `task_identities` row
   existed only where a named Identity had been selected, which in a test
   fixture is almost never. That file made every clamped Task carry a row and
   default it to `_anonymous`, so every hand-built clamped Task now has one.

2. **A hand-built in-flight Task holds no Lease.** `claim_task` writes the
   Task Lease and the Identity Leases in one statement. A fixture that inserts
   `status = 'running'` with a `lease_expires_at` writes the first and not the
   second, so `lease_live_for(t)` is true and `task_held_identities(t.id)` is
   empty.

3. **The check has no program filter.** `FROM tasks t WHERE ...` and nothing
   about `rk2_program()`. Every class in this module shares one database, so
   one fixture's leftover Task is reported to every other class that asserts
   `violations == []` — which is what turns one bad fixture into eighty-seven
   failures.

The product path is consistent: `claim_task` inserts a Lease for every
`task_identities` row including the anonymous one, so a Task claimed the real
way satisfies the arm. `rk db verify` on the live engagement is clean.

## The residual underneath it

`identity_leases_exclusive_idx` is `UNIQUE (identity_entity_id) WHERE
released_at IS NULL`, with no exemption for `_anonymous`. `identities` carries
`CHECK (class = 'anonymous' OR secret_ref IS NOT NULL)` — an anonymous Identity
is the absence of a credential, and there is nothing about it to hold
exclusively. So at most one clamped Task per Program may run anonymously at
once.

`20261120T000000Z:84` names this and measures the cost as zero, correctly: the
driver claims one Task per `rk run`, so the practical concurrency is one. It
stops being zero the day two children run at once, and ticket 199's `chain`
profile floors two clamped lanes — `hunt` and `conclude` are both `web_hunter`.

## What has to be decided

- **Fix the fixtures.** Whichever class leaves a clamped Task in flight writes
  the Identity Lease too, or leaves it `pending`. Smallest change, and it keeps
  the check saying exactly what it says.
- **Or stop leasing the anonymous Identity.** Neither the arm nor the exclusive
  index would ask a run to hold an Identity with no secret. Larger: `claim_task`
  raises when a clamped Task writes no Lease at all, so that arm moves too.

## Answer

The second, because the first is not available.

- [x] **The fixture is right about the product.** `WaveMeasurementTest` stands
      up four concurrent hunters in one Program, which is what a wave is. Giving
      each of them the Lease `claim_task` would have written is impossible: they
      all name `_anonymous` and `identity_leases_exclusive_idx` admits one
      holder. The fixture did not break. Concurrent anonymous hunting did, on
      20261120, and this is where it showed.

- [x] **`20261201T000000Z` stops writing the Lease.** `claim_task` leases every
      Identity a clamped Task names except the anonymous one, and counts what
      the Task NAMES rather than what was inserted, so the refusal it raises is
      still about a clamped Task that names nothing at all. Arm (b) of
      `check_identity_clamp` gains the same predicate. A Task acting as a named
      Identity without the Lease is still a violation.

- [x] **Nothing downstream was reading it.**
      `enforce_allowed_receipt_capability` admits a Receipt whose Tool run names
      no `identity_slot` and whose Identity is NULL through a branch that asks
      for no Lease, and an anonymous Identity has no `identity_slots` row for
      the other branch to join. The Lease was written and never read.

- [x] **The negative control names somebody.** Control (b) built a hunt Task and
      let the projection give it `_anonymous`, which is now exempt, so it would
      have stopped breaking the check it exists to break. It now mints a `user`
      Identity with a `secret_ref` and names that.

- [x] **The other half of the same cap is gone too.** `20261204T000000Z`.
      `scheduler_lane_state` bounded a clamped lane's headroom by the Identities
      the Program has free:

      ```sql
      CASE WHEN c.clamp_to_identity_leases
           THEN least(greatest(c.max_slots - live, 0), coalesce(free.n, 0))
           ELSE greatest(c.max_slots - live, 0) END AS headroom
      ```

      `free` counts unleased Identities, and a Program whose only Identity is
      the anonymous one counts one — so `hunt` reported headroom 1 against
      `max_slots` 2 even with the Lease gone. Counting the absence of a
      credential as one credential is the same mistake in the other half of the
      view, and ticket 199's `chain` profile is what stopped it costing nothing:
      `max_concurrent_subagents` is 3 and `hunt` is `web_hunter` at 2, so the
      second anonymous hunt was refused `lane_full` by a lane that was not full.

      Where the Program has an anonymous Identity available the clamp now does
      not bind at all — not "counts as many", because there is no number of
      anonymous runs the supply refuses. Loosening is the safe direction:
      20260908 states that the view is an upper bound and that `claimable_for`
      asks `identity_held` before `lane_full`, so a Task naming a held named
      Identity is still refused by the finer gate. A Program with no anonymous
      Identity reads exactly as it read before.

      `IdentityClampTest` measures it: two hunts over one anonymous Identity,
      headroom 2 rather than 1, and both of them start.

- [x] **A suite that skips is a suite that is red -- and the gate for it
      already exists.** `tools/release_gate.py:772` runs both suites twice and
      reads three things the exit code does not say: that the two runs of a
      suite selected the same number of tests, that a suite ran any test at all,
      and that

      ```
      the composed suite skipped as much as the offline one
      (N against M), so nothing live ran
      ```

      `ran()` raises on any non-zero exit, so a failing composed suite stops the
      gate rather than being counted. Nothing has to be built.

      What is true is that this gate is stage-gated to the release candidate --
      ticket 65 -- and the four gates `docs/agents/testing.md` names for the
      daily loop are `check_audit`, `check_wiring`, `check_baseline` and
      `check_coverage`, none of which runs a test. That is the design: a
      database run costs 630 seconds and takes a cluster-global lock, so it is
      not in the loop on purpose.

      The eighty-seven failures were therefore not invisible to this repository.
      They were invisible to the operator who read a 630-second run through
      `tail -60`, which is a habit and not a hole. `dbsuite.sh` in this ticket's
      working directory redirects the whole run to a file for that reason.

## Why

Eighty-seven failing tests and one cause, standing for however long it has
been, in the file that tests the entire schema. Every other gate was green
throughout — which is the shape of a suite whose default is silence.
