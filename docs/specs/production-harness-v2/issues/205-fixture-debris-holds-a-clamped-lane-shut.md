# 205 — Fixture debris holds a clamped lane shut

**What to build:** `CampaignRecoveryTest` back to green, and the three separate
reasons it went red written down, because only one of them is a fixture fault.

**Blocked by:** nothing.

**Status:** resolved

## What was measured

`tests.test_database.CampaignRecoveryTest`, the last red class after 201 and
204, against a disposable server on 2026-08-26.

```
ERROR: setUpClass (tests.test_database.CampaignRecoveryTest)
AssertionError: ('control', 24)
```

The assertion is `restart`'s: a restart claims exactly when there is something
to claim. Twenty-four Tasks pending and the pass was offered nothing.

```
tasks:  analyze claimed 1, hunt abandoned 2, hunt parked 1,
        recon claimed 8, recon done 24, recon pending 24, validate done 3
lanes:  ('recon', 'recon', min 0, max 1, live 8, headroom 0, deficit 0)
stuck:  T25 analyze / T26 T27 T28 T29 T31 T32 T37 T38 recon
        all claimed, lease live, one Agent run each, still open, no stop reason
```

Eight Tasks in a lane of one slot.

## The mechanism, part one: nothing ends a manufactured claim

Two helpers write a Task straight into `claimed` with a half-hour Lease,
because the verbs under test refuse a run whose Task is not held and
`claim_task` needs a slate these fixtures are not running:

- `claimed_agent_run`, through `agent_run_of`, once per offline-tool run and
  once per browser mission;
- `ReplayFixture.replay_run`, once per replay — and the investigation performs
  seven.

Neither ends what it began. Every other class in the module can afford that
because none of them runs the scheduler afterwards. This one does, and ticket
199's `chain` profile caps `recon` at the role's one concurrent slot, so the
first manufactured Task takes the only slot and every pass after it is offered
an empty slate.

`scheduler_lane_state.live_slots` counts Tasks in `claimed` or `running`
whatever is behind them, which is correct: a slot is a slot. The product path
cannot produce this state at all — `claim_task` refuses a full lane — so there
is no verb whose job is to undo it.

## The mechanism, part two: the campaign then reaches work it never had

With the lane open the campaign runs on past where it used to stop, and the
first thing it finds is correct behaviour the fixture had never seen:

```
Violation(code='invalid_configuration', source='database',
  detail='TR36 is approval_required/ask by call_risk_rules:net_borrowed_identity:
          filed as D4 for a human to answer')
```

From the investigation onwards each campaign holds a provisioned Identity, and
`20261120T000000Z` derives the second state of every subject the moment one
exists. A recon Task acting as somebody is a borrowed credential on the wire,
`call_risk_rules` answers `ask`, and `execution._unauthorized` files the
question rather than deciding it. That is the harness asking a person, not a
restart that failed to recover.

It does not run out. Each round of `rk run` derives more of the second state
from what the last round mapped, so draining it is a treadmill — measured, at
sixty rounds, still deriving.

## The mechanism, part three: the comparison counted the treadmill

Criterion 5 compares the two campaigns row by row. Two of those rows moved:

```
decisions: 7 != 6
control  credential_needed  GET a10.example.net/ (identity member)
control  credential_needed  GET a19.example.net/ (identity member)
injected credential_needed  GET a10.example.net/ (identity member)
```

Both campaigns file one such question per leftover pass. The injected campaign
has fewer leftover passes because its stops consume them, so the count is the
schedule and not the knowledge. The three `impact_unauthorized` questions the
investigation itself asks are identical in both.

The same tail flipped the parity of the last orchestrator session: a pass that
parks spends a turn and stops, so with `max_turns` 2 the injected campaign ended
inside its seventeenth session rather than at the end of it.

## Answer

- [x] **`close_lane_runs` ends what the fixture manufactured.** Every run from
      `agent_run_of` and `replay_run` is recorded, and released, ended and its
      Task abandoned as `superseded` by the owner — symmetrically with how it
      was begun. `abandoned` and not `done` because `enforce_task_completion`
      refuses `done` for a Task no proposal of which was promoted, which is
      right: this Task never carried work to promote. It runs after each lane
      command, at the head of every `restart`, and after the last judgement.

- [x] **A parked question is not a failed restart.** `restart` and `drain` allow
      a violation whose detail is the campaign filing a question for a human,
      and nothing else. The assertion that a restart claims exactly when there
      is something to claim is untouched.

- [x] **The decisions projection is scoped to what the investigation asked.**
      `credential_needed` is excluded and the reason is in the query. Every
      question this comparison was written for is still compared.

- [x] **A campaign may end inside a session.** The ceilings assertion now reads
      every session but the last as closed by a configured ceiling, and the last
      as either closed by one or still open. What is a statement about the
      ceilings — that nothing else ever ends a session — is unchanged.

- [x] **Green.** `Ran 24 tests in 280.427s / OK`.

## Why

A lane cap the fixtures had never met, met. Ticket 199 gave `recon` one slot on
the `chain` profile and the manufactured claims had been free until then; 191
gave every subject a second state and the approval gate had never been reached.
Neither is a bug, and between them they took a whole class down.
