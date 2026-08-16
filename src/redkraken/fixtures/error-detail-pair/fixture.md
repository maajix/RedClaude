---
description: A search route whose failure path returns an interpreter traceback on one variant and a fixed sentence on the other, carrying no authorization boundary of any kind.
bb:kind: own_pair
bb:classes: ["information_disclosure.error_detail"]
bb:subject: /search
bb:facts: ["query_parameter"]
bb:identities: []
bb:provenance: Written for ticket 46 as the out-of-class negative for the authorization family; ground truth taken from the ticket 18 class description, not from any Playbook's declaration.
---

# A failure that says too much

`GET /search?q=<term>&limit=<n>` returns matching rows. A `limit` that is not an
integer fails, and the two variants fail differently:

* **vulnerable** returns the interpreter's traceback: the module path, the line,
  the frame and the exception text.
* **secure** returns a fixed sentence and a `400`.

## Why this fixture is here

Ticket 46 criterion 1 asks for a meaningful out-of-class negative, and the word
doing the work is *meaningful*. An empty page would be a negative nothing could
fire on; this one has a real defect, in a family no authorization Playbook
declares. A Playbook that reports `authorization.object_ownership` here is not
being asked a hard question -- it is reporting its own class against a route with
no object, no owner and no second session, which is what "fires on everything"
looks like from the outside.

The route deliberately carries no session and no identity at all. There is no
caller to check an object against, so `authorization.*` is not merely absent from
the ground truth: there is nothing here that could make it true.

## What the ground truth claims

`information_disclosure.error_detail` on the vulnerable variant, and nothing
else. The result rows are static, the query is not passed to any interpreter and
the `limit` is compared rather than concatenated, so a claim of
`injection.query_language` against this fixture is a false positive.
