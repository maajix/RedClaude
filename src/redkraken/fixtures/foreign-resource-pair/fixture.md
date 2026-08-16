---
description: A page that embeds a script from an address the caller supplies, served twice from one source, one variant writing a tag for any host and the other loading only one host and pinning what it expects to receive.
bb:kind: own_pair
bb:classes: ["injection.foreign_resource"]
bb:subject: /embed
bb:facts: ["query_parameter", "read_method", "url_valued_parameter", "web_surface"]
bb:identities: []
bb:provenance: Written for ticket 52 against the class description ticket 52 added, from what the class says rather than from any Playbook's steps; no upstream corpus.
---

# The tag is well formed; the host is not checked

`GET /embed?src=<address>` serves a page carrying one `<script>` tag. Without a
`src` both variants load the same default, `https://assets.widgets.invalid/widget.js`.
The difference is what happens for any other address:

* **vulnerable** writes the tag for whatever it was handed, so a caller chooses
  which host executes script in this page.
* **secure** writes the tag only for `https://assets.widgets.invalid/`, pins the
  digest it expects with `integrity`, and otherwise renders a refusal.

Every address named in the fixture is under `.invalid`, which RFC 2606 reserves
and which never resolves. A fixture that named a host somebody owns would reach
that host every time it was graded.

## What the ground truth claims, and what it does not

`injection.foreign_resource` on the vulnerable variant, and nothing else.

`injection.markup` is not in this pair, and the source is written so that cannot
be misread: both halves put the address through the same attribute escape, so a
value carrying a quote or an angle bracket stays inside the attribute on both. A
run that reports markup injection here has reported an escape that is present.

The difference is not whether a tag appears. Both halves emit the same tag for
the default address, and a run that only asked for the default sees identical
documents and has measured nothing. What separates them is which addresses reach
the tag.

There is no Content Security Policy on either half. A policy listing allowed
script sources would answer this pair's question in a header, and header policy
is a different pair's class.

`integrity` is on the secure half only, and it is part of one answer rather than
a second difference: an allow-list says which host, a digest says which bytes,
and a fixture that allowed the host but not the bytes would still be loading
whatever that host served today.

Nothing here authenticates, holds a session, writes anything, or fetches the
address itself. This process emits markup naming a host and never contacts it,
which is what makes the finding readable from the served document.
