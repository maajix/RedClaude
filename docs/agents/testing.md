# Which tests to run, and when

The suite is 3659 tests across 53 modules. Running all of them for every change
is not a safety habit, it is a way of not measuring anything, because a run that
takes long enough gets skipped or read at the tail. This page says what to run
instead, and the numbers it rests on are measured on this repository rather than
estimated.

## The one shape that matters

`tests/test_database.py` is 47170 lines, 81 classes and **1359 tests** -- 37% of
the suite in one file. It is also the **only** module that needs a PostgreSQL
server. The other 52 modules, 2300 tests between them, run against nothing.

That split is the whole optimisation. A change that touches no schema, no verb
and no grant does not need the server at all, and a change that does need it
needs a handful of the 81 classes, not all of them.

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
`tests/test_database.py` classes to the same command, under the lock:

```
export RK_TEST_SUPERUSER_URL="postgres://postgres:...@127.0.0.1:5432/postgres"
export RK_TEST_DATABASE=<a name nobody else is using>
flock -w 3600 /tmp/rk2-db.lock uv run python -m unittest \
  tests.test_database.CleanCreationTest tests.test_database.<YourClass> -q
```

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
rotates their passwords on every run (`:313`), and `RK_TEST_DATABASE` isolates
the database but **not** the roles. Two concurrent database runs poison each
other with:

```
28P01: password authentication failed for user "rk2_migrate"
```

So every database invocation takes `flock -w 3600 /tmp/rk2-db.lock`, no
exceptions, not even a one-off probe. This also means database runs do not
parallelise: when several agents work at once, the server is the bottleneck and
tier 1 above is what keeps them out of each other's way.

## Known failures that are not yours

On this machine, before any change:

- three client-certificate tests, including
  `tests.test_identity.SessionTest.test_a_client_key_exists_as_a_private_temporary_only_while_tls_loads_it`
  and `tests.test_proxy` `test_an_identity_client_certificate_reaches_only_the_https_connector`;
- `tests.test_cli.ContainmentTest.test_no_module_is_loaded_from_a_nonproduction_tree`,
  because the virtual environment sits inside the worktree root;
- an order dependence: running `tests.test_roster` before `tests.test_execution`
  breaks `ChoiceTest.test_every_kind_the_scheduler_can_claim_has_exactly_one_role`.

`tests.test_audit` freezes the spec report as a literal string, so it goes red
whenever a ticket is resolved. It is refreshed by re-measuring, not by relaxing:

```
PYTHONPATH=$PWD python3 -s -c "import tools.check_audit as c; print(c.check())"
```
