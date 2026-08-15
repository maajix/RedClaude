# 35 — Execute a structured Test through the replay Lane

**What to build:** Run one immutable Test specification with baseline, variant and control actions through production egress and derive a deterministic outcome from its assertions.

**Blocked by:** 25 — Reserve and reconcile campaign budgets; 33 — Promote an evidence-backed Hypothesis.

**Status:** resolved

- [x] A Test contains typed preconditions, setup, request or tool actions, assertions and cleanup; changing any part creates a new Test identity.
- [x] The runtime verifies scope, risk, Identity Leases and budget before moving the Hypothesis to testing.
- [x] Every network action uses a replay-bound capability and produces a Receipt whose Lane is exactly `replay`.
- [x] Baseline, variant and control roles remain explicit from action through Evidence and cannot be inferred from ordering.
- [x] Deterministic assertion evaluation records holds, refutes or inconclusive plus failed assertion identifiers and cleanup state.
- [x] A database constraint and negative test refuse attaching an agent-Lane Receipt, unrelated Tool run or foreign Artifact to the Test run.

## How each is met

1. `rk2_test_spec_problem` is the shape, and it is a function rather than a
   CHECK expression so that the constraint on `tests` and the sentence a caller
   is refused with are the same rule read twice — a caller who is told only
   "violates tests_spec_shape_check" has to guess which of thirty rules it was.
   The five parts are closed: a key the specification does not have a part for
   is refused by name, which is what stops a `teardown` nobody executes from
   being storable. Preconditions are prose under a typed word, not a predicate,
   because the four conditions the runtime can actually decide it decides in
   `open_test_replay` against canonical state, and a second copy stated in the
   specification would be a second answer that could disagree. Setup and
   cleanup carry a method and a url and nothing else — no role, because a role
   is what makes an action evidence and neither of them is evidence about the
   target. Every url in every part goes through `rk2_test_request_problem`,
   which refuses a path that resolves somewhere other than where it reads —
   `/public/../admin` is scope-classed as `/public/` when the plan is checked
   and reaches `/admin` when it is sent, and `%2e` goes with it because a dot
   the door decodes is a dot. Actions carry their own ordinal and are checked
   against their position, so the plan cannot be read in one order and numbered
   in another. A
   Test performs between 3 and 32 actions and at least one of every role, and
   the floor of three follows from the rule above it rather than standing on its
   own: this ticket asks for "baseline, variant and control actions", so a Test
   carries all three roles and cannot do that in fewer than three actions. What
   that rules out is the Test with no control — a baseline and a variant that
   differ, with nothing to say the target would not have differed anyway.
   Assertions are identified, and two sharing an identifier are refused —
   criterion 5 reports failures by identifier, so a duplicate would report a
   failure nobody can locate. Identity is `rk2_test_spec_digest` over the stored
   jsonb, which is canonical: keys are stored sorted and de-duplicated, so two
   specifications equal as jsonb digest the same. 008 made `spec_sha256` a plain
   column and a caller still supplies it, so what stops it disagreeing is
   `tests_spec_sha256_agrees_check` rather than the absence of the column —
   a stored digest that is not the digest of the stored specification is refused
   at write time. `tests` is immutable, so a changed part is a new row with a new
   digest and a new label rather than an edit, and
   `tests_hypothesis_id_spec_sha256_key` keeps one Hypothesis from holding two
   copies of one specification. `ReplayTestRunTest.test_a_specification_that_could_not_settle_its_claim_is_refused`,
   `test_each_refusal_names_what_is_wrong_with_the_specification`,
   `test_the_digest_is_the_identity_and_cannot_disagree_with_the_test` and
   `test_changing_any_part_of_a_test_produces_a_different_test`.

   What is deliberately not built: a Test action that runs an offline tool. This
   criterion words it as "request or tool actions", and it and criterion 6
   cannot both be met today. 030 gives an offline run a `tool_runs` row of its
   own — that is what carries its ceilings, its isolation and its exit — and a
   tool whose registry row says `network = 'proxy'` does reach the door under
   that row, so the Receipts it produces are its own Tool run's. Criterion 6
   refuses exactly that: a Test run may not cite a Receipt another Tool run
   produced. A tool action becomes possible when 030 has a way to perform a tool
   under a Tool run that already exists, and not before. `kind` is on every
   action and takes one word today, so the vocabulary widens in one place on the
   day it does.

