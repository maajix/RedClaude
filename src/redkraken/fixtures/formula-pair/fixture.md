---
description: A contact form and its spreadsheet export served twice from one source, one variant writing a stored name into a cell exactly as it arrived and the other prefixing an apostrophe when the name begins with a formula character, beside a count that changes on every read and a lookup route that reflects without storing.
bb:kind: own_pair
bb:classes: ["injection.formula"]
bb:subject: /contacts
bb:facts: ["form_request", "reflected_parameter", "state_changing_method"]
bb:identities: ["alice"]
bb:provenance: Written for ticket 53 against the formula class description ticket 53 added, from what the class says rather than from any Playbook's steps; the noisy count and the reflecting lookup route are the precision controls ticket 53 criterion 5 asks for.
---

# A cell that will be a formula on somebody else's machine

`POST /contacts` stores a name from a form body and returns it, and `GET
/contacts.csv` writes every stored name into a spreadsheet, both for a caller
holding a session. Both variants store
the same bytes, return the same acknowledgement and export the same rows. The
difference is one line in the export writer:

* **vulnerable** writes the stored name into the cell as it arrived.
* **secure** prefixes an apostrophe when the name begins with `=`, `+`, `-` or
  `@`, so the cell is text.

Nothing in this fixture evaluates anything, on either half. That is the class:
the interpreter is the spreadsheet application on the machine of whoever opens
the file, and the target's only part in it is writing a cell that will be read as
a formula there.

## What the two arms do here

Store two contacts. One name begins with `=` and one with a letter, and both end
with the same marker.

Against **vulnerable**, the export's cell for the first begins with `=` and the
cell for the second begins with its letter -- the writer added nothing to either.
Against **secure**, the first cell begins with an apostrophe and the second still
begins with its letter, so the writer treated the formula character specifically.

The second contact is why this fixture stores two. A writer that prefixed every
cell would look, from one row alone, exactly like a writer that neutralised a
formula, and only the ordinary row tells them apart.

## The two precision controls, on both variants

`GET /contacts/live` returns a count that increases on every read, so a reading
that never established a baseline has a route it can be wrong about.

`GET /contacts/echo?q=<value>` returns the value and stores nothing, so it never
reaches the export. It is a decoy for the reading that reports this class from a
reflection: the payload comes back in the response on both halves, and a
reflection is not a cell.

## What the ground truth claims, and what it does not

`injection.formula` on the export of the vulnerable variant, and nothing else
anywhere.

The response to `POST /contacts` is identical in shape on both variants and both
reflect the stored name, so nothing separates the halves before the file is
fetched -- which is the honest shape of this class and the reason the evidence is
a match inside an Artifact rather than a differenced response. Nothing here
parses the name, so `injection.query_language`, `injection.template` and
`injection.command` are false against every route: an `=` is a character to this
process and to both halves of it. The stored contacts are held in this process
and rebuilt per run.
