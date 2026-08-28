-- ---------------------------------------------------------------------------
-- 20261216T000000Z__a_test_action_carries_the_header_and_the_body_it_plans.sql
--                                                                  (ticket 211)
--
-- A Test action states a method and a url and nothing else, so a reading whose
-- differential lives in a header or in a document -- a GraphQL selection, a
-- gRPC frame, an XML body, a JSON filter -- cannot be planned as a Test. It can
-- only be filed as an Observation, and an Observation never reaches a Finding:
-- `rk2_finding_refusal` wants a `hypothesis_transitions` row, only
-- `close_test_replay` writes one, and its `to_status` comes from the Test's own
-- assertions. Measured against the corpus ticket 101 is rewriting, 130 of 268
-- reachable techniques stop there. This file is why they do not have to.
--
-- Three changes, and the third is the one that is easy to miss.
--
--   1. `rk2_test_request_problem` learns to grade a header block and a body.
--      It is the right place because its own COMMENT already says so: "Key sets
--      are the caller's business because an action carries three more keys than
--      a setup step does". Values are this function's business, and these are
--      values.
--
--   2. `rk2_test_spec_problem` widens the key set an action may carry, from
--      ('ordinal', 'role', 'kind', 'method', 'url') to those five plus
--      'headers' and 'body'. Setup and cleanup stay at ('method', 'url'): a
--      step that prepares or undoes a Test is not where a differential lives,
--      and widening it would be a decision this ticket has no business taking.
--
--   3. `rk2_open_replay` declares `body_allowed` on the Tool run it opens.
--      Without this the first two changes send nothing: `authorize_egress_request`
--      refuses a body from every tool but the browser unless the Tool run's args
--      say it may carry one, and the replay lane's args have never said anything
--      on the subject. The value is read off the spec, exactly as `methods` is,
--      so the Tool run declares what the plan will do rather than what its
--      Playbooks are allowed to do.
--
-- On that third point, and on ticket 96's rule specifically. `body_allowed` is
-- computed for the agent's Tool run from the selected Playbooks in
-- `execution.py`. A request body is framing and not, by itself, a mutating
-- effect: read-only GraphQL and JSON-filter requests need one too. The reason
-- ticket 96 gave for binding it -- "a
-- Tool run opened to carry a body chooses its bytes after the row was written"
-- -- is a statement about a model's argument, and it is not true of a Test: the
-- bytes are in the spec, the spec is digested into `tests.spec_sha256`, that
-- digest is on the Tool run's args, and `rk2_test_spec_problem` and the risk
-- gate both read it before a capability exists. So the replay lane is not
-- claiming ticket 96's exemption; it is a lane the rule was never measuring.
-- Nothing in the agent lane widens, and no Playbook changes its `bb:effects`.
--
-- `canonical_request` is not touched. It short-circuits for every tool that is
-- not `mcp__rk2__net_request`, and that arm already returns `reusable: false`,
-- so a replay Tool run's approval key covers one call whether or not it carries
-- a body. The new key lands in that arm's `arg_names` list, which is the honest
-- place for it: the approval document says this run was opened body-bearing.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION rk2_test_request_problem(p_request jsonb, p_position text)
RETURNS text
LANGUAGE plpgsql IMMUTABLE AS $fn$
DECLARE
    v_url     text := p_request ->> 'url';
    v_headers jsonb := p_request -> 'headers';
    v_name    text;
    v_value   text;
