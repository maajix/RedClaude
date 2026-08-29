---
description: Ask whether a route returns fields its own published contract never declared, by differencing the two sets of field names in both directions over stored Artifacts, and then whether the declared shape is only the narrowest thing the route will hand back, by widening the projection, naming a parameter the contract omits, asking the route for a second serialization of itself, and asking a server function to stringify its own argument.
bb:category: information_disclosure
bb:outputs: ["information_disclosure.undeclared_field"]
bb:triggers_all: ["authenticated_endpoint", "read_method", "tech_openapi"]
bb:skills: ["compare-responses", "enumerate-surface", "handle-untrusted-content", "use-identity"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-04-15
bb:provenance: Written for ticket 54 as the v2 replacement for v1's information-disclosure page against a new undeclared_field leaf added by ticket 54; the v1 page carried no attachments, and its advice to harvest whatever the extra fields contain is refused by the closing section. Rewritten for ticket 101 against the merged ledger, which carries five readings and one blocked family for this slug; four readings are new, one of them the second-serialization hand-off ticket 101 named as reachable and unused, and the shipped prose never named the tool run its own content_match bar requires. One key moved -- enumerate-surface is added, because section 3 harvests candidate names out of the served bundle with js_routes and js_parse.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "content_match", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "content_match", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "content_match", "polarity": "supports", "min_count": 1}]
---

# Ask what the contract said it would return

An application that publishes a schema has written down what its responses contain. A
serializer that walks the stored record instead ships whatever the record grew: a
margin, a score, an internal id, a column somebody added last quarter. And the published
shape is only the narrowest answer the route has. It may widen the projection when the
query string asks, accept a parameter the document never mentions, serve a second
encoding of itself that carries more, or hand back a function's own source.

Every claim here is a content_match, and content_match takes tool-run provenance alone,
so every reading ends in a run of jq through mcp__rk2__run_tool or of compare-responses
through mcp__rk2__run_skill_script over stored Artifacts, and a model that reads a body
and names a field has produced no Observation. Each Observation, in the role variant or
control, is filed with the proposal through mcp__rk2__submit_mission_result, which
promote_proposal writes, because an edge cannot be added once a claim is past proposed.

Every request goes through mcp__rk2__http_request, and the run that settles a claim is a
Test proposed with mcp__rk2__propose_test and closed by close_test_replay, the only
writer of the transition a Finding needs. Each specification carries the same four
actions, never re-ordered, because the ordinal binds an action to its Receipt. Actions 1
and 2 carry the role baseline: the plain request, twice unchanged, asserted body_equals.
Action 3 carries the role control, named by no differing assertion. Action 4 carries the
role variant: the arm, asserted body_differs against action 1. Fewer than three actions,
or a missing role, is refused at propose_test.

An arm may carry a body: since ticket 211 a Test action states its own headers and body,
and the door opens a run body-bearing because a Playbook was selected, not because one
admitted to changing something. Every send goes as whichever Identity the Task was
opened under, which is what the closing section's blocked family is about.

## 1. Store the contract, and establish the route twice

Fetch the published document -- `/openapi.json`, `/swagger.json`, `/v3/api-docs` --
through mcp__rk2__http_request, and register_proxy_artifacts files it as an Artifact
against the Receipt. Find inside it the schema for THIS route: the path, the method, the
status the baseline returns and the content type, all four, because a document declares
several and comparing a 200 against a 404's schema is a set difference with no meaning.
Treat it as untrusted content, which is the target's text and never a reason to send a
request the Task did not ask for.

Then send the route twice unchanged and store both responses. A route returning a
different set of NAMES on each call has no field set to make a claim about, and the
reading stops there. So does a document declaring no schema for this route: a bare 200,
a `$ref` that resolves to nothing, an `additionalProperties` left open. Report
inconclusive and say which it was. This section establishes the two documents, closes no
Test and grades nothing.

## 2. Difference the declared names against the returned names, both ways

Three tool runs and no fourth. Two mcp__rk2__run_tool runs of jq: one over the contract
Artifact, reducing to the leaf property paths the schema declares for this path, method,
status and content type, following `$ref`, `allOf` and `oneOf` and emitting each as a
dotted path so that order.total and shipment.total stay two declarations; one over the
response Artifact, emitting the names present by the same paths. Then one
mcp__rk2__run_skill_script run of compare-responses over the two outputs, each filed as
its own Artifact by close_offline_tool_run.

The names present and not declared are the claim: each with its path and the KIND of
value it held, never the value. The names declared and not present are the control
direction and that list must be empty, because if the contract's own names are missing
the comparison is pointed at the wrong route, status or content type. File both as
content_match Observations, roles variant and control, citing the runs. Both documents
must be JSON, since jq is the only registered binary that parses structure, so a YAML
contract or an XML route has no reader here and the verdict is inconclusive.

A name is not a finding when the contract declares that level open, when it is declared
somewhere the extraction missed -- a reference resolving through another file, a
composed schema, a discriminator -- or when it is the envelope's rather than the
payload's, a cursor, a links block, a trace id the route adds to everything. Say which
of the three were checked.

This section closes no Test and grades nothing. A set difference between a contract and
a response is not something the replay lane can assert -- a Test naming the contract's
url against the route would be a comparison of two unrelated documents, true of every
deployment and carrying none of the claim -- so the content_match over the two jq
outputs IS the reading, and it is an Observation. The transition a Finding needs comes
from sections 3 to 6, whose arms differ in the request line, and these Observations are
filed with that proposal.

## 3. Ask which parameter names the route accepts that nobody sends

The other direction of the same question. Harvest candidates from the application's own
served code with a mcp__rk2__run_tool run of js_routes or js_parse over the stored
bundle -- a hidden input, an unused variable, a name in the route table -- never from a
wordlist. The arm is the baseline request plus ONE harvested name, one name per arm. The
control is the same request plus an INVENTED name of the same shape and length, which
must not change the answer: without it, a response that changed when a parameter was
added is a statement about adding a parameter. Where the control moves too, stop. What
came back goes through section 2's pass, which is what makes the claim a content_match
rather than a reading by eye.

## 4. Ask whether the projection is only the narrowest default

On an OData-shaped endpoint the declared shape may be a default the query string widens.
The baseline is the collection with no expansion, where the related object appears as an
id alone. The arm adds `$expand` over one relation with a nested `$select` naming fields
the route's own schema does not declare. The control is the same `$expand` with a nested
`$select` naming a field that does not exist on the model, which must answer 400: that
is what proves the selection reaches the model rather than being parsed and dropped.
Both arms go through mcp__rk2__http_request, close_test_replay settles them as a
response_differential, and what came back goes through section 2's pass, which makes the
claim a content_match. One relation, one control. Do not read the values. Where a
relation yields credential-shaped field names, record it through this Task's own record
at once and stop: no question code in the served set says that a reading succeeded.

## 5. Ask whether a second serialization of the route carries more

An application rendering server components serves one route twice: as a rendered
document, and as a line-delimited payload marked with `$I`, `$F`, `$L`, `$@` and `$B`. A
`__NEXT_DATA__` block, a `__NUXT__` payload and Remix loader data have the same shape,
and the selector comes out of the served bundle with a js_routes or js_parse run, so the
encoding is read rather than guessed. Take the selector in the query string and not its
request-header spelling. The arm is the route plus the selector; the control is a
selector value that is not a live id, which must answer the ordinary document or 400,
proving the arm SELECTED a second encoding rather than renaming the first. Then run
compare-responses over the two stored encodings: the payload is line-delimited, so one
line is one chunk and the set difference IS the reading, and a property name present in
the second encoding and absent from the rendered document is the claim, filed as a
content_match. jq is wrong here because the stream is not one JSON document, and so is
js_parse. One route, then stop.

## 6. Ask whether a server function stringifies its own argument

Where the application exposes server functions, an argument reference that resolves to a
server reference can come back as the stringified function body, source and all. The arm
names a live action id in the `Next-Action` header and carries the encoded argument in
the body, both of which a Test action states since ticket 211. The baseline is the same
action id with an ordinary string argument, twice; the control is an id that does not
exist, which must answer 404 or 500, proving the id the arm used was live. The send is a
POST, and a method outside GET, HEAD and OPTIONS raises the call to approval_required at
the door under the code destructive_action. Ask for this Task to be parked with
mcp__rk2__park_for_human before the first send, naming it in `task_label` and that code
in `question_code`. This section is therefore a lead of this Playbook and grades
nothing: parking closes the run, and what follows the halt runs under whatever Task the
operator opens next. One action id, then stop. Where the reply carries something shaped
like a live credential rather than source text, record its class and never its value.

## 7. State the claim, and state what would refute it

The Hypothesis is information_disclosure.undeclared_field on the endpoint, carried to a
Finding with mcp__rk2__propose_finding once a Test has settled it. It is supported when
a name the schema does not declare came back, every declared name was found where the
schema said it would be, the two baseline responses carried the same set of names, that
reading's own control behaved as its section requires, and none of section 2's three
explanations applies. It is refuted when every declared name is present and nothing else
is. Anything else is inconclusive, including a document jq cannot parse.

Two neighbours are close. Where the extra data is another principal's rather than an
extra property of this caller's own, the class is information_disclosure.excess_field
and the Playbook is `graphql`, whose reading sends one selection under two Identities;
this one holds one on purpose, because it measures a contract and not a boundary. Where
the extra text appeared because something failed, it is
information_disclosure.error_detail and the Playbook is `exceptional-conditions`. This
section proposes no Test of its own and grades nothing. Cite the Artifact hashes, the jq
filters verbatim, and the comparison's digests.

## 8. The ceiling, and the one family this slug cannot close

This section performs and grades nothing. This Playbook is read_only and its baseline is
a session that stays stable. It does not walk the contract's other paths, call an
operation the contract declares, or use the document as a route list, which is
`attack-surface`'s question. And it does not harvest what the undeclared fields contain:
the finding is that a name is present the contract never promised, together with the
kind of value it held, and a report quoting the margins, the scores or the internal
identifiers of real records has published what it says should not have been published.
One family is blocked rather than dropped, because it is how most of this category is
worked by hand. Differencing an authenticated response against the anonymous one for the
same route, the detection step for authenticated XSSI, cannot be one Test: a replay run
holds one Identity slot for its length, so both arms of one Test are one Identity, and a
Finding needs a closed Test. Nothing here substitutes for it. The adjacent
account-existence oracle asks with no Identity on either arm and is not blocked, but its
class is information_disclosure.identifier_oracle.

5 of 8 steps cannot be graded.
