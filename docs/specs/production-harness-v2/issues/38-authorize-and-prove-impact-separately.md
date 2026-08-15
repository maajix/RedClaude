# 38 — Authorize and prove impact separately

**What to build:** Turn an already validated detection into a separately authorized impact or exploitation Test so demonstrated impact can never be inferred from banners, errors or model confidence.

**Blocked by:** 29 — Deliver pending decisions, Halt and resume verbs; 35 — Execute a structured Test through the replay Lane; 37 — Validate a Finding through a blind validator.

**Status:** resolved

- [x] Impact work is a new Task and immutable Test with an explicit risk class, expected side effect, cleanup and applicable operator grant.
- [x] Missing or mismatched grant parks the Task for a human before any target request.
- [x] Detection validation remains unchanged when impact execution is refused, inconclusive or unsafe.
- [x] Demonstrated impact requires its own holding Test run, Receipts, after-state and cleanup evidence.
- [x] Availability impact, third-party effects and out-of-scope pivots remain refused even when a lower-risk Finding is validated.
- [x] Severity inputs distinguish demonstrated impact, constrained inference and program context with an auditable rationale.

## How each is met

1. **Its own Task and its own Test.** `open_impact_task(finding, spec)` refuses a
   Finding that is not `validated` and writes two rows: a `tests` row whose spec
   carries the new optional `impact` block and whose `impact_class` column is
   read out of it, and a `hunt` Task naming the Finding. The block is four
   fields and `rk2_impact_problem` refuses every other shape -- a class that is
   not in `impact_classes`, missing effect or cleanup prose, an `after_state`
   ordinal the Test does not perform, an after-state no assertion reads, and an
   empty `cleanup` list. 035's spec digest already makes the Test immutable, and
   the grant is over that digest: `rk2_impact_digest` is class, Finding, Test,
   `spec_sha256`, scope version, the hosts the plan would reach, the Identity
   slot the run would hold, and the effect and cleanup sentences themselves --
   so an approval covers the specification the operator was shown and no other,
   and stops covering it the moment any of those moves.

2. **No grant, no request.** `open_impact_replay` asks `live_grant_for` for an
   approval over the digest before `rk2_replay_plan` and `rk2_open_replay` are
   called at all. With none it files the question through
   `rk2_ask_about_impact`, parks the Task, releases the leases, ends the run as
   `parked` and returns -- with no `tool_runs` row, so no capability, so nothing
   the door would let through. Two rules hold the park to the question rather
   than to the opener's habits: `pending_decisions_impact_names_a_task` is a
   CHECK that an impact question names a Task at all, and
   `pending_decisions_impact_parks_a_task` is a deferred constraint trigger that
   the named Task is parked on this very question by the time the transaction
   commits. Deferred because the question is filed and the Task parked in two
   statements, so the row is legitimately wrong in between.
   `test_no_grant_means_no_tool_run_and_so_nothing_that_could_be_sent` reads the
   Tool-run count, the Receipt count, the Task status, the run's stop reason and
   the lease count after the park; `replay.run` reports the same shape as a
   `decision` fact and a hold rather than a violation. A second run reaching the
   same wall joins the question already open instead of filing a copy: 026's
   unique index only covers approvals, and each park overwrites
   `tasks.pending_decision_id`, so a second copy would leave the first pointing
   at a Task that no longer pointed back.

3. **The detection is left exactly as validation left it.** `close_impact_replay`
   writes no transition, no Observation and no Evidence edge, and
   `record_test_action` no longer starts the claim `testing` when the run is an
   impact replay -- the flag it returns carries that condition, so the ticket-35
   path is unchanged and the impact path moves nothing at either end. Nobody can
   reach the other verb by mistake: `open_test_replay` refuses a Test that
   states an impact, and `open_impact_replay` refuses one that does not. The
   migration asserts all three at apply time by reading `prosrc`, the standing
   check's two (d) arms report any impact run whose Receipts an Observation
   cites or a Hypothesis transition names, and
   `test_an_impact_run_settles_nothing_about_the_claim` re-reads the claim, its
   transitions, its Evidence and the Finding after four impact runs -- one that
   held, one whose cleanup failed, one that did not hold, and one that reported a
   cleanup it never performed.

4. **A demonstration is the conjunction.** `impact_demonstrations` is written
   only when the run's outcome is `holds`, the after-state action produced a
   Receipt, the cleanup was reported `done` *and* every request the Test states
   as its undo actually reached the target. That last one is the difference
   between a word and evidence: `p_cleanup` is the supervisor's account, and
   `close_impact_replay` counts the Receipts under this Tool run whose method
   and route match the specification's `cleanup` entries, refusing when fewer
   were sent than were stated. Anything else returns a `demonstration_refused`
   sentence naming which conjunct failed and writes nothing. The row cannot be
   made to say otherwise afterwards: `run_outcome` is a `holds`-only CHECK with
   a MATCH FULL foreign key onto `test_runs (id, outcome)`, `cleanup` is a
   `done`-only CHECK, `cleanup_receipts >= 1`, `receipts >= 1`, and the standing
   check's arm (e) reports any demonstration whose after-state Receipt is not
   one of its own run's recorded actions.

