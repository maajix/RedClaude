# 236 — The documented database test command runs nothing

**What to build:** A one-line correction to `docs/agents/testing.md`, and
whatever makes the trap loud rather than silent.

**Blocked by:** nothing.

**Status:** resolved

**PRODUCES:** changed contract -- the documented database test command, and a
loud refusal in place of a silent skip when `/tmp/rk2-db.lock` is already held.

**CONSUMED BY:** `operator, via uv run python -m unittest
tests.test_database.<Class>`; `tests.test_database.ClusterLockTest, reading
LOCK_REASON`; every session that follows `docs/agents/testing.md`.

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
`os.environ.get("RK_TEST_CLUSTER_LOCK", "/tmp/rk2-db.lock")` at `:178`, so the
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

**Paid, 2026-09-02.** Ticket 134's review committed as `9378a597`, which left
the worktree clean, and the line landed in this ticket's second build commit
with nothing else in it. `check_audit` rc=0 after it.

**A second, dated instance of the same defect is left standing on purpose.**
`TASKS.md:337` records a measurement from 24.08.2026 -- "Vollständige Suite:
3996 Tests, OK, 101 übersprungen (`unittest discover`, unter `flock -w 3600
/tmp/rk2-db.lock`)". If the wrapper made the module skip, the 3996 excludes
the database tests -- not that 101 of them are database tests: a `setUpModule`
skip reports one skip standing for the whole module, which is what
`## What was measured` above prints. It is a dated
measurement block, which the standing bar reads as history, and re-measuring
the full suite is ticket 65's work. Recorded here rather than rewritten.

**The same shape was found in a third place two commits earlier.**
`tests.test_okf.FreezeTest`'s docstring gave a bundle regeneration command that
raises `ValueError: ... is not in the subpath of '.'`; ticket 235's commit
`5c35ca1e` corrected the docstring because that ticket had to run it. Ticket
235's own review later called that a defect routed around in prose, reverted the
docstring and fixed `okf.build` instead (`235-...md:517`), which is the fix that
stands. Two
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
changed is that a run stopped by the lock exits non-zero instead of printing
`OK`. `setUpModule`'s other silent door -- `RK_TEST_SUPERUSER_URL` unset, early
return, `Ran 0 tests` / `OK` / exit 0 -- is untouched and stays that way: it is
what lets the other 59 modules be discovered and run on a machine with no
server. Criterion 2 is written for the held lock, and that is the door this
closes; `docs/agents/testing.md` now names the one that is still silent rather
than implying there is none. `LOCK_REASON` grew from a clause to three sentences, and the two
new ones are the operator's two ways out -- wait, or set
`RK_TEST_CLUSTER_LOCK` -- plus the instruction not to wrap the command. The
note above `LOCK_PATH` says the module takes the lock itself, which is criterion
3 landing where the lock is taken rather than only on the page.

`ClusterLockTest` is the one class in a 56900-line database file that says
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
   `TASKS.md` is the one path with two owners here: the staged hunk was 134's,
   and line 393 -- the exit criterion this ticket refutes -- is this ticket's,
   which is the wall `## Build findings` priced and this ticket's second build
   commit paid.
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

**Re-run for cycle 1's NOW repairs, 2026-09-03.** The repairs touched production
code -- `raise ... from None` and the module docstring -- so the machine lines
were re-run at the review commit. Numbers that moved are marked.

1. **Every acceptance criterion is ticked.** `grep -c '^- \[ \]'` prints `0`;
   `grep -c '^- \[[ x]\]'` prints `3`. Unchanged: no criterion was added to
   this ticket by any verdict in this cycle.
