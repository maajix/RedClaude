-- ===========================================================================
-- Production harness 08 -- one compiled Scope Policy, asked the same question
-- from SQL and from Python
-- ===========================================================================
-- 021 built the storage and the evaluator for a scope grammar and then left
-- both unreachable: nothing writes `program_scope_versions`, `programs.
-- scope_version` is NULL for every Program that exists, and with it NULL every
-- entity projects to denied. That is a safe failure, and it is still a failure
-- -- a policy nothing compiles is a policy nothing enforces.
--
-- `scope.py` is the compiler. It turns the operator's TOML into rows and it is
-- the only thing in the system that parses a pattern. This file is the other
-- half: the rows those decisions live in, and an evaluator that reaches the
-- same verdict from them. Four changes, each of them a place where the two
-- halves could otherwise answer differently.
--
--   * Protocol becomes a rule dimension. 021's rules carried a port and a path
--     and no scheme, so a policy naming https had no way to say so and an
--     http request to a listed host matched anyway. The compiler expands the
--     configuration's protocol list into rows; the evaluator filters on it.
--
--   * The evaluator takes the question being asked. A request, the coverage of
--     a host and the coverage of a whole subtree are three questions, and they
--     want three path polarities: a request must be under the prefix by both
--     spellings, while a host with no path is covered when the prefix and the
--     path are in a prefix relationship either way round. 021 collapsed them,
--     and the collapse is why `scope_class_of_entity` required
--     `port IS NULL AND path_prefix IS NULL` -- a condition no compiled rule
--     can satisfy, so every wildcard entity was denied whatever the policy
--     said. Exclusions keep the polarity they had: either spelling is enough,
--     because breadth withdraws authority.
--
--   * The five Rules of Engagement become columns on the version. They are the
--     `[rules_of_engagement]` keys, spelled identically, so a sixth control
--     added to the loader cannot be silently dropped here: it has no column and
--     the compiler writing it fails. Absent is false, and false is a denial --
--     `decide_action` withholds rather than defaults.
--
--   * Required headers become a table whose values are not on the agent's read
--     surface. The name is registered in `state_read_surface`, the reference is
--     not, and `check_state_grants()` then refuses any grant that would make it
--     readable. The table emits no event either, so the reference is in one
--     place rather than in two with a redaction rule over the second.
--     "Runtime-owned" is a grant, not a convention.
--
-- What this file does NOT build: DNS. Nothing here resolves a name, and
-- nothing may -- a scope verdict that depends on what a resolver said today is
-- a verdict that changes under a policy nobody rewrote. The proxy checks the
-- peer address it actually connected to, and that check can only narrow this
-- one.
-- ===========================================================================


-- ---------------------------------------------------------------------------
-- 1. Protocol is a rule dimension
-- ---------------------------------------------------------------------------
-- Added with a default and then stripped of it. The default exists so the
-- statement is legal against a corpus that may hold rows; dropping it means a
-- later INSERT that forgets the scheme fails instead of quietly authorising
-- the one this line happened to pick.

ALTER TABLE program_scope_rules
    ADD COLUMN protocol text NOT NULL DEFAULT 'https';
ALTER TABLE program_scope_rules ALTER COLUMN protocol DROP DEFAULT;
ALTER TABLE program_scope_rules ADD CONSTRAINT scope_rules_protocol_check
    CHECK (protocol IN ('http', 'https'));

COMMENT ON COLUMN program_scope_rules.protocol IS
  'The scheme this rule authorises. One row per protocol: the compiler expands the configuration''s list, so the evaluator compares rather than parses.';

-- The lookup index carries it too, or every protocol filter is a heap fetch.
DROP INDEX scope_rules_key_idx;
CREATE INDEX scope_rules_key_idx
    ON program_scope_rules (program_id, version, match_key)
    INCLUDE (effect_rank, spec_kind, spec_len, tier, protocol, port, path_prefix);


