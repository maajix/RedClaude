-- ---------------------------------------------------------------------------
-- 20260807T191500Z__ticket10_playbooks.sql   (ticket 10 -- the playbook catalogue)
--
-- Was `027_ticket10_playbooks.sql` on branch prototype/playbook-format, written
-- against 001..018 + three siblings it could only guess at. Folded into the
-- consolidated corpus here. What the fold changed, and nothing else:
--
--   * `skills` already exists -- ticket 08 created it for the confidence gate
--     (name, enabled, description). 027 created a second one. This adds the one
--     column 027 needed (`source_sha256`) to the table that is already there.
--   * `risk_rank(text)` already exists -- ticket 28 defines it 0..3 over the
--     same four risk classes. 027 defined it 1..4. Both uses here are order
--     comparisons and a NULL test, so the offset is not observable; the
--     duplicate definition is dropped rather than shadowed.
--   * 027 enabled RLS and wrote its own two policies on `playbook_selections`.
--     `apply_state_rls()` is a finalizer as of ticket 33 and does that for every
--     program-scoped table on every `up`. The hand-written copy is removed.
--   * 027 issued relation-level `GRANT SELECT ... TO rk2_state`. Ticket 33
--     revoked every relation grant from that role and made the read surface a
--     column-level registry, so the grants become `state_read_surface` rows and
--     `apply_state_grants()` issues them.
--   * 027 classified none of its nine tables for emission and registered none of
--     its six cascading foreign keys. Both are added below (section H); neither
--     was optional, 027 simply predated the checks that say so.
-- ---------------------------------------------------------------------------


-- ===========================================================================
-- A -- the surface-fact vocabulary
--
-- A trigger atom is NOT an expression.  Ticket 08 decision 6 refused a task DAG
-- because readiness is a predicate over current rows; the same argument applies
-- here, and harder: 180 playbooks x N endpoints is where an expression language
-- becomes a per-row interpreter.  So an atom is a *name* drawn from a closed
-- vocabulary, and the whole trigger stage is set containment over one view.
-- ===========================================================================

CREATE TABLE surface_facts (
    id          text PRIMARY KEY CHECK (id ~ '^[a-z][a-z0-9_]*$'),
    scope       text NOT NULL CHECK (scope IN ('endpoint','application','program')),
    description text NOT NULL
);

INSERT INTO surface_facts (id, scope, description) VALUES
 -- endpoint shape
 ('authenticated_endpoint','endpoint','the endpoint requires authentication'),
 ('unauthenticated_endpoint','endpoint','the endpoint is reachable unauthenticated'),
 ('unknown_auth_endpoint','endpoint','whether the endpoint authenticates has not been established'),
 ('state_changing_method','endpoint','method is POST, PUT, PATCH or DELETE'),
 ('read_method','endpoint','method is GET or HEAD'),
 ('json_request','endpoint','request body is JSON'),
 ('form_request','endpoint','request body is form-encoded'),
 ('multipart_request','endpoint','request body is multipart'),
 -- parameters on the endpoint
 ('path_parameter','endpoint','at least one parameter in the path'),
 ('query_parameter','endpoint','at least one parameter in the query string'),
 ('body_parameter','endpoint','at least one parameter in the body'),
 ('header_parameter','endpoint','at least one parameter in a header'),
 ('cookie_parameter','endpoint','at least one parameter in a cookie'),
 ('object_identifier','endpoint','a parameter names an object (uuid, integer_id, opaque_id)'),
 ('numeric_identifier','endpoint','a parameter names an object by sequential integer'),
 ('reflected_parameter','endpoint','a parameter was observed reflected in a response'),
 ('url_valued_parameter','endpoint','a parameter carries a URL'),
 ('file_parameter','endpoint','a parameter carries a file'),
 ('email_valued_parameter','endpoint','a parameter carries an email address'),
 ('redirect_target','endpoint','the endpoint redirects to another endpoint'),
 -- application shape, propagated to the application's endpoints
 ('graphql_surface','application','the application is a GraphQL API'),
 ('spa_surface','application','the application is a single-page app'),
 ('api_surface','application','the application is a non-browser API'),
 ('websocket_surface','application','the application speaks websockets'),
 ('tech_jwt','application','a JWT implementation was identified'),
 ('tech_oauth','application','an OAuth implementation was identified'),
 ('tech_saml','application','a SAML implementation was identified'),
 ('tech_soap','application','a SOAP stack was identified'),
 ('tech_graphql','application','a GraphQL server was identified'),
 -- program shape, propagated to every subject in the program
 ('multiple_test_identities','program','two or more user identities are controlled'),
 ('privileged_identity_available','program','a privileged identity is controlled'),
 ('anonymous_identity_available','program','the anonymous identity is usable'),
 ('tenant_boundary','program','two controlled identities sit in different tenants');


