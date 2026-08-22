-- ---------------------------------------------------------------------------
-- 20260925T000000Z__the_model_asks_and_the_runtime_writes.sql
--                                                                  (ticket 102)
--
-- `open_finding` holds the only `INSERT INTO findings` in this corpus and has
-- never been called. 020's `mcp__rk2__propose_finding` is the ask that reaches
-- it, and this file is the half between the two: the child names a Hypothesis
-- by the label it can read, and something has to turn that label into the
-- claim, the run that settled it and the Agent run that asked.
--
-- WHY A VERB RATHER THAN THREE QUERIES IN THE SUPERVISOR.
--
-- The resolution is a join and not a lookup. The run that settled a claim is
-- named nowhere on the claim: it is reached through the transition from
-- `testing` to `supported` that the runtime recorded, the Receipt that
-- transition cites, and the Test run that Receipt belongs to -- which is
-- exactly the path arm seven of `rk2_finding_refusal` walks to refuse a
-- proposal that named the wrong run. Written in Python that join would be a
-- second copy of arm seven, in a second language, free to drift from the arm it
-- is supposed to agree with. Written here it is one statement beside the arm,
-- and the two are read together by anybody changing either.
--
-- WHAT THIS FUNCTION MAY NOT DO, AND DOES NOT.
--
-- It takes no Program. `open_finding` reads the Program off the session through
-- `rk2_program_required()`, and a Program argument here would be a second
-- statement of which Program the supervisor is holding a connection for. It
-- decides nothing: every refusal it can answer with is a sentence
-- `rk2_finding_refusal` wrote, except the one this file adds, and that one is
-- about a name rather than about evidence. And it is INVOKER rather than
-- SECURITY DEFINER, because the caller is `rk2_runtime`, which already executes
-- `open_finding` and already reads every table read here -- arm seven reads two
-- of them on its behalf today. A definer wrapper would hand the runtime a
-- privilege it does not need in order to do what it can already do.


-- ===========================================================================
-- 1. The label a child can say, resolved to the rows a Finding rests on
-- ===========================================================================

CREATE FUNCTION propose_finding(
        p_label     text,
        p_class     text,
        p_title     text,
        p_agent_run uuid DEFAULT NULL)
RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p           uuid := rk2_program_required();
    v_said      text := btrim(coalesce(p_label, ''));
    v_hypothesis uuid;
    v_test_run  uuid;
    v_agent_run uuid;
BEGIN
    -- The same guard `open_finding` puts on its own provenance, applied before
    -- the refusal path below can file a row citing it. An Agent run belonging
    -- to another Program is not provenance for a proposal here, and the
    -- composite foreign key would raise on it -- taking the record of the
    -- attempt down with the mistake.
    SELECT ar.id INTO v_agent_run
      FROM agent_runs ar WHERE ar.id = p_agent_run AND ar.program_id = p;

    SELECT h.id INTO v_hypothesis
      FROM hypotheses h WHERE h.program_id = p AND h.label = v_said;

    -- The one refusal this file owns. `open_finding` refuses an unknown claim
    -- already, in arm one, but it refuses a uuid: handed NULL it would answer
    -- "<NULL> is not a Hypothesis of this Program", which tells the child
    -- nothing about the word it actually said. So the sentence is written here,
    -- naming what was said, and the record of the attempt is filed in the same
    -- place every other refused proposal is filed rather than skipped because
    -- this one failed early.
    IF v_hypothesis IS NULL THEN
        PERFORM set_actor('runtime');
        INSERT INTO finding_proposals
            (program_id, agent_run_id, class_id, title, outcome, refusal)
        VALUES
            (p, v_agent_run, p_class,
             coalesce(nullif(btrim(coalesce(p_title, '')), ''), '(none)'),
             'refused',
             format('%s is not a Hypothesis of this Program',
                    coalesce(nullif(v_said, ''), '(none)')));
        RETURN jsonb_build_object(
            'outcome', 'refused',
            'refusal', format('%s is not a Hypothesis of this Program',
                              coalesce(nullif(v_said, ''), '(none)')));
    END IF;

    -- The run that settled the claim, read the way arm seven reads it. The
    -- latest such transition and not the first: a claim that went back to
    -- `testing` and forward again is settled by the second passage, and the
    -- Finding rests on the settlement in force rather than on the one that was
    -- superseded by re-testing.
    --
    -- NULL is a possible answer and is passed on rather than refused here. A
    -- claim with no runtime transition citing a run's Receipt is a claim that
    -- did not reach `supported` the way a Finding requires, and `open_finding`
    -- says which of its own arms that is -- in the order those arms are written,
    -- which puts the honest reason first. A sentence invented here would
    -- announce a missing run to a child whose real trouble is that its claim is
    -- still `proposed`.
    SELECT trr.test_run_id INTO v_test_run
      FROM hypothesis_transitions ht
      JOIN test_run_receipts trr ON trr.receipt_id = ht.receipt_id
     WHERE ht.hypothesis_id = v_hypothesis
       AND ht.from_status = 'testing'
       AND ht.to_status = 'supported'
       AND ht.actor_kind = 'runtime'
     ORDER BY ht.at DESC
     LIMIT 1;

    RETURN open_finding(v_hypothesis, v_test_run, p_class, p_title, v_agent_run);
