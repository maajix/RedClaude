# 199 — No rung of the ladder can finish a campaign

**What to build:** a lane quota profile on which the last three links of the
chain are reachable, because on all three shipped profiles they are not.

**Blocked by:** nothing.

**Status:** resolved

## What was measured

Database `rk2here`, 2026-08-26, after eight hours and 81 passes.

```
epoch | profile | reason | opened_at_pass | opened_at
    0 | breadth | seed   |              0 | 2026-08-25 18:19:44.924567+00
```

One epoch. The program has never moved off the rung it was seeded on.

```
role         | agent runs        kind     | pending | done
orchestrator |         81        recon    |     220 |   79
recon        |         79        hunt     |     342 |    0
web_hunter   |          1        perform  |       1 |    0
```

```
hypotheses | testable | tests | findings
        92 |       91 |     1 |        0
```

```
task_slate: 405 recon offers, 5 hunt offers
            all five hunt offers are one slate
```

Ninety-one claims this campaign could test, one Test authored from them, and
one `perform` Task that has been pending since the single hunt that authored
it.

## The mechanism

`rank_candidates()` sorts entitlement first and priority second:

```sql
SELECT o.id, o.kind, (o.in_lane <= o.deficit) AS entitled, o.rnk
  FROM ordered o
 ORDER BY (o.in_lane <= o.deficit) DESC, o.rnk;
```

and `deficit = greatest(c.min_slots - coalesce(live.n, 0), 0)`, where `live`
counts running Agent runs.

This runtime claims one Task per pass. `execution._claim`'s own docstring is
*One Task off the slate*, and the child is launched after the claim returns. So
at every claim `live` is 0 for every lane, `deficit` is exactly `min_slots`, and
a lane with a floor is permanently below it.

**`min_slots` is therefore not a floor. It is an absolute priority class.** A
lane at 0 is not unreserved, it is last, always, and it is reached only on a
pass where no floored lane holds a single claimable Task.

`breadth` gives recon 1 and hunt 0. There have been 220 or more claimable recon
Tasks at every pass of this campaign. So hunt was reachable exactly once — the
one pass on which zero recon Tasks were claimable, which is the one slate of
five hunt offers in `task_slate` and the one `web_hunter` run in `agent_runs`.

## What it explains, including the parts that work

- **79 recon runs and 1 hunt run.** Recon holds the only floor on this rung.
- **91 testable hypotheses and 1 Test.** Tests are authored by hunts.
- **The `perform` Task has never been claimed.** `perform` is min 0 on every
  rung, so it is behind 220 recon Tasks and 342 hunt Tasks forever.
- **No Finding.** A Finding needs `conclude`, which is min 0 on every rung.
- **435 entities.** Recon works. It is the lane the floor was pointed at.

## Read as priority classes, no rung can produce a Finding

The chain is `recon -> hunt -> perform -> conclude -> validate -> report`.

```
           recon  hunt  analyze  perform  conclude  validate  report
breadth      1     0       0        0         0         1        0
balanced     1     1       0        0         0         1        0
depth        0     2       1        0         0         1        0
```

`perform`, `conclude` and `report` are 0 on all three.

`20261014T000000Z` and `20261021T000000Z` each gave their new kind a floor of 0
and each said why: *a floor would be holding a slot for work that is not there
yet*. That is true of a reservation and false of a priority class. A lane with
no claimable Task contributes no rows to `rank_candidates` at all, so its floor
costs nothing while it is idle. What the 0 buys is not thrift. It is a
guarantee that the last three links of the chain never run.

## And the ladder cannot climb

Policy 5's two exits from `breadth` are both unreachable. Measured now:

```
recon_novelty       1.0000
recon_novelty_rise  0.0000
hunt_backpressure   0.0000
budget_fraction     0.0163
```

- `deepen_on_recon_dry` needs `recon_novelty <= 0.34`, and
  `lane_signal_recon_novelty` is `max(novelty_for(t))` over pending recon. One
  unmapped subject pins it at 1.0. `0037:610` already says this about policy
  1's **widen** rule — *true for as long as any unreconned endpoint exists* —
  and policy 5 fixed the widen rule and left the same signal level-triggered in
  the deepen rule.
- `deepen_on_backpressure` needs `hunt_backpressure >= 2`, and
  `lane_signal_hunt_backpressure` returns 0 whenever the hunt lane has
  headroom. On `breadth` hunt is min 0 of max 2, so headroom is 2 and the
  signal is 0 with 342 ready hunt Tasks waiting. It can only rise in a profile
  that already gives hunt slots.

## Answer

- [x] **A rung the whole chain can run on.** `20261130T000000Z` adds profile
      `chain` (rung 3):

      ```
      recon 0  hunt 1  analyze 1  perform 1  conclude 1  validate 1  report 1
      ```

      Four kinds run as subagents — recon, hunt, analyze, conclude — and
      `max_concurrent_subagents` is 3, so at most three of the four may carry a
      floor. recon gives it up, because recon is the lane that has run and the
      lane whose floor starved the other six. It is not switched off: it
      competes on `priority` like any unfloored lane, and on a fresh Program it
      wins every early pass by default, because at the start of a campaign
      nothing else has a claimable Task at all.

- [x] **One floor is enough.** In a runtime that claims one Task per pass the
      number decides how many of a lane's Tasks appear entitled in a five-entry
      slate and nothing else, because the claim takes the first entry either
      way. A 2 buys slate composition and spends a subagent cap that a seventh
      lane would rather have.

- [x] **Policy 7, seeded and held, with no rules.** The third policy in this
      table with none. A rule needs a signal, and the two signals that could
      carry one are the two measured above as unable to fire. A policy that
      listed them would read as a ladder and behave as a rung. Policy 5 stays
      as a row: its rules are what `tests/ab.sql` measured.

- [x] **The live Program is carried, not climbed.** `advance_lane_quota` reads
      the seed only for a Program with no epoch, so `rk2here` was moved with
      `force_lane_quota('chain', ...)`, which writes `reason = 'operator'` and
      a human actor into the ledger. That is the honest record.

- [ ] **The two signals are not touched.** Both are wrong about what they
      measure and both were measured in `tests/ab.sql`. Rewriting a measured
      signal on a reading is how the ladder got here. Ticket 200.

## Why

Eight hours of a live engagement produced 734 Receipts, 435 entities, 92
hypotheses and no Finding. The record of that reads like a quiet target. It was
a queue in which the three lanes that turn work into a Finding were sorted last
on every rung of a ladder that could not move.
