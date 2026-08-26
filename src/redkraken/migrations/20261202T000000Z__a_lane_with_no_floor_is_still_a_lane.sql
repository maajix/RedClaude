-- ---------------------------------------------------------------------------
-- Ticket 203: a lane with no floor is still a lane
--
-- WHAT WAS MEASURED. `SlateClaimTest` seeds one Task of each of five kinds and
-- claims each in turn. Under ticket 199's `chain` profile the first claim is
-- refused:
--
--     23514: task T1 is not on the current slate
--
-- with seven Tasks pending and a slate of five:
--
--     slate   validate, report, hunt, analyze, hunt
--     pending T1 recon 0.152, T2 hunt 0.171, T3 analyze 0.361, T4 validate
--             0.696, T5 report 0.602, T6 hunt 0.598, T7 hunt 0.199
--
-- Six of the seven are of kinds `chain` floors. `recon` is floored at 0, so it
-- is unentitled, and `offer_slate` orders `entitled DESC, rnk` and then takes
-- `slate_size`. Six entitled candidates against five seats: the whole slate is
-- entitled and recon is not merely last, it is absent.
--
-- WHAT IT COSTS ON A LIVE CAMPAIGN. `rk2here`, the same hour:
--
--     hunt    pending 342     recon pending 220     perform pending 5
--
-- Three hundred and forty-seven entitled Tasks against five seats. The two
-- hundred and twenty recon Tasks are not competing on priority and losing --
-- they cannot be offered at all, and a hunt that finds a new host writes
-- another recon Task that also cannot be offered. Recon is off, permanently,
-- and nothing says so.
--
-- WHAT 199 GOT WRONG. `20261130T000000Z` set recon to 0 so that it would
-- "compete on priority" and wrote down why min_slots is a priority class rather
-- than a concurrency floor. Both halves are right. What neither says is what
-- happens at the truncation: entitlement decides the ORDER, and `slate_size`
-- then decides how much of that order anybody sees. A kind at the back of an
-- order longer than the slate is a kind that does not exist.
--
-- THE FIX, AND WHY IT IS THIS ONE. One seat of the slate is held for the best
-- unentitled candidate whenever there is one. Not a floor for recon -- that is
-- exactly the starvation 199 measured, running the other way. Not a change to
-- the sort either: entitlement first is what makes a floor mean anything, and
-- ticket 199 rests on it. What was wrong was that the truncation could empty a
-- whole class, so the truncation is what changes.
--
-- The seat is the LAST one, so nothing about which Task the runtime's own
-- argument-free `claim_task()` walks to first moves: it still takes the first
-- claimable entry in ordinal order, which is still the best entitled Task. What
-- the seat restores is the orchestrator's ability to see the alternative and
-- name it with `mcp__rk2__pick_task`, which is the whole reason a slate is a
-- list rather than a single answer.
--
-- `greatest(slate_size - 1, 1)` and not `slate_size - 1`: a slate of one is one
-- answer, and holding its only seat for the unentitled candidate would invert
-- the rule rather than soften it.
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

    -- Ticket 203. `ranked` numbers each entitlement class on its own, `seated`
    -- lets the entitled fill every seat but one when there is an unentitled
    -- candidate to hold it for, and the LIMIT is unchanged -- so a slate with
    -- nothing unentitled in it is exactly the slate this function offered
    -- before, entry for entry.
    INSERT INTO task_slate (slate_id, program_id, task_id, ordinal, entitled)
    SELECT sid, p, s.task_id,
           (row_number() OVER (ORDER BY s.entitled DESC, s.rnk))::integer,
           s.entitled
      FROM (
          WITH ranked AS (
              SELECT c.task_id, c.entitled, c.rnk,
                     row_number() OVER (PARTITION BY c.entitled ORDER BY c.rnk) AS within
                FROM rank_candidates() c
          )
          SELECT r.task_id, r.entitled, r.rnk FROM ranked r
           WHERE r.entitled
             AND r.within <= CASE
                     WHEN EXISTS (SELECT 1 FROM ranked u WHERE NOT u.entitled)
                     THEN greatest(w.slate_size - 1, 1)
                     ELSE w.slate_size END
          UNION ALL
          SELECT r.task_id, r.entitled, r.rnk FROM ranked r
           WHERE NOT r.entitled AND r.within <= w.slate_size
      ) s
     ORDER BY s.entitled DESC, s.rnk
     LIMIT w.slate_size;

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
  'One slate for this Program: the entitled lanes first in ranked order, then the rest, capped at scheduler_weights.slate_size -- with one seat held for the best unentitled candidate whenever there is one, so that a lane floored at zero is a lane that competes rather than a lane that cannot be seen. Supersedes the outstanding slate and any pick made against it.';


DO $$
DECLARE n integer;
BEGIN
    -- The seat is in the installed text. Asked of `prosrc` because the
    -- behaviour needs a Program with more entitled candidates than seats to
    -- show, and a migration has no way to stand one up.
    SELECT count(*) INTO n FROM pg_proc
     WHERE pronamespace = 'public'::regnamespace
       AND proname = 'offer_slate'
       AND prosrc ~ 'greatest\(w\.slate_size - 1, 1\)';
    IF n <> 1 THEN
        RAISE EXCEPTION 'ticket 203: offer_slate does not hold a seat for the unentitled';
    END IF;

    -- Not called here. `offer_slate` supersedes the outstanding slate and the
    -- pick made against it, so a migration that ran it to prove it parses would
    -- take a live campaign's offer away as a side effect of being installed.
    -- What proves it runs is `SlateClaimTest`, on a database built for it.
END $$;
