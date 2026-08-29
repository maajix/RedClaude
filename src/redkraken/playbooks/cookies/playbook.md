---
description: Ask which of two readers takes a Cookie header's value, by sending one header this reading authored under a second encoding and then one name stated twice, each differenced against an inert arm of the same shape, and separately read the browser's own jar for the scope the session cookie was actually given.
bb:category: session_handling
bb:outputs: ["session_handling.cookie_parsing", "session_handling.cookie_scope"]
bb:triggers_all: ["cookie_parameter", "read_method"]
bb:skills: ["browser-evidence", "use-identity"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 50 as the v2 replacement for v1's cookies pack, against the cookie-scope leaf of the ticket 18 vocabulary; v1 shipped a README for this topic and no reference text, so nothing is attached. Rewritten for ticket 101 against the merged ledger, which holds two readings that settle a claim, two that stop at an Observation and four refusals for this slug. One key moved. session_handling.cookie_parsing joins bb:outputs, because both settling readings are parsing readings and that class shipped with no emitter at all. The evidence bar is unchanged.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_differential", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "response_differential", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "response_differential", "polarity": "supports", "min_count": 1}]
---
# Two readers, one Cookie header, and a jar nobody can quote

A deployment runs more than one reader over the `Cookie` line. Something in front decides whether
the request is authenticated; the handler behind it decides whose record to answer with. Nothing
makes those two read the header the same way, and the two readings that settle a claim here are
about that gap: a value one layer expands into a structure, and one name stated twice that the two
layers resolve from opposite ends.

The scope question v1 asked is still here, as sections 3 and 4, and it is a lead. It executes in
the browser lane, `TEST_ACTION_KINDS` is `request` alone, so a mission is not a Test action and
close_test_replay never sees one.

Sections 1 and 2 send through `mcp__rk2__http_request` and propose through
`mcp__rk2__propose_test`. close_test_replay is the only writer of the transition a Finding needs
and derives it from a Test's own assertions. Since ticket 211 a Test action states `headers`
beside its method and url, which is what puts those two sections on the Finding path; a setup or
cleanup step still carries a method and a url alone.

**Sections 1 and 2 run from a Task opened with NO leased Identity, and that is the whole
reachability of both.** `identity.Session.inject` gives a leased Identity ownership of `Cookie`
and of every header it declares for the origin, so a plan-stated `Cookie` is dropped before the
wire. The differential in both sections IS the cookie crumb, so neither plan names an identity
slot, and this sentence is the reason. Nor does any arm quote a value the server issued:
`WIRE_RESPONSE_HEADERS` strips `set-cookie` from the agent view on every path, so every value
below is one this reading authored. Take one cookie the route reads and whose value the reading
supplies -- a token handed back in a body, a preference, an arbitrary marker -- never the session.
Sections 3 and 4 need the opposite lease and one Task holds one, so this Task performs the half
its lease admits and the other leaves as a `suggested_tasks` entry on
`mcp__rk2__submit_mission_result`; nothing re-leases a Task in flight.

**Both closing Tests have the same four actions.** Actions 1 and 2 carry role `baseline`: the
arm's own request, sent twice unchanged, asserted body_equals. Action 3 carries role `control`:
the inert arm of the same shape. Action 4 carries role `variant`, asserted body_differs against
action 3. That assertion names both of them, which is what leaves each a response_differential
in its own role and is the bar this Playbook declares. Record each action's Receipt immediately
after its own send, never in a batch, and never re-order the plan: the ordinal is what binds an
action to its Receipt.

## 1. Ask whether a layer in front expands the value

Send the route with `Cookie: <name>=AAAA` twice unchanged. Those are actions 1 and 2, asserted
body_equals: a route whose stored body is not stable across the pair cannot be differenced, and
the verdict is inconclusive.

Action 3 is the inert control, `Cookie: <name>=x:{"not":"AAAA"}` -- the same bytes, the same
length, the same punctuation, under a prefix no cookie layer expands. Action 4 is the variant,
`Cookie: <name>=j:{"not":"AAAA"}`, asserted body_differs against action 3. An RFC 2109 quoted
value carrying a `\073` escape is a second spelling of the same arm and gets its own
specification. The control is what the claim rests on: without it a difference is the value being
longer or carrying punctuation, and with it the difference is the `j:` prefix, which is a layer
expanding a string into a structure. close_test_replay writes the verdict; where the answer
echoes the expanded value, file reflected_input beside it through
`mcp__rk2__submit_mission_result`, which promote_proposal inserts under the kind the proposal
named.

Where the variant and the inert control both answer `400` naming the cookie, the deployment
refuses the shape as such and no arm is attributable to a second parser. That is a reading that
ran out rather than a question for a person: none of the five `question_code` values
`mcp__rk2__park_for_human` takes says it, so record inconclusive in the Task's own record, with
the trigger quoted verbatim and the Receipt label of every arm sent before it, and stop.

## 2. Ask which occurrence of a repeated name each reader takes

One `Cookie` header, one name in it twice, both values authored here. Send `Cookie: <name>=A`
twice unchanged as actions 1 and 2, asserted body_equals, and record which value the answer
names.

Action 3 is the control and it is a second, DIFFERENT name carrying `B`: `Cookie: <name>=A;
<other>=B`. It must behave like the `A` arm; where it behaves like the variant instead, the effect
is header length and not name precedence. Action 4 is the variant, `Cookie: <name>=A; <name>=B`,
asserted body_differs against action 3. Before any of it, send `<name>=B` alone once through
`mcp__rk2__http_request`: it must name its own value, which separates "the answer quotes B" from
"the answer quotes whatever came last".

Four further spellings are four further specifications of the same four-action shape, one each:
the pair in reverse order, a quoted value hiding a separator (`<name>="B; <name>=A"`), the pair
with one leading space, and `$Version=1` ahead of it. A front reader taking the first occurrence
and a handler taking the last is two readers disagreeing about one header, and it is the claim.
close_test_replay settles it; the agent files reflected_input for the occurrence the answer
quoted, through `mcp__rk2__submit_mission_result`.

Where an arm returns a `5xx` or names a value that was never sent, re-send the single-value arms
once to establish that the route is still answering, and record the trigger and the arms in the
Task's own record. A header parsed into something nobody sent is reportable on its own, and is
still none of the five codes.

## 3. Inventory the jar, which is a lead

A lead, not a claim, and labelled as one here. Write one mission through `mcp__rk2__browse` under
`browser-evidence`: navigate an unauthenticated page of the origin, read_client_state for
cookies, complete the login inside the same plan, and read the jar again. A third read on a second
path of the same origin, with no navigation between it and the second, says whether the inventory
is about the cookie or about the page.

What comes back is the attribute set -- name, `Domain`, `Path`, `Secure`, `HttpOnly`, `SameSite`,
and the `__Host-` or `__Secure-` prefix. The registry strips cookie VALUES before the Artifact
exists, and a read that returns one is a regression: discard the Artifact, do not cite it, halt
the mission, and record the action name and the run id and never the value.

File header_policy_observed through `mcp__rk2__submit_mission_result`, written by
promote_proposal, citing the browse run itself, which is a tool run by foreign key and needs no
offline pass over the stored Artifact first. **This step stops at an Observation and cannot become
a Finding on its own.** A mission is not a Test action, so no assertion of any Test names it and
close_test_replay has nothing to settle; the Observation is a real edge on the scope Hypothesis
and is the end of what the step produces.

## 4. Read where the browser attaches the cookie, which is a lead too

The second lead, and the stronger half of the scope question. Unlike sections 1 and 2, this one
runs on a Task that carries the leased Identity: the cookie under test is the one the application
issued into the browser's own jar, and the plan still names no slot of its own. In one mission
through `mcp__rk2__browse`, navigate the application's own intended authenticated path twice
unchanged and record whether the session cookie was on both requests. Then one navigate each to
a sibling host under the same registrable domain, to a path beside the one the application uses,
and to the plain HTTP origin of the same host. What is recorded is the request the browser then
made and whether the cookie was on it, not a header the response contained.

Where the cookie reached one of those places, navigate an identity route there and assert_text
on a marker only a logged-in answer carries. A cookie that arrives is not yet a session; an
application that answers as the logged-in caller is what makes this scope rather than browser
behaviour. File response_differential over two of the mission's own per-navigation Receipts and
credential_effect over the identity read, both through `mcp__rk2__submit_mission_result` and
both written by promote_proposal. **This step stops at an Observation too, for the reason
section 3 gives.**

Where a navigation would resolve to a host or path the Program's scope does not include, do not
send it: call `mcp__rk2__park_for_human` with the running Task in `task_label` and `question_code`
scope_ambiguous, name the declared `Domain` and the target withheld, and let a person decide.

## 5. State the two claims, and say what would refute them

`session_handling.cookie_parsing` on the route is what sections 1 and 2 settle, through
`mcp__rk2__propose_finding` on the Hypothesis close_test_replay carried to supported. It is
supported where the expanded value or the repeated name changes the answer while the inert
same-shape control answers like the baseline and the baseline pair was invariant, and refuted
where the variant is indistinguishable from that control across both rounds: one reader, one copy,
no gap. Both verdicts are the Test's.

`session_handling.cookie_scope` on the application is what sections 3 and 4 observe. It is
supported where the browser attached the cookie outside the origin the application occupies and
the target honoured it there, and refuted where the jar declares `__Host-`, `Secure`, `HttpOnly`
and `SameSite=Lax` or `Strict`, which does not admit those places. Either way it is carried by
agent-filed Observations and opens no Finding under this Playbook. `HttpOnly` absent is not a
claim here at all: a cookie readable from script matters where script runs, and whether script
runs is `injection.markup` and `browser-script`. Record it as surface.

## 6. The ceiling, and the four readings this slug refuses

This Playbook is `read_only` and sends the arms of two specifications and one or two browse
missions. It hosts no second origin and will not, so a cross-site `SameSite` reading is described
with its preconditions rather than sent. Four readings are refused rather than dropped, because
each is cheap and each will otherwise be re-proposed.

Reading the attributes off `Set-Cookie` is unavailable, not merely unwritten:
header_policy_observed has a writer, and the input never arrives, because
`WIRE_RESPONSE_HEADERS` strips `set-cookie` on every path including the unbound one. Section 3
reads the same attributes minus the value.

Reading back a marker a script drove into `document.cookie` cannot answer: the client-state kind
is registered as attributes with values removed before the Artifact exists, and the probe registry
faults a probe that touches it. What would resume it is a probe that compares a named cookie to a
marker and returns neither.

Shadowing a session cookie from a controlled sibling host is refused on two independent grounds,
both decisions rather than gaps: this lane hosts no second origin, and the shadowing needs a
caller-chosen `Cookie` on a run whose Identity owns that field. The residue is section 3's
`__Host-` check.

One `Cookie` header carrying two server-issued session values, which the shipped
`cookie-parsing-pair` fixture asks for, is blocked twice over: the agent can never learn a session
value, and the Identity that holds one is the Identity whose injection deletes the caller's
header. Both halves have to fall for that fixture to grade, so it is recorded against ticket 100
rather than softened here, and sections 1 and 2 ask the same question of the same two readers.

This section performs nothing and grades nothing. 4 of 6 steps cannot be graded.
