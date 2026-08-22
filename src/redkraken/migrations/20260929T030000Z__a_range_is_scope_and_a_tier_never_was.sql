-- ---------------------------------------------------------------------------
-- 20260929T030000Z__a_range_is_scope_and_a_tier_never_was.sql
--                                                                  (ticket 117)
--
-- 021 built three things nothing could reach. This file keeps one of them and
-- removes the other two, and the two halves are answered differently because
-- they fail at different places.
--
-- THE ADDRESS RANGE STAYS, AND THE COMPILER NOW WRITES IT.
--
-- `program_scope_rules` has carried `net cidr` since 021, with a `'cidr'` arm in
-- the `pattern_kind` CHECK (`:86`), a pair of CHECKs asserting both directions
-- of "a CIDR rule has a net and no match_key" (`:109-110`), a partial GiST index
-- over it (`:119-121`), and a containment arm in the live classifier
-- (`20260810T193000Z...:341-343`). None of it was dead code: it was working code
-- with no writer. `src/redkraken/program.py` wrote thirteen columns and `net`
-- was not among them, because `scope.parse_pattern` produced exactly two kinds,
-- and it produced two kinds because `config.load` refused the string
-- `10.0.0.0/8` before the compiler ever saw it.
--
-- The sentence that settles it is in the function the ranges were built for.
-- `authorize_egress_address` re-decides the destination as the literal address
-- the proxy pinned, and asks the coverage question with this reason
-- (`20260810T231500Z...:110-116`): "A withdrawal is asked about the machine: an
-- operator who excluded a network excluded it, and an address that is only out
-- of bounds for one path was already refused -- or allowed -- by name, at the
-- decision this one sits behind." That gate ships, it is granted to `rk2_proxy`,
-- the proxy calls it on every request, and the only rule kind that can express
-- "a network" was the one no configuration could produce. The arm is the second
-- half of a two-gate design whose first half is complete.
--
-- Ranges are also the ordinary shape of a real scope. A single address is
-- already expressible, so a Program scoped to `203.0.113.0/24` was expressible
-- as 256 configuration entries and a Program scoped to a /16, or to any IPv6
-- range, was not expressible at all. Deleting the arm would have been choosing
-- that as the answer.
--
-- The schema needs nothing for this. What changed is Python, in four places --
-- the loader grammar, `scope.parse_pattern` and the three `Pattern` properties
-- that assumed a host, `Rule.row()`, and the column list in `program.py` -- and
-- section 1 below is the two column comments that say so, because a reader
-- meeting `net` in the live schema needs to know it is written now. Section 3
-- is the proof, and it is here rather than in a test because the end-to-end
-- claim -- a range rule inserts, and an Entity reached by an address inside it
-- projects to `target` -- has no test file this change owns.
--
-- Two things the range deliberately does not do, both of them decided
-- elsewhere and both of them mirrored on the Python side rather than argued
-- again. A range decides addresses and never names: the containment arm only
-- fires when the host asked about is an address literal, because the door
-- decides before it resolves -- "So the order is decide, then resolve, then
-- dial" -- and a policy that admitted `www.example.com` because its address
-- fell in a range would be a policy that depended on what a resolver said
-- today. And a range mints no configured subject:
-- `record_configured_subjects` filters `AND r.pattern_kind = 'exact'`
-- (`20260831T000000Z...:203`) and is untouched here, so a Program scoped only by
-- range opens with nothing to hunt, exactly as a Program scoped only by
-- `*.example.com` does today. That is the existing precedent and the range joins
-- it; whether an operator should be warned at compile time is ticket 83's.
--
-- THE EFFORT TIER COMES OUT, AND SO DOES `allow_private_ips`.
--
-- `program_scope_rules.tier` (`021:94`) and `program_scope_versions.default_tier`
-- (`021:42`) fail one step further along than the range did. `tier` is never set
-- on a rule and `default_tier` is never set on a version, so both arms of the
-- coalesce in `scope_class_of` (`20260810T193000Z...:394-399`) are NULL for
-- every verdict, `refresh_scope_projection` writes NULL into
-- `entities.scope_tier` for every Entity, `CHECK (tier IS NULL OR effect =
-- 'target')` can never fail, and `v_records` publishes `"scope_tier": null` in
-- every Entity payload the model reads. Nothing consumes the published value:
-- no ranker, no scheduler, and no Python -- `grep -rn "scope_tier"` over
-- `src/redkraken/*.py`, `tests/` and `tools/` returns nothing at all.
--
-- A policy that is declared, projected, published and always NULL is worse than
-- one that is absent, because a reader cannot tell the two apart: `null` here
-- reads as "this Entity has no tier" and means "this system has no tiers".
-- Unlike the range half there is no second gate waiting for it. If effort policy
-- is wanted later it belongs where effort is actually spent -- the budget and
-- lane tables -- and not on a scope rule, which is a statement about authority.
-- Nothing is preserved for it here, including the comment at `021:112` that says
-- the CHECK "mirrors the Python compiler": there is nothing in the Python
-- compiler to mirror and there never was.
--
-- `allow_private_ips` (`021:95`) is a prototype vestige whose job was taken by
-- something stricter. It was a per-rule opt-out in v1's policy engine, and v2
-- replaced it with an unconditional deny-by-default at the door --
-- `scope.address_refusal` and `proxy.unroutable`, whose docstring says "an
-- address is dialled because it is one the public internet routes to, not
-- because it failed to match a list of bad ones". The evaluation case that
-- genuinely needs a private address does not go through it either; that is
-- `authorize_fixture_address`, a separate question with its own table. A boolean
-- that would let a rule re-open what the door closes should not survive as a
-- column, and it has no writer, no reader and no occurrence anywhere in `src/`
-- but its own declaration.
--
-- WHAT REMOVING FOUR COLUMNS COSTS, WHICH IS FIVE OBJECTS RE-ISSUED IN FULL.
--
-- `tier` is in the INCLUDE list of `scope_rules_key_idx` and `scope_tier` is in
-- the INCLUDE list of `entities_in_scope_idx`, so both indexes are dropped and
-- rebuilt rather than left for `DROP COLUMN` to delete outright.
-- `scope_class_of` and `scope_class_of_entity` return `tier` as their fourth
-- output column, which is a change of signature and therefore a DROP and a
-- CREATE rather than a REPLACE; every caller in the corpus selects its columns
-- by name and none selects that one, and the two calls that select `*` are the
-- two rebuilt here. `entities_scope_is_projected` and `refresh_scope_projection`
-- name the column in their bodies, and `v_records` names it in a
-- `jsonb_build_object`, which is what makes a view depend on a column. All five
-- are re-issued as they stand with the tier limbs cut out and nothing else
-- touched, because a re-issue that also improved something would be a change
-- nobody could review against this ticket. A sixth thing goes with them, and it
-- is a row rather than an object: `state_read_surface` names
-- `entities.scope_tier` as part of the agent read surface, and
-- `check_state_grants()` fails a row whose column no longer exists, so section
-- 2f deletes it.
--
-- Depends on 021 (all four columns, both indexes, the guard and the
-- projection), 20260810T193000Z (the live evaluator and the key index) and
-- 20260814T080000Z (the live `v_records`). A new file rather than an edit to any
-- of them: a recorded migration whose file has changed is schema drift and `rk
-- db migrate` refuses the whole corpus for it.
-- ---------------------------------------------------------------------------


