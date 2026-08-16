# 82 — Run the door as the Agent network's one peer

**What to build:** A supported way to run the production door as a container on the Agent network, so that a machine can satisfy `execution.REQUIRED` without an operator writing their own entrypoint.

**Blocked by:** nothing.

**Status:** resolved

- [x] One shipped command or module runs the door bound wide inside a container, and refuses to do so unless the network it is on is `--internal` and it is that network's only peer.
- [x] `rk proxy serve` keeps refusing a routable bind. Whatever this adds does not become a second way to put a capability listener on an interface anybody can reach.
- [x] The door reaches the database and the internet over a second attachment, and the Agent network carries no route to either.
- [x] The three commands that read `execution.boundary` -- `rk run`, `rk tool run`, `rk browser run` -- work on a machine configured this way, proved by a test rather than by an operator's shell history.
- [x] `README.md` documents the five variables and how to satisfy them, because today nothing does.

## Why

Found during authorised live validation on 2026-08-16.

`execution.REQUIRED` is `RK_AGENT_IMAGE`, `RK_AGENT_NETWORK`,
`RK_AGENT_PROXY_CONTAINER`, `RK_AGENT_PROXY_URL` and `RK_PROXY_CA_FILE`, and
nothing is defaulted, for the reason `boundary`'s docstring gives. Four of the
five are cheap to satisfy. The fifth is not satisfiable with what this
repository ships.

`isolation._one_peer` requires that the Agent network be `--internal`, that the
container named by `RK_AGENT_PROXY_CONTAINER` be attached to it, that
`RK_AGENT_PROXY_URL`'s host name that container, and that no other peer be on
the network. So the door must be a container.

`proxy.serve` binds `127.0.0.1` and refuses anything routable:

> And it binds nowhere but this machine. `endpoint` refuses to send a
> capability to a proxy that is not local; a listener on a routable interface
> is the same hole from the other side, because what arrives at it is bearer
> material that anybody who can reach the port may spend.

That rule is right and is not the thing to relax. But loopback inside a
container is unreachable from that container's peers, so `rk proxy serve` can
never be the peer `_one_peer` is looking for.

The repository already knows the answer and has only written it for the suite.
`tests/browser_door.py` reaches for `proxy.listen`, the seam underneath `serve`,
and binds `0.0.0.0` inside a container whose network has exactly one other peer
-- with its own docstring explaining why that is sound and why relaxing `serve`
would not be. What is missing is the production version of that file: same
seam, same argument, but the shipped `connector` and `resolver` rather than the
fixture's twin.

## What was measured

A scaffolding door was written outside the repository, running `proxy.listen`
on `0.0.0.0:18080` inside a `python:3.14-slim` container attached to two
networks -- an `--internal` one carrying only itself, and an ordinary bridge
carrying the database and egress. With `RK_AGENT_*` pointed at it:

- `isolation._one_peer('docker', 'rk2-agent-net', 'rk2-door', 'rk2-door')` passes.
- `isolation.run` starts a child that sees `HTTP_PROXY`, `HTTPS_PROXY`,
  `NODE_EXTRA_CA_CERTS`, `SSL_CERT_FILE`, the SDK at `/opt/rk2-sdk` and the
  credential at `/run/redkraken-home/.claude/.credentials.json`.
- `rk run` stops reporting `nothing_to_execute` and reaches the scheduler.

So the boundary is sound and the only missing piece is that the door has no
shipped entrypoint. An operator following the README today cannot start an
Agent run at all, and nothing tells them why.

## What was built

`src/redkraken/door.py`, which is both ends of one assertion.

`door.main` is the door itself, inside the container: it reads its coordinates
from the environment, takes its port from the same `RK_AGENT_PROXY_URL` the
children's boundary carries, and calls the shipped `proxy.serve` with
`contained=True`. `rk proxy serve` was not relaxed. `proxy._unbindable` decides
where a fence may listen, and a routable bind is refused unless the caller asks
for it *and* a container marker is really present, so a host that passed
`--host 0.0.0.0` still gets the same refusal it always did. `serve` also gained
an `announce` callback, fired the moment the socket is bound *and* the fence is
attached, because a socket with no fence behind it answers every request with a
refusal.