-- ---------------------------------------------------------------------------
-- 2. The Rules of Engagement, and the configuration the version came from
-- ---------------------------------------------------------------------------
-- Columns, not a jsonb reach into `policy`. A permission that is a column is a
-- permission a view can be granted, a check can read and a typo cannot invent:
-- `policy->'roe'->>'mutaton'` is NULL, and NULL read as a boolean is the
-- permissive default this ticket exists to remove.
--
-- ALTER TABLE is DDL, so `scope_versions_immutable` -- a row trigger -- does
-- not fire. The append-only rule is about what a statement may say about a
-- version already written, and this statement says nothing about any row.

ALTER TABLE program_scope_versions
    ADD COLUMN availability_impact   boolean NOT NULL DEFAULT false,
    ADD COLUMN credential_use        boolean NOT NULL DEFAULT false,
    ADD COLUMN mutation              boolean NOT NULL DEFAULT false,
    ADD COLUMN pivoting              boolean NOT NULL DEFAULT false,
    ADD COLUMN sensitive_data_access boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN program_scope_versions.mutation IS
  'One of the five Rules of Engagement, named exactly as the configuration key. False is a denial, not an absence: a scope version that says nothing about mutation forbids it.';

-- Which configuration revision compiled to this version. Nullable, because the
-- FK is the guarantee that a stated revision is a real one and the standing
-- check below is the guarantee that the LIVE version states one; making the
-- column itself mandatory would only move the same failure earlier for rows
-- that authorise nothing.
ALTER TABLE program_scope_versions ADD COLUMN configuration_revision integer;
ALTER TABLE program_scope_versions
    ADD CONSTRAINT scope_versions_configuration_fkey
    FOREIGN KEY (program_id, configuration_revision)
    REFERENCES program_configurations (program_id, revision);

COMMENT ON COLUMN program_scope_versions.configuration_revision IS
  'The configuration revision this version was compiled from. Two sequences joined by a column rather than one number serving both: the case that separates them is the compiler changing while the operator''s file does not, which is a change in what the policy means and therefore a new version.';


-- ---------------------------------------------------------------------------
-- 3. Required headers: names readable, references not
-- ---------------------------------------------------------------------------
-- A program that requires `X-Bounty-Id` on every request is stating a fact the
-- agent may need to reason about -- which header identifies us -- and a
-- secret it must never hold: what the header says. Two columns, two
-- privileges.

CREATE TABLE program_required_headers (
    program_id uuid    NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    version    integer NOT NULL,
    ord        integer NOT NULL CHECK (ord >= 1),
    -- RFC 9110 field name: token characters only, and no colon or whitespace,
    -- so a "header" cannot smuggle a second one.
    name       text    NOT NULL CHECK (name ~ '^[A-Za-z0-9!#$%&''*+.^_`|~-]{1,64}$'),
    -- A `slot://` reference. The loader already refuses an inline value; this
    -- column holds the pointer, and the pointer is what stays runtime-owned.
    value_ref  text    NOT NULL CHECK (value_ref <> ''),
    PRIMARY KEY (program_id, version, ord),
    FOREIGN KEY (program_id, version)
        REFERENCES program_scope_versions (program_id, version)
);

-- Field names are case-insensitive, so the same header named twice in two
-- spellings is one header stated twice, and which value wins would be decided
-- by row order.
CREATE UNIQUE INDEX program_required_headers_name_idx
    ON program_required_headers (program_id, version, lower(name));

COMMENT ON TABLE program_required_headers IS
  'The headers a Program requires on every request, per scope version. Immutable with the version. `name` is on the agent read surface and `value_ref` is not.';

COMMENT ON COLUMN program_required_headers.value_ref IS
  'A slot reference the runtime resolves. Never granted to rk2_state and never in an event, so neither a query nor the event log yields the value.';

CREATE TRIGGER required_headers_immutable
    BEFORE UPDATE OR DELETE ON program_required_headers
    FOR EACH ROW EXECUTE FUNCTION reject_mutation_unless_purging();
-- 021's lesson: `session_replication_role = replica` skips ORIGIN triggers,
-- and a restore is exactly when an append-only table would be rewritten.
ALTER TABLE program_required_headers
    ENABLE ALWAYS TRIGGER required_headers_immutable;

INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
    ('program_required_headers', 'program_id', 'program-scoped: the purge root');

