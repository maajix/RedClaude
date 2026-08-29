---
description: Ask which column, relation or comparison the caller chose, by sending one query parameter as a name the interface offers, as a real name it never offered, and as a fictional name of the same shape, and reading which pair the query builder tells apart.
bb:category: injection
bb:outputs: ["injection.query_field"]
bb:triggers_all: ["authenticated_endpoint", "query_parameter", "tech_orm"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 53 as the v2 replacement for v1's orm page, against a new query_field leaf added by ticket 53 because an ORM injection changes which column the query names rather than what the query says; no upstream card. Rewritten for ticket 101 against the merged ledger, which carries four procedures and one refusal for this slug, and every procedure closes a Test because the whole differential is one parameter value in the request line. One key moved. The refuted variant leg moves from response_invariant to response_differential, the kind the supported leg of the same role names, because close_test_replay derives a kind from the specification rather than from the outcome, so one role writes one kind whichever way the reading comes out and a refuted leg naming a second kind is a leg nothing can ever write. The control role keeps response_invariant, which the unchanged repeat produces where sections 2 and 3 now plan that repeat as a control action rather than as a second baseline send.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_differential", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "response_invariant", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "response_differential", "polarity": "supports", "min_count": 1}]
---

# Ask which column the caller chose

An ORM was supposed to end this class. It parameterises values, so the quote that breaks a
hand-built statement does nothing, and a reading that only knows how to send quotes will
report every ORM-backed route as clean.

The defect moved rather than disappearing. The parts of a query an ORM cannot parameterise
are the parts that name things: which column to sort by, which column to filter on, which
relation to join, which fields to return. Those arrive as identifiers, and a route that
builds them out of a query parameter has let the caller choose them.

Every reading below is one Test of at least three actions holding a baseline, a variant and
a control, because rk2_test_spec_problem refuses a specification performing fewer than three
or leaving a role out. The arms go out with `mcp__rk2__http_request`, are filed as one
specification with `mcp__rk2__propose_test`, and close_test_replay closes them. Each one
turns on the same control and it is the control that makes the reading a reading: a real
name the caller was never offered, differenced against a fictional name of the same shape.
An ORM that resolves names at run time answers the real one and raises on the other; an
allow-list answers identically for both, because neither is on the list. No error message is
required for that comparison, and where one arrives quoting a field name it is filed as an
error_detail edge through `mcp__rk2__submit_mission_result`, which promote_proposal writes.

## 1. Name the parameter and what it looks like it selects

Read the parameter from the state view, and prefer the ones carrying identifiers rather than
values: sort, order, order_by, fields, filter, include, expand, embed, and the
framework-shaped compounds -- a filter key holding a double underscore, a dot or a bracket
is a relation traversal spelled in the framework's own syntax.

Name the framework the surface fact came from. The traversal separator is framework-specific
-- a double underscore in one, dots in another, slashes or brackets in a third -- and a
probe written in the wrong one is a probe for a field literally named user.email.

Complete this section with the endpoint, one parameter and the framework. It reads and names
and grades nothing.

## 2. The relation path the interface never offered

One Test. The baseline is the endpoint with the parameter carrying a value the interface
itself offers -- a column the page's own filter control uses -- repeated unchanged as a
second action carrying role control. The offered value is what establishes that the
parameter WORKS, which the refutation needs: a parameter ignored entirely produces the same
invariance as one that is validated, and those are different findings. No differing
assertion names either send, which is what leaves a response_invariant in the control role.

The variant is the parameter naming a relation path the interface never offered, ending on a
column the response does not show, with a string lookup suffix in the framework's syntax --
a created-by path into a user table, ending on a credential column, prefixed with one
character. A non-empty list where a wrong prefix returned an empty one is the widening. The
control is a name of the SAME length and shape, composed the same way, ending on a field
that cannot exist; it must error or return the list unfiltered. body_differs naming the real
path against the fictional one is what close_test_replay closes.

The repeat policy is three rounds of the pair, six requests, interleaved. The signal is
which rows came back, and a list endpoint's contents move for reasons that have nothing to
do with the caller -- another tenant writing, a cache filling, a page boundary shifting. A
difference that does not reproduce in all three rounds is inconclusive.

Where the traversal lands, the response may now be ordered or filtered by a column from a
related table, and that is where the reading stops. One character position is proof; walking
the rest of a hash is exfiltration wearing an ORM's syntax. Record the difference and the
one position, never a recovered value, and tell the operator where the column reached is
credential material.

## 3. The column in the sort position

A sort or order parameter that is not an enum reaches the identifier position of the
statement, and backticks around the value are a common false comfort that do not close it.

One Test, on the query-string spelling of the parameter, which is where a sort control puts
it. The baseline is a real column the interface's own sort control offers, repeated
unchanged as a control action, the response_invariant no differing assertion names; the rows
come back in that order and the pair must be invariant, because a list whose page boundary
moves has no invariant and this reading's whole signal is row ORDER. The variant is a real
column on the same table that the response does NOT show, which resolves and changes the
order. The control is a column of the same length and shape that certainly does not exist,
which must error or leave the order unchanged -- and where the control is indistinguishable
from the baseline the parameter is not reaching the query at all and neither arm means
anything. body_differs naming the hidden-column arm against the fictional-column arm is what
close_test_replay closes. Three rounds of the pair, interleaved.

An EXPRESSION is not sent here. A conditional, a subquery or a comma-separated fragment in
the sort value has crossed into injection.query_language, which belongs to sql-injection
with its own ceiling and its own approval; the reading stops before that arm and records
that no expression was sent. The filter reading on the same endpoint stays open.

## 4. The comparison operators an allow-list forgot

Whenever a mitigation is "the string lookups were removed", the next reading is the ordering
comparisons, which are routinely left off a deny list that covers the string functions by
name. They leak the same information through the collation order.

One Test, on a filter DSL that kept greater-than and less-than and exposes a navigation
property or a joined entity. The baseline is the comparison against a bound that must return
NOTHING, sent twice unchanged and invariant. The variant is the same comparison against a
bound partway up the space, first low then middle; a result set that flips across a single
boundary is the oracle. Two controls are both required: the comparison against an empty
bound must return EVERYTHING, and a comparison against a field that certainly does not exist
must error. Without the first anchor the counts mean nothing, and an unanchored version of
this reading is what produces confident noise. body_differs naming the mid-bound arm against
the must-be-empty anchor is what close_test_replay closes.

Establish the oracle and stop. The anchors are the reading; the search is not. Run to
completion this becomes information_disclosure.identifier_oracle, which is another
Playbook's class and another reason the anchors are what this section keeps. Record that
collation makes the comparison case-insensitive on most backends, so any inference is about
a case-folded value.

## 5. The pattern that only backtracks when its prefix matches

A regex lookup can be turned into a status oracle where the backend enforces a time limit on
regular expressions and the timeout surfaces as a 500. That limit is a hard precondition,
not colour: without it the pattern runs unbounded, and the reading is refused rather than
inconclusive, because unbounded backtracking on a shared database is a denial of service
with better manners.

One Test. The baseline is the regex lookup carrying an anchored lookahead on a character the
value cannot start with, followed by the nested wildcards, which answers 200 with an empty
list; sent twice unchanged and invariant. The variant is the identical pattern with the
lookahead anchored on the guessed character, which answers 500 because the prefix matched
and the backtracking ran into the limit. The control is a plain anchored prefix with no
wildcards at all, which must answer 200 non-empty and so proves the field and the lookup
exist and that the 500 came from backtracking rather than from a rejected filter name.
status_differs naming the matching-character arm against the non-matching one is what
close_test_replay closes.

Two probe characters and the control, and the reading is over; no alphabet is swept. Where a
500 arrives without the control having returned 200 non-empty, the load is unbounded, the
whole run stops on this subject, and the operator is told immediately.

This section is the cleanest case in the corpus of re-casting a timing mechanism into a
status observation, and it is worth stating as a rule rather than as one section's trick.
timing_differential is filable, from a Receipt that carries its own arrival and egress
stamps, so the status framing is chosen for evidence STRENGTH rather than for availability:
no assertion kind is time-shaped, and a Test that settles on a status settles.

## 6. State the claim, and name what this Playbook will not do

The Hypothesis is injection.query_field on the endpoint, proposed with
`mcp__rk2__propose_finding` naming sqli as the class -- that argument takes a
vulnerability_classes id and not a dotted Property class, and
property_class_vulnerability_classes carries no row for this Playbook's own class, so the
choice is recorded here rather than derived and finding_class_divergence stays silent for an
unmapped class. It is supported when the real-name arm differs from the fictional-name arm
against a baseline whose repeated sends were invariant. It is refuted when both arms are
invariant against each other on a stable baseline the offered value did move -- the
parameter works and it takes only what it offers. Inconclusive covers an unstable baseline,
a parameter the offered value did not move either, and a route returning one generic error
for everything.

Two neighbours are close. Where the value is concatenated into the statement's text rather
than naming one of its identifiers, the class is injection.query_language and the Playbook
is sql-injection. Where the value arrives as an operator in a document store's query
document, the class is injection.query_operator and the Playbook is nosql-injection.

One reading is refused by this Playbook's own ceiling rather than by any harness limit, and
the reason travels with it so it is not re-proposed. Traversing out through a shared
many-to-many relation and back into the same model reaches rows an application-level filter
deliberately removed, which is a tenant-isolation consequence rather than a wider projection
-- and it is a three-hop path, while this Playbook traverses one hop. The refusal is a
decision, not an omission: lifting it needs an operator who accepts what a loop-back join
returns.

This Playbook sends field names and relation paths, and its baseline is a session that stays
stable. It does not send a raw statement fragment through the identifier position, does not
chain a traversal past one hop, does not write a field the caller was not offered through
the same framework, and does not order a result set repeatedly to read a value out of the
ordering. Mass assignment through the same framework is a real and adjacent defect that
writes; this Playbook does not, and it belongs to a reading that declares that. Every halt
above is a reading that ran out -- one position established, one boundary flipped, two
characters probed -- and no question code says that, so each is reported through the Task's
own record.

This section proposes and grades nothing. 2 of 6 steps cannot be graded.
