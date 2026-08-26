-- ---------------------------------------------------------------------------
-- Two states of one claim are one way to supply a requirement
--
-- WHAT WAS MEASURED. `ChainUnlockTest` seeds two candidate claims that a sound
-- chain is one requirement short of, and asserts that a useful low-cost pivot
-- outranks a Task no chain is waiting on. It does not:
--
--     pivot    priority 0.09840642827103532
--     isolated priority 0.10050018206403608
--
-- `chain_unlock_for` divides a member's severity weight by
--
--     count(DISTINCT u2.task_id) ... WHERE k2.status = 'pending'
--
-- and `20261120T000000Z` doubled that count. Ticket 191 made the hunt frontier
-- a (claim, Identity) pair rather than a claim, so a claim that names nobody
-- owes one hunt Task per state the Program can work -- anonymous and each
-- provisioned account. Two Tasks, one claim. The divisor went from 2 to 4 and
-- every share halved.
--
-- WHY THAT IS THE WRONG DIVISOR. The comment on the function says the weight is
-- "shared between the pending Tasks that could supply that requirement". What
-- supplies the requirement is the claim being settled, and the two state Tasks
-- are two ways of settling ONE claim rather than two ways of supplying the
-- requirement. Either one answers it; they are alternatives and not additions.
-- Counting them separately says a Program that can work two states has half the
-- reason to pivot, which is the opposite of what having two states is for.
--
-- THE RULE. Divide by the distinct claims those Tasks are about, falling back
-- to the Task itself where there is no claim. A Task with a Hypothesis is
-- counted once per Hypothesis however many states it is worked in; a Task
-- without one -- a recon, a perform, a hunt nothing was derived for -- is
-- counted as itself, which is what it was counted as before. A Program with one
-- state therefore computes exactly the number it computed before this file,
-- because one state is one Task per claim and the two counts coincide.
--
-- The cap at one is unchanged, and so is everything else in the expression:
-- what moves is the denominator, and only where 191 put more than one Task
-- behind one claim.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION chain_unlock_for(t tasks) RETURNS numeric
LANGUAGE sql STABLE AS $fn$
    SELECT least(coalesce(sum(s.share), 0), 1.0)
      FROM (SELECT DISTINCT u.finding_id,
                   sw.weight
                     / greatest((SELECT count(DISTINCT
                                              coalesce(k2.hypothesis_id, u2.task_id))
                                   FROM task_chain_unlocks u2
                                   JOIN tasks k2
                                     ON k2.id = u2.task_id
                                    AND k2.program_id = u2.program_id
                                  WHERE u2.finding_id = u.finding_id
                                    AND u2.program_id = u.program_id
                                    AND k2.status = 'pending'), 1) AS share
              FROM task_chain_unlocks u
              JOIN findings f ON f.id = u.finding_id AND f.program_id = u.program_id
              -- Inner, so an unweighted band and an undetermined basis leave the
              -- member out of the sum by the same mechanism: no row, no share.
              JOIN severity_unlock_weights sw ON sw.severity = f.severity
             WHERE u.task_id = t.id
               AND u.program_id = t.program_id
               AND f.severity_basis <> 'undetermined') s;
$fn$;

COMMENT ON FUNCTION chain_unlock_for(tasks) IS
  'What this Task would add to what is already reachable: the severity weight of each DISTINCT Finding a sound chain is one requirement short of, shared between the pending CLAIMS that could supply that requirement -- a Task with no claim counting as itself -- capped at one. Claims and not Tasks because ticket 191 works one claim in every state the Program has, and two states of one claim are two ways of settling it rather than two ways of supplying the requirement. A member whose severity nobody has stated contributes nothing rather than a guess.';


DO $$
DECLARE n integer;
BEGIN
    SELECT count(*) INTO n FROM pg_proc
     WHERE pronamespace = 'public'::regnamespace
       AND proname = 'chain_unlock_for'
       AND prosrc ~ 'coalesce\(k2\.hypothesis_id, u2\.task_id\)';
    IF n <> 1 THEN
        RAISE EXCEPTION 'the chain unlock share still divides by Tasks rather than claims';
    END IF;
END $$;
