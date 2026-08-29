---
description: Ask whether the target delivers its session where page script can hold it rather than in a cookie the browser keeps closed, by inventorying what the browser holds across the authentication boundary and replaying the script-readable half of the credential on a Task that leases no Identity of its own.
bb:category: information_disclosure
bb:outputs: ["information_disclosure.client_storage"]
bb:triggers_all: ["authenticated_endpoint", "read_method", "web_surface"]
bb:skills: ["browser-evidence", "compare-responses", "handle-untrusted-content", "use-identity"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 52 against a new client-storage leaf added by ticket 52; v1 had no page on this topic, so nothing is attached rather than a placeholder. Rewritten for ticket 101 against the merged technique ledger, which carries four readings for this slug. Two frontmatter keys moved -- browser-evidence and handle-untrusted-content join bb:skills, because the client-state inventories the old step 4 declared impossible have been a registry-owned browser action since 20261210T000000Z and what they return is untrusted content. One bb:evidence leg moves and it is a repair -- the refuted leg of the control role asked for header_policy_observed while the supported leg of the same role asked for credential_effect, and one role carries one kind whichever way a reading goes, so the refuted leg now carries the kind its own role carries on supported. All three legs name agent-filed kinds, which close_test_replay does not derive, so each is filed with the proposal while the claim is still proposed.
bb:evidence: [{"to_status": "refuted", "role": "control", "kind": "credential_effect", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "credential_effect", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "credential_effect", "polarity": "supports", "min_count": 1}]
---

# Where the session is kept decides who else can hold it

A cookie marked `HttpOnly` is a credential the page's own script cannot read. A
token handed to the page in a response body is a credential the page's own script
must read, which means every script the page loads can read it too -- the
analytics bundle, the tag manager, the dependency that changed owner last month,
and anything a markup defect puts in the document.

The question is not where the value ended up. It is where the target put it.

## 1. Establish the session the way the target intends

Read the subject route through `mcp__rk2__http_request` as the Task's own
Identity. The run acts as whichever Identity the Task was opened under -- the
step does not choose it and there is no argument for it -- so a Task opened under
no Identity is the wrong Task for this half and is returned rather than worked
around. Store the whole exchange: the request that authenticated, the response
body, and which field carried a token, a bearer, a session identifier, a signed
blob or an API key.

That is the reading's anchor, and its Observation is a credential_effect edge
filed in the context role through `mcp__rk2__submit_mission_result`, which
promote_proposal writes, with the result that proposes the claim: the session,
held as the target hands it out, reaches the route. Without it a later failure is
equally well explained by a route that never worked. The baseline is
a stable session -- one session across every step below, because a reading that
re-authenticated between the steps is comparing two sessions.

## 2. Read where the value was put

Two places, and they are not exclusive. Set-Cookie is one of the six response
headers stripped from the agent view on every path, so the cookie half is read
in the browser lane: run `mcp__rk2__browse` and take the cookie inventory, which
returns each cookie's name, domain, path, httpOnly, secure and sameSite
attributes and its prefix, with the value stripped before the Artifact exists.
That inventory is filed as a header_policy_observed edge beside the bar rather
than as a leg of it -- all three legs of this Playbook's bar are
credential_effect -- and the attribute set goes in the Observation rather than a
summary of it.

The response body is the other place: a token, a bearer, a session identifier, a
signed blob, an API key -- anything the page would have to read to use. Record
which field, and record that it is the same value the cookie carries where it is.
A target that sets an `HttpOnly` cookie and also returns the same value in the
body has published it; the cookie's flag is doing nothing the body does not undo.

## 3. Inventory what the browser holds across the authentication boundary

The claim that this harness cannot read Web Storage is stale and is the reason
this section exists. In one `mcp__rk2__browse` plan: navigate to the origin
unauthenticated and take the local storage, session storage and IndexedDB name
inventories, which is the baseline; complete the login and take the same three
again, which is the variant; and take one of them a second time on another path
of the same origin, which is the control that keeps a key following the page
from being read as a key following the session. Take the service-worker
registrations in the same plan: a registration whose scope covers the
authenticated routes is a component the page's own scripts can reach sitting
between the session and every response it sees.

The writer is promote_proposal again, filing each inventory as a content_match
Observation over the browse run, which is a tool run and satisfies that kind's
provenance with no offline pass over the Artifact first. Unlike the cookie kind
these inventories are not value-stripped, so what comes back is untrusted content
in the ordinary sense and handle-untrusted-content governs it: record key names
and the fact of a value, redacted.

Two ceilings are real and are kept. The registry returns a worker's registration
and its scope, never its Cache Storage contents, so the claim is that a component
exists in the path and not that a response was cached. And a value held in a
closure, a variable or a memory-held store is seen by none of these reads: a
reading that wants to assert where the value lives reports inconclusive for that
part rather than asserting it. Where an inventory returns what is plainly a live
credential, stop reading further keys and route it to section 4, whose stop
conditions govern spending.

## 4. Replay the script-readable half alone

This is the Test, and it is planned with no Identity slot. A leased Identity owns
Cookie and every header it declares for the origin, and replaces the caller's
before the wire, so a variant whose whole content is a credential in Cookie or in
`Authorization` becomes the baseline again on a Task that holds a lease. The
reading therefore runs on a second Task opened with no Identity, asked for
through the suggested tasks of `mcp__rk2__submit_mission_result`. That Task cites
its own Receipts and no others, since an element citing another run's Receipt is
dropped as receipt_other_run, so what crosses from section 1 is the field name
and the value it recorded rather than section 1's Receipt.

On that Task, send both readings live before anything is proposed, with
`mcp__rk2__http_request`. One carries the body-borne value as its only
credential, the other carries nothing at all. File the first as a
credential_effect Observation in the variant role and the second as one in the
control role, each with the polarity its own answer showed, and file both WITH
the result that carries the Test. Every leg of this Playbook's bar is
credential_effect, and rk2_promote_hypotheses drops an edge naming a claim past
proposed, which the first recorded Test action makes it. Where the two live
answers did not differ, the control edge carries refutes, and that is the leg a
refutation grades on.

Then propose the Test through `mcp__rk2__propose_test`. The baseline action is
the subject route carrying nothing at all. The variant action is the same route
with the body-borne value as its only credential, in `Authorization` or in
whatever header the page's own requests use, which a Test action has stated since
ticket 211. The control action is the credential-less baseline repeated, which is
both the stability check and the arm that rules out a route answering the same
thing to everyone. Assert that the variant's body differs from the baseline's and
that the control's equals it; close_test_replay derives response_differential for
the variant from that pair and settles the Hypothesis, and the credential_effect
edges filed with the proposal are what name the mechanism. Holding means the
value the target handed to script is a working credential on its own, whatever
the cookie's flags said.

Where the value about to be replayed belongs to an Identity other than the Task's
own, do not send it. Ask through `mcp__rk2__park_for_human` for this Task to be
parked, its label in `task_label` and credential_needed in `question_code`, and
let a person decide. Where the replay would spend rather than read -- a write
verb, a single-use token -- ask for the same park with the same `task_label` and
destructive_action in `question_code`, which is the code the risk rules map a
non-safe method to. What is recorded is the field the value arrived in and the
Receipt it arrived on, never the value itself.

## 5. Ask whether page script writes caller input into the jar

A one-shot reflection becomes a stored one where the page's own script reads a
URL-supplied value and writes it into the cookie jar. In one `mcp__rk2__browse`
plan: navigate without the parameter and take the cookie inventory, which is the
baseline; navigate again with the parameter carrying a distinguishable inert
marker, take the inventory again and capture the document, which is the variant;
and navigate a third time without the parameter, which is the control -- a cookie
present in that arm came from the server and the reading is over. The marker is
searchable and is not script, and a marker that breaks the code that stores it
destroys the path that would show the link.

The writer is promote_proposal, filing a reflected_input Observation over the
captured document naming the parameter and the cookie name it landed in. A
browse step is never a Test action, so the proof here is the name and the
attribute set beside the captured document, and the Finding opens on section 4's
Test on the same subject.

## 6. State the claim, and state what would refute it

The Hypothesis is `information_disclosure.client_storage` on the route, and it
becomes a Finding through `mcp__rk2__propose_finding`, which rk2_finding_refusal
admits only where section 4's Test settled it. It is supported when the value the
target delivered to page script authenticates on its own, against a control
showing the same route does not answer a caller presenting nothing the way it
answered that value. It is refuted when the
session travels only in a cookie the page cannot read and no body-borne value
authenticates.

Two neighbours, both close. A cookie whose `Domain` or `Path` reaches further
than the application is `session_handling.cookie_scope`: a cookie exposed to the
wrong origin, where this is a credential exposed to script at the right one. A
response carrying fields beyond what the caller is entitled to is
`information_disclosure.excess_field`; a token belonging to the caller is not an
excess field, it is their own session delivered somewhere it should not have been.

## 7. Read the credential; do not spend it

This section is not a step the system grades. It is a standing constraint on
every step above, and it names no verb because its whole content is what not to
do.

This Playbook's effects are `read_only`. Every request it sends is a `GET` the
Identity was entitled to make, and the credential it replays is the tester's own.
It does not lift a value belonging to another Identity, does not put the value
anywhere it was not already, does not log out to see what survives -- that is
`session_handling.lifetime` and a different Playbook -- and does not write the
value into a report unredacted. What is cited is the field it arrived in and the
Receipt it arrived on.

6 of 7 steps cannot be graded.
