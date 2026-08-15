# 36 — Create a candidate Finding from a supported Hypothesis

**What to build:** Create one canonical candidate Finding from a Hypothesis settled by its own holding Test run without granting validation, reporting or exploitation status.

**Blocked by:** 35 — Execute a structured Test through the replay Lane.

**Status:** resolved

- [x] Finding creation requires a supported Hypothesis and the exact holding Test run that settled it.
- [x] The Finding records vulnerability class, affected subjects, identities, demonstrated behavior and evidence references using controlled vocabulary.
- [x] Duplicate candidates for the same Program, Property class and affected cell merge or refuse deterministically.
- [x] Candidate creation cannot set validated, reported, severity-from-impact or exploited state.
- [x] An unrelated Receipt, adjacent Hypothesis, failed replay or model completion claim cannot satisfy the creation guard.
- [x] Rejected candidate proposals remain auditable without polluting canonical Findings.

## How each is met

1. `rk2_finding_refusal` is the gate, and it answers with a sentence rather than
   raising for 035's reason: criterion 6 makes the caller file what it heard, and
   a rule that raises is a rule whose answer cannot be written down — the
   transaction that would record the refusal is the one the exception rolled
   back. Eight arms, in the order a caller can act on: the claim exists in this
   Program, it is `supported`, it was not superseded, the run exists in this
   Program, the run is a run of a Test *of this claim*, it concluded `holds`, it
   is on the `replay` Lane, it is the run that settled the claim, and the class
   is a word from the vocabulary. The eighth is what makes "the exact holding
   Test run" exact: 007's settling transition cites one Receipt, and that Receipt
   has to be one of this run's `test_run_receipts`. A second holding run of the
   same Test against the same target is not it — that is a re-run, and a re-run
   is what 037 validates with. The class arm is last on purpose: it is the one
   refusal that is about the proposal rather than about the evidence, and a
   hunter who gets it after fixing seven others has learned nothing.
   `findings.opened_by_test_run_id` is where the answer is kept, and it is a
   different column from `validated_by_test_run_id` because they are different
   runs by construction. `CandidateFindingTest.test_a_finding_opens_from_the_claim_its_own_run_settled`
   and `test_every_vector_that_did_not_settle_the_claim_is_refused`.

2. Everything the row says about the target is copied, in one statement, off
   rows something else wrote: the subject, the Identity pair and the Property
   class come from the claim, the class from the vocabulary table, and the
   behaviour from the run. What a caller supplies is a class and a title, and
   the title is the one field a human reads and no rule does.
   `rk2_demonstrated` derives the behaviour from the run's own stored
   `assertion_results` and its own `test_run_receipts` — which kinds of assertion
   held, which roles answered, how many Receipts — and `rk2_demonstrated_problem`
   is the shape rule, drawn from 035's `rk2_test_assertion_kinds()` and
   `rk2_test_roles()` rather than from copies of them, with a section 10
   assertion that keeps it that way. A fifth vocabulary of behaviours is
   deliberately not built: it would be model-authored, and the run has already
   answered the question in the two vocabularies a Test is written in. The
   Evidence references are the claim's own supporting Observations, cited in the
   order they were observed; `refutes` edges stay on the claim, because a run
   that disagreed and lost belongs on the claim rather than in the citation list
   of the Finding the claim produced. `test_the_demonstrated_behaviour_is_read_off_the_run_that_holds`,
   `test_a_behaviour_outside_the_vocabulary_is_refused`,
   `test_the_evidence_the_claim_rests_on_is_cited_by_the_finding` and
   `test_the_claim_is_rolled_up_onto_the_finding_once`.

