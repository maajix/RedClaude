---
description: A composer widget embedded in a parent page, served twice from one source, one variant rendering what is typed into it as markup and the other as text, with neither sending the value to the server at all.
bb:kind: own_pair
bb:classes: ["injection.client_channel"]
bb:subject: /widget
bb:facts: ["embedded_document", "read_method", "web_surface"]
bb:identities: []
bb:provenance: Written for ticket 52 against the class description ticket 52 added, from what the class says rather than from any Playbook's steps; no upstream corpus.
---

# The value that never leaves the browser

`GET /` serves a page whose only content is an `iframe` pointing at `/widget`.
`GET /widget` serves the subject: a `textarea#draft`, an empty `div#preview`, and
a script that renders the first into the second.

Two sources feed the same sink, and they are the two this class is about: an
`input` listener on the field, and a `message` listener for a value posted from
whatever framed the document. Neither one sends a request. The only difference
between the variants is which property the value is written to:

* **vulnerable** assigns `preview.innerHTML`, so a value carrying markup is
  parsed as markup.
* **secure** assigns `preview.textContent`, so the same value is a text node.

## What the ground truth claims, and what it does not

`injection.client_channel` is the whole of it, and the thing that makes it that
class rather than `injection.markup` is an absence: this process never sees the
value. Both variants serve `/widget` and then nothing. A reading whose Receipts
show a request carrying the typed value has not tested this fixture's sink, it
has tested something that is not here.

The document is identical between the halves apart from one property name. Same
routes, same status lines, same headers, same length of script -- so a reading
cannot separate the variants by differencing the served bytes of a request that
carries no input, which is the honest shape of this class and the reason a
browser is not optional.

Both halves are framable, with the same `frame-ancestors 'self'` on both. A
widget that could not be embedded would not be an embedded document, and a policy
that differed between the variants would put `transport.header_policy` in one
half of a pair that is supposed to hold one class.

The `message` listener is on both variants and both write it to the same sink.
It is here because the class includes it and a fixture that omitted it would be
grading a narrower thing than it declares -- not because anything in this harness
can post one. A reading that reports this class from having read that listener,
without having driven a value into the sink, has reported source code.

Nothing here authenticates, holds a session, stores anything between requests or
reaches a second process.
