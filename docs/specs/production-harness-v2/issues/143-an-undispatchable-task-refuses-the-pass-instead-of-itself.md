# 143 — An undispatchable Task refuses the pass instead of itself

**What to build:** An ending for a Task the dispatch slice cannot serve that
costs that Task and not every pass after it, and the readiness predicate that
would keep such a Task off the slate in the first place.

**Blocked by:** nothing.

**Status:** resolved

- [x] **A Task nobody can dispatch does not take the pass down with it.** Two
      steps in `execution.Slice._run` refuse with `ledger.fail`: the target step
      at `execution.py:1616`, when the subject carries no address, and the role
      step at `execution.py:1643`, when the role the roster gives the kind holds
      no `net.request`. `_pass` claims one Task per pass, so one such Task at the
      top of the ranking refuses every later pass with `ok: false` and exit 3.
      Measured on 2026-08-22: an `analyze` Task opened by hand against an
      Application in `rk2hunt4` did exactly this.
- [x] **And it does not stay pending either.** Skipping it forever is the same
      wedge at a slower rate, with an attempt spent each pass until
      `max_attempts` parks it. Whatever the pass does with it, the Task ends and
      the ending says why. **Paid by 158, not by this ticket** — see the note in
      "How it was paid" below. What shipped here was the runtime half; the
      scheduler half is `rank_pass` steps (2b) and (2c).
- [x] **`ready_for` answers "this subject carries no address".** A `recon` Task
      is ready today on two grounds -- it has a subject and the subject is in
      scope (`0023_scheduler_ranking.sql:468`) -- and neither is the question
      `execution.STARTED` asks, which is whether the subject is an Application or
      an Endpoint under one. Moving it there fixes the wedge for every producer
      at once and lets `scheduler_idle_report` name the predicate.
- [x] **The roster decision is not quietly reversed.** `roster.ROLES` withholds
      `net.request` from `js_analyst` on purpose -- *"an analyst that fetches is
      a hunter with the wrong quota"* -- and `reporter` is a renderer with no
      served surface at all. If this ticket changes either, it changes the
      roster where the decision is written and says why there.
- [x] **Checked by something that would go red.** The covering
      `tests/test_database.py` classes are named and run under `flock` with
      `CleanCreationTest` in the same invocation, and a `tests/test_execution.py`
      case holds the pass to surviving a Task it cannot dispatch.

## Why

Split out of ticket 142, which measured both and deliberately did not fix
either.

142 needed a suggested Task to become a real Task, and it needed the Tasks it
opens to be dispatchable. It got there by refusing the four kinds and the
subject types this runtime cannot serve at the moment the suggestion is read,
under `unopenable_kind` and `no_address`, so that a good result does not queue
work that wedges the harness. That is the right answer to "what should promotion
open". It is not an answer to "what should the pass do with an undispatchable
Task", which is what this ticket is, and it does nothing at all for a Task that
arrives from anywhere else -- an operator's hand, or whatever ticket 140 builds.

The `ready_for` half was left alone in 142 for a stated reason and not an
oversight. It is the scheduler's own predicate, read by the ranking, the claim
and the idle report, and exercised by a large part of a 1359-test module that
142 was not able to run: `tests/test_database.py` rotates cluster-global role
passwords at `:313` and the live engagement was in flight. A predicate moved
into the scheduler's hot path on an argument rather than on a measurement is not
a move worth making blind.

## Notes

142's walk asks the address question itself, in `rk2_promote_tasks`, against
`applications` and `endpoints` -- the two typed rows `execution.STARTED`
resolves a URL from. If this ticket moves that question into `ready_for`, that
branch becomes redundant and should go: `open_task` already asks `ready_for`
after the insert, so the walk would inherit the refusal as
`refused_by_invariant` with the predicate's own name in it.

## How it was paid

**One criterion was ticked early, and 158 is what paid it.** This ticket shipped
the runtime half of criterion 2: a Task the dispatch slice cannot serve is
retired instead of refusing the pass. The scheduler half -- a Task the readiness
predicate will never clear, which is never dispatched at all and so never
reaches `retire_task` -- was left open, and `rk2hunt16` measured it: T3 held at
`hunt.no_address` for five laps with zero attempts and no ending. 158 is the
counter and the rule that ends it; 157 is what made that particular Task
runnable instead.


Two halves, because two different things know the answer.

The half the database knows is the address. `rk2_subject_addressable(uuid)` asks
the one question `execution.STARTED` resolves a URL from -- is this Entity an
Application, or an Endpoint under one -- and `ready_for` reads it, returning
`recon.no_address` and `hunt.no_address`. A Task like that is never ranked,
never offered and never claimed, and `scheduler_idle_report` names the predicate
the same way it names every other one. `analyze` is deliberately not guarded
this way: what stops an `analyze` Task is the roster, not the address.

The half the database does not know stays in the runtime. Whether a role can
start as an isolated child, and whether it holds `net.request`, are facts of
`roster.ROLES`; putting them in SQL would be the roster decision written in a
second place, which criterion 4 refuses. So `execution.Slice._run` keeps
deciding and gains `retire_task(uuid, text)` to end the Task it cannot serve:
the three `ledger.fail` sites became `Slice._retire`, which ends that one Task
as `abandoned` for the new reason `undispatchable`, records a `task.retired`
event carrying the detail, and holds rather than fails -- so the pass goes on to
the next Task instead of ending at `ok: false`.

`retire_task` rather than a fourth argument to `finish_task_attempt`: an attempt
that never happened is not one to spend. `retire_task` rather than
`cancel_reason_for`: that would need a list of kinds in SQL that the roster is
free to change under it.

142's `no_address` branch in `rk2_promote_tasks` stays, against the Notes above.
Inheriting the refusal as `refused_by_invariant` would be true and useless: a
named drop reason is what the model reads back, and `no_address` says what to do
differently where the generic one does not.

Migration `20261019T000000Z__an_undispatchable_task_ends_itself.sql`. Covered by
`tests.test_database.FirstTaskTest` (the predicate and the addressability
question, run with `CleanCreationTest` in the same invocation) and by
`tests.test_execution.RefusalTest` (the pass survives all three, and the one
refusal left is a Task that could not be retired either).
