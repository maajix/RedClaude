# Throwaway schema prototype — tickets 32 and 33

Ticket 32 executed the 1337 lines of SQL tickets 06, 07 and 08 decided on.
Ticket 33 turned the fourteen migrations that fourteen sibling tickets each
wrote in isolation into one corpus that applies from empty, in one order, on one
server, with every standing check silent.

This is still a prototype. It is not the migration set the build will ship. It
is the evidence that the decisions survive contact with the database, and — from
ticket 33 — that they survive contact with **each other**.

Headline: **38 migrations, 113 managed tables, 19 standing checks, 0 problems.**
`./run_all.sh` is that claim, executed.

## Postgres major: 18

Pinned by `uuidv7()`, a `pg_catalog` builtin only from 18. Nothing in the source
tickets ever said so. Proof: `pgvector/pgvector:pg17` fails on the very first
table with

```
ERROR:  function uuidv7() does not exist
```

Full forcing list, highest floor first:

| Feature | Floor | Where |
| --- | --- | --- |
| `uuidv7()` builtin | PG 18 | every `id` default |
| `NULLS NOT DISTINCT` on a unique index | PG 15 | `tasks_live_dedup_idx` |
| `xid8` / `pg_current_xact_id()` | PG 13 | `events.txid` |
| `INCLUDE` on an index | PG 11 | several |
| `GENERATED ALWAYS AS IDENTITY` | PG 10 | `events.id`, `label_counters` |
| pgvector `hnsw` + `vector_cosine_ops` | pgvector 0.5 | `hypothesis_embeddings` |

Verified on `pgvector/pgvector:pg18` = Postgres 18.4, pgvector 0.8.6.

## Layout

```
migrate.sh          the runner: provision | up | status | verify | lint
new_migration.sh    prints the one legal filename for a new migration
restore.sh          the decided restore procedure, and what a restore may be forgiven
measure_hnsw.sh     the maintenance_work_mem measurement the settings migration cites
prove_holes.sh      43 adversarial checks: every guard shown going from silent to raising
run_all.sh          ten passes; the whole ticket, executed, one container
migrations/         001..016 frozen, then YYYYMMDDTHHMMSSZ__slug.sql
tests/
  _harness.sql        schema t, table t.results, expect_raise / expect_ok / expect_true
  seed.sql            the canonical fixture: two programs, scope policy, receipts
  checks_a.sql        constraint and trigger checks (group A)
  checks_b.sql        purge, replica-mode and integrity-checker checks (group B)
  checks_c.sql        ticket 33's 19 corpus checks (M01–M19)
  capability_receipts.sql  capability-backed receipt checks (K01–K04)
  scheduler.sql       scheduler fixture plus rank_pass() and claim_one()
  ticket07_checker.sql  ticket 07's event checker under a second name, for prove_holes
  999_drift_probe.sql   the migration nobody should write, written on purpose
```

## The numbering rule

Two filename forms, and `migrate.sh lint` refuses everything else:

```
NNN_slug.sql                  frozen baseline, NNN <= 016
YYYYMMDDTHHMMSSZ__slug.sql    every migration authored after it
```

Identity is the filename minus `.sql`; order is that identity ascending in C
collation, where `'0' < '2'` puts every legacy file before every timestamped one.
The freeze is at 016 because that is what branch `prototype/schema` contains at
`cfdc26e` and every sibling branch was cut from it. Past that, numbers are not
assignable: ticket 06 and ticket 08 both wrote an `011` and ticket 07 wrote a
`012` without either of them being wrong. A UTC timestamp is collision-free
without anyone having to look at what anyone else picked.

Enforced, not documented. `lint` refuses:

- a numeric name above 016, printing the `git mv` that fixes it;
- two files claiming one legacy number (different ids, so the duplicate-identity
  test cannot see it — the 011/011 collision, exactly);
- a name matching neither form;
- `BEGIN`/`COMMIT` inside a migration (apply and record are one transaction, and
  a migration that commits its own leaves the bookkeeping in a second one);
- `CREATE`/`ALTER`/`DROP`/`COMMENT ON ROLE` (roles are cluster-global and
  provisioning, and `rk2_migrate` deliberately has no `CREATEROLE`).

Ticket 32's ordering constraint survives it: `attach_event_triggers()` still has
to run after the last table exists, and now does so on **every** run, from the
runner, rather than from whichever migration happened to be last.

