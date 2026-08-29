---
description: Ask whether a write is refused when the object's own state forbids it and whether it binds only the properties the interface offers, by sending one operation against a permitting object, a forbidding object, a retired version of the same route, a verb the route never advertises and a property the interface never sends, and taking every verdict from the owner's own read-back.
bb:category: authorization
bb:outputs: ["authorization.object_property_write", "authorization.state_transition"]
bb:triggers_all: ["multiple_test_identities", "path_parameter", "state_changing_method"]
bb:skills: ["compare-responses", "enumerate-surface", "use-identity"]
bb:risk: constrained
bb:effects: mutates_object
bb:baseline: pristine_surface
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 51 as the v2 replacement for v1's api-authorization pack, against the state-transition leaf of the ticket 18 vocabulary; two v1 texts are attached as maintainer references and both describe the identifier work section 1 rests on. Rewritten for ticket 101 against the merged ledger, which carries six readings for this slug and no refusal. Three keys moved. bb:outputs gains authorization.object_property_write, one of the nine leaves nothing emitted, because four readings ask which property a write binds rather than which transition it performs, and D3 settles that the emitter line closes inside this ticket. bb:skills gains enumerate-surface, which the retired-prefix reading needs to take a version prefix off a bundle rather than off a wordlist. The refuted variant leg moves from response_invariant to state_change, the kind the supported leg of the same role names, because close_test_replay derives a kind from the specification and one role writes one kind whichever way the reading comes out.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "state_change", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "credential_effect", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "state_change", "polarity": "supports", "min_count": 1}]
bb:references: ["idor.md", "uuids.md"]
---

# Ask what the object's own state forbids, and what the write binds

An object carries a state, and the state is half of the authorisation decision. A shipped
order cannot be cancelled, a closed ticket cannot be reopened by its reporter, a revoked
invitation cannot be accepted. Applications write the owner check once and the state check
per route, which is why the owner check is the one usually there. The other half of the
question is which properties the write binds, because a route that reaches the object
decides twice -- whether this caller may move it, and which of its fields the request may
name.

Every reading below is one Test of at least three actions holding a baseline, a variant and
a control, because rk2_test_spec_problem refuses a specification performing fewer than three
or leaving a role out. Since ticket 211 an action states headers and body as well as method
and url, so a property-binding arm is an action rather than a send filed beside one. The
arms go out with `mcp__rk2__http_request`, are filed as one specification with
`mcp__rk2__propose_test`, and close_test_replay closes them. The state_change and
credential_effect Observations this Playbook's bar names are agent-filed and ride WITH the
proposal through `mcp__rk2__submit_mission_result`, which promote_proposal writes -- an edge
cannot be added once a claim is past proposed.

## 1. Name the object, the transition and the two Identities

The subject is a state-changing route naming an object in its path. Read the parameter that
names the object from the state view rather than from the URL, and read the object's states
from the route that returns it -- the transition this Playbook asks about is the target's
own, not a name invented here. Name two Identity labels the mission packet supplies. Label A
owns the objects and label B owns none of them; a call goes out as whichever Identity its
Task was opened under and there is no argument for it, so the label B arm is a second Task
and the comparison cites the Receipts both produced.

Then read every object this reading will touch, through label A, before anything is sent,
and store the answers. That is why the declared baseline is pristine_surface: an object
another Playbook moved between this section and the read-back makes every later reading a
statement about two changes. Without an object already in the forbidding state there is
nothing to ask, and this Playbook does not apply. This section reads and stores, proposes no
specification and grades nothing.

## 2. The transition the object's own state should forbid

One Test, six actions, every one of them as label A. Action 1 carries role baseline, the
read of the forbidding-state object before anything is sent -- this Test's own pristine
answer, taken again here because an assertion names ordinals inside its own specification
and section 1's stored copy is not one of them. Action 2 carries role baseline as well,
the operation on label A's object in a state that still admits it, which succeeds and so
says the route works and the operation is available to this caller at all. Action 3
carries role variant, the same operation, same method and same body shape, on label A's
object whose recorded state should forbid it; one variable moves against action 2 and it
is the object's state. Action 4 carries role variant as well, the read of that same
object again once action 3 has been sent. Action 5 carries role control, the same
operation on an identifier that names no object. That is the control most runs skip and
it decides the reading, because an application answering 404 for a missing object and 404
for a forbidden transition has said nothing. Action 6 carries role control too, the read
of an untouched sibling object sent twice unchanged and named by no differing assertion,
which is what leaves a response_invariant in the control role.

The status line of the variant is not the verdict, and body_differs naming action 4
against action 1 is what close_test_replay closes. An application answering 200 and
changing nothing refused in a confusing way; one answering 500 and cancelling the order
did the thing this Playbook asks about. `mcp__rk2__run_skill_script` naming
compare-responses states that difference in the report, and the state_change edge over
action 4's Receipt is filed with the proposal in the role variant.

Run the operation once as label B on label A's object. It must be refused, and that refusal
is the credential_effect this Playbook's control bar names. An arm that succeeds there is
authorization.object_ownership and routes to the Playbook holding that class, because an
object anyone may operate on says nothing about which states forbid the operation; a 404 for
a missing object against a 403 for one the caller does not own is
information_disclosure.identifier_oracle and routes out the same way. An after-state read
that is refused, or answers a body the difference cannot attribute, is inconclusive and is
reported as inconclusive.

