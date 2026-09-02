# 236 — The documented database test command runs nothing

**What to build:** A one-line correction to `docs/agents/testing.md`, and
whatever makes the trap loud rather than silent.

**Blocked by:** nothing.

**Status:** ready-for-agent

**PRODUCES:** changed contract -- the documented database test command, and a
loud refusal in place of a silent skip when `/tmp/rk2-db.lock` is already held.

**CONSUMED BY:** `operator, via uv run python -m unittest
tests.test_database.<Class>`; every session that follows
`docs/agents/testing.md`.

**CONSUMES:** `tests/test_database.py::setUpModule`, which takes
`/tmp/rk2-db.lock` itself and raises `unittest.SkipTest`;
`docs/agents/testing.md`.

**Touches:** `docs/agents/testing.md`, `tests/test_database.py`.


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

- [ ] **The page's command runs the tests.** Copied out of
      `docs/agents/testing.md` and pasted into a shell, it reports the class's
      tests rather than `Ran 0 tests`.
- [ ] **A skipped module is not a green run.** A skip of `setUpModule` for a
      held lock is distinguishable from a pass by whatever reads the result --
      the page says how, or the harness makes it non-zero.
- [ ] **The lock is documented where it is taken.** One sentence saying the
      suite takes the lock itself, so the next reader does not add a wrapper
      back.
