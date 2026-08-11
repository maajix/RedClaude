# 66 — Narrow the runtime role's privilege surface

**What to build:** Make `rk2_runtime` hold only the privileges the runtime is meant to use, and a standing check that keeps it that way, so a role-gated verb stays gated to the role the corpus granted it to.

**Blocked by:** 03 — Run production migrations and the integrity gate.

**Status:** ready-for-agent

**Triaged 2026-08-11:** kept as its own ticket rather than folded into 03, because
it changes promoted schema and decides a security surface. Ticket 62 now lists it
as a blocker, so it has a dependency path to the release ticket the way the
original 01–65 plan requires of every ticket.

## Why

The v1 corpus grants `rk2_runtime` its privileges in bulk and then narrows them by hand, one object at a time. `0016_event_log_corrections.sql:448-450` and `0017_program_isolation.sql:487` grant `SELECT, INSERT, UPDATE, DELETE ON ALL TABLES` and `EXECUTE ON ALL FUNCTIONS IN SCHEMA public`, and `ALTER DEFAULT PRIVILEGES FOR ROLE rk2_owner` keeps granting the same to everything created afterwards (noted at `0037_lane_quota.sql:83-84`).

The narrowing is therefore opt-out, and three of the four opt-outs were written as `REVOKE ALL ... FROM PUBLIC` followed by `GRANT ... TO <one role>`. That revokes nothing from `rk2_runtime`, because the default-privileges grant is role-specific and `FROM PUBLIC` does not touch it. Measured on a freshly migrated database:

| Function | Gated in the corpus to | `rk2_runtime` can execute |
| --- | --- | --- |
| `answer_decision(text,text,text,interval)` | `rk2_human` (`0026_human_control.sql:839-840`) | yes |
| `register_proxy_artifacts(text,text,text,text,text)` | `rk2_proxy` (`0040_receipt_contract.sql:38-39`) | function no longer exists |
| `write_blocked_receipt(uuid,jsonb,text)` | `rk2_proxy` (`0040_receipt_contract.sql:114-115`) | yes |
| `force_lane_quota(text,text,integer)` | `rk2_human` (`0037_lane_quota.sql:749-750`) | no |

`register_proxy_artifacts` was dropped by ticket 10 at `20260810T214500Z__capability_proxy_egress.sql:284`, which is why that row now reads as it does. It is left in the table because it is the shape of the problem rather than an instance to fix: the grant at `0040_receipt_contract.sql:38-39` was as open as the other two for as long as the function existed, and deleting a verb is not a mechanism that keeps the next one closed.

`force_lane_quota` is the one that is actually closed, and it is the one written as `REVOKE EXECUTE ... FROM rk2_runtime`. The corpus knows the pattern and applies it in one place out of the four it wrote.

`answer_decision` is the sharpest case: `0026_human_control.sql:980-984` revokes the decision queue from `rk2_state` on the reasoning that "an agent that can read the decision queue can read the question it caused and tune the next one". The same agent reaches the database as `rk2_runtime`, and as `rk2_runtime` it can answer its own escalation.

The table side is the same shape and wider: `rk2_runtime` holds `INSERT`, `UPDATE` and `DELETE` on all 113 base tables in `public`, including `events`, `standing_checks`, `event_table_config`, `event_table_exempt`, `secret_kek` and `secret_dek`. 60 of the 113 carry row-level security, so program isolation still holds for those; the remaining 53 are guarded by triggers and constraints alone.

## Not in scope

Ticket 03 deliberately left this alone. It is a decision about what the runtime is allowed to do, spanning 05 (program isolation), 07 (wire-artifact encryption), 13 (egress budget) and 29 (pending decisions), and it changes promoted schema. Closing it under a ticket about running migrations would have been a silent change to the security surface.

- [ ] `rk2_runtime` cannot execute any function the corpus gates to `rk2_human` or `rk2_proxy`, revoked from the role rather than from `PUBLIC`.
- [ ] A single declared mechanism decides which role holds which verb, so a new gated function is closed when it is created rather than when someone remembers to revoke it.
- [ ] The runtime's table privileges are stated per table against what the runtime writes, with the control registries (`standing_checks`, `event_table_config`, `event_table_exempt`, `program_global_tables`, `state_read_surface`, `purge_cascade_edges`) and the key tables (`secret_kek`, `secret_dek`) read-only or unreachable to it.
- [ ] `events` is append-only to `rk2_runtime`: no `UPDATE`, no `DELETE`.
- [ ] A standing check fails when `rk2_runtime` holds a privilege outside the declared surface, and a negative control in `tests/test_database.py` proves that check fails when the privilege is granted back.
- [ ] The gate is run against a database restored from an archive as well as a migrated one, because `pg_restore` replays grants and a fix that only lives in a finalizer would not survive the round trip.
