# 226 — The kill chain analysis has never held a single row

**What to build:** The two callers that put a run in front of a validated
Finding's impact, so that `pivot_stamps` and `chains` stop being empty tables
with a full function corpus above them.

**Blocked by:** nothing. 103 built the three MCP wrappers; 221 built the first
`conclude` Task that reaches a validated Finding at all.

**Status:** in-progress -- all three walls fall; acceptance 3 owed

## What was measured, 2026-08-30

Read against the live `rk2here` database, 9 Findings, one of them `validated`:

```
chains                 0
chain_steps            0
chain_edges            0
chain_proposals        0
pivot_stamps           0
impact_demonstrations  0
finding_chain_steps    0
finding_effects        0
report_renderings      0
```

`SELECT * FROM check_kill_chains()` returns zero rows, and that is the point:
the standing check is **vacuously green**. Every one of its seven arms is a
`FROM chains` or `FROM chain_edges` query, so an empty table passes all of them.
The campaign has run 197 laps and the corpus has never been told a chain is
missing, because a missing chain is not a shape that check can see.

## The three walls, in the order a run hits them

### Wall 1 — no objective ever names `open_impact_task`

`grep -n "open_impact_task\|OPEN_IMPACT_TASK" src/redkraken/execution.py` returns
nothing. The verb is granted (`runtime_verb_surface`, `66-seed`), wrapped by
ticket 103 as `propose_impact_task`
(`20261031T000000Z__the_verbs_downstream_of_a_finding_get_their_callers.sql:110`),
and sits in `state.conclude`, which `web_hunter` holds alone
(`roster.py:2275`). But the two `conclude` objectives are `_conclusion`
(ticket 156, names a Finding) and `_banding` (ticket 221, states a severity).
Neither mentions impact, so no child has ever been asked to prove one.

This is ticket 221's shape exactly: served, described, granted, unreachable.

### Wall 2 — the runtime never selects the impact replay

`replay.IMPACT` is the only `_Verbs` set that calls `issue_pivot_stamp` and
`build_kill_chain` (`replay.py:110-124`). It is selected in exactly one place:

```
cli.py:2904:  verbs=replay.IMPACT if arguments.impact else replay.DETECTION,
```

which is `rk test replay --impact`, an operator command. The two callers the
harness actually runs pass no `verbs=` at all and so take the `DETECTION`
default:

- `execution.py:2577` — `_replay`, how a `perform` Task performs its Test
- `validation.py:294` — the blind validator's reproduction

So even if wall 1 fell and an impact Test existed, replaying it would file a
detection run and stamp no pivot.

### Wall 3 — follows from the two above

`build_kill_chain` refuses a proposal of fewer than two members, and
`rk2_chain_unlock_frontier` starts from `rk2_chain_unsoundness(...) IS NULL`
over `chains`. With `pivot_stamps` empty, `derive_chain_unlocks()` runs on every
pass (`rank_pass` step 3b) and returns nothing, so `chain_unlock_for(t)` is a
constant zero inside the priority formula. Half of `w_unlock` is dead weight and
has been since the Program was created.

## The price, read from source this session

**Wall 2 is small.** `tests.impact_class` already exists and
`open_impact_replay` refuses a Test that lacks it
(`20260816T000000Z...:26`). What is missing is that `execution.py::STARTED`
does not select it, so `Claimed` cannot see it. That is one column in the
query, one field on the dataclass, one line in `_replay`:

```python
verbs=replay_module.IMPACT if claimed.impact_class else replay_module.DETECTION,
```

**Wall 1 is ticket 221 again.** A frontier function over validated Findings
that carry no `impact_demonstrations` row, a `derive_*` that opens the Task, the
`ready_for` / `novelty_for` / `cancel_reason_for` arms that keep it alive, and
an objective. `open_impact_task` opens its own `hunt` Task carrying
`finding_id` (`20260816T000000Z...:1265`), and 008's live-dedup index already
separates that row from the hunt that produced the claim, so no new index is
needed. Same as 221: one migration, `execution.py`, `test_database.py`,
`test_execution.py`.

**What neither wall buys: full automation.** `open_impact_replay` asks for a
live operator grant and, finding none, parks the Task and files a pending
decision (`20260816T000000Z...:67-92`). That is deliberate — proving impact is
demonstrating real harm — so every impact demonstration costs one operator
answer. An unattended campaign reaches `parked` and stops there.

## Why this matters to the campaign

