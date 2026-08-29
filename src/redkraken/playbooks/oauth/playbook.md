---
description: Ask whether an authorisation server binds the credential it issues to the request that asked for it, by mutating the registered callback, the response encoding, the redeemed code and the state value one arm at a time and differencing each against a control the server must refuse.
bb:category: session_handling
bb:outputs: ["session_handling.fixation"]
bb:triggers_all: ["query_parameter", "tech_oauth"]
bb:skills: ["browser-evidence", "compare-responses", "enumerate-surface", "use-identity"]
bb:risk: approval_required
bb:effects: mutates_object
bb:baseline: none
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 50 as the v2 replacement for v1's oauth pack, against the session-fixation leaf of the ticket 18 vocabulary; two v1 texts are attached as maintainer references and both describe the callback delivery this Playbook performs. Rewritten for ticket 101 against the merged ledger, which carries eight readings, one lead and two refusals for this slug. Three keys moved. bb:effects rises from mutates_session to mutates_object because section 2 registers a client on the subject and a Playbook that writes state must say so; bb:risk stays approval_required, which is above the floor that effects asks for. bb:skills gains compare-responses and enumerate-surface, both already held by the role that executes this text. Both variant rows move from state_change to response_differential, the kind every grading section's differing assertion writes, because the only state_change the ledger records for this slug sits in the observation_only lead section 6 carries, which reaches no Finding.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_differential", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "credential_effect", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "response_differential", "polarity": "supports", "min_count": 1}]
bb:references: ["oauth2-attack-via-google-oauth2-playground.md", "oauth2.md"]
---

# The credential, and the request it was supposed to belong to

An authorisation flow is a round trip. A browser sends a user to an issuer, the
issuer sends a credential back to a callback, and the callback turns it into a
session. Every reading below asks one question of one joint in that trip: is what
the server hands back tied to what asked for it. Every reading is one Test of at
least three actions holding a baseline, a variant and a control, because
rk2_test_spec_problem refuses a specification performing fewer than three or
leaving a role out. The arms are sent with `mcp__rk2__http_request` and filed as
one specification with `mcp__rk2__propose_test`, the only verb that makes a Test
exist, and close_test_replay closes it. The control is the arm that says
validation happens at all, and its Receipt carries the credential_effect this
Playbook's bar names, agent-filed in the role control WITH the proposal through
`mcp__rk2__submit_mission_result`, which promote_proposal writes: an edge cannot
be added once a claim is past proposed.

## 1. The registered callback, and the two components that read it

Send one authorisation request per arm through `mcp__rk2__http_request`, one
`url` each, changing one thing at a time. The baseline is the exactly
registered value, which is issued. Each variant is one mutation of it: an
appended path, query or fragment; a prefix or subdomain form; a case shift; a
foreign scheme; the plaintext downgrade. The control is an unrelated absolute
URI, which must be rejected, and for the suffix arm a foreign suffix on the
allowed host, which proves the suffix is compared and not the whole string. An
arm answered as the baseline names the accepted shape, and status_differs
naming it against the control is what close_test_replay closes.
rk2_test_request_problem refuses a `.` or `..` path segment and any `%2e`
anywhere in a specification url, so the encoded-traversal spelling is no arm:
it is sent once and filed as an agent Observation, and no Test carries it.

The second reading is a disagreement between the component that validates the
callback and the component that uses it. Each variant is one spelling: a
foreign host after userinfo, after a fragment, after a doubled separator,
behind a backslash, and `redirect_uri` stated twice registered-then-foreign,
then swapped. The controls are the foreign host alone, rejected, and the
parameter twice with both occurrences registered, accepted. An arm accepted in
one order and rejected in the other means the two components read different
occurrences. That verdict is `injection.parser_differential`, which
`browser-script` emits since ticket 101; hand it there.

## 2. The documents the server fetches, and the client it mints for anyone

Run this reading on a Task holding no leased Identity, because the question is
whether a credential is needed at all. This Task performs the half its own lease
admits and the other leaves as a `suggested_tasks` entry on
`mcp__rk2__submit_mission_result`; nothing re-leases a Task in flight. Since
ticket 211 an action states `headers` and `body` as well as `method` and `url`,
so all three arms are actions of one Test through `mcp__rk2__http_request` and
the registration document rides the request. The baseline is a minimal
registration document sent with no authorisation header, where a 401 is the
healthy answer. The variant is the same document answered with a 201 and a client
identifier, then that document carrying a URL-valued field the server itself
dereferences, pointed at the declared correlator. The control is a deliberately
malformed document sent with no authorisation header, where a 400 rather than a
401 shows the endpoint parses before it authenticates. status_differs naming the
well-formed arm against the malformed control is what close_test_replay closes,
each refusal's wording is an error_detail edge filed by promote_proposal, and an
arrival off the URL-valued field is filed by record_callback_interaction as
callback_interaction, provenance the channel itself. The correlator it needs is
the one section 3 mints. Register at most one client and stop.

Where the discovery document says requests by reference are supported, the
reading is whether the server really dereferences one. All three arms are one
`url` each on the authorisation path through `mcp__rk2__http_request`. The
baseline names a URL on the subject's own origin that certainly answers 404,
where a fetch-failed error says the server looked. The variant names a
same-origin URL answering 200 with a body that is not a signed request object,
where a parse error instead means the bytes came back. The control is a
syntactically invalid URL, which must return a validation error issued before
any fetch. body_differs naming the 200 arm against the 404 arm is what
close_test_replay closes. Two same-origin URLs are the whole reading: an arm
naming an internal address, a metadata service or a third party is not sent.

