# 56 — Migrate HTTP integrity and parsing Playbooks

**What to build:** Deliver production-ready Playbooks and fixtures for the three v1 topics whose findings depend on HTTP message boundaries, request integrity and parser disagreement.

**Blocked by:** 46 — Evaluate and promote one Playbook; 48 — Rework v1 Agents, Skills, references and sink packs.

**Status:** resolved

**Deviation on criterion 3:** two fixtures for three Playbooks. `request-integrity` and
`request-parsing` each ship an own-pair with explicit negative baselines; `http-desync` ships
none, and cannot. What survives of that pack is `transport.tls_configuration`, which is settled
by a measurement the proxy takes on a lane it does not intercept -- so a fixture for it would have
to terminate TLS with two deliberately different configurations and be reached by that lane, which
is a property of the harness's own transport rather than of any handler a fixture can write. The
half of the criterion the ticket names by technique is met, technique by technique, and only two
of the five by fixture. Parameter is `parameter-precedence-pair` and integrity is
`cross-origin-read-pair`, both with the negative baselines the criterion asks for. Host/header is
a fixture control rather than a fixture: `parameter-precedence-pair` ignores `X-Forwarded-Host` on
both variants, which is the explicit negative baseline for a claim `request-parsing` step 6 makes
an observation and step 7 refuses to arm, because rewriting the authority a hop routes on is how a
request arrives somewhere the Program did not grant. Smuggling and coalescing get no fixture at
all: they are not merely untested but unwritable, and 025's `ENABLE ALWAYS` trigger is what makes
that true rather than a paragraph of advice.

**Deviation on criterion 6, inherited from 49, 50, 51, 52, 53, 54 and 55:** the positive and
adversarial arrangement exists for the two fixtured Playbooks and is total; the evaluation that
would grade it has not run and cannot run from this ticket. All three ship `draft`. `stable` is
reachable only through `playbook_test_verdict` returning `pass` for the exact text, and an
evaluation run is an Agent run against a fixture listening on loopback, which `scope.compile_policy`
and `authorize_identity_egress_address` both refuse. Ticket 78 is where that route is decided for
`request-integrity` and `request-parsing`. It is not where it is decided for `http-desync`, and
that one is a harder statement: clause 1 of `playbook_test_verdict` returns `untested` for any
Playbook with no in-class own pair, so no agent run of any kind can move it while it has no
fixture. Its promotion is blocked on the fixture the deviation above says cannot be written,
rather than on the loopback route.
What moved is the measurement: the corpus is fifty Playbooks and fifty fixtures,
`playbook_fixture_binding` is still total over the fixture table, and each of the two new fixtures
is an out-of-class negative for the forty-nine Playbooks that do not output its class. The
selection half of the criterion is checked and holds: `PlaybookCorpusSelectionTest` is diagonal
across all fifty subjects, and all three new Playbooks are loadable by exactly one production
role.

- [x] HTTP Desync, Request Integrity and Request Parsing each exist as authored v2 Playbooks with complete metadata and scoped risk effects.
- [x] Tests distinguish target behavior from proxy transformation and use proxy-internal transport observations where interception would invalidate the claim.
- [x] Smuggling, coalescing, host/header, parameter and integrity variants use controlled local fixtures and explicit negative baselines.
- [x] Availability-impacting request patterns are absent unless separately granted and bounded.
- [x] Protocol claims cite exact request/response bytes and transport path rather than banner, generic error or race-only behavior.
- [ ] All three exact hashes pass relevant positive and adversarial evaluation before stable promotion.

## Comments

Implemented on 2026-08-17.

### Nine v1 pages, three readings, and one pack that was mostly unusable

v1 filed this material by technique: a desync pack of three pages, an integrity pack of two, a
parsing pack of four. What the three share is that most of their arms cannot survive this
harness. Every ordinary request is decoded and re-encoded by the interception proxy, so the bytes
the target frames are the proxy's; and the arms that do reach the target -- a poisoned socket, a
forwarded `CONNECT` -- land on the next caller, who is not part of the engagement.

So the ticket is mostly a subtraction, and each of the three documents is built around what is
left after it.

`http-desync` keeps one claim: what the target negotiated. 025 records `transport.request_framing`
as `unmakeable` behind an `ENABLE ALWAYS` trigger, so no Hypothesis about framing can be inserted
at all, and `transport.tls_configuration` is one of the two leaves that migration left
`probe_only`, with `tls_version`, `cipher` and `alpn` as its `allowed_fields`. The other,
`transport.certificate_trust`, is a different question over different fields and nothing here
claims it -- which is also why step 4 names only two shapes of disagreement rather than three: a
receipt whose chain or hostname did not verify is not citable at all, so there is no reading that
could hold one. The whole reading is two ordinary
reads and two measurements on the unintercepted lane, and step 6 says what it refuses with the
mechanism attached rather than with an argument. Its terminal case is the honest one: where the
runtime has no route to that lane, the verdict is `inconclusive` naming the missing capability,
never the ordinary path's answer relabelled.

