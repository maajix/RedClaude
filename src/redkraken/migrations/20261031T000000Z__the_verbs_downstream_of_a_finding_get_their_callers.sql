-- ===========================================================================
-- Production harness 103 -- the callers the downstream verbs never had
-- ===========================================================================
-- Six verbs run from a validated Finding to a sound kill chain and not one of
-- them has ever been called from `src/redkraken/*.py`. Ticket 103 splits them
-- three ways, and the line it draws is whether the verb takes a parameter the
-- runtime could not fill out of a row it wrote itself:
--
--   served to a model   `open_impact_task`, `state_severity`,
--                       `compose_finding_report`
--   runtime steps       `apply_computed_cvss`, `issue_pivot_stamp`,
--                       `build_kill_chain`
--   operator read       `read_kill_chain`
--
-- This file is the first third: the half between a Contract and the verb it
-- reaches, the way `propose_finding` (ticket 102) and `propose_test`
-- (ticket 141) are. A child names a Finding by the label it can read; something
-- has to turn that label into the row, and something has to turn an exception
-- into a sentence the run can correct and re-send inside the same run.
--
-- WHY THE THREE ARE WRAPPERS RATHER THAN DIRECT CALLS.
--
-- All three underlying verbs take a uuid and two of the three raise rather than
-- answer. A `RAISE` aborts the caller's transaction, which is the wrong shape
-- twice over: the child is told "an error occurred" instead of which of its
-- fields was wrong, and anything else the runtime had done in that transaction
-- goes with it. So each wrapper resolves the label, runs the verb inside a
-- block that catches the error classes those verbs actually raise, and answers
-- `{"outcome": "refused", "refusal": "..."}` -- the shape every other served
-- ask on this surface already answers with.
--
-- `WHEN OTHERS` is deliberately not used. The classes below are the ones
-- `open_impact_task` and `state_severity` raise by name -- 23503, 23514, 22023
-- and, through `rk2_refuse_forbidden_impact`, 42501 -- plus the four a
-- malformed specification reaches the table constraints with. A connection
-- that died or a deadlock that was chosen as the victim is not a refusal and is
-- not caught here.
--
-- WHAT IS NOT SERVED, AND WHY IT IS NOT.
--
-- `apply_computed_cvss` is called from section 4 below and from nowhere a model
-- can reach. Its answer is computed by `compute_finding_cvss`, and the live
-- `report_blockers` already emits `cvss_stale` with the computed vector written
-- out in its own detail -- so a model asked to call that verb would be handing
-- the runtime back a sentence the runtime wrote. The step goes where that
-- blocker would otherwise be raised, which is the moment a composition is
-- accepted.
--
-- INVOKER and not SECURITY DEFINER, for `propose_finding`'s reason: the caller
-- is `rk2_runtime`, which already executes all three underlying verbs and
-- already reads every table read here.


-- ===========================================================================
-- 1. The label a child can say, resolved to the Finding
-- ===========================================================================
-- One sentence, written once. All three wrappers refuse an unknown label the
-- same way and for `propose_finding`'s reason: a uuid-taking verb handed NULL
-- answers "<NULL> is not a Finding of this Program", which tells the child
-- nothing about the word it actually said.

CREATE FUNCTION rk2_finding_for_label(p_label text) RETURNS findings
LANGUAGE sql STABLE AS $fn$
    SELECT f.* FROM findings f
     WHERE f.program_id = rk2_program_required()
       AND f.label = btrim(coalesce(p_label, ''));
$fn$;

COMMENT ON FUNCTION rk2_finding_for_label(text) IS
    'Ticket 103: the Finding this Program holds under a label a child can read, '
    'or no row. The one resolution the three served downstream Contracts share.';

CREATE FUNCTION rk2_no_such_finding(p_label text) RETURNS jsonb
LANGUAGE sql IMMUTABLE AS $fn$
    SELECT jsonb_build_object(
        'outcome', 'refused',
        'refusal', format('%s is not a Finding of this Program',
                          coalesce(nullif(btrim(coalesce(p_label, '')), ''), '(none)')));