-- The one view that computes them.  Every branch is a plain join on the graph
-- ticket 06 already defines; nothing here reads model output.
--
-- Program- and application-level facts are attached to every endpoint subject
-- so that the trigger stage stays a single set-containment against one relation
-- instead of a three-way correlated match.
CREATE VIEW subject_facts AS
WITH ep AS (
    SELECT e.id AS entity_id, e.program_id, ep.application_id, ep.method,
           ep.auth_required, ep.request_content_type
      FROM entities e JOIN endpoints ep ON ep.entity_id = e.id
     WHERE e.in_scope
)
-- endpoint shape
SELECT program_id, entity_id AS subject_entity_id, 'authenticated_endpoint'::text AS fact
  FROM ep WHERE auth_required IS TRUE
UNION ALL SELECT program_id, entity_id, 'unauthenticated_endpoint' FROM ep WHERE auth_required IS FALSE
UNION ALL SELECT program_id, entity_id, 'unknown_auth_endpoint'    FROM ep WHERE auth_required IS NULL
UNION ALL SELECT program_id, entity_id, 'state_changing_method'    FROM ep WHERE method IN ('POST','PUT','PATCH','DELETE')
UNION ALL SELECT program_id, entity_id, 'read_method'              FROM ep WHERE method IN ('GET','HEAD')
UNION ALL SELECT program_id, entity_id, 'json_request'             FROM ep WHERE request_content_type LIKE '%json%'
UNION ALL SELECT program_id, entity_id, 'form_request'             FROM ep WHERE request_content_type LIKE '%form-urlencoded%'
UNION ALL SELECT program_id, entity_id, 'multipart_request'        FROM ep WHERE request_content_type LIKE '%multipart%'
-- parameters
UNION ALL SELECT DISTINCT ep.program_id, ep.entity_id,
       CASE p.location WHEN 'path' THEN 'path_parameter' WHEN 'query' THEN 'query_parameter'
                       WHEN 'body' THEN 'body_parameter' WHEN 'header' THEN 'header_parameter'
                       ELSE 'cookie_parameter' END
  FROM ep JOIN parameters p ON p.endpoint_id = ep.entity_id
UNION ALL SELECT DISTINCT ep.program_id, ep.entity_id, 'object_identifier'
  FROM ep JOIN parameters p ON p.endpoint_id = ep.entity_id
 WHERE p.value_class IN ('uuid','integer_id','opaque_id')
UNION ALL SELECT DISTINCT ep.program_id, ep.entity_id, 'numeric_identifier'
  FROM ep JOIN parameters p ON p.endpoint_id = ep.entity_id WHERE p.value_class = 'integer_id'
UNION ALL SELECT DISTINCT ep.program_id, ep.entity_id, 'reflected_parameter'
  FROM ep JOIN parameters p ON p.endpoint_id = ep.entity_id WHERE p.reflected IS TRUE
UNION ALL SELECT DISTINCT ep.program_id, ep.entity_id, 'url_valued_parameter'
  FROM ep JOIN parameters p ON p.endpoint_id = ep.entity_id WHERE p.value_class = 'url'
UNION ALL SELECT DISTINCT ep.program_id, ep.entity_id, 'file_parameter'
  FROM ep JOIN parameters p ON p.endpoint_id = ep.entity_id WHERE p.value_class = 'file'
UNION ALL SELECT DISTINCT ep.program_id, ep.entity_id, 'email_valued_parameter'
  FROM ep JOIN parameters p ON p.endpoint_id = ep.entity_id WHERE p.value_class = 'email'
UNION ALL SELECT DISTINCT ep.program_id, ep.entity_id, 'redirect_target'
  FROM ep JOIN relationships r ON r.src_entity_id = ep.entity_id AND r.type = 'redirects_to'
-- application shape
UNION ALL SELECT ep.program_id, ep.entity_id,
       CASE a.kind WHEN 'graphql' THEN 'graphql_surface' WHEN 'spa' THEN 'spa_surface'
                   WHEN 'api' THEN 'api_surface' ELSE 'websocket_surface' END
  FROM ep JOIN applications a ON a.entity_id = ep.application_id
 WHERE a.kind IN ('graphql','spa','api','websocket')
-- Spelled out rather than 'tech_' || lower(t.name).  check_playbook_integrity's
-- fact_not_computed rule reads the view definition looking for the atom's name,
-- and a name assembled by concatenation is invisible to it: all five tech_ atoms
-- were reported as uncomputed while the view was computing them correctly.  The
-- rule is right to be textual (it must catch an atom no branch produces), so the
-- view is what changes.
UNION ALL SELECT DISTINCT ep.program_id, ep.entity_id,
       CASE lower(t.name) WHEN 'jwt'     THEN 'tech_jwt'
                          WHEN 'oauth'   THEN 'tech_oauth'
                          WHEN 'saml'    THEN 'tech_saml'
                          WHEN 'soap'    THEN 'tech_soap'
                          WHEN 'graphql' THEN 'tech_graphql' END
  FROM ep JOIN relationships r ON r.src_entity_id = ep.application_id AND r.type = 'runs'
          JOIN technologies t ON t.entity_id = r.dst_entity_id
 WHERE lower(t.name) IN ('jwt','oauth','saml','soap','graphql')
-- program shape
UNION ALL SELECT ep.program_id, ep.entity_id, 'multiple_test_identities'
  FROM ep WHERE (SELECT count(*) FROM entities ie JOIN identities i ON i.entity_id = ie.id
                  WHERE ie.program_id = ep.program_id AND i.class = 'user'
                    AND i.invalidated_at IS NULL) >= 2
