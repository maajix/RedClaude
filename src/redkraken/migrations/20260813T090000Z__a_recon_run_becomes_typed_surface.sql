-- ===========================================================================
-- Production harness 21 -- a recon run becomes typed Surface
-- ===========================================================================
-- 020 promoted one element list and said why it stopped there: Entities,
-- Relationships and the rest "have their own dedup and transition rules, and a
-- promotion that wrote them here would write them without those rules. The
-- elements stay in `proposals.payload`, which is where ticket 21 reads them
-- from." This is that reading, and it is mostly those rules.
--
-- Six things, and each one is a criterion.
--
--   The canonical form. `rk2_parse_base_url` and `rk2_clean_path` are strict
--   acceptors, not parsers: they refuse anything that is not already the one
--   spelling this schema stores, so no second grammar for URLs or paths enters
--   the system beside `scope.py`'s. `rk2_dedup_key` is the one place a semantic
--   subject becomes the string `UNIQUE (program_id, type, dedup_key)` converges
--   on, which is the whole of "parallel proposals converge on one Entity".
--
--   The scope check. A proposed Entity is scope-classified BEFORE its row is
--   written, by the same `scope_class_of_entity` the projection uses, and a
--   `denied` verdict refuses the element. The Spec forbids discovery outside
--   the configured web and API scope; an Entity written first and projected
--   denied afterwards would be that discovery, recorded.
--
--   The grammar. `relationship_directions` says which ordered pair of types
--   each relationship type may join and `entity_containment` says which pairs
--   are containment and therefore may never be a relationship at all. Both are read by a
--   trigger, so the rule holds for every writer, not only for promotion.
--
--   The provenance. `entity_provenance` and `relationship_provenance` are one
--   row per (subject, evidence): the second proposal of a Host the harness
--   already holds adds a row rather than replacing one, which is what
--   "preserving all valid provenance" has to mean once convergence is the
--   point.
--
--   The origin. `entities.origin` and `relationships.origin` name who put the
--   row there -- the operator's configuration, an import, the runtime's own
--   instruments, or a model whose proposal was promoted. Four values because
--   the criterion names three and the corpus already had a fourth.
--
--   The read. `v_records` carries the origin, the containment parent and the
--   typed relationships on the Entity record itself, so the compact read
--   answers "what is this, what is it part of, what does it join, and who says
--   so" without anything reaching for the proposal the recon child wrote.
-- ===========================================================================


-- ---------------------------------------------------------------------------
-- 1. Two closed vocabularies: what a row can be, and where it came from
-- ---------------------------------------------------------------------------
-- The eight types first, because three later sections ask what they are. 003
-- wrote them as a CHECK on `entities.type`; section 3 seeds one `same_as`
-- direction per type and section 7 asks the same question of a proposed
-- element. Three copies of a closed vocabulary is how a ninth type reaches two
-- of them, so there is one and section 9 asserts that it still says what the
-- column says.
--
-- A function rather than a table: the column's CHECK is already the constraint,
-- and a registry beside it would be a second thing to keep true.

CREATE FUNCTION rk2_entity_types() RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $fn$
    SELECT ARRAY['domain','host','service','application',
                 'endpoint','parameter','technology','identity']::text[]
$fn$;

COMMENT ON FUNCTION rk2_entity_types() IS
    'The eight entity types, as a value. One definition, so the vocabulary the '
    'column takes and the vocabulary promotion offers cannot drift apart.';

-- `configured` is the default and the backfill, because it is what an
-- unmarked Entity actually is: the only writer of `entities` before this file
-- is `program.py`, projecting the identity slots an operator declared. Calling
-- those `observed` would be the schema inventing a discovery.
--
-- Relationships default to `observed` instead, and the asymmetry is the honest
-- one: no configuration document declares a relationship, so one that exists
-- without a promotion behind it was recorded by the runtime from something it
-- saw.
--
-- Two of the four have no writer of `entities` in this file, and both absences
-- are deliberate. `imported` is ticket 58's, which is the one place v1 state
-- crosses into this schema; `observed` on an Entity would be the runtime
-- creating a subject from its own instruments, and every instrument this
-- harness has today produces a Receipt that an agent then reads. Both are in
-- the vocabulary now rather than added later because the criterion is that the
-- origins stay distinguishable: a column that cannot say `imported` makes an
-- importer's first row either a lie or a migration, and one that cannot say
-- `observed` would have promotion answer for the runtime as well.

CREATE FUNCTION rk2_origins() RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $fn$
    SELECT ARRAY['configured','imported','observed','proposed']::text[]
$fn$;

COMMENT ON FUNCTION rk2_origins() IS
    'The four origins a canonical Surface row can have. One definition, so the '
    'two tables and the two checks cannot drift about what an origin is.';

ALTER TABLE entities ADD COLUMN origin text NOT NULL DEFAULT 'configured';
ALTER TABLE entities ADD CONSTRAINT entities_origin_check
    CHECK (origin = ANY (rk2_origins()));

ALTER TABLE relationships ADD COLUMN origin text NOT NULL DEFAULT 'observed';
ALTER TABLE relationships ADD CONSTRAINT relationships_origin_check
    CHECK (origin = ANY (rk2_origins()));

-- 021's `add_entity` gains the origin, dropped and recreated rather than
-- replaced: a `CREATE OR REPLACE` with one more argument is an overload, and
-- an overload here would make every six-argument call ambiguous.
DROP FUNCTION add_entity(uuid, text, text, text, text, integer, text);

CREATE FUNCTION add_entity(p_program uuid, p_type text, p_label text,
                           p_kind text, p_selector text,
                           p_port integer DEFAULT NULL,
                           p_dedup text DEFAULT NULL,
                           p_origin text DEFAULT 'configured')
RETURNS uuid LANGUAGE plpgsql AS $fn$
DECLARE new_id uuid;
BEGIN
    INSERT INTO entities (program_id, type, label, dedup_key, origin,
                          scope_selector_kind, scope_selector, scope_port)
    VALUES (p_program, p_type, p_label,
            coalesce(p_dedup, p_kind || ':' || coalesce(p_selector, p_label)),
            p_origin, p_kind, p_selector, p_port)
    RETURNING id INTO new_id;
    PERFORM refresh_scope_projection(p_program);
    RETURN new_id;
END $fn$;

COMMENT ON FUNCTION add_entity(uuid, text, text, text, text, integer, text, text) IS
    'Insert denied, then project. The origin says who caused the row; it '
    'defaults to the operator''s configuration because that is the only caller '
    'this function has ever had.';


-- ---------------------------------------------------------------------------
-- 2. Containment is structure, and structure is not a relationship
-- ---------------------------------------------------------------------------
-- Three containments exist in this schema and all three are foreign keys on a
-- detail table: a Service is on a Host, an Endpoint is in an Application, a
-- Parameter is of an Endpoint. None of them is expressible as a
-- `relationships` row, and this registry is what makes "none of them" a rule
-- rather than an omission -- section 4 refuses a relationship that joins a
-- containment pair in either direction, and section 8 reports one that already
-- exists.
--
-- The columns name the key that carries the containment so the check can
-- verify the registry against the catalogue. A registry describing a foreign
-- key that is not there would refuse relationships for a structure the schema had
-- stopped enforcing.

CREATE TABLE entity_containment (
    child_type    text NOT NULL,
    parent_type   text NOT NULL,
    detail_table  text NOT NULL,
    parent_column text NOT NULL,
    note          text NOT NULL,
    PRIMARY KEY (child_type, parent_type)
);

INSERT INTO entity_containment
    (child_type, parent_type, detail_table, parent_column, note) VALUES
    ('service',   'host',        'services',   'host_id',
     'a Service is a port on one Host and cannot outlive it'),
    ('endpoint',  'application', 'endpoints',  'application_id',
     'an Endpoint is a route of one Application'),
    ('parameter', 'endpoint',    'parameters', 'endpoint_id',
     'a Parameter is an input of one Endpoint');

COMMENT ON TABLE entity_containment IS
    'The three structural parent links, as rows. Containment is a foreign key '
    'on a detail table and is never a relationships row; this is the list both '
    'the grammar trigger and the standing check read.';

INSERT INTO program_global_tables (table_name, reason) VALUES
    ('entity_containment', 'schema structure: which entity types contain which');


-- ---------------------------------------------------------------------------
-- 3. The relationship vocabulary, with its directions
-- ---------------------------------------------------------------------------
-- 004 wrote the vocabulary as a CHECK and the directions as comments beside
-- it. A comment refuses nothing, so `serves` has been legal from an Endpoint to
-- a Domain since the day it was written. These are the same seven types with
-- the same directions the comments claimed, as rows a trigger can read.
--
-- `same_as` is every type to itself and nothing else, because two rows are one
-- subject or they are not, and a claim that a Host is the same subject as an
-- Endpoint is a category error rather than a duplicate. Nothing writes one yet;
-- the type is 004's and this file makes 004's list enforceable rather than
-- shortening it. `owns` reaches every addressable type from an Identity but
-- not another Identity, because that relationship has a name of its own.

