-- ---------------------------------------------------------------------------
-- 20261121T000000Z__a_root_mapped_as_nobody_is_not_mapped.sql
--                                                                  (ticket 193)
--
-- What a recon Task has left to learn is a question about a subject AND a
-- state, and `novelty_for` only ever asked about the subject.
--
-- What was measured. Database `rk2here`, 2026-08-26, eleven laps after ticket
-- 191 gave every root a Task in each provisioned state. The Tasks were derived,
-- were ready, and were never once offered:
--
--     slot_name      | kind  | status  | count
--     here-primary   | recon | pending | 108
--     here-secondary | recon | pending | 108
--     here-primary   | hunt  | pending | 20
--     here-secondary | hunt  | pending | 19
--
--     -- receipts by identity
--     (anonymous) | 453
--
-- `ready_for` refuses none of them. Every slate offered five anonymous recon
-- Tasks and the same low labels came back pass after pass. The ranking is
-- where they died, and one component accounts for all of it:
--
--     slot_name      | count | nov_min | nov_max
--     _anonymous     |    83 | 1.000   | 1.000
--     here-primary   |   108 | 0.625   | 1.000
--     here-secondary |   108 | 0.625   | 1.000
--
-- Every other component -- cost, time, safety, confidence -- was byte-identical
-- across the three states. Only novelty differed, and it differed the wrong
-- way: the state that had never sent a request scored LOWER than the state that
-- had sent 453.
--
-- THE CAUSE. Ticket 27's recon arm counts the property-class families already
-- claimed about the subject and returns what is left of the eight:
--
--     SELECT count(DISTINCT pc.family_id) INTO covered
--       FROM hypotheses h JOIN property_classes pc ON pc.id = h.property_class
--      WHERE h.subject_entity_id = t.subject_entity_id
--        AND h.superseded_by IS NULL;
--     RETURN greatest(1.0 - covered::numeric / total, 0);
--
-- `subject_entity_id` and nothing else. When every Task against a subject acted
-- as the same caller that was a complete question. Ticket 191 made it an
-- incomplete one: a host walked while signed out has had nothing at all learned
-- about it while signed in, and this function reads the signed-out claims and
-- discounts the signed-in Task for them. A root mapped as nobody is not mapped.
--
-- THE FIX, and why it is one EXISTS clause. The claims are still counted the
-- same way over the same vocabulary; what is added is which state each was
-- reached in. That is not stored on the claim -- `hypotheses.identity_a` is
-- filled by nothing, which is ticket 190 -- but it is recoverable exactly:
-- `hypothesis_provenance` names the run that reached the claim, the run names
-- its Task, and ticket 131 put the Identity on the Task. So the chain
-- `hypothesis_provenance.agent_run_id -> agent_runs.task_id ->
-- tasks.selected_identity_entity_id` answers it without a new column and
-- without a guess.
--
-- WHAT IT CHANGES IN PRACTICE. On a subject nothing has claimed anything about,
-- both states still score 1.0 and are genuinely tied -- neither has been
-- looked at, and the older Task winning the tie is the deterministic order the
-- ceiling needs. On a subject the anonymous walk has already covered, the
-- anonymous Task drops as it always did and the signed-in Task now stays at
-- 1.0, which is true: nothing has been learned there. So the signed-in state
-- stops being starved by the very evidence that proves it is unexplored, and it
-- is reached first exactly where the anonymous walk already succeeded, which is
-- also where a credential is most likely to show something new.
--
-- A claim with no provenance row counts for no state rather than for all of
-- them. That is the conservative direction and it is the direction 27 would
-- have chosen: the failure it produces is a Task that looks more novel than it
-- is and gets walked once too often, against a failure that hides a state
-- forever. Nothing in the corpus writes a claim without provenance --
-- `rk2_promote_hypotheses` writes the row in the same statement -- so the arm
-- is defensive rather than load-bearing.
--
-- Only the `recon` arm moves. `hunt` counts evidence on a claim, and a claim is
-- already per-Identity where anything names one; `analyze`, `validate`,
-- `perform`, `conclude` and `report` are lookups against a Test, a Finding or
-- an edge, and none of them is a scan of a subject that could read the wrong
-- state's history. The rest of the function is 20261016T000000Z's, restated
-- verbatim because `CREATE OR REPLACE` restates a whole body.
--
-- Depends on 20261016T000000Z (this function), 20261101T000000Z (the Task's
-- Identity) and 0003. A new file rather than an edit to any of them: a recorded
-- migration whose file has changed is schema drift and `rk db migrate` refuses
-- the whole corpus for it.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION novelty_for(t tasks) RETURNS numeric
LANGUAGE plpgsql STABLE AS $fn$
DECLARE
    covered   integer;
    total     integer;
    n_ev      integer;
    st        text;
    fired     boolean;
