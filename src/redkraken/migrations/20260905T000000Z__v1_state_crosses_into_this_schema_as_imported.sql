-- ===========================================================================
-- Ticket 58 -- v1 state crosses into this schema as `imported`
-- ===========================================================================
-- 20260813T090000Z reserved one word and left it unused: "`imported` is ticket
-- 58's, which is the one place v1 state crosses into this schema". This is that
-- place, and the whole of the design is what it refuses to write.
--
-- What an operator hands over is one redacted export, selected by path, carrying
-- a schema version and a hash of itself. What comes back out of it is four
-- things and no more:
--
--   the configuration      validated against this Program's scope and never
--                          applied. A v1 engagement's own scope is read to
--                          decide what may cross, not to widen what may be
--                          reached; the operator's configuration is the only
--                          thing that has ever set scope and still is.
--   the Surface            domains, hosts and applications, converged on the
--                          same dedup key the runtime uses, at `imported` when
--                          the export retained the bytes behind them and at
--                          `proposed` when it did not.
--   the finding hints      one row per (subject, Property class FAMILY), with a
--                          count and a severity ceiling. There is no column for
--                          a leaf Property class, no column for a status and no
--                          column for a label, so criterion 4 is a fact about
--                          the table rather than a rule somebody applies: a
--                          v1 `confirmed` cannot be spelt here.
--   the artifacts          bytes the export retained, filed under their own
--                          hash as a fourth kind of reference, and only after
--                          the digest matched and no redaction rule did.
--
-- What it will not write, ever: a Receipt, a Tool Run, an Agent run, a Task, a
-- Hypothesis, a Finding, a Test run or a pivot stamp. v1 retained none of the
-- provenance any of those stand on, and a row of any of them created here would
-- be this harness telling itself a story about work nobody can produce. Section
-- 6 is the standing check that says so out loud.
--
-- Every record is reported under one of five words -- accepted, merged, demoted,
-- skipped, redacted -- and the words are a closed vocabulary on the table rather
-- than a phrase in a summary, so "what happened to record 47" has an answer.
--
-- Why the Surface walk here is not `promote_proposal`'s. Two reasons, and both
-- are structural. `proposals.agent_run_id` and `proposals.task_id` are NOT NULL:
-- an import that staged a proposal would have to invent an Agent run and a Task
-- to hang it on, which is exactly the fabrication criterion 4 forbids, so an
-- import cannot be a proposal. And an import carries no Receipt, which
-- `promote_proposal` refuses as `no_provenance` for a reason that is right for
-- it -- a proposed Entity citing nothing is a guess. The three types accepted
-- here are the parentless ones for the same reason: an Endpoint recovered from a
-- v1 database is a claim about a route that nothing in the export witnessed, and
-- criterion 3 says such a row is a proposal rather than Surface. What an import
-- honestly carries is which addresses exist, which is what stops v2 enumerating
-- the same ground twice.
-- ---------------------------------------------------------------------------


-- ---------------------------------------------------------------------------
-- 1. A fourth reason a Program holds an Artifact
-- ---------------------------------------------------------------------------
-- 20260814T050000Z turned the three kinds into a table exactly so that a
-- ticket needing a fourth would add a row. `imported` is not `runtime`: the
-- harness did not store these bytes in the course of its own work, another
-- harness did, and a source analysis tool pointed at `source` must not reach
-- them on the strength of a word.

INSERT INTO artifact_reference_kinds (kind, description) VALUES
    ('imported',    'bytes a v1 export retained, filed under their own hash '
                    'after the digest matched and no redaction rule did');


-- ---------------------------------------------------------------------------
-- 2. One export, by the hash of itself
-- ---------------------------------------------------------------------------
-- The import unit. Idempotence lives here and nowhere else: a second run of the
-- same export against the same Program returns the first run's report rather
-- than walking the payload again, which is the same answer `promote_proposal`
-- gives a caller retrying after a lost connection.

CREATE TABLE v1_imports (
    id             uuid NOT NULL PRIMARY KEY DEFAULT uuidv7(),
    program_id     uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    -- The attribution criterion 2 asks for. Every record below hangs off this
    -- row, so "where did this Entity come from" is answerable as a path back to
    -- one hash of one directory an operator named.
    source_sha256  text NOT NULL CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
    schema_version text NOT NULL,
    exported_at    timestamptz NOT NULL,
    imported_at    timestamptz NOT NULL DEFAULT now(),
    -- Which scope decided what crossed. The projection moves when the operator
    -- revises the configuration, and a record of an import that does not say
    -- which version refused a host cannot be re-read later.
    scope_version  integer NOT NULL,
    report         jsonb NOT NULL,
    -- Program-scoped, which is criterion 5's isolation half: the same export
    -- imported into two Programs is two rows and two sets of records, and
    -- neither can see the other's.
    UNIQUE (program_id, source_sha256),
    UNIQUE (id, program_id)
);

COMMENT ON TABLE v1_imports IS
    'One operator-selected v1 export, by the hash of its own manifest. The '
    'source hash every imported row is attributed to, and the key idempotence '
    'is decided on.';

COMMENT ON COLUMN v1_imports.report IS
    'The answer the first run gave, kept so a repeat returns what is true '
    'rather than what this call did.';


-- ---------------------------------------------------------------------------
-- 3. Every record, and what became of it
-- ---------------------------------------------------------------------------
-- Criterion 5 names five outcomes and this table names the same five. A silent
-- drop is indistinguishable from a record the export never held -- 020 made the
-- same argument for `proposal_drops` -- and here it is worse, because the thing
-- being audited is whether an import invented anything.

