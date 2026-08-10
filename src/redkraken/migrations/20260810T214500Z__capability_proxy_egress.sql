-- ===========================================================================
-- Production harness 09 -- the capability is spent at one door, and the door
-- writes the record
-- ===========================================================================
-- 038, 039 and 040 built a capability, an authorizer and a receipt fence, and
-- then left the middle of the path unbuilt: nothing sent a capability anywhere,
-- so nothing exercised the three functions and nothing found what they were
-- getting wrong. `proxy.py` is the door those three were written for. This file
-- is the half of the door that lives in the database, and it is four changes,
-- each of them a place where the built path would otherwise have authorised
-- something the compiled policy does not.
--
--   * The Program's lifecycle joins the capability. 038 checked the Tool run,
--     its parent Agent run and its task lease and never asked whether the
--     Program was still open. A Program closes with runs still running -- that
--     is what `retire_program` does -- so a capability minted a minute earlier
--     outlived the authority it was minted under, for its full five minutes,
--     against a Program whose scope may have been withdrawn on purpose. The
--     same join goes on the trigger, because the trigger is the assertion and
--     the resolver is only the usual way to satisfy it.
--
--   * The proxy states the request; the database stops parsing it. 039 read the
--     host and port back out of the URL with `canonical_request` and the path
--     with a regular expression, while the process that would open the socket
--     parsed the same string with `urlsplit`. Two parsers over one string is a
--     differential, and the one that decides is never the one that connects.
--     Worse, the regular expression handed the RAW path to `scope_class_of` for
--     both spellings, and the `request` polarity requires both to be under the
--     prefix -- so `/public/../admin` was authorised as `/public`, which is
--     precisely the traversal 08 built two spellings to catch. And no protocol
--     was passed at all, so an http request satisfied an https-only rule. The
--     replacement takes the canonical spellings from the one process that will
--     use them, and refuses any that are not canonical.
--
--   * One writer per exchange. 040 gave the proxy `write_allowed_receipt` and a
--     separate `register_proxy_artifacts` that registered four hashes with
--     `byte_size 0` -- a claim about bytes nobody had stored, two of them
--     credential-bearing with no seal and no plaintext behind them. Two calls
--     also means a Receipt can name an artifact that was never registered, or
--     an artifact can be registered for a Receipt that was refused.
--     `record_proxy_exchange` is one call and one transaction: the bytes of both
--     directions, then the Receipt that names them, or neither.
--
--   * A wire view must be sealed, so this writer refuses to claim one. Nothing
--     in this ticket injects a credential, so nothing in it produces bytes that
--     differ from the ones the agent may read. Registering a wire hash equal to
--     the agent hash would put one artifact under two visibilities; registering
--     a different one would mean unsealed credential-bearing material. Ticket 12
--     injects, and ticket 12 seals.
--
-- What this file does NOT build: CONNECT. An HTTPS exchange this fence cannot
-- see inside is egress with no Receipt, and a tunnel that carried one anyway
-- would be a Receipt about bytes nobody read. Ticket 10 owns it, and until then
-- the door answers 405.
-- ===========================================================================


-- ---------------------------------------------------------------------------
-- 1. A capability does not outlive the Program it was minted under
-- ---------------------------------------------------------------------------
-- Two places, not one. The resolver is the door every honest caller comes
-- through, and the trigger is the invariant -- what makes an allowed agent
-- Receipt impossible rather than merely unwritten. A rule that lives only in
-- the resolver is a rule an owner-level INSERT walks around.