$fn$;

COMMENT ON FUNCTION rk2_no_such_finding(text) IS
    'Ticket 103: the refusal all three downstream Contracts answer a label this '
    'Program does not hold with, naming the word that was said rather than a '
    'null uuid.';


-- ===========================================================================
-- 2. The impact work a hunter asks for
-- ===========================================================================
-- `open_impact_task` writes `tests` and `tasks`, both of which are in the
-- roster's `CANONICAL`, so `_check_contracts` refuses any Contract naming
-- either in `writes`. What the Contract declares instead is `test_proposals` --
-- ticket 141's audit row beside `tests` -- and this function files it, because
-- the row an impact specification produces is a `tests` row like any other and
-- an operator counting refused specifications should not have to know which
-- verb wrote them.
--
-- `test_proposals.hypothesis_id` is resolved before the call rather than read
-- out of the answer, so a refusal still names the claim the impact Test would
-- have been authored against. It is null when the Finding rests on no claim,
-- which is one of the sentences `open_impact_task` raises.
--
-- Criterion 5 of ticket 38 is not restated here. A forbidden impact class is
-- refused inside `open_impact_task` by `rk2_refuse_forbidden_impact`, before a
-- `tests` row exists and long before a question a human might feel able to
-- answer does; this file catches that refusal and passes the sentence on. The
-- roster's own schema does not offer the three forbidden classes at all, so the
-- refusal is the second door rather than the first.

CREATE FUNCTION propose_impact_task(
        p_label     text,
        p_spec      jsonb,
        p_agent_run uuid DEFAULT NULL)
RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p           uuid := rk2_program_required();
    v_spec      jsonb := coalesce(p_spec, 'null'::jsonb);
    v_find      findings%ROWTYPE;
    v_hypothesis uuid;
    v_agent_run uuid;
    v_refusal   text;
    v_opened    jsonb;
    v_test      uuid;
BEGIN
    -- Provenance, and only this Program's, for `propose_test`'s reason: an
    -- Agent run belonging to somebody else is not provenance for a row here,
    -- and the composite foreign key would raise on it -- taking the record of
    -- the attempt down with the mistake.
    SELECT ar.id INTO v_agent_run
      FROM agent_runs ar WHERE ar.id = p_agent_run AND ar.program_id = p;

    v_find := rk2_finding_for_label(p_label);
    IF v_find.id IS NULL THEN
        RETURN rk2_no_such_finding(p_label);
    END IF;

    SELECT fh.hypothesis_id INTO v_hypothesis FROM finding_hypotheses fh
     WHERE fh.finding_id = v_find.id ORDER BY fh.hypothesis_id LIMIT 1;

    BEGIN
        v_opened := open_impact_task(v_find.id, v_spec, v_agent_run);
    EXCEPTION WHEN raise_exception OR foreign_key_violation OR check_violation
                OR unique_violation OR not_null_violation
                OR invalid_parameter_value OR invalid_text_representation
                OR insufficient_privilege THEN
        v_refusal := SQLERRM;
    END;

    -- `set_actor` writes a transaction-local setting, and the failed block
    -- above was a subtransaction, so a caught error took the declaration with
    -- it. Declared here rather than once at the top for that reason: the row
    -- below is written on both paths and the emitter checks the actor on both.
    PERFORM set_actor('runtime');

    IF v_refusal IS NOT NULL THEN
        INSERT INTO test_proposals
            (program_id, hypothesis_id, agent_run_id, spec, outcome, refusal)
        VALUES (p, v_hypothesis, v_agent_run, v_spec, 'refused', v_refusal);
        RETURN jsonb_build_object('outcome', 'refused', 'refusal', v_refusal);
    END IF;

    SELECT t.id INTO v_test FROM tests t
     WHERE t.program_id = p AND t.label = v_opened ->> 'test';

    INSERT INTO test_proposals
        (program_id, hypothesis_id, agent_run_id, spec, outcome, test_id)
    VALUES (p, v_hypothesis, v_agent_run, v_spec, 'created', v_test);

    RETURN v_opened || jsonb_build_object('outcome', 'created');
