# 206 — One open question stops the whole campaign

**What to build:** A pass that has a question waiting on a human works the rest
of the queue anyway, and says `awaiting_decision` only when there is nothing
else left to work.

**Blocked by:** nothing.

**Status:** resolved

## What was measured

`rk2here`, 2026-08-26, after `20261208T000000Z` fixed the park that undid
itself. The campaign holds one open question and stops on every lap:

```
lap 01 -> task_attempted   | ok True  | exit 0
lap 02 -> task_attempted   | ok True  | exit 0
lap 03 -> refused          | ok False | exit 3
lap 04 -> awaiting_decision| ok True  | exit 0
STOPPING after 04: a decision is waiting
```

What the queue held at that moment:

```
decisions_open       1
task_hunt_parked     1
task_hunt_pending  414
task_recon_pending 220
task_perform_pending 1
```

One question, one Task parked for it, and 635 Tasks that nothing had asked a
question about. The campaign stopped for all of them.

Two laps of work per approval, against 231 distinct host entities in the
Program, is on the order of 300 stops -- each one needing a person before the
next two laps can run.

## The mechanism

`program._workable` refused the whole pass:

```python
    if state.pending:
        ledger.hold(
            "execution",
            f"{len(state.pending)} decision(s) are waiting on a human; nothing was claimed",
        )
        return False
```

`state.pending` is every unanswered row of `pending_decisions` for the Program,
so it is a Program-wide fact used to gate Program-wide work. But a question is
not a Program-wide fact. `park_authorized_tool_run` moves the one Task the
question is about to `parked`, which takes it out of `pending` and out of every
ready set the scheduler reads -- the Task is already held, by the only
mechanism that needs to hold it.

`_report` then made the same mistake one layer up, ranking the question above
the work:

```python
    elif pending:
        stop_reason = STOPPED_AWAITING_DECISION
    elif attempted:
        stop_reason = STOPPED_TASK_ATTEMPTED
```

So even a pass that did claim and work a Task reported `awaiting_decision`,
and every driver loop -- `tools/hunt-loop.sh` in this tree, `hunt.sh` in an
engagement -- reads that word as "stop and fetch a human".

## Why it surfaced now

Nothing in this tree had ever parked a Task in a live campaign until
`20261120T000000Z` gave every campaign a provisioned Identity and
`call_risk_rules:net_borrowed_identity` began answering `ask`. Before that,
`state.pending` was almost always empty and the gate cost nothing. It is the
same reason `20261208T000000Z` surfaced when it did.

## The second half, measured after the first was fixed

With the gate open, the next live pass claimed `T582`, dispatched it, and the
door asked about it -- `closure.task_status` read `parked`, which is
`20261208T000000Z` holding. And the pass still refused:

```
stop_reason: refused                       exit 3
VIOLATION invalid_configuration | TR351 is approval_required/ask by
          call_risk_rules:net_borrowed_identity: filed as D7 for a human to answer
```

`execution._unauthorized` files the question and then reports it with
`code=INVALID_CONFIGURATION`. `outcome.AWAITING_DECISION` exists to say exactly
why that is wrong, in its own comment: every other class "names a fault an
operator should go and fix, and the only action this one calls for is answering
it -- reported as a refused configuration it would read as a harness that broke
rather than a harness that stopped to ask."

Downstream it read worse than that. A violation makes `_report` call the whole
pass `refused` whatever else it did, so the fix above was undone one layer
higher: the campaign claimed a Task, worked it, parked it -- and still reported
the word a driver loop stops on. `hunt.sh` also counts a non-zero exit toward
its three-consecutive-fault streak, so three asks in a row ended a sitting as
if the harness were broken.

## What was changed

`_workable` holds the sentence and returns nothing. `_report` ranks an attempt
that was made above a question waiting on a human, so `awaiting_decision`
survives as the word for a pass that did no work -- which is exactly when a
driver loop should stop. `execution._unauthorized` holds the filed question
instead of failing on it; `proxy.send` still refuses on the same event, because
there the operator asked for one response and got none.

`tools/hunt-loop.sh` stopped on exit code 12, which `rk run` does not produce
for this -- a question is a hold and not a violation, so the pass exits 0. It
reads the pass's own stop word now, and stops on either of the two that mean
no Task was attempted.

## The measurement afterwards

The same campaign, same command, two questions open:

```
stop_reason: task_attempted | ok: True | exit: 0
task: T583 hunt
closure: {"task": "T583", "accepted": true, "task_status": "done", ...}
violations: []
open questions seen at start: 2
```

## What was not changed

The gate. `call_risk_rules` grades one call at a time at the door, and a
second Task that needs the same permission parks and asks for its own question
exactly as before. Nothing is auto-approved and nothing is escalated. The only
difference is that the questions accumulate for one sitting of an operator's
attention instead of stopping the campaign one at a time.

The attempt spent on a parked Task also stays spent, for the reason
`20261208T000000Z` gives: a child ran and reached a tool call.

- [x] A pass with an open decision and workable Tasks claims one and reports `task_attempted`.
- [x] A pass whose own Task parked on a question exits 0 and is not a refusal.
- [x] A pass with an open decision and nothing else to work reports `awaiting_decision`.
- [x] The question is still in the report's `pending_decisions` and in the ledger either way.
- [x] No change to `call_risk_rules`, to parking, or to who may answer a question.
