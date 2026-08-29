---
description: Ask whether a GraphQL endpoint answers a caller more than the caller is entitled to, by sending one application operation as two people and closing on a single-Identity pair that differences the disputed selection against the same selection naming an object that does not exist.
bb:category: information_disclosure
bb:outputs: ["information_disclosure.excess_field"]
bb:triggers_all: ["graphql_surface", "multiple_test_identities"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-02-15
bb:provenance: Written for ticket 49 as the v2 replacement for v1's graphql pack, against the excess-field leaf of the ticket 18 vocabulary; the v1 api-graphql text is attached as a maintainer reference and is not the source of this class. Rewritten for ticket 101 against the merged ledger, which carries three procedures, one lead and two refusals for this slug. Two keys moved. The refuted variant leg moves from response_invariant to response_differential, the kind the supported leg of the same role names, because close_test_replay derives a kind from the specification rather than from the outcome and a refuted leg naming a second kind is one nothing writes. The description now names the single-Identity closing pair, because the cross-Identity comparison the shipped text was written around cannot itself settle a Test -- one replay run leases one Identity for its length -- and a reader following the old description would build a specification the run refuses.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_differential", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "credential_effect", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "response_differential", "polarity": "supports", "min_count": 1}]
bb:references: ["api-graphql.md"]
---

# Ask the same question as two people, and close it as one

A GraphQL endpoint answers the selection it is given. Authorisation in these stacks is
usually written per resolver rather than per response, so the interesting question is not
whether a type is reachable but whether one field on a reachable type carries a value for a
caller who should not have it.

That difference is between two documents sent under two Identities, and it is an exploration
rather than a verdict. A replay run leases one Identity for its whole length, so two arms
differing only in who sent them are two runs, and rk2_finding_refusal wants the settling
Receipt to belong to the one run the claim cites. The reading is therefore split: the
cross-Identity comparison motivates the claim and is filed beside it, and a single-Identity
pair inside the second caller's own Task is what closes it.

Every Test below holds at least three actions and at least one each of baseline, variant and
control, because rk2_test_spec_problem refuses a specification performing fewer than three
or leaving a role out. Since ticket 211 an action states headers and body as well as method
and url, so an operation document rides the action itself and no reading here has to be
respelled into a query string to be gradeable. A body is framing rather than an effect, and
this Playbook stays read_only while sending one.

One rule governs the agent-filed half of every section. The supported bar asks for a
credential_effect in role control; credential_effect is agent-filed, promote_proposal writes
the kind the proposal names, and rk2_promote_hypotheses drops an edge offered once a claim
has left proposed. So every arm goes out once through `mcp__rk2__http_request` before its
Test is proposed, and each section files that Observation in role control from the Receipt
of the arm that answers this Task's own Identity normally -- label B's own selection in
section 2, the trivially valid document in section 4, the extension-free operation in
section 5. Without it the settle is downgraded to inconclusive whatever the assertions did.
Sections 4 and 5 name the BASELINE as the other end of their differing assertion, so no
control action of theirs is named by one.

## 1. Name the operation and the two Identities

Read the recorded surface for the operation this subject carries. The selection this
Playbook sends is the application's own -- the one the client sends -- and not one written
here: an invented query tests the schema, and the schema is not what the application
authorises against.

Name two Identity labels the mission packet supplies. Label A is the one the data belongs
to. Label B is the one that should see less of it. A call goes out as whichever Identity its
Task was opened under and there is no argument for it, so reading as two people is opening
two Tasks.

If the operation is a mutation, this Playbook does not apply to the subject: it reads, and a
mutation sent twice is two writes. This section reads and names, proposes no specification
and grades nothing.

## 2. The same selection, sent as two people and closed as one

Open label A's Task first and send the application's own operation, then send it again
unchanged, both through `mcp__rk2__http_request`. That pair is the full document for the
caller the data belongs to, and it is what the later comparison is measured against.

Open label B's Task and propose one Test with `mcp__rk2__propose_test`. The baseline is
label B's own equivalent selection, which must come back with a populated data member --
that is what tells a refusal apart from a session that was never valid, and it is the
credential_effect this Playbook's control bar names, filed by promote_proposal from the same
Receipt. The variant is label A's operation sent byte-identical from label B's Task: same
operation name, same variables, same selection. The control is that same disputed selection
naming an object identifier that does not exist. body_differs naming the variant against the
control is what close_test_replay closes, and both arms are one Identity and two documents,
which is what a Test can carry.

If the selection has to be edited to be accepted under label B -- a different identifier in
a variable, a field removed -- then two things moved and the difference is about neither.
Stop and record that.

Difference label A's stored document against the variant's with
`mcp__rk2__run_skill_script`, naming compare-responses, and cite the fields the script
reports as present in both. That comparison is the exploration: it is filed WITH the
proposal through `mcp__rk2__submit_mission_result`, because promote_proposal is what writes
an agent-named Observation and an edge cannot be added once a claim is past proposed.

## 3. The disputed key, read with a tool rather than by eye

A GraphQL response nulls what a resolver refused and keeps the key, so "the field is in the
response" and "the field carries a value" are different findings and only the second is this
class. Establish which by running jq under `mcp__rk2__run_tool` over the stored Artifacts,
with a program that reports the disputed path beside the errors array. Run the same program
over label B's own control document, which must show label B's data present at that path,
and run it twice over one Artifact, which must return the same bytes: without the second leg
the difference could be the program rather than the document.

This section files an Observation and grades nothing. Its product is content_match, whose
only allowed provenance is a tool run, and close_test_replay writes response_differential
and response_invariant alone, derived from a Test's own assertions. The edge
rk2_promote_hypotheses writes from it is real and is never filtered out; it names the
mechanism behind the verdict section 2 settles, and it settles nothing itself. Where the
body is not JSON the reader exits with a parse error, no content_match is filed, and the
section is over.

## 4. The character the lexer ignores and a filter does not

Where a filter -- a gateway rule, a middleware pattern, a deny list -- refuses a named
token, the question is whether the defence is a string match on the request or a decision in
the schema.

One Test through `mcp__rk2__http_request`. The baseline is the plain document carrying the
blocked token, refused. The variant is the identical document with one character the GraphQL
lexer discards inserted between the token and its brace -- a newline, a tab, a comma, a
space. The control is a trivially valid document naming no blocked token, which must
succeed, because an endpoint refusing everything makes the variant mean nothing, and whose
Receipt is where this section's control credential_effect is filed from; a second control
repeats the baseline unchanged. status_differs naming the variant against the baseline is
what close_test_replay closes.

An accepted variant is a defeated filter and not this Playbook's class: what the reading
found is a disagreement between the component that matched and the component that parsed,
which is injection.parser_differential, and browser-script emits it since ticket 101. Hand
the verdict there. Store the answer as Surface, send no second separator, and stop.

## 5. The hash that was never registered

Where the endpoint answers automatic persisted queries, the question is whether the hash is
a cache key or an allow list.

One Test. The baseline carries a persisted-query extension whose hash was never registered
and no operation string beside it, which answers with a not-found error. The variant carries
the identical extension and hash WITH a full operation string, and a data member there means
the raw operation ran and was then cached under a hash the caller chose. The control is a
full operation with no persisted-query extension at all, which separates "the endpoint
required a hash" from "the endpoint never did" and whose Receipt is where this section's
control credential_effect is filed from; a second control repeats the baseline unchanged.
body_differs naming the variant against the baseline is what close_test_replay closes.

One operation, one hash. Register no second one, and send no mutation through the same path.
Name the hash that was written in the report so it can be evicted.

## 6. State the claim, and name the two readings this slug refuses

The Hypothesis is information_disclosure.excess_field on the operation, proposed with
`mcp__rk2__propose_finding` naming sensitive_data_exposure as the class -- that argument
takes a vulnerability_classes id and not a dotted Property class, and
property_class_vulnerability_classes maps this Playbook's class to it. It is supported when
the disputed selection carried a populated field belonging to label A where the same
selection against a nonexistent object did not, with label B's own selection answering
correctly beside it. It is refuted when the variant is answered as the nonexistent-object
control is, on a control that succeeded. Anything else is inconclusive: a document that
cannot be told apart between two sends, a resolver that nulls the key either way, an answer
whose fields could belong to either caller.

Two readings are refused rather than absent. Batching and aliasing -- one request carrying
an array of operations, or one document carrying many aliased copies of a field -- is
refused because the honest version is a deliberate load, and a deliberate load needs the
approval a rate-limit sequence needs; how much one request can cost is
rate_limiting.resource_cost, api emits it, and this Playbook may not claim it. Requesting
the type graph is refused by this Playbook rather than by the harness: the door sends it
happily, and its product is a surface fact. A schema says what fields exist, which is
surface -- record it as surface and let the scheduler choose an operation for the reading
above. Reporting the introspection response is reporting a configuration, not a document a
caller was not entitled to, and turning a recovered type graph into a sweep of the
operations it names is refused with it.

This Playbook reads. It sends no mutation, does not log out, does not retry the variant with
a rotated token, and leaves the session it was given. Its baseline is stable_session, so the
runtime drops it beside anything that moves one. Where a variant document returns a field
naming a natural person who is neither test Identity, the reading stops there and the
operator is told; that halt is a reading that ran out and it names no question code, so it
is reported through the Task's own record.

This section proposes and grades nothing. 3 of 6 steps cannot be graded.