END $fn$;

COMMENT ON FUNCTION propose_impact_task(text, jsonb, uuid) IS
    'Ticket 103. The caller''s half of `open_impact_task`: a Finding label a '
    'child can read, resolved to the row, and the exception that verb raises '
    'turned into a sentence the run can correct. Files a `test_proposals` row '
    'on either outcome, so a refused impact specification is counted beside '
    'every other refused specification.';


-- ===========================================================================
-- 3. The band a hunter states
-- ===========================================================================
-- `state_severity` is the only writer of `findings.severity` and it refuses
-- three ways: a severity claimed as demonstrated with no demonstration, an
-- inference about a Finding that has one, and a high or critical band read out
-- of nothing but the Program document. Each of those is a sentence a run can
-- act on, and each of them arrives as a `RAISE`, so this wrapper exists to
-- carry them back rather than abort with them.
--
-- Nothing is filed on a refusal. `severity_statements` is itself the record of
-- what was stated, and a refused statement is by definition one that stated
-- nothing: a row there would be a severity on a Finding that does not carry it.

CREATE FUNCTION propose_severity(
        p_label     text,
        p_severity  text,
        p_basis     text,
        p_rationale text)
RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE v_find findings%ROWTYPE;
BEGIN
    v_find := rk2_finding_for_label(p_label);
    IF v_find.id IS NULL THEN
        RETURN rk2_no_such_finding(p_label);
    END IF;
    BEGIN
        RETURN state_severity(v_find.id, p_severity, p_basis, p_rationale)
               || jsonb_build_object('outcome', 'stated');
    EXCEPTION WHEN raise_exception OR foreign_key_violation OR check_violation
                OR unique_violation OR not_null_violation
                OR invalid_parameter_value OR invalid_text_representation
                OR insufficient_privilege THEN
        RETURN jsonb_build_object('outcome', 'refused', 'refusal', SQLERRM);
    END;
END $fn$;

COMMENT ON FUNCTION propose_severity(text, text, text, text) IS
    'Ticket 103. The caller''s half of `state_severity`: a Finding label a child '
    'can read, and each of the three refusals ticket 38 wrote as an exception '
    'answered as a sentence instead. Writes nothing of its own -- the statement '
    'row is the record, and a refused statement stated nothing.';


-- ===========================================================================
-- 4. The report a hunter composes, and the vector the runtime computes
-- ===========================================================================
-- Two things in one function on purpose. `compose_finding_report` already
-- returns the hard blockers that remain after a composition, and `cvss_stale`
-- is one of them -- with the computed vector written out in its own detail. A
-- model handed that blocker could only answer it by reading the vector out of
-- the sentence and asking the runtime to store what the runtime just computed.
--
-- So the step runs here, between the composition and the blocker list, and the
-- list the child is shown is the one that is true afterwards. That is ticket
-- 103's "the step goes where that blocker would otherwise be raised", written
-- as the two statements it turns out to be.
--
-- The order matters and is not interchangeable: `compute_finding_cvss` reads
-- `finding_effects`, so a vector computed before the composition is a vector
-- about the previous rendering. `apply_computed_cvss` raises when there is
-- nothing to score, which after a `composed` outcome means the effects named no
-- witnessed impact metric -- a Finding with no CVSS is a Finding whose report
-- is blocked for other reasons, not an error to abort a composition with.
--
-- THE LABELS, RESOLVED BEFORE THE COMPOSITION IS PASSED ON.
--
-- `compose_finding_report` reads the evidence out of the document as uuids --
-- `(e.value ->> 'witness')::uuid`, `(c.value ->> 'receipt')::uuid` and
-- `(c.value ->> 'observation')::uuid`
-- (`20260820T000000Z__a_report_is_a_projection_of_what_holds.sql:494,508`) --
-- and nothing a model can read is a uuid. What the served Contract sends is
-- what the child was shown: an Observation label in each effect's `witness`
-- and in a citation's `observation`, a Receipt label in a citation's
-- `receipt`, all three bounded by `_label()` in `roster.py`'s
-- `mcp__rk2__compose_finding_report`. So the document is rewritten here,
-- before it is handed on, for `rk2_no_such_finding`'s reason one level down:
-- passed through as it arrived, `O7` reaches the cast as an
-- `invalid_text_representation`, and a Receipt belonging to another Program
-- reaches 034's `(receipt_id, program_id)` foreign key
-- (`0034_reports.sql:398-399`) -- two sentences written in uuids about a
-- composition that was written in labels.
--
-- Every unresolved label at once, and not the first one found. The Contract
-- admits sixteen effects and sixteen steps of eight citations each, so a run
-- that had to re-send the whole document once per bad word would spend its
-- turns discovering them one at a time. Nothing is written on that path: the
-- composition is the record of what was composed, and a refused composition
-- composed nothing.
--
-- `effect`, `mechanism` and `params` are passed through untouched. Those are
-- vocabulary ids and the slots a mechanism's sentence fills, not labels; 034's
-- own foreign keys rule on the first two and `chain_step_grounding` on the
-- third.

