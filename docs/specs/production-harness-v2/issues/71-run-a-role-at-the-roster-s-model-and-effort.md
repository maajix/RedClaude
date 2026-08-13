# 71 — Run a role at the roster's model and effort

**What to build:** Make the model and effort a claimed run records come from the roster row for its role, so the number in `agent_runs` is the number the child was started with.

**Blocked by:** 23 — Offer and claim a deterministic Slate.

**Status:** resolved

- [x] `claim_task()` writes the claimed role's own model and effort, not one constant for every non-renderer role.
- [x] A role's model and effort are stated in exactly one place, and adding a role cannot leave the scheduler writing someone else's numbers.
- [x] A test claims a task of each kind and asserts the run row against the roster row, so a future roster edit that the scheduler does not follow fails.

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

## Comments

Implemented on 2026-08-13. One migration,
`20260813T200000Z__a_role_runs_at_the_rosters_model_and_effort.sql`, two columns
on `roles`, one standing check, `roster_numbers`, and a fifth scenario in
`SlateClaimTest` that claims one Task of every kind.

### The first shape, because the second leaves a run row that cannot be written

The ticket offers two, and the second -- the runtime writing the numbers when it
starts the child -- is closer to the truth about who picks a model. It is also
not writable: `agent_runs.model` and `agent_runs.effort` are `NOT NULL`, so
"unset at claim time" is not a state the row has. Making them nullable to hold a
window open would weaken the record criterion 3 exists to assert against, so the
numbers moved onto `roles`, beside `max_concurrent` and
`clamp_to_identity_leases`, which are there for the same reason and read the same
way.

Both `agent_runs` constraints are restated on the roster row rather than trusted
to hold at INSERT time. `roles_effort_check` is `agent_runs`'s own vocabulary,
and `roles_renderer_runs_no_model` is `agent_runs_renderer_has_no_model` said
about the source: a roster row the run column would refuse is a claim that fails
on the first Task of that kind, in production, and a `CHECK` on the roster
refuses it while it is still a migration.

### What lands in the row is the alias, not the resolution

`claude-opus-5` is what one measured SDK/CLI pair resolves the alias `opus` to,
and 18's inventory manifest is bound to that pair by filename. The scheduler
copied the resolution out and would have gone stale without moving. The column
holds `opus`, and that is not a compromise: `_launch.options_for` hands
`role.model` to `ClaudeAgentOptions(model=...)` unchanged, so the alias is
literally the string the child was started with, which is what criterion 1 asks
the row to record. The resolution stays where the thing that performs it is
named.

Arm (b) of `check_roster_numbers()` is that rule as an invariant: no function
body in `public`, comments stripped, may match `claude-[a-z]`. Arm (a) is the
other half -- a `claim_task` whose source no longer selects `r.model` and
`r.effort` has gone back to deciding a role's numbers itself. Both arms are
textual on purpose, and the reason is stated in the migration: a run claimed
under a literal that happens to match today's roster is indistinguishable, row by
row, from one that read the roster, and they differ on exactly the day the roster
changes. A row arm was considered and rejected for a second reason --
`agent_runs.model` is also written by openers that are not agent runs
(`proxy.OPEN_RUN` records `operator`), so a check comparing every run to its
role's roster row would be asking those rows to lie. The negative control is the
smallest way to say what the check is for: a function whose body spells
`claude-opus-5`.

### The claim reads one row where it used to run two CASEs

`v_runs_as` is gone with the two `CASE` expressions that were its only readers.
One `SELECT` over `role_task_kinds JOIN roles` now returns the role, whether it
clamps, and both numbers -- so there is no longer any way to spell a role's
numbers in the scheduler at all, which is criterion 2. `tests/test_roster.py`
reads the migration's `UPDATE ... FROM (VALUES ...)` field by field against
`roster.ROLES` and asserts the two sets of role names are equal, so a sixth role
added to one side and not the other fails there rather than at the first claim.

### A fixture that claims every kind, and what that took

`SlateClaimTest` had nine Programs and every Task in all of them was a recon
Task -- which is one of the two kinds the old constant happened to be right
about. The tenth Program, `numbers`, seeds one Task of each kind with everything
`ready_for` asks of it: a testable Hypothesis under the hunt, an agent-visible
Artifact reachable through 12's `artifact_refs` bridge under the analyze, a
candidate Finding with a test spec under the validate, and a validated Finding in
the Program for the report. It is the first time `claimable_for` is asked about
all five kinds in one Program.

Each run is closed before the next Task is claimed, and that is not tidiness.
Four of the five kinds are run by a subagent role and `max_concurrent_subagents`
is three, so five simultaneous claims have the last one refused
`global_subagent_cap` -- a true refusal about somebody else's concurrency and
nothing to do with what the fixture asks. The closing returns the Task to
`pending` with the attempt spent, which frees both the lane and the count.

### A purge that cannot travel its own edge, found here and left open

`SlateClaimTest` is the first case in the suite to write a Finding, and its
teardown could not purge its own Programs:

```
update or delete on table "hypotheses" violates foreign key constraint
"finding_hypotheses_hypothesis_id_fkey" on table "finding_hypotheses"
```

016 gives `finding_hypotheses` exactly one cascade edge, the finding side, and
rewrites the hypothesis side to NO ACTION -- which is checked at the end of the
statement, by which time the program cascade is supposed to have removed the row.
It has not, because `hypotheses_program_id_fkey` is older than
`findings_program_id_fkey` and so cascades first: the NO ACTION check on the
rollup edge is queued before the delete that would satisfy it. This is 031's
failure -- a purge whose success depends on the order the catalogue happens to
hold foreign keys in -- in a place 031's finalizer does not repair, since it
rebuilds keys a *restore* reordered rather than the order the corpus builds. The
teardown deletes the edge rows first and says why; the defect is real, is not
this ticket's, and is owed one.