CREATE TABLE relationship_directions (
    type      text NOT NULL,
    src_type  text NOT NULL,
    dst_type  text NOT NULL,
    note      text NOT NULL DEFAULT '',
    PRIMARY KEY (type, src_type, dst_type)
);

COMMENT ON TABLE relationship_directions IS
    'Which ordered pair of entity types each relationship type may join. 004 wrote '
    'as comments; a comment refuses nothing.';

INSERT INTO relationship_directions (type, src_type, dst_type, note) VALUES
    ('resolves_to', 'domain',      'host',        'a name answers with an address'),
    ('serves',      'host',        'application', 'an application is reachable at a host'),
    ('runs',        'host',        'technology',  'a fingerprint attributed to the machine'),
    ('runs',        'application', 'technology',  'a fingerprint attributed to the application'),
    ('owns',        'identity',    'domain',      'resource ownership'),
    ('owns',        'identity',    'host',        'resource ownership'),
    ('owns',        'identity',    'service',     'resource ownership'),
    ('owns',        'identity',    'application', 'resource ownership'),
    ('owns',        'identity',    'endpoint',    'resource ownership'),
    ('owns',        'identity',    'parameter',   'resource ownership'),
    ('member_of',   'identity',    'identity',    'tenant or organisation membership'),
    ('redirects_to','endpoint',    'endpoint',    'one route answers with another');

INSERT INTO relationship_directions (type, src_type, dst_type, note)
    SELECT 'same_as', t.name, t.name, 'the two rows are one subject'
      FROM unnest(rk2_entity_types()) AS t(name);

INSERT INTO program_global_tables (table_name, reason) VALUES
    ('relationship_directions', 'the relationship vocabulary and its directions');

-- The CHECK stays, and it is not redundant: it is the constraint the planner
-- and a restore see, and the trigger below is `ENABLE ALWAYS` for the case
-- where it would not run. What it cannot say is which direction, which is what
-- the table is for. The two must agree, and section 8 asserts that they do.


-- ---------------------------------------------------------------------------
-- 4. The grammar, enforced for every writer
-- ---------------------------------------------------------------------------
-- On the table rather than in the promotion, because promotion is one writer.
-- An operator's psql session, a future importer and a restore that replays a
-- dump are the others, and a relationship with a direction nothing accepts is
-- exactly as wrong whichever of them wrote it.
--
-- Two refusals, worded apart. An unlisted pair is a vocabulary error and the
-- message says whether the reverse would have been accepted, because a reversed
-- relationship is the overwhelmingly likely mistake. A containment pair is a
-- modelling error: the fact is already true in the schema, and recording it
-- again as a relationship would make one containment two facts that can
-- disagree.

CREATE FUNCTION enforce_relationship_grammar() RETURNS trigger
LANGUAGE plpgsql AS $fn$
DECLARE
    v_src  text;
    v_dst  text;
    v_note text;
BEGIN
    SELECT e.type INTO v_src FROM entities e WHERE e.id = NEW.src_entity_id;
    SELECT e.type INTO v_dst FROM entities e WHERE e.id = NEW.dst_entity_id;

    SELECT c.note INTO v_note FROM entity_containment c
     WHERE (c.child_type, c.parent_type) IN ((v_src, v_dst), (v_dst, v_src));
    IF FOUND THEN
        RAISE EXCEPTION
            'relationship % may not join % and %: that pair is containment',
            NEW.type, v_src, v_dst
          USING DETAIL = v_note || ', which is a foreign key on its detail table; '
                         'recording it again as a relationship makes one fact two',
                ERRCODE = 'check_violation';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM relationship_directions d
                    WHERE d.type = NEW.type
                      AND d.src_type = v_src AND d.dst_type = v_dst) THEN
        RAISE EXCEPTION 'relationship % is not defined from % to %',
              NEW.type, v_src, v_dst
          USING DETAIL = CASE WHEN EXISTS (
                                  SELECT 1 FROM relationship_directions d
                                   WHERE d.type = NEW.type
                                     AND d.src_type = v_dst AND d.dst_type = v_src)
                              THEN 'it is defined the other way round; the source '
                                   'and destination are reversed'
                              ELSE 'no direction of this type joins those two types'
                         END,
                ERRCODE = 'check_violation';
    END IF;

    RETURN NEW;
END $fn$;

REVOKE ALL ON FUNCTION enforce_relationship_grammar() FROM PUBLIC;

CREATE TRIGGER relationships_follow_the_grammar
    BEFORE INSERT OR UPDATE ON relationships
    FOR EACH ROW EXECUTE FUNCTION enforce_relationship_grammar();
-- 007's reason, restated: a restore under `session_replication_role = replica`
-- skips ORIGIN triggers, and a relationship that entered during a restore would
-- be indistinguishable from one the grammar accepted.
ALTER TABLE relationships ENABLE ALWAYS TRIGGER relationships_follow_the_grammar;


-- ---------------------------------------------------------------------------
-- 5. Who says so, once per piece of evidence
-- ---------------------------------------------------------------------------
-- One row per (subject, evidence). Convergence is the reason it is a table and
-- not a column: two agent runs that both find `www.example.com` produce one
-- Entity, and the second one's Receipt is not less true for arriving second.
-- A column would hold the first and lose the rest, which is the half of
-- criterion 4 that is easy to miss.
--
-- Every foreign key carries `program_id` -- 017's rule 3 -- so a provenance row
-- citing another Program's Receipt is refused by the key rather than by a
-- clause someone has to remember to write.

CREATE TABLE entity_provenance (
    id           uuid NOT NULL PRIMARY KEY DEFAULT uuidv7(),
    program_id   uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    entity_id    uuid NOT NULL,
    origin       text NOT NULL CHECK (origin = ANY (rk2_origins())),
    proposal_id  uuid,
    element_path text,
    agent_run_id uuid,
    receipt_id   uuid,
    tool_run_id  uuid,
    observed_at  timestamptz NOT NULL DEFAULT now(),
    -- One cascade edge and no more, which is 016's rule: `program_id` is the
    -- purge root and every other key is NO ACTION, so a narrow delete of an
    -- Entity is refused rather than quietly taking its provenance with it.
    FOREIGN KEY (entity_id, program_id)    REFERENCES entities  (id, program_id),
    FOREIGN KEY (proposal_id, program_id)  REFERENCES proposals (id, program_id),
    FOREIGN KEY (agent_run_id, program_id) REFERENCES agent_runs(id, program_id),
    FOREIGN KEY (receipt_id, program_id)   REFERENCES receipts  (id, program_id),
    FOREIGN KEY (tool_run_id, program_id)  REFERENCES tool_runs (id, program_id),
    -- Exactly one evidence reference, or none. None is the configured and
    -- imported case, where the evidence is a document outside the database;
    -- both is the ambiguity 007 refuses on `observations` for the same reason.
    CHECK ((receipt_id IS NULL) OR (tool_run_id IS NULL)),
    -- The idempotence key. A promotion that runs twice writes the same row
    -- once; two different agent runs citing two different Receipts write two.
    UNIQUE (entity_id, origin, proposal_id, element_path)
);

CREATE INDEX entity_provenance_entity_idx ON entity_provenance (entity_id, origin);

COMMENT ON TABLE entity_provenance IS
    'One row per piece of evidence for one Entity. Append-only in practice: '
    'convergence adds rows, never replaces them.';

-- 017's rule 1 wants the composite key, and `relationships` has never been the
-- referenced side of one, so the key it would be referenced by does not exist
-- yet. `entities` got its in 003 for the same reason.
ALTER TABLE relationships ADD CONSTRAINT relationships_id_program_key
    UNIQUE (id, program_id);

CREATE TABLE relationship_provenance (
    id              uuid NOT NULL PRIMARY KEY DEFAULT uuidv7(),
    program_id      uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    relationship_id uuid NOT NULL,
    origin          text NOT NULL CHECK (origin = ANY (rk2_origins())),
    proposal_id     uuid,
    element_path    text,
    agent_run_id    uuid,
    receipt_id      uuid,
    tool_run_id     uuid,
    observed_at     timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (relationship_id, program_id) REFERENCES relationships(id, program_id),
    FOREIGN KEY (proposal_id, program_id)     REFERENCES proposals    (id, program_id),
    FOREIGN KEY (agent_run_id, program_id)    REFERENCES agent_runs   (id, program_id),
    FOREIGN KEY (receipt_id, program_id)      REFERENCES receipts     (id, program_id),
    FOREIGN KEY (tool_run_id, program_id)     REFERENCES tool_runs    (id, program_id),
    CHECK ((receipt_id IS NULL) OR (tool_run_id IS NULL)),
    UNIQUE (relationship_id, origin, proposal_id, element_path)
);

