-- ===========================================================================
-- Production harness 22 -- the Surface gets a fingerprint, and its deltas
-- ===========================================================================
-- 012 created `surface_fingerprints` with the contents charged to a later
-- ticket and 023 wrote the scheduler half that reads them: a retest trigger
-- fires when the Program's newest fingerprint differs from the one recorded
-- when the Hypothesis was settled. Both halves have been waiting for the
-- thing itself. This file is the thing itself.
--
-- Six things, and each one is a criterion.
--
--   The projection. `rk2_surface_projection` is the documented canonical
--   input: the Application's kind, its Endpoints, their Parameters, the
--   Technologies it runs and the Identity relationships that reach into it.
--   Sorted by a key each element carries, and holding no timestamp, no
--   identifier and no label -- so the fingerprint is a statement about a
--   surface and not about the rows that happen to hold it.
--
--   The value. `rk2_surface_fingerprint` is sha256 over the projection's
--   canonical text, which is `v_records`'s spelling of the same idea. Identical
--   surfaces come out identical whatever order they were written in, because
--   `jsonb` has one text form per value and every list in the projection is
--   sorted. The word for that value is `fingerprint`, everywhere: CONTEXT.md
--   tells this file to avoid hash, version, snapshot and signature, and a
--   fifth synonym invented here would be the same mistake with a new spelling.
--
--   The deltas. `surface_deltas` is one row per element that appeared,
--   disappeared or changed between two fingerprints of one Application, typed
--   `<section>_added`, `_removed` or `_changed`, carrying the element before
--   and after and the subject Entity where one row answers to the key.
--
--   The operation. `compute_surface_fingerprint` is a runtime verb. It writes
--   the fingerprint row, the deltas and one `surface.fingerprinted` Event, and
--   nothing else in the corpus computes a fingerprint -- no view, no read, no
--   trigger. A read that recomputed would make the value a function of who
--   looked and when. `fingerprint_program_surface` is the same verb over every
--   Application of one Program, which is what "after recon" means when a
--   promotion can reach more than one of them; `execution.py` calls it in the
--   transaction that promotes a recon result.
--
--   The classes. `surface_delta_property_classes` says which Property classes
--   each kind of change puts back in question, as rows. Ticket 34 joins them;
--   it does not read a sentence in a comment and decide what "relevant" meant.
--
--   The twins. Two Applications with the same routes, parameters and stack
--   fingerprint the same however their rows were written and whatever they
--   are called, because the projection holds neither the label nor the address.
--   The one the vulnerable twin has and the secure one has not is a delta with
--   a subject and a list of classes.
--
-- WHAT THE PROJECTION LEAVES OUT, and why each absence is load-bearing:
--
--   `base_url` and every label. An Application's address is its identity, not
--   its surface, and a fingerprint is compared against itself over time.
--   Including either would make the twins of criterion 6 differ by the two
--   things about them that were never the point.
--   Identity slot names. `identities_slot_idx` is unique per Program since
--   017, so two Applications of one Program cannot share a slot name and the
--   twins of criterion 6 could never agree while the projection carried it.
--   What is surface-relevant about an Identity is its class -- 007's retest
--   trigger is called `new_identity_class` -- so the projection carries the
--   class and collapses two Identities of one class that hold the same thing
--   into one element.
--   `first_seen_at`, `last_seen_at`, `banner`, `asn`, `cpe`, `secret_ref`.
--   Timestamps are the noise criterion 1 names; the rest are either the
--   harness's own bookkeeping or not observable from the outside.
--
-- WHAT THIS FILE DOES NOT DO. 023's `rank_pass` compares the Program's newest
-- fingerprint against the one a trigger recorded, and a Program with two
-- Applications now has two rows racing for "newest". That is the retest
-- wiring, it is ticket 34's, and this file deliberately leaves 023 alone: the
-- fingerprint is per Application because 012 made the column NOT NULL, and a
-- ticket that changed what fires a retest while inventing the input would be
-- two changes nobody could review apart.
-- ===========================================================================


-- ---------------------------------------------------------------------------
-- 1. What the projection is made of
-- ---------------------------------------------------------------------------
-- The sections as rows, because three other things are derived from this list:
-- the delta kinds, the standing check that the projection still has every
-- section, and the prose an operator reads. A section added in the function
-- and forgotten here is a change nothing would report.

-- The three ways an element can differ, as a value, for 021's reason: the seed
-- of the vocabulary, the CHECK on it and the arm that asserts the derivation
-- all need the list, and three spellings of it would be three chances to
-- disagree.
CREATE FUNCTION rk2_surface_changes() RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $fn$
    SELECT ARRAY['added','removed','changed']::text[]
$fn$;

COMMENT ON FUNCTION rk2_surface_changes() IS
    'What can happen to one element between two fingerprints. One definition, '
    'so the delta vocabulary and the check over it cannot drift apart.';

CREATE TABLE surface_projection_sections (
    section      text PRIMARY KEY,
    delta_prefix text NOT NULL UNIQUE,
    note         text NOT NULL
);