3. The cell is `rk2_finding_cell` — Program, Property class, subject, both
   Identity columns — and it is one function because three places ask the same
   question and only one of them is an index that cannot call it. A merge, not a
   refusal, and for a reason: a second claim settling onto an occupied cell is
   evidence, and refusing it would throw away the observation that two different
   claims about one cell both held. So the second proposal adds its claim and any
   Observations the first did not already cite, and is answered `merged` with the
   Finding it merged into. The lock is on the cell rather than on the row:
   `FOR UPDATE` locks what is there and locks nothing when the cell is empty, so
   two opens racing for an empty cell would both look, both find nothing and both
   insert — and the loser would be answered by `findings_cell_idx` with a unique
   violation that takes its own `finding_proposals` row down with it, losing
   criterion 6's record of the attempt along with the attempt. `open_finding`
   takes `pg_advisory_xact_lock` on the cell key first, which is 023's lock taken
   023's way, and `check_finding_candidates` reports the day somebody removes it.
   What a merge returns is read off the row rather than derived again from the
   merging run: the document names a Finding, so what it says that Finding
   demonstrates is what the Finding demonstrates.
   `test_a_second_proposal_on_one_cell_merges_into_the_finding_already_there`,
   `test_what_a_merge_reports_is_what_the_finding_holds`,
   `test_an_open_holds_the_cell_it_is_working_on_until_it_commits`,
   `test_a_second_finding_written_onto_one_cell_is_refused` and
   `test_only_one_finding_exists_for_all_of_it`.

4. `enforce_finding_birth` is an allowlist inverted, and that is the whole design
   decision. The criterion names states that do not exist yet — 038 has not
   written `exploited_at` — so a guard listing forbidden columns would be silent
   about the one state the criterion names last while looking complete.
   `rk2_finding_birth_columns()` names what a candidate may be born carrying and
   the trigger refuses everything else that is set, so a column a later ticket
   adds is refused at birth until that ticket decides otherwise. Three of the
   allowlisted columns are then checked for value as well, because their value is
   as much a claim as their presence: `status` is `candidate`, `severity` is
   `info`, `severity_basis` is `undetermined`. It is a trigger on the table
   rather than a rule inside `open_finding`, because criterion 4 is a property of
   the row and anything holding INSERT would otherwise walk around it — every arm
   of `refuse_what_the_row_may_not_say` is exactly that INSERT.
   `severity_basis` is this ticket's and not 038's for one reason: the birth
   guard fires BEFORE INSERT, so without it a caller opens at `info` and raises
   the severity in the next statement with nothing anywhere violated. The
   pairing CHECK is what makes the criterion a property of the row rather than of
   the moment it was written, and 038 raises the number and the ground in one
   statement or neither. `test_a_candidate_cannot_be_born_validated_reported_or_severe`
   and `test_severity_and_its_basis_move_together`.

5. Four vectors, four answers. An unrelated Receipt is arm 8: a run that holds
   and produced no exchange the settling transition cited is refused by name. An
   adjacent Hypothesis is arm 5: the run's Test has to be a Test of this claim,
   and the case walks a whole second claim rather than writing a bare row,
   because what the arm compares is the Test's own `hypothesis_id`. A failed
   replay is arm 6: `holds`, and only `holds`, and the case gets there by letting
   a real replay refute its claim rather than by writing an outcome. The model
   completion claim is the one with no field to arrive through — `open_finding`
   takes a claim, a run, a class and a title, and a model filling all four in
   changes nothing about what any of them say — so the only way in is the
   transition, and 007 has no arm into `supported` that is not the runtime's off
   a run. The case tries it the way a model would: the claim its replay left
   `inconclusive`, a real Receipt of the run it watched, `actor_kind = 'llm'`.
   The two forged `test_runs` rows are written directly and deliberately: the
   front door admits one in-flight replay per claim and only against a `testable`
   one, so a second run of a settled claim's Test is exactly the row an attacker
   or a careless migration would have to forge.
   `test_every_vector_that_did_not_settle_the_claim_is_refused` and
   `test_a_model_cannot_settle_the_claim_a_finding_would_rest_on`.

