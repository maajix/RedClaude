# 197 — The suite rotates a live hunt's password

**What to build:** the other side of the lock `hunt.sh` has always taken.

**Blocked by:** nothing.

**Status:** claimed

**PRODUCES:** changed -- `tools/hunt-loop.sh` holds an exclusive `flock` on the
cluster lock for the whole hunt, at the path `RK_TEST_CLUSTER_LOCK` names and
`/tmp/rk2-db.lock` by default.

**CONSUMED BY:** `tests.test_database::setUpModule`, reading `LOCK_PATH` with
`fcntl.flock(LOCK_EX | LOCK_NB)` and raising `LOCK_REASON` when it is held;
guarded by `tests.test_database.ClusterLockTest`.

**CONSUMES:** `RK_TEST_CLUSTER_LOCK`, the one path both sides resolve; the
`flock -w 60` / `exec 9>` pair quoted from `hunt.sh` in this ticket.

**Touches:** `tools/hunt-loop.sh`, `tests/test_database.py`,
`docs/agents/testing.md`. Corrected in §7:
`docs/specs/production-harness-v2/spec.md` is owed a `## Verify command` the
bar's second line has no substitute for, and `tools/check_audit.py` refuses a
spec section it does not audit, so the heading costs one entry in its
`SECTIONS` and one section in `tests/test_audit.py`'s `SMALL` fixture -- see
`## Build findings`.

- [x] **What happened.** 2026-08-26 06:20 UTC, sitting 02 of the here
      engagement, laps 65 to 67:

      ```
      lap 65 -> refused | ok False | exit 3
      lap 66 -> refused | ok False | exit 3
      lap 67 -> refused | ok False | exit 3
      STOPPING after 67: 3 laps in a row exited non-zero
      ```

      ```json
      {"code": "invalid_configuration", "source": "database",
       "detail": "rk2_runtime@127.0.0.1:55433/rk2here refused the connection:
                  28P01: password authentication failed for user \"rk2_runtime\""}
      ```

      Nothing was wrong with the engagement. `tests.test_database` had been run
      against the same cluster to settle ticket 188, and `_build` re-provisions
      every login role with `secrets.token_urlsafe(18)`. The six `rk2_*` roles
      are cluster-global, so the suite changed the live hunt's password while
      the hunt was holding a connection open.

- [x] **The lock already existed, on one side.** `hunt.sh` has taken
      `/tmp/rk2-db.lock` since it was written, and says why in its own comment:

      ```bash
      # The whole hunt runs under the database lock, not each lap. The six rk2_*
      # roles are cluster-global and `tests.test_database` rotates their
      # passwords; a hunt that loses its connection halfway leaves Tool runs
      # open against a live third-party target, which is the one state worth a
      # whole lock to avoid.
      exec 9>/tmp/rk2-db.lock
      flock -w 60 9 || { echo "another session holds /tmp/rk2-db.lock; not starting"; exit 5; }
      ```

      It names the suite by module. The suite never took the other side, so the
      lock only ever stopped a second hunt — the case it was not written for.

- [x] **The fix.** `setUpModule` opens `/tmp/rk2-db.lock` and takes `LOCK_EX |
      LOCK_NB` before `_build`, and `tearDownModule` closes it. Non-blocking,
      because waiting would be a suite sitting silent for the length of a
      sitting; it skips with the reason instead. `RK_TEST_CLUSTER_LOCK`
      overrides the path for anyone whose disposable server really is
      disposable.

- [x] **Measured after.** With sitting 02 running:

      ```
      setUpModule (tests.test_database) ... skipped 'another session holds
      /tmp/rk2-db.lock; a hunt is running on this cluster'
      ```

- [x] **The engagement was repaired, not recreated.** `rk db provision
      --database rk2here` with the engagement env sourced re-set the six
      passwords from `RK_PASSWORD_RK2_*`; `rk db verify` then answered
      `"violations": []`. No rows were touched and the door held its own
      connection throughout.

