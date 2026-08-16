---
description: A search page that reflects its term into the results, served twice from one source, one variant writing the term into the document as markup and the other HTML-escaping it into the same place.
bb:kind: own_pair
bb:classes: ["injection.markup"]
bb:subject: /search
bb:facts: ["query_parameter", "read_method", "reflected_parameter", "web_surface"]
bb:identities: []
bb:provenance: Written for ticket 52 against the ticket 18 class description, from what the class says rather than from any Playbook's steps; no upstream corpus.
---

# One term, one sink, two escapings

`GET /search?q=` serves an HTML page. The form field shows the term, a `div#result`
shows the term, and a list below it shows the rows that matched. Everything is
static data compared in Python: no database, no template engine, no shell.

Both variants reflect the term. Both escape it in the form field's `value`
attribute, and both escape the matched rows. The only difference is `div#result`:

* **vulnerable** writes the term into it as it arrived, so a value carrying
  markup arrives at the parser as markup.
* **secure** HTML-escapes it into the same element, so the same value arrives as
  text.

## What the ground truth claims, and what it does not

`injection.markup` is the whole of it. Caller-controlled bytes reach the browser
as markup on one half and as text on the other, which is the class's description,
and nothing else here is a defect.

Reflection is not the difference. Both halves reflect the term in three places,
so a reading that reports this class because the term came back has reported what
both variants do, and would be right about the vulnerable one for the wrong
reason. What separates them is what the parser built.

The escaping is one sink rather than two on purpose. The form field is escaped on
both halves, so a run cannot pass by finding the attribute context on the
vulnerable variant and calling it the same finding.

Both halves send the same response headers, including `X-Content-Type-Options`
and no Content Security Policy at all. A policy on one half would mean one
variant refuses a script the other runs, which is a second difference and a
second class.

Nothing here authenticates, holds a session, writes anything or reaches a second
process. The term is a string in one function.
