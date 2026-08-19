# 85 — Hold the Agent network between the check and the launch

**What to build:** Containment between two Agent children that does not depend
on their launches being ordered. Today `isolation.run` reads the network, finds
the door alone on it, and then starts a container; two launches that overlap
both read a clear network and both attach, and each child is then a peer of the
other.

**Blocked by:** nothing.

**Status:** ready-for-agent

- [ ] Two `isolation.run` calls that overlap cannot both put a child on one Agent network. Whichever loses is refused with a typed reason, or gets a network of its own -- either is an answer, and which one is this ticket's to decide.
- [ ] The refusal or the allocation is proved by a run in which the second launch really is inside the first's window, rather than by two launches that happen to be sequential.
- [ ] `tests/test_isolation.py::AgentContainerIsolationTest::test_a_peer_that_arrives_after_the_check_is_reachable_by_the_child` is rewritten as the statement of what now happens, or deleted with the reason. It exists to record the gap and should not outlive it.
- [ ] Whatever holds the network is held by the engine or by a lock this installation owns, not by a Python-side convention two processes could each believe. Two `rk run` processes on one machine are the case to answer, not two calls in one interpreter.
- [ ] Nothing about the single-child path gets slower or newly refusable. `one_peer` stays as it is for the case it already answers.

## Why

Found while measuring ticket 80's fourth failure mode, "turf wars": the paper's
agents disabled each other's Unix accounts, killed competing processes and
planted code disguised as another agent's, and the question was what separates
two children here.

Most of it separates them well. Every child runs `--read-only`, `--cap-drop
ALL`, `--security-opt no-new-privileges`, as uid 65534, on a `--tmpfs` scratch
of its own, with no engine socket, no shared PID namespace and no writable host
mount but the one the runtime supplies. There is no path from one child to
another's filesystem, process table or credential, and none by which one could
sign as the other -- the canonical rows are the only shared writable state, and
they are written through verbs the database authorises per Program.

The network is the exception, and the reason is one line of ordering. From
`isolation.run`:

    one_peer(engine, container.network, container.proxy_container, proxy_host)
    ...
    docker = [engine, *hardened(name), "--network", container.network, ...]

`one_peer` refuses if anything but the door is attached, which is what makes a
second child impossible *after* a first is up -- proved by
`test_a_second_agent_network_peer_is_refused_before_launch`. But the engine
holds nothing between that read and the `run`, and `RK_AGENT_NETWORK` is one
name for a whole installation, so two launches inside each other's window both
see a clear network and both attach. The internal network carries no route off
itself, but it carries every route across itself: two peers on it can address
each other directly.

Demonstrated deterministically rather than by racing, in
`test_a_peer_that_arrives_after_the_check_is_reachable_by_the_child`: a peer is
attached inside the launch call, after `one_peer` has returned and before the
engine is asked to start anything, and the child comes up and reaches it on
18081. Nothing about that is a defect in `one_peer`, which does exactly what it
says. The gap is that ordering the launches is what makes it hold, and nothing
orders them.

The roster caps concurrency per role and 073 caps it across roles, so the
overlap needs two roles claiming at once or two `rk run` processes on one
machine -- neither of which anything refuses today.