INSERT INTO surface_projection_sections (section, delta_prefix, note) VALUES
    ('endpoints', 'endpoint',
     'method and path template, with the auth flag and request content type'),
    ('parameters', 'parameter',
     'name, location, value class and whether it was seen reflected, under its route'),
    ('technologies', 'technology',
     'the name the Application runs, with every version currently attributed to it'),
    ('identity_relationships', 'identity_relationship',
     'which class of Identity owns what in this Application, and its memberships');

COMMENT ON TABLE surface_projection_sections IS
    'The four sections of the Surface projection. The delta kinds are derived '
    'from this list, which is why a section is a row and not a literal.';

INSERT INTO program_global_tables (table_name, reason) VALUES
    ('surface_projection_sections', 'the shape of the fingerprint input');


-- ---------------------------------------------------------------------------
-- 2. The projection
-- ---------------------------------------------------------------------------
-- Every element carries a `key`: the natural name of the thing, stable across
-- runs and unique within its section. The key is what a delta is about, what
-- the subject lookup resolves and what the lists are sorted by -- one string
-- doing all three jobs, so two elements that disagree about being the same
-- thing cannot exist.
--
-- The keys are written once, here, and everything else joins them. The
-- projection needs them to name its elements, the subject lookup needs them to
-- get back to a row, and a second spelling of "a route is its method and its
-- path" would be the place the two stopped agreeing.

CREATE FUNCTION rk2_surface_reach(p_application uuid)
RETURNS TABLE (entity_id uuid, key text)
LANGUAGE sql STABLE AS $fn$
    -- Everything in this Application an Identity can be said to hold, each
    -- under the key the projection knows it by: the Application, its routes and
    -- their parameters.
    SELECT p_application, 'application'
 UNION ALL
    SELECT en.entity_id, en.method || ' ' || en.path_template
      FROM endpoints en
     WHERE en.application_id = p_application
 UNION ALL
    SELECT pa.entity_id,
           en.method || ' ' || en.path_template
           || '#' || pa.location || ':' || pa.name
      FROM parameters pa
      JOIN endpoints en ON en.entity_id = pa.endpoint_id
     WHERE en.application_id = p_application
$fn$;

COMMENT ON FUNCTION rk2_surface_reach(uuid) IS
    'Every row of one Application under its projection key. The one definition '
    'of what an element is called, read by the projection and by the subject lookup.';

-- Which class of Identity holds what in this Application, one row per hold.
-- Extracted rather than written twice: the projection groups these into
-- elements and the subject lookup resolves one of them back to the holder, and
-- the membership rule below is the kind of predicate that stops being the same
-- predicate the second time somebody edits one copy of it.
CREATE FUNCTION rk2_surface_holds(p_application uuid)
RETURNS TABLE (entity_id uuid, class text, type text, target text)
LANGUAGE sql STABLE AS $fn$
    SELECT DISTINCT
           rel.src_entity_id,
           idn.class,
           rel.type,
           CASE WHEN rel.type = 'member_of' THEN 'identity:' || other.class
                ELSE reach.key END
      FROM relationships rel
      JOIN identities idn ON idn.entity_id = rel.src_entity_id
      LEFT JOIN rk2_surface_reach(p_application) reach
             ON reach.entity_id = rel.dst_entity_id
      LEFT JOIN identities other ON other.entity_id = rel.dst_entity_id
     WHERE (rel.type = 'owns' AND reach.entity_id IS NOT NULL)
        -- A membership is surface-relevant only for an Identity that holds
        -- something here. Every other Identity's org chart belongs to some
        -- other Application's fingerprint.
        OR (rel.type = 'member_of' AND other.entity_id IS NOT NULL
            AND EXISTS (SELECT 1 FROM relationships own
                          JOIN rk2_surface_reach(p_application) r2
                            ON r2.entity_id = own.dst_entity_id
                         WHERE own.type = 'owns'
                           AND own.src_entity_id = rel.src_entity_id))
$fn$;

COMMENT ON FUNCTION rk2_surface_holds(uuid) IS
    'One row per Identity hold that reaches into this Application, with the '
    'holder. The one definition of what a surface-relevant hold is.';

