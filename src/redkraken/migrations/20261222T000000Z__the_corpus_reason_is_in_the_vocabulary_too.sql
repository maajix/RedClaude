-- ---------------------------------------------------------------------------
-- The corpus reason is in the vocabulary too                         (ticket 218)
--
-- `20261221T000000Z__a_task_whose_playbook_moved_says_so.sql` added the
-- `corpus_moved` reason and its header states, wrongly, that the vocabulary is
-- free text because `0026_human_control.sql:449` dropped the enum. That line
-- did drop it. `20260814T080000Z__a_refutation_is_kept_and_made_due.sql:845`
-- put it back, and two later migrations have re-stated it since -- ticket 143's
-- `undispatchable` (`20261019T000000Z:63`) and the budget one's
-- `budget_exhausted_twice` (`20261024T000000Z:370`), both by the DROP-and-ADD
-- this file repeats. Reading the earliest statement of a rule and not the
-- latest is what produced the claim, and the first `rk run` after the previous
-- migration is what corrected it:
--
--     invalid_configuration | database | the scheduler could not offer a slate:
--     23514: new row for relation "tasks" violates check constraint
--     "tasks_abandoned_reason_check"
--
-- So `rank_pass` reached the Tasks, named them correctly, and could not write
-- the word down. Nothing was lost -- the whole pass rolls back on the raise --
-- but no pass could be made at all while it held.
--
-- The wall is the constraint, and its price is this file: one DROP, one ADD and
-- the twelve words that were already allowed. The previous migration is left as
-- it is rather than edited, because it is applied and `check_migrations` holds
-- its digest.
--
-- Told apart from `undispatchable` the same way that one is told apart from
-- `attempts_exhausted`. `undispatchable` is a Task this runtime cannot serve at
-- all. `corpus_moved` is a Task this runtime could serve perfectly well, for a
-- document it no longer has -- so the Task is fine, the harness is fine, and
-- what is missing is the text a past selection promised the model would read.

ALTER TABLE tasks DROP CONSTRAINT tasks_abandoned_reason_check;
ALTER TABLE tasks ADD CONSTRAINT tasks_abandoned_reason_check
    CHECK (abandoned_reason IN (
        'out_of_scope','superseded','answered','attempts_exhausted',
        'program_closed','budget_exhausted','near_duplicate',
        'decision_timeout','decision_denied','settled_negative',
        'undispatchable','budget_exhausted_twice','corpus_moved'));

COMMENT ON CONSTRAINT tasks_abandoned_reason_check ON tasks IS
  'Every reason a Task can end without being done. Thirteen words, and each is added by the migration that teaches something to write it -- a reason nothing emits is a reason nobody knows the scheduler can reach.';
