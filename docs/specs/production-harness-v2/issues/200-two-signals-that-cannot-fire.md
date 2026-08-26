# 200 — Two signals that cannot fire

**What to build:** a lane quota ladder that can be climbed, or the honest
removal of the two rules that pretend it can.

**Blocked by:** nothing.

**Status:** open

## What was measured

Database `rk2here`, 2026-08-26, at pass 81 of a live engagement.

```
recon_novelty       1.0000
recon_novelty_rise  0.0000
hunt_backpressure   0.0000
budget_fraction     0.0163
```

One lane quota epoch in eight hours, `breadth`, opened at pass 0 by the seed.
Policy 5's three rules are the only way off it and none of them has ever fired.

## The mechanism

**`deepen_on_recon_dry` needs `recon_novelty <= 0.34`.**

```sql
CREATE FUNCTION lane_signal_recon_novelty(p uuid) RETURNS numeric
LANGUAGE sql STABLE AS $fn$
    SELECT coalesce(max(novelty_for(t)), 0)
      FROM tasks t
     WHERE t.program_id = p AND t.kind = 'recon' AND t.status = 'pending';
$fn$;
```

A `max`. One pending recon Task on an unmapped subject pins it at 1.0, and a
campaign that is still finding hosts always has one. `0037:610` already says
this, about policy 1's **widen** rule: *`recon_novelty >= 0.67` is true for as
long as any unreconned endpoint exists*. Policy 5 fixed the widen rule by
making it edge-triggered on `recon_novelty_rise` and left the same signal
level-triggered in the deepen rule.

**`deepen_on_backpressure` needs `hunt_backpressure >= 2`.**

```sql
    SELECT CASE
        WHEN (SELECT s.headroom FROM scheduler_lane_state s
               WHERE s.program_id = p AND s.kind = 'hunt') > 0 THEN 0
        ELSE (SELECT count(*) FROM tasks t ...)
      END::numeric;
```

The guard's own comment is *a queue with a free slot is not backpressure, it is
a queue*, which assumes a free slot gets filled. It does not. Entitlement, not
capacity, is what gates the offer: on `breadth` hunt is min 0 of max 2, so
headroom is 2, the signal is 0, and 342 ready hunt Tasks wait behind it. The
signal can only rise in a profile that already gives hunt slots — which is a
profile you would only reach through this rule.

**`widen_on_new_surface` needs `recon_novelty_rise >= 0.34`.** The rise is
measured against the value the current epoch opened with. With novelty pinned
at 1.0 the rise is 0 forever. `0037:670` says this too, about the A/B: *the
shipped widen rule NEVER FIRED*, and ships policy 6 as the sensitive variant
rather than fixing it.

So all three rules of the shipped policy are known or now measured to be
unable to fire, and two of the three were already documented as such in the
file that ships them.

## What has to be decided

`tests/ab.sql` measured policy 1 against policies 2, 3 and 4 and picked 5. Any
change here has to go back through it, which is why ticket 199 did not touch
these functions and shipped a single-rung policy instead.

- **A signal that falls.** `recon_novelty` as a quantile or as the fraction of
  pending recon Tasks above a novelty, rather than a `max`. Falls as a surface
  is mapped, which is the sentence the rule wants. Changes what the A/B
  measured, so the A/B is owed again.
- **A backpressure that measures entitlement.** `min_slots = 0` rather than
  `headroom > 0`, reading the signal as *hunt work is ready and this rung gives
  hunt nothing*. Self-clearing: on a rung that floors hunt it returns 0 again.
- **Or delete the three rules.** Ticket 199 has already shown that a single
  well-chosen rung finishes a campaign, and a ladder is only worth its
  complexity if the climb is measurably better than the rung.

## Why

Two of these three rules were documented as unable to fire in the migration
that shipped them, and the third was measured that way here. A policy table
whose rows are known not to fire is a scheduler that reads as adaptive and
behaves as a constant, and the ledger it writes — one epoch in eight hours —
is the only place that says so.