BEGIN
    IF t.kind = 'recon' THEN
        -- Ticket 27, measured: the denominator is the 8 FAMILIES, not the 33
        -- leaves. Family coverage ranged 0.625 across the corpus against 0.24
        -- for leaf coverage, so the leaf denominator makes every recon task
        -- look equally novel forever.
        --
        -- And the numerator routes through `hypotheses`, not `observations`:
        -- 27 executed the schema and found `observations` has no
        -- `property_class` at all, and said explicitly not to add one. A
        -- property class is a claim about what a test IS; an observation is a
        -- fact. What "has this property been looked at on this subject" means
        -- is therefore "has a hypothesis about it been written down".
        --
        -- Ticket 193: "on this subject" is half the question. Since ticket 191
        -- a subject is walked once per state, and a claim reached while signed
        -- out says nothing about what is visible while signed in. The state a
        -- claim was reached in is not on the claim -- ticket 190 -- but the run
        -- that reached it is, and ticket 131 put the Identity on that run's
        -- Task. A claim with no provenance counts for no state rather than for
        -- every one: the failure that direction produces is one walk too many,
        -- and the other direction hides a whole state for the life of a hunt.
        SELECT count(DISTINCT pc.family_id) INTO covered
          FROM hypotheses h
          JOIN property_classes pc ON pc.id = h.property_class
         WHERE h.subject_entity_id = t.subject_entity_id
           AND h.superseded_by IS NULL
           AND EXISTS (SELECT 1
                         FROM hypothesis_provenance hp
                         JOIN agent_runs ar ON ar.id = hp.agent_run_id
                         JOIN tasks k ON k.id = ar.task_id
                        WHERE hp.hypothesis_id = h.id
                          AND k.selected_identity_entity_id
                              = t.selected_identity_entity_id);
        SELECT count(*) INTO total FROM property_class_families;
        RETURN greatest(1.0 - covered::numeric / total, 0);

    ELSIF t.kind = 'analyze' THEN
        -- Same shape over the other vocabulary 27 built. "analysis-kind" is
        -- decidable now: it is a kind a tool run may back, which is exactly
        -- what offline analysis over a content-addressed artifact produces.
        SELECT count(DISTINCT o.kind) INTO covered
          FROM observations o
          JOIN observation_kinds k ON k.id = o.kind
         WHERE o.subject_entity_id = t.subject_entity_id
           AND o.provenance_kind = 'tool_run'
           AND 'tool_run' = ANY (k.allowed_provenance);
        SELECT count(*) INTO total
          FROM observation_kinds WHERE 'tool_run' = ANY (allowed_provenance);
        RETURN greatest(1.0 - covered::numeric / total, 0);

    ELSIF t.kind = 'hunt' THEN
        SELECT h.status INTO st FROM hypotheses h WHERE h.id = t.hypothesis_id;
        SELECT EXISTS (SELECT 1 FROM hypothesis_retest_triggers x
                        WHERE x.hypothesis_id = t.hypothesis_id
                          AND x.fired_at IS NOT NULL) INTO fired;
        IF st IN ('supported','refuted') AND NOT fired THEN
            RETURN 0;
        END IF;
        SELECT count(*) INTO n_ev
          FROM hypothesis_evidence WHERE hypothesis_id = t.hypothesis_id;
        -- Ticket 127: the `penalised` discount that used to multiply this is
        -- gone with the action it belonged to. There is no similarity in this
        -- schema to discount by.
        RETURN 1.0 / (1 + n_ev);

    ELSIF t.kind = 'validate' THEN
        -- 32/D13 was closed by migration 015: a validate task names its
        -- finding, so this is a lookup rather than a scan of the subject.
        RETURN CASE WHEN EXISTS (
                 SELECT 1 FROM findings f
                  WHERE f.id = t.finding_id
                    AND f.status IN ('validated','reported','rejected'))
               THEN 0 ELSE 1 END;

    ELSIF t.kind = 'perform' THEN
        -- Ticket 152, found in the first live run that had a `perform` Task in
        -- it. Without this arm the function fell through to the closing
        -- `RETURN 0`, `cancel_reason_for`'s general rule read that as nothing
        -- left to learn, and every `perform` Task the pass derived was
        -- abandoned as `answered` before it could be offered once. `rk2hunt13`
        -- measured it exactly: T5 abandoned with 0 attempts, T6 pending and
        -- ready with `claimable_for = 'answered'`, and the lap that should
        -- have claimed T6 reported `nothing_to_execute`.
        --
        -- Shaped like `validate`'s and for the same reason: the Task names the
        -- Test it performs, so this is a lookup and not a scan of the subject.
        -- A specification nobody has walked is the whole of what is not yet
        -- known about it; once a replay is on file there is nothing further a
        -- second walk of the same actions could learn, which is also what
        -- `ready_for` says when it refuses `perform.already_performed`.
        RETURN CASE WHEN EXISTS (
                 SELECT 1 FROM test_replays tp WHERE tp.test_id = t.test_id)
               THEN 0 ELSE 1 END;

    ELSIF t.kind = 'conclude' THEN
        -- Ticket 156. A settled claim that no Finding rests on has one thing
        -- left to learn about it, and it is the thing this kind exists to
        -- write down: what the claim is a Finding OF. Once an edge in
        -- `finding_hypotheses` names it there is nothing further, and the
        -- second conclusion of one claim would be a merge into a row that is
        -- already open.
        RETURN CASE WHEN EXISTS (
                 SELECT 1 FROM finding_hypotheses fh
                  WHERE fh.hypothesis_id = t.hypothesis_id)
               THEN 0 ELSE 1 END;

    ELSIF t.kind = 'report' THEN
        RETURN CASE WHEN EXISTS (
                 SELECT 1 FROM findings f
                  WHERE f.program_id = t.program_id AND f.status = 'validated'
                    AND f.reported_at IS NULL) THEN 1 ELSE 0 END;
    END IF;
    RETURN 0;
