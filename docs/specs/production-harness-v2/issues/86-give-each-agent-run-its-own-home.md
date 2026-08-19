# 86 — Give each Agent run its own home

**What to build:** A writable home a child cannot share with another child.
Today `RK_AGENT_HOME` is one host directory per installation, it crosses
writable into every container, and every child is told it is `HOME`, so what one
child writes there is what the next child reads.

**Blocked by:** nothing.

**Status:** resolved

- [x] No child sees another child's files under `HOME`. Ticket 85 made two children on one Agent network impossible, so the leak that is left is sequential -- what a run leaves is what the next run finds -- and that is the case to answer. Whether the home is a per-run directory the runtime makes, a tmpfs the child gets to itself, or a subdirectory of the configured one is this ticket's to decide.
- [x] Whatever a run writes there is either its own to keep or gone when it ends, stated either way. A home that silently accumulates every run's leftovers is the same shared directory with a slower failure.
- [x] `tests/test_isolation.py::AgentContainerIsolationTest::test_a_child_reads_what_the_child_before_it_left_in_one_home` is rewritten as the statement of what now happens, or deleted with the reason. It exists to record the gap and should not outlive it.
- [x] The CLI still finds its session state where it expects it. The home crosses writable because the application keeps state in it, so a per-run home that broke a resumed session would trade one failure for another.
- [x] `baseline/multiagent-modes.tsv` moves `turf_wars_workspace` off `reproduced` with the run that says so, or the row stays and says why the mode is still reachable.

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

## What was built

The configured home is now a template, and nothing mounts it. `isolation.own_home`
copies it per run into a directory of this user's own, with the modes it had,
mounts the copy at `HOME`, and removes the copy when the run ends. So the CLI
finds the credential and the settings the operator seeded, exactly where it
expects them, and what a run writes beside them is gone with the run.

Gone rather than kept, of the two answers this ticket allowed. A per-run home
that is kept is a directory growing without limit on a machine nobody watches,
and session state that outlives its run is state the next run can be told is its
own -- the same leak, slower. Nothing needs it kept: what a session resumes from
is the capsule in the database rather than a file in a home.

Copying is bounded. `HOME_CEILING` is 64 MiB, measured before anything is
copied and refused with the size, because a home holding an engagement's worth
of transcripts is a directory that has been pointed at the wrong thing and
copying it once per Agent run would be a cost nobody asked for. The template is
refused for the two reasons a mount already was -- it may not be the operator's
own home, and the child has to be able to write what it is given -- and the copy
keeps the template's modes so that the second of those is decided by what the
operator set rather than by what the copy widened.

`baseline/multiagent-modes.tsv` moves `turf_wars_workspace` to enforced, citing
`test_a_child_gets_the_seeded_home_and_not_the_last_child_s`: two children run
one after the other, and the second finds what the operator seeded and nothing
the first left. With ticket 85's claim on the network beside it, both halves of
the turf-wars mode this harness could actually have are now closed.

## What the review changed

Three things, all found by the two-axis review of the first implementation.

**The credential is not copied.** The spec axis was right that criterion 4 was
argued around rather than answered: the CLI refreshes its own token and writes
the new one where it read the old, so a credential living only in the copy is a
token refreshed into a directory the run is about to delete, and the run after
the first expiry presents one already spent. It is now the single path
`copytree` skips, and `_mounts` puts the template's own file at
`/run/redkraken-home/.claude/.credentials.json` instead. Three consequences,
each stated where it bites: a refresh has to be written in place, because
nothing can be renamed onto a mounted file -- measured, `mv` over one returns
`EBUSY` -- so a CLI that replaces its credential fails visibly inside the child
rather than quietly refreshing into a copy about to go; the file has to be
writable by the contained user, which is now refused before launch with the path
rather than diagnosed after an expiry; and this process never reads the
operator's token at all, only names it to the engine.
`test_a_credential_the_child_refreshed_is_the_one_the_next_child_reads` runs two
real children and proves the second resolves what the first refreshed while the
first's other writes are gone.

**A killed run's copy does not outlive it.** The standards axis found that the
copy was removed only in a `finally`, which does not run for a process that is
killed -- and what is left behind is not an inert file like a stale network
claim, it is a copy of a home. Each run now holds its copy open under an
exclusive lock for as long as it has it, and `_sweep` removes every copy nothing
is holding just before the next one is made. That is the same kernel-held claim
ticket 85 uses, for the same reason: a lock nobody holds is a run that is gone.

**The ceiling stays, and is this ticket's.** The spec axis called
`HOME_CEILING` scope creep, since no criterion asks for a size limit. It is a
bound on the mechanism this ticket introduces rather than a new feature: copying
the home is a per-run cost that did not exist before, and a home pointed at an
engagement's worth of transcripts would spend it on every Agent run. Kept, with
the refusal naming the size.

Two judgement calls the review raised were left as they are, on purpose. A
symlink inside the template is copied as a symlink, so a link pointing outside
it names a path that does not exist in the container's namespace and reads
nothing; and the containment questions asked of the template before copying are
asked again by `_mounts` of what is actually mounted, which is one check in one
function called twice rather than two that could drift.