CREATE INDEX relationship_provenance_relationship_idx
    ON relationship_provenance (relationship_id, origin);

INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
    ('entity_provenance',       'program_id', 'program-scoped: the purge root'),
    ('relationship_provenance', 'program_id', 'program-scoped: the purge root');

-- `audit`, not `covered`. The row is an append-only trail of one runtime
-- decision and it is written on its own whenever a second agent run cites an
-- Entity that already exists -- so `entity.created` does not cover it, and an
-- Event per provenance row would put a second copy of the trail in the log.
INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
    ('entity_provenance',       'audit',
     'the append-only trail of what evidence produced one Entity; the row is the record', '21'),
    ('relationship_provenance', 'audit',
     'the append-only trail of what evidence produced one Relationship; the row is the record', '21'),
    ('entity_containment',      'reference', 'schema structure, changed only by migration', '21'),
    ('relationship_directions', 'reference', 'the relationship vocabulary, changed only by migration', '21');

GRANT SELECT, INSERT, UPDATE, DELETE ON entity_provenance TO rk2_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON relationship_provenance TO rk2_runtime;
GRANT SELECT ON entity_containment TO rk2_runtime;
GRANT SELECT ON relationship_directions TO rk2_runtime;

-- What the agent's role may read, column by column -- 033's registry, which is
-- the grant. `apply_state_grants()` issues it; naming a column here and
-- nowhere else is what keeps the read surface reviewable in one table.
--
-- Two `origin` columns and two provenance columns, and no more. `origins` on
-- the record is the whole of what an agent needs from the trail: which kinds
-- of evidence stand behind this row. Which Receipt, from which run, at which
-- second is the supervisor's question, and answering it to a child would put
-- another Program's label one join away from a role that must not resolve one.
INSERT INTO state_read_surface (table_name, column_name, added_by) VALUES
    ('entities',          'origin',    '21'),
    ('relationships',     'origin',    '21'),
    ('entity_provenance', 'entity_id', '21'),
    ('entity_provenance', 'origin',    '21');


-- ---------------------------------------------------------------------------
-- 6. Canonical form
-- ---------------------------------------------------------------------------
-- Strict acceptors, and the distinction matters. `scope.py` owns the one
-- grammar for hosts and paths in this system, and a second implementation here
-- would be a second answer to "is this the same URL". So neither function
-- below normalises anything it is not already sure of: they take the spelling
-- the schema stores, refuse everything else, and hand the caller a sentence
-- saying which part was refused. An agent that wants a percent-encoded path
-- promoted has to send the path.
--
-- The host half is not reimplemented at all: `scope_normalize_host` is 021's
-- mirror of `scope.normalize_host`, and both functions call it.

CREATE FUNCTION rk2_clean_path(p_path text)
RETURNS TABLE(path text, fault text)
LANGUAGE plpgsql IMMUTABLE AS $fn$
DECLARE v text := coalesce(btrim(p_path), '');
BEGIN
    IF v = '' THEN v := '/'; END IF;
    IF left(v, 1) <> '/' THEN
        RETURN QUERY SELECT NULL::text, 'path must be absolute and start with /'::text;
        RETURN;
    END IF;
    IF v ~ '[[:space:]]' OR position('?' IN v) > 0 OR position('#' IN v) > 0 THEN
        RETURN QUERY SELECT NULL::text,
            'path carries a query, a fragment or whitespace; those are not part of the route'::text;
        RETURN;
    END IF;
    -- Percent-encoding is refused rather than decoded. `entities` stores two
    -- spellings of a path and the scope evaluator compares both; producing the
    -- second spelling here would be this file deciding what `%2e%2e` means,
    -- which is the decision `scope.path_variants` already owns.
    IF position('%' IN v) > 0 THEN
        RETURN QUERY SELECT NULL::text,
            'path carries percent-encoding; send the decoded route'::text;
        RETURN;
    END IF;
    IF v LIKE '%//%' OR v LIKE '%/./%' OR v LIKE '%/../%'
       OR right(v, 2) = '/.' OR right(v, 3) = '/..' THEN
        RETURN QUERY SELECT NULL::text, 'path is not in normal form'::text;
        RETURN;
    END IF;
    IF length(v) > 1 AND right(v, 1) = '/' THEN
        v := left(v, length(v) - 1);   -- one trailing slash, which names one route
    END IF;
    RETURN QUERY SELECT v, NULL::text;
END $fn$;

COMMENT ON FUNCTION rk2_clean_path(text) IS
    'The one spelling of a route this schema stores, or the reason the offered '
    'one is not it. An acceptor, not a normaliser: scope.py owns that grammar.';

-- The scheme is one of the four things it returns, not a detail the parse can
-- drop: `applications.base_url` is a URL and a URL says how it is spoken to.
-- An `http://` Application stored as `https://` would be a row telling the next
-- agent run to open a connection this Program never made.
CREATE FUNCTION rk2_parse_base_url(p_url text)
RETURNS TABLE(scheme text, host text, port integer, path text, fault text)
LANGUAGE plpgsql IMMUTABLE AS $fn$
DECLARE
    m         text[];
    authority text;
    v_host    text;
    v_port    text;
    v_path    text;
    v_fault   text;
BEGIN
    m := regexp_match(coalesce(btrim(p_url), ''),
                      '^(https?)://([^/?#[:space:]]+)(/[^?#[:space:]]*)?$');
    IF m IS NULL THEN
        RETURN QUERY SELECT NULL::text, NULL::text, NULL::integer, NULL::text,
            'not an absolute http or https url without query or fragment'::text;
        RETURN;
    END IF;

    authority := m[2];
    -- Credentials in a base URL are a secret in a column an agent can read
    -- back. Refused here rather than stripped, because stripping would promote
    -- the Application and lose the fact that a credential was offered.
    IF position('@' IN authority) > 0 THEN
        RETURN QUERY SELECT NULL::text, NULL::text, NULL::integer, NULL::text,
            'url carries userinfo'::text;
        RETURN;
    END IF;

    IF authority LIKE '[%' THEN
        v_host := split_part(substring(authority FROM 2), ']', 1);
        v_port := nullif(substring(authority FROM position(']' IN authority) + 2), '');
    ELSIF position(':' IN authority) = 0 THEN
        v_host := authority;
        v_port := NULL;
    ELSIF length(authority) - length(replace(authority, ':', '')) = 1 THEN
        v_host := split_part(authority, ':', 1);
        v_port := split_part(authority, ':', 2);
    ELSE
        -- An unbracketed IPv6 literal, which is not a legal authority.
        RETURN QUERY SELECT NULL::text, NULL::text, NULL::integer, NULL::text,
            'ambiguous authority; an IPv6 address must be bracketed'::text;
        RETURN;
    END IF;

    v_host := scope_normalize_host(v_host);
    IF v_host IS NULL THEN
        RETURN QUERY SELECT NULL::text, NULL::text, NULL::integer, NULL::text,
            'host is not a name or address this policy grammar accepts'::text;
        RETURN;
    END IF;
    IF v_port IS NOT NULL AND (v_port !~ '^[0-9]{1,5}$'
                               OR v_port::integer NOT BETWEEN 1 AND 65535) THEN
        RETURN QUERY SELECT NULL::text, NULL::text, NULL::integer, NULL::text,
            'port is not a number between 1 and 65535'::text;
        RETURN;
    END IF;

    SELECT c.path, c.fault INTO v_path, v_fault
      FROM rk2_clean_path(coalesce(m[3], '/')) c;
    IF v_fault IS NOT NULL THEN
        RETURN QUERY SELECT NULL::text, NULL::text, NULL::integer, NULL::text, v_fault;
        RETURN;
    END IF;

    RETURN QUERY SELECT m[1], v_host,
                        coalesce(v_port::integer,
                                 CASE WHEN m[1] = 'https' THEN 443 ELSE 80 END),
                        v_path, NULL::text;
END $fn$;

COMMENT ON FUNCTION rk2_parse_base_url(text) IS
    'An Application base URL split into the four things the schema stores, or '
    'the reason it is not one. Refuses what it cannot spell canonically.';

-- What `UNIQUE (program_id, type, dedup_key)` converges on. One shape for
-- every type so that reading a key tells you which type wrote it:
--
--   domain      the fqdn, with the wildcard marked, because `*.here.com` and
--               `here.com` are two subjects
--   host        the hostname if there is one, else the address
--   service     the Host's key, the port, the protocol
--   application the base URL in its canonical spelling, scheme included:
--               one listener speaks one scheme, so http and https on the same
--               port are two subjects and not one seen twice
--   endpoint    the Application's key, the method, the path template
--   parameter   the Endpoint's key, the location, the name
--   technology  the lowercased name and the version, which are the two halves
--               of a fingerprint that can be more or less specific
--   identity    the slot name, which is already unique per Program
CREATE FUNCTION rk2_dedup_key(p_type text, p_parts text[]) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $fn$
    SELECT p_type || ':' || array_to_string(p_parts, '|')
