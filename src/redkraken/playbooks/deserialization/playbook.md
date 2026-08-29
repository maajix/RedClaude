---
description: Ask whether a serialised parameter lets the caller choose which type the route reconstructs, by classifying the blob offline, by telling a parse-level failure apart from a validation failure, and by sending two arms whose blobs differ only in the type name they carry against a baseline that was itself invariant.
bb:category: injection
bb:outputs: ["injection.object_graph"]
bb:triggers_all: ["authenticated_endpoint", "serialized_object_parameter", "state_changing_method"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: constrained
bb:effects: mutates_object
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-04-15
bb:provenance: Written for ticket 54 as the v2 replacement for v1's deserialization pack against a new object_graph leaf added by ticket 54; the pack's gadget page is attached as a maintainer reference and every chain, every payload generator and every proof-by-execution in it stays refused. Rewritten for ticket 101 against the merged ledger, which carries three readings that reach a Finding, three that stop at an Observation, and two refusals. Two keys moved. bb:effects leaves read_only for mutates_object because section 5 writes a property every route the same worker serves reads afterwards and no client action takes it back; bb:risk stays constrained, which is the floor mutates_object allows. The old reason, that a read_only selection could not carry a body, was never true of this tree. The refuted variant row leaves response_invariant for response_differential, the kind the supported row of that same role names, because one role writes one kind whichever way the reading goes.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_differential", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "response_invariant", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "response_differential", "polarity": "supports", "min_count": 1}]
bb:references: ["deserialization-attacks.md"]
---

# Ask who chose the type

A serialised blob carries two things, state and a name for what the state is,
and every question worth asking here is about the second. A route that
reconstructs whatever type the caller's string named has handed the caller a
constructor. The subject is an authenticated, state-changing route carrying a
parameter whose value holds a serialisation marker, and that parameter is read
off the state view rather than picked out of a request, because a route may
carry a session cookie, a token and a saved-state blob at once and only the last
is deserialised. Nothing here runs a chain: the readings ask who chose the type,
never what the reconstructed object then did.

Sections 2 to 4 are each one Test of at least three actions holding a baseline,
a variant and a control, because rk2_test_spec_problem refuses a specification
performing fewer than three or leaving a role out. The arms are sent with
`mcp__rk2__http_request` and filed with `mcp__rk2__propose_test`;
close_test_replay closes the Test and marks BOTH legs of a comparison, so a
differencing assertion names the VARIANT against the BASELINE and never against
a CONTROL, which is then named by an equality assertion or by none. Since ticket
211 an action states `headers` and `body` as well as `method` and `url`, which
is what put the body-borne blob inside the Test lane. A selection carrying this
Playbook permits a body, and that permission is read off the Tool run's own
arguments rather than off any one Playbook's effects.

The carrier decides how a reading may be spelled. rk2_test_request_problem
refuses any dot or double-dot path segment and any %2e anywhere in a
specification url, so a blob whose encoding produces one of those is re-encoded
or the reading moves to the body. record_test_action compares a Receipt to its
action over method, scheme, host, port and path and deliberately not the query,
so a query-borne blob rides through intact while two arms differing only in
their query are indistinguishable to that guard. body_equals and body_differs
read the response body digest alone, so a rotating header does not spoil a
comparison. A blob riding the Cookie header is the one carrier that must be
planned on a Task holding NO leased Identity for this origin, because
identity.Session.inject owns Cookie and drops a plan-stated one before the wire.

## 1. Classify the format before anything is edited

This is a lead and it grades nothing. Run `jq` under `mcp__rk2__run_tool` over an
Artifact already stored, with a `filter` testing the token against the format
table: the base64 prefix or the magic bytes of a Java stream, the leading opcode
of a pickle, the object or array marker of a PHP serialisation, a polymorphic
type-handling key in a JSON document, an XML declaration with a class element.
test, capture, splits and base64 decoding are ordinary jq and all fit inside the
one program. The `input` is one Artifact and the binary is invoked with no
flags, so the body has to be valid JSON: a token in a response header does not
qualify, and set-cookie is stripped from the agent view anyway. The control is
the same program over a token from an application known to issue random
identifiers, so a null match means something. Matching nothing, the reading
stops here rather than editing a field it has not found. The kind is
content_match, whose only provenance is a tool run, and it goes in with the
proposal as a supporting edge; alone it carries a Hypothesis nowhere.

## 2. Whether the value reaches a deserialiser at all

The cheap first reading; it says whether the next section is worth sending. The
baseline is the client's own blob replayed twice unchanged, which is both the
success answer and the proof that the route is byte-stable. The variant is that
blob truncated mid-stream: a parse-level failure, distinct in status from a
plain validation failure, means the value is entering a deserialiser rather than
being compared. The control is a structurally VALID blob carrying a different,
harmless value, which must succeed; failing the way the truncated one did, the
value is merely being compared and the truncation proved nothing. status_differs
naming the truncated arm against the baseline closes it, and a status_equals
holds the control to that baseline, so no differing assertion names the control
and it closes invariant. promote_proposal files error_detail where the failure
named the parser. This reads a status and never a stack trace.

## 3. Who chose the type

The baseline is the request sent twice, unchanged, carrying a blob the client
itself produced. The variant is the same state re-encoded by the same code path
naming a type the client never sends, taken from the runtime's own standard
library and chosen for being inert: a container, a collection, a primitive
wrapper, a date. No constructor, no readObject, no setstate, no property setter,
no finaliser that touches a file, a process, a socket or a class loader. The
control is the same state through the same encoder naming the type the client's
own blob named, so the pair differs in one string and not in the encoding; a
second control names a type of the right shape that resolves to nothing, and
reproducing the variant it says a validator was measured. Two rounds, four
requests, interleaved with the baseline rather than sent as a block, because a
difference that appears once and not again is a varying route. body_differs
naming the variant against the baseline closes it, a body_equals holds the first
control to that baseline, and the second control is read rather than asserted.

## 4. A type hint carried inside the token

Where the token carries its own type field -- a content type, a cty header, a
nested class name -- the caller's own string selects which parser reads the
remainder. This runs only where the signature is unverified or the token
unsigned; a verified signature inherits the refusal below and the verdict is
inconclusive. The baseline is the token with its normal hint, or none, sent
twice. The variant names a second document type and carries an inert payload of
that type, everything else identical. The control names a type nothing
implements, which separates a parser switch from a generic rejection.
body_differs naming the variant against the baseline closes it, and the control
is read rather than asserted, closing invariant. The second document stays
inert: no external entity, no template delimiter, nothing reaching an engine.
The general form, one document read by two components that disagree, is
`injection.parser_differential`, which browser-script emits, so a wider reading
goes there.

## 5. Whether a merge writes the prototype

This is a lead, it grades nothing, and it does not start without a person.
Pollution is not undoable in process: the write lands on the shared
Object.prototype that every route the same worker serves reads afterwards, and
no client action takes it back. Ask first with `mcp__rk2__park_for_human`, carrying the Task this run is
executing in `task_label` and a `question_code` of destructive_action, naming the
route, the property and the blast radius, and send nothing until the answer comes
back. The preconditions are two facts the recon pass established rather than
guessed: a JSON-accepting route whose handler MERGES the caller's document into
an object, and a JavaScript-shaped stack.

Three oracles, and the first that applies is the only one to run. Where the
route has a usable error path, the baseline is its own deliberately broken
request sent twice and shown byte-stable, the write carries one inert property
the framework itself reads under __proto__, and that broken request is then
re-sent unchanged. Where there is no usable error path but a read endpoint
exists, the write carries a serialisation property the response writer reads, an
indent width or a charset the application already speaks, and the read endpoint
is answered again. Where neither exists but a route echoes its own query
parameters, the write sets the query parser's parameter limit to one and the
identical three-parameter request comes back one parameter short. The value is
always inert and never touches routing, authentication or a template path.

Four controls make this a reading rather than a mood. A sibling route on the
same application that does not merge must still answer the baseline; three chain
steps must have NO effect, because the chain ends at Object.prototype, and an
effect at three means the oracle is not measuring the chain; the value-follows
control returns the property to its baseline, since a change that FOLLOWS the
value is pollution where a one-way change is anything; and a nested object of
the same shape whose Object.prototype is unreachable must do nothing. Keep the
SHALLOWEST step that works. Where the first spelling produced nothing, re-spell
the write through constructor.prototype as nested objects, which asks whether a
sanitiser removed the key name or the capability. The kind is state_change, a
side effect observable on a later request, filed through promote_proposal. Stop
at the first positive, tell the operator at once with the wall-clock instant of
the write so a restart can be correlated, and neither raise the depth nor chain
a second property. This stops at an Observation and reaches no Finding.

## 6. Propose the claim, name the halts, and name what is refused

Propose it with `mcp__rk2__propose_finding`, naming deserialization as its
`vulnerability_class`: that argument takes a vulnerability_classes id and never
a dotted Property class, and injection.object_graph carries no row in
property_class_vulnerability_classes, so the closest standing id is named and
the mapping is owed to ticket 101. It is supported when the type-name arm was
answered differently from a baseline invariant against itself while the one-
string control was not, and refuted when arm and baseline are invariant, which
says the blob was read as data into a shape the route had already chosen.

Two halts are a person's decision. A merge that writes Object.prototype parks
under destructive_action before the first write, for the reason section 5 gives. A
signed or encrypted envelope parks under scope_ambiguous, because the next move
would be key material and whether that question is in scope at all is an
operator's grant rather than a step here. Every other halt is a reading that ran
out, two rounds sent, a format that matched nothing, a route that will not hold
still, and no question code says that, so those go in the Task's own record.

Two things are refused and both are decisions rather than gaps. A blob the route
rejects identically whatever was edited is signed, and the reading records
inconclusive naming the signature; it does not go looking for the key, because a
reading that finds it can no longer tell whether the route trusted the blob after
verifying it or without ever checking. The related ciphertext reading, the intact
token against one flipped byte and against a length that is not a block multiple,
belongs to `information_disclosure.identifier_oracle` and is not folded in here.
Gadget chains, payload generators and proof-by-execution are refused as a class:
the chain proves nothing the type name did not, every generator produces code
execution and nothing smaller, a chain that misses leaves an unknown state, and
a remote-loading chain reaches infrastructure the engagement does not control.
The arrival that would carry it is evidential, so this is a decision and not a
gap. This section grades nothing. 3 of 6 steps cannot be graded.