## 3. The same transition through a version the route retired

Applications version a route and leave the old copy answering. The moving variable is which
copy of the rule replied, so the object identifier is the same in every arm and only the
path prefix moves. Take both prefixes from the application's own publication -- js_routes or
js_map under `mcp__rk2__run_tool` over a bundle the Program already fetched, a served
specification, or a `.well-known` document the application publishes and which names a version
the current prefix no longer carries -- never from a wordlist run at volume, and both inside
scope.

One Test. The baseline is the current prefix carrying the forbidden-state transition, which
is refused. The variant is the identical transition on the identical object through the
retired prefix. The control is a version prefix that certainly does not exist for the same
object and must answer 404, because where every /api/vN answers, the prefix is not a version
and the variant proved nothing. A second control repeats the retired prefix's read route
unchanged. status_differs naming the retired-prefix arm against the nonexistent-prefix
control is what close_test_replay closes, and the owner's read-back carries the state_change
edge. Enumerating objects under the retired prefix afterwards is a different reading and is
not this one.

## 4. The verb and the route the interface never offers for it

The transition is reached through a spelling the interface does not advertise, and the proof
is never the tampered request's own answer. One Test. The baseline is the declared
transition route under its declared verb from the forbidding state, which the application
refuses. The variants are the same transition against the same object under a spelling the
interface does not offer -- HEAD on the state-changing URL, then PUT, PATCH or DELETE on the
item route. The control is the same undeclared verb against a route that certainly has no
write handler, which must answer 405, so a 2xx on an arm is a handler rather than a
framework accepting everything; a second control repeats the read-back with nothing between
the two sends. Every method here is in the egress enum, so every spelling is expressible.
After each arm read the object again as label A, and body_differs naming the read-back that
followed an arm against the read-back that followed the baseline is what close_test_replay
closes. The HEAD spelling is the sharpest: the handler runs under a verb whose response
carries nothing, so the second request is the only honest proof.

## 5. The property the interface never sends

One Test whose arms are bodies, which an action states since ticket 211. The baseline is the
object PATCHed with exactly the field set the served interface carries, followed by a
read-back through the owner. The first variant adds ONE property the read representation
discloses and the interface never sends -- role, is_admin, tenant_id, owner, verified,
credit -- and reads the object back. The second variant sets a candidate property to a value
of the wrong type, which a bound property must react to and an unbound one cannot, and that
arm is what grades a property on a route whose after-state cannot be read. The first control
PATCHes a name the object does not have -- rk_nonexistent_attribute -- and reads back, and
it must land exactly as the baseline read-back did, which says unknown names are ordinarily
ignored. The second control sets the candidate property to its current valid value, read off
the representation, which must land and so proves the route reaches the property at all.
Every property name comes from the object's own read representation, never from a guess
list.

body_differs naming the added-property read-back against the unknown-name read-back is what
close_test_replay closes, and the state_change edge over the read-back Receipt is filed
beside it. The class here is authorization.object_property_write and not the transition
class -- every request is label A editing label A's own object, ownership is answered yes on
every arm, and the only differing truth is which properties the write binds. Where the
invalid value produces a 500 with a stack frame, record the error_detail for whoever holds
information_disclosure.error_detail and stop, because a crashing parser says nothing about
binding.

## 6. The rule the create path keeps and the update path drops

A route pair that creates and updates the same object may not validate the same property the
same way on both halves. One Test. The baseline POSTs the create route with one property set
to a value that route refuses -- out of range, wrong type, over length -- and the refusal is
the rule. The variant creates the object with a legal value, then PATCHes that same property
to the value the create route refused, and reads the object back through the owner. The
control PATCHes that property to a value the create route also accepts and reads back, which
must land, so a landed refused value is a missing rule rather than a route that writes
nothing; a second control repeats the create refusal unchanged. body_differs naming the
refused-value read-back against the accepted-value read-back is what close_test_replay
closes. Where the create route accepts the value the reading believed it refused, there is
no rule to be missing and the reading has no subject.

## 7. Propose the claim, and name where a reading halts

Propose it with `mcp__rk2__propose_finding`. The transition readings name workflow_bypass as
the class and the property readings name mass_assignment; that argument takes a
vulnerability_classes id and not a dotted Property class.
property_class_vulnerability_classes maps this Playbook's transition class to the first and
carries no row at all for the property class, so the second is a choice this text records
rather than one the table derives, and finding_class_divergence stays silent for an unmapped
class. The gate is rk2_finding_refusal, which opens nothing without the transition
close_test_replay wrote.

Every object this Playbook creates or moves is named in the report with the identifier
section 1 read. One transition per reading and no repeat to see whether the second also
lands; label B's objects are never touched and nothing is deleted. Two halts are a person's
decision, asked for with `mcp__rk2__park_for_human`, which carries the `task_label` of the
Task this run is executing beside the `question_code` that names why. An arm that would
fall on a shared object rather than one the test identity owns parks under
destructive_action. A route pair the Program's rules of engagement do not admit a write to
parks under scope_ambiguous, and three controls with no variant is an honest reason to
report a subject unread. The writer is park_task_for_human. Every other halt is a reading
that ran out -- one transition sent, one property graded, a create route that enforced
nothing -- and no question code says that, so those are reported through the Task's own
record.

This section proposes and grades nothing. 2 of 7 steps cannot be graded.
