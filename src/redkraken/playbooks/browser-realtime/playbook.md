---
description: Ask whether a socket route reaches an authorization decision about a channel name before it reaches the protocol, and whether the ticket a realtime stack mints over ordinary https is scoped to the channel the caller asked for, by carrying a second Identity's channel name in the query of an ordinary GET and differencing the answer against a name nobody owns.
bb:category: authorization
bb:outputs: ["authorization.channel_subscription"]
bb:triggers_all: ["multiple_test_identities", "query_parameter", "websocket_surface"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 52 against the channel-subscription leaf ticket 52 added, with the v1 websocket text attached as a maintainer reference. Rewritten for ticket 101 against the merged technique ledger, which holds two readings and two refusals for this slug. Every step of the shipped text was an upgrade handshake, and our own egress drops connection and upgrade before the wire, which is why this was the only Playbook of fifty with no executable reading. The two readings that replace them are ordinary GETs differing in the query, so bb:effects stays read_only and bb:risk stays constrained. The refuted leg moves from response_invariant to credential_effect, which is the kind its own role already asked for on the supported leg. Repaired again in review -- the caller's own channel is the baseline and the name nobody owns the control, which is the shape section 3 already had, and the second Task leaves through suggested_tasks rather than standing as a requirement with no verb.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "credential_effect", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "credential_effect", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "credential_effect", "polarity": "supports", "min_count": 1}]
bb:references: ["websocket-attacks.md"]
---

# The channel name is read before the protocol is

A realtime surface multiplexes. One connection carries many channels -- a room,
a document, an order, a tenant -- and which channel a caller is entitled to is
decided from a name the caller supplied. That name is a query parameter, which
is what this Surface says it has.

The handshake that would carry it does not survive this harness's own egress,
and section 5 names that refusal with its cause so nobody re-proposes it. What
does survive is the same request without the two headers the door removes -- an
ordinary GET of the socket path -- and the ticket route a client calls before
it opens anything. Both are authorization decisions about a channel name, both
differ in the request line, and both are readings a Test can settle.

## 1. Fix the three channel names and the two Tasks

This step is a lead and cannot be graded. It reads state through
`mcp__rk2__get_attack_surface` and writes no Observation, because naming a
channel is a selection and not a reading.

Two Identities and one channel each, and one Task holds one lease for its
length. This Task is the second Identity's and performs the half that lease
admits: a run acts as whichever Identity its Task was opened under, the step
does not choose it, and there is no argument for it. The first Identity's own
session, and the channel name it is entitled to, leave as a `suggested_tasks`
entry on `mcp__rk2__submit_mission_result`; nothing re-leases a Task in flight,
and where no name is recorded for that Identity this Task reads no further.

A name the second Identity was also entitled to proves nothing, so the name has
to be one the first Identity owns and the second does not, established from the
target's own answers rather than assumed from the spelling. Record a third name
as well, minted here, that names nothing at all. That third name is what a
refusal from this route to this caller looks like, and everything below is read
against it.

The only thing that moves between the arms below is the channel name in the
query.

## 2. Difference the socket route's own refusals

Send the socket path over ordinary https from the second Identity's Task with
`mcp__rk2__http_request`, one name at a time, and spell no `Upgrade` or
`Connection` header -- the door drops both, so stating them changes the plan
and nothing else. Then propose the reading with `mcp__rk2__propose_test`, four
actions in plan order and never re-ordered.

* action 1, role baseline, the socket path carrying this caller's own channel
* action 2, role baseline, the same url again, unchanged
* action 3, role control, the same path carrying the name nobody owns
* action 4, role variant, the same path carrying the first Identity's name

Three assertions. `body_equals` on action 2 against action 1 reads the stored
body digest alone and says the route is byte-stable. `status_differs` on action
3 against action 1 says this route answers a name nobody owns differently from
one this caller holds, which is what makes any answer mean anything.
`status_differs` on action 4 against action 3 is the claim.

The writer is `close_test_replay`. It takes the Observation kind from the
specification and never from the outcome, so the control arm and the variant
arm both carry `response_differential` whichever way the run comes out, and it
is the only runtime writer that carries a Hypothesis from testing to supported.

The bar this Playbook declares is `credential_effect` on both roles, and that
edge is the agent's own rather than the Test's. `promote_proposal` writes it, it
names the mechanism the differential does not, and it settles nothing by itself.
Its Receipts are live sends of the same three urls, made before the reading is
proposed, because an evidence edge is dropped once the first recorded action has
moved the claim past proposed.

Send those with `mcp__rk2__http_request` and file them through
`mcp__rk2__submit_mission_result`, as `observations` with the proposal, naming
which session each was sent under. Three names, one request each; enumerating
channel names is a wordlist and section 5 refuses it.

## 3. Ask the ticket route for a channel the caller does not own

Where the client calls an https-side negotiate, ticket or token route before it
opens the socket, that route is where the entitlement decision actually lives.
Establish it from observed traffic or from the served bundle, never by guessing
a path.

The shape is the same, held at the second Identity. Send the arms with
`mcp__rk2__http_request` and propose the reading with `mcp__rk2__propose_test`,
four actions in plan order and never re-ordered.

* action 1, role baseline, the ticket route naming that Identity's own channel
* action 2, role baseline, the same url again, unchanged
* action 3, role control, a channel that does not exist and has to refuse
* action 4, role variant, the first Identity's channel

Assert `body_equals` on action 2 against action 1, and `status_differs` on
action 4 against action 3. The writer is `close_test_replay`, which takes the
Observation kind from the specification and is the only runtime writer that
carries a Hypothesis from testing to supported. The `credential_effect` edge
this Playbook's bar names is the agent's own and settles nothing by itself.

Its Receipts are live sends made before the reading is proposed: send them with
`mcp__rk2__http_request` and file them through
`mcp__rk2__submit_mission_result`, as `observations` with the proposal.

A ticket that comes back at all means the minting step did not consult
entitlement. A ticket whose body names the requested channel means it did not
re-scope it either. Redact any credential value before it is recorded.

Since ticket 211 an action states its own `headers` and `body`, so a ticket
route that wants a posted document is expressible here and no longer stops the
reading. What still stops it is a route that answers with a stream rather than
a document, because a stream is a connection this reading does not hold. That
halt is a reading that ran out rather than a question for a person, so it is
reported through the Task's own record and no code is named for it.

## 4. State the claim, and state what an accepted decision is not

The Hypothesis is `authorization.channel_subscription` on the socket route or
on the ticket route, whichever answered. It is supported when the arm carrying
a channel this caller does not own differs from the control carrying a name
nobody owns, against a baseline showing the route answers this caller at all.
It is refuted when that arm is invariant against the same control -- the
session is good and the route refused it that channel anyway. Both legs are
filed as `credential_effect` because one role writes one kind either way.

Anything else is inconclusive, and the common shape is the honest one. All four
arms returning the same status and the same body is what a route that checks
the protocol before it checks anything else looks like. Record which check the
route reached and do not add a fourth name.

An authorization decision reached over https is not a subscription. What
sections 2 and 3 show is that a route read a channel name and decided about it,
or that a ticket was minted for a channel the caller does not own. What neither
shows is that a socket would have opened, that the channel was busy, or that
anything the other Identity sent would have arrived. A reading tempted to add
"and then the messages were readable" has left its evidence behind and reports
inconclusive on that half.

Where the question is whether an origin is checked rather than whether a caller
is, the class is `session_handling.csrf` and belongs to the Playbook holding
it.

The gate is `rk2_finding_refusal`, and what it wants is the settling transition
`close_test_replay` wrote for the Test section 2 or section 3 proposed.

This section proposes no Test of its own and grades nothing. Open the claim with
`mcp__rk2__propose_finding`, citing the Receipts, the status and body of each
arm, and the channel name each carried.

## 5. What the door removes, and what neither lane speaks

This section is a lead and cannot be graded. It records two refusals, both of
them this harness's rather than the target's, so the reasons travel with them.

The upgrade handshake is unsendable. `connection` and `upgrade` are both in the
hop-by-hop set the egress drops, and the wire headers are rebuilt without them.
The browser lane carries the same drop set in its own shim, and the door
terminates a tunnel request rather than relaying it, so there is no tunnel to
upgrade inside either. A request planned as a handshake reaches the target as a
plain GET and is answered as one, which is a fact about this door. That is the
whole of the shipped step 2, and lifting it is a capability ask rather than a
technique.

Application frames after the upgrade are unspeakable. A request url is an http
or https url, so no socket scheme is expressible; the browse action registry
holds twelve actions and none of them sends a frame; and a posted message
reports that it was dispatched rather than that it matched, so no step may
claim a listener read a body. Lifting the header strip would not lift this one.
They are two capabilities, and the frame half sits behind the handshake half
anyway.

This Playbook is read_only. It sends at most eight GETs against two recorded
routes, holds no connection open, does not reconnect in a loop to find a limit
-- that is `rate_limiting.per_identity` -- and never hands the second
Identity's own channel to the first.

3 of 5 steps cannot be graded.
