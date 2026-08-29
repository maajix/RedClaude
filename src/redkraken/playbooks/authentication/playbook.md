---
description: Ask whether the check happens rather than whether the secret is right, by presenting one credential in shapes the comparison was not written for, and by asking the same question of a recovery flow -- what its answer hands back, who addressed the link it built, whether the credential it minted is unique and single-use, and whether the step that completes the change compares anything at all.
bb:category: authentication
bb:outputs: ["authentication.credential_verification", "authentication.recovery_flow"]
bb:triggers_all: ["email_valued_parameter", "state_changing_method"]
bb:skills: ["compare-responses", "enumerate-surface", "use-identity"]
bb:risk: approval_required
bb:effects: mutates_account
bb:baseline: none
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 50 as the v2 replacement for v1's authentication pack, against the credential-verification leaf of the ticket 18 vocabulary; four v1 texts are attached as maintainer references and the type-juggling one is the only one that named this defect. Rewritten for ticket 101 against the merged ledger, which carries eleven readings, three blocked and two refused for this slug. Four keys moved. bb:outputs gains authentication.recovery_flow, the emitter ticket 101 owes and the class ten of the sixteen rows read. bb:effects rises from mutates_session to mutates_account because section 5 completes a recovery on an account the Program designates, and bb:risk rises with it to approval_required, the floor that effect asks for. bb:skills gains enumerate-surface, already held by the role that executes this text. The refuted variant row moves from response_invariant to credential_effect, the kind the supported row of that same role names, because close_test_replay derives the kind from the specification.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "credential_effect", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "credential_effect", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "credential_effect", "polarity": "supports", "min_count": 1}]
bb:references: ["cloud-aws-cognito.md", "http-attacks-password-reset.md", "sign-up-login-register.md", "type-juggling.md"]
---
# Ask whether the check happens, not whether the password is right

The subject is wherever a credential is presented or minted: a login, a token exchange, a recovery
request, the step that completes one. Guessing a password is not this Playbook and never becomes it.
Two questions are answerable. Does the server decide by comparing what was sent against what it
holds, and is the credential a recovery flow issues unique, single-use and compared when it comes
back. Every reading is one Test of at least three actions holding a baseline, a variant and a
control, because rk2_test_spec_problem refuses a specification performing fewer than three or
leaving a role out. The arms go out with `mcp__rk2__http_request` and are filed as one specification
with `mcp__rk2__propose_test`. Since ticket 211 an action states `headers` and `body` beside
`method` and `url`, so a login document, a recovery request and a completion form ride the action
itself. What settles a claim is close_test_replay, deriving the transition and the Observation kind
from the specification's own assertions and nothing else. The credential_effect, reflected_input and
content_match Observations named below are agent-filed and go in WITH the proposal through
`mcp__rk2__submit_mission_result`, because an edge cannot be added once a claim is past proposed.

## 1. The secret presented in a shape the comparison was not written for

The correct credential is a leased Identity. The run acts as whichever Identity the Task was opened
under -- the step does not choose it and there is no argument for it -- and the door attaches it;
nothing here prints or copies the secret, and where no lease holds a working one the reading does
not start. Baseline, that credential presented correctly. One control is the same request with the
secret replaced by a certainly wrong value of the same type, which says a decision is returned at
all: an endpoint answering 200 to both does not authenticate here. The second is the baseline sent
twice unchanged, because a login answer carries a fresh token and an unstable route cannot be
differenced.

Each variant changes one thing and is sent once: the field omitted; present and empty; carrying a
boolean, a number, an empty array or an object; and where the credential is a signature or a MAC,
the same document with it removed and with it present but empty. A second family belongs to the same
Test, one spelling per request -- an LDAP wildcard against a known username, an XPath predicate
closing the quoted term and appending an always-true clause, a comparison-operator document where
the store parses documents -- with its own control: that spelling against a username that certainly
does not exist, which must be refused. Nothing iterates over values of the same type, and the blind
halves that rebalance a filter or walk a node set positionally are enumeration and belong to
sql-injection. status_differs naming a malformed arm against the wrong-secret control is what
close_test_replay closes, and the decision returned for a credential nothing verified is what
credential_effect is for. An arm matching neither end of the scale is an error_detail question for
exceptional-conditions.