`request-integrity` keeps the read half of v1's CORS/CSRF pack and gives the write half back to
018. `session_handling.csrf` already exists and `realtime` already outputs it, so a second
Playbook forging a write would put two documents on one class and 036's binding would grade both
against both fixtures. What had no leaf was the other direction: a response that exists only
because a session was attached, made readable to an origin nobody meant to trust.

`request-parsing` keeps parameter pollution and refuses the rest of its pack. Response splitting
needs a control character to survive re-serialisation, host-header rewrites need the proxy to
forward an authority it does not, and the WAF catalogue is detection evasion rather than a claim.

### Two new leaves, and why neither is a rename

`session_handling.cross_origin_read` is not `session_handling.cross_origin` under another name and
not `authorization.function_access`. Nothing about it is who may ask -- the caller holds a valid
session and the route was right to answer. The defect is entirely in two response headers deciding
who may read what came back, which is why the fixture's two variants serve byte-identical bodies
and differ only in `Access-Control-Allow-Origin` and `Access-Control-Allow-Credentials`. A reading
that established this class from a body established it from the wrong evidence, and the fixture is
built so that it cannot.

`injection.parameter_precedence` is in the `injection` family and injects nothing. No value in
either arm is interpreted anywhere: `xml` is a format the builder already knew, chosen because the
application does not offer it. What makes it an injection leaf rather than a parsing curiosity is
where the defect lives -- one request, two readers, and the check performed on an occurrence the
work did not use. It is the family's boundary case and the fixture says so in its own ground truth.

### The fact is a self-join, not a column

`repeated_parameter_name`, `endpoint` scope, computed in `subject_facts` by joining `parameters`
to itself on equal `name` and differing `location`. 020 keys that table on
`(endpoint_id, location, name)`, so a name that repeats necessarily repeats across two carriers.
That is not a weakened version of the fact the reading wanted -- two carriers is precisely what
lets two halves of an application disagree. A name repeated inside one carrier is a list, and
every framework agrees about lists.

It is a trigger rather than something the reading discovers, because discovering it would mean
sending every known name twice at a route that writes, and `request-parsing` is `mutates_object`
with a `pristine_surface` baseline. The recon pass records what it saw accepted; the Playbook
spends that record.

### Criterion 4, which this ticket meets by having nothing to grant

Nothing in the three sends a pattern whose cost is the target's availability. `http-desync` opens
four connections total and says in its ceiling that the two measurements are two because a
negotiation needs one repeat to be a property rather than an event -- not many connections to see
which get a different answer. `request-integrity` sends four requests and changes nothing.
`request-parsing` sends four and creates at most one object per send, each named in the finding
with the identifier the route gave it, and its ceiling forbids re-sending the arm to see whether
it works twice. No arm in any of the three is a race, a flood, a renegotiation or a long-poll, so
there is no bounded grant to write down: the criterion is met by absence rather than by a budget.

### Criterion 5, and why `http-desync` refutes with a receipt

`http-desync` is the only Playbook in the corpus whose three evidence rows are all
`transport_parameters_observed`. That is the criterion stated as schema: the claim cannot be
carried by a banner, by a generic error or by a race, because the only evidence kind that can
transition its Hypothesis is a measurement the database judged citable, taken on a named lane.
The other two refute with a `response_invariant` -- the same request under a different origin, the
same request with the name in one carrier -- and support with a `response_differential`, because
both are comparisons between two sends of one route rather than readings of one body.

### What tells the three apart on the Surface

`http-desync` triggers on `read_method`, `spa_surface` and `tech_edge_proxy` -- a terminating
front end is the thing that has a TLS configuration to differ from what the deployment
advertises. `request-integrity` is the corpus's only `authenticated_endpoint` +
`header_parameter` + `read_method` triple: the answer varies with a header the caller controls,
which is what an origin is. `request-parsing` is the only reading anywhere keyed on
`repeated_parameter_name`, which is why the fact was added rather than borrowed.

All three are `web_hunter`'s. `request-parsing` and `http-desync` carry `compare-responses`
alone, which by 048's capability rule already fixes the role; `request-integrity` adds
`use-identity` because it holds a session, and no other role can load either skill together.
