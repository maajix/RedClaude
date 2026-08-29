---
description: Ask whether a step enforces the steps before it, by completing the flow once in order and then reaching the same step from a session that never took them -- spelled a different way, or entered from a second flow whose steps the step's own guard may be reading.
bb:category: business_logic
bb:outputs: ["business_logic.workflow_order"]
bb:triggers_all: ["flow_step", "state_changing_method"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: constrained
bb:effects: mutates_object
bb:baseline: pristine_surface
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 51 as the v2 replacement for v1's routing pack, against the workflow-order leaf of the ticket 18 vocabulary; two v1 texts are attached as maintainer references and both describe the spellings section 3 sends. Rewritten for ticket 101 against the merged ledger's six readings for this slug. Three close a Test, one is a selector that closes nothing, and two are named in the closing section, one as another Playbook's reading and one as blocked by the method enum; the dot-segment spelling is split off from the spellings Test as a lead of its own, because the specification checker refuses that path. The declared bar is response_differential in all three entries rather than state_change, because the outcome read that sees the effect is itself an action of the same Test and an evidence edge cannot be added once the claim is past proposed, so the kind the settling assertions derive is the only kind the bar can name.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_differential", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "response_differential", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "response_differential", "polarity": "supports", "min_count": 1}]
bb:references: ["http-attacks-verb-tampering.md", "status-code-bypass.md"]
---

# Ask what the step before this one was for

A flow is a sequence the interface walks: cart, address, payment, confirm. Enrol, verify, activate. It
runs in that order because the interface is what the developer tested, and each route is usually written
as if the one before it had already run. The subject here is a route something else leads to, which is
what makes it a step, and the question is whether the step is a step or just a route that happens to come
later in the screens.

Sends go through `mcp__rk2__http_request` and Tests are proposed through `mcp__rk2__propose_test`. Since
ticket 211 a Test action states `headers` and a `body` beside its method and url, which is what puts the
override-header arm of section 3 on the Finding path. A setup or a cleanup step still carries a method
and a url alone, so a flow step that needs a posted body is walked on the ordinary door before the Test
opens; the door opens that run body-bearing because a Playbook was selected, not because this one admits
to changing something.

close_test_replay is the only writer of the transition from testing to supported that a Finding needs,
and it derives the Observation kind from the Test's own assertions rather than from what came back. The
bar is response_differential in all three entries, so every entry is an Observation a Test writes. It is
not state_change: the outcome read that sees the effect is an action of the same Test, and an evidence
edge cannot be added once record_test_action has moved the claim past proposed. An agent-filed
state_change still names the mechanism where a step takes one, but it corroborates and never settles.

**The whole reading runs inside one Task holding one Identity, and every arm goes out under it, the
step choosing nothing.** The differential is what the session has already walked and never a value
this reading states, so nothing is dropped before the wire. `Session.capture` puts the target's `Set-Cookie` into the
leased jar and `Session.inject` puts it back on every later request: the jar accumulates and cannot be
rewound, which fixes the arm order in section 5 and blocks the three-jar form of that reading outright.

## 1. Walk the flow once, and record what nothing looks like

Complete the flow the way the interface does, storing every answer, all as whichever Identity the Task
was opened under -- the step does not choose it and there is no argument for it, so the flow is walked
once by one caller rather than assembled from several. A run that has not walked the flow does not know
which steps exist and cannot say a step was skipped -- it can only say a route answered. Complete this
step with the ordered list of routes, the route stating the authoritative outcome, and what it reads as
when the flow was earned.

Then read the authoritative outcome route on a fresh flow instance that has taken no steps at all, and
store that answer. That is what "nothing has happened" looks like and it is the other end of every
difference below. `pristine_surface` is the baseline: a flow another Playbook advanced under this one
turns every verdict here into a statement about two runs.

## 2. Take the step alone, and read the verdict at the outcome route

On a fresh flow instance under the same Identity, send the subject step exactly as the walk sent it --
same method, same path, same body, only the earlier calls missing. The step's own answer is not the
verdict. The authoritative outcome route is.

**Five actions, and all three roles are present.** Actions 1 and 2 carry role `baseline`: the outcome
route read twice on the completed flow with nothing sent between, asserted `body_equals`, because a
`body_differs` verdict fires on a timestamp as readily as on a state change. Action 3 carries role
`control`: the pristine outcome read. Action 4 carries role `variant`: the lone step itself, carrying the
body the walk sent, which an action may state since ticket 211. Action 5 carries role `variant` too: the
outcome route read after it, asserted `body_differs` against action 3. That assertion is the differential
close_test_replay reads off the specification, and it writes that kind whichever way the reading goes --
the refutation is the same Test settling on an outcome that stayed where the pristine read left it.

Where the outcome matches neither the completed-flow answer nor the pristine one, record it and stop. A
half-applied flow is a state the application did not expect and is not evidence about ordering, and the
reading does not continue into further spellings from it. Describe the half-applied state to the operator
before anything else is sent, then unwind through the target's own route and read the outcome back. That
halt is a reading that ran out and it names no question code.

## 3. Try the spellings a Test can carry

Where the lone step was refused, the refusal may belong to the front of the stack rather than to the
application, and the same route reached differently is what the two attached references call verb
tampering and status-code bypass. Every spelling stays at the recorded route on the recorded host.

One Test per spelling, each on a fresh flow instance, and the first spelling that moves the outcome ends
the section. The same path under a different method the route also serves, including `HEAD`. The same
path with a trailing slash, a doubled separator or a mixed-case segment. And the step's own request sent
as `GET` carrying `X-HTTP-Method-Override` -- or `X-Method-Override`, or `X-HTTP-Method` -- naming the
step's verb, which is the reachable substitute for a verb the method enum has no word for. That last arm
is an action header: the name matches the door's pattern and is neither hop-by-hop nor `x-redkraken-*`,
so it forwards. `HEAD` is the sharpest arm and the easiest to over-report -- a 200 to `HEAD` says the
handler ran and never what it returned, which is why the verdict is read at the outcome route.

**Six actions, all three roles.** Actions 1 and 2 carry role `baseline`: the completed-flow outcome read
twice, so a `body_differs` verdict is not a timestamp. Action 3 carries role `control`, the pristine
outcome read, and action 4 carries it too -- the leg the shipped text did not have and the one the
references insist on, the same decoration applied to a path that certainly does not exist, asserted
`status_equals` 404, because a server answering 200 to anything of that shape has produced every result
in this section. Action 5 carries role `variant`: the spelling itself. Action 6 carries role `variant`
too: the outcome read after it, asserted `body_differs` against action 3. `status_equals` states a status
and names no second action, so action 4 is not part of the differential.

Where a spelling reaches a route the flow does not contain at all -- an admin console, a debug handler --
or the outcome shows an effect on an object the flow does not own, stop on that spelling: the claim is
`authorization.function_access` and continuing here would grade the wrong class. The other spellings may
still be sent. Record the spelling, its answer and the class it was handed to, and tell the operator and
that Playbook's owner.

## 4. The spelling a Test cannot carry

**This is a lead: it stops at an Observation and cannot become a Finding.** A dot segment is the
decoration the references name and the one the specification checker refuses: rk2_test_request_problem
rejects a `.` or a `..` segment in the path and `%2e` anywhere in the url, so no Test action carries it,
while the ordinary door forwards both verbatim in origin form.

The reading is performable through `mcp__rk2__http_request`, and the outcome read after it is a real
state_change filed with the proposal through `mcp__rk2__submit_mission_result` before the section 3 Test
is proposed, because an edge cannot be added once the claim is past proposed. It corroborates and never
settles. Send it, file it, and let section 3 carry the claim.

## 5. Ask whether one flow's guard reads another flow's slot

Where the target runs two multi-step flows with per-phase endpoints, at least one reachable without a
credential and both sharing a plausible phase marker, the ordering question has a second form: the guard
on a late step may read a session slot the other flow writes.

**The arms are sent baseline, then control, then variant, and that order is not a preference.** The jar
only accumulates, so an arm sent early can never be un-walked and the reading cannot be re-run without a
fresh Identity. Four actions, all of them requests for the guarded late step. Actions 1 and 2 carry role
`baseline`: the guarded late step before anything has been walked, sent twice unchanged and asserted
`body_equals`. Action 3 carries role `control`: the same step again after an equal number of unrelated
requests on the same session -- a search, a product page -- and it must still refuse, which rules out
both "any warm session passes" and "a guard that only checks a session exists". Action 4 carries role
`variant`: the same step once more, asserted `status_differs` against action 3, after walking step 1 of
the guarded flow and then steps 1 and 2 of the unguarded one on the ordinary door. A guard that is now
satisfied says one session slot was serving both flows.

Where the guarded phase is entered -- the late step answers rather than refusing -- stop there and send
nothing further in either flow. Completing a reset or a registration on the far side of the guard is an
account takeover and not a reading. Tell the operator immediately, because a guard satisfied without its
own predecessor is an authentication-adjacent result, and record the interleaving, the reads and the
account named in every arm. The unguarded flow needs no unwind: only its early steps were walked.

## 6. Read what OPTIONS advertises, and use it to choose a verb

**This is a lead: it proposes no Test and settles nothing.** `OPTIONS` the recorded route, then
`OPTIONS` another route the flow does contain, which separates a route advertising these methods from a
server advertising one set for everything. Both go through `mcp__rk2__http_request`, and the agent files
header_policy_observed from each Receipt through `mcp__rk2__submit_mission_result` before the section 3
Test is proposed. `Allow` is stripped by neither the hop-by-hop set nor the wire response filter, so the
value arrives.

The advertised set is a selector and never the evidence: `Allow` frequently lies about what the handler
dispatches, so it chooses which verb section 3 sends and supports business_logic.workflow_order not at
all. A proposal citing it as the ordering evidence is refused at the proposal rather than at the
request. Record the advertised set and that it was used as a selector.

## 7. State the claim, and state what would refute it

The Hypothesis is `business_logic.workflow_order` on the step, proposed through
`mcp__rk2__propose_finding`. It is supported when the authoritative outcome shows the step's effect with
the earlier steps never taken, against a control that shows the same effect when they were, and with the
nonexistent-path decoration control still answering 404. It is refuted when the outcome after sections 2,
3 and 5 is the pristine one.

A step that answers `200` and does nothing is not this claim. Neither is a sequence the target never said
was one: where the interface offers the step directly, the order was not a rule and there is nothing here
to break.

## 8. Advance one flow, unwind it, and the two readings this slug refuses

This Playbook's effects are `mutates_object`: it moves one flow forward without its earlier steps, on
purpose. One flow per reading, on the tester's own account, cancelled or emptied afterwards through the
target's own route with the outcome read back to confirm. It does not send the same step repeatedly to
see how far the state gets, it does not walk another Identity's flow, and it does not test what a route
does under load: availability is not a Property class here.

Two readings are named here rather than performed. Supplying an off-site authority to a redirect
parameter and reading where the response points is reachable and is not this reading: the class here is
`business_logic.workflow_order`, and where a browser is sent is a claim with no flow and no ordering rule
in it. It is recorded so it is not derived a third time, and no third-party host, shortener or paste site
is named from here. Reaching the step under `TRACE`, under `CONNECT` or under an invented method token is
blocked outright: the method argument is a closed enum of `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `HEAD`
and `OPTIONS`, restated for the specification checker, and with no request there is no Receipt and
nothing to file. The substitute is section 3's override header, and what is recorded is the refused
method beside the arm sent in its place.

This section performs nothing and grades nothing. 5 of 8 steps cannot be graded.
