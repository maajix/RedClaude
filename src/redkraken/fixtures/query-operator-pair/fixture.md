---
description: A JSON search route served twice from one source, one variant handing a field's value to the matcher whatever type it arrived as and the other requiring a string, beside a cursor that changes on every request and an echo route that reflects the body without matching on it.
bb:kind: own_pair
bb:classes: ["injection.query_operator"]
bb:subject: /search
bb:facts: ["json_request", "state_changing_method", "tech_document_store"]
bb:identities: ["alice"]
bb:provenance: Written for ticket 53 against the query_operator class description ticket 53 added, from what the class says rather than from any Playbook's steps; the noisy cursor and the echo route are the precision controls ticket 53 criterion 5 asks for.
---

# A filter whose value chose its own type

`POST /search` takes a JSON object and returns the records whose owner matches.
Both variants read the same field, hold the same records and answer identically
for a plain string. The difference is one check:

* **vulnerable** passes the field's value to the matcher whatever it arrived as,
  so a one-key object is read as an operator rather than as a value.
* **secure** requires the field to be a string and refuses anything else before
  the matcher is reached.

The matcher understands one operator, `$ne`, and treats any other key as a field
name to look up. That is the whole of the store this fixture pretends to be, and
it is enough, because the property the class turns on is that the *type* of a
value decides what the query means.

## What the two arms do here

Against **vulnerable**, `{"owner": {"$ne": "nobody"}}` widens the match to every
record, because no record's owner is `nobody`. `{"owner": {"eq": "nobody"}}` is
the same shape, the same nesting, the same key length, and `eq` is not an
operator -- so it is read as a field lookup, matches nothing, and returns an
empty set. Two bodies differing in one character, two different answers.

Against **secure**, both are objects rather than strings, both are refused before
the matcher, and both return the same fixed sentence. The arms are invariant
against each other, which is this class's refutation -- and the plain string does
return records on the same variant, which is what says the field works.

## The two precision controls, on both variants

`POST /search/live` returns a cursor that changes on every request. A reading
that never establishes what two identical requests look like will find a
differential here every time, on both halves, with no operator involved.

`POST /search/echo` puts the submitted body back in the response and matches
nothing. It is a decoy for the reading that treats a payload appearing in a
response as evidence that something interpreted it.

## What the ground truth claims, and what it does not

`injection.query_operator` on `/search` of the vulnerable variant, and nothing
else anywhere.

Nothing here concatenates a value into a query string, so
`injection.query_language` is false against every route: there is no expression
to break and no quote that means anything. Nothing reaches a shell, a template or
a document parser. `POST` is the method because that is where JSON bodies live,
and no route stores anything -- the records are rebuilt per process and every
route is a read wearing a writing method.
