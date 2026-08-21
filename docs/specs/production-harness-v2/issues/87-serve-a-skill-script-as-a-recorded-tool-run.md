# 87 — Serve a Skill script as a recorded Tool run

**What to build:** A path by which a running Agent can execute one of the
deterministic scripts its Skills ship, over Artifacts this Program holds, and
have that execution recorded. `mcp__rk2__run_skill_script` has had a contract in
`roster` since ticket 18 and no handler in any launch, so today the only thing
that ever runs a Skill script is `skill.check` in CI.

**Blocked by:** nothing.

**Status:** resolved

- [x] A child holding a Skill can run that Skill's script and read back what it
      printed, or the harness says plainly and in one place that it cannot.
- [x] The run leaves a receipt. `roster._check_contracts` refuses an `ACT` that
      records nothing -- "an act that records nothing leaves no receipt" -- so
      whatever serves this either writes `tool_runs` or is not an act.
- [x] Inputs are named the way the rest of the agent surface names Artifacts.
      The contract's `input_artifact_hashes` is the shape `packet.Reader.artifact`
      refuses on purpose: "a verb taking a hash reads across Programs whenever
      the caller can guess the bytes". Either the argument becomes labels, or
      the handler resolves hashes only against Artifacts already staged for this
      run, and the contract says which.
- [x] What the script reads is the whole Artifact or a stated prefix of it. The
      packet stages excerpts, and a deterministic transform over a silently
      truncated input is not deterministic about anything a reader can name.
- [x] `mcp__rk2__run_tool`, the other member of `exec.tool_run`, is either served
      by the same channel or has its own answer recorded here. Two roles hold the
      group today and neither can reach either tool.
- [x] The test that pins the unserved set (`tests/test_agent.py`) is rewritten as
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

## The design this is built to

Written down before the first line, because four of the six criteria are
decided by where the channel is rather than by how it is coded.

**A Skill script is a registered program the harness ships.** `jsscan.py`
already is one: `offline_tools.analyser` names a file beside `tool.py`, the
runtime reads it off its own disk, hashes it, mounts it read-only at `/input`
and runs it. A Skill script is the same object in a different directory, so the
registry gains where the file lives rather than a second mechanism beside it.
Two columns:

* `offline_tools.skill` -- the Skill whose `scripts/` directory holds the
  analyser, or NULL for one beside `tool.py`. What changes is the *host* path;
  `rk2_offline_analyser_path` is unchanged, because the container path was
  never the part that differed.
* `offline_tools.input_delivery` -- `argv`, which is what every row does today,
  or `stdin`. A Skill script takes no arguments at all: it reads one JSON
  object, and `skill.Case.payload()` is the only executable statement of that
  object's shape. A row that delivers on `stdin` records its input Artifacts
  and does not append their paths to the argv.

Everything else the registry already decides is thereby decided for a Skill
script too, in the same words and by the same code: which roles may run it, the
Halt, the ceilings, the version the program reports, the analyser digest the
run records, and -- criterion 3 -- that an Artifact argument is a **label**
resolved against `artifact_references` for this Program. There is no hash on
this surface to resolve.

**The channel is the pipe the child already has.** `isolation.run` grows an
`answer` callable. Given one, the launch keeps the child's stdin open and pumps
its stdout line by line: a line that is an object carrying `rk2_call` is handed
to `answer`, and what comes back is written to stdin as one line under
`rk2_answer` with the same `id`. Every other line is kept, so `_last_document`
still finds the result document. On the child's side `_launch` writes one frame
and blocks on one line, under a lock and through `asyncio.to_thread`, which is
what `http_request` already does with a socket.

The supervisor is the side that may act: `agent.launch` holds the runtime
connection, so the handler opens the `tool_runs` row, runs the container, files
the streams as Artifacts and closes the row. The child still writes nothing,
which is what `Submission` says and what this design does not disturb.

**Criterion 4 is answered by which side reads the bytes.** The packet stages an
excerpt for the model; the supervisor holds the Store and reads the Artifact
whole. The envelope carries the whole Artifact and says so, and a run whose
input could not be read whole is a refusal rather than a transform over a
prefix nobody named.

**`run_tool` is served by the same channel**, which is criterion 5's first
branch. Its contract is corrected to the registry it drives: named `arguments`
rather than a free `argv`, because `open_offline_tool_run` builds the argv, and
an enum that is the registry's own tool names rather than six binaries no row
has ever held.

## Comments
Ticket 64 recorded the finding rather than fixing it: the fix is a channel the
harness does not have, and inventing one in a review pass is how a boundary gets
crossed quietly. The tree now states the gap instead of implying the opposite --
`skill.stage` no longer says the runtime runs `scripts/`, and
`tests/test_agent.py` asserts which contracts are declared and unserved and
names this ticket.
