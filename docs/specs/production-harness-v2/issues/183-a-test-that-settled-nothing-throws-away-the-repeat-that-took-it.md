# 183 — A Test that settled nothing throws away the repeat that took it

**What to build:** the `perform` lane stops carrying a settled Test's verdict
into the Program pass as a violation. `replay._conclude` spends
`INVALID_CONFIGURATION` on a Test that settled `inconclusive` or whose
conclusion the epistemic machine withheld, which is right for `rk test replay`
and wrong for the Task that performed it.

**Blocked by:** nothing.

**Status:** resolved

- [x] **Measured.** Canary attempt nine, database `rk2grade9` on 2026-08-25.
      The first evaluation, `attack-surface` against `artifact-exposure-pair`,
      exited 3 carrying exactly one violation:

          invalid_configuration  test_run
          TST1 holds over 3 action(s); the claim is inconclusive, because
          playbook playbooks/attack-surface/playbook.md requires 1 x
          (role=control, kind=response_differential) for supported, found 0

      Nothing else in that database is wrong. `check_test_replays()` reports 0
      problems, 13 Tasks are `done`, and `test_runs` holds both shapes the
      evaluation produced: `TST1 refutes` with `H1 refuted`, and `TST1 holds`
      with `H1 inconclusive`. The first did not fail a pass and the second did.
- [x] **What the verdict then cost.** The pass ledger read:

          ok    passes  repeat 0 (vulnerable) worked 3 pass(es), nothing_to_execute
          ok    passes  repeat 0 (secure)     worked 5 pass(es), nothing_to_execute
          ok    repeat  repeat 0 filed as 01a03782-... from 2 Program(s)
          ok    passes  repeat 1 (vulnerable) worked 4 pass(es), stopped on refused
          ok    closure T4 is done; 1 run(s), 0 tool run(s) and 0 lease(s) closed
          FAIL  repeat  repeat 1 did not complete; nothing was filed for it

      `stopped on refused` is that same violation ending the pass loop, and
      `evaluation._repeat` then refuses the repeat outright. The Task was done
      on the line above it.
- [x] **The code was claiming the wrong thing.** `INVALID_CONFIGURATION` says
      an operator configured this lane wrongly. What happened is that a Test ran,
      the door let it through, three actions were recorded and the playbook bar
      the harness ships would not admit `supported` from a control leg that
      produced no `response_differential`. Ticket 182 made that outcome an
      `inconclusive` Test run rather than a rolled-back close, and wrote down
      what it is: "a measurement rather than an outage". Nothing was left to fix.
- [x] **The fix is the lane's own contract.** `_replay`'s docstring already
      states it: "The Task's ending is the Test run, not this report. A Test that
      ran and settled nothing reports `inconclusive` and fails -- correctly,
      because somebody has to run it again -- while the Task that performed it is
      done." `settled = performed.facts.get("test_run") is not None` was already
      computed three lines below to decide `stop_reason`; it is now computed
      first and decides this too.
- [x] **`rk test replay` is unchanged.** `_conclude` still fails, still spends
      `INVALID_CONFIGURATION` and still exits 3 for an operator who asked for a
      Test and got no answer. Only the pass that performed the Task inside its
      own claim demotes it, and only when a `test_runs` row exists.
- [x] **Nothing quiet is introduced.** The sentence is demoted, not dropped: it
      is recorded as a held `run` assertion carrying the same detail, so the
      transition rationale an operator reads is still in the pass ledger and
      still on `facts["replay"]`, where the replay's own report keeps it as a
      violation. A replay that died before settling keeps every violation it
      raised, including the `test_run` one `_abandon` writes when
      `close_test_replay` was itself refused -- `settled` is false on that path,
      because the transaction that would have written the Test run rolled back.
- [x] **The pair moves together.** `_conclude` is the only writer of a `run`
      assertion in `replay.py` and, once a Test run exists, the only writer of a
      `test_run` violation, so demoting on `name == "run"` and filtering on
      `source == "test_run"` name the same one event. No assertion is left
      without the violation behind it, which is the invariant `Ledger` is
      documented to keep.

## Why

This is the same fault as ticket 177 one layer up. There, the runtime's Ledger
spent its word for "this run cannot be trusted" on a door refusing a verb, which
is the boundary working. Here it spends it on a playbook bar refusing a
conclusion, which is the epistemic machine working. Both are ordinary events
over 1650 runs, both were voiding measurements, and in both cases the repeat
that was thrown away included a variant that had already finished.

The shape it produces is worse than an outage, because it is silent and biased:
a campaign that discards every repeat in which a Test could not reach its
conclusion measures only the runs where every Test concluded, and then reports
the result as if it had measured all of them.

## Notes

`attack-surface` still cannot settle a claim as `supported` from a control leg
that produced no `response_differential`, and nothing here tries to make it.
That is ticket 84's measurement to report, not a fault to fix.

Ticket 180's disagreement is unchanged and still not fixed here:
`evaluation.PASSES` is 12 and a Program's token budget is 400000, so twelve
passes at the 40000-token worst case would need 480000.
