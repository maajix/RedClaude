# 37 — Validate a Finding through a blind validator

**What to build:** Give an independent validator only the canonical reproduction packet for one candidate Finding and let database rules decide whether its closed verdict can validate the Finding.

**Blocked by:** 18 — Compile and enforce the six-role roster; 36 — Create a candidate Finding from a supported Hypothesis.

**Status:** resolved

- [x] The validation packet is built from an empty structure by a positive column allowlist over Finding, Hypothesis, Test, Test-run, Receipt and Artifact facts.
- [x] Hunter reasoning, transcripts, prompts, pending-decision prose and unrelated Program data have no field or tool path into the packet.
- [x] The validator runs as a fresh top-level session with no network, shell, source, Artifact browsing, Skill or delegation tools.
- [x] Its only output is confirmed, refuted or insufficient plus closed failed-assertion identifiers.
- [x] The verdict is stored as input while database constraints independently enforce the Finding transition.
- [x] A smuggled field, foreign Receipt, missing holding replay or changed Artifact makes validation fail closed.

## How each is met

1. **The packet is an allowlist.** `validation_packet_columns` is a table: one
   row per column any packet field may come from, with the packet key it
   becomes. `rk2_validation_packet(program, finding, replay)` is `BEGIN ATOMIC`,
   so its read set is in `pg_depend`, and the migration asserts at apply time
   that the columns it reads are exactly the ones the table names -- a column
   added to the function without a row is a migration that will not apply.
   `test_the_packet_is_exactly_the_keys_the_allowlist_names` closes the other
   half: the keys that actually arrive are the keys the table declares, so a
   named column that produces no field is caught too.

2. **No prose has a path in.** The blindness guard in the migration walks
   `pg_depend` for every relation the packet function reads and refuses to apply
   if any of `proposals`, `proposal_drops`, `finding_proposals`, `agent_runs`,
   `agent_sessions`, `orchestrator_sessions`, `hypothesis_transitions` or
   `pending_decisions` is reachable -- and raises if one of those names stops
   being a relation, so the list cannot rot into a check of nothing.
   `BlindValidationTest` writes the hunter's title and claim as literals and
   `ValidationCommandTest.test_neither_the_hunters_title_nor_its_claim_reaches_the_session`
   searches the whole request -- packet, objective and all -- for both.

3. **A fresh top-level session.** `open_validation_session` opens a Task and a
   parent-less `agent_runs` row with an empty mission packet, at the roster's
   model and effort for `validator`. The tool group `validate.judge` is
   `get_validation_packet` and `submit_verdict` and nothing else, which the
   roster closes and `agent.SERVED_GROUPS` serves.
   `test_the_session_is_handed_a_packet_and_nothing_else_to_reach_with` asserts
   the request carries no state packet, no capsule and no egress.

4. **Three words and a closed vocabulary.** `verdicts.verdict` is a CHECK over
   the three; `enforce_verdict_input` refuses an assertion identifier the
   Finding's Test does not state, and a `confirmed` verdict that names a failure
   at all. `record_verdict` asks the same three questions first and answers them
   with a sentence rather than an exception, because a child picks its own word
   and its own identifiers: a raise would abort the transaction that closes the
   attempt and strand the Finding under a session that has stopped.
   `test_the_verb_refuses_what_the_trigger_would_raise_about` asserts both the
   sentences and that the arrangement is exactly as the refusals found it.

5. **The verdict is input.** `record_verdict` writes the row and then asks for
   the transition; `enforce_finding_validation` independently re-derives what
   status that word implies, refuses a move with no verdict behind it, a move to
   a status the verdict does not imply, and a `validated` Finding pointing at any
   run other than the one its validation was opened against.
   `test_a_finding_cannot_be_moved_out_of_judgement_by_hand` drives all three by
   hand and reads the sentences back.

6. **Fail closed.** `rk2_validation_refusal` is the one place that says why a
   packet may not be served, and `open_validation` files a `refused` attempt with
   that sentence rather than serving anything: no request, the birth run, another
   Test's run, another Program's, a run on any Lane but `replay`, an unfinished
   run, one whose Receipts include a foreign Lane, a Finding that is no longer a
   candidate, and a purged Artifact. `refuse_what_cannot_be_served` causes each
   one. The changed Artifact in the general case is the digest: the attempt keeps
   `packet_sha256`, `record_verdict` rebuilds the packet and compares, and a
   verdict about a document that would now read differently is `stale` --
   recorded on the attempt, with the word it said, and acted on by nobody.

## What this ticket also changed

- **012's completion question grew a second arm.** A validator promotes no
  proposal, so `task_result_accepted(task)` now answers "promoted proposal, or an
  answered validation", and the trigger, `finish_task_attempt` and 020's standing
  check `check_execution_closure` all ask through it. The check mattered: left
  asking about proposals it would have reported every validation this ticket
  closes as a leak.
- **`validation_attempts.refusal` may now be set on a `stale` attempt**, which is
  where the word a session answered about a moved document is kept.
- **`rk finding validate` is the ask.** The command runs `request_validation`
  itself: 011 built the queue as the request, every verb below refuses a Finding
  nobody asked about, and an operator naming one Finding on the command line has
  said exactly what the queue records.
- **`reject_validation_attempt_rewrite` holds `agent_run_id` immutable**, with
  the rest of what was true when the attempt opened.

## What is not covered

- **`mcp__rk2__request_validation` is not served to anybody.** The verb exists
  and the CLI calls it; deciding to validate a Finding is the orchestrator's
  step, and the tool it makes that step through belongs to the orchestrator
  dispatch ticket.
- **The duplicated Artifact walk in `rk2_validation_packet` stays duplicated.**
  Both halves of the `CROSS JOIN LATERAL (VALUES (r.request_agent_sha),
  (r.response_agent_sha))` read are spelled out where they are read. Extracting
  the walk into a helper would take those columns out of the function's own read
  set, and the read set is what the `pg_depend` allowlist assertion is made of:
  the refactor would silently delete the check that criterion 1 rests on.
- **What a model actually decides is not tested.** `ValidationCommandTest` drives
  a real `_launch.Judgement` around a real packet and answers through it, so
  everything either side of the decision is exercised -- the document crossing
  the boundary, the label check, the latch, the answer travelling back. The
  decision itself is not a thing a test can have.