## 2. The pre-authentication answer that names an account

Where the pre-authentication surface answers an identifier from the request line -- an availability
check at registration, a lookup route, a public profile route -- the differential rides the url and
the reading is three sends. Baseline, an identifier that certainly does not exist. Variant, one
known to exist, where the operator's own account is enough. Control, a SECOND certainly-absent
identifier, whose answer must match the baseline byte for byte: two identical sends would not
separate a stable page from one stable for a single identifier, and where the absent arms already
differ the endpoint carries a nonce and the variant proves nothing.

status_differs or body_differs naming the known arm against an absent arm is what close_test_replay
closes, and the difference is sometimes a single invisible character a byte comparison catches and a
reader does not. Three requests, declared before starting, stopping at the first pair that differs:
the question is whether an oracle exists, never how many accounts can be harvested. The Hypothesis
it settles carries `information_disclosure.identifier_oracle`, which `exceptional-conditions` emits
and this Playbook does not.

## 3. What the recovery answer hands back, who addressed it, and who it was addressed to

Three readings, one Test each, on a Task holding no leased Identity because the recovery request is
unauthenticated, and both only against accounts the Program designates. This route DELIVERS MAIL,
and an arm carrying an address the engagement does not own is refused rather than sent. The first
asks whether the answer carries the issued credential itself, and it gates the family: where the
credential arrives only in a mailbox, nothing below starts. Baseline, the recovery request for the
first designated account, sent twice unchanged. Variant, the same naming the second. Control, the
same naming an identifier that certainly does not exist, whose answer must NOT carry a
credential-shaped field -- if it does, the field is a template rather than a live credential and the
reading is void. body_differs naming the variant against that control is what close_test_replay
closes, and a jq run under `mcp__rk2__run_tool` over the two answers, or js_parse where the answer
is not JSON, names the credential-shaped member as the content_match the agent files.

The second asks where the absolute URL in that answer takes its authority from. Baseline, the same
request with no override header, sent twice, whose echoed link names the deployment's own authority.
Variant, that request carrying a forwarded-authority header set to a marker the Program controls;
those names are in neither the hop-by-hop set nor the internal prefix, so they reach the target
verbatim. Two controls: the override set to the application's OWN host, whose answer must match the
baseline, and a valid name the Program does not control, which says whether an allowlist exists.
Without the own-host arm those two answers cannot be told apart. body_differs naming the marker arm
against the own-host control closes it, and the marker authority inside the generated link is the
reflected_input edge. The duplicate-Host and absolute-request-line spellings are not arms: host is
hop-by-hop and one header name carries one value.

The third asks whether the recipient field takes more than one value. One Test on the same route,
every address on both sides one the Program's test identity controls. Baseline, a single valid owned
address, accepted. Variants, one multiplicity spelling per request: the name repeated in the query
and in the document, a JSON array of two owned addresses, a comma list, a value carrying a folded cc
line, a form body restated as JSON with a nested array. Two controls: a value that is not a valid
address, which must be a validation error and says the field is validated at all, and the baseline
sent twice unchanged. status_differs naming an accepted multiplicity arm against the invalid-address
control is what close_test_replay closes. The claim is kept on whether the SHAPE was accepted and
never on what arrived anywhere; this endpoint's abuse is visible to end users rather than to logs.

## 4. The credential the flow issued, replayed and read for structure

Baseline, request a credential for a designated account and use it once, which succeeds, storing the
whole answer. Variant, replay the identical completion request with the same credential. Control,
issue a SECOND fresh credential and use it once, which must succeed, separating a single-use
credential from credentials that stopped working after the first change. status_differs naming the
replayed arm against the fresh-credential control is what close_test_replay closes. The expiry
sibling is one further arm. The structural half runs off sends of its own: a credential for the
first designated account, a second for that account seconds later, a third for the second account,
read side by side with a jq or js_parse run under `mcp__rk2__run_tool` for the version and variant
nibbles where the value is a UUID, the shared prefix, the ordering, and any decodable timestamp or
account identifier. A credential minted by a DIFFERENT endpoint of the same application, read the
same way, says whether the property belongs to the deployment or to this one flow. The all-zero
credential is a one-request arm. That structure is a content_match filed off the reader run, cited
from sends made before the proposal. Walking a bracketed range against the redemption endpoint until
an answer changes is refused by section 6.