UNION ALL SELECT ep.program_id, ep.entity_id, 'privileged_identity_available'
  FROM ep WHERE EXISTS (SELECT 1 FROM entities ie JOIN identities i ON i.entity_id = ie.id
                         WHERE ie.program_id = ep.program_id AND i.class = 'privileged'
                           AND i.invalidated_at IS NULL)
UNION ALL SELECT ep.program_id, ep.entity_id, 'anonymous_identity_available'
  FROM ep WHERE EXISTS (SELECT 1 FROM entities ie JOIN identities i ON i.entity_id = ie.id
                         WHERE ie.program_id = ep.program_id AND i.class = 'anonymous'
                           AND i.invalidated_at IS NULL)
UNION ALL SELECT ep.program_id, ep.entity_id, 'tenant_boundary'
  FROM ep WHERE (SELECT count(DISTINCT r.dst_entity_id)
                   FROM entities ie JOIN identities i ON i.entity_id = ie.id
                   JOIN relationships r ON r.src_entity_id = ie.id AND r.type = 'member_of'
                  WHERE ie.program_id = ep.program_id) >= 2;

COMMENT ON VIEW subject_facts IS
 'The trigger stage input. One row per (subject, fact). Registered facts with no '
 'branch here are caught by check_playbook_integrity() rule fact_not_computed.';


-- ===========================================================================
-- B -- the one column the skill registry was missing
--
-- 027 created `skills` because no migration it could see had. Ticket 08's
-- scheduler migration did: `skills (name, enabled, description)`, global,
-- referenced by `tasks.required_skills`. Creating a second one here would have
-- failed, and replacing ticket 08's would have dropped the `enabled` flag the
-- confidence gate reads.
--
-- So only the drift column is added, and it is NULLable on purpose: ticket 08's
-- rows are a name and a flag, with no file behind them. `skill_drift` below
-- compares `skill_sha256_at_promotion` to this, and a promotion that was made
-- against a skill with no recorded text has nothing to drift from -- NULL <> x
-- is NULL, so the row is not reported, which is the correct answer rather than
-- a convenient one.
--
-- `role_skills` is new: it is ticket 11's per-role skill list, which nothing in
-- the corpus had.
-- ===========================================================================

ALTER TABLE skills
    ADD COLUMN source_sha256 text CHECK (source_sha256 ~ '^[0-9a-f]{64}$');

COMMENT ON COLUMN skills.source_sha256 IS
 'sha256 of the skill file, for ticket 10 drift detection. NULL for a registry row with no file behind it (ticket 08 created the table with a name and an enabled flag and nothing else).';

-- FK, not a CHECK list.  The first draft of this table spelled the roster out
-- and got it wrong -- ticket 11's hunter role is `web_hunter`, and a CHECK list
-- is exactly the second copy of a vocabulary that dump_vocab.sh exists to
-- prevent.  A wrong CHECK list does not fail loudly: it accepts a role nobody
-- has and silently selects nothing for it.
CREATE TABLE role_skills (
    role       text NOT NULL REFERENCES roles(role) ON DELETE RESTRICT,
    skill_name text NOT NULL REFERENCES skills(name) ON DELETE RESTRICT,
    PRIMARY KEY (role, skill_name)
);


-- ===========================================================================
-- C -- the playbook catalogue
--
-- Knowledge is program-global on purpose: a playbook promoted on one program is
-- the same document on the next, and ticket 05's promotion pipeline has no
-- program dimension.  Registered in program_global_tables below so ticket 35's
-- rule 2 stays satisfied rather than silently exempted.
-- ===========================================================================

CREATE TABLE playbooks (
    id            uuid PRIMARY KEY DEFAULT uuidv7(),
    -- Identity is the path, for ticket 09's reason: a `bb:id` would be a second
    -- identity, and 12 of v1's 27 skills had already drifted on exactly that.
    path          text NOT NULL UNIQUE CHECK (path ~ '^playbooks/[a-z0-9][a-z0-9/_-]*\.md$'),
    -- Version is content, not a hand-maintained semver (ticket 09).
    source_sha256 text NOT NULL CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
    okf_type      text NOT NULL CHECK (okf_type <> ''),
    category      text NOT NULL REFERENCES property_class_families(id),
    status        text NOT NULL CHECK (status IN ('draft','stable','deprecated')),
    stale_after   timestamptz,
    -- Four classes, not Q4's three: ticket 13 added `forbidden` because
    -- "always escalate" puts a human in the loop for a call already refused.
    -- Here `forbidden` means a playbook the runtime will not run at all.
    risk          text NOT NULL CHECK (risk IN (
                      'autonomous','constrained','approval_required','forbidden')),
    -- the composition axes; conflict is derived from these, never declared
    effects       text NOT NULL CHECK (effects IN (
                      'read_only','mutates_session','mutates_object','mutates_account')),
    baseline      text NOT NULL DEFAULT 'none' CHECK (baseline IN (
                      'none','stable_session','pristine_surface')),
    specificity   integer NOT NULL DEFAULT 0,   -- |all-triggers|, the tie-break
    promoted_at   timestamptz,
    ingested_at   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT playbooks_stable_is_promoted
        CHECK (status <> 'stable' OR promoted_at IS NOT NULL),
    -- `bb:risk` is a FLOOR, not a verdict: the least supervision the author says
    -- this class of work can be run under.  Ticket 28 owns per-call assignment
    -- and may raise it; nothing may lower it.  The first draft of this
    -- constraint only bound the read_only direction and happily accepted an
    -- account-mutating playbook that called itself `autonomous` -- which is the
    -- exact declaration the runtime must never take at face value.
    CONSTRAINT playbooks_risk_matches_effects
        CHECK (CASE effects
                 WHEN 'read_only'       THEN true
                 WHEN 'mutates_session' THEN risk <> 'autonomous'
                 WHEN 'mutates_object'  THEN risk <> 'autonomous'
                 WHEN 'mutates_account' THEN risk IN ('approval_required','forbidden')
               END)
);

