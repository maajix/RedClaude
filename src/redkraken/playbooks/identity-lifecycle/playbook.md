---
description: Ask whether a session survives the event that was supposed to end it, by driving one leased session across a logout or a credential change and replaying a request that only a live session answers, and by re-presenting a kept token after further authentications on a Task that leases no Identity.
bb:category: session_handling
bb:outputs: ["session_handling.lifetime"]
bb:triggers_all: ["cookie_parameter", "state_changing_method"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: constrained
bb:effects: mutates_session
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 50 as the v2 replacement for v1's identity-lifecycle pack, against the session-lifetime leaf of the ticket 18 vocabulary; v1 shipped a README for this topic and no reference text, so nothing is attached. Rewritten for ticket 101 against the merged technique ledger, which carries three readings for this slug. One frontmatter key moved and it is a repair, not a widening. The three legs asked for credential_effect, which close_test_replay never writes, and every Test below is an equality specification whose actions no differencing assertion names, so the kind each of its arms produces is response_invariant and the old bar was one no run could clear. All three legs now carry that kind, the refuted leg carries the kind its own role carries on supported, and the credential_effect readings the body still takes are filed in the context role beside the bar.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_invariant", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "response_invariant", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "response_invariant", "polarity": "supports", "min_count": 1}]
---

# Ask what the end of a session actually ends

Applications end sessions in three places and they are usually three different
pieces of code: the logout route, the credential change that is supposed to
invalidate every other device, and the administrative revocation. Each of them
can delete a cookie in the browser and leave the server side untouched, and the
browser is not where a stolen token is used.

The question is one probe repeated after each of those events: does the session
that answered a moment ago still answer?

## 1. Keep the probe in the slot, and establish what refusal looks like

Follow `use-identity`: the run acts as whichever Identity the Task was opened
under -- the step does not choose it and there is no argument for it -- and the
proxy holds the session. Sections 3 and 4 never read the cookie or the bearer and
do not need to. A call through a slot is already a request no browser took part
in, so a session that still answers one after the client was told to forget it is
exactly the reading this Playbook is after: the server side does not care what
the browser deleted.

Send one authenticated read through the label with `mcp__rk2__http_request` and
store the answer. That is the probe, and the same request is what every section
below repeats. What refusal looks like is the same read with nothing
attached, and neither this run nor any Test below can take it, since a lease owns
Cookie and every header it declares. Ask for it as a second Task through the
suggested tasks of `mcp__rk2__submit_mission_result`, which promote_proposal
writes, and let that run file its own credential_effect Observation from its own
Receipt in the context role -- an element citing another run's Receipt is dropped
as receipt_other_run, so this reading carries the answer and not the citation. A
route that answers `200` to a caller holding nothing is not a route that keeps
sessions alive too long, it is a route that never checked, and that is
`authentication.credential_verification` and somebody else's claim.

## 2. Trigger one ending, and only one

Pick the event the subject supports and cause it exactly once, and cause it
inside the Test that measures it: the logout route and the credential change are
both actions of a specification proposed with `mcp__rk2__propose_test` and
performed by the replay lane, which is what keeps the arms on either side of one
ending. One event per reading. Two endings at once and the answer says nothing
about either.

The administrative revocation is the third event and is not writable as a Test
here: it needs two Identities inside one specification, the revoked session and
the actor performing the revocation, and a Test's actions all run under the one
Identity the Task was opened under. That branch is a lead and is not graded. Ask
through `mcp__rk2__park_for_human` for this Task to be parked, its own label in
`task_label` and destructive_action in `question_code`, since the revocation is a
person acting on the target's own state.

## 3. Difference the probe across the logout

Propose the Test with `mcp__rk2__propose_test`. Four actions, and the order is
the reading. The baseline action is the probe. The first control action is the
probe sent a second time, unchanged. The second control action is the logout,
carrying the method, the url and the body a Test action has stated since ticket
211, and no assertion names it. The variant action is the probe sent once more,
after it. The logout is an action and never a setup step: setup runs before
action 1, so a logout there puts all three probes after the ending and the
reading measures nothing. Assert that the first control's body equals the
baseline's and that the variant's does too.

Both holding is the reading, and the direction is the opposite of most Tests in
this corpus: support means the session outlived the ending, so the assertion that
must hold is an equality. No differencing assertion names any action, so
close_test_replay derives response_invariant for every arm and settles the claim
supported, which is the kind all three legs of this Playbook's bar ask for. The
same assertion failing is the refutation -- the post-logout read no longer
answers as the probe did, and the ending took effect -- and close_test_replay
writes that leg too, from the same specification and in the same kind.

A third outcome is neither: an answer matching neither the probe nor the
refusal, a `500` after a logout, is a state the application did not expect rather
than evidence about session lifetime. Record it and stop. One condition has to
hold before any of this means anything: the lease behind the label has to be the
one the probe was spent under, so read the Receipts for both calls before
differencing, and where the label was re-leased in between the reading is
inconclusive and is reported as inconclusive through the Task's own record.
Repeat the probe once after a short wait where the target is a cluster: a
revocation that propagates in seconds is a different finding from one that never
happens, and reporting the first as the second is how a valid report becomes an
argument.

## 4. Ask whether a credential change ends what predates it

The change has to be the self-service one, performed by the account's own session
through the same label; that is what keeps the whole reading inside one Identity
and one Test. The baseline action is the probe and the control action is the
probe repeated. The change itself is a second control action carrying the new
credential in its body and named in no assertion, and the variant action is the
probe sent again afterwards. Assert the same
two equalities as section 3: both holding says the session that predates the
change is still live, which is the claim. close_test_replay writes the bar off
those assertions; a credential_effect edge the agent files beside it takes the
context role and names the mechanism rather than standing in for a leg.

A completed password recovery is the second spelling of the same ending and is
one reading at a time: where the Program supplies the reset link, complete the
recovery on the same account and replay the probe.

Where the rules of engagement do not clearly admit an account mutation, or the
account is one the Program did not designate, do not send the change. Park this
Task through `mcp__rk2__park_for_human`, naming it in `task_label` under a
`question_code` of destructive_action, and let a person decide. Record which
single ending was triggered, both probes, and the lease identity on each Receipt.

## 5. Ask whether the application bounds concurrent sessions

This reading is planned with no Identity slot, and that is not a preference. A
leased Identity owns Cookie and every header it declares for the origin and
replaces the caller's before the wire, so a Task holding a lease cannot present a
second credential at all and the arm that carries the whole reading would become
the arm it is meant to differ from. It runs on a Task with no leased Identity,
against an account the Program designated, and it needs credential material the
reading may itself present; where the door attaches the credential and the
reading may never see it, this section cannot be run and saying so is the result.

Authenticate once and keep the first token. The baseline action is a read of the
identity route presenting that token, the first control action is that read
repeated unchanged, and the variant actions are a declared further number of
authentications -- ten, not the hundred the older guidance suggests -- followed by
the same read presenting the first token again. Assert that the first control's
body equals the baseline's and that the final read's does too: both holding says
no cap was applied and no earlier session was invalidated. The same arm answers
the replay question, since a token re-sent unchanged after its stated expiry, or
one whose identifier was meant to be single-use, is the same reading.

Two more controls are worth their requests and both come last, because the first
of them ends the session the variant needs: the logout route with the first token
followed by the same read, which must be refused, and a read presenting a token
whose signature is deliberately corrupted, which must also be refused. If the
route honours either, it never checked the token and the variant says nothing
about concurrency. The declared count is fixed before the first login and is not
raised until an answer appears; where the account is one the Program did not name,
or the credential material is not the tester's own, ask through
`mcp__rk2__park_for_human` for the Task to be parked, its label in `task_label`
and credential_needed in `question_code`. Reaching the declared count is not that:
it is a reading that ran out, and it is reported through the Task's own record.

## 6. Propose the claim, and say what would refute it

The Hypothesis is `session_handling.lifetime` on the application, and it becomes a
Finding through `mcp__rk2__propose_finding`, which rk2_finding_refusal admits only
where the Test of section 3, 4 or 5 settled it. It is supported when the probe is
answered as a live session after the ending, against the control arm that shows
the same probe unchanged before it. It is refuted when the probe after the ending
stops answering as it did, and section 1's second Task is what says which of the
two answers a refusal is.

An absolute expiry is not this claim unless it was measured. "The token has a long
lifetime" read off a `JWT` payload is a statement about a claim in a document; the
finding is that the session still answered, which is a request and an answer.

## 7. Leave one ended session behind

This section is not a step the system grades. It is a standing constraint on
every section above and it names no verb, because its whole content is what not
to do.

This Playbook's effects are `mutates_session`: it ends one on purpose. It does
not end another Identity's session, it does not revoke devices it did not create,
and where the ending it needs is a credential change it stops unless the Program
admits that mutation. Its baseline is `stable_session` at the same time, which
reads like a contradiction and is not one. The baseline is the precondition: the
probe has to be a session nothing else is disturbing, or a refusal after the
ending says nothing about the ending. The effect is the consequence: section 2
ends that session. Because conflict is derived from one Playbook's baseline
against another's effects, the pair is what keeps this Playbook alone on a
subject -- nothing that moves a session is scheduled beside it, and it is
scheduled beside nothing that needs one held still. That is the right schedule for
a reading whose whole content is one session ending exactly once.

4 of 7 steps cannot be graded.
