# 182 — The refusal preview asks half the bar

**What to build:** `hypothesis_transition_refusal` asks the playbook evidence
bar as well as the 007 rule. Both refuse the write it is a preview of, so a
preview that asks one of them is a preview that returns NULL for a transition
the other raises on.

**Blocked by:** nothing.

**Status:** resolved

- [x] **Measured.** Canary attempt eight, database `rk2grade8` on 2026-08-25.
      The first evaluation, `attack-surface` against `artifact-exposure-pair`,
      exited 3 on:

          what this replay recorded was refused: playbook
          playbooks/attack-surface/playbook.md requires 1 x (role=control,
          kind=response_differential) for supported, found 0

      The other four evaluations exited 9 without doing any work at all:

          integrity_failed: 2 problem(s):
          (replay_without_run,TR4,"closed as error and wrote no Test run");
          (replay_left_testing,H1,"a replay of TST1 closed and the claim is
          still testing")

      `rk run` reads `check_test_replays` before every pass, so one Program that
      could not reach `supported` stopped every Program in the database.
- [x] **The mechanism, end to end.** TR4 performed its three actions and the
      control leg answered 404 on record as R6. `close_test_replay` reached its
      settling step, which does not attempt the transition -- its own comment
      says "Asked, not attempted. What comes back is a verdict about the
      conclusion and not an error in this transaction" -- and asked
      `hypothesis_transition_refusal`. The answer was NULL.
      `enforce_playbook_evidence` then raised on the insert. That aborted the
      whole close: no `test_runs` row, `tool_runs` left `running`, claim left
      `testing`. `replay._abandon` re-ran the same refusing statement, got the
      same refusal, and left the row open; `resume_program` on the next pass
      closed it as `error`. Those are exactly the two problems
      `check_test_replays` names.
- [x] **Why the preview was half.** 0032 states the relationship outright: the
      playbook trigger is "named to sort before enforce_hypothesis_transition
      ... the two checks are a conjunction". A preview of a conjunction has to
      ask both conjuncts. This one asked one, and its own COMMENT is honest
      about which: "why 007 would refuse this hypothesis transition".
- [x] **The arm is the trigger's own.** It calls `playbook_evidence_unmet`,
      which is what `enforce_playbook_evidence` calls, and formats the string
      that trigger formats. It is placed first in the body because that trigger
      fires first, so the answer is the sentence a writer would actually be
      given. No bar, no trigger, no Playbook row and no phrasing changes.
- [x] **Nothing that was admitted stops being admitted.** The new arm returns
      non-NULL only where `playbook_evidence_unmet` returns a row, which is
      exactly where the write would have raised. What changes is that a caller
      is now told, so `close_test_replay` can do what it was already written to
      do with the answer.
- [x] **Covered.** `test_the_refusal_preview_asks_the_playbook_bar_as_well`
      puts the claim of `settle_one_that_holds_and_cannot_say_so` under
      `attack-surface`'s shipped bar with one `playbook_selections` row, and
      asserts the preview answers with `enforce_playbook_evidence`'s own
      sentence rather than NULL.

## Why

`settle_one_that_holds_and_cannot_say_so` already wrote down the invariant this
broke: "The state this produces is the one that has to be closeable. A refusal
raised out of the settling would take the Test run and its Receipts down with it
and leave the Tool run running, which is the one state no check reports and no
retry can leave." It held for the 007 half of the bar and was never asked about
the other half.

This is the seventh instrument fault in a row, and the first that is not merely
biased or empty but contagious: the wreck one Program leaves is a Program-wide
integrity failure, and `rk run` refuses on it, so every later Program in the
same database does no work at all. Canary eight measured one evaluation and
lost four.

## Notes

`attack-surface` still cannot settle a claim as `supported` from a control leg
that produced no `response_differential`, and nothing here tries to make it.
After this fix that outcome is an `inconclusive` Test run whose transition
rationale says why, which is a measurement rather than an outage.
