# 34 — Retain refutation and make it due on Surface change

**What to build:** Keep a refuted Hypothesis as Negative knowledge with its exact conditions and make it retestable only when a relevant Surface delta invalidates those conditions.

**Blocked by:** 22 — Fingerprint Surface and detect change; 33 — Promote an evidence-backed Hypothesis.

**Status:** resolved

- [x] Refutation records the settling Test conditions, identities, Surface fingerprint, evidence and transition reason rather than deleting the Hypothesis.
- [x] Matching unchanged Surface suppresses redundant equivalent Tasks and returns the Negative knowledge in bounded context.
- [x] An unrelated Surface change leaves the refutation current.
- [x] A typed relevant delta creates an explicit `retest_due` transition and makes a new Task eligible without rewriting history.
- [x] Multiple recomputations and restarts are idempotent and emit no duplicate transitions.
- [x] Legacy negative states without settling provenance import as unverified rather than active suppression.

## How each is met

1. `negative_knowledge` copies the conditions rather than joining them, which is
   the whole reason it is a table: `hypotheses` carries the claim as it is now,
   the record carries the claim as it was when it failed, so a subject later
   superseded or a Property class the vocabulary later drops cannot rewrite what
   was settled. The columns come in groups — the claim (subject, Property
   class, both Identity cells), the Surface (`application_entity_id`,
   `fingerprint_id`), the settling (`test_id`, `test_run_id`, `spec_sha256`,
   `outcome`, `assertion_results`), the transition and its `reason`, and the
   edges as a second table — and where a group means nothing half-filled, a
   check says so rather than a convention: the Surface pair is null or present
   together, and so are the run and the Test that produced it. What was read
   OFF the run gets a weaker rule, one direction only, because a run whose
   outcome the schema allows to be null is still a run and what has to be
   refused is the other shape — a record with no settling run carrying a spec
   digest or an outcome from somewhere else. `receipt_id` is in none of the
   groups on purpose: it is the Receipt the settling TRANSITION cited, which is
   on file whether or not a run of this claim's own Test is behind it.
   `negative_knowledge_evidence` is separate and is deliberately
   not a view over `hypothesis_evidence`: an Observation attached after the
   claim was refuted did not settle it, and a reader asking what refuted this
   has to be able to tell the two apart. Nothing deletes the Hypothesis — it
   stays `refuted` with its whole transition history, and the record hangs off
   it. `basis` is the one column that says whether the settling is on file, and
   `CHECK ((basis = 'settled') = (test_run_id IS NOT NULL))` is what stops a row
   claiming provenance it has not got, because every rule downstream reads
   `basis` and none re-derives it. All three tables carry
   `reject_mutation_unless_purging`, so a kept refutation is not editable after
   the fact; a claim refuted a second time is a second row under the
   `(hypothesis_id, transition_id)` key, not an overwrite.
   `NegativeKnowledgeTest.test_a_refutation_is_kept_with_the_conditions_it_was_settled_under`,
   `test_the_surface_it_was_settled_against_is_the_one_that_stood`,
   `test_the_test_that_settled_it_is_the_claims_own`,
   `test_the_evidence_is_kept_as_it_stood_at_settling`,
   `test_a_kept_refutation_cannot_be_rewritten_afterwards`,
   `test_a_refutation_that_left_no_transition_is_kept_as_unverified` and
   `test_a_claim_refuted_twice_keeps_both_records_and_stands_on_the_newer`.

