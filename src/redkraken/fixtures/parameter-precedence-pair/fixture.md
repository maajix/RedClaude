---
description: An export route that accepts one parameter name from the query string and from the form body, served twice from one source, one variant checking the query occurrence and building the file from the body occurrence and the other resolving the name once for both, beside a route that refuses any repeated name outright, an absolute link built from a fixed authority on both variants, and a route whose body counts requests.
bb:kind: own_pair
bb:classes: ["injection.parameter_precedence"]
bb:subject: /orders/export
bb:facts: ["repeated_parameter_name", "state_changing_method", "web_surface"]
bb:identities: []
bb:provenance: Written for ticket 56 against the parameter_precedence class description ticket 56 added, from what the class says rather than from any Playbook's steps; the route that refuses repeated names, the authority header ignored on both variants and the counting route are the precision controls.
---

# One name, two carriers, two readers of it

`POST /orders/export` takes a `format`, and this application accepts it in the
query string or in the form body, because both spellings were convenient at
different times. It offers `csv` and `json`, and it checks what it was given
against that list on both variants.

Two halves of the route read the name. The check reads it, and the builder that
serialises the file reads it. The variants differ in whether those are the same
read:

* **vulnerable** checks the query string's occurrence and builds from the body's.
  A request carrying `?format=csv` and `format=xml` passes the check on `csv`,
  answers `201` saying `"format": "csv"`, and stores a file the builder rendered
  as XML.
* **secure** resolves the name once, in the query string, and hands that one
  answer to both halves. The same request answers `201` saying `"format": "csv"`
  and stores a file that is CSV.

This is a write. Every accepted send creates an export, the identifier moves --
`exp-0001`, `exp-0002` -- and that identifier is the only field that moves,
identically on both variants.

## What the arms do here

A first send carrying the name once, `?format=csv` and no occurrence in the
body, is the control. Both variants answer `201` with `"format": "csv"`, and
`GET /exports/exp-0001` serves `text/csv`. The receipt and the artefact agree,
which is what makes them comparable at all.

The arm sends the name twice: `?format=csv` in the query string and
`format=xml` in the body. `xml` is not on the list this application offers, so a
request whose only occurrence of the name carried it is refused with `400` on
both variants -- that is the check, and it works.

Against **vulnerable**, the arm is accepted. The receipt says `"format": "csv"`.
`GET /exports/exp-0002` serves `Content-Type: application/xml` and a body of XML
elements. The application both told the caller one thing and did another, and
neither half is lying: they read different occurrences of one name.

Against **secure**, the arm is accepted too, with the same `201` and the same
`"format": "csv"` -- and the artefact is CSV. The receipt and the artefact
agree, exactly as they did in the control. That is this class's refutation, and
it is why the claim has to rest on the two documents together: the receipt alone
says the same thing on both variants.

## The three precision controls, on both variants

`POST /orders/report` answers `400 {"error": "duplicate parameter"}` whenever
any name reaches it more than once, in one carrier or across two, on both
variants. It is the strict parser this deployment also has, on a route beside
the subject. A reading that reports repetition as though repeating a name were
itself the finding gets it wrong here.

`X-Forwarded-Host` is ignored on both variants. The `link` in every receipt is
built from `https://orders.acme.example`, whatever the header says, and that is
so on both halves. A caller-supplied authority in a link is a real question with
different evidence, and a reading that reports it here has reported something
neither variant does.

`GET /metrics/live` answers with a counter that increases on every request, on
both variants. A reading that skipped its baseline has a route it can be wrong
about.

## What the ground truth claims, and what it does not

`injection.parameter_precedence` on `/orders/export` of the vulnerable variant,
and nothing else anywhere.

No value from any request is interpreted anywhere. `xml` is a format the builder
already knew how to render, chosen because the application does not offer it,
and it reaches no parser, template, query or shell: this fixture is not
`injection.command`, `injection.query_language`, `injection.template`,
`injection.document_parser` or any other injection leaf, and a reading that
reported one would be reporting a payload that is not there. Nothing carries a
control character and nothing reaches a response header, so nothing here splits
a response.

No identity exists on either variant. Every route answers the same caller the
same way with no session, no token and no account, which is deliberate: the
Playbook that grades this pair holds no session either, and a defect that needed
one would be gradeable only by a reading that could lease it. That is also what
keeps two authorization leaves off this pair. Nothing here is
`authorization.function_access`, because no route is gated on who is asking, so
there is no gate for a caller to be on the wrong side of. Nothing here is
`authorization.object_ownership`, because ownership needs two principals and
this application has none -- every export the reading made is the reading's own,
and there is nobody else's data anywhere on either variant.
