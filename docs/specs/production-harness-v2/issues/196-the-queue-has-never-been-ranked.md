# 196 — The queue has never been ranked

**What to build:** whatever writes `expected_information_gain` and `potential_impact`, because nothing does, and without them the whole ranking is inert.

**Blocked by:** nothing.

**Status:** resolved

## What was measured

Database `rk2here`, 2026-08-26, after a full sitting and 734 Receipts.

```
entities | hypotheses | testable | tests | findings
     435 |         92 |       91 |     1 |        0
```

```
role         | agent runs
orchestrator |         81
recon        |         79
web_hunter   |          1
```

```
kind    | pending | done | abandoned
recon   |     276 |   44 |         3
hunt    |     152 |    0 |         0
perform |       1 |    0 |         0
```

The campaign has done one hunt. It has 91 claims it could test and has authored
one Test from them. It has never produced a Finding.

## The mechanism

Every step is checkable from the live schema.

1. `tasks.expected_information_gain` and `tasks.potential_impact` are NULL on
   all 480 Tasks that have ever existed in this Program, and have never been
   anything else:

   ```
   SELECT count(*) AS total, count(expected_information_gain) AS gain_set FROM tasks;
   -- 480 | 0
   ```

2. Nothing writes them. Every occurrence of either name in the migration corpus
   is a read — `jsonb_build_object`, a `SELECT` list, a comment. There is no
   occurrence at all in `src/redkraken/*.py`. Asked of the live schema, no
   function both mentions the column and writes to `tasks`:

   ```
   SELECT p.oid::regprocedure FROM pg_proc p
    WHERE p.prosrc ~ 'expected_information_gain'
      AND p.prosrc ~ '(INSERT INTO tasks|UPDATE tasks)';
   -- 0 rows
   ```

   Only `tests/` sets them, which is why every unit test of the ranking passes.

   And it is not this Program. Every other database on this machine says the
   same thing:

   ```
   rk2grade2:  5 tasks, 0 ranked
   rk2grade3: 23 tasks, 0 ranked
   rk2hunt:    2 tasks, 0 ranked
   ```

3. `value_for(t, w)` returns NULL when either is NULL:

   ```sql
   WHEN t.expected_information_gain IS NULL OR t.potential_impact IS NULL
       THEN NULL
   ```

4. `rank_pass` therefore writes NULL:

   ```sql
   priority = CASE WHEN r.direct_value IS NULL THEN NULL ELSE ... END
   ```

   Every other derived column is filled — all 480 Tasks have a `novelty`, a
   `safety_cost`, an `estimated_cost`. `priority` alone is NULL, on every row,
   always.

5. `rank_candidates()` orders by `priority DESC NULLS LAST, created_at, id`.
   With `priority` uniformly NULL that is FIFO by creation, and `offer_slate()`
   takes the first five of it.

6. The first recon Task was created at `18:51:01.999922` and the first hunt
   Task at `18:51:02.376201`. Recon is four tenths of a second older and there
   are more of them, so recon fills every slate.

## What it explains, including the parts that work

- **79 recon runs, 1 hunt run.** FIFO, and recon is first in line.
- **Hunt was offered exactly once.** `task_slate` holds 405 recon offers and 5
  hunt offers, and all five hunt offers are one slate at `22:07:20` — a moment
  when fewer than five recon Tasks were claimable, so the FIFO order reached
  the hunt lane. The orchestrator took one. That is the single `web_hunter` run.
- **One Test.** Tests are authored by hunts.
- **No Findings.** Findings come from Tests that were performed, and the one
  `perform` Task is still pending behind 276 recon Tasks.
- **435 entities.** Recon works. It is the only lane that has run.

## What this is not

**Corrected, 2026-08-26.** This section read *not the lane quota*, on the
grounds that `deficit` was 0 for both lanes and `entitled` false for
everything. That was a snapshot taken while a recon run was live, not a rule.
`deficit = greatest(min_slots - live, 0)` and this runtime claims one Task per
pass, so at claim time `live` is 0, recon's `deficit` is its `min_slots` of 1,
and recon's top Task is entitled on every pass. Entitlement sorts before
priority, so the quota is the other half of this — and it is the larger half.
Ticket 199 holds it. This ticket holds the ranking that decides the order once
entitlement has been settled.

Not ticket 193. That fixed novelty being blind to the Identity a Task acts in.
Novelty is computed correctly and then multiplied by a NULL.