2. Suppression is one arm in `cancel_reason_for`, and it has its own word:
   `settled_negative`, not `answered`. The two were conflated and they are
   different facts — an operator reading a Task's end wants to know whether the
   question was answered or is merely being held down by a record that could
   stop being current tomorrow. The arm fires only when the claim is `refuted`
   AND `rk2_negative_standing` of its current record is `settled`, which is the
   sentence criterion 2 and criterion 6 share. "Equivalent Tasks" needs no
   equivalence rule here because 033 already built one: two hunters proposing
   the same claim converge on one Hypothesis row, so a Task asking the same
   question is a Task naming the same `hypothesis_id`, and suppression keyed on
   the claim is equivalence by construction. The bounded read is
   `rk2_hypothesis_negative`, spliced into `v_records` beside
   `observed_fingerprint`, and it says three things: standing, when it was
   settled, and the reason. Not the fingerprint, not the delta, not the
   Application — 020 kept Surface fingerprints away from the model, because an
   agent that can read what the runtime watches for change can aim at it, and
   that decision survives here. `v_negative_knowledge` is the operator's read
   and carries all of it in labels, which is 020's rule 5.
   `test_an_unchanged_surface_suppresses_the_task_that_asks_again`,
   `test_the_suppression_is_its_own_reason_and_not_answered`,
   `test_the_bounded_read_carries_the_refutation_and_not_the_fingerprint`,
   `test_the_record_a_hunter_reads_names_its_negative_knowledge` and
   `test_the_operator_view_names_the_conditions_in_labels`.

3. Relevance is a join and not a judgement, and for a Surface delta
   `rk2_negative_relevant_deltas` is the whole of it. 022 owns one half — which
   Property classes a typed delta puts back in question, as
   `surface_delta_property_classes` — and this file adds the other: the delta's
   subject has to be in the claim's scope or be one of its Identity cells, and
   the delta has to belong to a fingerprint of the claim's own Application newer
   than the one recorded. One path does not go through that query at all, and
   deliberately: 007's watch rows are a relevance judgement somebody already
   made and recorded, so a fired watch makes its claim's record due on its own
   authority, under the reason `watch` rather than `surface_delta`, with no
   delta to name. What 022 handed over was that the watch was reading the wrong
   Surface, not that it should be re-decided here. Each of the three ways for a
   delta to be unrelated fails a different conjunct, which is why four of the
   fixture's refutations sit on the same question rather than one: a change of a
   class the claim is not about fails the mapping, a change to another route
   under the same Application with the same Property class fails the scope, and
   a change to another Application fails the `application_entity_id` join. The
   `nested` claim is the fourth and it is there for the other direction — a
   change one level ABOVE its subject has to reach it. The comparison is
   against the recorded fingerprint ROW ordered by `(computed_at, id)` rather
   than against `detected_at`: transaction time is not settling order, and a
   fingerprint computed in a transaction that started before the settling one
   and committed after it would carry an earlier timestamp than the refutation
   it invalidates.
   `test_a_change_of_a_class_the_claim_is_not_about_leaves_it_current`,
   `test_a_change_to_another_route_leaves_the_neighbouring_claim_current`,
   `test_a_change_to_another_application_leaves_the_refutation_current` and
   `test_a_change_above_the_claims_subject_reaches_it_too`.

4. `refresh_negative_knowledge` runs as step (1) of `rank_pass` and writes two
   rows per record that has become due: a `refuted -> testable` transition whose
   rationale names the delta (`retest due: endpoint_changed on GET /notes`) and
   a `negative_knowledge_retests` row citing both the delta and the transition.
   The transition is what makes the Task eligible — 023 ranks testable claims —
   and nothing already written is touched: the record keeps the fingerprint it
   was settled against, so the claim stays due against the Surface it was
   actually settled under rather than against the one that reopened it. Scope is
   `rk2_claim_scope`, the projection's containment read backwards, and it walks
   BOTH ways. Down, because a claim about a route is a claim about that route's
   inputs. Up, because a claim about a parameter was settled under the route the
   parameter sits on, and without that arm a route whose authentication was
   removed leaves every ownership refutation about its own inputs standing.
   Ordering inside the pass is load-bearing: step (1) runs before step (2) reads
   statuses, or the Task asking the question again is abandoned in the same pass
   that reopened the claim. The log is a row Event on the retest row rather than
   a hand-written insert, which is 026's shape — the table exists, so a trigger
   writes the Event and no call site can forget to.
   `test_a_relevant_delta_makes_the_refutation_due_and_names_it`,
   `test_a_change_above_the_claims_subject_reaches_it_too`,
   `test_the_claim_re_enters_through_a_transition_and_the_history_stands`,
   `test_the_conditions_it_was_settled_under_are_not_rewritten_by_the_retest`,
   `test_the_reopened_claim_is_no_longer_suppressed` and
   `test_the_log_says_the_question_was_reopened_and_why`.