CREATE TABLE v1_import_records (
    import_id   uuid NOT NULL,
    program_id  uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    ordinal     integer NOT NULL,
    kind        text NOT NULL
                CHECK (kind IN ('scope','surface','finding','artifact')),
    -- What the export called it. Opaque here on purpose: it is the operator's
    -- handle for going back to the export and looking, not a key.
    ref         text NOT NULL,
    disposition text NOT NULL
                CHECK (disposition IN ('accepted','merged','demoted','skipped','redacted')),
    detail      text NOT NULL,
    -- What it became, where it became something. All three null for a skip.
    entity_id   uuid,
    hint_id     uuid,
    sha256      text CHECK (sha256 IS NULL OR sha256 ~ '^[0-9a-f]{64}$'),
    PRIMARY KEY (import_id, ordinal),
    UNIQUE (import_id, kind, ref),
    FOREIGN KEY (import_id, program_id) REFERENCES v1_imports (id, program_id) ON DELETE CASCADE,
    FOREIGN KEY (entity_id, program_id) REFERENCES entities   (id, program_id),
    -- A skip produced nothing, and a row claiming otherwise would be the one
    -- shape a reader counting acceptances cannot see past.
    CHECK (disposition <> 'skipped'
           OR (entity_id IS NULL AND hint_id IS NULL AND sha256 IS NULL)),
    -- And a redaction produced nothing either, which is the stronger of the
    -- two: `redacted` is the word for bytes this import refused to file, so a
    -- redacted record naming the hash it filed them under would be the failure
    -- inverted -- the audit saying the secret was kept out while the store
    -- holds it.
    CHECK (disposition <> 'redacted'
           OR (entity_id IS NULL AND hint_id IS NULL AND sha256 IS NULL))
);

CREATE INDEX v1_import_records_disposition_idx
    ON v1_import_records (import_id, disposition, kind);

COMMENT ON TABLE v1_import_records IS
    'One row per record the export offered, under one of the five words '
    'criterion 5 names. The import''s own audit: what it took, what it merged, '
    'what it took less of than was claimed, what it would not take and what it '
    'refused to file.';

COMMENT ON COLUMN v1_import_records.disposition IS
    'accepted -- written as offered. merged -- this Program already held it and '
    'the import is a second voice for it. demoted -- written with less than was '
    'claimed, because the export retained no bytes behind the claim. skipped -- '
    'not written: out of scope, malformed, or about another Program. redacted '
    '-- bytes a redaction rule matched, which are not filed at all.';


-- ---------------------------------------------------------------------------
-- 4. What a v1 finding is allowed to become
-- ---------------------------------------------------------------------------
-- Story 193, as a table: "v1 findings used only as prioritization evidence at
-- family granularity, so that missing Playbook and Skill provenance is not
-- fabricated". A family is 018's rollup unit and explicitly never a dedup key,
-- which is what makes it the right granularity here -- a hint at family
-- granularity can raise the priority of looking at a subject and cannot be
-- mistaken for a claim about it, because there is no claim it corresponds to.
--
-- The absent columns are the design. No `property_class`: 007's dedup key is
-- (subject, identity a, identity b, property class) and a leaf here would be a
-- Hypothesis with the label filed off. No `status` and no `title`: v1's
-- `confirmed` is the word criterion 4 names first, and a column to put it in is
-- a column something will eventually read. No `finding_id`: a hint is not a
-- Finding that has not been validated yet, it is a different kind of thing.

CREATE TABLE v1_finding_hints (
    id                uuid NOT NULL PRIMARY KEY DEFAULT uuidv7(),
    program_id        uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    import_id         uuid NOT NULL,
    subject_entity_id uuid NOT NULL,
    family_id         text NOT NULL REFERENCES property_class_families(id),
    -- How many v1 records rolled up here. A count, because "v1 reported four
    -- authorization problems about this Application" is a different prior from
    -- "v1 reported one", and neither is a claim that any of them still holds.
    reported          integer NOT NULL CHECK (reported > 0),
    severity_ceiling  text NOT NULL
                      CHECK (severity_ceiling IN ('info','low','medium','high','critical')),
    -- Whether any of the records that rolled up here came with bytes the export
    -- retained and this import filed. Story 194's two outcomes, as a boolean:
    -- correlated to exact retained evidence, or demoted.
    correlated        boolean NOT NULL DEFAULT false,
    UNIQUE (program_id, import_id, subject_entity_id, family_id),
    UNIQUE (id, program_id),
    FOREIGN KEY (import_id, program_id)         REFERENCES v1_imports (id, program_id) ON DELETE CASCADE,
    FOREIGN KEY (subject_entity_id, program_id) REFERENCES entities   (id, program_id)
);

CREATE INDEX v1_finding_hints_subject_idx
    ON v1_finding_hints (program_id, subject_entity_id, family_id);

COMMENT ON TABLE v1_finding_hints IS
    'What a v1 finding is allowed to become: one row per subject and Property '
    'class family, with a count and a severity ceiling. Prioritization '
    'evidence, never a claim -- there is no column here a Hypothesis or a '
    'Finding could be reconstructed from.';

COMMENT ON COLUMN v1_finding_hints.correlated IS
    'True when at least one of the records behind this hint arrived with bytes '
    'the export retained and this import filed. False is the demoted case, '
    'which is every v1 terminal label with nothing behind it.';

ALTER TABLE v1_import_records
    ADD FOREIGN KEY (hint_id, program_id) REFERENCES v1_finding_hints (id, program_id) ON DELETE CASCADE;


-- ---------------------------------------------------------------------------
-- 5. The one writer
-- ---------------------------------------------------------------------------