BEGIN
    IF upper(coalesce(p_request ->> 'method', '')) NOT IN
       ('GET', 'HEAD', 'OPTIONS', 'POST', 'PUT', 'PATCH', 'DELETE') THEN
        RETURN p_position || ' states no method this runtime sends';
    END IF;
    IF p_request ->> 'method' <> upper(p_request ->> 'method') THEN
        -- The method is part of the digest, so one spelling of it. A plan
        -- carrying `get` would digest differently from the same plan carrying
        -- `GET` and would describe the same request.
        RETURN p_position || ' states its method in lower case';
    END IF;
    IF v_url IS NULL
       OR v_url !~ '^https?://[a-z0-9.-]+(:[0-9]{1,5})?(/[^\s]*)?$' THEN
        RETURN p_position || ' states no absolute http or https url in canonical form';
    END IF;
    IF length(v_url) > 2000 THEN
        RETURN p_position || ' states a url longer than a url may be';
    END IF;
    -- A path this file resolves one way and the door resolves another is a
    -- request nobody planned: `/public/../admin` is scope-classed as `/public/`
    -- when the plan is checked and reaches `/admin` when it is sent. The scope
    -- is stated over paths, so one spelling of a path, and it is the resolved
    -- one. `%2e` goes with it because a dot the door decodes is a dot.
    IF split_part(regexp_replace(v_url, '^https?://[^/]*', ''), '?', 1)
           ~ '(^|/)\.\.?(/|$)'
       OR v_url ~* '%2e' THEN
        RETURN p_position || ' states a path that resolves somewhere else';
    END IF;

    -- Ticket 211. Absent is the ordinary case and is not an error: a setup step
    -- may not carry either key at all, and most actions carry neither.
    -- `jsonb_typeof` of a key that is not there is SQL NULL, which is how
    -- absence is told apart from a stated JSON null.
    IF jsonb_typeof(v_headers) IS NOT NULL THEN
        IF jsonb_typeof(v_headers) <> 'object' THEN
            RETURN p_position || ' states headers that are not an object';
        END IF;
        -- Two names differing only in case are two keys in JSON and one header
        -- on the wire. Which value survives is the client library's business
        -- and not this plan's, so the plan is refused rather than resolved.
        IF (SELECT count(DISTINCT lower(k)) FROM jsonb_object_keys(v_headers) k)
           <> (SELECT count(*) FROM jsonb_object_keys(v_headers) k) THEN
            RETURN p_position || ' states one header name twice in two cases';
        END IF;
        FOR v_name IN SELECT jsonb_object_keys(v_headers) LOOP
            IF v_name !~ '^[A-Za-z][A-Za-z0-9-]{0,63}$' THEN
                RETURN p_position || ' states no header name in ' || v_name;
            END IF;
            -- The eleven the door strips, spelled here because a plan naming
            -- one describes a request that is not the request sent. Kept in
            -- step with `HOP_BY_HOP` in `src/redkraken/proxy.py`; a name added
            -- there is added here. `content-length` is among them, so a body's
            -- length is the door's arithmetic and never the plan's claim.
            IF lower(v_name) IN ('connection', 'content-length', 'host',
                                 'keep-alive', 'proxy-authenticate',
                                 'proxy-authorization', 'proxy-connection',
                                 'te', 'trailer', 'transfer-encoding',
                                 'upgrade') THEN
                RETURN p_position || ' states ' || v_name
                       || ', which the door owns and would strip';
            END IF;
            -- The control prefix. A plan writing one would be describing a
            -- request whose provenance the door states, and the door states it.
            IF lower(v_name) LIKE 'x-redkraken-%' THEN
                RETURN p_position || ' states ' || v_name
                       || ', which is reserved for the door';
            END IF;
            IF jsonb_typeof(v_headers -> v_name) <> 'string' THEN
                RETURN p_position || ' states a value for ' || v_name
                       || ' that is not a string';
            END IF;
            v_value := v_headers ->> v_name;
            -- Printable ASCII and nothing else. A carriage return or a newline
            -- in a value is header injection, and this is the position where
            -- the request is still a document rather than bytes.
            IF v_value !~ '^[ -~]*$' THEN
                RETURN p_position || ' states a value for ' || v_name
                       || ' that is not printable ascii';
            END IF;
            -- Stated as a length rather than in the pattern because this
            -- engine refuses a repetition count above 255.
            IF length(v_value) > 1024 THEN
                RETURN p_position || ' states a value for ' || v_name
                       || ' longer than a header value may be';
            END IF;
        END LOOP;
    END IF;

    IF jsonb_typeof(p_request -> 'body') IS NOT NULL THEN
        IF jsonb_typeof(p_request -> 'body') <> 'string' THEN
            RETURN p_position || ' states a body that is not a string';
        END IF;
        -- Characters and not bytes. What the door sends is this string encoded
        -- as UTF-8, so the byte count can exceed this one; the bound is on what
        -- a plan may state, which is the thing a reader of the plan sees.
        IF length(p_request ->> 'body') > 65536 THEN
            RETURN p_position || ' states a body longer than a body may be';
        END IF;
    END IF;

    RETURN NULL;
