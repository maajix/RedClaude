---
description: Ask whether an operation is refused when the object's own state forbids it, by sending the same operation against an object that may still take it, an object somebody else owns and an identifier that names nothing, and reading the owner's own view of what changed.
bb:category: authorization
bb:outputs: ["authorization.state_transition"]
bb:triggers_all: ["multiple_test_identities", "path_parameter", "state_changing_method"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: constrained
bb:effects: mutates_object
bb:baseline: pristine_surface
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 51 as the v2 replacement for v1's api-authorization pack, against the state-transition leaf of the ticket 18 vocabulary; two v1 texts are attached as maintainer references and both describe the identifier work step 1 rests on.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_invariant", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "credential_effect", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "state_change", "polarity": "supports", "min_count": 1}]
bb:references: ["idor.md", "uuids.md"]
---

# Ask what the object's own state forbids

An object carries a state, and the state is half of the authorisation decision.
A shipped order cannot be cancelled, a closed ticket cannot be reopened by its
reporter, a revoked invitation cannot be accepted. Applications write the owner
check once and the state check per route, which is why the owner check is the
one that is usually there.

The question is one operation sent four times: against an object that may still
take it, against an object whose state should forbid it, against an object
somebody else owns, and against an identifier that names nothing.

## 1. Name the object, the transition and the two Identities

The subject is a state-changing route naming an object in its path. Read the
parameter that names the object from the state view rather than from the URL,
and read the object's states from the route that returns it -- the transition
this Playbook asks about is the target's own, not a name invented here.

Name two Identity labels the mission packet supplies. Label A owns the objects.
Label B owns none of them and is the second half of step 3.

Complete this step with: the route, the parameter, the two labels, and two
objects of label A's in two different states. Without an object already in the
forbidding state there is nothing to ask, and this Playbook does not apply.

## 2. Record the pristine state

Read every object this reading will touch, through label A, before anything is
sent. Store the answers. This is the baseline the claim is measured against and
it is also what says which objects were already in which state, which nothing
after step 4 can establish.

`pristine_surface` is this Playbook's baseline for that reason: an object
another Playbook moved between this step and step 5 makes every reading below a
statement about two changes.

## 3. Send the three controls

All three go through `mcp__rk2__http_request` with `identity_slot` set. Same
route, same method, same body shape; one thing moves per call.

* **the owner control.** The operation on label A's object in the state that
  still admits it. It succeeds, and that is what says the route works, the
  session is good and the operation is available to this caller at all.
* **the foreign-owner control.** The same operation, as label B, on label A's
  object. It is refused, and the refusal is a `credential_effect`. If it
  succeeds, the finding is `authorization.object_ownership` and it belongs to
  the Playbook that claims that class -- record it and stop, because an object
  anyone may operate on says nothing about which states forbid the operation.
* **the nonexistent control.** The same operation, as label A, on an identifier
  that names no object. Store what absence looks like. This is the control most
  runs skip and it is the one that decides the reading: an application that
  answers `404` for a missing object and `404` for a forbidden transition has
  told you nothing, and a run without this control cannot know which of the two
  it received.

## 4. Send the variant

The operation, as label A, on label A's object whose state should forbid it.
One variable against the owner control: the object's state.

## 5. Read the after-state, as the owner

Read the object again through label A and run `compare-responses` over that
answer and the same object's answer from step 2. The status line of step 4 is
not the finding. An application that answers `200` and changes nothing has
refused in a confusing way, and an application that answers `500` and cancels
the order has done the thing this Playbook is asking about.

The claim rests on the difference between two authoritative reads. Cite the
script's output for that pair, and cite the nonexistent control's answer beside
it, because the second is what says the first was a decision rather than an
absence.

Where the after-state read is refused, or answers a body the difference cannot
attribute, the reading is inconclusive and is reported as inconclusive.

## 6. State the claim, and state what would refute it

The Hypothesis is `authorization.state_transition` on the route. It is supported
when the after-state shows the transition happened from a state the target's own
rules forbid, against a foreign-owner control that was refused. It is refuted
when the variant is answered the way the foreign-owner control was and the
after-state is unchanged from step 2.

Two readings are somebody else's claim and are recorded as such rather than
stretched into this one: an operation any caller may perform is
`authorization.object_ownership`, and a route no caller should reach at all is
`authorization.function_access`.

## 7. Change one object, and say which one

This Playbook's effects are `mutates_object`: step 4 changes one object of label
A's on purpose, and that is the evidence. It does not touch label B's objects,
it does not delete, and it does not repeat step 4 to see whether the second one
also lands -- one transition per reading, named in the report by the identifier
step 1 read.

Where the Program's rules of engagement do not admit a write to the subject, the
reading stops at step 3. Three controls and no variant is not a finding, and it
is an honest thing to report as a reason a subject was not read.