-- The severity order, once. `findings.severity` and the ceiling above are the
-- same five words and a ceiling is a maximum, so somebody has to say which of
-- two is higher; an inline CASE at the one call site would be a second spelling
-- of a vocabulary the schema already closed twice.
CREATE FUNCTION rk2_severity_rank(p_severity text) RETURNS integer
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $fn$
    SELECT array_position(ARRAY['info','low','medium','high','critical'], p_severity)
$fn$;

COMMENT ON FUNCTION rk2_severity_rank(text) IS
    'Where one severity sits in the order, or null for a word that is not one '
    'of the five. Null is the refusal: a ceiling computed over an unknown '
    'severity would silently be the other operand.';

-- One list out of the payload, or an empty one. Four call sites ask the same
-- question and a `CASE jsonb_typeof(...)` written four times is four chances to
-- let a scalar through as a one-element array.
CREATE FUNCTION rk2_import_list(p_payload jsonb, p_key text) RETURNS jsonb
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $fn$
    SELECT CASE WHEN jsonb_typeof(p_payload -> p_key) = 'array'
                THEN p_payload -> p_key ELSE '[]'::jsonb END
$fn$;

COMMENT ON FUNCTION rk2_import_list(jsonb, text) IS
    'One of an export payload''s lists, or an empty list. Absent and malformed '
    'are the same answer on purpose: an import of nothing is a valid import.';

-- The four questions every loop below asks in the same words. Written once for
-- the reason `rk2_import_list` was: a sentence repeated four times is four
-- places for the fifth caller to say something slightly different, and every one
-- of these decides what an operator is told a record became.

CREATE FUNCTION rk2_import_ref(p_element jsonb) RETURNS text
LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE AS $fn$
DECLARE
    v_ref text := nullif(btrim(p_element ->> 'ref'), '');
BEGIN
    IF v_ref IS NULL THEN
        RAISE EXCEPTION 'every record of an export carries a ref'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN v_ref;
END $fn$;

COMMENT ON FUNCTION rk2_import_ref(jsonb) IS
    'The name one record answers to, or a refusal. A record with no ref cannot '
    'be reported on, and criterion 5 says every record is reported on.';

CREATE FUNCTION rk2_import_foreign(p_element jsonb, p_slug text) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $fn$
    SELECT 'the record belongs to program ' || left(btrim(p_element ->> 'program'), 100)
     WHERE nullif(btrim(p_element ->> 'program'), '') IS NOT NULL
       AND btrim(p_element ->> 'program') <> p_slug
$fn$;

COMMENT ON FUNCTION rk2_import_foreign(jsonb, text) IS
    'Why one record is somebody else''s, or null. The manifest''s program name '
    'is about the whole export; this is about one row, which is the shape that '
    'survives a manifest check.';

CREATE FUNCTION rk2_import_correlated(p_kept jsonb, p_element jsonb) RETURNS boolean
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $fn$
    SELECT coalesce(p_kept ->> nullif(btrim(p_element ->> 'evidence'), ''), '') = 'retained'
$fn$;

COMMENT ON FUNCTION rk2_import_correlated(jsonb, jsonb) IS
    'Whether the export retained the bytes this record points at. The pointing '
    'is the export''s claim; that the bytes are the bytes it named is what was '
    'checked, and correlation is the two together.';

CREATE FUNCTION rk2_import_disposition(p_created boolean, p_correlated boolean) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $fn$
    SELECT CASE WHEN NOT p_created THEN 'merged'
                WHEN p_correlated  THEN 'accepted'
                ELSE 'demoted' END
$fn$;

COMMENT ON FUNCTION rk2_import_disposition(boolean, boolean) IS
    'What became of a record this Program now holds a row for: merged into one '
    'that was already there, accepted on retained bytes, or demoted for having '
    'none.';

-- One import, whole. Everything the caller has already done -- verify the
-- manifest, hash every file, rescan the bytes, file what survived -- is checked
-- again here where it can be, because a function that took the caller's word
-- for what it filed would be trusting the one thing this ticket is about.
--
-- `p_source` is the export's identity: schema, source hash, export time.
-- `p_payload` is its four lists. The report comes back as jsonb and is stored,
-- so the answer survives the connection that asked for it.
CREATE FUNCTION record_v1_import(p_source jsonb, p_payload jsonb) RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p            uuid := rk2_program_required();
    v_import     uuid;
    v_sha        text := nullif(btrim(p_source ->> 'source_sha256'), '');
    v_schema     text := nullif(btrim(p_source ->> 'schema'), '');
    v_exported   timestamptz;
    v_version    integer;
    v_slug       text;
    v_next       integer := 0;
    v_element    jsonb;
    v_ref        text;
    v_reason     text;
    v_type       text;
    v_state      text;
    v_kept       jsonb := '{}'::jsonb;   -- artifact ref -> state, as the export claims
    v_refs       jsonb := '{}'::jsonb;   -- surface ref -> entity id, for the findings
    v_origin     text;
    v_disposition text;
    v_detail     text;
    v_entity     uuid;
    v_created    boolean;
    v_hint       uuid;
    v_fault      text;
    v_selector_kind text;
    v_selector   text;
    v_port       integer;
    v_path_text  text;
    v_dedup      text;
    v_scope_class text;
    v_fqdn       text;
    v_apex       text;
    v_wildcard   boolean;
    v_hostname   text;
    v_address    text;
    v_scheme     text;
    v_base_url   text;
    v_app_kind   text;
    v_family     text;
    v_severity   text;
    v_subject    uuid;
    v_correlated boolean;
    v_earlier    boolean;
    v_wrote      boolean := false;
    v_counts     jsonb;
