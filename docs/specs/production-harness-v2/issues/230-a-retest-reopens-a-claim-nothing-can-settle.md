# 230 — A retest reopens a claim nothing can settle

**What to build:** Two halves of one file. Narrow `check_finding_candidates`
rule 3 so the watch lane's reopen does not stop every Program, and widen
`rk2_test_performance_frontier` so the reopened claim's Test is performed again
— which is the only thing that closes what the first half stays silent about.
Built and applied on 2026-08-31 as
`20270108T000000Z__a_retest_reopens_a_claim_the_hunt_can_settle.sql`.

**Blocked by:** nothing. 223 narrowed the same rule for the validation lane and
named this shape as the one it was leaving out.

**Status:** resolved

## What was measured, 2026-08-31

`rk2here` after six days. The campaign stopped at 03:39 UTC and the supervisor
stood down:

```
[2026-08-31T03:39:50] STOPPING: 4 restarts inside 15 minutes; the hunt is not
failing at the end of a run, it is failing at the start of one
lap 01 -> refused | ok False | exit 9
integrity_failed | standing:finding_candidates
```

One row, and it is the whole reason:

```
 problem                     | subject | detail
-----------------------------+---------+------------------
 finding_claim_not_supported | F12     | H215 is testable
```

At 03:25:29.444997 `refresh_negative_knowledge()` step (2) — the watch lane,
`20260814T080000Z:775-786` — moved H215 `supported -> testable` with the
rationale `retest trigger fired`, because the watched Application's response
fingerprint had changed:

```
 kind                         | fired_at
------------------------------+-------------------------------
 response_fingerprint_changed | 2026-08-31 03:25:29.444997+00
```

F12 is a `candidate` Finding on H215. Rule 3 refuses that pairing.
`standing_checks.program_scoped` is false for this row, so **one Program's
retest stopped every Program in the database** — the same sentence 223 wrote
about the validation lane.

## WALL 1 — nothing can close the window the watch lane opens

This is what makes 230 a different ticket from 223 rather than the same one
again. 223's window has a `validation_queue` row with a state that ends;
this one has nothing.

```
WALL    Three refusals, each read live and each correct on its own terms:

          rk2_hypothesis_hunt_frontier (20261012T000000Z:138-152)
            NOT EXISTS (... tasks k WHERE k.kind = 'hunt'
                          AND k.hypothesis_id = h.id)
            in ANY status. A claim that reached `supported` has a finished
            hunt Task, so it is refused for good. The header says so on
            purpose (:128-136): "If the claim is worth asking again, 034's
            retest trigger is what says so, and it moves the claim rather
            than minting a Task."

          rk2_test_performance_frontier (20261014T000000Z:284-304, confirmed
            live through pg_get_functiondef)
            NOT EXISTS (... test_replays tp WHERE tp.test_id = ts.id)
            NOT EXISTS (... tasks k WHERE k.kind = 'perform'
                          AND k.test_id = ts.id)
            A claim reaches `supported` through a replay, so its Test has
            both rows. Refused for good as well.

          hypothesis_retest_triggers.fired_at
            Set once and never cleared. `arm_retest_watches` is idempotent
            and leaves a fired watch alone (20260927T010000Z:292); no writer
            in the corpus NULLs the column or deletes the row.

        There is no `retest` Task kind (`task_kinds`, 0019_role_kinds.sql:57
        and the later additions). So the sentence the hunt frontier's header
        relies on -- that moving the claim is enough -- is false: nothing
        downstream turns the moved claim into work.

        Measured, not reasoned: of the 23 fired watches on `rk2here`, ten
        claims stood in `testable` with zero Tasks created since the fire.
        H215 had 0 pending Tasks and 0 Tasks of any kind created after
        03:25:29.

PRICE   One `CREATE OR REPLACE FUNCTION` on the performance frontier, one on
        `check_finding_candidates`, one new predicate function the two share,
        and one `runtime_verb_surface` row for it. No new table, no new
        column, no new Task kind, no new role.

        The way back already exists and is simply never entered:
        `open_test_replay` refuses only a replay that is in flight
        (`tr.status = 'running'`) and asks only that the claim be `testable`;
        `close_test_replay` settles it again (`20260815T000000Z:1857-1859`,
        last overridden `20260816T000000Z:1125-1129`).

PURPOSE Rule 3 exists so a Finding written around `open_finding` is caught. It
        was never for a state this runtime creates on purpose. And the retest
        lane exists so a claim is asked again when the target moves -- not so
        a claim is parked in `testable` where no frontier will look at it.

RULE    A window nothing closes is not a window. The exclusion in rule 3 is
        only honest because the frontier guarantees something closes it. Both
        halves ship together or neither does.
```

## WALL 2 — a verb the runtime holds must be declared

Found by the first test run, not by reading:

```
integrity_failed | standing:runtime_privileges
(runtime_holds_undeclared_verb,"rk2_retest_reopened_at(uuid, uuid)",
 "closed to PUBLIC and executable by rk2_runtime with no runtime_verb_surface row")
```

