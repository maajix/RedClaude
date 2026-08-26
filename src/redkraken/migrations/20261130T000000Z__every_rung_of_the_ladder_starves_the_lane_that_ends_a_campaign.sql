-- ---------------------------------------------------------------------------
-- 20261130T000000Z__every_rung_of_the_ladder_starves_the_lane_that_ends_a_campaign.sql
--
-- A rung a campaign can finish on.
--
-- Measured on `rk2here`, 2026-08-26, after eight hours and 81 passes: one lane
-- quota epoch, `breadth`, opened at pass 0 and never left. 80 child runs, 79 of
-- them `recon` and one `web_hunter`. 92 hypotheses, 91 of them testable, one
-- Test, no Finding. 342 pending hunt Tasks, 220 pending recon Tasks, and one
-- pending `perform` Task that has been pending since the single hunt.
--
-- WHY MIN_SLOTS 0 IS NOT "NO FLOOR". `rank_candidates()` sorts
--
--     ORDER BY (o.in_lane <= o.deficit) DESC, o.rnk
--
-- so entitlement is the FIRST key and priority is the second, and
-- `deficit = greatest(min_slots - live, 0)`. `live` counts running Agent runs.
-- This runtime claims ONE Task per pass -- `execution._claim` is "one Task off
-- the slate" and the child is launched after the claim -- so at every claim
-- `live` is 0 for every lane, `deficit` is exactly `min_slots`, and a lane with
-- a floor is permanently below it.
--
-- Which turns `min_slots` from a concurrency floor into an absolute priority
-- class. A lane at 0 is not "unreserved", it is LAST, always, and it is reached
-- only on a pass where no floored lane has a single claimable Task. `breadth`
-- gives recon 1 and hunt 0; there have been 220 or more claimable recon Tasks
-- at every pass of this campaign; so hunt was reachable exactly once, on the
-- one pass where zero recon Tasks were claimable. `task_slate` records that
-- pass: 405 recon offers and 5 hunt offers, and all five hunt offers are one
-- slate.
--
-- READ THAT WAY, NO RUNG CAN PRODUCE A FINDING. The chain is
-- recon -> hunt -> perform -> conclude -> validate -> report, and:
--
--     breadth   recon 1  hunt 0  analyze 0  perform 0  conclude 0  validate 1  report 0
--     balanced  recon 1  hunt 1  analyze 0  perform 0  conclude 0  validate 1  report 0
--     depth     recon 0  hunt 2  analyze 1  perform 0  conclude 0  validate 1  report 0
--
-- `perform`, `conclude` and `report` are 0 on every rung. `20261014T000000Z`
-- and `20261021T000000Z` each gave their new kind a floor of 0 and each said
-- why -- "a floor would be holding a slot for work that is not there yet" --
-- which is true of a reservation and false of a priority class. A lane with no
-- claimable Task contributes no rows to `rank_candidates` at all, so its floor
-- costs nothing when it is idle; what the 0 buys is not thrift, it is a
-- guarantee that the last three links of the chain never run.
--
-- AND THE LADDER CANNOT CLIMB. Policy 5's two exits from `breadth` are both
-- unreachable, for reasons this file only reports:
--
--   * `deepen_on_recon_dry` needs `recon_novelty <= 0.34`, and
--     `lane_signal_recon_novelty` is `max(novelty_for(t))` over pending recon.
--     One unmapped subject pins it at 1.0. `0037:610` already says this about
--     policy 1's WIDEN rule -- "true for as long as any unreconned endpoint
--     exists" -- and policy 5 fixed the widen rule and left the same signal
--     level-triggered in the deepen rule. Measured now: 1.0000.
--   * `deepen_on_backpressure` needs `hunt_backpressure >= 2`, and
--     `lane_signal_hunt_backpressure` returns 0 whenever the hunt lane has
--     headroom. In `breadth` hunt is min 0 of max 2, so headroom is 2 and the
--     signal is 0 with 342 ready hunt Tasks waiting. It can only rise in a
--     profile that already gives hunt slots. Measured now: 0.0000.
--
-- WHAT THIS FILE DOES AND DOES NOT DO. It does not touch either signal. Both
-- are wrong about what they measure and both were measured in `tests/ab.sql`;
-- rewriting a measured signal on a reading is how the ladder got here, and
-- ticket 200 is where that belongs with an A/B behind it. What this file does
-- is name one rung the whole chain can run on, and ship a policy that seeds it
-- and holds. A ladder whose every exit is unreachable is already a single rung.
-- This makes that true on purpose and picks a rung that works.
--
-- WHY `chain` LOOKS LIKE IT DOES. Four kinds run as subagents -- recon, hunt,
-- analyze and conclude -- and `max_concurrent_subagents` is 3, so at most three
-- of the four may carry a floor. recon is the one that gives it up, and the
-- reason is the measurement at the top: recon is the lane that has run, and it
-- is the lane whose floor starved the other six. It is not switched off. It
-- competes on `priority` like any unfloored lane, and on a fresh Program it
-- wins every early pass by default, because at the start of a campaign nothing
-- else has a claimable Task at all.
-- ---------------------------------------------------------------------------

