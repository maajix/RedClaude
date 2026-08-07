-- ---------------------------------------------------------------------------
-- 021_ticket26_scope_policy.sql   (ticket 26)
--
-- Applies on top of 001-017 (branch `prototype/program-isolation`, 6579365).
--
-- Ticket 06 left `programs.scope_policy` an untyped JSONB column. This turns it
-- into three things the rest of the system can cite:
--
--   1. an IMMUTABLE, versioned policy document, because a receipt has to name
--      the policy that authorised it and an in-place edit makes every past
--      receipt unauditable;
--   2. a COMPILED rule set, written by the same Python compiler the proxy runs,
--      so nothing in SQL parses a host pattern (two parsers for one grammar is
--      how `*.here.com` comes to mean two different things in one system);
--   3. a PROJECTION on `entities`, which is what the scheduler and the recon
--      agent read.
--
-- The projection is ADVISORY by construction. `scope.decide_egress` resolves
-- DNS and validates the peer address, so it cannot be a SQL function; the
-- projection is `scope.decide_static`, which `decide_egress` can only ever
-- narrow. A stale projection therefore wastes a task -- it cannot authorise a
-- request. That asymmetry is why a cache is safe in this direction and would
-- not be safe in the other.
--
-- Ticket 35 applies to every line below: both new tables are program-scoped,
-- every foreign key between two program-scoped rows carries `program_id`, and
-- `check_program_isolation()` must return nothing when this file finishes --
-- which the DO block at the bottom enforces, the way 017 does.
-- ---------------------------------------------------------------------------

-- ===========================================================================
-- 1. The policy document, versioned and append-only
-- ===========================================================================

CREATE TABLE program_scope_versions (
    program_id    uuid     NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    version       integer  NOT NULL CHECK (version >= 1),
    policy        jsonb    NOT NULL,
    policy_sha256 char(64) NOT NULL,
    -- Denormalised for the projection. NOT a scope gate: `default_tier` is read
    -- only after a verdict of `target` has already been reached.
    default_tier  text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    reason        text     NOT NULL DEFAULT '',
    PRIMARY KEY (program_id, version)
);

COMMENT ON TABLE program_scope_versions IS
  'Append-only. A scope change mid-hunt is a new version, never an edit: receipts, observations and findings all name the version that authorised them, and rewriting a version would rewrite what they mean.';

CREATE FUNCTION scope_versions_are_immutable() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION
        'program_scope_versions is append-only; a scope change is a new version, '
        'never an edit (receipts name the version that authorised them)';
END $$;

CREATE TRIGGER scope_versions_immutable
    BEFORE UPDATE OR DELETE ON program_scope_versions
    FOR EACH ROW EXECUTE FUNCTION scope_versions_are_immutable();
-- ticket 07: `session_replication_role = replica` skips ORIGIN triggers.
ALTER TABLE program_scope_versions ENABLE ALWAYS TRIGGER scope_versions_immutable;

-- Which version is live. NULL means "no policy yet", and with no policy every
-- entity projects to denied -- a program with no scope document is a program
-- nothing may be sent to.
ALTER TABLE programs ADD COLUMN scope_version integer;
ALTER TABLE programs ADD CONSTRAINT programs_scope_version_fkey
    FOREIGN KEY (id, scope_version)
    REFERENCES program_scope_versions (program_id, version);

-- ===========================================================================
-- 2. The compiled rules
--
-- One row per rule, written by scope.compile_policy. SQL does set membership
-- and precedence; it never parses a pattern.
-- ===========================================================================

