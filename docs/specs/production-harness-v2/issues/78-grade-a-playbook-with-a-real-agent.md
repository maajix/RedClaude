# 78 — Grade a Playbook with a real Agent behind the door

**What to build:** A route by which the Agent that does the work in `rk playbook evaluate` reaches a synthetic fixture the way it reaches a real target -- through the door, with a Receipt per request -- without giving the door a way to dial the machine it runs on.

**Blocked by:** 46 — Evaluate and promote one Playbook.

**Status:** ready-for-agent

- [ ] An evaluation run with an Agent boundary configured reaches the fixture, and the requests appear as Receipts against the evaluation Program.
- [ ] The address a Receipt pins is the address that was dialled. A fixture reached by a name that resolved to something else is a Receipt that lies, and closes nothing here.
- [ ] `scope.compile_policy` still refuses an inclusion naming a loopback, private, link-local or documentation address, and `authorize_identity_egress_address` still refuses to dial one. Whatever this ticket adds, it does not add a Program configuration that can point the door at 127.0.0.1.
- [ ] `check_playbook_tests` gains an arm, or an existing one is extended, so a filed run with zero `tool_runs` against a configured Agent boundary is a reported problem rather than a silent zero.
- [ ] The existing loopback path keeps working for a machine with no Agent boundary. Both routes are documented in `evaluation.py`, with which one a given run took visible in the report.

## Why this is open

Ticket 46 built the evaluator on the production seams: `program.run` opens each
Program, `config.load` and `scope.compile_policy` read the document, the work is
whatever `program.Execute` the caller would have used on a real target, and
`record_playbook_test_run` does the counting. What it could not put on the
production path is the door.

The fixture is served by `evaluation.served` on an ephemeral loopback port, and
the door refuses loopback -- `scope.address_refusal` calls it out by name, and
`authorize_identity_egress_address` asks the same question again at dial time.
That refusal is correct and is not the thing to relax: a Program whose scope
could name `anything.localhost` at a port of its choosing is a Program that can
be pointed at this host's own PostgreSQL, and the compiler's rule is what stands
between a configuration file and that.

So today an evaluation on a machine with no Agent boundary runs end to end and
files honest zeroes, and an evaluation on a machine that has one has no route
from the Agent to the fixture. The measurement that matters -- does this
Playbook find the defect -- needs that route.

## What ticket 31 did, and why it is not the answer as it stands

The browser slice has the same problem and solved it for the suite: `browser_target`
runs in a container on the door's `--internal` network, and `tests/browser_door.py`
runs the production door with a `connector` that dials the container by name.
`proxy.listen` takes that connector as a parameter, so the seam is a real one.

The part that does not generalise is the address. That door reports
`ADDRESS = "93.184.216.34"` because the database will not authorise a private
one, and nothing is ever sent there. Inside a test that is a fixture with a
fixed twin; on a production path it is a Receipt recording an address the
request did not go to, which is the one thing a Receipt may not do.

## Three routes worth weighing before building

1. **A fixture container the door may legitimately dial.** Requires an address
   family the door accepts, which today means a globally routable one. Naming a
   real address the traffic does not reach is the same lie in a different place.
2. **A scope class for synthetic targets.** `receipts.scope_class` already
   separates `target` from egress support. A fourth class -- a fixture the
   evaluation opened itself, whose address is recorded as what it is -- would let
   the door authorise it without widening what `target` may reach. This is the
   route that keeps the Receipt honest, and it is the largest.
3. **Declare the loopback route sufficient and grade with a slice that does not
   need the door.** Cheapest, and it moves the problem: a Playbook graded through
   a work callable that is not the one production uses is a Playbook graded
   against a system nobody ships, which is the sentence `evaluation.py` opens with.

Pick with the reason written down. Route 2 is the one this ticket expects, and
route 3 is a legitimate answer if the reason survives being written out.
