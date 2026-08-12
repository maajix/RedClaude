# 71 — Run a role at the roster's model and effort

**What to build:** Make the model and effort a claimed run records come from the roster row for its role, so the number in `agent_runs` is the number the child was started with.

**Blocked by:** 23 — Offer and claim a deterministic Slate.

**Status:** ready-for-agent

- [ ] `claim_task()` writes the claimed role's own model and effort, not one constant for every non-renderer role.
- [ ] A role's model and effort are stated in exactly one place, and adding a role cannot leave the scheduler writing someone else's numbers.
- [ ] A test claims a task of each kind and asserts the run row against the roster row, so a future roster edit that the scheduler does not follow fails.

## Why

`0023_scheduler_ranking.sql:946-947` decides the two fields by looking at
`runs_as` and nothing else:

```sql
v_model  := CASE WHEN v_runs_as = 'renderer' THEN 'none' ELSE 'claude-opus-5' END;
v_effort := CASE WHEN v_runs_as = 'renderer' THEN 'none' ELSE 'high'          END;
```

The roster disagrees with that for three of the five agent roles. `recon` is
`medium`, the `orchestrator` is `xhigh`, and the `validator` is `max` -- and the
validator's effort carries a reason in the roster: "a validator false negative
costs more than the tokens the effort buys". Written this way, a validate task
claims at `high`, and the reason is silently not in force.

The model half is the same shape and worse to leave. Ticket 18 pinned
`claude-opus-5` as what the alias `opus` resolved to for a measured SDK/CLI pair,
recorded in the inventory manifest under `models`. The scheduler spells that
resolution out as a literal, so the day the pair resolves `opus` to something
else, the run row says the old string and the child ran on the new model. The
manifest is version-bound on purpose; a copy of one of its values in a migration
is not.

Nothing downstream reads these two columns yet, which is why this is its own
ticket rather than a fix inside 18 -- but `agent_runs.model` and
`agent_runs.effort` are the record of what a run cost and why, and a wrong
constant is worse than a null.

## How

The roster is the single statement, so the scheduler has to be able to read it.
Two shapes are open, and the ticket should pick one rather than add a third
place:

- Carry `model` and `effort` on the `roles` table the way `max_concurrent` and
  `clamp_to_identity_leases` already are, filled by the same migration that
  fills the rest of the row, and have `claim_task()` select them alongside
  `runs_as`. The roster's `tests/test_roster.py` schema-agreement test already
  reads those `INSERT` statements field by field and would extend to two more
  columns.
- Or leave the run row's model and effort unset at claim time and have the
  runtime write them when it starts the child, from the roster object it already
  holds.

The first keeps the run row complete inside one transaction and puts the
agreement under the existing test. The second is closer to the truth -- the
runtime is what actually picks the model -- but leaves a window where a claimed
run has no model.

Whichever is chosen, `model = 'none'` and `effort = 'none'` for a renderer stay
exactly as they are: the roster says `None` for both and 0019 already refuses a
renderer that spent a token.
