# 33 — Promote an evidence-backed Hypothesis

**What to build:** Turn one hunter proposal into a canonical, deduplicated Hypothesis only when its subject, Property class and supporting Observations are valid for the Program.

**Blocked by:** 21 — Promote a recon Mission into typed Surface.

**Status:** resolved

- [x] A proposed Hypothesis names one canonical subject, Property class, relevant Identity cell and structured rationale without claiming execution.
- [x] Evidence edges reference immutable Observations with polarity and baseline, variant or control role.
- [x] Runtime promotion verifies Program reachability, vocabulary, provenance and duplicate identity before creating canonical rows.
- [x] Semantically duplicate proposals converge on one Hypothesis and retain distinct valid evidence edges.
- [x] Unsupported, foreign, missing-provenance and vocabulary-invalid proposals remain rejected staging outcomes.
- [x] Only the runtime may transition the Hypothesis from proposed to testable, and no proposal can mark it testing or terminal.

## How each is met

1. Four things named, and each one resolves against a row rather than against
   prose. The subject is a label this Program holds, refused `no_subject`
   otherwise and `label_other_program` when the label is somebody else's — one
   answer either way is what 021 deliberately avoided, so the two stay apart.
   The Property class is 018's closed vocabulary, refused `unknown_kind`. The
   Identity cell goes through `rk2_identity_cell`, which reports the Entity and,
   when it does not resolve, the sentence the refusal quotes: an element naming a
   cell this Program has not got is refused `no_identity` rather than promoted
   with a NULL, because half the dedup key silently going NULL merges two claims
   about two different callers into one. The rationale is three closed keys
   (`rk2_rationale_keys`), each required — `mechanism`, `expectation`,
   `falsifier` — because `statement` is one sentence and two hunters can write
   the same sentence about different mechanisms. Execution is not claimable at
   all: an element that names a status, an outcome or a transition is refused
   `claims_execution` rather than clamped, since a hunter that wrote
   `status: supported` asserted a Test it did not run and clamping would promote
   the rest of the element as if it had not. One shape rule beside the four:
   a candidate carries a `ref`, because an edge of the same result names its
   claim by `ref` and has no other handle for one, so a candidate without one is
   refused `malformed_field` where the mistake is rather than `no_support` at
   the end of pass 3, which would name a real rule and the wrong fault.
   `HypothesisPromotionTest.test_one_proposal_became_one_hypothesis_naming_all_four`,
   `test_a_promoted_claim_says_what_would_refute_it`,
   `test_a_proposal_that_states_a_status_is_refused_rather_than_clamped` and
   `test_a_claim_that_cannot_be_named_by_an_edge_is_refused_for_that`.

2. `hypothesis_evidence` is the edge and it carries both halves: `polarity` in
   (supports, refutes) and `role` in (baseline, variant, control, context), each
   from 007's closed vocabulary and each refused `unknown_kind` outside it. The
   criterion names three roles and the column takes a fourth, which is not a
   widening: `context` is 018's role for an Observation that may be attached and
   may never push a claim anywhere, and the promotion counts baseline, variant
   and control alone — a claim whose only edge is `context` is refused
   `no_support`, so the three roles the criterion names are exactly the three
   that carry a Hypothesis into existence. The Observation side is a label or a
   `ref` from this same result, never a foreign one — 017 gave the table a
   derived `program_id` joined to both its ends, so an edge spanning two
   Programs is refused by the key rather than by a check. What makes the
   Observation immutable is 013: `reject_mutation_unless_purging` refuses an
   UPDATE or DELETE outside `app.purging`, so an edge's citation cannot be
   rewritten under it after the fact.
   `test_the_edges_name_observations_with_a_polarity_and_a_role`,
   `test_an_observation_an_edge_cites_cannot_be_rewritten_afterwards`,
   `test_a_polarity_and_a_role_outside_their_vocabularies_are_refused`,
   `test_a_claim_standing_only_on_context_stands_on_nothing` and
   `test_an_edge_naming_another_programs_observation_is_refused`.

