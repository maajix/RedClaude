# 226 — The kill chain analysis has never held a single row

**What to build:** The two callers that put a run in front of a validated
Finding's impact, so that `pivot_stamps` and `chains` stop being empty tables
with a full function corpus above them.

**Blocked by:** nothing. 103 built the three MCP wrappers; 221 built the first
`conclude` Task that reaches a validated Finding at all.

**Status:** resolved

**PRODUCES:** new -- the first `pivot_stamps` row and the first `chains` row
this harness has ever reached without an operator typing
`rk test replay --impact`, and the test that watches it happen.

**CONSUMED BY:** `operator, via uv run python -m unittest
tests.test_database.RuntimeChainTest`; the arm the acceptance line names,
`check_kill_chains()`, read over a Program that holds a chain rather than over
an empty table.

**CONSUMES:** `redkraken.replay::_downstream`, which is the only caller of
`issue_pivot_stamp` and `build_kill_chain` on a hunt's path;
`redkraken.replay::run`'s `verbs=` parameter and `redkraken.replay::IMPACT`,
written by ticket 38 and ticket 103 -- what wall 2 wrote is the *selection* of
`IMPACT` in `execution.py::_replay`; `open_impact_task`, written by ticket 38's
impact migration -- what wall 1 wrote is the *objective* that names it.

**Touches:** `tests/test_database.py` and `tests/test_execution.py`. No source
file joined either: running walls 1 and 2 together for the first time found
nothing wrong with them, and cycle 1's two criteria are a test that reads a line
nothing read and a fixture that stops re-spelling what it can reference.
`tests/test_execution.py` came in with the first of those. Two more files came in
with `## Build findings, 2026-09-03`'s NOW repair --
`docs/specs/production-harness-v2/issues/65-prove-first-hunt-release-candidate.md`
and `tests/test_audit.py` -- and neither is production code.

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

*Read from source on 2026-08-30, and cited by the line numbers of that day.
Two have since moved: `cli.py:2904` is now `cli.py:2948`, and
`execution.py:2577` is now `execution.py:2640`.*

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
- [x] One end-to-end fixture reaches a non-empty `pivot_stamps` and a
      `chains` row that `check_kill_chains()` passes non-vacuously.
      `tests.test_database.RuntimeChainTest`; see below.
- [x] `check_kill_chains()` gains an arm that fires when a Program holds a
      validated Finding and no chain **and** the derivation wiring that would
      close it has gone from `rank_pass`. The pair, not the state alone: a
      standing check that returns rows refuses every pass, so a state-only arm
      would halt the campaign rather than report on it. See "the grace it was
      given" below. The empty case with the wiring intact still reads green,
      which cycle 1 declined closing, in writing.
- [x] The runtime's own `verbs=` selection is asserted where it lives.
      `execution.py:2724` is the only runtime site and nothing reads it: added
      by cycle 1 for the [ticket] finding that narrowing it to `DETECTION`
      leaves the whole tree green. One assertion over `_replay`'s call kwargs
      in `tests.test_execution.ImpactReplayTest`, watched failing under that
      narrowing first, and `RuntimeChainTest.attempt`'s hand-copy of the
      expression dropped to `verbs=replay.IMPACT` so the rule has two readers
      rather than three spellings.
- [x] `RuntimeChainTest` inherits or references what it copied.
      Added by cycle 1 for the [craft] finding: the nine members that touch
      neither a Receipt nor a door are not this case's work. `called`,
      `as_owner` and `rows_of` hoisted onto `LiveDoorFixture` with
      `ValidationCommandTest.called` deleted so both live-door subclasses
      inherit one copy; `ImpactRunFixture.REASON`,
      `ValidationCommandTest.TITLE`, `ValidatedFindingFixture`'s six statement
      constants and `DECLARED` referenced rather than re-spelled; `id_of` and
      the third `replay.run` spelling dropped with them. `settle` and `approve`
      were kept local as well, which cycle 2 found this line claiming away:
      each re-spells a fixture that lives over `cls.connection` --
      `PivotStampFixture.settled` and `ImpactRunFixture.as_operator` -- which is
      the branch reason `ReplayFixture`'s own copies were kept for, and neither
      is door-shaped. Named here rather than done, per cycle 2's verdict.

**Which commit each criterion landed in, recorded by cycle 1 and corrected by
cycle 2.** Criterion 3 is the only one inside **cycle 1's** diff, and criteria 5
and 6 are the whole of cycle 2's: they landed in `f1f1c0bd`, which carries the
`(ticket 226)` marker. So three of the six have been pinned as a diff and three
have not. Criteria 1, 2 and 4 landed in
`685d860f` and `cf1b75fa`, and neither subject carries a `(ticket 226)` marker,
so this flow's fixed-point procedure cannot see them and no cycle has ever
pinned them as a diff. `tools/check_audit.py` does not enforce the marker
either, so the gap is invisible to the gate that counts this ticket audited.
Cycle 1 read their substance anyway -- four of its findings are about that
work, two of them on criterion 2 and criterion 4 themselves -- so what is
unreviewed is the diff, not the behaviour. Any later re-read of walls 1 and 2
pins those two commits one at a time; growing a cycle's diff to reach them
would swallow the seven other tickets that carry a marker in that range --
134, 166, 216, 231, 233, 235 and 236 -- each reviewed by its own cycle.

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

**Acceptance 3 was not built by this wall**, and was built on 2026-09-03; see
`## Resolution` below. An end-to-end fixture reaching a non-empty
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


## Seam check, 2026-09-03

`PRODUCES: new`, and the new thing is two rows plus the case that watches them
arrive. Every far end below was opened or run.

```
WROTE  tests.test_database::RuntimeChainTest
       READ BY  operator, via uv run python -m unittest
                tests.test_database.RuntimeChainTest
WROTE  tests.test_database::WritingTarget
       READ BY  tests.test_database::RuntimeChainTest, reading TARGET --
                spent by LiveDoorFixture.setUpClass's counterparty(cls.TARGET)
WROTE  tests.test_database::LiveDoorFixture.SOURCE
       READ BY  tests.test_database::LiveDoorFixture.setUpClass, reading
                cls.SOURCE
WROTE  tests.test_database::LiveDoorFixture.root_secret
       READ BY  tests.test_database::LiveDoorFixture.setUpClass, reading
                cls.root_secret at header.provision and proxy.listen; and
                tests.test_database::RuntimeChainTest.provisioned
WROTE  the pivot_stamps and chains rows the two impact runs left
       READ BY  check_kill_chains() arms (a)-(g), reading FROM chains,
                chain_steps and chain_edges -- the first pass in which they
                evaluate over rows rather than over an empty table, which is
                the non-vacuous green criterion 3 asks for; and
                build_kill_chain, reading
                ARRAY(SELECT id FROM pivot_stamps WHERE program_id = $1) on
                the second run, which is the first run's stamp
                -- corrected by cycle 1. Arm (h) was recorded here and does
                not discriminate: its second half wants a rank_pass that no
                longer calls the two derive functions, and the deployed one
                calls both, so it is quiet with the chain and without it. Its
                own proof was taken in cf1b75fa, against a stubbed rank_pass
                inside a rolled-back transaction. rk2_chain_unlock_frontier
                was recorded here and reads nothing either: its gap CTE wants
                a stamp that is not already a chain_step, and both of these
                are steps of the chain they composed, so wall 3's
                chain_unlock_for(t) is still a constant zero after this pass.
                Wall 3 is therefore reachable and still unmeasured; a third
                stamp would measure it.
WROTE  65-prove-first-hunt-release-candidate.md's Blocked by entry for 233
       READ BY  tools/check_audit.py, reading the release-outcome closure over
                RELEASE_OUTCOME = 65
WROTE  tests/test_audit.py's frozen report line
       READ BY  operator, via uv run python -m unittest tests.test_audit

READ   redkraken.replay::_downstream
       WRITTEN BY  ticket 103, status resolved
READ   redkraken.replay::run's verbs= parameter, and redkraken.replay::IMPACT
       WRITTEN BY  ticket 38, commit 3f2d4921, for the parameter and IMPACT's
                   open and close; ticket 103, commit 77bcfecd, for IMPACT's
                   two stamp statements -- corrected by cycle 1, which found
                   685d860f touches no file under src/redkraken/replay.py.
                   What wall 2 wrote is the selection at execution.py:2724,
                   and RuntimeChainTest.attempt hand-copies that expression
                   rather than calling _replay, so wall 2's own line has no
                   reader in this case
READ   open_impact_task, and the conclude objective that names it
       WRITTEN BY  ticket 38's migration; the objective by ticket 226 wall 1,
                   commit cf1b75fa
READ   check_kill_chains() arm (h)
       WRITTEN BY  ticket 226 wall 1, commit cf1b75fa
READ   open_impact_replay, close_impact_replay, issue_pivot_stamp,
       build_kill_chain
       WRITTEN BY  tickets 38, 39 and 40's migrations, all resolved
```

No `NOBODY`.

**The greps, and what was skipped.** `cls.SOURCE` has three hits in `tests/`
and two of them belong to other names -- `SOURCE_RESPONSE` at
`test_database.py:28307` and `tests/test_jsscan.py:360`'s own class attribute.
`WritingTarget` and `RuntimeChainTest` have no hit outside the block that
defines them and the two lines above, which is what a new test class looks
like. `tools/check_audit.py:140` registers `tests.test_database` as a whole
module rather than by class, so a class added to it needs no registration --
measured rather than assumed, because the alternative was a new test the
verification census could not see.

**The live run.** This ticket's case *is* the live run, and it is the first one
this path has ever had: a real PostgreSQL 18 cluster (`rk2-test-pg` on
`127.0.0.1:55433`, `RK_TEST_DATABASE=rk2_t226`), a real `proxy.listen` door
with the proxy role behind it, and a real counterparty on a loopback port. Two
impact replays went out through it under a leased Identity, each after an
operator answer on the `rk2_human` connection, and each Receipt was written by
the door's own `write_allowed_receipt` rather than by the case. The far end
read was `check_kill_chains()` over a Program holding one chain: no rows, with
`chains = 1` and `pivot_stamps = 2` beside it.

**There was no `live-inputs.md` in this effort when this pass ran**, which
ticket 236 measured one day earlier and recorded rather than created. Recorded
again rather than minted: the file's own rule is that the walking skeleton's
session creates it, this effort is 236 tickets past that, and a file starting at
ticket 226 would carry one block and read as though the 225 before it had no
live inputs. **Superseded.** Cycle 1's [seam] finding took the other side of
that judgement and its NOW verdict minted
`docs/specs/production-harness-v2/live-inputs.md` with one block for 226 and a
header saying why the file starts 225 tickets in. The second pass below reads
that block. This paragraph is kept as the reading it was, and marked by cycle 2,
because for one cycle the two passes under this heading contradicted each other
in the present tense.

