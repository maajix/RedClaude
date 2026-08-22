# 156 — A supported claim opens no work

**What to build:** A Task kind that puts a role holding `propose_finding` in
front of a claim the runtime has settled, so a campaign that proves something
writes it down instead of stopping one step short.

**Blocked by:** nothing.

**Status:** resolved

- [x] **The kind exists everywhere a kind has to exist.** `task_kinds`,
      `role_task_kinds`, a default `scheduler_lanes` row, a slot in all three
      `lane_quota_profile_slots` profiles, and `cost_prior` and `time_prior`
      entries. `check_role_kind_mapping`, `check_scheduler_closure` and
      `check_lane_quota_closure` all enumerate the vocabulary, and a kind
      missing from one of them is a Task that is ranked and never offered.
- [x] **A settled claim becomes exactly one Task, once.** `rk2_finding_frontier`
      names the claims at `supported` that a replay settled, that are still
      canonical, whose subject is in scope, that no Finding rests on and that no
      `conclude` Task already names in any status. `derive_finding_claims` opens
      them under a ceiling of its own, and `rank_pass` calls it.
- [x] **The pass that derives one does not end it in the same breath.**
      `cancel_reason_for` reads a claim at `supported` as an answered question
      and abandons the Task asking it. That is correct for every kind that
      existed before this one and exactly backwards for the kind that exists
      *because* the claim settled. The arm now excepts `conclude` on a
      `supported` claim and nothing else — a refuted claim still answers a
      conclusion.
- [x] **The novelty is a real question rather than a second exception.**
      `novelty_for` scores a `conclude` Task 1 while no Finding rests on its
      claim and 0 once one does, so the trailing "nothing left to learn"
      sweep needs no `conclude` in its kind list. 152's `report` exception
      documents why the hard-coded list is the weaker of the two.
- [x] **The child is told what this Task is, and it is not a measurement.**
      `roster.web_hunter` gains the kind — it already holds `state.propose` and
      `net.request` — and `execution.Claimed.objective` builds a different
      paragraph for it: the claim is supported, nothing further needs to be
      measured, and the one call owed is `propose_finding` with a class and a
      title.
- [x] **Checked by something that would go red.**
      `tests/test_database.py::FindingClaimTest` walks one Test that settles its
      claim and one that does not, runs four passes, and asserts the Task is
      derived once, is still alive after the pass that could have cancelled it,
      is never opened against the unsettled claim, and ends as `answered` once
      the Finding exists.

## Why

`rk2hunt16` on 22 August is the first run in this tree where the chain ran end
to end:

```
receipts 10   observations 16   hypotheses 2   evidence 8
tests 1       test_runs 1 (replay, holds)      findings 0
```

And then:

```
20:40:18.861  test_run -> holds ; hypothesis H2 -> supported
20:40:18.888  agent_run AR8 (performer) done ; task T5 (perform) done
lap 5         nothing_to_execute
```

`propose_finding` lives in the tool group `state.propose`
(`src/redkraken/roster.py`), held by `recon`, `web_hunter` and `js_analyst`.
Nothing opened a Task for any of the three against a claim at `supported`, so
no child was ever asked to write the Finding down.

`validate` is not that step and cannot be made into it: `ready_for`'s validate
arm wants a candidate Finding that already exists, and `validator` holds only
`validate.judge`. Validation is what happens *after* the Finding.

## Notes

Built on 152's precedent for `perform`
(`src/redkraken/migrations/20261014T000000Z__an_authored_test_is_performed_by_a_task.sql`),
which is the whole shape of adding a kind. The one thing 152 did not have to
deal with is section 4: a `perform` Task's claim is `testable` while it runs,
and a `conclude` Task's claim is `supported` before it starts.

`conclude` is deliberately not something a model can ask for.
`rk2_promote_tasks` opens `recon` Tasks from a child's suggestion and drops
every other kind as `unopenable_kind`; the runtime derives this one from a
transition it wrote itself, and a model asking for it would be a model asking to
conclude.

## How it was paid

`20261021T000000Z__a_supported_claim_becomes_the_finding_it_earned.sql`, in
seven sections: the kind and its four seats (vocabulary, role, lane, quota
profiles, priors), `ready_for`'s arm with `conclude.no_hypothesis`,
`conclude.claim_not_supported`, `conclude.already_found` and
`conclude.no_address`, `novelty_for`'s arm, `cancel_reason_for`'s one
exception, `rk2_finding_frontier` and `derive_finding_claims`, `rank_pass`
step (3e), and the two `runtime_verb_surface` rows.

Runtime side: `roster.TASK_KINDS` and `roster.ROLES["web_hunter"].task_kinds`,
and `execution.MISSIONS` plus `Claimed._conclusion`, which is the objective a
`conclude` child reads instead of the send-a-request-and-submit paragraph every
other kind gets.

Run: `CleanCreationTest FindingClaimTest`, 17 tests, OK. `tests.test_execution`
and `tests.test_roster`, 277 tests, OK. Full `tests.test_database` under the
lock, OK.
