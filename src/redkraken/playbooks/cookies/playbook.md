---
description: Ask whether a session cookie is reachable outside the origin it was issued for, by reading the attributes it carries in the browser's own jar and then observing where that cookie is actually attached.
bb:category: session_handling
bb:outputs: ["session_handling.cookie_scope"]
bb:triggers_all: ["cookie_parameter", "read_method"]
bb:skills: ["browser-evidence", "use-identity"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 50 as the v2 replacement for v1's cookies pack, against the cookie-scope leaf of the ticket 18 vocabulary; v1 shipped a README for this topic and no reference text, so nothing is attached.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_invariant", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "header_policy_observed", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "credential_effect", "polarity": "supports", "min_count": 1}]
---

# A missing flag is a configuration; a cookie that arrives somewhere is a finding

`HttpOnly` absent, `Domain` set to a registrable parent, `SameSite=None`,
`Secure` missing: each of those is a line in a header, and a report that stops
there is a report about a header. The class is `session_handling.cookie_scope`
and it says the cookie is exposed *beyond its intended origin*, which is a claim
about where the cookie goes.

So this Playbook reads the attributes first and then goes and looks.

## 1. Get a session the way a browser gets one

Follow `browser-evidence` and write one mission whose plan names the Identity
slot and drives the subject, so the application issues its own cookie into the
browser's jar. Do not craft one: a cookie this Playbook wrote is a cookie the
server never scoped, and its attributes would be ours.

`use-identity` still governs the credential: the slot is named in the plan, the
proxy attaches it, and nothing here quotes it.

## 2. Record what the server declared

Declare a step that reports the browser's own cookie jar for the origin, and
record from its Artifact every attribute per cookie: name, `Domain`, `Path`,
`Secure`, `HttpOnly`, `SameSite`, `Max-Age` or `Expires`. That is a
`header_policy_observed` observation and it is the control: it is what the server
says the scope is, and everything below is whether the browser agrees.

The jar is where this comes from and not the exchange. A `Set-Cookie` on an
Identity call stays in the sealed wire view, so a mission that could not report
the jar has no control, and a run without the control is inconclusive rather than
a scope finding read off a header nobody saw.

Record the same for the cookie the application uses on its *intended* path. A
target that scopes one cookie tightly and another loosely is the interesting
case, and a run that recorded only the session cookie cannot see it.

## 3. Ask where the cookie actually goes

Extend the same mission's plan to each place the declared scope admits but the
application does not occupy:

* a sibling host under the same registrable domain, when `Domain` names the
  parent
* a path beside the one the application uses, when `Path` is `/`
* the plain-`http` origin of the same host, when `Secure` is absent
* a cross-site request from another origin the Program's scope includes, when
  `SameSite` is `None`

Each of those is one navigation or one request, captured with its network log.
What is being recorded is a request the browser made carrying the session
cookie -- not a header the response contained.

None of this leaves the Program's scope. A sibling host that scope does not
include is out of bounds, and the honest end of that path is to record the
declared `Domain` as surface and stop.

## 4. Ask whether the target honours it there

A cookie that arrives is not yet a session. In the same mission, have the browser
read an identity route at the place the cookie reached, and record whether the
application answered as the logged-in caller. That is the `credential_effect`,
and it is what makes this a scope finding rather than a browser behaviour: the
credential was honoured somewhere its own scope should not have carried it.

It is a step in the plan rather than an exchange beside it. While
`browser-evidence` is loaded the run does not hold `mcp__rk2__http_request`, and
a raw request sent alongside a mission is a Receipt nobody can tell apart from
the browser's afterwards.

## 5. Propose the claim, and say what would refute it

The Hypothesis is `session_handling.cookie_scope` on the application. It is
supported when the browser attached the cookie outside the origin the
application occupies and the target honoured it there, with the declared
attributes recorded as the control. It is refuted when the browser did not
attach it: the request went out without the cookie and the answer was
indistinguishable from an unauthenticated one.

`HttpOnly` is deliberately not the class. A cookie readable from script matters
only where script runs, and whether script runs is `injection.markup` -- a
different Playbook, a different fixture, a different claim. Record the absent
flag as surface and let the scheduler decide what to ask.

## 6. Leave the session as you found it

This Playbook reads. It does not log out, it does not rotate the session, and it
does not carry the cookie anywhere the Program's scope does not include. Its
baseline is `stable_session`, so the runtime drops it beside anything that moves
one.