**Rule 3b.** No double was injected. The one thing this case fakes is the
address -- `LiveDoorFixture.dial` puts every authorised name on the loopback
port, for `ProxyEgressTest`'s reason that `127.0.0.1` can never be a Program's
scope -- so what is faked is where the socket goes and nothing about the
decision that authorised it. The Identity material is real sealed ciphertext,
opened by the door under the installation root.

**Second pass, 2026-09-03, over cycle 1's two criteria, under this same
heading.** The rows the first pass recorded did not move: nothing in this diff
writes a `pivot_stamps`, `chains` or `check_kill_chains()` row differently, and
the promoted case that reads them was re-run live and still reads the far end
`live-inputs.md` records. What this pass has to answer is narrower -- the
criteria wrote one assertion and moved five fixture members, so the question is
whether each of those is read.

```
WROTE  tests.test_execution::ImpactReplayTest.replay_called, and its two tests
       READ BY  operator, via uv run python -m unittest
                tests.test_execution.ImpactReplayTest -v; both tests read by
                name in the paste under `## Bar`
WROTE  tests.test_database::LiveDoorFixture.called
       READ BY  tests.test_database::ValidationCommandTest.candidate, reading
                cls.called -- the copy this criterion deleted from that class;
                and
                tests.test_database::RuntimeChainTest.validated_finding and
                .prove, seven call sites between them. Both subclasses were
                watched red under the mutation below, which is what makes this
                one copy rather than one declaration
WROTE  tests.test_database::LiveDoorFixture.as_owner
       READ BY  tests.test_database::RuntimeChainTest.project_the_scope,
                .open_run and .settle, reading cls.as_owner. One reader in this
                branch, not two: what these two were duplicated against was
                ReplayFixture's copies over cls.connection, and the criterion
                puts them where the next live-door subclass finds them
WROTE  tests.test_database::LiveDoorFixture.rows_of
       READ BY  tests.test_database::RuntimeChainTest.setUpClass, reading
                cls.rows_of for check_kill_chains(), and .settle for the runs
                still open on a settled Task. Same one-reader note as as_owner
WROTE  tests.test_database::RuntimeChainTest.replayed's agent_run=,
       identity_slot= and **verbs
       READ BY  tests.test_database::RuntimeChainTest.attempt, passing all
                three -- the claimed run, SLOT and replay.IMPACT; and
                .must_hold, passing none, which is the detection replay the
                member Finding is opened on
WROTE  tests.test_database::RuntimeChainTest.must_hold
       READ BY  tests.test_database::RuntimeChainTest.validated_finding, twice
                -- the born run and the reproduction

READ   redkraken.execution::Slice._replay's verbs= call kwarg
       WRITTEN BY  ticket 226 wall 2, commit 685d860f, which is the selection
                   at execution.py:2724. This is the line cycle 1 found had no
                   reader at all; it has one now, and the mutation below is the
                   proof that it discriminates
READ   tests.test_execution::PerformTest.SETTLED and .DOOR
       WRITTEN BY  ticket 152, commit 6d701067
READ   tests.test_database::ValidatedFindingFixture.OPEN_FINDING, .REQUEST,
       .REOPEN, .SESSION, .VERDICT, .FINISH
       WRITTEN BY  ticket 37, commit d9067b7f, all six lines
READ   tests.test_database::ValidationCommandTest.TITLE
       WRITTEN BY  ticket 37, commit d9067b7f. The second occurrence of that
                   sentence in the module was written by this ticket's own
                   eea3f05d and is what this criterion deletes
READ   tests.test_database::ImpactRunFixture.REASON
       WRITTEN BY  ticket 39, commit 37d99d6b, corrected by cycle 2. This head
                   read `ticket 38, commit 3f2d4921`, and that commit holds no
                   `class ImpactRunFixture`: `git log -S 'class
                   ImpactRunFixture'` returns 37d99d6b alone, and `git blame`
                   puts the attribute there
READ   tests.test_database::DECLARED
       WRITTEN BY  PH2-21's Surface promotion, commit 7ee327ed. It names
                   `member`, which is what RUNTIME_CHAIN_SLUG's SLOT is, so
                   SCOPED + DECLARED is byte-identical to the f-string it
                   replaces
