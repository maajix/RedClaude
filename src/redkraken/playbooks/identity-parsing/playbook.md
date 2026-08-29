---
description: Ask whether the identity an assertion is trusted for is the identity its signature actually covers, by submitting one signed document whose subject is stated twice, one with every signature removed, one missing a required element, and one where a genuine credential is posted beside somebody else's name.
bb:category: authentication
bb:outputs: ["authentication.federation_trust"]
bb:triggers_all: ["state_changing_method", "tech_saml"]
bb:skills: ["compare-responses", "handle-untrusted-content", "use-identity"]
bb:risk: approval_required
bb:effects: mutates_session
bb:baseline: none
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 50 as the v2 replacement for v1's identity-parsing pack, against the federation-trust leaf of the ticket 18 vocabulary; the v1 saml text is attached as a maintainer reference and is the source of the wrapping technique this Playbook uses. Rewritten for ticket 101 against the merged ledger, which carries four readings and one blocked reading for this slug; three of the four are new. One key moved. The refuted variant row named response_invariant while the supported row of the same role names credential_effect, and one role writes one kind whichever way a reading goes, so the refuted row now names credential_effect too.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "credential_effect", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "credential_effect", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "credential_effect", "polarity": "supports", "min_count": 1}]
bb:references: ["saml.md"]
---

# Two readers, one document, and the identity they disagree about

A relying party that consumes a signed assertion runs two readers over the same bytes. One verifies a
signature over some region of the document; the other pulls out the subject and logs somebody in. Nothing
guarantees those two regions are the same, and every classic defect in this family is that gap: a second
assertion added beside the signed one, an element moved under a wrapper, a `NameID` the verifier never
covered, a document with no signature at all, a genuine token posted beside somebody else's name.

Every request goes out through `mcp__rk2__http_request` and every specification is proposed with
`mcp__rk2__propose_test`, because close_test_replay is the only writer of the transition a Finding
needs and derives both the verdict and the Observation kind from a Test's own assertions. Since ticket
211 a Test action states a `body`, which is what puts all four readings on the Finding path: every arm
differs from its baseline in the POSTED DOCUMENT. A setup step still carries a method and a url alone, so
the unchanged post that establishes the scale is an action rather than setup.

**Every closing Test has the same shape.** Actions 1 and 2 carry role `baseline`: the unchanged document
posted twice, asserted `body_equals`. Action 3 carries role `control`: the arm's own control, which must
be refused. Action 4 carries role `variant`, asserted `status_differs` against action 3. A specification
holds three to thirty-two actions and must carry all three roles, so a two-armed form is refused before
it runs. `close_test_replay` derives a `response_differential` for the two actions that assertion names.

The credential_effect the bar declares is a second edge and its timing is not free. An edge cannot be
added to a claim past proposed, and the first recorded action moves a claim to testing, so every arm is
sent live and its identity route read live BEFORE a specification is proposed, and both Observations are
filed with that proposal through `mcp__rk2__submit_mission_result` in the roles the bar names.

**These readings run under a leased Identity and no arm states a `Cookie` of its own.** The differential
is the posted document, never a crumb, and a leased Identity owns `Cookie` and every header it declares
for the origin, so a plan-stated one would be dropped anyway. What it also does is absorb the target's
`Set-Cookie` into its own jar and re-present it, which is how the identity-route reads below carry the
session the consumer minted; the jar holds the last one, so read that route right after its own post.

One coverage limit, named rather than designed around: this Playbook is selected on `tech_saml`, so an
OIDC or OAuth deployment never reaches it even though section 5's reading is cheapest there and is the
same class. Where recon did not type the surface as SAML, the question belongs to whoever holds it.

## 1. Get one real assertion, and read it as untrusted content

Every variant below is one signed document with one edit, so this Playbook needs the document. Drive the
issuer's own assertion route once with `mcp__rk2__http_request`, using the federated account the Program
provisioned; what comes back was minted for us, for this relying party, and its Receipt and stored
transcript are the record. An assertion collected from anywhere else is somebody else's credential. An
assertion that exists only inside a leased Identity's exchange is sealed by `use-identity`: record the
reading inconclusive in the Task's own record, name the route that would have minted one, and stop.

Follow `handle-untrusted-content` before quoting anything out of it. A signed assertion carries
attacker-influenceable text in the same envelope as the parts that matter. Write down, from the document
itself: which element carries the subject, which region the signature references, and whether that
reference is by identifier or by position. That last one decides which relocation section 2 can attempt
-- an enveloped signature is a descendant of what it signs, an enveloping one an ancestor, a detached one
neither, and the placement is what leaves the `ds:Reference` resolvable after a move. Preserve the signed
subtree byte for byte: any reserialisation changes the digest and turns every arm below into a rejection
that says nothing about the consumer. This section proposes no specification and grades nothing.

## 2. Ask which subject the consumer read

Post the captured assertion back unchanged, twice: actions 1 and 2, asserted `body_equals`. Then read the
identity route under the session that post produced and the jar absorbed, because a `302` to a dashboard
is not a statement about which account is behind it.

Action 3 is the control, the same document with one byte of the signature changed, which must be refused.
A relying party that logs us in with a broken signature is `authentication.credential_verification`, and
this Playbook hands that over rather than claiming it. A second control is the same forged assertion with
the SIGNED assertion removed entirely. It must also be refused; where it is accepted the finding is
signature exclusion, section 3 is the reading, and the wrapping claim is unproved.

Action 4 is the variant, and the variants each state the subject twice and change nothing else, one edit
per request: a second unsigned assertion carrying a different subject placed before the signed one; the
signed assertion moved under a wrapper element with a copy carrying the other subject left where the
original stood; the subject element duplicated inside the signed assertion. The other name is always a
subject the Program controls.

