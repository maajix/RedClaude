---
description: Ask whether a query parameter names a stored field or a relation to the ORM that builds the statement, by sending one request with a field the caller was never offered and differencing the response against a request naming a field that does not exist.
bb:category: injection
bb:outputs: ["injection.query_field"]
bb:triggers_all: ["authenticated_endpoint", "query_parameter", "tech_orm"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 53 as the v2 replacement for v1's orm page, against a new query_field leaf added by ticket 53 because an ORM injection changes which column the query names rather than what the query says; no upstream card.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_invariant", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "response_invariant", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "response_differential", "polarity": "supports", "min_count": 1}]
---

# Ask which column the caller chose

An ORM was supposed to end this class. It parameterises values, so the quote that
breaks a hand-built statement does nothing, and a reading that only knows how to
send quotes will report every ORM-backed route as clean.

The defect moved rather than disappearing. The parts of a query an ORM cannot
parameterise are the parts that name things: which column to sort by, which
column to filter on, which relation to join, which fields to return. Those arrive
as identifiers, and a route that builds them out of a query parameter has let the
caller choose them.

The subject is an authenticated endpoint carrying a query parameter on an
Application running an ORM. The question is whether that parameter reaches the
query as a name.

## 1. Name the parameter and what it looks like it selects

Read the parameter from the state view, and prefer the ones that carry
identifiers rather than values: `sort`, `order`, `order_by`, `fields`, `filter`,
`include`, `expand`, `embed`, and the framework-shaped compounds -- a filter key
that contains a double underscore, a dot, or a bracket is a relation traversal
spelled in the framework's own syntax.

Name the framework the surface fact came from. The traversal syntax is
framework-specific, and a probe written in the wrong one is a probe for a field
literally named `user.email`.

Complete this step with the endpoint, one parameter, and the framework.

## 2. Establish the baseline, twice

Send the request through `mcp__rk2__http_request`, the parameter carrying a value
the interface offers -- a column the page's own sort control uses, a field the
documentation lists. Then send it again, unchanged. Both go out as whichever
Identity the Task was opened under: the step does not choose it and there is no
argument for it.

The offered value matters. It establishes that the parameter works, which the
later refutation needs: a parameter that is ignored entirely produces the same
invariance as a parameter that is validated, and those are different findings.

## 3. Send the two arms

Two more requests.

* The variant names something the interface never offered: a column on the same
  table that the response does not show, or a traversal into a related table
  spelled in the framework's syntax.
* The control names something that cannot exist -- a name of the same length and
  shape, composed the same way, that no schema would contain.

The control is the point of the design. An ORM that accepts arbitrary names
answers differently for a real column and a fictional one, because one resolves
and one raises. A route with an allow-list answers identically for both, because
neither is on the list. That single comparison separates "the caller chooses the
column" from "the caller chooses from a menu", and no error message is required
for it.

Hold everything else constant.

The repeat policy is three rounds of the pair, six requests, interleaved. The
signal here is which rows or columns came back, and a list endpoint's contents
move for reasons that have nothing to do with the caller -- another tenant
writing, a cache filling, a page boundary shifting. A difference that does not
reproduce in all three rounds is inconclusive.

## 4. Difference the stored bytes

Run `compare-responses` over the real-name arm and the fictional-name arm, and
over the two baseline requests. Cite what the script returns.

The characteristic ORM signal is that the two arms part company at all: an
allow-list rejects both names with one message, and a query builder that resolves
names at run time answers the real one and raises on the other. Which of the two
raised is worth recording, because a 500 quoting a field name is the strongest
single observation this reading produces.

## 5. Read what a traversal returns, and stop there

If the traversal arm succeeds, the response may now contain a column from a
related table -- and that is where this reading stops. A `sort` parameter that
traverses into a users table orders the results by somebody's password hash, and
the ordering itself leaks the value one comparison at a time. That is the impact,
it belongs in the report's narrative, and performing it is the blind extraction
loop wearing an ORM's syntax.

Record the difference. Do not sort your way through the column.

## 6. State the claim, and state what would refute it

The Hypothesis is `injection.query_field` on the endpoint. It is supported when
the real-name arm differs from the fictional-name arm against a baseline whose
two requests were invariant. It is refuted when both arms are invariant against
each other, on a stable baseline that the offered value did move -- the parameter
works, and it takes only what it offers.

Inconclusive covers an unstable baseline, a parameter the offered value did not
move either, and a route that returns the same generic error for everything.

Two neighbours are close.

* Where the value is concatenated into the statement's text rather than naming
  one of its identifiers, the class is `injection.query_language` and the
  Playbook is `sql-injection`. A `sort` parameter that accepts `id DESC, (SELECT
  1)` has crossed over into that one.
* Where the value arrives as an operator in a document store's query document,
  the class is `injection.query_operator` and the Playbook is `nosql-injection`.

Cite the two Artifacts and the difference the script returned.

## 7. Names only, and only names that read

This Playbook is `read_only` and its baseline is a session that stays stable.

It sends field names and relation paths. It does not send a raw SQL fragment
through the identifier position, does not chain a traversal further than one hop,
does not use a mass-assignment parameter to write a field the caller was not
offered, and does not order a result set repeatedly in order to read a value out
of the ordering.

Mass assignment through the same framework is a real and adjacent defect. It
writes, this Playbook does not, and it belongs to a reading that declares that.