CREATE OR REPLACE FUNCTION resolve_egress_capability(p_capability text)
RETURNS TABLE (
    program_id uuid,
    tool_run_id uuid,
    agent_run_id uuid,
    task_id uuid,
    decision text,
    capability_expires_at timestamptz
)
LANGUAGE sql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
    SELECT tr.program_id, tr.id, tr.agent_run_id, tr.task_id, tr.decision,
           tr.egress_token_expires_at
      FROM tool_runs tr
      JOIN programs p
        ON p.id = tr.program_id AND p.closed_at IS NULL
      JOIN agent_runs ar
        ON ar.id = tr.agent_run_id AND ar.program_id = tr.program_id
      LEFT JOIN tasks t
        ON t.id = tr.task_id AND t.program_id = tr.program_id
     WHERE p_capability IS NOT NULL
       AND tr.program_id = rk2_program()
       AND tr.egress_token_sha256 = encode(digest(p_capability, 'sha256'), 'hex')
       AND tr.egress_token_expires_at > clock_timestamp()
       AND tr.status = 'running'
       AND tr.decision = 'allow'
       AND ar.finished_at IS NULL
       AND ((tr.task_id IS NULL AND ar.task_id IS NULL)
            OR (tr.task_id IS NOT NULL AND ar.task_id = tr.task_id
                AND t.status IN ('claimed', 'running')
                AND t.lease_expires_at > clock_timestamp()));
$fn$;

COMMENT ON FUNCTION resolve_egress_capability(text) IS
  'Resolves a plaintext capability only while its program, tool run, parent run and optional task lease remain active. A closed Program resolves nothing, whatever its runs still say.';

CREATE OR REPLACE FUNCTION enforce_allowed_receipt_capability() RETURNS trigger
LANGUAGE plpgsql AS $fn$
BEGIN
    IF NEW.lane = 'agent' AND NEW.decision = 'allowed'
       AND NOT EXISTS (
           SELECT 1
             FROM tool_runs tr
             JOIN programs p
               ON p.id = tr.program_id AND p.closed_at IS NULL
             JOIN agent_runs ar
               ON ar.id = tr.agent_run_id AND ar.program_id = tr.program_id
             LEFT JOIN tasks t
               ON t.id = tr.task_id AND t.program_id = tr.program_id
            WHERE tr.id = NEW.tool_run_id
              AND tr.program_id = NEW.program_id
              AND tr.status = 'running'
              AND tr.decision = 'allow'
              AND tr.egress_token_sha256 IS NOT NULL
              AND tr.egress_token_expires_at > clock_timestamp()
              AND ar.finished_at IS NULL
              AND ((tr.task_id IS NULL AND ar.task_id IS NULL)
                   OR (tr.task_id IS NOT NULL AND ar.task_id = tr.task_id
                       AND t.status IN ('claimed', 'running')
                       AND t.lease_expires_at > clock_timestamp()))
       ) THEN
        RAISE EXCEPTION 'allowed agent receipt lacks a live authorized capability'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $fn$;


-- ---------------------------------------------------------------------------
-- 2. The request is stated in canonical form, not re-derived from a URL
-- ---------------------------------------------------------------------------
-- DROP and CREATE, because the argument list changes and REPLACE cannot change
-- one. Not an overload beside the old shape either: two authorizers reachable
-- by one name, with the weaker one selected by anybody who still passes a URL,
-- is worse than either.
--
-- The trade this makes is worth naming. The database no longer parses the URL,
-- so it can no longer disagree with the process that opens the socket -- which
-- was the actual defect. What it takes instead is the proxy's word for the
-- canonical spellings, and it takes that word only after checking the shape of
-- it: a host that is not already `scope_normalize_host`'s output is refused, a
-- normalised path still carrying a dot segment is refused, and neither of those
-- is a spelling `scope.canonical_request` can produce. What SQL cannot check is
-- whether a normalised path is the normalisation OF that raw path, and a proxy
-- that lied about that would be authorising itself -- but a proxy that can lie
-- about its own canonicalisation is one that could have sent a different
-- request entirely, so the check would be theatre either way. The place that
-- assertion belongs is the fixture matrix, where both implementations answer
-- the same questions.

DROP FUNCTION authorize_egress_request(text, text, text, text);

