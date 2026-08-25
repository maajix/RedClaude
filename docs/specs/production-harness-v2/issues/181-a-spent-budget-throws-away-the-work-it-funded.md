# 181 — A spent budget throws away the work it funded

**What to build:** `claim_task` answers NULL when the Task a pick names is
refused for capacity, the way the same function already answers NULL when the
slate walk finds nothing claimable. A Program that has spent its budget is an
idle queue, not a broken pass.

**Blocked by:** nothing.

**Status:** resolved

- [x] **Measured.** Canary attempt seven, database `rk2grade7` on 2026-08-25.
      `browser-script` against `markup-pair` exited 3. Repeat 1 of the secure
      variant was worked nine passes and stopped on `refused`:

          the claim against a 1-Task slate failed: 23514: task T7 is no longer
          claimable: program_tokens_reserved | PL/pgSQL function
          claim_task(text) line 73 at RAISE

      `evaluation._repeat` reads a violation as a repeat that did not complete,
      so it filed nothing for repeat 1, never ran repeat 2, and the Playbook's
      verdict came back `untested: 54 fixture(s) in the binding have no run at
      this text`.
- [x] **Why that Program and not the others.** `program_capacity` in the same
      database, per graded Program:

          markup-pair-secure-1        spent 366321   free 33679   runs 17
          markup-pair-vulnerable-1    spent 371054   free 28946   runs 16
          object-ownership (worst)    spent 320792   free 79208   runs 12
          artifact-exposure (worst)   spent 226238   free 173762  runs 10

      `run_tokens` is 40000 throughout. Nothing here is peculiar to one run: any
      Program worked down to within one run's worst case with a pick
      outstanding trips it, and `browser-script` is the graded Playbook that
      spends the most. `markup-pair-secure-0` ended on 33635 free and did not
      trip, because it stopped on `nothing_to_execute` before attempting another
      claim.
- [x] **The slate and the claim never disagreed.** `rank_candidates` selects
      with `claimable_for(t, w) IS NULL`, so T7 was affordable when it was
      offered. Between the offer and the claim the orchestrator ran its chooser,
      and that is an Agent run that spends tokens like any other -- the log
      records `AR17 answered chosen (T7) after 1 pick(s)` immediately before the
      refusal. The margin the slate saw is spent by the act of choosing from it.
- [x] **The rule was already written, one branch away.** The ELSE branch of
      `claim_task`, which walks the slate when there is no pick, says: "Nothing
      claimable, including nothing offered. NULL rather than a refusal: an empty
      slate is the queue being idle... A raise here would make 'nothing to do'
      indistinguishable from 'the world moved under a choice'." The pick branch
      raises for both. `unaffordable`, `program_tokens_reserved`,
      `program_requests_reserved`, `lane_tokens_reserved` and
      `lane_requests_reserved` are the queue being idle, and now return NULL
      from the pick branch too.
- [x] **Nothing is hidden by the NULL.** `scheduler_idle_report()` is how the
      runtime reads an idle queue and it names the predicate that refused each
      Task, so the reason survives exactly as it does for the slate walk.
      `execution._claim` turns a NULL into `N Task(s) offered and none of them
      was claimable`, the pass stops on `nothing_to_execute`, and
      `evaluation._repeat` already treats that stop reason as a Program that
      finished.
- [x] **Only when the caller named no Task.** `claim_task(p_task_label)` is an
      operator or a test asking for one Task in particular, and NULL there would
      answer a question that was not asked.
      `BudgetReservationTest.arrange_capped` names its Task for exactly that
      reason -- "so the refusal is about this Task and not about a slate that
      ran out of entries" -- and reads the raise back. The runtime never names
      one: `execution.CLAIM` is `SELECT claim_task()`, which is the path this
      ticket measured and the only path the ELSE branch's NULL was reachable
      from.
- [x] **`budget_unreadable` keeps the raise.** `budget_refusal_for` returns it
      when no `program_capacity` row can be read at all, and calls that defence
      rather than a path. A Program that cannot be priced is broken, not spent,
      and must not report an idle queue.
- [x] **Covered.** `test_a_spent_token_budget_ends_the_claim_without_raising`
      puts one Task under a pick in the state the graded Programs reach, asserts
      `claimable_for` still names `program_tokens_reserved`, and asserts
      `claim_task` answers NULL rather than raising.

## Why

Ticket 180 fixed the replay lane and closed with a prediction: "After this fix a
Program that exhausts its tokens stops working passes and still performs its
Test." Half of that was right. The replay is no longer refused, but the pass
loop that gets it there does not stop -- it raises out of `claim_task` and takes
the repeat with it.

This is the sixth instrument fault in a row that reported zero without reporting
a fault, and it shares the shape ticket 180 called the worst of them: the
measurement is thrown away in proportion to how hard the child worked, so what
survives is biased rather than merely sparse.

## Notes

`evaluation.PASSES` at 12 and a 400000-token budget still do not agree, and
still nothing here changes either. `evaluation.BUDGETS`' own comment says the
token budget is "the real bound" and `PASSES` is "the bound on the number of
times the harness is willing to ask". After this fix that is what happens: the
budget binds first, the Program stops, and what it filed is kept.
