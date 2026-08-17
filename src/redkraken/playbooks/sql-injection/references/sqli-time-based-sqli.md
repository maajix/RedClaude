# Time-based SQL injection: the noisiest channel, and its control

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

The fallback when the response body says nothing at all: no differential, no
error, no reflected value. Make the database wait, and measure.

The page gave the per-engine syntax -- `SLEEP(5)` on MySQL, `pg_sleep(5)` on
PostgreSQL, `WAITFOR DELAY '0:0:5'` on MSSQL, and the Oracle workaround with
`DBMS_PIPE.RECEIVE_MESSAGE` -- plus the conditional wrapper that turns a delay
into a bit:

```
' AND IF(SUBSTRING(...)='a', SLEEP(5), 0) --
```

and the usual advice to raise the delay until the signal beats the noise.

## The half the Playbook uses

**The unconditional delay, once, with a paired control.**

This is the whole of it. One request whose payload asks for a fixed delay, one
request identical in every other respect whose payload asks for a delay of zero,
several samples of each, interleaved. What is claimed is the separation between
two sampled distributions.

Three rules the page did not have, and the Playbook does:

* **The control must be the same statement.** `pg_sleep(0)` against `pg_sleep(2)`
  -- not "the payload" against "no payload". The second comparison includes the
  cost of parsing the payload, of any WAF inspecting it, and of whatever else
  differs between two unlike requests.
* **Interleave, do not batch.** Backend latency drifts on a scale of seconds.
  Ten payload requests followed by ten control requests measures the drift.
* **The delay is small and it is bounded by the Playbook's budget.** Two seconds
  is a signal. Ten seconds is a signal and a partial outage of one worker, and on
  a route with a connection pool it is an outage of the route.

**"Timing is the last resort" as a rule rather than a preference.** The Playbook
orders its steps so timing runs only after the boolean pair and the error ladder
have both returned nothing. A timing finding is the most expensive to produce,
the hardest to reproduce, and the one a triager is most likely to reject.

## The half that stays out, and why

**Conditional timing over data.** `IF(SUBSTRING(...)='a', SLEEP(5), 0)` in a loop
is blind extraction with a slower clock, and it is out for the reasons the blind
page's notes give -- with the additional cost that every single bit costs the
target the full delay. Extracting one 32-character value at 2 seconds a bit is
over eight minutes of deliberately held connections.

**Escalating the delay until it works.** The page's advice, and it is how a
reading turns into a denial of service without anybody deciding to cause one. If
2 seconds does not separate the distributions, the answer is more samples, not a
longer sleep.

**Heavy-query timing.** `AND (SELECT COUNT(*) FROM generate_series(1,10000000))`
as a substitute where `pg_sleep` is unavailable. It produces a delay by burning
the target's CPU, and the amount it burns is not knowable in advance.

## The trap in the whole technique

Everything on a network is slow sometimes. A single 5-second response to a
`SLEEP(5)` payload feels like proof and is one sample from a distribution with a
long tail. Cold caches, a JIT warming up, a connection pool refilling, a
cross-region hop, a neighbour's batch job -- all produce multi-second responses
on routes with no injection anywhere near them.

The inverse trap is worse and less discussed: **a timeout is not a delay.** If
the route's own gateway cuts requests at 3 seconds and the payload asks for 5,
the injected and control requests both return at 3, the distributions overlap,
and a live injection reads as refuted. Which is why the Playbook records the
observed ceiling and reports `inconclusive` rather than `refuted` when the
payload's delay exceeds it.
