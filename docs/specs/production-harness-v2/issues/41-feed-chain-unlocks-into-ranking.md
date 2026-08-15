# 41 — Feed sound chain unlocks into Task ranking

**What to build:** Turn missing requirements on sound kill-chain paths into auditable candidate Tasks and include their marginal unlock value in the existing deterministic ranking.

**Blocked by:** 26 — Rank Tasks by value, cost and unlock; 40 — Build and evaluate a sound kill chain.

**Status:** resolved

- [x] The runtime derives candidate Tasks only from sound chain requirements and current Surface subjects, not from arbitrary model-written edges.
- [x] Each derived Task records the chain members and capabilities it would unlock without claiming that it will succeed.
- [x] Marginal unlock counts only newly reachable sound paths and avoids double-counting shared downstream Findings.
- [x] Invalidating a member, pivot or scope condition removes its unlock contribution on the next Ranking pass.
- [x] Direct value, probability, cost and safety still constrain ranking; unlock cannot bypass eligibility or Rules of Engagement.
- [x] Fixtures prove that a useful low-cost pivot can outrank an isolated Task while an unsound proposed chain contributes zero.

## How each is met

1. **The frontier is one query, and every row it can produce comes from a chain
   that still holds and a stamp that still stands.**
   `rk2_chain_unlock_frontier` begins at
   `rk2_chain_unsoundness(program, chain) IS NULL` -- 040's sentence, asked
   rather than re-worded -- and reaches the stamp that would JOIN through
   `rk2_pivot_refusal(program, stamp.tool_run_id) IS NULL`, which is 039's. The
   second is not the first restated: the stamp is nobody's step, so rejecting the
   Finding under it leaves every chain sound and leaves the stamp row exactly
   where it was, and a frontier reading `pivot_stamps` alone would go on paying
   for a member somebody withdrew. Everything after those two reads only rows a
   model cannot write: `chain_steps`, `pivot_stamps`, and `tests.pivot_provides`, which
   039's trigger derives from the specification an operator's impact grant was
   over. There is no argument for a capability, no table an agent may insert an
   unlock into, and `derive_chain_unlocks` takes no parameters at all: it is the
   Program it is bound to and nothing else. The Surface half is `e.in_scope` on
   the candidate's own subject and `h.superseded_by IS NULL` on its claim, so a
   Test about a subject the policy no longer covers is not on the frontier and
   the Task the last pass minted for it is abandoned `out_of_scope` by step (2)
   of the next one.

2. **Four names and no fifth column.** `task_chain_unlocks` is (task, chain,
   capability, member) with the stamp that wants the capability beside them, and
   the columns that are ABSENT are the criterion: no probability, no expected
   value, no confidence, no verdict, no "would succeed". The row says what
   becomes reachable if the capability arrives; whether it arrives is what
   running the Task finds out. `test_an_unlock_row_is_four_names_and_carries_no_prediction`
   asserts the whole column list, in the shape 040 used for the same claim about
   chains -- a prediction has nowhere to be stored, which is shorter than any
   rule forbidding one. There is no `basis` column either: 026 needed a
   vocabulary because a model's opinion and a derived rule compete for its slot,
   and here there is one kind of row and no way for a model to state one.

3. **The share is over members, and the division is over Tasks.**
   `chain_unlock_for` sums `SELECT DISTINCT u.finding_id, weight/tasks` -- so two
   chains waiting on the same member through the same Task pay for that member
   once, which is the "shared downstream Findings" half; and the weight is
   divided by the count of pending Tasks whose rows name that member, which is
   026's own rule about a dependent's value being shared rather than paid to
   each. "Newly reachable" is the frontier's `cardinality(missing) = 1`: a stamp
   the chain already satisfies is missing nothing and is not on it
   (`test_a_capability_a_chain_already_has_is_not_something_to_unlock`), and a
   stamp two capabilities short is not one hop away
   (`test_a_stamp_two_capabilities_short_is_never_on_the_frontier`). The currency
   is the member's severity band through `severity_unlock_weights`, and only
   where `severity_basis <> 'undetermined'` -- the `info` / `undetermined` pair
   `open_finding` writes is a default rather than an assessment, and a queue that
   paid for it would be paying for the act of opening a Finding.