CREATE TABLE playbook_triggers (
    playbook_id uuid NOT NULL REFERENCES playbooks(id) ON DELETE CASCADE,
    mode        text NOT NULL CHECK (mode IN ('all','any')),
    fact        text NOT NULL REFERENCES surface_facts(id),
    PRIMARY KEY (playbook_id, mode, fact)
);
CREATE INDEX playbook_triggers_fact_idx ON playbook_triggers (fact, mode);

CREATE TABLE playbook_outputs (
    playbook_id    uuid NOT NULL REFERENCES playbooks(id) ON DELETE CASCADE,
    property_class text NOT NULL REFERENCES property_classes(id),
    PRIMARY KEY (playbook_id, property_class)
);
CREATE INDEX playbook_outputs_class_idx ON playbook_outputs (property_class);

-- A dangling skill reference is structurally unwritable: the FK refuses the
-- insert, and ON DELETE RESTRICT refuses the removal from the other side.
CREATE TABLE playbook_skills (
    playbook_id             uuid NOT NULL REFERENCES playbooks(id) ON DELETE CASCADE,
    skill_name              text NOT NULL REFERENCES skills(name) ON DELETE RESTRICT,
    skill_sha256_at_promotion text CHECK (skill_sha256_at_promotion ~ '^[0-9a-f]{64}$'),
    PRIMARY KEY (playbook_id, skill_name)
);

-- Evidence requirements the runtime can decide.  Hypothesis machine only: the
-- finding machine's evidence is ticket 06/32's and declaring rows nothing reads
-- is the mistake ticket 09 removed from the skill format.
CREATE TABLE playbook_evidence (
    playbook_id      uuid NOT NULL REFERENCES playbooks(id) ON DELETE CASCADE,
    to_status        text NOT NULL CHECK (to_status IN ('supported','refuted','inconclusive')),
    role             text NOT NULL CHECK (role IN ('baseline','variant','control','context')),
    observation_kind text NOT NULL REFERENCES observation_kinds(id),
    polarity         text CHECK (polarity IN ('supports','refutes')),
    min_count        integer NOT NULL CHECK (min_count >= 1),
    PRIMARY KEY (playbook_id, to_status, role, observation_kind)
);


-- ===========================================================================
-- D -- what the runtime selected, per task.  Program-scoped, so RLS.
-- ===========================================================================

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conname = 'tasks_id_program_key' AND conrelid = 'tasks'::regclass) THEN
        ALTER TABLE tasks ADD CONSTRAINT tasks_id_program_key UNIQUE (id, program_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conname = 'entities_id_program_key' AND conrelid = 'entities'::regclass) THEN
        ALTER TABLE entities ADD CONSTRAINT entities_id_program_key UNIQUE (id, program_id);
    END IF;
END $$;

CREATE TABLE playbook_selections (
    id                uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id        uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    task_id           uuid NOT NULL,
    subject_entity_id uuid NOT NULL,
    playbook_id       uuid NOT NULL REFERENCES playbooks(id) ON DELETE RESTRICT,
    -- frozen at selection: this is what makes an in-flight mission survive the
    -- playbook going stale, and what a finding cites three months later
    playbook_sha256   text NOT NULL CHECK (playbook_sha256 ~ '^[0-9a-f]{64}$'),
    rank              integer,
    dropped_because   text,          -- NULL = kept and fed to the model
    outcome           text NOT NULL DEFAULT 'running'
                      CHECK (outcome IN ('running','produced','exhausted')),
    went_stale_at     timestamptz,   -- the playbook went stale during this run
    selected_at       timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (task_id, program_id) REFERENCES tasks (id, program_id) ON DELETE CASCADE,
    FOREIGN KEY (subject_entity_id, program_id) REFERENCES entities (id, program_id) ON DELETE CASCADE,
    CONSTRAINT playbook_selections_dropped_has_no_outcome
        CHECK (dropped_because IS NULL OR outcome = 'running'),
    UNIQUE (task_id, playbook_id)
);
CREATE INDEX playbook_selections_subject_idx
    ON playbook_selections (program_id, subject_entity_id, playbook_id);