Not something a unit test could have caught. `tests/test_database.py` sets both
columns by hand in every ranking fixture, so the formula is well tested and the
fact that nothing fills its inputs is invisible from inside the suite.

## What has to be decided

The column comment in `0006_tasks_and_runs.sql` says *model-estimated, kept
apart from runtime-computed so the eval suite can ask whose estimate was wrong*.
So the design says a model supplies them, and no verb was ever built for it.
Three ways out, and they are not equivalent:

- **A verb.** The orchestrator estimates gain and impact when it opens or claims
  a Task. Closest to the stated design, and it puts a model's guess at the centre
  of the scheduler.
- **A default.** Every Task starts at a per-kind prior — `scheduler_weights`
  already carries `cost_prior` and `safety_prior` per kind, so there is a place
  for it — and the model may refine it. Smallest change; makes the ranking work
  tomorrow; keeps the model out of the loop until someone wants it there.
- **Drop the two columns from the formula.** Rank on novelty, cost, safety and
  unlock alone, all of which are computed and correct today.

A standing check belongs with whichever is chosen: a Program whose Tasks are all
unranked is a Program running FIFO, and nothing said so for the whole of this
campaign.

## Answer

The default, which is the second of the three above.

- [x] **A per-kind prior, where the other priors already live.**
      `20261129T000000Z` gives `scheduler_weights` a `gain_prior` and an
      `impact_prior`, both jsonb keyed by kind, in the shape `cost_prior` and
      `time_prior` already have, read the way `cost_for` and `time_for` already
      read theirs. `value_for` takes the estimate where a Task carries one and
      the prior where it does not:

      ```sql
      w.w_gain   * coalesce(t.expected_information_gain, (w.gain_prior   ->> t.kind)::numeric)
    + w.w_impact * coalesce(t.potential_impact,          (w.impact_prior ->> t.kind)::numeric)
      ```

      `coalesce` on each side rather than on the pair, so a Task carrying one
      estimate and not the other uses the estimate it has. The columns keep the
      meaning their comment gives them: the day a verb writes them, the priors
      become what they say they are.

- [x] **The numbers, and that they are unvalidated.** Decision 16 says every
      number in this table is. Under the shipped `w_gain 0.4 / w_impact 0.6`
      they order the kinds as

      ```
      perform 0.72  hunt 0.70  conclude 0.57  validate 0.54
      analyze 0.46  report 0.40  recon 0.35
      ```

      A hunt resolves a claim either way and is the largest single reduction in
      uncertainty this harness makes; a perform is what turns a resolved claim
      into evidence; a recon is information by construction, but one subject is
      a small share of a map. Hunt is worth twice a recon, which is a sentence
      the scheduler could not say at all before.

- [x] **The standing check this ticket asked for.**
      `check_scheduler_closure` arm (a) asked this about `cost_prior` alone and
      now asks it about all three. With every registered kind priced, a NULL
      `priority` is unreachable rather than merely unlikely, so these three arms
      are the check — and there is no fourth one counting unranked queues,
      which would fire on every freshly seeded Program before its first pass.

- [x] **A kind nobody priced still ranks NULL.** Both coalesces fall through
      for a kind with no entry, which is the old behaviour and is now a standing
      problem rather than a silence.

- [x] **One fixture assumed an unranked Task would stay last.**
      `BudgetReservationTest.arrange_capped` seeded two recon Tasks worth 0.1
      and 0.2, and read the claim back as "whichever of my two was taken". The
      Task the claim actually takes is the recon Task `program.run` leaves
      behind when it opens the Program, which promises nothing and therefore now
      carries the 0.35 prior -- above both. The fixture, not the ranking, was
      wrong: it needs a Task the total no longer covers, and either of its two
      is one. It now takes the first that survives the claim.

      This is the whole of what the change moved. Two full runs of the database
      suite either side of it differ by this one class and nothing else.

## What this did not fix

Ranking decides the order **within** the entitled set, and entitlement is the
first sort key. A working `priority` does not start the hunt on its own: recon
still outranks hunt on the measured priors, because recon's `cost_prior` is
0.30 against hunt's 0.60. Ticket 199 is the other half.

## Why

The scheduler is the part of this harness that decides what to look at next. It
has never decided anything. Eight hours of a live engagement went into mapping
surface that nothing was ever going to hunt, and the record of that is 734
Receipts, 435 entities and no Finding — which reads like a quiet target rather
than a queue that was never sorted.
