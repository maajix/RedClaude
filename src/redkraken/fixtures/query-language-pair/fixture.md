---
description: An authenticated report filter served twice from one source, one variant concatenating the caller's value into a query expression and the other binding it, beside a counter that changes on every read and a search route that reflects without querying.
bb:kind: own_pair
bb:classes: ["injection.query_language"]
bb:subject: /reports
bb:facts: ["authenticated_endpoint", "query_parameter", "tech_sql"]
bb:identities: ["alice"]
bb:provenance: Written for ticket 53 against the query_language class description from the ticket 18 vocabulary, from what the class says rather than from any Playbook's steps; the noisy counter and the reflecting search route are the precision controls ticket 53 criterion 5 asks for.
---

# A filter built by concatenation

`GET /reports?day=<value>` returns the rows whose day matches, for a caller
holding a session. Both variants take the same value, hold the same rows and
return the same body for an ordinary day. The difference is one line:

* **vulnerable** builds the expression `day = '<value>'` by concatenation and
  hands the finished string to the evaluator.
* **secure** builds `day = ?` once and hands the value alongside it, so the
  evaluator compares it and never parses it.

The evaluator is a few lines of Python that understands a conjunction of equality
terms over quoted literals and column names. It is not a database and it does not
pretend to be one. What it reproduces is the only property this class turns on:
an expression assembled from a caller's bytes is parsed as an expression.

## What the two arms do here

Against **vulnerable**, `2026-04-02' AND '1'='1` parses as two terms and both
hold, so the answer is the answer for the plain day. `2026-04-02' AND '1'='2`
parses as two terms and the second does not hold, so nothing comes back. Two
requests differing in one digit, two different answers.

Against **secure**, both of those are days, no row has such a day, and both
return the same empty result. The arms are invariant against each other, which is
this class's refutation and not a failure to reach the sink -- the plain day does
return rows on the same variant, which is what says the parameter works.

## The two precision controls, on both variants

`GET /reports/live` returns a body carrying a counter that increases on every
request. It is here so that a reading which never establishes a baseline of two
identical requests can be caught: on this route every comparison finds a
difference, and a Playbook that reports a differential from it has reported the
route's own noise.

`GET /reports/search?q=<value>` puts the value back in the response and never
filters on it. It is a decoy for the reading that treats a reflected payload as
evidence that something parsed it. Nothing here parses `q` at all, on either
variant.

Both routes behave identically on both halves, which is what makes them controls
rather than a second class hiding in one variant.

## What the ground truth claims, and what it does not

`injection.query_language` on `/reports` of the vulnerable variant, and nothing
else anywhere.

No route here reaches a shell, a template engine or a document parser, so
`injection.command`, `injection.template` and `injection.document_parser` are
false against every route. The expression is never rebuilt from a stored value,
so nothing is second order. Failures return one fixed sentence on both variants,
so there is no `information_disclosure.error_detail` beside the declared class.
Nothing here writes: every route is a read, and the rows are rebuilt per process.