-- No `ENABLE ROW LEVEL SECURITY` and no policies here. 027 wrote both because
-- 020's sweep had already run by the time it applied; ticket 33 made that sweep
-- `apply_state_rls()`, a finalizer that runs at the end of every `up` over every
-- program-scoped table not in `program_global_tables`. `check_rls_coverage()`
-- is what proves this table got them.
--
-- No `GRANT ... TO rk2_state` either: ticket 33 revoked every relation-level
-- grant from that role and replaced it with the column registry in section H.
--
-- And no `GRANT ... TO rk2_runtime`. 027 listed all nine tables because it was
-- written against 016, where a table added after the one-shot sweep was
-- invisible to the runtime. The consolidated corpus sets ALTER DEFAULT
-- PRIVILEGES FOR ROLE rk2_owner before any of this applies, so a table created
-- here is readable and writable by rk2_runtime the moment it exists.
-- `runtime_readwrite_on_every_managed_table` in `migrate.sh verify` is what
-- says so, and it counts tables, not migrations.

INSERT INTO program_global_tables (table_name, reason) VALUES
 ('surface_facts',     'the trigger-atom vocabulary; a property of the schema'),
 -- `skills` is ticket 08's and was already registered global by it.
 ('role_skills',       'the roster is one roster for the whole system'),
 ('playbooks',         'curated knowledge: a playbook promoted on one program is the same document on the next'),
 ('playbook_triggers', 'belongs to the playbook'),
 ('playbook_outputs',  'belongs to the playbook'),
 ('playbook_skills',   'belongs to the playbook'),
 ('playbook_evidence', 'belongs to the playbook');


-- ===========================================================================
-- E -- selection: 180 -> trigger -> metadata -> conflict -> N
-- ===========================================================================

-- `risk_rank(text)` is ticket 28's, defined 0..3 over the same four classes in
-- the same order. 027 defined its own 1..4; both uses below are `<=` between
-- two ranks and an `IS NULL` test, so the offset is unobservable and a second
-- definition would only be a second place for the order to drift.

-- Stage 1.  Set containment, nothing else.
CREATE FUNCTION playbooks_by_trigger(p_program uuid, p_subject uuid)
RETURNS SETOF uuid LANGUAGE sql STABLE AS $$
    WITH f AS (SELECT fact FROM subject_facts
                WHERE program_id = p_program AND subject_entity_id = p_subject)
    SELECT p.id FROM playbooks p
     WHERE NOT EXISTS (SELECT 1 FROM playbook_triggers t
                        WHERE t.playbook_id = p.id AND t.mode = 'all'
                          AND NOT EXISTS (SELECT 1 FROM f WHERE f.fact = t.fact))
       AND (NOT EXISTS (SELECT 1 FROM playbook_triggers t
                         WHERE t.playbook_id = p.id AND t.mode = 'any')
            OR EXISTS (SELECT 1 FROM playbook_triggers t JOIN f ON f.fact = t.fact
                        WHERE t.playbook_id = p.id AND t.mode = 'any'));
$$;

-- Stage 2.  Metadata, all of it decidable without a model.
CREATE FUNCTION playbooks_by_metadata(
        p_program uuid, p_subject uuid, p_property_class text,
        p_role text, p_ceiling text)
RETURNS SETOF uuid LANGUAGE sql STABLE AS $$
    SELECT p.id FROM playbooks p
     WHERE p.id IN (SELECT playbooks_by_trigger(p_program, p_subject))
       AND p.status <> 'deprecated'
       AND (p.stale_after IS NULL OR p.stale_after > now())
       AND p.risk <> 'forbidden'
       AND risk_rank(p.risk) <= risk_rank(p_ceiling)
       AND (p_property_class IS NULL
            OR EXISTS (SELECT 1 FROM playbook_outputs o
                        WHERE o.playbook_id = p.id
                          AND (o.property_class = p_property_class
                               OR (p_property_class ~ '^[a-z_]+$'          -- a family
                                   AND o.property_class LIKE p_property_class || '.%'))))
       -- every skill the playbook needs must be loadable by the role that will
       -- run it.  Ticket 09: a skill a role lacks is a load-time error, not a
       -- runtime escalation -- so it is a filter here, not a park later.
       AND NOT EXISTS (SELECT 1 FROM playbook_skills ps
                        WHERE ps.playbook_id = p.id
                          AND NOT EXISTS (SELECT 1 FROM role_skills rs
                                           WHERE rs.role = p_role
                                             AND rs.skill_name = ps.skill_name))
       -- exhausted on this subject already
       AND NOT EXISTS (SELECT 1 FROM playbook_selections s
                        WHERE s.program_id = p_program
                          AND s.subject_entity_id = p_subject
                          AND s.playbook_id = p.id
                          AND s.outcome = 'exhausted');
$$;

-- Conflict is derived, never declared.  Declared composition edges are an
-- O(n^2) set that rots exactly the way ticket 08's task DAG would have, so
-- composition is emergent and only incompatibility is computed.
--
-- The two axes are what one playbook needs the world to hold still and what
-- another playbook changes about it.
CREATE FUNCTION playbooks_conflict(a uuid, b uuid) RETURNS boolean
LANGUAGE sql STABLE AS $$
    SELECT a <> b AND (
           (x.baseline = 'stable_session'  AND y.effects IN ('mutates_session','mutates_account'))
        OR (y.baseline = 'stable_session'  AND x.effects IN ('mutates_session','mutates_account'))
        OR (x.baseline = 'pristine_surface' AND y.effects <> 'read_only')
        OR (y.baseline = 'pristine_surface' AND x.effects <> 'read_only'))
      FROM playbooks x, playbooks y WHERE x.id = a AND y.id = b;
