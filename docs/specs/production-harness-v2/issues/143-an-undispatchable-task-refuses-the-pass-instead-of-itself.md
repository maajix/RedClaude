# 143 — An undispatchable Task refuses the pass instead of itself

**What to build:** An ending for a Task the dispatch slice cannot serve that
costs that Task and not every pass after it, and the readiness predicate that
would keep such a Task off the slate in the first place.

**Blocked by:** nothing.

**Status:** ready-for-agent

- [ ] **A Task nobody can dispatch does not take the pass down with it.** Two
      steps in `execution.Slice._run` refuse with `ledger.fail`: the target step
      at `execution.py:1616`, when the subject carries no address, and the role
      step at `execution.py:1643`, when the role the roster gives the kind holds
      no `net.request`. `_pass` claims one Task per pass, so one such Task at the
      top of the ranking refuses every later pass with `ok: false` and exit 3.
      Measured on 2026-08-22: an `analyze` Task opened by hand against an
      Application in `rk2hunt4` did exactly this.
- [ ] **And it does not stay pending either.** Skipping it forever is the same
      wedge at a slower rate, with an attempt spent each pass until
      `max_attempts` parks it. Whatever the pass does with it, the Task ends and
      the ending says why.
- [ ] **`ready_for` answers "this subject carries no address".** A `recon` Task
      is ready today on two grounds -- it has a subject and the subject is in
      scope (`0023_scheduler_ranking.sql:468`) -- and neither is the question
      `execution.STARTED` asks, which is whether the subject is an Application or
      an Endpoint under one. Moving it there fixes the wedge for every producer
      at once and lets `scheduler_idle_report` name the predicate.
- [ ] **The roster decision is not quietly reversed.** `roster.ROLES` withholds
      `net.request` from `js_analyst` on purpose -- *"an analyst that fetches is
      a hunter with the wrong quota"* -- and `reporter` is a renderer with no
      served surface at all. If this ticket changes either, it changes the
      roster where the decision is written and says why there.
- [ ] **Checked by something that would go red.** The covering
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
