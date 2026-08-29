---
description: Ask whether a rule the deployment enforces in front of the application is enforced by the application behind it, by asking one refused path again under a second spelling that resolves to the same route, under each method the tool contract offers, under a client address the caller writes, and under a path the router reads out of a header the authoriser never saw, each arm against a control on a path nobody restricted.
bb:category: authorization
bb:outputs: ["authorization.edge_rule"]
bb:triggers_all: ["read_method", "tech_edge_proxy", "web_surface"]
bb:skills: ["compare-responses"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: none
bb:status: draft
bb:stale_after: 2027-05-15
bb:provenance: Written for ticket 55 as the v2 replacement for v1's deployment pack against a new edge_rule leaf added by ticket 55; the pack's server pages are attached as maintainer references and their desync techniques, their TLS downgrade work and their default-credential lists are refused by the closing section. Rewritten for ticket 101 against the merged ledger, which carries five readings, one lead and five refusals for this slug; three readings are new and two of them became closeable only when ticket 211 let a Test action state its headers. One key moved -- the refuted variant row now asks for the kind its own supported row asks for, because close_test_replay derives one kind per role from the specification and a refuted leg asking for a second kind is a leg nothing can write.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_differential", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "response_invariant", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "response_differential", "polarity": "supports", "min_count": 1}]
bb:references: ["apache-tomcat.md", "http-attacks-tls-attacks.md"]
---

# Ask whether the front door's rule reaches the room behind it

A deployment that refuses a path is two programs agreeing about what that path is. The
front end matches the bytes it was handed; the application resolves them into a route, and
takes the verb, the caller's address and the target itself from places the matcher never
looked. Where they disagree, the refusal is about a string and the serving is about a
route. Four shapes of that, one reading each, on a browser-rendered application with a
terminating front end.

Every request goes through mcp__rk2__http_request. The run that settles a claim is a Test
proposed with mcp__rk2__propose_test and closed by close_test_replay, the only writer of
the transition a Finding needs, which derives the outcome and the Observation kind from
the Test's own assertions. Every specification below carries the same four actions, never
re-ordered, because the ordinal binds an action to its Receipt. Actions 1 and 2 carry the
role baseline: that reading's plain request, twice unchanged, asserted body_equals. Action
3 carries the role control, named by no differing assertion, which leaves it a
response_invariant. Action 4 carries the role variant: the arm, asserted status_differs or
body_differs against action 1, which makes it a response_differential whichever way the
run comes out. Fewer than three actions, or a missing role, is refused at propose_test and
never runs. Since ticket 211 an action states its own headers, which is what puts sections
5 and 6 on the Finding path; a setup or a cleanup step still carries a method and a url
and nothing else.

## 1. Fix one refused path, establish it twice, and say who refused it

Read the recorded surface with mcp__rk2__get_attack_surface for a path that answers 403 or
404 to a caller holding nothing, and take exactly one. Send it twice unchanged through
mcp__rk2__http_request; register_proxy_artifacts files the request and the response
Artifact of each send against its Receipt, and the two sends are actions 1 and 2 of every
specification below. body_equals and body_differs read the response body digest alone, so
a varying Age or Date header never moves them and a refusal page that renders a request id
or a timestamp INTO its body always does; a differential taken against an unchecked
refusal is noise with a verdict attached.

Plan this reading, and every reading below it, without an Identity slot. The subject is
what the deployment answers a caller holding nothing, and a leased Identity owns Cookie
and every header it declares for the origin: it would put a session on both arms and
quietly change what the refusal is a refusal of.

Then say, from the answer rather than from a guess, which program refused. The front end's
tell is a server's own error page beside a Server, Via, CF-Ray or X-Cache value the
application's routes do not carry; the application's tell is its own refusal, in its own
shape, beside the headers it sets on everything else. Read that off the non-cookie
headers, because the wire response filter strips set-cookie, set-cookie2 and
www-authenticate from the agent view on every path. Fix what the application's header set
is from one unrestricted route that answers 200, or the attribution is an adjective, and
file it as a header_policy_observed Observation through mcp__rk2__submit_mission_result,
which promote_proposal writes. Only a front-end refusal is this Playbook's subject: a
refusal the application produced is its own check, and asking whether a second spelling
gets past it is authorization.function_access. This section establishes and attributes; it
closes no Test and grades nothing.

## 2. Ask whether the two programs normalise at different times

One arm, one transformation, resolving to the same route: a doubled separator
//admin/config, a trailing dot or an encoded trailing space on a segment, one
percent-encoded separator /admin%2fconfig, or one matrix parameter /admin;x=1/config.
Method and headers are byte-identical to the baseline, and an arm carrying two
transformations at once cannot say which the front end missed. The control is that same
single transformation applied to a path nobody restricted, the application's index or a
route that answered 200 before this reading started, and its Receipt must show a 200.
Where it comes back refused or mangled the deployment rejects that spelling everywhere,
the arm proves nothing, and the reading moves on. Three spellings at most, one control
each. Each arm goes out through mcp__rk2__http_request as action 4 of its own
specification, proposed with mcp__rk2__propose_test, and close_test_replay writes the
response_differential that settles it.

## 3. The spellings a Test cannot state

This step is a lead and nothing grades its outcome. The specification checker refuses any
path segment that is `.` or `..`, and any `%2e` anywhere in a specification url, while the
door normalises nothing and forwards all of them verbatim. So /admin/./config, the `..%2f`
climb and the `..%252f` family are performable through mcp__rk2__http_request and
unspellable in a Test. Send them once section 2's spellings are exhausted, file the
difference as a response_differential Observation through mcp__rk2__submit_mission_result,
which promote_proposal writes, and say which arm produced which. No Test closes on these,
so they produce an Observation and an argument, never a settled claim.

## 4. Ask whether the rule names verbs rather than resources

The method enum is exactly GET, POST, PUT, PATCH, DELETE, HEAD and OPTIONS, so the survey
is bounded by the tool contract and no eighth verb is spellable. Send the refused path
under HEAD and under OPTIONS, one arm each; the method is one of the fields the replay
lane binds a Receipt to its action by, so each arm is a Test action. The control is the
same verb against an unrestricted path, which must be served or must 405 the way this
deployment does everywhere, or a 200 on the arm is a deployment treating every unusual
verb alike rather than a rule with a verb list. An Allow header worth recording is filed
beside the Test as a header_policy_observed Observation through
mcp__rk2__submit_mission_result. Do not send PUT, PATCH or DELETE. This Playbook is
declared read_only, a 200 to a DELETE is a deletion, and a method outside the safe set
raises the call to approval_required at the door in any case. Ask for this Task to be
parked with mcp__rk2__park_for_human under `question_code` destructive_action, name this
run's own Task in `task_label` and the three withheld verbs, and let a person decide.

## 5. Ask whether the decision is made on an address the caller writes

X-Forwarded-For, X-Real-IP, X-Client-IP and X-Custom-IP-Authorization are in neither the
hop-by-hop set nor the internal prefix, so they reach the target as written, and a leased
Identity does not own them either. A loopback literal is a header VALUE here and not a
destination this harness dials, so the address refusal guarding our own url does not reach
it.

The arm sets exactly one of those headers to a loopback or internal literal. The control
sets the same header to an ordinary public address the deployment has no reason to trust,
and its Receipt must still show the refusal: that is what separates a rule that trusts
this header from an edge that any extra header confuses. Where the control is served too,
stop, report inconclusive with the control's behaviour named, and do not sweep an address
range through the header. The mechanism edge is a credential_effect filed through
mcp__rk2__submit_mission_result, because a refusal becoming a 200 in answer to a trust
header a caller wrote is a response to a presented credential. Stop when the four names
are exhausted; they are also the only caller-writable input to a per-origin limit, which
is rate_limiting.per_origin and another Playbook's.

## 6. Ask whether the router reads a path the authoriser never saw

X-Original-URL, X-Rewrite-URL, Request-Uri and x-middleware-subrequest match the served
header-name pattern, none is hop-by-hop, and all four forward. The component that
authorises reads the request line while the component that serves reads the header, so the
path authorised and the path served are two paths. Here the plain request of actions 1 and
2 is an ALLOWED path rather than the refused one. The arm is that allowed path with the
refused path named in exactly one override header, asserted body_differs against action 1,
one header name per arm and three arms at most. The control is the same allowed path with
the same header naming a path that does not exist: where its Receipt shows the allowed
path's own body the header is ignored and any difference on the arm was about something
else, and where it shows a 404 for the named path the header reaches the router. Where the
refused path's own content arrives under an allowed request line, file reflected_input
beside the Test through mcp__rk2__submit_mission_result as the edge that names what came
back, and do not fuzz header names: a name this family does not read answers nothing.

## 7. State the claim, and state what would refute it

The Hypothesis is authorization.edge_rule on the refused path, carried to a Finding with
mcp__rk2__propose_finding once a Test has settled it. This section proposes no Test of its
own and grades nothing. It is supported when one arm was served by the application, the
plain spelling was refused by the front end, the two baseline reads were invariant, and
that arm's own control behaved as its section requires. It is refuted when every arm comes
back invariant against the baseline refusal, which is what a front end that normalises
before it matches, lists no verbs and reads no caller header looks like. Then say which
program answered the arm, by section 1's reading of its headers: the finding is that the
application answered a request the front end was supposed to stop, and a report reading
that off the status alone has published half a reading. Where the two cannot be told apart
the verdict is inconclusive, and that halt is reported through this Task's own record,
because no question code in the served set says a reading ran out of tells.

Two neighbours are close. Where the second door is a route the platform shipped rather
than a second spelling of this one, the class is authorization.parallel_route and the
Playbook is `cms`; where the front end serves one caller a response it stored for another,
it is information_disclosure.cached_response and the Playbook is `web-cache`. Cite the
Artifacts, the `compare-responses` result over each pair, and the attributing header.

## 8. The ceiling, and the five readings this slug refuses

This section performs and grades nothing. This Playbook is read_only, holds no session,
and sends per reading two baselines and at most three arms with a control each, against
one deployment. Five readings are refused rather than dropped, so none is re-proposed as
cheap. The transport audit that is the whole of the attached
`http-attacks-tls-attacks.md`: a differential across two handshakes is about the proxy's
handshake, its scanners are scanners against a port, and the downgrade and memory-read
attacks have no read_only version. Making an intermediary drop the header the decision
rests on, by naming it in a Connection field or by sending one header name twice: the
forwarding filter and an object-shaped header block refuse those between them. A
caller-pinned Host, and with it the vhost and origin-behind-the-CDN family, because the
wire headers are rebuilt as the url's authority plus what forwards, though
X-Forwarded-Host, X-Host and X-Original-Host do forward and section 6 reads those. A
listener that is not the scoped web ingress, an AJP connector or an origin address
inferred from hosting history, where the scope grant is the rule and not the url pattern.
And the management console of `apache-tomcat.md`, its shipped credentials and its archive
upload: record that the console exists and present nothing to it, and where a credential
is about to be presented ask for this Task to be parked with mcp__rk2__park_for_human
instead, under `question_code` credential_needed and this Task's own label in
`task_label`.

4 of 8 steps cannot be graded.
