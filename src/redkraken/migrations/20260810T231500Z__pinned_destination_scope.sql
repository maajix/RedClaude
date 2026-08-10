-- ===========================================================================
-- Production harness 11 -- the destination is decided as an address, not only
-- as a name
-- ===========================================================================
--
-- What was here before decided a request once, against the hostname the caller
-- asked for, and then handed that hostname to the socket layer to resolve for
-- itself. Two lookups, one decision, and the gap between them belongs to
-- whoever runs the zone: a record with a one-second life answers the policy
-- with an address in scope and answers the connect with `169.254.169.254`.
-- Nothing in the schema could see that happen, because nothing in the schema
-- was ever told an address.
--
-- So the proxy now resolves the name once, itself, after the first decision has
-- passed -- never before, because a lookup is a packet leaving the machine
-- carrying the name that was asked for, and one made for a request about to be
-- refused would be egress with no Receipt behind it. It checks every address
-- the name answered with for being one the public internet routes to, which is
-- a question about addresses and not about policy and therefore stays in the
-- process that holds the socket. And then it asks this function the one
-- question that is policy: whether the Program withdrew the machine it is about
-- to open a connection to.
--
-- The answer is deliberately narrow, and the narrowness is the whole design.
-- Asking "is this address in scope" would refuse every request there is: a
-- policy written in names says nothing about addresses, so every address would
-- come back `unlisted`, and a fence that denies by default would deny
-- everything. What is asked instead is whether a withdrawal reaches the
-- address. Silence is the ordinary case and is not a refusal; an exclusion --
-- a network, an address, whichever name was used to arrive at it -- is.
--
-- This has to be a definer function rather than a query the proxy writes,
-- because `rk2_proxy` holds no `SELECT` on `program_scope_rules` and
-- `scope_class_of` is not a definer. The proxy cannot read the policy even to
-- agree with it, and that is the property worth keeping: a door that could read
-- the rules is a door that could be made to evaluate them itself.

CREATE FUNCTION authorize_egress_address(
    p_capability text,
    p_protocol   text,
    p_host       text,
    p_port       integer,
    p_address    text
) RETURNS TABLE (
    scope_class text,
    reason      text
)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE
    -- What a normalized address looks like, and nothing else does. The same two
    -- shapes `scope_normalize_host` uses to decide it is holding an address:
    -- four dotted decimal groups, or hexadecimal with at least one colon in it.
    -- The colon is why it is spelled this way rather than as a character class
    -- -- `cafe` is a legal single-label hostname and is made entirely of
    -- hexadecimal digits -- and the four groups are why `1.2.3` is a name here,
    -- as it is there, rather than the address `inet` would widen it into.
    v_shape   constant text := '^([0-9]{1,3}(\.[0-9]{1,3}){3}|[0-9a-f]*:[0-9a-f:]*)$';
    v_auth    record;
    v_version integer;
    v_address text;
    v_asked   text;
    v_class   text;
    v_reason  text;
BEGIN
    -- The capability again, and not the Program the proxy claims. It is resolved
    -- here for the Program it belongs to and for the liveness it carries: this
    -- call happens after the first decision and before the socket, so a
    -- capability whose Tool run closed, whose Program closed, whose parent run
    -- finished or whose task lease lapsed in between stops the exchange with
    -- nothing dialled.
    SELECT * INTO v_auth FROM resolve_egress_capability(p_capability);
    IF NOT FOUND THEN
        RAISE EXCEPTION 'egress capability refused' USING ERRCODE = '23514';
    END IF;

    IF p_protocol IS NULL OR p_protocol NOT IN ('http', 'https') THEN
        RAISE EXCEPTION 'egress destination states no known protocol'
            USING ERRCODE = '23514';
    END IF;
    IF p_port IS NULL OR p_port < 1 OR p_port > 65535 THEN
        RAISE EXCEPTION 'egress destination states no port in 1-65535'
            USING ERRCODE = '23514';
    END IF;

    -- An address, and nothing that merely looks like one. `scope_normalize_host`
    -- answers with a bare host for a name and with the canonical spelling for an
    -- address, so the shape above is what separates the two: a caller passing a
    -- hostname here would be asking the policy about the thing it was already
    -- asked about, and getting a second yes for free.
    v_address := scope_normalize_host(p_address);
    IF v_address IS NULL OR v_address !~ v_shape THEN
        RAISE EXCEPTION 'egress destination % is not an address',
            coalesce(p_address, '<null>') USING ERRCODE = '23514';
    END IF;

    -- A request that named an address had nothing to resolve, so the address it
    -- is dialled at must be the address it named. A proxy handing over a
    -- different one would be asking about a destination it is not about to open.
    v_asked := scope_normalize_host(p_host);
    IF v_asked ~ v_shape AND v_asked IS DISTINCT FROM v_address THEN
        RAISE EXCEPTION
            'egress destination % is not the address % the request named',
            v_address, v_asked USING ERRCODE = '23514';
    END IF;

    SELECT p.scope_version INTO v_version
      FROM programs p WHERE p.id = v_auth.program_id;

    -- The coverage question at the root, not the request question at this
    -- request's path. A withdrawal is asked about the machine: an operator who
    -- excluded a network excluded it, and an address that is only out of bounds
    -- for one path was already refused -- or allowed -- by name, at the decision
    -- this one sits behind. The protocol and port are passed because they name
    -- the socket that is about to be opened, and a rule about a different port
    -- is a rule about a different destination.
    SELECT s.scope_class, s.reason INTO v_class, v_reason
      FROM scope_class_of(v_auth.program_id, v_version,
                          v_address, p_port, '/', '/', p_protocol, 'coverage') s;
    IF v_reason = 'excluded' THEN
        RAISE EXCEPTION 'egress destination % is withdrawn by the current scope',
            v_address USING ERRCODE = '23514';
    END IF;

    RETURN QUERY SELECT coalesce(v_class, 'denied'), coalesce(v_reason, 'unlisted');
