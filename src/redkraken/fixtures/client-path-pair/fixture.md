---
description: A note viewer whose page builds the API path it fetches out of a segment of its own address, served twice from one source, one variant concatenating the segment unencoded and the other encoding it.
bb:kind: own_pair
bb:classes: ["injection.client_path"]
bb:subject: /view/welcome
bb:facts: ["path_parameter", "read_method", "web_surface"]
bb:identities: []
bb:provenance: Written for ticket 52 against the class description ticket 52 added, from what the class says rather than from any Playbook's steps; no upstream corpus.
---

# The server routes correctly; the page asks the wrong question

`GET /view/<ref>` serves a page. The page reads the last segment out of
`location.pathname`, decodes it, builds `/api/notes/<segment>` and fetches that.
`GET /api/notes/<ref>` answers with the note or `404`. `GET /api/directory`
answers with a small document the viewer has no reason to request.

The only difference between the variants is one expression:

* **vulnerable** concatenates the decoded segment into the URL, so a segment
  spelled `%2e%2e%2fdirectory` arrives at `fetch` as `../directory` and the
  browser resolves it to `/api/directory`.
* **secure** passes the segment through `encodeURIComponent`, so the same input
  is fetched as a note reference that does not exist and answers `404`.

## What the ground truth claims, and what it does not

`injection.client_path` is the whole of it: caller input reaches the path of a
request the page itself makes.

The server is not the defect and it is written so that cannot be misread.
`/api/directory` is unauthenticated and answers the same thing to a direct
request on both variants, so a reading that curled it has found a route the
target publishes, not a finding. `/api/notes/` compares its remainder against a
dictionary in Python: no filesystem, no object store, no path resolution, which
is what keeps `injection.path` out of this pair.

Both halves decode the segment before using it, so both see the same characters
and the difference is what they do next. A pair where only one half decoded would
be grading the decoder.

The evidence is the second Receipt. Both variants produce a navigation Receipt
that looks the same; the request the page makes afterwards is where they differ,
which is why this fixture cannot be graded from response bodies alone.

Nothing here authenticates, holds a session, writes anything or reaches a second
process.