## The runner

`rk2_meta.schema_migrations` holds id, sha256, applied_at, applied_by and the
runner version. `migrate.sh up`:

1. `lint`;
2. takes advisory lock `8158253941`, so two runners cannot interleave;
3. `precheck` — refuses if an applied file's checksum changed, or if a pending
   file sorts before one already applied (a merge from a parallel branch);
4. applies each pending file and writes its version row **in one transaction**,
   so there is no half-applied state to design a repair for;
5. runs the finalizers;
6. `verify`, which exits non-zero if anything is not true.

Finalizers, unconditional, in this order: `apply_server_settings()`,
`attach_event_triggers()`, `enforce_always_triggers()`, `apply_state_rls()`,
`apply_state_grants()`, `enforce_fk_fire_order()`. They exist because the
alternative is asking every future migration author to remember six things; the
finalizer makes the class of drift impossible rather than fixed once per
migration. This is why the drift probe's missing RLS is silently healed while
its four other defects fail the run.

## Standing checks

`standing_checks` is a table, `run_standing_checks()` runs every row, and
`assert_standing_checks()` raises. 19 checks. `check_check_registration()` is
the one that closes the loop: a `check_%` function in `public` with no
`standing_checks` row is itself a problem. Nine of the twelve checkers the
corpus inherited had no caller at all after their own migration committed, which
is why four of the five defects this ticket was given were live.

## Roles, settings, restore

Six roles: `rk2_owner` (owns everything), `rk2_migrate` (applies migrations, no
`CREATEROLE`), `rk2_runtime` (the write connection), `rk2_state` (the agent read
connection, column-level grants only), `rk2_human` (membership is the only thing
authorising `actor_kind='human'`), `rk2_restore`.

Settings ship as `ALTER DATABASE ... SET` and are asserted with their source, so
a session `SET` cannot satisfy them. `maintenance_work_mem = 256MB` is measured,
not guessed — see `measure_hnsw.sh` and the table in the settings migration.
Postmaster-context GUCs (`wal_level`, `shared_buffers`, `max_connections`)
cannot ship as a migration at all and are asserted instead; that is also the
answer to the full-history-auditing question, which needs `wal_level=logical` or
pgaudit and is therefore an image decision, not a schema one.

`restore.sh` is the decided restore procedure. Data-only restore into a
populated schema is not supported. A full restore into a freshly provisioned
database needs no trigger manipulation, and `migrate.sh up` afterwards is not
decoration: `pg_dump` does not carry `ALTER DATABASE ... SET`, and `pg_restore`
recreates foreign keys in dump order, which puts 8 parent/child pairs in an
order where a purge raises instead of cascading. One check tolerance exists and
is named: after a restore, `row_last_write_unaccounted` is false for every row
by construction, because `xmin` is now the restore's transaction.

## Running it

```sh
./run_all.sh                    # everything: container rk2-mig-db, database rk2
./prove_holes.sh                # the adversarial suite, on its own database
CT=x DB=y ./migrate.sh up       # against an existing container
./migrate.sh status | verify | lint
```

`run_all.sh` has ten passes and ends `run_all: everything passed`. Groups A, B,
C and K end with an `86 checks, 0 failing` line.

## Check inventory

Group A, `tests/checks_a.sql`. Ticket 32 shipped three of these (C24–C26) as
assertions that a **hole** was open; ticket 35's migration closed all three and
they are now `expect_raise` naming the constraint that refuses.