2. `open_test_replay` is one transaction that either commits a plan or raises,
   and every condition is checked in it before the row that would move anything
   exists: the Program is not Halted, the agent run has not ended, the claim is
   `testable` rather than any other status, no replay of that claim is already
   in flight, the named Identity slot is held by a live lease of this run's,
   `budget_refusal_for` will carry the work, and every url in the actions, the
   setup and the cleanup classes as `target` or `egress_support` against the
   current scope version. The scope loop covers the setup and the cleanup for
   the reason the actions are covered: a cleanup step pointing outside the scope
   is a request the door would refuse at the moment the run is least able to do
   anything about it. The claim moves to `testing` in `record_test_action`, on
   the first action and not before, because 007 requires a Receipt for that
   transition and the first action is the first moment one exists — so a replay
   refused by any of the checks above leaves the claim exactly where it was, and
   so does one that was allowed but reached nothing.
   `test_the_conditions_are_checked_before_the_hypothesis_moves`,
   `test_a_refused_replay_leaves_the_claim_where_it_was`,
   `test_the_risk_gate_decides_before_the_first_request`,
   `test_the_claim_moved_to_testing_on_the_first_action_and_not_before` and
   `test_a_replay_that_recorded_nothing_leaves_the_claim_testable`.

3. The Lane is a property of the capability and nothing the runtime says.
   `open_test_replay` writes the `test_replays` row before it calls
   `authorize_tool_run`, so the mark exists by the time a capability does;
   `write_allowed_receipt` sets `lane := rk2_capability_lane(tool_run_id)`,
   which answers `replay` for a Tool run performing a Test and `agent` for every
   other. No argument anywhere carries the word, which is what makes this a
   property of the schema rather than a discipline the runtime is trusted with.
   The trigger that holds an allowed Receipt to a live capability read
   `NEW.lane = 'agent'` and now reads `IN ('agent', 'replay')` — otherwise a
   `replay` Receipt would have skipped every check in it — so a replay Receipt
   still requires a Program that is open and unhalted, an agent run that has not
   ended and a Task lease that has not expired. `record_test_action` refuses a
   Receipt of any other Lane at the citation site as well.
   `test_every_receipt_a_replay_produced_carries_the_replay_lane`,
   `test_the_lane_is_read_off_the_tool_run_rather_than_taken_from_a_caller`,
   `test_a_replay_receipt_still_needs_a_live_capability_behind_it`,
   `test_a_replay_tool_run_is_classed_and_named_like_every_other`,
   `test_a_request_the_door_refused_is_a_replay_receipt_too` — the Lane is
   derived the same way for a request the door turned down, so a Test that was
   stopped is on the record as a Test rather than as an agent's stray call — and
   `ReplayCommandTest.test_every_receipt_the_door_wrote_for_it_carries_the_replay_lane`,
   which reads the Lane off Receipts a real `proxy.listen` door wrote on the
   proxy role's own session rather than off rows the case wrote itself.