INSERT INTO lane_quota_profiles (profile, rung, description) VALUES
 ('chain', 3,
  'every link of recon -> hunt -> perform -> conclude -> validate -> report carries a floor except recon, which competes on priority; the one rung on which a campaign can reach a Finding');

-- Every kind, because `check_lane_quota_closure` rule (a) refuses a profile
-- that names fewer: a kind left out silently reverts that lane to the default,
-- which is a quota move nobody wrote down.
INSERT INTO lane_quota_profile_slots (profile, kind, min_slots) VALUES
 ('chain', 'recon',    0),
 ('chain', 'hunt',     1),
 ('chain', 'analyze',  1),
 ('chain', 'perform',  1),
 ('chain', 'conclude', 1),
 ('chain', 'validate', 1),
 ('chain', 'report',   1);

-- One is enough for every floor. In a runtime that claims one Task per pass the
-- number decides how many of a lane's Tasks appear entitled in a five-entry
-- slate and nothing else -- the claim takes the first entry either way -- so a
-- 2 buys slate composition and spends the subagent cap that a seventh lane
-- would rather have.

UPDATE lane_quota_policies SET active = false WHERE version = 5;

INSERT INTO lane_quota_policies (version, seed_profile, min_dwell_passes, active, notes)
VALUES (7, 'chain', 4, true,
        'ticket 199: one rung, seeded and held. Policy 5 is kept as a row -- its rules are what tests/ab.sql measured and ticket 200 re-measures.');

-- No rules, deliberately, and it is the third policy in this table with none.
-- A rule needs a signal, and the two signals that could carry one are the two
-- this migration's header shows cannot fire. A policy that listed them would
-- read as a ladder and behave as a rung; this one says which it is.

-- An existing Program keeps the epoch it is on -- `advance_lane_quota` only
-- reads the seed when a Program has no epoch at all -- so a campaign already
-- under way is moved by `force_lane_quota('chain', ...)`, which is the human's
-- verb and writes `reason = 'operator'` into the ledger. That is the honest
-- record: this Program did not climb here, an operator carried it.


DO $$
DECLARE n integer; d text; s jsonb;
BEGIN
    SELECT count(*), string_agg(problem || ' ' || detail, '; ')
      INTO n, d FROM check_lane_quota_closure();
    IF n > 0 THEN
        RAISE EXCEPTION 'ticket 199: the new rung left % problem(s): %', n, d;
    END IF;

    -- The claim this file is named for, asked of the rows rather than of the
    -- prose: on this rung every kind that ends a campaign carries a floor.
    SELECT string_agg(kind, ', ' ORDER BY kind) INTO d
      FROM lane_quota_profile_slots
     WHERE profile = 'chain' AND min_slots = 0 AND kind <> 'recon';
    IF d IS NOT NULL THEN
        RAISE EXCEPTION 'ticket 199: chain still starves %', d;
    END IF;

    -- And the rung the old ones could not reach is still described, so that the
    -- comparison ticket 200 owes has both sides of it in the schema.
    SELECT count(*) INTO n FROM lane_quota_profiles
     WHERE profile IN ('breadth','balanced','depth','chain');
    IF n <> 4 THEN
        RAISE EXCEPTION 'ticket 199: % of the four rungs are present, expected 4', n;
    END IF;

    -- One active policy, and it is this one.
    SELECT count(*) INTO n FROM lane_quota_policies WHERE active AND version = 7;
    IF n <> 1 THEN
        RAISE EXCEPTION 'ticket 199: policy 7 is not the active policy';
    END IF;
END $$;