CREATE TABLE program_scope_rules (
    program_id   uuid     NOT NULL,
    version      integer  NOT NULL,
    ord          integer  NOT NULL,
    effect       text     NOT NULL CHECK (effect IN ('exclude','egress_support','target')),
    effect_rank  smallint NOT NULL CHECK (effect_rank BETWEEN 0 AND 2),
    pattern_kind text     NOT NULL CHECK (pattern_kind IN ('exact','wildcard','cidr')),
    pattern_text text     NOT NULL,
    -- Equality join key. Exact rules store the bare host, wildcard rules store
    -- '*.'||suffix. NULL for CIDR rules, which match by address containment.
    match_key    text,
    net          cidr,
    port         integer CHECK (port IS NULL OR port BETWEEN 1 AND 65535),
    path_prefix  text,
    tier         text,
    allow_private_ips boolean NOT NULL DEFAULT false,
    spec_kind    smallint NOT NULL,
    spec_len     smallint NOT NULL,
    PRIMARY KEY (program_id, version, ord),
    -- NO ACTION, not CASCADE: ticket 07's rule is that the only unit of
    -- deletion is one whole program, and end-of-statement checking is what
    -- lets the whole-program purge pass while a narrower delete refuses.
    FOREIGN KEY (program_id, version)
        REFERENCES program_scope_versions (program_id, version),
    -- ...and the program edge, which is the one the purge travels.
    FOREIGN KEY (program_id) REFERENCES programs (id) ON DELETE CASCADE,
    -- A CIDR rule matches by address containment and by nothing else; every
    -- other kind matches by key. Both directions are asserted: a rule with
    -- both, or with neither, is a rule the evaluator would silently skip.
    CHECK ((pattern_kind = 'cidr') = (net IS NOT NULL)),
    CHECK ((pattern_kind = 'cidr') = (match_key IS NULL)),
    -- effort policy may only ride on a target rule (mirrors the Python compiler)
    CHECK (tier IS NULL OR effect = 'target')
);

-- The projection's whole performance story: one index scan per lookup.
CREATE INDEX scope_rules_key_idx
    ON program_scope_rules (program_id, version, match_key)
    INCLUDE (effect_rank, spec_kind, spec_len, tier, port, path_prefix);
CREATE INDEX scope_rules_net_idx
    ON program_scope_rules USING gist (net inet_ops)
    WHERE pattern_kind = 'cidr';

