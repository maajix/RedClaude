---
description: Ask which origins a served document grants authority to run inside it, by reading the stored document and the stored variant a URL-valued parameter produced, listing every reference that carries executable authority, and naming the ones the Program's scope does not claim.
bb:category: injection
bb:outputs: ["injection.foreign_resource"]
bb:triggers_all: ["read_method", "url_valued_parameter", "web_surface"]
bb:skills: ["analyse-source", "handle-untrusted-content"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: none
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 52 as the v2 replacement for v1's broken-link-hijacking page, against a new foreign-resource leaf added by ticket 52; the v1 text is attached as a maintainer reference and step 5's refusal is where this Playbook and that page part company.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "content_match", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "content_match", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "content_match", "polarity": "supports", "min_count": 1}]
bb:references: ["broken-link-hijacking.md"]
---

# Every script tag is a delegation

A document that loads a script from somewhere else has handed that somewhere the
same authority its own code has: the DOM, the cookies the page can read, the
requests the page can make. Usually the somewhere is a vendor the target chose.
Sometimes it is a bucket that was deleted, a package name that was unpublished, a
domain that lapsed, or a host named by a parameter the caller supplied.

The subject is a page that takes a URL. The question is which origins end up
holding that authority, and which of those the target never claimed.

## 1. List what the document already delegates to

Take the Artifact the Task names for the route as served with no parameter set,
and run `analyse-source` over it. Every reference that carries executable
authority goes in the list:

* `<script src>`, and any `import` the loaded modules perform
* `<link rel=stylesheet>` and `<link rel=preload as=script>`
* `<iframe src>` where the frame is same-origin or is granted `allow` attributes
* a service worker registration, which outlives the page

Not in the list: images, fonts, media, and anything loaded with an integrity hash
that a browser enforces. Say which ones carried `integrity` and `crossorigin`,
because a pinned digest is the target having already answered this question.

That is a `content_match` on the stored document, in the `control` role: it is
what the page delegates before anyone touches it.

## 2. Add what the parameter can add

The variant is the same route with the URL-valued parameter naming a host that is
not the target's, and it arrives the way the first one did: as a second stored
Artifact, fetched by whoever had a network. This role does not fetch it. Where
the Task names one hash and not two, the parameter half is unanswered, and saying
so is the result -- a document nobody stored is not a document that says nothing.

The reading is where the value lands. A URL in a link's `href` is a redirect
question and belongs elsewhere. A URL that becomes a `src` on a script, a
stylesheet or a same-origin frame is this one: the caller chose which origin runs
in the target's page.

That is the variant `content_match`, and cite the stored bytes rather than a
description of them.

## 3. Ask, for each origin, whether the target claims it

For every name the two lists produced, and from the bytes rather than from the
wire:

* is the registrable domain one the Program's scope claims
* is it a provider's own hostname carrying a name of the target's -- a bucket, an
  app, an account -- and is that name one these bytes use elsewhere
* is the package name one the target publishes, according to the manifest that
  named it
* did the document pin it with an integrity hash a browser enforces

A name the scope claims is the target delegating to itself and is not this claim.
A name outside the scope, with no pin, on a reference that carries execution, is
the candidate.

## 4. Say what would have to be true for it to matter

The list from step 1 is longer than the finding, always. Three questions cut it
down. Two are answered in these bytes and the third is not, and the third is the
ceiling on this reading.

* Is the reference **reached**? A script tag inside a template that never renders
  delegates nothing. Say which page state loads it. Answered here.
* Does the page **grant it anything**? A script with `integrity` cannot be
  swapped. A sandboxed frame with no `allow-same-origin` is a different origin
  and cannot reach the page. Answered here.
* Is the origin **takeable** -- does the name still resolve, and does it resolve
  to a provider's "no such bucket", "no such app", "no such account" answer
  rather than to content? That is an exchange with a third party, and this role
  has no way to make one. It is not answered here and it is not guessed here.

Two yeses and a name the scope does not claim is what this Playbook concludes: a
document that hands execution to a name the target never claimed. Whether that
name is unclaimed today is the separate reading above, and the report says which
of the two it holds rather than letting the first imply the second.

## 5. Do not take the name

This is the refusal that separates the reading from the exploit, and it is not
negotiable by a run that thinks the proof would be cleaner.

Do not register the domain. Do not create the bucket. Do not publish the package.
Do not claim the account. Do not serve anything from any of them. Every one of
those is an irreversible act against a third party who is not in this Program's
scope, taken to prove a claim the previous four steps already establish -- and
each of them makes the tester the owner of a name every visitor to the target
will now load code from.

The unclaimed name goes in the report as a name. What happens to it next is the
target's decision.

## 6. State the claim, and state what would refute it

The Hypothesis is `injection.foreign_resource` on the page. It is supported when
the stored document grants executable authority to an origin the Program's scope
does not claim, whether that origin was already in the document or was put there
by the parameter, against the control list of what the document delegates by
default. It is refuted when every origin with that authority is one the scope
claims, or is pinned by an integrity hash a browser enforces.

Where the parameter instead makes the *server* fetch something, the class is
`injection.request_forgery` and belongs to the Playbook holding it. The
difference is who makes the request, and the Receipts say which -- and neither
those Receipts nor that Playbook are this role's to produce.

## 7. Read the bytes; reach nothing

This Playbook's effects are `read_only`, and the role that loads it has no
network at all. It reads Artifacts by hash, runs offline tools over them, and
writes a list of names.

Nothing here resolves a name, opens a socket towards a third-party origin, or
sends anything anywhere: not one request leaves on this Playbook's account. That
is the strongest form of the rule the topic needs, because every origin in the
list belongs to somebody who never agreed to be tested, and the reading works
without touching any of them.
