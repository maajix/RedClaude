-- ---------------------------------------------------------------------------
-- a_test_is_authored_inside_the_scope_it_will_run_in.sql   (ticket 154)
--
-- `rk2_replay_plan` walks every request a Test would make and refuses the run
-- if one of them falls outside the Program's scope. `propose_test` does not,
-- so the two disagree about whether a row may exist: one admits the Test and
-- the other refuses to act on it, and the disagreement is only discovered by
-- the Task that claimed it, a pass later and a run too late.
--
-- Measured on `rk2hunt13`, the first lap that reached `replay.run` from a
-- `perform` Task:
--
--     the registry refused this replay: the Test reaches outside the
--     current scope: http://www.yekta-it.de/
--
-- Both Tests the hunts authored carry `http://` actions and the Program admits
-- https on 443 and nothing else, so both were unrunnable from the moment they
-- were written. `test_proposals` recorded both as `created`.
--
-- The walk moves to where the Test is written. A hunt that is refused there can
-- author a second specification inside the same run; a hunt that is refused a
-- pass later has ended. Nothing else about the claim changes: no Test row is
-- written, so the Hypothesis stays `testable`, which is what it is.
-- ---------------------------------------------------------------------------

-- ===========================================================================
-- 1. The walk, as a question rather than an exception
-- ===========================================================================
--
-- `rk2_replay_plan` raises, because by then there is a run to stop. Here there
-- is an author to answer, and `propose_test` already has one channel for that:
-- a `refused` row in `test_proposals` carrying the sentence. So this returns
-- the sentence and raises nothing.
--
-- The three lists are walked together and in the same order the replay walks
-- them, for the reason the replay gives: a cleanup step pointing outside the
-- scope is a request the door would refuse at the moment the run is least able
-- to do anything about it.

CREATE FUNCTION rk2_test_scope_problem(p_program uuid, p_spec jsonb) RETURNS text
LANGUAGE plpgsql STABLE AS $fn$
DECLARE
    v_action jsonb;
    v_route  record;
    v_class  text;
BEGIN
    FOR v_action IN
        SELECT * FROM jsonb_array_elements(
            coalesce(p_spec -> 'actions', '[]'::jsonb)
              || coalesce(p_spec -> 'setup', '[]'::jsonb)
              || coalesce(p_spec -> 'cleanup', '[]'::jsonb))
    LOOP
        SELECT * INTO v_route FROM rk2_test_route(v_action ->> 'url');
        SELECT s.scope_class INTO v_class
          FROM programs pr
          CROSS JOIN LATERAL scope_class_of(
                pr.id, pr.scope_version, v_route.host, v_route.port,
                v_route.path, v_route.path, v_route.scheme, 'request') s
         WHERE pr.id = p_program;
        -- The same two classes the replay admits, and `denied` for a URL no
        -- rule mentions: a scope that does not name a host has not permitted
        -- it.
        IF coalesce(v_class, 'denied') NOT IN ('target', 'egress_support') THEN
            RETURN format('the Test reaches outside the current scope: %s',
                          v_action ->> 'url');
        END IF;
    END LOOP;
    RETURN NULL;
END $fn$;

COMMENT ON FUNCTION rk2_test_scope_problem(uuid, jsonb) IS
  'Ticket 154: the first URL in a specification that the Program''s scope does not admit, as the sentence an author is answered with, or NULL when every request the Test would make is in scope. The same walk `rk2_replay_plan` makes before a replay, asked early enough that the run which wrote the Test can write another one.';

