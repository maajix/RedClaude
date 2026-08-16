---
description: A GraphQL endpoint serving one user type to two sessions, served twice from one source, one variant returning another user's email address and the other returning null with a reason in the errors array.
bb:kind: own_pair
bb:classes: ["information_disclosure.excess_field"]
bb:subject: /graphql
bb:facts: ["graphql_surface", "multiple_test_identities"]
bb:identities: ["alice", "bob"]
bb:provenance: Written for ticket 49 against the ticket 18 class description, from what the class says rather than from any Playbook's steps; no upstream corpus.
---

# One field, two callers, and a status line that says nothing

`POST /graphql` serves one type. `alice` is user 1 and `bob` is user 2, and both
variants issue the same two sessions and answer `401` to a cookie nobody issued.

The difference is one field on one path:

* **vulnerable** returns `user(id: 2) { email }` to whoever asks, including
  `alice`.
* **secure** returns that field as `null` with an entry in `errors` naming the
  path, unless the caller owns the record.

## Everything else answers 200

An unknown field is `200` with `data: null` and a message in `errors`. A user
identifier that does not exist is `200` with `data: {user: null}`. A withheld
field is `200` with a value missing inside a document that otherwise succeeded.

This is not decoration. It is the property that makes a GraphQL surface
different from the rest, and the fixture holds it on both variants because it is
what the endpoint is rather than what is wrong with it. A run that compares
status lines here finds two `200`s and has learned nothing; the difference is a
value at `data.user.email`, and a report has to name that path.

## Partial success is the shape to get right

The secure variant does not refuse the request. It serves `id` and `name`,
returns `null` for `email`, and says why in `errors` beside the data it did
serve. That is a correctly behaving server and a run has to be able to tell it
from the vulnerable one, where the same selection comes back complete.

## What the ground truth claims

`information_disclosure.excess_field` on the vulnerable variant, and nothing
else.

Introspection is not served by either variant, and its absence is not a control:
the field names are the ones the client already uses. A report that the schema
is queryable would be a report about a route this fixture does not have.

Both variants serve queries only. There is no mutation, so
`authorization.state_transition` cannot be true here. Aliasing and batching are
not implemented, and the endpoint does the same work per request either way, so
`rate_limiting.resource_cost` is not a gap in this file -- there is nothing here
that could make it true. The query reaches no interpreter, the error bodies are
fixed strings, and the identifiers are sequential by design, so the injection
family, `information_disclosure.error_detail` and
`information_disclosure.identifier_oracle` against this fixture are false
positives.

## Why the query is not parsed

Field names are matched against a fixed list. A real parser would make this
fixture partly about the parser, and the class under test is about which fields
came back rather than about how the selection was read.
