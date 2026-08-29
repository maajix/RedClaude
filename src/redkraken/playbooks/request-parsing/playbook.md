---
description: Ask whether two components that both act on one request resolve one name, one grammar or one encoding the same way, by duplicating the name, re-declaring the representation, re-spelling the value or moving it into a carrier the method does not have, and closing each reading on a Test whose control is the same shape applied where it must not work.
bb:category: injection
bb:outputs: ["injection.parameter_precedence"]
bb:triggers_all: ["repeated_parameter_name", "state_changing_method", "web_surface"]
bb:skills: ["compare-responses", "enumerate-surface", "use-identity"]
bb:risk: constrained
bb:effects: mutates_object
bb:baseline: pristine_surface
bb:status: draft
bb:stale_after: 2027-05-15
bb:provenance: Written for ticket 56 as the v2 replacement for v1's request-parsing pack against a new parameter_precedence leaf added by ticket 56; the pack's four pages are attached as maintainer references, and its response-splitting payloads, its host-header rewrites and its filter-evasion catalogue are refused by the closing section. Rewritten for ticket 101 against the merged ledger, which carries eleven readings that settle a claim and five refusals for this slug. Two keys moved. bb:skills gains enumerate-surface, which the route-suffix reading of section 4 needs, and use-identity, which the readings against an authenticated route need; both are already held by the role that executes this text. The refuted variant row moves from response_invariant to response_differential, the kind the supported row of that same role names, because close_test_replay derives the kind from the specification and one role writes one kind whichever way the reading goes.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_differential", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "response_invariant", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "response_differential", "polarity": "supports", "min_count": 1}]
bb:references: ["http-attacks-crlf-injection-and-response-splitting.md", "http-attacks-host-header.md", "parameter-pollution.md", "waf-bypasses.md"]
---

# Ask whether the thing that checked and the thing that acted read the same value

One request arrives and two components read it. Where the two resolve one name, one
grammar or one encoding differently, the check passes on one reading and the work is
done from another. The request was ambiguous, and it was resolved twice.

Every reading is one Test of at least three actions holding a baseline, a variant and
a control, because rk2_test_spec_problem refuses a specification performing fewer
than three or leaving a role out. The arms are sent with `mcp__rk2__http_request`,
which states a `method`, a `url`, and since ticket 211 `headers` and a `body`, and
are filed with `mcp__rk2__propose_test`, the only verb that makes a Test exist.
close_test_replay closes it and derives the Observation kind from the specification,
and every Test leaves at least one control named by no differencing assertion,
because close_test_replay writes response_differential for both legs of one and the
supported control row asks that role for the invariant. One control recurs -- the
baseline sent twice, because a route not stable across that pair cannot be
differenced.

## 1. One name in two places, and which occurrence each component kept

Both occurrences ride the query string, stated inside one `url` through
`mcp__rk2__http_request`. record_test_action compares method, scheme, host, port and
path, so a duplicated key is expressible with nothing else moved. The baseline is the
route's own request with the name once, recorded with its status, the value it says
it accepted and the shape of what it produced; an answer carrying neither of the last
two stops as inconclusive. The name goes in a second time carrying a value the
application would refuse if it were the only one there. That pair with the
occurrences swapped, because first-wins and last-wins are different defects with
different fixes. Then the name three times, each occurrence carrying a distinct value
the application does list, in one order and reordered -- an echo that moves with the
order is concatenation, one that does not is precedence.

The controls are the same name duplicated with both occurrences legitimate, which
must be accepted, and the baseline pair, which carries role control here as
everywhere else. A 400 on the first says duplicated names are refused everywhere and
the arms proved nothing. status_differs or body_differs naming an accepted arm
against the baseline is what close_test_replay closes; no differencing assertion
names either control, which leaves them the response_invariant the bar asks for. Name
which carrier held which occurrence, because which one won decides the fix. An
ordering pair aimed at a real value transfer is not sent -- prove it on a read step,
or park under destructive_action.

## 2. A second carrier, and a second parser behind one route

Two readings, both moving something a Test action states only since ticket 211, on a
Task whose Identity may call the route. The first asks whether the second carrier
exists. The baseline is the route requested with the name in the query only and no
body; the variant is the identical request with a `body` carrying that name and a
second value; the controls are the same body under the route's own write method,
which shows a body parser exists, and the baseline pair. An answer that moves under
the read method is a body parser running under a method nothing in front of it read.
That a body is unkeyed almost everywhere is `information_disclosure.cached_response`
under `web-cache`.

The second asks which parser ran. The baseline is the documented representation, and
its repeat carries role control. The variants re-declare the same semantic fields one
representation at a time in the `headers` and the `body`, then omit the declaration.
The second control is the alternate representation carrying a document invalid for
it, which must answer a parse error -- that is what says the alternate parser ran
rather than the body being ignored. status_differs naming an accepted alternate
against that invalid control is what close_test_replay closes, and the repeated
baseline, named by no differencing assertion, writes the response_invariant the bar
asks for. Each refusal's wording is an error_detail edge filed by promote_proposal.
Where every arm answers 415 the rest are not sent, and that halt is a reading that
ran out.

## 3. The operation name, one layer above the parameter

A dispatcher reading an operation name from somewhere other than the body it executes
-- a dispatch header, a method-override field -- is the same shape one layer up, and
every spelling is expressible. The baseline names one permitted operation in both
carriers. The variant names that operation in the header and a different one in the
body. Two controls are needed: both carriers naming the restricted operation, which
must be refused if the dispatcher checks anything at all; and the override set to a
verb that does not exist, which must answer differently from a plain request, since
answered identically the override is ignored and the variant means nothing. The
override spelling rides the query, so `POST /x?_method=DELETE` against a plain
request is a request-line differential, while the dispatch-header and body-element
spellings ride the `headers` and the `body`. An arm aimed at a verb a front end
blocks measures the edge, which is `authorization.edge_rule`. status_differs or
body_differs naming the split arm against the baseline is what close_test_replay
closes; no differencing assertion names either control.

