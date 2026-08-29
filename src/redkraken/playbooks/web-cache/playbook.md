---
description: Ask whether a front end hands one caller's answer to another, by storing and reading a response on a key this reading invented, and by asking through the path where the origin thinks a route ends, whether the path is resolved before it is routed, and which shape the classifier files as a static asset.
bb:category: information_disclosure
bb:outputs: ["information_disclosure.cached_response"]
bb:triggers_all: ["read_method", "tech_cdn", "web_surface"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 52 as the v2 replacement for v1's cache-poisoning page, against a new cached-response leaf added by ticket 52; the v1 text is attached as a maintainer reference and the invented key is where this Playbook and that page part company. Rewritten for ticket 101 against the merged ledger, which carries six procedures, one lead and three refusals for this slug. One key moved. The refuted variant row leaves response_invariant for response_differential, the kind the supported row of that same role names, because close_test_replay derives the kind from the specification and one role writes one kind whichever way the reading goes. Every closing assertion below names its variant against a control arm rather than against the baseline, which is what keeps the declared control row reachable.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_differential", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "response_differential", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "response_differential", "polarity": "supports", "min_count": 1}]
bb:references: ["cache-poisoning.md"]
---

# A cache is a key, and the defect is what the key leaves out

Something in front of this application stores answers and hands them to whoever asks the same
question. Which askers count as the same is the cache key, usually the method, the host and the
path. The session is not in it and the `Authorization` header is not in it, which is fine unless the
answer depends on them, and the defect is the case where it does.

Six of the nine sections below are procedures, each ending at one Test of three to thirty-two
actions holding at least one baseline, one variant and one control, because rk2_test_spec_problem
refuses a specification performing fewer than three or leaving a role out. The arms go out with
`mcp__rk2__http_request`, are filed as one specification with `mcp__rk2__propose_test`, the only
verb that makes a Test exist, and close_test_replay closes them. Three conventions hold across all
six. The closing assertion names the variant against a control arm, never against the baseline, so
the control's own Observation is the differential this Playbook declares for that role. The baseline
role carries two identical sends asserted equal, because response_agent_sha covers Date and Age too.
And every arm rides a key this reading invented.

## 1. Establish that the answer depends on the caller, and invent the key

Read the route twice with `mcp__rk2__http_request`, once on a Task holding the Identity and once on
a Task holding none: a call goes out as whichever Identity its Task was opened under, so the
anonymous half is a second Task. Where the two answers are the same there is nothing to leak
whatever the cache does and the reading ends.

That difference is an agent-filed credential_effect, submitted with the proposal through
`mcp__rk2__submit_mission_result`, which promote_proposal writes, and taken before any specification
exists, because an evidence edge cannot be added to a claim already past proposed. This section
closes no Test and grades nothing.

Every arm below rides a path this reading invented: the route with one added query parameter whose
name is a random token, `?rk-<token>=1`, fresh for each arm. A cache key is a string, and an
unguessable parameter produces a key no real user will ever request, so whatever is stored under it
is stored for an audience of exactly this reading, while the measurement is unchanged because a
query parameter adds no session. Read one invented path anonymously first: a target varying on
unknown parameters has put the query string in the key.

## 2. Store one caller's answer on the invented key, and read it with nothing

Request the invented path once on the Task holding the Identity. That is the seeding, and it is what
lets one replay run hold both closing arms. The Test then runs entirely on the Task holding no
Identity, so both closing arms sit under one Identity setting and differ only in the path and query.
Actions 1 and 2 carry the baseline role: a second invented key that was never seeded, read twice,
asserted equal to each other. Action 3 carries the control role: the bare route with nothing
presented, the answer an anonymous caller is entitled to. Action 4 carries the variant role: the
seeded invented key, nothing presented. The closing assertion says action 4 differs from action 3,
and action 5 repeats action 4 under the same assertion, because one hit can be a coincidence of
timing.

File the cache headers of every arm as an agent-filed header_policy_observed edge from the same
Receipts. None is stripped: `Cache-Control`, `Age`, `Vary` and whatever `X-Cache` the front end
publishes all reach the agent view, and a `Vary: Cookie` on the seeded answer is the target saying
it already thought about this. Our own proxy is ruled out by construction rather than by inspection,
because it stores nothing and the invented key has never been seen on this side of the wire, which
is what makes the `Age` a claim about the target.

## 3. Ask where the origin thinks the path ends

A framework that truncates a path at a delimiter answers the bare route for a path the cache files
under a different, static-looking name. Baseline: the route on one fresh invented key, sent twice,
asserted equal. Control: the same route with the static-looking suffix appended directly, no
delimiter, on its own key, which must not answer as the baseline. Variant: one arm per candidate
delimiter, each with the same suffix behind it, each on its own key -- a matrix parameter separator,
an extension dot, an encoded NUL, an encoded newline, a currency sign, one to an arm.

Two assertions carry it: the variant differs from the control, which is what close_test_replay
reads, and the variant equals the baseline, which is the sameness the reading is about. Where the
control already matches the baseline the origin maps every unknown path to one page, both assertions
are founded on nothing, and the reading stops.

## 4. Ask whether the path is resolved before it is routed

A cache whose rule is a string prefix and an origin that resolves dot segments disagree about which
route a path names, and the spelling is the whole of this section. rk2_test_request_problem refuses
a specification url carrying a literal dot or double-dot segment, and refuses the encoded-dot string
anywhere in the url, so exactly two spellings can appear in a Test: `..%2f` and `..;/`. After the
dots comes a percent sign or a semicolon rather than a slash, which is why neither refusal reaches
them, and origin_form appends the path verbatim so both arrive on the wire as written.

Baseline: the private route on one fresh invented key, twice, asserted equal. Control: the same
prefix path without the traversal, nothing presented, which must not reach the private route.
Variant: the traversal path, nothing presented, one arm per spelling. The closing assertion says the
variant differs from the control -- the private body arrived for a caller holding nothing. Where the
control already reaches the private route, the prefix proxies everything and no rule was escaped.
The literal and percent-encoded dot spellings are exploration and not arms: send each once with
`mcp__rk2__http_request`, file the answer as an agent Observation, and keep both out of the
specification.

## 5. Ask whether the router matches a shape the cache files as an asset

A private route reached through a name ending in a cacheable extension is matched by the router and
filed by the cache as a static asset. Seed it under the Identity first: request the private route
plus a nonce-named suffix carrying that extension, and confirm the router still answers privately.
The Test then runs on the Task holding no Identity. Baseline: the bare private route, nothing
presented, twice, asserted equal. Control: a nonexistent sibling path carrying the same nonce
suffix, nothing presented, which must answer a not-found. Variant: the seeded suffixed path, nothing
presented. The closing assertion says the variant differs from the control. Both arms carry the
suffix and only one names a real route, so a front end answering every suffixed path alike cannot
produce the difference.

The nonce makes the created key identifiable, and the exact key goes in the finding so it can be
purged. Where the suffixed path reaches a route that mutates -- a non-idempotent answer, a changed
object -- stop before repeating it and ask `mcp__rk2__park_for_human` to park the Task, its label
in `task_label` and destructive_action in `question_code`, since the next send may change state.

## 6. Ask which shape the classifier keys on

A cacheable-extension list does not mean a response is stored: method, status, cache-control, size
and plan still decide, and the reading asks which shape the key is built from. Baseline: the dynamic
route on one fresh invented key, twice, asserted equal. Control: the genuine static path and the
genuine well-known file fetched directly, each on its own key. Variant: the same dynamic route
driven at through a static extension, a static directory prefix, and a well-known filename, three
arms and three keys. The closing assertion says each variant differs from the genuine-static
control. An arm returning the genuine static body rather than the dynamic one was normalised at the
cache and not at the origin, which this control is here to rule out.

## 7. Ask whether an internal edge header reclassifies the answer

A framework whose edge and origin share an internal header answers the same path with a serialised
properties document where it answered a rendered page, and moves the caching class with it. Since
ticket 211 a Test action states its own `headers` beside its `method` and `url`, so all three arms
are actions of one Test sent with `mcp__rk2__http_request`; the header name matches the action
pattern, is not hop-by-hop and does not carry the internal prefix, so it forwards.

Baseline: the route with no extra header, on one fresh invented key, twice, asserted equal. Control:
the route with the framework's data-request marker and without the internal header, on its own key,
which isolates the header as the cause. Variant: the route with both, on its own key. The closing
assertion says the variant differs from the control. The caching headers ride inside the same hashed
message, so a moved cache-control directive is part of that difference, and both header lines are
quoted verbatim beside it. Stop at one route with one control; carrying it through to a stored copy
on a shared key is poisoning, refused in section 9.

## 8. A cache that declares nothing, which is a lead

Where the response declares no caching headers at all, the only remaining discovery signal is
duration. Send the plain url several times and the same url with a fresh invented key as often,
interleaved rather than blocked, and time a url known to be uncacheable both ways as the
calibration. Every Receipt carries its own arrival and egress timestamps and its own waited value.

This is a lead. No assertion kind names a duration -- the set is status_equals, status_differs,
body_equals and body_differs -- so no Test closes on it, and promote_proposal files the separation
as an agent-filed timing_differential which is a real edge and settles nothing. Where the
calibration shows variance of the same order as the measured difference, file nothing: an
uncalibrated timing edge reads as evidence. That halt is a reading that ran out and it names no
question code.

## 9. State the claim, and name the three readings this Playbook refuses

The Hypothesis is information_disclosure.cached_response on the route, proposed with
`mcp__rk2__propose_finding` naming sensitive_data_exposure as its `vulnerability_class`, which takes
a vulnerability_classes id and not a dotted Property class. It is supported when a caller holding
nothing received, on a key this reading created, an answer a session or a private route produced,
against a control that did not, and refuted when every arm keeps getting the anonymous answer. An
answer matching neither is a second cache layer or a rotating upstream: record it and stop.

Where a traversal or a suffix returns a body belonging to a caller who is not the test Identity,
stop at once, send no further shape of that family, name the exact key so it can be purged, and tell
the engagement operator immediately, because the stored answer has a lifetime running. That halt is
none of the five question codes a model may name, so it is reported through the Task's own record.

Three readings are refused rather than absent. Sending an unkeyed input the front end reflects -- a
forwarded host or scheme, an original-url override, a duplicate parameter, an oversized value -- is
refused on every key, invented or shared: that is not a test, it is a change to what every visitor
receives, it cannot be withdrawn once the entry exists, and its blast radius is decided by a
lifetime the reading does not control. Storing a refusal so the key serves it to a clean request is
refused twice, once by that same sentence and once because what it produces is a denial of service
and availability is not a Property class in this vocabulary at all. Seeding the entry from a
victim's browser is refused because the browser lane hosts no second origin and asks no other
browser for anything; the same-origin half stays checkable in a Task note, since a session cookie
that does not ride a cross-site subresource decides whether the seeding would have worked. The cost
of the invented key is the one sentence this Playbook may not write: no reading above says a real
user would have received the stored answer.

This section performs and grades nothing. 3 of 9 steps cannot be graded.