`door.start` is the half that runs on this machine, reached as `rk proxy door`.
It decides everything decidable before it starts anything -- the boundary is
described, both directories the door writes are writable by 65534, the artifact
key is a file rather than an `op://` reference, `RK_PROXY_CA_FILE` names the
authority this door will sign with, no container holds the door's name, and both
networks are what they claim -- then starts the door on its egress attachment
alone, waits for the readiness marker, joins the Agent network, and asserts
`isolation.one_peer`: the same question `isolation.run` asks before every child,
asked by the command that built the machine rather than by the first run that
used it.

Both networks, because the door binds every interface it has. `empty_network`
says the Agent network is internal and carries nothing yet, and `door._outward`
says the way out is a way out -- not the Agent network again, not itself
`--internal`, and with no peers, since a peer there could reach the fence
without a capability ever having been minted for it. That is also why the
shipped `EGRESS` is `rk2-egress`, a network the operator creates, rather than
the engine's default `bridge` where every container on the machine is a peer.

The assertion cannot live in the container and `door.main`'s docstring says so
rather than leaving it implied. A process inside a container has no engine to
ask and cannot enumerate the peers of the networks it is on; it can see that it
is contained, which is all `proxy._unbindable` asks of it. So the topology is
established from outside, and `python3 -m redkraken.door` run by hand elsewhere
gets a wide bind on a network nobody vouched for. The door is only the door when
the command that starts it is the one that put it there.

`isolation.empty_network` is new and separate from `one_peer` on purpose. That
one says the proxy is alone, which can only be true once the proxy exists; a
peer that was already there is a peer that had a route to the door for however
long it took to start it. Six other names in `isolation` were promoted rather
than copied -- `hardened`, `engine_for`, `engine_command`, `remove`,
`writable_by_the_child`, `one_peer` -- because a door denied less than the
children around it is the hole, and a second copy of the denial list is where
one of them quietly goes missing. `hardened` grew one keyword, `ephemeral`,
because the door is the one container this harness starts that outlives the
command starting it, and a door that vanished on failure would take the only
account of why with it.

Two things deliberately do not cross into the container: the operator's home,
and a secret reference to the artifact key. Resolving one inside the container
would mean a service-account token inside the container, and resolving it
outside and passing the material in would put key material in an environment
`docker inspect` prints. The key crosses as a file or not at all.

`tests/test_proxy.py::BindPolicyTest` holds the bind policy from both sides
without an engine. `tests/test_database.py::ContainedDoorTest` starts the
shipped door with `door.start` and then holds the machine it left behind: the
Agent network's only peer is the door, a child started by `isolation.run`
reaches it and cannot reach the internet, a name server, this machine or the
database -- while the door, from inside the same container, reaches the database
and resolves the gateway, which is the two attachments proved as one pair. A
child's request comes back carrying `X-RedKraken-Decision: no-program`, which is
the production fence over the production `rk2_proxy` role answering before it
dials anything. A tool on the proxy adapter, the path `rk tool run` and `rk
browser run` both take, gets its own network with the same door on it and gives
it back. A child given the three optional variables finds the application, the
SDK and a home it can write, with the first two on its import path.

Criterion 4 is proved by running the three commands rather than by reasoning
about them: `rk run`, `rk tool run` and `rk browser run` are each started as
real subprocesses with this machine's environment and a configuration that is
not there, and each reports exactly one violation, against its own `config`.
What is asserted is what is not said -- no violation names a boundary variable.
The control beside it removes `RK_PROXY_CA_FILE` and gets precisely that, so the
silence is a boundary read and accepted rather than one never looked at.

Ten refusals are held alongside: seven for the things decided before anything is
started, and three for the way out -- an egress network that is the Agent
network, one that is itself internal, and one that already has a peer.
