-- ---------------------------------------------------------------------------
-- 20260924T000000Z__a_request_may_carry_a_body.sql
--                                                                   (ticket 96)
--
-- `mcp__rk2__http_request` grows a `body`, and two of the three rules a body
-- needs live here because the schema is the only place they can live: the door
-- is the party that cannot be talked out of a decision, and the approval digest
-- is the document a person actually answers about.
--
-- WHAT THIS FILE DOES NOT ADD, AND WHY IT SAYS SO.
--
-- No column. `receipts` has carried `request_agent_sha` and `request_wire_sha`
-- since 005, `transcript` is the start line, the headers and the body
-- concatenated, and `sent` and `wire_sent` are built from it -- so the bytes of
-- a request body have been inside the hashes a Receipt already names since
-- before there was a body to put there. A `request_body_sha256` would be a
-- second hash of bytes already hashed, and two statements of one fact drift.
--
-- RULE ONE: PERMISSION IS DECIDED AT OPEN AND ENFORCED AT THE DOOR.
--
-- A request may carry a body only if the Tool run that authorized it was opened
-- as body-bearing, and it is opened as body-bearing only when the Playbooks
-- selected for its Task declare `bb:effects` above `read_only`. The runtime
-- writes that answer into `tool_runs.args` beside `url` and `method`, which is
-- where the risk class is computed and where a human is asked, and this file is
-- where it binds: `authorize_egress_request` refuses a body the Tool run was not
-- opened for, beside the method binding it mirrors, and the door files a blocked
-- Receipt for it like every other refusal.
--
-- The parameter goes onto the existing decision rather than into a decision of
-- its own, and that is the one shape question this rule had. A second verb the
-- door calls when it happens to have a body is a verb a door with a bug does not
-- call, and the difference between a check and a suggestion is whether skipping
-- it is possible. `authorize_egress_address` is separate for a reason that does
-- not apply here -- the address does not exist until the name has been resolved
-- -- while a body is on the socket before anything is decided.
--
-- Changing the arity costs two DROP/CREATE pairs, two grants, one row of
-- `runtime_verb_surface` and the two signature literals in
-- `check_capability_receipt_fence`. All of it is bookkeeping that follows a
-- signature, and it is written out rather than avoided.
--
-- RULE TWO: AN APPROVAL COVERS ONE BODY-BEARING TASK, BECAUSE THE DIGEST
-- CANNOT SEE THE BYTES.
--
-- `canonical_request` derives `body_keys` only from an object body and sets
-- `reusable: true` for this tool, so two entirely different string bodies to one
-- path template have shared one `equivalence_key` and one human approval would
-- have covered both. Ticket 96 offers two ways out: put `body_sha256` in the
-- digest, or make a call with a non-object body `reusable: false`.
--
-- The first is not available in this system, and the reason is worth writing
-- down rather than discovering later. The digest is built from `tool_runs.args`
-- -- `current_request_digest` reads that column and nothing else -- and the args
-- are written when the Tool run is opened, before the child that will choose the
-- bytes exists. The door cannot add them afterwards: it holds no INSERT and no
-- UPDATE on `tool_runs`, which is ticket 66's split and a good one. So a
-- `body_sha256` here would be the digest of a key that is never present, one
-- constant for every bodied call, separating nothing while reading as though it
-- separated everything. That is a worse defect than the one it would be closing.
--
-- So: A TOOL RUN OPENED AS BODY-BEARING IS `reusable: false`. Its key carries the
-- nonce the non-canonicalisable tools already get, and the grant lookup in
-- `gate_tool_call` therefore cannot match anything the operator was not asked
-- about. One human approval covers one Task.
--
-- ONE TASK, and not one Tool run, and that is a correction rather than a
-- softening. The obvious spelling is the Tool run's own label, which is what
-- `current_request_digest` has always passed as the nonce, and it does not work
-- here: `park_for_human` closes the Tool run it filed the question about -- its
-- own comment says "parked, terminal, and it never resumes" -- and the Task the
-- operator releases is claimed again as a NEW Tool run with a new label. A key
-- built on the old label is a key no later attempt can compute, so the operator
-- would approve, the work would resume, the gate would ask the same question
-- again, and an approved body-bearing Task would never run. The Task is what the
-- answer is actually about: stable across the attempts of one Task, different
-- for every other Task, which is exactly the reuse this rule set out to stop. So
-- section 5 changes the nonce for this one case and leaves every other tool's
-- alone.
--
-- What that does not buy, said out loud: a child may call `http_request` many
-- times inside the one Tool run an approval released, and every body it sends is
-- covered by that approval. That is the granularity the control surface has for
-- everything else too -- two query strings and two paths under one template share
-- an approval the same way -- and narrowing it further means the bytes reaching
-- the digest, which means the door writing `tool_runs`.
--
-- The whole net_request document is kept rather than swapped for the
-- non-canonicalisable shape, deliberately. `net_unsafe_method`,
-- `net_host_out_of_scope` and `net_borrowed_identity` read `method`,
-- `host_in_scope` and `identity_slot` out of the digest, and `host_in_scope` is
-- stamped by `current_request_digest` only when the digest carries a `host`. A
-- bodied call answered with the four-key shape would silently stop all three
-- rules firing, which is the failure `risk_fact_not_in_digest` exists to catch
-- and would not have caught, because the facts would still be emitted for the
-- probe it asks with.
--
-- The third rule -- that the agent-visible request Artifact is scrubbed against
-- the bound session's secrets -- is in `proxy.py`, because it is about bytes
-- this process holds and never sends to the database.
--
-- Depends on 0026 (the digest and the equivalence key), 20260810T214500Z (the
-- capability fence), 20260811T150000Z (the Identity arm), 20260814T040000Z and
-- 20260815T000000Z (the browser and replay arms of the authorizer, whose body is
-- carried forward here unchanged apart from the new binding) and 20260914T000000Z
-- (the fence check this rewrites the signatures in). A new file rather than an
-- edit to any of them: a recorded migration whose file has changed is schema
-- drift and `rk db migrate` refuses the whole corpus for it.
-- ---------------------------------------------------------------------------