CREATE FUNCTION rk2_surface_projection(p_application uuid) RETURNS jsonb
LANGUAGE sql STABLE AS $fn$
    WITH reach AS (
        SELECT * FROM rk2_surface_reach(p_application)
    ), route AS (
        SELECT en.entity_id, reach.key,
               en.method, en.path_template,
               en.auth_required, en.request_content_type
          FROM endpoints en
          JOIN reach ON reach.entity_id = en.entity_id
         WHERE en.application_id = p_application
    ), field AS (
        SELECT pa.entity_id, reach.key,
               r.key AS route_key, pa.name, pa.location, pa.value_class, pa.reflected
          FROM parameters pa
          JOIN route r ON r.entity_id = pa.endpoint_id
          JOIN reach ON reach.entity_id = pa.entity_id
    ), stack AS (
        -- Keyed by name, with the versions beside it, so an upgrade is one
        -- `technology_changed` rather than a removal and an addition that a
        -- reader has to pair up again.
        SELECT te.name AS key,
               coalesce(jsonb_agg(DISTINCT to_jsonb(te.version)
                                  ORDER BY to_jsonb(te.version))
                        FILTER (WHERE te.version IS NOT NULL), '[]'::jsonb) AS versions
          FROM relationships rel
          JOIN technologies te ON te.entity_id = rel.dst_entity_id
         WHERE rel.src_entity_id = p_application AND rel.type = 'runs'
         GROUP BY te.name
    ), held AS (
        -- Keyed by the class and the kind of hold rather than by one target,
        -- for the reason the stack is keyed by name: a class that gained a
        -- route is that class changing, and a `_changed` a key can never
        -- express is a delta kind nothing could ever produce.
        SELECT h.class || '|' || h.type AS key, h.class, h.type,
               jsonb_agg(DISTINCT to_jsonb(h.target) ORDER BY to_jsonb(h.target)) AS targets
          FROM rk2_surface_holds(p_application) h
         GROUP BY h.class, h.type
    )
    SELECT jsonb_build_object(
        'application_kind', (SELECT ap.kind FROM applications ap
                              WHERE ap.entity_id = p_application),
        'endpoints', (
            SELECT coalesce(jsonb_agg(e.element ORDER BY e.element ->> 'key'), '[]'::jsonb)
              FROM (SELECT jsonb_build_object(
                               'key', r.key,
                               'method', r.method,
                               'path_template', r.path_template,
                               'auth_required', r.auth_required,
                               'request_content_type', r.request_content_type) AS element
                      FROM route r) e),
        'parameters', (
            SELECT coalesce(jsonb_agg(e.element ORDER BY e.element ->> 'key'), '[]'::jsonb)
              FROM (SELECT jsonb_build_object(
                               'key', f.key,
                               'endpoint', f.route_key,
                               'name', f.name,
                               'location', f.location,
                               'value_class', f.value_class,
                               'reflected', f.reflected) AS element
                      FROM field f) e),
        'technologies', (
            SELECT coalesce(jsonb_agg(e.element ORDER BY e.element ->> 'key'), '[]'::jsonb)
              FROM (SELECT jsonb_build_object(
                               'key', s.key,
                               'versions', s.versions) AS element
                      FROM stack s) e),
        'identity_relationships', (
            SELECT coalesce(jsonb_agg(e.element ORDER BY e.element ->> 'key'), '[]'::jsonb)
              FROM (SELECT jsonb_build_object(
                               'key', h.key,
                               'identity_class', h.class,
                               'type', h.type,
                               'targets', h.targets) AS element
                      FROM held h) e))
$fn$;

COMMENT ON FUNCTION rk2_surface_projection(uuid) IS
    'The canonical fingerprint input for one Application: four sorted sections '
    'of keyed elements, no timestamp, no identifier and no label.';

CREATE FUNCTION rk2_surface_fingerprint(p_projection jsonb) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $fn$
    SELECT encode(sha256(convert_to(p_projection::text, 'utf8')), 'hex')
$fn$;

COMMENT ON FUNCTION rk2_surface_fingerprint(jsonb) IS
    'sha256 over the projection''s canonical text. `jsonb` has one text form per '
    'value, so insertion order cannot reach the fingerprint.';

