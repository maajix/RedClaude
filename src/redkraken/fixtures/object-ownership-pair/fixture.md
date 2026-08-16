---
description: A note API where one route names an object by path and two sessions are issued, served twice from one source, one variant checking the note's owner against the caller and the other not.
bb:kind: own_pair
bb:classes: ["authorization.object_ownership"]
bb:subject: /notes/2
bb:facts: ["multiple_test_identities", "object_identifier", "path_parameter"]
bb:identities: ["alice", "bob"]
bb:provenance: Written for ticket 46 against the ticket 18 vocabulary, from the class description rather than from any Playbook; no upstream corpus.
---

# Two notes, two sessions, one flag

`GET /notes/{id}` returns a note. `alice` owns note 1 and `bob` owns note 2.
Both variants issue sessions the same way and both refuse an unknown session
with `401`. The only difference between them is one comparison:

* **vulnerable** returns the note to any caller holding a valid session.
* **secure** returns `403` unless the session's user owns the note.

## What the ground truth claims, and what it does not

`authorization.object_ownership` is the whole of it. The vulnerable variant
hands `bob`'s note to `alice`, which is the class's description -- the object
named by the request is not checked against the caller -- and nothing else here
is a defect. The error bodies are fixed strings, the sessions are opaque, the
identifiers are sequential integers on purpose and the route is reachable by
design, so a claim of `information_disclosure.error_detail`,
`authorization.function_access` or `information_disclosure.identifier_oracle`
against this fixture is a false positive rather than a gap in this file.

## Why the 401 is on both variants

A refusal under the second session is only evidence of an enforced boundary if
that session was working at the time. Both variants therefore answer `401` to a
cookie nobody issued and `200` to `bob` asking for `bob`'s note, so a run that
never established the control cannot read the secure variant's `403` as a
boundary and cannot read the vulnerable variant's `200` as one either. The
control is a property of the fixture, not an instruction to whoever tests it.

## Why the pair is one file

`kind: own_pair` is one source, one variant flag and two ports. Two files would
be two applications that drift, and the difference between them is the thing the
fixture exists to state: it has to be one comparison in one place, readable in
the diff of nothing at all.
