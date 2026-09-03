# Which tests to run, and when

The suite is 4359 tests across 60 modules. Running all of them for every change
is not a safety habit, it is a way of not measuring anything, because a run that
takes long enough gets skipped or read at the tail. This page says what to run
instead, and the numbers it rests on are measured on this repository rather than
estimated.

## The one shape that matters

`tests/test_database.py` is 56920 lines, 92 classes and **1592 tests** -- 37% of
the suite in one file. It is also the **only** module that needs a PostgreSQL
server. The other 59 modules, 2767 tests between them, run against nothing.

That split is the whole optimisation. A change that touches no schema, no verb
and no grant does not need the server at all, and a change that does need it
needs a handful of the 92 classes, not all of them.

## The fixed cost of a database run

Creating the schema is paid once per process and dominates a small run:

| Invocation | Result |
|---|---|
| `tests.test_database.CleanCreationTest` | 9 tests, 24.8s |
| `+ ScopeEvaluatorTest` | 20 tests, 30.9s |
| `+ CallbackPublisherTest + CallbackAdmissionTest` | 45 tests, 44.5s |

Roughly 25 seconds of schema, then seconds per class. So **batch every database
class you need into one invocation**. Four separate one-class runs cost four
schemas; one four-class run costs one.

## Three tiers

**1. While you work -- the modules you touched.**
Name them explicitly. This is the loop you run dozens of times.

```
export PATH="$HOME/.local/bin:$PATH"
uv run python -m unittest tests.test_config tests.test_scope -q
```
Measured: 126 tests, 0.146s.

If the change touches schema, verbs or grants, add the covering
`tests/test_database.py` classes to the same command:

```
export RK_TEST_SUPERUSER_URL="postgres://postgres:...@127.0.0.1:5432/postgres"
export RK_TEST_DATABASE=<a name nobody else is using>
uv run python -m unittest \
  tests.test_database.CleanCreationTest tests.test_database.<YourClass> -q
```

**No `flock` on that command.** `tests/test_database.py::setUpModule` takes
`/tmp/rk2-db.lock` itself, so an outer wrapper is the "another session" the
module then declines to run beside. That wrapper was documented here until
ticket 236, and what it produced was `Ran 0 tests` / `OK` / exit 0 -- a green
schema run that never happened.

`CleanCreationTest` belongs in every database invocation: it is the one that
proves the corpus still applies from empty, which is what a new migration most
often breaks.

To find your classes, read the class list rather than guessing:

```
grep -n '^class .*Test' tests/test_database.py
```

**2. Before you hand a ticket back -- the four gates.**

```
PYTHONPATH=$PWD python3 -s tools/check_audit.py
PYTHONPATH=$PWD python3 -s tools/check_wiring.py
PYTHONPATH=$PWD python3 -s tools/check_baseline.py
PYTHONPATH=$PWD/src:$PWD python3 -s tools/check_coverage.py
```

Note the different `PYTHONPATH` on `check_coverage`: without `src` it dies with
`ModuleNotFoundError: No module named 'redkraken'` and misleadingly reports
rc=0. Three of the four are fast; `check_wiring` costs about 40 seconds.

Two test modules are slow for their size and are worth knowing about, because
they are the ones people add to a loop by accident: `tests.test_audit` is 70
tests in 64.6s (it rebuilds the whole spec report), and `tests.test_wiring`
carries most of a 41s pair.

**3. The full suite -- at named points only.**

Run everything when, and only when:

- a release candidate is about to be exercised;
- a migration lands that changes the schema broadly -- a new table, a dropped
  column, a changed role grant -- because those are the changes whose blast
  radius is not local;
- the ticket loop goes quiet and the tree is about to be left alone.

Anywhere else, a full run buys re-measurement of 3600 tests that could not have
been affected by the diff.

## The trap that makes concurrency expensive

The seven roles in `migrate.ROLES` are **cluster-global**. `tests/test_database.py`
rotates their passwords on every run (`_build`), and `RK_TEST_DATABASE` isolates
the database but **not** the roles. Two concurrent database runs poison each
other with:

```
28P01: password authentication failed for user "rk2_migrate"
```

So everything that touches this cluster runs under `/tmp/rk2-db.lock`, no
exceptions, not even a one-off `psql`. Two things already take that lock
themselves and must not be wrapped: the suite, in `setUpModule`, and
`tools/hunt-loop.sh`, which holds it for the whole hunt. Anything else still
needs its own `flock /tmp/rk2-db.lock`. This also means database runs do not
parallelise: when several agents work at once, the server is the bottleneck and
tier 1 above is what keeps them out of each other's way.

When the lock is already held, the run stops with a non-zero status and
`RuntimeError: another session holds /tmp/rk2-db.lock`, not with a skip. A skip
exits 0 and prints `OK`, which is indistinguishable from a pass to a reader and
to a CI step, so a run stopped by the lock now says so. Either wait for the
other session, or point `RK_TEST_CLUSTER_LOCK` at a path of your own if this
server is not the one the hunt is on.

One door is still silent on purpose: with `RK_TEST_SUPERUSER_URL` unset,
`setUpModule` returns early and the run prints `Ran 0 tests` / `OK` / exit 0.
That skip is what lets the other 59 modules be discovered and run on a machine
with no server, so it stays. It means an exported-and-typoed variable reads as
a pass -- check that the run reports the class's tests, not `Ran 0 tests`.

## Known failures that are not yours

On this machine, before any change:

- three client-certificate tests, including
  `tests.test_identity.SessionTest.test_a_client_key_exists_as_a_private_temporary_only_while_tls_loads_it`
  and `tests.test_proxy` `test_an_identity_client_certificate_reaches_only_the_https_connector`;
- `tests.test_cli.ContainmentTest.test_no_module_is_loaded_from_a_nonproduction_tree`,
  because the virtual environment sits inside the worktree root;
- an order dependence: running `tests.test_roster` before `tests.test_execution`
  breaks `ChoiceTest.test_every_kind_the_scheduler_can_claim_has_exactly_one_role`;
- `tests.test_database.CallbackAdmissionTest`
  `.test_an_arrival_cannot_backdate_itself_into_a_dead_correlator`, which is
  ticket 215: measured at a clean `8810e7c4`, it fails five times in six when
  asked on its own and passes after its twenty-four neighbours. A single red
  here is the flake, not your change -- re-run the whole class before believing
  it.

**`FORCE_COLOR` in the environment turns fifty-two `tests.test_cli` tests red.**
Python 3.14 colours `argparse` help, and
`OperatorSurfaceTest.test_every_command_has_a_handler_and_help_that_names_it`
asserts `format_help().startswith("usage: rk <name>")` against plain text. It is
one test with fifty-two subTests, so the count looks like a catastrophe and is
one assertion. Some terminals and some agent harnesses export `FORCE_COLOR`
without being asked. Run the suite with `NO_COLOR=1` and it is green:

```
NO_COLOR=1 PYTHONPATH=$PWD:$PWD/src .venv/bin/python -m unittest discover -s tests -t .
```

`tests.test_audit` freezes the spec report as a literal string, so it goes red
whenever a ticket is resolved. It is refreshed by re-measuring, not by relaxing:

```
PYTHONPATH=$PWD python3 -s -c "import tools.check_audit as c; print(c.check())"
```
