-- Group C: ticket 08's ranking pass and claim protocol, made executable.
--
-- Ticket 08 states the pass as one SQL statement over three helper functions it
-- never defines. This file defines them as closely to the ticket's prose as the
-- schema allows, and marks in comments every place the prose could not be
-- turned into SQL.

SET client_min_messages = warning;
SELECT set_config('app.actor_kind', 'runtime', false);

-- ---------------------------------------------------------------------------
-- Fixture: a queue big enough for order to mean something.
-- ---------------------------------------------------------------------------

DO $fix$
DECLARE
    p    uuid := '11111111-1111-7111-8111-111111111111';
    app  uuid := 'aaaaaaaa-0000-7000-8000-000000000001';
    ent  uuid;
    hyp  uuid;
    fnd  uuid;
    i    integer;
    g    numeric;
BEGIN
    FOR i IN 10..21 LOOP
        ent := ('aaaaaaaa-0000-7000-8000-0000000001' || lpad(i::text, 2, '0'))::uuid;
        INSERT INTO entities (id, program_id, type, label, dedup_key)
        VALUES (ent, p, 'endpoint', 'EP' || i, 'GET /api/r' || i);
        INSERT INTO endpoints (entity_id, application_id, method, path_template)
        VALUES (ent, app, 'GET', '/api/r' || i);

        -- gain and impact are stable functions of i, never random
        g := (i % 7 + 1) / 8.0;
        INSERT INTO tasks (program_id, label, kind, subject_entity_id,
                           expected_information_gain, potential_impact)
        VALUES (p, 'TR' || i, 'recon', ent, g, ((i % 5) + 1) / 6.0);

        IF i <= 15 THEN
            hyp := ('bbbbbbbb-0000-7000-8000-0000000001' || lpad(i::text, 2, '0'))::uuid;
            INSERT INTO hypotheses (id, program_id, label, subject_entity_id,
                                    property_class, statement)
            VALUES (hyp, p, 'HG' || i, ent, 'authz.horizontal', 'generated ' || i);
            INSERT INTO hypothesis_transitions
                (program_id, hypothesis_id, from_status, to_status, actor_kind)
            VALUES (p, hyp, 'proposed', 'testable', 'llm');
            INSERT INTO tasks (program_id, label, kind, subject_entity_id,
                               hypothesis_id, expected_information_gain,
                               potential_impact)
            VALUES (p, 'TH' || i, 'hunt', ent, hyp, g, ((i % 3) + 1) / 4.0);
        END IF;

        IF i BETWEEN 18 AND 20 THEN
            fnd := ('55555555-0000-7000-8000-0000000001' || lpad(i::text, 2, '0'))::uuid;
            INSERT INTO findings (id, program_id, label, subject_entity_id,
                                  class_id, title, severity)
            VALUES (fnd, p, 'FG' || i, ent, 'idor', 'generated finding ' || i, 'medium');
            -- NOTE: a validate task cannot name the finding. `tasks` has
            -- subject_entity_id and hypothesis_id and nothing else, so the link
            -- is by subject entity only.
            INSERT INTO tasks (program_id, label, kind, subject_entity_id,
                               expected_information_gain, potential_impact)
            VALUES (p, 'TV' || i, 'validate', ent, 0.2, 0.9);
        END IF;
    END LOOP;

    -- one report task, subject NULL, which the dedup index allows exactly once
    INSERT INTO tasks (program_id, label, kind, expected_information_gain,
                       potential_impact)
    VALUES (p, 'TP', 'report', 0.1, 0.5);

    -- a task with no model estimate at all, which must sink to NULL priority
    INSERT INTO tasks (program_id, label, kind, subject_entity_id)
    VALUES (p, 'TN', 'recon', 'aaaaaaaa-0000-7000-8000-000000000005');

    -- history for the cost estimator: completed runs with known token totals
    FOR i IN 1..8 LOOP
        INSERT INTO agent_runs (program_id, label, role, model, effort,
                                mission_packet, input_tokens, output_tokens,
                                stop_reason, finished_at)
        VALUES (p, 'AH' || i, 'hunter', 'claude-opus-5', 'high', '{}',
                10000 * i, 5000 * i, 'completed', now());
    END LOOP;
END $fix$;

-- ---------------------------------------------------------------------------
-- The helper functions ticket 08 names but never writes.
-- ---------------------------------------------------------------------------