5. Idempotence is the key and not the guard. `negative_knowledge_retests` is
   `UNIQUE (negative_id)`: one record stops being current once, because a record
   that has been made due is done making claims about the world and the retest
   that follows produces its own record with its own conditions. So a second
   reason for the same record is refused by the database rather than by a writer
   remembering to check, and `v_negative_knowledge`'s scalar `retest` subquery
   cannot be handed two rows. `note_retest_due` is the single writer both loops
   call and it carries the guard itself, which the watch loop needs: that loop
   selects trigger rows and only afterwards asks which record the claim was
   standing on, so a record step (1) made due earlier in the same pass reaches
   it, and returning null is what stops the unique key taking the pass down.
   Step (1) additionally takes each claim's row `FOR UPDATE` and re-reads the
   guard under it, so two passes reaching the same claim concurrently do not
   both write a transition — the second would fail 007's stale-status check and
   take the whole pass down with it. `record_negative_knowledge` is idempotent
   the same way, under `(hypothesis_id, transition_id)` with
   `NULLS NOT DISTINCT`, which is what makes the transition-less import
   re-runnable. Restart is asserted as a restart: the sixth pass runs on a
   connection the case has never used, with `rk2.program_id` resolved again and
   no plan cached, and the whole transition ledger plus the row counts are
   compared across it.
   `test_two_more_passes_over_a_recomputed_surface_write_nothing`,
   `test_one_record_stops_being_current_once_however_often_it_is_asked`,
   `test_a_record_can_only_stop_being_current_once_by_the_key`,
   `test_a_restart_re_runs_the_pass_and_writes_nothing` and
   `test_recording_the_same_settling_twice_returns_the_record_it_made`.

6. Section 9 imports every refutation already in the corpus through the same
   writer the triggers use. A claim refuted through a transition citing a Test
   run's Receipt imports as `settled` — the provenance was always there, nothing
   had read it — and everything else imports as `unverified`. `unverified` is
   not merely a label: `cancel_reason_for`'s new arm requires `settled` before
   it will suppress, so nothing this ticket adds holds work down on the strength
   of a status somebody typed. That alone would not free the claim, and the next
   step is the one that does. An unverified record is made due by the first
   pass, which moves the claim out of `refuted` entirely. Without that, 023's
   older rule still applies — a claim in `supported` or `refuted` with no watch
   fired is `answered`, and `novelty_for('hunt')` returns 0 for the same claim —
   so the imported claim would be held down anyway, by a rule that predates this
   ticket and reads the status alone. Reopening is the only thing that actually
   un-suppresses it, which is why the assertion before the first pass is
   `answered` and not "not cancelled". The cost is one transition per record
   nothing settles: the legacy corpus once, on the first pass after this
   migration, and after that every claim inserted with `refuted` already set,
   because the `hypotheses` trigger records that door too and a claim that
   arrived refuted has no settling to find either. The alternative is a corpus
   of refutations nobody can point at and nothing can ever re-ask. What an
   import does NOT get is a reconstructed past: no Surface condition unless the
   Program has a fingerprint for the subject's Application, and then today's row
   rather than a guess at the one that stood, which makes the claim due on the
   next change rather than on a change that already happened.
   `test_an_import_is_not_suppression_before_any_pass_has_run`,
   `test_the_first_pass_reopens_what_nothing_on_file_settles` and
   `test_an_unverified_record_names_no_settling_test`.

## 022's hand-off, closed here

022 recorded a bug rather than fixing it: 007's `hypothesis_retest_triggers`
compare a watched entity's fingerprint against "the Program's newest
fingerprint", and a Program with two Applications makes that wrong in both
directions — the watch fires on a change to an Application it is not watching,
and stays silent when its own moves and another Application's row is newer. The
comparison now goes through `rk2_current_fingerprint(rk2_application_of(...))`,
so a watch reads the Surface of the Application its watched entity belongs to.
A watch whose entity belongs to no Application is counted as
`watches_unwatchable` rather than compared against something arbitrary.
`test_a_watch_does_not_fire_on_another_applications_change`,
`test_a_watch_fires_when_the_application_it_watches_changes` and
`test_the_pass_reports_what_it_reopened`.