6. `finding_proposals` holds one row per attempt: what was proposed, what became
   of it, and for a refusal the sentence that answered it. The refused ones are
   why the table exists — a hunter whose Finding was refused learns nothing from
   silence, and an operator reading a Program with no Findings cannot tell
   "nothing was proposed" from "everything was refused" — and the accepted ones
   are recorded too, because a table that only holds refusals is one whose rate
   nobody can read. "Without polluting canonical Findings" is the direction of
   the edge: `finding_id` is the only join and it runs from the proposal to the
   Finding, so nothing reading Findings reaches a proposal, and it is null
   exactly when nothing canonical came of it. The rows are immutable below the
   owner, because an audit trail that can be edited afterwards is one that agrees
   with whatever is convenient now. `class_id` is deliberately not a foreign key:
   a proposal naming a class nobody defined is one of the things the refusal is
   for, and a key here would refuse the record of the refusal. The table is
   registered `audit` rather than `covered`, per ADR 0001: two of its three
   outcomes write no canonical row for an Event to be about.
   `test_every_proposal_is_on_file_with_the_sentence_that_answered_it`,
   `test_a_refused_proposal_names_no_finding` and
   `test_the_record_of_a_proposal_cannot_be_edited_or_removed`.

7. `check_finding_candidates` is what a Finding looks like when it was not opened
   by `open_finding`, which is the case worth reporting: every rule above is a
   trigger or a constraint, and a later migration that disables one to backfill
   something leaves no other trace. Seven arms: a Finding naming no holding run,
   one whose run did not hold, one resting on a claim that stopped being
   supported (not an error in itself — 034 can reopen a claim, and a Finding on a
   reopened one is exactly what an operator should be looking at), a candidate
   carrying a severity it has not earned, two live Findings on one cell, a
   refused proposal that reached a Finding after all, and a stored behaviour the
   current shape rule would no longer accept. One arm is about the function
   rather than about the rows: whether `open_finding` still takes the cell lock,
   because the race it closes is invisible in every test that runs one
   transaction at a time and a later edit that drops it would look like a
   simplification. The negative control in `NegativeControlTest` is a candidate
   resting on a run that concluded nothing — what the state looks like when a
   Finding was written around the front door.

## What this ticket also changed

`reject_non_agent_evidence` said "evidence may only cite the agent lane", which
was written when there were two Lanes and one of them was the proxy fetching its
own CSRF token. 035 added a third, and every Observation a replayed Test produces
is backed by a `replay` Receipt — so left alone the rule would have made this
ticket impossible: a Finding could cite none of the evidence its own claim rests
on. It is widened to the pair and not dropped, because `proxy_internal` is still
exactly what 034 was refusing. `reject_non_agent_citation` is widened with it:
034 attached both to `finding_chain_step_citations`, and leaving one behind would
make one table answer two different ways about one replay exchange — admissible
cited through the Observation it produced, inadmissible cited directly. 040 is
what builds chains and should find one rule there.

Two of 009's edge tables had NO ACTION keys to `observations` and `hypotheses`.
Nothing had ever written `finding_evidence` before this ticket, so nothing had
ever discovered that a purge deletes Observations first and is then refused by a
key that fires too late. Both are rebuilt as composite cascades and registered in
`purge_cascade_edges`, and `findings_validated_run_program_fk` is rebuilt behind
the new cascade so 017's rule (d) still holds: RI triggers fire in name order and
a name embeds the constraint OID, so a cascade added today would otherwise fire
after a NO ACTION check added last year.

## What is not covered

Severity above `info`. The vocabulary of grounds is closed here because a CHECK
needs its vocabulary closed at the point the column exists, but nothing reachable
today states one: `demonstrated_impact`, `constrained_inference` and
`program_context` are 038's, and each of them requires that ticket's separately
authorised impact work to have happened.

`duplicate_of_finding_id` is 009's column and stays unwritten. The merge is what
this ticket does with a second claim on one cell, and marking a duplicate is what
a ticket that can un-mark one would need; the index is partial over it either
way, so the day a row is marked, the cell is free again and
`check_finding_candidates` is what notices if two end up live on it.