4. **Withdrawal is the complement of the frontier, and names none of the ways a
   chain can stop holding.** 026 enumerated its withdrawal predicate because its
   derivation is two hand-written rules with no single expression behind them;
   this one has such an expression, and the list it would replace has six entries
   every one of which is a second wording of a clause in the frontier, free to
   drift the day the frontier is edited. So a member invalidated, a pivot 039
   would no longer stamp, a moved scope version, a withdrawn Identity, a denied
   subject and a review gate each make `rk2_chain_unsoundness` return a sentence,
   which drops the chain out of `sound`, which drops every row under it out of
   the frontier, which deletes them -- and `derive_chain_unlocks` says none of
   that. The same holds one step further out, for the stamp the candidate would
   JOIN: it belongs to no chain, so no chain becomes unsound when it stops
   standing, and the `standing` CTE asks 039's own refusal sentence and the
   Program's scope version of it instead. The case moves three of them and
   asserts the rows go: a subject off the Surface
   (`test_a_candidate_that_leaves_the_surface_gives_its_share_back`), a member
   withdrawn (`test_an_invalidated_member_takes_every_unlock_under_it_with_it`),
   and the member under the stamp that would JOIN withdrawn
   (`test_a_pivot_that_would_no_longer_be_stamped_stops_being_worth_reaching`),
   which is the case where every chain in the Program stays sound and the rows
   have to go anyway.

5. **An unlock constrains a value; it cannot be one.** The candidate Tasks
   `derive_chain_unlocks` mints carry NULL estimates on purpose -- what a Task is
   worth on its own is the model's sentence, and a runtime that filled it in
   would be inventing the one number this criterion relies on. `value_for` is
   NULL for those Tasks and `rank_pass` writes `priority = NULL`, so a Task with
   four unlock rows under it and nobody's estimate on it sinks under NULLS LAST
   (`test_an_unlock_cannot_rank_a_task_nobody_has_estimated`). The chain unlock
   is added to 026's direct unlock inside its cap and multiplied by the same
   `w_unlock`, so it shares the ceiling rather than reaching past it. That
   summand is zero for every Task on this frontier and the test says so rather
   than pretending otherwise: `unlock_for` counts `task_dependencies` rows whose
   basis is `sound`, only `runtime_rule` is sound, and both of 026's rules derive
   edges whose UNLOCKER is a `recon` or a `validate` Task -- a candidate is a
   `hunt`. So `test_the_chain_unlock_is_the_whole_of_the_unlock_and_stays_under_the_cap`
   asserts `direct = 0`, `chain = chain_unlock_value` and
   `unlock_value = least(direct + chain, 1.0)` together, which states the cap is
   shared without claiming a sum nothing has ever exercised. And
   `cancel_reason_for` runs in step (2) of the same pass, before anything is
   scored, so an unlock cannot keep alive a Task the Program budget, the scope,
   the attempt count or a settled negative would have cancelled.

6. **Three hunt Tasks in one Program, and the lead changes twice.**
   `ChainUnlockTest` stamps five pivots, composes two chains, and states two
   unrun Tests claiming the one capability both chains are short of. The isolated
   Task promises MORE on its own -- 0.30 against 0.20 -- so nothing but the
   unlock term can put a candidate in front of it, and
   `test_the_three_tasks_differ_in_nothing_but_what_they_unlock` asserts the
   other five components are equal across all three before
   `test_a_useful_low_cost_pivot_outranks_a_task_no_chain_is_waiting_on` reads
   the ordering. Then the members are withdrawn and the isolated Task takes the
   lead back, which is the half a single pass could never show. The unsound
   proposal is stronger than a zero: `build_kill_chain` refuses it outright, so
   there is no chain for a frontier to read at all, and the assertion is the
   refusal sentence naming the step and the capability nothing supplies.

