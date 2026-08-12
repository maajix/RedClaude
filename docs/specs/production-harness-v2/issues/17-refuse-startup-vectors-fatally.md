# 17 — Refuse every startup vector fatally and durably

**What to build:** Exercise every credential and settings vector through the real launch interface and make any pre-spawn or init refusal a durable fatal supervisor outcome.

**Blocked by:** 04 — Create or resume a Program with the same command; 16 — Start one clean real Agent child.

**Status:** resolved

- [x] Every watched environment variable, settings helper, watched settings environment key, malformed setting and unexpected init source is parameterized through an actual child launch.
- [x] Pre-spawn violations construct the SDK transport zero times; init violations serve zero tools and close the transport.
- [x] Refusal closes the Agent run, returns its Task to pending without consuming an attempt, releases Task and Identity Leases and removes session bindings in one transaction.
- [x] Exactly one redacted `startup.refused` occurrence Event is emitted, and repeated cleanup is an idempotent no-op.
- [x] The supervisor latches after refusal, rejects another Agent run in the same process and exits non-zero; a clean process restart may proceed after remediation.
- [x] A refusal before Program creation leaves no invalid Event or state, and diagnostics expose names, phases and measured effects but no values.

## Comments

Implemented on branch `implementation/startup-assertion` in commit `79754bc` on
2026-08-12, and finished in the commit that follows this note, which carries the
review fixes.

Ticket 16 built the assertion; this one makes a failed assertion an outcome the
harness survives. Three parts. `agent.StartupRefusal` gained a subclass,
`Latched`, and the module gained the one piece of process state in it, `_LATCH`:
the first refusal in a process is remembered, and every later `agent_run` in the
same process raises `Latched.of` that same measurement rather than spawning
anything. A refusal is a fact about the machine, not about the run that happened
to hit it, so the second run is refused with the first run's violations -- the
remediation is the same remediation, and re-measuring would only be re-reading
an environment nothing has changed. The latch is a module global rather than a
field on something, because what it has to survive is every caller in the
process, and a caller holding it could drop it.

`agent.close_refusal` is the durable half: one call to
`close_startup_refusal(...)`, on a runtime connection bound to the Program, that
closes the Agent run, returns its Task to `pending` with the attempt given back,
releases the Task and Identity Leases, removes the session bindings and writes
one redacted `startup.refused` occurrence Event. All of it in one statement, so
a refusal is durable as a whole or not at all -- a half-applied cleanup is a
Task that lost an attempt to a machine misconfiguration. Repeating the call
finds nothing left and writes no second Event. The SQL constrains the phase to
`pre_spawn` or `init` and the payload to records with the refusal's four keys,
so a payload that is not a refusal closes nothing.

Third, `outcome.STARTUP_REFUSED` and `EXIT_STARTUP_REFUSED = 13`, placed in
`PRECEDENCE` between `MISSING_DEPENDENCY` and `INVALID_CONFIGURATION`: a
credential vector is a fact about the machine like a missing dependency, and it
outranks anything about this program's configuration, because no configuration
can be judged on a machine that must not start a run at all.

One migration came with it,
`20260812T050000Z__a_session_unbinding_is_a_write_the_log_accounts_for.sql`.
`agent_sessions` had an INSERT trigger and no UPDATE one, so unbinding a session
was a row the event log could not account for and
`check_event_log_integrity` reported `row_last_write_unaccounted` the moment a
refusal unbound one. The migration registers `session.unbound`, sets
`event_table_config.updated_type` and asserts the UPDATE bit is actually on the
trigger afterwards, rather than trusting that `attach_event_triggers()` was
called.

`tests/test_agent.py` is 47 tests and `StartupRefusalTest` in
`tests/test_database.py` is another 6, the second group against a real server
because whether a cleanup commits as a whole, whether a repeat finds anything,
and whether one Program can close another's run are questions only a server
answers. `VectorChildTest` drives every vector through a real child process:
each of the seven watched environment names, each of the same seven again inside
a settings document's `env` block, the settings helper, both at once, three
unreadable documents, and the four init families. Each case is compared against
`_startup.evaluate_inputs` for the same symbolic input, so the child and the
measured credential matrix are held to one answer rather than to two that agree.
`LatchTest` runs the latch in a real process and reads back what it spawned:
one launch for two runs, the second refusal a `Latched`, and exit status 13.

