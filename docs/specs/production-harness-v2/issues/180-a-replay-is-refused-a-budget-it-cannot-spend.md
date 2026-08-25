# 180 — A replay is refused a budget it cannot spend

**What to build:** the token arms of `budget_refusal_for` stop deciding whether
a replay may run. A replay starts no model and spends no tokens; the request
arms are the ceiling it can actually reach and they are untouched.

**Blocked by:** nothing.

**Status:** resolved

- [x] **Measured.** Canary attempt six, all five graded pairs, database
      `rk2grade6` on 2026-08-24. Ticket 179 held -- every evaluation selected
      its Playbook -- and four of the five ended on:

          the registry refused this replay: the budget refuses this replay:
          program_tokens_reserved

      each losing the repeat that carried it. `attack-surface`, the one graded
      Playbook that performs no Test, was the one evaluation that passed.
- [x] **Why the number was always going to run out.** `program_capacity` in
      that database, per graded Program:

          token_budget 400000   run_tokens 40000   tokens_spent 190000 .. 403446

      `evaluation.BUDGETS` funds 400000 tokens with a 40000 per-run ceiling, and
      `evaluation.PASSES` is 12. Twelve passes at the ceiling is 480000, so a
      Program that works hard has less than one run's worth left by the time its
      Test is performed. Two markup-pair Programs finished over the whole
      budget.
- [x] **The quantity was wrong, not the ceiling.** `budget_refusal_for` refuses
      with `program_tokens_reserved` when `run_tokens > tokens_free` --
      the worst case of one more *agent* run. `rk2_replay_plan` asked it and
      refused on any answer, so a Program with 38127 tokens free refused an
      operation that would have spent none of them because it could not afford
      a 40000-token one. The comparison is between a replay and an agent run.
- [x] **What still binds.** `program_requests_reserved`,
      `lane_requests_reserved`, `budget_unreadable` and every other answer
      `budget_refusal_for` gives are unchanged, and a replay does send requests,
      so the ceiling it can reach still refuses it. The Identity lease, the
      claim status, the scope walk and the Halt are all untouched and all still
      happen before anything is sent.
- [x] **The budget is not raised.** `evaluation.BUDGETS` says "small on purpose
      and not configurable: a synthetic target on loopback that needs thousands
      of requests is a run that has stopped measuring the Playbook". That
      argument is about requests and it still holds. Raising the token budget
      would have hidden this rather than answered it.
- [x] **Covered.**
      `test_a_replay_is_not_refused_a_token_ceiling_it_cannot_spend` puts one
      Task in the state the graded Programs reach, asks the two questions in
      that one state, and asserts both answers: `budget_refusal_for` still says
      `program_tokens_reserved`, and `open_test_replay` opens anyway.

## Why

This is the fifth instrument fault in a row that reported zero without
reporting a fault, and the first one that only appears once the Programs have
done enough work to run low. Every earlier canary either never reached a Test
(175), never reached the Playbook (176, 178), lost the repeat to something else
(177) or could select nothing (179). A grading campaign whose measurement gets
thrown away in proportion to how hard the child worked is the worst shape of
the five: it is biased, not just empty.

## Notes

`evaluation.PASSES` at 12 and a 400000-token budget are two ceilings that do not
agree -- 12 runs at the stated per-run ceiling is 480000. Nothing here changes
either. After this fix a Program that exhausts its tokens stops working passes
and still performs its Test, which is the outcome both ceilings were written to
produce.