REVOKE ALL ON FUNCTION rk2_surface_changes() FROM PUBLIC;
REVOKE ALL ON FUNCTION rk2_surface_reach(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION rk2_surface_holds(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION rk2_surface_projection(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION rk2_surface_fingerprint(jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION rk2_surface_changes() TO rk2_runtime;
GRANT EXECUTE ON FUNCTION rk2_surface_reach(uuid) TO rk2_runtime;
GRANT EXECUTE ON FUNCTION rk2_surface_holds(uuid) TO rk2_runtime;
GRANT EXECUTE ON FUNCTION rk2_surface_projection(uuid) TO rk2_runtime;
GRANT EXECUTE ON FUNCTION rk2_surface_fingerprint(jsonb) TO rk2_runtime;


-- ---------------------------------------------------------------------------
-- 3. The delta vocabulary, and what each kind puts back in question
-- ---------------------------------------------------------------------------
-- Twelve kinds, derived from the four sections rather than typed out, so a
-- fifth section cannot arrive with two of its three kinds.

CREATE TABLE surface_delta_kinds (
    kind    text PRIMARY KEY,
    section text NOT NULL REFERENCES surface_projection_sections(section),
    change  text NOT NULL CHECK (change = ANY (rk2_surface_changes())),
    UNIQUE (section, change)
);

INSERT INTO surface_delta_kinds (kind, section, change)
    SELECT s.delta_prefix || '_' || c.change, s.section, c.change
      FROM surface_projection_sections s
     CROSS JOIN unnest(rk2_surface_changes()) AS c(change);

COMMENT ON TABLE surface_delta_kinds IS
    'The twelve typed deltas, one per section per kind of change. Derived from '
    'surface_projection_sections, which is why nothing here is a literal.';

-- Which Property classes a change puts back in question. Rows because ticket
-- 34's rule is "a typed RELEVANT delta", and relevance stated in prose is a
-- judgement each reader makes again.
--
-- Removals map to nothing, and that is the decision rather than an omission: a
-- route that is gone tests nothing, and a refutation about it is not made due
-- by its subject disappearing. The row still exists, with its subject, so the
-- disappearance is recorded and something later can be built on it.
CREATE TABLE surface_delta_property_classes (
    kind             text NOT NULL REFERENCES surface_delta_kinds(kind),
    property_class_id text NOT NULL REFERENCES property_classes(id),
    note             text NOT NULL,
    PRIMARY KEY (kind, property_class_id)
);

INSERT INTO surface_delta_property_classes (kind, property_class_id, note)
SELECT k.kind, m.property_class_id, m.note
  FROM (VALUES
    -- A route that was not there is a route nothing has been asked about.
    ('endpoint',  'authorization.function_access',
     'a route that appeared or changed may be reachable by a caller who should not reach it'),
    ('endpoint',  'authorization.object_ownership',
     'a route names objects, and whose objects it will serve is settled per route'),
    ('endpoint',  'authentication.credential_verification',
     'the auth flag is part of the element, so a route that stopped requiring one is this delta'),
    ('endpoint',  'session_handling.csrf',
     'a state-changing route is where cross-site submission is settled'),
    ('endpoint',  'rate_limiting.per_identity',
     'a new route is a new thing to repeat'),
    -- A parameter is an input, and an input is where an interpreter is reached.
    ('parameter', 'injection.query_language',
     'a new or changed input may reach a database query'),
    ('parameter', 'injection.command',
     'a new or changed input may reach a shell or process boundary'),
    ('parameter', 'injection.template',
     'a new or changed input may reach a template engine'),
    ('parameter', 'injection.markup',
     'the reflected flag is part of the element, so a parameter that started reflecting is this delta'),
    ('parameter', 'injection.path',
     'a new or changed input may reach a filesystem path'),
    ('parameter', 'injection.request_forgery',
     'a new or changed input may be a URL the server fetches'),
    ('parameter', 'authorization.object_ownership',
     'an identifier parameter is what an ownership check is about'),
    ('parameter', 'information_disclosure.identifier_oracle',
     'a parameter that distinguishes existing from absent objects is an oracle'),
    -- A stack that moved is the closest thing this schema has to a deploy.
    ('technology', 'information_disclosure.error_detail',
     'error pages and stack traces are the framework''s, so a framework that moved moves them'),
    ('technology', 'injection.document_parser',
     'a parser version is the whole of what a parser bug is about'),
    ('technology', 'injection.template',
     'a template engine that moved may render differently'),
    ('technology', 'transport.header_policy',
     'security headers are usually the server''s defaults, and defaults move with versions'),
    ('technology', 'session_handling.cookie_scope',
     'cookie attributes are usually the framework''s defaults'),
    -- A new class of Identity is a new pair to ask every authorization
    -- question about. 007 named this trigger `new_identity_class`.
    ('identity_relationship', 'authorization.tenant_isolation',
     'a membership that appeared or changed is a boundary that can now be crossed'),
    ('identity_relationship', 'authorization.object_ownership',
     'a new holder is a new pair for every ownership question'),
    ('identity_relationship', 'authorization.function_access',
     'a new class of holder is a new answer to who may reach a route'),
    ('identity_relationship', 'authorization.token_scope',
     'a credential honoured beyond its scope is settled per holder')
  ) AS m(prefix, property_class_id, note)
  JOIN surface_projection_sections s ON s.delta_prefix = m.prefix
  JOIN surface_delta_kinds k ON k.section = s.section AND k.change IN ('added','changed');

COMMENT ON TABLE surface_delta_property_classes IS
    'Which Property classes each typed delta puts back in question. Removals '
    'map to nothing on purpose: a subject that is gone tests nothing.';

INSERT INTO program_global_tables (table_name, reason) VALUES
    ('surface_delta_kinds',            'the delta vocabulary'),
    ('surface_delta_property_classes', 'which Property classes a delta puts back in question');


-- ---------------------------------------------------------------------------
-- 4. The deltas themselves
-- ---------------------------------------------------------------------------
-- 012 gave `surface_fingerprints` no composite key, because nothing had ever
-- referenced it. 017's rule 1 wants one before anything does.

ALTER TABLE surface_fingerprints ADD CONSTRAINT surface_fingerprints_id_program_key
    UNIQUE (id, program_id);

CREATE TABLE surface_deltas (
    id                      uuid NOT NULL PRIMARY KEY DEFAULT uuidv7(),
    program_id              uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    application_entity_id   uuid NOT NULL,
    fingerprint_id          uuid NOT NULL,
    previous_fingerprint_id uuid NOT NULL,
    kind                    text NOT NULL REFERENCES surface_delta_kinds(kind),
    -- The subject, where one row answers to the key. Null is not an evasion:
    -- a removed element names something the Program may no longer hold, and a
    -- key two rows answer to -- one Identity class holding one route twice --
    -- is a subject this delta genuinely does not have. `subject_key` is
    -- NOT NULL for exactly that reason: it always says what changed.
    subject_entity_id       uuid,
    subject_key             text NOT NULL,
    before_element          jsonb,
    after_element           jsonb,
    detected_at             timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (application_entity_id, program_id)   REFERENCES entities(id, program_id),
    FOREIGN KEY (subject_entity_id, program_id)       REFERENCES entities(id, program_id),
    FOREIGN KEY (fingerprint_id, program_id)          REFERENCES surface_fingerprints(id, program_id),
    FOREIGN KEY (previous_fingerprint_id, program_id) REFERENCES surface_fingerprints(id, program_id),
    -- An added element has no before and a removed one has no after; a change
    -- has both and they differ. Stated here because a delta that says nothing
    -- happened would still join ticket 34's retest rule.
    CHECK (before_element IS NOT NULL OR after_element IS NOT NULL),
    CHECK (before_element IS DISTINCT FROM after_element),
    -- One recompute reports one thing per subject per kind. It does not make a
    -- second recompute idempotent -- that one mints its own fingerprint row and
    -- collides with nothing. What it forbids is the writer emitting two rows
    -- for one element of one comparison, which is what a key that stopped
    -- being unique inside its section would produce.
    UNIQUE (fingerprint_id, kind, subject_key)
);

CREATE INDEX surface_deltas_application_idx
    ON surface_deltas (application_entity_id, detected_at DESC);
CREATE INDEX surface_deltas_subject_idx
    ON surface_deltas (subject_entity_id) WHERE subject_entity_id IS NOT NULL;

COMMENT ON TABLE surface_deltas IS
    'One row per element that appeared, disappeared or changed between two '
    'fingerprints of one Application.';

INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
    ('surface_deltas', 'program_id', 'program-scoped: the purge root');

-- `derived` for the same reason 030 classified `surface_fingerprints` that
-- way: both are recomputable from the rows that produced them, and the act
-- that produced them is `surface.fingerprinted`, which is one Event rather
-- than one per element.
INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
    ('surface_deltas', 'derived',
     'recomputable from two fingerprint rows; surface.fingerprinted records the act', '22'),
    ('surface_projection_sections', 'reference',
     'the shape of the projection, changed only by migration', '22'),
    ('surface_delta_kinds', 'reference',
     'the delta vocabulary, changed only by migration', '22'),
    ('surface_delta_property_classes', 'reference',
     'which classes a delta puts back in question, changed only by migration', '22');

GRANT SELECT, INSERT, UPDATE, DELETE ON surface_deltas TO rk2_runtime;
GRANT SELECT ON surface_projection_sections TO rk2_runtime;
GRANT SELECT ON surface_delta_kinds TO rk2_runtime;
GRANT SELECT ON surface_delta_property_classes TO rk2_runtime;

-- Not granted to `rk2_state`, which is 020's decision about
-- `surface_fingerprints` applied to the thing derived from it: an agent that
-- can read what the runtime is watching for change can aim at it, and the
-- Surface itself is already readable as Entity records.


-- ---------------------------------------------------------------------------
-- 5. Comparing two projections
-- ---------------------------------------------------------------------------

CREATE FUNCTION rk2_surface_section_deltas(p_before jsonb, p_after jsonb)
RETURNS TABLE (section text, change text, subject_key text,
               before_element jsonb, after_element jsonb)
LANGUAGE sql STABLE AS $fn$
    WITH was AS (
        SELECT s.section, x.element ->> 'key' AS key, x.element
          FROM surface_projection_sections s
         CROSS JOIN LATERAL jsonb_array_elements(
                        coalesce(p_before -> s.section, '[]'::jsonb)) AS x(element)
    ), is_now AS (
        SELECT s.section, x.element ->> 'key' AS key, x.element
          FROM surface_projection_sections s
         CROSS JOIN LATERAL jsonb_array_elements(
                        coalesce(p_after -> s.section, '[]'::jsonb)) AS x(element)
    )
    SELECT coalesce(n.section, w.section),
           CASE WHEN w.key IS NULL THEN 'added'
                WHEN n.key IS NULL THEN 'removed'
                ELSE 'changed' END,
           coalesce(n.key, w.key),
           w.element, n.element
      FROM is_now n
      FULL JOIN was w ON w.section = n.section AND w.key = n.key
     WHERE w.element IS DISTINCT FROM n.element
$fn$;

COMMENT ON FUNCTION rk2_surface_section_deltas(jsonb, jsonb) IS
    'Two projections in, one row per element that differs out. Keyed by the '
    'element''s own key, so a moved element is a change and not a pair.';

-- Which row a delta is about, where exactly one row answers to the key. The
-- key is the natural name and the identifier is not in the projection, so this
-- is the one place the two are put back together.
CREATE FUNCTION rk2_surface_subject(p_application uuid, p_section text, p_key text)
RETURNS uuid
LANGUAGE plpgsql STABLE AS $fn$
DECLARE v_subject uuid;
BEGIN
    CASE p_section
    WHEN 'endpoints', 'parameters' THEN
        -- Both are rows of the Application, so both are the reach read
        -- backwards. A removed element resolves to nothing, which is the
        -- honest answer: the row is gone. `strict` for the same reason as the
        -- two branches below -- a key two rows answer to is a key, not a
        -- subject, and a plain select would pick one of them and say nothing.
        SELECT r.entity_id INTO STRICT v_subject
          FROM rk2_surface_reach(p_application) r WHERE r.key = p_key;
    WHEN 'technologies' THEN
        -- One name, two versions, two Entities: a subject this delta does not
        -- have. `strict` is what says so rather than picking one of them.
        SELECT te.entity_id INTO STRICT v_subject
          FROM relationships rel
          JOIN technologies te ON te.entity_id = rel.dst_entity_id
         WHERE rel.src_entity_id = p_application AND rel.type = 'runs'
           AND te.name = p_key;
    WHEN 'identity_relationships' THEN
        -- The subject is the holder, and a class two Identities share is a key
        -- neither of them owns. `distinct` because one holder holding three
        -- routes is still one subject, and the element is keyed by the class
        -- rather than by the route.
        SELECT DISTINCT h.entity_id INTO STRICT v_subject
          FROM rk2_surface_holds(p_application) h
         WHERE h.class = split_part(p_key, '|', 1)
           AND h.type = split_part(p_key, '|', 2);
    ELSE
        -- A section registered in section 1 and not answered here would give
        -- every one of its deltas a null subject and no arm would notice, so
        -- the fifth section is a refusal rather than a silence.
        RAISE EXCEPTION 'no subject rule for projection section %', p_section
            USING ERRCODE = 'feature_not_supported';
    END CASE;
    RETURN v_subject;
EXCEPTION
    -- TOO_MANY_ROWS from a STRICT select, and NO_DATA_FOUND from one whose
    -- subject has since been removed. Both mean the same thing here: the key
    -- says what changed and no single row answers to it.
    WHEN too_many_rows OR no_data_found THEN
        RETURN NULL;
END $fn$;

COMMENT ON FUNCTION rk2_surface_subject(uuid, text, text) IS
    'The row one delta is about, or null where the key names no single row. '
    'Raises for a projection section it has no rule for.';

REVOKE ALL ON FUNCTION rk2_surface_section_deltas(jsonb, jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION rk2_surface_subject(uuid, text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION rk2_surface_section_deltas(jsonb, jsonb) TO rk2_runtime;
GRANT EXECUTE ON FUNCTION rk2_surface_subject(uuid, text, text) TO rk2_runtime;


-- ---------------------------------------------------------------------------
-- 6. The operation
-- ---------------------------------------------------------------------------
-- One verb, and the only thing in the corpus that writes a fingerprint. It
-- always writes a row, including when nothing moved: "we looked and it was the
-- same" is the fact ticket 34's third criterion rests on, and a function that
-- only recorded changes could not tell an unchanged surface from one nobody
-- had looked at since.
--
-- The first fingerprint of an Application produces no deltas. There is nothing
-- to have changed from, and N `added` rows against an empty predecessor would
-- put the whole of a first recon into a table whose rows mean "this moved".

INSERT INTO event_types (id, family, subject_table, description) VALUES
    ('surface.fingerprinted', 'occurrence', NULL,
     'the runtime recomputed one Application''s Surface fingerprint (ticket 22)');

CREATE FUNCTION compute_surface_fingerprint(p_application uuid) RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p             uuid := rk2_program_required();
    v_label       text;
    v_projection  jsonb;
    v_fingerprint text;
    v_previous    surface_fingerprints%ROWTYPE;
    v_id          uuid;
    v_deltas      bigint := 0;
    v_by_kind     jsonb := '{}'::jsonb;
    v_result      jsonb;
BEGIN
    SELECT e.label INTO v_label
      FROM applications ap
      JOIN entities e ON e.id = ap.entity_id
     WHERE ap.entity_id = p_application AND e.program_id = p;
    IF NOT FOUND THEN
        -- Including the case where the Application is another Program's. The
        -- message is the same either way, for `state.py`'s reason: two ways of
        -- not having a row are one answer.
        RAISE EXCEPTION 'no application % in this program', p_application
            USING ERRCODE = 'no_data_found';
    END IF;

    v_projection  := rk2_surface_projection(p_application);
    v_fingerprint := rk2_surface_fingerprint(v_projection);

    SELECT * INTO v_previous FROM surface_fingerprints sf
     WHERE sf.program_id = p AND sf.application_entity_id = p_application
     ORDER BY sf.computed_at DESC, sf.id DESC LIMIT 1;

    INSERT INTO surface_fingerprints
        (program_id, application_entity_id, fingerprint, inputs)
    VALUES (p, p_application, v_fingerprint, v_projection)
    RETURNING id INTO v_id;

    IF v_previous.id IS NOT NULL THEN
        WITH written AS (
            INSERT INTO surface_deltas
                (program_id, application_entity_id, fingerprint_id,
                 previous_fingerprint_id, kind, subject_entity_id, subject_key,
                 before_element, after_element)
            SELECT p, p_application, v_id, v_previous.id, k.kind,
                   rk2_surface_subject(p_application, d.section, d.subject_key),
                   d.subject_key, d.before_element, d.after_element
              FROM rk2_surface_section_deltas(v_previous.inputs, v_projection) d
              JOIN surface_delta_kinds k
                ON k.section = d.section AND k.change = d.change
            RETURNING kind
        )
        SELECT coalesce(sum(g.n), 0), coalesce(jsonb_object_agg(g.kind, g.n), '{}'::jsonb)
          INTO v_deltas, v_by_kind
          FROM (SELECT kind, count(*) AS n FROM written GROUP BY kind) g;
    END IF;

    -- One object, said once. The Event and the caller are entitled to exactly
    -- the same account of what just happened, and two `jsonb_build_object`
    -- calls differing by one key would be the place they stopped being.
    v_result := jsonb_build_object(
        'application', v_label,
        'application_entity_id', p_application,
        'fingerprint_id', v_id,
        'fingerprint', v_fingerprint,
        'previous_fingerprint', v_previous.fingerprint,
        'baseline', v_previous.id IS NULL,
        'changed', v_previous.id IS NOT NULL
                   AND v_previous.fingerprint IS DISTINCT FROM v_fingerprint,
        'deltas', v_deltas,
        'by_kind', v_by_kind);

    INSERT INTO events (program_id, type, actor_kind, payload)
    VALUES (p, 'surface.fingerprinted', 'runtime', v_result);

    RETURN v_result;
END $fn$;

COMMENT ON FUNCTION compute_surface_fingerprint(uuid) IS
    'Recompute one Application''s Surface fingerprint: one row, its deltas '
    'against the previous row, and one surface.fingerprinted Event. The only '
    'writer of surface_fingerprints, and never reached from a read.';

-- "After recon", as one call. A promotion turns one agent result into rows
-- that can reach several Applications, and `promote_proposal` returns labels
-- rather than which Application each one landed under -- so the runtime asks
-- for the Program rather than reconstructing the list, and an Application the
-- promotion did not touch gets the row that says so.
--
-- Not a trigger on promotion, for criterion 4's reason read forwards as well
-- as backwards: the fingerprint is something the runtime decides to do and
-- records, not something that happens to a table while somebody writes to it.
CREATE FUNCTION fingerprint_program_surface() RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p           uuid := rk2_program_required();
    v_one       jsonb;
    v_results   jsonb := '[]'::jsonb;
    v_changed   integer := 0;
    v_app       uuid;
BEGIN
    FOR v_app IN
        SELECT ap.entity_id FROM applications ap
          JOIN entities e ON e.id = ap.entity_id
         WHERE e.program_id = p
         ORDER BY e.label
    LOOP
        v_one     := compute_surface_fingerprint(v_app);
        v_results := v_results || jsonb_build_array(v_one);
        v_changed := v_changed + CASE WHEN (v_one ->> 'changed')::boolean THEN 1 ELSE 0 END;
    END LOOP;

    RETURN jsonb_build_object(
        'applications', jsonb_array_length(v_results),
        'changed', v_changed,
        'fingerprints', v_results);
END $fn$;

COMMENT ON FUNCTION fingerprint_program_surface() IS
    'Recompute every Application''s Surface fingerprint in this Program, one '
    'Event each. What the runtime calls in the transaction that promotes a recon result.';

REVOKE ALL ON FUNCTION compute_surface_fingerprint(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION fingerprint_program_surface() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION compute_surface_fingerprint(uuid) TO rk2_runtime;
GRANT EXECUTE ON FUNCTION fingerprint_program_surface() TO rk2_runtime;


-- ---------------------------------------------------------------------------
-- 7. The read
-- ---------------------------------------------------------------------------
-- What a delta is, with the classes it puts back in question already joined,
-- because every caller needs both and a caller that joined it itself would be
-- the second place that decides what a delta means. Security invoker, like
-- `v_records`: the view reads as whoever asked, so row level security is not
-- something this file has to restate.

-- No identifier columns, which is 020's rule 5 and not an accident of this
-- view: a `v_` read cites labels, and the two things a caller would have
-- reached for an identifier for are here as what they actually are. A
-- fingerprint is named by its own value, because that is what a fingerprint
-- is. A subject is named by its label, because that is what a subject is
-- called.
CREATE VIEW v_surface_deltas WITH (security_invoker = true) AS
SELECT app.label            AS application,
       now_fp.fingerprint   AS fingerprint,
       was_fp.fingerprint   AS previous_fingerprint,
       d.kind,
       k.section,
       k.change,
       subject.label        AS subject,
       d.subject_key,
       d.before_element,
       d.after_element,
       d.detected_at,
       (SELECT coalesce(jsonb_agg(pc.property_class_id ORDER BY pc.property_class_id),
                        '[]'::jsonb)
          FROM surface_delta_property_classes pc
         WHERE pc.kind = d.kind) AS property_classes
  FROM surface_deltas d
  JOIN surface_delta_kinds k ON k.kind = d.kind
  JOIN entities app ON app.id = d.application_entity_id
  JOIN surface_fingerprints now_fp ON now_fp.id = d.fingerprint_id
  JOIN surface_fingerprints was_fp ON was_fp.id = d.previous_fingerprint_id
  LEFT JOIN entities subject ON subject.id = d.subject_entity_id;

COMMENT ON VIEW v_surface_deltas IS
    'Every recorded Surface delta with its subject and the Property classes it '
    'puts back in question. Reading it computes nothing.';

GRANT SELECT ON v_surface_deltas TO rk2_runtime;


-- ---------------------------------------------------------------------------
-- 8. The standing check
-- ---------------------------------------------------------------------------
-- Two arms for what the operation can get wrong and two for the structures
-- that would make the first two meaningless. A projection that lost a section
-- and a vocabulary missing a kind both read as "no violations" from a query
-- over `surface_deltas` alone.

CREATE FUNCTION check_surface_fingerprint()
RETURNS TABLE (problem text, subject text, detail text)
LANGUAGE sql STABLE AS $fn$
    -- Criterion 4, as a row: every fingerprint is an operation somebody ran,
    -- and the Event is what says so. A row without one was written by
    -- something other than `compute_surface_fingerprint`.
    SELECT 'fingerprint_without_event', sf.id::text,
           'no surface.fingerprinted event names this fingerprint'
      FROM surface_fingerprints sf
     WHERE NOT EXISTS (
        SELECT 1 FROM events e
         WHERE e.program_id = sf.program_id
           AND e.type = 'surface.fingerprinted'
           AND e.payload ->> 'fingerprint_id' = sf.id::text)

  UNION ALL
    -- The value is a function of the stored input, so it can be checked
    -- against it. A row where the two disagree is a fingerprint whose input
    -- was edited afterwards, which would make every comparison since a lie.
    SELECT 'fingerprint_disagrees_with_inputs', sf.id::text,
           'fingerprint is not the sha256 of the inputs it was recorded with'
      FROM surface_fingerprints sf
     WHERE sf.fingerprint IS DISTINCT FROM rk2_surface_fingerprint(sf.inputs)

  UNION ALL
    -- The registry and the projection are two statements of one shape. A
    -- section the function stopped emitting is a class of change that silently
    -- stops being detected: `rk2_surface_section_deltas` would compare two
    -- absent lists and find them equal.
    --
    -- Asked of the function rather than of the stored rows. A projection of no
    -- Application still carries every section as an empty list, which is the
    -- structural question this arm is actually asking; reading
    -- `surface_fingerprints` instead would let one old row that still carries
    -- the section keep the arm green for the rest of the Program's life.
    SELECT 'projection_section_missing', s.section,
           'surface_projection_sections names a section the projection does not carry'
      FROM surface_projection_sections s
     WHERE NOT (rk2_surface_projection(NULL::uuid) ? s.section)

  UNION ALL
    -- The vocabulary is derived from the sections, and the derivation is only
    -- true while nothing has inserted into either table by hand.
    SELECT 'delta_kind_vocabulary_disagrees',
           s.delta_prefix || '_' || c.change,
           'surface_delta_kinds does not carry this section and change'
      FROM surface_projection_sections s
     CROSS JOIN unnest(rk2_surface_changes()) AS c(change)
     WHERE NOT EXISTS (
        SELECT 1 FROM surface_delta_kinds k
         WHERE k.section = s.section AND k.change = c.change
           AND k.kind = s.delta_prefix || '_' || c.change)
$fn$;

REVOKE ALL ON FUNCTION check_surface_fingerprint() FROM PUBLIC;

COMMENT ON FUNCTION check_surface_fingerprint() IS
    'What fingerprinting can get wrong, as rows, plus the two structures that '
    'keep the first two of them empty by construction.';

INSERT INTO standing_checks(name, query, owner_ticket, note) VALUES
    ('surface_fingerprint', 'SELECT * FROM check_surface_fingerprint()', '22',
     'every fingerprint is an operation with an Event and the sha256 of its own recorded input, and the projection still carries every section the delta vocabulary is derived from');

-- The fingerprint of an Application that does not exist: four empty sections
-- and no kind. Not a special case in the function -- every part of the
-- projection is a select that found nothing -- which is what makes it usable
-- as the structural question the third arm above asks.
DO $$
DECLARE v jsonb := rk2_surface_projection(NULL::uuid);
BEGIN
    IF v -> 'endpoints' <> '[]'::jsonb OR v -> 'identity_relationships' <> '[]'::jsonb THEN
        RAISE EXCEPTION 'ph2-22: the empty projection is not empty: %', v;
    END IF;
END $$;


-- ---------------------------------------------------------------------------
-- 9. The invariants this file must not have broken
-- ---------------------------------------------------------------------------

SELECT apply_state_rls();

DO $$
DECLARE n integer; d text;
BEGIN
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_program_isolation();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-22 breaks program isolation (% problems): %', n, d;
    END IF;

    SELECT count(*), string_agg(problem || ': ' || subject, '; ')
      INTO n, d FROM check_surface_fingerprint();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-22 refuses to finish: % fingerprint violation(s): %', n, d;
    END IF;
END $$;
