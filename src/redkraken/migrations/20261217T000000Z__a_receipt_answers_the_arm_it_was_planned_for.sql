-- ---------------------------------------------------------------------------
-- 20261217T000000Z__a_receipt_answers_the_arm_it_was_planned_for.sql
--                                                                  (ticket 214)
--
-- 211 let a Test action plan a header block and a body, and decided in writing
-- that the Receipt comparison would stay at the route. That decision is taken
-- back here, in ticket 214, and the two reasons it gave are answered below
-- rather than dropped. Nothing checks that the
-- Receipt recorded for that action answered them. `record_test_action` compares
-- the method, the scheme, the host, the port and the path and stops there, and
-- its own comment says why the query is left out: only the digest is on the
-- Receipt. So two actions to one route differing only in a header, a body or a
-- query record each other's Receipts without a word. An assertion is evaluated
-- against whatever Receipt sits under its ordinal, which makes that a
-- differential built out of an exchange nobody planned -- the same hole 211
-- closed one level up, at the level 211 opened.
--
-- Three digests close it:
--
--   1. Three columns on `receipts`, written by the door.
--   2. Three functions that spell the same digest out of the plan.
--   3. `record_test_action` refuses when the two disagree.
--
-- The header digest carries a defaulting rule, and it is not decoration.
-- `http.client` appends `Accept-Encoding: identity` whenever the caller does
-- not name it: `HTTPConnection.putrequest` defaults `skip_accept_encoding` to
-- false, and `_send_request` sets it only for a caller that spells the header
-- itself. The door already knows this and says so beside `agent_headers`,
-- `src/redkraken/proxy.py:2939-2943`. A plan that does not name the header
-- therefore reaches the target carrying it, and a digest over the plan alone
-- could never match -- not once, for any request. So the plan side defaults the
-- same single name before it hashes. One name, not a list: every other header
-- on the wire was either stated by the plan or stripped by `forwardable`.
--
-- Which view is digested: the one the caller stated, before the Identity
-- injection (`src/redkraken/proxy.py:2951` copies `agent_headers` into
-- `wire_headers`, and the injection is at `:2992`). A leased Identity overwrites
-- `Cookie` and every name it carries, and the plan still said what it said.
-- These columns answer "which arm was this", not "what was on the wire"; the
-- wire picture is already `request_wire_sha`.
--
-- One case fails loudly rather than quietly, and that is the right direction: a
-- caller who sends a `Connection` header naming its own hop-by-hop additions
-- has those stripped by `forwardable` (`src/redkraken/proxy.py:643-651`), the
-- digest moves, and `record_test_action` refuses. A request the plan cannot
-- describe is a request no Test should record.
-- ---------------------------------------------------------------------------


-- ===========================================================================
-- 1. What the door records
-- ===========================================================================
--
-- `20260924T000000Z__a_request_may_carry_a_body.sql:12-17` refused a
-- `request_body_sha256` in writing, under the heading "WHAT THIS FILE DOES NOT
-- ADD, AND WHY IT SAYS SO": the body is already inside `request_agent_sha`,
-- and "two statements of one fact drift". That reasoning was right for the
-- question 96 was asking and does not answer this one. `request_agent_sha` is
-- the digest of the whole document -- start line, headers, blank line, body --
-- and a plan states the parts. There is no operation that turns three stated
-- parts into that one digest without rebuilding the exact bytes the door sent,
-- including the headers the door itself added. So the fact these columns state
-- is not the one 96 declined to restate: 96 asked "what did the door send",
-- and this file asks "is this Receipt the answer to the arm that was planned".
-- The drift 96 warned about is real and is what section 5 is for.
--
-- Nullable, and a null is not an empty value. For the two body columns it means
-- nothing was sent -- the separation `query_sha256` already makes, for the
-- reason its docstring gives (`src/redkraken/proxy.py:832-842`): a hash of the
-- empty string would make "no body" and "an empty body" one fact.
--
-- `request_headers_sha256` is the exception. After the defaulting above every
-- request carries at least one header, so the door never writes a null there.
-- The column is nullable anyway, because every Receipt written before this file
-- has none, and a null there means "written before this file" and not "sent no
-- headers".
--
-- `response_body_sha256` is written from the first row even though nothing
-- reads it yet. It is the answer's own digest, next to `response_agent_sha`
-- which is the digest of the whole message; a body-level differential needs the
-- body alone. Added now rather than later because a column added later is a
-- column null for every Receipt written in between, and there is no backfill
-- for bytes nobody kept.

