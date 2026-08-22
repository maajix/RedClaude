# 120 — A Task never names the Skill it needs

**What to build:** A writer for the Task columns that bind a Task to a Skill and
to an evidence profile, or the decision that the binding is made elsewhere and
the columns come off the agent's read surface.

**Blocked by:** nothing.

**Status:** ready-for-agent

- [ ] The four writers of `tasks` are named and the gap is stated against them.
      `open_task`, `open_impact_task`, `open_validation_session` and
      `derive_chain_unlocks` are the only statements that `INSERT INTO tasks`,
      and between them they set `program_id`, `kind`, `subject_entity_id`,
      `hypothesis_id`, `finding_id` and `status`. `rank_pass` later UPDATEs the
      nine ranking terms. Nothing ever sets `skill_name`
      (`0015_epistemic_corrections.sql:148`), `skill_sha256` (`:149`),
      `skill_version`
      (`20260822T000000Z__a_skill_teaches_what_the_role_may_already_do.sql:318`),
      `required_skills` (`0012_scheduler.sql:21`), `evidence_profile_id`
      (`0015_epistemic_corrections.sql:178`), `expected_information_gain` or
      `potential_impact` (`0006_tasks_and_runs.sql:16-17`).
- [ ] Each consequence is closed or accepted in writing:
      `tasks_skill_sha256_check` and `tasks_skill_version_check` constrain a
      column that is always NULL;
      `tasks_skill_name_fkey -> skills(name)` never resolves, so the seeded
      `skills` rows are reachable only through `role_skills` and never through
      the Task that needs one;
      `tasks_evidence_profile_id_fkey -> evidence_profiles(id)` never resolves,
      and the four `evidence_profile_*` functions dispatch off
      `hypotheses` and `transition_rules.consults_evidence_profile` instead, so
      it is specifically the task-side half of that design that has no producer;
      `v_records` publishes `skill_name`, `expected_information_gain` and
      `potential_impact` to the model as `null` on every Task.
- [ ] The read surface matches the answer. `state_read_surface` grants
      `rk2_state` column SELECT on all six of `skill_name`, `skill_sha256`,
      `required_skills`, `evidence_profile_id`, `expected_information_gain` and
      `potential_impact`. Six always-NULL columns on the surface the model plans
      from is the same defect as an always-NULL column anywhere else, with a
      reader that cannot tell.
- [ ] The two model priors are separated from the Skill binding, because they
      fail for different reasons. `expected_information_gain` and
      `potential_impact` are ticket 06 columns a proposing model was meant to
      estimate; `skill_name` and its two digests are ticket 15's binding between
      a Task and the Skill that performs it. A single ticket may answer both,
      but it must answer them as two questions.
- [ ] Whether the Skill binding belongs on the Task at all is the question that
      gets settled. `20260822T000000Z__a_skill_teaches_what_the_role_may_already
      _do.sql` made a Skill a thing a role may already do; if the role carries
      the Skill and the Task does not, then the columns are superseded and the
      ticket that removes them says so.

## Why

`docs/research/wiring/23-database-wiring.md` section 1.3(a). This is the largest
single block of always-NULL columns on the agent's read surface, and it sits on
the table the scheduler ranks: a Task that cannot say which Skill it needs
cannot be matched to a role that has it, and `required_skills` is the column the
matching would read.

`needs-triage` rather than `ready-for-agent` because "which writer should have
set these" has two credible answers -- the opener that creates the Task, or the
ranking pass that already UPDATEs nine other columns on it -- and picking one
without deciding whether the binding is still the design is how the columns got
here.

## The decision, taken 2026-08-22

**The Skill binding is deferred, not superseded, and it is the same missing write
path as ticket 119's -- so this ticket becomes downstream of 119 rather than a
separate design. The two model priors are a different question with a different
answer: they need a writer, that writer is not `rank_pass`, and until they have
one the whole seven-component ranking produces no order at all. The read surface
is corrected now, under both answers.**

### The binding is deferred

The corpus's most recent word on these columns says so in as many words.
`20260822T000000Z__a_skill_teaches_what_the_role_may_already_do.sql:320-329`:
"Both are nullable and **neither has a writer yet -- the runtime that serves
`Skill` calls is what will fill them, and until it exists** the criterion these
columns carry is that a run *can* be recorded and that a recorded one can be
compared, which `check_skill_registry` does." That migration is the one the
ticket's last criterion proposes might have superseded the binding; read in
place, it is the migration that re-affirmed it, added the missing foreign key to
`skills(name)`, and added a third column to the set.

And the writer 015 named is precisely the one 119 defers: "Ticket 09: **the
PreToolUse hook on `Skill`** writes both of these onto the task row, which is
what binds a skill to a transition and what keeps a finding reproducible across a
skill edit" (`0015_epistemic_corrections.sql:144-146`). Half of that hook now
exists and holds the values in its hand: `roster.Gate._skill`
(`src/redkraken/roster.py:1354-1364`) reads `call.arguments["skill"]` on every
`Skill` call and decides against `role.skills`. It decides in-process and writes
nothing, which is 119's defect stated about a different column. One write path
fills both, and building two would be building the same path twice.