-- ===========================================================================
-- 1. The range arm has a writer, said where a reader of the schema meets it
-- ===========================================================================

-- No constraint moves here and none needs to: `pattern_kind` has admitted
-- `cidr` since 021 and the paired CHECKs have asserted the `net`/`match_key`
-- exclusivity since 021. What changes is that something now produces one, and
-- that is a fact about the column a `--` comment in a migration file cannot
-- carry.

COMMENT ON COLUMN program_scope_rules.pattern_kind IS
 'How this rule is matched, closed to three. `exact` and `wildcard` are keys: the evaluator joins match_key by equality against the candidate series a host expands to, and parses nothing. `cidr` is an address range and is decided by containment on net instead, which is why the two CHECKs beside it assert that exactly one of the two columns is set. All three are written by scope.compile_policy and by nothing else; SQL never parses a pattern.';

COMMENT ON COLUMN program_scope_rules.net IS
 'The address range a cidr rule authorises or withdraws, written by scope.Rule.row() and NULL on every other kind. It decides addresses and never names: the containment arm in scope_class_of fires only when the host being asked about is an address literal, because the door decides before it resolves and a verdict that depended on what a resolver answered today would be a verdict that changed under a policy nobody rewrote. A subtree question never reaches it either -- a range is not a domain and cannot cover one. An inclusion naming a range that is not globally routable is refused at compile time by the same rule the egress door applies to a single address.';