$$;

-- Stage 3.  Deterministic greedy over a total order, so two runs of the same
-- surface hand the model the same set -- ticket 08's determinism requirement.
CREATE FUNCTION select_playbooks(
        p_program uuid, p_subject uuid, p_property_class text DEFAULT NULL,
        p_role text DEFAULT 'web_hunter', p_ceiling text DEFAULT 'constrained',
        p_limit integer DEFAULT 3)
RETURNS TABLE (playbook_id uuid, path text, rank integer, dropped_because text)
LANGUAGE plpgsql STABLE AS $$
DECLARE
    r    record;
    kept uuid[] := '{}';
    n    integer := 0;
    c    uuid;
BEGIN
    IF risk_rank(p_ceiling) IS NULL OR p_ceiling = 'forbidden' THEN
        RAISE EXCEPTION 'autonomy ceiling % is not a runtime risk class', p_ceiling;
    END IF;
    FOR r IN
        SELECT p.id, p.path, p.status, p.specificity
          FROM playbooks p
         WHERE p.id IN (SELECT playbooks_by_metadata(p_program, p_subject,
                                                     p_property_class, p_role, p_ceiling))
         ORDER BY (p.status = 'stable') DESC, p.specificity DESC, p.path
    LOOP
        c := NULL;
        FOREACH c IN ARRAY coalesce(kept, '{}'::uuid[]) LOOP
            IF playbooks_conflict(r.id, c) THEN
                playbook_id := r.id; path := r.path; rank := NULL;
                dropped_because := 'conflicts_with:' || (SELECT p2.path FROM playbooks p2 WHERE p2.id = c);
                RETURN NEXT;
                c := 'ffffffff-ffff-ffff-ffff-ffffffffffff';   -- sentinel: dropped
                EXIT;
            END IF;
        END LOOP;
        CONTINUE WHEN c = 'ffffffff-ffff-ffff-ffff-ffffffffffff';
        EXIT WHEN n >= p_limit;
        n := n + 1;
        kept := kept || r.id;
        playbook_id := r.id; path := r.path; rank := n; dropped_because := NULL;
        RETURN NEXT;
    END LOOP;
END $$;

-- The funnel, as a measurement rather than a claim.
CREATE FUNCTION playbook_funnel(
        p_program uuid, p_subject uuid, p_property_class text DEFAULT NULL,
        p_role text DEFAULT 'web_hunter', p_ceiling text DEFAULT 'constrained',
        p_limit integer DEFAULT 3)
RETURNS TABLE (corpus integer, after_trigger integer, after_metadata integer,
               after_conflict integer, dropped integer)
LANGUAGE sql STABLE AS $$
    SELECT (SELECT count(*)::int FROM playbooks),
           (SELECT count(*)::int FROM playbooks_by_trigger(p_program, p_subject)),
           (SELECT count(*)::int FROM playbooks_by_metadata(p_program, p_subject,
                                        p_property_class, p_role, p_ceiling)),
           (SELECT count(*)::int FROM select_playbooks(p_program, p_subject,
                       p_property_class, p_role, p_ceiling, p_limit) WHERE dropped_because IS NULL),
           (SELECT count(*)::int FROM select_playbooks(p_program, p_subject,
                       p_property_class, p_role, p_ceiling, p_limit) WHERE dropped_because IS NOT NULL);
$$;


-- ===========================================================================
-- F -- evidence, checked by the runtime rather than by the model
--
-- "LLM proposes, runtime commits" at the playbook layer.  Attribution is the
-- task row, written by the runtime at selection; the model never names the
-- playbook a transition is judged against.
-- ===========================================================================

CREATE FUNCTION playbook_evidence_unmet(p_hypothesis uuid, p_to_status text)
RETURNS TABLE (path text, req_role text, req_kind text, req_polarity text,
               need integer, have integer)
LANGUAGE sql STABLE AS $$
    SELECT p.path, e.role, e.observation_kind, e.polarity, e.min_count, h.n
      FROM playbook_selections s
      JOIN tasks t     ON t.id = s.task_id
      JOIN playbooks p ON p.id = s.playbook_id
      JOIN playbook_evidence e ON e.playbook_id = s.playbook_id AND e.to_status = p_to_status
      CROSS JOIN LATERAL (
            SELECT count(*)::int AS n
              FROM hypothesis_evidence he JOIN observations o ON o.id = he.observation_id
             WHERE he.hypothesis_id = p_hypothesis
               AND he.role = e.role AND o.kind = e.observation_kind
               AND (e.polarity IS NULL OR he.polarity = e.polarity)) h
     WHERE t.hypothesis_id = p_hypothesis
       AND s.dropped_because IS NULL
       AND h.n < e.min_count;
