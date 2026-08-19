# 86 — Give each Agent run its own home

**What to build:** A writable home a child cannot share with another child.
Today `RK_AGENT_HOME` is one host directory per installation, it crosses
writable into every container, and every child is told it is `HOME`, so what one
child writes there is what the next child reads.

**Blocked by:** nothing.

**Status:** ready-for-agent

- [ ] No child sees another child's files under `HOME`. Ticket 85 made two children on one Agent network impossible, so the leak that is left is sequential -- what a run leaves is what the next run finds -- and that is the case to answer. Whether the home is a per-run directory the runtime makes, a tmpfs the child gets to itself, or a subdirectory of the configured one is this ticket's to decide.
- [ ] Whatever a run writes there is either its own to keep or gone when it ends, stated either way. A home that silently accumulates every run's leftovers is the same shared directory with a slower failure.
- [ ] `tests/test_isolation.py::AgentContainerIsolationTest::test_a_child_reads_what_the_child_before_it_left_in_one_home` is rewritten as the statement of what now happens, or deleted with the reason. It exists to record the gap and should not outlive it.
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
`test_a_child_reads_what_the_child_before_it_left_in_one_home`: one child writes
a file under `HOME` and exits, and the next child reads it back -- and reads it
without knowing there was a child before it. That is the paper's planted code in
the smallest form this harness can be asked about, and it needs no privilege at
all: the two children are one unprivileged user writing one directory.

It was two children at once when the mode was measured, and ticket 85 closed
that form -- the launch now holds an exclusive claim on the Agent network across
the check and the child, so two children cannot overlap on one installation. The
home does not need them to overlap: a run that finished an hour ago left its
session state where the next child will find it, which is why this ticket stayed
open when 85 closed.
