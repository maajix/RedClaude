# 236 — The documented database test command runs nothing

**What to build:** A one-line correction to `docs/agents/testing.md`, and
whatever makes the trap loud rather than silent.

**Blocked by:** nothing.

**Status:** claimed

**PRODUCES:** changed contract -- the documented database test command, and a
loud refusal in place of a silent skip when `/tmp/rk2-db.lock` is already held.

**CONSUMED BY:** `operator, via uv run python -m unittest
tests.test_database.<Class>`; every session that follows
`docs/agents/testing.md`.

**CONSUMES:** `tests/test_database.py::setUpModule`, which takes
`/tmp/rk2-db.lock` itself and raises `unittest.SkipTest`;
`docs/agents/testing.md`.

**Touches:** `docs/agents/testing.md`, `tests/test_database.py`. Corrected in
§1: `docs/specs/production-harness-v2/TASKS.md` carries the same rule as a
ticked exit criterion and is owed -- see `## Build findings` for why it is not
in the first commit.


## What was measured

Measured on 2026-09-02. The command the page gives, run exactly as written:

```
flock -w 3600 /tmp/rk2-db.lock uv run python -m unittest \
  tests.test_database.CleanCreationTest -v
  setUpModule (tests.test_database) ... skipped 'another session holds
  /tmp/rk2-db.lock; a hunt is running on this cluster'
  Ran 0 tests in 0.000s
  OK (skipped=1)
```

The same command without the outer `flock` runs 9 tests and passes.
`setUpModule` takes `/tmp/rk2-db.lock` itself, so the documented wrapper is the
"another session" it then declines to run beside.

`OK` with exit status 0 is what a reader and a CI step both see. An agent
following the page gets a green schema run that never happened, which is the
opposite of what the lock is for.

## Acceptance criteria

- [x] **The page's command runs the tests.** Copied out of
      `docs/agents/testing.md` and pasted into a shell, it reports the class's
      tests rather than `Ran 0 tests`.
- [x] **A skipped module is not a green run.** A skip of `setUpModule` for a
      held lock is distinguishable from a pass by whatever reads the result --
      the page says how, or the harness makes it non-zero.
- [x] **The lock is documented where it is taken.** One sentence saying the
      suite takes the lock itself, so the next reader does not add a wrapper
      back.

## Seam check, 2026-09-02

`PRODUCES:` a changed contract on two ends. The documented command in
`docs/agents/testing.md` no longer carries an outer `flock`, and
`tests/test_database.py::setUpModule` raises instead of skipping when the lock
is held.

`CONSUMED BY`, each opened or run:

- `operator, via uv run python -m unittest tests.test_database.<Class>` -- the
  command was copied out of the page and pasted into a shell:
  `Ran 10 tests in 29.678s` / `OK`, against
  `postgres://postgres:...@127.0.0.1:55433/postgres` with
  `RK_TEST_DATABASE=rk2_t236`. Far end **reached**, and it is the criterion.
- every session that follows `docs/agents/testing.md` -- nothing in the tree
  reads that page, so the far end is a reader rather than a symbol.
  `grep -rn "docs/agents" tests/*.py tools/*.py` prints nothing. Recorded as
  **the reader at `docs/agents/testing.md`**, not as NOBODY: the page is an
  agent-facing artifact and its only consumer is the next session.
- `tests.test_database.ClusterLockTest` -- new here, and the mechanical far end
  the reader above cannot be. It holds the lock and runs a child, so the
  contract is asserted rather than described. Far end **reached**.

`CONSUMES:` `tests/test_database.py::setUpModule` at `:328`, opened: it takes
`LOCK_PATH` with `os.open` and a non-blocking `fcntl.flock`, and the `except
OSError` branch is the one this ticket changed. `LOCK_PATH` is
`os.environ.get("RK_TEST_CLUSTER_LOCK", "/tmp/rk2-db.lock")` at `:177`, so the
escape hatch the new message names already existed and needed no code.

No `NOBODY`.

## Build findings, 2026-09-02

**The skip was the right refusal and the wrong report.** `setUpModule`'s own
comment says the non-blocking lock is deliberate -- "waiting would mean a suite
that sits silent for the length of a sitting; skipping says which server is
busy and leaves the operator a choice between the two" -- and that reasoning is
untouched. A `RuntimeError` says which server is busy just as well, leaves the
same choice, and protects a live hunt identically, because neither one runs the
schema. The only thing that changed is the exit status of a run that did not
happen. Nothing had to be designed around: the lock stays non-blocking.

**One wall, priced.** `docs/specs/production-harness-v2/TASKS.md:393` is a
ticked exit criterion reading
``Jede Datenbankausführung enthält `CleanCreationTest`, läuft unter `flock -w
3600 /tmp/rk2-db.lock` ...`` -- the rule this ticket refutes, stated as
satisfied.

