# 82 — Run the door as the Agent network's one peer

**What to build:** A supported way to run the production door as a container on the Agent network, so that a machine can satisfy `execution.REQUIRED` without an operator writing their own entrypoint.

**Blocked by:** nothing.

**Status:** ready-for-agent

- [ ] One shipped command or module runs the door bound wide inside a container, and refuses to do so unless the network it is on is `--internal` and it is that network's only peer.
- [ ] `rk proxy serve` keeps refusing a routable bind. Whatever this adds does not become a second way to put a capability listener on an interface anybody can reach.
- [ ] The door reaches the database and the internet over a second attachment, and the Agent network carries no route to either.
- [ ] The three commands that read `execution.boundary` -- `rk run`, `rk tool run`, `rk browser run` -- work on a machine configured this way, proved by a test rather than by an operator's shell history.
- [ ] `README.md` documents the five variables and how to satisfy them, because today nothing does.

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
