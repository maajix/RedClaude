# 175 — An evaluation works a Program once and stops before the Playbook

**What to build:** `rk playbook evaluate` drives the Program the way an
engagement does, instead of performing one pass and filing what recon left
behind. Fixed here, in `_repeat`, with a pass ceiling; this ticket records the
measurement that found it and what it means for every grade taken before it.

**Blocked by:** nothing.

**Status:** resolved

- [x] **The evaluation performed exactly one pass per Program.**
      `_repeat` called `program.run` once per variant inside its `served` block
      (`src/redkraken/evaluation.py`, before this change) and never read the
      stop reason back. `program._report`'s own docstring calls the stop reason
      "the one word a driver loop reads", so `rk run` is one pass by design and
      the loop belongs to the caller. This caller had none.
- [x] **One pass cannot reach a Playbook.** A Program opens with its configured
      recon Task (`20260831T000000Z`), the recon run proposes, and
      `execution._promote` promotes. Ticket 140's migration
      (`20261012T000000Z__a_proposed_claim_becomes_work.sql`) is what moves a
      claim `proposed -> testable` and derives the hunt Task from it, and it
      runs in the ranking pass -- the *next* pass. A Playbook is selected when
      that hunt Task is dispatched. So a Program worked once ends with a
      `proposed` claim, no hunt Task, no selection and no Test.
- [x] **Measured, not reasoned.** One canary evaluation of
      `playbooks/attack-surface/playbook.md` against `artifact-exposure-pair`
      on the door route, in database `rk2grade` on 2026-08-24, ran 6 Programs
      to completion with `ok: true` and `exit_code: 0`. What it left behind:

          tasks                 6 recon, all done, 0 hunt
          playbook_selections   0 rows
          hypotheses            3, every one still `proposed`
          findings              0
          playbook_test_runs    3 rows, claims 0, discriminating_tp 0

      The ledger line that names the stage it stopped at is
      `PR1 is promoted: 4 Observation(s) canonical, 0 Task(s) opened, 4 refused`,
      repeated once per Program.
- [x] **What it would have cost.** `playbook_test_verdict` fails a Playbook
      whose median discriminating finding is below 1. Every fixture would have
      filed `discriminating_tp = 0`, so the whole 1650-run campaign would have
      returned five `fail` verdicts and measured this bug -- the same shape
      ticket 166 was found in, one stage earlier.
- [x] **The fix, and the two things it had to keep true.** `_repeat` now works
      one Program until its Slate is empty, its pass is refused, a human is
      being asked, or `evaluation.PASSES` (12) is spent. The loop is inside the
      `served` block, because the fixture has to keep answering on the port the
      Program recorded; and `_graded_work` marks the Program and records the
      fixture address on the first pass only, because `open_fixture_address`
      writes a row rather than merging one and a second write of an unchanged
      address would refuse a pass over nothing.
- [x] **The ceiling is not the budget.** `[budgets]` in `evaluation.BUDGETS`
      bounds a graded Program at 400000 tokens and 200 requests and is what
      actually stops a talkative Program. `PASSES` bounds how many times the
      harness is willing to ask, because `chooser_cut_off` and `task_attempted`
      both mean "there is more to do" and neither ever ends a loop by itself.

## Why

Ticket 84 is the campaign this command exists for, and ticket 78 put the door
route under it so a graded run would produce the evidence a real engagement
produces. Both are about making the measurement faithful. A harness that runs
recon and files the zeroes is faithful to nothing: it produces a number that
reads exactly like a Playbook which found nothing, which is the same failure
mode ticket 161 named for `nothing_to_execute` and the same one ticket 142 named
for a silently discarded suggestion.

The canary is what caught it, and that is what a canary is for. Thirty runs were
spent to learn that the instrument was not measuring, which is thirty runs well
spent against sixteen hundred and fifty that would not have been.

## Notes

The canary database `rk2grade` is kept, not dropped. It holds the six Programs
and the three rows this ticket is evidence from, and a measurement marked
invalid still has to be readable.

Nothing here widens what a graded Program may do. The passes are the same
`program.run` an operator drives by hand, against the same Program, under the
same budgets, through the same door.
