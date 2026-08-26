-- ---------------------------------------------------------------------------
-- Ticket 203, second cut: one seat for every lane, not one for the leftovers
--
-- WHAT `20261202T000000Z` DID, AND WHY IT WAS NOT ENOUGH. It held the last
-- seat of the slate for the best UNENTITLED candidate. That is one seat for a
-- class, and the class has more than one lane in it. Measured on the database
-- `SlateClaimTest` builds, immediately after that file was applied:
--
--     candidates  T4 validate  e=t r=1     T7 hunt   e=f r=5
--                 T5 report    e=t r=2     T2 hunt   e=f r=6
--                 T6 hunt      e=t r=3     T1 recon  e=f r=7
--                 T3 analyze   e=t r=4
--     slate       T4, T5, T6, T3, T7
--
-- The held seat went to T7 -- an unentitled HUNT, because hunt's deficit is 1
-- and T6 had already taken it. The recon lane was still not on the slate, and
-- the claim was still refused:
--
--     23514: task T1 is not on the current slate
--
-- Reserving a seat for "the unentitled" answers the question that was asked
-- and not the one that matters. What starves is a LANE, and a lane starves the
-- same way whether the Tasks in front of it are entitled or not.
--
-- THE RULE THIS FILE INSTALLS. Every lane's best candidate is seated first, in
-- rank order, and whatever seats are left go to the rest in rank order. A
-- Program with fewer pending kinds than seats therefore offers every kind it
-- has plus the best of the remainder, and a Program with more kinds than seats
-- offers the best-ranked kinds -- never the same kind twice while another kind
-- has nothing.
--
-- On `rk2here` the pending kinds are hunt 342, recon 220 and perform 5: three
-- seats go to the three lanes and two to the best of what is left, where
-- before this the whole slate was hunts.
--
-- WHAT DOES NOT MOVE. The ordinal is still `entitled DESC, rnk`, so the
-- argument-free `claim_task()` -- the runtime's own call -- still walks to the
-- best entitled Task first. `rank_candidates()` is untouched, so an
-- unaffordable Task is still no candidate at all. What changes is only which
-- rows survive the truncation, which is where a lane was disappearing.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION offer_slate()
RETURNS TABLE (ordinal integer, task_label text, kind text, subject_label text,
               priority numeric, factors jsonb, entitled boolean,
               expires_at timestamptz)
LANGUAGE plpgsql AS $fn$
DECLARE
    p   uuid := rk2_program_required();
    w   scheduler_weights%ROWTYPE;
    sid uuid := uuidv7();
BEGIN
    SELECT * INTO w FROM scheduler_weights WHERE active;

    -- A superseded slate must stop being claimable, or the orchestrator can
    -- pick from a stale offer after the world moved. Consumed, not deleted:
    -- ticket 16 has to be able to ask what was offered and never taken.
    --
    -- The choice made against it goes the same way, and for the stronger
    -- version of the same reason: a pick that outlived the list it was made
    -- from is a choice between options the chooser can no longer see.
    UPDATE task_slate s SET consumed = true
     WHERE s.program_id = p AND NOT s.consumed;

    PERFORM supersede_pick(p);

    -- `in_kind` numbers each lane's candidates on their own, so `in_kind = 1`
    -- is that lane's best and there is exactly one of them per lane. Sorting
    -- those to the front before the LIMIT is the whole of the fix: a Program
    -- with no starved lane sorts every row with the same key it had before and
    -- offers exactly the slate it offered before, entry for entry.
    INSERT INTO task_slate (slate_id, program_id, task_id, ordinal, entitled)
    SELECT sid, p, s.task_id,
           (row_number() OVER (ORDER BY s.entitled DESC, s.rnk))::integer,
           s.entitled
      FROM (
          SELECT r.task_id, r.entitled, r.rnk
            FROM (
                SELECT c.task_id, c.entitled, c.rnk,
                       row_number() OVER (PARTITION BY c.kind ORDER BY c.rnk)
                           AS in_kind
                  FROM rank_candidates() c
            ) r
           ORDER BY (r.in_kind = 1) DESC, r.rnk
           LIMIT w.slate_size
      ) s
     ORDER BY s.entitled DESC, s.rnk;

    RETURN QUERY
    SELECT s.ordinal, t.label, t.kind, e.label,
           round(t.priority, 6),
           task_rank_factors(t),
           s.entitled,
           s.offered_at + w.slate_ttl
      FROM task_slate s
      JOIN tasks t ON t.id = s.task_id
      LEFT JOIN entities e ON e.id = t.subject_entity_id
     WHERE s.slate_id = sid
     ORDER BY s.ordinal;
END $fn$;

-- 20260922T020000Z turned the JIT off for this function because the planner
-- spent more compiling the slate than running it. `CREATE OR REPLACE` keeps
-- function-level settings, but the setting is cheap to state and expensive to
-- lose, so it is stated.
ALTER FUNCTION offer_slate() SET jit = off;

COMMENT ON FUNCTION offer_slate() IS
  'One slate for this Program: every pending lane''s best candidate first, then the rest, capped at scheduler_weights.slate_size and ordered entitled-first by rank -- so a lane floored at zero is a lane that competes rather than a lane that cannot be seen. Supersedes the outstanding slate and any pick made against it.';


DO $$
DECLARE n integer;
BEGIN
    -- The lane seat is in the installed text, and the seat `20261202T000000Z`
    -- held for the unentitled class is not. Asked of `prosrc` because the
    -- behaviour needs a Program with more pending Tasks than seats across more
    -- than one lane to show, and a migration has no way to stand one up.
    SELECT count(*) INTO n FROM pg_proc
     WHERE pronamespace = 'public'::regnamespace
       AND proname = 'offer_slate'
       AND prosrc ~ 'ORDER BY \(r\.in_kind = 1\) DESC'
       AND prosrc !~ 'greatest\(w\.slate_size - 1, 1\)';
    IF n <> 1 THEN
        RAISE EXCEPTION 'ticket 203: offer_slate does not seat every lane';
    END IF;

    -- Not called here. `offer_slate` supersedes the outstanding slate and the
    -- pick made against it, so a migration that ran it to prove it parses would
    -- take a live campaign's offer away as a side effect of being installed.
    -- What proves it runs is `SlateClaimTest`, on a database built for it.
END $$;