## 3. Chained delivery, where the proof is an arrival

Where the Program has a declared and bound out-of-band channel, mint a correlator
with `mcp__rk2__mint_callback`, naming that channel in `channel` and the flow in
`subject_label`, and run the flow three ways. The baseline is the ordinary flow with the registered
callback, where nothing arrives on the channel. The variant points the callback
at an open redirect inside the Program's scope that forwards to the correlator,
and an arrival carrying the credential proves the chain end to end. The control
points the callback straight at the correlator, which the allowlist must reject.
A control arrival cannot be the negative, because a control correlator is tied to
a null subject and writes no Observation. status_differs naming the chained arm
against the rejected control is what close_test_replay closes, and
record_callback_interaction files the arrival as the edge carrying the weight.
One arrival ends the attempt, and the delivered credential is never redeemed.

## 4. The encoding, and the credential redeemed twice

Both readings are one `url` or one `body` per arm through
`mcp__rk2__http_request`, and since ticket 211 the token endpoint's form
parameters ride the action itself. The encoding reading needs the target's own
provider. Baseline: the ordinary code response. Variants: a multi-valued response
type with a fragment response mode, an implicit token response, and the same with
the token parameter renamed. Control: that multi-valued parameter carrying a
value that is not a response type, which must return an unsupported-response-type
error. Three combinations and stop. The redemption reading is sequential.
Baseline: redeem the code once, tokens issued. Variants: the same code a second
time, a code after its stated lifetime, one client's code at a second client's
endpoint. Control: a code never issued, which must be refused. Any variant
matching the baseline's issue status is the defect. status_differs naming an
accepted arm against its control is what close_test_replay closes in both
readings; a response to a presented credential is what credential_effect is for,
and promote_proposal files it off the refused control's own Receipt in the role
control. Record the issue status and stop.

## 5. The binding the callback does not read

The differential is the binding value in the callback url, which rides the
request line, so the arms are one `url` each through `mcp__rk2__http_request`,
filed as one specification with `mcp__rk2__propose_test` and closed by
close_test_replay. Run them on a Task with no leased Identity for the client's
origin, because `identity.Session.inject` replaces `Cookie` with the jar's on a
Task that holds one. The other half leaves as section 2's does, a
`suggested_tasks` entry on `mcp__rk2__submit_mission_result`. The cost is that
there is no jar either, so a binding cookie the authorisation step set is not
carried back: the baseline is what tells that apart from a callback that never
read the binding, and where the baseline itself establishes no session the
reading is inconclusive and stops. The baseline replays the callback exactly as
the issuer produced it and the client establishes a session. The variants replay
it with the binding value removed, with it altered by one character, and with a
value from an earlier flow. The control replays it with the authorisation code
altered instead, which must fail, proving the replay path is live. status_differs
naming the binding-removed variant against that control is what close_test_replay
closes: the variant establishing a session where the control is refused is the
defect and settles the claim supported, and the variant refused exactly as the
control is refutes it. Codes are single-use, so a burnt one ends the set.

## 6. One lead, in a second browser

Drive two profiles with `mcp__rk2__browse`, stating both as `steps`. Complete one
flow honestly in the first and record the callback the issuer produced. Replay it
in a second profile that is genuinely clean, holding neither the binding value
nor the outbound cookie, then perform one authenticated read of the identity
route there. A dashboard redirect is not a session; the read is. This is a lead.
No step of it can be a Test action, because a browse-lane Receipt is filed under
the agent lane and record_test_action refuses any Receipt whose lane is not the
replay one, so it stops at an Observation and reaches no Finding.
promote_proposal files state_change for the clean profile that now holds a
session and credential_effect for the honest flow it is measured against.

## 7. Propose the claim, and name where a reading halts

Propose it with `mcp__rk2__propose_finding`, naming session_fixation as its
`vulnerability_class`: that argument takes a vulnerability_classes id, not a
dotted Property class, and property_class_vulnerability_classes maps this
Playbook's class to that id. The gate is rk2_finding_refusal, which opens
nothing without the transition close_test_replay wrote. An accepted callback
shape is the claim only where the credential is shown to reach that
destination; otherwise what was measured is the validator.

Four halts are a person's decision, asked for with `mcp__rk2__park_for_human`
carrying the run's own `task_label` and the `question_code` that names why.
Registering a client writes state on the subject, so the first registration parks
under destructive_action. An issuer that is a third-party identity provider
rather than the target's own parks under scope_ambiguous. A clean profile ending
up with a session that is not the leased Identity's parks under
third_party_impact. An arm needing a second client registration the Program has
not supplied parks under credential_needed. The writer is park_task_for_human.
Every other halt is a reading that ran out -- three combinations sent, one
arrival recorded, a code burnt -- and no question code says that, so those are
reported through the Task's own record. Two readings are refused. Reading the
session the callback minted off the response's own `Set-Cookie` header is
blocked, because that header is scrubbed before the response is handed back and
ticket 172 owns the audited reveal. Redirect scheme hijacking, where a second
application registers the same custom URI scheme and catches the credential, is
out of scope, because its subject is a mobile client and no open ticket decides
whether that is ever a subject this harness names.

This section runs no Test and grades nothing. 2 of 7 steps cannot be graded.