-- ===========================================================================
-- 1. The door asks about the body in the same breath as everything else
-- ===========================================================================

-- DROP and CREATE, because a parameter is being added and `CREATE OR REPLACE`
-- cannot change a function's arity. The identity arm goes first: it is the only
-- caller, and dropping the callee out from under a live wrapper would leave one
-- statement in this transaction able to resolve a function the next statement
-- replaces.
DROP FUNCTION authorize_identity_egress_request(
    text, text, text, text, integer, text, text);
DROP FUNCTION authorize_egress_request(
    text, text, text, text, integer, text, text, text);

-- The body below is 20260815T000000Z's, carried forward verbatim apart from the
-- new parameter and the one arm at the end. Copied rather than wrapped: two
-- authorizers reachable by one name, with the weaker one selected by anybody who
-- passes the old argument list, is worse than either -- which is the same
-- sentence 20260810T214500Z wrote when it took the URL out of this function.
CREATE FUNCTION authorize_egress_request(
    p_capability text,
    p_method     text,
    p_protocol   text,
    p_host       text,
    p_port       integer,
    p_path_raw   text,
    p_path_norm  text,
    p_identity   text DEFAULT NULL,
    p_has_body   boolean DEFAULT false)
RETURNS TABLE (program_id uuid, tool_run_id uuid, scope_version integer,
               scope_class text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public
AS $fn$
DECLARE
    v_auth    record;
    v_version integer;
    v_class   text;
    v_tool    text;
    v_args    jsonb;
    v_method  text;
BEGIN
    SELECT * INTO v_auth FROM resolve_egress_capability(p_capability);
    IF NOT FOUND THEN
        RAISE EXCEPTION 'egress capability refused' USING ERRCODE = '23514';
    END IF;
    SELECT tr.tool, tr.args INTO v_tool, v_args
      FROM tool_runs tr WHERE tr.id = v_auth.tool_run_id;
    v_method := upper(coalesce(p_method, 'GET'));

    -- The canonical form, asserted rather than assumed. Each of these is a
    -- spelling the compiler's own canonicaliser cannot emit, so a request
    -- carrying one did not come through it.
    IF p_protocol IS NULL OR p_protocol NOT IN ('http', 'https') THEN
        RAISE EXCEPTION 'egress request states no known protocol'
            USING ERRCODE = '23514';
    END IF;
    IF p_host IS NULL OR scope_normalize_host(p_host) IS DISTINCT FROM p_host THEN
        RAISE EXCEPTION 'egress request states a host that is not in canonical form'
            USING ERRCODE = '23514';
    END IF;
    IF p_port IS NULL OR p_port < 1 OR p_port > 65535 THEN
        RAISE EXCEPTION 'egress request states no port in 1-65535'
            USING ERRCODE = '23514';
    END IF;
    IF p_path_raw IS NULL OR NOT starts_with(p_path_raw, '/')
       OR p_path_norm IS NULL OR NOT starts_with(p_path_norm, '/') THEN
        RAISE EXCEPTION 'egress request states a path that is not absolute'
            USING ERRCODE = '23514';
    END IF;
    -- A normalised path with a dot segment left in it is not normalised, and
    -- passing the raw spelling twice is exactly how 039 authorised
    -- `/public/../admin` under a rule that covers `/public`.
    IF p_path_norm ~ '(^|/)\.\.?(/|$)' THEN
        RAISE EXCEPTION 'egress request states a normalised path that still traverses'
            USING ERRCODE = '23514';
    END IF;

    -- Decided against the CURRENT policy and the request that actually arrived,
    -- not against the arguments that minted the capability. Subresources and
    -- redirects deliberately share one capability (§7); each still earns its own
    -- verdict, which is what makes sharing safe.
    SELECT p.scope_version INTO v_version
      FROM programs p WHERE p.id = v_auth.program_id;
    SELECT s.scope_class INTO v_class
      FROM scope_class_of(v_auth.program_id, v_version,
                          p_host, p_port, p_path_raw, p_path_norm,
                          p_protocol, 'request') s;
    IF coalesce(v_class, 'denied') NOT IN ('target', 'egress_support') THEN
        RAISE EXCEPTION 'egress request is outside current scope'
            USING ERRCODE = '23514';
    END IF;
    IF v_method <> 'CONNECT'
       AND v_tool IN ('mcp__rk2__net_request', rk2_browser_tool(), rk2_replay_tool())
       AND coalesce(p_identity, '') IS DISTINCT FROM
           coalesce(v_args ->> 'identity_slot', '') THEN
        RAISE EXCEPTION 'egress identity does not match authorized tool run'
            USING ERRCODE = '23514';
    END IF;
    IF v_tool IN (rk2_browser_tool(), rk2_replay_tool()) THEN
        -- CONNECT is exempt for ticket 10's reason: no tunnel is opened at all,
        -- so there is no request for a declared method to describe.
        IF v_method <> 'CONNECT'
           AND NOT (v_method = ANY (ARRAY(SELECT jsonb_array_elements_text(
                        coalesce(v_args -> 'methods', '[]'::jsonb))))) THEN
            RAISE EXCEPTION 'egress method is not one this plan derived'
                USING ERRCODE = '23514';
        END IF;
    -- The method the Tool run declared binds every request that could change
    -- something, and only those. §7 has subresources and redirects sharing one
    -- capability, and both arrive as GET whatever the declared method was: a
    -- page authorized as a POST pulls its scripts with GETs, and a 303 turns the
    -- POST itself into one. Refusing those would make the sharing unusable while
    -- protecting nothing, because a safe method is the one thing a caller who
    -- already holds the capability gains nothing by substituting. Anything
    -- outside the safe set is matched exactly.
    ELSIF v_method NOT IN ('GET', 'HEAD', 'OPTIONS', 'CONNECT')
       AND upper(coalesce(v_args ->> 'method', 'GET')) IS DISTINCT FROM v_method THEN
        RAISE EXCEPTION 'egress method does not match authorized tool run'
            USING ERRCODE = '23514';
    END IF;

    -- Ticket 96, and it sits here because it is the same kind of rule as the one
    -- above: what the Tool run was opened to do binds what the request arriving
    -- under it may be. The method says what kind of request this is; the body is
    -- the document the target's parser will actually read, and RFC 9110 §9.2.1
    -- is explicit that the method alone cannot tell you whether something is a
    -- write -- "it is common for Web-based content editing software to use
    -- actions within query parameters". So the narrower and honest property is
    -- the one bound here: a Tool run whose whole Playbook selection is readings
    -- cannot put bytes in front of a parser.
    --
    -- There is no safe-set exemption of the kind the method binding has, and
    -- nothing is lost by there not being one. The case that exemption exists for
    -- is a subresource or a redirect arriving as a GET under a capability minted
    -- for a POST, and both of those are fetched with no body at all.
    --
    -- The browser is named out of this rather than left out of it. Its bytes are
    -- a page's -- a form the target itself served, submitted by a real engine --
    -- rather than an argument a model wrote, and `body_allowed` is a statement
    -- about a model's argument. What binds a browser run is the method set its
    -- own plan derived, in the arm above. Every other tool is bound here,
    -- including the ones that send no body today, because a tool that grows one
    -- later should have to say so rather than inherit permission by omission.
    IF p_has_body
       AND v_tool IS DISTINCT FROM rk2_browser_tool()
       AND NOT coalesce(v_args -> 'body_allowed' = 'true'::jsonb, false) THEN
        RAISE EXCEPTION 'egress body does not match authorized tool run'
          USING ERRCODE = '23514',
                HINT = 'a Tool run carries a body only when the Playbooks '
                       'selected for its Task declare effects above read_only';
    END IF;

    RETURN QUERY SELECT v_auth.program_id, v_auth.tool_run_id,
                        v_version, v_class;
END $fn$;

COMMENT ON FUNCTION
    authorize_egress_request(text,text,text,text,integer,text,text,text,boolean) IS
  'Resolves a live capability and re-decides the request the proxy is about to send against the current compiled policy, in the canonical spellings the proxy will use. Refuses any spelling the canonicaliser could not have produced, an Identity or a method the Tool run was not authorized for, and a body a Tool run opened read-only may not carry.';


-- ===========================================================================
-- 2. The Identity arm passes it on and decides nothing about it
-- ===========================================================================

CREATE FUNCTION authorize_identity_egress_request(
    p_capability text,
    p_method     text,
    p_protocol   text,
    p_host       text,
    p_port       integer,
    p_path_raw   text,
    p_path_norm  text,
    p_has_body   boolean DEFAULT false
) RETURNS TABLE(
    program_id uuid,
    tool_run_id uuid,
    scope_version integer,
    scope_class text,
    identity_entity_id uuid,
    identity_label text
)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE v_identity record; v_authorized record;
BEGIN
    SELECT * INTO v_identity FROM resolve_egress_identity(p_capability);
    SELECT * INTO v_authorized FROM authorize_egress_request(
        p_capability, p_method, p_protocol, p_host, p_port,
        p_path_raw, p_path_norm, coalesce(v_identity.identity_label, ''), p_has_body
    );
    RETURN QUERY SELECT v_authorized.program_id, v_authorized.tool_run_id,
                        v_authorized.scope_version, v_authorized.scope_class,
                        v_identity.identity_entity_id, v_identity.identity_label;
END $fn$;

COMMENT ON FUNCTION
    authorize_identity_egress_request(text,text,text,text,integer,text,text,boolean) IS
  'The door''s own authorizer: resolves the Identity the capability''s Tool run selected, then decides the request under it. The body flag is carried through untouched -- what a body is allowed to be is one decision, and it is taken in authorize_egress_request beside the method binding it mirrors.';


-- ===========================================================================
-- 3. The grants and the declared surface follow the signatures
-- ===========================================================================
--
-- Both functions are born open to PUBLIC, because that is what PostgreSQL does
-- with a new function and section 1 of 20260909 only stopped the default grant
-- to `rk2_runtime`. So the revokes are load-bearing rather than decorative: a
-- role reaches a verb through PUBLIC as readily as through its own grant, and
-- `check_capability_receipt_fence` asserts below that `rk2_proxy` cannot execute
-- the inner authorizer at all.

REVOKE ALL ON FUNCTION
    authorize_egress_request(text,text,text,text,integer,text,text,text,boolean)
    FROM PUBLIC;
REVOKE ALL ON FUNCTION
    authorize_identity_egress_request(text,text,text,text,integer,text,text,boolean)
    FROM PUBLIC;

GRANT EXECUTE ON FUNCTION
    authorize_egress_request(text,text,text,text,integer,text,text,text,boolean)
    TO rk2_runtime;
GRANT EXECUTE ON FUNCTION
    authorize_identity_egress_request(text,text,text,text,integer,text,text,boolean)
    TO rk2_proxy;

-- `runtime_verb_surface` is checked both ways -- a granted verb with no row and
-- a row naming no function both fail the gate -- so the old identity text has to
-- go with the old function. The Identity arm has no row and gets none: 20260909
-- took it off the runtime's surface as one of the six proxy verbs, and it is
-- granted to `rk2_proxy` alone above.
DELETE FROM runtime_verb_surface
 WHERE verb = 'authorize_egress_request(text, text, text, text, integer, text, text, text)';

INSERT INTO runtime_verb_surface (verb, added_by, note) VALUES
    ('authorize_egress_request(text, text, text, text, integer, text, text, text, boolean)',
     '96',
     're-decides one egress request against the current compiled policy, including whether the Tool run it is spent under was opened to carry a body');


-- ===========================================================================
-- 4. The fence check reads the signatures that exist now
-- ===========================================================================
--
-- Two literals move and nothing else does. `has_function_privilege` raises on a
-- name that resolves to no function, so a check left naming the old arity would
-- not report a stale row -- it would take the whole standing gate down with an
-- `undefined_function`, which is a loud failure in the wrong place.

CREATE OR REPLACE FUNCTION check_capability_receipt_fence()
RETURNS TABLE(problem text, detail text) LANGUAGE sql STABLE AS $fn$
    SELECT 'proxy_can_insert_receipts', 'rk2_proxy has direct INSERT'
     WHERE has_table_privilege('rk2_proxy', 'receipts', 'INSERT')
    UNION ALL
    SELECT 'allowed_receipt_trigger_missing', 'trigger absent or not ENABLE ALWAYS'
     WHERE NOT EXISTS (SELECT 1 FROM pg_trigger
                        WHERE tgrelid = 'receipts'::regclass
                          AND tgname = 'receipts_allowed_capability' AND tgenabled = 'A')
    UNION ALL
    SELECT 'proxy_identity_writer_missing', 'rk2_proxy cannot execute the Identity fence'
     WHERE NOT has_function_privilege(
               'rk2_proxy',
               'authorize_identity_egress_request(text,text,text,text,integer,text,text,boolean)',
               'EXECUTE')
        OR NOT has_function_privilege(
               'rk2_proxy', 'authorize_identity_egress_address(text,text,text,integer,text)',
               'EXECUTE')
        OR NOT has_function_privilege('rk2_proxy', 'open_identity_slot(text,text)', 'EXECUTE')
        OR NOT has_function_privilege(
               'rk2_proxy', 'confirm_identity_slot_open(text,text,uuid,text)', 'EXECUTE')
        OR NOT has_function_privilege(
               'rk2_proxy',
               'record_identity_proxy_exchange(text,jsonb,jsonb,jsonb,text,bigint,jsonb)',
               'EXECUTE')
        OR NOT has_function_privilege(
               'rk2_proxy', 'ensure_proxy_wire_keying(text,bytea,bytea)', 'EXECUTE')
        OR NOT has_function_privilege(
               'rk2_proxy', 'write_blocked_receipt(uuid,jsonb,text)', 'EXECUTE')
        OR NOT has_function_privilege(
               'rk2_proxy', 'authorize_fixture_address(text,text,text,integer)',
               'EXECUTE')
    UNION ALL
    SELECT 'proxy_bypasses_identity_writer', 'rk2_proxy retains an unchecked writer'
     WHERE has_function_privilege('rk2_proxy', 'write_allowed_receipt(text,jsonb)', 'EXECUTE')
        OR has_function_privilege(
               'rk2_proxy', 'record_proxy_exchange(text,jsonb,jsonb)', 'EXECUTE')
        OR has_function_privilege(
               'rk2_proxy', 'record_proxy_exchange(text,jsonb,jsonb,jsonb)', 'EXECUTE')
        OR has_function_privilege(
               'rk2_proxy',
               'authorize_egress_request(text,text,text,text,integer,text,text,text,boolean)',
               'EXECUTE')
        OR has_function_privilege(
               'rk2_proxy', 'authorize_egress_address(text,text,text,integer,text)', 'EXECUTE')
        OR has_function_privilege('rk2_proxy', 'provision_identity_slot(uuid,text,bigint,jsonb)',
                                  'EXECUTE')
        OR has_table_privilege('rk2_proxy', 'identity_slots', 'SELECT')
    UNION ALL
    SELECT 'state_can_reach_identity_slots', 'the agent-facing role can reach slot state'
     WHERE has_table_privilege('rk2_state', 'identity_slots', 'SELECT')
        OR has_function_privilege('rk2_state', 'open_identity_slot(text,text)', 'EXECUTE')
        OR has_function_privilege(
               'rk2_state', 'provision_identity_slot(uuid,text,bigint,jsonb)', 'EXECUTE')
    UNION ALL
    SELECT 'unsealed_zero_byte_wire_artifact', a.sha256
      FROM artifacts a
     WHERE a.encrypted AND a.byte_size = 0 AND a.purged_at IS NULL
       AND NOT EXISTS (SELECT 1 FROM artifact_seal s WHERE s.sha256 = a.sha256)
    UNION ALL
    SELECT 'blocked_receipt_answers_with_a_row_id',
           'a refusal would name its record with something no label resolves'
     WHERE pg_get_function_result(
               'write_blocked_receipt(uuid,jsonb,text)'::regprocedure) <> 'text'
    UNION ALL
    SELECT 'stored_transcript_is_unheld',
           'no label in program ' || r.program_id::text || ' names ' || t.sha256
      FROM receipts r
      CROSS JOIN LATERAL (VALUES (r.request_agent_sha), (r.response_agent_sha))
        AS t(sha256)
      JOIN artifacts a ON a.sha256 = t.sha256
     WHERE t.sha256 IS NOT NULL
       AND a.visibility = 'agent_visible'
       AND NOT a.encrypted
       AND a.purged_at IS NULL
       AND NOT EXISTS (SELECT 1 FROM artifact_references x
                        WHERE x.program_id = r.program_id AND x.sha256 = t.sha256)
    UNION ALL
    -- Ticket 78. A Receipt classed `fixture` names a synthetic target this
    -- harness started, and the only thing that can say where one was is the
    -- fixture address the evaluation opened. Without that row the class is the
    -- door's own word for what it dialled, which is the one thing no
    -- Receipt column is allowed to be.
    SELECT 'fixture_receipt_without_an_address',
           'receipt ' || r.id::text || ' is classed fixture at ' || r.host
           || ':' || r.port::text || ', which no fixture address names'
      FROM receipts r
     WHERE r.scope_class = 'fixture'
       AND NOT EXISTS (SELECT 1 FROM fixture_addresses e
                        WHERE e.program_id = r.program_id
                          AND e.host = r.host AND e.port = r.port)
$fn$;


-- ===========================================================================
-- 5. One approval covers one body-bearing Task
-- ===========================================================================
--
-- The header of this file argues the choice. What the code does is small: the
-- net_request document keeps every fact it had, `reusable` becomes the negation
-- of `body_allowed`, and a Tool run that is not reusable carries the nonce so
-- its key is its own.
--
-- `body_keys` stays, and stays derived from an object body that this contract
-- cannot express. It is not dead: `digest_facts` declares it, a rule may name
-- it, and a structured body is the phase-2 shape the research file proposes. An
-- empty array for a string body is the true answer to "which top-level keys did
-- this body declare", and removing the fact would take a rule's vocabulary away
-- to say the same thing.

CREATE OR REPLACE FUNCTION canonical_request(p_tool text, p_args jsonb, p_nonce text)
RETURNS jsonb LANGUAGE plpgsql IMMUTABLE AS $fn$
DECLARE
    u  text;
    m  text[];
    sc text; ho text; po int; pa text; qs text;
    bb boolean;
BEGIN
    IF p_tool <> 'mcp__rk2__net_request' THEN
        -- Not reusable, so the nonce makes every key unique. `tool_name` is
        -- still carried because it is a risk FACT: a rule that names a fact the
        -- digest never holds is a rule that can never fire, which is a hole
        -- that looks like a policy. Carrying it cannot widen an approval --
        -- `reusable` is false either way.
        RETURN jsonb_build_object(
            'tool', p_tool, 'reusable', false, 'nonce', p_nonce,
            'tool_name', coalesce(p_args ->> 'tool_name', ''),
            'arg_names', (SELECT coalesce(jsonb_agg(k ORDER BY k), '[]'::jsonb)
                            FROM jsonb_object_keys(coalesce(p_args,'{}'::jsonb)) k));
    END IF;

    u := p_args ->> 'url';
    m := regexp_match(coalesce(u,''),
                      '^(https?)://([^/:?#]+)(?::([0-9]+))?([^?#]*)(?:\?([^#]*))?$');
    IF m IS NULL THEN
        RAISE EXCEPTION 'net_request url is not canonicalisable: %', coalesce(u,'<null>')
            USING ERRCODE = '22023';
    END IF;
    sc := lower(m[1]);
    ho := lower(m[2]);
    po := coalesce(m[3]::int, CASE sc WHEN 'https' THEN 443 ELSE 80 END);
    pa := path_template(nullif(m[4], ''));
    qs := coalesce(m[5], '');

    -- Ticket 96. The Tool run was opened body-bearing or it was not, and the
    -- bytes themselves are never in this document to be hashed: they are chosen
    -- by the child after the row was written, and the door that carries them
    -- holds no write on `tool_runs`. So the honest key for a call that may send
    -- a body it cannot describe is a key that matches nothing else.
    bb := coalesce(p_args -> 'body_allowed' = 'true'::jsonb, false);

    RETURN jsonb_build_object(
        'tool',          p_tool,
        'reusable',      NOT bb,
        'method',        upper(coalesce(p_args ->> 'method', 'GET')),
        'scheme',        sc,
        'host',          ho,
        'port',          po,
        'path_template', pa,
        'identity_slot', coalesce(p_args ->> 'identity_slot', ''),
        -- names, never values
        'query_names',   (SELECT coalesce(jsonb_agg(DISTINCT split_part(kv,'=',1)), '[]'::jsonb)
                            FROM unnest(string_to_array(qs,'&')) kv
                           WHERE kv <> ''),
        'body_keys',     (SELECT coalesce(jsonb_agg(k ORDER BY k), '[]'::jsonb)
                            FROM jsonb_object_keys(
                                 CASE WHEN jsonb_typeof(p_args -> 'body') = 'object'
                                      THEN p_args -> 'body' ELSE '{}'::jsonb END) k))
      || CASE WHEN bb THEN jsonb_build_object('nonce', p_nonce) ELSE '{}'::jsonb END;
END $fn$;

COMMENT ON FUNCTION canonical_request(text, jsonb, text) IS
  'What makes two tool calls the same call, as the document a human approval is taken over. Names and never values, one shape per tool, and no reusable key for a call the digest cannot fully describe: a Tool run opened to carry a body chooses its bytes after this row was written, so its key carries a nonce and one approval covers one Task.';


-- And the nonce a body-bearing request is keyed on, which is the half that
-- decides whether an approval can ever be spent. Everything else keeps the Tool
-- run's label it has always had; the reason this one case cannot is written
-- against the branch that makes the exception.
CREATE OR REPLACE FUNCTION current_request_digest(p_tool_run_id uuid) RETURNS jsonb
LANGUAGE plpgsql STABLE AS $fn$
DECLARE
    tr     tool_runs%ROWTYPE;
    digest jsonb;
    raw    text[];
    sclass text;
    nonce  text;
BEGIN
    SELECT * INTO tr FROM tool_runs WHERE id = p_tool_run_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'no tool_run %', p_tool_run_id; END IF;

    -- Ticket 96. `park_for_human` closes the Tool run it asked about and the
    -- Task the operator releases is claimed again as a new one, so a key built
    -- on this Tool run's label is a key the next attempt cannot compute: the
    -- question would be asked again, answered again, and asked again. What the
    -- operator answered about is the Task, so that is what a body-bearing
    -- request is keyed on. Only that case: for every other tool the nonce is
    -- what it has always been, because widening any of them is a decision this
    -- ticket has no business taking.
    nonce := tr.label;
    IF tr.task_id IS NOT NULL
       AND tr.tool = 'mcp__rk2__net_request'
       AND coalesce(tr.args -> 'body_allowed' = 'true'::jsonb, false) THEN
        SELECT t.label INTO nonce FROM tasks t WHERE t.id = tr.task_id;
    END IF;

    digest := canonical_request(tr.tool, coalesce(tr.args,'{}'::jsonb), nonce);
    IF digest ->> 'host' IS NOT NULL THEN
        -- ticket 26's projection, resolved from the RAW path (the scope rules
        -- match on real paths, not on the templated one) at the program's
        -- current scope version. `scope_class` lands in the digest and is
        -- therefore part of the equivalence key: an approval given under one
        -- scope version does not survive a scope change that reclassifies the
        -- host, which is the behaviour ticket 26 asks for.
        raw := regexp_match(coalesce(tr.args ->> 'url',''),
                            '^https?://[^/:?#]+(?::[0-9]+)?([^?#]*)');
        SELECT s.scope_class INTO sclass
          FROM programs p
          CROSS JOIN LATERAL scope_class_of(p.id, p.scope_version,
                                            digest ->> 'host', (digest ->> 'port')::int,
                                            coalesce(nullif(raw[1],''),'/'),
                                            coalesce(nullif(raw[1],''),'/')) s
         WHERE p.id = tr.program_id;
        digest := digest || jsonb_build_object(
            'scope_class',   coalesce(sclass, 'not_addressable'),
            'host_in_scope', coalesce(sclass,'') IN ('target','egress_support'));
    END IF;
    RETURN digest;
