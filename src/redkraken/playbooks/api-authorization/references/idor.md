# Direct object references: where the identifier comes from, and what it proves

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## Why this file sits under a state-transition Playbook

v1 filed identifier work under "IDOR", which is one name covering two different
claims. This corpus splits them, and the split is where a report either holds up
or does not:

* the object named by the request is not checked against the caller --
  `authorization.object_ownership`, and the Playbook that claims it sends one
  request twice under two Identities
* the object is in a state that should forbid the operation --
  `authorization.state_transition`, which is the Playbook this file is attached
  to

Both need a real identifier for a real object, which is what the sections below
are about. Neither is proved by an identifier alone.

## Where the identifiers are

* path segments: `/api/users/1234/profile`, `/orders/ORD-2291/cancel`
* query values: `?id=ABC123`, `?file=report_user123.pdf`
* body fields, including the ones the client never shows: `user_id`, `owner`,
  `account`
* the mismatch pair: `PUT /api/user/456` with `{"user_id": 123}` in the body,
  where the two disagree and only one of them is checked

An identifier that arrives encoded is still the identifier. Base64 (`/api/user/MQ==`),
percent-encoding (`/api/user/%31`) and hashed references all decode to something
the application looked up, and re-encoding an edited value is the same request
with one variable moved.

## Reading state off an identifier's own response

The state-transition reading needs two objects of the same kind in two states.
The cheapest way to get them is the target's own list route, read as the owner:
it names the objects and usually names the state beside each one. An object
whose state has to be guessed is an object this Playbook cannot use, because the
claim is that a transition was forbidden and a guessed starting state cannot say
it was.

## What does not follow from an identifier

* a sequential identifier is not a finding. It is a hint that enumeration is
  cheap, and cheap enumeration of objects the caller owns is not a defect
* an identifier appearing in a response is not a finding either; the response
  reaching a caller who should not have it is, and that is a different class
* an error that differs between "no such object" and "not yours" is
  `information_disclosure.identifier_oracle`, which is worth reporting and is
  somebody else's claim

## Parameter pollution belongs to whoever parses it

`?id=456&id=123` and its body equivalents are worth sending once, because two
parsers in one stack that disagree about which value wins is a real defect. It
is not a state-transition finding: what it shows is a framework and a proxy
reading the same request differently, which the corpus files under
`transport.request_framing` when the disagreement is between hops.