END $fn$;

COMMENT ON FUNCTION rk2_test_request_problem(jsonb, text) IS
    'The values every request in a specification carries, checked the same way '
    'wherever one appears: the method and the url as before, and now the header '
    'block and the body an action may plan. Header names outside the set the '
    'door owns, values that cannot inject a second header, and a body inside '
    'its bound. Key sets are the caller''s business because an action carries '
    'five more keys than a setup step does.';

CREATE OR REPLACE FUNCTION rk2_test_spec_problem(p_spec jsonb) RETURNS text
LANGUAGE plpgsql IMMUTABLE AS $fn$
DECLARE
    v_parts    text[] := ARRAY['preconditions', 'setup', 'actions',
                               'assertions', 'cleanup'];
    v_part     text;
    v_key      text;
    v_item     jsonb;
    v_problem  text;
    v_actions  integer;
    v_index    integer;
    v_role     text;
    v_ids      text[] := '{}';
    v_id       text;
    v_kind     text;
    v_action   integer;
    v_against  integer;
BEGIN
    IF jsonb_typeof(p_spec) <> 'object' THEN
        RETURN 'the specification is not an object';
    END IF;

    FOR v_key IN SELECT jsonb_object_keys(p_spec) LOOP
        -- `impact` and `pivot` are stated, not performed, so neither is one of
        -- the parts the loop below requires to be an array.
        IF NOT (v_key = ANY (v_parts)) AND v_key NOT IN ('impact', 'pivot') THEN
            RETURN 'the specification carries no part named ' || v_key;
        END IF;
    END LOOP;

    FOREACH v_part IN ARRAY v_parts LOOP
        IF jsonb_typeof(p_spec -> v_part) IS DISTINCT FROM 'array' THEN
            RETURN 'the ' || v_part || ' of a Test are an array';
        END IF;
    END LOOP;

    -- Preconditions are stated, not performed: what has to be true before the
    -- run is worth starting. They are prose under a typed word rather than a
    -- predicate the runtime evaluates, because the four things the runtime can
    -- decide -- scope, risk, the Identity lease, the budget -- it decides in
    -- `open_test_replay` against canonical state, and a second copy stated in
    -- the specification would be a second answer.
    IF jsonb_array_length(p_spec -> 'preconditions') > 16 THEN
        RETURN 'a Test states at most 16 preconditions';
    END IF;
    v_index := 0;
    FOR v_item IN SELECT * FROM jsonb_array_elements(p_spec -> 'preconditions') LOOP
        v_index := v_index + 1;
        IF jsonb_typeof(v_item) <> 'object' THEN
            RETURN 'precondition ' || v_index || ' is not an object';
        END IF;
        FOR v_key IN SELECT jsonb_object_keys(v_item) LOOP
            IF v_key NOT IN ('kind', 'detail') THEN
                RETURN 'precondition ' || v_index || ' carries no key named ' || v_key;
            END IF;
        END LOOP;
        IF NOT (coalesce(v_item ->> 'kind', '')
                  = ANY (rk2_test_precondition_kinds())) THEN
            RETURN 'precondition ' || v_index
                   || ' states no kind a precondition may have';
        END IF;
        IF coalesce(v_item ->> 'detail', '') = ''
           OR length(v_item ->> 'detail') > 500 THEN
            RETURN 'precondition ' || v_index || ' states no detail';
        END IF;
    END LOOP;

    -- Setup and cleanup are requests the run makes and no assertion may name.
    -- They carry no role for that reason: a role is what makes an action
    -- evidence, and neither of these is evidence about the target.
    FOREACH v_part IN ARRAY ARRAY['setup', 'cleanup'] LOOP
        IF jsonb_array_length(p_spec -> v_part) > 16 THEN
            RETURN 'a Test performs at most 16 ' || v_part || ' requests';
        END IF;
        v_index := 0;
        FOR v_item IN SELECT * FROM jsonb_array_elements(p_spec -> v_part) LOOP
            v_index := v_index + 1;
            IF jsonb_typeof(v_item) <> 'object' THEN
                RETURN v_part || ' request ' || v_index || ' is not an object';
            END IF;
            FOR v_key IN SELECT jsonb_object_keys(v_item) LOOP
                IF v_key NOT IN ('method', 'url') THEN
                    RETURN v_part || ' request ' || v_index
                           || ' carries no key named ' || v_key;
                END IF;
            END LOOP;
            v_problem := rk2_test_request_problem(
                v_item, v_part || ' request ' || v_index);
            IF v_problem IS NOT NULL THEN
                RETURN v_problem;
            END IF;
        END LOOP;
    END LOOP;

    v_actions := jsonb_array_length(p_spec -> 'actions');
    IF v_actions < 3 OR v_actions > 32 THEN
        -- Three is the floor because it follows from the rule below it rather
        -- than standing on its own: 035 asks for "one immutable Test
        -- specification with baseline, variant and control actions", so a Test
        -- carries all three roles and cannot do that in fewer than three
        -- actions. What that rules out is the Test with no control -- a
        -- baseline and a variant that differ, with nothing to say the target
        -- would not have differed anyway.
        RETURN 'a Test performs between 3 and 32 actions';
    END IF;
    v_index := 0;
    FOR v_item IN SELECT * FROM jsonb_array_elements(p_spec -> 'actions') LOOP
        v_index := v_index + 1;
        IF jsonb_typeof(v_item) <> 'object' THEN
            RETURN 'action ' || v_index || ' is not an object';
        END IF;
        FOR v_key IN SELECT jsonb_object_keys(v_item) LOOP
            IF v_key NOT IN ('ordinal', 'role', 'kind', 'method', 'url',
                             'headers', 'body') THEN
                RETURN 'action ' || v_index || ' carries no key named ' || v_key;
            END IF;
        END LOOP;
        IF jsonb_typeof(v_item -> 'ordinal') IS DISTINCT FROM 'number'
           OR (v_item ->> 'ordinal')::numeric IS DISTINCT FROM v_index::numeric THEN
            RETURN 'action ' || v_index || ' is not numbered ' || v_index;
        END IF;
        IF NOT (coalesce(v_item ->> 'role', '') = ANY (rk2_test_roles())) THEN
            RETURN 'action ' || v_index || ' carries no role a Test action may have';
        END IF;
        IF coalesce(v_item ->> 'kind', '') <> 'request' THEN
            RETURN 'action ' || v_index || ' is not a request, which is the '
                   'only kind of action this runtime performs';
        END IF;
        v_problem := rk2_test_request_problem(v_item, 'action ' || v_index);
        IF v_problem IS NOT NULL THEN
            RETURN v_problem;
        END IF;
    END LOOP;

    FOREACH v_role IN ARRAY rk2_test_roles() LOOP
        IF NOT EXISTS (
            SELECT 1 FROM jsonb_array_elements(p_spec -> 'actions') a
             WHERE a ->> 'role' = v_role) THEN
            RETURN 'a Test performs at least one ' || v_role || ' action';
        END IF;
    END LOOP;

    IF jsonb_array_length(p_spec -> 'assertions') NOT BETWEEN 1 AND 32 THEN
        RETURN 'a Test states between 1 and 32 assertions';
    END IF;
    v_index := 0;
    FOR v_item IN SELECT * FROM jsonb_array_elements(p_spec -> 'assertions') LOOP
        v_index := v_index + 1;
        IF jsonb_typeof(v_item) <> 'object' THEN
            RETURN 'assertion ' || v_index || ' is not an object';
        END IF;
        FOR v_key IN SELECT jsonb_object_keys(v_item) LOOP
            IF v_key NOT IN ('id', 'kind', 'action', 'against', 'status') THEN
                RETURN 'assertion ' || v_index || ' carries no key named ' || v_key;
            END IF;
        END LOOP;

        v_id := coalesce(v_item ->> 'id', '');
        IF v_id !~ '^[a-z][a-z0-9-]{2,62}$' THEN
            RETURN 'assertion ' || v_index || ' states no identifier';
        END IF;
        IF v_id = ANY (v_ids) THEN
            -- Criterion 5 reports failed assertions by identifier, so two
            -- assertions sharing one would report a failure nobody can locate.
            RETURN 'two assertions are identified as ' || v_id;
        END IF;
        v_ids := array_append(v_ids, v_id);

        v_kind := coalesce(v_item ->> 'kind', '');
        IF NOT (v_kind = ANY (rk2_test_assertion_kinds())) THEN
            RETURN 'assertion ' || v_id || ' states no kind this runtime evaluates';
        END IF;

        IF jsonb_typeof(v_item -> 'action') IS DISTINCT FROM 'number' THEN
            RETURN 'assertion ' || v_id || ' names no action';
        END IF;
        v_action := (v_item ->> 'action')::numeric::integer;
        IF v_action NOT BETWEEN 1 AND v_actions THEN
            RETURN 'assertion ' || v_id || ' names action ' || v_action
                   || ', which this Test does not perform';
        END IF;

        IF v_kind = 'status_equals' THEN
            IF v_item ? 'against' THEN
                RETURN 'assertion ' || v_id || ' compares against an action '
                       'and states a status as well';
            END IF;
            IF jsonb_typeof(v_item -> 'status') IS DISTINCT FROM 'number'
               OR (v_item ->> 'status')::numeric::integer NOT BETWEEN 100 AND 599 THEN
                RETURN 'assertion ' || v_id || ' states no status in 100-599';
            END IF;
        ELSE
            IF v_item ? 'status' THEN
                RETURN 'assertion ' || v_id || ' states a status and compares '
                       'two actions as well';
            END IF;
            IF jsonb_typeof(v_item -> 'against') IS DISTINCT FROM 'number' THEN
                RETURN 'assertion ' || v_id || ' names no action to compare against';
            END IF;
            v_against := (v_item ->> 'against')::numeric::integer;
            IF v_against NOT BETWEEN 1 AND v_actions THEN
                RETURN 'assertion ' || v_id || ' compares against action '
                       || v_against || ', which this Test does not perform';
            END IF;
            IF v_against = v_action THEN
                RETURN 'assertion ' || v_id || ' compares action ' || v_action
                       || ' against itself';
            END IF;
        END IF;
    END LOOP;

    RETURN rk2_impact_problem(p_spec);