2. **The seam test passes, read by name.**

   ```
   NO_COLOR=1 uv run python -m unittest -v tests.test_database.ClusterLockTest
     Ran 1 test in 0.907s
     OK
   ```

   Criterion 1, the page's own block pasted after the page was corrected, against
   `rk2-test-pg` on `127.0.0.1:55433` with `RK_TEST_DATABASE=rk2_t236r`:

   ```
   uv run python -m unittest \
     tests.test_database.CleanCreationTest tests.test_database.ClusterLockTest -q
     Ran 10 tests in 25.636s
     OK
     exit=0
   ```

   Criterion 2's contrast, the old wrapped command, on the same live cluster --
   and this is what the `from None` repair changed, so the whole output is
   carried rather than its tail:

   ```
   flock -w 5 /tmp/rk2-db.lock uv run python -m unittest \
     tests.test_database.CleanCreationTest -q
     ======================================================================
     ERROR: setUpModule (tests.test_database)
     ----------------------------------------------------------------------
     Traceback (most recent call last):
       File ".../tests/test_database.py", line 356, in setUpModule
         raise RuntimeError(LOCK_REASON) from None
     RuntimeError: another session holds /tmp/rk2-db.lock; a hunt is running on
     this cluster. Wait for it to finish, or set RK_TEST_CLUSTER_LOCK to a path
     of your own if this server is not the one the hunt is on. Do not wrap the
     command in flock: this module takes the lock itself.
     ----------------------------------------------------------------------
     Ran 0 tests in 0.008s
     FAILED (errors=1)
     exit=1
   ```

   The `BlockingIOError` traceback and the "During handling of the above
   exception" line that stood between the command and the reason are gone. That
   is the whole of what changed in the refusal.
3. **Forward references redeemed. Moved: 3 at the build commit, 12 now.** The
   grep, this ticket excluded, prints 12 lines: `TASKS.md:393`, which is this
   ticket's own second build commit; `134-...md:329` and `:408`; `233-...md:360`;
   `226-...md:437`, `:784`, `:1010` and `:1481`; and `235-...md:215`, `:410` and
   `:517`. Nine of the twelve are tickets 226, 233 and 235 citing this one as
   history after it landed. `grep -c 'CONSUMED BY\|CONSUMES\|deferred to'` over
   those same twelve prints `0`, so nothing is owed to this ticket and the rule
   passes on all twelve, as it did on the three.
4. **Existing tests still pass, none skipped, deleted or weakened. Moved: the
   file is 1592 tests, not the 1359 the page claimed.**

   ```
   NO_COLOR=1 uv run python -m unittest tests.test_audit tests.test_coverage -q
     Ran 107 tests in 59.574s
     OK (skipped=3)
   ```

   `check_audit`, `check_wiring`, `check_baseline` and `check_coverage` all
   rc=0, run as `uv run python -m tools.<name>` -- run as a path they fail on
   `ModuleNotFoundError: No module named 'tools'`, which is how the build's own
   paste should be read.

   `tests.test_audit` is the module the REOPEN of ticket 197 could break, and it
   is the one that caught it: reopening 197 dropped `resolved` from 205 to 204
   against a hardcoded expectation, and setting this ticket `resolved` in the
   same commit put it back. The two moves balance, which is why the literal in
   `tests/test_audit.py` needed no edit.

   The full `tests/test_database.py` was again **not** run: 1592 tests, and the
   repair touches one `raise` line, one module docstring and one added
   assertion. What was run is `setUpModule`'s success path end to end
   (`CleanCreationTest` from empty) and its held-lock failure path, live.

   `git diff --numstat` for the review commit: `docs/agents/testing.md` 19 added
   and 11 deleted, `tests/test_database.py` 8 added and 2 deleted. No `.skip`,
   no deleted test, no removed assertion -- one assertion was **added**,
   `assertNotIn("BlockingIOError", told)`, and it was watched red first.
5. **The diff is what the review settled.** `git status --short
   --untracked-files=all` holds four paths, and the commit names all four:
   `docs/agents/testing.md`, `tests/test_database.py`, this ticket, and
   `docs/specs/production-harness-v2/issues/197-...md`, which the REOPEN verdict
   wrote. Nothing else is in the worktree this time.
6. **The blocks.** `grep -c '^## Resolution'` prints `1`, `grep -c '^## Bar'`
   prints `1` -- this paste sits under the build's heading rather than opening a
   dated one -- and `grep -c '^## Handoff'` prints `0`.

**Judgement, red and mutated, for the repair.** The one production-code repair
that could regress was watched red: `assertNotIn("BlockingIOError", told)`
failed with the full 15-line chained traceback in its assertion message before
`from None` landed. The docstring repair is prose over behaviour that was
already correct and is proved by the run above, where `ClusterLockTest` passes
with `RK_TEST_SUPERUSER_URL` unset -- the exception the docstring now names.

## Review findings, 2026-09-03 — cycle 1