## What this ticket also changed

- **`rank_pass` gained one step and one component.** `derive_chain_unlocks()` is
  step (3b), after the dependency edges and before the ranking: after, because a
  Task abandoned in step (2) must stop unlocking anything; before, because a row
  derived now has to be visible to this pass rather than the next. Not folded
  into `derive_task_dependencies` -- that function is 026's two rules over
  `ready_for` and this one creates Tasks, and a derivation that both restated a
  readiness predicate and minted rows would be two jobs sharing a name and a
  transaction-local licence.
- **`tasks.chain_unlock_value` is its own column beside `unlock_value`.**
  `unlock_value` stays the number the priority is computed from -- the two
  unlocks summed under one cap -- and the new column is what the audit reads, so
  `task_rank_factors` can say which of the two a priority came from. Without it
  the two terms are indistinguishable after the fact, and 026's criterion 1 is
  that a stored priority has its components stored beside it.
- **A severity band is worth a number to the queue, and that is a policy.**
  `severity_unlock_weights` is reference data in its own table rather than a CASE
  inside `chain_unlock_for`, because a scheduling ratio over 009's ordinal bands
  is a decision an operator may want to see and a migration may want to change.
  Registered in `program_global_tables` and exempt from the event rule as
  reference data, and arm (e) of `check_chain_unlocks` asks the drift question
  the second table created: a Finding carrying a band with no weight beside it is
  a member that has silently stopped counting. The grants are `REVOKE UPDATE,
  DELETE` and not `REVOKE INSERT, UPDATE, DELETE`, which is 029's own idiom for a
  reference table (`20260811T170000Z`, "Two verbs rather than all of them"):
  `check_runtime_connection` requires INSERT on every managed table, so revoking
  it turns a locked-down table into a runtime that will not start. INSERT is the
  inert direction here anyway -- severity is the primary key and 009 fixes the
  five bands, so there is no sixth row to add.
- **The first draft priced an unlock in CVSS and would have paid nothing,
  always.** `findings.cvss_vector` is NULL on every Finding this harness has ever
  opened -- 038 states a severity band and a basis, and the vector is a v1 column
  nothing in v2 writes. The band is the number the harness actually has.
- **`check_chain_unlocks` joins the standing checks.** Five arms: a stored row
  the frontier would not derive, a row under a settled Task, a pending Task
  scored a chain unlock with no row accounting for it, a frontier that has
  stopped consulting `rk2_chain_unsoundness` or `rk2_pivot_refusal`, and a
  severity band a Finding carries with no unlock weight beside it. Arm (c) is
  about the pending Tasks because 026 clears `priority` when it abandons a Task
  and leaves the components where they are -- the priority is an instruction and
  the components are a measurement, and this column is a component. Arm (d) names
  two callees because the frontier asks soundness of two different things, and
  losing the second is the quieter loss: every chain still holds while a
  withdrawn member goes on paying.
- **The shape of the Ranking pass became a table.** Three of 026's arms are about
  a LIST of function names rather than about ranking -- no step reads the clock,
  no scheduler function is callable by PUBLIC, and (new) no registered name has
  gone missing. 023 wrote that list into a check, 026 copied it and added four
  names, and this file would have been the third copy and the second author to
  have to remember. So `ranking_pass_functions` holds the thirteen names with an
  `in_the_pass` flag and an owning ticket, `check_task_ranking` is restated over
  it, and a ticket adding a factor registers it once. Two memberships and not
  one: everything listed is a scheduler function, and only the subset that runs
  inside a pass is forbidden the clock -- a standing check that could not ask
  what time it is would be a check with one hand tied. The cost of a registry is
  that it can empty itself quietly, which is what new arm (b2)
  `ranking_function_registered_but_absent` is for.
- **`ChainFixture` was extracted between `PivotStampFixture` and
  `KillChainTest`.** Stamping a set of pivots on their own routes and composing
  them is 040's arrangement and 041's premise, so it is one class rather than two
  copies. Not hoisted into `PivotStampFixture`, because 039's case owns
  `pivot_spec`, `stamped` and `stamp` for three other things -- a Test's optional
  block with one part replaced, the one stamp it issued, and the row behind it --
  and a subclass that has to override most of what it inherits is the smell the
  extraction exists to avoid.
