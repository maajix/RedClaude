# Cache poisoning and cache deception: the key, and who else asks for it

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

Two techniques that share a mechanism and differ entirely in blast radius.

**Deception**: request a path the cache treats as static and the origin treats as
dynamic -- `/account/settings.css`, `/profile/x.js`, `/me/;.css` -- so the front
end stores an authenticated response under a key that looks like an asset. Then
read it back with no session.

**Poisoning**: find an input the origin reflects and the cache does not key on --
`X-Forwarded-Host`, `X-Original-URL`, `X-Forwarded-Scheme`, a duplicate
parameter, an oversized header that triggers an error page -- send it once, and
every subsequent visitor gets the response it shaped. The v1 page had the header
list, the cache-buster advice, and a section on chaining a poisoned response into
stored XSS.

## The half the Playbook uses

The key, as the thing being reasoned about, and the deception reading -- moved
onto a path the reading itself invented.

That move is the whole design of the attached Playbook and it deserves the
argument rather than the assertion. The measurement wanted is: does the cache key
include the caller? That question is answered by storing one response and reading
it back on the same key. It does not require the key to be one anybody else uses.
Adding `?rk-<random>=1` produces a key with an audience of one, and the omission
being tested -- the session is not in the key -- is unchanged by it, because
adding a query parameter does not add a session.

So the reading keeps its evidence and loses its blast radius. What is given up is
the ability to say "and a real user would have received this", which was never
measured anyway; it was inferred from the same key arithmetic the safe version
performs.

The one assumption to check rather than assume: that the front end does not key
on the query string. Read the invented path once anonymously first. If it answers
differently from the bare route, the query string is in the key and the reading
proceeds knowing that instead of measuring the wrong thing.

## The half that stays out, and why

**Poisoning a shared key**, entirely.

It is not a test. Sending an unkeyed header on a path real users request changes
what those users receive, for a duration set by a TTL the tester does not control
and cannot shorten. There is no undo. The scale is decided by the target's
traffic, not by the tester's intent, and a "harmless" poisoned response is still
the tester deciding what a stranger's browser renders.

Also out:

* **Cache-buster loops** to find the parameter the cache ignores. That is
  hundreds of requests at a CDN, which is a rate profile that gets a program's
  access pulled and is indistinguishable from a scanner.
* **Eviction.** Filling a cache to drop somebody else's entry is an availability
  action, and availability is not a Property class in this vocabulary.
* **Chaining into stored XSS.** A poisoned response carrying markup is a payload
  served to real users from the target's origin.
* **Path-confusion spellings against a live shared route** -- `;.css`, `%3f.css`,
  a trailing `/index.css`. These are the deception technique, and they belong on
  an invented key or nowhere.

## The trap in the whole technique

`X-Cache: HIT` and a nonzero `Age` are the cache saying it stored something, not
the cache saying it stored something private. Almost every hit on almost every
site is a correctly cached public asset.

The reading that matters is the first step and it is the one that gets skipped:
does this route answer differently to different callers at all? If it does not,
every cache header on the page is uninteresting. The attached Playbook puts that
step first, and ends the reading there when the two answers match.