## 5. The completion step, and what the change leaves standing

Three readings against a flow the Program designates. Two change a credential, which is why this
Playbook declares the effects it does and sits at the risk floor that effect asks for.
status_differs naming the variant against the control is what close_test_replay closes in all three.
The first runs where the flow has a SEPARATE validate step, so acceptance is readable without
completing the change, and where the credential rides the query string, the shape a mailed link has.
Baseline, that step with a well-formed and certainly wrong credential, rejected. Variants, the field
absent, present and empty, the JSON null, the string spelling of null, an empty array, one per
request. Two controls: the well-formed-wrong arm, which says the step rejects at all, and that arm
sent twice unchanged. What an accepted absence names is a stored side of the comparison nothing ever
populated.

The second completes the change. Baseline, the completion route posted with a fabricated identifier,
a new password and its confirmation and no credential field at all, sent twice. Variant, that
request naming the Program's own account, where a success with nothing presented is the class.
Control, the same naming that account with a malformed confirmation field, which must answer a
validation error and proves the success came from the recovery path rather than a route answering
200 to everything. The one follow-on request presenting the new password is the Receipt
credential_effect is filed from.

The third asks what the completed change ended. Baseline, the identity route read under the leased
session, answering 200 with the account's own record, sent twice. Variant, complete the recovery for
that account and read the identity route again under the SAME session, where a 200 says the change
left the old session standing. Control, post the logout route under that session and read once more,
which must refuse: without it a 200 after the change says nothing about recovery, and where the
logout arm does not refuse the reading stops before any recovery is completed, because the change
cannot be undone. The Task's credential material has to survive the change or be reissued, and the
recovery has to be completable in band -- section 3's gate, or this section's no-credential path --
because the recorded channel takes DNS and HTTP arrivals and is not a mailbox.

## 6. Propose the claim, name where a reading halts, and state what is refused

Propose it with `mcp__rk2__propose_finding`, naming improper_authentication as its
`vulnerability_class` for the comparison readings and weak_credential_recovery for the recovery
ones: that argument takes a vulnerability_classes id and never a dotted Property class. The gate is
rk2_finding_refusal, which opens nothing without the transition close_test_replay wrote.

Three halts are a person's decision, asked for with `mcp__rk2__park_for_human`, which sends nothing
without both the `task_label` of the Task this run is executing and the `question_code` that names
why. Completing a recovery writes a new credential on the subject, so the first completion parks
under destructive_action. A recovery request for an address the Program has not designated parks
under third_party_impact and is not sent. An arm needing a second account the Program has not
supplied parks under credential_needed. Every other halt is a reading that ran out -- a declared
count reached, a credential burnt, a lockout or a 429 arriving mid-sequence -- and none of the five
codes says that, so those are reported through the Task's own record.

Three readings are blocked and each keeps its reason. A credential that exists only inside a mailbox
is blocked: the recorded channel takes DNS and HTTP arrivals, is not an MX, and nobody clicks a
mailed link. Its digest-derivation sibling, where the code is a hash of the account's own fields, is
blocked because no registered program computes a hash. Reading the challenge a 401 issues, or the
session artifact a login sets, is blocked because those six response header names are stripped from
the agent view on every path, so the status half survives and nothing else does. Settling a claim on
elapsed time is blocked because no assertion kind is time-shaped, so the channel is observed and not
claimed. Two readings are refused. Composing a vendor default or a reused pair and presenting it is
refused because this Playbook sends each SHAPE once and never a second value of the same type; a
leased Identity owns Cookie and every header it declares for the origin, so such a credential would
not reach the wire under one anyway. Presenting a recovery credential minted for one account
alongside a second account's identifier is refused, and with it the two neighbours it stands for: a
credential disclosed in a response and proved by completing the change, and a password policy
enforced at signup and not at completion. Every arm of it is expressible; what is refused is
completing a change on an account whose own flow never asked for one.

This section proposes and refuses and runs no Test, so it grades nothing. 1 of 6 steps cannot be
graded.