- **wall:** that file was being edited by ticket 134's review cycle in this same
  worktree while this ran, and it was staged in the index by that session.
  Committing it here would put another ticket's work inside this ticket's
  commit, which is the commit its own review pins as a fixed point. Staging one
  hunk needs `git add -p`, which this session cannot run.
- **price:** one line of German spec documentation reads the old rule for the
  length of one commit.
- **purpose:** each ticket's commit is the unit its review pins. That is worth
  more than one line's freshness for one commit.
- **rule:** the line is not in the first commit. It is written down here by
  file and line number, and it lands as this ticket's own second build commit
  as soon as ticket 134's review has committed the file. `Touches` above is
  corrected to name it.

**A second, dated instance of the same defect is left standing on purpose.**
`TASKS.md:337` records a measurement from 24.08.2026 -- "Vollständige Suite:
3996 Tests, OK, 101 übersprungen (`unittest discover`, unter `flock -w 3600
/tmp/rk2-db.lock`)". If the wrapper made the module skip, that run's 101 skips
included all 1359 database tests and the 3996 excludes them. It is a dated
measurement block, which the standing bar reads as history, and re-measuring
the full suite is ticket 65's work. Recorded here rather than rewritten.

**The same shape was found and fixed in a third place four commits earlier.**
`tests.test_okf.FreezeTest`'s docstring gave a bundle regeneration command that
raises `ValueError: ... is not in the subpath of '.'`; it was corrected in
ticket 235's commit `5c35ca1e` because that ticket had to run it. Two
documented commands that do not run, found within an hour, is the reason
criterion 2 is asserted by a test rather than by a sentence.

## Resolution, 2026-09-02

Three changes, and the smallest of the three is the one the ticket was filed
for.

The page's command lost its `flock` wrapper, and gained a bolded paragraph
saying why there is none -- because the previous reader added one, and the
paragraph is what stops the next one putting it back. The paragraph names the
ticket, so the correction carries its own provenance.

`setUpModule` raises `RuntimeError(LOCK_REASON)` where it raised
`unittest.SkipTest(LOCK_REASON)`. One line, and the lock behaviour is
unchanged: still non-blocking, still refusing to run beside a hunt. What
changed is that a run which never reached the schema exits non-zero instead of
printing `OK`. `LOCK_REASON` grew from a clause to three sentences, and the two
new ones are the operator's two ways out -- wait, or set
`RK_TEST_CLUSTER_LOCK` -- plus the instruction not to wrap the command. The
note above `LOCK_PATH` says the module takes the lock itself, which is criterion
3 landing where the lock is taken rather than only on the page.

`ClusterLockTest` is the one class in a 47000-line database file that says
something about the file rather than about the schema, and it needs no
PostgreSQL: `setUpModule` refuses before `_build`, so a child with any non-empty
`RK_TEST_SUPERUSER_URL` and the lock held stops at the refusal. The child runs
that same class, which never executes, so the test costs one interpreter start.

`Red:` `AssertionError: 0 == 0 : setUpModule (tests.test_database) ... skipped
'another session holds /tmp/rk2-db.lock; a hunt is running on this cluster'` --
`tests.test_database.ClusterLockTest.test_a_run_that_could_not_take_the_cluster_lock_is_not_green`,
watched failing before the raise changed, with the child's whole
`Ran 0 tests in 0.000s` / `OK (skipped=1)` carried in the assertion message.
That is the defect the ticket measured, reproduced by a test.

`Mutated:` `raise RuntimeError(LOCK_REASON)` narrowed to
`raise RuntimeError("busy")`:
`AssertionError: 'another session holds /tmp/rk2-db.lock; ... Do not wrap the
command in flock: this module takes the lock itself.' not found in 'setUpModule
(tests.test_database) ... ERROR ... RuntimeError: busy ... FAILED (errors=1)'`
-- so the test holds the message and not merely the exit status. A run that
fails for the wrong reason is not what this ticket asked for.

Forward references this ticket leaves standing: none. Two tickets cite this
number and both citations are history inside dated blocks; nothing is owed to
this ticket. One line of `TASKS.md` is owed *by* it, and `## Build findings`
names the file and the line.

## Bar, 2026-09-02

1. **Every acceptance criterion is ticked.** `grep -c '^- \[ \]' <ticket>`
   prints `0`; `grep -c '^- \[[ x]\]' <ticket>` prints `3`.