CREATE FUNCTION propose_finding_report(p_label text, p_composition jsonb)
RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p        uuid  := rk2_program_required();
    v_comp   jsonb := coalesce(p_composition, 'null'::jsonb);
    -- Malformed is empty here, so that a document whose `effects` is not an
    -- array is refused by the sentence `compose_finding_report` already writes
    -- for one that is empty (`20260820T000000Z...:477-484`) rather than by
    -- `jsonb_array_elements` raising 22023 inside the rewrite below -- which
    -- would abort the caller's transaction, which is the thing this whole file
    -- exists to stop happening.
    v_effects jsonb := CASE WHEN jsonb_typeof(v_comp -> 'effects') = 'array'
                            THEN v_comp -> 'effects' ELSE '[]'::jsonb END;
    v_steps  jsonb := CASE WHEN jsonb_typeof(v_comp -> 'steps') = 'array'
                           THEN v_comp -> 'steps' ELSE '[]'::jsonb END;
    v_obs    jsonb;              -- Observation label -> id, this Program's only
    v_rcpt   jsonb;              -- Receipt label -> id, likewise
    v_missing text[];
    v_find   findings%ROWTYPE;
    v_result jsonb;
    v_vector text;
BEGIN
    v_find := rk2_finding_for_label(p_label);
    IF v_find.id IS NULL THEN
        RETURN rk2_no_such_finding(p_label);
    END IF;

    -- Every label the document says, in the three places it can say one,
    -- looked for in this Program alone -- which is what turns a Receipt
    -- belonging to somebody else into a word this Program does not hold rather
    -- than into a foreign key violation two calls later. A jsonpath and not a
    -- walk because reading is all this half does, and because lax mode answers
    -- an absent key, a `steps` that is not an array and an element that is not
    -- an object with no rows rather than an error -- the same answer the
    -- rewrite below gives all three.
    WITH said AS (
        SELECT 'observation'::text AS kind, q.token #>> '{}' AS label
          FROM jsonb_path_query(v_comp, '$.effects[*].witness') AS q(token)
        UNION
        SELECT 'observation', q.token #>> '{}'
          FROM jsonb_path_query(v_comp, '$.steps[*].citations[*].observation') AS q(token)
        UNION
        SELECT 'receipt', q.token #>> '{}'
          FROM jsonb_path_query(v_comp, '$.steps[*].citations[*].receipt') AS q(token)
    ),
    held AS (
        SELECT said.kind, said.label, coalesce(o.id, r.id)::text AS id
          FROM said
          LEFT JOIN observations o ON said.kind = 'observation'
                                 AND o.program_id = p AND o.label = said.label
          LEFT JOIN receipts r ON said.kind = 'receipt'
                              AND r.program_id = p AND r.label = said.label
         -- A slot holding JSON null said no label; it stays null and reaches
         -- `compose_finding_report` as the null it already was.
         WHERE said.label IS NOT NULL
    )
    SELECT coalesce(jsonb_object_agg(h.label, h.id)
                      FILTER (WHERE h.kind = 'observation' AND h.id IS NOT NULL), '{}'::jsonb),
           coalesce(jsonb_object_agg(h.label, h.id)
                      FILTER (WHERE h.kind = 'receipt' AND h.id IS NOT NULL), '{}'::jsonb),
           array_agg(initcap(h.kind) || ' ' || h.label ORDER BY h.kind, h.label)
                      FILTER (WHERE h.id IS NULL)
      INTO v_obs, v_rcpt, v_missing
      FROM held h;

    -- Named with the kind each was read as, because a Receipt label sent in an
    -- `observation` slot is a real mistake whose only visible symptom is that
    -- this Program holds no Observation by that name.
    IF v_missing IS NOT NULL THEN
        RETURN jsonb_build_object(
            'outcome', 'refused',
            'refusal', format(
                'this composition cites evidence this Program does not hold: %s',
                array_to_string(v_missing, ', ')));
    END IF;

    -- The same document in the ids the verb takes. Rebuilt rather than patched
    -- in place: every key `compose_finding_report` reads is written here and a
    -- key it does not read is not its business. `jsonb_strip_nulls` on the
    -- citation is what keeps a key that was absent absent, so that 034's
    -- `(receipt_id IS NOT NULL) <> (observation_id IS NOT NULL)`
    -- (`0034_reports.sql:396`) stays a question about what the hunter cited.
    v_comp := jsonb_build_object(
        'effects', (SELECT coalesce(jsonb_agg(jsonb_build_object(
                                        'effect',  e.value -> 'effect',
                                        'witness', v_obs -> (e.value ->> 'witness'))
                                    ORDER BY e.ordinality), '[]'::jsonb)
                      FROM jsonb_array_elements(v_effects)
                           WITH ORDINALITY AS e(value, ordinality)),
        'steps',   (SELECT coalesce(jsonb_agg(jsonb_build_object(
                                        'mechanism', s.value -> 'mechanism',
                                        'params',    coalesce(s.value -> 'params', '{}'::jsonb),
                                        'citations', (
                                            SELECT coalesce(jsonb_agg(jsonb_strip_nulls(
                                                       jsonb_build_object(
                                                           'receipt',     v_rcpt -> (c.value ->> 'receipt'),
                                                           'observation', v_obs  -> (c.value ->> 'observation')))
                                                   ORDER BY c.ordinality), '[]'::jsonb)
                                              FROM jsonb_array_elements(
                                                       CASE WHEN jsonb_typeof(s.value -> 'citations') = 'array'
                                                            THEN s.value -> 'citations' ELSE '[]'::jsonb END)
                                                   WITH ORDINALITY AS c(value, ordinality)))
                                    ORDER BY s.ordinality), '[]'::jsonb)
                      FROM jsonb_array_elements(v_steps)
                           WITH ORDINALITY AS s(value, ordinality)));

    v_result := compose_finding_report(v_find.id, v_comp);
    IF v_result ->> 'outcome' IS DISTINCT FROM 'composed' THEN
        RETURN v_result;
    END IF;

    BEGIN
        v_vector := apply_computed_cvss(v_find.id);
    EXCEPTION WHEN raise_exception THEN
        v_vector := NULL;
    END;
    PERFORM set_actor('runtime');

    RETURN v_result || jsonb_build_object(
        'finding',     v_find.label,
        'cvss_vector', v_vector,
        'blockers', (SELECT coalesce(
                              jsonb_agg(jsonb_build_object('code', b.code,
                                                           'detail', b.detail)
                                        ORDER BY b.code, b.detail), '[]'::jsonb)
                       FROM report_blockers(v_find.id) b
                      WHERE b.severity = 'hard'));
