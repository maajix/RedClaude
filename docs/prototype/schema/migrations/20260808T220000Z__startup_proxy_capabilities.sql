-- Ticket 04: resolve the capability against the request the proxy will send.

CREATE FUNCTION authorize_egress_request(
    p_capability text,
    p_method text,
    p_url text,
    p_identity text DEFAULT ''
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
    v_digest  jsonb;
    v_raw     text[];
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

    -- Canonicalise the request that reached the proxy, not the arguments that
    -- originally minted the capability. Subresources deliberately share the
    -- capability, but each still receives its own current scope decision.
    v_digest := canonical_request(
        'mcp__rk2__net_request',
        jsonb_build_object('url', p_url, 'method', upper(coalesce(p_method, 'GET')),
                           'identity_slot', coalesce(p_identity, '')),
        'proxy');
    v_raw := regexp_match(coalesce(p_url, ''),
                          '^https?://[^/:?#]+(?::[0-9]+)?([^?#]*)');
    SELECT p.scope_version INTO v_version
      FROM programs p WHERE p.id = v_auth.program_id;
    SELECT s.scope_class INTO v_class
      FROM scope_class_of(v_auth.program_id, v_version,
                          v_digest ->> 'host', (v_digest ->> 'port')::integer,
                          coalesce(nullif(v_raw[1], ''), '/'),
                          coalesce(nullif(v_raw[1], ''), '/')) s;
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
    IF upper(coalesce(p_method, 'GET')) NOT IN ('GET', 'HEAD', 'OPTIONS', 'CONNECT')
       AND upper(coalesce(v_args ->> 'method', 'GET')) IS DISTINCT FROM
           upper(coalesce(p_method, 'GET')) THEN
        RAISE EXCEPTION 'egress method does not match authorized tool run'
            USING ERRCODE = '23514';
    END IF;

    RETURN QUERY SELECT v_auth.program_id, v_auth.tool_run_id,
                        v_version, v_class;
END $fn$;

REVOKE ALL ON FUNCTION authorize_egress_request(text, text, text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION authorize_egress_request(text, text, text, text) TO rk2_runtime;

COMMENT ON FUNCTION authorize_egress_request(text, text, text, text) IS
  'Resolves a live capability and independently canonicalises and scope-checks the actual proxy request before egress.';
