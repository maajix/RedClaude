# Out-of-band DNS: the last-resort channel, and the reasons it stays shut

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

What to do when the response tells you nothing at all -- no differential, no
error, no timing separation, because the query runs in a background job or its
result is discarded. Make the database itself send a signal to a host you
control.

The page gave the per-engine primitives: `xp_dirtree` and `xp_fileexist` on
MSSQL, `LOAD_FILE('\\\\host\\share')` on MySQL with `secure_file_priv` unset,
`UTL_INADDR.GET_HOST_ADDRESS` and `UTL_HTTP` on Oracle, `dblink` or `COPY FROM
PROGRAM` on PostgreSQL. Then the extraction pattern: concatenate the value you
want into a subdomain, and read it off your own resolver's log.

## Why the Playbook does not run it

**It proves reachability, not execution.** A DNS lookup arriving at your resolver
says something on the target's network resolved a name. It does not say the
database evaluated your expression, and the gap between the two is where the
false positives live: a WAF that resolves hostnames it finds in request bodies, a
logging pipeline that enriches records, a security product that detonates
suspicious strings in a sandbox. Each one produces the exact signal the page
treats as proof.

**It puts the engagement on infrastructure nobody in it controls.** The lookup
traverses the target's resolver, its upstream, and whatever recursive service
sits above that. The record is a log line on machines belonging to third parties,
retained under policies nobody in the engagement chose, containing a subdomain
that -- in the extraction pattern -- is the target's own data.

**The extraction pattern is extraction.** Concatenating a password hash into a
hostname is the blind loop with a worse evidence trail: it is data taken from the
target and written into the global DNS.

**Every primitive it needs is a primitive this Playbook refuses.** `COPY FROM
PROGRAM`, `xp_dirtree`, `UTL_HTTP` -- these are the same functions the engine
notes rule out. There is no version of this technique that stays inside
`read_only`.

**It needs infrastructure the Playbook does not have.** A registered domain, an
authoritative resolver, log access, correlation between a lookup and a request.
A reading that has to stand that up mid-flight is not a reading.

## What is kept

The honest verdict for the situation the page was written for. When a route
discards the query's result -- a fire-and-forget write, a queued job, an audit
insert -- the response-side channels have nothing to measure, and the correct
outcome is `inconclusive` with a note saying which channels were tried.

That is a worse answer than the page's and it is a true one. `inconclusive`
routes to an operator who can decide whether an out-of-band channel is worth
standing up for this specific Program, with its rules of engagement in front of
them. That decision is theirs and it is not one a Playbook should make by
default.

## The trap in the whole technique

A callback that arrives late is uncorrelatable. Batch jobs run on their own
schedule, queues drain when they drain, and a lookup landing six hours after the
reading closed belongs to a request nobody can name.

Worse, callbacks arrive from Programs you are not testing. Anyone who has run a
collaborator host for a month knows the pattern: lookups from crawlers, from
sandboxes, from a payload somebody else planted on a shared platform months ago,
all hitting the same subdomain space. Attribution requires a token per request
and discipline nobody maintains under time pressure, and the failure mode is
reporting a finding on a target that never sent anything.
