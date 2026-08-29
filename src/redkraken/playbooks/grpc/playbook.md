---
description: Ask whether a callable is anyone's to invoke, by putting a name the application never publishes where the published one goes -- in a path segment, in a request field, or in a gRPC-Web method path called under a second leased Identity -- and reading whether the answer parts from the router's own refusal.
bb:category: authorization
bb:outputs: ["authorization.function_access"]
bb:triggers_all: ["multiple_test_identities", "tech_grpc"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-02-15
bb:provenance: Written for ticket 49 as the v2 replacement for v1's grpc pack, against the function-access leaf of the ticket 18 vocabulary; v1 shipped a README for this topic and no reference text, so nothing is attached. Rewritten for ticket 101 against the merged ledger, which carries four readings here, three reachable and one blocked. The trigger set is unchanged. A first pass moved it onto path_parameter and was wrong to -- that fact is recorded for a parameter recon classified inside the path, not for the path itself, so it misses this Playbook's own subject and selects on every route that has one. tech_grpc stays required. bb:evidence keeps response_differential on both variant legs and moves the supported control leg from credential_effect to response_invariant, because two of the three readings present no credential at all and the ledger asks for credential_effect in role variant on the third rather than in role control; it survives as a named mechanism edge in section 3 and is no longer a bar no section can meet.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_differential", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "response_invariant", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "response_differential", "polarity": "supports", "min_count": 1}]
---

# Ask whether the callable is anyone's to invoke

A service is a list of callables, and the list is longer than the one the client uses. Authorisation
in these stacks lives in an interceptor, and an interceptor is configured per service or per
callable rather than derived from the schema, so a callable nobody's client invokes is a callable
nobody's interceptor was written for. The question is about the callable, not about the message it
carries; what comes back matters only insofar as it says the call was allowed.

Three readings ask that question in three carriers -- the name in a path segment, the name in a
request field, and a gRPC-Web method path called under a second Identity. The first two are
transport-independent, which is why bb:triggers_all now asks for path_parameter and the wire moved
to bb:triggers_any. Reading under two Identities is reading two Tasks: which Identity a call goes
out under is a property of the Tool run and never an argument of it, so one Task is opened under
label A and one under label B, and every step names the label whose Task it belongs to. A Test is
one run under one lease, though, so a section needing both labels closes inside one of them and
cites the other.

Every reading is one Test of three to thirty-two actions holding a baseline, a variant and a
control, because rk2_test_spec_problem refuses a specification performing fewer than three or
leaving a role out. The arms go out with `mcp__rk2__http_request` and are filed with
`mcp__rk2__propose_test`. Since ticket 211 an action states `headers` and `body` beside `method` and
`url`, so a gRPC-Web frame rides the action itself; a selection that is wholly read_only may still
carry one, because authorize_egress_request reads that permission off the Tool run's own arguments.
Two rules of the Test lane travel with all three sections: rk2_test_request_problem refuses any dot
or double-dot path segment and any percent-encoded dot anywhere in a specification url, and since
ticket 214 record_test_action compares a Receipt to its action over the query, the planned header
block and the body as well as over method, scheme, host, port and path, so two arms differing only
in a query or in a frame each record as themselves.

One rule governs how the assertions are written. Each section below names a REFUSAL REFERENCE as its
BASELINE arm -- a name that exists nowhere, a value that is not a name, a deliberately malformed
frame -- and asserts body_differs between the variant and that baseline, so the assertion holds
exactly when the boundary is missing. The ordinary published call is a CONTROL, being the variant
with the one property removed that the hypothesis is about, and so are the two identical sends that
open every section. close_test_replay derives each action's Observation kind from the specification
and not from the outcome: an action a differing assertion names, as its action or as its against,
closes response_differential, and every other action closes response_invariant. So the variant
closes response_differential either way, which is what both variant rows of bb:evidence name, and
the controls, named by nothing, close the response_invariant the control row names. A section
pointing its differing assertion at a control instead would leave that row unmet and settle
inconclusive. body_equals and body_differs compare the response body digest alone, so a volatile
Date or request-id header does not make the comparison useless; a nonce inside the body does, and
the two identical sends are what measure that. Where every arm answers 200 whatever the verdict --
and on gRPC-Web every arm does -- the status assertions carry nothing and the body digest is the
whole reading.

The credential_effect and error_detail Observations below are agent-filed, and each cites a Receipt
of an ordinary `mcp__rk2__http_request` send made BEFORE the specification is proposed: every arm
goes out once through that verb, the Observations ride WITH the proposal through
`mcp__rk2__submit_mission_result`, and the Test then replays the same arms. rk2_promote_hypotheses
drops an edge offered once the claim has left proposed, so an Observation citing a Receipt the Test
run itself produced is one nothing attaches.

## 1. Whether the router will invoke a callable the application never publishes

This reading needs a recorded surface listing at least one published callable name in a path
segment, which is what a `/package.Service/Method` route is and what every reflection-dispatch front
end is. It needs no Identity pair and no body: where the front end answers a GET, or answers a
bodiless POST with a router-level refusal, that bodiless spelling is the one to write the
specification with, and where the front end demands a frame before it routes, section 3's
precondition applies instead.

Baseline, the identical request to a name that exists nowhere, which is the refusal reference and
the reading's whole point: it separates a router that invoked an unpublished callable from a router
that answers everything alike. Variant, the identical request to a name the runtime can reach and
the application never advertises. Two controls: the published name, whose answer is what "this
router routes" looks like on this surface, and the two identical sends of the baseline for the noise
floor. The specification names the unpublished-name action in a body_differs assertion against the
nowhere-name baseline, and in a status_differs assertion beside it where the statuses part. Halt the
moment the unpublished name answers with anything other than the router's refusal shape: stop, name
no further callable, and in particular none that writes or that takes an argument.

## 2. Whether a request field names the callable to invoke

This reading needs a route taking a callable NAME in a request field rather than in a path segment
-- a query key spelling action, method or op, or that same key in a document. The probe is read-only
by construction, because the name it sends is one that cannot exist.

Baseline, the identical request with the field carrying a value that is not a name -- empty, or a
value of another type -- which is the refusal reference and separates a dispatcher that looked the
name up and failed from a route that validates the field and refuses anything unfamiliar. Variant,
the identical request with a syntactically valid name that cannot exist, where a reflection
exception, a "no such method" message or a stack frame naming a dispatcher is the claim that the
field reached a dispatcher at all. Two controls: the field carrying a name the application
publishes, answered normally, and the two identical sends of the baseline.

The specification names the cannot-exist action in a body_differs assertion against the not-a-name
baseline, and error_detail is the agent-filed mechanism edge naming the dispatcher the message
exposed. Prefer the query spelling; since ticket 211 the document spelling rides the action too, so
that carrier is now a Test rather than an agent-filed Observation, and the guard of the paragraph
above compares both by digest. Halt at the probe. Do not name a callable that writes and do not
supply an argument list: that is an impact Task opened under `mcp__rk2__open_impact_task`, never a
step inside a detection reading.

## 3. Whether a gRPC-Web callable checks who is calling it

This reading needs the recorded surface to say the deployment fronts the service with a gRPC-Web
proxy -- an Envoy filter or a gateway. It is not a way to discover one, and where the surface does
not say so, the refusal in section 4 applies instead. It also needs two labels: A, whose client
calls the method, and B, which should not reach it. gRPC-Web is reachable where the native protocol
is not, for three reasons worth stating because they are exactly the three the native reading fails
on: it does not depend on HTTP/2 framing and works over HTTP/1.1, its trailer block rides INSIDE the
response body rather than in an HTTP trailer, and application/grpc-web-text+proto is base64, so one
length-prefixed frame is spellable as a printable string body.

The whole Test runs inside label B's lease. replay.run holds the one Identity its Task was opened
under for the length of a run, so a specification whose arms need three Identity states is one no
run can carry, and the arms that need a second state are cited in the report rather than named
here.

Baseline, A's method called from B's Task with a deliberately malformed frame: this section's
refusal reference, and the shape the route answers with when it never reached the callable. Variant,
the byte-identical call to A's method from B's Task with a well-formed frame, where grpc-status 0 in
the decoded trailer block is the claim. Two controls: B's Task calling a method B's own client
calls, which says B's credential is accepted somewhere and without which a refusal under B might
only mean B was never authenticated; and the two identical sends of the baseline. A's own call under
label A, and the same call from a Task holding no leased Identity, are separate readings named in
the report and not arms of this Test.

The specification names the variant in a body_differs assertion against the malformed-frame
baseline, and credential_effect from the variant's own pre-proposal Receipt is the agent-filed
mechanism edge in role variant. Halt where grpc-status 12 comes back on either arm, or where the
malformed-frame baseline answers as the B-calls-B control did, which says the route is answering
about the encoding rather than about the caller: stop and report inconclusive. A 12 says the front
end did not route the call, not that the call was denied, so it refutes nothing. Do not reach for a
method neither label calls, which is a second question and makes an unroutable name
indistinguishable from a refusal.

## 4. Propose the claim, name where a reading halts, and state what is refused

Propose it with `mcp__rk2__propose_finding`, naming function_level_access as its
`vulnerability_class`: that argument takes a vulnerability_classes id and never a dotted Property
class, and property_class_vulnerability_classes is what maps this Playbook's own output onto it. The
gate is rk2_finding_refusal, which opens nothing without the transition close_test_replay wrote.

Three halts are a person's decision, asked for with `mcp__rk2__park_for_human` carrying the Task's
own `task_label` and the `question_code` naming why. Enumerating further callables on a service
prefix after section 1 has found one parks under scope_ambiguous. A name that writes or that takes
an argument, which sections 1 and 2 both stop short of, parks under destructive_action. Section 3
needing a second leased label where the Program has issued one parks under credential_needed. Every
other halt is a reading that ran out -- the refusal reference matched, the probe answered, a 12
arrived -- and none of the five codes says that, so those go through the Task's own record with all
three Artifact digests, the compare-responses output and the exact names sent, so a reader can
re-run one request.

One reading is blocked, and it is the one this Playbook's slug is named after: calling a native gRPC
method over HTTP/2 and reading grpc-status out of the response trailer block. Three walls stand
together. The door negotiates HTTP/1.1 by ALPN and offers nothing else, and the h2c upgrade route is
closed by construction because upgrade and connection are both hop-by-hop names the forwarder drops.
The trailer block never reaches the agent view, because trailer is itself a hop-by-hop name and no
trailer-reading path exists on the response side. And a native frame is a one-byte compressed flag,
a four-byte big-endian length and binary protobuf, which a string body cannot spell byte for byte.
All three have to be answered together: any one alone leaves the reading unrunnable, and no
arrangement of the other two is a workaround. Record which wall was hit first, so a later reader
does not re-derive the other two. This is the reading the shipped triggers were scoped to, and
moving tech_grpc into bb:triggers_any is what stops the whole Playbook waiting on it.

Beyond that: this Playbook varies the name in the request line and the label the Task was opened
under, and nothing else. It does not vary the message a call carries, does not enumerate a service,
and sends no name that writes. This section proposes and refuses and runs no Test, so it grades
nothing. 1 of 4 steps cannot be graded.
