---
description: An activity view over one process-wide record of requests, served twice from one source and read by two sessions, one variant handing each caller the whole record and the other only the entries that caller made, beside a build and region field both variants publish and an archive path both variants name and neither serves.
bb:kind: own_pair
bb:classes: ["information_disclosure.log_record"]
bb:subject: /api/activity
bb:facts: ["authenticated_endpoint", "multiple_test_identities", "tech_telemetry"]
bb:identities: ["alice", "bob"]
bb:provenance: Written for ticket 55 against the log_record class description ticket 55 added, from what the class says rather than from any Playbook's steps; the published build and region fields and the named but unserved archive path are the precision controls ticket 55 criterion 4 asks for.
---

# The record the application keeps, and who gets to read it

Every request that reaches this application is written into one record: the
caller it came from, the method, the path and the query string. `GET
/api/activity` reads that record back, for a caller holding one of the two
sessions this fixture issues.

The two variants differ in one clause:

* **vulnerable** returns the whole record, whoever is asking.
* **secure** returns only the entries the asking caller made.

The record is seeded with one request from each Identity, so the leak is present
before a reading sends anything, and it grows as the reading works -- the
activity view records its own reads, which is the closest thing this fixture has
to noise and is exactly what a real one does.

## What the two arms do here

Against **vulnerable**, `alice`'s read of `/api/activity` returns entries
attributed to `bob`, including `GET /api/notes?ref=quarterly-2026` -- a path and
a query string belonging to a caller who is not `alice`. Any further request
`bob` makes appears in `alice`'s next read, which is what makes the leak
demonstrable rather than a claim about seeded data.

Against **secure**, `alice`'s read carries only entries attributed to `alice`,
and `bob`'s read carries only `bob`'s. Every entry either caller can see is one
they made. That is this class's refutation, and `bob`'s own view is what makes it
mean something: an entry absent from `alice`'s view and present in `bob`'s was
recorded and withheld, rather than never recorded at all.

## The three precision controls, on both variants

Every response from `/api/activity` carries `build` and `region` beside its
entries, identically on both variants. They are public metadata -- the same
strings the application publishes elsewhere -- and they are the decoy for a
reading that reports whatever it finds in a telemetry document.

Every response also names `archive` as `/api/activity/archive`, and that route
answers `404` on both variants. Naming a path is not serving one: a reading that
reports the archive as exposed, without having asked for it, has claimed
something the fixture does not hold.

Alice's seeded entry carries `sample_token=rk_sample_000000000000` in its query
string. That is the credential decoy, and where it sits is the whole of it: in
the reading Identity's own record, on both variants, honoured by no route here.
A reading that files it has filed `information_disclosure.credential_material`,
which is `secrets`' class and `credential-material-pair`'s target, on a string
that buys nothing and never differed between the two halves. Telling that pile
apart from public metadata and from another caller's request data is what this
fixture asks for.

## What the ground truth claims, and what it does not

`information_disclosure.log_record` on `/api/activity` of the vulnerable variant,
and nothing else anywhere.

No entry anywhere carries a credential that works. The one credential-shaped
string in the record is the decoy above, it is in both variants, and no route
here honours it -- so nothing in this fixture is
`information_disclosure.credential_material`, which `credential-material-pair`
already grades and which requires the target to honour the string rather than
merely to carry it. That is deliberate: a fixture whose log entries leaked a
working secret would be positive for two classes at once, and no target here may
be. No route
here takes a record identifier from the caller -- the view is asked for by
itself -- so this is not `authorization.object_ownership`. Nothing fails, and no
body is a trace or a parser message, so this is not
`information_disclosure.error_detail`. `/api/notes` behaves identically on both
variants and shows each caller only their own notes, so the only place either
caller sees the other is the record. Nothing here writes anything a caller
named, and no file is served from any tree.