-- Exempt, for the same reason and in the same words as its two siblings: this
-- is compiled output, not a decision. `program.configured` already records the
-- revision every header row is derived from, and the digest on the scope
-- version says which compilation produced them. An event per header would log
-- the same fact once per row and would put `value_ref` somewhere a redaction
-- rule has to keep removing it, rather than nowhere.
INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
    ('program_required_headers', 'reference',
     'the headers of a scope version; immutable with it and compiled from the revision that does emit', 'ph2-08');

-- The read surface: four columns of five. Registering `value_ref` here is the
-- one edit that would make it readable, and rule 4 of the check below refuses
-- exactly that edit.
INSERT INTO state_read_surface (table_name, column_name, added_by) VALUES
    ('program_required_headers', 'program_id', 'ph2-08'),
    ('program_required_headers', 'version',    'ph2-08'),
    ('program_required_headers', 'ord',        'ph2-08'),
    ('program_required_headers', 'name',       'ph2-08');


-- ---------------------------------------------------------------------------
-- 4. The evaluator
-- ---------------------------------------------------------------------------
-- DROP and CREATE, not CREATE OR REPLACE: the argument list changes, and
-- REPLACE cannot change one. Adding the arguments as a second overload would
-- be worse than either -- two evaluators reachable by the same name, with the
-- old one silently chosen by any caller that passes the old five.
--
-- The two new arguments go on the END of 021's list, and that placement is the
-- whole of the compatibility story. `gate_tool_call` (026) and
-- `authorize_egress_request` (039) both call the six-argument shape
-- positionally, both are plpgsql, and PostgreSQL tracks no dependency through a
-- plpgsql body: a signature that put `p_protocol` in the middle would drop out
-- from under them, commit green, and fail at the first gated tool call with
-- "function scope_class_of(uuid, integer, text, integer, text, text) does not
-- exist" -- there being no implicit integer-to-text cast to resolve it against.
-- Ordered this way their calls resolve to the first six parameters exactly, and
-- the defaults answer for the rest: any protocol, and the request question.

-- Whether a path is at or below a prefix, ending on a segment boundary.
-- Mirrors scope.path_under. `starts_with` alone would make the prefix `/v1`
-- authorise `/v1-internal/dump`.
CREATE FUNCTION scope_path_under(p_path text, p_prefix text) RETURNS boolean
LANGUAGE sql IMMUTABLE AS $$
    SELECT starts_with(p_path, p_prefix)
       AND (right(p_prefix, 1) = '/'
            OR length(p_path) = length(p_prefix)
            OR substr(p_path, length(p_prefix) + 1, 1) = '/')
$$;

-- The question vocabulary, asserted rather than assumed. Every other closed
-- vocabulary in this system raises on a word it does not know, and this one has
-- to as well: the two coverage polarities are the wide readings, so a caller
-- that mistyped `request` would be answered under the widest one and read it as
-- an authorisation. The matcher below also fails closed on an unknown word, so
-- the two guards cover each other.
CREATE FUNCTION scope_assert_question(p_question text) RETURNS boolean
LANGUAGE plpgsql IMMUTABLE AS $$
BEGIN
    IF p_question IS NULL OR p_question NOT IN ('request', 'coverage', 'subtree') THEN
        RAISE EXCEPTION 'unknown scope question %', coalesce(p_question, '(null)');
    END IF;
    RETURN true;
END $$;

-- Three shapes 021 read as addresses and this file does not, each because
-- PostgreSQL and Python disagreed about it:
--
--   * `db`, `cafe`, `ec2` matched `^[0-9a-f:]+$` with no colon in them, so an
--     ordinary single-label name was cast to inet, refused, and reported as a
--     malformed address. A colon is now required.
--   * `093.184.216.34` is an address to inet, which reads the octet as decimal
--     and returns 93.184.216.34; Python's ipaddress refuses a leading zero
--     outright. Refused here too, so neither side canonicalises what the other
--     rejects.
--   * `::102:304` renders as `::1.2.3.4` through host() and as `::102:304`
--     through Python. Same address, two match keys, so a rule compiled from one
--     spelling covers nothing written in the other. The deprecated
--     IPv4-compatible range is refused on both sides instead.
CREATE OR REPLACE FUNCTION scope_normalize_host(raw text) RETURNS text
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

    IF v ~ '^[0-9]{1,3}(\.[0-9]{1,3}){3}$' OR v ~ '^[0-9a-f]*:[0-9a-f:]*$'
       OR v ~ '^::ffff:[0-9]{1,3}(\.[0-9]{1,3}){3}$' THEN
        IF v ~ '(^|\.)0[0-9]' THEN
            RETURN NULL;                       -- '093.184.216.34'
        END IF;
        BEGIN
            a := v::inet;
            IF family(a) = 6 AND host(a) LIKE '::ffff:%.%' THEN
                RETURN split_part(host(a), ':', 4);
            END IF;
            IF family(a) = 6 AND a << inet '::/96'
               AND host(a) NOT IN ('::', '::1') THEN
                RETURN NULL;                   -- '::1.2.3.4', '::102:304'
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