`severity_basis` has three values and `demonstrated_impact` is the one that
needs an `impact_demonstrations` row. With that table empty, every band this
harness can state is `constrained_inference` or `program_context`, and
`program_context` cannot carry high or critical. So the ceiling on an unattended
campaign is whatever `constrained_inference` will bear.

That is not a blocker for a medium finding. It is the blocker for a proven one.

## Acceptance

- [x] A validated Finding with no impact demonstration produces exactly one
      Task that reaches `propose_impact_task`, and a second pass does not
      abandon it.
- [x] A Test carrying an `impact_class` is replayed through `replay.IMPACT`
      by the runtime, without `rk test replay --impact`.
- [ ] One end-to-end fixture reaches a non-empty `pivot_stamps` and a
      `chains` row that `check_kill_chains()` passes non-vacuously.
- [x] `check_kill_chains()` gains an arm that fires when a Program holds a
      validated Finding and no chain, so the empty case stops reading as green.
      Built with the grace the honest version needs; see below.

## What was built for wall 2, 2026-08-30

`20261231T000000Z__an_impact_test_reaches_the_replay_that_stamps_a_pivot.sql`
and the `execution.py` change in the same commit.

**The lane.** `rk2_impact_performance_frontier(uuid)` is the sibling of
`rk2_test_performance_frontier` over the rows that one excludes: impact Tests
nobody has replayed, that no `perform` Task names, whose claim is still
`supported` and whose Finding is `validated`. The Finding comes off the `hunt`
Task `open_impact_task` opened beside the Test, because that is the only row
that says which Finding a Test is proving impact on -- `tests` carries a
hypothesis and a class and no Finding, and one claim can carry several.
`derive_impact_performances()` spends it, sharing
`max_performances_derived_per_pass` with the detection derivation because both
open `perform` Tasks. `rank_pass` gains step (3d2).

**The arm.** `ready_for`'s `perform` arm asked the Test's claim to be
`testable`. An impact Test is written after that claim settled, so the arm
refused every impact Task the moment it was derived -- ticket 152's measurement
in a new place. It now splits on `tests.impact_class` and asks an impact Task
for the condition `open_impact_replay` itself checks: a Finding, and that
Finding `validated` or `reported`. `novelty_for` needed no change; its `perform`
arm reads `test_replays` and nothing about the claim.

**The dispatch.** `execution.py::STARTED` selects `ts.impact_class`, `Claimed`
carries it, and `_replay` passes
`verbs=replay.IMPACT if claimed.impact_class else replay.DETECTION`. That is the
only path outside `rk test replay --impact` that reaches `issue_pivot_stamp` and
`build_kill_chain`.

**Not built here:** wall 1. No objective asks a child to call
`propose_impact_task`, so no impact Test is written in the first place. This
commit is what makes that one worth making: a Test written into a lane that
cannot run it is a row nobody reads.

## What was verified

- `tests.test_execution` -- 215 tests, including `ImpactReplayTest`'s five.
- `tests.test_database.ImpactPerformanceTest` -- the frontier, the derivation,
  the `finding_id` the replay verb requires, the arm that would have refused it,
  and the detection Task whose rule did not move.
- The migration applied inside a rolled-back transaction against live `rk2here`
  before it was applied for real.
- `check_wiring`, `check_audit`, `check_baseline`, `check_coverage`,
  `check_dispositions`, `check_secrets` -- all exit 0.

## What was built for wall 1, 2026-08-30

`20270104T000000Z__a_banded_finding_gets_the_task_that_asks_for_its_impact.sql`
and the `execution.py` change in the same commit.

**The order, which is the whole design.** `rk2_severity_frontier` refuses a
Finding that any `conclude` Task names, in any status. So a specification Task
opened before the band would be the row that stops ticket 221's Task from ever
being derived, and 221's lane would close the day this file landed. The band
comes first and the impact ask follows it. That costs the FIRST band its
strongest basis -- `state_severity` refuses `demonstrated_impact` while no
demonstration exists, so the first statement is always an inference -- and buys
221 untouched plus a fence that needs no new column.

**The fence.** `rk2_task_proves_impact(tasks)`. A `conclude` Task naming a
Finding was opened to band it if it predates the Finding's first
`severity_statements` row, and to prove its impact if it does not; the two can
never overlap, because `rk2_severity_frontier` will not open a band Task once
`severity_basis` has moved. One function and not the same expression three
times, because the frontier, `novelty_for` and `execution.py`'s claim query all
have to read it identically -- ticket 157 measured what it costs when two
readers of one rule drift.

