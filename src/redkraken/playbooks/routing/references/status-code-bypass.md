# Status-code bypasses: which of them belong to this corpus, and which do not

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 list was

A long catalogue of ways to turn a `403` into a `200`: path spellings, method
swaps, proxy headers, protocol downgrades, host tricks, hitting the origin IP
directly. It is a good catalogue and most of it is out of scope for the Playbook
this file is attached to. The split is worth stating plainly, because a run that
works down the list will leave the engagement's boundaries before it reaches the
bottom.

## The half the Playbook uses

Different spellings of the *same recorded route on the same host*:

```
/checkout/confirm      -> 403
/checkout/confirm/     -> ?
/checkout//confirm     -> ?
/checkout/./confirm    -> ?
/Checkout/Confirm      -> ?
```

These work because two components disagree about what the path is. A proxy
matches the literal string and passes it on; the application normalises it and
routes it. The rule was written against the string, so the normalised form never
meets the rule. Percent-encoded separators (`%2f`, `%2e`) are the same
disagreement with a decoder in the middle of it.

The other half the Playbook uses: read what came *with* a refusal. A `302` to
the login page that also carries the step's own response body is the step having
run and the redirect being cosmetic. A `403` page whose body contains the
created object's identifier is the same thing. The status line is a claim the
application makes about itself, and the body is frequently a better witness.

## The half that stays out, and why

* **Origin IP and CNAME contact.** Reaching the host behind the proxy is
  reaching a different host. The Program named what is in scope, and an IP that
  answers the same content is not automatically in it.
* **Protocol downgrade to plain HTTP, or a different port.** Same reason: not
  the recorded service.
* **Proxy and client-IP headers** -- `X-Forwarded-For: 127.0.0.1`,
  `X-Original-URL: /admin`, `X-Rewrite-URL`, hop-by-hop tricks. These are real
  and they are a *different claim*: the front of the stack and the back of the
  stack disagree about who the caller is or what they asked for. That is
  `transport.request_framing` or `transport.header_policy`, not workflow
  ordering, and it belongs to the Playbook that holds those classes.
* **Reaching a route the flow does not contain at all** -- an admin console, a
  debug handler. `authorization.function_access`.
* **Stressing the server with common requests**, which the v1 list mentions in
  passing. Availability is not a Property class in this vocabulary and nothing
  here produces it.
* **Archive lookups** for a file that used to be public. Useful reconnaissance,
  and evidence about the past rather than about this target now.

## The trap in the whole technique

A `200` is not access. Half of these spellings return `200` with an error page,
a login form, or an empty body, and a run that grades on the status line alone
will report every one of them.

This is why the attached Playbook never grades a spelling on its own response.
It sends the spelling, then reads the authoritative outcome route and differences
that against the completed-flow answer and the pristine answer. The status code
selects what is worth reading; the state says whether anything happened.
