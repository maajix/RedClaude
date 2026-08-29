---
description: Ask who is allowed to read an answer that only exists because the caller holds a session, by sending the same authenticated read under a trusted origin, an untrusted one and a near miss and reading the two headers that decide it, by asking whether the allow list recognises names the scope never published, and by asking whether the route will hand the same answer to a script tag.
bb:category: session_handling
bb:outputs: ["session_handling.cross_origin_read"]
bb:triggers_all: ["authenticated_endpoint", "header_parameter", "read_method"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-05-15
bb:provenance: Written for ticket 56 as the v2 replacement for v1's request-integrity pack against a new cross_origin_read leaf added by ticket 56; the pack's two pages are attached as maintainer references, its forged-write proofs are refused by the closing section, and the write half of its subject stays the csrf leaf that realtime outputs. Rewritten for ticket 101 against the merged ledger, which carries five procedures, one lead and one refusal. One key moved. The refuted variant row leaves response_invariant for response_differential, the kind the supported row of that same role names, because close_test_replay derives the kind from the specification and one role writes one kind whichever way the reading goes. Every closing assertion names its variant against the baseline and leaves the control named by no differing assertion, which is what keeps the declared control row an invariant. Ticket 211 turned four of these readings from Observations into procedures, because an action now states the header it varies.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_differential", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "response_invariant", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "response_differential", "polarity": "supports", "min_count": 1}]
bb:references: ["cors.md", "csrf.md"]
---

# Ask who is allowed to read the answer, not who is allowed to ask

An authenticated read answers because the caller holds a session. A browser will attach that session
to a request another site made and will then refuse to hand the answer back to that site, unless the
application said otherwise. Two response headers are the whole of otherwise, and one older
convention -- a response shaped like a script -- goes round them entirely.

Before anything is sent, lease the Identity through the use-identity Skill and send the subject once
with no origin header at all. That send establishes two things the rest depends on: that the route
answers for this session, since a route answering the same for nobody is not tied to a session and
is not this subject; and which fields in the answer are the caller's own rather than the
application's -- an address, a plan, an identifier, a balance. A permissive header over a document
that says the same thing to everybody is a misconfiguration and not a disclosure, and section 7 is
where that distinction is spent.

Five of the seven sections are procedures, each ending at one Test of three to thirty-two actions
holding at least one baseline, one variant and one control, because rk2_test_spec_problem refuses a
specification performing fewer than three or leaving a role out. The arms go out with
`mcp__rk2__http_request`, are filed as one specification with `mcp__rk2__propose_test`, and
close_test_replay closes them. Since ticket 211 an action states its own `headers` and `body` beside
its `method` and `url`, which is what turned four of these readings from Observations into
procedures; setup and cleanup steps still carry a method and a url alone.

Two conventions hold across all five. The closing assertion names the variant against the baseline,
and the control is named by no differing assertion of its own, so it closes as the invariant this
Playbook declares for that role. And the baseline role carries two identical sends of one url
asserted equal to each other, because response_agent_sha covers the whole agent-view message
including its Date, so a header differential with no invariance leg is not a reading. Neither
Access-Control-Allow-Origin nor Access-Control-Allow-Credentials is stripped on any path, so both
reach the agent view and both land in the hashed transcript.

## 1. The pair that decides who may read the answer

Baseline: the subject with no origin header, sent twice, asserted equal. Variant: two arms, one
request each, identical but for the origin -- one naming a site with nothing to do with this
application, and one naming the trusted origin with a single character changed, a different
top-level domain or the trusted host as a prefix of a longer name. Control: an origin sharing no
substring with anything the application publishes, asserted equal to the baseline, because it must
not be reflected; that is what separates an allow list recognising a name from a target reflecting
whatever it is handed.

Carry a fourth arm naming an origin the application itself points at, its own scheme and host or a
partner origin it published. Nothing asserts anything about that arm; it is read, and it is what
keeps the reading from reporting a deliberate configuration, since an application answering a known
origin with that origin and a credentials line has been configured to do so. Where the untrusted arm
is answered exactly as that one is, there is no difference to report.

Quote both header lines verbatim from every arm that carried them, and say whether the allow-origin
value is the origin that was sent, a fixed value or a wildcard, and whether the credentials line is
true. Neither half carries the claim alone. A wildcard with no credentials line means a browser
sends the request without the session and gets a document that is not the caller's. A reflected
origin beside a true credentials line means a browser sends the session and hands the answer to
whoever asked, and only the second is this class. Say also whether the body differed between the
arms; it should not, and an arm whose body moved is a different question.

## 2. Where the match is anchored

A list that reflects whatever it is sent and a list whose pattern is anchored at the wrong end are
different defects with different fixes, and the near miss is what tells them apart. Baseline: the
trusted origin's arm, whose answer names that origin, sent twice, asserted equal. Variant: two arms
-- the trusted host as a suffix of a foreign name, and the trusted host as a prefix of a longer one.
Control: the no-substring origin again, named by no differing assertion, which must not be
reflected.

Each closing assertion says its variant differs from the baseline. Two arms chosen for what they
distinguish, and no list: sending a hundred origins to find one that reflects is a scan and produces
the answer these two already produce. A third distinct answer, neither the reflected shape nor the
refused one, means something other than a string match is deciding; record it and stop, because the
two-arm reading no longer separates anything.

## 3. The allow list read as a directory of names

The same four requests asked as a different question. An allow list that recognises a name the scope
never published has answered a question about that name, which is an identifier oracle rather than a
cross-origin read risk, and no Playbook emits that class. Baseline: the route with no origin header,
sent twice, asserted equal. Variant: two arms, one naming a host the scope publishes and one naming
a plausible internal host it does not. Control: sixteen random characters under a domain nobody
owns, named by no differing assertion, which must not be reflected.

Each closing assertion says its variant differs from the baseline. Four origin values at most, then
stop, recognised or not. Sweeping a subdomain word list through the origin header is a scan against
a route and is not this reading. A recognised internal name is Program information and is reported
as such; where a step then proposes to request that origin directly, ask for the Task to be parked
with `mcp__rk2__park_for_human`, which is refused without both that Task's own `task_label` and a
`question_code`, here scope_ambiguous, because the scope document does not say the name is in it.

## 4. The answer a script tag could read

A body wrapped in a function name the caller chose is loadable across origins through a script tag
whatever the two headers say. Baseline: the route with no callback parameter, sent twice, asserted
equal. Variant: the same url with a caller-named callback parameter, one arm per candidate name --
the ordinary one, the padding one, the short one, and the framework-specific shape. Control: a
parameter name the application does not know, of the same length, asserted equal to the baseline,
which separates a wrapper from an endpoint echoing every parameter it receives.

Each closing assertion says its variant differs from the baseline. The wrapper is in the body, so
this reading needs no header at all; the content type usually flips to a script type with it, and
that flip is filed beside the Test as an agent-filed header_policy_observed edge through
`mcp__rk2__submit_mission_result`, which promote_proposal writes, before the specification is
proposed. Stop at the shape. Report that the response is script-readable and do not build the
including page.

## 5. The validator whose length is the oracle

Where a conditional validator encodes the length of the body it was issued for, a request head
padded to just under a runtime's fixed header ceiling turns that length into a status. Baseline: the
padded url carrying the validator of a body just under a length boundary, sent twice, asserted
equal. Variant: the same padded url carrying the validator of a body one byte longer, which crosses
the boundary and pushes the head over the ceiling. Control: the same padded url with no conditional
header at all, named by no differing assertion, which establishes that the padding alone is under
the ceiling and that the refusal came from the extra byte.

The closing assertion says the variant differs from the baseline in status. Establish the boundary
once and stop. Walking it is extraction rather than measurement, and no arm of this Playbook
binary-searches a body through an oracle. The cross-site half of the same technique, measuring a
navigation counter across two loads, needs a second origin the browser lane does not host and
model-authored script the browse action enum does not admit, so only the server-side precondition is
read here and the rest is written up as a precondition.

## 6. Whether the response carries session state at all, which is a lead

A script or JSON route only matters to a cross-origin page if its answer moves with the session.
Fetch it from a Task holding no Identity twice, then from a Task holding the Identity once, and
calibrate with a versioned static asset fetched from both Tasks, which must be byte-identical. Where
even a static asset differs the deployment stamps every response, no body difference here is
evidence of session content, and that changes what every other differential on this target means.

This is a lead and it stops at an Observation. The two arms differ only in which Identity sends
them, and one replay run holds one Identity setting for its whole length, so they cannot be two
actions of one Test; the difference is filed as an agent-filed credential_effect over the two
Receipts and settles nothing. It is still the precondition the inclusion half would need, and the
inclusion half is not sent.

## 7. State the claim, and state the ceiling

The Hypothesis is session_handling.cross_origin_read on the subject, proposed with
`mcp__rk2__propose_finding` naming permissive_cors as its `vulnerability_class`, which takes a
vulnerability_classes id and not a dotted Property class. It is supported when an untrusted or
near-miss origin came back in the allow-origin header beside a true credentials line, the trusted
arm was answered as it was before this reading started, and the fields named before section 1 are
the caller's own. It is refuted when the untrusted arms were answered exactly as the baseline was,
no header or a fixed value that is not what was sent, which is what a correct allow list looks like.
Anything else is inconclusive, and it says so in that word.

What raises it and what lowers it belongs in the write-up, from what was observed rather than from
what is usually true. It is raised by fields that are the caller's own, by a reflected origin
anybody can obtain, and by a route reachable with an ordinary session. It is lowered by a reflected
origin the operator controls, by a document that is the same for every caller, and by an absent
credentials line.

Three neighbours are close. Where the question is whether a state-changing request is accepted
without proof of same-origin intent, the class is session_handling.csrf and the Playbook is
realtime; it is a write and this Playbook does not send one. Where the question is which channel
policy headers a page carries, the class is transport.header_policy and the Playbook is
browser-framing. Where the answer carries fields belonging to another caller rather than to this
one, the class is authorization.object_ownership and the header was never the point.

The ceiling is short and none of it is negotiable. This Playbook sends a small, counted number of
reads to one route and changes nothing. It does not build the page: it hosts no markup, opens no
browser against an origin it controls, and asks no victim's browser for anything, because the claim
rests on the headers the application returned, which is what a browser would have acted on. It does
not reach the trusted origin either -- registering it, claiming it, taking a foothold on it or
sitting between it and a client are all refused, the first two as claiming a third-party resource
and the last as a machine-in-the-middle position, and the allow-list membership the reachable
sections established is reported instead on its own terms. It does not touch a session it is not
holding, log the leased session out or clear a cookie.

Halts here are readings that ran out -- four origin values sent, one boundary established, one
wrapper found -- and none of the five question codes a model may name says that, so they are
reported through the Task's own record.

This section performs and grades nothing. 2 of 7 steps cannot be graded.
