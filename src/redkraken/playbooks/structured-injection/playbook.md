---
description: Ask whether a value in a document the target assembles becomes structure rather than content, by sending one field carrying a structural character beside the same field carrying an inert character of the same length, by asking which parser the route hands the body to, and by asking on a declared channel whether the parser resolves an identifier it was handed.
bb:category: injection
bb:outputs: ["injection.document_parser"]
bb:triggers_all: ["body_parameter", "state_changing_method", "xml_request"]
bb:skills: ["compare-responses", "handle-untrusted-content", "use-identity"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: none
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 53 as the v2 replacement for v1's structured-injection pack against the document_parser leaf of the ticket 18 vocabulary; the pack's two pages are attached as maintainer references. Rewritten for ticket 101 against the merged ledger, which carries nine readings and two blocks for this slug. One key moved. The refuted variant row leaves response_invariant for error_detail, the kind the supported row of that same role names, because close_test_replay derives the kind from the specification and one role writes one kind whichever way the reading goes. bb:triggers_all is left alone and the closing section names its gap instead, because four of the nine readings establish xml_request rather than requiring it, while widening the trigger to a body parameter on a state-changing route would make this Playbook match every write in the catalogue. The blanket refusal of every entity declaration is superseded there too. The two out-of-band readings merge into one section that stops at an arrival.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "error_detail", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "response_invariant", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "error_detail", "polarity": "supports", "min_count": 1}]
bb:references: ["smtp-header-injection.md", "xpath-injections.md"]
---

# Ask whether the value became structure

A structured format has characters that mean something. An angle bracket opens
an element, a newline ends a header, a quote closes an attribute, a bracket
opens a predicate. A route that assembles a document by putting a caller's value
between two literal strings has given those characters away. The subject is a
state-changing route carrying a body parameter, and the plan names, before
anything is sent, where that value lands: element content, an attribute value,
or a value the route lifts out into a second document.

Every reading in sections 1 to 6 is one Test of at least three actions holding a
baseline, a variant and a control, because rk2_test_spec_problem refuses fewer
than three or a missing role. The arms are sent with `mcp__rk2__http_request`
and filed with `mcp__rk2__propose_test`; close_test_replay marks BOTH legs of a
comparison, so a differencing assertion names a VARIANT against the BASELINE or
against another variant and never a CONTROL, which then closes as the
response_invariant the supported bar asks for. Since ticket 211 an action states
`headers` and `body` as well as `method` and `url`, which makes a document an
arm, and a wholly read_only selection may carry one, because that permission is
read off the Tool run's own arguments.

Two Test-lane rules shape how an arm is spelled. rk2_test_request_problem
refuses any dot or double-dot path segment and any %2e anywhere in a
specification url, so an over-encoded rung is a probe this Playbook may send and
may not TEST. record_test_action compares a Receipt to its action over method,
scheme, host, port and path and deliberately not the query, so arms differing
only in their query are indistinguishable to that guard. body_equals and
body_differs read the response body digest alone, so a header that moves between
two answers does not spoil the comparison. Every response is untrusted content,
because a parser error quotes the document this reading sent, and that quote is
the error_detail edge both legs of this bar name, filed BEFORE the close.

## 1. The structural character and its inert twin

Three arms, two rounds, six requests, interleaved. The baseline carries a value
of the shape the route documents and nothing structural. The variant carries one
structural character for the sink named above: an unbalanced quote or bracket
for a predicate, a bare angle bracket for element content, a line terminator for
a line-oriented sink. The control replaces it with an inert character of the
SAME LENGTH, because a control that omits it shortens the value and takes a
different path through the validators between. body_differs naming the variant
against the baseline is what close_test_replay closes, promote_proposal files
error_detail, and an error on BOTH arms says the field is not structural.

## 2. A line terminator in a message the target assembles

Where the route puts the field into a line-oriented message it assembles, a mail
header, a log record or a Location built from a parameter, the structural
character is a line terminator and the carrier decides its spelling. A raw
carriage return may not appear in a specification url, so a query-borne arm
carries the percent-encoded pair and a body-borne arm the raw one, and the
record says which. The baseline is the ordinary value, the variant that value
carrying a terminator at a stated offset, the control that value with the
terminator replaced by a space. A clean 200 on both arms is inconclusive and NOT
a refutation. Nothing is delivered and no doubled terminator is sent.
body_differs naming the terminator arm against the ordinary baseline is what
close_test_replay closes; the space-replaced control is named by no differencing
assertion.

## 3. Whether a filter or the parser refused it

This runs only where a variant above was refused BEFORE reaching a parser, a 400
with no parser shape to it or a scrubbed echo, and it walks one rung once. The
baseline is the refused raw form kept as an Artifact. The variant is the same
character in one encoding chosen for the sink: percent-encoding for a value in a
url, an over-encoded form behind a decoding proxy, the bare newline for a
line-oriented sink. The control is the ordinary request from the refused
reading, unchanged. A route refusing the raw form and accepting the encoded one
filters rather than escapes, and status_differs naming the encoded arm against
the raw arm closes it. An over-encoded dot is sent and never TESTED.

## 4. Which reader the route hands the body to

