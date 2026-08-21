# 120 — A Task never names the Skill it needs

**What to build:** A writer for the Task columns that bind a Task to a Skill and
to an evidence profile, or the decision that the binding is made elsewhere and
the columns come off the agent's read surface.

**Blocked by:** nothing.

**Status:** needs-triage

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
