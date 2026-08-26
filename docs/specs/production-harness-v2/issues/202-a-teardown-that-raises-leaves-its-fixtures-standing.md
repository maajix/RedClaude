# 202 — A teardown that raises leaves its fixtures standing

**What to build:** a class purge that cannot be rolled back by a row another
class wrote, so one bad teardown stops being every later class's failure.

**Blocked by:** nothing.

**Status:** resolved

## What was measured

Ticket 201 fixed one standing check and the suite got *worse* in a way that
looked better:

```
dbsuite.log   Ran  347 tests   87 failures   74 name standing:identity_clamp
dbsuite3.log  Ran  367 tests   86 failures    2 name standing:identity_clamp
                                             73 name standing:test_replays
```

Twenty more tests ran, and the failure count barely moved because the same
*shape* of defect was waiting underneath. Two more layers came off the same
way:

```
dbsuite4.log  Ran  961 tests   39 failures   26 name standing:execution_closure
dbsuite5.log  Ran 1102 tests   36 failures    0 name any of the three
```

Three hundred and forty-seven tests to eleven hundred and two, without a single
change to a product path.

## The shape

Every one of the three is the same four facts.

1. **One database, many classes.** `tests.test_database` runs every class
   against the same server, in one schema.
2. **A standing check with no Program filter.** `integrity.run(connection,
   expected, families, programs=None)` means every Program, so a row belonging
   to class A is reported to class B.
3. **A class that asserts the gate is quiet before it begins.** Dozens of
   `setUpClass` bodies end with `assert opened.ok, opened.violations`.
4. **A teardown that raises.** The purge runs inside one transaction, and a
   single foreign-key violation in it rolls back the `DELETE FROM programs`
   above it. The class's fixtures survive, and fact 2 hands them to fact 3.

The result is that one class with a deliberately odd fixture -- which is what a
fixture is for -- fails every class that runs after it. The failure names the
check rather than the class, so the log points at the schema and not at the
teardown.

## The two collisions found

**Content-addressed artifacts.** `artifacts.sha256` is a digest, so two
Programs that saw the same bytes name the same row. Fourteen teardowns wrote

```sql
DELETE FROM artifacts WHERE sha256 = ANY($1::text[])
```

unguarded. Three were caught raising `receipts_response_agent_sha_fkey` --
`CandidateFindingTest`, `ExecutionSliceTest`, `ProxyEgressTest` -- and the rest
were the same statement waiting for the same collision.

**Cluster-wide KEK generations.** `secret_kek(gen)` is not per Program.
`SealedWireArtifactTest.tearDownClass` deleted every generation and raised
`artifact_seal_kek_gen_fkey` on a row it did not write.

## Answer

- [x] **The purge deletes only what nothing else names.** `UNREFERENCED_ARTIFACTS`
      in `tests/test_database.py` guards the delete with `NOT EXISTS` over
      `artifact_references` and over all four `receipts` digest columns, and the
      fourteen array-form sites use it. The KEK purge is guarded the same way
      over the four tables that reference `secret_kek(gen)`.

- [x] **The measurement is the same measurement.** `dbsuite5.log` is the same
      command as `dbsuite.log`, against a disposable server built from the same
      migration corpus. 347 tests to 1102, and none of the three sources
      appears in it.

- [x] **A fixture that is odd on purpose stays odd.** Nothing about the classes
      changed. `CandidateFindingTest` still seeds two replay runs with no
      Receipt, because that is what it tests; it simply no longer leaves them
      behind.

- [ ] **The check that has no Program filter still has none.** Filtering
      `standing:test_replays` and `standing:execution_closure` by
      `rk2_program()` would make a leftover fixture invisible to the next class
      *and* invisible to `rk db verify` run against one Program, which is the
      only way the operator ever runs it. That is a change to what the checks
      mean and it is not made here. What this ticket removes is the reason a
      leftover exists at all.

## Why

Eighty-seven failures were read as one defect for as long as they were read at
all. They were four, stacked, each hidden by the one above it, and every one of
them was a teardown rather than a product path.
