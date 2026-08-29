---
description: Ask what a deployment advertises about its own transport and whether the advertisement is the deployment's policy or one fleet member's, by reading the subject twice unchanged and differencing the pair against a route on the same origin the front end serves differently.
bb:category: transport
bb:outputs: ["transport.header_policy", "transport.tls_configuration"]
bb:triggers_all: ["read_method", "spa_surface", "tech_edge_proxy"]
bb:skills: ["compare-responses"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: none
bb:status: draft
bb:stale_after: 2027-05-15
bb:provenance: Written for ticket 56 as the v2 replacement for v1's http-desync pack against the tls_configuration leaf 018 already named; the pack's three pages are attached as maintainer references and its smuggling, desync, coalescing and tunnelling techniques are refused by the last section, because 025 records request framing as unmakeable behind the interception proxy and enforces that refusal in a trigger. Rewritten for ticket 101 against the merged technique ledger, which holds one executable reading, two blocked ones and two refusals for this slug. The one that executes is a header-policy reading, and bb:outputs gains transport.header_policy under D3 so that this Playbook has a step its own harness can perform -- the alternative leaves it describing only readings the harness refuses. The evidence rows move off transport_parameters_observed, which the ledger established has no agent-reachable writer by any path. The repair swapped the roles -- the identical repeat is the control, the differing sibling the variant.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_differential", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "response_invariant", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "response_differential", "polarity": "supports", "min_count": 1}]
bb:references: ["http-attacks-http-2-downgrading.md", "http-attacks-request-smuggling-and-http-desync.md", "proxy-tunnels.md"]
---

# Ask the deployment what it says about its own transport

Every ordinary request this harness sends is decoded and re-encoded on the way
out. The bytes the target frames, the protocol it agreed to speak and the
certificate it presented are all things the interception proxy saw and the
reading did not, and a reading that reported them would be describing its own
door.

That is not a gap in this Playbook, it is this Playbook's subject. What a
reading here can hold is what the deployment tells callers about itself, in
headers that survive to the agent view, read twice so that an advertisement is
a policy rather than one fleet member's configuration. What it cannot hold is
the measurement the slug is named for, and section 3 says exactly why rather
than leaving it to be rediscovered.

The subject is a read on an application shell with a terminating front end in
front of it. The whole executable reading is three requests.

## 1. Read the advertisement, twice, against a route that differs

Send the arms with `mcp__rk2__http_request`, presenting nothing, and propose
the reading with `mcp__rk2__propose_test`. Three actions, in plan order and
never re-ordered.

* action 1, role baseline, the subject
* action 2, role control, the same url again, unchanged
* action 3, role variant, a route on the same origin the front end serves
  differently

Two assertions. `body_equals` on action 2 against action 1 says the deployment
answers one way, so what it advertises is its policy rather than one member's;
that arm is named by no differing assertion, which is what leaves it a
response_invariant in the role this Playbook's bar asks it for.
`body_differs` on action 3 against action 1 is the reading, and it is
load-bearing rather than decorative -- without an arm that is known to differ,
an invariance is equally well explained by a comparison that never fires.

Neither assertion can see the three values recorded next. Both body kinds read
the stored response body digest alone, so the delivery protocol, `Alt-Svc` and
`Strict-Transport-Security` sit outside every assertion a Test can state, and
they travel instead as the agent-filed edge named at the end of this section.

Record from the answers alone, for each of the two identical sends, the
protocol the response was delivered over, `Alt-Svc` if it is there, and
`Strict-Transport-Security` if it is there. Write the word absent for each one
that is not present. An absent header is a measurement; a guessed one is not.
Neither of those two names is stripped from the agent view, so both survive to
the reading, and a value that moved between the two sends is one member's
configuration rather than the deployment's.

The writer is `close_test_replay`. It takes the Observation kind from the
specification rather than from the outcome, so the repeated control arm carries
`response_invariant` whichever way the run comes out and the differing sibling
route carries `response_differential`, and it is the only runtime writer that
carries a Hypothesis from testing to supported. Beside it, an agent-filed
`header_policy_observed` edge names each of the three values or its absence,
and `promote_proposal` writes that one from the read's own Receipt.

## 2. State the claim, and state what would refute it

The Hypothesis is `transport.header_policy` on the subject, and it has to be
that one. A supporting edge filed on this Playbook's other declared class is
refused where it is written, because that class is probe-only and admits one
Observation kind that nothing on the agent's side can produce -- so even the
invariant the Test just wrote would be rejected at insert. Section 3 is where
that wall is set out.

It is supported when the two identical reads are byte-identical and the sibling
route differed from them, which is what both assertions state and all that they
state. It is refuted when either fails -- the repeated read is not byte-identical,
so the deployment has no single advertisement and the premise a comparison rests
on is not there, or the sibling came back identical, so nothing distinguishes
this deployment's routes at all. Both legs of the variant are
`response_differential`, because one role writes one kind whichever way the
reading goes.

The three recorded values are not in either assertion and no Test can compare
them. They are carried by the agent-filed `header_policy_observed` edge alone,
and a report that reads a difference between the two sends off that edge says
so in those words.

Anything else is inconclusive -- a subject that answers nothing, a front end
that rewrites both reads into one page. Where the two reads disagree, say which
of the three moved. Do not average them and do not take the second.

Where the question is which channel policy headers a page carries to a framing
context rather than what a deployment says about its transport, the Playbook is
`browser-framing`. Where the question is whether the front end and the
application resolve one path differently, the class is
`authorization.edge_rule` and the Playbook is `deployment`.

The gate is `rk2_finding_refusal` and what it wants is the settling transition
`close_test_replay` wrote for the Test above.

Open the claim with `mcp__rk2__propose_finding`, citing both Receipts, the
three values from each and the word absent where one was missing. This section
proposes no Test of its own and grades nothing.

## 3. The measurement this Playbook was named for, and the certificate

This section is a lead and cannot be graded. It records two blocked readings so
that neither is re-proposed as a documentation gap, and the cause in both is
this harness rather than the target.

The unintercepted measurement exists and no reading here may cite it. The door
takes it automatically after the first https exchange with a target, once per
target for as long as the process is up, so there is no argument that requests
one and no way to repeat one. Its Receipt is on the internal lane, which a
proposal element may not cite and which the state policy hides from the agent
role outright. The record the agent can read projects none of the negotiated
fields, and the one Observation kind a probe-only transport claim will accept
demands both a citable Receipt of that lane and metadata the proposal writer
hard-codes past. Three walls, and lifting any one of them alone changes
nothing.

`transport.certificate_trust` is worse and is worth its own sentence. Every
certificate field a client behind this door can see belongs to the run's own
authority, because the door mints a leaf per host, so a reading that reported
one would be reporting this installation. The verified-chain and
verified-hostname fields on the measurement Receipt are conjuncts of the
citability column, so a Receipt whose chain did not verify is not citable at
all and no reading can ever hold one to report from. That class stays
unemitted, and this is why it is not cheap to close.

A reading that finds itself wanting either of these stops, says which
capability was missing in those words, and routes to an operator. That is a
better outcome than a claim the evidence cannot carry, and until those routes
exist it is the only honest one available here.

## 4. Framing, tunnelling and a position on the wire

This section is a lead and cannot be graded. It records the refusals the v1
pack under this name was mostly made of, each with the reason that travels with
it.

`transport.request_framing` cannot be written down. It is registered unmakeable
and the guard that enforces that is a trigger the database always runs, so the
claim is refused where it is first written rather than found not to work.
Independently, the two framing headers are both hop-by-hop and dropped before
the wire, there is no length argument because the door re-measures the document
it re-serialises, and a header value is printable ASCII so no line break can be
spelled into one. A body is a model-authored string and chunk framing can be
typed into it, which is precisely the hazard -- the door's recomputed length
and the typed framing would disagree, and that disagreement is the ambiguous
framing this corpus refuses to construct. The second reason is the one that
settles it either way. The remainder prefixes the next request on that
connection, the next request belongs to somebody who is not part of this
engagement, and a technique with no bounded blast radius has no undo.

Nothing here tunnels or coalesces. The method enum holds no tunnel verb, there
is no argument that expresses a request-target form, and a caller-written host
header never reaches the target because it is hop-by-hop and the wire headers
are rebuilt without it -- so the whole virtual-host family is excluded by
construction rather than by policy. A machine-in-the-middle position is refused
by decision for the same reason a tunnel is. The destination or the position is
the whole point, and both are outside what the Program granted.

Where a hop routes on a caller-supplied authority and a second component builds
a url from a different one, the class is `injection.parameter_precedence` and
the Playbook is `request-parsing`. Where a caller-supplied parameter decides
what the server fetches, it is `injection.request_forgery`. Where the question
is what a front end stored and handed to the next caller, it is
`information_disclosure.cached_response`, which web-cache asks with a read that
reaches nobody else. Request-target mangling is performable here, because the
door forwards dot segments and repeated slashes verbatim, but it is not this
Playbook's -- it lands in the authorization or the caching family and neither
is in the transport family this category confines it to.

This Playbook is read_only, holds no session and sends three reads to one
deployment. It does not scan a port, renegotiate, offer a restricted parameter
set, or open many connections to see which of them answer differently.

3 of 4 steps cannot be graded.