Fixed point `9378a597`, the parent of this ticket's first build commit. The
diff read is `9378a597..7f91a929`, this ticket's own two build commits, not
`...HEAD`: tickets 134, 235, 233 and 226 landed after it and were reviewed by
their own cycles, so their work is not this review's diff. Current source was
read at HEAD wherever a citation was opened.

- [seam] **The produced contract holds for one of `setUpModule`'s two silent
  doors.** `if not SUPERUSER_URL: return` still prints `Ran 0 tests in 0.000s`
  / `OK (skipped=1)` and exits 0 -- byte-identical to the output
  `## What was measured` records as the defect. Verified with
  `env -u RK_TEST_SUPERUSER_URL uv run python -m unittest
  tests.test_database.CleanCreationTest -q`, exit 0. Extend the refusal to the
  missing-export door, or record why that door is exempt when the held-lock
  door was not. — required — NOW. `## Resolution` now says which door this closes and which stays silent, and `docs/agents/testing.md` names the `RK_TEST_SUPERUSER_URL`-unset skip rather than implying there is none. The early return stays: it is what lets the other 59 modules be discovered on a machine with no server.
- [seam] **The page states the new rule without its door.** `docs/agents/testing.md`
  says a run that never reached the schema now says so; that is false for the
  missing `RK_TEST_SUPERUSER_URL` case, which the page's own tier-1 block
  invites by telling the reader to export it. Either the finding above lands
  and the sentence becomes true, or the sentence gains the clause naming the
  one skip that still exits 0. — required — NOW. Same repair. The page's sentence reads "a run stopped by the lock", and a paragraph below it names the one door that still exits 0.
- [seam] **`docs/agents/testing.md`'s headline counts are stale and this commit
  edited the page without re-measuring them.** The page says 47170 lines, 81
  classes, 1359 tests; current source is 56920 lines and 92 classes by the
  page's own `grep -n '^class .*Test'`, 89 of them before this ticket.
  Converged with [ticket], [bar] and [craft] below. — nit — NOW. Re-measured 2026-09-03 and corrected in place: 4359 tests, 60 modules, `tests/test_database.py` 56920 lines / 92 classes / 1592 tests, the other 59 modules 2767 tests. The 37% ratio survived the re-measure; the absolutes did not.
- [seam] **The password-rotation citation is 48 lines stale and this diff moved
  it 13 further.** `docs/agents/testing.md` cites `tests/test_database.py:313`;
  the rotation is at `:374` now and was at `:361` at the fixed point. Cite
  `_build` by symbol. Converged with [craft] below. — nit — NOW. Cited as `_build` by symbol instead of `:313`.

