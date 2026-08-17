# CRLF injection and response splitting: refused, and the blast radius is why

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

Get a carriage return and a line feed into a place the application writes into a
response header. The classic sink is a redirect built from a caller-supplied
value: `%0d%0a` in the parameter closes the `Location` line and opens whatever
comes next. Then the encodings, because the first spelling rarely survives --
`%0d%0a`, `%0a` alone, `%e5%98%8a%e5%98%8d` and the other overlong forms some
decoders fold into control characters, the same sequences doubly encoded for a hop
that decodes twice.

Then the yields, in increasing order of severity. A header of the reading's
choosing -- a cookie set on the victim's browser, a caching directive. A whole
second response, so the body after the injected blank line is a document the
reading wrote. And, where a cache sits in front, that document stored under the
real URL and served to everybody who asks for it next.

## Why the Playbook refuses all of it

**The proof lands on the next caller.** The interesting arm is the one that ends
in a cache, and a poisoned cache entry is served to whoever asks next -- people
who are not part of this engagement, for however long the entry lives. There is no
bounded version of that, no undo, and no way to know in advance whether the entry
will be shared. Nothing in this corpus may have an effect whose blast radius is
"whoever connects next".

**The non-cache arms still write somebody's headers.** A `Set-Cookie` the reading
chose, delivered to a browser, is a session-scoped change to a person's client.
That is not `read_only` and it is not the reading's to make.

**The encoding ladder is filter evasion.** Trying seven spellings of one control
character until one survives is exactly what the note about filter bypasses beside
this one refuses, and for the same reason: what it establishes is that a filter
can be defeated, which is a statement about the filter rather than about the
application behind it.

**And the framing is not ours anyway.** The interception proxy parses and
re-serialises every request; where a control character survives the reading's own
egress path at all is a property of the proxy, not of the target. A negative
result would say nothing and a positive one would be unattributable.

## What the Playbook kept

The observation, without the arm. A route that builds a header from something the
caller supplied is worth noticing -- a `Location` assembled from a parameter, a
link in a body built from an authority header -- and step 6 of the Playbook asks
for exactly that: read what the route already returned and say whether a
caller-supplied value appears in a header. That is free, it comes from responses
already collected, and it is the fact whoever holds the right grant needs.

It is written down as an observation and it is never promoted to a claim here. A
value appearing in a header is not a split response, and the Playbook's own class
is about two components resolving a name differently rather than about a control
character surviving a serialiser.

## If a split genuinely looks reachable

Say so, quote the response header the value appeared in, and stop. An operator can
decide whether a cache sits in front of that route, whether the Program's rules
permit an arm that could poison it, and whether a maintenance window is needed.
Establishing that first, from a response the reading already had, is the whole
contribution this Playbook can make to the subject.
