---
description: Ask whether a state-changing request is accepted without proof that the caller's own page asked for it, by replaying one guarded submission with the anti-forgery token absent, emptied, mutated and borrowed from a second session, under a changed verb, under Referer and Origin shapes an allow list may mismatch, and under a content type that provokes no preflight.
bb:category: session_handling
bb:outputs: ["session_handling.csrf"]
bb:triggers_all: ["authenticated_endpoint", "form_request"]
bb:triggers_any: ["state_changing_method", "websocket_surface"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: constrained
bb:effects: mutates_object
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-02-15
bb:provenance: Written for ticket 49 as the v2 replacement for v1's realtime pack, against the csrf leaf of ticket 18's vocabulary. Rewritten for ticket 101 under decision D1, which found the shipped websocket reading cannot execute on any lane and gave this Playbook a truthful form-CSRF scope. Four keys moved. bb:triggers_all becomes authenticated_endpoint and form_request, admitting state_changing_method and websocket_surface. D1 asked for authenticated_endpoint alone; measured, that one fact reaches seventeen of the other forty-nine subjects and takes rank 1 from five under a constrained ceiling, while form_request is what all five form readings are about and leaves two overlaps. bb:effects rises to mutates_object because every reading submits a state change on an object the test Identity owns and restores; bb:risk stays constrained, the floor mutates_object asks for. The supported variant row leaves response_invariant for response_differential; that framing belonged to the blocked handshake reading.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_differential", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "credential_effect", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "response_differential", "polarity": "supports", "min_count": 1}]
---

# Ask what the server checks besides the session

A browser will attach this origin's cookies to a request another site made. The only things that
stop the request from counting are a token the application issued for this session, a header the
application reads and trusts, and a content type that forces a preflight the other site cannot
answer. Each reading below asks one of those three whether it is really being checked.

Five of the seven sections are procedures, each ending at one Test of three to thirty-two actions
holding at least one baseline, one variant and one control, because rk2_test_spec_problem refuses a
specification performing fewer than three or leaving a role out. The arms go out with
`mcp__rk2__http_request`, are filed as one specification with `mcp__rk2__propose_test`, and
close_test_replay closes them. Since ticket 211 an action states its own `headers` and `body` beside
its `method` and `url`, which is what makes a token field, a borrowed token, a Referer value and a
content type into arms rather than into notes; setup and cleanup steps still carry a method and a
url alone.

Two conventions hold across all five. The closing assertion names the variant against the control,
which is the arm carrying a credential the server must refuse, and that control's own answer is also
filed as an agent-filed credential_effect edge through `mcp__rk2__submit_mission_result`, which
promote_proposal writes, before the specification is proposed. And the baseline role carries two
identical sends of the honest request asserted equal to each other, because a success page carrying
a fresh token, a request identifier or a timestamp would otherwise fire a differing assertion on its
own.

## 1. Name the object, and agree what may change on it

This Playbook is mutates_object, not read_only, and the reason is the whole of its method: a guarded
action is only shown to be unguarded by submitting it. Every arm below is a state change on an
object the test Identity owns, names by identifier, and can restore. Choose that object before
anything is sent, record its identifier and its state, and record the request that restores it.

Stop after the first arm that is accepted and the state changes. Restore the object, send no further
arm of that section, and record whether the restore succeeded. An arm accepted on an object
belonging to somebody else is not this reading and it has already gone too far. This section closes
no Test and grades nothing.

## 2. The token, absent, emptied and mutated

Three replays of one submission, differing from the honest request in exactly one body field.
Baseline: the state change with the token the application issued, sent twice, asserted equal, which
also shows what a change that took looks like. Variant: three arms -- the token key removed
entirely, the key present with an empty value, the key present with one character changed. Control:
the same-length mutated token, which must be rejected. Same length matters, because it is what rules
out a comparison on length alone, and where a mutated token is accepted the endpoint never reads the
token and the other two arms say nothing about validation being skipped.

Each closing assertion says its variant differs from that control. The three arms separate a check
skipped when the field is missing from one that only tests presence from one that never compares at
all, and which of the three it is belongs in the finding. The control's own answer is a decision
returned for a presented credential, which is what credential_effect names, and it goes in with the
proposal.

## 3. The token minted for another session

A token the server merely recognises is not a token bound to the session that was issued it. This
reading needs two Identities and therefore two Tasks, since the Identity is a property of the Tool
run and is chosen once per Task; the Playbook states the requirement and selects nothing. Mint a
token in the first Identity's Task and record it. The Test then runs entirely in the second
Identity's Task, so every closing arm sits under one Identity setting and the difference between
them is the token value in the body.

Baseline: the second Identity's own submission with its own token, sent twice, asserted equal.
Variant: the identical request carrying the first Identity's token. Control: a token-shaped string
of the same length that was never issued, which must be rejected, or nothing is checked and the
variant is only section 2's weaker finding restated. The closing assertion says the variant differs
from that control. The token value itself is not written into the finding; the Receipt labels and
the object identifier are.

## 4. The verb the guard was attached to

A guard bolted to a method rather than to an action is answered by reissuing the action under
another verb. Baseline: the guarded submission with a valid token and its parameters in the query
string, sent twice, asserted equal. Variant: the identical url with no token, sent as a read method,
which is a pure request-line difference and the cheapest arm in this Playbook. Control: the real
verb with no token, which must be rejected, since a route unguarded either way is a route this
section says nothing about.

The closing assertion says the read-method variant differs from that control. Two further arms ask
the same question through an override -- the real verb named in a body field, and the real verb
named in an override header -- and both are arms of the same Test since an action states its own
body and headers. The method enum is the seven ordinary verbs and nothing else, so a step naming an
invented verb or a diagnostic one is a step that cannot run and is not written.

## 5. Referer and Origin, and where the match is anchored

Neither header is hop-by-hop and neither carries the internal prefix, so both forward as written,
and every value here is printable ASCII with no carriage return or newline, which the header value
pattern enforces by construction. Baseline: the submission with a correct same-site Referer, sent
twice, asserted equal. Variant: three arms, one changed header each -- the header omitted entirely,
the trusted host as a subdomain of a foreign name, and the trusted host as a query or path fragment
of a foreign name. Control: a plainly foreign Referer with no trick in it, which must be rejected,
or the header is not read and all three arms prove nothing.

Each closing assertion says its variant differs from that control. The three arms separate a defence
that fails open on a missing header from one anchored at the wrong end from one that is not read at
all, and the fail-open case is both the commonest and the first to run. Quote the exact header value
of every arm in the finding.

## 6. The content type that provokes no preflight

A handler that parses a body sent under a safelisted content type can be reached by a form another
origin submits, with no preflight to refuse it. The body is a free string, so the model spells its
own encoding and a form-shaped or hybrid declaration is expressible. Baseline: the route's own
request under its declared type, sent twice, asserted equal. Variant: the byte-identical body under
plain text with a character set, then under form encoding, then under a hybrid declaration, with no
non-safelisted header on any arm. Control: the same safelisted-type request with one byte of the
body corrupted, which must be refused, proving a parser ran and the accepted arm was a real
invocation rather than a no-op.

Each closing assertion says its variant differs from that control. Stop after one accepted arm and
do not run the remaining content types; one accepted invocation is the whole answer and every
further send is another state change on the object.

## 7. State the claim, and name the three readings this Playbook cannot perform

The Hypothesis is session_handling.csrf on the route, proposed with `mcp__rk2__propose_finding`
naming csrf as its `vulnerability_class`, which takes a vulnerability_classes id and not a dotted
Property class. It is supported when an arm carrying no valid proof of same-origin intent was
accepted and changed state, while the control carrying an invented credential was refused. It is
refuted when every arm is refused exactly as the control is, which is what a working check looks
like. Inconclusive covers a route that refuses the control too, a body that moves between two
identical sends, and an arm whose acceptance cannot be told from the honest request's.

A cookie policy is a different class and is not restated as this one. Where a strictly same-site
session cookie is why a cross-site request would never have carried the session at all, that is
session_handling.cookie_scope being right rather than this claim being wrong, and it is recorded as
an Observation under cookies. Where the question is who may READ an authenticated answer rather than
who may cause one, the class is session_handling.cross_origin_read and the Playbook is
request-integrity.

The websocket reading this Playbook was originally written around is blocked, and by our own egress
rather than by any target. connection and upgrade are both members of proxy.HOP_BY_HOP, forwardable
drops every member, and the wire headers are rebuilt from the authority plus what survives, so
neither header is ever on the wire. The browser lane is not a way around it, because the container
shim carries the same drop set. And the door terminates a tunnel request rather than relaying it,
reading the request inside as a request, so there is no tunnel to upgrade within either. A step
whose first move is a protocol-switch response cannot complete, and no reading here proposes one.

Two further readings are refused rather than absent. Serving a page from an origin this reading
controls, opening the socket or the form in a victim's session and relaying what comes back is
refused because the browser lane hosts no second origin and will not; the honest write-up names the
unvalidated header and the cookie policy as separate checkable conditions and says the cross-origin
half was described and not executed. And the double-submit reading, where the caller supplies both
the cookie crumb and the body copy so a server comparing only the two halves accepts a pair the
caller invented, cannot be composed at all. identity.Session.inject gives a leased Identity
ownership of Cookie and of every header it declares for the origin, so a plan-stated Cookie is
dropped before the wire; and on a Task with no leased Identity the caller does spell the whole
header but has no session value to put in it, because set-cookie is stripped from the agent view on
every path. Both halves have to fall for that reading to run, and both stand.

Halts here are readings that ran out -- one accepted arm, one object restored, three families sent
-- and none of the five question codes a model may name says that, so they are reported through the
Task's own record. This section performs and grades nothing. 2 of 7 steps cannot be graded.