-- ===========================================================================
-- 2. The effort tier, out of the evaluator, the projection and the payload
-- ===========================================================================

-- 2a. The evaluator. Dropped and recreated because the output column list is
-- part of the signature; the bodies are 20260810T193000Z's with the `tier`
-- selection, the `tierpick` CTE and the `default_tier` fallback removed.

DROP FUNCTION scope_class_of_entity(uuid, integer, text, text, integer, text, text);
DROP FUNCTION scope_class_of(uuid, integer, text, integer, text, text, text, text);

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
RETURNS TABLE(scope_class text, reason text, rule_ord integer)
LANGUAGE sql STABLE AS $$
    WITH nh AS (SELECT scope_normalize_host(p_host) AS h,
                       scope_assert_question(p_question) AS asked),
    m AS (
        SELECT r.ord, r.effect, r.effect_rank, r.spec_kind, r.spec_len
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
        w.ord::integer
    -- LEFT JOIN so the no-match case still returns exactly one row. A scope
    -- evaluator that can return zero rows fails open the first time a caller
    -- writes `IF NOT FOUND`.
      FROM (VALUES (1)) AS d(x) LEFT JOIN win w ON true
$$;

COMMENT ON FUNCTION scope_class_of(uuid, integer, text, integer, text, text, text, text) IS
  'The verdict for one address question. Deny by default, lowest effect rank wins over every match, and specificity picks only which rule is cited.';

CREATE FUNCTION scope_class_of_entity(
    p_program uuid, p_version integer,
    p_kind text, p_selector text,
    p_port integer DEFAULT NULL,
    p_path_raw text DEFAULT '/', p_path_norm text DEFAULT '/')
RETURNS TABLE(scope_class text, reason text, rule_ord integer)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    -- An entity with no selector is not a scope question at all: an identity
    -- slot and a technology fingerprint have no address. They are NOT in scope
    -- (nothing may be sent *to* them), and the distinct reason keeps that
    -- separable from `unlisted` downstream.
    IF p_kind IS NULL THEN
        RETURN QUERY SELECT 'not_addressable'::text, 'not_addressable'::text,
                            NULL::integer;
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
-- 2b. The write guard and the projection. 021's bodies, with the two clauses
-- that mention `scope_tier` removed. The guard keeps its subject: `in_scope`
-- and `scope_class` are projected columns and an entity is still born denied.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION entities_scope_is_projected() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF current_setting('rk2.scope_projection', true) = 'on' THEN
        RETURN NEW;
    END IF;
    IF TG_OP = 'INSERT' THEN
        IF NEW.in_scope OR NEW.scope_class <> 'denied' THEN
            RAISE EXCEPTION
                'entities.in_scope/scope_class are projected from the scope '
                'policy; an entity is born denied. Call '
                'refresh_scope_projection(program_id) instead of asserting scope.';
        END IF;
    ELSIF NEW.in_scope IS DISTINCT FROM OLD.in_scope
       OR NEW.scope_class IS DISTINCT FROM OLD.scope_class
       OR NEW.scope_reason IS DISTINCT FROM OLD.scope_reason THEN
        RAISE EXCEPTION
            'entities.in_scope/scope_class are projected from the scope policy; '
            'direct writes are refused (use refresh_scope_projection)';
    END IF;
    RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION refresh_scope_projection(p_program uuid)
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
               scope_version_at = ver
          FROM computed c
         WHERE e.id = c.id
           -- Touch only what moves. Re-projecting at the same version is then a
           -- no-op that writes no rows and emits no events, so the scheduler can
           -- refresh as often as it likes without drowning the event log.
           AND (e.in_scope IS DISTINCT FROM (c.scope_class IN ('target','egress_support'))
             OR e.scope_class  IS DISTINCT FROM c.scope_class
             OR e.scope_reason IS DISTINCT FROM c.reason
             OR e.scope_version_at IS DISTINCT FROM ver)
        RETURNING e.id, e.label, c.old_class, c.scope_class
    )
    SELECT * FROM upd WHERE old_class IS DISTINCT FROM scope_class;

    PERFORM set_config('rk2.scope_projection', 'off', true);
