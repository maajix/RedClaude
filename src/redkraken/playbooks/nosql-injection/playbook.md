---
description: Ask whether a JSON body's value is passed to a document store as a query fragment rather than as a scalar, by sending the same field once as a string and once as a one-key operator object and differencing the two stored responses.
bb:category: injection
bb:outputs: ["injection.query_operator"]
bb:triggers_all: ["json_request", "state_changing_method", "tech_document_store"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 53 as the v2 replacement for v1's nosql-injection page, against a new query_operator leaf added by ticket 53 because a document store takes its query as a document and the injected thing is a type rather than a string; no upstream card.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_invariant", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "response_invariant", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "response_differential", "polarity": "supports", "min_count": 1}]
---

# Ask whether the value changed type

A document store does not take a query as a string. It takes a document, and the
keys of that document decide what the query means. `{"user": "ada"}` asks for an
equality; `{"user": {"$ne": null}}` asks for everything.

So the injected thing here is not a fragment of a language. It is a type. A
route that reads a JSON body and hands its fields to a driver without checking
that a string is a string has let the caller write an operator where a value was
expected, and no quote, comment or separator is involved anywhere.

The subject is a state-changing endpoint that takes a JSON body on an
Application running a document store. The question is whether one field's type is
checked.

## 1. Name the field and read the body

Read the request's fields from the state view. The interesting ones are the
fields a query filters on: an identifier, a name, an email, a token, a status.
A field that is only ever written -- a comment body, a description -- is a
smaller target because it does not reach a filter.

Name the store the surface fact came from. The operator spelling differs:
`$ne` and `$gt` in MongoDB's dialect, a different vocabulary elsewhere, and an
operator the driver does not know is a field name rather than an operator.

Complete this step with the endpoint, one field, and the store.

## 2. Establish the baseline, twice

Send the request through `mcp__rk2__http_request`, the chosen field carrying an
ordinary string. Then send it again, unchanged. Both go out as whichever Identity
the Task was opened under: the step does not choose it and there is no argument
for it.

Two identical requests, for the reason every reading in this category sends two:
a route whose response carries a timestamp or an id is not byte-stable, and the
projection the later comparison uses has to be fixed before any variant is sent
rather than chosen afterwards to fit the answer.

## 3. Send the two arms

Two more requests, differing in the type of one field.

* The variant carries a one-key object whose key is an operator the store's
  driver understands and whose effect is to widen the match.
* The control carries a one-key object whose key is *not* an operator -- an
  ordinary name the driver will treat as a field -- with the same nesting, the
  same key length and the same value.

The control is what separates the two explanations for a changed response. A
route that returns 400 for any nested object is validating its schema, and it
will return 400 for both arms. A route that returns one thing for the operator
and another for the plain nested key has had the operator interpreted.

This is the whole reason the control here is an object rather than the original
string: comparing an object against a string compares two shapes, and every
serialiser, validator and logger in the path treats them differently.

The repeat policy is three rounds of the pair, six requests, interleaved. A
document store behind a load balancer can answer one replica's view and then
another's, and a widening that shows up once is that rather than an operator. A
differential that does not reproduce in all three rounds is inconclusive.

## 4. Difference the stored bytes

Run `compare-responses` over the operator arm and the nested-key arm, and over
the two baseline requests. Cite what the script returns.

The second comparison is the one that makes the first mean anything: a route
whose two identical requests already differ has no invariant to measure against,
and the arms' difference is then unattributable.

Note separately whether the nested-key arm was rejected outright. A 400 that both
arms share is a schema validator refusing the shape, and neither arm reached a
query.

## 5. Read the widening, not the count

A `$ne` that works usually shows up as a larger result set, a different status,
or a record returned where a lookup should have missed. Report the difference the
script found.

Do not enumerate what came back. If the widened query returned other people's
records, the reading has already proved its point and the records are not
evidence -- they are somebody's data, and this harness stores what it is given.
One differing response is the observation; the contents of the widened set are
not part of it.

## 6. State the claim, and state what would refute it

The Hypothesis is `injection.query_operator` on the endpoint. It is supported
when the operator arm differs from the nested-key arm against a baseline whose
two requests were invariant. It is refuted when the operator arm and the
nested-key arm are invariant against each other -- the route treated both as
data, or rejected both for the same reason.

Inconclusive covers the rest: an unstable baseline, a route that answers 400 to
every nested shape, a route whose query result does not reach the response.

Two neighbours are close.

* Where the value is concatenated into a query language rather than typed into a
  document, the class is `injection.query_language` and the Playbook is
  `sql-injection`. Document stores that accept a string query expression fall
  there, not here.
* Where a JSON field decides which stored field the query filters on, the class
  is `injection.query_field` and the Playbook is `orm`.

Cite the two Artifacts and the difference the script returned.

## 7. One operator, and the least mutating one available

This Playbook is `read_only` and its baseline is a session that stays stable,
which on a state-changing route needs saying carefully.

The endpoint is reached with a method that writes, because that is where JSON
bodies live and where filters are applied to them. What this reading sends is a
request whose operator widens a *read* inside that route -- a lookup, a
uniqueness check, an authorisation filter -- and it does not send an operator
that changes what the route stores. `$ne` on a lookup field is a wider match.
`$set` on an update body is a write, and it is out.

Also out: `$where` and any operator that evaluates code, operator payloads in an
authentication route used to get a session, aggregation stages, and iterating a
widened match to read the collection.

Where the field cannot be widened without also changing what the route writes,
this Playbook does not apply to that field and says so.