ALTER TABLE receipts
    ADD COLUMN request_headers_sha256 text
        CHECK (request_headers_sha256 ~ '^[0-9a-f]{64}$'),
    ADD COLUMN request_body_sha256 text
        CHECK (request_body_sha256 ~ '^[0-9a-f]{64}$'),
    ADD COLUMN response_body_sha256 text
        CHECK (response_body_sha256 ~ '^[0-9a-f]{64}$');

COMMENT ON COLUMN receipts.request_headers_sha256 IS
    'SHA-256 over the headers the caller stated for this request, canonicalised as lowercase name, colon, space, value, newline, sorted by name in byte order, with `accept-encoding: identity` supplied when the caller named no `Accept-Encoding` -- because `http.client` supplies it on the wire. The view before the Identity injection: this answers which arm was performed, and `request_wire_sha` answers what was sent. NULL means the Receipt predates the column.';

COMMENT ON COLUMN receipts.request_body_sha256 IS
    'SHA-256 over the request body as sent, or NULL where there was no body. An empty body is a body and hashes to the digest of no bytes, the same separation `query_sha256` makes.';

COMMENT ON COLUMN receipts.response_body_sha256 IS
    'SHA-256 over the answer''s body alone, where `response_agent_sha` names the whole message. What a body-level differential is read against.';


-- ===========================================================================
-- 2. The same digests, spelled out of the plan
-- ===========================================================================
--
-- Three functions, one job: say what the door will have written, from the plan
-- alone. Immutable, because a plan is a document and the answer is a function
-- of it.

CREATE FUNCTION rk2_test_query(p_url text) RETURNS text
LANGUAGE sql IMMUTABLE AS $fn$
    SELECT nullif((regexp_match(p_url,
               '^https?://[^/:?#]+(?::[0-9]+)?[^?#]*\?([^#]*)'))[1], '')
$fn$;

COMMENT ON FUNCTION rk2_test_query(text) IS
    'The query string a planned url states, or NULL where it states none. The '
    'same parse `rk2_test_route` reads the route out of, continued past the '
    'first question mark; a url that does not parse answers NULL, which is what '
    'a Receipt with no query holds. An empty query is NULL and not the empty '
    'string, because the door writes NULL for it.';

-- The canonical form both sides spell. `COLLATE "C"` and not the database's
-- collation: the Python side sorts by codepoint, a locale collation folds
-- punctuation, and header names may carry a hyphen -- so `a-b` and `ab` sort
-- one way here and the other way there unless the order is stated in bytes.
-- The name is lowercased in the line as well as in the sort, because the case a
-- plan writes is not the case the client sends and 211 already refuses two
-- names differing only in case.
--
-- Never NULL. After the defaulting there is always at least one line, and a
-- NULL here would be a comparison that fails for every ordinary request.

CREATE FUNCTION rk2_planned_headers_sha256(p_headers jsonb) RETURNS text
LANGUAGE sql IMMUTABLE AS $fn$
    SELECT encode(sha256(convert_to(
               string_agg(h.name || ': ' || h.value || E'\n', ''
                          ORDER BY h.name COLLATE "C"), 'UTF8')), 'hex')
      FROM (SELECT lower(k) AS name, coalesce(p_headers, '{}'::jsonb) ->> k AS value
              FROM jsonb_object_keys(coalesce(p_headers, '{}'::jsonb)) k
             UNION ALL
            SELECT 'accept-encoding', 'identity'
             WHERE NOT EXISTS (SELECT 1
                                 FROM jsonb_object_keys(coalesce(p_headers, '{}'::jsonb)) k
                                WHERE lower(k) = 'accept-encoding')) h
$fn$;

COMMENT ON FUNCTION rk2_planned_headers_sha256(jsonb) IS
    'The digest the door will have written for a planned header block: '
    'lowercase name, colon, space, value, newline, sorted by name in byte '
    'order. A plan that names no `Accept-Encoding` is given `identity`, because '
    '`http.client` gives it one on the wire whether the plan asked or not. '
    'Never NULL, including for a plan with no headers at all. Kept in step with '
    '`stated_headers_sha256` in `src/redkraken/proxy.py`.';

