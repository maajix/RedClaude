---
description: Ask whether a query parameter is concatenated into a SQL statement rather than bound to it, by sending one request as two arms whose payloads differ only in a clause the database evaluates and differencing the two stored responses against a neutral baseline.
bb:category: injection
bb:outputs: ["injection.query_language"]
bb:triggers_all: ["authenticated_endpoint", "query_parameter", "tech_sql"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 53 as the v2 replacement for v1's sql-injection pack against the query_language leaf of the ticket 18 vocabulary; the pack's twelve pages are attached as maintainer references and every extraction, union and escalation step in them is refused by step 6.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_invariant", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "response_invariant", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "response_differential", "polarity": "supports", "min_count": 1}]
bb:references: ["sqli-advanced-sqli-techniques.md", "sqli-advanced-sqlmap.md", "sqli-blind-sql-injection.md", "sqli-custom-tampering.md", "sqli-identifying-vulnerabilities.md", "sqli-intro-to-mssql-sql-server.md", "sqli-leaking-netntlm-hashes.md", "sqli-out-of-band-dns.md", "sqli-postgresql-specific-techniques.md", "sqli-remote-code-execution.md", "sqli-time-based-sqli.md", "sqli.md"]
---

# Ask whether the database evaluated it

A value either arrives at the database as data or arrives as part of the
statement. The difference is invisible in one response and obvious across two,
provided the two differ in one clause and nothing else.

The subject is an authenticated endpoint carrying a query parameter on an
Application running a SQL engine. The question is whether that parameter is
concatenated into a statement, and the whole reading is three requests.

## 1. Name the parameter and the engine

Read the parameter from the state view. Do not pick one out of the URL: a route
may carry four and only one of them reaches a WHERE clause, and the state view
already records which values the surface takes.

Prefer, in this order, a parameter that names a sort column, a pagination bound,
a filter, then anything else. A sort or a limit cannot be bound -- SQL has no
placeholder for an identifier -- so those positions are hand-built even in
codebases that parameterise everything else.

Name the engine the surface fact came from. It is not decoration: string
concatenation is `||` on PostgreSQL and `+` on MSSQL, and a control written in
the wrong dialect is a syntax error being reported as a differential.

Complete this step with the endpoint, the one parameter, and the engine.

## 2. Establish the baseline, twice

Send the request through `mcp__rk2__http_request`, with the parameter carrying an
ordinary value. Then send it again, unchanged. Both go out as whichever Identity
the Task was opened under: the step does not choose it and there is no argument
for it.

Two identical requests, because the comparison later has to know what "the same
response" looks like on this route. A page carrying a CSRF token, a request id,
a timestamp or a rotating panel is not byte-stable, and a differential measured
against a baseline nobody checked is noise with a verdict attached.

If the two differ, run `compare-responses` over them and record what moved. The
remaining steps compare only the parts that held still. If nothing holds still,
this Playbook cannot read the route and says so.

## 3. Send the two arms

Two more requests. The parameter carries:

* the value with a clause the engine evaluates to true appended
* the same value, same length, same metacharacters, with the clause evaluating
  to false

The second arm is the control, and it is a control in the strongest sense
available: it contains every character the first one does. A control that drops
the quote, or that sends the plain value, differs from the variant in the
encoding *and* in what a filter would match, and the comparison then has two
variables.

Interleave them with the baseline rather than sending them as a block. Backend
latency and deployment state drift on the scale of seconds.

Hold everything else constant. Same Identity, same headers, same body, same
order of parameters. The clause is the only thing that moves.

The repeat policy is three rounds of the pair, six requests, interleaved. A
differential that appears in one round and not the next two is a route that
varies, not a clause that evaluated, and the verdict for it is inconclusive
rather than supported. Three rounds is the floor because two agreeing rounds
cannot tell a stable difference from a coincidence that happened twice.

## 4. Difference the stored bytes

Run `compare-responses` over the true arm and the false arm, then over the true
arm and the baseline. Cite what the script returns, not a description of it.

Two comparisons, answering different questions. True against false is the
differential: if the two responses differ, something evaluated a clause that
differs only in a digit. True against baseline is the corroboration that says
which way round it went -- a clause that evaluated true leaves the answer as it
was, and it is the false arm that should have moved.

An injection where the *true* arm is the one that moved is still a differential
and still worth reporting, and it is worth saying in the observation, because it
usually means the clause landed somewhere other than the WHERE the reading
assumed.

## 5. Rule out the filter

A route that answers differently for a string containing `AND` may be answering
a signature rather than a statement. Send one more request whose parameter
carries a value that looks equally hostile and is not valid SQL in that
position.

If that response matches the true arm, something is grading the request text and
the database never saw it. That is a finding about a filter and it is not this
Hypothesis.

Anything else clears it. The probe is not valid SQL where it lands, so an engine
that really parsed it answers with a syntax error, an empty result or whatever
the false arm got -- and none of those is a text grader reproducing its verdict
on hostile-looking bytes. The test is that the probe did not reproduce the true
arm, not that it matched the baseline: on a genuinely injectable route it will
not match the baseline, and a reading that required it to would refuse to report
every true positive it found.

This is one request and it is the difference between a report a triager accepts
and the most common false positive in this class.

## 6. State the claim, and state what would refute it

The Hypothesis is `injection.query_language` on the endpoint. It is supported
when the two arms differ from each other in every round, the two baseline
requests were invariant against each other, and the filter probe did not
reproduce the true arm. It is refuted when the two arms are invariant against
each other against a baseline that was itself stable -- the value went in as
data and came out as data.

Anything else is inconclusive, and inconclusive is the honest verdict for an
unstable baseline, for a route that answers 403 to every arm, and for a route
whose query result never reaches the response at all.

Two neighbours are close.

* Where the input decides which stored field or relation the query filters on
  rather than what the query says, the class is `injection.query_field` and the
  Playbook is `orm`.
* Where the input arrives as an operator or a type in a document store's query
  document rather than as a fragment of a query language, the class is
  `injection.query_operator` and the Playbook is `nosql-injection`.

Cite the two Artifacts and the difference the script returned.

## 7. One clause, no second statement

This Playbook is `read_only` and its baseline is a session that stays stable.

It appends one clause to one value and it reads the response. It does not send a
union, count columns, read `information_schema`, stack a second statement, sleep
the database, write a file, call a program, open an outbound connection, or
extract a single byte of the target's data. Those steps prove nothing this
reading has not already proved, and the twelve attached references say for each
one why it is out.

Where the response-side channels have nothing to measure -- a route that queues
its query, discards its result, or answers from a cache -- the verdict is
`inconclusive` and it routes to an operator. It is not an invitation to reach for
a channel this Playbook does not have.