5. **Three classes nobody may grant.** `impact_classes` maps
   `degrade_availability`, `reach_third_party` and `pivot_out_of_scope` onto the
   `forbidden` risk class, which `pending_decisions_never_forbidden` refuses --
   so the question cannot be filed, and there is no answer that admits it.
   `open_impact_task` refuses the class when the Test is written and
   `open_impact_replay` asks again at the moment a request would be sent, because
   a migration can move a class between the two. Asking twice is the rule and
   saying it twice is not, so both call `rk2_refuse_forbidden_impact` and the
   migration asserts at apply time that exactly one function in the corpus words
   that refusal. `revalidate_decision` answers
   `now_forbidden` for a grant whose class has moved since it was given. The
   migration asserts there are exactly three such classes and that the constraint
   still exists, and the standing check's arm (a) reports a Test that states one.

6. **Severity is stated, with a basis.** `severity_statements` is append-only and
   `state_severity` is the only writer of `findings.severity`. The three bases
   are distinguished because each is refused for its own reason:
   `demonstrated_impact` with no demonstration, `constrained_inference` about a
   Finding that has one -- an inference is what you make when there is no proof,
   and calling it that when there is rests the severity on the weaker of two
   things somebody was holding -- and `high` or `critical` on nothing but
   `program_context`, which is a reading of a document rather than a claim about
   the target. A fourth word is refused outright. The rationale is 20 to 2000
   characters, the scope version in force is recorded, and
   `severity_statements_basis_names_its_evidence` makes the demonstration a
   condition of the demonstrated basis. `assert_severity_was_stated` refuses a
   hand-written UPDATE by re-reading the latest statement, `report_blockers`
   gains a hard `severity_unstated` and a soft `severity_scope_moved`, and arms
   (f), (g) and (h) of the standing check report a column that disagrees with its
   statement, a basis nothing ever stated, and a statement citing another
   Finding's demonstration.

## What this ticket also changed

- **035's two replay verbs were split rather than branched.**
  `rk2_replay_subject`, `rk2_replay_plan`, `rk2_open_replay`, `rk2_replay_offer`,
  `rk2_settle_replay` and `rk2_finish_replay` are what both openers and both
  closers are made of, so the ordering that makes 035 safe -- nothing sent before
  the scope walk, no capability before `test_replays` exists, the Tool run
  stopped last of all -- is written once. Each verb keeps only its own questions:
  the claim is `testable` and no replay of it is in flight for the detection
  pair, the grant and the Finding for the impact one.
- **One impact replay of a Finding at a time.** `open_impact_replay` refuses
  while another impact replay of the same Finding has a running Tool run. Not in
  the criteria: it is 035's own rule about a claim under test, carried over,
  because two concurrent runs writing to the same target are two runs neither of
  which can say what it left behind.
- **`pending_decisions` may be about a Test.** Both run columns became nullable,
  `test_id` joined them, and `pending_decisions_names_one_subject` requires
  exactly one subject. `assert_decision_closes_once` holds the new column
  immutable with the rest of the request half. 029 generated its column grants
  from the table as it stood, so `GRANT SELECT (test_id) ON pending_decisions TO
  rk2_runtime` puts the new column back inside that migration's rule of
  "everything but the answer".
- **`live_grant_for` came out of `gate_tool_call`.** 011's rule 5 is now one
  reading of what a standing grant is, asked by the gate and by the impact
  opener.
- **019's severity writer is gone.** `apply_computed_severity` set a band from a
  CVSS vector with no basis and no reason, and nothing ever called it.
  `apply_computed_cvss` keeps what it computed -- the vector is derived -- and
  the band it decided is now a judgement `state_severity` makes. `report_blockers`
  kept the vector half of its CVSS arm and lost the band half for the same
  reason.
- **`rk test replay --impact`.** One flag picks the pair of verbs; `replay.py`
  holds them in a `_Verbs` and nothing below that declaration asks which pair it
  is running, because the plan, the door, the walk and the report are identical.
  Both pairs stay in the `replay` Lane -- the Lane is 011's word for which door a
  Receipt came through, and this ticket added no door. The command reports a
  fifth fact, `decision`, on the park path.
- **`ValidatedFindingFixture`** carries the arrangement that walks a claim to a
  validated Finding, and `BlindValidationTest` and `ImpactProofTest` both sit on
  it.

## What is not covered

- **`close_impact_replay`'s "no Receipt answered the after-state" arm is
  unreachable through the front door.** `rk2_impact_problem` requires an
  assertion that reads the after-state action, so an action with no Receipt makes
  the run `inconclusive` and the outcome arm fires first. The arm stays because
  the two rules are enforced in different places and only one of them is a CHECK
  on the specification.
- **No verb is served to a model.** `open_impact_task`, `open_impact_replay` and
  `state_severity` are called by the CLI and by the tests. Which Finding is worth
  proving impact on is the orchestrator's decision, and the tool it makes that
  decision through belongs to the orchestrator dispatch ticket.
- **Nothing checks that the cleanup worked.** The rule is that the stated undo
  requests were sent and the door answered them; whether the target actually went
  back to the state the baseline read is a question only another Test could
  answer, and this ticket does not write one. A cleanup request that answered 500
  still counts as sent -- what stops that run is the supervisor reporting the
  cleanup `failed`, which is a report and not a measurement.
