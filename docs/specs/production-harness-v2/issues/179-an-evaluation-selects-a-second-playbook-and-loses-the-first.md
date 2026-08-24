# 179 — An evaluation selects a second Playbook and loses the first

**What to build:** an evaluation Program records the Playbook it grades and no
other. The trigger that refuses a foreign Playbook refuses by raising, and the
raise takes the graded row down with it.

**Blocked by:** nothing.

**Status:** resolved

- [x] **Measured.** Canary attempt five, all five graded pairs, database
      `rk2grade5` on 2026-08-24. One evaluation passed and four ended on the
      same refusal:

          no Playbook could be selected for T3: 23514: program 01a0358d-... evaluates
          playbooks/object-ownership/playbook.md, so it cannot also select
          playbooks/attack-surface/playbook.md

      `playbook_selections` in that database holds four rows, every one of them
      `attack-surface` inside `attack-surface`'s own evaluation. The other four
      evaluations filed nothing at all.
- [x] **The mechanism, and why both halves are needed.**
      `record_playbook_selection` (20260823T000000Z) writes every row
      `select_playbooks` decided -- kept rows and dropped rows -- in one
      `INSERT ... SELECT`. `a_evaluation_program_runs_one_playbook`
      (20260824T000000Z) is a `BEFORE INSERT` trigger on the same table that
      raises when an evaluation Program records a Playbook other than the one
      it grades. A raise aborts the statement, so the row for the graded
      Playbook, decided in the same statement, never lands either.
- [x] **The trigger is right and is in the wrong place to be the decision.**
      A claim is attributed to a Playbook through `(program, subject, class)`,
      which is exact only while an evaluation Program runs one Playbook, so
      nothing about what may be stored changes here. What changes is that the
      filter is now written where the rows are chosen, and the trigger goes back
      to being a backstop that ordinary input does not reach.
- [x] **One clause, and only inside an evaluation.**

          WHERE s.playbook_id = coalesce(
                    (SELECT e.playbook_id FROM evaluation_programs e
                      WHERE e.program_id = v_program),
                    s.playbook_id)

      A real Program has no `evaluation_programs` row, the coalesce falls
      through to the candidate's own id, and every candidate is recorded exactly
      as before. Fewer rows are written, never more.
- [x] **What it cannot hide.** `select_playbooks` returns every Playbook the
      subject's facts matched exactly once, kept or dropped, so the graded
      Playbook is in the set whenever the subject matched it at all. If the
      subject did not match it, this call records nothing and the run reports
      the same "kept nothing" it reports today, with the near misses beside it.
- [x] **Covered.**
      `test_an_evaluation_records_the_playbook_it_grades_and_no_other` gives a
      second Playbook the graded one's own triggers, runs the selection on the
      evaluation Task, and asserts one row.
      `test_an_evaluation_program_cannot_also_select_another_playbook` is
      unchanged and still proves the trigger refuses a direct insert.

## Why

Four canaries in a row found the instrument reporting zero without reporting a
fault, and this is the fifth. It is the first one that could not have been seen
before now: every earlier canary graded `attack-surface` alone, so the Program
under evaluation and the Playbook its subject also matched were the same
Playbook and the trigger never fired. Grading five pairs is what put a second
Playbook in front of it.

## Notes

Ticket 178 did not cause this and does not depend on it. The trigger fires on
any row for a foreign Playbook, kept or dropped, and
`record_playbook_selection` has written dropped rows since it was written -- so
an evaluation whose subject matched a second Playbook would have aborted before
178 as well. What 178 changed is that `attack-surface` is now selectable at all,
which is what made it the second Playbook in four other evaluations.

The verdict word in `grading/*/lane*.ndjson` is scraped out of the log with a
grep and read `pass` for all five runs of canary five, including the four that
filed nothing. The `rc` column is the reliable one and read 3 for those four.
That scrape is cosmetic and is not fixed here.