END $$;


-- ---------------------------------------------------------------------------
-- 2c. The payload. `v_records` is what the model reads an Entity as, and
-- 20260814T080000Z's definition re-issued with one key of one jsonb_build_object
-- gone. A view is the one kind of object that records a dependency on a column,
-- so this has to happen before the `ALTER TABLE` below rather than after it.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW v_records WITH (security_invoker = true) AS
SELECT r.kind,
       r.label,
       r.revision,
       encode(sha256(convert_to(r.record::text, 'utf8')), 'hex') AS digest,
       r.record
  FROM (
    SELECT 'entity'::text AS kind, e.label,
           -- The revision has to cover the record, and the record now carries
           -- this Entity's relationships. A Relationship is its own row with
           -- its own Events, so joining one changes the digest and leaves
           -- `rk2_revision('entities', ...)` where it was -- and `state.py`
           -- ranks by revision while a packet reader compares them. The
           -- greatest of the two is the revision of what is being read.
           greatest(rk2_revision('entities', e.id),
                    coalesce((SELECT max(rk2_revision('relationships', rel.id))
                                FROM relationships rel
                               WHERE rel.src_entity_id = e.id
                                  OR rel.dst_entity_id = e.id), 0)) AS revision,
           jsonb_build_object(
               'kind', 'entity',
               'label', e.label,
               'type', e.type,
               'in_scope', e.in_scope,
               'descriptor', rk2_descriptor(e.id),
               'identity_class', i.class,
               'scope_class', e.scope_class,
               'origin', e.origin,
               'origins', (SELECT coalesce(jsonb_agg(DISTINCT o.origin), '[]'::jsonb)
                             FROM (SELECT e.origin AS origin
                                   UNION
                                   SELECT ep.origin FROM entity_provenance ep
                                    WHERE ep.entity_id = e.id) o),
               'parent_label', par.label,
               'relationships', (
                   SELECT coalesce(jsonb_agg(x.entry ORDER BY x.entry), '[]'::jsonb)
                     FROM (SELECT jsonb_build_object(
                                      'type', rel.type, 'direction', 'out',
                                      'label', other.label) AS entry
                             FROM relationships rel
                             JOIN entities other ON other.id = rel.dst_entity_id
                            WHERE rel.src_entity_id = e.id
                            UNION ALL
                           SELECT jsonb_build_object(
                                      'type', rel.type, 'direction', 'in',
                                      'label', other.label)
                             FROM relationships rel
                             JOIN entities other ON other.id = rel.src_entity_id
                            WHERE rel.dst_entity_id = e.id
                            ORDER BY 1 LIMIT 20) x),
               'relationship_count', (SELECT count(*) FROM relationships rel
                                       WHERE rel.src_entity_id = e.id
                                          OR rel.dst_entity_id = e.id),
               'first_seen_at', rk2_instant(e.first_seen_at),
               'last_seen_at', rk2_instant(e.last_seen_at)) AS record
      FROM entities e
      LEFT JOIN identities i ON i.entity_id = e.id
      LEFT JOIN services   cs ON cs.entity_id = e.id
      LEFT JOIN endpoints  ce ON ce.entity_id = e.id
      LEFT JOIN parameters cp ON cp.entity_id = e.id
      LEFT JOIN entities  par ON par.id = coalesce(cs.host_id, ce.application_id,
                                                   cp.endpoint_id)

    UNION ALL
    SELECT 'hypothesis', hy.label,
           -- Same rule as the entity arm above, for the same reason: the record
           -- now carries what the claim's refutation is doing, and a record
           -- that stopped being current while the claim did not move is a
           -- change to the record with nothing on `hypotheses` to show for it.
           -- The retest row is the Event that says so.
           greatest(rk2_revision('hypotheses', hy.id),
                    coalesce((SELECT max(rk2_revision('negative_knowledge_retests', rt.id))
                                FROM negative_knowledge_retests rt
                                JOIN negative_knowledge n ON n.id = rt.negative_id
                               WHERE n.hypothesis_id = hy.id), 0)),
           jsonb_build_object(
               'kind', 'hypothesis',
               'label', hy.label,
               'status', hy.status,
               'property_class', hy.property_class,
               'statement', hy.statement,
               'rationale', hy.rationale,
               'subject_label', subj.label,
               'identity_a_label', ia.label,
               'identity_b_label', ib.label,
               'superseded_by_label', sup.label,
               'observed_fingerprint', hy.observed_fingerprint,
               -- 034. Not the Surface fingerprint it was settled
               -- against, which stays the runtime's: what a claim's
               -- refutation is currently doing, and why.
               'negative_knowledge', rk2_hypothesis_negative(hy.id),
               'status_changed_at', rk2_instant(hy.status_changed_at),
               'created_at', rk2_instant(hy.created_at))
      FROM hypotheses hy
      LEFT JOIN entities subj ON subj.id = hy.subject_entity_id
      LEFT JOIN entities ia   ON ia.id   = hy.identity_a_entity_id
      LEFT JOIN entities ib   ON ib.id   = hy.identity_b_entity_id
      LEFT JOIN hypotheses sup ON sup.id = hy.superseded_by

    UNION ALL
    SELECT 'observation', o.label,
           rk2_revision('observations', o.id),
           jsonb_build_object(
               'kind', 'observation',
               'label', o.label,
               'observation_kind', o.kind,
               'summary', o.summary,
               'provenance_kind', o.provenance_kind,
               'subject_label', subj.label,
               'receipt_label', rc.label,
               'tool_run_label', tr.label,
               'observed_at', rk2_instant(o.observed_at))
      FROM observations o
      LEFT JOIN entities  subj ON subj.id = o.subject_entity_id
      LEFT JOIN receipts  rc   ON rc.id   = o.receipt_id
      LEFT JOIN tool_runs tr   ON tr.id   = o.tool_run_id

    UNION ALL
    SELECT 'receipt', rc.label,
           rk2_revision('receipts', rc.id),
           jsonb_build_object(
               'kind', 'receipt',
               'label', rc.label,
               'lane', rc.lane,
               'purpose', rc.purpose,
               'decision', rc.decision,
               'reason', rc.reason,
               'method', rc.method,
               'scheme', rc.scheme,
               'host', rc.host,
               'port', rc.port,
               'path', rc.path,
               'status_code', rc.status_code,
               'identity_label', idn.label,
               'tool_run_label', tr.label,
               'scope_class', rc.scope_class,
               'intercepted', rc.intercepted,
               'transport_citable', rc.transport_citable,
               'request_agent_sha', rc.request_agent_sha,
               'response_agent_sha', rc.response_agent_sha,
               'waited_ms', rc.waited_ms,
               'ts_arrival', rk2_instant(rc.ts_arrival))
      FROM receipts rc
      LEFT JOIN entities  idn ON idn.id = rc.identity_entity_id
      LEFT JOIN tool_runs tr  ON tr.id  = rc.tool_run_id

    UNION ALL
    SELECT 'tool_run', tr.label,
           rk2_revision('tool_runs', tr.id),
           jsonb_build_object(
               'kind', 'tool_run',
               'label', tr.label,
               'tool', tr.tool,
               'status', tr.status,
               'decision', tr.decision,
               'decision_reason', tr.decision_reason,
               'risk_class', tr.risk_class,
               'transport', tr.transport,
               'mcp_server', tr.mcp_server,
               'task_label', tk.label,
               'args_sha256', tr.args_sha256,
               'result_sha256', tr.result_sha256,
               'started_at', rk2_instant(tr.started_at),
               'finished_at', rk2_instant(tr.finished_at))
      FROM tool_runs tr
      LEFT JOIN tasks tk ON tk.id = tr.task_id

    UNION ALL
    SELECT 'task', tk.label,
           rk2_revision('tasks', tk.id),
           jsonb_build_object(
               'kind', 'task',
               'label', tk.label,
               'task_kind', tk.kind,
               'status', tk.status,
               'subject_label', subj.label,
               'hypothesis_label', hy.label,
               'finding_label', f.label,
               'skill_name', tk.skill_name,
               'priority', tk.priority,
               'expected_information_gain', tk.expected_information_gain,
               'potential_impact', tk.potential_impact,
               'novelty', tk.novelty,
               'estimated_cost', tk.estimated_cost,
               'confidence_of_execution', tk.confidence_of_execution,
               'attempts', tk.attempts,
               'abandoned_reason', tk.abandoned_reason,
               'created_at', rk2_instant(tk.created_at),
               'claimed_at', rk2_instant(tk.claimed_at),
               'finished_at', rk2_instant(tk.finished_at))
      FROM tasks tk
      LEFT JOIN entities   subj ON subj.id = tk.subject_entity_id
      LEFT JOIN hypotheses hy   ON hy.id   = tk.hypothesis_id
      LEFT JOIN findings   f    ON f.id    = tk.finding_id

    UNION ALL
    SELECT 'test', ts.label,
           rk2_revision('tests', ts.id),
           jsonb_build_object(
               'kind', 'test',
               'label', ts.label,
               'hypothesis_label', hy.label,
               'supersedes_label', prev.label,
               'spec_sha256', ts.spec_sha256,
               'created_at', rk2_instant(ts.created_at))
      FROM tests ts
      LEFT JOIN hypotheses hy ON hy.id = ts.hypothesis_id
      LEFT JOIN tests prev ON prev.id = ts.supersedes_test_id

    UNION ALL
    SELECT 'finding', f.label,
           rk2_revision('findings', f.id),
           jsonb_build_object(
               'kind', 'finding',
               'label', f.label,
               'status', f.status,
               'class_id', f.class_id,
               'title', f.title,
               'severity', f.severity,
               'cvss_vector', f.cvss_vector,
               'subject_label', subj.label,
               'duplicate_of_label', dup.label,
               'external_ref', f.external_ref,
               'validated_run_outcome', f.validated_run_outcome,
               'status_changed_at', rk2_instant(f.status_changed_at),
               'reported_at', rk2_instant(f.reported_at),
               'created_at', rk2_instant(f.created_at))
      FROM findings f
      LEFT JOIN entities subj ON subj.id = f.subject_entity_id
      LEFT JOIN findings dup  ON dup.id  = f.duplicate_of_finding_id
  ) r;