BEGIN
    IF v_sha IS NULL OR v_sha !~ '^[0-9a-f]{64}$' THEN
        RAISE EXCEPTION 'an import is identified by the sha256 of its manifest'
            USING ERRCODE = 'check_violation';
    END IF;
    IF v_schema IS NULL THEN
        RAISE EXCEPTION 'an import states the schema version of the export it read'
            USING ERRCODE = 'check_violation';
    END IF;

    -- Idempotent, and it reports the same answer rather than a different one.
    SELECT i.id, i.report INTO v_import, v_counts
      FROM v1_imports i WHERE i.program_id = p AND i.source_sha256 = v_sha;
    IF FOUND THEN
        RETURN v_counts || jsonb_build_object('import', v_import::text, 'repeated', true);
    END IF;

    -- The same actor the caller declared before it filed the artifacts, spelt
    -- the same way. `set_actor` overwrites, so a second spelling here would
    -- attribute the import event to one name and the references filed a moment
    -- earlier in the same transaction to another.
    PERFORM set_actor('runtime', 'rk import');

    SELECT pr.scope_version, pr.slug INTO v_version, v_slug FROM programs pr WHERE pr.id = p;
    IF v_version IS NULL THEN
        -- Fail closed rather than import wide. Every record below is admitted
        -- on the strength of a scope class, and a Program whose policy has not
        -- been compiled has no class to give: importing into one would be
        -- taking another engagement's word for what may be touched, which is
        -- the one thing the configuration half of this ticket refuses.
        RAISE EXCEPTION 'this Program has no compiled scope version to classify an import against'
            USING ERRCODE = 'check_violation',
                  HINT = 'compile the scope policy before importing v1 state';
    END IF;

    BEGIN
        v_exported := (p_source ->> 'exported_at')::timestamptz;
    EXCEPTION WHEN invalid_datetime_format OR datetime_field_overflow THEN
        v_exported := NULL;
    END;
    IF v_exported IS NULL THEN
        RAISE EXCEPTION 'an import states when the export it read was taken'
            USING ERRCODE = 'check_violation';
    END IF;

    -- One pass for a ref that repeats inside its own list, before anything is
    -- written. `v1_import_records` is unique on (import, kind, ref) and would
    -- refuse the second one halfway through with a constraint name, which tells
    -- an operator holding a bad export nothing about which record to look at.
    SELECT k.kind || ' record ' || left(btrim(e.value ->> 'ref'), 60)
      INTO v_reason
      FROM (VALUES ('artifact', 'artifacts'), ('scope', 'scope'),
                   ('surface', 'surface'), ('finding', 'findings')) k(kind, key),
           LATERAL jsonb_array_elements(rk2_import_list(p_payload, k.key)) e(value)
     GROUP BY k.kind, btrim(e.value ->> 'ref')
    HAVING count(*) > 1
     LIMIT 1;
    IF v_reason IS NOT NULL THEN
        RAISE EXCEPTION 'an export names the same % twice', v_reason
            USING ERRCODE = 'check_violation';
    END IF;

    INSERT INTO v1_imports
        (program_id, source_sha256, schema_version, exported_at, scope_version, report)
    VALUES (p, v_sha, v_schema, v_exported, v_version, '{}'::jsonb)
    RETURNING id INTO v_import;

    -- === Artifacts =========================================================
    -- First, because the Surface and the hints ask what became of the bytes.
    -- The caller has already filed what survived; what happens here is the
    -- other half of that -- holding its account of each one against the row it
    -- would have had to write, in both directions.
    FOR v_element IN
        SELECT value FROM jsonb_array_elements(rk2_import_list(p_payload, 'artifacts'))
    LOOP
        v_ref := rk2_import_ref(v_element);
        v_state := nullif(btrim(v_element ->> 'state'), '');
        v_reason := NULL;

        IF v_state IS NULL OR v_state NOT IN ('retained','redacted','stale','absent') THEN
            v_disposition := 'skipped';
            v_detail := 'the export says nothing usable about these bytes';
        ELSIF coalesce(v_element ->> 'sha256', '') !~ '^[0-9a-f]{64}$' THEN
            v_disposition := 'skipped';
            v_detail := 'the record names no sha256, so nothing about these bytes is checkable';
        ELSE
            -- The check the caller cannot talk its way past. `retained` means a
            -- reference of kind `imported` exists for this Program; anything
            -- else means one must not. A caller that filed a secret and then
            -- called it redacted is refused here, which is where it matters,
            -- because the alternative is bytes in the store that the audit says
            -- were never taken.
            v_created := EXISTS (
                SELECT 1 FROM artifact_references x
                 WHERE x.program_id = p AND x.sha256 = v_element ->> 'sha256'
                   AND x.kind = 'imported');
            -- Except where an earlier import of this Program already accepted
            -- those bytes. Two exports of the same engagement disagreeing about
            -- one artifact -- v1 pruned it, or a redaction rule shipped between
            -- them -- is a disagreement between exports and not a caller lying
            -- about what it filed, and refusing it would leave the second
            -- import unrunnable with no way to withdraw the first.
            v_earlier := EXISTS (
                SELECT 1 FROM v1_import_records r
                 WHERE r.program_id = p AND r.sha256 = v_element ->> 'sha256'
                   AND r.import_id <> v_import);
            IF v_state = 'retained' AND NOT v_created THEN
                RAISE EXCEPTION 'artifact % is claimed as retained and this Program holds no imported reference to it', v_ref
                    USING ERRCODE = 'check_violation';
            ELSIF v_state <> 'retained' AND v_created AND NOT v_earlier THEN
                RAISE EXCEPTION 'artifact % is claimed as % and this Program holds an imported reference to it', v_ref, v_state
                    USING ERRCODE = 'check_violation';
            END IF;
            v_disposition := CASE v_state
                WHEN 'retained' THEN 'accepted'
                WHEN 'redacted' THEN 'redacted'
                ELSE 'skipped' END;
            v_detail := CASE v_state
                WHEN 'retained' THEN 'the bytes hash to the name the export filed them under'
                WHEN 'redacted' THEN 'a redaction rule matched these bytes and they were not filed'
                WHEN 'stale'    THEN 'the bytes do not hash to the name the export filed them under'
                ELSE 'the export names these bytes and does not carry them' END;
            IF v_earlier AND v_state <> 'retained' THEN
                v_detail := v_detail || '; an earlier import of this Program retained them';
            END IF;
        END IF;

        v_kept := v_kept || jsonb_build_object(
            v_ref, CASE WHEN v_disposition = 'accepted' THEN 'retained' ELSE 'lost' END);
        INSERT INTO v1_import_records
            (import_id, program_id, ordinal, kind, ref, disposition, detail, sha256)
        VALUES (v_import, p, v_next, 'artifact', v_ref, v_disposition, v_detail,
                CASE WHEN v_disposition = 'accepted' THEN v_element ->> 'sha256' END);
        v_next := v_next + 1;
    END LOOP;

    -- === Configuration =====================================================
    -- Read, classified, recorded, and applied to nothing. The v1 scope is the
    -- export's account of what it was allowed to touch; this Program's scope is
    -- the operator's account of what it is allowed to touch, and only the
    -- second one has ever set a rule. An entry this Program denies is skipped
    -- with the sentence, which is the one an operator wanting it back acts on.
    FOR v_element IN
        SELECT value FROM jsonb_array_elements(rk2_import_list(p_payload, 'scope'))
    LOOP
        v_ref := rk2_import_ref(v_element);
        v_selector := scope_normalize_host(v_element ->> 'host');
        v_port := CASE WHEN v_element ->> 'port' ~ '^[0-9]{1,5}$'
                       THEN (v_element ->> 'port')::integer END;
        IF v_selector IS NULL THEN
            v_disposition := 'skipped';
            v_detail := 'the entry names no host this Program could classify';
        ELSE
            SELECT s.scope_class INTO v_scope_class
              FROM scope_class_of(p, v_version, v_selector, v_port) s;
            v_disposition := CASE WHEN v_scope_class = 'denied' THEN 'skipped' ELSE 'accepted' END;
            v_detail := v_selector || coalesce(':' || v_port::text, '') ||
                        ' classifies ' || v_scope_class || ' under scope version ' ||
                        v_version::text;
        END IF;
        INSERT INTO v1_import_records
            (import_id, program_id, ordinal, kind, ref, disposition, detail)
        VALUES (v_import, p, v_next, 'scope', v_ref, v_disposition, v_detail);
        v_next := v_next + 1;
    END LOOP;

    -- === Surface ===========================================================
    FOR v_element IN
        SELECT value FROM jsonb_array_elements(rk2_import_list(p_payload, 'surface'))
    LOOP
        v_ref := rk2_import_ref(v_element);
        v_reason := NULL; v_fault := NULL; v_entity := NULL;
        v_selector_kind := NULL; v_selector := NULL; v_port := NULL;
        v_path_text := '/'; v_dedup := NULL; v_base_url := NULL;
        v_fqdn := NULL; v_apex := NULL; v_wildcard := NULL;
        v_hostname := NULL; v_address := NULL; v_app_kind := NULL;
        v_type := nullif(btrim(v_element ->> 'type'), '');

        -- Criterion 6's cross-Program identifier, at the record level, and it is
        -- asked first because a row belonging to somebody else is not this
        -- Program's to have an opinion about the shape of.
        v_reason := rk2_import_foreign(v_element, v_slug);
        IF v_reason IS NOT NULL THEN
            NULL;
        ELSIF v_type IS NULL OR v_type NOT IN ('domain','host','application') THEN
            v_reason := 'an import carries domains, hosts and applications; ' ||
                        coalesce(left(v_type, 60), 'no type') || ' is not one of them';
        ELSIF v_type = 'domain' THEN
            v_fqdn := scope_normalize_host(v_element ->> 'fqdn');
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
                v_fault := 'address is not an IP address';
            ELSIF v_hostname IS NULL AND v_address IS NULL THEN
                v_fault := 'a host needs a hostname or an address, and neither was usable';
            ELSE
                v_selector_kind := 'host';
                v_selector := coalesce(v_hostname, v_address);
                v_dedup := rk2_dedup_key(v_type, ARRAY[v_selector]);
            END IF;
        ELSE   -- application
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
                v_base_url := v_scheme || '://' || v_selector ||
                    CASE WHEN v_port = CASE WHEN v_scheme = 'https' THEN 443 ELSE 80 END
                         THEN '' ELSE ':' || v_port::text END ||
                    CASE WHEN v_path_text = '/' THEN '' ELSE v_path_text END;
                v_dedup := rk2_dedup_key(v_type, ARRAY[v_base_url]);
            END IF;
        END IF;

        IF v_reason IS NULL AND v_fault IS NOT NULL THEN
            v_reason := left(v_fault, 300);
        END IF;

        -- Scope, before the row exists. The Spec forbids discovery outside the
        -- configured scope and an import is discovery somebody else did.
        IF v_reason IS NULL THEN
            SELECT s.scope_class INTO v_scope_class
              FROM scope_class_of_entity(p, v_version, v_selector_kind, v_selector,
                                         v_port, v_path_text, v_path_text) s;
            IF v_scope_class = 'denied' THEN
                v_reason := 'out of this Program''s scope: ' ||
                            left(coalesce(v_selector, '') ||
                                 coalesce(':' || v_port::text, ''), 200);
            END IF;
        END IF;

        IF v_reason IS NOT NULL THEN
            INSERT INTO v1_import_records
                (import_id, program_id, ordinal, kind, ref, disposition, detail)
            VALUES (v_import, p, v_next, 'surface', v_ref, 'skipped', v_reason);
            v_next := v_next + 1;
            CONTINUE;
        END IF;

        -- Criterion 3, at the one place it is decidable. A row the export
        -- retained bytes for keeps the provenance it claims and is `imported`;
        -- a row with nothing behind it is an unverified proposal and is
        -- `proposed`, which is the origin the runtime's own promotion writes for
        -- something nobody has confirmed either.
        v_correlated := rk2_import_correlated(v_kept, v_element);
        v_origin := CASE WHEN v_correlated THEN 'imported' ELSE 'proposed' END;

        -- The lift is one way and only out of `proposed`. Two v1 rows for one
        -- address, one of them carrying bytes, say the same thing whichever the
        -- export lists first, and an Entity whose origin depended on that order
        -- would make the report a fact about the file rather than about what is
        -- behind it. Anything the runtime itself established outranks both and
        -- is left alone: an import is the weakest voice in the table.
        INSERT INTO entities
            (program_id, type, dedup_key, origin, scope_selector_kind,
             scope_selector, scope_port, scope_path_raw, scope_path_norm)
        VALUES (p, v_type, v_dedup, v_origin, v_selector_kind,
                v_selector, v_port, v_path_text, v_path_text)
        ON CONFLICT (program_id, type, dedup_key)
            DO UPDATE SET last_seen_at = now(),
                          origin = CASE
                              WHEN entities.origin = 'proposed'
                               AND EXCLUDED.origin = 'imported' THEN 'imported'
                              ELSE entities.origin END
        RETURNING id, (xmax = 0) INTO v_entity, v_created;
        v_wrote := true;

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
        ELSE
            INSERT INTO applications (entity_id, base_url, kind)
            VALUES (v_entity, v_base_url, v_app_kind)
            ON CONFLICT (entity_id) DO UPDATE
               SET kind = coalesce(applications.kind, EXCLUDED.kind);
        END IF;

        -- No Receipt and no Tool Run, which 20260813T090000Z's own comment
        -- calls "the configured and imported case, where the evidence is a
        -- document outside the database". The element path names the record in
        -- the export, so the document can be opened at the right line.
        INSERT INTO entity_provenance
            (program_id, entity_id, origin, element_path)
        VALUES (p, v_entity, v_origin, 'v1:' || left(v_sha, 12) || ':' || v_ref);

        v_refs := v_refs || jsonb_build_object(v_ref, v_entity::text);
        v_disposition := rk2_import_disposition(v_created, v_correlated);
        INSERT INTO v1_import_records
            (import_id, program_id, ordinal, kind, ref, disposition, detail, entity_id)
        VALUES (v_import, p, v_next, 'surface', v_ref, v_disposition,
                CASE v_disposition
                    WHEN 'merged'   THEN 'this Program already held ' || v_dedup ||
                                         '; the import is a second voice for it'
                    WHEN 'accepted' THEN v_dedup || ', at origin imported: the export '
                                         || 'retained the bytes behind it'
                    ELSE v_dedup || ', at origin proposed: the export retained no '
                                 || 'bytes behind it' END,
                v_entity);
        v_next := v_next + 1;
    END LOOP;

    -- === Findings ==========================================================
    -- Nothing here writes a Finding, a Hypothesis or a Test run. What a v1
    -- finding produces is a count against a family, and the v1 status travels
    -- into the record's `detail` -- a sentence an operator reads -- and into no
    -- column anything joins on.
    FOR v_element IN
        SELECT value FROM jsonb_array_elements(rk2_import_list(p_payload, 'findings'))
    LOOP
        v_ref := rk2_import_ref(v_element);
        v_hint := NULL;
        v_family := nullif(btrim(v_element ->> 'family'), '');
        v_severity := lower(coalesce(nullif(btrim(v_element ->> 'severity'), ''), ''));
        v_subject := nullif(v_refs ->> nullif(btrim(v_element ->> 'subject_ref'), ''), '')::uuid;
        v_state := coalesce(nullif(btrim(v_element ->> 'status'), ''), 'unstated');

        v_reason := rk2_import_foreign(v_element, v_slug);
        IF v_reason IS NOT NULL THEN
            NULL;
        ELSIF v_family IS NULL
              OR NOT EXISTS (SELECT 1 FROM property_class_families f WHERE f.id = v_family) THEN
            v_reason := 'a hint is filed against a Property class family, and ' ||
                        coalesce(left(v_family, 60), 'none') || ' is not one';
        ELSIF rk2_severity_rank(v_severity) IS NULL THEN
            v_reason := 'severity is not one of info, low, medium, high, critical';
        ELSIF v_subject IS NULL THEN
            v_reason := 'its subject ' ||
                        coalesce(left(btrim(v_element ->> 'subject_ref'), 60), 'is unnamed') ||
                        ' is not Surface this import wrote';
        END IF;

        IF v_reason IS NOT NULL THEN
            INSERT INTO v1_import_records
                (import_id, program_id, ordinal, kind, ref, disposition, detail)
            VALUES (v_import, p, v_next, 'finding', v_ref, 'skipped', v_reason);
            v_next := v_next + 1;
            CONTINUE;
        END IF;

        v_correlated := rk2_import_correlated(v_kept, v_element);

        INSERT INTO v1_finding_hints
            (program_id, import_id, subject_entity_id, family_id, reported,
             severity_ceiling, correlated)
        VALUES (p, v_import, v_subject, v_family, 1, v_severity, v_correlated)
        ON CONFLICT (program_id, import_id, subject_entity_id, family_id) DO UPDATE
           SET reported = v1_finding_hints.reported + 1,
               severity_ceiling = CASE
                   WHEN rk2_severity_rank(EXCLUDED.severity_ceiling)
                      > rk2_severity_rank(v1_finding_hints.severity_ceiling)
                   THEN EXCLUDED.severity_ceiling
                   ELSE v1_finding_hints.severity_ceiling END,
               correlated = v1_finding_hints.correlated OR EXCLUDED.correlated
        RETURNING id, (xmax = 0) INTO v_hint, v_created;

        v_disposition := rk2_import_disposition(v_created, v_correlated);
        INSERT INTO v1_import_records
            (import_id, program_id, ordinal, kind, ref, disposition, detail, hint_id)
        VALUES (v_import, p, v_next, 'finding', v_ref, v_disposition,
                'v1 called it ' || left(v_state, 60) || ' at ' || v_severity ||
                CASE v_disposition
                    WHEN 'merged'   THEN '; it joins the ' || v_family || ' hint about its subject'
                    WHEN 'accepted' THEN '; it is a ' || v_family ||
                                         ' hint correlated to bytes the export retained'
                    ELSE '; the label is dropped and it is a ' || v_family ||
                         ' hint with nothing behind it' END,
                v_hint);
        v_next := v_next + 1;
    END LOOP;

    IF v_wrote THEN
        PERFORM refresh_scope_projection(p);
    END IF;

    SELECT jsonb_build_object(
        'source_sha256', v_sha,
        'schema', v_schema,
        'scope_version', v_version,
        'records', v_next,
        'by_disposition', coalesce(jsonb_object_agg(d.disposition, d.n), '{}'::jsonb),
        'by_kind', coalesce((SELECT jsonb_object_agg(k.kind, k.n)
                               FROM (SELECT r.kind, count(*) AS n FROM v1_import_records r
                                      WHERE r.import_id = v_import GROUP BY r.kind) k),
                            '{}'::jsonb))
      INTO v_counts
      FROM (SELECT r.disposition, count(*) AS n FROM v1_import_records r
             WHERE r.import_id = v_import GROUP BY r.disposition) d;

    UPDATE v1_imports SET report = v_counts WHERE id = v_import;
    RETURN v_counts || jsonb_build_object('import', v_import::text, 'repeated', false);
