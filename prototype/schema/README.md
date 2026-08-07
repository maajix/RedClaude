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
migrations/   001..016, applied in filename order
tests/
  _harness.sql   schema t, table t.results, expect_raise / expect_ok / expect_true
  seed.sql       one realistic program plus the fixtures the checks need
  checks_a.sql   41 constraint and trigger checks (group A)
  checks_b.sql   21 purge, replica-mode and integrity-checker checks (group B)
  scheduler.sql  scheduler fixture plus rank_pass() and claim_one()
apply.sh      apply every migration, one transaction per file, ON_ERROR_STOP
run_all.sh    fresh container, fresh database, apply, seed, run groups A and B
```

`016_ticket07_fixes.sql` closes the divergences ticket 32 charged to ticket 07 —
D2, D3, D5, plus D1, which ticket 32 charged to ticket 08 but which is ticket
07's function — and one divergence ticket 32 did not find: every trigger in the
schema is skipped by `SET session_replication_role = 'replica'`, and every
foreign key with them.

`015_ticket06_fixes.sql` closes the five divergences ticket 32 charged to ticket
06 — D4, D6, D7, D8, D9 — and lands the schema debt tickets 08 and 09 left on
06's tables. It is the only migration written after the divergence list, and it
is where the reopened ticket 06 decisions actually execute. D10 and the
cross-program holes are ticket 35's, and are still open here.

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
Groups A and B print as one table and end with a `0 failing of 62` line.

To confirm the migrations are not accidentally idempotent, run `./apply.sh`
twice without dropping the database. The second run must fail, and does:

```
ERROR:  relation "programs" already exists
```

## Check inventory

Group A, `tests/checks_a.sql`, 41 checks, all passing. Three of them (C24–C26)
assert a **hole** — they pass because the database permits something the tickets
say should not happen. Each is commented as such in the file. All three are
cross-program citation, which is ticket 35's scope; the other three holes the
first run found (C23, C27, C28) were ticket 06's and are now assertions.

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
| C20 | `identities_slot_idx` refuses a duplicate slot name |
| C21 | composite FK refuses an endpoint on an entity of the wrong type |
| C22 | `identity_leases_exclusive_idx` refuses an overlapping lease |
| C23 | a transition may not cite a `proxy_internal` receipt |
| C24–C26 | holes, ticket 35: a transition may cite another program's receipt or a `program_id` that disagrees with its hypothesis; a hypothesis may point at another program's entity |
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

Group B, `tests/checks_b.sql`, 21 checks, all passing — ticket 07's
re-resolution. B01–B14 run inside rolled-back subtransactions like group A;
B20–B26 need writes committed in one transaction to be visible to a check in the
next, so they run at top level on a throwaway program that B25 purges.

| Check | What it pins |
| --- | --- |
| B01 | every non-internal trigger in `public` is `tgenabled='A'` |
| B02 | under `session_replication_role='replica'`, a write still emits and still gets a label |
| B03–B05 | replica mode does not defeat immutability, the causal `status` hinge, or the `events` envelope |
| B06 | the runtime role cannot `DISABLE TRIGGER` — `must be owner of table entities` |
| B07 | the runtime role cannot `SET session_replication_role` |
| B08 | the runtime role's ordinary write still emits, so the split costs nothing |
| B09–B12 | no single `entities`, `agent_runs`, `tasks` or `findings` row can be deleted, even under `app.purging` |
| B13 | no FK outside `purge_cascade_edges` has a delete action — the invariant a later migration would otherwise break silently |
| B14 | `reject_mutation()` no longer exists (D1) |
| B20 | `check_event_log_integrity()` is silent on honest state |
| B21, B22 | an ignored-column write is recorded in `suppressed_writes` and is not a false positive |
| B23 | a mutation made with the emitter disabled is caught by `xmin` accounting |
| B24 | a row created and deleted inside the same disabled window is **not** caught — stated as a test, closed by B06/B07 rather than by detection |
| B25 | `DELETE FROM programs` still takes everything, under the new all-`NO ACTION` rules |
| B26 | the checker is silent again afterwards |

Group C (ranking determinism, concurrent claim, HNSW) is probes rather than
assertions — run by hand against the same database, results in the ticket 32
answer.
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

- HNSW at 1536 dimensions outgrows the default 64MB `maintenance_work_mem` at
  9752 tuples. No ticket mentions a server setting. Ticket 33's.
- Cross-program citation is unconstrained (C24–C26). Ticket 35's.

Fixed by `016`, kept here so the diff is readable: a program holding any
`hypothesis_near_matches` row could never be purged, because ticket 08 attached
the old `reject_mutation()`; deleting a single `agent_runs` row was impossible
because `ON DELETE SET NULL` fired an UPDATE into immutable `observations`;
`events.task_id ON DELETE CASCADE` destroyed unrelated history;
`check_event_log_integrity()` read `pg_trigger` existence but not `tgenabled`,
so a disabled event trigger passed green.

Fixed by `015`, kept here so the diff is readable: `guard_status_cache()` gated
on `pg_trigger_depth() < 2`, so any trigger could write `status` with no
transition row; labels were wired to nothing, so a second unlabelled row in one
program hit `entities_program_id_label_key`; `RAISE EXCEPTION 'illegal transition
%s -> %s'` printed `testables -> supporteds`.
