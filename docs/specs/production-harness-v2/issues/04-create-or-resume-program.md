# 04 — Create or resume a Program with the same command

**What to build:** Make `rk run` create a Program from validated configuration on first use and resume the same durable Program on later use without transcript or in-memory state.

**Blocked by:** 03 — Run production migrations and the integrity gate.

**Status:** resolved

- [x] The first `rk run` persists one Program, its configuration revision and source hash in one actor-attributed transaction.
- [x] The same command with the same Program identity resumes existing rows and does not create a duplicate Program.
- [x] Configuration drift is detected before execution and produces an explicit revision or refusal rather than silently replacing policy.
- [x] Program creation and resume each emit exactly one correctly typed Event with no secret configuration values.
- [x] Readiness failure before Program creation leaves the database unchanged; failure afterward leaves a durable, inspectable outcome.
- [x] The command returns only durable identifiers, lifecycle, stop reason, pending decisions and an integrity summary.

## Comments

Implemented on branch `implementation/startup-assertion` in commit `4662e2a` on
2026-08-10.

`src/redkraken/program.py` is the operation; `rk run --config <path>` is the
adapter over it. `20260809T213000Z__program_configuration.sql` is the first
timestamped migration — the numbers are frozen at 0042 — and adds
`program_configurations`: append-only revisions carrying both hashes the loader
computes, the validated document, and the `platform` and `token_budget` the
revision projects onto the `programs` row.

Identity is the slug in the file. Policy is `canonical_sha256`, taken over
sorted-key compact JSON, so reflowing the file or reordering its tables resumes
rather than recording a revision that changed nothing. A changed policy is
refused, naming both hashes and `--accept-change`; the flag records the next
revision instead of adopting it silently. Everything up to and including the
decision runs under one advisory lock, so two runs starting together cannot
both read no Program and both insert one.

### What is asserted, and by what

The offline suite is 223 tests, green, with `python -m compileall` and
`python tools/check_baseline.py` (`classifications=10 regressions=7
artifacts=223`). `tests/test_program.py` covers the two pure seams — `decide()`'s
four answers and `lifecycle()` — and the refusals that never open a connection.
`tests/test_integrity.py` covers the family subset: a caller asking for fewer
families never sends the other query, and the report names which ran.

`tests/test_database.py::ProgramRunTest` is ten live tests and the only class in
that module that commits, because what survives the transaction is its entire
subject. It runs as `rk2_runtime`, not as the owner: row level security is in
force and the readiness assertion is made about the connection production uses.
`tearDownClass` purges its Programs through `app.purging`, which is also what
proves the immutability triggers release for a purge and hold for anything else.

Run on 2026-08-10 against `pgvector/pgvector:pg18` — PostgreSQL 18.4 with
pgvector 0.8.6, the pairing ticket 03 was verified on. All ten pass, including
the negative controls for both branches of the new standing check.
`tests/test_database.py` is 49 live tests; the whole suite with the server
present is 272, one skip (`test_packaging`, which needs `setuptools==82.0.1`).

The commit predates that run: the code is `4662e2a`, unchanged by it.

The limit ticket 03 named still stands — the live suite skips unless
`RK_TEST_SUPERUSER_URL` is set and there is no CI, so nothing forces the run.
What a clean checkout enforces on its own is the 223-test offline suite and
`tools/check_baseline.py`.

### Decisions worth naming

`programs` stays classified `undecided` in `event_table_exempt`. It has no
`program_id` column, so `emit_event()` would write a NULL one; whether the
identity row should emit an event of its own is ticket 07's question. The
consequence is that `_revise`'s `UPDATE programs SET platform, token_budget`
writes nothing to the log by itself, so the revision recorded in the same
transaction restates both values, they are unredacted in `program.configured`,
and `check_program_configuration()` fails the gate when the root row and the
newest revision disagree. A budget change is therefore readable as a before and
an after, and a change made without a revision behind it is a gate failure.

Accepting a change emits two events, not one: a `program.configured` for the new
revision and a `run.resumed` for the sweep. Both happened.

`rk run` runs two of the gate's three families. The role catalogue is the
runner's — `0029_roles_and_grants.sql` revokes it from PUBLIC saying so — and it
is reachable as `rk2_runtime` today only through the default-privileges grant
that ticket 66 exists to close. Asking for it would have made 66 a breaking
change for every run. The report names the families that ran, so a narrowed gate
cannot read as a whole one.

The migration grants `rk2_runtime` `USAGE` on `rk2_meta` and `SELECT` on
`rk2_meta.schema_migrations`. Two of `check_server_baseline()`'s checks read that
table and the function is not `SECURITY DEFINER`, so without the grant the whole
baseline family raises and readiness cannot be answered on the runtime's own
connection. It is a read on one ledger table; ticket 66 should account for it
when it states the runtime's surface per object.

### Raised by review and deliberately not built here

- Compiling the configuration's scope into `program_scope_versions` is ticket
  08. A Program opened by `rk run` has revisions but no compiled scope, and
  nothing between here and 08 may write a Receipt that claims one.
- Invalidating dependent surface or epistemic state when a revision is accepted
  (decision 4) needs the surface and fingerprint machinery of 21 and 22.
- Occurrence-event payload schemas have no registry to validate against;
  `run.resumed` carries a self-declared `schema_version`. That registry is not
  in this ticket's criteria.
- `resume_program()`'s sweep authors row events of its own when it actually
  unclaims something. Criterion 4 is about the command's event; the sweep's are
  the durable record of what it changed.
