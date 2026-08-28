-- A body comparison reads the body
-- ---------------------------------------------------------------------------
-- Ticket 101. `body_equals` and `body_differs` have compared whole messages
-- since `20260815T000000Z__a_test_runs_through_the_replay_lane.sql:1500-1516`,
-- because `receipts.response_agent_sha` was the only response digest a Receipt
-- carried. That column is `store.put(transcript(status line, headers, blank
-- line, body))` (`proxy.py:3088`, `:3104`), so it is the whole answer and not
-- the body of it.
--
-- Which makes the simplest control a Test can state unusable. "Send the same
-- request twice and the two answers agree" is the baseline half of twenty
-- Playbooks, and a `Date` header that ticks over between the two sends is
-- enough to make it fail. A control that cannot hold leaves every Test
-- `inconclusive`, and an inconclusive Test reaches no Finding -- so the corpus
-- was grading a stability check that the schema could not answer.
--
-- The column this needs was added by ticket 214 for a different question.
-- `receipts.response_body_sha256` is the digest of the bytes the agent was
-- returned, without the status line and without the headers
-- (`20261217T000000Z__a_receipt_answers_the_arm_it_was_planned_for.sql`). So
-- the price here is two arms of one CASE and no new column.
--
-- ## The NULL branch stays where it is
--
-- `20260815T000000Z:1500-1502` answers NULL when either Receipt has no
-- `response_agent_sha`, and the comment above it gives the reason: two Receipts
-- that both stored nothing are not two identical bodies, they are two answers
-- nobody kept, and reading them as equal would turn an unanswered question into
-- a refutation. That question -- did anyone look -- is still the question
-- `response_agent_sha` answers, because it is the column the store writes for
-- every allowed exchange. Only the comparison underneath it moves.
--
-- The old-Receipt case falls out of that unchanged. A Receipt written before
-- ticket 214 has a `response_agent_sha` and a NULL `response_body_sha256`, so
-- the guard passes, the comparison is NULL, and the assertion is unanswerable
-- rather than false. `IS DISTINCT FROM` is still not used here, and for the
-- same reason it was not used before: it would spell that NULL as a verdict.


CREATE OR REPLACE FUNCTION evaluate_test_assertions(p_tool_run_id uuid) RETURNS jsonb
LANGUAGE plpgsql STABLE AS $fn$
DECLARE
    v_spec      jsonb;
    v_assertion jsonb;
    v_kind      text;
    v_left      receipts%ROWTYPE;
    v_right     receipts%ROWTYPE;
    v_held      boolean;
    v_results   jsonb := '[]'::jsonb;
    v_failed    text[] := '{}';
    v_unknown   boolean := false;
    v_outcome   text;