2. **The seam test passes, read by name.** This effort's spec carries no
   `## Verify command`; the test this change reaches is named in full.

   ```
   NO_COLOR=1 uv run python -m unittest -v \
     tests.test_database.ClusterLockTest.test_a_run_that_could_not_take_the_cluster_lock_is_not_green
     test_a_run_that_could_not_take_the_cluster_lock_is_not_green ... ok
     Ran 1 test in 0.934s
     OK
   ```

   And criterion 1 itself, which is a command rather than a test -- the page's
   own block, pasted:

   ```
   export RK_TEST_SUPERUSER_URL="postgres://postgres:...@127.0.0.1:55433/postgres"
   export RK_TEST_DATABASE=rk2_t236
   uv run python -m unittest \
     tests.test_database.CleanCreationTest tests.test_database.ClusterLockTest -q
     Ran 10 tests in 29.678s
     OK
   ```

   The old command, for the contrast criterion 2 asks for:

   ```
   flock -w 5 /tmp/rk2-db.lock uv run python -m unittest \
     tests.test_database.CleanCreationTest -q
     RuntimeError: another session holds /tmp/rk2-db.lock; a hunt is running on
     this cluster. Wait for it to finish, or set RK_TEST_CLUSTER_LOCK to a path
     of your own if this server is not the one the hunt is on. Do not wrap the
     command in flock: this module takes the lock itself.
     Ran 0 tests in 0.009s
     FAILED (errors=1)
     exit=1
   ```

   `exit=1` was read from `$?` of the run itself, not of a pipeline: the first
   attempt at this measurement read `tail`'s status and printed `exit=0`, which
   is the same class of mistake as the one this ticket fixes.
3. **Forward references redeemed.** `grep -rn 'ticket 236\|Ticket 236'
   docs/specs/production-harness-v2/`, this ticket excluded, prints 3 lines:
   `134-...md:329` and `:408`, both inside that ticket's `## Bar` and
   `## Review findings` blocks, and `235-...md:167`, inside its
   `## Build findings` block. All three are history by the bar's own rule. No
   `CONSUMED BY`, `CONSUMES` or `deferred to` on any of them, and nothing was
   owed to this ticket.
4. **Existing tests still pass, none skipped, deleted or weakened.**

   ```
   NO_COLOR=1 uv run python -m unittest tests.test_audit tests.test_coverage -q
     Ran 107 tests in 60.990s
     OK (skipped=3)
   ```

   Those two are the modules that read which tests exist, which is what adding
   a class could break. The four gates run clean as programs: `check_audit`,
   `check_wiring`, `check_baseline` and `check_coverage` all rc=0.

   The full `tests/test_database.py` was **not** run: 1359 tests and over thirty
   minutes, against a change that touches one `except` branch of `setUpModule`
   and adds one class that does not inherit `DatabaseCase`. What was run is the
   whole of `setUpModule`'s success path -- `CleanCreationTest` provisions the
   database from empty, which is `_build` end to end -- plus both of its failure
   paths, the held lock in a child and the held lock under an outer `flock`.

   `git diff --numstat`: `docs/agents/testing.md` 18 added and 4 deleted;
   `tests/test_database.py` 62 added and 2 deleted, of which 2 are code -- the
   raise and the reason -- and the rest are `ClusterLockTest` and two notes. No
   `.skip`, no deleted test, no removed assertion. One skip was **removed**:
   the module no longer skips on a held lock, which is the ticket.
5. **The diff is what the ticket asked for.**
   `git status --short --untracked-files=all` holds nine paths, and this commit
   names three of them explicitly: `tests/test_database.py`,
   `docs/agents/testing.md` -- the `Touches` line -- and this ticket. The other
   six belong to ticket 134's review cycle, running concurrently in this
   worktree: `README.md`, `src/redkraken/config.py`, `src/redkraken/scope.py`,
   `tests/test_scope.py`, that ticket's own file, and
   `docs/specs/production-harness-v2/TASKS.md`, which that session had already
   staged. The commit is made with explicit pathspecs so none of them rides it.
6. **The blocks.** `grep -c '^## Resolution' <ticket>` prints `1`,
   `grep -c '^## Bar' <ticket>` prints `1`, `grep -c '^## Handoff' <ticket>`
   prints `0`.

**Judgement, red and mutated.** Both watched in this session, and both
assertion messages in `## Resolution` are quoted from those runs. The red is
the ticket's own measurement reproduced as a test rather than as a paste.

**Judgement, no unexplained NOBODY.** Two of the three far ends are a command
that was run and a test that was written. The third is the page's reader, and
it is recorded as the reader at `docs/agents/testing.md` after measuring that
nothing in `tests/` or `tools/` reads the file -- an agent-facing document whose
consumer is the next session, which is why criterion 2 was not left to a
sentence on that page.

**Judgement, the live run reached this ticket's case.** There is no
`live-inputs.md` in this effort. The live part of this ticket is a real
PostgreSQL cluster, and it was reached: `rk2-test-pg` on `127.0.0.1:55433`,
`RK_TEST_DATABASE=rk2_t236`, provisioned from empty and dropped again by
`tearDownModule`. Both the success path and the held-lock path ran against it.

**Judgement, Rule 3b.** No double was injected. `ClusterLockTest` runs a real
child interpreter against the real `setUpModule` and a real `flock`; the only
thing it fakes is the connection string, which is never opened because the
refusal happens first.
