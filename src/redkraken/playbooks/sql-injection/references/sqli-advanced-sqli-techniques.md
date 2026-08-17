# Advanced SQL injection techniques: mostly out, one thing kept

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

The page you reached once the basics worked and the target fought back. Second
order injection, where a value is stored cleanly and concatenated later by a
different route. Injection into positions with no bind placeholder: `ORDER BY`,
`LIMIT`, table and column identifiers. Filter evasion by case, by inline comments
(`/**/` for a blocked space, `UN/**/ION`), by scientific notation, by
alternate whitespace bytes. Out-of-band channels. Stacked queries, and what
becomes possible once a second statement runs.

## The half the Playbook uses

**Second order, and it is the most valuable idea in the pack.**

A registration form stores a display name. Nothing happens. Three routes later,
an admin report builds a query by concatenating that display name, and the
injection fires in a request the value was never sent to. Every step of a
single-request reading misses this, because the differential appears somewhere
the reading is not looking.

The Playbook cannot chase this on its own -- it reads one subject -- but it can
do the two things that make the chase possible for whatever reads next:

* When a value is stored and the response says so, record a `state_change`
  observation naming the value and the field. A stored marker is the anchor a
  later reading needs.
* Prefer a marker that is inert but searchable: a token that will show up in a
  later response body without being SQL. The point is to find where the value
  resurfaces, and a payload that breaks the second query destroys the very
  route that would have shown you the link.

**Positions with no placeholder.** `ORDER BY $col` and `LIMIT $n` cannot be
parameterised, so they are hand-built even in codebases that are otherwise
disciplined. The Playbook's step ranks a sort or pagination parameter above a
filter parameter for exactly this reason. Detection there is a differential over
result ordering, which is cheap and needs no error at all: ask for the same page
sorted by a column that exists and by an expression, and see whether the order
changes.

**Inline-comment substitution, once, as a control probe.** Same use as the
command pack's `$IFS`: if `UNION` is rejected and `UN/**/ION` is not, a deny list
is grading the request. One probe, and the finding is about the filter.

## The half that stays out, and why

**Stacked queries.** A second statement is a write by construction, and the
Playbook is `read_only`.

**Out-of-band channels.** They are covered in their own note; the short version
is that they prove reachability and put a record of the engagement on a resolver
somebody else runs.

**The evasion catalogue at length.** Case shuffling, scientific notation, unicode
whitespace, comment padding in ten variants. Each one is another way to reach a
differential the Playbook can already reach or has already ruled out.

## The trap in the whole technique

Second order readings produce the most confident wrong answers in this class, in
both directions.

A value stored during a reading may fire days later in a batch job, in a report
nobody requested this week, in an export a human triggers by hand. The reading
that planted it will have closed as `refuted` long before, and the effect will
surface with no record connecting it to the request that caused it.

That is the argument for the inert marker and for writing the `state_change`
down. It is also the reason the Playbook never plants a payload it would not be
willing to have execute at an unknown time, on an unknown route, with nobody
watching.