```
WALL    066's registry: `REVOKE ... FROM PUBLIC` plus `GRANT ... TO
        rk2_runtime` is exactly the pair `runtime_verb_surface` exists to
        name, and an undeclared one refuses every pass before any work runs.
PRICE   One INSERT, `added_by = '230'`.
RULE    The registry is the answer, not the grant. A predicate is not a verb
        an Agent reaches, but it is a function the runtime connection
        executes, and that is the only distinction the check makes.
```

## What was narrowed, and what was not

`rk2_retest_reopened_at(hypothesis, program)` answers when the retest lane last
reopened a claim without it settling since, and NULL when no such reopen
stands. Read off `fired_at` against the last settling transition rather than
off `hypotheses.status_changed_at`, and that is not a detail: the window has to
hold across `testable -> testing` as well, because a claim moves to `testing`
the moment the replay that closes the window opens. A `status_changed_at`
comparison would drop the exclusion in the middle of the replay it is waiting
for, and rule 3 would fire again.

Self-closing, so nothing has to clear `fired_at`: `close_test_replay` writes a
settling transition later than `fired_at` and the function answers NULL again.

Still reported, each deliberately:

- a claim that came back `refuted`, which is neither `testable` nor `testing`;
- a Finding on a claim nobody asked to reopen;
- a validation lane that finished `done` and left the claim unsupported, which
  is the refutation the packet is meant to show;
- 223's whole exclusion, which is untouched and asserted by the migration's own
  self-check.

Verified on `rk2here` before the migration was applied, read-only against the
live rows: the new exclusion silences exactly one Finding (F12), and the
widened frontier admits ten Tests, TST111 among them.

## Acceptance

- [x] **The narrowed rule silences the reopen and nothing else.** One Finding
      on the live rows, measured before applying: F12.
- [x] **The widened frontier admits the reopened Test and nothing else.** Ten
      Tests, all ten on a claim with an open retest window; with no window
      standing the cut point is `-infinity` and both `NOT EXISTS` read exactly
      as they did.
- [x] **`rk db migrate` applies it.** 245 migrations recorded on `rk2here`,
      `check_finding_candidates()` returns 0 rows,
      `rk2_test_performance_frontier` returns 10.
- [x] **The corpus still applies from empty.** `CleanCreationTest`,
      `CandidateFindingTest`, `BlindValidationTest`, `ValidationCommandTest`,
      `FindingClaimTest`, `NegativeControlTest` and `RetestReopenTest`: 107
      tests, OK. `tests.test_migrate`: 30 tests, OK.
- [x] **The four gates stay green.** `check_audit`, `check_wiring`,
      `check_baseline`, `check_coverage` all exit 0. W3 goes 210 -> 211 verbs
      granted and 527 -> 528 reached, with `5 owed` unchanged, so the new verb
      is reached rather than added to the debt.
- [x] **The window closes for real, not on paper.** `RetestReopenTest` fires
      the watch through `refresh_negative_knowledge()`, replays the same stored
      Test a second time through `performed`, and asserts
      `rk2_retest_reopened_at` answers NULL afterwards.
- [x] **The hunt runs again.** `./hunt.sh 1 0` on `rk2here`:
      `lap 01 -> task_attempted | ok True | exit 0`. The pass derived three
      `perform` Tasks (T1339/TST2, T1340/TST22, T1341/TST35) against the
      ceiling of 3 and the frontier went 10 -> 7.

## What this does not change

- No transition rule. `testable -> supported` is still illegal,
  `testable -> testing` still requires a Receipt.
- No data. No claim, no Finding, no Receipt was touched.
- `rk2_hypothesis_hunt_frontier` is untouched. The way back runs through the
  Test the claim already has; a second `hunt` Task for a claim that has one
  would be work the corpus deliberately refuses.
- `standing_checks.program_scoped` for `finding_candidates` stays false. That
  one Program can still stop every other one is a separate ticket;
  `program_configuration` is the only row in the corpus with `true`
  (`20260830T000000Z:169-172, 233-236`).
- Ticket 129 (no tool reads `negative_knowledge`) and the six unmapped Property
  classes from ticket 114 stay open.

## What else the same session had to clear

Neither is this ticket's work and both stood between the fix and a running
hunt, so they are written down rather than remembered:

1. **The six `rk2_*` passwords.** `tests/test_database.py::_build` provisions
   every login role with a fresh `secrets.token_urlsafe(18)` per run and never
   puts them back, and the roles are cluster-global — so a suite run takes the
   login away from every live engagement on the server. Written up as
   `restore-roles.sh` in the engagement folder; it takes the exclusive side of
   `/tmp/rk2-db.lock` and resets all six from `secrets.sh`. Run it after any
   database test run.
2. **Four decisions past their deadline.** `standing:control_surface` reported
   `decision_past_deadline_unswept` for D34-D37, which expired at 04:28-05:36
   while the hunt was down and nothing was running `rk decision sweep`. One
   sweep cleared them. This is ticket 224's subject, not one this file touches.
