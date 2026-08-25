# 184 — The last budget reason still throws away the work

**What to build:** `claim_task()` ends an unnamed claim on `unaffordable` as it
already does on the four reservation reasons. Ticket 181 left this one raising
on two readings, and neither survived the measurement.

**Blocked by:** nothing.

**Status:** resolved

- [x] **Measured.** Canary attempt nine, database `rk2grade9` on 2026-08-25.
      The second evaluation, `object-ownership` against
      `object-ownership-pair`, filed repeats 0 and 1 with both variants -- the
      furthest any canary has reached -- and then exited 3:

          ok    passes  repeat 2 (vulnerable) worked 7 pass(es), nothing_to_execute
          ok    passes  repeat 2 (secure)     worked 8 pass(es), stopped on refused
          FAIL  repeat  repeat 2 (secure) did not complete; nothing was filed for it

          invalid_configuration  database
          the claim against a 1-Task slate failed: 23514: task T7 is no longer
          claimable: unaffordable | PL/pgSQL function claim_task(text) line 113

      The verdict line above the failure read `pass`, which the invocation
      could not stand behind on two of three repeats.
- [x] **It is ticket 181's fault by its fifth door.** Everything 181 established
      about the mechanism holds unchanged: `rank_candidates` selects with
      `claimable_for(t, w) IS NULL`, so the entry was affordable when the slate
      was written, and the orchestrator's own chooser run spends the margin
      between the slate and the claim. Only the name the refusal comes back
      under differs.
- [x] **The first reading was about a cheaper Task.** 181's comment argued that
      `unaffordable` "is a statement about one Task being too expensive rather
      than about the Program having no room, and a cheaper Task may still be
      claimable". That Task is not reachable from this branch -- a Task has
      already been picked and the walk that could go looking is the `ELSE` -- and
      it does not need to be, because `SlateClaimTest`'s
      `test_an_unaffordable_task_is_not_offered` holds that an unaffordable Task
      is never written into a slate at all. The only way to reach the arm is the
      race, and a Program in that state has no room.
- [x] **The second reading was about a test, and was not checked.**
      `test_a_task_the_budget_no_longer_covers_is_refused_after_being_offered`
      arranges its refusal with `SELECT claim_task($1)`, naming the Task. The
      `p_task_label IS NULL` clause ticket 181 added in its own second revision
      already excludes every named claim, so the exclusion of `unaffordable` was
      protecting a test that did not need protecting. It still asserts its raise
      and still gets it, and `test_a_named_claim_still_raises_on_the_cost_it_cannot_meet`
      now says so from the list's own side.
- [x] **Nothing that raised for a reason of its own stops raising.**
      `budget_unreadable` keeps its exception: a capacity that cannot be read is
      a broken Program rather than a spent one and must not report an idle
      queue. Every named claim keeps its exception on every reason. The
      predicate is untouched -- `claimable_for` still refuses and no Task becomes
      claimable that was not.
- [x] **The pick survives.** `arrange_outgrown` asserts the `task_picks` row is
      still there and unconsumed, and that the claim opened no Agent run and
      moved no Task, which is what separates "there was nothing to claim" from
      "something was claimed and then given up on".
- [x] **Covered.** `test_a_task_this_ones_cost_outgrew_ends_an_unnamed_claim_too`
      reaches `unaffordable` after a pick and claims with no argument, which is
      what `execution.CLAIM` does and what nothing in the suite did before.

## Why

Ticket 181 fixed four of the five answers a spent budget gives and reasoned its
way out of the fifth. The reasoning was written down, which is why it could be
checked, and one measurement was enough to check it: the runtime never names a
Task, so the clause that made the excluded test safe made the exclusion
pointless.

The cost was the same as 181's. `evaluation._repeat` reads a violation as a
repeat that did not complete and discards every variant of it, including the one
that had already finished. Two of three repeats survived here, which is better
than 181 and still not a measurement.

## Notes

`arrange_reserved`'s docstring said `unaffordable` "still raises". It no longer
does on an unnamed claim, so the sentence is corrected there rather than left to
mislead the next reader of the arm beside it.

Ticket 180's disagreement is unchanged and still not fixed here:
`evaluation.PASSES` is 12 and a Program's token budget is 400000, so twelve
passes at the 40000-token worst case would need 480000.
