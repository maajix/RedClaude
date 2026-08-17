---
description: An authenticated summary route with a numeric window served twice from one source, one variant handing back the conversion failure it caught along with the file, line, build and host that produced it and the other answering one bounded sentence for every value that is not a number, beside a counter that changes on every read and an echo route whose failure quotes the caller's value and nothing else.
bb:kind: own_pair
bb:classes: ["information_disclosure.error_detail"]
bb:subject: /reports/summary
bb:facts: ["authenticated_endpoint", "quantity_valued_parameter", "read_method"]
bb:identities: ["alice"]
bb:provenance: Written for ticket 54 against the error_detail class description from the ticket 18 vocabulary, from what the class says rather than from any Playbook's steps; the noisy counter, the echo route and the out-of-range value are the precision controls ticket 54 criterion 5 asks for. The second target for this class beside ticket 46's error-detail-pair, which stays as it was written.
---

# A failure that described the process that had it

`GET /reports/summary?limit=<n>` answers with up to `n` rows, for a caller
holding a session. The application's own rule is that the window is between 1 and
100, and both variants enforce it identically. The variants differ in what
happens to a value that is not a number at all:

* **vulnerable** lets `int()` fail and hands back what it raised, together with
  the source file, the line, the function, the build and the host.
* **secure** decides what a window is before converting, and answers one bounded
  sentence for every value that is not one.

## What the three arms do here

Two arms carry values that are not numbers -- `limit=all` and `limit=none`.

Against **vulnerable** they come back as two different documents, because each
failure quotes the value that caused it, and both carry
`File "/srv/reports/summary.py", line 41, in summarise`, the build string and the
host name. Against **secure** they are byte for byte the same
`{"error": "limit is a whole number"}`. Invariance between those two arms is this
class's refutation.

The third arm is `limit=0`: a value of the right type that the route's own rule
rejects. It answers `{"error": "limit is between 1 and 100"}` identically on both
variants, and identically on repeat. It is the harmless-error control ticket 54
criterion 5 asks for -- a reading that cannot tell it apart from the other two is
reporting the fact that the route validates, not the fact that it confesses.

## The two precision controls, on both variants

`GET /reports/live` returns a body carrying a counter that increases on every
request, so a reading that skipped its baseline has a route it can be wrong
about.

`GET /reports/echo?limit=` answers `400` with the caller's own value quoted
inside the route's own sentence. It is a decoy for the reading that scores any
failure containing its input as internal detail; what makes the subject's failure
internal is the file, the line, the exception type and the host, none of which
are here.

## What the ground truth claims, and what it does not

`information_disclosure.error_detail` on `/reports/summary` of the vulnerable
variant, and nothing else anywhere.

The catalogue holds a second target for this class, and the two are not
duplicates. `error-detail-pair` was written for ticket 46 as an out-of-class
negative for the authorization family: an anonymous search route with no session,
no object and no controls, whose whole job is to be a real defect that no
authorization Playbook may claim. Widening it would have destroyed what it is
for. This one is what a Playbook about failure behaviour is graded on -- a
session, a window the application has a rule about, a harmless error that trips
that rule, and a decoy that quotes the caller without confessing anything.

The traceback names a source path, and no route serves it: requesting
`/srv/reports/summary.py` is the same bounded `no such route` on both variants,
so nothing here is `information_disclosure.artifact_exposure`. Nothing in the
disclosed text is a credential, a token or a key, so nothing here is
`information_disclosure.credential_material`. The window reaches no store: rows
are a constant list and `limit` only slices it.
