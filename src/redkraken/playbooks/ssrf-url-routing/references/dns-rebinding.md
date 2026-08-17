# DNS rebinding: the race between the check and the fetch

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

The technique for beating a validator that resolves the hostname itself. Stand
up an authoritative resolver for a domain you own. Serve a very short TTL. Answer
the first lookup with a public address the allowlist accepts, and the second with
`127.0.0.1` or an internal address. The target's validator resolves, sees the
public answer, approves; the target's HTTP client resolves again a moment later,
gets the internal answer, and connects there.

The page covered the variants: multiple A records so the client picks the second,
`0.0.0.0` on stacks that treat it as loopback, and the hosted services that
provide rebinding as a URL so nobody has to run a resolver.

## Why the Playbook does not run it

**It needs infrastructure and a race.** An authoritative nameserver, a domain,
TTL control, and a timing window measured in whatever the target's resolver
caches. A reading that has to stand that up mid-flight is not a reading, and one
that uses a public rebinding service has routed the target's DNS through a third
party nobody in the engagement chose.

**The whole point of it is to reach loopback and internal ranges.** That is what
the second answer is for. Everything the SSRF reference says about the metadata
endpoint and internal sweeps applies here with a resolver in front of it.

**It is unreliable in both directions.** A caching resolver in the path defeats
it, and when it works the timing depends on the target's connection pool. Both
outcomes are hard to distinguish from the route simply refusing, which makes it a
poor test of anything.

**A refuted result proves nothing.** Rebinding that fails may mean the validator
and the fetcher share one resolution, or may mean a resolver cached. The
Playbook's refutation has to mean something, and this technique's does not.

## What is kept

The idea underneath it, which is the Playbook's whole subject: *the check and the
fetch are two different reads of the same URL, and a defect exists wherever they
can disagree*. Rebinding makes them disagree about DNS. Userinfo makes them
disagree about which substring is the host. A redirect makes them disagree about
which URL is being fetched at all. The last two are demonstrable against a host
the Program controls; the first is not.

Also kept: the correct fix, which belongs in a report about any member of this
family -- resolve once, pin the address, and connect to the address that was
checked.

## The trap in the whole technique

A rebinding "success" is frequently something else. Targets that appear to have
connected to `127.0.0.1` are often connecting to a container's own loopback,
where nothing is listening, and the resulting connection error looks identical to
the one a blocked request produces.

Reporting a rebinding finding therefore usually rests on the resolver's log
rather than on the target's response -- which means the evidence is an arrival,
which means the question being answered is `injection.request_forgery`, which is
`webhooks`, with a correlator and without a race.
