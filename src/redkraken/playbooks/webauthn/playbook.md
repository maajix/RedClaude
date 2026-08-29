---
description: Ask whether a step-up route enforces the factor it asks for or merely offers it, by driving the action honestly once and then reaching it with the factor withheld, renamed, replayed, or its subject taken from a value the caller writes.
bb:category: authentication
bb:outputs: ["authentication.factor_enforcement"]
bb:triggers_all: ["state_changing_method", "tech_webauthn"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: approval_required
bb:effects: mutates_account
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 50 as the v2 replacement for v1's webauthn pack, against the factor-enforcement leaf of the ticket 18 vocabulary; v1 shipped a README for this topic and no reference text, so nothing is attached. Rewritten for ticket 101 against the merged ledger, which carries four readings and one refusal for this slug. One key moved. The refuted variant row moves from response_invariant to state_change, the kind the supported row of that same role names, because close_test_replay derives the kind from the specification and one role writes one kind whichever way the reading goes.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "state_change", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "credential_effect", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "state_change", "polarity": "supports", "min_count": 1}]
---

# A second factor the client can decline is not a second factor

The subject is a route that demands a second factor before a sensitive action.
The question is never whether the factor step exists -- it does, or there would
be nothing to read -- but whether the action can be reached without it. So every
reading below is judged on the account route afterwards and not on the status
the action returned. A 200 says a document was accepted; the account says what
changed.

Every reading is one Test of at least three actions holding a baseline, a
variant and a control, because rk2_test_spec_problem refuses a specification
performing fewer than three or leaving a role out. Since ticket 211 an action
states `headers` and `body` as well as `method` and `url`, so the client's own
factor document is part of the specification rather than something described
around it. The actions are sent with `mcp__rk2__http_request` and filed as one
specification with `mcp__rk2__propose_test`, the only verb that makes a Test
exist, and close_test_replay closes it.

Every reading therefore runs twice over, and the order is not optional. The
state_change and credential_effect Observations this Playbook's bar names
are agent-filed, so the honest pass and the refusal that produce them happen
first in the agent lane and go in WITH the proposal through
`mcp__rk2__submit_mission_result`, which promote_proposal writes, in the
variant and control roles the bar names. An edge cannot be added once a claim is
past proposed, and record_test_action moves a claim off proposed on the
first recorded action, so an Observation filed from inside the Test arrives too
late to count. The price is that the account moves twice for one demonstration,
which is what the destructive_action park in section 6 covers.

## 1. Drive it honestly, then reach the action without the factor

Drive the sensitive route once with the factor completed through
`mcp__rk2__http_request`, record the request the client sent for the factor step
and for the action, and read the account route to verify the action took effect.
That honest pass is the baseline every later arm is differenced against, and
where the Program grants no account mutation the reading stops here and reports
it alone.

The Test is six actions in three roles. Actions 1 and 2 are the baseline: the
honest action again, then the account read-back. Actions 3 and 4 are the
variant: an older interface version reaching the same transition -- a
first-version path where the client uses the second -- then the account
read-back after it. Actions 5 and 6 are the control: the same action with its
factor field replaced by a right-shaped value that was never issued, which must
be refused, then its read-back, which must show nothing moved. A route accepting
an invented assertion enforces nothing, and the claim there is
`authentication.credential_verification` rather than this class. `body_differs`
naming the variant's read-back against the baseline's is what
`close_test_replay` closes, over the `state_change` and `credential_effect`
edges the agent-lane pass already filed.

The credential-less control belongs to a second Task and not to this Test: one
replay run holds one leased Identity for its whole length, so an arm sent with
no session cannot stand beside an arm that carries one. Ask for that Task
through the suggested tasks of `mcp__rk2__submit_mission_result`; it is what
separates a skipped factor from a route that never had one.

Two more variants stop at an Observation rather than closing anything: the
action route called directly with a session that passed the password step and
not the factor, and the same again adding a correctly spelled `Referer` naming
the factor page. One demonstration is the finding: each further arm mutates the
account again.

## 2. The client's own word about which factor ran

A route where the client names the factor is a route whose real factor is the
weakest one enrolled. This needs a leased Identity the Program owns with more
than one factor enrolled, so there is a weaker one to name. Each arm is one
action request and one account read-back, actions of one Test through
`mcp__rk2__http_request`, the client's document in the `body`.

The baseline is the honest action request naming the factor the flow actually
performed, with the read-back showing it took effect. Each variant changes one
name: the method name, the declared factor type, or the list of allowed factors,
altered to name a factor the account holds and the flow did not perform. The
control alters the same field to name a factor the account does not hold, which
must be refused -- that separates a server taking the client's word from a
server accepting any well-formed document, and it is what makes an accepted arm
mean anything.

`body_differs` naming the renamed arm's read-back against the honest one is what
`close_test_replay` closes, and `promote_proposal` files the moved account value
as `state_change` and the refusal of the unenrolled name as `credential_effect`.
Stop at the first accepted name; the remaining factor names are not enumerated.

## 3. Factor material presented twice

The question is whether an assertion is bound to its own challenge or is simply
a thing that has to happen once. It needs a second sensitive action on the same
account, because replaying against the same action cannot tell replay from
idempotence. Each arm is one action and one account read-back through
`mcp__rk2__http_request`, the factor material in the `body`.

The baseline drives the second action honestly with its own factor step
completed and reads the account back. The variant drives the second action with
the first action's factor material replayed verbatim. The control drives it with
factor material of the right shape that was never issued at all, which must be
refused, and it distinguishes a server that accepts a replayed assertion from
one that accepts anything shaped like one -- different findings with different
severities.

`body_differs` naming the replay's read-back against the honest one is what
`close_test_replay` closes; `promote_proposal` files the moved account value as
`state_change` and the never-issued refusal as `credential_effect`. One replay
demonstrates it, and a second mutates the account again for nothing.

## 4. The subject taken from a value the caller writes

This reading runs on a Task with no leased Identity for this origin, and the
reason is the reading itself. `identity.Session.inject` gives a leased Identity
ownership of `Cookie` and of every header it declares for the origin, so a
plan-stated one is dropped before the wire -- and here the rewritten cookie is
the whole differential, so an Identity slot would delete the thing under test.
The arms are three requests through `mcp__rk2__http_request`, the account-naming
cookie stated in `headers`.

Every arm carries a deliberately wrong code, so nothing succeeds and the reading
is built on rejections. The baseline completes step one for the Program's own
first account and submits step two with the cookie unmodified. The variant
submits step two with the account-naming cookie rewritten to a second account
the Program also controls. The control submits it with that cookie set to an
invented account name, where a distinct unknown-account answer shows the value
is read rather than ignored -- without it a differing rejection could be the
endpoint echoing whatever it was handed.

Every arm here is a rejection, so no account moves and there is no
`state_change` to file -- and this Playbook's bar asks for one in the variant
role for either direction, so this reading closes no Test and grades nothing. It
stops at an Observation: a response to a presented credential is exactly what
`credential_effect` is for, and `promote_proposal` files each rejection under
that kind from its own Receipt, as the argument for a reading that does move an
account. Two accounts, both the Program's, and only wrong codes.

## 5. Propose the claim

Propose it with `mcp__rk2__propose_finding`, naming improper_authentication
as its `vulnerability_class` and citing the account read-backs rather than the
action's status: that argument takes a vulnerability_classes id, not a dotted
Property class, and property_class_vulnerability_classes maps this Playbook's
class to that id.

The gate is `rk2_finding_refusal`, which opens nothing without the transition
`close_test_replay` wrote. The claim is supported where the account changed
under an arm the factor did not run for, and refuted where every arm is answered
the way the invented assertion is and the account is unchanged after each. A
control that was not refused refutes nothing, because the run then measured a
route enforcing nothing at all, which is a different and larger claim. This
section proposes no Test of its own and grades nothing.

## 6. Where a reading halts, and what is refused

Three halts are a person's decision, asked for with `mcp__rk2__park_for_human`
given the running Task's `task_label` and the `question_code` that names why.
Every arm here changes an account, so the first arm of a session parks under
destructive_action before it is sent. An Identity with only one factor
enrolled, or a second account the Program has not issued, parks under
credential_needed rather than being improvised. A submitted code that could
succeed against an account that is not the Program's parks under
third_party_impact, before sending.

The writer is `park_task_for_human`. Every other halt is a reading that ran out
-- one accepted factor name, one successful replay, one action that took effect
-- and no question code says that, so those are reported through the Task's own
record.

One reading is refused. Establishing the challenge the server advertises by
reading the `WWW-Authenticate` header is blocked: that name is stripped from the
agent's view of every response on every path, and no assertion kind is
header-shaped to name it with even if it arrived, so ticket 172 owns the audited
reveal that would change it. What runs instead is section 1 -- drive the route
honestly once and record the request the client sent for the factor step, which
is caller-side and fully visible.

This section performs and grades nothing. 3 of 6 steps cannot be graded.
