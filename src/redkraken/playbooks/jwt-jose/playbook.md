---
description: Ask whether anything reads the part of a token that says what it is for, by presenting one genuine token at a second audience and a second scope, by editing one claim under a preserved signature, and by reading which failure the server reaches first when the key identifier or the payload is altered under a signature that is deliberately wrong.
bb:category: authorization
bb:outputs: ["authorization.token_scope"]
bb:triggers_all: ["authenticated_endpoint", "tech_jwt"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 50 as the v2 replacement for v1's jwt-jose pack, against the token-scope leaf of the ticket 18 vocabulary; the v1 jwt text is attached as a maintainer reference and supplies the header and claim edits this Playbook sends. Rewritten for ticket 101 against the merged ledger, which carries eight readings, one lead, one block and one refusal for this slug. One key moved. The refuted variant row leaves response_invariant for credential_effect, the kind the supported row of that same role names, because close_test_replay derives the kind from the specification and one role writes one kind whichever way the reading goes. bb:effects stays read_only and bb:risk stays constrained; the one section that mints a credential does so for this run's own account under a registration the Program supplied, and parks for a person where it has neither. Ticket 211 is what turned six of these readings from Observations into Tests, because an action now states the header the token rides in.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "credential_effect", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "credential_effect", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "credential_effect", "polarity": "supports", "min_count": 1}]
bb:references: ["jwt.md"]
---

# A token says what it is for; ask whether anything reads that part

A signed token states who a session belongs to and what it is for -- the
audience, the scope, the issuer, the expiry, the key that signed it. Libraries
check the signature by default and leave the second statement to the
application, which is why it is so often unread. Nothing here forges: the
question is whether a token that is genuine, or edited without touching its
signature, is honoured somewhere it never claimed to be valid.

Every reading is one Test of at least three actions holding a baseline, a
variant and a control, because rk2_test_spec_problem refuses a specification
performing fewer than three or leaving a role out. The arms are sent with
`mcp__rk2__http_request`, filed as one specification with
`mcp__rk2__propose_test` and closed by close_test_replay, which derives the
Observation kind and the transition from the Test's own assertions. Since ticket
211 an action states `headers` and `body` as well as `method` and `url`, so a
token in an Authorization value is an arm of a Test. The credential_effect
Observations the bar names are agent-filed and go in WITH the proposal through
`mcp__rk2__submit_mission_result`, because an edge cannot be added past proposed.

There are two token sources and only two. A leased Identity may hold the token
as its static Authorization header for the origin, and section 1 is written for
that spelling, where only the url varies. Every other section EDITS the token,
and identity.Session.inject gives a leased Identity ownership of Cookie and of
every header it declares for the origin, so an edited Authorization value stated
in a plan is dropped before the wire. Those sections are planned on a Task
holding no leased Identity for this origin and each says so. The bytes come from
an issuance, refresh or exchange route this run drove itself; a run whose only
copy sits in a slot has no variants to send and records the reading
inconclusive. Write down the field names and the decision each should drive,
which is aud, scope or scp, iss, exp, kid and alg, and nothing else.

## 1. The same token, at a second audience and a second scope

One Test, one url per arm through `mcp__rk2__http_request`, on a Task leasing
the Identity that holds this token, so nothing in the plan touches the
credential. The baseline is the endpoint the token was issued for, sent twice
unchanged, because a response carrying a request id or a counter has no
invariant for a variant to be measured against. The variants are the identical
token at a second endpoint whose surface names a different scope, and at a
second application sharing the issuer where aud names only the first. The
control is a third url this Identity is known to be refused at, which must
answer refused: it rules out the boring explanation, that this Identity is
answered everywhere. status_differs naming a variant against the control is what
close_test_replay closes, and promote_proposal files a credential_effect off
each Receipt as the edges the bar names.

## 2. Whether the signature is read at all

Plan this on a Task holding no leased Identity for this origin, because the
differential IS the Authorization value and a leased Identity replaces it before
the wire. One Test, each arm stating its own `headers` through
`mcp__rk2__http_request`. The baseline replays the issued token untouched, sent
twice. One variant edits a single claim and leaves the original signature in
place, where an authenticated answer means the payload is trusted unverified; a
second carries the same claims with alg set to none and an emptied signature.
The control is the original token with one signature byte altered, which must be
refused, and where that is accepted too nothing is verified anywhere and the
class is `authentication.credential_verification`. status_differs naming a
variant against the control is what close_test_replay closes, and `jq` under
`mcp__rk2__run_tool` does the base64url round trip without computing anything.

## 3. The algorithm name, compared rather than normalised

This starts where the last ended, with plainly spelled alg none REJECTED, and
without that floor nothing has anything to slip past. Same Task, no leased
Identity, same three roles through `mcp__rk2__http_request`. The baseline is the
plain none rejection sent twice and differenced, so the sameness of a message is
measured rather than eyeballed. The variants are one spelling each: alg in mixed
case, the header segment re-encoded with extra base64 padding, and the standard
alphabet for the url-safe one. The control is alg set to an INVENTED algorithm
name, which must be rejected with the same status and words as plain none;
answered differently it says the deny-list is enumerated rather than an
allow-list, which is itself the result. status_differs naming an accepted
spelling against the control is what close_test_replay closes, and where the
messages move but nothing is accepted, promote_proposal files error_detail.