$$;

CREATE FUNCTION enforce_playbook_evidence() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE u record;
BEGIN
    SELECT * INTO u FROM playbook_evidence_unmet(NEW.hypothesis_id, NEW.to_status) LIMIT 1;
    IF FOUND THEN
        RAISE EXCEPTION
            'playbook % requires % x (role=%, kind=%) for %, found %',
            u.path, u.need, u.req_role, u.req_kind, NEW.to_status, u.have;
    END IF;
    RETURN NEW;
END $$;

-- Named to sort before enforce_hypothesis_transition: Postgres fires row
-- triggers in name order, and the base rule should not have applied its UPDATE
-- before the stricter rule refuses.  A playbook can only ever be stricter --
-- the two checks are a conjunction, so declaring min_count 1 cannot lower the
-- base transition_rules minimum, and there is no syntax for declaring 0.
CREATE TRIGGER a_playbook_evidence_guard
    BEFORE INSERT ON hypothesis_transitions
    FOR EACH ROW EXECUTE FUNCTION enforce_playbook_evidence();


-- ===========================================================================
-- G -- integrity: the checks that make a hole raise instead of go quiet
-- ===========================================================================

-- Staleness is evaluated at SELECTION, never mid-run.  Re-evaluating it would
-- make a resumed task come back with a different playbook set than it started
-- with, which is ticket 08's rotting-dependency-edge failure in a new costume.
-- So the sweep records the fact and the next pass excludes it; the live run is
-- untouched.
CREATE FUNCTION mark_stale_selections() RETURNS integer LANGUAGE sql AS $$
    WITH u AS (
        UPDATE playbook_selections s SET went_stale_at = now()
          FROM playbooks p
         WHERE p.id = s.playbook_id AND s.outcome = 'running'
           AND s.dropped_because IS NULL AND s.went_stale_at IS NULL
           AND p.stale_after IS NOT NULL AND p.stale_after <= now()
        RETURNING 1)
    SELECT count(*)::int FROM u;
$$;