- **`ChainFixture.re_addressed` takes an optional path.** `scope_class_of`'s
  inclusion arm needs both spellings of the path under the rule's prefix, and
  `VALID` includes `app.example.com` under `/api/` -- so a subject given that host
  and the default `/` is `denied` rather than in scope, which is the right answer
  to the question asked and not the one a case putting a subject on the Surface
  wants. The parameter defaults to NULL and both path columns are written through
  `coalesce($5, ...)`, because they are NOT NULL and there is therefore no "no
  path" to write: 040's two callers, which move a host and mean nothing by the
  path, go on writing exactly what they wrote before.

## What is not covered

- **No verb is served to a model, and there is no CLI.** The frontier and the
  derivation are called by `rank_pass` and by the tests. Which candidate to run
  is the ordinary scheduling decision, made over the Slate like any other.
- **The candidate Task is minted, not planned.** `derive_chain_unlocks` creates a
  `hunt` Task on the frontier's hypothesis and stops. Nothing decides which
  Identity it should run as, whether it needs an impact grant, or what its
  estimates should be -- the last of those on purpose, since it is the number
  criterion 5 depends on being somebody else's.
- **One hop, and no plan to make it two.** A chain two capabilities short pays
  nothing even when both are claimed by Tests, because a path whose first step
  nobody has demonstrated is a story. Whether a second hop is worth a discounted
  weight is a question for a ticket with measurements behind it.
- **The share is over pending Tasks at the moment of the pass.** A candidate
  claimed and running still counts, and one abandoned between passes stops
  counting on the next -- so a member's weight moves between the Tasks that could
  reach it as the queue changes. That is the intent, and it means a priority is
  only comparable within one pass, which was already true of every other
  component.
- **`chain_unlock_the_frontier_no_longer_supports` cannot be reached through the
  pass.** The derivation withdraws exactly what the arm looks for, so the arm is
  about rows that arrived some other way -- a restore, a partial purge, a repair
  -- which is what a standing check is for.
- **A candidate abandoned `out_of_scope` never comes back.** Step (1) mints a
  Task only where no `hunt` Task on that hypothesis exists in ANY status, so a
  subject that leaves the Surface and returns is not re-proposed: the abandoned
  Task is still there, blocking the mint. That is deliberate for now -- reviving a
  settled Task is a status transition nothing in 026 licenses -- and it means a
  policy change that widens the scope back does not re-open the queue by itself.
- **The stamp that would JOIN is asked 039's question and not 040's other six.**
  `standing` asks `rk2_pivot_refusal` and the Program's scope version, which
  between them cover the run, the grant, the Program status, the member's
  disposition, the Receipt, the artifacts and the identity slot. It does not ask
  the invalidated-Identity, denied-subject, `known_issue` or `duplicate` arms
  `rk2_chain_unsoundness` asks of a step, because those are questions about a
  chain's step and this stamp is nobody's step yet. A candidate can therefore be
  worth reaching for one pass past the moment its target stopped being reachable
  -- and then the chain that would have absorbed it fails 040's check the instant
  it does become a step.
- **`tests.pivot_provides` is model-authored, and the share divides by count.**
  Two Tests claiming the same capability halve each other's share whether or not
  either is serious, so a model that states many thin pivot Tests dilutes a
  genuine candidate rather than promoting itself. The direction is the safe one
  and the ceiling is 039's -- a capability only pays once the stamp behind it is
  real -- but nothing here prices a claim by its author.
- **A moved scope CONDITION is covered only through `rk2_chain_unsoundness`.**
  The fixture moves a subject off the Surface and moves a Program's scope
  version; it does not build a chain whose step depends on a condition that later
  changes and leave the members alone. 040's case owns that arrangement and this
  file inherits the answer rather than re-staging it.
