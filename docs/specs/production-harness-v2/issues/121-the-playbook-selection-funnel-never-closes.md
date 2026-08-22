# 121 — The Playbook selection funnel never closes

**What to build:** The update at the end of a Playbook run that says what the
selection produced, and a caller for the sweep that marks a live selection
stale.

**Blocked by:** nothing.

**Status:** resolved

- [x] A finished Playbook run sets `playbook_selections.outcome`.
      `record_playbook_selection`
      (`20260823T000000Z__a_playbook_is_chosen_before_the_model_reads_it.sql:487`,
      called from `src/redkraken/execution.py:335`) inserts the row at the
      column default of `'running'` (`0032_playbooks.sql:325-326`), and nothing
      in the tree ever updates it. The migration that froze the rest of the row
      says in as many words what is supposed to move: "`outcome` and
      `went_stale_at` are what a run updates" (`20260823T000000Z...:460-463`),
      and `enforce_playbook_selection_frozen` (`:464-478`) exists to allow
      exactly those two columns to change.
- [x] `'exhausted'` is written where the run produced nothing, because that
      value is load-bearing rather than cosmetic. `playbook_candidates` drops a
      Playbook for a subject with the reason `'exhausted'` when a prior
      selection on the same `(program, subject, playbook)` carries that outcome
      (`20260823T000000Z...:291-296`, and the same test at
      `0032_playbooks.sql:420`). With nothing writing it, a Playbook that has
      already been run against a subject and found nothing is offered again on
      every pass, forever.
- [x] `mark_stale_selections()` (`0032_playbooks.sql:561-570`) acquires a
      caller. It is the only writer of `went_stale_at`, and it has none in
      `src/`. Its own prose (`:556-560`) describes it as a sweep: "the sweep
      records the fact and the next pass excludes it; the live run is
      untouched". There is no sweep.
- [x] The two constraints that are decoration today become falsifiable:
      `playbook_selections_outcome_check`'s `'produced'` and `'exhausted'` arms
      (`0032:326`), and `playbook_selections_dropped_has_no_outcome`
      (`0032:331-332`), which asserts that a dropped row stays at `'running'`
      and cannot fail while every row stays at `'running'`.
- [x] `check_playbook_integrity`'s `stale_during_run` warning
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

## What was built

One verb and two calls.
`20260925T010000Z__a_finished_run_says_what_its_playbook_produced.sql` adds
`settle_playbook_selections(uuid)`, which takes a Task and writes `produced` or
`exhausted` on every kept selection of it that is still `running`.
`src/redkraken/execution.py:2431-2479` calls it in the pass's closing `finally`,
in its own transaction after `finish_task_attempt`, and
`src/redkraken/execution.py:1082-1115` calls `mark_stale_selections()` once per
pass beside the Lease reconciliation, before anything is offered.

Nothing else was written. `mark_stale_selections` needed no grant and no repair:
027 wrote it, it is open to PUBLIC, and the runtime has held `UPDATE` on
`playbook_selections` since 029. What it lacked was the one line that runs it.

## What `produced` is measured by

The edge the schema already grades promotions with, and no new one. 046 states
the constraint plainly: `playbook_promotion_evidence` joins a selection to a
hypothesis on `(program, subject, property class)` through `playbook_outputs`,
"and there is no other edge between a selection and the hypothesis it caused".
010 measured a keep limit of three, so up to three Playbooks sit on one subject
and nothing downstream can say which of them the model was following. Inventing
a narrower edge here would have been inventing an attribution the rest of the
system does not have.

The two answers are not symmetric, and the predicate fails towards the
reversible one. A wrong `exhausted` is permanent -- the Playbook is dropped for
that subject on every later pass and no later run can undo it -- while a wrong
`produced` costs one more offer. So `produced` is the generous arm: a hypothesis
on a class the Playbook declares, at whatever status it reached and whether or
not something superseded it. `exhausted` is what is left when the run raised
nothing the Playbook claims to be able to conclude.

That is deliberately wider than `playbook_promotion_evidence`, which goes on
requiring `supported`, evidence of the supporting polarity and an Observation
under it. Promotion is a conjunction, so widening this arm cannot promote
anything the narrow one refuses; what it does is stop the harness retiring a
Playbook on a subject whose hypothesis is still open.

A Playbook that declares no output class settles `produced`, which is wrong in
the direction chosen above. There is no class to look for, so the measurement
could never have come out any other way, and reading the absence of a
declaration as the absence of a result would retire that Playbook forever on a
question nobody could have answered. `playbook._playbook` requires `bb:outputs`
and refuses an empty one, so the only rows that arm can reach are catalogue rows
written by hand.

## When, which is the other half of not writing `exhausted` by accident

Only once the Task is settled. `finish_task_attempt` hands a Task with attempts
left back onto the Slate whenever the attempt promoted nothing, and the retry
runs under the very rows this attempt recorded -- `playbook_selections` is
unique on `(task_id, playbook_id)`, so there is no second set to record. A
settlement charged per attempt would retire a Playbook because a container
failed to start, and would retire it in front of the retry that was about to run
it properly. So the verb reads the Task's status for itself and answers without
writing for anything outside `done`, `failed` and `abandoned`, rather than
taking a word from the caller that closed it.

The call is in the closing `finally` and in a transaction of its own. Sharing
the closing's transaction would mean reading a status that transaction was still
deciding, and would put a settlement failure in front of the one call an attempt
must not lose.

One case is left where it was: `reconcile_leases` retires a Task whose owner
stopped beating, and no runtime calls this verb for it. Those selections stay at
`running`, which is what every selection in the corpus was before this ticket,
so the Playbook goes on being offered exactly as it did yesterday. A second
sweep that settled Tasks it had never watched would be writing `exhausted` about
runs it knows nothing about, and that is the one value worth being slow with.

## A third rule was decoration, and the ticket did not name it

`playbook_promotion_evidence` requires `s.outcome = 'produced'`
(`0035_corpus_promotion.sql:81`, re-issued at `20260824T000000Z...:319`), so
with nothing writing that word the function returned no rows for any Playbook at
any digest, `enforce_playbook_promotion` refused every promotion for "no runtime
provenance for this text", and no Playbook in this corpus could reach `stable`
by any route. The criteria name two decorative constraints and this warning;
this was a third, and it is the one that was holding the promotion pipeline
shut. It opens with the rest.

## What it is asserted with

`tests/test_execution.py:1638-1780`, ten cases over the recorder: the sweep runs
before the offer and runs on a pass that claims nothing; a catalogue that moved
under a live mission is reported; a sweep the database refused does not stop the
pass; the settlement happens after the closing, is told the Task and nothing
else, reports what it exhausted, declines to write for a Task going back onto
the Slate, runs for an attempt that never started a child, and cannot take the
closing down with it when it fails.

The database side is asserted by the migration's own closing `DO` block: the
runtime can execute the new verb, the sweep's new caller is one that will be
allowed to run, the two constraints and the freeze trigger this file makes
falsifiable are all still there, and `playbook_outputs` is not empty -- an empty
one would settle every selection `produced` through the no-declared-class arm
and report success while doing nothing.
