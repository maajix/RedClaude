# 126 — The eval store is connected at neither end

**What to build:** A decision about `0033_eval_store.sql`: either the grading
run writes its scores into it and something reads them back, or the four tables
and their five read functions are retired.

**Blocked by:** nothing.

**Status:** needs-triage

- [ ] The state is recorded first. `eval_runs` (`0033_eval_store.sql:37`),
      `eval_pair_scores` (`:60`), `eval_fn_attribution` (`:150`) and
      `eval_family_coverage` (`:198`) have no `INSERT` anywhere -- not in a
      function, not in Python, not even a seed row in their own migration. The
      five functions that read them -- `eval_recall_by_kind` (`:244`),
      `eval_precision` (`:260`), `eval_family_coverage_of` (`:286`),
      `eval_key_diff` (`:296`) and `eval_comparable` (`:307`) -- have no caller.
      Twenty-nine columns and twenty-seven CHECK constraints sit between two
      ends that are both open.
- [ ] The evaluation that does exist is distinguished from the one that is
      declared. `src/redkraken/evaluation.py` writes `evaluation_programs`
      (`evaluation.py:140`) and is reached by `rk playbook evaluate` and
      `rk playbook cost`. That is a fixture-program registry, not a score: it
      says which Playbook is being measured against which fixture, and nothing
      records how it did.
- [ ] The question the ticket answers is whether a run is meant to be
      measurable from the database at all. `run_key` is "the sha256 of
      everything that must be equal for two runs to be repeats of the same
      measurement" and `key_components` keeps the pre-image so two runs that
      differ can be told where (`0033:31-36`); `eval_comparable` exists to
      answer whether two runs may be compared at all. That is a considered
      design for A/B measurement of the hunter, and either it is due or it is
      not.
- [ ] The one thing that is not re-decided is the exclusion from the agent's
      read surface. `0033:17-20` gives the reason and it stands: "an eval score
      is a measurement of the hunter, and letting the hunter read it is the one
      thing that would make the measurement worthless."
- [ ] If the answer is "later", it is written into the migration corpus rather
      than left as an absence, so the next audit does not re-report four empty
      tables as a hole.

## Why

`docs/research/wiring/23-database-wiring.md` section 3.1: "a whole subsystem
declared with neither end connected". It is the largest single block of
unreachable schema in the database and the only one where every table, every
constraint and every function on both sides is unreached.

`needs-triage` because there is no defect to fix here in the ordinary sense.
Nothing is broken by the eval store being empty; what is wrong is that the
repo's own standard -- a declared thing with no producer is either wired or
documented as deferred -- is unmet for a subsystem this size.
