# 218 — A corpus rewrite retires its stranded Tasks under the wrong reason

**What to build:** A cancel reason that says a Task's frozen Playbook selection
names a corpus this installation no longer carries, so the scheduler retires it
for what actually happened rather than spending three passes to call it
`attempts_exhausted`.

**Blocked by:** nothing.

**Status:** ready-for-agent

## What was measured

Ticket 101 rewrote all 50 Playbooks, so every `source_sha256` moved. The
`rk2here` engagement was migrated onto it on 2026-08-29 and the next `rk run`
refused:

```
integrity_failed | corpus | T731 was selected playbooks/browser-framing/playbook.md,
                           which this installation does not carry at the digest
                           the selection froze
```

Measured over the whole engagement, not off the one Task the run named:

```
316 selections, all 316 stale, across 142 Tasks
766 Tasks pending; 14 of them carry a stale selection; 36 rows, 8 of them active
223 done and 80 abandoned Tasks keep their frozen digests, and should
```

The refusal is correct and this ticket does not ask for it to soften.
`execution.py:2775-2779` states why: such a record "would describe something
other than what the model read, and a grading run against it would be reading
the wrong document."

## The harness does clear this on its own

Measured rather than assumed. One pass was run and the counters read either
side of it:

```
before: 14 stranded Tasks, attempts summing to 15
after:  13 stranded Tasks, attempts summing to 13
        T732 -> status abandoned, abandoned_reason attempts_exhausted
```

A corpus refusal counts as an attempt, `cancel_reason_for` retires a Task at
`max_attempts` (`0023_scheduler_ranking.sql:548`, `max_attempts = 3` here), and
the queue drains itself. **No SQL is needed and none should be written**: a
`DELETE` on `playbook_selections` is refused by `reject_mutation_unless_purging`
(`0013_events.sql:13-21`), and `20260809T213000Z__program_configuration.sql:82-85`
says why -- "so a program purge can still delete the rows and nothing else can."

So the capability is there. Three things about it are wrong.

## What is actually wrong

**1. The reason is a lie.** `cancel_reason_for`
(`0023_scheduler_ranking.sql:539-585`) knows eight reasons -- `program_closed`,
`budget_exhausted`, `attempts_exhausted`, `out_of_scope`, `superseded`,
`answered`, `near_duplicate`, and `settled_negative` from
`20260814T080000Z__a_refutation_is_kept_and_made_due.sql:881`. None of them is
"the corpus moved". The Task did not exhaust its attempts on the work; it was
never allowed to start. An operator reading `attempts_exhausted` on 13 Tasks
reads three failed tries each, which is not what happened.

**2. It costs a full pass per attempt.** 12 Tasks at 2 attempts each was 24
passes when this was measured, each one a complete `rk run` that opens the
Program, ranks the queue, claims a Task and refuses. The scheduler already knows
the selection is stale at ranking time -- it could cancel there, in the pass it
already makes, for nothing.

**3. It kills the hunt loop.** `hunt.sh` stops after three non-zero laps in a
row, and every corpus refusal is one. A queue that was two passes from clearing
reads as a broken harness. The engagement's `hunt.sh` now carries an exception
for it, capped at 40, in the same shape as the ticket-195 capability-ceiling
exception beside it -- which is a workaround in an engagement script, not a fix.

## The wall, priced

```
WALL    cancel_reason_for (0023_scheduler_ranking.sql:539-585) has no reason for
        a selection frozen at a corpus this installation dropped, so the only
        exit is the attempts counter at :548, three passes later.
PRICE   One predicate in a function that already runs on every pending Task
        every pass, plus a reason string. Both ends exist: `playbook_selections`
        carries `playbook_sha256`, `playbooks` carries `source_sha256`, and the
        join is the one `execution.py:2800-2812` already makes. The reason
        vocabulary is not an enum -- `abandoned_reason` is free text written by
        the same UPDATE at :664 -- so adding one costs no migration to a type.
PURPOSE An engagement should survive a corpus rewrite without spending a pass
        per attempt and without an exception in its hunt loop.
RULE    capability before catalogue.
```

Whether the new reason should also cover `playbook_version` drift or only
`source_sha256` is the open question: `execution.py:2802` refuses on either, and
a version-only mismatch is the same document under a changed projection.

## Acceptance criteria

- [ ] **A stranded Task is cancelled in the pass that ranks it**, not three
      passes later, and `abandoned_reason` names the corpus rather than the
      attempt counter.
- [ ] **The count is measured either side.** Same command as above: stranded
      Tasks and their attempt sum, before and after one pass, on a database
      where the corpus really moved.
- [ ] **A finished Task keeps its frozen digest.** The audit reading of a
      completed run is what the freeze is for.
- [ ] **The refusal at `execution.py:2800-2812` still fires** for an active
      stale selection that reached execution anyway. This ticket widens no door.
- [ ] **`hunt.sh`'s exception can come out.** The engagement script carries a
      `STRANDED` counter today; when the scheduler cancels these at ranking
      time, no lap refuses and the exception is dead code. Removing it is how
      this ticket proves itself.

## What this does not change

`playbook_selections` freezing `playbook_sha256` and `playbook_version` at
selection, and `reject_mutation_unless_purging` keeping those rows immutable.
Both are what make an old hunt result readable at all, and this ticket depends
on them.
