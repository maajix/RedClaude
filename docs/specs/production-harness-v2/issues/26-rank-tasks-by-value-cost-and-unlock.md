# 26 — Rank Tasks by value, cost and unlock

**What to build:** Give the scheduler an auditable priority that balances expected finding value, success probability, time, safety cost, novelty and dependency unlock.

**Blocked by:** 23 — Offer and claim a deterministic Slate.

**Status:** resolved

- [x] Each rank result exposes normalized value, probability, estimated time, safety cost, novelty, direct unlock and weights-version components.
- [x] The formula and tie-breakers are deterministic for the same canonical rows.
- [x] A low-cost Task that provably unlocks several valuable ready paths can outrank a higher isolated score.
- [x] Unsupported or unsound dependency edges contribute zero unlock value rather than a guessed penalty or benefit.
- [x] Operator-configured weights are versioned and changing them creates a new Ranking pass without rewriting historical passes.
- [x] Fixture scenarios cover greedy ranking, unlock ranking, equal scores, missing estimates and bounded fallback defaults.

## Comments

Implemented on 2026-08-13, in one migration --
`20260813T235500Z__rank_by_value_cost_and_what_it_unlocks.sql` -- and nothing
else. No Python changed: `execution.py` issues `rank_pass('runtime')` and
`offer_slate()` and passes `factors` through as opaque JSON, which is what let
the formula gain four terms without a line moving above the database.

The shape is the 023 formula with two halves widened:

    priority = novelty * confidence * (value + w_unlock * unlock)
             / max(w_tokens*cost + w_time*time + w_safety*safety, cost_floor)

Under version 1's weights -- `w_unlock = 0`, `w_tokens = 1`, the other two zero
-- this is 023 character for character. Version 2 is what the installation runs
on, and it is created through the operator's own verb at the bottom of the file
rather than by an INSERT, so the first thing the versioning path does is the
thing this migration needed done.

### Why the numerator grew and the denominator did too

Value was already there under another name: 023 multiplied
`w_gain * expected_information_gain + w_impact * potential_impact` inline. It is
now `value_for(tasks, scheduler_weights)` and lands on `tasks.direct_value`,
because a component the criterion says must be exposed cannot be an expression
nobody can read back.

Cost was one number and is now three. `time_for` is `cost_for` over
`extract(epoch FROM (finished_at - started_at))` instead of tokens; `safety_for`
is the maximum `risk_rank(risk_class)` of an Agent run's Tool runs, divided by
three, averaged over the same window. Both shrink toward a prior with the same
`shrinkage_n0`, and both are bounded into `[cost_floor, 1]` the way cost is.

The Agent run is the unit for all three deliberately. Safety could have been
measured per Tool run, and then `shrinkage_n0` would mean "runs" in two of the
three terms and "tool calls" in the third -- one number with two meanings, which
is the shape of a constant nobody can tune.

### Unlock is a table, not an inference

`task_dependencies` is the edge, `task_dependency_bases` is what makes an edge
count. Two bases ship: `runtime_rule` is sound, `proposed` is not, and
`unlock_for` joins the basis table and filters on `sound`. That join is the
whole of criterion 4. Without it every edge is worth its full value, and the
edges a model can write are the ones that would be worth the most.

Two rules derive edges today, both from `ready_for`'s own vocabulary:

- an analyze Task reporting `analyze.no_agent_visible_artifact`, unlocked by a
  pending recon Task on the same `subject_entity_id`;
- a report Task reporting `report.no_validated_finding`, unlocked by any pending
  validate Task in the Program -- not per subject, because the predicate is
  asked of the Program.

`derive_task_dependencies` withdraws before it derives, and `rank_pass` calls it
as step 3. An edge the pass does not refresh is one the pass keeps paying for:
the unlocked Task gets abandoned, the unlocker keeps the credit, and the
scheduler spends the rest of the engagement on reconnaissance for a question
nobody is asking any more. Withdrawal fires on three conditions -- the blocked
Task stopped being pending, the unlocker stopped being pending, or the predicate
the edge names is no longer the one the blocked Task reports.

`UNIQUE (task_id, unlocked_by_task_id, basis)` and not `(task_id,
unlocked_by_task_id)`. With the pair, a `proposed` edge written first occupies
the slot and `ON CONFLICT DO NOTHING` silently declines to derive the sound one
-- a model suppressing a real unlock by claiming it. With the basis in the key
both rows exist, `unlock_for` counts the sound one, and `SELECT DISTINCT b.id`
keeps the blocked Task from being counted twice.

