---
description: An authenticated upload route whose destination name the caller chooses served twice from one source, one variant letting the extension on that name decide what the retrieval calls the stored bytes and the other storing under a generated name and serving every upload as an opaque attachment, beside a counter that changes on every read, a name route that stores nothing and a delete route so a reading can undo what it stored.
bb:kind: own_pair
bb:classes: ["injection.stored_file"]
bb:subject: /uploads
bb:facts: ["file_parameter", "path_valued_parameter", "state_changing_method"]
bb:identities: ["alice"]
bb:provenance: Written for ticket 54 against the stored_file class description ticket 54 added, from what the class says rather than from any Playbook's steps; the noisy counter, the name route and the ordinary extension are the precision controls ticket 54 criterion 5 asks for, and the delete route is what lets a reading meet criterion 4's cleanup ceiling.
---

# A name that decided what the bytes were

`POST /uploads?name=<name>` takes a body of bytes and stores it for a caller
holding a session; `GET /uploads/<stored>` gives it back. Both variants reduce
the caller's name to its last segment first, so a traversal in the name is
nobody's finding here. They differ in what the name is allowed to decide:

* **vulnerable** stores under the caller's name and reads the extension off it
  to decide what the retrieval calls the bytes.
* **secure** stores under a name it generated, keeps the caller's as a label, and
  serves every upload as `application/octet-stream` with an attachment
  disposition.

## What the three arms do here

Two arms store the identical bytes `rk-probe-6f21` under two names that differ
only in extension: `rk-probe.html` and `rk-probe.svg`.

Against **vulnerable** the two retrievals come back as `text/html` and
`image/svg+xml`: same bytes, two different things, and the caller picked which.
Against **secure** the two retrievals are identical -- same status, same
`application/octet-stream`, same attachment disposition, same body. Invariance
between those two retrievals is this class's refutation.

The third arm stores the same bytes under `rk-probe.txt` twice and retrieves
both. It answers identically within each variant, which is the control that says
the store is deterministic and the retrieval is not carrying a request id.

## The two precision controls, on both variants

`GET /uploads/live` returns a body carrying a counter that increases on every
request, so a reading that skipped its baseline has a route it can be wrong
about.

`POST /uploads/name?name=` returns the name the route would have stored under,
having stored nothing. It is a decoy for the reading that treats an accepted
filename as a stored file.

## What the ground truth claims, and what it does not

`injection.stored_file` on `/uploads` of the vulnerable variant, and nothing else
anywhere.

The stored bytes are the ASCII string `rk-probe-6f21`. Nothing here is markup,
nothing here is script, and nothing here runs: the property is what the server
says the bytes are, not what a browser would do with them, which is what keeps
this apart from `injection.markup`. Both variants take the last segment of the
name, so nothing here resolves outside a directory and nothing here is
`injection.path`. Uploads are held in memory, capped at four kilobytes, and
`DELETE /uploads/<stored>` removes one, so a reading can leave the fixture as it
found it. Every upload is retrievable only by the session that stored it.