-- Which refusal a host earned. `scope_normalize_host` returns NULL for both
-- "there was no host" and "the host was malformed", and scope.py distinguishes
-- them, so the fixture matrix would disagree on reason while agreeing on
-- verdict. One function, so the distinction is made in one place.
CREATE FUNCTION scope_host_problem(raw text) RETURNS text
LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE v text;
BEGIN
    IF raw IS NULL THEN RETURN 'no_host'; END IF;
    v := rtrim(lower(btrim(raw)), '.');
    IF v LIKE '[%]' THEN v := substring(v from 2 for length(v) - 2); END IF;
    IF v = '' THEN RETURN 'no_host'; END IF;
    RETURN 'malformed_host';
END $$;

DROP FUNCTION scope_class_of(uuid, integer, text, integer, text, text);

CREATE FUNCTION scope_class_of(
    p_program   uuid,
    p_version   integer,
    p_host      text,
    -- NULL means "any", in both cases, and both defaults are NULL because the
    -- caller that leaves them out is asking about a host rather than about a
    -- request. 021 defaulted the port to 443, which answered a narrower
    -- question than the caller asked and denied every entity on a policy that
    -- also listed port 80.
    p_port      integer DEFAULT NULL,
    p_path_raw  text    DEFAULT '/',
    p_path_norm text    DEFAULT '/',
    p_protocol  text    DEFAULT NULL,
    -- 'request' | 'coverage' | 'subtree'. Mirrors scope.QUESTIONS.
    p_question  text    DEFAULT 'request')