$fn$;

COMMENT ON FUNCTION rk2_dedup_key(text, text[]) IS
    'The string two proposals of one semantic subject must agree on. The whole '
    'of convergence: the unique key does the rest.';

-- Which evidence one proposed element cites, resolved once for all three walks.
-- Every element list asks it identically -- exactly one of a Receipt label and a
-- Tool Run label, resolved inside this Program -- and 020 wrote the question
-- inline for observations. Two more copies of it in section 7 would be three
-- places to fix the day an element may cite a third kind of evidence.
--
-- Both labels is not an ambiguity to resolve but a refusal to report: it comes
-- back with no kind, which is what makes the caller write `no_provenance`. The
-- label travels back with it, because a refusal that cannot say which label
-- failed is not worth recording.
CREATE FUNCTION rk2_element_evidence(p_program uuid, p_element jsonb)
RETURNS TABLE(receipt_id uuid, tool_run_id uuid, provenance_kind text, cited text)
LANGUAGE sql STABLE AS $fn$
    WITH named AS (
        SELECT nullif(btrim(p_element ->> 'receipt_label'), '')  AS receipt_label,
               nullif(btrim(p_element ->> 'tool_run_label'), '') AS tool_run_label
    )
    SELECT r.id, t.id,
           CASE WHEN r.id IS NOT NULL THEN 'receipt'
                WHEN t.id IS NOT NULL THEN 'tool_run' END,
           coalesce(n.receipt_label, n.tool_run_label)
      FROM named n
      LEFT JOIN receipts r ON r.program_id = p_program
                          AND r.label = n.receipt_label
                          AND n.tool_run_label IS NULL
      LEFT JOIN tool_runs t ON t.program_id = p_program
                           AND t.label = n.tool_run_label
                           AND n.receipt_label IS NULL
$fn$;