The suite is 870 tests. Fourteen failures are pre-existing and environmental,
identical at HEAD before this work: ten in `ArchiveTest`, which needs `pg_dump`
and `pg_restore` on `PATH`, and four in `test_identity`, `test_proxy` and
`ProxyEgressTest`, which need `os.memfd_create`, absent from the uv CPython
builds this machine runs. `tools/check_baseline.py` reports
`classifications=10 regressions=7 artifacts=223`, and `compileall -q src tests
tools` is clean. Both interpreters, and with `RK_TEST_CONTAINERS=1` the
`test_agent`/`test_isolation` subset is 57 tests green, one skip.

### Two limitations, stated rather than worked around

*The init phase cannot be provoked by a real CLI.* On the measured runtime pair
there is no input that makes the CLI report an `apiKeySource` other than `none`
without a credential vector the pre-spawn phase has already refused -- which is
the point of the pre-spawn phase. So the four init families are provoked by
answering as a CLI that did: `VectorChildTest` launches a real child, in a real
environment, running `_launch.run` in its real order, and supplies only the
transport. What is measured there is the child's -- phase `init`, one source per
family, `agent.REFUSED` on the way out, nothing on standard output, and the
transport closed exactly once, read back from a file the child wrote after the
refusal. `InitRefusalTest` asks the same four questions one level in, where the
surface that never opened can be read directly.

*Criterion 5's "exits non-zero" has no production caller yet.*
`agent.diagnostics` turns a refusal into a `Report` whose `exit_code` is 13, and
nothing in `src/` calls it, because nothing in `src/` calls `agent_run` either:
the command that starts an Agent run is ticket 20. The exit path is exercised
by a real process rather than argued -- `LATCH_CHILD` calls
`agent.diagnostics(refusal).exit_code` and raises `SystemExit` with it -- and
wiring it into a command that does not exist would be building ticket 20 here.

### Three review suggestions not taken

*A third phase for the latched refusal.* `Latched` reuses the phase of the
refusal it repeats. The SQL function constrains the phase to exactly
`pre_spawn` or `init`, and it is right to: those are the two points a launch can
fail, and `latched` is not a third one -- it is the same failure, reported
again, at a run that never got as far as a phase.

*Recording the `Latched` Event against the second run's id.* Each Agent run gets
exactly one `startup.refused` Event, under its own id, carrying the violations
that are the reason it was refused. The alternative -- pointing the second run
at the first run's Event -- would make the log a place where one run's row
explains another's, and would leave the second run with no record of why it was
closed.

*Having `close_refusal` call `program.assert_runtime_connection`.* It takes a
Ledger and belongs at the command layer, where one exists. `close_refusal`
takes the connection it was handed and binds the Program on it, which is the
same idiom every other runtime-scoped call in this application uses.

### What the review axes changed

The Standards axis found the `assess` contract had gone stale: `managed_settings`
defaulted to `MANAGED_SETTINGS` evaluated at import time, so the seam a test
needs was also a way for one process's idea of where settings live to be
frozen into another's. It defaults to `None` now and resolves at the call, and
`_launch` passes nothing at all -- the process doing the asserting is the one
whose locations are read. It also found a data clump in the four arguments
`Latched` was rebuilt from at its one call site, now `Latched.of`; a mysterious
name, `_recordable`, now `_recording_program`; and duplicated test scaffolding
-- two `EXPORTED` constants with different values and two near-identical refusal
builders -- now `fixtures.EXPORTED`, `fixtures.startup_refusal` and
`fixtures.unlatched`, the last of which is what lets an in-process test provoke
a refusal without becoming the process that refused.

One bug came out of that axis rather than a smell: the cleanup in `agent_run`
was wrapped in a bare `except` that let a database error replace the refusal on
the way out, so a machine with a key exported into it and a database that had
just gone away would report the database. It is `raise refusal from failure`
now -- the classification is the refusal's, and the cleanup that could not run
is a row the lease expiry reclaims.

The Spec axis found criterion 1 partial on two counts. Watched settings
environment keys were exercised with one name, `ANTHROPIC_AUTH_TOKEN`, where the
environment vectors were exercised with all seven; the settings case now loops
`_startup.WATCHED_ENV_VECTORS` too, because a document's `env` block is the same
vector arriving by a route the process environment cannot be searched for. And
the unexpected init source never reached a child at all, which is the limitation
described above -- now met as far as it can be, by a real child that is handed
only the transport.
