# Custom tampering: telling the filter apart from the database

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

Writing your own transformation for a payload when the stock ones are blocked.
In sqlmap terms, a tamper script: a function that takes a payload and returns a
mangled equivalent. The page walked through the usual transformations -- comment
padding for whitespace, case randomisation, double URL encoding, `CHAR()`
concatenation instead of quoted strings, `%0b` and other whitespace bytes an
engine accepts and a regex does not -- and how to chain them.

## The half the Playbook uses

**The diagnostic, not the evasion.**

A payload that comes back rejected has two possible explanations and they lead to
opposite verdicts:

1. Something between the caller and the database matched a pattern and refused
   the request. The database never saw it. The route may be perfectly injectable
   behind the filter.
2. The database saw the value as data. There is nothing to inject into.

These look identical from the outside -- a 403, a generic error, a scrubbed
response -- and a reading that cannot distinguish them will call the second case
correctly and the first case wrongly, every time, on exactly the targets where a
finding exists.

The Playbook's step is one request. Take the rejected payload, apply one minimal
transformation that changes the bytes a signature matches without changing what
the engine would parse -- `/**/` where a space was, mixed case in the keyword --
and send it. Three outcomes, three verdicts:

* Still rejected, identical response: consistent with the value never reaching a
  parser. Continue the reading with the remaining channels; do not escalate.
* Now accepted and the response matches the neutral baseline: a filter was
  grading the request and the database treats the value as data. The finding, if
  any, is about the filter.
* Now accepted and the response differs from the neutral baseline: the filter was
  the only thing standing between the caller and a parser. That is the
  differential, and it is a stronger finding than either of the others because it
  names both defects.

**One transformation, not a chain.** A chained transformation that succeeds tells
you nothing about which link mattered, and the goal is a legible verdict.

## The half that stays out, and why

**Tampering as a way to land a bigger payload.** The catalogue exists so a union
or a stacked statement can get through. This Playbook has no union and no stacked
statement to land, so the catalogue's purpose does not apply to it.

**Double encoding and byte-level tricks against the proxy layer.** These are
often less about the database than about disagreements between a CDN, a
load balancer and an origin over how to decode a request. That disagreement is a
real class of finding and it belongs to the `web-cache` and `routing` readings,
which have the right vocabulary for it.

## The trap in the whole technique

Successful evasion is deeply satisfying and it produces a specific error: the
reading concludes that a filter which can be bypassed is itself the finding, and
reports it as an injection.

A managed WAF in front of a route with parameterised queries can be walked around
all day, and every bypass proves the same thing -- that the WAF has gaps, which
its vendor already documents. There is no injection there.

The rule the Playbook applies: a bypass is only worth reporting when the bypassed
request produces a differential the neutral baseline does not. Getting past the
filter is not a result. What the request does after it is past is the result.