| Check | What it pins |
| --- | --- |
| C01, C02 | direct write to `status` raises, on both `hypotheses` and `findings` |
| C03 | `testable -> testing` refused with `actor_kind='llm'` |
| C04 | `testable -> testing` refused with `actor_kind='runtime'` and no receipt |
| C05 | `testable -> testing` accepted with `actor_kind='runtime'` plus a receipt |
| C06 | stale `from_status` refused |
| C07 | transition absent from `transition_rules` refused |
| C08 | `proposed -> supported` refused below the evidence count |
| C09 | `supported` refused without control evidence |
| C10 | `validated -> reported` refused without a human actor |
| C11 | `validated` refused with no `validated_by_test_run_id` |
| C12 | receipt with `actor_kind='proxy_internal'` refused for a transition |
| C13 | `observations` immutable — UPDATE raises |
| C14 | any row trigger raises when `app.actor_kind` is unset |
| C15 | `tasks_live_dedup_idx` refuses a second recon task with NULL `hypothesis_id` |
| C16 | the same task is allowed again once the first is `done` |
| C17 | `scheduler_weights_one_active` refuses a second active row |
| C18 | a second inactive weights row is allowed |
| C19 | one lane per `(program_id, kind)` |
| C20 | the same slot name in two programs is legal (ticket 35 scoped the index) |
| C20b | `identities_slot_idx` still refuses a duplicate slot within one program |
| C21 | composite FK refuses an endpoint on an entity of the wrong type |
| C22 | `identity_leases_exclusive_idx` refuses an overlapping lease |
| C23 | a transition may not cite a `proxy_internal` receipt |
| C24–C26 | closed by ticket 35: a transition may not cite another program's receipt or hypothesis, and a hypothesis may not point at another program's entity |
| C27 | `validated_by_test_run_id` must be a run of a test of one of the finding's own hypotheses |
| C28 | that run's `outcome` must be `holds`, enforced by composite FK |
| C29, C30 | a trigger cannot forge `status` on either table — the D6 payload |
| C31 | a legitimate transition still writes the `status` cache |
| C32 | `testing -> supported` refused citing a receipt no test run of that hypothesis produced |
| C33 | the same transition accepted citing its own test run's receipt |
| C34 | `test_runs` immutable — the pinned outcome cannot be rewritten |
| C35 | a cited `test_run` cannot be deleted, even under `app.purging` (D4, intended) |
| C36 | two unlabelled rows get distinct labels, past the labels the seed took |
| C37 | the seed's unlabelled rows were labelled and `label_counters` advanced |
| C38 | an entity type with no registered prefix raises |
| C39 | a skill's declared `evidence_profile` is consulted and can refuse |
| C40 | the same transition accepted once the profile is satisfied |
| C41 | registering an `evidence_profile` with no predicate function raises |

Group B, `tests/checks_b.sql` — ticket 07's re-resolution. B01–B14 run inside
rolled-back subtransactions like group A; B20–B26 need writes committed in one
transaction to be visible to a check in the next, so they run at top level on a
throwaway program that B25 purges.

| Check | What it pins |
| --- | --- |
| B01 | every non-internal trigger in `public` is `tgenabled='A'` |
| B02 | under `session_replication_role='replica'`, a write still emits and still gets a label |
| B03–B05 | replica mode does not defeat immutability, the causal `status` hinge, or the `events` envelope |
| B06 | the runtime role cannot `DISABLE TRIGGER` — `must be owner of table entities` |
| B07 | the runtime role cannot `SET session_replication_role` |
| B08 | the runtime role's ordinary write still emits, so the split costs nothing |
| B09–B12 | no single `entities`, `agent_runs`, `tasks` or `findings` row can be deleted, even under `app.purging` |
| B13 | no FK outside `purge_cascade_edges` has a delete action |
| B14 | `reject_mutation()` no longer exists (D1) |
| B20 | `check_event_log_integrity()` is silent on honest state |
| B21, B22 | an ignored-column write is recorded in `suppressed_writes` and is not a false positive |
| B23 | a mutation made with the emitter disabled is caught by `xmin` accounting |
| B24 | a row created and deleted inside the same disabled window is **not** caught — stated as a test, closed by B06/B07 rather than by detection |
| B25 | `DELETE FROM programs` still takes everything, under the new all-`NO ACTION` rules |
| B26 | the checker is silent again afterwards |

Group M, `tests/checks_c.sql`, 19 checks — ticket 33's, on the corpus rather
than on any one migration: the vocabularies and the fixture agree, scope policy
is published before a receipt can name it, a purge runs to completion with 021's
immutability guard installed, `resume_program()` no longer deletes a curated
emitter's rows, `rk2_state` holds no relation-level grant, and every checker in
the corpus is registered.

Group K, `tests/capability_receipts.sql`, proves that only an active database
gate can mint a capability, allowed receipts derive their authority from it,
and cross-program, fabricated, expired or closed-run capabilities do not resolve.

`prove_holes.sh` is the adversarial half: 43 cases, each run twice against the
same database at the same moment — once through ticket 07's checker and once
through the corpus's — so the interesting result is where the old one says
nothing. It also covers the runner: checksum drift, out-of-order arrival, both
numbering refusals, the settings assertion, and the restore entitlement.
