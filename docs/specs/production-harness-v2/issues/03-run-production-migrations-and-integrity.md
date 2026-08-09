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

Criterion 5, exactly. All 51 checks the gate runs are accounted for, and
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
