# 86 — Give each Agent run its own home

**What to build:** A writable home a child cannot share with another child.
Today `RK_AGENT_HOME` is one host directory per installation, it crosses
writable into every container, and every child is told it is `HOME`, so two
children that run at once read and write each other's session state.

**Blocked by:** nothing.

**Status:** ready-for-agent

- [ ] Two children that run at once do not see each other's files under `HOME`. Whether the home is a per-run directory the runtime makes, a tmpfs the child gets to itself, or a subdirectory of the configured one is this ticket's to decide.
- [ ] Whatever a run writes there is either its own to keep or gone when it ends, stated either way. A home that silently accumulates every run's leftovers is the same shared directory with a slower failure.
- [ ] `tests/test_isolation.py::AgentContainerIsolationTest::test_two_children_running_at_once_read_and_write_one_home` is rewritten as the statement of what now happens, or deleted with the reason. It exists to record the gap and should not outlive it.
- [ ] The CLI still finds its session state where it expects it. The home crosses writable because the application keeps state in it, so a per-run home that broke a resumed session would trade one failure for another.
- [ ] `baseline/multiagent-modes.tsv` moves `turf_wars_workspace` off `reproduced` with the run that says so, or the row stays and says why the mode is still reachable.

## Why

Found while measuring ticket 80's fourth failure mode, "turf wars": the paper's
agents disabled each other's Unix accounts, killed competing processes and
planted code disguised as another agent's, and the question was what separates
two children here.

Most of it separates them. Every child runs `--read-only`, `--cap-drop ALL`,
`--security-opt no-new-privileges`, as uid 65534, on a `--tmpfs` scratch of its
own, with no engine socket and no shared PID namespace. There is no account to
disable and no process of another child to signal.

The home is the exception, and `isolation._mounts` says so in as many words:

    The home is the one writable mount -- the CLI keeps session state in it.

`_supplied` carries it as `(HOME_DIR, container.home, False, False)` -- the one
row of that table that is not read-only -- and `container_environment` sets
`HOME` to `/run/redkraken-home` for every child. The host side is
`RK_AGENT_HOME`, which `execution.boundary` reads once per process: one
directory, one name, every run.

Demonstrated in
`test_two_children_running_at_once_read_and_write_one_home`: two children are
launched through a barrier inside the launch call, each writes a file under
`HOME` and waits for the other's, and each reads what the other wrote while both
are still running. That is the paper's planted code in the smallest form this
harness can be asked about, and it needs no privilege at all -- the two children
are one unprivileged user writing one directory.

The two children have to overlap for it to matter, which is ticket 85's
condition as well: the roster caps concurrency per role and 073 caps it across
roles, so it takes two roles claiming at once or two `rk run` processes on one
machine. Unlike 85, the home does not need them to overlap to leak -- a run that
finished an hour ago left its session state where the next child will find it.
