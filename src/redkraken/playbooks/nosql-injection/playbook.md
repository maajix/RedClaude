---
description: Ask whether a value reaches a document store as a query fragment rather than as a scalar, by sending the same field once as a string, once as a one-key operator object and once as a one-key object whose key is not an operator, and differencing the last two.
bb:category: injection
bb:outputs: ["injection.query_operator"]
bb:triggers_all: ["tech_document_store"]
bb:triggers_any: ["body_parameter", "query_parameter"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 53 as the v2 replacement for v1's nosql-injection page, against a new query_operator leaf added by ticket 53 because the injected thing here is a type rather than a string; no upstream card. Rewritten for ticket 101 against the merged ledger, which carries three procedures and one refusal for this slug. Two keys moved. bb:triggers_all narrows to tech_document_store and bb:triggers_any takes body_parameter and query_parameter, because the shipped set demanded json_request and state_changing_method together and so selected for exactly one of the three readings -- the parser-built and regex-anchor readings both ride a query string on a read, and a trigger set that never fires for them hides two thirds of the Playbook. The refuted variant leg moves from response_invariant to response_differential, the kind the supported leg of the same role names, because close_test_replay derives a kind from the specification and one role writes one kind whichever way the reading comes out.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_differential", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "response_invariant", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "response_differential", "polarity": "supports", "min_count": 1}]
---

# Ask whether the value changed type

A document store does not take a query as a string. It takes a document, and the keys of
that document decide what the query means. One shape asks for an equality; a one-key object
in the same position asks for everything. So the injected thing here is not a metacharacter
and it is not a quote -- it is a TYPE, and the question is whether a value the caller sent
arrived as a scalar or as a fragment of the query itself.

That makes this class about the shape of the value rather than about the backend behind it.
A relational mapper whose filter clause accepts an untyped object is the same reading with
the same control; the trigger set gates on a document store because the operator spellings
are the store's own, and an ORM-backed subject reaches the same sink through orm's
identifier reading instead.

Every reading below is one Test of at least three actions holding a baseline, a variant and
a control, because rk2_test_spec_problem refuses a specification performing fewer than three
or leaving a role out. The arms go out with `mcp__rk2__http_request`, are filed as one
specification with `mcp__rk2__propose_test`, and close_test_replay closes them. Since ticket
211 an action states headers and body as well as method and url, so a JSON document rides
the action itself: a body is framing rather than an effect, and this Playbook stays
read_only while sending one.

## 1. Name the store, the field and the spelling

Name the store first. The operator spelling is dialect-specific, and an operator the driver
does not know is a field name rather than an operator, which makes an unnamed store a
reading that cannot tell a refusal from a miss.

Then name the field. It must be one a query FILTERS on -- an identifier, a name, an email, a
status -- and not one that is only written. A field the handler stores and never matches on
has no query to be injected into.

Then name the spelling the route offers, because the three readings below sit on different
ones: a JSON body field, a query-string parameter an extended parser expands, and a
query-string filter carrying a regex operator. This section names and grades nothing.

## 2. The object where a scalar was expected

One Test. The baseline is the request with the chosen field carrying an ordinary string,
and the projection the later comparison reads is fixed HERE rather than chosen afterwards
to fit the answer. That same send goes out once more as a second action, this one carrying
role control; body_equals pairs the two and no differing assertion names either, which is
what leaves a response_invariant in the control role.

The variant carries that one field as a one-key object whose key is an operator the driver
understands and whose effect is to WIDEN a match -- a not-equal, a greater-than, an
inclusion, on a lookup field. Never a set, never a server-side evaluation, never an
aggregation stage.

The control carries that one field as a one-key object whose key is NOT an operator: an
ordinary name the driver treats as a field, same nesting, same key length, same value. That
is the whole design. A route that returns 400 for any nested object is validating its schema
and returns 400 for both arms; a route answering one way for the operator and another way for
the plain nested key has interpreted the operator. Comparing an object against the original
STRING would compare two shapes, and every serialiser, validator and logger in the path
treats those differently. body_differs naming the operator arm against the nested-key arm is
what close_test_replay closes.

The array-wrapping spelling folds in here as a further variant -- an identifier field sent
as a one-element array where a scalar was expected -- and it needs no dialect knowledge at
all, which makes it the right first probe on a store nobody has named confidently.

Three rounds of the pair, six requests, interleaved: a widening that shows up once is a
replica, not an operator. Where a widened response returns records belonging to principals
other than this run's own, stop at that arm, record the record COUNT and the difference, and
never the records themselves.

## 3. The object the parser built

The caller need not write the object at all. An extended query-string parser -- the default
in more than one common framework -- expands a bracketed parameter name into a nested object
before the handler ever sees it, so the caller writes ASCII into a request target and the
framework writes the operator.

One Test, on a route that is NOT an authentication route. The baseline is the route with
the field as a plain scalar carrying a value that must not match -- a wrong token on a
reset-token route is the sharpest instance -- and its unchanged repeat is a second action
carrying role control, so the body_equals over that pair is where this reading's
control-role response_invariant comes from. The variant is the same request with the field
spelled in the parser's bracket syntax so it arrives as an object, carrying the same wrong
value: a valid answer where an equality could never have matched means the parser built an
operator object and nothing type-checked it. The control is the same bracket syntax on a
field name the handler does not use, which must return the invalid answer, and it rules
out both boring explanations at once -- that any bracketed parameter is accepted, and that
the parser rejects brackets outright. body_differs naming the bracket arm against the
wrong-field arm is what close_test_replay closes.

One spelling constraint the replay lane adds, and it is about the url rather than the
payload: brackets ride fine, but a specification url may carry no dot or double-dot path
segment and no percent-encoded dot anywhere, so the bracket parameter goes in the query and
the path stays plain.

This reading is also partly injection.parser_differential -- the parser and the handler
disagree about what arrived -- and browser-script emits that class since ticket 101. Where
the disagreement rather than the widening is the finding, hand the verdict there.

## 4. The two anchors, and one bit

A per-guess boolean is only worth reading where it is observable at all, and that is what
the anchors establish before any character is guessed.

One Test, on the injectable filter section 3 established, on a route that is not an
authentication route. The baseline is the must-be-TRUE rung, the filter field carrying a
regex operator whose pattern matches everything; that rung is sent a second time unchanged
as an action carrying role control, and the body_equals over the two is the control role's
response_invariant. The variant is one rung, the same operator with a pattern anchored on
a single guessed leading character; its answer equalling the true anchor is a true bit and
equalling the false anchor is a false bit. The control is the must-be-FALSE rung, the same
operator with a pattern that cannot match, built from a character the value cannot
contain. body_differs naming the guess rung against the false anchor is what
close_test_replay closes.

**That anchor pair is the whole reading and it is what every payload list omits.** Where the
true anchor and the false anchor answer identically there is no observable boolean, the
ladder is not there, and the reading is refuted rather than inconclusive. Without a
forced-false rung every "false" reading is indistinguishable from a broken request.

The anchors and ONE true bit, and the reading stops. The ladder is not run to completion and
is never run against credential material at all: run to completion it becomes
information_disclosure.identifier_oracle, which is another Playbook's class, and that is a
second reason the anchors rather than the ladder are what this section keeps. The same
anchor pair carries over verbatim to the boolean ladders in other query languages, which is
why the vocabulary is written once here.

## 5. State the claim, and name the payload this Playbook refuses

The Hypothesis is injection.query_operator on the field, proposed with
`mcp__rk2__propose_finding` naming sqli as the class -- that argument takes a
vulnerability_classes id and not a dotted Property class, and
property_class_vulnerability_classes carries no row for this Playbook's own class, so the
choice is recorded here rather than derived and finding_class_divergence stays silent for an
unmapped class. It is supported when the operator arm differs from the plain nested-key arm,
or the bracket arm from the wrong-field arm, against a repeated pair that was invariant. It
is refuted when the two arms are answered alike -- the route treated both as data, or
rejected both for the same reason -- and when the two anchors cannot be told apart.
Inconclusive covers an unstable baseline and a route returning one generic error for
everything.

Two neighbours are close. Where the value is concatenated into a statement's text, the class
is injection.query_language and the Playbook is sql-injection. Where the value names a
column or a relation rather than an operator, the class is injection.query_field and the
Playbook is orm.

One payload is refused, and it is the most-cited one in every source this corpus reads: a
widening operator in a credential field on an authentication route, sent in order to obtain
a session. The refusal travels with its reason so it is not re-proposed by the next reader
of the next source. A session obtained that way is a session the run holds without having
authenticated for it, which this Playbook's read_only effects and stable_session baseline
both forbid; and a second, weaker obstacle would remain even if that decision moved, because
the proof those sources cite is the response's own session-setting header, and that header
is stripped from the agent view on every path. The redirect is to a non-authentication
filter field on the same application, which is section 2.

This Playbook reads. It sends no set, no server-side evaluation and no aggregation stage; it
does not enumerate what a widened match returned, does not iterate the widened match, and
does not walk an operator table. Every halt above is a reading that ran out -- one accepted
operator, one flipped boundary, one true bit -- and no question code says that, so each is
reported through the Task's own record. Where an accepted bracket arm returns a state that
would let the run act as another principal, the operator is told immediately, the flow is not
completed, and the matched value is not used.

This section proposes and grades nothing. 2 of 5 steps cannot be graded.