END $fn$;

REVOKE ALL ON FUNCTION
    authorize_egress_address(text, text, text, integer, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION
    authorize_egress_address(text, text, text, integer, text) TO rk2_runtime, rk2_proxy;

COMMENT ON FUNCTION authorize_egress_address(text, text, text, integer, text) IS
  'Re-decides the destination as the literal address the proxy pinned, after resolution and before the socket. Refuses an address the current policy withdraws, and refuses a capability that stopped being live in between.';


-- ---------------------------------------------------------------------------
-- The standing check learns the new writer
-- ---------------------------------------------------------------------------
-- Restated whole rather than added beside, for the reason the previous file
-- gave: `capability_receipt_fence` is where a reader already looks, and a
-- second check answering half the same question is a second place to look.
--
-- A missing grant here fails closed on its own -- the proxy's call raises and
-- the request is refused -- so this rule is not what makes the fence hold. It
-- is what makes a door that has silently stopped being able to ask the address
-- question visible as a broken fence rather than as a run of refusals somebody
-- eventually investigates.

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
        OR NOT has_function_privilege(
               'rk2_proxy',
               'authorize_egress_address(text,text,text,integer,text)',
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
    -- The policy the proxy must not be able to read for itself. The address
    -- decision is a definer function precisely so that this stays false; a role
    -- that can select the rules can evaluate them, and then the fence is a
    -- convention rather than a boundary.
    SELECT 'proxy_can_read_the_scope_rules',
           'rk2_proxy has SELECT on program_scope_rules'
     WHERE has_table_privilege('rk2_proxy', 'program_scope_rules', 'SELECT')
    UNION ALL
    SELECT 'unsealed_zero_byte_wire_artifact', a.sha256
      FROM artifacts a
     WHERE a.encrypted AND a.byte_size = 0 AND a.purged_at IS NULL
       AND NOT EXISTS (SELECT 1 FROM artifact_seal s WHERE s.sha256 = a.sha256)
$fn$;

COMMENT ON FUNCTION check_capability_receipt_fence() IS
  'The proxy writes Receipts only through the writers that check them, reaches both decisions only through the definer functions that make them, cannot read the policy it is fenced by, and no credential-bearing artifact escapes the seal rule by being empty.';

UPDATE standing_checks
   SET note = 'the proxy reaches an allowed receipt only through record_proxy_exchange, decides the name and the pinned address only through the definer authorizers, cannot select the scope rules itself, and an encrypted artifact is sealed however few bytes it has'
 WHERE name = 'capability_receipt_fence';


-- ---------------------------------------------------------------------------
-- This file's own rules, or it does not finish
-- ---------------------------------------------------------------------------

DO $$
DECLARE n integer; d text;
BEGIN
    IF NOT has_function_privilege(
               'rk2_proxy',
               'authorize_egress_address(text,text,text,integer,text)', 'EXECUTE') THEN
        RAISE EXCEPTION
            'rk2_proxy cannot call authorize_egress_address; the door would have '
            'no way to have the address it pinned decided by anything';
    END IF;
    IF has_table_privilege('rk2_proxy', 'program_scope_rules', 'SELECT') THEN
        RAISE EXCEPTION
            'rk2_proxy can select program_scope_rules; the address decision is a '
            'definer function so that the proxy cannot evaluate the policy itself';
    END IF;

    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_capability_receipt_fence();
    IF n > 0 THEN
        RAISE EXCEPTION 'capability receipt fence broken (% problems): %', n, d;
    END IF;
END $$;