**The lane.** `rk2_impact_specification_frontier(uuid)` over validated Findings
somebody has banded, whose impact nobody has specified or demonstrated, that no
`conclude` Task has named since the band. `derive_impact_specifications()`
spends it, sharing `max_conclusions_derived_per_pass` with the other two
conclusion derivations. `rank_pass` gains step (3g), immediately after (3f).

**The arm.** `novelty_for`'s `conclude` arm, and only that one. `ready_for`
needs no change -- its arm asks a Task carrying a Finding for a supported claim
and a validated Finding, which both shapes satisfy. `cancel_reason_for` needs
none either: ticket 156's exception already keeps a `conclude` Task alive over a
settled claim. `novelty_for` is the one that would have ended it: 221's reading
scores a Task 0 as soon as `severity_basis` moves, which is true of every Task
this file derives by construction, and `cancel_reason_for`'s general rule reads
a zero as answered. Ticket 152's measurement, in a third place.

**The objective.** `Claimed.proves_impact`, off
`coalesce(rk2_task_proves_impact(t.*), false)` in `STARTED`, and
`Claimed._impact`. It names `mcp__rk2__open_impact_task`, writes out the three
grantable impact classes from `roster.IMPACT_CLASSES` (the tuple the served
enum is built from, so the words shown and the words accepted are one list),
and carries one paragraph the two sibling objectives have no need of: **YOU DO
NOT RUN THIS TEST.** An impact run writes to a live system and
`open_impact_replay` asks an operator first; a child that demonstrated it itself
would have performed the unauthorized half of the procedure this harness exists
to ask permission for.

**The check arm, and the grace it was given.** Arm (h) of `check_kill_chains`
fires on a PAIR: a Program holding a validated Finding with no chain at all,
AND a `rank_pass` whose text no longer calls `derive_impact_specifications` or
`derive_impact_performances`. Both halves, because either alone is wrong.

- Not "a validated Finding has a chain". `build_kill_chain` refuses fewer than
  two members, so a Program with one Finding may compose no chain and be
  entirely healthy. That arm could never go green.
- Not "a validated Finding has a demonstration". A child that reads a Finding
  and says no impact class fits has answered correctly, and an arm refusing that
  would halt the harness over a run that did its job.
- Not the state half alone. It fires the moment a Finding is validated, before
  the lane has had a turn, and a standing check that returns rows refuses every
  pass -- so it would halt the campaign rather than report on it. That is D-11's
  mechanism, and live `rk2here` holds exactly that shape today.
- Not the code half alone. That is a lint about a function nobody asked to run.

Read off `pg_proc.prosrc` with comments stripped, which is
`check_chain_unlocks` arm (d)'s shape and `check_scheduler_closure` arm (g)'s
rule about comments. Verified quiet on live `rk2here` and verified firing with
both callee names when `rank_pass` is stubbed inside a rolled-back transaction.

**What this does not buy.** Two things, named because neither is a bug.

1. `open_impact_replay` still asks for a live operator grant, parks the Task and
   files a pending decision. That gate was not touched and must not be: proving
   impact is demonstrating real harm. Under D-12 the orchestrator answers these
   routinely, so it is friction rather than a stop.
2. Nothing restates a severity after a demonstration lands. The first band is an
   inference by construction of the order above, `severity_statements` is
   append-only and a later statement is allowed, and `derive_finding_bands`
   requires `severity_basis = 'undetermined'` so it will not re-derive. The
   `demonstrated_impact` road to high and critical therefore still needs one more
   caller. That is a ticket, not a defect in this one.

**Acceptance 3 was not built.** An end-to-end fixture reaching a non-empty
`pivot_stamps` needs an answered operator decision inside the fixture (
`open_impact_replay` parks otherwise), a live door for the impact actions and
their cleanup, and TWO stamped pivots before `build_kill_chain` will compose
anything at all. That is a fixture on the scale of `ImpactRunFixture` plus
`ChainFixture`, not something that falls out of a derivation test.

**One wart, recorded rather than migrated away.** The `runtime_verb_surface`
note for `derive_impact_specifications()` says the two `conclude` shapes are
"told from it by the Finding's own `severity_basis`". That was the first
design's rule, dropped for `rk2_task_proves_impact` because it silently changed
ticket 221's answer, and the note kept the old sentence. The migration is
applied and frozen, the corpus has never once amended a `runtime_verb_surface`
note, and nothing reads the column as behaviour -- the authoritative sentence is
`COMMENT ON FUNCTION derive_impact_specifications()`, which is correct. Left for
whichever migration next touches this area; it is not worth a file of its own.