## 4. Which failure the server reaches first

Two readings, one Test each, every request carrying a DELIBERATELY WRONG
signature, which removes the need for any key, and both on a Task holding no
leased Identity for the reason section 2 gives. First: the baseline is a valid
key identifier under that signature, sent twice, which records the verification
error and shows it stable; the variants set kid to a traversal path and to a
value carrying a quote or a lookup separator; the control is a random string of
the same length that is not a path, which establishes the unknown-key error.
Second: the baseline is the intact token twice, the variants flip one byte in
the payload half and one in the signature half, and the control truncates at the
separator. body_differs naming a variant against its control is what
close_test_replay closes in both, error_detail is the supporting edge, and a kid
value returning file CONTENT ends the reading at once with the operator told.

## 5. The client decode, settled by a server-side control

Retrieve the served bundles and run `js_parse` under `mcp__rk2__run_tool` over
them, because the kind this half files is content_match and its only provenance
is a tool run. Note the call sites that decode a token and act on a claim, a
role, an administrator flag or a tenant, with no adjacent verification and no
server round trip; the bundles are the served application, and a source
repository, a build runner or a vendor's own interface is out of scope as a
subject. A code reading settles nothing alone, so the section closes on the
server: one Test, no leased Identity, the baseline the intact token, the variant
that token with the client-read claim altered under its preserved signature, the
control a corrupted signature that must be refused. status_differs naming the
variant against that control is what close_test_replay closes, and the
content_match goes in with the proposal beside a credential_effect.

## 6. A token past its own lifetime

This is a lead and it is opportunistic. The reading is taken when a run has
already held a token past its own exp; it is never manufactured, and a run about
to sleep or loop in order to age one stops and records the reading not
applicable rather than refuted. Replay the aged token, replay a freshly issued
one at the same moment, and replay the aged token with its signature corrupted;
an authenticated answer to the first means the lifetime claim is not read. It
closes no Test, because the variable is elapsed time and rk2_test_assertion_kinds
is exactly status_equals, status_differs, body_equals and body_differs.
promote_proposal files credential_effect off the aged and the corrupted
Receipts, the edges are real, and the claim reaches no Finding here.

## 7. A scope the grant never defined

Where the surface names a token endpoint and a discovery document, ask whether a
widened scope string is also a widened enforcement. One Test through
`mcp__rk2__http_request`, the exchange parameters riding each action's own `body`
since ticket 211. The baseline exchanges a code with exactly the scope the
authorization request carried, then reads a resource route twice, invariant. The
variant repeats the exchange with an added wider scope and reads the same route.
The control is a third exchange naming an INVENTED scope value, because many
servers echo a requested scope and enforce the granted one. body_differs naming
the widened read against the invented-scope read is what close_test_replay
closes, and promote_proposal files credential_effect off both resource Receipts.
The code is one this run obtained for its own account under a registration the
Program supplied; with neither, ask a person through `mcp__rk2__park_for_human`,
naming the Task this run is executing in `task_label` under a `question_code` of
credential_needed, rather than borrowing one.

## 8. Propose the claim, name the halts, and name what is refused

Propose it with `mcp__rk2__propose_finding`, naming privilege_escalation as its
`vulnerability_class`: that argument takes a vulnerability_classes id and never a
dotted Property class, which the served schema refuses before the call is made,
and property_class_vulnerability_classes maps this Playbook's class to that id.
The gate is rk2_finding_refusal, which opens nothing without the transition
close_test_replay wrote. It is supported when a token issued for one audience,
scope, lifetime, key or algorithm was honoured under another against a control
showing a broken signature refused, and refuted when every variant is answered
the way that signature is. Which DATA came back is a separate question: records
belonging to another tenant are `authorization.tenant_isolation`, and where the
token was found rather than what it does is
`information_disclosure.artifact_exposure`.

Two halts are a person's decision. A second application sharing the issuer that
the scope document does not clearly admit parks under scope_ambiguous, and a
client registration or account the Program has not supplied parks under
credential_needed. Every other halt is a reading that ran out -- a spelling set
exhausted, three error readings taken, an aged token absent, a variant accepted
-- and no question code says that, so those go in the Task's own record, with
the operator told at once where a variant was accepted.

One block and one refusal, kept apart on purpose. Every reading whose proof
needs a computed signature is BLOCKED, and the missing capability is exact: the
offline tool enum is exactly jq, js_map, js_parse and js_routes, none handles a
key, and no Skill ships a signing script, so a symmetric algorithm over a
published public key, a re-signing under the key an identifier selects and an
offline secret recovery cannot be composed. Fetching the published key set is an
ordinary read and is not the gap. Pointing the key-set or certificate header at
a document this run serves is separately REFUSED, because hosting a second
origin is a standing decision; folding it into the block would let a signing
script quietly re-open it, and its weaker form, that header pointed at a URL
with the fetch read on the declared channel, is a blind-validation claim and not
a token-scope one. This section grades nothing. 2 of 8 steps cannot be graded.