4. The role travels by copy, in one direction, and is never derived. The Test
   states it; `record_test_action` reads it out of the plan by ordinal and
   writes `test_replay_actions.role` — the verb takes an ordinal and a Receipt
   and has no role parameter, so a caller cannot supply one; `close_test_replay`
   copies it into `test_run_receipts.role`, a column 008 did not have and the
   reason a reader of a finished run had to infer the role from the order; and
   each `hypothesis_evidence` row copies it from there. `test_run_receipts.role`
   is NOT NULL with no backfill, which is safe precisely because nothing in
   `src/` has ever written that table — an ALTER that refused here would be
   reporting a row whose role would have to be invented. Ordering carries
   nothing: `test_replay_actions` is keyed by `(tool_run_id, ordinal)` and
   `receipt_id` is unique across it, so one Receipt answers one action and a run
   cannot cite one exchange as both its baseline and its variant to produce a
   differential against itself. `test_the_role_of_an_action_reaches_the_test_run_receipt`,
   `test_the_role_reaches_the_evidence_the_run_filed`,
   `test_a_role_cannot_be_read_off_the_order_the_rows_were_written_in`,
   `test_the_caller_never_supplies_a_role`, `test_one_receipt_answers_one_action`
   and `ReplayCommandTest.test_the_run_it_filed_names_the_three_roles_in_the_planned_order`.

5. `evaluate_test_assertions` is STABLE and reads only the run's own Receipts,
   so the outcome is a function of what the door recorded rather than of what
   the process concluded — asked twice it answers the same thing, and
   `close_test_replay` calls it rather than accepting an outcome. Each assertion
   answers true, false or null, and the three add up in one place: one null
   makes the run `inconclusive`, one false `refutes`, everything true `holds`.
   Section 1 renamed 008's `fails` and `error` to get there, and the rename is
   not spelling — `fails` and `refutes` are one word for one fact, and `error`
   is not `inconclusive`, because 007's machine has no `testing -> error` arm
   and a run that errored had nowhere to leave the claim. The three words now map
   one-to-one onto the three statuses `testing` may reach, which is what lets the
   close settle a claim without a second judgement about what the run meant. A
   null verdict is stored as a null rather than dropped, so a reader can tell an
   assertion nobody could answer from one that failed; `IS DISTINCT FROM` is
   deliberately not used on the bodies, because two Receipts that both stored
   nothing are not two identical bodies but two answers nobody kept, and reading
   them as equal would turn an unanswered question into a refutation. The failed
   identifiers and the cleanup state are stored beside the verdicts in
   `assertion_results`, and the cleanup is the runtime's honest report of one of
   three things: `done`, `failed` (it tried and could not) or `skipped` (it never
   got there). An inconclusive run files no Evidence and settles nothing.
   `test_a_run_whose_assertions_all_held_holds`,
   `test_a_run_with_a_failed_assertion_refutes_and_names_it`,
   `test_a_run_that_could_not_evaluate_an_assertion_is_inconclusive`,
   `test_the_stored_results_carry_every_assertion_and_the_cleanup`,
   `test_an_unevaluated_assertion_is_recorded_as_a_verdict_nobody_reached`,
   `test_the_same_run_evaluated_again_answers_the_same_thing`,
   `test_the_outcome_is_a_function_of_the_receipts_and_not_of_the_caller`,
   `test_the_close_reports_how_the_tool_run_ended` — the Tool run is `error`
   for the inconclusive run and `success` for the two that answered, which is
   how a reader of `tool_runs` alone sees a Test that settled nothing — and
   `test_the_three_words_a_run_may_conclude_are_the_three_a_claim_may_reach`.