## 4. Two grammars over one request URI

Where a filter runs on the raw request URI before the router reads it, the segment
the filter matched is not the segment the router routed on. The baseline is the
refused route requested unmodified, twice. The variant appends a matrix-parameter
suffix to the last segment -- `/route;.wadl` is the shape -- so the router discards
what the filter matched on. The controls are the baseline pair and the same suffix on
a route that certainly does not exist, which must answer 404. The suffix holds a dot
and never a dot segment, so no %2e appears in the url and rk2_test_request_problem's
segment rule does not match, keeping all three arms storable.

The same question is cheaper on the query string, where the baseline is two ordinary
parameters separated by an ampersand; the variant separates them with a semicolon
inside what an ampersand-only splitter reads as one value; the controls are the
baseline pair and the same url with the separator and the equals sign
percent-encoded, which must stay on the baseline answer; if the encoded form flips
too the application is doing generic last-wins decoding and nothing was proved about
a delimiter. One raw form and its encoded twin, then stop. The verdict on both is
`injection.parser_differential`, which `browser-script` emits and is handed there.
body_differs names the semicolon arm against the ampersand baseline; the baseline
pair and the percent-encoded twin are named by no differencing assertion.

## 5. The bytes the guard read, and the declaration the parser built

Two readings of one question. The baseline is the plain spelling of a value the
deployment demonstrably refuses, sent twice, the two refusals matching. The first
variant re-spells that declaration so the guard's reading of the bytes and the
parser's reading of them diverge -- a value inside a comment the consumer strips, a
single-pass strip defeated by a doubled sequence, a full-match-anchored pattern fed a
value that merely contains the character. Those spellings ride the `body` the action
states rather than the `url`, clear of rk2_test_request_problem's refusal of any dot
segment or %2e in a specification url.

The second variant sends the transform source of a filtered ASCII character --
`%EF%BC%8F`, `%C2%A5`, `%EF%BC%82` -- so a component transcoding between the check
and the sink produces the character the check never saw. None holds %2e and all three
are storable in a `url`. The egress header value pattern is printable ASCII, so the
non-ASCII half rides percent-encoded in the query or raw in the body, never in a
header of this run's own. The control for both readings is an inert re-spelling of
the same encoding, length and character classes, declaring nothing, which must answer
as the baseline refusal did. Accepted as well, the guard is reacting to the shape and
not to the declaration, and that halt is a reading that ran out. status_differs or
body_differs names whichever transform arm was accepted against the baseline; the
inert re-spelling is named by no differencing assertion.

## 6. The value that becomes structure in the request the front end builds

Where a route proxies a value into a second request it builds, a percent-encoded
structural character is structure to the inner parser and data to the outer one. The
baseline is the route with an ordinary value returning a known, narrow result. The
variant appends a percent-encoded separator so the inner query gains a parameter,
then a percent-encoded fragment marker so it is truncated, one spelling per action.
Three controls follow, and the first decides it. A value that is simply wrong must
produce the not-found answer, so a truncation arm answering as the plain value did
while the wrong value does not is a fragment marker cutting an inner query string.
Then the same arm double-encoded, which must read as a literal miss, or the front end
decodes twice. Then the baseline pair. status_differs naming the injected arm against
the wrong-value control, with body_equals naming that same arm against the baseline,
is what close_test_replay closes; an equality names nothing differentially, so the
double-encoded control and the baseline pair write the response_invariant the bar
asks for. Structural characters and nothing else -- not a quote, not a bracket, not a
template delimiter. Whether the inner service is itself a subject parks under
scope_ambiguous.

## 7. Propose the claim, and name what this Playbook will not do

The Hypothesis is `injection.parameter_precedence` on the subject, proposed through
`mcp__rk2__propose_finding`. Its `vulnerability_class` takes a vulnerability_classes
id and never a dotted Property class, which the served schema refuses;
property_class_vulnerability_classes holds no row for this leaf, so name the closest
standing id. It is supported when an arm was accepted, the answer names one value and
the thing it produced was built from the other, and the control shows the deployment
does not refuse the shape as such. It is refuted when the arm is answered as the
baseline is, and inconclusive otherwise.

Two halts are a person's decision, asked for with `mcp__rk2__park_for_human` under
the executing Task's own `task_label` and the `question_code` that names why -- an
ordering pair against a real value transfer under destructive_action, and an inner
service that may not be a subject under scope_ambiguous. Every other halt is a
reading that ran out, which no question code says, so those go through the Task's own
record.

Five readings are refused rather than absent. A carriage return and line feed in a
header this run writes is unrepresentable, because the egress name and value patterns
admit no control byte; in a parameter value it is refused by decision, because a
split response puts a header of this reading's choosing in front of another document.
A verb outside the seven the egress enum admits cannot be composed, and
rk2_test_request_problem refuses the same seven, so section 3's override is the only
substitute. Rewriting the authority is refused in both halves -- Host never leaves
the door, and the forwarded-authority family does forward, so that half is a decision
and not a missing capability; a Location already returned is read into the Task note.
The same header name twice is not expressible -- the egress headers argument is an
object and one name carries one value. Re-spelling a value until a front end stops
refusing it is refused, because a defeated filter is not a defect found.

This section runs no Test and grades nothing. 1 of 7 steps cannot be graded.