COMMENT ON VIEW v_records IS
    'Every labelled record this Program holds, with its revision and a digest of itself. The only identifier is the label.';


-- ---------------------------------------------------------------------------
-- 2d. The two indexes that carry a tier column along for an index-only scan
-- nothing performs. Rebuilt rather than dropped: `DROP COLUMN` would take the
-- whole index with it, and both of them earn their keep on their key columns.
-- ---------------------------------------------------------------------------

DROP INDEX scope_rules_key_idx;
CREATE INDEX scope_rules_key_idx
    ON program_scope_rules (program_id, version, match_key)
    INCLUDE (effect_rank, spec_kind, spec_len, protocol, port, path_prefix);

DROP INDEX entities_in_scope_idx;
-- What the scheduler actually reads. Partial on `in_scope`, so the index holds
-- ONLY rows a ranking pass may act on, and `label` is in the key so the ordered
-- read needs no sort. The INCLUDE is gone with the column it carried.
CREATE INDEX entities_in_scope_idx
    ON entities (program_id, type, label)
    WHERE in_scope;


-- ---------------------------------------------------------------------------
-- 2e. The four columns. `program_scope_rules.tier` takes `CHECK (tier IS NULL
-- OR effect = 'target')` with it, which is the intended outcome and not a
-- side effect: the constraint could never fail and the comment on it named a
-- mirror in the Python compiler that has never existed.
-- ---------------------------------------------------------------------------

