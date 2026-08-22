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

It is not that the Playbook refuses this technique -- it is that this is a
different question, and the split is deliberate. Where the other side of the
split currently sits has a section of its own below, because the answer this
page used to give was wrong three times over.

**Where the browser goes is a navigation claim.** The evidence is a `Location`
header or a navigation the browser performed, and the subject is a redirect
target the caller supplied.

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

## What the other side of the split is, and what it is not yet

This page and the Playbook both used to route the browser side to a class called
`client_side.navigation`, graded by `routing` on a `redirect_target` trigger.
Three claims, none of them true. There is no `client_side` family --
`property_class_families` holds eight and that is not one of them -- so there is
no such class either. `routing` declares `bb:category: business_logic`,
`bb:outputs: ["business_logic.workflow_order"]` and
`bb:triggers_all: ["flow_step", "state_changing_method"]`: it asks whether a step
enforces the steps before it, and it has never asked where a browser is sent. And
`redirect_target` is a real surface fact -- registered at `0032_playbooks.sql:66`
and computed from a `redirects_to` relationship on every rebuild of
`subject_facts` -- that no Playbook in this corpus lists in any trigger set. It is
a fact the harness computes for nobody.

Ticket 113 settled where the reading belongs and carries the argument in full.
The short form is that the leaf goes in the `injection` family, because the
browser's URL resolver is an interpreter and the three browser-side leaves minted
before it -- client channel, client path and foreign resource -- are all under
`injection` for exactly that reason. It is not folded into
`injection.url_authority`, which the Playbook this page hangs off already emits,
because the two are settled by different proofs: `injection.url_authority` is a
disagreement read off a response body, and this one is a `Location` header or a
navigation a browser performed. A fixture that graded both would have to accept
two proofs for one class. The leaf itself is not named here, and not out of
coyness: the family is the part the evidence settles and the name is the part a
maintainer may still change, and a name written down before the row exists is
how this page came to say `client_side.navigation` in the first place.

What has not happened yet is the leaf. Ticket 100 mints it with the fixture that
grades it, and ticket 101 writes the Playbook that emits it and so gives
`redirect_target` its first consumer. Until both land, this page names no class
for the browser side and neither does the Playbook, because naming one the
vocabulary does not hold is the defect ticket 113 was raised about.

## What is kept

One thing the Playbook uses directly: the redirect *chain* as a way to make the
checker and the fetcher disagree. A URL on an allowed host that answers `302` to
a controlled host is a legitimate variant for step 3, because the validator sees
the allowed URL and the fetcher follows the hop. That is a server-side fetch and
it lands here.

The rest -- the phishing value, the address-bar argument, the `Referer` leak --
belongs to the navigation claim, and to the report whichever Playbook eventually
emits it will write. Nothing in this corpus writes that report today.

## The trap in the whole technique

`Location: //evil.test` is not always a redirect anyone follows. Many clients
refuse a scheme-relative jump, many frameworks emit the header and then serve a
body, and a `3xx` in a `curl` transcript says nothing about what a browser does.

Whichever Playbook is asking, the evidence has to be the navigation or the fetch
that actually happened, not the header that suggested one might.