REVOKE ALL ON FUNCTION rk2_element_evidence(uuid, jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION rk2_element_evidence(uuid, jsonb) TO rk2_runtime;

COMMENT ON FUNCTION rk2_element_evidence(uuid, jsonb) IS
    'The Receipt or Tool Run one proposed element cites, or no kind at all when '
    'it cites both, neither, or one this Program has not got.';


-- ---------------------------------------------------------------------------
-- 7. Promotion, with three element lists instead of one
-- ---------------------------------------------------------------------------
-- The order of the three walks is the argument for doing them in one function.
--
--   Entities first, because a Relationship joins two of them and an
--   Observation is about one, and an agent run that found a Host and a fact about
--   it proposes both in one result.
--   Relationships second, so both ends can be either an Entity this Program
--   already held or one the walk above just created.
--   Observations last, unchanged except that `subject_ref` now resolves --
--   which closes a real gap: until this file, an Observation about an Entity
--   proposed beside it was refused `no_subject` for naming a label that could
--   not exist yet.
--
-- Four more refusal reasons, all provable only here:
--
--   `malformed_field`   a typed field is absent or is not the canonical
--                       spelling. The cited value is the acceptor's sentence,
--                       because "which field and why" is the whole content of
--                       the refusal.
--   `no_parent`         a Service, Endpoint or Parameter named no containment
--                       parent, named one this Program has not got, or named
--                       one of the wrong type. Not `no_subject`: the element
--                       is about itself and it is the structure that is
--                       missing.
--   `out_of_scope`      the subject scope-classifies `denied`. The Spec
--                       forbids discovery outside the configured scope, and an
--                       Entity written and then projected denied would be that
--                       discovery with a row to prove it.
--   `invalid_direction` the relationship type exists and this ordered pair of
--                       types is not one it joins.
--   `is_containment`    the two ends are a containment pair, in either
--                       direction. Its own reason rather than
--                       `invalid_direction`, because they are different
--                       mistakes: one is an orientation to reverse, the other
--                       is a fact the schema already holds as a foreign key.
--                       An agent told the first would send the same claim back
--                       around the other way.
--
-- `unknown_kind` is reused for an unknown entity type and an unknown
-- relationship type rather than split three ways. It says one thing -- a closed
-- vocabulary refused the value -- and `element_path` already says which
-- vocabulary.

ALTER TABLE proposal_drops DROP CONSTRAINT proposal_drops_reason_check;
ALTER TABLE proposal_drops ADD CONSTRAINT proposal_drops_reason_check
    CHECK (reason IN ('no_such_receipt','receipt_other_program',
                      'receipt_proxy_internal','receipt_other_run',
                      'no_such_tool_run','no_such_label',
                      'label_other_program','no_provenance',
                      'no_subject','unknown_kind','incompatible_provenance',
                      'refused_by_invariant',
                      'malformed_field','no_parent','out_of_scope',
                      'invalid_direction','is_containment'));

CREATE OR REPLACE FUNCTION promote_proposal(p_proposal uuid) RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p           uuid := rk2_program_required();
    v           proposals%ROWTYPE;
    v_version   integer;
    v_next      integer;
    v_element   jsonb;
    v_path      text;
    v_receipt   uuid;
    v_tool_run  uuid;
    v_evidence  text;   -- the label the element cited, whatever came of it
    v_subject   uuid;
    v_kind      text;
    v_parent_type text;
    v_scope_class text;
    v_allowed   text[];
    v_provenance text;
    v_reason    text;
    v_cited     text;
    v_label     text;
    v_refs      jsonb := '{}'::jsonb;   -- the proposal's own handles
    v_type      text;
    v_parent    uuid;
    v_parent_key text;
    v_parent_selector_kind text;
    v_parent_selector text;
    v_parent_port integer;
    v_parent_path text;
    v_selector_kind text;
    v_selector  text;
    v_scheme    text;
    v_base_url  text;
    v_port      integer;
    v_path_text text;
    v_dedup     text;
    v_fault     text;
    v_entity    uuid;
    v_created   boolean;
    v_fqdn      text;
    v_apex      text;
    v_wildcard  boolean;
    v_address   text;
    v_hostname  text;
    v_protocol  text;
    v_method    text;
    v_template  text;
    v_location  text;
    v_name      text;
    v_app_kind  text;
    v_identity_class text;
    v_src       uuid;
    v_dst       uuid;
    v_src_type  text;
    v_dst_type  text;
    v_relationship uuid;
    v_src_label text;
    v_dst_label text;
    v_entities  text[] := '{}';
    v_relationships text[] := '{}';
    v_promoted  text[] := '{}';
    v_refused   integer := 0;
    v_wrote_entity boolean := false;   -- whether the scope projection has work
    v_canonical boolean;               -- whether anything at all became canonical
BEGIN
    SELECT * INTO v FROM proposals
     WHERE id = p_proposal AND program_id = p FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'proposal % is not a staged result of this Program', p_proposal
            USING ERRCODE = 'check_violation';
    END IF;

    -- Idempotent, and it reports the same answer rather than a different one.
    -- A promotion that ran and a promotion that had already run are the same
    -- state, and the caller retrying after a lost connection needs to be told
    -- what is true rather than what this call did. The two new lists are read
    -- back from the provenance rows, which is what they are for.
    IF v.status <> 'staged' THEN
        RETURN jsonb_build_object(
            'proposal', v.label, 'status', v.status, 'repeated', true,
            'entities', coalesce(
                (SELECT jsonb_agg(DISTINCT e.label) FROM entity_provenance ep
                   JOIN entities e ON e.id = ep.entity_id
                  WHERE ep.proposal_id = v.id), '[]'::jsonb),
            'relationships', coalesce(
                (SELECT jsonb_agg(DISTINCT s.label || ' ' || r.type || ' ' || d.label)
                   FROM relationship_provenance rp
                   JOIN relationships r ON r.id = rp.relationship_id
                   JOIN entities s ON s.id = r.src_entity_id
                   JOIN entities d ON d.id = r.dst_entity_id
                  WHERE rp.proposal_id = v.id), '[]'::jsonb),
            'observations', coalesce(
                (SELECT jsonb_agg(o.label ORDER BY o.label) FROM observations o
                  WHERE o.program_id = p AND o.metadata ->> 'proposal' = v.label),
                '[]'::jsonb),
            'refused', (SELECT count(*) FROM proposal_drops d WHERE d.proposal_id = v.id));
    END IF;

    PERFORM set_actor('runtime', 'promotion');
    PERFORM set_cause(v.agent_run_id, v.task_id);

    SELECT pr.scope_version INTO v_version FROM programs pr WHERE pr.id = p;
    SELECT coalesce(max(ordinal) + 1, 0) INTO v_next
      FROM proposal_drops WHERE proposal_id = v.id;

    -- === Entities ==========================================================
    FOR v_element, v_path IN
        SELECT e.value, 'new_entities[' || (e.n - 1) || ']'
          FROM (SELECT value, row_number() OVER () AS n
                  FROM jsonb_array_elements(
                          CASE WHEN jsonb_typeof(v.payload -> 'new_entities') = 'array'
                               THEN v.payload -> 'new_entities' ELSE '[]'::jsonb END)
                 WHERE jsonb_typeof(value) = 'object') e
         ORDER BY e.n
    LOOP
        CONTINUE WHEN EXISTS (
            SELECT 1 FROM proposal_drops d
             WHERE d.proposal_id = v.id AND d.element_path = v_path);

        v_reason := NULL; v_cited := NULL; v_fault := NULL;
        v_receipt := NULL; v_tool_run := NULL; v_provenance := NULL;
        v_parent := NULL; v_parent_key := NULL;
        v_selector_kind := NULL; v_selector := NULL; v_port := NULL;
        v_path_text := '/'; v_dedup := NULL;
        v_scheme := NULL; v_base_url := NULL;

        v_type := nullif(btrim(v_element ->> 'type'), '');
        SELECT x.receipt_id, x.tool_run_id, x.provenance_kind, x.cited
          INTO v_receipt, v_tool_run, v_provenance, v_evidence
          FROM rk2_element_evidence(p, v_element) x;

        IF v_type IS NULL OR NOT (v_type = ANY (rk2_entity_types())) THEN
            v_reason := 'unknown_kind';
            v_cited := v_type;
        ELSIF v_provenance IS NULL THEN
            -- An Entity is a claim that something is out there, and criterion 1
            -- asks for stable evidence references. A proposed Entity citing
            -- nothing is a guess, and the harness has no way to tell it from a
            -- finding later.
            v_reason := 'no_provenance';
            v_cited := v_evidence;
        END IF;

        -- The containment parent, for the three types that have one.
        IF v_reason IS NULL AND v_type IN ('service','endpoint','parameter') THEN
            v_cited := coalesce(nullif(btrim(v_element ->> 'parent_ref'), ''),
                                nullif(btrim(v_element ->> 'parent_label'), ''));
            IF nullif(btrim(v_element ->> 'parent_ref'), '') IS NOT NULL THEN
                v_parent := nullif(v_refs ->> btrim(v_element ->> 'parent_ref'), '')::uuid;
            ELSIF nullif(btrim(v_element ->> 'parent_label'), '') IS NOT NULL THEN
                SELECT e.id INTO v_parent FROM entities e
                 WHERE e.program_id = p AND e.label = btrim(v_element ->> 'parent_label');
            END IF;
            IF v_parent IS NULL THEN
                v_reason := 'no_parent';
            ELSE
                SELECT e.dedup_key, e.type, e.scope_selector_kind, e.scope_selector,
                       e.scope_port, e.scope_path_raw
                  INTO v_parent_key, v_parent_type, v_parent_selector_kind, v_parent_selector,
                       v_parent_port, v_parent_path
                  FROM entities e WHERE e.id = v_parent;
                IF NOT EXISTS (SELECT 1 FROM entity_containment c
                                WHERE c.child_type = v_type AND c.parent_type = v_parent_type) THEN
                    v_reason := 'no_parent';
                    v_cited := v_cited || ' is a ' || v_parent_type;
                END IF;
            END IF;
        END IF;

        -- The typed fields, per type. Each arm produces a selector for the
        -- scope question and the parts of the dedup key, or a sentence saying
        -- which field it could not accept.
        IF v_reason IS NULL THEN
            IF v_type = 'domain' THEN
                v_fqdn := scope_normalize_host(v_element ->> 'fqdn');
                -- `coalesce`, because an absent key compares NULL rather than
                -- false and `domains.wildcard` is NOT NULL: a Domain proposed
                -- without the flag is a Domain, not a refusal.
                v_wildcard := coalesce((v_element -> 'wildcard') = 'true'::jsonb, false);
                IF v_fqdn IS NULL OR position('.' IN v_fqdn) = 0 OR v_fqdn !~ '[a-z]' THEN
                    v_fault := 'fqdn is absent or is not a dotted domain name';
                ELSE
                    SELECT array_to_string(l[greatest(1, cardinality(l) - 1):cardinality(l)], '.')
                      INTO v_apex FROM (SELECT string_to_array(v_fqdn, '.') AS l) s;
                    v_selector_kind := CASE WHEN v_wildcard THEN 'wildcard_domain' ELSE 'host' END;
                    v_selector := v_fqdn;
                    v_dedup := rk2_dedup_key(v_type,
                        ARRAY[CASE WHEN v_wildcard THEN '*.' || v_fqdn ELSE v_fqdn END]);
                END IF;

            ELSIF v_type = 'host' THEN
                v_hostname := scope_normalize_host(v_element ->> 'hostname');
                v_address  := scope_normalize_host(v_element ->> 'address');
                IF nullif(btrim(v_element ->> 'address'), '') IS NOT NULL
                   AND (v_address IS NULL OR v_address !~ '^([0-9.]+|[0-9a-f:]+)$') THEN
                    -- Refused rather than dropped. A Host promoted on its
                    -- hostname with the offered address silently discarded is a
                    -- row that answers "what address is this" with nothing,
                    -- while the agent that sent one has been told it landed.
                    v_fault := 'address is not an IP address';
                ELSIF v_hostname IS NULL AND v_address IS NULL THEN
                    v_fault := 'a host needs a hostname or an address, and neither was usable';
                ELSE
                    v_selector_kind := 'host';
                    v_selector := coalesce(v_hostname, v_address);
                    v_dedup := rk2_dedup_key(v_type, ARRAY[v_selector]);
                END IF;

            ELSIF v_type = 'service' THEN
                v_protocol := lower(coalesce(nullif(btrim(v_element ->> 'protocol'), ''), 'tcp'));
                v_port := CASE WHEN v_element ->> 'port' ~ '^[0-9]{1,5}$'
                               THEN (v_element ->> 'port')::integer END;
                IF v_port IS NULL OR v_port NOT BETWEEN 1 AND 65535 THEN
                    v_fault := 'port is absent or is not a number between 1 and 65535';
                ELSIF v_protocol !~ '^[a-z0-9_+-]{1,32}$' THEN
                    v_fault := 'protocol is not a short lowercase token';
                ELSE
                    v_selector_kind := v_parent_selector_kind;
                    v_selector := v_parent_selector;
                    v_dedup := rk2_dedup_key(v_type,
                        ARRAY[v_parent_key, v_port::text, v_protocol]);
                END IF;

            ELSIF v_type = 'application' THEN
                SELECT u.scheme, u.host, u.port, u.path, u.fault
                  INTO v_scheme, v_selector, v_port, v_path_text, v_fault
                  FROM rk2_parse_base_url(v_element ->> 'base_url') u;
                v_app_kind := nullif(btrim(v_element ->> 'kind'), '');
                IF v_fault IS NULL AND v_app_kind IS NOT NULL
                   AND v_app_kind NOT IN ('web','api','spa','graphql','websocket') THEN
                    v_fault := 'kind is not one of web, api, spa, graphql, websocket';
                END IF;
                IF v_fault IS NULL THEN
                    v_selector_kind := 'host';
                    -- The canonical spelling, built once: the key two proposals
                    -- converge on and the URL the column stores are the same
                    -- string, so they cannot drift apart.
                    v_base_url := v_scheme || '://' || v_selector ||
                        CASE WHEN v_port = CASE WHEN v_scheme = 'https' THEN 443 ELSE 80 END
                             THEN '' ELSE ':' || v_port::text END ||
                        CASE WHEN v_path_text = '/' THEN '' ELSE v_path_text END;
                    v_dedup := rk2_dedup_key(v_type, ARRAY[v_base_url]);
                END IF;

            ELSIF v_type = 'endpoint' THEN
                v_method := upper(coalesce(nullif(btrim(v_element ->> 'method'), ''), ''));
                SELECT c.path, c.fault INTO v_template, v_fault
                  FROM rk2_clean_path(v_element ->> 'path_template') c;
                IF v_method !~ '^[A-Z]{3,10}$' THEN
                    v_fault := 'method is absent or is not an HTTP method token';
                ELSIF v_fault IS NULL THEN
                    -- The route as the fence would see it. An Application at
                    -- `/api` and an Endpoint at `/users` is one request to
                    -- `/api/users`, and the scope question is about that.
                    v_path_text := CASE
                        WHEN v_parent_path = '/' THEN v_template
                        WHEN v_template = v_parent_path
                          OR starts_with(v_template, v_parent_path || '/') THEN v_template
                        ELSE v_parent_path || v_template END;
                    v_selector_kind := v_parent_selector_kind;
                    v_selector := v_parent_selector;
                    v_port := v_parent_port;
                    v_dedup := rk2_dedup_key(v_type,
                        ARRAY[v_parent_key, v_method, v_template]);
                END IF;

            ELSIF v_type = 'parameter' THEN
                v_name := nullif(btrim(v_element ->> 'name'), '');
                v_location := lower(coalesce(nullif(btrim(v_element ->> 'location'), ''), ''));
                IF v_name IS NULL THEN
                    v_fault := 'name is absent';
                ELSIF v_location NOT IN ('query','body','path','header','cookie') THEN
                    v_fault := 'location is not one of query, body, path, header, cookie';
                ELSE
                    v_selector_kind := v_parent_selector_kind;
                    v_selector := v_parent_selector;
                    v_port := v_parent_port;
                    v_path_text := v_parent_path;
                    v_dedup := rk2_dedup_key(v_type,
                        ARRAY[v_parent_key, v_location, v_name]);
                END IF;

            ELSIF v_type = 'technology' THEN
                v_name := nullif(btrim(v_element ->> 'name'), '');
                IF v_name IS NULL THEN
                    v_fault := 'name is absent';
                ELSE
                    v_dedup := rk2_dedup_key(v_type,
                        ARRAY[lower(v_name),
                              coalesce(nullif(btrim(v_element ->> 'version'), ''), '')]);
                END IF;

            ELSE   -- identity
                v_name := nullif(btrim(v_element ->> 'slot_name'), '');
                v_identity_class :=
                    lower(coalesce(nullif(btrim(v_element ->> 'class'), ''), 'anonymous'));
                IF v_name IS NULL THEN
                    v_fault := 'slot_name is absent';
                ELSIF v_identity_class <> 'anonymous' THEN
                    -- 003: a non-anonymous Identity must carry a secret_ref, and
                    -- a secret is the operator's to place. Refused here with a
                    -- sentence rather than left to the CHECK, because "the row
                    -- was refused" and "an agent may not propose credentials"
                    -- are different things to have been told.
                    v_fault := 'an agent may propose only an anonymous identity; '
                            || 'a credentialed one is configured by the operator';
                ELSE
                    v_dedup := rk2_dedup_key(v_type, ARRAY[v_name]);
                END IF;
            END IF;

            IF v_fault IS NOT NULL THEN
                v_reason := 'malformed_field';
                v_cited := left(v_fault, 300);
            END IF;
        END IF;

        -- Scope, before the row exists. `not_addressable` is not a refusal: a
        -- Technology and an Identity have no address, which 021 says is a
        -- different answer from being out of scope.
        IF v_reason IS NULL THEN
            SELECT s.scope_class INTO v_scope_class
              FROM scope_class_of_entity(p, v_version, v_selector_kind, v_selector,
                                         v_port, v_path_text, v_path_text) s;
            IF v_scope_class = 'denied' THEN
                v_reason := 'out_of_scope';
                v_cited := left(coalesce(v_selector, '') ||
                                coalesce(':' || v_port::text, '') ||
                                CASE WHEN v_path_text = '/' THEN '' ELSE v_path_text END, 300);
            END IF;
        END IF;

        IF v_reason IS NOT NULL THEN
            INSERT INTO proposal_drops
                (proposal_id, program_id, ordinal, element_path, reason, cited)
            VALUES (v.id, p, v_next, v_path, v_reason, v_cited);
            v_next := v_next + 1;
            v_refused := v_refused + 1;
            CONTINUE;
        END IF;

        BEGIN
            -- Converge on the key, and touch nothing else. `last_seen_at` is
            -- the only column a second sighting is evidence about; the scope
            -- columns are the projection's and 021's trigger refuses them here.
            INSERT INTO entities
                (program_id, type, dedup_key, origin, scope_selector_kind,
                 scope_selector, scope_port, scope_path_raw, scope_path_norm)
            VALUES (p, v_type, v_dedup, 'proposed', v_selector_kind,
                    v_selector, v_port, v_path_text, v_path_text)
            ON CONFLICT (program_id, type, dedup_key)
                DO UPDATE SET last_seen_at = now()
            RETURNING id, (xmax = 0), label INTO v_entity, v_created, v_label;

            -- The detail row. Filled where it is empty and never overwritten:
            -- a second proposal that knows less is not a correction.
            IF v_type = 'domain' THEN
                INSERT INTO domains (entity_id, fqdn, apex, wildcard)
                VALUES (v_entity, v_fqdn, v_apex, v_wildcard)
                ON CONFLICT (entity_id) DO NOTHING;
            ELSIF v_type = 'host' THEN
                INSERT INTO hosts (entity_id, hostname, address)
                VALUES (v_entity, v_hostname, v_address::inet)
                ON CONFLICT (entity_id) DO UPDATE
                   SET hostname = coalesce(hosts.hostname, EXCLUDED.hostname),
                       address  = coalesce(hosts.address,  EXCLUDED.address);
            ELSIF v_type = 'service' THEN
                INSERT INTO services (entity_id, host_id, port, protocol, banner)
                VALUES (v_entity, v_parent, v_port, v_protocol,
                        left(nullif(btrim(v_element ->> 'banner'), ''), 500))
                ON CONFLICT (entity_id) DO UPDATE
                   SET banner = coalesce(services.banner, EXCLUDED.banner);
            ELSIF v_type = 'application' THEN
                INSERT INTO applications (entity_id, base_url, kind)
                VALUES (v_entity, v_base_url, v_app_kind)
                ON CONFLICT (entity_id) DO UPDATE
                   SET kind = coalesce(applications.kind, EXCLUDED.kind);
            ELSIF v_type = 'endpoint' THEN
                INSERT INTO endpoints (entity_id, application_id, method, path_template,
                                       auth_required, request_content_type)
                VALUES (v_entity, v_parent, v_method, v_template,
                        CASE WHEN jsonb_typeof(v_element -> 'auth_required') = 'boolean'
                             THEN (v_element -> 'auth_required') = 'true'::jsonb END,
                        left(nullif(btrim(v_element ->> 'request_content_type'), ''), 200))
                ON CONFLICT (entity_id) DO UPDATE
                   SET auth_required = coalesce(endpoints.auth_required, EXCLUDED.auth_required),
                       request_content_type = coalesce(endpoints.request_content_type,
                                                       EXCLUDED.request_content_type);
            ELSIF v_type = 'parameter' THEN
                INSERT INTO parameters (entity_id, endpoint_id, name, location,
                                        value_class, reflected)
                VALUES (v_entity, v_parent, v_name, v_location,
                        left(nullif(btrim(v_element ->> 'value_class'), ''), 200),
                        CASE WHEN jsonb_typeof(v_element -> 'reflected') = 'boolean'
                             THEN (v_element -> 'reflected') = 'true'::jsonb END)
                ON CONFLICT (entity_id) DO UPDATE
                   SET value_class = coalesce(parameters.value_class, EXCLUDED.value_class),
                       reflected   = coalesce(parameters.reflected,   EXCLUDED.reflected);
            ELSIF v_type = 'technology' THEN
                INSERT INTO technologies (entity_id, name, version, cpe)
                VALUES (v_entity, v_name,
                        nullif(btrim(v_element ->> 'version'), ''),
                        left(nullif(btrim(v_element ->> 'cpe'), ''), 200))
                ON CONFLICT (entity_id) DO UPDATE
                   SET cpe = coalesce(technologies.cpe, EXCLUDED.cpe);
            ELSE
                INSERT INTO identities (entity_id, slot_name, class)
                VALUES (v_entity, v_name, 'anonymous')
                ON CONFLICT (entity_id) DO NOTHING;
            END IF;

            INSERT INTO entity_provenance
                (program_id, entity_id, origin, proposal_id, element_path,
                 agent_run_id, receipt_id, tool_run_id)
            VALUES (p, v_entity, 'proposed', v.id, v_path,
                    v.agent_run_id, v_receipt, v_tool_run)
            ON CONFLICT (entity_id, origin, proposal_id, element_path) DO NOTHING;

            v_wrote_entity := true;
            v_entities := v_entities || v_label;
            IF nullif(btrim(v_element ->> 'ref'), '') IS NOT NULL THEN
                v_refs := v_refs || jsonb_build_object(btrim(v_element ->> 'ref'),
                                                       v_entity::text);
            END IF;
        EXCEPTION WHEN check_violation OR raise_exception OR not_null_violation
                    OR foreign_key_violation OR unique_violation THEN
            INSERT INTO proposal_drops
                (proposal_id, program_id, ordinal, element_path, reason, cited)
            VALUES (v.id, p, v_next, v_path, 'refused_by_invariant',
                    left(SQLERRM, 300));
            v_next := v_next + 1;
            v_refused := v_refused + 1;
        END;
    END LOOP;

    -- One projection for the whole walk. Every Entity above was inserted denied
    -- and every one of them was scope-checked before it was; this is what turns
    -- the check into the stored class, and re-running it at the same version
    -- writes nothing.
    IF v_wrote_entity AND v_version IS NOT NULL THEN
        PERFORM refresh_scope_projection(p);
    END IF;

    -- === Relationships =====================================================
    FOR v_element, v_path IN
        SELECT e.value, 'relationships[' || (e.n - 1) || ']'
          FROM (SELECT value, row_number() OVER () AS n
                  FROM jsonb_array_elements(
                          CASE WHEN jsonb_typeof(v.payload -> 'relationships') = 'array'
                               THEN v.payload -> 'relationships' ELSE '[]'::jsonb END)
                 WHERE jsonb_typeof(value) = 'object') e
         ORDER BY e.n
    LOOP
        CONTINUE WHEN EXISTS (
            SELECT 1 FROM proposal_drops d
             WHERE d.proposal_id = v.id AND d.element_path = v_path);

        v_reason := NULL; v_cited := NULL;
        v_receipt := NULL; v_tool_run := NULL; v_provenance := NULL;
        v_src := NULL; v_dst := NULL;

        v_type := nullif(btrim(v_element ->> 'type'), '');
        SELECT x.receipt_id, x.tool_run_id, x.provenance_kind, x.cited
          INTO v_receipt, v_tool_run, v_provenance, v_evidence
          FROM rk2_element_evidence(p, v_element) x;

        IF nullif(btrim(v_element ->> 'src_ref'), '') IS NOT NULL THEN
            v_src := nullif(v_refs ->> btrim(v_element ->> 'src_ref'), '')::uuid;
        ELSIF nullif(btrim(v_element ->> 'src_label'), '') IS NOT NULL THEN
            SELECT e.id INTO v_src FROM entities e
             WHERE e.program_id = p AND e.label = btrim(v_element ->> 'src_label');
        END IF;
        IF nullif(btrim(v_element ->> 'dst_ref'), '') IS NOT NULL THEN
            v_dst := nullif(v_refs ->> btrim(v_element ->> 'dst_ref'), '')::uuid;
        ELSIF nullif(btrim(v_element ->> 'dst_label'), '') IS NOT NULL THEN
            SELECT e.id INTO v_dst FROM entities e
             WHERE e.program_id = p AND e.label = btrim(v_element ->> 'dst_label');
        END IF;

        SELECT e.type INTO v_src_type FROM entities e WHERE e.id = v_src;
        SELECT e.type INTO v_dst_type FROM entities e WHERE e.id = v_dst;

        IF v_provenance IS NULL THEN
            v_reason := 'no_provenance';
            v_cited := v_evidence;
        ELSIF v_src IS NULL OR v_dst IS NULL THEN
            v_reason := 'no_subject';
            v_cited := CASE WHEN v_src IS NULL
                            THEN coalesce(nullif(btrim(v_element ->> 'src_ref'), ''),
                                          nullif(btrim(v_element ->> 'src_label'), ''))
                            ELSE coalesce(nullif(btrim(v_element ->> 'dst_ref'), ''),
                                          nullif(btrim(v_element ->> 'dst_label'), '')) END;
        ELSIF NOT EXISTS (SELECT 1 FROM relationship_directions d WHERE d.type = v_type) THEN
            v_reason := 'unknown_kind';
            v_cited := v_type;
        ELSIF EXISTS (SELECT 1 FROM entity_containment c
                       WHERE (c.child_type, c.parent_type) IN
                             ((v_src_type, v_dst_type), (v_dst_type, v_src_type))) THEN
            -- Named apart from `invalid_direction` on purpose: the pair is not
            -- merely undefined, it is already a fact of the schema, and the
            -- agent's mistake is modelling rather than orientation.
            v_reason := 'is_containment';
            v_cited := v_src_type || ' and ' || v_dst_type || ' are containment, not a relationship';
        ELSIF NOT EXISTS (SELECT 1 FROM relationship_directions d
                           WHERE d.type = v_type AND d.src_type = v_src_type
                             AND d.dst_type = v_dst_type) THEN
            v_reason := 'invalid_direction';
            v_cited := v_type || ' does not go from ' || v_src_type || ' to ' || v_dst_type;
        END IF;

        IF v_reason IS NOT NULL THEN
            INSERT INTO proposal_drops
                (proposal_id, program_id, ordinal, element_path, reason, cited)
            VALUES (v.id, p, v_next, v_path, v_reason, left(v_cited, 300));
            v_next := v_next + 1;
            v_refused := v_refused + 1;
            CONTINUE;
        END IF;

        BEGIN
            INSERT INTO relationships (program_id, src_entity_id, dst_entity_id, type, origin)
            VALUES (p, v_src, v_dst, v_type, 'proposed')
            ON CONFLICT (src_entity_id, dst_entity_id, type)
                DO UPDATE SET last_seen_at = now()
            RETURNING id INTO v_relationship;

            INSERT INTO relationship_provenance
                (program_id, relationship_id, origin, proposal_id, element_path,
                 agent_run_id, receipt_id, tool_run_id)
            VALUES (p, v_relationship, 'proposed', v.id, v_path,
                    v.agent_run_id, v_receipt, v_tool_run)
            ON CONFLICT (relationship_id, origin, proposal_id, element_path) DO NOTHING;

            SELECT e.label INTO v_src_label FROM entities e WHERE e.id = v_src;
            SELECT e.label INTO v_dst_label FROM entities e WHERE e.id = v_dst;
            v_relationships := v_relationships ||
                (v_src_label || ' ' || v_type || ' ' || v_dst_label);
        EXCEPTION WHEN check_violation OR raise_exception OR not_null_violation
                    OR foreign_key_violation OR unique_violation THEN
            INSERT INTO proposal_drops
                (proposal_id, program_id, ordinal, element_path, reason, cited)
            VALUES (v.id, p, v_next, v_path, 'refused_by_invariant',
                    left(SQLERRM, 300));
            v_next := v_next + 1;
            v_refused := v_refused + 1;
        END;
    END LOOP;

    -- === Observations ======================================================
    FOR v_element, v_path IN
        SELECT e.value, 'observations[' || (e.n - 1) || ']'
          FROM (SELECT value, row_number() OVER () AS n
                  FROM jsonb_array_elements(
                          CASE WHEN jsonb_typeof(v.payload -> 'observations') = 'array'
                               THEN v.payload -> 'observations' ELSE '[]'::jsonb END)
                 WHERE jsonb_typeof(value) = 'object') e
         ORDER BY e.n
    LOOP
        CONTINUE WHEN EXISTS (
            SELECT 1 FROM proposal_drops d
             WHERE d.proposal_id = v.id AND d.element_path = v_path);

        v_reason := NULL;
        v_receipt := NULL;
        v_tool_run := NULL;
        v_provenance := NULL;
        v_subject := NULL;
        v_cited := NULL;

        SELECT x.receipt_id, x.tool_run_id, x.provenance_kind, x.cited
          INTO v_receipt, v_tool_run, v_provenance, v_evidence
          FROM rk2_element_evidence(p, v_element) x;

        -- `subject_ref` first, because an Observation about an Entity proposed
        -- in the same result has no label to name until the walk above ran.
        IF nullif(btrim(v_element ->> 'subject_ref'), '') IS NOT NULL THEN
            v_subject := nullif(v_refs ->> btrim(v_element ->> 'subject_ref'), '')::uuid;
            v_cited := btrim(v_element ->> 'subject_ref');
        ELSE
            SELECT e.id INTO v_subject FROM entities e
             WHERE e.program_id = p AND e.label = v_element ->> 'subject_label';
            v_cited := v_element ->> 'subject_label';
        END IF;
        v_kind := v_element ->> 'kind';
        SELECT k.allowed_provenance INTO v_allowed
          FROM observation_kinds k WHERE k.id = v_kind;

        IF v_provenance IS NULL THEN
            v_reason := 'no_provenance';
            v_cited := v_evidence;
        ELSIF v_subject IS NULL THEN
            v_reason := 'no_subject';
        ELSIF v_allowed IS NULL THEN
            v_reason := 'unknown_kind';
            v_cited := v_kind;
        ELSIF NOT (v_provenance = ANY (v_allowed)) THEN
            v_reason := 'incompatible_provenance';
            v_cited := v_kind;
        END IF;

        IF v_reason IS NOT NULL THEN
            INSERT INTO proposal_drops
                (proposal_id, program_id, ordinal, element_path, reason, cited)
            VALUES (v.id, p, v_next, v_path, v_reason, v_cited);
            v_next := v_next + 1;
            v_refused := v_refused + 1;
            CONTINUE;
        END IF;

        BEGIN
            INSERT INTO observations
                (program_id, agent_run_id, subject_entity_id, kind, summary,
                 provenance_kind, receipt_id, tool_run_id, metadata)
            VALUES
                (p, v.agent_run_id, v_subject, v_kind,
                 left(coalesce(v_element ->> 'summary', ''), 2000),
                 v_provenance, v_receipt, v_tool_run,
                 jsonb_build_object('proposal', v.label, 'element', v_path))
            RETURNING label INTO v_label;
            v_promoted := v_promoted || v_label;
        EXCEPTION WHEN check_violation OR raise_exception OR not_null_violation
                    OR foreign_key_violation OR unique_violation THEN
            INSERT INTO proposal_drops
                (proposal_id, program_id, ordinal, element_path, reason, cited)
            VALUES (v.id, p, v_next, v_path, 'refused_by_invariant',
                    left(SQLERRM, 300));
            v_next := v_next + 1;
            v_refused := v_refused + 1;
        END;
    END LOOP;

    -- Promoted if anything at all became canonical. A recon run that found
    -- four Hosts and asserted nothing about them has done its Task, and 020's
    -- completion trigger reads this status.
    v_canonical := cardinality(v_promoted) > 0
              OR cardinality(v_entities) > 0
              OR cardinality(v_relationships) > 0;

    UPDATE proposals
       SET status = CASE WHEN v_canonical THEN 'promoted' ELSE 'rejected' END,
           promoted_at = CASE WHEN v_canonical THEN now() END
     WHERE id = v.id;

    RETURN jsonb_build_object(
        'proposal', v.label,
        'status', CASE WHEN v_canonical THEN 'promoted' ELSE 'rejected' END,
        'repeated', false,
        'entities', to_jsonb(v_entities),
        'relationships', to_jsonb(v_relationships),
        'observations', to_jsonb(v_promoted),
        'refused', v_refused);
END $fn$;

REVOKE ALL ON FUNCTION promote_proposal(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION promote_proposal(uuid) TO rk2_runtime;

COMMENT ON FUNCTION promote_proposal(uuid) IS
    'Turns one staged agent-run result into canonical Entities, Relationships and '
    'Observations, in one transaction with the Events that record them. Every '
    'subject is canonicalized and scope-checked before its row exists; what '
    'cannot be grounded becomes a proposal_drops row rather than an exception.';


-- ---------------------------------------------------------------------------
-- 8. The compact read
-- ---------------------------------------------------------------------------
-- Four things join the Entity record, and each is a question an agent would
-- otherwise answer by reading the transcript that proposed the row.
--
--   `origin` and `origins` -- who put it there, and everyone who has since
--   said so. They differ exactly when a subject converged: the first is the
--   creation, the second is every distinct provenance.
--   `parent_label` -- the containment parent, so a Parameter names its
--   Endpoint without a second read.
--   `relationships` and `relationship_count` -- the typed relationships,
--   capped, each as a direction and the label at the other end, beside the
--   number there are. Capped because a record is a bounded read: an Entity with
--   two hundred relationships would otherwise spend the packet's whole ceiling
--   on one row. The count travels with the cap for `packet.Section`'s reason --
--   a truncated list that does not say so reads as a complete one.

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
               'scope_tier', e.scope_tier,
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
           rk2_revision('hypotheses', hy.id),
           jsonb_build_object(
               'kind', 'hypothesis',
               'label', hy.label,
               'status', hy.status,
               'property_class', hy.property_class,
               'statement', hy.statement,
               'subject_label', subj.label,
               'identity_a_label', ia.label,
               'identity_b_label', ib.label,
               'superseded_by_label', sup.label,
               'observed_fingerprint', hy.observed_fingerprint,
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
-- 9. The standing check
-- ---------------------------------------------------------------------------
-- Four arms for what promotion can get wrong and four for the structures that
-- would make the first four meaningless. An unregistered direction and a
-- detached trigger both read as "no violations" from a query over
-- `relationships` alone, which is exactly the failure a standing check is for.

CREATE FUNCTION check_surface_promotion()
RETURNS TABLE (problem text, subject text, detail text)
LANGUAGE sql STABLE AS $fn$
    SELECT 'promoted_entity_without_provenance', e.label,
           'origin=proposed and no entity_provenance row says which evidence produced it'
      FROM entities e
     WHERE e.origin = 'proposed'
       AND NOT EXISTS (SELECT 1 FROM entity_provenance ep WHERE ep.entity_id = e.id)

  UNION ALL
    SELECT 'promoted_relationship_without_provenance', r.id::text,
           'origin=proposed and no relationship_provenance row says which evidence produced it'
      FROM relationships r
     WHERE r.origin = 'proposed'
       AND NOT EXISTS (SELECT 1 FROM relationship_provenance rp
                        WHERE rp.relationship_id = r.id)

  UNION ALL
    SELECT 'relationship_direction_unknown',
           s.label || ' ' || r.type || ' ' || d.label,
           'no relationship_directions row joins ' || s.type || ' to ' || d.type
      FROM relationships r
      JOIN entities s ON s.id = r.src_entity_id
      JOIN entities d ON d.id = r.dst_entity_id
     WHERE NOT EXISTS (SELECT 1 FROM relationship_directions rd
                        WHERE rd.type = r.type AND rd.src_type = s.type
                          AND rd.dst_type = d.type)

  UNION ALL
    SELECT 'relationship_expresses_containment',
           s.label || ' ' || r.type || ' ' || d.label,
           s.type || ' and ' || d.type || ' are containment, which is a foreign key'
      FROM relationships r
      JOIN entities s ON s.id = r.src_entity_id
      JOIN entities d ON d.id = r.dst_entity_id
      JOIN entity_containment c
        ON (c.child_type, c.parent_type) IN ((s.type, d.type), (d.type, s.type))

  UNION ALL
    SELECT 'relationship_grammar_detached', 'relationships',
           'relationships_follow_the_grammar is missing or not ENABLE ALWAYS'
     WHERE NOT EXISTS (
        SELECT 1 FROM pg_trigger
         WHERE tgrelid = 'relationships'::regclass
           AND tgname = 'relationships_follow_the_grammar'
           AND tgenabled = 'A')

  UNION ALL
    SELECT 'containment_registry_untrue', c.detail_table || '.' || c.parent_column,
           'the registry names a foreign key the schema does not have'
      FROM entity_containment c
     WHERE NOT EXISTS (
        SELECT 1 FROM pg_attribute a
         WHERE a.attrelid = to_regclass('public.' || c.detail_table)
           AND a.attname = c.parent_column
           AND a.attnum > 0 AND NOT a.attisdropped)

  UNION ALL
    -- The CHECK on `relationships.type` and this registry are two statements of
    -- one vocabulary. A type in the registry the CHECK refuses would make the
    -- grammar accept a relationship the column cannot hold.
    SELECT 'direction_type_not_in_column_vocabulary', d.type,
           'relationship_directions offers a type relationships.type refuses'
      FROM (SELECT DISTINCT type FROM relationship_directions) d
     WHERE NOT EXISTS (
        SELECT 1 FROM pg_constraint con
         WHERE con.conrelid = 'relationships'::regclass
           AND con.contype = 'c'
           AND pg_get_constraintdef(con.oid) LIKE '%''' || d.type || '''%')

  UNION ALL
    -- The same question of the other vocabulary, and the same direction of it:
    -- a type `rk2_entity_types()` offers and the column refuses is a promotion
    -- that ends in a constraint error rather than in a drop row. The reverse --
    -- a type the column takes and the function omits -- is a type no proposal
    -- can name, which is a smaller failure and not one a catalogue query can
    -- see without parsing the CHECK.
    SELECT 'entity_type_vocabulary_disagrees', t.name,
           'rk2_entity_types() and the CHECK on entities.type do not list the same types'
      FROM unnest(rk2_entity_types()) AS t(name)
     WHERE NOT EXISTS (
        SELECT 1 FROM pg_constraint con
         WHERE con.conrelid = 'entities'::regclass
           AND con.contype = 'c'
           AND pg_get_constraintdef(con.oid) LIKE '%''' || t.name || '''%')
$fn$;

REVOKE ALL ON FUNCTION check_surface_promotion() FROM PUBLIC;

INSERT INTO standing_checks(name, query, owner_ticket, note) VALUES
    ('surface_promotion', 'SELECT * FROM check_surface_promotion()', '21',
     'every promoted Entity and Relationship names the evidence that produced it, every relationship follows a registered direction, and no relationship restates a containment the schema already holds');

COMMENT ON FUNCTION check_surface_promotion() IS
    'What promotion can get wrong, as rows, plus the four structures that keep '
    'the first two of them empty by construction.';


-- ---------------------------------------------------------------------------
-- 10. The invariants this file must not have broken
-- ---------------------------------------------------------------------------

SELECT apply_state_rls();

DO $$
DECLARE n integer; d text;
BEGIN
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_program_isolation();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-21 breaks program isolation (% problems): %', n, d;
    END IF;

    SELECT count(*), string_agg(problem || ': ' || subject, '; ')
      INTO n, d FROM check_surface_promotion();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-21 refuses to finish: % promotion violation(s): %', n, d;
    END IF;
END $$;