END $fn$;

COMMENT ON FUNCTION novelty_for(tasks) IS
    'What one Task has left to learn, in 0..1. Ticket 27 for the shape; ticket '
    '193 for the recon arm, which since ticket 191 must answer about a subject '
    'AND a state: a root walked while signed out has had nothing learned about '
    'it while signed in, and counting the signed-out claims against the '
    'signed-in Task is what kept every provisioned account out of every slate.';


-- The guard. Two statements, and each is a way this file could be wrong rather
-- than a restatement of what it just wrote.
DO $$
DECLARE n integer;
BEGIN
    -- (i) A subject nothing has claimed anything about is still wholly novel in
    --     every state. If this moved, the arm is counting rows it should not
    --     see at all.
    SELECT count(*) INTO n
      FROM tasks t
     WHERE t.kind = 'recon'
       AND NOT EXISTS (SELECT 1 FROM hypotheses h
                        WHERE h.subject_entity_id = t.subject_entity_id
                          AND h.superseded_by IS NULL)
       AND novelty_for(t) <> 1.0;
    IF n > 0 THEN
        RAISE EXCEPTION 'an unclaimed subject is no longer wholly novel (% Task(s))', n;
    END IF;

    -- (ii) And the defect itself, as a predicate: no recon Task may be
    --      discounted for claims reached in a state it does not act in. Asked
    --      as "the score is at least what the same subject scores counting only
    --      this state's claims", which is what the arm now computes -- so a
    --      future edit that reintroduced the subject-wide count would fail here
    --      on any database where two states have walked one subject.
    SELECT count(*) INTO n
      FROM tasks t
     WHERE t.kind = 'recon'
       AND novelty_for(t) < greatest(
             1.0 - (SELECT count(DISTINCT pc.family_id)
                      FROM hypotheses h
                      JOIN property_classes pc ON pc.id = h.property_class
                     WHERE h.subject_entity_id = t.subject_entity_id
                       AND h.superseded_by IS NULL
                       AND EXISTS (SELECT 1 FROM hypothesis_provenance hp
                                     JOIN agent_runs ar ON ar.id = hp.agent_run_id
                                     JOIN tasks k ON k.id = ar.task_id
                                    WHERE hp.hypothesis_id = h.id
                                      AND k.selected_identity_entity_id
                                          = t.selected_identity_entity_id))::numeric
                 / (SELECT count(*) FROM property_class_families), 0);
    IF n > 0 THEN
        RAISE EXCEPTION
            '% recon Task(s) are discounted for another state''s claims', n;
    END IF;
END $$;
