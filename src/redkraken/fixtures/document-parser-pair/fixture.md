---
description: An XML order intake served twice from one source, one variant building its lookup predicate by concatenating a field's text and the other escaping it first, beside an acknowledgement counter that changes on every request and an echo route that returns a field without looking it up.
bb:kind: own_pair
bb:classes: ["injection.document_parser"]
bb:subject: /services/orders
bb:facts: ["body_parameter", "state_changing_method", "xml_request"]
bb:identities: []
bb:provenance: Written for ticket 53 against the document_parser class description from the ticket 18 vocabulary, from what the class says rather than from any Playbook's steps; the noisy acknowledgement route and the echo route are the precision controls ticket 53 criterion 5 asks for.
---

# A value that became structure in the second document

`POST /services/orders` takes an XML body, lifts the text of `<reference>` and
looks the order up. Both variants read the same body the same way. The difference
is what happens to the lifted text next:

* **vulnerable** builds the predicate `ref[@id='<text>']` by concatenation, so a
  quote in the text closes the literal early and the rest is read as structure.
* **secure** escapes the text before building the same predicate, so the quote is
  a character in a literal and the predicate always parses.

There are two documents here and only the second one is the subject. The XML the
caller sends is read safely on both halves; the predicate the route then builds
out of one of its fields is the string-built one. That is the shape this defect
actually takes in applications that already switched to a real parser.

## What the two arms do here

Against **vulnerable**, a reference containing `'` leaves the predicate with an
unbalanced quote, the reader refuses it, and the route answers `400` with the
position it stopped at. The same reference with the quote replaced by a letter --
same length, same position, same everything else -- parses and answers `200`.

Against **secure**, both parse and both answer `200`. The pair is invariant,
which is this class's refutation.

The refusal names an offset and nothing else. No module path, no frame, no
exception text: a fixture whose parser error carried a traceback would hold
`information_disclosure.error_detail` beside the class it declares, and a reading
could then pass by reporting the wrong one.

## The two precision controls, on both variants

`POST /services/ack` returns an acknowledgement number that increases on every
request, so a reading that never established a baseline has a route it can be
wrong about.

`POST /services/echo` lifts the same field, returns it and looks nothing up. It
is a decoy for the reading that treats a reflected field as evidence that a
parser acted on it.

## What the ground truth claims, and what it does not

`injection.document_parser` on `/services/orders` of the vulnerable variant, and
nothing else anywhere.

No entity is ever resolved: the body reader lifts one element's text and
recognises no declaration at all, on both halves, so an XXE claim against this
fixture is a false positive. Nothing reaches a shell or a template. The predicate
selects from a fixed list held in this process, so a widened predicate returns
rows that exist here and nothing that belongs to anyone. Nothing is stored.