**Rejected: "the role carries the Skill, so the Task need not."** The role's
grant and the Task's record answer different questions. `skills_ungranted_for`
(`20260814T000000Z...:266-278`) asks *may* this role load that Skill, and it is
enforced at the claim. `skill_name`/`skill_sha256`/`skill_version` record *which*
Skill ran and *which text of it* -- "the instructions the model read, and
everything that ran underneath them", which is what makes drift answerable across
an edit. A grant cannot answer that retrospectively, and the reproducibility
claim 015 makes is not one the roster can carry.

**Rejected: dropping the columns.** It would delete the FK to `skills(name)`,
both digest CHECKs, the `evidence_profiles` half of a registry whose trigger
already guards it (`0015:159-172`), and `check_skill_registry`'s drift question,
to save three nullable columns.

### The two priors need a writer, and it is not the ranking pass

`0006_tasks_and_runs.sql:15-17` states the rule that decides this: the columns are
"**model-estimated, kept apart from runtime-computed** so the eval suite can ask
whose estimate was wrong (Q14)". `rank_pass` is the runtime-computed side; having
it write the model side would collapse the one distinction the pair exists for
and make Q14 unanswerable. So of the ticket's two candidates, the opener is the
right one -- and the consequence to write into the ticket is that an opener can
only carry an estimate a model supplied, which makes this a Contract-argument
question: the proposal that causes a Task to be opened has to carry the two
numbers, and no Contract in `roster.py` carries them today.

That is worth building rather than dropping, because of what the missing numbers
cost. `value_for` returns NULL when either estimate is missing
(`20260813T235500Z...:294-302`), `rank_pass` sets `priority = NULL` whenever
`direct_value` is NULL (`20260813T235500Z...:851-859`, and the same shape at
`0023_scheduler_ranking.sql:687-695`), and every offer orders by `priority DESC
NULLS LAST, created_at` (`0023:715`, `20260813T170000Z...:247-256`,
`tasks_queue_idx` at `0006:30`). **Since nothing writes either column, every Task
in the system has a NULL priority, and the Slate is FIFO by `created_at`.** The
novelty, cost, time, safety, confidence and unlock terms are all computed, all
stored and all multiplied by nothing: the `CASE` short-circuits before they are
used. Dropping the two columns would mean deleting the scheduler's ordering, not
tidying two nulls.

### The read surface is corrected now

Four Task columns are always NULL and are granted to `rk2_state`: `skill_name`,
`skill_sha256`, `skill_version` and `evidence_profile_id`, plus the two priors,
which are also always NULL. Six columns, and `v_records` publishes three of them
into every Task payload (`20260810T094500Z...:302-303`, carried forward to the
live definition). They come off until their writers land, for the reason ticket
119 gives about its own seven: a granted always-NULL column tells the model the
harness knows something it does not.

## What was measured

`grep -rn "expected_information_gain\|potential_impact" src/ tools/` returns
**twenty-one** lines and **not one of them is a write** -- every hit is a read in
a ranking expression, an `explain`-style payload or a `v_records` projection.
`open_task` has exactly one caller in the whole tree
(`20260831T000000Z...:412`, the recon Task a Program opens over its own scope).
`grep -rn "required_skills" src/` returns six lines, of which three are live
readers.

## Correction: `required_skills` is not an always-NULL column and has three
readers

The ticket lists `required_skills` among the columns "nothing ever sets" and
among "six always-NULL columns on the surface the model plans from". It is
`text[] NOT NULL DEFAULT '{}'` (`0012_scheduler.sql:21`), so it is never NULL,
and empty is a value the design uses deliberately: "`required_skills` defaults to
`'{}'`, so a Task that requires none unnests to no rows and is never ungranted"
(`20260814T000000Z...:264-265`). It has three live readers -- a BEFORE
INSERT/UPDATE trigger that refuses unregistered names
(`0023_scheduler_ranking.sql:135-154`), gate 3 of the confidence term
(`0023:433-438`), and `skills_ungranted_for`, which the claim admission rule
refuses on (`20260814T000000Z...:314`) and a standing check reports on. It is not
this ticket's defect and should not be removed from the read surface with the
others. The surface count is five always-NULL columns, not six.

## Correction: the two priors are not "the same defect as an always-NULL column
anywhere else"

The ticket's fourth criterion is right that the priors and the Skill binding fail
for different reasons, but understates the difference. `expected_information_gain`
and `potential_impact` have a live reader that was written specifically to handle
their absence: `value_for`'s NULL arm carries the comment "The NULL arm is
explicit and cannot be folded into the clamp: `greatest(NULL, 0)` is 0 in SQL,
not NULL, so clamping an absent estimate would silently report a Task nobody
estimated as one worth nothing" (`20260813T235500Z...:289-293`). The system
knows these are missing and says so correctly at every level. What it does not do
is ever have one -- so the defect is a missing producer for a consumer that
handles the gap, not a column nobody reads.