- [x] **The in-repo hunt loop takes the lock too.** `tools/hunt-loop.sh` calls
      itself a hunt in its own header -- "`rk run` works one Task per
      invocation, so a hunt is this loop" -- and takes no lock:
      `grep -n 'flock\|lock' tools/hunt-loop.sh` prints nothing across its 76
      lines. `hunt.sh` is the operator-side script this ticket quoted, and it is
      not in this repository, so an operator driving a hunt with the loop that
      *is* leaves the suite's non-blocking `flock` finding the path free and
      rotating the six cluster-global passwords underneath it. That is the
      incident at the top of this file, reproduced through the one hunt driver
      the repository ships. Either `tools/hunt-loop.sh` grows the same
      `exec 9>/tmp/rk2-db.lock` / `flock` pair `hunt.sh` carries, or it says in
      its header that it does not take the lock and must not run beside the
      suite.

      Built as the lock, not the footnote: `## Why` below rules the footnote
      out. `tools/hunt-loop.sh` now resolves
      `LOCK="${RK_TEST_CLUSTER_LOCK:-/tmp/rk2-db.lock}"` -- the same override
      `setUpModule` reads, because a driver locking a path the suite does not
      read for is not a lock -- takes `exec 9>"$LOCK"` and `flock -w 60 9`
      before its first lap, and exits 5 with `another session holds %s; not
      starting` when it cannot. Guarded by
      `tests.test_database.ClusterLockTest.test_the_hunt_loop_this_repository_ships_takes_the_other_side`,
      which drives the real script and the real `setUpModule` and asserts the
      refusal names the lock path.

- [ ] **The loop's own refusal branch gets a test, or the promoted block says
      which direction it covers.** `docs/specs/production-harness-v2/live-inputs.md`'s
      `## 197` block records two directions -- the loop holds and the suite
      is refused, and the mirror, the suite holds first and `tools/hunt-loop.sh`
      exits 5 -- under one `STATUS: promoted to
      tests.test_database.ClusterLockTest.test_the_hunt_loop_this_repository_ships_takes_the_other_side`,
      but that test drives only the first direction. Once a block promotes it
      is not replayed by hand again, so the mirror keeps exactly one proof,
      taken once, forever. Add a test that starts the loop against a path
      `RK_TEST_CLUSTER_LOCK` already holds and asserts exit 5 and `not
      starting`, or split the mirror into its own block kept at `live` until
      one exists.

## Reopened, 2026-09-03

Ticket 236's review cycle 1 raised this on two axes. This ticket's own `## Why`
is the argument for it -- "One side of a lock is not a lock" -- and
`tools/hunt-loop.sh` landed in the same commit as this ticket's fix without
taking a side. `tests/test_database.py:171-177` still tells a source reader
"the hunt loop has taken this lock since it was written", which is true of
`hunt.sh` and false of the loop in `tools/`.

## Why

A test suite that can stop a live engagement is not a test suite with a
footnote, it is a shared resource with no mutual exclusion. The footnote was
written — in `hunt.sh`, naming this exact module — and the module it names
never read it. One side of a lock is not a lock.

The cost here was 220 minutes of sitting and three laps that read as refusals
from the target. The refusal text was honest and pointed straight at the cause,
which is the only reason this was a fifteen-minute diagnosis rather than an
afternoon.

## Seam check, 2026-09-03

```
WROTE  the held flock on LOCK_PATH   READ BY  tests.test_database::setUpModule,
                                              reading RK_TEST_CLUSTER_LOCK and
                                              the default /tmp/rk2-db.lock
WROTE  "another session holds %s; not starting" / exit 5
                                     READ BY  operator, via tools/hunt-loop.sh
WROTE  the lock rule for both drivers
                                     READ BY  operator, via docs/agents/testing.md
READ   RK_TEST_CLUSTER_LOCK          WRITTEN BY  operator, by hand at the hunt env
READ   /tmp/rk2-db.lock (default)    WRITTEN BY  tests.test_database::LOCK_PATH;
                                                 hunt.sh, out of repo
```

Both sides resolve one pair of literals and nothing else does.
`grep -rn 'RK_TEST_CLUSTER_LOCK' src/ tests/ tools/ docs/agents/` prints seven
hits and `grep -rn 'rk2-db.lock'` prints seven, all of them one of: the
module's `LOCK_PATH` / `LOCK_REASON`, the loop's `LOCK=`, the new test, or the
operator page. No name drift, and no third spelling: `src/` has no hit on
either literal, so nothing in the application resolves this path.

