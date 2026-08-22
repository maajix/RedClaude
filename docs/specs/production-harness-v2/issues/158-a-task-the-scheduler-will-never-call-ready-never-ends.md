# 158 — A Task the scheduler will never call ready never ends

**What to build:** The half of 143's second criterion that 143 did not pay. A
pending Task with no attempts, whose readiness predicate has named the same
fact about its own row for `max_attempts` consecutive passes, ends — with the
predicate on the record, and without ending work that is merely early.

**Blocked by:** nothing.

**Status:** resolved

- [x] **The counter is on the row and costs one UPDATE.** `tasks.unready_passes`
      is incremented by the pass that finds a Task unready and reset to 0 by the
      pass that finds it ready, so it counts the current run rather than a
      lifetime total. `rank_pass` already touches every pending Task in step
      (2); no new table and no timer, because a timer would make the rule depend
      on how often an operator runs the pass.
- [x] **Terminal means a fact about the Task's own row.**
      `rk2_terminal_predicate(text)` is the whole of the rule, written as a
      function so an operator reading "why did this Task end" reads one list:
      `no_subject`, `no_hypothesis`, `no_test`, `no_finding`. Every other
      `ready_for` arm reads a row somewhere else, and every one of those can
      change with no change to the Task.
- [x] **`no_address` is not on that list, and 157 is why.** A subject has an
      address when this Program holds an Application on its name, and recon
      promotes Applications — so a name that carries none today can carry one
      next pass. `ChainUnlockTest` holds the case and would have gone red:
      two hunt Tasks on `technology` subjects read `hunt.no_address` for five
      passes and are still the Tasks the chain arithmetic is about. A
      permanently addressless subject is 159's problem — nothing proposes the
      Host or the Application — and is not paid for by ending work that may
      become runnable.
- [x] **Work that is merely early is untouched.**
      `report.no_validated_finding` is unready for as many passes as it takes
      somebody to validate a Finding. Ending it would end the one Task that
      writes the report, which is the same failure `cancel_reason_for`'s own
      `report` exception exists to stop.
- [x] **It ends the way 143 ends the same state from the other side.**
      `retire_task` — `abandoned` / `undispatchable`, with the predicate as the
      sentence on a `task.retired` event. Not a new `abandoned_reason` word per
      predicate, and not a predicate thrown away to fit the existing vocabulary.
- [x] **Checked by something that would go red.**
      `tests/test_database.py::UnreadyTaskTest` stands three Tasks side by side
      — one unready for its own row, one unready for the queue, one ready — runs
      `max_attempts` passes, and asserts which one ended, on which pass, with
      which sentence, while the other two are exactly where they started.

## Why

143 put the address question in `ready_for` so a Task the runtime cannot serve
never reaches the slate. That worked, and `rk2hunt16` proved it: the pass
survived, exit 0 on all five laps, where `rk2hunt4` had died. It also left this:

```
T3  hunt  pending  ready_for -> hunt.no_address  cancel_reason_for -> none
```

Zero attempts, five laps, never offered, never ended — which is exactly what
143's second criterion forbids ("And it does not stay pending either"). That
tick was set too early.

157 gave a Domain an address and un-stuck that particular Task. This ticket is
the general rule, and the two do not replace each other: 157 makes the runnable
work runnable, 158 ends the work that never was.

The T3 case itself is 157's, not this one's — see the second criterion. Writing
this rule is what made that clear: `hunt.no_address` looks like a fact about the
Task and is a fact about `applications`, and the first draft of
`rk2_terminal_predicate` had it in the list. `ChainUnlockTest` said no, in six
assertions, and it was right.

## Notes

**Deviation from the plan, stated:** the plan put the rule in
`cancel_reason_for`, "abandoned with that predicate as the reason". That cannot
be done as written. `tasks.abandoned_reason` is a closed vocabulary of eleven
words and `cancel_reason_for` returns one of them; `recon.no_address` is not a
word in it. Growing the vocabulary by one word per predicate would be the same
fact said twice, and dropping the predicate to fit the existing words would be
the fact said badly. 143 already minted the word for this exact state —
`undispatchable`, "the Task is well-formed and this runtime cannot serve it" —
and `retire_task` already writes the sentence into a `task.retired` event. So
the rule is a step in `rank_pass` that calls `retire_task`, and
`cancel_reason_for` is not touched at all.

The ceiling is `max_attempts` and deliberately not a new knob: it is the number
an operator already sets to say how many times this scheduler tries something
before giving up on it.

## How it was paid

`20261022T000000Z__a_task_the_scheduler_will_never_call_ready_ends.sql`:
`tasks.unready_passes`, `rk2_terminal_predicate(text)`, and two new steps in
`rank_pass` — (2b) the counter over what the cancellation left standing, and
(2c) the retirement of what the counter and the list agree on. The pass reports
`retired_unready` beside `abandoned`, in the return and on the
`scheduler.ranked` event, because one is work the engagement answered and the
other is work this installation could never start.

Ticket 143's second criterion now names this ticket as what paid it, and 143's
`How it was paid` says plainly that the tick was set on the runtime half alone.

Run: `CleanCreationTest ChainUnlockTest UnreadyTaskTest`, 38 tests, OK. Full
`tests.test_database` under the lock, OK.