-- The ticket's recon novelty divides by |vocabulary|, which it defers to ticket
-- 27. There is no vocabulary table, so the denominator is a literal here.
CREATE OR REPLACE FUNCTION novelty_for(t tasks) RETURNS numeric
LANGUAGE plpgsql STABLE AS $$
DECLARE
    n_classes integer;
    n_ev      integer;
    st        text;
    sim       numeric;
BEGIN
    IF t.kind = 'recon' THEN
        SELECT count(DISTINCT h.property_class) INTO n_classes
          FROM observations o
          LEFT JOIN hypotheses h ON h.subject_entity_id = o.subject_entity_id
         WHERE o.subject_entity_id = t.subject_entity_id;
        RETURN 1 - n_classes / 8.0;          -- 8 = stand-in for |vocabulary|
    ELSIF t.kind = 'analyze' THEN
        -- "same shape, over analysis-kind observations": observations.kind has
        -- no vocabulary either, so there is no predicate to write.
        RETURN 1;
    ELSIF t.kind = 'hunt' THEN
        SELECT status INTO st FROM hypotheses WHERE id = t.hypothesis_id;
        IF st IN ('supported','refuted') AND NOT EXISTS (
             SELECT 1 FROM hypothesis_retest_triggers
              WHERE hypothesis_id = t.hypothesis_id AND fired_at IS NOT NULL) THEN
            RETURN 0;
        END IF;
        SELECT count(*) INTO n_ev FROM hypothesis_evidence
         WHERE hypothesis_id = t.hypothesis_id;
        -- The penalty cannot be applied: hypothesis_near_matches records the
        -- MATCHED hypothesis and the candidate as free text, so the row cannot
        -- be found from the hypothesis the candidate became.
        SELECT max(similarity) INTO sim FROM hypothesis_near_matches
         WHERE matched_hypothesis_id = t.hypothesis_id AND action = 'penalised';
        RETURN (1.0 / (1 + n_ev)) * coalesce(1 - sim, 1);
    ELSIF t.kind = 'validate' THEN
        -- "1 unless the finding is already validated or reported" — the task
        -- cannot name a finding, so this reads every finding on the subject.
        RETURN CASE WHEN EXISTS (
                 SELECT 1 FROM findings
                  WHERE subject_entity_id = t.subject_entity_id
                    AND status IN ('validated','reported')) THEN 0 ELSE 1 END;
    ELSIF t.kind = 'report' THEN
        RETURN CASE WHEN EXISTS (
                 SELECT 1 FROM findings
                  WHERE program_id = t.program_id AND status = 'validated'
                    AND reported_at IS NULL) THEN 1 ELSE 0 END;
    END IF;
    RETURN 0;
END $$;

-- N in "the last N completed agent_runs" is never fixed by the ticket; 20 here.
-- The grouping is "(role, kind)", but nothing maps a task kind to an agent role,
-- so this groups by kind alone, via the task each run served.
CREATE OR REPLACE FUNCTION cost_for(t tasks, w scheduler_weights) RETURNS numeric
LANGUAGE plpgsql STABLE AS $$
DECLARE
    med   numeric;
    n     integer;
    prior numeric;
    est   numeric;
BEGIN
    SELECT count(*), percentile_cont(0.5) WITHIN GROUP (
               ORDER BY (r.input_tokens + r.output_tokens))
      INTO n, med
      FROM (SELECT ar.input_tokens, ar.output_tokens
              FROM agent_runs ar
              LEFT JOIN tasks tk ON tk.id = ar.task_id
             WHERE ar.program_id = t.program_id
               AND ar.stop_reason = 'completed'
               AND coalesce(tk.kind, t.kind) = t.kind
             ORDER BY ar.started_at DESC
             LIMIT 20) r;

    prior := coalesce((w.cost_prior ->> t.kind)::numeric, 0.5);
    est := (coalesce(n, 0) * coalesce(med, 0) + w.shrinkage_n0 * prior * w.cost_reference_tokens)
           / (coalesce(n, 0) + w.shrinkage_n0);
    RETURN least(greatest(est / w.cost_reference_tokens, w.cost_floor), 1.0);
END $$;

CREATE OR REPLACE FUNCTION confidence_for(t tasks, w scheduler_weights)
RETURNS numeric LANGUAGE plpgsql STABLE AS $$
DECLARE
    n         integer;
    successes integer;
    ok        boolean;