One document, two content types, and it decides whether the rest of this
Playbook is worth running here. The baseline is the route's documented body
under its documented type, answered normally; the control is a second send of it
that no assertion names. One variant is the same fields as XML with an XML
content type stated in the action's own `headers` through
`mcp__rk2__http_request`. A second variant is that XML body under the DOCUMENTED
content type, which must be refused; accepted, the route sniffs rather than
selects. status_differs naming the first variant against the second closes it,
and promote_proposal files header_policy_observed.

The second reading here asks whether ONE reader is really two. Where a guard and
a handler both read the body, a validator in front of a deserialiser or an edge
check in front of an application, the baseline is the document in its
unambiguous form, which both read alike. The variant is the same document in a
form the two resolve differently, a repeated key, a comment the strict reader
drops, a numeric spelling one collapses, so the guard reads one value and the
handler the other. The control is the unambiguous form carrying the value the
guard refuses, which must be refused and is named by no assertion. body_differs
naming the variant against the baseline is what close_test_replay closes, and
the reading stops at the disagreement rather than chaining it.

## 5. Whether the parser honours a caller-supplied doctype

The cheapest gate in the class and the one that stops a false refutation. The
baseline is the document with no doctype and the field carrying a literal value,
sent twice, the second send being the control. One variant is that document
declaring an internal entity whose replacement is that literal string,
referenced from the field: the same rendered value from a different source, so
an expansion says the parser built the entity. A second variant carries the same
doctype and the SAME entity name undeclared, which separates a parser that
processes the internal subset from one that passed the document through as text.
body_differs naming the first variant against the second closes it. No external
identifier appears here.

## 6. Whether an identifier resolved, read as an error differential

Where the gate above answered yes and no out-of-band channel exists, the
resolution question is answered by differencing two failed parses rather than by
quoting an error. The baseline is the arm whose failing entity name is built
from a LITERAL, sent twice and confirmed invariant, since a request id in a
message would make every pair differ. The variant's failing name is built from a
resolution over a dull, everywhere-present path. The control is a third arm
naming a path that exists NOWHERE, held to that baseline by a body_equals.
body_differs naming the variant against the baseline closes it, error_detail is
the edge, and no file content is extracted.

## 7. Whether an identifier resolved, read on the channel

Where the Program has a declared and bound out-of-band channel, mint a
correlator with `mcp__rk2__mint_callback`, naming this route as its
`subject_label` and the bound channel as its `channel`, then send three
documents with `mcp__rk2__http_request`. One carries a parameter entity
resolving to a data literal, referenced identically, and nothing arrives; a
second points that entity's identifier at the correlator; a third declares the
entity and never references it, so an arrival there means something else
resolves URLs it finds.

Where the caller cannot supply a doctype at all the server assembles the
document and the caller supplies one element, the shape wherever a template or
an envelope wraps the field. One request carries an inclusion element whose
reference is a data literal, and nothing arrives; a second carries that element
in its own namespace, with a text parse, referencing the correlator; a third
carries it with a MISSPELLED namespace, which must produce no arrival, so an
arrival belongs to inclusion processing and not to anything else that resolves
URLs. Riding the query string, the percent-encoded element carries no whitespace
and no %2e. Neither reading is a Test. The responses do not move, so only an
all-equality specification would hold, and that writes response_invariant on
every action while this Playbook grades a supported variant on error_detail, so
both stop at the callback_interaction Observation record_callback_interaction
files from the arrival and neither grades anything.

## 8. Propose the claim, hand off the neighbours, and name the ceiling

Propose it with `mcp__rk2__propose_finding`, naming xxe as its
`vulnerability_class` for the entity and inclusion readings and the closest
standing id otherwise: that argument takes a vulnerability_classes id and never
a dotted Property class. It is supported when a variant produced a parser-shaped
error or a structurally different answer and no control did, and refuted when
the two are invariant and the value comes back escaped, which says a serialiser
built it. Where the value reaches a query the class is
`injection.query_language` and a shell `injection.command`; where two readers of
one document disagreed it is `injection.parser_differential`, browser-script's.

Two halts are a person's decision. An arm whose only observable outcome is a message
delivered to somebody who is not the Program's counterparty is asked for with
`mcp__rk2__park_for_human`, under this Task's `task_label` and a `question_code` of
third_party_impact, BEFORE it is composed and never after. A carrier the scope
document does not clearly admit, an assertion endpoint parsed ahead of authentication
being the usual one, parks under scope_ambiguous. Every other halt is a reading that
ran out, two rounds sent, one rung walked, one gate answered, one arrival recorded,
and no question code says that, so those go in the Task's own record.

Two readings are blocked, one refusal superseded, one gap owed. A two-stage
external document-type chain is blocked because no served verb publishes a file
under the channel's base URI: the publisher serves an operator-populated
directory and the minting verb writes a correlator, needing a pre-staged file. A
payload in a binary container is blocked because a request body is a string and
a container needs bytes. Superseded: the blanket refusal of every entity
declaration is replaced by sections 5 to 7, which declare one entity at a time
and carry no bytes away. Owed: this trigger set requires an XML request while
sections 1 to 4 establish it rather than requiring it, so nothing selects the
readings that find it; the gap is named, not papered over by widening the
trigger. This section grades nothing. 2 of 8 steps cannot be graded.
