-- ---------------------------------------------------------------------------
-- Ticket 201, criterion 5: being nobody is not a credential the lane can run
-- out of
--
-- WHAT WAS LEFT. `20261201T000000Z` stopped `claim_task` taking an Identity
-- Lease on the anonymous Identity, because an anonymous Identity is the absence
-- of a credential and there is nothing about it to hold exclusively. Ticket 201
-- wrote down that the other half of the same mistake was still standing and
-- that it would cost nothing "while the driver claims one Task per pass". It
-- costs something now.
--
-- `scheduler_lane_state.headroom` bounds a clamped lane by the Program's
-- unheld Identities:
--
--     CASE WHEN c.clamp_to_identity_leases
--          THEN least(greatest(c.max_slots - live, 0), coalesce(free.n, 0))
--          ELSE greatest(c.max_slots - live, 0) END
--
-- `free` counts every Identity nothing holds. Since 20261201 nothing ever holds
-- the anonymous one, so a Program whose only Identity is the anonymous one
-- counts exactly one free credential forever -- and a clamped lane reports
-- headroom 1 however many slots its role has. Under ticket 199's `chain`
-- profile `hunt` is `web_hunter`, whose `max_concurrent` is 2, so the second
-- hunt of a Program that acts as nobody is refused `lane_full` by a lane that
-- is not full.
--
-- Measured: `IdentityClampTest.arrange_anonymous` builds two hunts over one
-- anonymous Identity and reads `headroom` before the first claim. It is 1. Its
-- own comment says "two free slots, one free Identity", which was the
-- observation this file is the correction to -- one free Identity is not a
-- bound when the Identity is nobody, because nobody may be acted as by any
-- number of runs at once.
--
-- THE RULE. Where the Program has an anonymous Identity available, the clamp
-- does not bind at all. Not "counts as many": there is no number of anonymous
-- runs the supply refuses, and writing one in would be a second arbitrary
-- ceiling beside `max_slots`, which is the ceiling that means something.
--
-- WHY LOOSENING IS SAFE. 20260908 states the invariant this rests on: the view
-- is an upper bound rather than a count of claimable Tasks, and "`claimable_for`
-- asks `identity_held` before it asks `lane_full`, so the coarser number can
-- never refuse a Task the finer one would have allowed". A Task naming a named
-- Identity that something holds is still refused `identity_held` by the finer
-- gate, whatever this view says. The direction that breaks that invariant is
-- the tight one, and the tight one is what is here now.
--
-- A Program with no anonymous Identity is unaffected. `rk2_anonymous_identity`
-- mints one lazily, so a Program that has never opened a clamped Task has none
-- and this reads exactly as it read before.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW scheduler_lane_state AS
    SELECT c.program_id, c.kind, c.role, c.min_slots, c.max_slots, c.overridden,
           coalesce(live.n, 0)                             AS live_slots,
           CASE WHEN c.clamp_to_identity_leases AND NOT coalesce(free.nobody, false)
                THEN least(greatest(c.max_slots - coalesce(live.n, 0), 0),
                           coalesce(free.n, 0))
                ELSE greatest(c.max_slots - coalesce(live.n, 0), 0)
           END                                             AS headroom,
           greatest(c.min_slots - coalesce(live.n, 0), 0)  AS deficit
      FROM effective_lane_capacity c
      LEFT JOIN LATERAL (
          SELECT count(*) AS n FROM tasks t
           WHERE t.program_id = c.program_id AND t.kind = c.kind
             AND t.status IN ('claimed','running')
      ) live ON true
      LEFT JOIN LATERAL (
          -- `n` is the named supply the clamp is a bound on. `nobody` says
          -- whether the Program can act as the absence of a credential, which
          -- is not a supply and cannot be exhausted.
          SELECT count(*) FILTER (WHERE i.class <> 'anonymous') AS n,
                 bool_or(i.class = 'anonymous')                 AS nobody
            FROM identities i
           WHERE i.program_id = c.program_id
             AND i.invalidated_at IS NULL
             AND NOT EXISTS (SELECT 1 FROM identity_leases l
                              WHERE l.identity_entity_id = i.entity_id
                                AND l.released_at IS NULL)
      ) free ON true;

COMMENT ON VIEW scheduler_lane_state IS
  'Live occupancy against capacity, per lane, per program. A lane whose role is clamped to Identity Leases has its headroom bounded by the Program''s unheld named Identities as well as by its free slots -- unless the Program has an anonymous Identity available, in which case there is no credential to run out of and only the slots bind. An upper bound and not a count of claimable Tasks: claimable_for asks identity_held before lane_full, so this number may never be the tighter of the two.';


DO $$
DECLARE n integer;
BEGIN
    -- The anonymous exemption is in the installed view.
    SELECT count(*) INTO n FROM pg_views
     WHERE schemaname = 'public' AND viewname = 'scheduler_lane_state'
       AND definition ~ 'nobody';
    IF n <> 1 THEN
        RAISE EXCEPTION 'ticket 201: scheduler_lane_state still counts nobody as a credential';
    END IF;
END $$;
