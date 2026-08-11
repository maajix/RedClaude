# 03 — Run production migrations and the integrity gate

**What to build:** Let the operator create, upgrade and verify the complete production database through supported application commands rather than prototype shell composition.

**Blocked by:** 02 — Boot an installable `rk doctor`.

**Status:** resolved

- [x] A supported migration command applies the complete ordered schema corpus to an empty Postgres database and is safe to rerun.
- [x] The promoted schema uses one causal Lane vocabulary — `agent`, `replay` and `proxy_internal` — while control and transport metadata use separate types.
- [x] Row Events are trigger-authored, direct lifecycle-cache writes are refused and writes without transaction actor context fail loudly.
- [x] All registered schema, Event, provenance, Receipt, scope, scheduler and catalogue integrity checks run through one supported gate.
- [x] Every hard integrity check has a negative control that demonstrably makes it fail.
- [x] Clean creation, dump, restore and post-restore integrity all pass without `docker exec psql` or prototype runtime helpers.

## Comments

Implemented on branch `implementation/startup-assertion` in commit `6c87bbe` on
2026-08-09.

`rk db provision|migrate|verify|status|dump|restore` is the whole surface.
`src/redkraken/pg.py` is a stdlib wire client, so the application still declares
no third-party dependency; `migrate` lints the corpus before it opens a
connection and ends every run with six finalizers and the gate; `integrity` is
the single gate over the server baseline, the role catalogue and the registered
standing checks; `backup` restores into a provisioned empty database and repairs
the two things `pg_dump` cannot carry.

Verified against PostgreSQL 18.4 with pgvector 0.8.6.
`tests/test_database.py` is 31 live tests: 42 migrations applied to an empty
database, a rerun applying nothing with 62 assertions holding, the Lane
constraint read back from `pg_get_constraintdef`, a trigger-authored
`entity.created`, refusals for a write with no actor context, a write carrying
an earlier transaction's actor and a direct `hypotheses.status` write, one gate
covering all three families, and dump → provision → restore → gate.

Criterion 5 is not complete. All 51 checks the gate runs are accounted for, and
`test_every_check_the_gate_runs_has_a_control` fails by name if a new check
arrives without an entry:

- 45 have a control that makes that named check report false.
- Four cannot: `roles:proxy_role_exists`, `roles:runtime_role_exists`,
  `baseline:pgvector_version` and `baseline:hnsw_cosine_opclass`. Taking their
  subject away makes a sibling check in the same function raise, which aborts
  the family before any row is returned. The gate reports that as a refusal and
  exits 9 naming the missing object, which is the property that protects an
  operator, but the check that was about to fail is never named. The test
  asserts the refusal instead, and says so.
- Two are properties of the running binary: `baseline:server_major` and
  `baseline:uuidv7_is_builtin`. Falsifying either means a different PostgreSQL.

The last two have no negative control, and the four family-refusal cases do not
make the named check return false. Accounting for them keeps a new untested
check visible, but it is not the acceptance criterion as written; the box stays
unticked until those checks have an executable falsification.

Three defects the review found were fixed before the commit: `_apply` inlined
`set_actor()`'s body instead of calling it (it now calls the helper wherever it
exists, and documents why the first twelve migrations cannot);
`uuidv7_is_builtin` read a scalar subquery that would have raised, aborting the
whole baseline, on a second zero-argument `uuidv7()`; and `rk db restore`
promised an empty target without checking, so a non-empty one failed as raw
`pg_restore` stderr rather than as a refusal.

One limit worth naming: the live suite skips unless `RK_TEST_SUPERUSER_URL` is
set, and the repository has no CI, so nothing forces it to run. Until there is
one, the offline suite and `tools/check_baseline.py` are what a clean checkout
actually enforces.

### Review remediation, 2026-08-09

`/code-review` against the merge base raised 15 findings. Two were
self-refuted in the reviewer's own report and one is filed as ticket 66 rather
than fixed here; the rest are closed.

The wire client was the substance of it. `pg.Connection` had no notion of a
stream it could no longer parse: an unknown message tag was skipped silently,
so a `CopyInResponse` left the client waiting for a `ReadyForQuery` the server
would never send, and the next statement on that connection read the previous
one's bytes. It now refuses the stream, names COPY separately from an unknown
tag, marks the connection unusable and says so on the next statement instead of
answering from a desynchronised buffer. `close()` no longer writes Terminate
into a stream it knows is broken, the connect timeout is cleared once the
connection is up so a long migration is not cut off at the connect budget, a
literal IP address no longer travels as an SNI server name, and a password
SASLprep rejects is a refusal rather than a `ValueError` out of the client.

The advisory lock covered one migration at a time, which serialized the writing
and left the deciding unguarded: two runners reading an empty
`schema_migrations` in the same moment both planned every file. `exclusive` now
holds a session lock across the plan, the apply loop, the finalizers and the
gate. `rk db verify` and `rk db status` refuse the wrong connection string the
way `migrate` already did, the gate's own counts reach the `migrate` and
`restore` reports rather than being dropped on the floor, a failed `pg_dump` no
longer leaves a partial archive that makes the retry fail as "already exists",
`PGCONNECT_TIMEOUT` never truncates a sub-second budget to `0`, which libpq
reads as no budget at all, and a connection that drops mid-command is rendered
as a report rather than a traceback.

Two live tests could not fail and now can:
`test_the_restore_repairs_what_the_archive_could_not_carry` asserted only that a
ledger key existed and now reads `pg_db_role_setting` back against the migrated
database, and `test_the_restored_database_still_authors_its_own_events` counted
triggers against the config rows that declare them and now writes a row and
reads the Event it authored. The live suite is 39 tests, and
`tests/test_backup.py` covers offline what the archive tests cannot reach.

Ticket 66 is the one finding left open. `rk2_runtime` can execute
`answer_decision`, `register_proxy_artifacts` and `write_blocked_receipt`,
which the corpus gates to `rk2_human` and `rk2_proxy`, because those three were
revoked `FROM PUBLIC` rather than from the role that `ALTER DEFAULT PRIVILEGES`
had already granted them to. Fixing it means changing promoted schema and
deciding what the runtime's privilege surface is, which is not what a ticket
about running migrations gets to decide silently.

### Completion remediation, 2026-08-11

The earlier criterion-5 limitation is superseded. The server baseline now
passes its observed runtime facts through `evaluate_server_runtime`, a pure
gate evaluator. The four binary/extension facts can therefore be supplied one
independently false observation at a time without pretending the live server
changed underneath the test. Missing runtime and proxy roles now produce their
own named false catalogue checks rather than aborting a whole family first.

The live negative-control suite consequently has an executable falsification
for every check the gate runs. Its coverage assertion still fails by name when
a new registered check arrives without a control.
