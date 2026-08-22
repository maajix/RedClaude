# 152 — A Test is authored and nothing performs it

**What to build:** The caller that performs a stored Test, or the Task kind that
gets one dispatched.

**Blocked by:** nothing.

**Status:** resolved

- [x] **The measurement is in the ticket.** `rk2hunt11`, 2026-08-22, the first
      Program in this tree to author a Test. Three hunts, three Tests, one per
      claim:

      ```
      label|claim
      TST1 |H2
      TST2 |H3
      TST3 |H1
      ```

      and nothing performed any of them:

      ```
      test_replays  |0
      replay_actions|0
      findings      |0
      ```

      All three claims are still `testable`. A claim reaches `supported` through
      a replay, a Finding rests on a supported claim, and a `validate` Task is
      minted from a Finding -- so the whole tail of the pipeline is downstream
      of a step nothing takes.

      `replay.run` has exactly one caller, `cli.py:2705`, behind
      `rk test replay`. Run as an operator against a finished hunt it refuses,
      correctly:

      ```
      the registry refused this replay: agent run AR10 has already ended
      ```

      So a replay must happen while an Agent run is open, and no Agent run this
      harness opens ever performs one. The operator command cannot stand in for
      the missing step, because by the time an operator can type it every run it
      could attribute to has ended.

- [x] **The decision is made rather than assumed.** Two shapes, and they are
      not the same ticket: a `hunt` run performs the Test it just authored
      inside its own open run, or the scheduler mints a Task whose kind is
      dispatched to a role that replays. The second is what `validate` looks
      like for Findings and is the one the lane machinery already fits.

- [x] **Checked by something that would go red.** A Test on file with no replay
      is the state this ticket describes; whatever is built, that state must
      stop being reachable through a full pass.

## Why

This is the last structural link. Tickets 139, 144, 140, 147 and 151 together
turned a harness that proposed nothing into one that reaches a Test on every
hunt -- three for three in `rk2hunt11`. What is on the other side of this one is
the rest of the pipeline: `supported`, the Finding, the validation Task and the
report.

It does not hinder hunting. Recon runs, claims are graded, hunts are dispatched
and Tests are authored, all without an operator. What it hinders is finishing.

## What was built

The second shape, which is the one the lane machinery already fits: `perform`
is a Task kind like the other five, and the claim that opens it is the Agent
run the replay is attributed to.

**The role.** `performer`, a renderer -- the second one after `reporter`,
because a replay walks a specification a hunt already authored and there is
nothing in it for a model to decide. It holds no model, no turn and no tool,
which the schema enforces twice: `roles_renderer_runs_no_model` requires
'none'/'none' and `agent_runs_renderer_spends_nothing` refuses a run of it that
reports a token.

**The kind.** A kind needs four things to exist in this schema, and the
migration writes all four because each has a check that would have caught a
missing one: the `role_task_kinds` row (`check_role_kind_mapping` (a)), the
default lane (the same check, (d)), the ranking priors
(`check_scheduler_closure` `kind_has_no_cost_prior`) and an entry in each of
the three lane quota profiles (`check_lane_quota_closure`
`profile_missing_kind`). The lane and the priors both live on tables that are
immutable after 037 and 023, so both writes disable the trigger and put it back
`ENABLE ALWAYS` -- the shape 20260815 used for the same reason.

**The Task names the Test.** `tasks.test_id`, keyed
`(test_id, program_id) -> tests(id, program_id)` and NO ACTION, because 017
refuses a cross-table key that does not carry the Program and 016 refuses an
unregistered cascade. `tasks_live_dedup_idx` grew with it.

**When one is ready.** `ready_for` gained a `perform` arm with three
conditions, and the third -- a Test that has been replayed is not ready to be
replayed -- is what makes the state this ticket describes unreachable rather
than merely unlikely.

**What closes it.** `task_result_accepted` gained a third arm: a `test_runs`
row off the replay lane. Without it every `perform` Task would have gone back to
the queue with an attempt spent and been abandoned as `attempts_exhausted` after
the third -- having performed its Test three times.

**The derivation.** `rk2_test_performance_frontier(uuid)` and
`derive_test_performances()`, called from `rank_pass` at step (3d), capped by
`scheduler_weights.max_performances_derived_per_pass`. The frontier excludes an
impact Test (`open_test_replay` refuses one by name), a superseded Test, a Test
already replayed, and a Test any `perform` Task names in any status.

**The caller.** `execution.Slice._replay`, reached by a branch at the top of
`_run` before every check that is about a dispatch. No packet, no Playbook, no
capability minted here and no child: `replay.run` opens its own Tool run and
mints its own capability inside the transaction that opens it. The Task's
ending is the Test run rather than this report -- a Test that settled nothing
reports `inconclusive` and fails, correctly, while the Task that performed it is
done.

## The test that would go red

`tests.test_database.TestPerformanceTest` -- one Test that must become work,
two that must not (an impact Test, a performed one) with the one beside them
that must, and a ceiling that defers rather than drops. Reverting the
derivation makes `performances_derived` 0 and the first case red.

`tests.test_execution.PerformTest` -- the seam. Reverting the branch in `_run`
starts a child for a `perform` Task and `run.call_count` is 0.

## Follow-up found in the live run

The first Program to carry `perform` Tasks abandoned both of them before either
could be offered. `novelty_for` answers per kind and had five arms; a `perform`
Task fell past all of them to the closing `RETURN 0`, and `cancel_reason_for`
ends with the general rule that nothing left to learn is nothing worth running.

```
label|status   |novelty|cancel  |ready|claimable
T5   |abandoned|0      |answered|     |not_pending
T6   |pending  |0      |answered|     |answered
```

Migration `20261015T000000Z__a_performance_is_novel_until_it_is_performed.sql`
adds the arm, shaped like `validate`'s: a Test nobody has walked is the whole
of what is not yet known about it. Measured again on the same rows afterwards,
novelty 1 and no refusal, and the next lap claimed T6 as AR10.

`tests/test_database.py::TestPerformanceTest::test_the_derived_task_survives_the_pass_that_follows_it`
is the test that would go red.