- [ticket] **The in-repo hunt loop takes no cluster lock, and the comment this
  diff extended says it does.** `grep -n 'flock\|lock' tools/hunt-loop.sh`
  prints nothing across its 76 lines; `tests/test_database.py`'s block asserts
  "the hunt loop has taken this lock since it was written", and
  `## Build findings` rests its safety argument on it ("protects a live hunt
  identically"). The only lock-taker in the tree is `setUpModule`. `hunt.sh` is
  an out-of-repo operator script quoted in ticket 197. Not 236's regression,
  but 236 re-asserted the citation without opening it. Converged with [craft]
  below. — required — REOPEN ticket 197. The comment is true of `hunt.sh`, which is out of repo and quoted verbatim in 197, and false of `tools/hunt-loop.sh`, which ships here and takes nothing. 197's own `## Why` is the argument -- "One side of a lock is not a lock" -- and the loop landed in the same commit as its fix. Criterion added there. Not 236's diff, and not 236's regression.
- [ticket] **The rewritten blanket rule leaves a one-off probe with no
  mechanism.** `docs/agents/testing.md` keeps "every database invocation runs
  under `/tmp/rk2-db.lock`, no exceptions, not even a one-off probe" and adds
  "Do not add a wrapper." The suite takes the lock itself; a `psql` probe does
  not, and the new sentence forbids the only way it could. The criterion is
  that the next reader does not add a wrapper back, not that no invocation may
  ever hold the lock. Scope the prohibition to `tests/test_database.py`.
  Converged with [craft] below. — required — NOW. The rule now reads "everything that touches this cluster", names the suite as the one thing that already holds the lock itself, and leaves `flock /tmp/rk2-db.lock` as the mechanism for everything else.
- [ticket] **The page's headline numbers are stale and `## Bar` §4 quotes one
  of them back as this ticket's measurement.** Measured at HEAD via the
  unittest loader: 56920 lines, 92 `TestCase` subclasses, 1592 tests; 56004
  lines at `7f91a929`. Converged with [seam], [bar] and [craft]. — nit — NOW. Covered by the page re-measure above; `## Bar` §4's count corrected in the re-run paste below.
- [ticket] **`## Bar` §3's forward-reference count is stale against this
  ticket's own endpoint.** It records 3 lines; at `7f91a929` the grep prints 4,
  because this ticket's second build commit added `(Ticket 236)` to
  `TASKS.md:393`. The gate was measured before the commit it gates. Converged
  with [bar] below. — nit — NOW. Re-run at HEAD in the paste below: 12 lines, all history inside dated blocks, none carrying `CONSUMED BY`, `CONSUMES` or `deferred to`.
- [ticket] **One seam citation is off by one.** `## Seam check` says `LOCK_PATH`
  is at `:177`; at `9378a597` it is `:178` and at `34723f98` it is `:182`. The
  sibling citation, `setUpModule` at `:328`, is exact. — nit — NOW. `:178`.
- [ticket] **The `CONSUMED BY:` header names two far ends and `## Seam check`
  enumerates three.** `tests.test_database.ClusterLockTest` -- the one
  mechanical far end, and the only one a later `seam-check` grep can find --
  exists only in the report prose, not in the greppable field. Add it in the
  `<module::symbol>, reading <literal>` form. — nit — NOW. `tests.test_database.ClusterLockTest, reading LOCK_REASON` added to the field.

- [bar] **The machine lines were cleared against the first build commit only,
  and the second commit invalidated two of them.** §3's grep prints 4 at
  `7f91a929`, not 3. §5 assigns `docs/specs/production-harness-v2/TASKS.md` to
  "ticket 134's review cycle", which the corrected `Touches` line and the
  "Paid, 2026-09-02" note in `## Build findings` directly contradict -- that
  file is this ticket's own second commit. Only `check_audit` was re-run after
  it. The 4th grep hit carries no `CONSUMED BY`, `CONSUMES` or `deferred to`,
  so §3 still passes on the rule, just not on the number. Converged with
  [ticket] above. — required — NOW. §5's clause corrected to say which part of `TASKS.md` was whose, and §1-6 re-run at HEAD in the paste below.
- [bar] **§4's "1359 tests and over thirty minutes" is the sole justification
  for not running `tests/test_database.py`, and it is an unmeasured number
  lifted out of the page this ticket was editing.** `docs/agents/testing.md`
  claims its numbers are "measured on this repository rather than estimated";
  they were correct at `09e930e1` and have since drifted to 56004 lines / 1572
  `def test` at `7f91a929`. `## Resolution`'s "47000-line database file" is the
  same stale figure. Either measure the count in the Bar paste, or correct the
  page, which this ticket already owns. Converged with [seam], [ticket] and
  [craft]. — required — NOW. Covered by the page re-measure; the paste below carries the measured count in place of the quoted one.
- [bar] **`## Build findings` contradicts this ticket's own measurement.** "That
  run's 101 skips included all 1359 database tests" is refuted by
  `## What was measured`, which prints `OK (skipped=1)`: a `setUpModule` skip
  reports one skip standing for the whole module, so at most 1 of those 101 was
  the database file. The conclusion -- leave `TASKS.md:337` to ticket 65 -- does
  not turn on the arithmetic. — nit — NOW. The clause is dropped and the part that holds -- the 3996 excludes them -- is kept.
- [bar] **Two slips in the `okf` citation in `## Build findings`.** `5c35ca1e`
  is two commits earlier, not four. And ticket 235's own review later ruled that
  docstring edit a defect routed around in prose, reverted the docstring and
  fixed `okf.build` instead (`235-...md:517`). — nit — NOW. "Two commits", and 235's review named as the fix that stands.

- [craft] **The page's four headline numbers are stale, and this is the commit
  that edits the page and adds a class to the file it counts.** Measured at HEAD
  with `unittest.TestLoader().discover('tests', top_level_dir='.')`: 4359 tests
  and 60 modules against the page's 3659 and 53. The wrong 1359 has propagated
  into this ticket's `## Bar` and into the brief for this review. The 37% ratio
  survives a re-measure; the absolutes do not. Converged with [seam], [ticket]
  and [bar]. — required — NOW. Same repair as [seam] and [ticket] above. Converged three ways, which is why it was worth a re-measure rather than a note.
- [craft] **The new operator guidance rests on a premise this tree
  contradicts.** `tests/test_database.py:171-181` says the lock "is `hunt.sh`'s"
  and that "the hunt loop has taken this lock since it was written";
  `tools/hunt-loop.sh` takes no `flock` and never names `/tmp/rk2-db.lock`. The
  diff promotes an undocumented env var into published advice in two places --
  `LOCK_REASON` and `docs/agents/testing.md` -- and following it while
  `tools/hunt-loop.sh` runs on that cluster reproduces ticket 197's incident,
  because the in-repo loop holds no lock to be "the hunt on". The same gap makes
  the page's "no exceptions, not even a one-off probe" false for the
  distribution it covers. Converged with [ticket] above. — required — REOPEN ticket 197. Converged with [ticket] above.
- [craft] **The module docstring still says every class needs PostgreSQL, and
  this diff added the one class for which that is false.** Line 3 reads "the
  module skips itself unless `RK_TEST_SUPERUSER_URL` names one";
  `ClusterLockTest` passes with the variable unset (`Ran 1 test in 0.903s` /
  `OK`). The correction lives 640 lines away in the class's own docstring, and
  the page's "read the class list rather than guessing" tip now hands a reader a
  non-database class. Add the clause to the module docstring. — required — NOW. The module docstring now names `ClusterLockTest` as the one class that runs with the variable unset.
- [craft] **The password-rotation citation is stale and the diff shifted its
  target.** `docs/agents/testing.md:104` cites `:313`; the rotation
  (`secrets.token_urlsafe(18)` in `_build`) is at `:374`, and `:313` lands on a
  `pg.Settings` field annotation. Point at `_build` by name. Converged with
  [seam] above. — nit — NOW. Converged with [seam] above; the same repair covers both.
- [craft] **The refusal an operator reads arrives under a chained traceback.**
  `raise RuntimeError(LOCK_REASON)` fires inside `except OSError`, so the four
  sentences print after "During handling of the above exception, another
  exception occurred" and a `BlockingIOError` traceback -- measured, 15 lines of
  it. `raise ... from None` is one word and leaves the message clean;
  `ClusterLockTest` passes either way. — nit — NOW. `raise RuntimeError(LOCK_REASON) from None`, against a watched red: `assertNotIn("BlockingIOError", told)` was added to `ClusterLockTest` first and failed with the 15-line chained traceback carried in the assertion message. Production code, so the red came first and the machine lines were re-run.
- [craft] **The seam test pins the whole message as one substring.**
  `assertIn(LOCK_REASON, told)` turns a reflow or a reworded remedy into a test
  edit while the behaviour under test is unchanged. The mutation the ticket ran
  is caught by far less. Assert the two stable parts:
  `f"another session holds {LOCK_PATH}"` and `"Do not wrap the command in
  flock"`. — nit — DECLINED. The whole-message assertion is what criterion 2's mutation proof rests on -- narrowing `RuntimeError(LOCK_REASON)` to `RuntimeError("busy")` is caught precisely because the message is pinned. Loosening it trades that proof for reflow convenience.
- [craft] **The same rule is now restated in four places in one file.** The `#:`
  block at `:178-181`, `LOCK_REASON` at `:187`, the `setUpModule` comment at
  `:350-353`, and the `ClusterLockTest` docstring at `:640-644`. The `:178-181`
  block earns least and says so itself; `LOCK_REASON` two lines below is
  criterion 3's sentence and reaches the operator at runtime. Drop the added
  `#:` paragraph. — nit — DECLINED. The `#:` block at `LOCK_PATH` is where criterion 3 lands -- "the lock is documented where it is taken". `LOCK_REASON` is runtime text an operator reads after a refusal, not source documentation a reader of the file meets at the constant. The other two serve different readers again.

Review cycle 1 of 3 — undecided: none