Where a variant produces a session for a subject the Program does not control, log it out through the
application's own route, stop composing placements, and call `mcp__rk2__park_for_human` with the running
Task in `task_label` and `question_code` third_party_impact, naming the document sent, the subject each
copy named and the session created. A session made as somebody who did not ask is a person's decision.

## 3. Ask whether verification is skipped when there is nothing to verify

Change one `AttributeValue` and the `NameID` to a second account the operator owns, and delete every
`ds:Signature` element. Authentication as the changed subject means the verifier has a branch with no
rejecting else.

The control is decisive: the SAME changed document with the ORIGINAL signature left in place, which must
be rejected. That is the only way to tell a skipped check from an attribute the digest never covered,
which is a different and much smaller finding. The variant is asserted `status_differs` against it and
`close_test_replay` settles the pair.

Halt where the unsigned document is accepted, and do not go on to section 2's placements in the same run:
a consumer that accepts an unsigned document makes every wrapping result unattributable. That halt is a
reading that ran out rather than a question for a person, so none of the five `question_code` values
applies: record both documents, the control that separated the two explanations, and the session created
and logged out, in the Task's own record. An unsigned document accepted is a full authentication bypass
and is reported as one.

## 4. Ask whether the consumer fails closed in states nobody configured

Four arms, one request each, each still a valid signed document apart from the one thing it changes: the
`Conditions` element omitted entirely; a whitespace-only `Issuer`; the consumer reached while the SSO
integration is disabled; and the same document with the audience left unchanged, so the arm isolates the
omission.

The control is a document with a VALID signature naming a subject that certainly does not exist locally.
It must be rejected at account resolution rather than at signature validation, which separates
"verification was skipped" from "the user is unknown", the failure this reading is most often confused
with. Where the answer carries the consumer's own message about which check it skipped, file
error_detail as a second edge, with the proposal, through `mcp__rk2__submit_mission_result`.
Two shapes are worth naming because they are what produces this: a verification call guarded by a mode
test with no rejecting else, and a presence check that passes on a whitespace-only value which later
normalises to the configured empty default.

Halt where an arm returns a `5xx` or the consumer stops answering the baseline document. Re-send the
unmodified baseline once; where it does not answer, the halt is the run rather than the route. This
endpoint is a production authentication path, so record the arm that preceded the failure, the document,
and the baseline re-send and its answer in the Task's own record.

## 5. Ask whether the credential is verified or the identity beside it is trusted

Where the relying party takes a provider credential and an identity field side by side, post the token
together with its own identity twice as the baseline pair, then post the same token together with a
SECOND account's identifier as the variant, and read the identity route under the session it returns. A
session belonging to the second account is the reading. The control is a structurally valid but
never-issued token submitted with the first identity, which must fail; that separates "the endpoint
trusts the identity beside the token" from "the endpoint accepts anything in that field".
`close_test_replay` settles the pair on `status_differs`, and the `credential_effect` comes from the
identity-route read.

Where the token and the identity ride QUERY parameters rather than a posted document, the whole
differential moves into the request line, which is the cheapest shape this reading has; look for it
first. Halt where a session is issued for an account other than the one the token names: log it out
through the application's own route, do not substitute a third identity, and record both identifiers, the
token used and the session and its logout in the Task's own record.

## 6. State the claim, and state what would refute it

The Hypothesis is `authentication.federation_trust` on the application, proposed through
`mcp__rk2__propose_finding` once close_test_replay has carried it to supported. It is supported when a
variant produced a session for a subject outside the signed region, or for a subject named beside the
credential rather than inside it, against a control that shows the consumer refusing a broken signature
or an unissued token. It is refuted when every variant is answered the way that control is, or when the
session belongs to the subject the document was minted for: the consumer read the subject from inside
what it verified. Both verdicts are the Test's; this section runs none of its own and grades nothing,
and the credential_effect edge names which account was behind the session.

Anything else is inconclusive: a consumer that refuses every arm including the unchanged baseline, an
assertion that could not be preserved byte for byte, a `302` this reading cannot resolve to an account.
Assertion replay is a different question: the same unmodified document accepted twice is
`business_logic.replay`, and this Playbook does not test it. What these readings really prove is that the
consumer's verifier and its reader disagree about which node is authoritative, which is
`injection.parser_differential`, handed to `browser-script`, which emits that class since ticket 101;
this reading claims `authentication.federation_trust`.

## 7. The ceiling, and the two readings this slug refuses

Effects are `mutates_session` and risk is `approval_required`, because this Playbook posts to a route
that mints identity and the issuer on the other side is a third party. It sends nothing to the identity
provider beyond section 1's one assertion request, it does not enumerate subjects, and every session a
variant creates is logged out through the application's own route.

The hand-written parser's error-recovery overread -- one attribute left unterminated, so the recovery
path consumes bytes nobody sent -- is blocked where the reported cases land it, a `Set-Cookie` header:
`WIRE_RESPONSE_HEADERS` strips that from the agent view on every path, so the proof never arrives. Where
a deployment reflects the overread into the response BODY instead, the same defect is reachable and is
one more arm of section 4, with `reflected_input` filed for the bytes that were not sent. Its
denial-of-service form is refused outright: it crashes the consumer worker on a production authentication
path, and availability is not a Property class here.

The third-party half is refused and the reason travels with it, because it is re-proposed often. A
genuine provider token minted for a different `client_id` needs an OAuth client registered at a vendor's
own authorization server, which is claiming a third-party resource and a vendor API subject. The in-scope
alternative, editing an `aud` or an email claim, needs a signing primitive this harness does not have.

This section performs and grades nothing. 3 of 7 steps cannot be graded.