REVOKE ALL ON FUNCTION rk2_test_scope_problem(uuid, jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION rk2_test_scope_problem(uuid, jsonb) TO rk2_runtime;


-- ===========================================================================
-- 2. The author is asked before the row is written
-- ===========================================================================

CREATE OR REPLACE FUNCTION propose_test(
        p_label     text,
        p_spec      jsonb,
        p_agent_run uuid DEFAULT NULL)
RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p            uuid := rk2_program_required();
    v_said       text := btrim(coalesce(p_label, ''));
    v_spec       jsonb := coalesce(p_spec, 'null'::jsonb);
    v_hypothesis uuid;
    v_status     text;
    v_agent_run  uuid;
    v_refusal    text;
    v_digest     text;
    v_id         uuid;
    v_label      text;
    v_outcome    text;
BEGIN
    PERFORM set_actor('runtime');

    -- Provenance, and only this Program's. An Agent run belonging to somebody
    -- else is not provenance for a row here, and the composite foreign key
    -- would raise on it -- taking the record of the attempt down with the
    -- mistake.
    SELECT ar.id INTO v_agent_run
      FROM agent_runs ar WHERE ar.id = p_agent_run AND ar.program_id = p;

    SELECT h.id, h.status INTO v_hypothesis, v_status
      FROM hypotheses h WHERE h.program_id = p AND h.label = v_said;

    IF v_hypothesis IS NULL THEN
        v_refusal := format('%s is not a Hypothesis of this Program',
                            coalesce(nullif(v_said, ''), '(none)'));
    ELSIF v_status <> 'testable' THEN
        v_refusal := format(
            'hypothesis %s is %s, and a Test may only be authored for a testable claim',
            v_said, v_status);
    ELSE
        v_refusal := rk2_test_spec_problem(v_spec);
        -- Ticket 154, and second because the shape has to hold before the URLs
        -- inside it can be read at all. `rk2_test_spec_problem` is what says
        -- every action carries a well-formed `url`; asking the scope first
        -- would be asking `rk2_test_route` to parse whatever arrived.
        IF v_refusal IS NULL THEN
            v_refusal := rk2_test_scope_problem(p, v_spec);
        END IF;
    END IF;

    IF v_refusal IS NOT NULL THEN
        INSERT INTO test_proposals
            (program_id, hypothesis_id, agent_run_id, spec, outcome, refusal)
        VALUES (p, v_hypothesis, v_agent_run, v_spec, 'refused', v_refusal);
        RETURN jsonb_build_object('outcome', 'refused', 'refusal', v_refusal);
    END IF;

    v_digest := rk2_test_spec_digest(v_spec);

    -- `ON CONFLICT` rather than a look-then-insert, and rather than the advisory
    -- lock `open_finding` takes on its cell. A Finding's cell is a functional
    -- expression with no unique index behind it, so that one has to hold a lock;
    -- this one is `tests_hypothesis_id_spec_sha256_key`, a real unique
    -- constraint, so the database decides the race and the loser reads the row
    -- the winner wrote. What that avoids is the failure mode 036 names: a unique
    -- violation aborts the transaction and takes the record of the attempt down
    -- with it, so the one proposal an operator most wants to see is the one that
    -- would leave no row.
    INSERT INTO tests (program_id, hypothesis_id, spec, spec_sha256, created_by_run_id)
    VALUES (p, v_hypothesis, v_spec, v_digest, v_agent_run)
    ON CONFLICT (hypothesis_id, spec_sha256) DO NOTHING
    RETURNING id, label INTO v_id, v_label;

    IF v_id IS NULL THEN
        -- One Hypothesis holds one copy of a specification -- performing it
        -- twice is what a second Test run is for. So a second identical
        -- proposal is answered with the Test that is already there and is not a
        -- refusal: it is a run that reached the same plan the last one did,
        -- which is a fact worth having in this table and not a mistake.
        SELECT t.id, t.label INTO v_id, v_label
          FROM tests t
         WHERE t.hypothesis_id = v_hypothesis AND t.spec_sha256 = v_digest;
        v_outcome := 'existing';
    ELSE
        v_outcome := 'created';
    END IF;

    INSERT INTO test_proposals
        (program_id, hypothesis_id, agent_run_id, spec, outcome, test_id)
    VALUES (p, v_hypothesis, v_agent_run, v_spec, v_outcome, v_id);

    RETURN jsonb_build_object(
        'outcome',     v_outcome,
        'test',        v_label,
        'hypothesis',  v_said,
        -- The identity, because that is what a Test is. `tests` is immutable and
        -- `rk2_test_spec_digest` is over the stored jsonb, so this is the one
        -- value that distinguishes the plan that was stored from any other plan
        -- the run might have meant to send.
        'spec_sha256', v_digest,
        'actions',     jsonb_array_length(v_spec -> 'actions'),
        'assertions',  jsonb_array_length(v_spec -> 'assertions'));
END $fn$;

INSERT INTO runtime_verb_surface (verb, added_by, note) VALUES
    ('rk2_test_scope_problem(uuid, jsonb)', '154',
     'the scope walk `propose_test` makes before it writes a Test, so a specification the door would refuse is refused to its author instead');