CREATE FUNCTION authorize_egress_request(
    p_capability text,
    p_method     text,
    p_protocol   text,
    p_host       text,
    p_port       integer,
    p_path_raw   text,
    p_path_norm  text,
    p_identity   text DEFAULT ''
) RETURNS TABLE (
    program_id uuid,
    tool_run_id uuid,
    scope_version integer,
    scope_class text
)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE
    v_auth    record;
    v_version integer;
    v_class   text;
    v_tool    text;
    v_args    jsonb;
BEGIN
    SELECT * INTO v_auth FROM resolve_egress_capability(p_capability);
    IF NOT FOUND THEN
        RAISE EXCEPTION 'egress capability refused' USING ERRCODE = '23514';
    END IF;
    SELECT tr.tool, tr.args INTO v_tool, v_args
      FROM tool_runs tr WHERE tr.id = v_auth.tool_run_id;

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
    IF upper(coalesce(p_method, 'GET')) <> 'CONNECT'
       AND v_tool = 'mcp__rk2__net_request'
       AND coalesce(p_identity, '') IS DISTINCT FROM
           coalesce(v_args ->> 'identity_slot', '') THEN
        RAISE EXCEPTION 'egress identity does not match authorized tool run'
            USING ERRCODE = '23514';
    END IF;
    -- The method the Tool run declared binds every request that could change
    -- something, and only those. §7 has subresources and redirects sharing one
    -- capability, and both arrive as GET whatever the declared method was: a
    -- page authorized as a POST pulls its scripts with GETs, and a 303 turns the
    -- POST itself into one. Refusing those would make the sharing unusable while
    -- protecting nothing, because a safe method is the one thing a caller who
    -- already holds the capability gains nothing by substituting. Anything
    -- outside the safe set is matched exactly. CONNECT is exempt for a different
    -- reason: no tunnel is opened at all (ticket 10), so there is no request for
    -- the declared method to describe.
    IF upper(coalesce(p_method, 'GET')) NOT IN ('GET', 'HEAD', 'OPTIONS', 'CONNECT')
       AND upper(coalesce(v_args ->> 'method', 'GET')) IS DISTINCT FROM
           upper(coalesce(p_method, 'GET')) THEN
        RAISE EXCEPTION 'egress method does not match authorized tool run'
            USING ERRCODE = '23514';
    END IF;

    RETURN QUERY SELECT v_auth.program_id, v_auth.tool_run_id,
                        v_version, v_class;
END $fn$;

REVOKE ALL ON FUNCTION
    authorize_egress_request(text,text,text,text,integer,text,text,text)
    FROM PUBLIC;
GRANT EXECUTE ON FUNCTION
    authorize_egress_request(text,text,text,text,integer,text,text,text)
    TO rk2_runtime, rk2_proxy;

COMMENT ON FUNCTION
    authorize_egress_request(text,text,text,text,integer,text,text,text) IS
  'Resolves a live capability and re-decides the request the proxy is about to send against the current compiled policy, in the canonical spellings the proxy will use. Refuses any spelling the canonicaliser could not have produced.';


-- ---------------------------------------------------------------------------
-- 3. One exchange, one call: the bytes and the Receipt that names them
-- ---------------------------------------------------------------------------
-- `receipts.request_agent_sha` is a foreign key into `artifacts`, so the rows
-- have to exist before the Receipt does; and 07's `artifact_refs` counts the
-- two receipt columns as Program references, so writing the Receipt is what
-- makes the bytes reachable. Split across two calls those two facts are a race
-- with two losing sides: a Receipt naming bytes no row registered, or bytes
-- registered for a Receipt that was refused. One function, one statement, one
-- transaction, and the failure of either is the failure of both.

DROP FUNCTION register_proxy_artifacts(text, text, text, text, text);