3. "Before creating canonical rows" is a claim about order, so the walk is three
   passes rather than one. Pass 1 checks every candidate — reachability,
   vocabulary, Identity, rationale, execution — and writes nothing. Pass 2 checks
   every edge against the pass-1 survivors and this Program's rows, and writes
   nothing; an edge naming a candidate pass 1 refused is refused with its own
   reason rather than silently ignored. Pass 3 writes, one PL/pgSQL sub-block per
   candidate covering that candidate's edges as well as itself, because whether
   an edge is admissible is not fully knowable from the payload: 018's
   `enforce_evidential_kind` refuses a non-evidential Observation in any role but
   `context` and 025's transport guard refuses fields a transport claim may not
   assert, so the honest test of "is this supported" is to write the edges and
   see which survive. A block that ends unsupported rolls back its Hypothesis,
   its provenance and every edge it wrote, and no other transaction sees any of
   it. The refusals are collected in an array and flushed after the loop for the
   same reason — a `proposal_drops` row written inside the block would roll back
   with it, and the agent has to be told about the edges the refusal took down.
   `test_a_claim_whose_only_support_the_schema_refuses_leaves_no_row` and
   `test_the_whole_wrong_result_left_the_canonical_tables_alone`.

4. The dedup key is 018's partial unique index on `(subject_entity_id,
   identity_a_entity_id, identity_b_entity_id, property_class)` with
   `NULLS NOT DISTINCT`, and the insert is `ON CONFLICT ... DO UPDATE SET
   statement = hypotheses.statement` — `DO UPDATE` for 021's reason, that
   `DO NOTHING` returns no row against a concurrent uncommitted promotion, and a
   no-op SET because the first hunter's words are what other rows may already
   cite. What the second hunter contributes is a second `hypothesis_provenance`
   row (`converged` true, read off the trail rather than off the insert), the
   union of the evidence, and a `hypothesis_near_matches` row with action
   `key_collision` — the trace 018 built that column for and had no writer for
   until now. Edges naming a Hypothesis this Program already holds are the other
   half of "retain distinct evidence": they stand on their own, `DO NOTHING` on
   conflict, because an edge already there was asserted by whoever asserted it
   and its `proposal_id` goes on saying so. "Distinct" has a limit, and 007 drew
   it: the edge key is `(hypothesis_id, observation_id, role)` and `polarity` is
   not in it, so one Observation saying `supports` and the same Observation
   saying `refutes` in the same role are the same edge, not two. `DO NOTHING`
   would keep the first and drop the second in silence, and the second hunter
   would read a converged claim carrying the opposite of what it wrote. The
   polarity is read back off the row that stands — the inserted one, or the
   existing one when nothing was inserted — and an edge that disagrees with it
   is refused `polarity_conflict` and does not count as support.
   `test_the_second_proposal_converged_rather_than_writing_a_second_row`,
   `test_both_proposals_are_named_and_the_second_says_it_arrived_second`,
   `test_the_first_hunters_words_are_the_ones_that_stand`,
   `test_the_statement_that_converged_is_kept_as_a_key_collision`,
   `test_the_converged_claim_kept_the_evidence_of_both_proposals`,
   `test_the_same_observation_cannot_stand_both_ways_in_one_role` and
   `test_promoting_the_same_result_again_changes_nothing_and_says_so`.

5. Every refusal is a `proposal_drops` row and the proposal itself still
   promotes whatever else it carried, which is what "remain rejected staging
   outcomes" asks for: nothing raises, and `v_canonical` says `rejected` for a
   result whose every element was dropped. Five reasons are this ticket's —
   `claims_execution`, `no_identity`, `no_support`, `claim_past_proposed` and
   `polarity_conflict` — and the rest are reused deliberately. `no_support` is
   not `no_provenance`: a citation that does not resolve is one mistake, and a
   claim whose every citation resolves and which nothing stands behind is
   another. `no_identity` is not `no_subject` for 021's reason, that an agent
   told `no_subject` would resend the same claim about the same subject.
   `claim_past_proposed` is not `claims_execution`, which is about an element
   asserting a status of its own; this one is about a claim somebody else has
   already moved. `polarity_conflict` is not `unknown_kind`, because both
   polarities are in the vocabulary and it is the pairing that is spoken for.
   `unknown_kind` itself covers a Property class, a polarity and a role alike,
   because `element_path` already says which vocabulary was asked.
   `test_a_claim_about_a_subject_no_program_holds_is_refused`,
   `test_a_claim_about_another_programs_subject_is_refused_by_name`,
   `test_an_identity_cell_that_is_not_an_identity_is_refused_by_name`,
   `test_a_property_class_outside_the_vocabulary_is_refused`,
   `test_a_rationale_that_names_no_falsifier_is_refused`,
   `test_a_claim_nothing_in_the_result_supports_is_refused`,
   `test_an_edge_citing_no_observation_has_no_provenance_to_stand_on` and
   `test_an_edge_that_names_no_claim_is_refused_for_naming_none`.

6. 007 seeded `proposed -> testable` with `required_actor_kind = 'llm'`, the one
   hypothesis transition a model could make. It becomes `runtime`, and a DO block
   in the same migration refuses to apply the file if any hypothesis transition
   still admits a non-runtime actor, so the property is asserted rather than
   assumed. `testable` is not a formality: 023 ranks testable Hypotheses into
   Tasks, so a model that could set it could schedule its own work. Everything
   past `testable` was already the runtime's, and `claims_execution` closes the
   other door — a proposal cannot arrive at `testing` or a terminal status by
   naming one, because naming one is a refusal. There is a third door and it is
   the quiet one: a claim can be moved after it was promoted, and a later
   proposal converging on the same key would add evidence to a Hypothesis whose
   Test is already running. The dedup index says nothing about status, so the
   convergence would succeed, and 007's transition machine counts every
   `hypothesis_evidence` row for `min_supporting_evidence` regardless of who
   wrote it — a model could carry a claim over a quorum it is not allowed to set
   directly. Both writing paths take the status under `FOR UPDATE` first, the
   converging candidate and the edge naming a Hypothesis by label, and a claim
   past `proposed` is refused `claim_past_proposed` before anything is written.
   `test_no_hypothesis_transition_is_open_to_a_model`,
   `test_a_model_cannot_call_the_claim_it_proposed_testable`,
   `test_a_claim_under_test_is_not_something_a_later_result_may_reach` and
   `test_the_runtime_may_move_it_and_the_status_follows_the_transition`.

## The support check is where this ticket lives

Everything else here is a lookup: a label resolves or it does not, a class is in
the vocabulary or it is not. Support is the only question that cannot be
answered by reading the element, because it is a fact about a different list —
the edges — and about what the schema will accept from that list once the rows
are real.

That is why it is three passes and why pass 3 is a sub-block per candidate
rather than one block around the loop. A single block would make one unsupported
claim take the whole result down, which is not a staging outcome, and checking
support from the payload alone would call a claim supported on the strength of
an edge `enforce_evidential_kind` was going to refuse. Writing the edges and
seeing which survive is the only version of the check that is not a guess, and
the sub-block is what makes it free: the Hypothesis, its provenance and its edges
all disappear together, and the drops describing them are held outside so they
do not disappear with them.

`RK033` is that block's own SQLSTATE. It is raised where support is decided and
caught once, so the handler does not have to recognise a refusal by its prose,
and so a genuine invariant violation from the same block is still reported as
`refused_by_invariant` with the message the schema gave.

What is not covered: a Hypothesis can be supported by an Observation that turns
out to mean something else. Nothing here reads an Observation's content — the
edge says this Observation stands behind this claim, the vocabulary says the
Observation is the kind of thing that can stand behind one, and settling whether
it actually does is what a Test is for. `check_hypothesis_promotion` re-asks the
structural half of the question of everything already promoted: a promoted claim
with no supporting edge, one with no falsifier, and the three structures — the
transition rule, the status guard, the dedup index — whose drift would make the
first two read clean while meaning nothing.
