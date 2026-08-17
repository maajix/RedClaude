# Open redirection: the same parser bug, pointed at a browser

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

Find the `next`, `return_to`, `redirect_uri`, `continue`, `url` or `dest`
parameter. Put somebody else's host in it. Confirm that the target answers a `3xx`
with your host in `Location`, or that its JavaScript calls
`window.location.assign` with your value.

Then the bypass list, which is the same list as the server-side one because it is
the same parsers: `//evil.test` with no scheme, `https:/\evil.test`,
`https://target.test@evil.test`, `https://target.test.evil.test`,
`https://evil.test%23@target.test`, a double-encoded value, and a path-relative
value that the browser resolves against the wrong base.

The page then listed what it is worth: phishing with the target's own domain in
the address bar, stealing an OAuth `code` when the redirect is the
`redirect_uri`, and slipping a token out through the `Referer`.

## Why the Playbook does not run it

It is not that the Playbook refuses this technique -- it is that this question
belongs to a different Playbook, and the split is deliberate.

**Where the browser goes is a client-side routing claim.** The evidence is a
`Location` header or a navigation the browser performed, the subject is a
redirect target, and the class is `client_side.navigation`. `routing` asks it,
with a `redirect_target` trigger and a browser to observe with.

**Where the server goes is this one.** The evidence is what the *server* fetched,
read off the response body, and the subject is a URL parameter the server
consumes. Nothing about a browser is involved.

They share a parser bug and nothing else. A route can be an open redirect and
fetch nothing; a route can fetch the caller's authority and never emit a
`Location`.

**The OAuth escalation is a third Playbook.** A `redirect_uri` that accepts a
foreign host is an authorisation-server registration defect, and `oauth` asks it
with the flow in front of it. Chasing a leaked `code` from here means completing
somebody's authorisation flow, which is not read-only and is not this claim.

## What is kept

One thing the Playbook uses directly: the redirect *chain* as a way to make the
checker and the fetcher disagree. A URL on an allowed host that answers `302` to
a controlled host is a legitimate variant for step 3, because the validator sees
the allowed URL and the fetcher follows the hop. That is a server-side fetch and
it lands here.

The rest -- the phishing value, the address-bar argument, the `Referer` leak --
belongs to the report `routing` writes.

## The trap in the whole technique

`Location: //evil.test` is not always a redirect anyone follows. Many clients
refuse a scheme-relative jump, many frameworks emit the header and then serve a
body, and a `3xx` in a `curl` transcript says nothing about what a browser does.

Whichever Playbook is asking, the evidence has to be the navigation or the fetch
that actually happened, not the header that suggested one might.