```

No `NOBODY`.

**The greps, and what was skipped.** `grep -c 'cls\.called'
tests/test_database.py` prints `136`, and all but eight resolve to a declaration
in a different branch -- three declarations, not one, which cycle 2 measured by
resolving each reading class through its bases: 110 to `ReplayFixture.called`,
14 to `BrowserMissionTest.called` and 4 to `OfflineToolRunTest.called`, each
over its own `cls.connection`. The eight that reach the hoisted copy are
`ValidationCommandTest.candidate`'s one and `RuntimeChainTest`'s seven, and
those are the two `setUpClass` paths the mutation below killed. `grep -c 'id_of'`
prints `18`, none of them inside `RuntimeChainTest` any more;
`ImpactRunFixture.id_of` is pre-existing and untouched, and it is the only other
declaration in the module -- `grep 'def id_of'` returns two lines at the fixed
point, that one and the one this criterion deletes.
`replay.run(` has one call site inside `RuntimeChainTest`, down from two, so the
hierarchy holds two spellings rather than three.

**The live run.** The promoted case was run for real again on this diff, on the
same cluster the block records -- `rk2-test-pg` on `127.0.0.1:55433`, this time
`RK_TEST_DATABASE=rk2_t226b` -- and reached the same far end: two impact
replays out through a real `proxy.listen` door under a leased Identity, two
operator answers on the `rk2_human` connection, `pivot_stamps` = 2, `chains` =
1 composing 2 steps over 1 edge, and `check_kill_chains()` returning no rows
over it. That far end is asserted rather than read by hand, which is why
`live-inputs.md`'s only block is `promoted to
tests.test_database.RuntimeChainTest`; no block in that file has a `STATUS`
beginning `live`, so no hand replay was owed and `REPLAYS` stays at `0 ()`.

**The mutation, and why it is the seam proof and not decoration.** Each
criterion closed a claim cycle 1 found unfalsifiable, so each was broken on
purpose and watched:

1. `execution.py:2724` narrowed to a flat `verbs=replay_module.DETECTION`. One
   test of 224 in `tests.test_execution` went red, and it is the new one --
   which is exactly the finding, since before this diff that narrowing left the
   whole tree green.
2. `cls.runtime` replaced by `cls.connection` in all three hoisted members,
   which is the one token the review found the copies differed in. Both
   live-door subclasses died in `setUpClass`:
   `redkraken.pg.DatabaseError: 42501: rk2.program_id is not set on this
   connection | PL/pgSQL function rk2_program_required() line 6 at RAISE`,
   `Ran 0 tests`, `FAILED (errors=2)` -- one error per class, both through
   `LiveDoorFixture.called`.

**Rule 3b.** One double was injected, which this line denied until cycle 2 read
it: `ImpactReplayTest.replay_called` adds `mock.patch.object(
execution.replay_module, "run", ...)`, and criterion 5's only assertion reads
`run.call_args.kwargs["verbs"]` off that mock rather than off the real
`replay.run`. The real thing is checked in this same ticket -- `attempt` hands
`verbs=replay.IMPACT` to the real `replay.run` and reaches both stamps -- so
the substitution is checked, not deferred. The four the first pass and cycle 1
recorded are otherwise the same four, in the same places, and none was
removed.

## Build findings, 2026-09-03

- [build] **`check_audit` is red at HEAD: `audit failed: ticket 233:
  resolved, and no path reaches ticket 65 from it`. Ticket 233 is `resolved`
  and ticket 65's `Blocked by` line does not name it, so the release outcome's
  transitive closure excludes finished work.** — required — NOW. One entry
  added to that line, `233 — A probe-only Playbook bar asks for two kinds its
  own trigger refuses`, in the position the list puts a ticket as it lands.
  `check_audit` rc=0 after it. No production code, so no red test is owed.
- [build] **`tests.test_audit` freezes the audit report as a literal and the
  NOW repair above moved it: measured `tickets 236 resolved 204` against a
  frozen `tickets 235 resolved 203`.** — required — NOW. Refreshed by
  re-measuring, per `docs/agents/testing.md`:
  `PYTHONPATH=$PWD python3 -s -c "import tools.check_audit as c;
  print(c.check())"`, one line replaced, nothing relaxed. The two gates
  disagreed at HEAD -- `check_audit` red and `tests.test_audit` green -- because
  the frozen literal was measured from the same red tree.

**Nothing was wrong with wall 1 or wall 2.** This is worth writing down because
it was the open question: two lanes built a fortnight apart, neither ever run
end to end, and the first run of them together went green on the first attempt.
The only red in this session was the case's own `assertEqual([], self.problems)`
against a `rows` accessor that answers a tuple.

**One wall the ticket already priced, and the price was right.** Acceptance 3
needed an answered operator decision inside the fixture, a live door for the
impact actions and their cleanup, and two stamped pivots before
`build_kill_chain` would compose anything. All three were needed, and the
fixture is 250 lines of `LiveDoorFixture` subclass because of it. What the
ticket's estimate got wrong is only which fixture it sits beside:
`ImpactRunFixture` and `ChainFixture` descend from `ReplayFixture`, which writes
its Receipts by hand and has no door, so this case could not inherit them --
their five verbs are called here in the same order over replays the door
performed.

**Second pass, 2026-09-03, over cycle 1's two criteria, under this same
heading.** One finding, and it is about this pass's own diff rather than about
something else being broken.

- [build] **An assertion was removed from a class that stayed.
  `RuntimeChainTest.attempt` held `assert impact_class is not None, test` over
  a column it read only to re-derive the runtime's dispatch, and criterion 5
  drops both the read and the assert. The standing bar's lowering-move 2 is
  "assertions removed from a test that stayed", and this is one, so it gets a
  verdict rather than a sentence in the bar paste.** — nit — ALREADY OWNED by
  cycle 1's `verbs=` criterion on this ticket, which is the move: the rule that
  guard re-derived is now read where it is made, in
  `tests.test_execution::ImpactReplayTest`, against the call kwargs `_replay`
  passes. `open_impact_replay` refuses a Test carrying no `impact_class` in any
  case, so the fixture is not left unguarded -- the guard moved from a fixture
  that could only assert about itself to a test that asserts about the runtime.
  The nit row would say DECLINE; the work is owned, so the departure is written
  here rather than left silent, as cycle 1 did for its three owned nits.

**Nothing else was wrong.** Both criteria were built against source that
already said what cycle 1 said it said. The `verbs=` line at
`execution.py:2724` was correct and unread; the nine copied members were copies
of exactly the originals cycle 1 named, and `SCOPED + DECLARED` came out
byte-identical to the f-string it replaced. The only surprise was small: the
first draft of criterion 5's harness reached no `replay.run` at all, because
`_replay` refuses to run on a machine that names no door, so the helper
references `PerformTest.DOOR` as well as `PerformTest.SETTLED`.

## Resolution, 2026-09-03

`tests.test_database.RuntimeChainTest` is the first thing in this repository to
reach a `pivot_stamps` row and a `chains` row without an operator typing
`rk test replay --impact`. It walks the whole of it: a claim tested through a
real door, a Finding validated on that Test, then twice over -- an impact Test
written by `open_impact_task`, a first `replay.run` under `replay.IMPACT` that
finds no grant and parks the Task having sent nothing, an operator's
`answer_decision` on the `rk2_human` connection, and a second `replay.run` that
performs the three actions and the PUT that undoes them. The seam is
`replay._downstream`, which is the only caller of `issue_pivot_stamp` and
`build_kill_chain` on a hunt's path and had never been executed by anything; the
five tests guard it. The first run stamps a pivot and is refused a chain, because
one stamp is a stamp; the second stamps the pivot that requires what the first
provides, and the chain composes 2 steps over 1 edge.

`verbs=` is passed the way `execution.py::_replay` passes it -- read off the
Test's own `impact_class`, asserted non-null first -- so what the case exercises
is the harness's dispatch and not the operator command's.

Two changes outside the new block, both in `LiveDoorFixture` and both one line:
`SOURCE` is now a class attribute defaulting to `SCOPED`, because `SCOPED`
declares no `[[identity]]` and `rk2_pivot_problem` requires a pivot to name a
slot; and the installation root secret moved from a local to `cls.root_secret`,
because a subclass sealing Identity material has to seal it under the root the
door was started with. Neither moved anything for `ReplayCommandTest` or
`ValidationCommandTest`, which were run to say so.

**Red:** none — born green. Walls 1 and 2 landed on 2026-08-30 and this
criterion adds the assertion nobody had made over them, so there was no code to
watch fail.

**Mutated:** `replay._downstream`'s `if not verbs.stamp_sql: return` narrowed
to `if True: return`, which is the defect this ticket measured -- a runtime that
performs the run and reaches neither verb. Four of the five tests went red, and
the state they read is the one the ticket opens with:
`AssertionError: Tuples differ: (1, 2) != (0, 0)` on
`test_the_standing_check_is_green_over_a_program_that_holds_a_chain`, and
`AssertionError: Lists differ: ['other_account_data', 'credential_material'] !=
[]` on `test_the_runtime_stamped_a_pivot_off_each_run_it_performed`. Restored
and re-run green.

A second mutation was watched and is reported for what it is rather than as the
proof: `verbs=replay.IMPACT if impact_class else replay.DETECTION` narrowed to
`verbs=replay.DETECTION`, which is wall 2 undone. That one fails in the
fixture's own arrangement -- `AssertionError: {... 'decision': None}` at
`prove`'s park assertion, because `open_test_replay` refuses an impact Test
before any pivot is at stake -- so it discriminates without being an assertion
about the value crossing the seam.

**Forward references left standing:** none. Two tickets cite this number in
prose inside their own bodies and neither citation is a seam-field head, so
nothing is owed to this ticket and nothing is owed by it.

Nothing in the ticket turned out wrong. The three walls it named are the three
walls, and its own pricing of acceptance 3 was accurate down to the two stamps.

## Resolution, 2026-09-03 — cycle 1's two criteria

Two claims cycle 1 found unfalsifiable now have readers that can refuse them.
The runtime's verb selection at `execution.py:2724` is read where it is made:
`tests.test_execution::ImpactReplayTest.replay_called` stubs
`execution.replay_module.run` on one `perform` attempt and hands back the mock,
and the two tests either side of it assert
`run.call_args.kwargs["verbs"]` is `replay.IMPACT` for a Task whose Test states
an impact class and `replay.DETECTION` for one that does not. That is the seam
`_replay` sits on -- the claim's own column deciding which verb set the
performer is given -- and before this diff nothing crossed it. The second claim
was `RuntimeChainTest` asserting over a fixture it had hand-copied: `called`,
`as_owner` and `rows_of` now live once on `LiveDoorFixture` and both live-door
subclasses inherit them, `ValidationCommandTest.called` is gone, and the
sentences and statements the case used to re-spell -- `ImpactRunFixture.REASON`,
`ValidationCommandTest.TITLE`, `ValidatedFindingFixture`'s six statement
constants and `DECLARED` -- are referenced. `id_of` went with them, because
`open_impact_task` already answers the label `replay.run` takes, and the third
`replay.run` spelling went with `attempt`, which is now a claimed run, a slot
and `verbs=replay.IMPACT` handed to the one call site this class keeps.

`RuntimeChainTest`'s five tests are the guard for the second criterion and they
still run the same live path: a real door, two real impact replays, two operator
answers, `pivot_stamps` = 2 and one chain over 2 steps and 1 edge.
`ValidationCommandTest`'s twenty are the guard for the half of the hoist that
class reads.

**Red:** none — born green. Both criteria assert over code that shipped four
days ago in `685d860f` and `eea3f05d`: the first reads a line that was already
correct and unread, and the second moves test code without changing behaviour.
So the mutations below are the sole proof, per `build-slice` §2's born-green
rule, and both were watched in this session.

**Mutated:** `execution.py:2724`'s selection narrowed to a flat
`verbs=replay_module.DETECTION` -> `AssertionError: _Verbs(open_sql='SELECT
open_impact_replay($1::uuid, $2::uuid, $3)', ... chain_sql='SELECT
build_kill_chain(...)') is not _Verbs(open_sql='SELECT open_test_replay($1::uuid,
$2::uuid, $3)', close_sql='SELECT close_test_replay($1::uuid, $2, $3)',
stamp_sql='', chain_sql='')`, one red in 224. And `cls.runtime` replaced by
`cls.connection` in all three hoisted members -- the one token the review found
the copies differed in -> `redkraken.pg.DatabaseError: 42501: rk2.program_id is
not set on this connection | PL/pgSQL function rk2_program_required() line 6 at
RAISE`, raised through `LiveDoorFixture.called` in both subclasses'
`setUpClass`, `Ran 0 tests`, `FAILED (errors=2)`.

**Forward references left standing:** none.

Nothing in either criterion turned out wrong. One departure from criterion 6's
letter, recorded rather than left to a reader: hoisting `as_owner` and `rows_of`
onto `LiveDoorFixture` gives each **one** reader in that branch, not two -- only
`called` was duplicated between the two live-door subclasses, and those two were
duplicated against `ReplayFixture`'s copies over `cls.connection`, which is a
different branch of the tree and keeps its own. The criterion asked for all
three hoisted and all three are; what it buys for two of them is the next
live-door subclass rather than a second reader today. The `## Seam check`
record names it on both lines.

One member was added rather than deleted. `RuntimeChainTest.replayed` used to be
a `replay.run` call and two assertions in one method; `attempt` needs the call
without the assertions, so the assertions moved to `must_hold`, which
`validated_finding` calls twice. That is one method where cycle 1 counted nine
copies, and it is door-shaped: the assertions are about this fixture's own door
replay holding.

**A third departure, found by cycle 2 rather than written here.** `settle` and
`approve` are two of the nine members cycle 1 counted, they touch no door, and
no hunk of this diff touched either: `settle` still holds
`PivotStampFixture.settled`'s two statements and `approve` still re-spells
`ImpactRunFixture.as_operator`'s connect, BIND and close. The reason is the one
this block already gives for `ReplayFixture`'s copies -- both originals live on
fixtures over `cls.connection`, a different branch of the tree -- but criterion
6's summary said "only the door-shaped members kept local" instead of saying
that, so the departure was silent until the review read it. Two axes read it
independently. The criterion now names both members and this reason.

## Bar, 2026-09-03

1. **Every acceptance criterion is ticked.**

   ```
   grep -c '^- \[ \]' <ticket>
     0
   grep -c '^- \[[ x]\]' <ticket>
     4
   ```
2. **The seam test passes, read by name.** This effort's spec carries no
   `## Verify command`, which ticket 236 measured one day earlier; the tests
   are named in full.

   ```
   export RK_TEST_SUPERUSER_URL="postgres://postgres:...@127.0.0.1:55433/postgres"
   export RK_TEST_DATABASE=rk2_t226
   NO_COLOR=1 uv run python -m unittest tests.test_database.RuntimeChainTest -v
     test_each_impact_run_was_parked_for_a_person_before_it_ran ... ok
     test_the_chain_the_runtime_built_holds_both_stamps_in_order ... ok
     test_the_first_run_is_refused_a_chain_and_the_second_composes_one ... ok
     test_the_runtime_stamped_a_pivot_off_each_run_it_performed ... ok
     test_the_standing_check_is_green_over_a_program_that_holds_a_chain ... ok
     Ran 5 tests in 25.004s
     OK
   ```
3. **Forward references redeemed.** Nothing was owed to this ticket.

   ```
   grep -rn 'ticket 226\|Ticket 226' docs/specs/production-harness-v2/   # this ticket excluded
     229-...md:124: ... the same vacuous-green failure ticket 226 names for the
     228-...md:198: ... and ticket 226's whole point is that a
   ```

   Both are prose inside those tickets' own bodies. No `CONSUMED BY`,
   `CONSUMES` or `deferred to` on either.
4. **Existing tests still pass, none skipped, deleted or weakened.** The
   `skipped=3` below is `tests.test_audit.RunnableProbe`'s three deliberate
   probes, pre-existing and untouched by this diff, which changes one literal
   line of that file -- noted by cycle 1.

   ```
   NO_COLOR=1 uv run python -m unittest tests.test_database.CleanCreationTest \
     tests.test_database.RuntimeChainTest tests.test_database.ImpactPerformanceTest \
     tests.test_database.KillChainTest tests.test_database.PivotStampTest \
     tests.test_database.ImpactProofTest tests.test_database.ReplayCommandTest \
     tests.test_database.ValidationCommandTest -q
     Ran 137 tests in 73.431s
     OK
   ```

   Those seven neighbours are the ones a change here could break: the two
   `LiveDoorFixture` subclasses that already existed, the four classes that own
   the impact, pivot and chain verbs, and `CleanCreationTest`, which every
   database invocation carries.

   ```
   NO_COLOR=1 uv run python -m unittest tests.test_audit tests.test_coverage -q
     Ran 107 tests in 58.426s
     OK (skipped=3)
   ```

   And the four gates as programs: `check_audit` rc=0 (rc=1 before this
   ticket's NOW repair), `check_wiring` rc=0, `check_baseline` rc=0,
   `check_coverage` rc=0.

   The full `tests/test_database.py` was **not** run: 1359 tests and over
   thirty minutes, against a change that adds one class and rewrites five lines
   of one fixture. What was run instead is every class that inherits the
   rewritten fixture and every class that owns a verb the new one calls.

   ```
   git diff --numstat
     21  2  docs/specs/.../226-the-kill-chain-has-never-had-a-single-row.md
     1   1  docs/specs/.../65-prove-first-hunt-release-candidate.md
     1   1  tests/test_audit.py
     551 5  tests/test_database.py
   ```

   The five deletions in `tests/test_database.py` are the whole of the
   `LiveDoorFixture` rewrite and nothing else:

   ```
   git diff -U0 -- tests/test_database.py | grep '^-' | grep -v '^---'
     -        # establishes the key generation under.
     -        root_secret = seal.Root("live-proxy-selftest-root", SECRET)
     -        source = SCOPED.replace(SCOPED_BUDGETS, WIDE_ENOUGH)
     -            root_secret=root_secret,
     -            root_secret=root_secret,
   ```

   No `.skip`, no deleted test, no removed assertion. The one deleted comment
   line was replaced by a longer one on the line above it.
5. **The diff is what the ticket asked for.**

   ```
   git status --short --untracked-files=all
     M docs/specs/.../226-the-kill-chain-has-never-had-a-single-row.md
     M docs/specs/.../65-prove-first-hunt-release-candidate.md
     M tests/test_audit.py
     M tests/test_database.py
   ```

   Four paths, no untracked file. `tests/test_database.py` is the `Touches`
   line; this ticket's file is this flow's own; and the other two are the NOW
   repair `## Build findings` records, named there by file.
6. **The blocks.**

   ```
   grep -c '^## Resolution' <ticket>
     1
   grep -c '^## Bar' <ticket>
     1
   grep -c '^## Handoff' <ticket>
     0
   ```

**Judgement, red and mutated.** The red is `none — born green`, and it is the
honest answer: walls 1 and 2 shipped four days ago and this criterion asserts
over them. So the `Mutated:` line is the sole proof, and it was watched in this
session -- `_downstream` cut off at its first statement, four tests red, the two
assertion messages in `## Resolution` quoted from that run, the file restored
from a copy and the class re-run green.

**Judgement, no unexplained NOBODY.** Every far end in `## Seam check` is a
symbol that was opened, a command that was run, or a resolved ticket that wrote
the thing being read. The one non-code reader is the operator running the named
test, and that command is pasted in line 2 above.

**Judgement, the live run reached this ticket's case.** It is the case: this is
the first execution of `replay._downstream` in the history of this repository,
and it went out through a real door to a real socket under a real sealed
Identity, twice, after two real operator answers. `chains = 1` and
`pivot_stamps = 2` on a Program that held neither an hour ago. There is no
`live-inputs.md` in this effort to replay, which `## Seam check` records.

**Judgement, Rule 3b, as cycle 1 corrected it.** No double stands in for a
door, an Identity or a Receipt: the run is real ciphertext through a real
`proxy.listen` to a real socket, and the Receipts are the door's own. Four
things are substituted, each reasoned where it sits in `tests/test_database.py`
and none of them named here before the review:

1. **The dialled address.** `LiveDoorFixture.dial` puts every authorised name
   on the loopback port, for `ProxyEgressTest`'s reason that `127.0.0.1` can
   never be a Program's scope. What is faked is where the socket goes, not the
   decision that authorised it.
2. **The counterparty's state transition.** `WritingTarget.served` increments
   on every request, so the `body_differs` of the reading action against the
   baseline holds whether or not the POST wrote anything, and the pivot's
   held-rather-than-refuted verdict rests on a comparison that cannot fail.
   The counter is needed because four GETs of one url must all differ; the
   consequence is that this case proves the run reached the target, not that
   the target changed. `rk2_pivot_refusal`'s own rule is checked by
   `PivotStampTest`, over rows written by hand.
3. **`claim_task`.** `UPDATE tasks SET status = 'claimed'` in its place.
   `claim_task`'s own behaviour is checked by the scheduler's classes.
4. **The scheduler's settle, and the lease.**
   `UPDATE tasks SET status = 'abandoned'` in place of the settle, and a direct
   `INSERT INTO identity_leases`. Both are arrangement, and both verbs are
   checked where they are owned.

None is deferred, because in each case the real thing is checked by a named
existing class rather than by this one.

**Re-measured by review cycle 1, 2026-09-03, under this same heading.** Two
criteria were added by this cycle's verdicts, so line 1 no longer prints `0`
and this ticket is mid-flight rather than finished. The two `unittest`
invocations behind lines 2 and 4 need the live cluster and were not available
to this pass; what could be re-run was.

```
1.  grep -c '^- \[ \]'   <ticket>
      2                       # the two criteria this cycle added, both open
    grep -c '^- \[[ x]\]' <ticket>
      6                       # four ticked from the build, two open

2.  not re-run: needs the PostgreSQL cluster. The build's paste stands, and
    the seam report is unchanged by this cycle except in what it names as the
    readers of rows already written.

3.  grep -rn 'ticket 226\|Ticket 226' docs/specs/production-harness-v2/
      live-inputs.md:3          # minted by this cycle; prose
      228-...md:198             # prose in that ticket's own body
      229-...md:124             # prose in that ticket's own body
      … (14 lines, all inside this ticket's own dated blocks: history)
    No CONSUMED BY, CONSUMES or deferred to on any of them.

4.  not re-run for tests.test_database: needs the cluster. Re-run here:
      NO_COLOR=1 .venv/bin/python -m unittest tests.test_audit tests.test_coverage -q
        Ran 107 tests in 58.878s
        OK (skipped=3)
      and the four gates as programs, each under .venv/bin/python:
        check_audit rc=0
        check_wiring rc=0
        check_baseline rc=0
        check_coverage rc=0
    This cycle's repairs add no .skip, delete no test and remove no assertion:
      git diff -U0 -- tests/test_database.py | grep '^-' | grep -v '^---'
        -    def rows_of(cls, sql: str, parameters: tuple = ()) -> list:
        -WEARER = "member"
        … (7 lines, each the WEARER spelling replaced by SLOT on the line below)

5.  git status --short --untracked-files=all
      M .../226-the-kill-chain-has-never-had-a-single-row.md
      M .../65-prove-first-hunt-release-candidate.md
      M tests/test_database.py
      ?? docs/specs/production-harness-v2/live-inputs.md
    git diff --numstat
      210  13  .../226-the-kill-chain-has-never-had-a-single-row.md
      1    1   .../65-prove-first-hunt-release-candidate.md
      13   9   tests/test_database.py
    Four paths. This ticket's own file and 65's are this flow's; the three
    edits to tests/test_database.py are three NOW repairs; and live-inputs.md
    is the effort artifact one NOW repair minted. tests/test_audit.py is NOT
    in this list, and that is the point of the audit finding's verdict: the
    frozen literal moves in the commit that writes `resolved`, not in this one.

6.  grep -c '^## Resolution' <ticket>   1
    grep -c '^## Bar'        <ticket>   1
    grep -c '^## Handoff'    <ticket>   0
```

## Bar, 2026-09-03 — cycle 1's two criteria

A second dated heading rather than an append under the first, because this is a
build run and not a review's NOW repair: the build above cleared the bar over
four criteria, and cycle 1 added two more.

1. **Every acceptance criterion is ticked.**

   ```
   grep -c '^- \[ \]' <ticket>
     0
   grep -c '^- \[[ x]\]' <ticket>
     6
   ```
2. **The seam test passes, read by name.** This effort's spec still carries no
   `## Verify command`, which ticket 236 measured and this ticket's first bar
   run recorded; the tests are named in full. Criterion 5's test:

   ```
   NO_COLOR=1 uv run python -m unittest tests.test_execution.ImpactReplayTest -v
     test_a_row_from_before_this_column_reads_as_a_detection_task ... ok
     test_a_task_whose_test_states_an_impact_takes_the_impact_verbs ... ok
     test_a_task_whose_test_states_no_impact_is_handed_the_detection_verbs ... ok
     test_a_task_whose_test_states_none_is_a_detection_task ... ok
     test_the_class_reaches_the_claim_through_the_row_the_query_returns ... ok
     test_the_runtime_hands_the_performer_the_impact_verbs ... ok
     test_the_two_verb_sets_are_not_the_same_object ... ok
     Ran 7 tests in 0.004s
     OK
   ```

   `test_the_runtime_hands_the_performer_the_impact_verbs` and
   `test_a_task_whose_test_states_no_impact_is_handed_the_detection_verbs` are
   the two this criterion added. Criterion 6's guards are the two live-door
   classes, and the criterion is behaviour-preserving, so what it has to show is
   both of them still green over the hoisted members:

   ```
   export RK_TEST_SUPERUSER_URL="postgres://postgres:...@127.0.0.1:55433/postgres"
   export RK_TEST_DATABASE=rk2_t226b
   NO_COLOR=1 uv run python -m unittest tests.test_database.RuntimeChainTest \
     tests.test_database.ValidationCommandTest -v
     test_each_impact_run_was_parked_for_a_person_before_it_ran ... ok
     test_the_chain_the_runtime_built_holds_both_stamps_in_order ... ok
     test_the_first_run_is_refused_a_chain_and_the_second_composes_one ... ok
     test_the_runtime_stamped_a_pivot_off_each_run_it_performed ... ok
     test_the_standing_check_is_green_over_a_program_that_holds_a_chain ... ok
     … (20 lines, ValidationCommandTest's own tests, each `... ok`)
     Ran 25 tests in 33.336s
     OK
   ```
3. **Forward references redeemed.** Nothing was owed to this ticket, and this
   pass wrote none.

   ```
   grep -rn 'ticket 226\|Ticket 226' docs/specs/production-harness-v2/   # this ticket excluded
     live-inputs.md:3:Minted at ticket 226 by that ticket's review cycle 1, not by the walking
     229-the-only-notifier-a-finding-has-is-not-in-this-repository.md:124:this corpus can see -- the same vacuous-green failure ticket 226 names for the
     228-one-broken-notifier-halts-the-whole-harness.md:198:  is not consent to demonstrate impact, and ticket 226's whole point is that a
   ```

   Three hits, all prose: `live-inputs.md`'s header sentence and one line inside
   each of two other tickets' own bodies. No `CONSUMED BY`, `CONSUMES` or
   `deferred to` on any of them.
4. **Existing tests still pass, and one assertion moved rather than went.** The
   `skipped=3` below is `tests.test_audit.RunnableProbe`'s three deliberate
   probes, pre-existing and untouched by this diff, which does not touch that
   file at all.

   ```
   NO_COLOR=1 uv run python -m unittest tests.test_execution -q
     Ran 224 tests in 0.574s
     OK

   NO_COLOR=1 uv run python -m unittest tests.test_database.CleanCreationTest \
     tests.test_database.RuntimeChainTest tests.test_database.ImpactPerformanceTest \
     tests.test_database.KillChainTest tests.test_database.PivotStampTest \
     tests.test_database.ImpactProofTest tests.test_database.ReplayCommandTest \
     tests.test_database.ValidationCommandTest -q
     Ran 137 tests in 74.313s
     OK

   NO_COLOR=1 uv run python -m unittest tests.test_audit tests.test_coverage -q
     Ran 107 tests in 73.843s
     OK (skipped=3)
   ```

   `137` is the same count the first bar run measured over the same eight
   classes, and `224` is `tests.test_execution` with this pass's two tests in
   it. The four gates as programs, each under `.venv/bin/python`:

   ```
   check_audit rc=0
   check_wiring rc=0
   check_baseline rc=0
   check_coverage rc=0
   ```

   The full `tests/test_database.py` was **not** run, for the first bar run's
   reason and more strongly: this diff adds no schema, no verb and no grant, and
   moves five fixture members inside one class hierarchy. What was run is every
   class that inherits the rewritten fixture -- `RuntimeChainTest`,
   `ValidationCommandTest` and `ReplayCommandTest` are `LiveDoorFixture`'s three
   subclasses and all three are above -- plus the four that own the impact,
   pivot and chain verbs, plus `CleanCreationTest`.

   ```
   git diff -U0 -- tests/test_execution.py | grep '^-' | grep -v '^---'
     (no output: 49 added lines, 0 deleted)
   ```

   **One assertion was removed, and it is the one criterion 5 replaced.**
   `RuntimeChainTest.attempt` held `assert impact_class is not None, test` over
   a column it read only to re-derive the runtime's dispatch. The dispatch is
   now asserted in `tests.test_execution.ImpactReplayTest` against the call
   `_replay` actually makes, and `open_impact_replay` refuses a Test carrying no
   class in any case, so what went is a fixture guard whose subject moved to a
   test -- lowering-move 2 read the other way round. Everything else deleted
   from `tests/test_database.py` is a member the criterion named:

   ```
   git diff -U0 -- tests/test_database.py | grep '^-' | grep -v '^---' | grep -c .
     92
   ```

   No `.skip`, no `# type: ignore`, no deleted test, and no test class or test
   method removed -- the 92 deleted lines are two `called` copies, `rows_of`,
   `as_owner`, `id_of`, four re-spelled constants, six inline statements, the
   third `replay.run` spelling and the docstrings that described them.

   ```
   git diff --numstat
     405  5   docs/specs/.../226-the-kill-chain-has-never-had-a-single-row.md
     104  92  tests/test_database.py
     49   0   tests/test_execution.py
   ```
5. **The diff is what the ticket asked for.**

   ```
   git status --short --untracked-files=all
     M docs/specs/.../226-the-kill-chain-has-never-had-a-single-row.md
     M tests/test_database.py
     M tests/test_execution.py
   ```

   Three paths, no untracked file. Both test files are on the `Touches` line as
   §1 corrected it this session, and this ticket's own file is this flow's.
   `tests/test_audit.py` and ticket 65's file are **not** in this list: cycle 1's
   audit verdict put the frozen `resolved 204` in the commit that finally writes
   `resolved`, which is `review-pass`'s commit and not this one, and 65's
   `Blocked by` entry landed in cycle 1's review commit.
6. **The blocks.**

   ```
   grep -c '^## Resolution' <ticket>
     2
   grep -c '^## Bar' <ticket>
     2
   grep -c '^## Handoff' <ticket>
     0
   ```

   Two of each: one pair from the build, one from this pass. The bar asks for at
   least one, and the later dated block is the current one.

**Judgement, red and mutated.** `Red: none — born green`, honestly, and for
both criteria: criterion 5 asserts over a selection that shipped in `685d860f`
and criterion 6 changes no behaviour at all. So the mutations are the sole
proof and both were watched in this session, not reasoned about --
`execution.py:2724` narrowed to a flat `DETECTION` for one red in 224, and
`cls.runtime` swapped for `cls.connection` in the three hoisted members for two
dead `setUpClass` calls. Both assertion messages are quoted verbatim in
`## Resolution, 2026-09-03 — cycle 1's two criteria`, and the files were
restored from copies taken before each mutation.

**Judgement, no unexplained NOBODY.** No `NOBODY` in the second seam pass. Every
far end is a symbol that was opened and read, or the operator running a named
test, and both of those commands are pasted in line 2 above. The one departure
worth a reader's attention is recorded on its own two lines in the seam record
and in the resolution: `as_owner` and `rows_of` have one reader each in the
live-door branch, not two.

**Judgement, the live run reached this ticket's case.** It did, again: the same
two impact replays through a real `proxy.listen` door, real sealed Identity
material, two operator answers on the `rk2_human` connection, `pivot_stamps` =
2 and one chain over 2 steps and 1 edge, `check_kill_chains()` quiet over it.
`live-inputs.md` holds one block, 226's, at
`STATUS promoted to tests.test_database.RuntimeChainTest` -- no block in the
file has a `STATUS` beginning `live`, so nothing was owed a hand replay and
`REPLAYS` stays `0 ()`. The spec names no `Load` figure for this path.

**Judgement, Rule 3b.** Unchanged. The four substitutions the first bar run
listed -- the dialled address, the counterparty's state transition, `claim_task`
and the scheduler's settle with its lease -- are the same four, in the same
places, each still reasoned where it sits and each still checked in the real by a
named existing class. One double **was** injected, which cycle 2 found this
sentence denying, so it is a fifth substitution rather than a correction:
`tests/test_execution.py`'s `ImpactReplayTest.replay_called` stubs
`execution.replay_module.run` with `mock.patch.object`, and criterion 5's two
assertions read `verbs` off that mock. What checks the real thing is
`RuntimeChainTest` in this same ticket, which hands `verbs=replay.IMPACT` to
the real `replay.run` and reaches both stamps through a real door -- so nothing
is deferred. The stub is the point of that test rather than a shortcut in it:
the seam under assertion is which verb set `_replay` passes, and a test that
performed the replay would be asserting the performer instead.

**Cycle 2's NOW repairs, re-run under this heading rather than under a new
dated one** -- a dated heading is a build's, and this is a review's repair
(`hold-the-line` verdict 1). No production file was touched: the repairs are
five edits to `tests/`, ten to this ticket's prose, and one frozen count. So no
red test is owed, and what follows is the machine lines re-read.

1. **Every acceptance criterion is ticked.**

   ```
   grep -c '^- \[ \]' <ticket>
     0
   grep -c '^- \[[ x]\]' <ticket>
     6
   ```

   Still six. Cycle 2 added no criterion, which is why this pass writes
   `resolved`.
2. **The seam test passes, read by name.** Criterion 5's tests, with the
   renamed one among them:

   ```
   NO_COLOR=1 uv run python -m unittest tests.test_execution.ImpactReplayTest -v
     test_a_row_from_before_this_column_reads_as_a_detection_task ... ok
     test_a_task_whose_test_states_an_impact_carries_the_impact_class ... ok
     test_a_task_whose_test_states_no_impact_is_handed_the_detection_verbs ... ok
     test_a_task_whose_test_states_none_is_a_detection_task ... ok
     test_the_class_reaches_the_claim_through_the_row_the_query_returns ... ok
     test_the_runtime_hands_the_performer_the_impact_verbs ... ok
     test_the_two_verb_sets_are_not_the_same_object ... ok
     Ran 7 tests in 0.007s
     OK
   ```

   Criterion 6's guard is the live-door branch, and this pass edited the base
   class twice -- `called` onto `committed`, a docstring on `rows_of` -- so all
   three subclasses were run, inside the eight-class batch of line 4:

   ```
   export RK_TEST_SUPERUSER_URL="postgres://postgres:...@127.0.0.1:55433/postgres"
   export RK_TEST_DATABASE=rk2_t226c2b
   NO_COLOR=1 uv run python -m unittest tests.test_database.CleanCreationTest \
     tests.test_database.RuntimeChainTest tests.test_database.ImpactPerformanceTest \
     tests.test_database.KillChainTest tests.test_database.PivotStampTest \
     tests.test_database.ImpactProofTest tests.test_database.ReplayCommandTest \
     tests.test_database.ValidationCommandTest -v
     test_each_impact_run_was_parked_for_a_person_before_it_ran ... ok
     test_the_chain_the_runtime_built_holds_both_stamps_in_order ... ok
     test_the_first_run_is_refused_a_chain_and_the_second_composes_one ... ok
     test_the_runtime_stamped_a_pivot_off_each_run_it_performed ... ok
     test_the_standing_check_is_green_over_a_program_that_holds_a_chain ... ok
     … (132 lines, the other seven classes' tests, each `... ok`)
     Ran 137 tests in 92.533s
     OK
   ```

   The five quoted are `RuntimeChainTest`'s, filtered out of that run's verbose
   output by class name rather than re-run on their own.
3. **Forward references redeemed.** Nothing is owed to this ticket and this
   pass wrote none. Cycle 2's [bar] finding was that the paste above is not what
   the command prints, so here it is whole, with full paths:

   ```
   grep -rn 'ticket 226\|Ticket 226' docs/specs/production-harness-v2/ | wc -l
     29
   grep -rn 'ticket 226\|Ticket 226' docs/specs/production-harness-v2/
     docs/specs/production-harness-v2/live-inputs.md:3:Minted at ticket 226 by that ticket's review cycle 1, not by the walking
     docs/specs/production-harness-v2/issues/228-one-broken-notifier-halts-the-whole-harness.md:198:  is not consent to demonstrate impact, and ticket 226's whole point is that a
     … (26 lines, all inside this ticket's own dated blocks: history, and 23 of
        them written by cycle 2 itself, including this very paste)
     docs/specs/production-harness-v2/issues/229-the-only-notifier-a-finding-has-is-not-in-this-repository.md:124:this corpus can see -- the same vacuous-green failure ticket 226 names for the
   ```

   29 hits, 26 of them this ticket's own, run after this paste landed so that
   the paste's own lines are inside the elided 26. **The order is not stable and
   no reader should pin it.** Cycle 2's [bar] finding said 228 and 229 came out
   in the reverse of the order the command emits; re-run after this file was
   rewritten, 228 is hit 2 and 229 is hit 29, where in the earlier run they were
   24 and 25. `grep -r` walks the directory in `readdir` order, which moves when
   a file in it is rewritten. So the three non-self hits are quoted whole and the
   self-hits are elided by count, which is what the standing bar asks for and what
   cycle 1's own repair carried. All three are prose -- no `CONSUMED BY`, no
   `CONSUMES`, no `deferred to` -- and cycle 2 read the other 26 as well.
4. **Existing tests still pass, and nothing was skipped, deleted or weakened.**
   The `skipped=3` is `tests.test_audit.RunnableProbe`'s three deliberate
   probes, pre-existing and untouched.

   ```
   NO_COLOR=1 uv run python -m unittest tests.test_execution -q
     Ran 224 tests in 0.582s
     OK

   NO_COLOR=1 uv run python -m unittest <the eight classes of line 2> -q
     Ran 137 tests in 92.533s
     OK

   NO_COLOR=1 uv run python -m unittest tests.test_audit tests.test_coverage -q
     Ran 107 tests in 59.217s
     OK (skipped=3)
   ```

   The three counts are the same 224, 137 and 107 the criterion pass measured:
   this pass renames one test and freezes one number, and adds none. Every
   deleted line, read whole rather than counted:

   ```
   git diff -U0 -- tests/ | grep '^-' | grep -v '^---'
     -            "  tickets                236   resolved 204  audited 63  deferred criteria 11\n"
     -        the copies was the connection's name and nothing else.
     -        with cls.runtime.transaction():
     -            cls.runtime.execute("SELECT set_actor('runtime', 'selftest')")
     -            answered = cls.runtime.execute(sql, parameters).scalar()
     -        return json.loads(str(answered))
     -        **verbs,
     -            **verbs,
     -    def test_a_task_whose_test_states_an_impact_takes_the_impact_verbs(self):
   ```

   Nine lines: the frozen count, the four-line `called` body and one docstring
   sentence that `committed` replaces, the two `**verbs` spellings the named
   keyword replaces, and the old name of a test whose new name is added in the
   same hunk. No `.skip`, no ignore pragma, no deleted test file, no removed
   assertion, no removed test method.

   The four gates, as `docs/agents/testing.md` tier 2 spells them -- which is
   cycle 2's other [bar] finding, because `.venv/bin/python tools/check_audit.py`
   exits 1 with `ModuleNotFoundError: No module named 'tools'`:

   ```
   PYTHONPATH=$PWD python3 -s tools/check_audit.py
     tickets                236   resolved 205  audited 63  deferred criteria 11
     rc=0
   PYTHONPATH=$PWD python3 -s tools/check_wiring.py
     register                    42 rows   tickets 6  findings 42  distinct 42
     rc=0
   PYTHONPATH=$PWD python3 -s tools/check_baseline.py
     baseline ok: classifications=10 regressions=7 adapters=11 artifacts=223 frozen
     rc=0
   PYTHONPATH=$PWD/src:$PWD python3 -s tools/check_coverage.py
     catalogue               51   skills 6  references 86
     rc=0
   ```

   `resolved 205` is this pass writing `resolved`, and it is the reason
   `tests/test_audit.py` is in the diff: cycle 1's audit verdict put the frozen
   `resolved 204` in the commit that finally writes the status, which is this
   one. `audited 63` did not move, exactly as cycle 1 predicted it would not.
5. **The diff is what the review asked for.**

   ```
   git status --short --untracked-files=all
     M docs/specs/production-harness-v2/issues/226-the-kill-chain-has-never-had-a-single-row.md
     M tests/test_audit.py
     M tests/test_database.py
     M tests/test_execution.py

   git diff --numstat
     313  23  docs/specs/.../226-the-kill-chain-has-never-had-a-single-row.md
     1    1   tests/test_audit.py
     21   7   tests/test_database.py
     1    1   tests/test_execution.py
   ```

   The three code rows are final. The first row is the one number a paste inside
   the file it measures cannot state about itself -- it grows by however many
   lines the paste of it adds -- so it is measured immediately before the commit
   and `git show --numstat` on this cycle's review commit is the authority over
   it. Cycle 1 took a [ticket] finding for a `numstat` row measured mid-write,
   and this is the form that stops that repeating rather than repeating it
   quietly. Four paths, no untracked file. All four are on the `Touches` line as this
   ticket carries it -- both test files from the build, `tests/test_audit.py`
   named there by the build findings' NOW repair -- and this ticket's own file is
   this flow's. No other ticket file: cycle 2 raised no CRITERION, REOPEN or
   TICKET verdict, so nothing was written outside this ticket.
6. **The blocks.**

   ```
   grep -c '^## Resolution' <ticket>
     2
   grep -c '^## Bar' <ticket>
     2
   grep -c '^## Handoff' <ticket>
     0
   ```

   Unchanged: this pass appended under the second `## Bar` heading rather than
   opening a third, and added a paragraph to the second `## Resolution` rather
   than dating a new one.

**Judgement, red and mutated, cycle 2.** Not owed and not claimed. Every repair
in this pass is a rename, a collapse onto an existing helper, a named keyword, an
import-time assert, a docstring, a frozen count and ten prose corrections -- no
production file is in the diff, which is the one case `hold-the-line` verdict 1
lets a NOW repair skip a red test for. The two mutations that prove this
ticket's seams are cycle 1's, quoted in `## Resolution, 2026-09-03 — cycle 1's
two criteria`, and they still hold: the `verbs=` selection is read by two tests
in `ImpactReplayTest`, and both live-door subclasses still die in `setUpClass`
if the hoisted members are pointed at the wrong connection.

**Judgement, no unexplained NOBODY.** Unchanged, and one head corrected rather
than added: `ImpactRunFixture.REASON`'s writer is ticket 39's `37d99d6b`, not
ticket 38's `3f2d4921`. No `NOBODY` anywhere in either pass.

**Judgement, the live run reached this ticket's case.** It did, a third time, on
`rk2-test-pg` at `127.0.0.1:55433` with `RK_TEST_DATABASE=rk2_t226c2b`: the same
two impact replays through a real `proxy.listen` door under a leased Identity,
two operator answers on the `rk2_human` connection, and
`test_the_standing_check_is_green_over_a_program_that_holds_a_chain` green over
the result. `live-inputs.md`'s one block still reads
`STATUS promoted to tests.test_database.RuntimeChainTest` and `REPLAYS 0 ()`; no
block in the file begins `live`, so no hand replay was owed and this pass moved
`REPLAYS` for nothing.

**Judgement, Rule 3b.** Five substitutions, not four -- see the correction under
this heading above and in `## Seam check`'s second pass. The fifth is
`ImpactReplayTest.replay_called`'s stub of `execution.replay_module.run`, and
what checks the real thing is `RuntimeChainTest`, which hands the real
`replay.run` a real door in this same ticket. Nothing is deferred to another
ticket.

## Review findings, 2026-09-03 — cycle 1

Fixed point `7cfabf29`, the parent of this ticket's only `(ticket 226)` build
commit. Four readers, run apart, reported 25 findings; the axis tag on each
entry is the reader that raised it. Three convergences are noted in the entries
that share them.

- [ticket] **Criterion 2 is ticked over a line nothing asserts. `verbs=` at `execution.py:2723-2725` is the only runtime site; `ImpactReplayTest`'s five tests assert `Claimed.impact_class` and the two `stamp_sql` values, never the call kwargs; and `RuntimeChainTest.attempt` re-spells the expression at `test_database.py:55057` instead of calling `_replay`. Narrowing `execution.py:2724` to `DETECTION` leaves the whole tree green.** — required — CRITERION on ticket 226. The criterion added above: one assertion over `_replay`'s call kwargs in `ImpactReplayTest`, watched failing under the narrowing first.
- [bar] **Both audit gates go red on the edit that resolves this ticket: `check_audit` computes the release-outcome closure over ticket 65's `Blocked by` and 226 is not on it, so `resolved` yields `ticket 226: resolved, and no path reaches ticket 65 from it`; and `test_audit.py:76`'s frozen `resolved 204` becomes 205. This is the same defect `## Build findings` repaired for 233 and did not apply to 226 itself.** — required — NOW. `226 — The kill chain analysis has never held a single row` added to ticket 65's `Blocked by`, in the position the list puts a ticket as it lands. `check_audit` rc=0 after it and the report is unchanged, because 226 is still `claimed`; `tests/test_audit.py`'s frozen `resolved 204` is therefore untouched and moves to 205 in the commit that finally writes `resolved`. No production code, so no red test is owed.
- [seam] **The record's reader for the rows this ticket wrote cannot falsify. Arm (h)'s second half requires a `rank_pass` whose comment-stripped `prosrc` no longer matches `derive_impact_specifications` or `derive_impact_performances`, and the deployed `rank_pass` calls both in code, so arm (h) is quiet whether `chains` holds a row or not. Converges with the [ticket] entry below.** — required — NOW. `## Seam check`'s `READ BY` for those rows rewritten: arms (a)-(g) and `build_kill_chain`'s own `SELECT id FROM pivot_stamps` named as the readers that evaluate over the rows, and arm (h) recorded as the non-discriminating far end it is, with its real proof placed where it was taken.
- [ticket] **Neither far end named for "the pivot_stamps and chains rows the two impact runs left" reads them. Arm (h) reads `chains` only through `NOT EXISTS`, and `rk2_chain_unlock_frontier` gates its `gap` CTE on a stamp that is not already a step, so two stamps both consumed by the composed chain yield no frontier row and wall 3's `chain_unlock_for(t)` is still zero here. Converges with the [seam] entry above.** — required — NOW. Same rewrite: `rk2_chain_unlock_frontier` recorded as reading nothing here, with the gap CTE's condition given, and wall 3 written down as reachable and still unmeasured. Going and measuring it is not asked for by any criterion; a third stamp is the lead a later session needs.
- [craft] **Nine members of `RuntimeChainTest` were copied from fixtures they touch no Receipt and no door to justify: `as_owner` byte-identical to `ReplayFixture.as_owner`; `rows_of` and `id_of` differing from theirs in the single token `cls.connection`/`cls.runtime`; `settle` re-spelling `PivotStampFixture.settled`; `called` re-spelling `ValidationCommandTest.called`; `approve` re-spelling `ImpactRunFixture.as_operator` plus `approve` over two attributes `LiveDoorFixture` already holds; `GRANTED` and `TITLE` re-spelling `ImpactRunFixture.REASON` and `ValidationCommandTest.TITLE` character for character; and `validated_finding` re-spelling as inline literals the six connection-free constants `ValidatedFindingFixture` names. What blocked reuse is the connection's name, not the hand-written Receipts the ticket cites, and three fixture docstrings in this same file set the opposite standard.** — required — CRITERION on ticket 226. The criterion added above, naming each member and its original. The session that returns has the cluster the refactor needs; this one does not.
- [seam] **`READ redkraken.replay::run's verbs= parameter, and redkraken.replay::IMPACT` is recorded as `WRITTEN BY ticket 226 wall 2, commit 685d860f`, and that commit touches no file under `src/redkraken/replay.py`. `git blame` puts `verbs: _Verbs = DETECTION` and `IMPACT`'s open and close at `3f2d4921`, and `IMPACT`'s two stamp statements at `77bcfecd`. The ticket's own wall-2 section says as much, so the file contradicts itself. Converges with the [ticket] entry below.** — required — NOW. Rewritten to ticket 38 for the parameter and `IMPACT`'s open and close, ticket 103 for the two stamp statements, with what wall 2 actually wrote named beside it.
- [ticket] **Two of the three `CONSUMES` writer heads name a commit that does not contain the cited symbol: `replay::run`'s `verbs=` and `replay.IMPACT` were written by ticket 38, and `open_impact_task` is created in ticket 38's impact migration, not by wall 1 — which this ticket's own `## Seam check` already states for `open_impact_task`. Converges with the [seam] entry above.** — required — NOW. Both heads rewritten to ticket 38, keeping wall 2 as the writer of the selection and wall 1 as the writer of the objective.
- [ticket] **Criterion 4's text promises "so the empty case stops reading as green", and the shipped arm (h) fires only on a pair whose second half is a stubbed `rank_pass`, so with the wiring intact the empty case still reads green. The ticket concedes it twice and names its own test for it.** — required — NOW. The criterion rewritten to the pair the arm asserts, with the reason a state-only arm cannot be built, and the residual named as declined below.
- [seam] **This pass wrote a live far end nothing following it can read. There is no `docs/specs/production-harness-v2/live-inputs.md`, so the next ticket's §5 and `close-effort` walk 4 have no block for the first execution of `replay._downstream` in this repository. Ticket 166's wall is cited as covering it, but that wall's PRICE is the 231-file layout move and never prices this one file at this repository's own path, and 226 is the first ticket in the effort with a live far end worth recording — a fact 166 did not have.** — required — NOW. `docs/specs/production-harness-v2/live-inputs.md` minted with one block for 226 at `STATUS promoted to tests.test_database.RuntimeChainTest`, `REPLAYS 0 ()`, and a header saying why the file starts 225 tickets in. `promoted to` because the case is the assertion, so no following ticket owes a hand replay -- what `close-effort` walk 4 gets is a block it can read rather than nothing.
- [bar] **The Rule 3b judgement names the dialled address as the one faked value, and the fixture also hand-writes three pieces of state the runtime's own verbs own: `UPDATE tasks SET status = 'claimed'` in place of `claim_task`, `UPDATE tasks SET status = 'abandoned'` in place of the scheduler's settle, and a direct `INSERT INTO identity_leases`. Each is reasoned in its own docstring and none is visible to a reader of the ticket. Converges with the [ticket] entry below.** — required — NOW. The judgement rewritten to four numbered substitutions, each naming the class that checks the real verb, so none is deferred.
- [ticket] **The Rule 3b judgement also omits that the counterparty's state transition is faked: `WritingTarget.served` increments on every request, so the `body_differs` of action 3 against action 1 holds whether or not the POST wrote anything, and the pivot the case celebrates rests on a comparison that cannot fail. The class docstring is honest about the counter; the judgement is not. Converges with the [bar] entry above.** — nit — NOW. Substitution 2 of that rewrite, which states plainly that this case proves the run reached the target and not that the target changed.
- [ticket] **Criteria 1, 2 and 4 were built in commits `685d860f` and `cf1b75fa`, neither of whose subjects carries a `(ticket 226)` marker, so this flow's fixed-point procedure reaches criterion 3 alone and no review cycle has ever pinned the other three. Nothing in `tools/check_audit.py` enforces the marker, so the gap is invisible to the gate that counts this ticket as audited.** — required — NOW. Recorded under `## Acceptance` by commit, with what cycle 1 did and did not reach, and the rule that a later re-read pins those two commits one at a time rather than growing a cycle's diff over the fifteen tickets between them.
- [seam] **The record folds two written kinds into one `WROTE` line and cites only `FROM chains` readers, so `pivot_stamps` has no named reader — although the case proved one live, the second run's `build_kill_chain(ARRAY(SELECT id FROM pivot_stamps ...))` reading the first run's stamp.** — nit — NOW. `build_kill_chain`'s read of the first run's stamp named in the same rewrite.
- [bar] **Bar item 3's pasted command does not print its pasted output: run verbatim it prints seven hits, five of them this ticket's own lines, the two quoted lines have truncated filenames and mid-line elisions, and the five dropped lines carry no `… (N lines)` marker the standing bar requires.** — nit — NOW. Re-run and re-pasted whole under the existing `## Bar` heading, seven hits and no elision.
- [ticket] **Bar item 4's pasted `git diff --numstat` shows `21 2` for this ticket's own file where the pinned diff is `331 2`; the other three rows match exactly, so the row was measured mid-write.** — nit — NOW. Re-measured in the same append.
- [bar] **Bar item 4's heading reads "none skipped, deleted or weakened" and the paste four lines below it reads `OK (skipped=3)` with nothing reconciling them. The three are `test_audit.RunnableProbe`'s deliberate probes and are pre-existing.** — nit — NOW. The clause naming `RunnableProbe`'s three probes added to the heading.
- [bar] **`**Acceptance 3 was not built.**` still stands as a bald sentence while criterion 3 is now ticked; only a reader who tracks the dated headings can resolve the contradiction.** — nit — NOW. Rewritten to `was not built by this wall`, pointing at `## Resolution`.
- [ticket] **Two of the three citations in `## The three walls` no longer resolve: `cli.py:2904` is now `cli.py:2948`, and `execution.py:2577` lands in `_child`'s heartbeat block rather than `_replay`, which is at `execution.py:2640`.** — nit — NOW. The section dated as a 2026-08-30 reading, with both moved lines given their current numbers. Dating it beats re-citing three lines that will move again.
- [ticket] **`RuntimeChainTest.rows_of` is annotated `-> list` while `.rows` answers a tuple — the defect `## Build findings` measured and then fixed at the call site rather than at the accessor.** — nit — NOW. `-> tuple`. The two other `-> list` spellings of `rows_of` in this module are pre-existing and were left alone.
- [craft] **`LiveDoorFixture.SOURCE` is now an extension point with an unstated contract: `setUpClass` still does `.replace(SCOPED_BUDGETS, WIDE_ENOUGH)` and `.replace('name = "matrix-web"', ...)`, and both silently no-op for a subclass whose document is not `SCOPED`-derived, surfacing as unexplained budget refusals rather than as an error. The in-place change itself pushes nothing onto the two existing subclasses.** — nit — NOW. Four comment lines above the `replace`, naming both anchors and what a missing one looks like.
- [craft] **`WEARER` invents a word for the concept `CONTEXT.md` names Identity and this module spells `slot` everywhere else — `identity_slot=`, `slot_name`, `provisioned_identity(slot)`, `PivotStampFixture.configured(slots=...)`. `docs/agents/domain.md` requires the glossary's term over a synonym.** — nit — NOW. Renamed to `SLOT`, nine occurrences, matching the value and the spelling `ImpactRunFixture.SLOT` already uses.
- [bar] **`RuntimeChainTest.attempt` hand-copies `verbs=replay.IMPACT if impact_class else replay.DETECTION` from `execution.py:2724`, and its own `assert impact_class is not None` two lines up makes the `DETECTION` branch dead — a third reader of a one-line rule with nothing binding it to the first two, which is the drift this ticket's wall-1 section cites ticket 157 about.** — nit — ALREADY OWNED by cycle 1's `verbs=` criterion on this ticket, which names this hand-copy as half of its work. The nit row would say DECLINE; the work is owned, not declined, so the departure is written here rather than left silent.
- [craft] **`replay.run(...)` with the same six keyword arguments is now spelled three times inside one hierarchy — `LiveDoorFixture.walk`, `RuntimeChainTest.replayed` and `RuntimeChainTest.attempt` — differing only in `test`, `identity_slot` and `verbs`.** — nit — ALREADY OWNED by cycle 1's inherit-or-reference criterion on this ticket, which names the third spelling. Same departure from the nit row as above.
- [craft] **`RuntimeChainTest.id_of` exists only to make a round trip that ends where it started: `prove` already holds `opened["test"]`, `id_of` turns that label into an id, and `attempt` then selects the same label back out plus a second query for `impact_class`.** — nit — ALREADY OWNED by cycle 1's inherit-or-reference criterion, which names `id_of`. Same departure.
- [craft] **The `[[identity]]` block in `RuntimeChainTest.SOURCE` is hand-spelled for the sixth time in this module when `DECLARED` already holds that string.** — nit — ALREADY OWNED by cycle 1's inherit-or-reference criterion, which names `DECLARED`. Same departure.

**Declined in writing, so it is not the next review's finding.** Closing the
gap criterion 4 used to promise -- a `check_kill_chains()` arm that fires on a
Program holding a validated Finding and no chain, with the wiring intact --
will not be done. `check_kill_chains()` is a gate: a standing check that
returns rows refuses every pass, so such an arm would halt the campaign over a
Program that is merely early, which is D-11's mechanism and the shape live
`rk2here` holds today. Reporting vacuous green without gating on it is a
different mechanism than this corpus offers, and no criterion in this effort
asks for one. Ticket 229 names the same vacuous-green failure for Findings
nobody was told about; it is an analogy in that ticket's own prose, not
ownership of this arm.

Review cycle 1 of 3 — undecided: none

## Review findings, 2026-09-03 — cycle 2

Fixed point `172633bf`, cycle 1's review commit. The diff is one build commit,
`f1f1c0bd`, the repair of cycle 1's two criteria: 3 files, 558 insertions and 97
deletions, of which 405 insertions are this ticket's own file. Four readers, run
apart, reported 18 findings; the axis tag on each entry is the reader that
raised it. Three convergences are noted in the entries that share them.

- [ticket] **Criterion 6 is ticked over a claim source refuses. It says "the nine members that touch neither a Receipt nor a door are not this case's work" and "only the door-shaped members kept local", and two of cycle 1's nine were left local while being door-shaped in neither sense: `settle` (`test_database.py:55142`) still holds `PivotStampFixture.settled`'s two statements, differing in the single token `cls.connection`/`cls.runtime` that the other three were hoisted for, and `approve` (`:55123`) still re-spells `ImpactRunFixture.as_operator`'s connect/BIND/close ceremony plus its docstring sentence. The criterion's own enumeration silently drops both from the nine, no hunk in the diff touches either, and `## Resolution — cycle 1's two criteria` records two smaller departures under the sentence "Nothing in either criterion turned out wrong". Converges with the [craft] entry below.** — required —NOW. Criterion 6's last clause rewritten to name `settle` and `approve` and the branch reason they were kept for, and a third departure paragraph added to `## Resolution, 2026-09-03 — cycle 1's two criteria` beside the two it already recorded. The duplication is not removed: `PivotStampFixture.settled` and `ImpactRunFixture.as_operator` live on a different branch of the fixture tree, which is the reason this pass already accepted for `ReplayFixture`'s three copies, and no criterion in this effort asks for the module-wide de-duplication that would remove it. What was wrong was the silence.
- [craft] **Same two members, from the other side: criterion 6's summary "only the door-shaped members kept local" is false of `settle` and `approve`, and the technique this diff already proved on `ValidatedFindingFixture`'s six statement constants was not applied to either. Converges with the [ticket] entry above.** — required —NOW. Same rewrite, recorded once. Converged with the [ticket] entry above, which is what gives it its weight: two readers who could not see each other both opened criterion 6's summary against source.
- [craft] **`LiveDoorFixture.called` is a fourth hand-rolled copy of the module-level `committed()` (`test_database.py:25738`) — transaction, `set_actor`, `scalar` — while the three sibling `called` members (`OfflineToolRunTest:26504`, `BrowserMissionTest:28759`, `ReplayFixture:30703`) are each the one-liner `return json.loads(committed(cls.connection, sql, parameters))`, and `LiveDoorFixture.claimed` five lines below calls `committed(cls.runtime, ...)` itself. The de-dup criterion moved the copy up a class instead of collapsing it onto the helper that already exists, and the new docstring's own reason — "what differed between the copies was the connection's name and nothing else" — is precisely the argument for passing the connection in.** — required —NOW. `return json.loads(committed(cls.runtime, sql, parameters))`, matching the three siblings, with the docstring's second paragraph saying why the connection is handed in rather than the transaction spelled a fourth time. Ten lines to one.
- [bar] **The Rule 3b judgement rests on "This diff injects no double and removes none", which is false of its own diff: `tests/test_execution.py:1560` adds `mock.patch.object(execution.replay_module, "run", return_value=performed)`, a stub of the exact function whose `verbs=` kwarg criterion 5 asserts, so the ticket's headline new test is built on an injected double the Rule 3b enumeration does not list. Converges with the [seam] entry below.** — required —NOW. A fifth substitution added to the bar's Rule 3b judgement, naming the `execution.replay_module.run` stub, the class that checks the real thing -- `RuntimeChainTest`, live through a real door in this same ticket -- and why the stub is the point of that test rather than a shortcut in it. Nothing deferred; only the enumeration was wrong.
- [seam] **`## Seam check`'s second pass says "No double was injected and none was removed; the four substitutions the first pass and cycle 1 recorded are the same four", and `ImpactReplayTest.replay_called` adds a fifth: `mock.patch.object(execution.replay_module, "run", ...)`, off which criterion 5's only assertion reads `run.call_args.kwargs["verbs"]` rather than off the real `replay.run`. Converges with the [bar] entry above.** — required —NOW. The same correction in `## Seam check`'s second pass, which is where the sentence was written. Converged with the [bar] entry above.
- [seam] **`## Seam check`'s writer head for `READ tests.test_database::ImpactRunFixture.REASON` says `ticket 38, commit 3f2d4921`, and `git show 3f2d4921:tests/test_database.py` contains no `class ImpactRunFixture`; `git log -S 'class ImpactRunFixture'` and `git blame` both put the attribute at `37d99d6b`, ticket 39's `FEAT: stamp a pivot from the run that showed it`. A third instance of the writer-head defect cycle 1 corrected twice, inside the pass written to repair cycle 1.** — required —NOW. Rewritten to `ticket 39, commit 37d99d6b`, with the two commands that settle it and what the head used to read. Settled before writing: `git log -S 'class ImpactRunFixture' -- tests/test_database.py` returns `37d99d6b` alone, `git blame` puts `REASON` there, and `39-stamp-demonstrated-pivot.md` is that commit's ticket.
- [seam] **`## Seam check`'s first pass still reads, in bold, "**There is no `live-inputs.md` in this effort**" (line 429), while line 526 under the same `## Seam check, 2026-09-03` heading says "`live-inputs.md`'s only block is `promoted to tests.test_database.RuntimeChainTest`". Cycle 1's NOW verdict minted the file. Both passes carry the same date, both read present-tense, and nothing marks the first as superseded — at the one address `/plumbline:prove` and the next cycle's Seam axis read.** — required —NOW. The first pass's sentence put in the past tense and marked **Superseded**, naming cycle 1's finding, the mint and the second pass that reads the block. Kept as the reading it was rather than deleted, so the judgement ticket 236 measured stays legible.
- [craft] **`ImpactReplayTest.test_a_task_whose_test_states_an_impact_takes_the_impact_verbs` (`test_execution.py:1503`) promises the verbs and asserts `assertIsNotNone(subject.impact_class)` — the column only. That false name is what let cycle 1's gap sit invisible for a cycle, and this diff added the honest reader directly beneath it, so the class now carries two names claiming the impact verbs and one asserts nothing about them.** — required —NOW. Renamed to `test_a_task_whose_test_states_an_impact_carries_the_impact_class`, matching its honest sibling `test_a_task_whose_test_states_none_is_a_detection_task`. Nothing outside this ticket's own `## Bar` paste referenced the old name, and that paste is history.
- [craft] **`LiveDoorFixture.as_owner` (`test_database.py:32716`) is byte-for-byte identical to `ReplayFixture.as_owner` (`:30708`) — same signature, same `-> None`, same five lines, same `cls.owner_connection`, not one token different — so the module's count of that body is unchanged and only its owner moved. It touches neither `cls.runtime` nor `cls.connection`, so the hoist's stated reason does not apply to it at all, and cycle 1 named this exact twin.** — required —DECLINED. The module holds seven `as_owner` declarations over three different connections, four of them without the return annotation, plus `DatabaseCase.owner` and `_set_analyser` as the same ceremony spelled per purpose. Collapsing the twin means a module-wide refactor of that idiom, which no criterion in this effort asks for and which would put a 57k-line test file into a review commit. Criterion 6 asked for the hoist and the hoist landed; what stands is the module's pre-existing pattern, written down here so the next reader of `LiveDoorFixture.as_owner` does not raise it again.
- [craft] **The hoist put `rows_of` over `cls.runtime` (`test_database.py:32723`) 25 lines below the pre-existing instance method `rows` over `self.connection`, and `LiveDoorFixture` keeps `settings_for = "migrate"`, so the base class now exposes two same-signature row readers over two different roles with names that say which for neither: reaching for `rows` reads as the owner and passes, silently bypassing the RLS these cases exist to exercise. The build's own mutation proves only the loud direction (`42501`). The two-role pair already existed inside `RuntimeChainTest`; what the hoist changed is that all three `LiveDoorFixture` subclasses now inherit it.** — required —NOW. A docstring on the hoisted `rows_of` naming both roles and what `rows` will do if a case reaches for it, matching the four comment lines cycle 1 put on `SOURCE`'s two anchors. Not renamed: `rows`/`rows_of` is this module's own convention at roughly two hundred call sites, so a rename here would trade a silent role difference for a silent convention break.
- [bar] **Bar item 3's pasted grep is not what the command prints and the block asserts "Three hits": run verbatim, `grep -rn 'ticket 226\|Ticket 226' docs/specs/production-harness-v2/` prints 22 lines, 19 of them this ticket's own, elided with no `… (N lines)` marker, filenames cut to basenames, and 228/229 in the reverse of the order the command emits. This is the defect cycle 1 raised as a [bar] nit against item 3 and NOW-repaired, and whose repair paste at line 914 does carry `… (14 lines, all inside this ticket's own dated blocks: history)` — so the second block drops a marker the previous cycle put in. The substance survives: none of the 22 is a `CONSUMED BY`/`CONSUMES` seam head or a criterion `deferred to`.** — required —NOW. Re-run and re-pasted whole under the existing `## Bar` heading, with full paths and an explicit marker over this ticket's own history lines.
- [ticket] **`## Acceptance`'s "Which commit each criterion landed in" says "Criterion 3 is the only one inside this ticket's reviewed diff", now false: criteria 5 and 6 landed in `f1f1c0bd`, which carries the `(ticket 226)` marker and is this cycle's entire diff. A reader of that paragraph concludes five of six criteria have never been pinned when the true figure is three — 1, 2 and 4.** — nit —NOW. Rewritten to say that three of the six criteria have been pinned as a diff and which cycle pinned which.
- [seam] **`## Seam check`'s "The greps, and what was skipped" says of the 128 `cls.called` hits that do not reach the hoisted copy that "all but eight belong to a different branch: `ReplayFixture` declares its own `called`", naming one declaration where source has three: resolving each reading class through its bases gives 110 to `ReplayFixture.called`, 14 to `BrowserMissionTest.called` (`test_database.py:28759`) and 4 to `OfflineToolRunTest.called` (`:26504`). The eight that reach the hoisted copy is right. Converges with the [ticket] entry below.** — nit —NOW. Rewritten to three declarations with each one's count -- 110, 14 and 4 -- and how the readers were resolved.
- [ticket] **Same census, plus one citation that has never existed: "`ImpactRunFixture.id_of` and `ReplayFixture`'s are pre-existing" cites a `ReplayFixture.id_of` that source does not hold — at the fixed point `grep 'def id_of'` returns exactly two lines, `:35399` (`ImpactRunFixture`) and `:54874`, the one this diff deletes. Converges with the [seam] entry above.** — nit —NOW. Same rewrite; the `ReplayFixture.id_of` half of the sentence dropped, with `grep 'def id_of'`'s two lines at the fixed point given instead. Converged with the [seam] entry above.
- [seam] **`## Seam check`'s second-pass `READ BY` for `LiveDoorFixture.called` cites the reader as `cls.called at test_database.py:34879`, and `seam-check` §3 says record the symbol, not the line number (`cut-slices` Rule 2). This ticket already took a cycle-1 nit for citations that stopped resolving.** — nit —NOW. The line number dropped. `ValidationCommandTest.candidate` is the address.
- [bar] **Bar item 4's four tier-2 gates are recorded as `check_audit rc=0 / check_wiring rc=0 / check_baseline rc=0 / check_coverage rc=0` with no command and no output, which is characterizing where the standing bar says quote verbatim, and "each under `.venv/bin/python`" is not runnable as written: `.venv/bin/python tools/check_audit.py` exits 1 with `ModuleNotFoundError: No module named 'tools'`. Only `-m tools.check_audit` or `docs/agents/testing.md` tier 2's `PYTHONPATH=$PWD python3 -s tools/check_audit.py` works. Ticket 235's cycle required this once already.** — nit —NOW. The four gates re-run as `docs/agents/testing.md` tier 2 spells them, pasted with each one's decisive line under the existing `## Bar` heading. `.venv/bin/python tools/check_audit.py` really does die with `ModuleNotFoundError: No module named 'tools'`, so the three words that stood there cannot have been the command that ran.
- [craft] **`RuntimeChainTest.replayed`'s `**verbs` is a plural-named catch-all carrying exactly one optional keyword — `attempt` is its sole caller and passes `verbs=replay.IMPACT` — so the signature stops stating what it takes and a mistyped keyword travels to `replay.run` before it fails.** — nit —NOW. `verbs=replay.DETECTION` as a named keyword, passed through as `verbs=verbs`. `attempt` is unchanged and still hands `verbs=replay.IMPACT`.
- [craft] **`RuntimeChainTest.SOURCE = SCOPED + DECLARED` is byte-identical to the f-string it replaces, but the substitution drops the only code-level tie between the document's identity name and the `SLOT` `attempt` leases under, leaving it in a comment 42,000 lines away.** — nit —NOW. `assert f'name = "{SLOT}"' in DECLARED` beside `SLOT`, with the reason, so an edit to either one is refused at import instead of surfacing as a lease the door has no material for.

Review cycle 2 of 3 — undecided: none