ALTER TABLE program_scope_rules DROP COLUMN tier;
ALTER TABLE program_scope_rules DROP COLUMN allow_private_ips;
ALTER TABLE program_scope_versions DROP COLUMN default_tier;
ALTER TABLE entities DROP COLUMN scope_tier;


-- ---------------------------------------------------------------------------
-- 2f. The read-surface row the dropped column leaves behind. `rk2_state` holds
-- no relation-level grant: `state_read_surface` IS the grant, one row per
-- column (`0030_corpus_corrections.sql:246-263`), and `entities.scope_tier`
-- entered it through that file's `33-seed` bulk insert rather than by anyone
-- naming it. `DROP COLUMN` takes the column privilege with the column but
-- leaves the row, and `check_state_grants()` fails a row that names no such
-- column -- so the registry is corrected in the same file that removes the
-- column, or every run of the standing check reports a surface that does not
-- exist. The other three columns were never on the agent surface and have no
-- row to delete.
-- ---------------------------------------------------------------------------

DELETE FROM state_read_surface
 WHERE table_name = 'entities' AND column_name = 'scope_tier';


-- ===========================================================================
-- 3. A range rule, written and then classified, and rolled back
-- ===========================================================================

-- The claim is the ticket's fifth criterion: a configuration with a CIDR target
-- compiles, projects, and an Entity inside the range comes out `target`. The
-- compiling half is `tests/test_scope.py` and `tests/test_config.py`; this is
-- the other half, and it is asserted here because the file that would hold it
-- is not this change's to write.
--
-- The rule row is written in exactly the shape `scope.Rule.row()` now produces
-- for a range -- `pattern_kind = 'cidr'`, `net` set, `match_key` null,
-- `spec_kind = 0` and `spec_len` the prefix length -- so the two CHECKs at
-- `021:109-110` are being asserted as well as the classifier. The Entity is
-- reached by address and not by name, which is the only form a range decides.
--
-- Written and then rolled back, because it is an assertion and not state: the
-- inner block is a subtransaction, the sentinel at the bottom of it unwinds
-- every write, and a real refusal carries a different SQLSTATE and leaves.
-- `refresh_scope_projection` needs a declared actor and has one: `rk db migrate`
-- calls `set_actor('runtime', ...)` before it applies anything.
DO $$
DECLARE
    v_program uuid; v_inside uuid; v_outside uuid;
    v_class text; v_ord integer;