6. `enforce_test_run_receipt_lane` is one trigger with three arms, and it is a
   trigger rather than a convention because section 9 passes all three by
   construction and the rule is for every other writer. The Lane arm is 042's,
   unchanged. The Tool run arm refuses a Receipt produced by any Tool run but
   this replay's own: another run's Receipt is another run's evidence however it
   was obtained, and a Test run that could cite one could rest a conclusion on a
   request nothing about this Test caused. The Artifact arm refuses a Receipt
   naming bytes sealed to another Program — bytes are content-addressed and
   therefore global, so the seal is the only thing that makes an Artifact this
   Program's, and 017's isolation is exactly what citing one would cross. What
   it matches is `artifact_seal.sha256` — the wire plaintext digest, which is
   that table's primary key and therefore the seal's identity — against every
   digest the Receipt names, all four of them, because the question is whether
   this Receipt names bytes somebody else sealed and a digest is a digest. It
   never reads `artifact_seal.agent_sha256`: the redacted view is a second
   description of bytes the seal already identifies, so matching it would catch
   nothing the identity does not already catch and would make the arm depend on
   which view of an exchange the citing Receipt happened to record.
   `record_test_action`
   refuses the first two at the citation site as well, so a run is stopped when
   it tries rather than when it closes, and it refuses a fourth thing the
   trigger cannot see: a Receipt of this run's own that answers a different
   request than the action states. The method, scheme, host, port and path on
   the row are compared against the planned url, so a run that performed its
   actions out of order, or performed one twice, cannot file the wrong exchange
   under a planned ordinal and produce a differential between two requests
   nobody planned to compare. `check_test_replays` reports from the other end,
   over rows that are already stored: a replay whose Tool run ended and wrote no
   Test run, a claim left in `testing`, a Receipt cited across Lanes, a
   conclusion resting on no Receipt at all, and a stored specification the
   current shape rule would no longer accept.
   `test_a_receipt_from_another_tool_run_is_refused`,
   `test_an_agent_lane_receipt_is_refused_at_both_places_it_could_arrive`,
   `test_a_receipt_naming_another_programs_artifact_is_refused`,
   `test_a_receipt_that_answers_another_action_is_refused` and
   `test_the_refused_rows_are_not_there`. The last arm of the check has a
   negative control of its own in `NegativeControlTest`: a replay whose Tool run
   closed as a success and left no Test run, which is work that was performed
   and billed with nothing anywhere saying what it found.

7. The settle is asked for, not attempted. 007 counts the Evidence a claim rests
   on and consults the skill's evidence profile before it lets one move, and the
   ordinary way a replay falls short is a control the door blocked: the shape
   rule makes every Test carry one, an action with no Receipt is an action that
   files no Observation, and a run can hold every assertion it stated and still
   be one short of what `testing -> supported` asks for. A refusal raised
   through `close_test_replay` would take the Test run and the Receipts that
   transaction just recorded down with it and leave the Tool run `running`,
   which is the one state no check reports — every one of them waits for a run
   that stopped — and which a retry would reach the same way. So the close asks
   first and settles `inconclusive` when the answer is no, with the refusal in
   the rationale and in `settle_refused` on the returned document, and the
   command reports the run as an error because a claim nobody settled is a Test
   somebody has to run again. Asking means the rule has to be a question as well
   as an exception, and it has to be the *same* rule: 015's guard is split, so
   `hypothesis_transition_refusal` is the verdict from the rule lookup onward
   and `enforce_hypothesis_transition` keeps only the two questions that need
   the row lock it takes — does the claim exist, and is it where the row says it
   is — and raises whatever the shared function returns, in the words 015 raised
   them in. A caught exception would have been the shorter way and is the wrong
   one twice over: it is a second answer to "may this claim move", and a plpgsql
   `EXCEPTION` block is a subtransaction, so every row written inside one is
   written under a subtransaction id that `check_event_log_integrity` cannot
   match against the event the trigger wrote — the settle would have reported
   itself as an unaccounted write.
   `test_a_run_that_holds_on_too_little_evidence_settles_inconclusive`,
   `test_the_refused_settle_still_closes_the_tool_run`,
   `test_the_claim_records_what_was_asked_for_and_what_was_settled`,
   `test_the_receipts_the_refused_settle_walked_over_are_still_cited` and
   `test_a_settle_that_was_not_refused_says_nothing_about_a_refusal`.

