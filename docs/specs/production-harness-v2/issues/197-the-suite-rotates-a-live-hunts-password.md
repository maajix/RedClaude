# 197 — The suite rotates a live hunt's password

**What to build:** the other side of the lock `hunt.sh` has always taken.

**Blocked by:** nothing.

**Status:** resolved

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

## Why

A test suite that can stop a live engagement is not a test suite with a
footnote, it is a shared resource with no mutual exclusion. The footnote was
written — in `hunt.sh`, naming this exact module — and the module it names
never read it. One side of a lock is not a lock.

The cost here was 220 minutes of sitting and three laps that read as refusals
from the target. The refusal text was honest and pointed straight at the cause,
which is the only reason this was a fifteen-minute diagnosis rather than an
afternoon.