BEGIN
    BEGIN
        INSERT INTO programs (slug, name)
        VALUES ('ticket-117-proof', 'ticket 117 proof')
        RETURNING id INTO v_program;
        INSERT INTO program_scope_versions (program_id, version, policy, policy_sha256)
        VALUES (v_program, 1, '{}'::jsonb, repeat('0', 64));

        INSERT INTO program_scope_rules
            (program_id, version, ord, effect, effect_rank, pattern_kind,
             pattern_text, match_key, net, protocol, port, path_prefix,
             spec_kind, spec_len)
        VALUES (v_program, 1, 1, 'target', 2, 'cidr',
                '93.184.216.0/24', NULL, '93.184.216.0/24'::cidr, 'https', 443,
                '/', 0, 24);

        -- The coverage question, which is the one an Entity asks and the one
        -- `refresh_scope_projection` puts through `scope_class_of_entity`.
        SELECT s.scope_class, s.rule_ord INTO v_class, v_ord
          FROM scope_class_of_entity(v_program, 1, 'host', '93.184.216.7') s;
        IF v_class IS DISTINCT FROM 'target' OR v_ord IS DISTINCT FROM 1 THEN
            RAISE EXCEPTION
                'ticket 117: an address inside the range classified % citing rule %',
                v_class, v_ord;
        END IF;

        -- And the neighbouring /24, so the assertion is that the range decides
        -- rather than that the evaluator says target to everything.
        SELECT s.scope_class INTO v_class
          FROM scope_class_of_entity(v_program, 1, 'host', '93.184.217.7') s;
        IF v_class IS DISTINCT FROM 'denied' THEN
            RAISE EXCEPTION
                'ticket 117: an address outside the range classified %', v_class;
        END IF;

        -- A name is not admitted by the range its address falls in, whatever
        -- that address is. This is the design decision the door turns on, not
        -- an omission, and it is asserted so that a later reading of the
        -- containment arm cannot quietly widen it.
        SELECT s.scope_class INTO v_class
          FROM scope_class_of_entity(v_program, 1, 'host', 'www.example.com') s;
        IF v_class IS DISTINCT FROM 'denied' THEN
            RAISE EXCEPTION
                'ticket 117: a name was admitted by a range and classified %', v_class;
        END IF;

        -- The projection, end to end: the column the rest of the system reads.
        INSERT INTO entities (program_id, type, label, dedup_key,
                              scope_selector_kind, scope_selector, scope_port)
        VALUES (v_program, 'host', 'inside-the-range', 'host:93.184.216.7',
                'host', '93.184.216.7', 443)
        RETURNING id INTO v_inside;
        INSERT INTO entities (program_id, type, label, dedup_key,
                              scope_selector_kind, scope_selector, scope_port)
        VALUES (v_program, 'host', 'outside-the-range', 'host:93.184.217.7',
                'host', '93.184.217.7', 443)
        RETURNING id INTO v_outside;
        PERFORM set_scope_version(v_program, 1);

        IF (SELECT scope_class FROM entities WHERE id = v_inside) <> 'target'
           OR NOT (SELECT in_scope FROM entities WHERE id = v_inside) THEN
            RAISE EXCEPTION
                'ticket 117: the projection did not carry the range to the Entity';
        END IF;
        IF (SELECT scope_class FROM entities WHERE id = v_outside) <> 'denied' THEN
            RAISE EXCEPTION
                'ticket 117: the projection put an Entity outside the range in scope';
        END IF;

        RAISE EXCEPTION 'ticket 117 proof' USING ERRCODE = 'RK117';
    EXCEPTION WHEN SQLSTATE 'RK117' THEN
        NULL;
    END;
