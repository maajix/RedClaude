# 223 — A window nothing closes is not a window

**What to build:** Narrow `check_finding_candidates` rule 3 so the reproduction
window the validation lane opens on purpose is not read as an integrity
violation. Built and applied on 2026-08-30 as
`20261223T000000Z__the_reproduction_window_is_the_validation_lanes_own.sql`.

**Blocked by:** nothing.

**Status:** resolved

## What was measured

`rk finding validate` calls `reopen_for_reproduction` (`validation.py:66`,
`20260815T180000Z:783`), which moves the Finding's claim `supported -> testable`
so the Test can be replayed. `check_finding_candidates` rule 3
(`20260815T120000Z:970-981`) reports a `candidate` Finding whose claim is not
`supported`. The two are the same row.

The migration that added the reopen priced the collision in its own header
(`20260815T180000Z:777-782`) and decided to accept it:

> The window between this verb and the replay's close is a Finding on a claim
> that is not `supported`, which 036's `finding_claim_not_supported` reports and
> is meant to ... It is not narrowed here. The runtime holds the window inside
> one command, and an operator who sees it has seen something true.

**The premise is false in this runtime.** Ticket 222 is why: the replay half
could not run at all, so the command opened the window and returned. Measured on
`rk2here` after one `rk finding validate` at 00:08:37 on 2026-08-30:

```
 problem                     | subject | detail
-----------------------------+---------+------------------
 finding_claim_not_supported | F8      | H160 is testable
```

```
integrity_failed | standing:finding_candidates
lap 01 -> refused | ok False | exit 9
```

The standing family gates every pass and `standing_checks.program_scoped` is
false for this row, so **one Program that asked for a validation stopped every
Program in the database**. It stayed stopped for the next nine hours, because
nothing in the tree moves a claim back out of `testable` without a Receipt:

- `testable -> supported` directly: `illegal transition testable -> supported`
- `testable -> testing` to walk it back: `transition testable -> testing
  requires a tool receipt`
- `abandon_validation`: answers `nothing_open` and moves no claim
- deleting the Finding: `finding_proposals rows are immutable`

Every one of those refusals is right. What was wrong was the check.

## The wall, priced

```
WALL    check_finding_candidates rule 3 (`20260815T120000Z:976-981`), read
        live out of `pg_get_functiondef` 2026-08-30, against
        `reopen_for_reproduction` (`20260815T180000Z:783`) read the same way.
        Both ends: the verb that writes the state and the check that refuses
        it.
PRICE   One `CREATE OR REPLACE FUNCTION` and one `AND NOT (...)`. Everything
        the predicate needs is already there -- `validation_queue.state` has
        carried `queued`/`running`/`done` since 011. No new table, no new
        column, no grant.
PURPOSE The check exists so a Finding written around `open_finding` is caught.
        It was never for the lane that writes this state on purpose, and a
        check that stops the whole runtime over a state its own runtime
        creates is not reporting, it is a deadlock.
RULE    Capability before catalogue. The data is honest and stays untouched:
        the claim, the Test, the six Receipts and every transition are what
        they were. What changed is the sentence read over them.
```

## What was narrowed, and what was not

The rule keeps its whole reach except one shape: a claim in `testable` or
`testing` whose Finding holds a `queued` or `running` row in
`validation_queue`. That claim is on its way back through the replay the lane
asked for, and `reopen_for_reproduction` is the only thing that puts it there.

Still reported, each deliberately:

- a claim reopened by 034's negative-knowledge retest, which asked for no
  validation;
- a claim that came back `refuted`, which is not `testable` or `testing`;
- a Finding on a claim nobody asked to validate;
- state `done` -- a lane that finished and left the claim unsupported is the
  refutation the packet is meant to show, not a window.

Verified on `rk2here` before applying, as a read-only query over the live rows:
the rule as it stood matched exactly one row (`F8`, `H160 testable`, queue
`queued`) and the narrowed rule matched none.

## Acceptance criteria

- [x] **The narrowed rule matches the reproduction window and nothing else.**
      Measured against the live table before the migration was applied.
- [x] **`rk db migrate` applies it and the gate stays green.** 233 migrations
      recorded, every standing check `0 problem(s)`, `violations: []`.
- [x] **The corpus still applies from empty.** `CleanCreationTest`,
      `CandidateFindingTest`, `BlindValidationTest` and `FindingClaimTest`: 61
      tests, OK.
- [x] **The check reads clean on a Program that has been validated.**
      `check_finding_candidates()` returns 0 rows after `rk finding validate`
      ran end to end on `rk2here`.

## What this does not change

Nothing about the transitions. `testable -> supported` is still illegal,
`testable -> testing` still requires a Receipt, and a Finding is still
immutable. The claim this ticket unblocked came back to `supported` the way
every claim does -- by a replay that held.

This is not ticket 222's fix and does not pretend to be. It stops one unrunnable
command from taking the runtime with it. 222 is what made the command runnable.