BEGIN
    -- gate: the subject is in scope
    IF t.subject_entity_id IS NOT NULL THEN
        SELECT in_scope INTO ok FROM entities WHERE id = t.subject_entity_id;
        IF NOT coalesce(ok, false) THEN RETURN 0; END IF;
    END IF;

    -- gate: the identities the hypothesis names are not leased out
    IF t.hypothesis_id IS NOT NULL AND EXISTS (
         SELECT 1 FROM hypotheses h
           JOIN identity_leases l
             ON l.identity_entity_id IN (h.identity_a_entity_id, h.identity_b_entity_id)
          WHERE h.id = t.hypothesis_id
            AND l.released_at IS NULL AND l.expires_at > now()) THEN
        RETURN 0;
    END IF;

    -- gate: "every required_skills entry exists and is enabled". There is no
    -- skills table, so this gate cannot be evaluated and is skipped.

    SELECT count(*),
           count(*) FILTER (WHERE ar.stop_reason = 'completed' AND EXISTS (
               SELECT 1 FROM observations o
                WHERE o.agent_run_id = ar.id AND o.provenance_kind = 'receipt'))
      INTO n, successes
      FROM agent_runs ar
      LEFT JOIN tasks tk ON tk.id = ar.task_id
     WHERE ar.program_id = t.program_id
       AND coalesce(tk.kind, t.kind) = t.kind;

    RETURN (successes + w.shrinkage_n0 * w.confidence_prior) / (n + w.shrinkage_n0);
END $$;

-- ---------------------------------------------------------------------------
-- The pass, in the ticket's own shape.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION rank_pass(p_program uuid) RETURNS void
LANGUAGE sql AS $$
WITH w AS (SELECT * FROM scheduler_weights WHERE active),
     r AS (
       SELECT t.id,
              novelty_for(t)          AS novelty,
              cost_for(t, w)          AS estimated_cost,
              confidence_for(t, w)    AS confidence
         FROM tasks t, w
        WHERE t.program_id = p_program AND t.status = 'pending'
     )
UPDATE tasks t
   SET novelty = r.novelty,
       estimated_cost = r.estimated_cost,
       confidence_of_execution = r.confidence,
       priority = CASE
           WHEN t.expected_information_gain IS NULL
             OR t.potential_impact IS NULL THEN NULL
           ELSE r.novelty * r.confidence
                * (w.w_gain * t.expected_information_gain
                 + w.w_impact * t.potential_impact)
                / greatest(r.estimated_cost, w.cost_floor)
       END
  FROM r, w
 WHERE t.id = r.id;
$$;

-- ---------------------------------------------------------------------------
-- The claim, step 3 of the protocol.
-- ---------------------------------------------------------------------------

-- Returns the claimed label, or NULL when nothing is claimable. Lane headroom
-- is max_slots per kind counted over live runs, per decision 8.
CREATE OR REPLACE FUNCTION claim_one(p_program uuid, p_run_label text)
RETURNS text LANGUAGE plpgsql AS $$
DECLARE
    v_task tasks%ROWTYPE;
    v_ttl  interval;
BEGIN
    SELECT lease_ttl INTO v_ttl FROM scheduler_weights WHERE active;

    SELECT t.* INTO v_task
      FROM tasks t
      JOIN scheduler_lanes l
        ON l.kind = t.kind AND l.program_id IS NOT DISTINCT FROM NULL
     WHERE t.program_id = p_program
       AND t.status = 'pending'
       AND (SELECT count(*) FROM tasks c
             WHERE c.program_id = p_program AND c.kind = t.kind
               AND c.status IN ('claimed','running')) < l.max_slots
     ORDER BY t.priority DESC NULLS LAST, t.created_at, t.id
       FOR UPDATE OF t SKIP LOCKED
     LIMIT 1;

    IF NOT FOUND THEN RETURN NULL; END IF;

    UPDATE tasks
       SET status = 'claimed', attempts = attempts + 1, claimed_at = now(),
           lease_expires_at = now() + v_ttl
     WHERE id = v_task.id;

    INSERT INTO agent_runs (program_id, label, task_id, role, model, effort,
                            mission_packet)
    VALUES (p_program, p_run_label, v_task.id, 'hunter', 'claude-opus-5', 'high', '{}');

    RETURN v_task.label;
END $$;
