# 87 — Serve a Skill script as a recorded Tool run

**What to build:** A path by which a running Agent can execute one of the
deterministic scripts its Skills ship, over Artifacts this Program holds, and
have that execution recorded. `mcp__rk2__run_skill_script` has had a contract in
`roster` since ticket 18 and no handler in any launch, so today the only thing
that ever runs a Skill script is `skill.check` in CI.

**Blocked by:** nothing.

**Status:** ready-for-agent

- [ ] A child holding a Skill can run that Skill's script and read back what it
      printed, or the harness says plainly and in one place that it cannot.
- [ ] The run leaves a receipt. `roster._check_contracts` refuses an `ACT` that
      records nothing -- "an act that records nothing leaves no receipt" -- so
      whatever serves this either writes `tool_runs` or is not an act.
- [ ] Inputs are named the way the rest of the agent surface names Artifacts.
      The contract's `input_artifact_hashes` is the shape `packet.Reader.artifact`
      refuses on purpose: "a verb taking a hash reads across Programs whenever
      the caller can guess the bytes". Either the argument becomes labels, or
      the handler resolves hashes only against Artifacts already staged for this
      run, and the contract says which.
- [ ] What the script reads is the whole Artifact or a stated prefix of it. The
      packet stages excerpts, and a deterministic transform over a silently
      truncated input is not deterministic about anything a reader can name.
- [ ] `mcp__rk2__run_tool`, the other member of `exec.tool_run`, is either served
      by the same channel or has its own answer recorded here. Two roles hold the
      group today and neither can reach either tool.
- [ ] The test that pins the unserved set (`tests/test_agent.py`) is rewritten as
      the statement of what is now served, or deleted with the reason.

## Why

Found by ticket 64's final review and recorded as
`skill-script-declared-and-unserved` in `baseline/final-review.tsv`: "Story
169/170: Skill scripts are unrunnable at run time." Story 169 asks for
"deterministic Skill logic placed in scripts with runnable checks, so that
prompts are not used for work code can perform". The corpus has the scripts and
the checks -- `skills/compare-responses/scripts/compare.py` and
`skills/analyse-source/scripts/extract_paths.py`, each with declared cases run
twice under a bare environment -- and story 170's other half, a Skill being
unable to widen a role's tool surface, is enforced at compile time by
`roster._check_skills`. What is missing is the run-time half: during a run the
model reads the instructions and does the work a script could do.

## What ticket 64 found out about the shape

Written down because each of these closed off an implementation that looked
cheap from outside:

* A child writes nothing. `_launch.Submission` says it: "the row is written by
  the runtime after this process ends and after its provenance is checked". So a
  handler cannot open a `tool_runs` row itself, and an act must leave one.
* The runtime's own runner is not reachable from a turn. `tool.run` is called
  from `cli.py` and nowhere else, and the container's one network reaches the
  capability proxy.
* An offline tool's analyser is a flat file beside `tool.py`
  (`analyser ~ '^[a-z][a-z0-9_]{0,31}\.py$'`, read as `ANALYSERS / Path(name).name`),
  and a Skill script is `skills/<skill>/scripts/<file>.py`. Registering the
  scripts as analysers means changing that boundary, not adding rows.
* Serving one member of a group is already a mechanism: `agent.SERVED_MEMBERS`
  plus `_check_served_members`, which is how `sched.pick` is served in part.

## Comments

Ticket 64 recorded the finding rather than fixing it: the fix is a channel the
harness does not have, and inventing one in a review pass is how a boundary gets
crossed quietly. The tree now states the gap instead of implying the opposite --
`skill.stage` no longer says the runtime runs `scripts/`, and
`tests/test_agent.py` asserts which contracts are declared and unserved and
names this ticket.