`hunt.sh` is the out-of-repo far end this ticket quoted verbatim; grep cannot
cross that boundary, and what checks it is the literal default
`/tmp/rk2-db.lock` appearing in this ticket's own quotation of it. That is a
version pin by quotation, not a contract test, and it is the weakest end of
this seam.

Live, on the real default path, with the real script and the real
`setUpModule` -- `rk` stubbed as `sleep 30`, because `rk` is not on this seam:

```
--- probe /tmp/rk2-db.lock ---
LOCK-HELD by the loop
--- suite, same default path ---
    raise RuntimeError(LOCK_REASON) from None
RuntimeError: another session holds /tmp/rk2-db.lock; a hunt is running on this cluster. Wait for it to finish, or set RK_TEST_CLUSTER_LOCK to a path of your own if this server is not the one the hunt is on. Do not wrap the command in flock: this module takes the lock itself.
Ran 0 tests in 0.044s
FAILED (errors=1)
```

The mirror run, loop started while the lock was already held:

```
another session holds /tmp/rk2-db.lock; not starting
loop exit 5
```

`docs/specs/production-harness-v2/live-inputs.md` holds one block, `226`, at
`promoted to tests.test_database.RuntimeChainTest`, so there was nothing to
replay. This ticket's block was added at `197`.

**Double injected.** The `rk` stub, on both the live run and in the test. Rule
3b: what checks the real `rk` is every other class in
`tests/test_database.py` -- the stub replaces the thing that runs *inside* the
lock, never the lock, and `tools/hunt-loop.sh` takes the lock before it ever
resolves `rk` on `PATH`. Deferred to nothing; there is no real-`rk` assertion
this seam wants.

### Findings

- [seam] **`tools/hunt-loop.sh` reads `$RK_TEST_CLUSTER_LOCK`, a variable
  named for the test suite, from a production hunt driver. The name is the
  seam -- both sides must resolve one variable -- but a reader of the loop
  alone cannot tell why a hunt honours an `RK_TEST_*` override.** — nit —
  DECLINED. Renaming costs both sides plus `LOCK_REASON`, `docs/agents/testing.md`
  and ticket 236's published advice, and buys a nicer name for a variable
  neither side may resolve differently. The loop's comment states the reason in
  place: "It reads the same $RK_TEST_CLUSTER_LOCK override, because a loop
  locking a path the suite does not read for is not a lock at all."

## Build findings, 2026-09-03

- [build] **`uv` cannot create a virtual environment on this working tree, and
  destroyed the one that was there.** The tree is reached over a gvfs sftp
  mount at `/run/user/1000/gvfs/sftp:host=majix.server/home/majix/redKrakenV2`.
  `uv run python -m unittest ...` printed `Ignoring existing virtual
  environment linked to non-existent Python interpreter: .venv/bin/python3`,
  `Removed virtual environment at: .venv`, then `error: failed to symlink file
  from .../.venv/lib64 to lib: Input/output error (os error 5)`. The mount
  creates symlinks and cannot read them back -- `ln -s lib ./ptest/lib64;
  readlink ./ptest/lib64` prints an empty line, and `ls -la` on one reports
  `cannot read symbolic link: Function not implemented` -- so no `venv`
  layout survives here. `.venv/` is gitignored, so nothing tracked was lost,
  but every `uv run` command in `docs/agents/testing.md` is unusable from this
  mount until a `uv sync` is run on `majix.server` itself. — required —
  DECLINED for this session: not repairable from the mount that broke it. The
  repair is one operator command on the host, `cd ~/redKrakenV2 && uv sync`,
  named here and in this session's final report. Nothing in this ticket's diff
  caused or depends on it.
- [build] **`_build` rotates six passwords, not seven, and this ticket's own
  text said six while `docs/agents/testing.md` says seven roles.** Measured:
  `len(migrate.ROLES)` is 7 and `[r.name for r in migrate.ROLES if r.login]` is
  `['rk2_migrate', 'rk2_restore', 'rk2_runtime', 'rk2_state', 'rk2_human',
  'rk2_proxy']`, six; `tests/test_database.py:381` generates a password per
  `role.login` only. Both statements were true of different things and read as
  a contradiction. — nit — NOW. Both comments this diff touched now say "the
  six login roles in `migrate.ROLES`". `docs/agents/testing.md`'s own "seven
  roles in `migrate.ROLES` are cluster-global" is correct as written and was
  left alone.