BEGIN
    SELECT te.spec INTO v_spec
      FROM test_replays tp JOIN tests te ON te.id = tp.test_id
     WHERE tp.tool_run_id = p_tool_run_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'tool run % is not a replay', p_tool_run_id
            USING ERRCODE = '23503';
    END IF;

    FOR v_assertion IN SELECT * FROM jsonb_array_elements(v_spec -> 'assertions')
    LOOP
        v_kind := v_assertion ->> 'kind';
        v_left := NULL;
        v_right := NULL;
        SELECT r.* INTO v_left
          FROM test_replay_actions a JOIN receipts r ON r.id = a.receipt_id
         WHERE a.tool_run_id = p_tool_run_id
           AND a.ordinal = (v_assertion ->> 'action')::numeric::integer;
        IF v_assertion ? 'against' THEN
            SELECT r.* INTO v_right
              FROM test_replay_actions a JOIN receipts r ON r.id = a.receipt_id
             WHERE a.tool_run_id = p_tool_run_id
               AND a.ordinal = (v_assertion ->> 'against')::numeric::integer;
        END IF;

        v_held := CASE
            -- The two comparisons a missing row makes unanswerable, first,
            -- because every arm below reads a column off one of them.
            WHEN v_left.id IS NULL THEN NULL
            WHEN v_assertion ? 'against' AND v_right.id IS NULL THEN NULL
            WHEN v_kind = 'status_equals' THEN
                v_left.status_code = (v_assertion ->> 'status')::numeric::integer
            WHEN v_kind = 'status_differs' THEN
                CASE WHEN v_left.status_code IS NULL OR v_right.status_code IS NULL
                     THEN NULL
                     ELSE v_left.status_code <> v_right.status_code END
            -- `IS DISTINCT FROM` is deliberately not used on the bodies: two
            -- Receipts that both stored nothing are not two identical bodies,
            -- they are two answers nobody kept, and reading them as equal would
            -- turn an unanswered question into a refutation. That is what this
            -- arm asks -- did anyone look -- and `response_agent_sha` is the
            -- column that answers it, because the store writes it for every
            -- allowed exchange.
            WHEN v_left.response_agent_sha IS NULL
                 OR v_right.response_agent_sha IS NULL THEN NULL
            -- And the comparison itself reads the body. `response_agent_sha` is
            -- the whole message, so a `Date` that ticks over between two sends
            -- would refute "the same request answers the same way", which is
            -- the control half of twenty Playbooks. A Receipt written before
            -- ticket 214 carries no body digest, so this is NULL for it and the
            -- assertion is unanswerable rather than false.
            WHEN v_kind = 'body_equals' THEN
                v_left.response_body_sha256 = v_right.response_body_sha256
            WHEN v_kind = 'body_differs' THEN
                v_left.response_body_sha256 <> v_right.response_body_sha256
        END;

        IF v_held IS NULL THEN
            v_unknown := true;
        ELSIF NOT v_held THEN
            v_failed := array_append(v_failed, v_assertion ->> 'id');
        END IF;

        v_results := v_results || jsonb_build_object(
            'id', v_assertion ->> 'id',
            'kind', v_kind,
            'held', v_held);
    END LOOP;

    v_outcome := CASE WHEN v_unknown THEN 'inconclusive'
                      WHEN cardinality(v_failed) > 0 THEN 'refutes'
                      ELSE 'holds' END;

    RETURN jsonb_build_object(
        'assertions', v_results,
        'failed', to_jsonb(v_failed),
        'outcome', v_outcome);
END $fn$;


-- ---------------------------------------------------------------------------
-- What this migration is held to
-- ---------------------------------------------------------------------------
-- Read off the installed definition rather than off this file, because a body
-- that failed to replace would leave the old arms running and nothing else here
-- would notice.
DO $check$
DECLARE
    v_body text := pg_get_functiondef('evaluate_test_assertions(uuid)'::regprocedure);
BEGIN
    IF position('v_left.response_body_sha256 = v_right.response_body_sha256' IN v_body) = 0 THEN
        RAISE EXCEPTION 'body_equals does not compare the body digests';
    END IF;
    IF position('v_left.response_body_sha256 <> v_right.response_body_sha256' IN v_body) = 0 THEN
        RAISE EXCEPTION 'body_differs does not compare the body digests';
    END IF;
    -- The guard, still asking its own question off its own column.
    IF position('v_left.response_agent_sha IS NULL' IN v_body) = 0 THEN
        RAISE EXCEPTION 'the unanswerable arm no longer reads response_agent_sha';
    END IF;
    -- And nothing compares whole messages any more. The guard is the only
    -- reader of either side's `response_agent_sha`, so each qualified name
    -- occurs exactly once. Counting the qualified form rather than the bare
    -- column name, because the prose above it names the column too and
    -- `pg_get_functiondef` returns the comments with the code.
    IF (length(v_body) - length(replace(v_body, 'v_left.response_agent_sha', ''))) / 25 <> 1
       OR (length(v_body) - length(replace(v_body, 'v_right.response_agent_sha', ''))) / 26 <> 1
    THEN
        RAISE EXCEPTION 'the whole message is still compared somewhere in the body';
    END IF;
    IF (SELECT count(*) FROM pg_proc
         WHERE proname = 'evaluate_test_assertions'
           AND pronamespace = 'public'::regnamespace) <> 1 THEN
        RAISE EXCEPTION 'evaluate_test_assertions is not one function';
    END IF;
END $check$;
