---
description: Ask whether a query parameter is concatenated into a statement rather than bound to it, by sending arms whose values differ only in a clause the engine evaluates and differencing them against a length-matched twin and a baseline checked for stability first, in SQL and in the two neighbouring query languages the same shape reads.
bb:category: injection
bb:outputs: ["injection.query_language"]
bb:triggers_all: ["authenticated_endpoint", "query_parameter", "tech_sql"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 53 as the v2 replacement for v1's sql-injection pack against the query_language leaf of the ticket 18 vocabulary; the pack's twelve pages are attached as maintainer references and every extraction, union and escalation step in them is refused by section 8. Rewritten for ticket 101 against the merged technique ledger, which carries eighteen readings and five standing refusals for this slug. One frontmatter key moved and it is a repair -- the refuted leg of the variant asked for response_invariant while its supported leg asked for response_differential, and close_test_replay derives one kind per role from the specification, so the refuted leg was a bar nothing could clear. Repaired again in review -- the differing assertions named the control, which would have left the control row unmet, so they now name the baseline; and section 5 is restated as a lead, since a park closes the run and no assertion reads a correlator or a clock. Sections 3 and 4 gained a baseline and an assertion in round 3.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_differential", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "response_invariant", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "response_differential", "polarity": "supports", "min_count": 1}]
bb:references: ["sqli-advanced-sqli-techniques.md", "sqli-advanced-sqlmap.md", "sqli-blind-sql-injection.md", "sqli-custom-tampering.md", "sqli-identifying-vulnerabilities.md", "sqli-intro-to-mssql-sql-server.md", "sqli-leaking-netntlm-hashes.md", "sqli-out-of-band-dns.md", "sqli-postgresql-specific-techniques.md", "sqli-remote-code-execution.md", "sqli-time-based-sqli.md", "sqli.md"]
---

# Ask whether the database evaluated it

A value either arrives at the database as data or arrives as part of the statement. The
difference is invisible in one response and obvious across two, provided the two differ in
one clause and nothing else.

Every reading below is one Test proposed with `mcp__rk2__propose_test` and settled by
close_test_replay off the Test's own assertions. A specification performs three to
thirty-two actions and holds at least one in each of the roles baseline, variant and
control, so a two-armed reading is refused before it runs; the control here is the
length-matched twin, one truth value different. The body assertion kinds read the stored
response body digest alone, and a body is available where a reading needs one: the egress
authorisation reads body_allowed off the specification, so a read-only selection is not one
that sends no body.

## 1. Name the parameter, the engine and the position

This section is a lead. It selects what the rest reads and files no result of its own, so
the system cannot grade it. Read the parameter from the state view with
`mcp__rk2__get_attack_surface` rather than picking one out of the URL: a route may carry
four and only one reaches a WHERE clause. Prefer a sort column, then a pagination bound,
then a filter, then anything else -- a sort or a limit cannot be bound, because there is no
placeholder for an identifier, so those positions are hand-built even where everything else
is parameterised. Name the engine the surface fact came from: a control in the wrong dialect
is a syntax error read as one.

## 2. Fix the enclosure, then send the pair

A tautology that fails usually failed on the enclosure. The baseline is the value producing
the ordinary answer, sent twice; each variant is one candidate enclosure, closing the
quoting and bracket depth it assumes and commenting out the tail, with its own control, the
same enclosure with the clause false. One apostrophe against two reads it cheapest: if a
balanced pair restores the baseline's answer a quote is consumed by syntax, and if the
balanced arm errors too, something is rejecting the character rather than parsing it.

Then the pair itself. The variant carries the value with a clause the engine evaluates true
-- the quoted form, or the numeric form a quote-only reading misses entirely, an identifier
against the arithmetic that produces it -- and the control carries the same value, same
length, same metacharacters, clause false. Assert body_differs on the variant against the
baseline and body_equals between the two baseline sends; the control is named by no
differing assertion, which leaves it the response_invariant this Playbook's bar asks of that
role, where a comparison naming it would leave that row unmet. It is still read and the
report still says what it answered. close_test_replay derives the kinds from the
specification and settles the claim, and the agent files an error_detail edge through
`mcp__rk2__submit_mission_result` where the engine surfaced one. Repeat the pair for three
interleaved rounds rather than as a block: latency drifts on the scale of seconds, and a
differential in one round and not the next two is a route that varies. On a sort parameter
the arms are a real column, one that certainly does not exist, and an expression whose
ordering the reading predicts, where the ordering is the answer and no error is needed.

## 3. Rule out the grader, and rule out the caller

Two things other than a database produce the same split. For the grader: send an obviously
hostile value on a parameter the application does not consume. A refusal there is a text
grader, because the value cannot have reached a query; read the other way, the same axis
re-spells the rejected payload so it means the same thing to an engine and something else to
a signature. Accepted and matching the neutral control means a grader decided; accepted and
differing means the engine parsed.

For the caller: hold the payload fixed and move only the caller-identifying header, which a
Test action has stated since ticket 211, with an inert value sent under both spellings as
the control. If the inert value is refused under the tool-shaped one, the route is refusing
the caller and every negative verdict under it is void. Both are one Test on section 2's
baseline, the differing assertion naming the variant against it and never the control.

## 4. Ask a question the reading already knows the answer to

The strongest arms are the ones a text grader cannot reproduce, because their answer is
fixed before the request is sent and predicted from public application state. Steer row
selection with arithmetic: the enclosure plus an equality against a scalar the engine must
compute, a count over a relation the application displays, with the record named in advance
and a control asking for that scalar plus one, which must return the next record.

Carry a constant back in an impossible cast: two variants differing only in the constant, so
the differing bytes are the constant and the engine both evaluated the expression and
surfaced its result, with no target data read. Name the family from what parses: a tautology
using a function only one family implements, against a control expression none implements.
Ask a privilege as a boolean over an oracle already known to work -- role membership,
superuser, the bulk-operations or file roles -- with the negation of the predicate as the
control, since exactly one must return the true response. The privilege is read, never
exercised. Each arm is one Test on the same baseline, and no differing assertion names the
control.

## 5. Ask a route that answers somewhere else, or later

This section is a lead: each of its three readings ends at an Observation and none settles
this Playbook's bar. They share one shape, that the response the arm produces is not where
the answer is. A value stored cleanly by one route may be concatenated by a different route
later, and that reading needs one ordinary write through the application's own path, which
this Playbook's declared effects do not admit. It stops before the write and asks through
`mcp__rk2__park_for_human` for the Task to be parked, that Task's label going in
`task_label` and destructive_action in `question_code`. Parking closes the run, so the
write and the reads after it belong to the Task a person opens next, and nothing after the
park is a step this Playbook grades. Name its three arms and stop: an ordinary value stored
and the route read twice as the baseline, the clause-carrying value stored and read again
as the variant, the neutralised twin stored and read again as the control.

Where the route discards its result, the answer travels out of band. Mint the correlator
with `mcp__rk2__mint_callback`, naming the Program's bound channel in `channel` and this
reading in `subject_label`, put it in the name the injected expression makes the
database resolve, and keep the response arms equal: baseline an inert value, control that
value repeated, variant the correlated expression. Every arm is asserted equal, so no action
is named by a differing assertion, none closes response_differential, and the variant row of
this Playbook's bar goes unmet: the reading stops at a callback_interaction edge on a claim
that stays proposed. Fire one arrival at the channel first: that control arrival writes no
Observation, by design, and its absence is what makes a real one mean anything. Where the
answer is the clock, one arm asks a fixed delay and the other a zero delay of the same
statement -- never the payload against no payload, which also measures parsing --
interleaved rather than batched. No assertion kind is time-shaped, so nothing in a Test
reads a duration and that reading stops at a timing_differential Observation as well.

## 6. The same reading in a directory filter and in an XPath predicate

The three-armed shape is the reading, not the dialect. No surface fact names either engine,
so this Playbook is selected on a SQL surface and this section runs where the route turns
out to be backed by a directory or an XML document; saying which it was is part of the
result. In both dialects the differing assertion names the variant against the baseline and
never the twin, which leaves the twin the response_invariant the control role asks for.

In a directory filter the variant is a forced-true fragment and the control a forced-FALSE
fragment of the same length carrying the same metacharacters. A second control runs the
forced-true fragment against a term known to match nothing and must stay empty: if it
returns the directory, the clause matches everything rather than the entry. The same pair
pivots onto a foreign attribute against one that certainly does not exist, and onto a
substring predicate over the first character of a value the application already displays,
which says the clause reads content and not only truth -- one character, already public, and
no second. Most directory attributes are case-insensitive, so a recovered value is
case-folded.

In XPath the variant closes the parameter out of its quote and re-opens with a predicate the
engine must resolve true, against the inverted twin; if the false twin also moves, the
difference is a parse error and not an oracle. Where the parameter names an output selector,
the variant unions it with a positional node-set and a correct injection renders empty,
against a control that is the other legitimate selector and must print.

## 7. State the claim, and state what would refute it

The Hypothesis is `injection.query_language` on the endpoint, and it becomes a Finding
through `mcp__rk2__propose_finding`, which rk2_finding_refusal admits only where one of the
Tests above settled it. This section proposes no Test of its own and grades nothing. It is
supported when the arms differ from each other in every round, the two baseline sends were
equal, and neither the grader nor the caller probe reproduced the split. It is refuted when
the arms are equal against a baseline that was itself stable: the value went in as data.

Anything else is inconclusive, and inconclusive is the honest verdict for an unstable
baseline, for a route answering 403 to every arm, and for a route whose query result never
reaches the response. Two neighbours are close: where the input decides which stored field
the query filters on rather than what the query says, the class is `injection.query_field`
and the Playbook is `orm`; where it arrives as an operator in a document store's query
document, the class is `injection.query_operator` and the Playbook is `nosql-injection`.

## 8. One clause, no second statement

This section is a refusal and there is nothing in it to grade. Five readings are refused,
and each reason travels because every one will be re-proposed by somebody who can see the
requests themselves are ordinary.

Reading the target's data through a confirmed injection is out, including one character of
one column of one row: what comes back is credentials and personal data, which would live in
this store under a retention policy nobody wrote for it, and the reading is complete without
it. Stacking a second statement is out, and so is walking result-set shape -- an ordinal
ladder, a union of nulls widened to the arity, a literal rotated through the positions --
and the same walk over a backing document's depth and sibling count. Those three are refused
by this Playbook's own read-only line rather than by capability, and whoever owns that line
may decide otherwise, in writing. A blind predicate read off the clock by making the true
branch cost real evaluation time is refused on cost: the unblocking capability is the
ability to impose unbounded load, and the boolean oracle answers it in two.

So: no union, no column count, no catalogue walk, no information schema, no second
statement, no unbounded sleep, no file written, no program called, no outbound connection
this Playbook did not mint a correlator for, and not one byte of the target's data. Where
the response side has nothing to measure the verdict is inconclusive and routes to an
operator through the Task's own record. 4 of 8 steps cannot be graded.
