---
description: Ask whether a serialised parameter lets the caller choose which type the route reconstructs, by sending one request as two arms whose blobs differ only in the type name they carry and differencing the two stored responses against a baseline that was itself invariant.
bb:category: injection
bb:outputs: ["injection.object_graph"]
bb:triggers_all: ["authenticated_endpoint", "serialized_object_parameter", "state_changing_method"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-04-15
bb:provenance: Written for ticket 54 as the v2 replacement for v1's deserialization pack against a new object_graph leaf added by ticket 54; the pack's gadget page is attached as a maintainer reference and every chain, every payload generator and every proof-by-execution in it is refused by step 6.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_invariant", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "response_invariant", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "response_differential", "polarity": "supports", "min_count": 1}]
bb:references: ["deserialization-attacks.md"]
---

# Ask who chose the type

A serialised blob carries two things: state, and a name for what the state is.
Every question worth asking about deserialisation is the second one. If the
route decides what it is reconstructing, the blob is data. If the blob decides,
the reachable set of types is the process's, and the caller picked from it.

The subject is an authenticated state-changing endpoint carrying a parameter a
recon pass typed as serialised. The question is whether the type name in that
parameter reaches a constructor, and the whole reading is five requests.

## 1. Name the parameter and read the format

Read the parameter from the state view rather than picking one out of the
request. A route may carry a session cookie, a CSRF token and a saved-state blob,
and only the last of those is deserialised.

Then say what the format is, from the first bytes of a blob the client itself
produced:

* `AC ED 00 05` or the base64 `rO0` -- Java serialisation
* `80 04 95` or a leading `(dp0` -- Python pickle
* a leading `O:` or `a:` inside a `s:`-counted string -- PHP `serialize`
* `{"$type":` or `{"@class":` or `__type` -- a .NET or Jackson document with
  polymorphic type handling switched on
* a leading `<?xml` with `<object class=` or `java.beans.XMLDecoder` -- XML
  object graphs
* anything bespoke, in which case say where the type name sits in it

The format is not decoration. It decides where the type name is, and a reading
that edits the wrong field is comparing two blobs that differ in state.

Then declare the ceiling, before the first arm is composed, because everything
after this step sends a blob the client did not produce:

* **mutation** -- this reading writes what an ordinary client write writes and
  nothing else. If the route stores what it deserialises, say so here and say
  what the stored row is.
* **cleanup** -- whatever the writes above create is removed by the route the
  target itself offers, and if there is no such route, say that here too.
* **execution** -- nothing sent constructs a type with a side effect. The arms
  name a type that does not exist and a type the route already accepts, and
  neither loads a class, reaches an engine, opens a connection or runs anything.

If the ceiling cannot be met -- if the only way to see a difference is to store
something the client cannot delete -- stop here, record `inconclusive`, and route
to an operator. Step 7 restates all three at the end.

Complete this step with the endpoint, the one parameter, the format and the
ceiling.

## 2. Establish the baseline, twice

Send the request under the leased Identity through `mcp__rk2__http_request` with
`identity_slot` set, carrying a blob the client itself produced, unedited. Then
send it again, unchanged.

Two identical requests, because everything after this is a comparison and the
comparison has to know what "the same response" looks like here. A route that
returns a fresh token, a timestamp or a rotating panel is not byte-stable, and a
differential measured against a baseline nobody checked is noise with a verdict
attached.

If the two differ, run `compare-responses` over them and record what moved. The
remaining steps compare only the parts that held still. If nothing holds still,
this Playbook cannot read the route and says so.

## 3. Send the two arms

Two more requests. Both carry the same state, re-encoded in the same format, and
differ only in the type name:

* the variant names a type the client never sends, chosen from the runtime's own
  standard library and chosen for being inert -- a container, a collection, a
  primitive wrapper, a date
* the control names the type the client's own blob named, re-encoded by the same
  code path

The control is a control in the strongest sense available here: it went through
the same encoder, carries the same fields and differs in one string. A control
that sends the untouched original blob differs from the variant in the encoding
as well as in the name, and the comparison then has two variables.

Inert is a requirement, not a preference. The type named in the variant must have
no constructor, no `readObject`, no `__setstate__`, no property setter and no
finaliser that touches a file, a process, a socket or a class loader. Naming a
type that runs something proves nothing this reading needs and is the step that
turns a question into an incident.

Interleave the arms with the baseline rather than sending them as a block, and
hold everything else constant: same Identity, same headers, same field order, one
string moving.

The repeat policy is two rounds of the pair, four requests, interleaved. A
difference that appears once and not again is a route that varies, not a type
that was constructed.

## 4. Difference the stored bytes

Run `compare-responses` over the variant arm and the control arm, then over the
control arm and the baseline. Cite what the script returns, not a description of
it.

Two comparisons answering different questions. Variant against control is the
differential: two blobs identical but for a type name, two different answers, and
something read the name. Control against baseline says the re-encoding was
faithful -- if those differ, the encoder moved something and the first comparison
has a second variable in it after all.

What a positive looks like varies by runtime and all of it counts: a field that
only the named type has, a different shape of document, a different status, a
different length, an answer that names what it restored. What does not count is a
difference in an error message, which is the next step.

## 5. Rule out the parser

A route that answers differently for an unfamiliar type name may be reporting
that its own schema check failed. Send one more request whose blob names a type
that does not exist in any runtime -- a string of the right shape and no meaning.

If that response matches the variant arm, the route is answering the shape of the
name rather than constructing anything, and what was measured is a validator.
That is a finding about a validator and it is not this Hypothesis.

If the response instead matches the control, or matches neither, the variant's
difference survives: a name that resolves to nothing behaved like an ordinary
rejection while a name that resolves to a real type did not.

One request, and it is the difference between a report a triager accepts and a
schema error with a verdict attached.

## 6. State the claim, and state what would refute it

The Hypothesis is `injection.object_graph` on the endpoint. It is supported when
the variant and control arms differ in both rounds, the two baseline requests
were invariant against each other, and the nonexistent-type probe did not
reproduce the variant. It is refuted when the two arms are invariant against each
other against a baseline that was itself stable -- the blob was read as data into
a shape the route had already chosen.

Anything else is inconclusive, and inconclusive is the honest verdict for an
unstable baseline, for a route that rejects every edited blob because the blob is
signed, and for a route whose answer does not depend on what it restored.

Two neighbours are close.

* Where the input arrives as a field name or a relation the query filters on
  rather than as a type to construct, the class is `injection.query_field` and
  the Playbook is `orm`.
* Where the input arrives as an operator inside a document store's query document,
  the class is `injection.query_operator` and the Playbook is `nosql-injection`.

Cite the two Artifacts and the difference the script returned.

## 7. The ceiling, restated at the end

This Playbook is `read_only` and its baseline is a session that stays stable. It
sends five requests, all of them to the one endpoint the Task names, and it
changes one string in each.

It does not construct a type with a side effect, build a gadget chain, use a
payload generator, name a type that loads a class, reach a template engine, open
an outbound connection, sleep the process, write a file, or run a command. The
attached reference covers exactly those techniques and says for each one why it
is out: they prove the same property this reading already proved, and they prove
it by doing the thing the report would ask the target to fix.

Nothing here is cleaned up afterwards because nothing here is created. A route
whose deserialisation writes -- a saved cart, a stored preference, an audit row
-- is still in scope for this reading, and the ceiling is that the reading writes
what an ordinary client write writes and nothing else. If the only way to see the
difference is to store something the client cannot delete, the verdict is
`inconclusive` and it routes to an operator.
