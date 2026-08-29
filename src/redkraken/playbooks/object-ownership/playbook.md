---
description: Ask whether the object named in a request is checked against the caller, by holding one Identity and moving the object identifier between two arms of one Test, and by asking the same question of an implied subject, a re-spelled identifier, a second lookup key, an obfuscated reference and one written property.
bb:category: authorization
bb:outputs: ["authorization.object_ownership"]
bb:triggers_all: ["multiple_test_identities", "object_identifier"]
bb:triggers_any: ["body_parameter", "path_parameter", "query_parameter"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-02-15
bb:provenance: Written for ticket 45 against the object-ownership leaf of the ticket 18 vocabulary; no upstream card, no third-party list. Rewritten for ticket 101 against the merged technique ledger, which holds six executable readings for this slug. Five of them read. The sixth writes one property of an object the caller does not own, and the class that reading produces is one the vocabulary shipped with no emitter. D3 places that emitter here, and this file does not take it -- the shipped test pins this Playbook's outputs, effects and triggers to what it already declares, so moving them is a code change under a different ticket rather than a rewrite. bb:outputs, bb:effects and bb:risk therefore stand, and the write leg is written the way a read_only Playbook may carry one -- it halts for a person before it sends, and what resumes runs under whatever Task that decision opens. Disagreement recorded per D3's own preamble.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_differential", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "response_differential", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "response_differential", "polarity": "supports", "min_count": 1}]
bb:references: ["why-two-identities.md"]
---

# Ask who the object belongs to

One endpoint names an object. Two Identities are leased. The question is
whether the server checks the second against the first, and the only thing that
answers it is the same request sent twice with one variable changed.

Which variable moves is the whole design. A replay run holds one leased
Identity for its length, so a two-Identity comparison cannot be one Test. What
can be one Test is a single run held at the second Identity whose arms name two
different objects: a request-line differential settles a claim.

So every reading below has the same three arms, in plan order and never
re-ordered. Action 1, role baseline, is the caller's own object. Action 2, role
control, is that url sent again unchanged. Action 3, role variant, is the one
thing under test. The differing assertion runs from the variant against the
control, so both arms carry the kind the evidence bar asks for, and
`body_equals` between baseline and control reads the stored body digest alone:
the route is byte-stable.

## 1. Name the object, the two Identities and the parameter

This step is a lead and cannot be graded. It reads state through
`mcp__rk2__get_attack_surface` and writes no Observation. The subject is an
endpoint carrying an object identifier, in the path, the query or the body.
Read that parameter from the state view rather than guessing it from the url.
Whether the two identifiers the state view supplies are predictable from one
another -- consecutive, one field apart, or the same value under a reversible
spelling -- is read off the pair this reading already holds and filed as an
Observation, because a route that checks nothing is only reachable where a
caller can name a neighbour. A third identifier arrived at by counting is a
sweep and is not sent.
Name two Identity labels the mission packet supplies: label A owns the object,
label B should not reach it. A run acts as whichever Identity its Task was
opened under and there is no argument for it, so a reading that needs two
Identities is two Tasks. Where only one is leased, the comparison has no second
side.

## 2. Ask who the object belongs to

Send the arms with `mcp__rk2__http_request` and propose the reading with
`mcp__rk2__propose_test`, from Task B and held at label B for the length of the
run.

Action 1 is a read for an object label B owns. Action 2 repeats it unchanged.
Action 3 is the byte-identical read for the object label A owns. Assert
`body_equals` on action 2 against action 1, and `status_differs` on action 3
against action 2. One variable moves and it is the object identifier. The
control is what makes the variant mean anything: without it a refusal under
label B is equally well explained by a session that was never valid, a route
that rejects everything, or a rate limit. `close_test_replay` is the writer. It
takes the Observation kind from the specification rather than the outcome, so
both arms carry `response_differential` whichever way the run comes out, and it
alone carries a Hypothesis to supported. The two-Task reading is corroboration
rather than settlement; `promote_proposal` writes it, and its Observations are
made in Task B, because an element citing another run's Receipt is dropped.

## 3. Ask what the route reads as the subject, and as the key

Send the arms with `mcp__rk2__http_request` and propose each of the three
readings below with `mcp__rk2__propose_test`, and close_test_replay writes each
settlement from the specification rather than the outcome.

Some routes carry no identifier: the subject is whatever the session says,
until a parameter overrides it. Action 1 reads the route with the subject
implied, action 2 repeats it, and action 3 is the same url with an identifier
parameter the route never advertised, naming a second account the operator
owns. A different collection under the variant means an implicit subject can be
overridden by an explicit one. Harvest the parameter name from what
neighbouring delete and edit calls send; a list of guessed names is a sweep.
Where the name can only travel in a body the arm is still sendable, since an
action states its own `body` since ticket 211.

One Identity is enough for the two readings that follow, which separates them
from section 2. The first re-spells the caller's own identifier in a shape the
client never sends -- an integer where an opaque value is expected, a wildcard
segment, or the nil UUID. A record that is not the caller's, or a collection
where one object was expected, means the lookup accepts a shape the check never
anticipated. The control is a well-formed identifier of the original shape that
certainly names nothing, without which a returned record cannot be told from a
route returning the caller's own whatever it is sent.

The second asks whether a second lookup key is guarded like the first, on a
type whose observed traffic already showed a username, a slug or an address
beside the id. Action 1 queries the type by id for an object this Identity
owns, action 2 repeats it, and action 3 queries the same foreign object by the
alternate argument. Populated where the id path denied is the finding, and a
fourth request querying that foreign object by id has to be denied, without
which the variant's success is ordinary access to something public. Stop at the
first shape and the first populated response: one foreign object, read only, is
the whole claim, and sweeping either key is a different class. A wildcard
spelled as a dot segment cannot be a Test arm, because a specification url
refuses a dot segment and `%2e`: that one is sent outside the Test with
`mcp__rk2__http_request` and filed with the proposal through
`mcp__rk2__submit_mission_result`, which promote_proposal writes and no Test
grades.

## 4. Recover an obfuscated reference before asking again

Where the identifier is opaque, the reading recovers the transformation rather
than guessing at the value. Run `mcp__rk2__run_tool` over the served bundle,
`js_parse` for the transformation and `jq` for the structure of the decoded
value.

The kind is `content_match`, whose provenance is a tool run -- and a browse run
is a tool run, so a reading that read the value off a page needs no second pass
over the stored bytes. Then recompute the reference for a neighbouring
identifier and run section 2 against it, with the control a recomputed
reference for an identifier that certainly does not exist, which shows the
recomputation is right rather than the route permissive. Where the
transformation cannot be recovered, stop: guessing is a sweep and the control
no longer exists. That halt is a reading that ran out rather than a question
for a person, so it is reported through the Task's own record.

## 5. Write one property of an object the caller does not own

This is the one reading here that changes something, and this Playbook declares
that it only reads, so the reading may not perform it. The disclosing half is
section 2's and is a finding on its own. This leg halts before it sends, which
makes it a lead of this Playbook: parking closes the run, so the write and the
Test that follows belong to the Task the operator opens next.

Halt through `mcp__rk2__park_for_human`, carrying this run's own Task in
`task_label`, destructive_action in `question_code`, and the halt trigger
verbatim in `question`: the request may change state at the target and a write
to somebody else's object is exactly that. A person decides, names the object,
the single property and the cleanup that puts it back.

What resumes there is the same three arms under one Identity: action 1 writes
one property of an object this Identity owns, which says the write path works
for this caller at all, action 2 repeats it, and action 3 is the same write
shape naming label A's object, with the identifier taken from a listing rather
than guessed. A fourth request writes to an identifier that names nothing and
has to fail, or a success on A's object cannot be told from a route that
accepts every write.

Read A's object afterwards from Task B: that read is what says the write landed
rather than being accepted and discarded, and `promote_proposal` files it as a
`state_change` edge citing that Receipt. The identifier differential travels in
the path, so `close_test_replay` settles it; where the payload is the variable
instead, the differential lives in a body the Test carries since ticket 211 and
the claim belongs to whichever class the payload names.

## 6. State the claim, and state what would refute it

The Hypothesis is `authorization.object_ownership` on the endpoint, for the
write leg as much as for the reads, because what section 5 shows is still that
the object was not checked against the caller. It is supported when the variant
arm returns the object's content, or writes it, under a session that does not
own it, and the control arm shows that session working correctly on its own
object. It is refuted when the variant is invariant against a control that
succeeded, meaning the session is good and the server still refused. Both legs
are `response_differential`, because one role writes one kind either way.
Anything else is inconclusive: a generic error page, a redirect to a login the
control did not hit, a rate limit. Where the second door is a different route
to the same records rather than the same route under a different caller, the
class is `authorization.parallel_route`; an alternate key that also tells an
existing identifier from a missing one is
`information_disclosure.identifier_oracle`.

The gate is `rk2_finding_refusal` and what it wants is the settling transition
`close_test_replay` wrote for the Test being cited. Cite the difference the
comparison returned rather than a description of it.

This section proposes no Test of its own and grades nothing. Open the claim
with `mcp__rk2__propose_finding`.

## 7. The ceiling

This section is a lead and cannot be graded. It states what this Playbook does
not do. It does not log out, rotate a token or change a password. Its baseline
is a session that stays stable, so the runtime drops any Playbook that mutates
one rather than running both. It performs no write of its own: section 5's is
one property of one object, authorised by a person under a Task this Playbook
did not open, with the cleanup named before it was sent. It does not substitute
an identifier while the Identity also moves, sweep a range of identifiers, or
name a subject the operator does not own.

4 of 7 steps cannot be graded.