CREATE FUNCTION check_playbook_integrity()
RETURNS TABLE (severity text, problem text, detail text) LANGUAGE sql STABLE AS $$
    -- HARD: a registered trigger atom nothing computes.  Silently never fires,
    -- so a playbook keyed on it is dead corpus.
    SELECT 'error'::text, 'fact_not_computed'::text, f.id
      FROM surface_facts f
     WHERE position(('''' || f.id || '''') IN pg_get_viewdef('subject_facts'::regclass)) = 0
       AND position((f.id) IN pg_get_viewdef('subject_facts'::regclass)) = 0
UNION ALL
    -- HARD: a playbook naming a skill that is gone.  The FK makes this
    -- unwritable, so a row here means someone bypassed the catalogue.
    SELECT 'error', 'skill_missing', p.path || ' -> ' || ps.skill_name
      FROM playbook_skills ps JOIN playbooks p ON p.id = ps.playbook_id
     WHERE NOT EXISTS (SELECT 1 FROM skills s WHERE s.name = ps.skill_name)
UNION ALL
    -- WARNING: the skill still exists but its content moved since promotion.
    -- Not a refusal: ticket 09 forbids playbooks pinning skill versions, so
    -- drift is corpus rot to be reported, not a reason to stop hunting.
    SELECT 'warning', 'skill_drift', p.path || ' -> ' || ps.skill_name
      FROM playbook_skills ps
      JOIN playbooks p ON p.id = ps.playbook_id
      JOIN skills s ON s.name = ps.skill_name
     WHERE ps.skill_sha256_at_promotion IS NOT NULL
       AND ps.skill_sha256_at_promotion <> s.source_sha256
UNION ALL
    -- WARNING: no role can load every skill this playbook needs, so it can
    -- never be selected by anyone.
    SELECT 'warning', 'playbook_unloadable', p.path
      FROM playbooks p
     WHERE EXISTS (SELECT 1 FROM playbook_skills ps WHERE ps.playbook_id = p.id)
       AND NOT EXISTS (
            SELECT 1 FROM (SELECT DISTINCT role FROM role_skills) r
             WHERE NOT EXISTS (SELECT 1 FROM playbook_skills ps
                                WHERE ps.playbook_id = p.id
                                  AND NOT EXISTS (SELECT 1 FROM role_skills rs
                                                   WHERE rs.role = r.role
                                                     AND rs.skill_name = ps.skill_name)))
UNION ALL
    -- WARNING: a playbook whose outputs sit outside its declared category.
    SELECT 'warning', 'output_outside_category', p.path || ' -> ' || o.property_class
      FROM playbook_outputs o JOIN playbooks p ON p.id = o.playbook_id
      JOIN property_classes pc ON pc.id = o.property_class
     WHERE pc.family_id <> p.category
UNION ALL
    -- WARNING: stale but still `stable`.  Selection already excludes it; this
    -- is the promotion pipeline's cue.
    SELECT 'warning', 'stale_but_stable', p.path
      FROM playbooks p
     WHERE p.status = 'stable' AND p.stale_after IS NOT NULL AND p.stale_after <= now()
UNION ALL
    -- WARNING: a live mission whose playbook went stale under it.
    SELECT 'warning', 'stale_during_run', p.path || ' @ task ' || s.task_id::text
      FROM playbook_selections s JOIN playbooks p ON p.id = s.playbook_id
     WHERE s.went_stale_at IS NOT NULL AND s.outcome = 'running'
UNION ALL
    -- HARD: a trigger atom no playbook uses is fine; a playbook with no trigger
    -- at all is not -- it would match every subject in the program.
    SELECT 'error', 'playbook_without_trigger', p.path
      FROM playbooks p
     WHERE NOT EXISTS (SELECT 1 FROM playbook_triggers t WHERE t.playbook_id = p.id);
$$;

COMMENT ON FUNCTION check_playbook_integrity() IS
 'severity=error is a refusal, severity=warning is corpus rot. The split is the '
 'answer to "missing skill vs changed skill": missing is unwritable and refused, '
 'changed is reported and still selectable.';


-- ===========================================================================
-- H -- what the corpus requires of any migration, which 027 predated
--
-- 027 was written before ticket 33 turned four conventions into checks. None of
-- what follows is a new decision about playbooks; it is the same decisions,
-- written where the checker looks.
-- ===========================================================================

-- H1 -- emission. Every table emits or is exempt, and exactly one of the two.
--
-- Nothing here emits. The catalogue is knowledge loaded from disk by
-- `playbooks.py`, and an event per catalogue row would record the importer's
-- file walk, not anything the runtime learned. `playbook_selections` is the one
-- that carries a runtime decision, and it is `covered`: the scheduler writes the
-- selection in the same transaction as the task that emits `task.created`, and
-- the selection names that task. A second event would double-count one decision.
-- `skills` is already classified (ticket 33 registered it for ticket 34); this
-- migration adds a column to it, not the table.
INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
 ('surface_facts',      'reference', 'the trigger-atom vocabulary; changed only by migration', '10'),
 ('role_skills',        'reference', 'the roster''s per-role skill list; changed only by migration', '11'),
 ('playbooks',          'reference', 'curated knowledge imported from markdown by playbooks.py; the file is the record and its sha256 is in the row', '10'),
 ('playbook_triggers',  'reference', 'belongs to the playbook; loaded and replaced with it', '10'),
 ('playbook_outputs',   'reference', 'belongs to the playbook; loaded and replaced with it', '10'),
 ('playbook_skills',    'reference', 'belongs to the playbook; loaded and replaced with it', '10'),
 ('playbook_evidence',  'reference', 'belongs to the playbook; loaded and replaced with it', '10'),
 ('playbook_selections','covered',   'written in the same transaction as the task it names, and task.created is that record; the selection is how the task was assembled, not a second thing that happened', '10');


-- H2 -- the purge graph. Ticket 07 check (e): a foreign key with a delete
-- action that is not declared here re-opens the purge silently.
--
-- The four catalogue children cascade off `playbooks`, which is program-global:
-- the edge is a catalogue delete, not a program purge, and it is declared for
-- the same reason -- the checker asks about delete actions, not about programs.
-- `playbook_selections` has three, and all three are the purge: its program, the
-- task it was made for, and the entity it was made about.
INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
 ('playbook_triggers',  'playbook_id',       'catalogue child: a trigger without its playbook is not a row'),
 ('playbook_outputs',   'playbook_id',       'catalogue child: an output without its playbook is not a row'),
 ('playbook_skills',    'playbook_id',       'catalogue child: a skill requirement without its playbook is not a row'),
 ('playbook_evidence',  'playbook_id',       'catalogue child: an evidence rule without its playbook is not a row'),
 ('playbook_selections','program_id',        'program-scoped: the purge root'),
 ('playbook_selections','task_id',           'the selection was made for this task and has no meaning without it'),
 ('playbook_selections','subject_entity_id', 'the selection was made about this entity and has no meaning without it');


-- H3 -- the agent read surface. 027 wrote seven relation-level `GRANT SELECT
-- ... TO rk2_state`; ticket 33 revoked relation grants from that role outright
-- and made publication a per-column decision, so the same seven tables are
-- enumerated here instead and `apply_state_grants()` issues the grants.
--
-- Enumerated at migration time on purpose: a column added to one of these
-- tables later is NOT published by inheritance. That is the property section D
-- of ticket 33 bought and it is not worth spending for brevity here.
INSERT INTO state_read_surface (table_name, column_name, added_by)
SELECT c.relname, a.attname, '10'
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
  JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
 WHERE c.relname IN ('surface_facts','playbooks','playbook_triggers','playbook_outputs',
                     'playbook_skills','playbook_evidence','playbook_selections');


-- H4 -- the integrity check becomes a standing check.
--
-- Errors only. The four warnings are drift a human triages (a skill file moved,
-- a stable playbook aged out); the four errors are states in which the catalogue
-- cannot be used at all, and those are the ones no `up` may leave behind.
INSERT INTO standing_checks (name, query, owner_ticket, note) VALUES
 ('playbook_integrity',
  'SELECT * FROM check_playbook_integrity() WHERE severity = ''error''',
  '10',
  'no dead corpus: every fact is computed, every named skill exists, every playbook has a trigger');