CREATE FUNCTION rk2_planned_body_sha256(p_body jsonb) RETURNS text
LANGUAGE sql IMMUTABLE AS $fn$
    SELECT CASE WHEN jsonb_typeof(p_body) = 'string'
                THEN encode(sha256(convert_to(p_body #>> '{}', 'UTF8')), 'hex')
           END
$fn$;

COMMENT ON FUNCTION rk2_planned_body_sha256(jsonb) IS
    'The digest of the body a plan states, over its UTF-8 bytes, or NULL where '
    'the plan states none. A stated empty string is a body and hashes to the '
    'digest of no bytes.';


-- ===========================================================================
-- 3. The comparison
-- ===========================================================================
--
-- Verbatim from `20260816T000000Z` except for the declaration of `v_query` and
-- the three blocks after the route comparison, each naming the axis it refused
-- on so a failure reads as a fact and not as a puzzle.

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
    IF v_receipt.request_headers_sha256 IS DISTINCT FROM
           rk2_planned_headers_sha256(v_action -> 'headers') THEN
        RAISE EXCEPTION 'receipt % carries different headers than action % states',
            p_receipt, p_ordinal USING ERRCODE = '23514';
    END IF;
    IF v_receipt.request_body_sha256 IS DISTINCT FROM
           rk2_planned_body_sha256(v_action -> 'body') THEN
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
    'the action states -- route, query, headers and body, each on its own.';


-- ===========================================================================
-- 4. The writer
-- ===========================================================================
--
-- Verbatim from `20261117T000000Z` except for two things. The six lines that
-- carry the three new columns, placed beside `query_sha256` and
-- `response_content_type` because those are the columns they belong with to a
-- reader -- not because the row is ordered that way, since `ALTER TABLE` puts
-- them last. And the comment above the `lane` assignment, which opened "The one
-- changed line" and was true of that file and is not true of this one; the
-- reasoning it carried is restated below rather than dropped.
--
-- Only the allowed writer. Not because a blocked Receipt could not carry these
-- digests -- two of the refusal paths have the headers in hand
-- (`src/redkraken/proxy.py`, the `_exchange` refusal and the one after a
-- Receipt fails to write) -- but because `write_blocked_receipt`'s column list
-- was not extended, so every blocked Receipt holds three nulls. A blocked
-- Receipt of a replay run carries lane `replay` (`20261122T000000Z` derives it
-- from the Tool run), so it reaches the comparison in section 3, and a null
-- there would be reported as "carries different headers" for a request that
-- was never sent. Section 3 refuses it by decision instead, ahead of the three
-- digests.

CREATE OR REPLACE FUNCTION write_allowed_receipt(p_capability text, p_receipt jsonb)
RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public
AS $fn$
DECLARE
    v_auth          record;
    v_receipt       receipts%ROWTYPE;
    v_scope_version integer;
    v_id            uuid;
BEGIN
    IF p_capability IS NULL
       OR coalesce(jsonb_typeof(p_receipt), 'null') <> 'object' THEN
        RAISE EXCEPTION 'egress capability refused' USING ERRCODE = '23514';
    END IF;
    IF position(p_capability IN p_receipt::text) > 0 THEN
        RAISE EXCEPTION 'receipt payload contains protected capability'
            USING ERRCODE = '23514';
    END IF;

    SELECT * INTO v_auth FROM resolve_egress_capability(p_capability);
    IF NOT FOUND THEN
        RAISE EXCEPTION 'egress capability refused' USING ERRCODE = '23514';
    END IF;
    SELECT scope_version INTO v_scope_version
      FROM programs WHERE id = v_auth.program_id;

    v_receipt := jsonb_populate_record(NULL::receipts, p_receipt);
    v_receipt.id := uuidv7();
    v_receipt.program_id := v_auth.program_id;
    v_receipt.label := '';
    v_receipt.tool_run_id := v_auth.tool_run_id;
    -- `agent` was correct while the only holder of a capability was a
    -- subagent; a replay holds one too, and which of them is acting is a fact
    -- about the Tool run rather than about this call. Carried from
    -- `20261117T000000Z`, where it was the one changed line.
    v_receipt.lane := rk2_capability_lane(v_auth.tool_run_id);
    v_receipt.decision := 'allowed';
    v_receipt.scope_version := v_scope_version;
    v_receipt.ts_arrival := coalesce(v_receipt.ts_arrival, clock_timestamp());
    v_receipt.intercepted := coalesce(v_receipt.intercepted, true);

    PERFORM set_actor('runtime');
    INSERT INTO receipts (
        id, program_id, label, tool_run_id, lane, decision, reason,
        identity_entity_id, identity_tls_cert_sha256,
        method, scheme, host, port, path, query_sha256,
        request_headers_sha256, request_body_sha256,
        pinned_ips, status_code, response_content_type, response_body_sha256,
        ts_arrival, ts_egress, waited_ms,
        request_agent_sha, request_wire_sha, response_agent_sha,
        response_wire_sha, notes, scope_version, scope_class, intercepted,
        alpn_pin_mode, agent_tls_version, agent_cipher, agent_alpn,
        agent_cert_sha256, agent_cert_issuer, agent_cert_subject,
        agent_cert_not_after, wire_tls_version, wire_cipher, wire_alpn,
        wire_cert_sha256, wire_cert_issuer, wire_cert_subject,
        wire_cert_not_after, wire_sni, wire_chain_verified,
        wire_hostname_verified, interception_ca_id
    ) VALUES (
        v_receipt.id, v_receipt.program_id, v_receipt.label,
        v_receipt.tool_run_id, v_receipt.lane, v_receipt.decision,
        v_receipt.reason, v_receipt.identity_entity_id,
        v_receipt.identity_tls_cert_sha256, v_receipt.method,
        v_receipt.scheme, v_receipt.host, v_receipt.port, v_receipt.path,
        v_receipt.query_sha256,
        v_receipt.request_headers_sha256, v_receipt.request_body_sha256,
        v_receipt.pinned_ips, v_receipt.status_code,
        v_receipt.response_content_type, v_receipt.response_body_sha256,
        v_receipt.ts_arrival, v_receipt.ts_egress, v_receipt.waited_ms,
        v_receipt.request_agent_sha, v_receipt.request_wire_sha,
        v_receipt.response_agent_sha, v_receipt.response_wire_sha,
        v_receipt.notes, v_receipt.scope_version, v_receipt.scope_class,
        v_receipt.intercepted, v_receipt.alpn_pin_mode,
        v_receipt.agent_tls_version, v_receipt.agent_cipher,
        v_receipt.agent_alpn, v_receipt.agent_cert_sha256,
        v_receipt.agent_cert_issuer, v_receipt.agent_cert_subject,
        v_receipt.agent_cert_not_after, v_receipt.wire_tls_version,
        v_receipt.wire_cipher, v_receipt.wire_alpn,
        v_receipt.wire_cert_sha256, v_receipt.wire_cert_issuer,
        v_receipt.wire_cert_subject, v_receipt.wire_cert_not_after,
        v_receipt.wire_sni, v_receipt.wire_chain_verified,
        v_receipt.wire_hostname_verified, v_receipt.interception_ca_id
    )
    RETURNING id INTO v_id;
    RETURN v_id;
END $fn$;


-- ===========================================================================
-- 5. What has to hold afterwards
-- ===========================================================================
--
-- `jsonb_populate_record` fills a new column without being told, and the INSERT
-- below it does not: a column missing from the explicit list is written as null
-- for every row and nothing raises. That is the failure this block exists to
-- catch, and it is the same one `20261117T000000Z:257-269` catches for
-- `response_content_type`.

DO $$
DECLARE c text; d text; n integer;
BEGIN
    d := pg_get_functiondef('write_allowed_receipt(text, jsonb)'::regprocedure);
    FOREACH c IN ARRAY ARRAY['request_headers_sha256', 'request_body_sha256',
                             'response_body_sha256'] LOOP
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                        WHERE table_schema = 'public' AND table_name = 'receipts'
                          AND column_name = c) THEN
            RAISE EXCEPTION 'receipts.% was not added', c;
        END IF;
        -- Twice, not once. A correct writer names the column in the list and
        -- again as `v_receipt.<column>` in the VALUES, and the failure this
        -- block exists for -- a column carried by one of the two, or written as
        -- a literal null -- passes any check that only asks whether the name
        -- appears at all.
        IF (length(d) - length(replace(d, c, ''))) / length(c) < 2 THEN
            RAISE EXCEPTION 'write_allowed_receipt names % once, not in both lists', c;
        END IF;
    END LOOP;

    -- And the reader asks for all three. A comparison that compiled without one
    -- of them is the hole this file was written to close, still open.
    d := pg_get_functiondef('record_test_action(uuid, integer, text)'::regprocedure);
    FOREACH c IN ARRAY ARRAY['rk2_test_query', 'rk2_planned_headers_sha256',
                             'rk2_planned_body_sha256'] LOOP
        IF position(c IN d) = 0 THEN
            RAISE EXCEPTION 'record_test_action does not compare %', c;
        END IF;
    END LOOP;
    IF position('v_receipt.decision <> ''allowed''' IN d) = 0 THEN
        RAISE EXCEPTION 'record_test_action does not refuse a receipt the door blocked';
    END IF;

    -- The canonical form, pinned to the bytes and not only to itself. Two
    -- spellings compared against each other can be wrong together; these
    -- digests are the third party, and `stated_headers_sha256` in
    -- `src/redkraken/proxy.py` is held against the same two in
    -- `tests/test_proxy.py`.
    IF rk2_planned_headers_sha256(NULL) IS DISTINCT FROM
       '8ec3bcd85980cc3dcccf76a2d027942d57b412a3685a420eaa76adb0069aefa2' THEN
        RAISE EXCEPTION 'a plan with no headers is not one accept-encoding line';
    END IF;
    IF rk2_planned_headers_sha256('{"Accept-Encoding": "identity"}'::jsonb)
       IS DISTINCT FROM rk2_planned_headers_sha256(NULL) THEN
        RAISE EXCEPTION 'the accept-encoding default is not the header itself';
    END IF;
    IF rk2_planned_headers_sha256('{"Accept-Encoding": "gzip"}'::jsonb) IS DISTINCT FROM
       '46e1727a2350e8e270b7f132190e1b80314c73cfee55549c7cc2fb24d3885dd9' THEN
        RAISE EXCEPTION 'a stated accept-encoding did not suppress the default';
    END IF;

    -- Absence and emptiness stay two facts, on both of the axes that have one.
    IF rk2_planned_body_sha256(NULL) IS NOT NULL THEN
        RAISE EXCEPTION 'an absent body was given a digest';
    END IF;
    IF rk2_planned_body_sha256('""'::jsonb) IS DISTINCT FROM
       'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855' THEN
        RAISE EXCEPTION 'an empty body is not the digest of no bytes';
    END IF;
    IF rk2_test_query('https://app.example.com/a') IS NOT NULL
       OR rk2_test_query('https://app.example.com/a?') IS NOT NULL
       OR rk2_test_query('https://app.example.com/a?b=1') IS DISTINCT FROM 'b=1'
       OR rk2_test_query('https://app.example.com/a?b=1&c=2') IS DISTINCT FROM 'b=1&c=2'
       OR rk2_test_query('https://app.example.com:8443/a?b=1') IS DISTINCT FROM 'b=1'
       OR rk2_test_query('https://app.example.com/a#b?c=1') IS NOT NULL THEN
        RAISE EXCEPTION 'rk2_test_query does not read a query the way the door does';
    END IF;

    -- One immutable function per name, in this schema. Counted by name rather
    -- than in total, because three overloads of one of them and none of the
    -- other two is also three rows.
    FOREACH c IN ARRAY ARRAY['rk2_test_query', 'rk2_planned_headers_sha256',
                             'rk2_planned_body_sha256'] LOOP
        SELECT count(*) INTO n FROM pg_proc
         WHERE proname = c AND provolatile = 'i'
           AND pronamespace = 'public'::regnamespace;
        IF n <> 1 THEN
            RAISE EXCEPTION '% is not one immutable function of this schema', c;
        END IF;
    END LOOP;
END $$;