-- Both tables reach the purge root directly (ticket 07's registry).
INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
    ('program_scope_versions', 'program_id', 'program-scoped: the purge root'),
    ('program_scope_rules',    'program_id', 'program-scoped: the purge root');

-- ===========================================================================
-- 3. Receipts name the policy that authorised them
--
-- Two changes, both forced by facts settled elsewhere.
--
-- `lane` gains 'control'. Ticket 21 measured the agent's own control-plane
-- traffic: one zero-tool SDK turn makes 11 outbound requests, nine to
-- api.anthropic.com carrying the OAuth token plus Datadog telemetry. Under
-- "one egress path" those arrive at the same listener as hunt traffic. They are
-- not the program's, they are never evidence, and they draw from no program
-- rate bucket -- so they get their own lane rather than a rule in a policy no
-- program wrote.
--
-- `scope_version` makes every receipt attributable to a policy. Without it,
-- "this request was in scope" is a claim about whatever file happened to be on
-- disk at the time.
-- ===========================================================================

ALTER TABLE receipts DROP CONSTRAINT receipts_lane_check;
ALTER TABLE receipts ADD CONSTRAINT receipts_lane_check
    CHECK (lane IN ('agent','replay','proxy_internal','control'));

ALTER TABLE receipts ADD COLUMN scope_version integer;
ALTER TABLE receipts ADD COLUMN scope_class text
    CHECK (scope_class IN ('target','egress_support','control_plane','denied'));
ALTER TABLE receipts ADD CONSTRAINT receipts_scope_version_fkey
    FOREIGN KEY (program_id, scope_version)
    REFERENCES program_scope_versions (program_id, version);
-- A control-plane receipt has no program policy version, and a program receipt
-- must have one. The biconditional is the point: neither half is optional.
ALTER TABLE receipts ADD CONSTRAINT receipts_control_lane_has_no_policy
    CHECK ((lane = 'control') = (scope_version IS NULL));
ALTER TABLE receipts ADD CONSTRAINT receipts_control_lane_class
    CHECK ((lane = 'control') = (scope_class = 'control_plane'));
-- No default and no backfill: every receipt records the verdict its request
-- actually got. On a database that already holds receipts this ALTER fails,
-- which is the correct outcome -- inventing a scope class for a request nobody
-- classified is worse than refusing to migrate.
ALTER TABLE receipts ALTER COLUMN scope_class SET NOT NULL;

-- ===========================================================================
-- 4. Host normalisation and candidate keys
--
-- Mirrors scope.normalize_host; returns NULL where the Python raises
-- PolicyError, and the caller maps NULL to denied/malformed_host.
-- ===========================================================================

CREATE FUNCTION scope_normalize_host(raw text) RETURNS text
LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
    v text;
    lbl text;
    a inet;
BEGIN
    IF raw IS NULL THEN RETURN NULL; END IF;
    v := rtrim(lower(btrim(raw)), '.');
    IF v LIKE '[%]' THEN v := substring(v from 2 for length(v) - 2); END IF;
    IF v = '' THEN RETURN NULL; END IF;
    IF v !~ '^[[:ascii:]]*$' THEN RETURN NULL; END IF;

    -- IP literal. Only attempted on shapes Python also accepts, so the two
    -- agree on what is *not* an address (Python rejects '1.2.3'; inet widens it
    -- to 1.2.0.3). IPv4-mapped IPv6 collapses to its IPv4 form for the same
    -- reason it does in Python: `::ffff:93.184.216.34` and `93.184.216.34` are
    -- one machine, and version-mismatched containment silently answers false.
    IF v ~ '^[0-9]{1,3}(\.[0-9]{1,3}){3}$' OR v ~ '^[0-9a-f:]+$'
       OR v ~ '^::ffff:[0-9]{1,3}(\.[0-9]{1,3}){3}$' THEN
        BEGIN
            a := v::inet;
            IF family(a) = 6 AND host(a) LIKE '::ffff:%.%' THEN
                RETURN split_part(host(a), ':', 4);
            END IF;
            RETURN host(a);
        EXCEPTION WHEN others THEN
            RETURN NULL;
        END;
    END IF;

    IF length(v) > 253 THEN RETURN NULL; END IF;
    FOREACH lbl IN ARRAY string_to_array(v, '.') LOOP
        IF lbl !~ '^[a-z0-9_]([a-z0-9_-]{0,61}[a-z0-9_])?$' THEN
            RETURN NULL;                       -- '.here.com', 'here..com', ...
        END IF;
    END LOOP;
    RETURN v;
END $$;

-- Candidate keys. This is where the apex trap is encoded in SQL.
--
-- For host a.b.c the candidates are:  a.b.c (exact), *.b.c, *.c
-- For host b.c   the candidates are:  b.c   (exact), *.c
--
-- `*.b.c` is NOT a candidate of `b.c`. generate_series starts at label 2, and
-- that single `2` is the entire apex rule. A `1` here silently puts every
-- program's apex in scope.
CREATE FUNCTION scope_host_candidates(h text)
RETURNS TABLE(match_key text)
LANGUAGE sql IMMUTABLE AS $$
    WITH l AS (SELECT string_to_array(h, '.') AS labels)
    SELECT h FROM l
    UNION ALL
    SELECT '*.' || array_to_string(labels[i:cardinality(labels)], '.')
      FROM l, generate_series(2, cardinality(labels)) AS i
$$;

-- The wildcard ENTITY question, which is a different question.
-- `*.account.here.com` is covered by `*.here.com` AND by itself, so the series
-- starts at 1. An exact rule never appears here: every candidate starts '*.',
-- and exact rules store a bare host as their key. That is `jaguar.here.com`
-- being a legal target without authorising enumeration of `*.jaguar.here.com`.
CREATE FUNCTION scope_wildcard_candidates(suffix text)
RETURNS TABLE(match_key text)
LANGUAGE sql IMMUTABLE AS $$
    WITH l AS (SELECT string_to_array(suffix, '.') AS labels)
    SELECT '*.' || array_to_string(labels[i:cardinality(labels)], '.')
      FROM l, generate_series(1, cardinality(labels)) AS i
$$;

-- ===========================================================================
-- 5. The verdict
--
-- Path normalisation is the CALLER's job: both spellings are passed in, so
-- there is exactly one implementation of path_variants (scope.py) and SQL
-- cannot drift from it. Polarity differs by effect, same as the Python.
-- ===========================================================================

CREATE FUNCTION scope_class_of(
    p_program   uuid,
    p_version   integer,
    p_host      text,
    p_port      integer DEFAULT 443,
    p_path_raw  text    DEFAULT '/',
    p_path_norm text    DEFAULT '/')
RETURNS TABLE(scope_class text, reason text, rule_ord integer, tier text)
LANGUAGE sql STABLE AS $$
    WITH nh AS (SELECT scope_normalize_host(p_host) AS h),
    m AS (
        SELECT r.ord, r.effect, r.effect_rank, r.spec_kind, r.spec_len, r.tier
          FROM program_scope_rules r, nh
         WHERE nh.h IS NOT NULL
           AND r.program_id = p_program AND r.version = p_version
           AND (
                r.match_key IN (SELECT c.match_key
                                  FROM scope_host_candidates(nh.h) c)
             OR (r.pattern_kind = 'cidr'
                 AND r.net >>= (CASE WHEN nh.h ~ '^([0-9.]+|[0-9a-f:]+)$'
                                     THEN nh.h END)::inet)
           )
           AND (r.port IS NULL OR r.port = p_port)
           -- Same polarity split as scope.Rule.matches_request: an exclusion
           -- fires if EITHER spelling matches, an inclusion needs BOTH.
           AND (r.path_prefix IS NULL
                OR CASE WHEN r.effect = 'exclude'
                        THEN starts_with(p_path_raw,  r.path_prefix)
                          OR starts_with(p_path_norm, r.path_prefix)
                        ELSE starts_with(p_path_raw,  r.path_prefix)
                         AND starts_with(p_path_norm, r.path_prefix)
                   END)
    ),
    -- min(effect_rank) over EVERY match: document order is not a semantic.
    win AS (
        SELECT m.* FROM m
         WHERE m.effect_rank = (SELECT min(effect_rank) FROM m)
         -- specificity picks only WHICH rule is cited; the verdict is fixed.
         ORDER BY m.spec_kind DESC, m.spec_len DESC, m.ord ASC
         LIMIT 1
    ),
    tierpick AS (
        SELECT m.tier FROM m
         WHERE m.effect = 'target' AND m.tier IS NOT NULL
         ORDER BY m.spec_kind DESC, m.spec_len DESC, m.ord ASC
         LIMIT 1
    )
    SELECT
        CASE WHEN (SELECT h FROM nh) IS NULL      THEN 'denied'
             WHEN w.effect IS NULL                THEN 'denied'
             WHEN w.effect = 'exclude'            THEN 'denied'
             WHEN w.effect = 'egress_support'     THEN 'egress_support'
             ELSE 'target' END,
        CASE WHEN (SELECT h FROM nh) IS NULL      THEN 'malformed_host'
             WHEN w.effect IS NULL                THEN 'unlisted'
             WHEN w.effect = 'exclude'            THEN 'excluded'
             WHEN w.effect = 'egress_support'     THEN 'matched_egress_support'
             ELSE 'matched_target' END,
        w.ord::integer,
        CASE WHEN w.effect = 'target' THEN
            coalesce((SELECT tier FROM tierpick),
                     (SELECT sv.default_tier FROM program_scope_versions sv
                       WHERE sv.program_id = p_program
                         AND sv.version = p_version))
        END
    -- LEFT JOIN so the no-match case still returns exactly one row. A scope
    -- evaluator that can return zero rows fails open the first time a caller
    -- writes `IF NOT FOUND`.
      FROM (VALUES (1)) AS d(x) LEFT JOIN win w ON true
$$;

-- The verdict for a stored ENTITY. Dispatches on selector kind, because a
-- wildcard seed and a host are not the same question.
CREATE FUNCTION scope_class_of_entity(
    p_program uuid, p_version integer,
    p_kind text, p_selector text,
    p_port integer DEFAULT NULL,
    p_path_raw text DEFAULT '/', p_path_norm text DEFAULT '/')
RETURNS TABLE(scope_class text, reason text, rule_ord integer, tier text)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    -- An entity with no selector is not a scope question at all: an identity
    -- slot and a technology fingerprint have no address. They are NOT in scope
    -- (nothing may be sent *to* them), and the distinct reason keeps that
    -- separable from `unlisted` downstream.
    IF p_kind IS NULL THEN
        RETURN QUERY SELECT 'not_addressable'::text, 'not_addressable'::text,
                            NULL::integer, NULL::text;
        RETURN;
    END IF;
    -- Unknown kind RAISES. It must not fall through to zero rows: a LATERAL
    -- join over zero rows yields NULLs, and a NULL scope class is the same
    -- failure mode as an allow.
    IF p_kind NOT IN ('host', 'wildcard_domain') THEN
        RAISE EXCEPTION 'unknown entity selector kind %', p_kind;
    END IF;

    IF p_kind = 'host' THEN
        -- delegate, so there is one host evaluator in the system, not two
        RETURN QUERY SELECT * FROM scope_class_of(
            p_program, p_version, p_selector,
            coalesce(p_port, 443), p_path_raw, p_path_norm);
        RETURN;
    END IF;

    RETURN QUERY
    WITH nh AS (SELECT scope_normalize_host(p_selector) AS h),
    m AS (
        SELECT r.ord, r.effect, r.effect_rank, r.spec_kind, r.spec_len, r.tier
          FROM program_scope_rules r, nh
         WHERE nh.h IS NOT NULL
           AND r.program_id = p_program AND r.version = p_version
           -- a port- or path-qualified rule cannot describe a whole domain
           AND r.port IS NULL AND r.path_prefix IS NULL
           AND r.match_key IN (SELECT c.match_key
                                 FROM scope_wildcard_candidates(nh.h) c)
    ),
    win AS (
        SELECT m.* FROM m
         WHERE m.effect_rank = (SELECT min(effect_rank) FROM m)
         ORDER BY m.spec_kind DESC, m.spec_len DESC, m.ord ASC LIMIT 1
    ),
    tierpick AS (
        SELECT m.tier AS t FROM m
         WHERE m.effect = 'target' AND m.tier IS NOT NULL
         ORDER BY m.spec_kind DESC, m.spec_len DESC, m.ord ASC LIMIT 1
    )
    SELECT
        CASE WHEN (SELECT h FROM nh) IS NULL  THEN 'denied'
             WHEN w.effect IS NULL            THEN 'denied'
             WHEN w.effect = 'exclude'        THEN 'denied'
             WHEN w.effect = 'egress_support' THEN 'egress_support'
             ELSE 'target' END,
        CASE WHEN (SELECT h FROM nh) IS NULL  THEN 'malformed_host'
             WHEN w.effect IS NULL            THEN 'unlisted'
             WHEN w.effect = 'exclude'        THEN 'excluded'
             WHEN w.effect = 'egress_support' THEN 'matched_egress_support'
             ELSE 'matched_target' END,
        w.ord::integer,
        CASE WHEN w.effect = 'target' THEN
            coalesce((SELECT t FROM tierpick),
                     (SELECT sv.default_tier FROM program_scope_versions sv
                       WHERE sv.program_id = p_program
                         AND sv.version = p_version))
        END
      FROM (VALUES (1)) AS d(x) LEFT JOIN win w ON true;
END $$;

-- ===========================================================================
-- 6. The projection on `entities`
-- ===========================================================================

-- What the projection is computed FROM. Every entity that can be the subject of
-- a request must be able to say what address question it asks.
ALTER TABLE entities
    ADD COLUMN scope_selector_kind text
        CHECK (scope_selector_kind IN ('host','wildcard_domain')),
    ADD COLUMN scope_selector  text,
    ADD COLUMN scope_port      integer,
    ADD COLUMN scope_path_raw  text NOT NULL DEFAULT '/',
    ADD COLUMN scope_path_norm text NOT NULL DEFAULT '/',
    ADD COLUMN scope_class     text NOT NULL DEFAULT 'denied'
        CHECK (scope_class IN ('target','egress_support','denied','not_addressable')),
    ADD COLUMN scope_reason    text NOT NULL DEFAULT 'unlisted',
    ADD COLUMN scope_tier      text,
    ADD COLUMN scope_version_at integer,
    ADD CONSTRAINT entities_selector_pair
        CHECK ((scope_selector_kind IS NULL) = (scope_selector IS NULL)),
    -- An addressable entity type with no selector is not scope-decidable, and
    -- the old default made it in-scope anyway. Only the two types that have no
    -- address at all may omit one.
    ADD CONSTRAINT entities_addressable_types_carry_a_selector
        CHECK (scope_selector IS NOT NULL OR type IN ('identity','technology'));

-- THE DEFAULT WAS BACKWARDS. Ticket 06 shipped
-- `in_scope boolean NOT NULL DEFAULT true`, so a row inserted by recon was in
-- scope until something said otherwise, and nothing did: no trigger, no
-- generated column, no reference to any policy. Deny by default is the whole
-- premise of the grammar; it has to be the column default too.
ALTER TABLE entities ALTER COLUMN in_scope SET DEFAULT false;

-- The write guard. `in_scope` is a projected column, so the only way it may
-- change is by projecting. Without this, "scope" is a boolean any INSERT can
-- assert and the grammar is decoration.
CREATE FUNCTION entities_scope_is_projected() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF current_setting('rk2.scope_projection', true) = 'on' THEN
        RETURN NEW;
    END IF;
    IF TG_OP = 'INSERT' THEN
        IF NEW.in_scope OR NEW.scope_class <> 'denied' OR NEW.scope_tier IS NOT NULL THEN
            RAISE EXCEPTION
                'entities.in_scope/scope_class are projected from the scope '
                'policy; an entity is born denied. Call '
                'refresh_scope_projection(program_id) instead of asserting scope.';
        END IF;
    ELSIF NEW.in_scope IS DISTINCT FROM OLD.in_scope
       OR NEW.scope_class IS DISTINCT FROM OLD.scope_class
       OR NEW.scope_tier  IS DISTINCT FROM OLD.scope_tier
       OR NEW.scope_reason IS DISTINCT FROM OLD.scope_reason THEN
        RAISE EXCEPTION
            'entities.in_scope/scope_class are projected from the scope policy; '
            'direct writes are refused (use refresh_scope_projection)';
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER entities_scope_projected
    BEFORE INSERT OR UPDATE ON entities
    FOR EACH ROW EXECUTE FUNCTION entities_scope_is_projected();
ALTER TABLE entities ENABLE ALWAYS TRIGGER entities_scope_projected;

-- What the scheduler actually reads. Partial on `in_scope`, so the index holds
-- ONLY rows a ranking pass may act on: out-of-scope entities are not merely
-- filtered out, they are not in the structure being scanned. `label` is in the
-- key so the ordered read needs no sort, and `scope_tier` rides along so
-- ranking is an index-only scan.
CREATE INDEX entities_in_scope_idx
    ON entities (program_id, type, label)
    INCLUDE (scope_tier)
    WHERE in_scope;

-- ===========================================================================
-- 7. Recompute -- the answer to "what happens when scope changes mid-hunt"
--
-- A new immutable version, one refresh, and a report of every entity whose
-- class moved. Nothing is deleted: observations of a host that has just left
-- scope are the record of what we did while it was in scope, and destroying
-- them destroys the audit trail. What changes is forward eligibility.
-- ===========================================================================

CREATE FUNCTION refresh_scope_projection(p_program uuid)
RETURNS TABLE(entity_id uuid, label text, was_class text, now_class text)
LANGUAGE plpgsql AS $$
DECLARE ver integer;
BEGIN
    -- The projection is a runtime write and has to look like one. Ticket 07's
    -- emit_event trigger on `entities` raises when app.actor_kind is unset;
    -- setting it here would be the runtime forging its own provenance, so this
    -- function refuses instead.
    IF nullif(current_setting('app.actor_kind', true), '') IS NULL THEN
        RAISE EXCEPTION
            'refresh_scope_projection must run inside a runtime session '
            '(app.actor_kind unset)';
    END IF;

    SELECT p.scope_version INTO ver FROM programs p WHERE p.id = p_program;
    IF ver IS NULL THEN
        RAISE EXCEPTION 'program % has no live scope version', p_program;
    END IF;
    PERFORM set_config('rk2.scope_projection', 'on', true);

    RETURN QUERY
    WITH computed AS (
        SELECT e.id, e.label, e.scope_class AS old_class, v.*
          FROM entities e
          CROSS JOIN LATERAL scope_class_of_entity(
              e.program_id, ver, e.scope_selector_kind, e.scope_selector,
              e.scope_port, e.scope_path_raw, e.scope_path_norm) v
         WHERE e.program_id = p_program
    ), upd AS (
        UPDATE entities e
           SET in_scope        = (c.scope_class IN ('target','egress_support')),
               scope_class     = c.scope_class,
               scope_reason    = c.reason,
               scope_tier      = c.tier,
               scope_version_at = ver
          FROM computed c
         WHERE e.id = c.id
           -- Touch only what moves. Re-projecting at the same version is then a
           -- no-op that writes no rows and emits no events, so the scheduler can
           -- refresh as often as it likes without drowning the event log.
           AND (e.in_scope IS DISTINCT FROM (c.scope_class IN ('target','egress_support'))
             OR e.scope_class  IS DISTINCT FROM c.scope_class
             OR e.scope_reason IS DISTINCT FROM c.reason
             OR e.scope_tier   IS DISTINCT FROM c.tier
             OR e.scope_version_at IS DISTINCT FROM ver)
        RETURNING e.id, e.label, c.old_class, c.scope_class
    )
    SELECT * FROM upd WHERE old_class IS DISTINCT FROM scope_class;

    PERFORM set_config('rk2.scope_projection', 'off', true);
END $$;

-- Promote a version and reproject in one transaction. Returns every entity
-- whose class moved, which is exactly the list the scheduler must act on.
CREATE FUNCTION set_scope_version(p_program uuid, p_version integer)
RETURNS TABLE(entity_id uuid, label text, was_class text, now_class text)
LANGUAGE plpgsql AS $$
DECLARE cur integer;
BEGIN
    SELECT p.scope_version INTO cur FROM programs p WHERE p.id = p_program;
    IF cur IS NOT NULL AND p_version <= cur THEN
        RAISE EXCEPTION 'scope version must increase: live %, offered %',
              cur, p_version;
    END IF;
    UPDATE programs SET scope_version = p_version WHERE id = p_program;
    RETURN QUERY SELECT * FROM refresh_scope_projection(p_program);
END $$;

-- Convenience for callers: insert denied, then project. There is no code path
-- that creates an in-scope entity in one statement, on purpose.
CREATE FUNCTION add_entity(p_program uuid, p_type text, p_label text,
                           p_kind text, p_selector text,
                           p_port integer DEFAULT NULL,
                           p_dedup text DEFAULT NULL)
RETURNS uuid LANGUAGE plpgsql AS $$
DECLARE new_id uuid;
BEGIN
    INSERT INTO entities (program_id, type, label, dedup_key,
                          scope_selector_kind, scope_selector, scope_port)
    VALUES (p_program, p_type, p_label,
            coalesce(p_dedup, p_kind || ':' || coalesce(p_selector, p_label)),
            p_kind, p_selector, p_port)
    RETURNING id INTO new_id;
    PERFORM refresh_scope_projection(p_program);
    RETURN new_id;
END $$;

-- ===========================================================================
-- 8. Ticket 35's model must still hold, or this migration does not finish
-- ===========================================================================

DO $$
DECLARE n integer; d text;
BEGIN
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_program_isolation();
    IF n > 0 THEN
        RAISE EXCEPTION '021 breaks program isolation (% problems): %', n, d;
    END IF;
END $$;
