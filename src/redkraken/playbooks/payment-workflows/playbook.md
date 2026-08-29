---
description: Ask which number the server believes, by stating the invariant the target itself publishes, reading the pristine total, sending one order with exactly one number edited, and differencing the total the target computes against the same order made legitimately.
bb:category: business_logic
bb:outputs: ["business_logic.quantity_or_price"]
bb:triggers_all: ["authenticated_endpoint", "quantity_valued_parameter", "state_changing_method"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: constrained
bb:effects: mutates_object
bb:baseline: pristine_surface
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 51 as the v2 replacement for v1's payment-workflows pack, against the quantity-or-price leaf of the ticket 18 vocabulary; v1 shipped a README for this topic and no reference text, so nothing is attached. Rewritten for ticket 101 against the merged ledger, which carries four readings, one lead and two refusals for this slug. No frontmatter key moved, because all three evidence rows already name response_differential and the refuted row is reachable as written.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_differential", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "response_differential", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "response_differential", "polarity": "supports", "min_count": 1}]
---

# Ask which number the server believes

A price is computed twice: once by the client, which is a convenience, and once by
the server, which is the only one that means anything. This Playbook asks whether
they are the same computation, and it is judged on the authoritative total the
target itself states, never on the status of the edit that produced it. A 200 on a
forbidden order says the route accepted a document; the total says what it charged.

Every reading is one Test: `rk2_test_spec_problem` refuses a specification
performing fewer than three actions or leaving out the baseline, variant or control
role. The baseline is `pristine_surface`, so this Playbook is never scheduled beside
a second writer: with two writers the total is about both.

## 1. One number edited, against an invariant the target publishes

The rule has to be the target's own -- a listed unit price, an accepted quantity
range, a stated quota. Without one this is a guess and the reading does not open.

Send the arms with `mcp__rk2__http_request` and propose the reading with
`mcp__rk2__propose_test`. Five actions, in plan order and never re-ordered, and
since ticket 211 an action states `headers` and `body` as well as `method` and
`url`, so a JSON order rides the action itself.

Action 1, role baseline, reads the cart, order or account before anything is sent,
which is the pristine total the run opened with. Actions 2 and 3, role control, are
the allowed mutation -- the same operation with a value the rules admit -- and the
authoritative total read after it. Actions 4 and 5, role variant, are the same
operation with exactly one number edited to a value the invariant forbids -- a
negative quantity, a quantity above the stated maximum, a price the client should
not be sending at all, a currency the account does not hold -- and the total read
after that, sent once. Without the control arm a total that does not move under the
variant is equally well explained by a route that refused, a session that was not
valid, or a cart that was never touched. No sweep: the finding needs one order, not
forty.

`body_differs` naming the total read after the variant against the total read after
the control is what `close_test_replay` closes, and it is why all three evidence
rows of this Playbook ask for `response_differential`. The side effect on the object
is a further `state_change` edge filed by `promote_proposal` from the same Receipt.

## 2. A single-use value submitted twice

The target's published terms have to say the value may be used once; without that
rule this is the same guess section 1 refuses. Send the arms with
`mcp__rk2__http_request` and propose the reading with `mcp__rk2__propose_test`, with
the code in the `url` or in the `body`. Six actions, all three roles.

Actions 1 and 2, role baseline, submit the code once and re-read the authoritative
total. Actions 3 and 4, role variant, submit the identical request a second time and
re-read the total again; a second reduction is the defect, while a second success
answer that does not move the total is sloppy messaging and nothing more. Actions 5
and 6, role control, submit a code of the same shape that was never issued, which
must be refused, and re-read the total, which must not have moved -- if invalid
codes are accepted too, the endpoint validates nothing and replay is the wrong
headline for a larger finding.

`body_differs` naming the total read after the second submission against the total
read after the never-issued code is what `close_test_replay` closes, so the control
carries the differential too, and `promote_proposal` files the further
`state_change` edge. Two submissions, not a loop: no balance is drained and no third
is stacked.

## 3. A property the published interface never sends

An update route that accepts a structure the client previously received will often
bind more of it than it publishes. The object must be one the Program owns and the
test Identity may modify. Each arm is one update and one read-back, sent with
`mcp__rk2__http_request` and proposed as one Test with `mcp__rk2__propose_test`, the
document in the `body`.

The baseline is the object read back after an ordinary update carrying only
published fields. The variant is the read-back after the same update carrying one
extra field the server should own -- a price, a unit price, an owner, a tenant
identifier, a role. Two controls are both needed: an update carrying a field name
that certainly means nothing, showing unknown fields are ordinarily ignored, and an
update rewriting a field the user legitimately owns, such as a display name, which
the server must accept. The second separates a server that refused the privileged
field from one that rejected the document as malformed, and from outside those look
identical.

`body_differs` naming the extra-field read-back against the read-back after the
meaningless-field control is what `close_test_replay` closes, so the control carries
the differential too: the ordinary arm carries no extra field at all and cannot be
the comparator. A later request that sees the side effect is exactly what
`state_change` is for, and `promote_proposal` files it from the read-back's own
Receipt. The verdict this reading supports is `authorization.object_property_write`,
which `api-authorization` has emitted since ticket 101, so that verdict is handed
there and what is filed stays this Playbook's class.

## 4. What a very large integer becomes

This asks what the field does with a number, without asking the application to act
on the result. The `body` argument is a string of up to 65536 bytes, so a 96-digit
literal is well inside the ceiling; where the field is a query parameter the four
arms are four `url` values instead. Send them with `mcp__rk2__http_request` and
propose one Test with `mcp__rk2__propose_test`.

The baseline is the ordinary value and the answer it produces. The variant is the
96-digit integer in the same field. Two collapse targets are the controls, each its
own arm: the field set to zero, and set to the exponent form of the oversized value.
A variant matching either names the collapse; matching neither and not erroring
means the value was carried exactly. Without them a strange answer says nothing
about which representation the server chose.

`body_differs` naming the oversized arm against the ordinary one is what
`close_test_replay` closes, and a second `body_differs` names the zero control
against that same ordinary arm, which makes that control a differential and shows
the collapse targets discriminate at all. Where the collapse surfaces as a parse or
range message that wording is an `error_detail` edge, and where the collapsed
representation comes back in the answer it is a `reflected_input` edge; both are
filed by `promote_proposal`. An arm that moves the authoritative total rather than
only the answer to the edit belongs to section 1, which has the cleanup this one
does not need.

## 5. One lead, the money parameter given twice

Send the money-bearing parameter once at the value the rules admit and read the
total; then the same operation with the parameter twice, the allowed value first and
a forbidden one second, then the two swapped; then twice with both occurrences
allowed, which must produce the first total. A total reflecting the second
occurrence in one ordering and the first in the other means the validating component
and the charging one read different ones.

This is a lead and not a claim. Duplicate query keys and duplicate body keys are
both expressible, but the reading needs the same name repeated within one carrier
and read back twice under an unchanged cart, and the repetition ceiling is not what
ticket 211 moved: it stops at an Observation and cannot become a Finding on its own.
`promote_proposal` files the totals as `state_change`, an edge no writer can carry
to supported, and the verdict it points at is `injection.parser_differential`, which
`browser-script` has emitted since ticket 101, so the lead is handed there. Stop at
the ordering that moves the total; do not sweep further duplications.

## 6. Propose the claim, then remove what was ordered

This section proposes no Test of its own and grades nothing. Propose the claim with
`mcp__rk2__propose_finding`, naming mass_assignment as its `vulnerability_class` and
citing the two totals: that argument takes a vulnerability_classes id, not a dotted
Property class, and property_class_vulnerability_classes maps this Playbook's class
to that id.

The gate is `rk2_finding_refusal`, which opens nothing without the transition
`close_test_replay` wrote. What refutes the claim is stated in the same breath: the
total after the variant is exactly the total after the control, or unchanged from
the pristine read, with the control having landed. A control that did not land
refutes nothing, because the run then measured a route that was never working.

Every order, cart line and object this Playbook created is removed through the
target's own removal route before the run finishes, and the account is left at the
pristine total it was read at.

## 7. Where a reading halts, and what is refused

Three halts are a person's decision, asked for with `mcp__rk2__park_for_human`
carrying the running Task's `task_label` and the `question_code` that names why. A
field the Program did not clearly authorise rewriting parks under scope_ambiguous,
before the update is sent. An object that turns out not to be the test Identity's
parks under third_party_impact. A single-use value the Program has not issued to
this Identity parks under credential_needed rather than being guessed at.

The writer is `park_task_for_human`. Every other halt is a reading that ran out --
one order sent, two submissions made, a total moved -- and no question code says
that, so those are reported through the Task's own record.

Two readings are refused. Completing a purchase to demonstrate the invariant --
charging an instrument, capturing funds, notifying a merchant -- is refused by
decision and nothing is missing for it: a total is available before the money moves,
and no test-mode purchase is substituted without the Program saying in writing that
test mode is in scope. The concurrent pair, two requests sent so they occupy one
read-and-then-write window, is blocked: one exchange sends one request and returns,
nothing in the contract expresses two in flight, and the single-packet attack that
would make such a test reliable is refused by decision. The sequential replay in
section 2 runs instead, and the write-up says the concurrent arm was not tested.

This section performs and grades nothing. 3 of 7 steps cannot be graded.
