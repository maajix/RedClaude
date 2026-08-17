# SQL injection: the core page and what survives of it

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

The root of v1's largest pack. A route builds a statement by concatenating a
caller's value into SQL, and the page taught the whole arc: break the quoting,
observe that the statement changed, then extend the statement to read what you
were not given.

It covered the classic entry points -- `'`, `"`, `)`, a bare numeric with `+0` --
the three shapes of exploitation (in-band union, blind boolean, blind timing),
comment syntax per engine, and the `information_schema` walk that turns a working
injection into a table listing.

## The half the Playbook uses

The first two thirds of the arc and none of the last.

**Breaking the quoting is a differential, not an error.** The page's habit was to
send `'` and look for a stack trace. That works and it is the weakest version of
the reading, because a route that returns a 500 for `'` may have a fragile parser
somewhere else entirely. What the Playbook drives instead is the pair the page
introduced later:

```
value' AND '1'='1      -- the true arm
value' AND '1'='2      -- the false arm
```

Two requests, same length, same shape, and the only difference is a clause the
database evaluates. If the two responses differ, something evaluated them. If
they do not, they were data. That is a boolean differential with its own control
built in, and it is why the Playbook's evidence rows are `response_differential`
paired with `response_invariant` rather than `error_detail` alone.

**The engine-fingerprint step, reduced.** The page fingerprinted by error text so
it could pick the right union syntax. The Playbook fingerprints only to pick the
right neutral control -- string concatenation differs by engine, and a control
that is syntactically invalid on the target is not a control. It never
fingerprints in order to escalate.

**Numeric context.** Worth keeping because it is the case a quote-only reading
misses entirely: an `id=7` that answers identically to `id=8-1` is concatenated
into arithmetic the database performed. One request, no quoting, no error.

## The half that stays out, and why

**`UNION SELECT` and everything downstream.** Column counting, type juggling to
find a printable column, `information_schema.tables`, `group_concat` of a user
table. All of it is out. The verdict was reached by the boolean pair; the union
exists to extract data, and extracted data from a live Program is somebody's
personal information sitting in this harness's evidence store, subject to a
retention policy nobody wrote for it.

**Stacked queries.** `; DROP`, `; UPDATE`, `; INSERT` -- the Playbook is
`read_only` and a stacked statement is by definition not.

**Authentication bypass as a demonstration.** `' OR 1=1 --` in a login form is
the most famous payload in the field and the Playbook will not use it as proof,
because the successful version of it authenticates as a real person.

## The trap in the whole technique

A boolean differential can come from the WAF rather than the database. A route
that returns a different body for `' AND '1'='1` may be returning it because an
inline filter matched the string `AND`, not because a database evaluated it.

The tell is a third arm. Send the same request with an equally suspicious-looking
string that is *not* valid SQL in that position -- something a signature would
flag but an engine would reject -- and see which response it matches. If it looks
like the true arm, a filter is grading the request and there is no injection to
report. The Playbook makes this a step rather than a footnote, because a WAF
differential is the single most common false positive in this class.
