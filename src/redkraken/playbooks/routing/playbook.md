---
description: Ask whether a step enforces the steps before it, by completing the flow once in order and then reaching the same step from a session that never took them, including where the step is spelled a different way.
bb:category: business_logic
bb:outputs: ["business_logic.workflow_order"]
bb:triggers_all: ["flow_step", "state_changing_method"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: constrained
bb:effects: mutates_object
bb:baseline: pristine_surface
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 51 as the v2 replacement for v1's routing pack, against the workflow-order leaf of the ticket 18 vocabulary; two v1 texts are attached as maintainer references and both describe the spellings step 4 sends.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_invariant", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "state_change", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "state_change", "polarity": "supports", "min_count": 1}]
bb:references: ["http-attacks-verb-tampering.md", "status-code-bypass.md"]
---

# Ask what the step before this one was for

A flow is a sequence the interface walks: cart, address, payment, confirm.
Enrol, verify, activate. Request, approve, publish. The interface walks it in
order because the interface is what the developer tested, and each route is
usually written as if the one before it had already run.

The subject here is a route something else leads to, which is what makes it a
step. The question is whether the step is a step, or just a route that happens
to come later in the screens.

## 1. Walk the flow once, in order

Complete the flow the way the interface does, through `identity_slot`, storing
every answer. This is the control and it is a `state_change`: it says what the
sequence is, what each step does to the state, and what the final step's success
looks like when it was earned.

A run that has not walked the flow does not know which steps exist and cannot
say a step was skipped. It can only say a route answered.

Complete this step with: the ordered list of routes, the route that states the
authoritative outcome, and what that outcome reads as when the flow was
completed properly.

## 2. Record the pristine state

Read the outcome route on a session that has taken no steps at all, and store
that answer. That is what "nothing has happened" looks like, and it is the other
end of every difference below.

`pristine_surface` is the baseline: a flow another Playbook advanced under this
one turns step 5 into a statement about two runs.

## 3. Take the step alone

On a session that has completed no earlier step, send the subject step exactly
as step 1 sent it -- same method, same path, same body, only the earlier calls
missing.

## 4. Try the other spellings of the same step

Where step 3 is refused, the refusal may belong to the front of the stack rather
than to the application, and the same route reached differently is the reading
v1 called verb tampering and status-code bypass. Send, one at a time and each on
its own:

* the same path under a different method the route also serves, including `HEAD`
* the same path with a trailing slash, a doubled separator, or a mixed-case
  segment
* the same request where the answer was a redirect or an error page: read what
  came with it, because a `302` to the login screen that also carried the step's
  own response body is the step having run

Each of these is the same step at the same host, in the Program's scope, and
nothing here goes looking for another host, another port or another service. A
spelling that leaves the recorded route is not this reading.

## 5. Read the outcome, and difference it

Read the authoritative outcome route and run `compare-responses` over that
answer, the completed-flow answer from step 1 and the pristine answer from step
2. Cite what the script returns.

* it matches step 1: the step ran without the steps before it
* it matches step 2: the step was refused and the state never moved, which is
  the refutation
* it matches neither: record it and stop. A half-applied flow is a state the
  application did not expect and is not evidence about ordering.

## 6. State the claim, and state what would refute it

The Hypothesis is `business_logic.workflow_order` on the step. It is supported
when the authoritative outcome shows the step's effect with the earlier steps
never taken, against a control that shows the same effect when they were. It is
refuted when the outcome after step 3 and step 4 is the pristine one.

A step that answers `200` and does nothing is not this claim. Neither is a
sequence the target never said was one: if the interface offers the step
directly, the order was not a rule and there is nothing here to break.

Where a spelling from step 4 reaches a route the flow does not contain at all,
that is `authorization.function_access` and belongs to the Playbook that claims
that class.

## 7. Advance one flow, and finish it or unwind it

This Playbook's effects are `mutates_object`: it moves one flow forward without
its earlier steps, on purpose. One flow per reading, on the tester's own account,
and it is cancelled or emptied afterwards through the target's own route with
the outcome read back to confirm.

It does not send the same step repeatedly to see how far the state gets, it does
not walk a flow belonging to another Identity, and it does not test what a route
does under load. Availability is not a Property class here and nothing in this
Playbook produces it.
