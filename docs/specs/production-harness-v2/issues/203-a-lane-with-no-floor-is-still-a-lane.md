# 203 — A lane with no floor is still a lane

**What to build:** a slate that cannot empty a whole lane out of the picture,
so a kind floored at zero competes rather than disappears.

**Blocked by:** nothing.

**Status:** resolved

## What was measured

`SlateClaimTest` seeds one Task of each of five kinds and claims each in turn.
Under ticket 199's `chain` profile the first claim was refused:

```
23514: task T1 is not on the current slate
```

with seven Tasks pending and a slate of five:

```
slate   validate, report, hunt, analyze, hunt
pending T1 recon 0.152, T2 hunt 0.171, T3 analyze 0.361, T4 validate 0.696,
        T5 report 0.602, T6 hunt 0.598, T7 hunt 0.199
```

Six of the seven are of kinds `chain` floors. `recon` is floored at 0, so it is
unentitled, and `offer_slate` ordered `entitled DESC, rnk` and then took
`slate_size`. Six entitled candidates against five seats: the whole slate is
entitled and recon is not merely last, it is absent.

## What it costs on a live campaign

`rk2here`, the same hour:

```
hunt pending 342     recon pending 220     perform pending 5
```

Three hundred and forty-seven entitled Tasks against five seats. The two
hundred and twenty recon Tasks were not competing on priority and losing — they
could not be offered at all, and a hunt that finds a new host writes another
recon Task that also cannot be offered. Recon was off, permanently, and nothing
said so.

## What ticket 199 got right and what it left out

`20261130T000000Z` set recon to 0 so that it would "compete on priority", and
wrote down correctly that `min_slots` is a priority class rather than a
concurrency floor. What neither half says is what happens at the truncation:
entitlement decides the ORDER, and `slate_size` then decides how much of that
order anybody sees. A kind at the back of an order longer than the slate is a
kind that does not exist.

## Answer

- [x] **The first cut reserved a seat for the wrong thing.**
      `20261202T000000Z` held the last seat for the best UNENTITLED candidate.
      That is one seat for a class, and the class has more than one lane in it.
      Measured immediately after it was applied:

      ```
      candidates  T4 validate e=t r=1   T7 hunt  e=f r=5
                  T5 report   e=t r=2   T2 hunt  e=f r=6
                  T6 hunt     e=t r=3   T1 recon e=f r=7
                  T3 analyze  e=t r=4
      slate       T4, T5, T6, T3, T7
      ```

      The held seat went to T7 — an unentitled *hunt*, because hunt's deficit is
      1 and T6 had taken it. The recon lane was still absent and the claim was
      still refused. What starves is a lane, and a lane starves the same way
      whether the Tasks in front of it are entitled or not.

- [x] **`20261203T000000Z` seats every lane before it fills the rest.**
      `in_kind` numbers each lane's candidates on their own, `in_kind = 1` is
      that lane's best, and those sort to the front of the truncation. A Program
      with fewer pending kinds than seats offers every kind it has plus the best
      of the remainder; a Program with more kinds than seats offers the
      best-ranked kinds — never one kind twice while another has nothing.

- [x] **Nothing about what the runtime claims moves.** The ordinal is still
      `entitled DESC, rnk`, so the argument-free `claim_task()` — which is what
      `execution.CLAIM` calls — still walks to the best entitled Task first.
      What the lane seat restores is the orchestrator's ability to *see* the
      alternative and name it with `mcp__rk2__pick_task`, which is the whole
      reason a slate is a list rather than a single answer.

- [x] **A Program with no starved lane offers exactly what it offered before.**
      Sorting on `(in_kind = 1) DESC` is a no-op when every lane already has its
      best candidate inside the first `slate_size` rows, which is every Program
      whose pending kinds fit the slate.

- [x] **`rank_candidates()` is untouched.** An unaffordable Task is still not a
      candidate, so `test_an_unaffordable_task_is_not_offered` holds and the
      race `claim_task` documents at its `unaffordable` arm is still the only
      way to reach it.

- [x] **The fixture that found this was itself two versions stale.** Two of
      `SlateClaimTest`'s assertions were written before the profile and the
      derivation they depend on:

      - `test_only_what_the_lane_has_room_for_is_entitled` expected the top of a
        six-recon slate to be entitled. Ticket 199 floored recon at 0, so the
        Lane is short of nothing and no entry is entitled.
      - `arrange_model_and_effort` claimed its five seeded Tasks by label and
        expected them to be the Program's only Tasks. Each `cls.finding` mints a
        testable Hypothesis for the Finding to be a finding of, and `rank_pass`
        derives a hunt Task for every testable claim no hunt Task names — so the
        Program holds three hunts, and the seeded one is not the best of them.
        The fixture now claims whichever Task of the kind the slate holds, which
        is what it was ever asking about: the role a kind is claimed as.

## Why

Two hundred and twenty Tasks that cannot be offered is a lane that is off, and
the queue reports it as a lane that is merely behind. The scheduler's own
numbers say `pending 220` right up to the moment somebody asks why nothing has
been mapped in a day.
