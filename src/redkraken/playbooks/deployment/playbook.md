---
description: Ask whether a rule the deployment enforces in front of the application is enforced by the application behind it, by requesting a path the front end refuses and then requesting the same path written a second way that resolves to it, and differencing the two answers against a path whose spelling nobody restricted.
bb:category: authorization
bb:outputs: ["authorization.edge_rule"]
bb:triggers_all: ["read_method", "tech_edge_proxy", "web_surface"]
bb:skills: ["compare-responses"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: none
bb:status: draft
bb:stale_after: 2027-05-15
bb:provenance: Written for ticket 55 as the v2 replacement for v1's deployment pack against a new edge_rule leaf added by ticket 55; the pack's server pages are attached as maintainer references and their desync techniques, their TLS downgrade work and their default-credential lists are refused by step 7.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_invariant", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "response_invariant", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "response_differential", "polarity": "supports", "min_count": 1}]
bb:references: ["apache-tomcat.md", "http-attacks-tls-attacks.md"]
---

# Ask whether the front door's rule reaches the room behind it

A deployment that refuses a path is two programs agreeing about what that path
is. The front end matches the bytes it was handed; the application resolves them
into a route. When the two normalise differently, the refusal is about a string
and the serving is about a route, and a second spelling reaches what the first
was refused.

The subject is a read on a browser-rendered application with a terminating front
end in front of it. The question is whether a rule enforced out there is enforced
in here, and the whole reading is eight requests.

## 1. Find one path the deployment refuses, and say who refused it

Read the Surface for a path that answers `403` or `404` to a caller holding
nothing, and take exactly one. Then say, from the answer itself rather than from
a guess, which of the two programs produced it:

* the front end answered -- the body is a server's own page, the headers are not
  the application's, no application cookie is set
* the application answered -- the body is the application's own refusal, in its
  own shape, beside the headers it sets on everything else

Only the first is this reading's subject. A refusal the application produced is
the application's own check, and asking whether a second spelling gets past it is
`authorization.function_access`, which is a different Playbook and a different
claim.

Complete this step with the path, the refusing status and which program refused.

## 2. Establish the baseline, twice

Send the refused path twice, unchanged, with nothing presented.

Two identical requests, because everything below is measured against this one. A
front end that carries a request id, a ray id or a varying `Age` in every answer
is not byte-stable, and a differential taken against a refusal nobody checked is
noise with a verdict attached.

## 3. Send the second spelling

One request. The same path, written a second way that resolves to the same route,
and it is one of these:

* a dot segment: `/admin/./config`
* a doubled separator: `//admin/config`
* a trailing dot or space on a segment
* one percent-encoded separator: `/admin%2fconfig`
* a matrix parameter on a segment: `/admin;x=1/config`

One arm, one transformation. The variable under test is the spelling, and an arm
carrying two transformations at once cannot say which of them the front end
missed. Everything else -- method, headers, the absence of a session -- is
exactly what step 2 sent.

## 4. Send the control spelling

One request, and this is what keeps the reading honest: the same transformation,
applied to a path nobody restricted -- the application's own index, or any route
that answered `200` before this reading started.

If the control comes back `200`, the transformation is one the deployment serves
normally, and a difference on the arm is about the rule rather than about the
spelling. If the control comes back refused or mangled, the transformation is one
this deployment rejects everywhere, the arm proves nothing, and the reading
returns to step 3 with the next spelling on the list.

Three spellings at most, one control each. With step 2's two baselines, that is
the eight requests.

## 5. Difference the answers

Run `compare-responses` over the arm and the baseline refusal, then over the two
baseline requests. Cite what the script returns.

Arm against baseline is the differential that carries the claim. What counts is
the arm being *served*: a status the baseline did not have, a body the
application produced, a header the application sets. A `403` that changed its
request id is not a difference and the script will say so.

Baseline against baseline says the refusal was stable, which is what makes the
first comparison mean anything.

Then say which program answered the arm, the same way step 1 did. The finding is
that the application answered a request the front end was supposed to have
stopped, and the answer's own shape is what says the application answered it.

## 6. State the claim, and state what would refute it

The Hypothesis is `authorization.edge_rule` on the refused path. It is supported
when the second spelling was served by the application, the first spelling was
refused by the front end, the two baseline requests were invariant, and the
control spelling on an unrestricted path came back normally. It is refuted when
every spelling tried comes back invariant against the baseline refusal -- which
is what a front end that normalises before it matches looks like.

Anything else is inconclusive: a deployment whose front end and application
cannot be told apart from their answers, a path whose refusal turns out to be the
application's own, a spelling the deployment rejects everywhere.

Two neighbours are close.

* Where the second door is a different route that the platform shipped rather
  than a second spelling of this one, the class is
  `authorization.parallel_route` and the Playbook is `cms`.
* Where the front end serves one caller a response it stored for another, the
  class is `information_disclosure.cached_response` and the Playbook is
  `web-cache`.

Cite the Artifacts and the difference the script returned. Quote the arm's status
line and the header that says which program answered.

## 7. The ceiling

This Playbook is `read_only`, holds no session, and sends eight requests -- two
baselines and at most three spellings with a control each -- to one
deployment: two baselines, and at most four arms with a control each.

It does not desynchronise anything. No request in it carries two length headers,
a chunked body with a trailing length, a header the front end and the application
would frame differently, or anything else whose effect lands on the next
connection -- because the next connection belongs to somebody who is not part of
this engagement, and a technique that poisons it has no bounded blast radius and
no undo.

It does not test the channel. It does not renegotiate, downgrade, offer a weaker
cipher, or ask what the certificate says: 018 records that no transport claim can
be settled through the scope proxy at all, so a reading that tried would be
producing a receipt that cannot mean what it says.

It does not go looking for the deployment. It does not scan a port, resolve a
name to find an origin, request a path in order to identify a server, try a
default credential, or send a request to anything other than the scoped ingress
this Task names. Criterion 3 of the ticket that wrote this Playbook is the rule
and it is short: web and API ingress that the Program put in scope, and nothing
underneath it.

Where the deployment refuses every spelling, the verdict is `refuted` and the
reading is over. Where it cannot be told which program answered, the verdict is
`inconclusive` and it routes to an operator.
