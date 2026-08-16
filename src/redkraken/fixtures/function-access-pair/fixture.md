---
description: A gRPC-Web surface with an open method and an administrator method, served twice from one source, one variant serving the administrator method to any session and the other answering grpc-status 7, both under HTTP 200.
bb:kind: own_pair
bb:classes: ["authorization.function_access"]
bb:subject: /billing.Admin/ListAll
bb:facts: ["multiple_test_identities", "tech_grpc"]
bb:identities: ["alice", "bob"]
bb:provenance: Written for ticket 49 against the ticket 18 class description, from what the class says rather than from any Playbook's steps; no upstream corpus.
---

# The method is the path, and the answer is not the status

Two methods. `POST /billing.Invoices/ListMine` serves whoever is calling their
own invoices, on both variants and for both sessions. `POST
/billing.Admin/ListAll` serves everybody's, and it is the one thing the variants
disagree about:

* **vulnerable** serves it to any session, `grpc-status: 0`.
* **secure** serves it to `alice` and answers `bob` with `grpc-status: 7`,
  PERMISSION_DENIED.

Every response is HTTP `200`. The refusals are `200`. The unknown method is
`200`. A run that reads the status line here finds no difference anywhere, which
is the point: the decision is in the `grpc-status` value and a report has to
quote it.

## The three refusals are three different answers

* `16` UNAUTHENTICATED -- the caller was not identified. Both variants, for a
  cookie nobody issued.
* `7` PERMISSION_DENIED -- the caller was identified and refused. Secure
  variant, on the administrator method.
* `12` UNIMPLEMENTED -- there is no such method. Both variants, for any other
  path.

`12` is the trap. It is what a guessed method name returns, and it means the
server has nothing there rather than that something was defended. A run that
reads `12` as a boundary has read an absence as a decision.

## Why the open method is on both variants

It is the control. `bob` getting `7` on the administrator method is evidence of
an enforced boundary only if `bob`'s session was working, and the way to
establish that is a method `bob` is served. Both variants serve it identically,
so a run that never called it cannot read the secure variant's `7` as a boundary
and cannot read the vulnerable variant's `0` as one either.

## What the ground truth claims

`authorization.function_access` on the vulnerable variant, and nothing else. The
boundary that fails is on the operation: `ListAll` is a method one role may call
and the vulnerable variant does not check the role.

No method here names an object the caller could substitute -- `ListMine` is
scoped by the session and takes no identifier -- so
`authorization.object_ownership` is not a gap in this file, there is nothing
here that could make it true. Nothing mutates, the request body is read and
discarded, the messages are fixed strings and the invoice identifiers are not
guessable inputs to anything, so the injection family,
`authorization.state_transition`, `information_disclosure.error_detail` and
`information_disclosure.identifier_oracle` against this fixture are false
positives.

## Two deviations from the wire, stated

The codec is JSON rather than protobuf, and `grpc-status` is a response header
rather than a trailer frame -- which is what a Trailers-Only response looks like
on the wire. Both keep the fixture readable by an ordinary HTTP client, and
neither touches the property under test: what decided the call is not the HTTP
status.