END $fn$;

COMMENT ON FUNCTION propose_finding(text, text, text, uuid) IS
    'Ticket 102. The caller''s half of `open_finding`: a Hypothesis label a '
    'child can read, resolved to the claim, to the run whose Receipt the '
    'runtime cited when it settled that claim, and to the Agent run that '
    'asked. Answers whatever `open_finding` answered, and refuses a label this '
    'Program does not hold by naming the label rather than a null uuid.';

REVOKE ALL ON FUNCTION propose_finding(text, text, text, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION propose_finding(text, text, text, uuid) TO rk2_runtime;

-- 066's registry, which is what makes the grant above a declaration rather than
-- a fact somebody would have to go and measure. `check_runtime_privileges`
-- refuses a verb the runtime can execute that no row here names, so the grant
-- and the row are one statement made twice on purpose: the second half is the
-- one a reader of the surface finds.
INSERT INTO runtime_verb_surface (verb, added_by, note) VALUES
    ('propose_finding(text, text, text, uuid)',
     '102',
     'resolves a Hypothesis label to the claim and the run that settled it, and calls open_finding -- the corpus''s only writer of a Finding, which had no caller before this');


-- ===========================================================================
-- 2. What this migration claims, asserted
-- ===========================================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_proc
         WHERE proname = 'propose_finding'
           AND has_function_privilege('rk2_runtime', oid, 'EXECUTE')
    ) THEN
        RAISE EXCEPTION 'ticket 102: the runtime cannot carry a proposal';
    END IF;

    -- The point of the whole ticket, stated as the thing that would have to
    -- stay true. `open_finding` is reachable from a caller only because this
    -- function calls it, so a later file that dropped the grant, or renamed
    -- the function out from under this one, should fail here rather than
    -- quietly return the tree to the state the wiring audit found it in.
    IF NOT EXISTS (
        SELECT 1 FROM pg_proc
         WHERE proname = 'open_finding'
           AND has_function_privilege('rk2_runtime', oid, 'EXECUTE')
    ) THEN
        RAISE EXCEPTION 'ticket 102: open_finding is not executable by its caller';
    END IF;

    -- A proposal that names no claim still leaves a row, which is the half of
    -- ticket 36's record that the early refusal above could have lost. If the
    -- column ever stopped accepting a null claim, that row could not be written
    -- and the refusal would raise instead of answering.
    IF EXISTS (
        SELECT 1 FROM pg_attribute
         WHERE attrelid = 'finding_proposals'::regclass
           AND attname = 'hypothesis_id' AND attnotnull
    ) THEN
        RAISE EXCEPTION 'ticket 102: a proposal naming no claim can no longer be filed';
    END IF;
END $$;