CREATE FUNCTION record_proxy_exchange(
    p_capability text,
    p_receipt    jsonb,
    p_artifacts  jsonb
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE
    v_tool_run uuid;
    v_id       uuid;
    v_label    text;
    v_named    text[];
    v_problem  text;
BEGIN
    IF p_capability IS NULL
       OR coalesce(jsonb_typeof(p_receipt), 'null') <> 'object'
       OR coalesce(jsonb_typeof(p_artifacts), 'null') <> 'array' THEN
        RAISE EXCEPTION 'proxy exchange refused' USING ERRCODE = '23514';
    END IF;
    -- `write_allowed_receipt` makes the same check of the Receipt. It is made
    -- again here of the artifact list, which that function never sees: a
    -- capability spelled into a content type would otherwise be a capability in
    -- a table the operator console can read.
    IF position(p_capability IN p_artifacts::text) > 0 THEN
        RAISE EXCEPTION 'artifact payload contains protected capability'
            USING ERRCODE = '23514';
    END IF;

    SELECT a.tool_run_id INTO v_tool_run
      FROM resolve_egress_capability(p_capability) a;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'egress capability refused' USING ERRCODE = '23514';
    END IF;

    -- A wire view is the claim that what crossed the network differed from what
    -- the agent may read. Nothing that reaches this function has injected
    -- anything, so nothing that reaches it has produced a second view, and a
    -- hash recorded in a wire column would be either the agent's own bytes
    -- under a second visibility or credential-bearing material with no seal.
    IF nullif(p_receipt ->> 'request_wire_sha', '') IS NOT NULL
       OR nullif(p_receipt ->> 'response_wire_sha', '') IS NOT NULL THEN
        RAISE EXCEPTION 'a wire view must be sealed, and this writer cannot seal one'
            USING ERRCODE = '23514';
    END IF;

    -- Shape before storage, so a malformed list is a sentence rather than a
    -- primary-key violation from inside a function the caller cannot see into.
    IF EXISTS (SELECT 1 FROM jsonb_to_recordset(p_artifacts)
                 AS a(sha256 text, byte_size bigint, content_type text)
                WHERE a.sha256 IS NULL OR a.sha256 !~ '^[0-9a-f]{64}$'
                   OR a.byte_size IS NULL OR a.byte_size < 0) THEN
        RAISE EXCEPTION 'proxy exchange names an artifact with no hash or no byte count'
            USING ERRCODE = '23514';
    END IF;

    PERFORM set_actor('runtime');
    INSERT INTO artifacts (sha256, byte_size, content_type, visibility, encrypted)
    SELECT a.sha256, a.byte_size, a.content_type, 'agent_visible', false
      FROM jsonb_to_recordset(p_artifacts)
        AS a(sha256 text, byte_size bigint, content_type text)
    ON CONFLICT (sha256) DO NOTHING;

    -- The store is one namespace keyed by the hash of the plaintext, so a hash
    -- this exchange produced may already be registered by another Program's
    -- identical bytes -- which is the point of it, and is why the insert above
    -- conflicts silently. What must not pass silently is a disagreement: the
    -- same hash registered with a different length, or as something the agent
    -- may not read. Either means this Receipt is about to name bytes that are
    -- not the bytes it measured.
    SELECT string_agg(a.sha256 || ' (' || d.detail || ')', '; ')
      INTO v_problem
      FROM jsonb_to_recordset(p_artifacts)
        AS a(sha256 text, byte_size bigint, content_type text)
      LEFT JOIN artifacts x ON x.sha256 = a.sha256
      CROSS JOIN LATERAL (SELECT CASE
              WHEN x.sha256 IS NULL THEN 'not registered'
              WHEN x.byte_size <> a.byte_size
                   THEN 'registered as ' || x.byte_size || ' byte(s)'
              WHEN x.visibility <> 'agent_visible' OR x.encrypted
                   THEN 'registered as ' || x.visibility
              WHEN x.purged_at IS NOT NULL THEN 'purged'
              END AS detail) d
     WHERE d.detail IS NOT NULL;
    IF v_problem IS NOT NULL THEN
        RAISE EXCEPTION 'proxy exchange names artifacts it did not store: %', v_problem
            USING ERRCODE = '23514';
    END IF;

    -- Both directions, and both from this list. A Receipt naming a hash the
    -- caller did not register would be citing bytes it never measured, and the
    -- foreign key would accept it as long as some other Program had stored the
    -- same plaintext.
    SELECT array_agg(a.sha256) INTO v_named
      FROM jsonb_to_recordset(p_artifacts)
        AS a(sha256 text, byte_size bigint, content_type text);
    IF nullif(p_receipt ->> 'request_agent_sha', '') IS NULL
       OR nullif(p_receipt ->> 'response_agent_sha', '') IS NULL
       OR NOT (p_receipt ->> 'request_agent_sha' = ANY (coalesce(v_named, '{}')))
       OR NOT (p_receipt ->> 'response_agent_sha' = ANY (coalesce(v_named, '{}'))) THEN
        RAISE EXCEPTION 'proxy exchange must name the stored bytes of both directions'
            USING ERRCODE = '23514';
    END IF;

    v_id := write_allowed_receipt(p_capability, p_receipt);
    SELECT r.label INTO v_label FROM receipts r WHERE r.id = v_id;

    -- The label, not only the identifier. `rk2_proxy` holds no SELECT on
    -- `receipts`, and the label is what an agent cites in prose: returning the
    -- uuid alone would leave the caller holding a name it cannot resolve.
    RETURN jsonb_build_object('receipt_id', v_id, 'label', v_label,
                              'tool_run_id', v_tool_run);
END $fn$;

REVOKE ALL ON FUNCTION record_proxy_exchange(text, jsonb, jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION record_proxy_exchange(text, jsonb, jsonb) TO rk2_proxy;

-- And the door the proxy no longer has. `write_allowed_receipt` writes a
-- Receipt with no opinion about whether the bytes it names exist; leaving it
-- reachable beside `record_proxy_exchange` would leave the checks above
-- optional for the one role that has to pass them. The runtime keeps it: it is
-- the harness's own connection, it registers artifacts through `rk artifact`,
-- and it is not the role a compromised proxy would be holding.
REVOKE EXECUTE ON FUNCTION write_allowed_receipt(text, jsonb) FROM rk2_proxy;

COMMENT ON FUNCTION record_proxy_exchange(text, jsonb, jsonb) IS
  'The only path from the proxy to an allowed Receipt: registers the agent-visible bytes of both directions, refuses any hash it did not measure or cannot seal, writes the Receipt through write_allowed_receipt, and returns the label the agent will cite.';


-- ---------------------------------------------------------------------------
-- 4. The fence, restated for the door that now exists
-- ---------------------------------------------------------------------------
-- Same check name and same standing row: `capability_receipt_fence` is where a
-- reader already looks for "can the proxy write a Receipt it should not", and
-- splitting the answer across two checks would mean two places to look.
--
-- Rule 5 closes a hole 07 left open on purpose. Its rule 2 exempts
-- `byte_size = 0` from the seal requirement, and the reason it gives is
-- `register_proxy_artifacts()` -- the function section 3 drops. With no writer
-- left that registers bytes it does not have, an encrypted zero-length artifact
-- is no longer a placeholder; it is credential-bearing material entering the
-- one gap in the seal rule. It is here rather than in 07 because this file is
-- what removed the reason the exemption existed; asserted as one more rule
-- rather than by rewriting eight of 07's to change one predicate.
--
-- Nothing here checks that a Receipt's cited bytes are still readable. That is a
-- retention question -- an artifact may be purged while the Receipt that names
-- it stays -- and answering it in this check would report the retention policy
-- working as a fence that had broken.

CREATE OR REPLACE FUNCTION check_capability_receipt_fence()
RETURNS TABLE(problem text, detail text) LANGUAGE sql STABLE AS $fn$
    SELECT 'proxy_can_insert_receipts', 'rk2_proxy has direct INSERT'
     WHERE has_table_privilege('rk2_proxy', 'receipts', 'INSERT')
    UNION ALL
    SELECT 'allowed_receipt_trigger_missing', 'trigger absent or not ENABLE ALWAYS'
     WHERE NOT EXISTS (
        SELECT 1 FROM pg_trigger
         WHERE tgrelid = 'receipts'::regclass
           AND tgname = 'receipts_allowed_capability' AND tgenabled = 'A')
    UNION ALL
    SELECT 'proxy_writer_missing', 'rk2_proxy cannot execute a required writer'
     WHERE NOT has_function_privilege(
               'rk2_proxy', 'record_proxy_exchange(text,jsonb,jsonb)', 'EXECUTE')
        OR NOT has_function_privilege(
               'rk2_proxy', 'write_blocked_receipt(uuid,jsonb,text)', 'EXECUTE')
        OR NOT has_function_privilege(
               'rk2_proxy',
               'authorize_egress_request(text,text,text,text,integer,text,text,text)',
               'EXECUTE')
    UNION ALL
    -- The unchecked writer, reachable again. Every rule in
    -- `record_proxy_exchange` is optional for a role that can call the function
    -- it delegates to.
    SELECT 'proxy_bypasses_the_exchange_writer',
           'rk2_proxy can execute write_allowed_receipt directly'
     WHERE has_function_privilege(
               'rk2_proxy', 'write_allowed_receipt(text,jsonb)', 'EXECUTE')
    UNION ALL
    SELECT 'unsealed_zero_byte_wire_artifact', a.sha256
      FROM artifacts a
     WHERE a.encrypted AND a.byte_size = 0 AND a.purged_at IS NULL
       AND NOT EXISTS (SELECT 1 FROM artifact_seal s WHERE s.sha256 = a.sha256)
$fn$;

COMMENT ON FUNCTION check_capability_receipt_fence() IS
  'The proxy writes Receipts only through the writers that check them, an allowed agent Receipt requires a live capability, and no credential-bearing artifact escapes the seal rule by being empty.';

UPDATE standing_checks
   SET note = 'the proxy reaches an allowed receipt only through record_proxy_exchange, allowed agent receipts require a live capability, and an encrypted artifact is sealed however few bytes it has'
 WHERE name = 'capability_receipt_fence';


-- ---------------------------------------------------------------------------
-- 5. This file's own rules, or it does not finish
-- ---------------------------------------------------------------------------
-- The privilege half is asserted directly because the catalogue can be asked.
-- The behavioural half -- that a fabricated capability resolves to nothing, that
-- a closed Program's capability stops working, that an owner cannot insert an
-- allowed Receipt outside the invariant -- needs rows to exist and belongs to
-- the live test suite, which builds and purges its own Program.

DO $$
DECLARE n integer; d text;
BEGIN
    IF has_function_privilege('rk2_proxy', 'write_allowed_receipt(text,jsonb)', 'EXECUTE') THEN
        RAISE EXCEPTION
            'rk2_proxy can still call write_allowed_receipt directly; every check '
            'in record_proxy_exchange is optional for the role that has to pass them';
    END IF;
    IF NOT has_function_privilege(
               'rk2_proxy', 'record_proxy_exchange(text,jsonb,jsonb)', 'EXECUTE') THEN
        RAISE EXCEPTION
            'rk2_proxy cannot call record_proxy_exchange; the proxy has no way to '
            'record an exchange it was authorized to make';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_proc p
                JOIN pg_namespace n ON n.oid = p.pronamespace AND n.nspname = 'public'
               WHERE p.proname = 'register_proxy_artifacts') THEN
        RAISE EXCEPTION
            'register_proxy_artifacts still exists; it registers hashes with no '
            'bytes behind them and record_proxy_exchange replaces it';
    END IF;

    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_capability_receipt_fence();
    IF n > 0 THEN
        RAISE EXCEPTION 'capability receipt fence broken (% problems): %', n, d;
    END IF;
END $$;