## What this file had to repair to be writable at all

`hypothesis_retest_triggers.watched_entity_id` and
`test_run_receipts.receipt_id` were both written `ON DELETE CASCADE` by the
migrations that created them, and 016's rule (e) — no foreign key outside
`purge_cascade_edges` may cascade — stripped the delete action from both,
correctly, because neither was declared. Undeclared, they make a Program
unpurgeable once it holds either row: `DELETE FROM programs` reaches `entities`
and `receipts` directly and reaches these two children only through `hypotheses`
and `test_runs`, so the referential check of a child nothing has deleted yet
runs against a parent that is already gone. 031 repairs firing order within one
parent-child pair; this is across two parents, which no ordering fixes. Both
edges are now declared in `purge_cascade_edges` and the cascade their own
migrations wrote comes back with them. This ticket's fixture is the first thing
in the corpus to write either row, which is why neither had been seen.

Rule (e) reads one way only — it refuses a cascade nothing declared, and says
nothing about a declaration whose key does not cascade — so
`test_every_cascade_this_file_declares_is_one` asserts the other half for all
four of this file's edges.

## Follow-ups recorded

- MEASURED: `basis = 'settled'` is unreachable from the running system today.
  It requires a `test_run_receipts` row joining the settling transition's
  Receipt to a run of the claim's own Test, and nothing in `src/` writes that
  table — 035 is the ticket that will, when it runs a Test through the replay
  Lane and records the Receipt each action produced. Until then every record
  this file writes is `unverified`, every claim is reopened by the first pass,
  and `settled_negative` suppression is exercised by the fixture and by nothing
  else. That is the correct behaviour rather than a gap — a refutation whose
  settling nobody can produce should not hold work down — but it means the
  suppression path goes into production untested by the runtime, and 035 is
  where it starts being used.
- MEASURED: five more foreign keys have the same shape as the two repaired here
  — declared nowhere, cascading nowhere, reachable from two parents —
  and no fixture writes them yet: `finding_chain_step_citations` (twice),
  `finding_effects`, `finding_evidence`, `finding_hypotheses` and
  `hypothesis_evidence` (twice). Repairing them blind, with nothing exercising
  the purge path, would be seven guesses; they are listed here so the first
  fixture that writes one of them knows what it is looking at.
- `rk2_application_of` resolves an Application, a route and a parameter, and
  nothing else. A `technology_changed` delta names the technology Entity, which
  belongs to an Application through the `runs` relationship rather than through
  containment, so 022's five technology Property classes currently reach no
  claim through `rk2_claim_scope`. Teaching `rk2_application_of` about `runs` is
  022's rule to change, not this file's.

## Where this ticket lives

Everything else is a lookup. The one question that is not is "does this change
bear on this claim", and it has exactly two failure modes, both silent: a rule
too narrow leaves a refutation suppressing work about a Surface that has moved
underneath it, and a rule too wide reopens every claim on every deploy, which is
the same as keeping no refutations at all.

So the rule is a join over rows somebody else already writes — 022's typed
deltas, 022's class mapping, 022's fingerprints, the projection's own
containment — and this file adds no new judgement of its own. What it adds is
the requirement that the join be re-checkable: `check_negative_knowledge` asks
its fourth arm of every `surface_delta` retest already written, so a retest
naming a delta the relevance query no longer agrees with shows up as a row
rather than as a claim quietly reopened for no reason. The other two reasons are
outside that arm because neither names a delta for it to re-check — `unverified`
is a record with no conditions to invalidate, and `watch` is 007's judgement
rather than this file's. Its fifth and sixth arms guard the two
structures whose drift would make the first four read clean while meaning
nothing — the `refuted -> testable` rule, without which every kept refutation is
permanent however many deltas arrive, and the delta-to-class mapping, whose
emptiness reads exactly like a Surface that never moved.

What is not covered: a refutation about a subject that belongs to no Application
— an Identity, a Host — records no Surface condition, and nothing can make it
due. It is settled and stays settled. The alternative is to pick some
Application for it, and a condition nobody can defend is worse than an absent
one; `v_negative_knowledge` says `application` is null and the operator can see
which records they are.