- [build] **This effort has no `## Verify command`, so the standing bar's second
  line has had nothing to run since ticket 01.** `grep -n '^## ' spec.md`
  printed seven headings and none was it; `cut-slices` Rule 1 puts it on the
  walking skeleton's session, 196 tickets ago. Ticket 236's `## Bar` §4 shows
  the shape of the workaround -- it pasted a command assembled from
  `docs/agents/testing.md` instead. — required — NOW. Written into `spec.md`
  under `## Verify command`, in the `-v` form §7 requires, as the two halves
  the tiering already has: the no-server `discover` run and the with-server
  class list. It also records the `PYTHONPATH` the `tools/check_*`
  subprocesses need, which is what the three failures in this session's first
  baseline run turned out to be. `Touches` corrected to match.

  The heading was priced before it was written, because a wall answered first.
  WALL: `tools/check_audit.py:365`, `if set(found) != set(SECTIONS): raise
  AuditError(...)`, with `sections()` at `:347` registering `## ` only -- so the
  spec may hold no top-level heading the audit does not list, and the first
  attempt printed `audit failed: the spec must hold exactly the audited
  sections; missing [], unread ['Verify command']`. PRICE: one entry in
  `SECTIONS` and one section in `tests/test_audit.py`'s `SMALL` fixture, which
  `AuditShapeTest.read` feeds to the same equality check; `read_spec` parses
  only the four sections it names, so a fifth needs no parser -- measured, both
  files, `check_audit rc=0` and `Ran 70 tests / OK (skipped=3)`. PURPOSE: the
  bar's second line has somewhere to point, for every ticket in this effort and
  not only this one; a `### Verify command` nested under `Testing Decisions`
  would have cost nothing and left `grep -n '^## Verify command'` printing
  nothing, which is the next session rediscovering this finding. RULE: the
  checker's own comment -- "A requirement nobody audits because it arrived
  under a heading nobody parsed is the failure this list exists for" -- says a
  new section is added to the list on purpose, not routed around. The comment
  now records that this one entry states no requirement.
- [build] **Three tests fail on a checkout with no installed `redkraken`, and
  it reads as a regression.** First baseline run in the clone:
  `tests.test_coverage.CoverageGateTest.test_the_command_prints_the_report_and_succeeds`
  FAIL and two
  `test_no_engagement_state_is_read_as_knowledge_input` ERRORs, all on
  `ModuleNotFoundError: No module named 'redkraken'` inside a `tools/check_*`
  child. `tests/__init__.py:15` puts `src` on the *parent's* `sys.path`; the
  child inherits `PYTHONPATH`, which is empty. Identical on pristine `HEAD`, so
  not a regression; all three pass with `PYTHONPATH=$PWD:$PWD/src`. — nit —
  NOW. Recorded in `spec.md`'s new `## Verify command` so the next session does
  not diagnose it again. No code change: `uv run` sets this up, and the wall
  above is why this session had no `uv`.

Build session 2026-09-03 — undecided: none

## Resolution, 2026-09-03

The lock now has two sides in this repository. `tools/hunt-loop.sh` -- the one
hunt driver that ships here, and the one an operator following
`docs/agents/testing.md` actually runs -- resolves
`LOCK="${RK_TEST_CLUSTER_LOCK:-/tmp/rk2-db.lock}"`, takes `exec 9>"$LOCK"` and
`flock -w 60 9` before its first lap, and exits 5 with `another session holds
%s; not starting` when it cannot get it. That is the same path
`tests.test_database::setUpModule` reads through `LOCK_PATH`, which is the whole
seam: the override has to be read by both, because a driver locking a path the
suite does not read for leaves the suite's non-blocking `flock` finding it free
and rotating the six cluster-global login passwords underneath a live hunt --
the incident at the top of this file. Blocking with a timeout on the loop's
side and non-blocking on the suite's, because a suite run is minutes and worth
waiting out where a hunt is a whole sitting and is not.

