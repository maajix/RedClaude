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
`redkraken.replay::run`'s `verbs=` parameter, written by wall 2;
`open_impact_task`, written by wall 1.

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
       READ BY  check_kill_chains() arm (h), reading FROM chains -- run in this
                pass over a Program that holds one; and
                rk2_chain_unlock_frontier, reading FROM chains
WROTE  65-prove-first-hunt-release-candidate.md's Blocked by entry for 233
       READ BY  tools/check_audit.py, reading the release-outcome closure over
                RELEASE_OUTCOME = 65
WROTE  tests/test_audit.py's frozen report line
       READ BY  operator, via uv run python -m unittest tests.test_audit

READ   redkraken.replay::_downstream
       WRITTEN BY  ticket 103, status resolved
READ   redkraken.replay::run's verbs= parameter, and redkraken.replay::IMPACT
       WRITTEN BY  ticket 226 wall 2, commit 685d860f
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
4. **Existing tests still pass, none skipped, deleted or weakened.**

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

**Judgement, Rule 3b.** No double was injected; `## Seam check` says what the
one faked value is -- the dialled address -- and why faking it is not faking the
decision.