END $fn$;

COMMENT ON FUNCTION propose_finding_report(text, jsonb) IS
    'Ticket 103. The caller''s half of `compose_finding_report`, and the home of '
    '`apply_computed_cvss`: takes the labels a child can read -- the Finding''s, '
    'the Observation witnessing each effect, and the Receipt or Observation each '
    'citation rests on -- resolves them to the ids that verb takes, composes the '
    'impact and reproduction halves, writes the CVSS vector the composition made '
    'computable, and answers with the hard blockers that are true after both. '
    'Refuses a label this Program does not hold by naming every unresolved one '
    'at once, and writes nothing on that path.';


-- ===========================================================================
-- 5. The surface, declared
-- ===========================================================================

REVOKE ALL ON FUNCTION rk2_finding_for_label(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION rk2_no_such_finding(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION propose_impact_task(text, jsonb, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION propose_severity(text, text, text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION propose_finding_report(text, jsonb) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION rk2_finding_for_label(text) TO rk2_runtime;
GRANT EXECUTE ON FUNCTION rk2_no_such_finding(text) TO rk2_runtime;
GRANT EXECUTE ON FUNCTION propose_impact_task(text, jsonb, uuid) TO rk2_runtime;
GRANT EXECUTE ON FUNCTION propose_severity(text, text, text, text) TO rk2_runtime;
GRANT EXECUTE ON FUNCTION propose_finding_report(text, jsonb) TO rk2_runtime;

-- 066's registry. `check_runtime_privileges` refuses a verb the runtime can
-- execute that no row here names, so the grant and the row are one statement
-- made twice on purpose: the second half is the one a reader of the surface
-- finds.
INSERT INTO runtime_verb_surface (verb, added_by, note) VALUES
    ('rk2_finding_for_label(text)', '103',
     'resolves a Finding label to the row, for the three served downstream Contracts that all refuse an unknown label the same way'),
    ('rk2_no_such_finding(text)', '103',
     'the refusal sentence those three answer an unknown label with, naming the word that was said'),
    ('propose_impact_task(text, jsonb, uuid)', '103',
     'the caller of open_impact_task, which had none: resolves the Finding label, files the test_proposals row and turns ticket 38''s exceptions into sentences'),
    ('propose_severity(text, text, text, text)', '103',
     'the caller of state_severity, which had none outside the tests: resolves the Finding label and carries back the three refusals ticket 38 wrote as exceptions'),
    ('propose_finding_report(text, jsonb)', '103',
     'the caller of compose_finding_report and the home of apply_computed_cvss: resolves the Finding label and every Observation and Receipt label the composition cites to the ids that verb takes, composes, writes the derived vector, and answers with the hard blockers that are true afterwards');


-- ===========================================================================
-- 6. What this migration claims, asserted
-- ===========================================================================

DO $$
BEGIN
    -- The point of the whole ticket, stated as the thing that would have to
    -- stay true: each of the three underlying verbs is reachable from a caller
    -- only because a function above calls it.
    IF (SELECT count(*) FROM pg_proc
         WHERE proname IN ('open_impact_task', 'state_severity',
                           'compose_finding_report', 'apply_computed_cvss')
           AND has_function_privilege('rk2_runtime', oid, 'EXECUTE')) <> 4 THEN
        RAISE EXCEPTION 'ticket 103: a downstream verb is not executable by its caller';
    END IF;

    -- And the half ticket 38 wrote and this file leans on: the three forbidden
    -- impact classes are still forbidden, so the schema that does not offer
    -- them is the second door rather than the only one.
    IF EXISTS (
        SELECT 1 FROM impact_classes ic
          JOIN risk_classes rc ON rc.risk_class = ic.risk_class
         WHERE ic.impact_class IN ('degrade_availability', 'reach_third_party',
                                   'pivot_out_of_scope')
           AND rc.decision <> 'deny'
    ) THEN
        RAISE EXCEPTION 'ticket 103: a forbidden impact class is no longer denied';
    END IF;
END $$;
