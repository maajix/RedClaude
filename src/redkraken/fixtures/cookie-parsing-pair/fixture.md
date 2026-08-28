---
description: An account route behind a session cookie, served twice from one source, one variant admitting a request by the first `session` in the header and answering it as the last, and the other reading the header once and refusing a repeated cookie name.
bb:kind: own_pair
bb:classes: ["session_handling.cookie_parsing"]
bb:subject: /account
bb:facts: ["authenticated_endpoint", "cookie_parameter", "read_method", "repeated_parameter_name"]
bb:identities: ["alice", "bob"]
bb:provenance: Written for ticket 100 against the class description this migration adds, from what the class says rather than from any Playbook's steps; no upstream corpus.
---

# Two readers, one header

`POST /session` checks a user and a password and issues
`session=...; Path=/; HttpOnly; SameSite=Lax`. Both variants issue exactly that
line, from the same route, with the same attributes.

`GET /account` reads it back twice, because two decisions are taken about it:

* the gate decides **whether** the request is authenticated, and walks the
  header from the front;
* the handler decides **whose** account to answer with, and walks it from the
  back.

The variants differ in whether those two readings can disagree:

* **vulnerable** keeps both readers. A header carrying
  `session=s-alice-4f2c; session=s-bob-9d17` is admitted as `alice` and answered
  with `bob`'s record, and the answer says so in `admitted_as`.
* **secure** reads the header once, and answers `400` naming `session` when the
  cookie arrives more than once.

## Why the difference is not a missing check

The vulnerable variant checks the session. It checks it against a value that is
really in the header, from a caller who really holds it. What it does not do is
check the same value twice, and that is the class: two components parsing one
header and acting on different answers from it.

A pair whose vulnerable half simply skipped authentication would grade a run for
finding a missing gate, which is `authorization.function_access` and has its own
case in this catalogue.

## The control

The `Set-Cookie` line, which is identical on both variants, and the single-cookie
request, which both variants answer alike. A run that reports a difference
without those two has reported that the fixture has two ports.

## What is not here

`session_handling.cookie_scope` is the neighbouring class and it is about where
a cookie is honoured -- domain, path, scheme. Nothing here varies an attribute
or serves a second host, and both variants set the same ones, so scope cannot be
what a differing answer read.

`injection.parser_differential` is the same shape one layer out, over a request
body rather than a cookie header, and it has its own pair. This one is the
cookie header specifically, because the header is the only place in HTTP where
a repeated name is ordinary rather than a defect.

Nothing here writes a cookie from script, tosses one from a sibling origin or
expires a session. Those are `injection.markup`, `session_handling.cookie_scope`
and `session_handling.lifetime`.

## Ground truth

* **vulnerable** holds `session_handling.cookie_parsing`. The gate and the
  handler read different `session` values out of one header, and the response
  is the second caller's record.
* **secure** holds nothing this catalogue declares. One reading, and a repeated
  cookie name is refused.
