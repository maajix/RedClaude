---
description: Ask whether a response that varies by caller is stored under a cache key that does not, by storing and reading one response on a unique path nobody else will ever request and never touching a key a real user shares.
bb:category: information_disclosure
bb:outputs: ["information_disclosure.cached_response"]
bb:triggers_all: ["read_method", "tech_cdn", "web_surface"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 52 as the v2 replacement for v1's cache-poisoning page, against a new cached-response leaf added by ticket 52; the v1 text is attached as a maintainer reference and step 2's unique key is where this Playbook and that page part company.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_invariant", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "response_differential", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "response_differential", "polarity": "supports", "min_count": 1}]
bb:references: ["cache-poisoning.md"]
---

# A cache is a key, and the defect is what the key leaves out

Something in front of this application stores answers and hands them to whoever
asks the same question. Which askers count as the same is the cache key, and the
key is usually the method, the host and the path. The session is not in it. The
`Authorization` header is not in it. That is fine as long as the answer does not
depend on them, and the defect is the case where it does.

The subject is a read on a surface a cache sits in front of. The question is
whether an answer shaped by one caller can be handed to another.

## 1. Establish that the answer depends on the caller

Read the route twice: once through `identity_slot`, once with nothing presented.
Store both.

That is the control and it is a `response_differential`. If the two answers are
the same, there is nothing here to leak, whatever the cache does, and the reading
ends. A route that answers identically to everyone cannot expose one caller's
answer to another.

Complete this step with both bodies and the difference between them, named.

## 2. Move to a key nobody else will ever ask for

Everything below happens on a path that this reading invented: the same route
with one added query parameter whose name is a random token generated for this
reading, `?rk-<token>=1`.

That is the whole safety design and it is worth stating in the terms it was
chosen for. A cache key is a string. Adding an unguessable parameter to it
produces a key that no real user will ever request, so whatever gets stored under
it is stored for an audience of exactly this reading. The measurement is
identical -- the key still omits the session, because adding a query parameter
does not add one -- and the blast radius is zero.

Check the assumption before relying on it: read the new path once, anonymously,
and confirm the target answers it the same way it answers the route without the
parameter. A target that varies on unknown parameters has told you the key
includes the query string, and the reading continues on that basis rather than
silently measuring the wrong thing.

## 3. Store the authenticated answer

Request the unique path through `identity_slot`. Read the response and the cache
headers it came with: `Cache-Control`, `Age`, `Vary`, `Expires`, and whatever
`X-Cache`, `CF-Cache-Status` or equivalent the front end publishes.

`Vary` is the target's own statement about the key. A `Vary: Cookie` or a
`Cache-Control: private` on this response is the target saying it already thought
about this, and it is read before anything else is concluded.

## 4. Read the same key with nothing presented

Request the unique path again with no session at all, and run `compare-responses`
over this answer, the step 3 authenticated answer and the step 1 anonymous
answer.

* it matches the authenticated answer: the key did not include the caller, and
  one caller's response was handed to another. That is the claim, and the `Age`
  or the front end's hit indicator is the corroboration.
* it matches the anonymous answer: the key included the caller, or nothing was
  stored. That is the refutation and it is a `response_invariant`.
* it matches neither: record it and stop. A third answer is a second cache layer
  or a rotating upstream, and it is not evidence about this key.

One layer is not the target's and has to be ruled out before any of the three
readings holds. Every request here leaves through the runtime's own proxy, and a
stored answer served from there would look exactly like a stored answer served
from the target. It is ruled out by construction rather than by inspection: the
proxy stores nothing, and the path in step 2 is unique to this run, so nothing on
this side of the wire has ever seen it. Say that the key was fresh, because that
sentence is what makes the `Age` a claim about the target.

Repeat once. A single hit can be a coincidence of timing; two consecutive reads
of the stored answer are the same fact stated twice, which is what a reader
needs.

## 5. State the claim, and state what would refute it

The Hypothesis is `information_disclosure.cached_response` on the route. It is
supported when an anonymous request on a key created by this reading returns the
answer a session produced, against a control showing the two callers get
different answers. It is refuted when the anonymous request keeps getting the
anonymous answer.

A cached answer that contains nothing caller-specific is not this claim even when
the headers look wrong: step 1 is what settles that, and it is first for exactly
that reason.

## 6. One invented key, and no unkeyed input on a shared one

This Playbook's effects are `read_only`, and the reason that is honest rather
than convenient is step 2.

The v1 material this replaces is a poisoning page: it teaches sending an unkeyed
header -- `X-Forwarded-Host`, `X-Original-URL`, an oversized header, a header the
origin reflects -- on a path real users request, so that the answer they get next
is the one the tester shaped. Do not do that here. That is not a test, it is a
change to what every visitor receives, it cannot be withdrawn once the entry
exists, and its blast radius is decided by a TTL the tester does not control.

What this Playbook sends is the ordinary request on a path it invented. It adds
no header the target's front end might key on and reflect. It does not request a
path belonging to another Identity. It does not repeat until an entry expires,
does not attempt to evict anything, and does not send the volume that would.

Where an unkeyed *input* is what has to be tested rather than an unkeyed
*caller*, that reading needs a target-side agreement about what may be poisoned
and for how long, and it is not this Playbook.
