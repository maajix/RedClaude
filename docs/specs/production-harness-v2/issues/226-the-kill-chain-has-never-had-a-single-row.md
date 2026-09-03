# 226 — The kill chain analysis has never held a single row

**What to build:** The two callers that put a run in front of a validated
Finding's impact, so that `pivot_stamps` and `chains` stop being empty tables
with a full function corpus above them.

**Blocked by:** nothing. 103 built the three MCP wrappers; 221 built the first
`conclude` Task that reaches a validated Finding at all.

**Status:** claimed

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

**Touches:** `tests/test_database.py`. No source file joined it: running walls
1 and 2 together for the first time found nothing wrong with either. Two more
files came in with `## Build findings, 2026-09-03`'s NOW repair --
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
- [ ] The runtime's own `verbs=` selection is asserted where it lives.
      `execution.py:2724` is the only runtime site and nothing reads it: added
      by cycle 1 for the [ticket] finding that narrowing it to `DETECTION`
      leaves the whole tree green. One assertion over `_replay`'s call kwargs
      in `tests.test_execution.ImpactReplayTest`, watched failing under that
      narrowing first, and `RuntimeChainTest.attempt`'s hand-copy of the
      expression dropped to `verbs=replay.IMPACT` so the rule has two readers
      rather than three spellings.
- [ ] `RuntimeChainTest` inherits or references what it copied.
      Added by cycle 1 for the [craft] finding: the nine members that touch
      neither a Receipt nor a door are not this case's work. `called`,
      `as_owner` and `rows_of` hoisted onto `LiveDoorFixture` with
      `ValidationCommandTest.called` deleted so both live-door subclasses
      inherit one copy; `ImpactRunFixture.REASON`,
      `ValidationCommandTest.TITLE`, `ValidatedFindingFixture`'s six statement
      constants and `DECLARED` referenced rather than re-spelled; `id_of` and
      the third `replay.run` spelling dropped with them; only the door-shaped
      members kept local.

**Which commit each criterion landed in, recorded by cycle 1.** Criterion 3 is
the only one inside this ticket's reviewed diff. Criteria 1, 2 and 4 landed in
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

**There is no `live-inputs.md` in this effort**, which ticket 236 measured one
day earlier and recorded rather than created. Recorded again rather than
minted: the file's own rule is that the walking skeleton's session creates it,
this effort is 236 tickets past that, and a file starting at ticket 226 would
carry one block and read as though the 225 before it had no live inputs.

**Rule 3b.** No double was injected. The one thing this case fakes is the
address -- `LiveDoorFixture.dial` puts every authorised name on the loopback
port, for `ProxyEgressTest`'s reason that `127.0.0.1` can never be a Program's
scope -- so what is faked is where the socket goes and nothing about the
decision that authorised it. The Identity material is real sealed ciphertext,
opened by the door under the installation root.

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