RETURNS TABLE(scope_class text, reason text, rule_ord integer, tier text)
LANGUAGE sql STABLE AS $$
    WITH nh AS (SELECT scope_normalize_host(p_host) AS h,
                       scope_assert_question(p_question) AS asked),
    m AS (
        SELECT r.ord, r.effect, r.effect_rank, r.spec_kind, r.spec_len, r.tier
          FROM program_scope_rules r, nh
         WHERE nh.h IS NOT NULL
           AND r.program_id = p_program AND r.version = p_version
           AND (
                -- A subtree question asks whether a whole domain is covered,
                -- and only a wildcard rule can cover one: an exact rule stores
                -- a bare host, and no candidate here is bare.
                -- No ELSE that matches: an unknown question matches nothing and
                -- is denied, rather than falling into the widest polarity.
                CASE p_question
                     WHEN 'subtree'
                     THEN r.match_key IN (SELECT c.match_key
                                            FROM scope_wildcard_candidates(nh.h) c)
                     WHEN 'request'
                     THEN r.match_key IN (SELECT c.match_key
                                            FROM scope_host_candidates(nh.h) c)
                     WHEN 'coverage'
                     THEN r.match_key IN (SELECT c.match_key
                                            FROM scope_host_candidates(nh.h) c)
                     ELSE false
                     END
             OR (p_question <> 'subtree' AND r.pattern_kind = 'cidr'
                 AND r.net >>= (CASE WHEN nh.h ~ '^([0-9.]+|[0-9a-f:]+)$'
                                     THEN nh.h END)::inet)
           )
           AND (p_protocol IS NULL OR r.protocol = p_protocol)
           AND (r.port IS NULL OR p_port IS NULL OR r.port = p_port)
           -- Three polarities, same as scope.Rule.matches:
           --   exclude   -- either spelling under the prefix withdraws
           --   request   -- both spellings must be under it, so a traversal
           --                that normalises out of the authorised subtree is
           --                not authorised by its raw form
           --   coverage  -- a prefix relationship either way round, because
           --   /subtree    the question is whether the rule and the subject
           --                overlap at all, not whether one request is inside
           AND (r.path_prefix IS NULL
                OR CASE WHEN r.effect = 'exclude'
                        THEN scope_path_under(p_path_raw,  r.path_prefix)
                          OR scope_path_under(p_path_norm, r.path_prefix)
                        WHEN p_question = 'request'
                        THEN scope_path_under(p_path_raw,  r.path_prefix)
                         AND scope_path_under(p_path_norm, r.path_prefix)
                        WHEN p_question IN ('coverage', 'subtree')
                        THEN scope_path_under(p_path_raw,  r.path_prefix)
                          OR scope_path_under(r.path_prefix, p_path_raw)
                        ELSE false
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
        CASE WHEN (SELECT h FROM nh) IS NULL      THEN scope_host_problem(p_host)
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

COMMENT ON FUNCTION scope_class_of(uuid, integer, text, integer, text, text, text, text) IS
  'The verdict for one address question. Deny by default, lowest effect rank wins over every match, and specificity picks only which rule is cited.';

-- The verdict for a stored ENTITY. Both selector kinds now delegate: the
-- second body 021 wrote for wildcards is gone, and with it the possibility
-- that the two disagree.
CREATE OR REPLACE FUNCTION scope_class_of_entity(
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

    -- An entity states no protocol: it is a thing, not a request. Passing NULL
    -- asks whether ANY listed protocol reaches it, which is what "is this host
    -- in scope" means.
    RETURN QUERY SELECT * FROM scope_class_of(
        p_program, p_version, p_selector, p_port,
        p_path_raw, p_path_norm, NULL,
        CASE WHEN p_kind = 'host' THEN 'coverage' ELSE 'subtree' END);
END $$;

COMMENT ON FUNCTION scope_class_of_entity(uuid, integer, text, text, integer, text, text) IS
  'The verdict for a stored entity. Dispatches on selector kind into the one evaluator: a host asks about coverage, a wildcard seed asks about a subtree.';


-- ---------------------------------------------------------------------------
-- 5. The invariants this file introduces
-- ---------------------------------------------------------------------------

CREATE FUNCTION check_scope_policy()
RETURNS TABLE (problem text, object text, detail text)
LANGUAGE sql STABLE AS $$
    -- 1. A Program that compiled a policy and is running none. Every entity
    --    projects to denied, which is safe and is also indistinguishable from
    --    a policy that lists nothing -- the operator wrote a scope and the
    --    harness is not enforcing it.
    --
    --    Deliberately NOT "has a configuration and has no version". That reads
    --    like the stronger invariant and is a deadlock: a database written
    --    before this file exists holds configured Programs with no scope
    --    version, `rk run` gates on the standing family before it writes
    --    anything, and the only code that can compile a policy runs after the
    --    gate. The check would refuse the run that would satisfy it, and the
    --    terminal assertion in this file would refuse the migration too. What
    --    is asserted instead is a state nothing honest produces: a version was
    --    written and never promoted. A legacy Program enters the invariant the
    --    first time it is resumed, because every answer that keeps a Program
    --    open now compiles and promotes.
    SELECT 'scope_version_not_promoted', p.slug,
           'the Program has compiled scope versions but programs.scope_version is NULL; every entity is denied'
      FROM programs p
     WHERE p.scope_version IS NULL
       AND EXISTS (SELECT 1 FROM program_scope_versions sv WHERE sv.program_id = p.id)
  UNION ALL
    -- 2. The live version was compiled from a revision that is no longer the
    --    newest. The operator changed the file, the revision was recorded, and
    --    the rules being enforced are the previous ones.
    SELECT 'scope_version_not_current', p.slug,
           'live scope version ' || p.scope_version || ' compiled from revision ' ||
           coalesce(sv.configuration_revision::text, '(none)') ||
           ', but the newest configuration revision is ' || c.revision
      FROM programs p
      JOIN program_scope_versions sv
        ON sv.program_id = p.id AND sv.version = p.scope_version
      JOIN LATERAL (SELECT revision FROM program_configurations
                     WHERE program_id = p.id
                     ORDER BY revision DESC LIMIT 1) c ON true
     WHERE sv.configuration_revision IS DISTINCT FROM c.revision
  UNION ALL
    -- 3. The compiled policy does not name the bytes it was compiled from. The
    --    version number matching is not enough: the digest is what makes
    --    "these rules are that file" checkable after the fact.
    SELECT 'scope_policy_digest_mismatch', p.slug || ' version ' || sv.version,
           'policy states configuration_sha256 ' ||
           coalesce(sv.policy->>'configuration_sha256', '(none)') ||
           ' but revision ' || c.revision || ' hashes to ' || c.canonical_sha256
      FROM programs p
      JOIN program_scope_versions sv
        ON sv.program_id = p.id AND sv.version = p.scope_version
      JOIN program_configurations c
        ON c.program_id = p.id AND c.revision = sv.configuration_revision
     WHERE sv.policy->>'configuration_sha256' IS DISTINCT FROM c.canonical_sha256
  UNION ALL
    -- 4. A required header's value reference became readable. The grant is the
    --    redaction; check_state_grants() enforces the registry, and this rule
    --    enforces what may enter it.
    SELECT 'header_value_is_readable', 'program_required_headers.' || s.column_name,
           'the agent read surface must carry header names only; the reference resolves to a runtime-owned secret'
      FROM state_read_surface s
     WHERE s.table_name = 'program_required_headers'
       AND s.column_name = 'value_ref'
  UNION ALL
    -- 5. A live version with no rules. Deny-by-default makes this safe and
    --    silent: the Program looks configured, every request is refused as
    --    `unlisted`, and the reason is that the compiler wrote a header row
    --    and no body.
    SELECT 'scope_version_has_no_rules', p.slug || ' version ' || sv.version,
           'the live scope version compiled to zero rules; every address is denied as unlisted'
      FROM programs p
      JOIN program_scope_versions sv
        ON sv.program_id = p.id AND sv.version = p.scope_version
     WHERE NOT EXISTS (SELECT 1 FROM program_scope_rules r
                        WHERE r.program_id = sv.program_id
                          AND r.version = sv.version)
$$;

COMMENT ON FUNCTION check_scope_policy() IS
  'Every Program that compiled a policy runs the compiled form of its newest revision, the compiled form names the bytes it came from and has rules, and no required-header value is readable by the agent.';

INSERT INTO standing_checks (name, query, owner_ticket, note) VALUES
    ('scope_policy', 'SELECT * FROM check_scope_policy()', 'ph2-08',
     'the live scope version is the newest configuration compiled, it names the bytes it came from, and required-header values stay off the agent read surface');


-- ---------------------------------------------------------------------------
-- 6. Bring the invariants to true for the corpus as it stands
-- ---------------------------------------------------------------------------

SELECT apply_state_rls();
SELECT apply_state_grants();


-- ---------------------------------------------------------------------------
-- 7. This file's own rule, or it does not finish
-- ---------------------------------------------------------------------------
-- Two assertions, because the two halves of the redaction fail differently. A
-- grant is a privilege the catalogue can be asked about directly; the
-- evaluator's agreement with scope.py cannot be asserted here at all and is
-- the fixture matrix's job.

DO $$
DECLARE n integer; d text;
BEGIN
    IF has_column_privilege('rk2_state', 'program_required_headers', 'value_ref', 'SELECT') THEN
        RAISE EXCEPTION
            'rk2_state can read program_required_headers.value_ref; the header '
            'value is runtime-owned and the grant is what says so';
    END IF;
    IF NOT has_column_privilege('rk2_state', 'program_required_headers', 'name', 'SELECT') THEN
        RAISE EXCEPTION
            'rk2_state cannot read program_required_headers.name; the agent has '
            'to be able to say which header identifies it';
    END IF;

    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_scope_policy();
    IF n > 0 THEN
        RAISE EXCEPTION 'scope policy invariants broken (% problems): %', n, d;
    END IF;
END $$;
