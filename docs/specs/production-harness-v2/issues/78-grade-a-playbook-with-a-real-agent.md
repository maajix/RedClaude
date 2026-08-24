# 78 — Grade a Playbook with a real Agent behind the door

**What to build:** A route by which the Agent that does the work in `rk playbook evaluate` reaches a synthetic fixture the way it reaches a real target -- through the door, with a Receipt per request -- without giving the door a way to dial the machine it runs on.

**Blocked by:** 46 — Evaluate and promote one Playbook; 175 — An evaluation works a Program once and stops before the Playbook; 176 — An evaluation points every Program at a route its fixture does not serve; 177 — A door refusal of one request throws away a whole repeat; 178 — A graded Playbook names a Skill its own role cannot open.

**Status:** resolved

- [x] An evaluation run with an Agent boundary configured reaches the fixture, and the requests appear as Receipts against the evaluation Program.
- [x] The address a Receipt pins is the address that was dialled. A fixture reached by a name that resolved to something else is a Receipt that lies, and closes nothing here.
- [x] `scope.compile_policy` still refuses an inclusion naming a loopback, private, link-local or documentation address, and `authorize_identity_egress_address` still refuses to dial one. Whatever this ticket adds, it does not add a Program configuration that can point the door at 127.0.0.1.
- [x] `check_playbook_tests` gains an arm, or an existing one is extended, so a filed run with zero `tool_runs` against a configured Agent boundary is a reported problem rather than a silent zero.
- [x] The existing loopback path keeps working for a machine with no Agent boundary. Both routes are documented in `evaluation.py`, with which one a given run took visible in the report.

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

## What was built

Route 2, and the reason is the one the ticket wrote down for it: it is the only
route on which the Receipt stays true. Routes 1 and 3 were declined -- 1 records
an address the request did not go to, and 3 grades a Playbook with a work
callable production does not use.

**A fourth scope class, and one table that gives it an address.**
`fixture_addresses` is one row per evaluation Program: the host its own
compiled policy already classes `target`, the port the fixture bound, and the
address that host is actually listening at. `open_fixture_address` writes it
and `authorize_fixture_address` reads it, both `SECURITY DEFINER`, and
`rk2_proxy` may execute only the second. A Receipt earned that way is classed
`fixture` rather than `target`, so a synthetic target the harness started for
itself is legible as one and `target` keeps meaning what it did.

**Nothing a configuration file writes reaches that function.**
`scope.compile_policy` is untouched and still refuses an inclusion naming a
loopback, private, link-local or documentation address, and
`authorize_identity_egress_address` still refuses to dial one. The fixture
address is fenced four ways instead: a foreign key to `evaluation_programs`, so
only a Program that is grading a Playbook may have one; a CHECK admitting
exactly one RFC 1918 or unique-local host, so it can never be loopback,
link-local or global; a `scope_class_of(..., 'coverage') = 'target'` test, so a
fixture address changes the address a target is dialled at and never makes
something a target; and `fixture_addresses_address_is_one_private_host`, so a
network cannot be smuggled in where a host belongs.

**The address is nobody's choice.** `isolation.host_route` reads the gateway of
the door's one non-internal attachment and refuses if there is no such
attachment or more than one. That address is what this machine answers on for
the door and what a child on the `--internal` Agent network has no route to, so
the fixture is reachable by exactly the process that is supposed to reach it.
`evaluation.route` calls it once and fails the run when it cannot: a described
Agent boundary with an unreadable door is a refusal, never a quiet fall back to
loopback.

**The fixture address is written after the marker and before the work.** Both
orders are load-bearing. The database will not accept a fixture address for a
Program that is not yet an evaluation, and on the door route the work's first
request is what has to find the fixture -- so `_graded_work` writes the marker,
then the fixture address, then runs the work.

**`_pin` asks about a fixture before it resolves a name.** A synthetic target is
the one destination whose address is not a property of its name, so the door
asks the database first; only when there is no fixture address does it resolve,
check `unroutable` and call `authorize_identity_egress_address` as it always
did. The class on the Receipt is the class the database answered with, and the
pinned address is the address the socket was opened to.

**The fixture route re-asks everything the ordinary route asks.**
`authorize_fixture_address` resolves the capability through
`resolve_egress_identity`, so a Tool run that selected an Identity slot whose
lease has lapsed is refused before it is told where anything is; and it re-runs
`scope_class_of(..., 'coverage')` at the Program's scope version as it stands
now, so a target withdrawn after the address was recorded is refused too. A
recorded address is where a target is dialled, not a standing permission to dial
it: without both re-reads the fixture route would be the one door path on which
a released lease or a withdrawn target still answered.

**`playbook_test_runs.route` is derived at filing, never supplied.** It is
`door` when the vulnerable Program opened a fixture address and `loopback`
otherwise, so it cannot disagree with what happened, and `check_playbook_tests`
gains an `error` arm: a run that had the door and filed zero `tool_runs` is a
reported problem rather than a silent zero. A loopback run with zero stays
silent, because on that route zero is the honest answer for a machine with no
Agent.

**Both routes are documented in `evaluation.py` and visible in the report.**
`route` is a sixth fact beside `playbook`, `fixture`, `repeats`, `runs` and
`verdict`, so an operator reading one report can see which route it took.

**Where it is proven.** `ContainedEvaluationTest` grades the shipped
object-ownership pair through a container door started by `rk proxy door`, with
each Program's request sent by `proxy.send` -- the function `rk proxy request`
calls -- and asserts that every Receipt is against its own evaluation Program,
classed `fixture`, pinned to the address `fixture_addresses` recorded.
`test_isolation.py` proves the gateway is reachable from the door and not from a
child. `PlaybookEvaluationTest` holds the SQL: what a fixture address may be,
what the door is answered with, both halves of the new check arm, and the two
refusals above -- a lapsed Identity lease and a target withdrawn after the
address was recorded. `PlaybookEvaluationCommandTest` covers the step in front
of the container class, where `rk playbook evaluate` builds the boundary out of
this machine's environment and hands it to the evaluator: a boundary naming a
door that does not exist refuses with that variable as the source, where a
command that dropped the boundary would report the loopback route and no
violation at all.

**What the suite drives is the boundary, not a model.** No Claude session is
started anywhere in the tests: `ContainedEvaluationTest`'s work spends a
capability through `proxy.send`, which is the request path an Agent's Tool run
takes and the one `rk proxy request` calls, and the CLI test proves the
described boundary reaches `evaluation.evaluate`. What no test covers is a child
started by `execution.Slice.attempt` deciding for itself what to ask -- that
costs a real Agent run per Program and answers differently each time, so it
belongs to the graded corpus rather than to the suite. Criterion 1 is therefore
proven to the depth of the route: the boundary is configured, the requests reach
the fixture, and the Receipts are filed against the evaluation Program.

**What this ticket did not do is grade the corpus.** One Playbook proves the
route; the other forty-eight are forty-eight sets of real Agent runs with a cost
and a result that may be `fail`. That is ticket 84, and the eleven deferred
criteria across tickets 46 and 49 through 57 now name it rather than this one.
