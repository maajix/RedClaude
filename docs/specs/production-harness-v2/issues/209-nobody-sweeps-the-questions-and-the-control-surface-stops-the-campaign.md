# 209 — Nobody sweeps the questions, and the control surface stops the campaign

**What to build:** A driver loop retires the questions whose deadline passed, so
a campaign is not stopped by the state its own integrity check forbids.

**Blocked by:** nothing.

**Status:** resolved

## What was measured

`rk2here`, 2026-08-27 06:12. Sitting 12 was started and refused three times in
a row without attempting a single Task:

```
lap 01 -> refused | ok False | exit 9
lap 02 -> refused | ok False | exit 9
lap 03 -> refused | ok False | exit 9
STOPPING after 03: 3 laps in a row exited non-zero
```

The report, in full:

```json
{"code": "integrity_failed",
 "source": "standing:control_surface",
 "detail": "3 problem(s): (decision_past_deadline_unswept,D18); (decision_past_deadline_unswept,D19); (decision_past_deadline_unswept,D20)"}
```

The three questions, and the window nobody used:

```
label  created_at            deadline_at           window
D18    2026-08-26 20:49:20   2026-08-27 00:49:20   04:00:00
D19    2026-08-26 20:57:01   2026-08-27 00:57:01   04:00:00
D20    2026-08-26 20:58:43   2026-08-27 00:58:43   04:00:00
```

All three are the same shape: `POST matrix.router.hereapi.com/v8/matrix`,
`call_risk_rules:net_unsafe_method`, one per Identity slot.

## The mechanism

`check_control_surface()` rule 3:

```sql
SELECT 'decision_past_deadline_unswept', d.label
  FROM pending_decisions d
 WHERE d.status = 'pending' AND d.deadline_at <= now()
```

`program.py` runs the control surface as a standing check, so the problem is a
violation, so the pass is `refused` and `rk run` exits 9. Not for one Task --
for the Program. Every pass, until somebody sweeps.

The sweeper exists. `expire_due_decisions()` is written, `decisions.sweep` calls
it, `rk decision sweep` exposes it, and `--every` exists so it can be left
running. Nothing ever ran it. The harness has always assumed a companion
process that no driver in this tree starts.

## Why the campaign was already stopped when it happened

Sitting 11 filed the three questions between 20:49 and 20:58 and ended on its
own 180-minute deadline at 21:45. The questions' deadlines fell at 00:49 --
three hours after the last process that could have swept them had exited. So
the state the integrity check forbids was reached with nothing running, and the
next thing to start found the door shut.

That is the shape of it: the sweep is needed exactly when nothing is running,
and it was only ever available while something was.

## What was changed

One statement at the top of each lap, in `tools/hunt-loop.sh` and in this
engagement's own `hunt.sh`:

```sh
rk decision sweep 2>&1 | tee -a "$LOG" || true
```

Inline rather than a daemon. It is one statement, it wants no second process to
reap, and a sweep is only ever needed where a pass is about to be made. Its exit
code is deliberately not the lap's: a sweeper that cannot reach the database is
a fault `rk run` reports for itself one line later, and counting it twice would
end a sitting on one fact reported two ways.

This does not shorten any question's window. A question filed at the top of a
lap has the whole four hours it was given; what changes is that the lap after
the fourth hour retires it instead of refusing over it.

## What it does not fix

The deadline still expires questions an operator was asleep for, and the Task
behind each becomes `abandoned/decision_timeout`. That is `expire_due_decisions`
doing what it says, and the window is a Program's setting, not this loop's. If
four hours is the wrong promise for a campaign hunted overnight, the promise is
what to change.

- [x] A driver loop sweeps before each pass.
- [x] A campaign with a past-deadline question runs instead of refusing.
- [x] A sweeper that cannot reach the database does not end the sitting by itself.
- [x] No question's answering window is shortened.