8. A new Lane is a new way to be invisible. Every standing rule about egress was
   written when `agent` was the only Lane a request could be made in, and each
   says so in a predicate, so a replay's Receipts — egress by every other
   measure — would go unread by all of them. Five are re-created with the Lane
   widened to the pair and nothing else changed: `receipt_integrity`'s arms for
   a request with no Tool run behind it, one made after the gate said no and one
   whose Lane disagrees with its run's; `egress_budget`'s count against the
   Program's widest budget; `transport_claims`' one-sided handshake; and the two
   CHECKs that say the same things at write time —
   `receipts_served_agent_needs_tool_run` and
   `receipts_agent_transport_records_both_sides`. Both keep their names, because
   022 and 20260811T210000Z look them up by name to assert the guarantee
   statically and a rename would be an edit to two other tickets' checks to make
   them say what they already say. `proxy_internal` stays outside all five for
   the reason 042 gave: the proxy fetching its own CSRF token is not a request
   this harness made, and it is not evidence either.
   `test_a_replay_receipt_with_no_tool_run_behind_it_is_reported`,
   `test_an_allowed_replay_receipt_naming_no_tool_run_is_refused_outright`,
   `test_a_replay_receipt_carrying_one_side_of_the_handshake_is_refused`,
   `test_the_two_write_time_rules_name_the_replay_lane_as_well` and
   `test_every_rule_that_reads_the_lane_reads_both_of_them` — the last two are
   read off the catalogue rather than provoked, because a rule that is a CHECK
   cannot be reached by writing the row it forbids and the budget arm would need
   the Program's whole allowance spent to report anything.

## The runtime half

`src/redkraken/replay.py` and `rk test replay` are the operator's way in, and
three properties of the module are the point of it. The Lane is passed nowhere:
the module opens the replay and spends the capability that comes back, and if it
sent a request under a capability minted some other way, `record_test_action`
would refuse the Receipt rather than record it under the wrong Lane. The outcome
is decided nowhere in it: `close_test_replay` derives it, so a run that could not
reach the target and a run whose assertions failed are told apart by the database
rather than by whatever the process concluded. And nothing in it chooses a url, a
method or a role — all three come out of the plan, which is why the command line
has no url on it. What the module contributes to an outcome is only which actions
it managed to record, and an action it could not record leaves an assertion
unevaluated, which is what makes the run inconclusive.

A refutation is not a failure of the command: the Test ran, the door let it
through and the claim is answered, so `refutes` exits 0 and names the assertions
that did not hold, while `inconclusive` exits non-zero, because a Test that
settled nothing is a Test somebody has to run again. Every way out of an opened
replay closes it, including the ones that raise, because an open replay whose
Tool run ended is the one state `check_test_replays` reports as a fault rather
than as history. An https Test with no trust root is refused before it sends
anything: the door presents a certificate for a host it does not own, and
believing it on any other ground would make the process indifferent to who was on
the path.

`ReplayCommandTest` drives the module end to end through a real `proxy.listen`
door with the proxy role behind it — a Test that holds, one the target refutes,
one the scope refuses before a packet leaves, and one https Test with no root —
and `test_cli.ReplayCommandTest` covers the command line down to the point where
a database and a door are needed.

## What is not covered

An assertion vocabulary of four kinds — `status_equals`, `status_differs`,
`body_equals`, `body_differs` — which is what the four columns a Receipt already
carries can answer honestly. A header assertion, a timing assertion or a body
substring needs something a Receipt does not hold today: the transcript is
content-addressed and only the digest is on the row, so `body_equals` is a digest
comparison and there is no way to ask "does it contain X" without reading bytes
this function has no business reading. Widening it is one array and one CASE arm
in `evaluate_test_assertions` on the day a Receipt carries the fact to compare.

A Test also cannot state an expected body, only that two answers agree or differ.
That is deliberate for the same reason `body_equals` compares digests: an
expected body is a literal in a specification that a target legitimately changes,
and a Test that goes inconclusive every time a footer moves is a Test nobody
runs twice.