The sum is capped at 1.0. Uncapped, a Task that unblocks twelve things outranks
everything for the rest of the engagement regardless of what it costs.

### Weights are a version and versions are not rewritten

`scheduler_weights_is_immutable` refuses UPDATE and DELETE on the row, with one
exception: the `active` flag, which is how a version stops being the current one.
The comparison is `to_jsonb(NEW) - 'active' IS DISTINCT FROM to_jsonb(OLD) -
'active'`, so a column added by a later migration is covered without that
migration knowing this trigger exists.

`version_scheduler_weights(jsonb)` is the only way to change them: copy the
active row, apply the named changes, insert as the next version, deactivate the
old one. It validates keys against `pg_attribute` first, because
`jsonb_populate_record` ignores an unknown key silently and the new version would
otherwise be a copy of the old one wearing a new number.

The verb takes three grant statements and not two. 029 set `ALTER DEFAULT
PRIVILEGES FOR ROLE rk2_owner ... GRANT EXECUTE ON FUNCTIONS TO rk2_runtime`, so
every function this file creates arrives with the runtime already on its ACL and
`REVOKE ... FROM PUBLIC` does not take it off. "Granted to `rk2_human` alone" was
false in the installation until the explicit revoke was added, and the test that
asserts the runtime is refused is what found it. Arm (h) of the check keeps it
true, because a later DROP/CREATE of the function would re-apply the default.
The same default has already given `rk2_runtime` EXECUTE on 026's
`answer_decision`; that is a separate hole and not this ticket's to close.

### The check

`check_task_ranking()` has eight arms. Three are textual and guard code:
Decision 12's no-clock rule extended to the four new factors, no scheduler
function executable by PUBLIC, and `unlock_for` still naming
`task_dependency_bases`. Two are about the vocabulary and the grants: a basis
table that has lost either answer, and the weights verb reachable from a
model-facing role. Three are about rows: a stored priority with no weights
version beside it, a stored priority with a component missing under it, and a
runtime-derived edge whose predicate the blocked Task no longer reports.

Arms (e) and (f) key on `priority IS NOT NULL` rather than on the Task being
pending. A Task with a missing model estimate has a NULL priority and NULL
`direct_value`, and the runtime still measures everything it can measure about
it -- that is criterion 6's case, not a violation.

Not an arm: recomputing the formula and comparing. The components and the
weights version are on the row, so a priority is reproducible by anyone who
wants to; a check that re-multiplied them would fail on the ordinary skew
between a stored `numeric` and the same expression evaluated again, and would
have to be tuned with a tolerance nobody can justify.

### The test

`TaskRankingTest` is seven Programs, one per disturbance, in the shape 23 and 25
established: everything commits in `setUpClass`, the assertions read what the
passes left, and the Programs are purged at the end. `SchedulerFixture` gained
`operator()`, because the weights verb is `rk2_human`'s and a test that versioned
them as the owner would exercise a path no operator has.

The unlock scenario is ranked three times and not once. A single ordering is
consistent with the unlock term doing nothing: the claim is that the same two
recon Tasks change places when the edges appear and change back when they are
withdrawn, and only three passes say that.

`reweighted` is a second copy of that scenario kept intact, because the weights
scenario needs live sound edges under it. Re-ranking the first one would have
proved that zeroing `w_unlock` changes nothing about a Program whose unlock term
was already zero.

The three blocked analyze Tasks each carry a Hypothesis of their own, which
`ready_for` does not read. `tasks_live_dedup_idx` is unique over `(program, kind,
subject, hypothesis, finding)` with NULLs not distinct, so three live analyze
Tasks about one subject are three rows the schema calls one; and
`hypotheses_dedup_idx` then needs three property classes for the same reason one
layer down.

`ordering()` filters by kind. The blocked analyze Tasks are worth 0.9 each and
lead any ordering that includes them, which says nothing -- they are unready and
`rank_candidates` will never offer them. The claim is about the two recon Tasks.

Two Controls, both structural: `unlock_for` rewritten without the basis join,
which is the one edit that makes every proposed edge move a priority; and the
grant on the weights verb that 029's default privileges would have made on their
own.
