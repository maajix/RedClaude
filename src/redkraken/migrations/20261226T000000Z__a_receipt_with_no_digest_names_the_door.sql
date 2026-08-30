-- A receipt with no digest names the door, not the headers          (ticket 220)
--
-- `record_test_action` compared three digests with `IS DISTINCT FROM`, which
-- collapses two different failures into one word. "The door wrote a different
-- digest" is a Receipt that answers another arm than the action states, and it
-- must stop the grading. "The door wrote no digest" is a door process older
-- than the release that added the column, and it must stop the grading too --
-- but the operator's next command is different, and the word they were given
-- sent them to the wrong one.
--
-- What it cost, measured on `rk2here` 2026-08-29: 2494 Receipts over four days,
-- none carrying `request_headers_sha256`, 86 lap reports saying "carries
-- different headers", 0 rows in `test_replay_actions`, 0 of 44 assertions
-- evaluated. Every Test was `inconclusive`, so no `hypothesis_transitions` row
-- was written and no Finding above `info` could exist. `docker restart
-- rk2here-door` fixed it in one command, three days after it broke. The door
-- runs `src/` bind-mounted, so `rk db migrate` moved the reader and the running
-- Python process kept the old writer.
--
-- The query digest is left exactly as it was, and that is a decision rather than
-- an omission. `rk2_test_query` answers NULL for a url with no query and the
-- door writes NULL for a request with none (`proxy.query_sha256`, "absence stays
-- absence"), so NULL against NULL is a match on both sides and there is no third
-- reading to separate. Measured: 2681 Receipts on `rk2here`, 68 with a query
-- digest, and the comparison has never been the one that raised.
--
-- A blocked Receipt already holds three nulls and is already refused one branch
-- earlier, on `decision <> 'allowed'`, so nothing here changes what it says.
--
-- Verbatim from `20261217T000000Z__a_receipt_answers_the_arm_it_was_planned_for.sql`
-- except for the two branches above the header and body comparisons and the
-- comment. That file is applied and `check_migrations` holds its digest, which
-- is why this is a new file rather than an edit.


CREATE OR REPLACE FUNCTION record_test_action(
        p_tool_run_id uuid,
        p_ordinal     integer,
        p_receipt     text)
RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p          uuid := rk2_program_required();
    v_replay   test_replays%ROWTYPE;
    v_run      tool_runs%ROWTYPE;
    v_spec     jsonb;
    v_action   jsonb;
    v_receipt  receipts%ROWTYPE;
    v_test     tests%ROWTYPE;
    v_first    boolean;
    v_route    record;
    v_query    text;
BEGIN
    SELECT tp.* INTO v_replay FROM test_replays tp
     WHERE tp.tool_run_id = p_tool_run_id AND tp.program_id = p
       FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'tool run % is not a replay of this Program', p_tool_run_id
            USING ERRCODE = '23503';
    END IF;
    SELECT * INTO v_run FROM tool_runs WHERE id = p_tool_run_id;
    IF v_run.status <> 'running' THEN
        RAISE EXCEPTION 'replay % was already closed as %', v_run.label, v_run.status
            USING ERRCODE = '23514';
    END IF;

    SELECT * INTO v_test FROM tests WHERE id = v_replay.test_id;
    v_spec := v_test.spec;
    v_action := v_spec -> 'actions' -> (p_ordinal - 1);
    IF v_action IS NULL THEN
        RAISE EXCEPTION 'this Test performs no action %', p_ordinal
            USING ERRCODE = '22023';
    END IF;

    SELECT * INTO v_receipt FROM receipts
     WHERE label = p_receipt AND program_id = p;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'no receipt named % in this Program', p_receipt
            USING ERRCODE = '23503';
    END IF;
    -- Criterion 6's second refusal, at the first place it can be made: a
    -- Receipt some other Tool run produced is not this run's evidence, whatever
    -- Lane it carries.
    IF v_receipt.tool_run_id IS DISTINCT FROM p_tool_run_id THEN
        RAISE EXCEPTION 'receipt % was not produced by this replay', p_receipt
            USING ERRCODE = '23514';
    END IF;
    IF v_receipt.lane <> 'replay' THEN
        RAISE EXCEPTION 'receipt % is lane % and a Test run is performed in the replay Lane',
            p_receipt, v_receipt.lane USING ERRCODE = '23514';
    END IF;

    -- And the Receipt has to be the answer to the action it is being recorded
    -- as. Everything above it is satisfied by any Receipt this replay produced:
    -- a setup request, or the answer to a different action. An assertion names
    -- an action and is evaluated against whatever Receipt sits under it, so a
    -- run that could record action 3's answer as action 2 could produce a
    -- differential out of one exchange and a plan nobody wrote. The comparison
    -- is over what the plan states and the scope is stated over -- the method,
    -- the scheme, the host, the port and the path.
    SELECT * INTO v_route FROM rk2_test_route(v_action ->> 'url');
    IF v_receipt.method IS DISTINCT FROM upper(v_action ->> 'method')
       OR v_receipt.scheme IS DISTINCT FROM v_route.scheme
       OR v_receipt.host   IS DISTINCT FROM v_route.host
       OR v_receipt.port   IS DISTINCT FROM v_route.port
       OR v_receipt.path   IS DISTINCT FROM v_route.path THEN
        RAISE EXCEPTION
            'receipt % answers % %, and action % states % %',
            p_receipt, v_receipt.method,
            v_receipt.scheme || '://' || v_receipt.host || v_receipt.path,
            p_ordinal, upper(v_action ->> 'method'), v_action ->> 'url'
            USING ERRCODE = '23514';
    END IF;

    -- A Receipt the door refused records a request that never left, and it
    -- holds no digest of one. Refused here on what it is rather than on what it
    -- does not carry, so the message names the fault: the three comparisons
    -- below would otherwise report a missing request as a differing one.
    IF v_receipt.decision <> 'allowed' THEN
        RAISE EXCEPTION 'receipt % was % and a Test action is performed by a request that was sent',
            p_receipt, v_receipt.decision USING ERRCODE = '23514';
    END IF;

    -- The same question one level down, which the header and body a Test action
    -- may now state made askable and left unasked.
    -- Two actions to one route differing only in a query, a header block or a
    -- body are two arms, and the comparison above cannot tell them apart. Each
    -- axis is compared as a digest because a digest is what the Receipt holds:
    -- the door records no value for any of the three, so this is not a weaker
    -- comparison than the one available, it is the one available.
    v_query := rk2_test_query(v_action ->> 'url');
    IF v_receipt.query_sha256 IS DISTINCT FROM
           encode(sha256(convert_to(v_query, 'UTF8')), 'hex') THEN
        RAISE EXCEPTION 'receipt % answers a different query than action % states',
            p_receipt, p_ordinal USING ERRCODE = '23514';
    END IF;
    -- Ticket 220. A NULL on the Receipt's side is a fact about the door and not
    -- about the headers, and the two are told apart before the comparison is
    -- made. `rk2_planned_headers_sha256` is never NULL and says so in its own
    -- comment, so a Receipt holding no header digest can only be one the
    -- running door wrote without the column -- which is a door older than the
    -- release that added it, not a request that carried other headers.
    IF v_receipt.request_headers_sha256 IS NULL THEN
        RAISE EXCEPTION
            'receipt % carries no header digest; the door that wrote it predates '
            'the column, so restart the door and replay',
            p_receipt USING ERRCODE = '23514';
    END IF;
    IF v_receipt.request_headers_sha256 IS DISTINCT FROM
           rk2_planned_headers_sha256(v_action -> 'headers') THEN
        RAISE EXCEPTION 'receipt % carries different headers than action % states',
            p_receipt, p_ordinal USING ERRCODE = '23514';
    END IF;
    -- The body is the same fault with one difference: `rk2_planned_body_sha256`
    -- *is* NULL for a plan that states no body, and the door writes NULL for a
    -- request that carried none, so NULL against NULL is a match and never
    -- reaches this branch. What does reach it is a plan that states a body
    -- against a Receipt holding no digest of one, and that is the same old door.
    IF v_receipt.request_body_sha256 IS DISTINCT FROM
           rk2_planned_body_sha256(v_action -> 'body') THEN
        IF v_receipt.request_body_sha256 IS NULL THEN
            RAISE EXCEPTION
                'receipt % carries no body digest and action % states a body; the '
                'door that wrote it predates the column, so restart the door and replay',
                p_receipt, p_ordinal USING ERRCODE = '23514';
        END IF;
        RAISE EXCEPTION 'receipt % carries a different body than action % states',
            p_receipt, p_ordinal USING ERRCODE = '23514';
    END IF;

    SELECT NOT EXISTS (SELECT 1 FROM test_replay_actions a
                        WHERE a.tool_run_id = p_tool_run_id)
       AND NOT EXISTS (SELECT 1 FROM impact_replays i
                        WHERE i.tool_run_id = p_tool_run_id)
      INTO v_first;

    PERFORM set_actor('runtime');
    INSERT INTO test_replay_actions
        (tool_run_id, ordinal, program_id, role, receipt_id)
    VALUES (p_tool_run_id, p_ordinal, p, v_action ->> 'role', v_receipt.id);

    IF v_first THEN
        INSERT INTO hypothesis_transitions
            (program_id, hypothesis_id, from_status, to_status, actor_kind,
             agent_run_id, receipt_id, rationale)
        VALUES (p, v_test.hypothesis_id, 'testable', 'testing', 'runtime',
                v_run.agent_run_id, v_receipt.id,
                'the replay of ' || v_test.label || ' reached the target');
    END IF;

    RETURN jsonb_build_object(
        'tool_run', v_run.label,
        'ordinal', p_ordinal,
        'role', v_action ->> 'role',
        'receipt', p_receipt,
        'started_testing', v_first);
END $fn$;



COMMENT ON FUNCTION record_test_action(uuid, integer, text) IS
    'Tie one Receipt to one planned action, under the role the plan gave it, '
    'and move the claim to `testing` on the first one -- unless the run is an '
    'impact replay, which moves nothing about the Hypothesis. Refuses a Receipt '
    'from another Tool run, a Receipt outside the replay Lane, an ordinal this '
    'Test does not perform, and a Receipt that answers a different request than '
    'the action states -- route, query, headers and body, each on its own. A '
    'Receipt carrying no header or body digest at all is refused separately and '
    'names the door, because that is a writer older than the column rather than '
    'a request that carried something else.';