END $fn$;


-- ===========================================================================
-- 6. What this migration claims, asserted
-- ===========================================================================

DO $$
DECLARE
    v_read_only jsonb := '{"url":"https://probe.invalid/a","method":"POST"}'::jsonb;
    v_bodied    jsonb := '{"url":"https://probe.invalid/a","method":"POST",'
                         '"body_allowed":true}'::jsonb;
BEGIN
    -- The rule, at the level it is actually spent. The nonce a body-bearing
    -- request is keyed on is its Task's, so two Tasks are two keys and one
    -- Task's second attempt is the key its operator already answered. Read-only
    -- work keeps one key whatever Task asked, which is the promise that nothing
    -- outside this rule moved.
    IF equivalence_key(canonical_request('mcp__rk2__net_request', v_read_only, 'T1'))
       IS DISTINCT FROM
       equivalence_key(canonical_request('mcp__rk2__net_request', v_read_only, 'T2')) THEN
        RAISE EXCEPTION
            'ticket 96: a read-only request stopped being one approval''s to cover';
    END IF;
    IF equivalence_key(canonical_request('mcp__rk2__net_request', v_bodied, 'T1'))
       = equivalence_key(canonical_request('mcp__rk2__net_request', v_bodied, 'T2')) THEN
        RAISE EXCEPTION
            'ticket 96: two body-bearing Tasks still share one human approval';
    END IF;
    IF equivalence_key(canonical_request('mcp__rk2__net_request', v_bodied, 'T1'))
       IS DISTINCT FROM
       equivalence_key(canonical_request('mcp__rk2__net_request', v_bodied, 'T1')) THEN
        RAISE EXCEPTION
            'ticket 96: an approved body-bearing Task could not compute its own key again';
    END IF;

    -- And the facts every per-call rule is written against are still in the
    -- document for the bodied shape. `risk_fact_not_in_digest` probes the
    -- read-only shape only, so this is the arm that would have caught a bodied
    -- call quietly losing `host` and taking `host_in_scope` with it.
    IF NOT (canonical_request('mcp__rk2__net_request', v_bodied, 'TR1')
            ?& ARRAY['method','scheme','host','port','path_template',
                     'identity_slot','query_names','body_keys','reusable']) THEN
        RAISE EXCEPTION
            'ticket 96: a body-bearing call is no longer described by the digest facts';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_proc p
         WHERE p.pronamespace = 'public'::regnamespace
           AND p.proname = 'authorize_identity_egress_request'
           AND pg_catalog.oidvectortypes(p.proargtypes)
               = 'text, text, text, text, integer, text, text, boolean'
           AND has_function_privilege('rk2_proxy', p.oid, 'EXECUTE')) THEN
        RAISE EXCEPTION 'ticket 96: the door cannot ask about a body';
    END IF;

    -- The split the whole fence rests on, re-asserted at the moment its
    -- signature moved: the door reaches the Identity arm and never the inner
    -- authorizer, so a door made to lie cannot skip the Identity resolution by
    -- calling one function instead of the other.
    IF EXISTS (
        SELECT 1 FROM pg_proc p
         WHERE p.pronamespace = 'public'::regnamespace
           AND p.proname = 'authorize_egress_request'
           AND has_function_privilege('rk2_proxy', p.oid, 'EXECUTE')) THEN
        RAISE EXCEPTION 'ticket 96: the door was handed the authorizer it must not hold';
    END IF;

    IF EXISTS (SELECT 1 FROM check_capability_receipt_fence()) THEN
        RAISE EXCEPTION 'ticket 96: the capability fence does not hold after the rewrite';
    END IF;
    IF EXISTS (SELECT 1 FROM check_control_surface()) THEN
        RAISE EXCEPTION 'ticket 96: the control surface does not hold after the rewrite';
    END IF;
END $$;
