# Throwaway schema prototype — ticket 32

The 1337 lines of SQL that tickets 06, 07 and 08 decided on, executed against a
real Postgres for the first time. Everything under `migrations/` is verbatim
from those tickets except where a comment says otherwise; everything under
`tests/` is new and exists only to push on the claims those tickets make.

This is a prototype. It is not the migration set the build will ship. It is the
evidence that the decisions in tickets 06, 07 and 08 do or do not survive
contact with the database — see the divergence list in the ticket 32 answer.

## Postgres major: 18

Pinned by `uuidv7()`, which is a `pg_catalog` builtin only from 18. Nothing in
the three tickets ever said so. Proof: `pgvector/pgvector:pg17` fails on the
very first table with

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
migrations/   001..014, applied in filename order
tests/
  _harness.sql   schema t, table t.results, expect_raise / expect_ok / expect_true
  seed.sql       one realistic program plus the fixtures the checks need
  checks_a.sql   28 constraint and trigger checks (group A)
  scheduler.sql  scheduler fixture plus rank_pass() and claim_one()
apply.sh      apply every migration, one transaction per file, ON_ERROR_STOP
run_all.sh    fresh container, fresh database, apply, seed, run group A
```

`014_scheduler_event_deltas.sql` is the only migration that is not verbatim from
a ticket. It applies the two deltas ticket 08 owes ticket 07 — the
`scheduler.idle` event type and `lease_expires_at` in the `tasks` ignored
columns — and then re-runs `attach_event_triggers()`. Ticket 08 names both
deltas in prose and ships neither as SQL.

Migration numbering is mine, not the tickets'. Ticket 06 ends at `011` and
ticket 08 also calls its file `011`; ticket 07 calls its file `012`. Order here
is 06 (001–011), then 08 (012), then 07 (013), because `attach_event_triggers()`
has to run after the last table exists.

## Running it

```sh
./run_all.sh                 # container rk2-schema, database rk2, image pgvector/pgvector:pg18
CT=other DB=other ./apply.sh # apply only, against an existing container
```

`run_all.sh` drops and recreates the database, so it is the from-empty check.
Group A prints as a table and ends with a `0 failing of 28` line.

To confirm the migrations are not accidentally idempotent, run `./apply.sh`
twice without dropping the database. The second run must fail, and does:

```
ERROR:  relation "programs" already exists
```

## Check inventory

Group A, `tests/checks_a.sql`, 28 checks, all passing. Six of them (C23–C28)
assert a **hole** — they pass because the database permits something the tickets
say should not happen. Each is commented as such in the file.

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
| C11 | `findings_check` refuses `validated` with no `validated_by_test_run_id` |
| C12 | receipt with `actor_kind='proxy_internal'` refused for a transition |
| C13 | `observations` immutable — UPDATE raises |
| C14 | any row trigger raises when `app.actor_kind` is unset |
| C15 | `tasks_live_dedup_idx` refuses a second recon task with NULL `hypothesis_id` |
| C16 | the same task is allowed again once the first is `done` |
| C17 | `scheduler_weights_one_active` refuses a second active row |
| C18 | a second inactive weights row is allowed |
| C19 | one lane per `(program_id, kind)` |
| C20 | `identities_slot_idx` refuses a duplicate slot name |
| C21 | composite FK refuses an endpoint on an entity of the wrong type |
| C22 | `identity_leases_exclusive_idx` refuses an overlapping lease |
| C23–C28 | holes: a transition may cite a `proxy_internal` receipt, another program's receipt, or a `program_id` that disagrees with its hypothesis; a hypothesis may point at another program's entity; `validated_by_test_run_id` may cite a test run of an unrelated test, or one whose `outcome` is `fails` |

Group B (purge, integrity checker, resume) and group C (ranking determinism,
concurrent claim, HNSW) are probes rather than assertions — they were run by
hand against the same database and their results are in the ticket 32 answer.
`tests/scheduler.sql` holds the fixture and the two functions those probes need:

- `rank_pass(program)` — the ranking pass from ticket 08, as far as it can be
  written. `novelty_for`, `cost_for` and `confidence_for` are stand-ins; each
  carries a comment naming the input ticket 08 does not supply
  (`|vocabulary|`, the observation `kind` list, `N` in "last N runs", the
  role-to-kind mapping, the `required_skills` registry).
- `claim_one(program, label)` — `FOR UPDATE SKIP LOCKED` against
  `scheduler_lanes`. Run four sessions against it: no double-claim, but lane
  caps are **not** held unless the caller also takes
  `pg_advisory_xact_lock`. That contradicts ticket 08's claim protocol.

## Known live defects the tests reproduce

Short list; the full one with tickets named is in the ticket 32 answer.

- A program holding any `hypothesis_near_matches` row can never be purged.
  Ticket 08 attaches the old `reject_mutation()`, which ticket 07 replaced.
- Deleting a single `agent_runs` row is impossible even under `app.purging`,
  because `ON DELETE SET NULL` fires an UPDATE into immutable `observations`.
- `events.task_id ON DELETE CASCADE` destroys unrelated history, and whether a
  task can be deleted at all depends on whether the runtime happened to set
  `app.task_id` when unrelated rows were written.
- `check_event_log_integrity()` reads `pg_trigger` existence but not
  `tgenabled`, so a disabled event trigger passes green.
- `guard_status_cache()` gates on `pg_trigger_depth() < 2`, so any trigger can
  write `status` directly with no transition row.
- HNSW at 1536 dimensions outgrows the default 64MB `maintenance_work_mem` at
  9752 tuples. No ticket mentions a server setting.