END $fn$;

COMMENT ON FUNCTION record_v1_import(jsonb, jsonb) IS
    'One redacted v1 export, recorded whole: the configuration classified and '
    'applied to nothing, the Surface converged at imported or proposed, the '
    'findings rolled up to family hints and the retained artifacts held against '
    'the references the caller filed. Idempotent on the export''s own hash.';

REVOKE ALL ON FUNCTION record_v1_import(jsonb, jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION rk2_import_list(jsonb, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION rk2_import_ref(jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION rk2_import_foreign(jsonb, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION rk2_import_correlated(jsonb, jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION rk2_import_disposition(boolean, boolean) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION record_v1_import(jsonb, jsonb) TO rk2_runtime;
GRANT EXECUTE ON FUNCTION rk2_import_list(jsonb, text) TO rk2_runtime;
GRANT EXECUTE ON FUNCTION rk2_import_ref(jsonb) TO rk2_runtime;
GRANT EXECUTE ON FUNCTION rk2_import_foreign(jsonb, text) TO rk2_runtime;
GRANT EXECUTE ON FUNCTION rk2_import_correlated(jsonb, jsonb) TO rk2_runtime;
GRANT EXECUTE ON FUNCTION rk2_import_disposition(boolean, boolean) TO rk2_runtime;


-- ---------------------------------------------------------------------------
-- 6. What an import must never have written
-- ---------------------------------------------------------------------------
-- Criterion 4 is an absence, and an absence nobody looks for is a claim. The
-- first four rows are the fabrication the ticket is named after: no Receipt, no
-- Tool Run, no Agent run and no attempt may cite an import, and the way any of
-- them could is a provenance row that carries one. The rest hold the two tables
-- to the shape sections 3 and 4 argue for.

CREATE FUNCTION check_v1_import() RETURNS TABLE(problem text, detail text)
LANGUAGE sql STABLE AS $fn$
    -- 1. An imported Entity's provenance cites a document, never an exchange.
    -- `imported` and `configured` are the two origins with no row behind them
    -- and this is the one of the two an importer writes.
    SELECT 'imported provenance cites runtime evidence',
           ep.id::text || ' is origin imported and cites a receipt or a tool run'
      FROM entity_provenance ep
     WHERE ep.origin = 'imported'
       AND (ep.receipt_id IS NOT NULL OR ep.tool_run_id IS NOT NULL
            OR ep.agent_run_id IS NOT NULL OR ep.proposal_id IS NOT NULL)
    UNION ALL
    SELECT 'imported relationship provenance cites runtime evidence',
           rp.id::text || ' is origin imported and cites a receipt or a tool run'
      FROM relationship_provenance rp
     WHERE rp.origin = 'imported'
       AND (rp.receipt_id IS NOT NULL OR rp.tool_run_id IS NOT NULL
            OR rp.agent_run_id IS NOT NULL OR rp.proposal_id IS NOT NULL)
    UNION ALL
    -- 2. A record that says it filed bytes filed them, under the kind the
    -- import is allowed to file under. The other direction is deliberately not
    -- asked: bytes this harness fetched itself and bytes a v1 export retained
    -- can be the same bytes, and two references to one hash under two kinds is
    -- convergence rather than a leak. What would be a fault is the audit
    -- claiming a filing that did not happen.
    SELECT 'an import record names bytes this Program does not hold as imported',
           i.import_id::text || '[' || i.ordinal::text || '] names ' || i.sha256
      FROM v1_import_records i
     WHERE i.sha256 IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM artifact_references r
                        WHERE r.sha256 = i.sha256 AND r.program_id = i.program_id
                          AND r.kind = 'imported')
    UNION ALL
    -- 3. A record that produced something says which of the three, and only
    -- one of them. The CHECKs cover the two empty cases; this covers the third
    -- shape, a record naming two different things it became.
    SELECT 'an import record names more than one outcome',
           r.import_id::text || '[' || r.ordinal::text || ']'
      FROM v1_import_records r
     WHERE (r.entity_id IS NOT NULL)::integer
         + (r.hint_id IS NOT NULL)::integer
         + (r.sha256 IS NOT NULL)::integer > 1
    UNION ALL
    -- 4. Every hint is about Surface an import wrote or this Program already
    -- held, and its severity is one the vocabulary knows. The foreign key gives
    -- the first half; a hint whose subject is a Hypothesis subject and nothing
    -- else is what the second would look like.
    SELECT 'a finding hint has an unrankable severity',
           h.id::text || ' is ceilinged at ' || h.severity_ceiling
      FROM v1_finding_hints h
     WHERE rk2_severity_rank(h.severity_ceiling) IS NULL
    UNION ALL
    -- 5. The structural half of criterion 4, asked of the catalogue rather than
    -- of the rows: a column named for a leaf Property class, a status or a
    -- Finding on the hint table would be the way a hint became a claim, and it
    -- would be added by a migration rather than by a writer.
    SELECT 'the hint table grew a column a claim could be rebuilt from',
           c.column_name
      FROM information_schema.columns c
     WHERE c.table_schema = current_schema()
       AND c.table_name = 'v1_finding_hints'
       AND c.column_name IN ('property_class', 'status', 'finding_id',
                             'hypothesis_id', 'title', 'label')
$fn$;

REVOKE ALL ON FUNCTION check_v1_import() FROM PUBLIC;

COMMENT ON FUNCTION check_v1_import() IS
    'What importing v1 state can get wrong, as rows: provenance that claims an '
    'exchange nobody made, an audit naming a filing that did not happen, a '
    'record with two outcomes, and the columns whose absence is what keeps a '
    'hint from being a claim.';

INSERT INTO standing_checks (name, query, owner_ticket, note) VALUES
    ('v1_import', 'SELECT * FROM check_v1_import()', '58',
     'v1 state crosses in as imported and fabricates nothing: no imported provenance cites a Receipt, a Tool Run, an Agent run or a proposal, every record naming bytes names bytes this Program holds as imported, every record names at most one outcome, and the hint table has no column a Hypothesis or a Finding could be rebuilt from');


-- ---------------------------------------------------------------------------
-- 7. Registries
-- ---------------------------------------------------------------------------

INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
    ('v1_imports',        'program_id', 'program-scoped: the purge root'),
    ('v1_import_records', 'program_id', 'program-scoped: the purge root'),
    ('v1_finding_hints',  'program_id', 'program-scoped: the purge root'),
    ('v1_import_records', 'import_id',
     'ON DELETE CASCADE to v1_imports: a record says what became of one line of one export and says nothing without it'),
    ('v1_import_records', 'hint_id',
     'ON DELETE CASCADE to v1_finding_hints: the record names the hint it produced and the hint is the import''s own'),
    ('v1_finding_hints',  'import_id',
     'ON DELETE CASCADE to v1_imports: a hint is a rollup of one export''s findings and is not evidence on its own');

-- The import is one Event with the whole report in it, because the report is
-- what an operator reads and splitting it across a row event per record would
-- be a log nobody can hold in one hand. The two child tables are covered by it
-- in the sense ADR-0001 means: they are written in the same transaction as the
-- `v1_imports` row whose event names them, and neither exists without it.
INSERT INTO event_types (id, family, subject_table, description) VALUES
    ('import.recorded', 'row', 'v1_imports',
     'one operator-selected v1 export was read and every record in it was disposed of (ticket 58)');

INSERT INTO event_table_config
    (table_name, created_type, updated_type, ignored_columns, redacted_columns)
VALUES ('v1_imports', 'import.recorded', NULL, '{report}', '{}');

INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
    ('v1_import_records', 'covered',
     'written in the same transaction as the v1_imports row whose import.recorded event reports the same five counts', '58'),
    ('v1_finding_hints', 'covered',
     'written in the same transaction as the v1_imports row whose import.recorded event reports it, and cascaded away with it', '58');

SELECT attach_event_triggers();

GRANT SELECT, INSERT, UPDATE ON v1_imports        TO rk2_runtime;
GRANT SELECT, INSERT          ON v1_import_records TO rk2_runtime;
GRANT SELECT, INSERT, UPDATE  ON v1_finding_hints  TO rk2_runtime;

-- UPDATE on the import for its own report, which is written after the walk that
-- produced it, and on the hint for the rollup. No DELETE for anybody: an import
-- is removed by purging the Program, which is the only thing that has ever been
-- allowed to remove history.


-- ---------------------------------------------------------------------------
-- 8. The invariants this file must not have broken
-- ---------------------------------------------------------------------------

SELECT enforce_always_triggers();
SELECT enforce_fk_fire_order();
SELECT apply_state_rls();
SELECT apply_state_grants();
