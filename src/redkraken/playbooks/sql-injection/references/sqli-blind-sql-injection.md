# Blind SQL injection: the differential without the extraction

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

What to do when the response never shows you a database row. The page's answer
was to turn the response itself into a one-bit channel: write a condition, send
it, and read the answer from whether the page came back the same.

```
' AND SUBSTRING((SELECT password FROM users LIMIT 1),1,1)='a' --
```

Then loop -- per character, per column, per row -- with a binary search on the
character to cut the request count, and a `LENGTH()` probe first to know when to
stop.

## The half the Playbook uses

**The one-bit channel, and only its first bit.**

The conditional differential is exactly the right primitive for detection: it is
`read_only`, it is repeatable, and it carries its own control because the same
request with an inverted condition is the neutralised twin. The Playbook's step
sends `AND 1=1` against `AND 1=2` -- conditions with no subquery in them at all
-- and reports the difference.

That single bit answers the question the hypothesis asked. Every later bit
answers a question about the target's data, which is a different question and one
this Playbook does not have permission to ask.

**Stability first.** The page assumed a page that is byte-identical between two
identical requests. Real routes are not: they carry a CSRF token, a request ID, a
timestamp, a rotating advertisement. So the Playbook's first blind step is two
identical requests, and if those differ, the comparison is narrowed to a
projection that is stable across them -- status, length bucket, a selected set of
elements -- before any condition is sent. A differential measured against an
unstable baseline is noise with a verdict attached.

**Interleaving.** True arm, false arm, true arm, false arm -- not five of one
then five of the other. A deployment rolling behind the load balancer will
otherwise hand you a beautiful differential that is entirely an artefact of when
the requests were sent.

## The half that stays out, and why

**The extraction loop.** `SUBSTRING`, `ASCII`, the binary search, `LENGTH()`,
the outer loop over rows. Out entirely.

The cost argument alone is decisive: a 32-character hash at one bit per request
is 256 requests with binary search, times a column, times a row. Against a live
Program under a 5-requests-per-second budget that is an afternoon of traffic to
prove something the second request already proved.

The evidence argument is stronger. What comes back is credentials. This harness
stores observations in a database, redacts them on export, and hands them to a
report. Nobody wants a target's password hashes in that pipeline, and no rules of
engagement this repository has seen would permit it.

**Conditional errors and conditional timing as extraction channels.** Same
machinery, same refusal. `CASE WHEN ... THEN 1/0 ELSE 1 END` is a fine detection
probe for a route that swallows differentials, and it stops being a detection
probe the moment the condition contains a subquery over user data.

## The trap in the whole technique

Blind readings are where confirmation bias does the most damage, because the
signal is small and the observer chooses the projection. If you compare full
bodies you see a difference every time; if you compare status codes you see one
almost never. Somewhere in between is a projection that shows exactly the
difference you were hoping for, and it is very easy to arrive at it by adjusting
until the answer appears.

The discipline the Playbook enforces: fix the projection *before* sending the
conditional pair, using the two identical requests, and do not change it
afterwards. If the projection turns out to be wrong, that is a new reading with
its own baseline, not an edit to this one.
