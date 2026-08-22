-- ---------------------------------------------------------------------------
-- a_performance_is_novel_until_it_is_performed.sql   (ticket 152)
--
-- 152 gave the scheduler a sixth kind and left the ranking pass unable to keep
-- one alive. `novelty_for` answers per kind and had five arms; a `perform`
-- Task fell past all of them to the closing `RETURN 0`. `cancel_reason_for`
-- ends with the general rule -- nothing left to learn is nothing worth running
-- -- so every derived `perform` Task came back `answered`, and `claimable_for`
-- refused it with the same word before the slate was ever built.
--
-- The live measurement, on `rk2hunt13`:
--
--     label | status    | novelty | cancel   | ready | claimable
--     T5    | abandoned | 0       | answered |       | not_pending
--     T6    | pending   | 0       | answered |       | answered
--
-- T5 was cancelled in step (2) of the pass that followed the one that derived
-- it, with `attempts = 0`. T6 was derived in step (3d) of the last pass, after
-- step (2) had already run, and survived only until the lap ended --  which it
-- did with `nothing_to_execute`, because `rank_candidates` filters on exactly
-- the `claimable_for` above.
--
-- One arm, stated the way `validate`'s is.
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
        SELECT count(DISTINCT pc.family_id) INTO covered
          FROM hypotheses h
          JOIN property_classes pc ON pc.id = h.property_class
         WHERE h.subject_entity_id = t.subject_entity_id
           AND h.superseded_by IS NULL;
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

    ELSIF t.kind = 'report' THEN
        RETURN CASE WHEN EXISTS (
                 SELECT 1 FROM findings f
                  WHERE f.program_id = t.program_id AND f.status = 'validated'
                    AND f.reported_at IS NULL) THEN 1 ELSE 0 END;
    END IF;
    RETURN 0;
END $fn$;
