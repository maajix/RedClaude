-- The orchestrator asks for a validation                             (ticket 105)
--
-- Two Contracts named a queue nothing served. This file serves one and retires
-- the other, which is the decision ticket 105 took on 2026-08-22 and has been
-- carrying since: "`request_validation` is served; `request_report` and
-- `report_queue` are retired ... one is a hand-off between two runtime roles and
-- the other is a request to take a step no part of the runtime may take."
--
-- What the delay cost, measured on `rk2here` 2026-08-30 before this file:
--
--     findings                 9   every one candidate, every one severity=info
--     validate tasks, ever     0
--     report tasks, ever       0
--     severity_statements      0
--
-- and the database's own sentence about each of them, from
-- `rk2_validation_refusal`: "nothing asked for the Finding F8 to be validated".
-- The thing that would have asked is `mcp__rk2__request_validation`, declared
-- since 011 and served by nothing, so a hunt that finds something can propose a
-- Finding and can never get one judged. An operator running `rk finding
-- validate` was the only way past it, one Finding at a time.
--
-- `propose_validation` is the wrapper the tool calls, and it is
-- `propose_severity` (`20261031T000000Z:194-215`) in the same shape for the same
-- reason: the agent surface speaks in labels and `request_validation` takes two
-- uuids, and a refusal has to come back as a document the child can read rather
-- than as an exception that aborts the transaction the supervisor holds open
-- across every call one child makes. Nothing here re-decides anything
-- `request_validation` decides. It resolves a label, or says there is no such
-- Finding in the words `rk2_no_such_finding` already uses.
--
-- `report_queue` is dropped. Three facts and any one of them would be enough:
-- no `INSERT` anywhere in the corpus, no reader anywhere, and the step it would
-- queue is reserved -- `cli.py:1327-1339`, "the last step, and the only one no
-- part of the runtime may take: `validated -> reported` is reserved for a human
-- actor". A model asking to be reported would be asking for a transition its own
-- runtime may not make on its behalf. Its two registry rows go with it, because
-- a row naming a table that is not there is what `check_purge_cascade` reports
-- and what `0030`'s own register exists to keep honest.
--
-- The three `IN` lists that name it by string -- `check_state_access` at
-- `0020:497` and `:507`, and `20260810T094500Z:409` -- are left alone. They
-- compare a name against `information_schema` and `pg_class`, so a name with no
-- table behind it matches nothing and reports nothing. Editing an applied
-- migration is the one thing `check_migrations` refuses outright.

-- ---------------------------------------------------------------------------
-- 1. The verb the tool calls
-- ---------------------------------------------------------------------------

CREATE FUNCTION propose_validation(p_label text) RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE v_find findings%ROWTYPE;
BEGIN
    v_find := rk2_finding_for_label(p_label);
    IF v_find.id IS NULL THEN
        RETURN rk2_no_such_finding(p_label);
    END IF;
    BEGIN
        RETURN request_validation(v_find.program_id, v_find.id);
    EXCEPTION WHEN raise_exception OR foreign_key_violation OR check_violation
                OR unique_violation OR not_null_violation
                OR invalid_parameter_value OR invalid_text_representation
                OR insufficient_privilege THEN
        RETURN jsonb_build_object('outcome', 'refused', 'refusal', SQLERRM);
    END;
END $fn$;

COMMENT ON FUNCTION propose_validation(text) IS
    'The orchestrator''s half of the hand-off `20260815T180000Z:632-634` names: '
    '"request_validation is the orchestrator''s step ... and open_validation is '
    'the runtime''s". A label in, the queue row or the refusal out, and every '
    'refusal returned rather than raised so that one refused ask does not cost '
    'the call after it.';

REVOKE ALL ON FUNCTION propose_validation(text) FROM PUBLIC, rk2_state, rk2_proxy;
GRANT EXECUTE ON FUNCTION propose_validation(text) TO rk2_runtime;


-- ---------------------------------------------------------------------------
-- 2. The queue nothing ever filled
-- ---------------------------------------------------------------------------

DELETE FROM purge_cascade_edges
 WHERE (table_name, column_name) = ('report_queue', 'program_id');

DELETE FROM event_table_exempt WHERE table_name = 'report_queue';

DROP TABLE report_queue;