END $$;


-- ===========================================================================
-- 4. The tier is gone from the schema, not merely from the writers
-- ===========================================================================

-- Read out of the catalogue rather than restated, so this block would fail if
-- one of the four `ALTER TABLE`s above were dropped from this file, and would
-- fail again the day somebody re-added one of the columns under its own name.
-- `v_records` is checked by its definition, because a view that still published
-- the key would mean the column came back somewhere.
DO $$
DECLARE v_columns text; v_published boolean;
BEGIN
    SELECT string_agg(c.table_name || '.' || c.column_name, ', ' ORDER BY c.table_name)
      INTO v_columns
      FROM information_schema.columns c
     WHERE c.table_schema = 'public'
       AND ((c.table_name = 'program_scope_rules'    AND c.column_name IN ('tier', 'allow_private_ips'))
         OR (c.table_name = 'program_scope_versions' AND c.column_name = 'default_tier')
         OR (c.table_name = 'entities'               AND c.column_name = 'scope_tier'));
    IF v_columns IS NOT NULL THEN
        RAISE EXCEPTION 'ticket 117: the effort tier is still declared at %', v_columns
          USING ERRCODE = '23514';
    END IF;

    SELECT pg_get_viewdef('v_records'::regclass, true) LIKE '%scope_tier%'
      INTO v_published;
    IF v_published THEN
        RAISE EXCEPTION 'ticket 117: v_records still publishes scope_tier'
          USING ERRCODE = '23514';
    END IF;
END $$;
