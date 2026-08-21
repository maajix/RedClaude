# 121 — The Playbook selection funnel never closes

**What to build:** The update at the end of a Playbook run that says what the
selection produced, and a caller for the sweep that marks a live selection
stale.

**Blocked by:** nothing.

**Status:** ready-for-agent

- [ ] A finished Playbook run sets `playbook_selections.outcome`.
      `record_playbook_selection`
      (`20260823T000000Z__a_playbook_is_chosen_before_the_model_reads_it.sql:487`,
      called from `src/redkraken/execution.py:335`) inserts the row at the
      column default of `'running'` (`0032_playbooks.sql:325-326`), and nothing
      in the tree ever updates it. The migration that froze the rest of the row
      says in as many words what is supposed to move: "`outcome` and
      `went_stale_at` are what a run updates" (`20260823T000000Z...:460-463`),
      and `enforce_playbook_selection_frozen` (`:464-478`) exists to allow
      exactly those two columns to change.
- [ ] `'exhausted'` is written where the run produced nothing, because that
      value is load-bearing rather than cosmetic. `playbook_candidates` drops a
      Playbook for a subject with the reason `'exhausted'` when a prior
      selection on the same `(program, subject, playbook)` carries that outcome
      (`20260823T000000Z...:291-296`, and the same test at
      `0032_playbooks.sql:420`). With nothing writing it, a Playbook that has
      already been run against a subject and found nothing is offered again on
      every pass, forever.
- [ ] `mark_stale_selections()` (`0032_playbooks.sql:561-570`) acquires a
      caller. It is the only writer of `went_stale_at`, and it has none in
      `src/`. Its own prose (`:556-560`) describes it as a sweep: "the sweep
      records the fact and the next pass excludes it; the live run is
      untouched". There is no sweep.
- [ ] The two constraints that are decoration today become falsifiable:
      `playbook_selections_outcome_check`'s `'produced'` and `'exhausted'` arms
      (`0032:326`), and `playbook_selections_dropped_has_no_outcome`
      (`0032:331-332`), which asserts that a dropped row stays at `'running'`
      and cannot fail while every row stays at `'running'`.
- [ ] `check_playbook_integrity`'s `stale_during_run` warning
      (`0032_playbooks.sql:625`, re-issued at
      `20260823T000000Z...:710-713`) can fire. It reports "a live mission whose
      playbook went stale under it" by asking for
      `went_stale_at IS NOT NULL AND outcome = 'running'`, which is
      unsatisfiable while nothing writes `went_stale_at`.

## Why

`docs/research/wiring/23-database-wiring.md` section 1.3(e): "the playbook
funnel never closes". The selection half of the design is complete -- candidates
are ranked, the choice is frozen, the drop reasons are recorded -- and the
outcome half, which is what makes the next selection different from the last
one, has no writer at all.

The cost is not bookkeeping. Playbook selection is how the harness decides what
to try next against a subject, and `exhausted` is the only memory in it. Without
that write, a hunt re-offers the same Playbook against the same subject for as
long as it runs, and the model's own record of what it already tried is the
transcript rather than the database.
