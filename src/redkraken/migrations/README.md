# The schema corpus

Forty-eight files that build the production database, applied in filename order by
`rk db migrate`. Nothing else applies them: there is no shell script, no
`docker exec psql`, and no ordering that lives in someone's head.

```
rk db provision --database rk2     # roles, database, vector extension (superuser, once)
rk db migrate                      # apply every pending file, finalize, verify
rk db verify                       # the same gate, on its own
rk db status                       # what is applied, what is pending
```

`rk db migrate` ends by running the integrity gate on a connection it opens
afterwards, so what it reports is what the next connection will see rather than
what this one started with.

## The rules the runner enforces before it connects

`load()` reads and lints in one step, and refuses the whole corpus rather than
applying half of it. A file is refused if it:

- is named neither `NNNN_slug.sql` nor `YYYYMMDDTHHMMSSZ__slug.sql`;
- claims a number above `0042` — the numbers are frozen, so a new migration is
  timestamped and two authors cannot claim one identity;
- shares a number with another file;
- is not UTF-8, or cannot be read;
- contains `BEGIN`, `COMMIT`, `ROLLBACK` or `START TRANSACTION` — the runner
  already wraps each file in one transaction with its own bookkeeping row, so a
  file that opens its own would commit the schema change without the row;
- contains role DDL — roles are cluster-global, `rk2_migrate` holds no
  `CREATEROLE`, and a role belongs in `rk db provision`.

Against the database, two more refusals outrank applying anything: a recorded
migration whose file has changed since it was applied, and a pending file that
sorts before something already applied. Both are schema drift (exit 8). The
answer to the second is to recreate the database and migrate from empty, which
is cheap precisely because nothing is live at that point.

## Finalizers

Six functions run once per run, in this order, in one transaction as
`rk2_owner`, whether or not anything was pending:

```
apply_server_settings  attach_event_triggers  enforce_always_triggers
apply_state_rls        apply_state_grants     enforce_fk_fire_order
```

They exist because four of the earlier corpus's invariants were established by
sweeping the tables that existed when a migration ran, so every table added
afterwards silently missed them. A finalizer is an end-of-run invariant instead:
the next migration written gets its RLS policy and its purge order without
asking, and the gate fails the run if it did not. They are also what makes a
restored database repairable by the same command that built it — `pg_dump`
carries neither
`ALTER DATABASE ... SET` nor the order foreign keys fire in, so `rk db restore`
runs the same six.

## What promotion changed

The corpus was promoted from the schema experiment that `baseline/status.json`
classifies as falsified. Each file records its own origin in its header — the
name it had there and the ticket that wrote it — so provenance is read next to
the SQL rather than from a table here that could drift from it. Three defects in
that register were closed on the way:

| Regression | What the experiment did | Where it is closed |
| --- | --- | --- |
| RK-REG-002 | Replay traffic was labelled as agent traffic | `0042_causal_attribution.sql` |
| RK-REG-004 | Actor context was session-wide, so one statement at connect time attributed every later transaction on a pooled connection | `0013_events.sql`, asserted by `0042` |
| RK-REG-007 | `control`, `transport`, `proxy-internal` and `runtime-internal` were used as Lane values | `0042_causal_attribution.sql` |

Lane answers one question — which party caused a request — and has exactly three
values: `agent`, `replay`, `proxy_internal`. What a request was *for* is
`purpose` (`control_plane`, `transport_measurement`), which is a different
column with a different check, because a Finding that rests on a receipt no
subagent ever made is the failure this separation exists to prevent.

Two structural changes came with the promotion: three numbering schemes were
folded into one order, and every checker was registered in `standing_checks` and
given a caller. Nine of the twelve had none, and four live defects survived in
that gap.

## Adding a migration

Name it `YYYYMMDDTHHMMSSZ__slug.sql`, write no transaction control and no role
DDL, and register any checker it adds in `standing_checks` — `check_registration`
fails the gate for a checker nobody calls. If it adds a table, the finalizers
give it the event trigger, the RLS policy, the state grants and the purge order;
`tests/test_database.py` then wants a negative control for whatever new check it
brings, and says so by name when there is none.