END $fn$;

CREATE OR REPLACE FUNCTION rk2_open_replay(p_program uuid, p_run agent_runs,
                                           p_test tests,
                                           p_identity_slot text,
                                           p_methods text[])
RETURNS uuid
LANGUAGE plpgsql AS $fn$
DECLARE v_id uuid;
BEGIN
    PERFORM set_actor('runtime');
    INSERT INTO tool_runs
        (program_id, agent_run_id, task_id, tool, args, status, transport)
    VALUES
        (p_program, p_run.id, p_run.task_id, rk2_replay_tool(),
         jsonb_build_object('identity_slot', p_identity_slot,
                            'methods', to_jsonb(p_methods),
                            'test', p_test.label,
                            'spec_sha256', p_test.spec_sha256,
                            -- Ticket 211. Read off the spec exactly as
                            -- `methods` is, so the Tool run declares what this
                            -- plan will do. `authorize_egress_request` refuses
                            -- a body from every tool but the browser unless the
                            -- args say one may be carried, and until now these
                            -- args said nothing, which that gate reads as no.
                            'body_allowed',
                            EXISTS (SELECT 1
                                      FROM jsonb_array_elements(
                                               p_test.spec -> 'actions') a
                                     WHERE jsonb_typeof(a -> 'body') = 'string')),
         'running', 'runtime')
    RETURNING id INTO v_id;

    -- Before the gate, and that ordering is the whole of 035's criterion 3: the
    -- row that makes this Tool run a replay has to exist by the time a
    -- capability does, or the first Receipt would be written into the agent
    -- Lane. Ticket 38's `impact_replays` row is inserted by its caller for the
    -- same reason and in the same window.
    INSERT INTO test_replays (tool_run_id, program_id, test_id, spec_sha256)
    VALUES (v_id, p_program, p_test.id, p_test.spec_sha256);

    RETURN v_id;
END $fn$;

COMMENT ON FUNCTION rk2_open_replay(uuid, agent_runs, tests, text, text[]) IS
  'Ticket 35 steps i-j, ticket 38 extraction, ticket 211 addition: the Tool run and the row that makes it a replay, both before any capability exists. The args declare what the plan will do -- its Identity slot, its distinct methods, and whether any of its actions states a body -- rather than what its Playbooks are allowed to do, because the spec is written down and digested before the risk gate reads it. The caller mints the capability once every row that must precede it has been written.';