Guarded by
`tests.test_database.ClusterLockTest.test_the_hunt_loop_this_repository_ships_takes_the_other_side`,
which runs the real script and the real `setUpModule` in one child chain with
only `rk` stubbed, on a lock path of the run's own, and asserts the suite's
refusal names that path. Two comments the reopen called false were corrected in
the same commit: `tests/test_database.py`'s `LOCK_PATH` block no longer tells a
reader "the hunt loop has taken this lock since it was written" as though it
were true of `tools/`, and `docs/agents/testing.md` now names both things that
take the lock themselves and must not be wrapped.

**Red:** `AssertionError: 'another session holds
/tmp/redkraken-tests-zwfbr0ym/tmpp926771n/cluster.lock' not found in
'setUpModule (tests.test_database) ... ERROR ... redkraken.pg.ConnectionError_:
cannot reach nobody@127.0.0.1:1/postgres: [Errno 111] Connection refused ...
Ran 0 tests in 0.084s ... FAILED (errors=1)\nsuite exit 1\n'` -- the suite
walked straight past the free lock into `_build`, which is the defect stated as
a traceback. … (the elided middle is the child's `_build` traceback, 24 lines)
**Mutated:** `tools/hunt-loop.sh:37`, `LOCK="${RK_TEST_CLUSTER_LOCK:-/tmp/rk2-db.lock}"`
-> `LOCK="/tmp/rk2-db.lock"`, so the loop locks a real path the test does not
read for -> the same assertion, on that run's own path: `AssertionError:
'another session holds /tmp/redkraken-tests-jg7zp2w2/tmpw5222hvt/cluster.lock'
not found in ...`. Restored, and both cases green again.
**Forward references left standing:** none.

Nothing in the ticket turned out wrong. The criterion offered two endings and
this took the first: `## Why` -- "A test suite that can stop a live engagement
is not a test suite with a footnote" -- rules the header-note ending out on its
own terms.

## Bar, 2026-09-03

Run in a `git clone --local` of this tree at `/tmp/rk197` with the diff
applied, because the working tree is reached over a gvfs sftp mount where a
single test class times out past 280s -- see `## Build findings`. Every command
below was run there and its output is pasted verbatim; the tree on the mount
carries the same diff, byte for byte, from `git diff > /tmp/rk197.diff`.

**1. Every acceptance criterion is ticked.**

```
$ grep -c '^- \[ \]' docs/specs/production-harness-v2/issues/197-the-suite-rotates-a-live-hunts-password.md
0
```

**2. The seam test passes, read by name.** The effort's verify command, first
half, which this session wrote into `spec.md` under `## Verify command` (see
`## Build findings`):

```
$ NO_COLOR=1 PYTHONPATH=$PWD:$PWD/src python -m unittest discover -s tests -t . -v
…
test_a_run_that_could_not_take_the_cluster_lock_is_not_green (tests.test_database.ClusterLockTest.test_a_run_that_could_not_take_the_cluster_lock_is_not_green) ... ok
test_the_hunt_loop_this_repository_ships_takes_the_other_side (tests.test_database.ClusterLockTest.test_the_hunt_loop_this_repository_ships_takes_the_other_side)
One side of a lock is not a lock -- ticket 197. ... ok
… (2835 test lines)
Ran 2835 tests in 253.461s

OK (skipped=220)
```

**3. Forward references this ticket redeemed.**

```
$ grep -rn 'ticket 197' docs/specs/production-harness-v2/ | grep -E 'CONSUMED BY|CONSUMES|deferred to' | wc -l
0
```

The five other `ticket 197` hits are all inside dated `##` blocks in ticket
236 -- its `## Bar` §4 and two `## Review findings` entries -- which the
redemption line reads as history. No seam-field head named this ticket, so
nothing was owed and nothing was rewritten.

**4. Existing tests still pass, nothing skipped, deleted or weakened.** Same
command on pristine `HEAD` in the same clone, via `git stash`:

```
$ git stash && NO_COLOR=1 PYTHONPATH=$PWD:$PWD/src python -m unittest discover -s tests -t .
Ran 2834 tests in 249.594s

OK (skipped=220)
```

2834 -> 2835 is this ticket's one added test, and the skip count is unchanged at
220 both ways. `git diff` adds no `.skip`, no `skipTest`, no `type: ignore`, no
`noqa` and no `TODO`:

```
$ git diff | grep -cE '^\+.*(\.skip|skipTest|@unittest\.skip|type: ignore|noqa|TODO)'
0
```

The four standing checkers, run as modules:

```
$ for m in check_audit check_wiring check_baseline check_coverage; do python -m tools.$m >/dev/null; echo "$m rc=$?"; done
check_audit rc=0
check_wiring rc=0
check_baseline rc=0
check_coverage rc=0
```

The full `tests/test_database.py` was **not** run: it needs a disposable
PostgreSQL 18 with pgvector, this session reached none, and pointing it at the
one cluster that answered on 127.0.0.1:5432 would rotate six cluster-global
passwords on a server nobody declared disposable -- which is this ticket's own
incident. `ClusterLockTest` is the one class in that file that needs no server
by design, and it is this ticket's class; every other class in it skips with
`set RK_TEST_SUPERUSER_URL …` and is untouched by this diff, which adds one
test method and edits one comment block.

**5. The diff contains only what this ticket asked for.**

```
$ git status --short --untracked-files=all
 M docs/agents/testing.md
 M docs/specs/production-harness-v2/issues/197-the-suite-rotates-a-live-hunts-password.md
 M docs/specs/production-harness-v2/live-inputs.md
 M docs/specs/production-harness-v2/spec.md
 M tests/test_audit.py
 M tests/test_database.py
 M tools/check_audit.py
 M tools/hunt-loop.sh
```

`tools/hunt-loop.sh`, `tests/test_database.py` and `docs/agents/testing.md` are
the `Touches` line. `tests/test_database.py` is also this ticket's test file,
which `Touches` does not list by rule. The three under
`docs/specs/production-harness-v2/` are this flow's own: the ticket file, the
`live-inputs.md` block §5 added, and `spec.md`'s `## Verify command`. That
heading is what pulls in the last two: `tools/check_audit.py` refuses a spec
section it does not audit, and `tests/test_audit.py`'s `SMALL` fixture is fed
to the same check. All four are the one NOW verdict in `## Build findings`, and
`Touches` was corrected in §7 to name them. No untracked file and no build
artifact.

**6. The ticket carries a resolution and a bar, and no handoff.**

```
$ grep -c '^## Resolution' <ticket>; grep -c '^## Bar' <ticket>; grep -c '^## Handoff' <ticket>
1
1
0
```

### By reading

- **Judgement — red watched, and broken once.** Both messages are in
  `## Resolution` and both were read in this session. The red is the honest one:
  with no lock in the loop the child walked past the free path into `_build` and
  died on the fake connection string, which is the incident's own shape. The
  mutation dropped the `RK_TEST_CLUSTER_LOCK` read from the loop so it locked a
  real path the test does not read for; the same assertion went red on that
  run's own temp path, and both cases were green again after restoring.
- **Judgement — no unexplained `NOBODY`.** `## Seam check` records five ends and
  none is bare `NOBODY`. Two are non-code by form and named as such:
  `operator, via tools/hunt-loop.sh` for the exit-5 refusal, and
  `hunt.sh, out of repo` as one of two writers of the default path. That
  out-of-repo end is the weakest and the report says so in place.
- **Judgement — the live run reached this ticket's case.** Not a green exit: the
  loop was probed holding `/tmp/rk2-db.lock` and the suite was then read
  refusing over that same path, in the two runs pasted under `## Seam check`,
  plus the mirror run where the loop refused at `loop exit 5`. That is exactly
  the state the 2026-08-26 incident was the absence of. `live-inputs.md` held
  one block, `226`, already `promoted`, so nothing was owed a replay; this
  ticket's block was added at `197`. The spec's `## Testing Decisions` names no
  load figure for this path.
- **Judgement — Rule 3b, the double.** One double, the `rk` stub, on both the
  test and the live run. `## Seam check` names what covers the real thing:
  `tools/hunt-loop.sh` takes the lock before it ever resolves `rk` on `PATH`,
  so the stub replaces what runs *inside* the lock and never the lock itself.
  No deferral ticket, because there is no real-`rk` assertion this seam wants.

**Review correction, 2026-09-03 (cycle 1).** §3 and §4 above grep this ticket
file too, so re-running either against the merged diff self-matches their own
pasted command text instead of reproducing the claimed counts -- ticket 236's
equivalent checks exclude themselves for the same reason. Re-run excluding
this file:

```
$ grep -rn 'ticket 197' docs/specs/production-harness-v2/ | grep -v '^docs/specs/production-harness-v2/issues/197-the-suite-rotates-a-live-hunts-password.md' | grep -E 'CONSUMED BY|CONSUMES|deferred to' | wc -l
0
$ git diff c52d0b8f...HEAD -- . ':(exclude)docs/specs/production-harness-v2/issues/197-the-suite-rotates-a-live-hunts-password.md' | grep -cE '^\+.*(\.skip|skipTest|@unittest\.skip|type: ignore|noqa|TODO)'
0
```

Both lines hold at `0`. §3's prose also undercounted: excluding this ticket's
own file, `ticket 197` gets six hits, not five -- five inside dated `##`
blocks in ticket 236 (its `## Bar` §4 and two `## Review findings` entries)
and one in `spec.md:834`, inside `## Verify command`'s own prose ("Written at
ticket 197..."), which is not a dated block. None of the six is `CONSUMED
BY`/`CONSUMES`/`deferred to`, so the redemption count was never wrong, only
the sentence describing where the other hits live.

## Review findings, 2026-09-03 — cycle 1

- [seam] **`docs/specs/production-harness-v2/live-inputs.md::## 197`: FAR END
  records two directions -- loop-holds/suite-refuses and the mirror,
  suite-holds/loop-refuses -- but `STATUS` reads `promoted to
  tests.test_database.ClusterLockTest.test_the_hunt_loop_this_repository_ships_takes_the_other_side`,
  and that test drives only the first direction; once promoted the mirror is
  never replayed by hand again.** — required — CRITERION on ticket 197. Added
  above as a new acceptance criterion.
- [ticket] **`## Bar` §3 and §4 grep this ticket's own file, so re-running
  either against the merged diff self-matches the pasted command text instead
  of reproducing the claimed `0`.** — nit — NOW. Corrected above, excluding
  the ticket file, matching ticket 236's convention.
- [bar] **`## Bar` §3's prose says "the five other `ticket 197` hits"; the
  count excluding this file is six, one of them in `spec.md:834`, which is
  neither in ticket 236 nor in a dated block.** — nit — NOW. Recounted and
  named above. Converged with [ticket] above.
- [bar] **`## Bar` §4's pasted `git diff | grep -c ...` -> `0` does not
  reproduce against the merged diff; it prints 3, all self-matches inside
  §4's own prose.** — nit — NOW. Same repair as the two entries above.
  Converged with [ticket] above.
- [craft] **`tools/hunt-loop.sh`'s lock comment restated
  `tests/test_database.py::LOCK_PATH`'s rationale paragraph almost verbatim
  instead of pointing at it -- this diff already had to fix the "six roles"
  fact in both copies once.** — required — NOW. Trimmed to the mechanical
  facts plus a pointer to `LOCK_PATH`.
- [craft] **`spec.md`'s `## Verify command` said `docs/agents/testing.md`
  "owns the tiering and the cluster lock rules these obey" but pasted
  commands that already differ from testing.md's (`python` vs `uv run
  python`/`.venv/bin/python`; always `-v` vs testing.md's `-q`) with no note
  that the difference is deliberate.** — required — NOW. One sentence added
  explaining both: bare `python` because `uv` cannot build a venv on this
  working tree (`## Build findings`), `-v` because printing every test's name
  is this command's job.
- [craft] **`tools/check_audit.py::SECTIONS`'s new `"Verify command"` entry is
  sentence-case where every sibling is Title Case.** — nit — DECLINED.
  Cosmetic only; a three-file rename (`spec.md`, `check_audit.py`,
  `tests/test_audit.py`'s `SMALL` fixture) for a casing preference is not
  worth the risk to an exact-match audit gate, and the string is used
  consistently everywhere it currently appears.

Review cycle 1 of 3 — undecided: none
