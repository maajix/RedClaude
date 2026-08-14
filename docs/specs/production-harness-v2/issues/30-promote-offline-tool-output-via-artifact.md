# 30 — Promote offline Tool output through an Artifact

**What to build:** Execute one allowlisted offline analysis tool in isolation and make its exact output usable as evidence only through a recorded Tool run and content-addressed Artifact.

**Blocked by:** 18 — Compile and enforce the six-role roster; 20 — Run one Task to a canonical Observation.

**Status:** resolved

- [x] Tool definitions use a closed registry of executable, argument schema, version, timeout, resource ceiling and compatible roles.
- [x] Execution occurs in an isolated runtime with no target network path unless the tool explicitly uses the proxy adapter.
- [x] A Tool run is recorded before process start and closed on success, failure, timeout and supervisor death.
- [x] Stdout, stderr and declared outputs become bounded content-addressed Artifacts with hashes and tool-version provenance.
- [x] A structured Mission proposal may cite those Artifacts, but shell text alone cannot create an Observation.
- [x] Unknown tools, extra arguments, path escape, resource overflow and foreign Artifacts fail closed with synthetic negative tests.

## Comments

Implemented on 2026-08-14 in one migration --
`20260814T030000Z__an_offline_tool_becomes_evidence.sql` -- one new Python
module, `tool.py`, reached by `rk tool run`, and a second runner in
`isolation.py` alongside the Agent container.

`mcp__rk2__run_tool` had been a contract with nothing behind it since ticket 18:
the roster compiles the name, the risk rules classify calls to it, and no path
in the harness started a process. What was missing is not a subprocess call. It
is the answer to what may run, with which arguments, under which ceilings, and
what has to be true of the bytes before anything may cite them.

### The registry is the whole of what a call may be

`offline_tools` names the executable, the version pattern its image must report,
the five ceilings and whether the tool has a network; `offline_tool_arguments`
is one row per parameter, so the argument schema is data rather than a string
the runtime parses; `offline_tool_outputs` declares the files a tool writes; and
`offline_tool_roles` says which roles may run it. Only `rk2_runtime` may read
any of it, and only the owner may write it -- a runtime that could add a row
could run anything, which is why the tests have to change roles to arrange
themselves.

Nothing composes an argv from model text. `open_offline_tool_run` validates the
call and *returns* the argv, and the runtime runs what it was handed. That is
the difference between an allowlist and a closed registry: there is no path
where a value the model supplied becomes a token the registry did not put there.

Path escape is structural rather than checked. Of the four argument kinds
exactly one names a file, and what it names is an Artifact label -- never a
path. The other three admit no `/` and no `\` at all, and none of the four
admits a leading `-`, so no value a model supplies can address the filesystem or
smuggle a flag, whatever the tool would do with it if it could.

### Three moments, and the order is the design

Open and commit, run bounded, then store, link and close in one transaction.

The row is committed before the container starts, because a row that only
existed inside the transaction that also ran the process would vanish exactly
when the process was what went wrong. From there every way out of `tool.run`
closes it: the two named failures close it and are reported, and anything else
-- a store that cannot write, a socket that dropped between the run and the
transaction that files it -- closes it saying so and re-raises. An open row left
behind is the one state `check_offline_tools` cannot tell from a supervisor that
died, so this is the difference between a failure and a mystery. Supervisor
death has no closer by definition, so it stays a check: a run still open past
twice its own declared timeout is a row saying the thing that was going to close
it is gone.

Storing and closing are one transaction so there is no committed state in which
a run is a success and its output is not there to read.

### The ceilings are what the kernel is holding

Memory, swap, CPU quota and process count are container flags, and the test
reads them back out of `/sys/fs/cgroup` inside the running container rather than
trusting the argv that asked for them. The output bound is enforced while the
process is still running, because a bound applied to output already read is not
a bound; the same is true of declared outputs, which end the run when the file
being collected crosses it.

Two versions are in play and they are not the same claim. The registry says
which versions it admits, as a pattern; the image says which one is installed,
and `tool.py` asks it in a container with no network and no inputs. What lands
on the run is what the image answered, so `tool_runs.tool_version` is provenance
rather than policy and a run made before an upgrade still says what produced its
bytes.

### The network is a per-run adapter or it is nothing

`offline_tools.network` is `none` or `proxy` and nothing else. A `none` run gets
`--network none`, and a Receipt attributed to one is a standing violation. A
`proxy` run gets its own internal network whose only peer is the Agent's proxy,
created for the run and removed with it; the caller names the network before the
first engine command, so a step that fails part of the way through still leaves
a name the `finally` knows to remove. The test asserts the proxy is reachable,
the target and `1.1.1.1` are not, and `docker network ls` is byte-identical
before and after.

### A tool that answers by exiting is history, not a fault

The reviewer was right that reporting every non-zero exit as
`INVALID_CONFIGURATION` sends an operator to fix a working machine. `grep` with
no match exits 1 and that is the tool's answer. So `_verdict` is three-valued:
timeout and output overrun are the supervisor stopping the run, are reported
failures, and keep criterion 6's fail-closed; a non-zero exit the tool chose
closes the row as `error` with the exit code on it and is reported as a hold.
Either way the run's own row carries the difference, and `exit_detail` is a new
column rather than a reuse of `hook_error`, because `closed_by` is NULL for
offline runs and would otherwise be the only thing telling the two apart.

### What the model may read

`tool_run_artifacts` and the four new `tool_runs` columns are published to
`state_read_surface`; the registry and its ceilings are not. An agent may read
what a run produced and what became of it. What it may run, and how much it is
given to run it with, is not its business to see.

An Observation citing an offline Tool run is refused unless that run finished
and its output was stored. The citation reaches the Artifacts through the run,
so a run still in flight or one whose output nobody kept is a sentence a model
wrote about bytes that are gone.
