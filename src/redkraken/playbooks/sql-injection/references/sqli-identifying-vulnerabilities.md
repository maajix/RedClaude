# Identifying SQL injection: where the reading actually starts

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

The detection page, as opposed to the exploitation pages. Which parameters are
worth testing, in what order, and how to tell a real signal from noise. It listed
the high-yield positions -- sort and order-by parameters, filter and search
fields, pagination limits, anything named `id`, and the ones people forget:
`Cookie`, `Referer`, `X-Forwarded-For`, `User-Agent`, because logging middleware
concatenates them into an INSERT.

It also gave the payload ladder people actually use: one quote, two quotes, a
comment, a boolean pair, then timing.

## The half the Playbook uses

**The position list, in full.** It is the most valuable content in the pack and
it costs nothing to carry. The ordering matters: a sort parameter is the single
best target in a modern application, because `ORDER BY $col` cannot be
parameterised -- there is no bind placeholder for an identifier -- so even
codebases that use an ORM everywhere else hand-build that one clause. The
`orm` Playbook takes the same observation from the other side.

**"Two quotes" as a first-class step.** The ladder's second rung is the one that
gets skipped, and it is the one that separates a parser from a filter. If `'`
gives an error and `''` gives the original response, a quote is being consumed by
SQL syntax. If `''` errors too, something is rejecting the character rather than
parsing it.

**The refutation, stated positively.** A parameter whose value is echoed back
byte-for-byte and whose response is identical across the true and false arms has
answered the question. The Playbook writes this down as a `refuted` verdict with
its own evidence rather than leaving the hypothesis open, because an injection
hypothesis that nobody closes gets re-tested by the next task.

## The half that stays out, and why

**Header injection as a routine step.** The page was right that `X-Forwarded-For`
reaches an INSERT in a lot of applications, and the Playbook does not sweep
headers by default. Two reasons: the sink is usually an audit or analytics table,
so a differential is invisible in the response and the only detection left is
timing or out-of-band, and a bad payload there corrupts a log the target relies
on. It is a step the operator can direct at a specific header, not one that runs
on its own.

**Scanning every parameter.** v1's implicit workflow was "test them all". This
Playbook is selected against a subject that already carries `tech_sql`, a query
parameter, and an authenticated endpoint, and it reads that subject. Breadth is
the recon Playbook's job and the selection layer's job, not this one's.

## The trap in the whole technique

Error-based detection over-reports and under-reports at the same time.

Over-reports: plenty of routes return a 500 for a quote because something
downstream -- a JSON serialiser, a regex, a template -- did not expect it. The
error proves an exception, not a database.

Under-reports: an application with a global exception handler returns a tidy 400
for a syntax error that would have been a stack trace in development, and a
reading that stops at "no error, no injection" walks past a live one.

The boolean pair suffers from neither, which is why it is the Playbook's primary
step and the error ladder is a supporting one.
