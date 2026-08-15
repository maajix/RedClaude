-- ---------------------------------------------------------------------------
-- 20260815T120000Z__a_supported_claim_becomes_a_candidate.sql      (ticket 36)
-- ---------------------------------------------------------------------------
--   009 built `findings` and the four tables around it, 015 gave them labels
--   and an immutable transition log, 018 gave them a class vocabulary and 034
--   seeded it. Nothing has ever written a row. A Finding today is a table any
--   holder of INSERT can fill in: it can be born `validated`, `critical` and
--   `reported`, resting on no claim and citing no run, and every rule 009 wrote
--   is about moving one that already exists.
--
--   This file makes the first row, and makes it the only way to make one.
--   Three decisions run through it.
--
--   A Finding is not authored, it is derived. Every field that says something
--   about the target -- the subject, the two Identity cells, the Property
--   class, what the run demonstrated -- is copied off the claim and off the
--   holding run. What a caller supplies is the vulnerability class, which is a
--   word from a closed vocabulary, and the title, which is prose for a human
--   and which no rule reads. A field a caller can state is a field a caller can
--   make agree with itself, and the whole point of a Finding is that it agrees
--   with something else.
--
--   A candidate is born knowing nothing it has not yet earned. Criterion 4
--   names four states it may not be born in and three of them have no column
--   yet -- exploitation is 038's, and 037 owns validation. So the birth guard
--   is written the other way round: it holds an allowlist of the columns a
--   candidate is born with, and refuses every other column that is set. A later
--   file that adds `exploited_at` gets a refusal on the first candidate it
--   tries to write, which is the moment someone should be deciding whether a
--   candidate may carry it.
--
--   A refusal is a record, not an exception. 034 gave a refused proposal a
--   `proposal_drops` row so a hunter learns why; the same reasoning applies
--   here, and harder, because a Finding is the artefact the whole harness runs
--   towards. `open_finding` asks `rk2_finding_refusal` for a sentence and files
--   what it hears -- criterion 6's "auditable without polluting canonical
--   Findings" is the `finding_proposals` table, which is beside `findings` and
--   not inside it. Asking rather than attempting is also what keeps the record:
--   an exception would roll back the row that explains it, and 035 established
--   that catching one opens a subtransaction the event log then reports as an
--   unaccounted write.
--
--   What is deliberately not here: severity above `info`, a CVSS vector, and
--   any path from a candidate to `validating`. 038 owns the first two -- it is
--   the ticket that separates demonstrated impact from inference -- and 037
--   owns the third. This file's only transition is the one that creates the
--   row.
-- ---------------------------------------------------------------------------


-- ---------------------------------------------------------------------------
-- 1. The cell a Finding occupies
-- ---------------------------------------------------------------------------
-- 009 gave a Finding a subject and a class. Neither is the thing that makes two
-- Findings the same Finding: the class is what you decided to call it, and 018
-- made that mapping advisory on purpose, because the findings worth having are
-- the ones where the property you tested and the class you found diverge.
--
-- What makes them the same is 007's key, one table over: subject, the two
-- Identity cells and the Property class. Criterion 3 words it as "Program,
-- Property class and affected cell", which is that key with the Program in
-- front of it -- and the Program is already implied by the subject, since an
-- Entity belongs to one. It is named in the index anyway, because an index a
-- reader has to derive the isolation of is one a later migration will widen
-- without noticing.
--
-- All four columns are nullable at the table level and required by the birth
-- guard. Nothing in the corpus has ever written a `findings` row, so there is
-- nothing to backfill; the reason not to write NOT NULL regardless is that an
-- imported Finding -- 047 has to deal with v1's -- may know its subject and not
-- its cell, and a column that refuses the import is a column that makes the
-- import invent one.

-- `severity` arrived in 009 with no default, so every caller had to state one,
-- and the only one a candidate may state is `info`. A default says that in the
-- schema instead of in each caller, and the birth guard still refuses any other
-- value: what changes is that omitting it is now the way to be right rather
-- than a NOT NULL violation.
ALTER TABLE findings ALTER COLUMN severity SET DEFAULT 'info';

ALTER TABLE findings
    ADD COLUMN property_class       text REFERENCES property_classes(id),
    ADD COLUMN identity_a_entity_id uuid,
    ADD COLUMN identity_b_entity_id uuid,
    ADD COLUMN opened_by_test_run_id uuid,
    ADD COLUMN demonstrated         jsonb,
    ADD COLUMN severity_basis       text NOT NULL DEFAULT 'undetermined'
        CHECK (severity_basis IN ('undetermined', 'demonstrated_impact',
                                  'constrained_inference', 'program_context'));

-- The three citations carry the Program, because 017 rule 3 says a citation
-- between two program-scoped rows must, and both Identity cells and the run
-- are program-scoped.
--
-- All three cascade, and all three are registered below. 016's rule is not
-- "cascades are bad" but "a cascade nobody declared is": a purge deletes the
-- Program and lets the graph do the rest, and Postgres fires the parents'
-- cascades in the order their constraints were created -- `identities` and
-- `test_runs` before `findings`, both older tables -- so a NO ACTION key here
-- is a key whose check runs after its parent is already gone. That is a
-- Program that cannot be purged, which is the one failure the whole registry
-- exists to prevent. Outside a purge nothing deletes an Identity or a Test
-- run: both are immutable and the corpus has no verb that removes one.
ALTER TABLE findings
    ADD CONSTRAINT findings_identity_a_program_fk
        FOREIGN KEY (identity_a_entity_id, program_id)
        REFERENCES identities (entity_id, program_id) ON DELETE CASCADE,
    ADD CONSTRAINT findings_identity_b_program_fk
        FOREIGN KEY (identity_b_entity_id, program_id)
        REFERENCES identities (entity_id, program_id) ON DELETE CASCADE,
    ADD CONSTRAINT findings_opened_by_run_program_fk
        FOREIGN KEY (opened_by_test_run_id, program_id)
        REFERENCES test_runs (id, program_id) ON DELETE CASCADE;

INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
    ('findings', 'identity_a_entity_id',
     'ON DELETE CASCADE to identities: half the cell a Finding is about, and a Finding on a cell whose Identity is gone is about nothing'),
    ('findings', 'identity_b_entity_id',
     'ON DELETE CASCADE to identities: the other half, for the same reason'),
    ('findings', 'opened_by_test_run_id',
     'ON DELETE CASCADE to test_runs: a candidate is the reading of one holding run, and without the run there is no reading');

-- The two edge tables 009 built and nothing had ever written. Their keys to the
-- Observation and to the Hypothesis were rewritten to NO ACTION by 016 because
-- nothing declared them, which was correct while both tables were empty and is
-- the same unpurgeable Program as soon as one is not. An edge row is
-- meaningless without either end, so each end cascades.
ALTER TABLE finding_evidence
    DROP CONSTRAINT finding_evidence_observation_id_fkey,
    ADD  CONSTRAINT finding_evidence_observation_id_fkey
         FOREIGN KEY (observation_id, program_id)
         REFERENCES observations (id, program_id) ON DELETE CASCADE;

ALTER TABLE finding_hypotheses
    DROP CONSTRAINT finding_hypotheses_hypothesis_id_fkey,
    ADD  CONSTRAINT finding_hypotheses_hypothesis_id_fkey
         FOREIGN KEY (hypothesis_id, program_id)
         REFERENCES hypotheses (id, program_id) ON DELETE CASCADE;

INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
    ('finding_evidence', 'observation_id',
     'ON DELETE CASCADE to observations: a citation of an Observation that is gone is not a citation'),
    ('finding_hypotheses', 'hypothesis_id',
     'ON DELETE CASCADE to hypotheses: a rollup edge whose claim is gone rolls up nothing');

-- And the ordering 017 rule (d) asserts, which the key above just broke.
--
-- `findings` now has two keys to `test_runs`: the new cascade, and 017's NO
-- ACTION `findings_validated_run_program_fk`. Rule (d) wants every cascade on
-- that pair to fire before every NO ACTION check, and RI triggers fire in
-- alphabetical order of a name that embeds the constraint OID -- so the key
-- added a minute ago fires last, which is the wrong way round. Rebuilding the
-- NO ACTION key moves it behind the cascade. It is the same rebuild 017 does
-- for the same reason, and rule (d) is what would have caught it either way.
--
-- The MATCH FULL `findings_validated_run_holds_fk` is RESTRICT, not NO ACTION,
-- and is left where it is: 037 owns what a purge does with a validated Finding,
-- and a candidate has no validating run to restrict on.
ALTER TABLE findings
    DROP CONSTRAINT findings_validated_run_program_fk,
    ADD  CONSTRAINT findings_validated_run_program_fk
         FOREIGN KEY (validated_by_test_run_id, program_id)
         REFERENCES test_runs (id, program_id);

COMMENT ON COLUMN findings.property_class IS
    'Copied off the claim this Finding was opened from. Half of the dedup key, '
    'and not the same question as `class_id`: the Property class is what was '
    'tested, the vulnerability class is what it turned out to be.';

COMMENT ON COLUMN findings.opened_by_test_run_id IS
    'Criterion 1. The exact holding Test run that settled the claim -- not any '
    'run of the same Test, and not the run that will later validate it, which '
    'is `validated_by_test_run_id` and is 037''s to write.';

COMMENT ON COLUMN findings.identity_a_entity_id IS
    'The Identity the claim was made as, copied off it. Null for the ordinary '
    'Finding about an anonymous caller, and half of the cell either way.';

COMMENT ON COLUMN findings.identity_b_entity_id IS
    'The second Identity, for a claim about one principal reaching another '
    'principal''s data. Null unless the claim named two.';

COMMENT ON COLUMN findings.demonstrated IS
    'Criterion 2. What the holding run showed, derived from its stored '
    'assertion results by `rk2_demonstrated`: which kinds of assertion held, '
    'which roles answered, how many Receipts. The run''s own reading and no '
    'later one -- a merge leaves this where it is, because the row says what '
    'the run that opened it demonstrated and the second run says its own on '
    'its own `test_runs` row.';

COMMENT ON COLUMN findings.severity_basis IS
    'Criterion 4, as the reason rather than as the number. `undetermined` is '
    'what a candidate is born with and the only basis on which `severity` may '
    'be `info`; the other three are 038''s, and each of them requires that '
    'ticket''s separately authorised impact work to have happened.';

-- Severity is a claim about impact, and a candidate has demonstrated none. The
-- pairing is the constraint rather than the value, so 038 raises the number and
-- the reason in one statement and cannot raise one without the other.
--
-- This is 036's business rather than 038's because the birth guard alone would
-- not close the criterion: it is a BEFORE INSERT trigger, so a caller holding
-- UPDATE opens at `info` and raises the severity in the next statement, and
-- nothing anywhere would have been violated. The CHECK is what makes the
-- criterion a property of the row rather than of the moment it was written.
-- The three grounds are named here and reachable by nobody today, because a
-- CHECK needs its vocabulary closed at the point the column exists and a
-- vocabulary that grows a value per ticket is one nothing can be asserted about.
ALTER TABLE findings ADD CONSTRAINT findings_severity_needs_a_basis_check
    CHECK (severity = 'info' OR severity_basis <> 'undetermined');

-- The cell, as one value. Three places ask what cell a row is on -- the index
-- below, the lookup `open_finding` takes under a lock, and the check that
-- reports two live Findings sharing one -- and an index cannot call a function.
-- So the two that can call this one, and the key is written twice rather than
-- three times. `quote_nullable` rather than `coalesce` with a marker: it
-- renders NULL as the word NULL and quotes everything else, so no Property
-- class spelled like the marker can read as a cell it is not on. The text
-- overload and the explicit casts are deliberate -- `quote_nullable(anyelement)`
-- and `concat_ws` are both STABLE, and a cell key that is not IMMUTABLE is one
-- no index expression and no equality could be trusted with later.
CREATE FUNCTION rk2_finding_cell(p_program uuid, p_property text, p_subject uuid,
                                 p_identity_a uuid, p_identity_b uuid)
RETURNS text LANGUAGE sql IMMUTABLE AS $fn$
    SELECT quote_nullable(p_program::text)    || '|' ||
           quote_nullable(p_property)         || '|' ||
           quote_nullable(p_subject::text)    || '|' ||
           quote_nullable(p_identity_a::text) || '|' ||
           quote_nullable(p_identity_b::text)
$fn$;

COMMENT ON FUNCTION rk2_finding_cell(uuid, text, uuid, uuid, uuid) IS
    'Criterion 3. The dedup key of a Finding as one comparable value: the '
    'Program, the Property class, the subject and the Identity pair. Two rows '
    'are on one cell exactly when this answers the same thing for both.';

REVOKE ALL ON FUNCTION rk2_finding_cell(uuid, text, uuid, uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION rk2_finding_cell(uuid, text, uuid, uuid, uuid)
    TO rk2_runtime, rk2_human;

-- `NULLS NOT DISTINCT`, for 018's reason on `hypotheses_dedup_idx`: most
-- Findings are about an anonymous caller and name no Identity cell at all, and
-- under the default two of those would be different cells.
--
-- Rejected rows are outside the index. A rejected Finding is a decision that
-- was made and kept -- 009 put `rejected` in the status vocabulary -- and a
-- cell nobody may ever claim again because one attempt was rejected is a cell
-- the harness has quietly abandoned. Duplicates are outside it for the reason
-- they are marked at all.
CREATE UNIQUE INDEX findings_cell_idx
    ON findings (program_id, property_class, subject_entity_id,
                 identity_a_entity_id, identity_b_entity_id)
    NULLS NOT DISTINCT
 WHERE duplicate_of_finding_id IS NULL AND status <> 'rejected';

COMMENT ON INDEX findings_cell_idx IS
    'Criterion 3. The same key 007 dedups claims on, with the Program named. '
    'Two candidates on one cell are one candidate; `open_finding` merges into '
    'the row that is already there rather than letting the index refuse, so '
    'that a second holding run adds its evidence instead of being lost.';


-- ---------------------------------------------------------------------------
-- 2. What a candidate is born holding
-- ---------------------------------------------------------------------------
-- The allowlist, and its inversion, are the answer to criterion 4 naming states
-- that do not exist yet. Listing the forbidden columns would mean this file
-- guards `validated_by_test_run_id` and `reported_at` and says nothing about
-- `exploited_at`, because 038 has not written it -- and the guard would look
-- complete while being silent about the one state the criterion names last.
--
-- Read as a sentence: a candidate Finding is born with an identity, a Program,
-- a label, a cell, a class, a title, the run it came from, what that run
-- demonstrated, and the two words that say it has demonstrated nothing else.

CREATE FUNCTION rk2_finding_birth_columns() RETURNS text[]
LANGUAGE sql IMMUTABLE AS $fn$
    SELECT ARRAY['id', 'program_id', 'label', 'subject_entity_id',
                 'identity_a_entity_id', 'identity_b_entity_id',
                 'property_class', 'class_id', 'title',
                 'severity', 'severity_basis', 'status', 'status_changed_at',
                 'opened_by_test_run_id', 'demonstrated', 'created_at']
$fn$;

COMMENT ON FUNCTION rk2_finding_birth_columns() IS
    'Every column a candidate Finding may be born carrying. The birth guard '
    'refuses any other column that is set, so a column a later ticket adds is '
    'refused at birth until that ticket decides a candidate may hold it.';

CREATE FUNCTION enforce_finding_birth() RETURNS trigger
LANGUAGE plpgsql AS $fn$
DECLARE
    v_extra text;
BEGIN
    -- Attached to INSERT alone. 009's transition guard owns every move after
    -- this one, and a Finding that has reached `validating` is supposed to be
    -- carrying columns this list does not have.
    SELECT string_agg(e.key, ', ' ORDER BY e.key) INTO v_extra
      FROM jsonb_each(to_jsonb(NEW)) AS e(key, value)
     WHERE jsonb_typeof(e.value) <> 'null'
       AND NOT (e.key = ANY (rk2_finding_birth_columns()));
    IF v_extra IS NOT NULL THEN
        RAISE EXCEPTION
            'a Finding is created as a candidate and may not be born stating %',
            v_extra
            USING ERRCODE = '23514',
                  HINT = 'the later states are ticket 37''s and ticket 38''s to write';
    END IF;

    -- The three allowlisted columns whose value is as much a claim as their
    -- presence would be. `status` first, because it is the one a caller is
    -- likeliest to have meant.
    IF NEW.status <> 'candidate' THEN
        RAISE EXCEPTION 'a Finding is created as a candidate, not as %', NEW.status
            USING ERRCODE = '23514';
    END IF;
    IF NEW.severity <> 'info' THEN
        RAISE EXCEPTION
            'a candidate Finding has demonstrated no impact and may not be born %',
            NEW.severity
            USING ERRCODE = '23514';
    END IF;
    IF NEW.severity_basis <> 'undetermined' THEN
        RAISE EXCEPTION
            'a candidate Finding may not be born on the severity basis %',
            NEW.severity_basis
            USING ERRCODE = '23514';
    END IF;

    -- And the four the criteria require it to have. Nullable columns on the
    -- table, for the import 047 has to make; required of anything born here.
    IF NEW.property_class IS NULL THEN
        RAISE EXCEPTION 'a candidate Finding names the Property class it rests on'
            USING ERRCODE = '23514';
    END IF;
    IF NEW.opened_by_test_run_id IS NULL THEN
        RAISE EXCEPTION 'a candidate Finding names the Test run that settled its claim'
            USING ERRCODE = '23514';
    END IF;
    IF NEW.demonstrated IS NULL THEN
        RAISE EXCEPTION 'a candidate Finding states what its holding run demonstrated'
            USING ERRCODE = '23514';
    END IF;

    RETURN NEW;
END $fn$;

COMMENT ON FUNCTION enforce_finding_birth() IS
    'Criterion 4. A candidate is born with the columns `rk2_finding_birth_'
    'columns` names and no others, as a candidate, at `info`, on no severity '
    'basis, naming its cell, its holding run and what that run demonstrated.';

CREATE TRIGGER findings_birth_guard
    BEFORE INSERT ON findings
    FOR EACH ROW EXECUTE FUNCTION enforce_finding_birth();
ALTER TABLE findings ENABLE ALWAYS TRIGGER findings_birth_guard;


-- ---------------------------------------------------------------------------
-- 3. What the run demonstrated
-- ---------------------------------------------------------------------------
-- Criterion 2 asks for "demonstrated behavior ... using controlled vocabulary".
-- The temptation is a fifth taxonomy -- a list of behaviours a hunter picks
-- from -- and it would be the wrong shape twice over: it would be model-
-- authored, and it would be a second answer to a question the run already
-- answered. 035 made the run state which assertions held, of which kind, over
-- Receipts carrying which roles, and every one of those words comes from a
-- closed vocabulary this corpus already owns.
--
-- So the behaviour is read off the run. `assertion_kinds` are 035's assertion
-- kinds, `roles` are 035's roles, and `receipts` is how many exchanges the run
-- rests on. Nothing here is a sentence, which is the point: the sentence is the
-- title, and no rule reads it.

CREATE FUNCTION rk2_demonstrated(p_test_run uuid) RETURNS jsonb
LANGUAGE sql STABLE AS $fn$
    SELECT jsonb_build_object(
        'assertion_kinds', coalesce((
            SELECT jsonb_agg(DISTINCT a.value ->> 'kind')
              FROM test_runs run,
                   LATERAL jsonb_array_elements(run.assertion_results -> 'assertions') a
             WHERE run.id = p_test_run
               AND (a.value -> 'held')::boolean IS TRUE
               AND a.value ->> 'kind' IS NOT NULL), '[]'::jsonb),
        'roles', coalesce((
            SELECT jsonb_agg(DISTINCT trr.role)
              FROM test_run_receipts trr
             WHERE trr.test_run_id = p_test_run), '[]'::jsonb),
        'receipts', (
            SELECT count(*) FROM test_run_receipts trr
             WHERE trr.test_run_id = p_test_run))
$fn$;

COMMENT ON FUNCTION rk2_demonstrated(uuid) IS
    'Criterion 2''s demonstrated behaviour, read off the holding run rather '
    'than authored beside it: which kinds of assertion held, which roles the '
    'exchanges behind them carried, and how many exchanges there were.';

CREATE FUNCTION rk2_demonstrated_problem(p_demonstrated jsonb) RETURNS text
LANGUAGE plpgsql IMMUTABLE AS $fn$
DECLARE
    v_key  text;
    v_item text;
BEGIN
    IF jsonb_typeof(p_demonstrated) <> 'object' THEN
        RETURN 'the demonstrated behaviour is not an object';
    END IF;
    FOR v_key IN SELECT jsonb_object_keys(p_demonstrated) LOOP
        IF v_key NOT IN ('assertion_kinds', 'roles', 'receipts') THEN
            RETURN 'the demonstrated behaviour carries no key named ' || v_key;
        END IF;
    END LOOP;

    IF jsonb_typeof(p_demonstrated -> 'assertion_kinds') IS DISTINCT FROM 'array'
       OR jsonb_array_length(p_demonstrated -> 'assertion_kinds') = 0 THEN
        RETURN 'the demonstrated behaviour names no assertion that held';
    END IF;
    FOR v_item IN
        SELECT jsonb_array_elements_text(p_demonstrated -> 'assertion_kinds')
    LOOP
        IF NOT (v_item = ANY (rk2_test_assertion_kinds())) THEN
            RETURN v_item || ' is not an assertion kind';
        END IF;
    END LOOP;

    IF jsonb_typeof(p_demonstrated -> 'roles') IS DISTINCT FROM 'array' THEN
        RETURN 'the demonstrated behaviour names no roles';
    END IF;
    FOR v_item IN SELECT jsonb_array_elements_text(p_demonstrated -> 'roles') LOOP
        IF NOT (v_item = ANY (rk2_test_roles())) THEN
            RETURN v_item || ' is not a role';
        END IF;
    END LOOP;
    -- The control is the one role whose absence changes what the Finding says.
    -- A baseline and a variant that differ are a difference; without the
    -- control they are a difference nobody showed was about the Identity.
    IF NOT (p_demonstrated -> 'roles' @> '["control"]'::jsonb) THEN
        RETURN 'the demonstrated behaviour rests on no control exchange';
    END IF;

    IF jsonb_typeof(p_demonstrated -> 'receipts') <> 'number'
       OR (p_demonstrated ->> 'receipts')::numeric < 1 THEN
        RETURN 'the demonstrated behaviour rests on no exchange';
    END IF;

    RETURN NULL;
END $fn$;

COMMENT ON FUNCTION rk2_demonstrated_problem(jsonb) IS
    'The shape of `findings.demonstrated`: three keys, every word in the two '
    'arrays drawn from ticket 35''s vocabularies, a control among the roles and '
    'at least one exchange under all of it.';

ALTER TABLE findings ADD CONSTRAINT findings_demonstrated_shape_check
    CHECK (demonstrated IS NULL OR rk2_demonstrated_problem(demonstrated) IS NULL);


-- ---------------------------------------------------------------------------
-- 4. Every proposal, kept
-- ---------------------------------------------------------------------------
-- Criterion 6. The refused ones are the reason the table exists -- a hunter
-- whose Finding was refused learns nothing from silence, and an operator
-- reading a Program with no Findings cannot tell "nothing was proposed" from
-- "everything was refused" -- but the accepted ones are recorded too, because a
-- table that only holds refusals is one whose rate nobody can read.
--
-- Beside `findings` and not inside it, which is the whole of "without polluting
-- canonical Findings": nothing joins from here into a report, `finding_id` is
-- the only edge, and it is null exactly when nothing canonical came of the
-- proposal.

-- Every citation is composite and carries the Program, per 017 rule 3, and
-- every one cascades. This is the newest table in the corpus, so on a purge its
-- own key to `programs` fires after every other table's: by the time anything
-- deletes a row here the claim, the run and the Finding it names are already
-- gone, and a NO ACTION key would be a check that runs too late every single
-- time. Nothing outside a purge deletes any of the four parents.
CREATE TABLE finding_proposals (
    id            uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id    uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    hypothesis_id uuid,
    test_run_id   uuid,
    agent_run_id  uuid,
    class_id      text,
    title         text NOT NULL,
    outcome       text NOT NULL CHECK (outcome IN ('created', 'merged', 'refused')),
    refusal       text,
    finding_id    uuid,
    at            timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (hypothesis_id, program_id) REFERENCES hypotheses (id, program_id)
        ON DELETE CASCADE,
    FOREIGN KEY (test_run_id, program_id)   REFERENCES test_runs  (id, program_id)
        ON DELETE CASCADE,
    FOREIGN KEY (agent_run_id, program_id)  REFERENCES agent_runs (id, program_id)
        ON DELETE CASCADE,
    FOREIGN KEY (finding_id, program_id)    REFERENCES findings   (id, program_id)
        ON DELETE CASCADE,
    -- A refusal is a sentence and an outcome at once, and the two may not
    -- disagree: an accepted proposal with a refusal on it would read as refused
    -- to anybody counting, and a refused one without would say nothing.
    CHECK ((outcome = 'refused') = (refusal IS NOT NULL)),
    -- One direction only. A refused proposal names no Finding, and that is a
    -- constraint; an accepted one may name none once 047's importer starts
    -- writing rows it did not open, and that is a row still worth reading.
    CHECK (outcome <> 'refused' OR finding_id IS NULL)
);

COMMENT ON TABLE finding_proposals IS
    'Criterion 6. One row per attempt to open a Finding, accepted or not, with '
    'the sentence that refused it. Auditable beside the canonical Findings and '
    'reachable from none of them: the edge runs the other way.';

COMMENT ON COLUMN finding_proposals.class_id IS
    'Not a foreign key, deliberately. A proposal naming a class that is not in '
    'the vocabulary is one of the things the refusal is for, and a key here '
    'would refuse the record of the refusal.';

COMMENT ON COLUMN finding_proposals.finding_id IS
    'The Finding this proposal reached: created for the first, merged for a '
    'later one on the same cell, null when it was refused. Nothing outside a '
    'purge deletes a Finding, so in practice the cascade fires once, when the '
    'Program goes and takes the proposal with it.';

CREATE INDEX finding_proposals_program_idx
    ON finding_proposals (program_id, at DESC);

INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
    ('finding_proposals', 'program_id',    'program-scoped: the purge root'),
    ('finding_proposals', 'hypothesis_id', 'ON DELETE CASCADE to hypotheses: the claim proposed about'),
    ('finding_proposals', 'test_run_id',   'ON DELETE CASCADE to test_runs: the run offered as settling it'),
    ('finding_proposals', 'agent_run_id',  'ON DELETE CASCADE to agent_runs: the run that proposed'),
    ('finding_proposals', 'finding_id',    'ON DELETE CASCADE to findings: the Finding the proposal reached');

-- `audit` and not `covered`, per ADR 0001: a `covered` row is written in the
-- same transaction as an emitting row that names it, and two of the three
-- outcomes here have no emitting row at all. A refusal writes the proposal and
-- returns; a merge writes the proposal and, when the claim and its Observations
-- are already on the Finding, nothing else. `finding.created` covers exactly one
-- outcome, so classing the table by it would be classing it by its best case.
INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
    ('finding_proposals', 'audit',
     'the append-only record of what was proposed and what was answered; only the created outcome has an Event of its own, and a refused or merged proposal writes no canonical row for one to be about', '36');

SELECT attach_event_triggers();

GRANT SELECT, INSERT ON finding_proposals TO rk2_runtime;
GRANT SELECT ON finding_proposals TO rk2_human;

-- No UPDATE and no DELETE for anybody below the owner. What was proposed and
-- what was answered is settled when it is written; a row that could be edited
-- afterwards is an audit trail that agrees with whatever is convenient now.
CREATE TRIGGER finding_proposals_immutable
    BEFORE UPDATE OR DELETE ON finding_proposals
    FOR EACH ROW EXECUTE FUNCTION reject_mutation_unless_purging();


-- ---------------------------------------------------------------------------
-- 5. The refusal
-- ---------------------------------------------------------------------------
-- Criteria 1 and 5, as one function that answers with a sentence or with NULL.
-- Its own function rather than a body inside `open_finding` for 035's reason:
-- the caller has to file what it hears, and a rule that raises is a rule whose
-- answer cannot be written down.
--
-- Criterion 5 lists four things that must not satisfy it, and each maps to one
-- arm below:
--
--   an unrelated Receipt      -- arm 7. The settling transition cites a Receipt;
--                                that Receipt has to be one this run produced.
--   an adjacent Hypothesis    -- arm 5. The run's Test has to be a Test of this
--                                claim, not of the one beside it.
--   a failed replay           -- arm 6. `holds`, and only `holds`.
--   a model completion claim  -- arms 2 and 7 together. The claim has to be
--                                `supported`, and it has to have got there
--                                through a transition the runtime made -- which
--                                007 already refuses to write on a model's say
--                                so. There is no field on this function a model
--                                can fill in to change any of that.

CREATE FUNCTION rk2_finding_refusal(
        p_program uuid, p_hypothesis uuid, p_test_run uuid, p_class text)
RETURNS text
LANGUAGE plpgsql STABLE AS $fn$
DECLARE
    v_hyp  hypotheses%ROWTYPE;
    v_run  test_runs%ROWTYPE;
    v_test tests%ROWTYPE;
BEGIN
    -- 1. The claim exists, here.
    SELECT * INTO v_hyp FROM hypotheses
     WHERE id = p_hypothesis AND program_id = p_program;
    IF NOT FOUND THEN
        RETURN format('%s is not a Hypothesis of this Program', p_hypothesis);
    END IF;

    -- 2. And it is supported. Every other status is a claim that has not
    --    settled, or has settled the other way.
    IF v_hyp.status <> 'supported' THEN
        RETURN format('hypothesis %s is %s, and a Finding rests on a supported claim',
                      v_hyp.label, v_hyp.status);
    END IF;

    -- 3. A superseded claim is one 007 folded into another. The Finding belongs
    --    on the keeper, and opening it here would put a canonical row on a cell
    --    whose claim has moved.
    IF v_hyp.superseded_by IS NOT NULL THEN
        RETURN format('hypothesis %s was superseded and is no longer canonical',
                      v_hyp.label);
    END IF;

    -- 4. The run exists, here.
    SELECT * INTO v_run FROM test_runs
     WHERE id = p_test_run AND program_id = p_program;
    IF NOT FOUND THEN
        RETURN format('%s is not a Test run of this Program', p_test_run);
    END IF;

    -- 5. And it is a run of a Test of this claim.
    SELECT * INTO v_test FROM tests WHERE id = v_run.test_id;
    IF v_test.hypothesis_id <> p_hypothesis THEN
        RETURN format('test run of %s settles %s, not %s',
                      v_test.label,
                      (SELECT label FROM hypotheses WHERE id = v_test.hypothesis_id),
                      v_hyp.label);
    END IF;

    -- 6. And it held. 035 derives the outcome from the run's own Receipts, so
    --    this is a fact about what came back and not about what was reported.
    IF v_run.outcome <> 'holds' THEN
        RETURN format('the run of %s concluded %s, and a Finding rests on a run that holds',
                      v_test.label, v_run.outcome);
    END IF;
    IF v_run.lane <> 'replay' THEN
        RETURN format('the run of %s is lane %s, and a Finding rests on a replay',
                      v_test.label, v_run.lane);
    END IF;

    -- 7. And it is the run that settled this claim. Not any holding run of the
    --    same Test: the transition 007 recorded cites one Receipt, and that
    --    Receipt has to be one of this run's. A second holding run of the same
    --    Test is a re-run, and a re-run is what 037 validates with.
    IF NOT EXISTS (
        SELECT 1 FROM hypothesis_transitions ht
          JOIN test_run_receipts trr ON trr.receipt_id = ht.receipt_id
         WHERE ht.hypothesis_id = p_hypothesis
           AND ht.from_status = 'testing' AND ht.to_status = 'supported'
           AND ht.actor_kind = 'runtime'
           AND trr.test_run_id = p_test_run) THEN
        RETURN format('the run of %s is not the run that settled %s',
                      v_test.label, v_hyp.label);
    END IF;

    -- 8. The class is a word from the vocabulary. Last, because it is the one
    --    refusal that is about the proposal rather than about the evidence, and
    --    a hunter who gets this after fixing six others has learned nothing.
    IF NOT EXISTS (SELECT 1 FROM vulnerability_classes WHERE id = p_class) THEN
        RETURN format('%s is not a vulnerability class', coalesce(p_class, '(none)'));
    END IF;

    RETURN NULL;
END $fn$;

COMMENT ON FUNCTION rk2_finding_refusal(uuid, uuid, uuid, text) IS
    'Criteria 1 and 5. Whether a Finding may be opened from this claim and this '
    'run, as the sentence that says why not. NULL means yes. Answers rather '
    'than raises, so that `open_finding` can file what it hears.';

REVOKE ALL ON FUNCTION rk2_finding_refusal(uuid, uuid, uuid, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION rk2_finding_refusal(uuid, uuid, uuid, text)
    TO rk2_runtime, rk2_human;


-- ---------------------------------------------------------------------------
-- 6. The lane a citation may come from
-- ---------------------------------------------------------------------------
-- 034 wrote "evidence may only cite the agent lane" when there were two lanes
-- and one of them was the proxy fetching its own CSRF token. The rule it meant
-- is 015's: a conclusion may not rest on traffic nothing asked for. 035 added a
-- third lane, and an exchange on it is the opposite of unasked-for -- it is a
-- request a stored Test named, performed under a capability bounded to it, with
-- the Receipt recorded against the action it answered.
--
-- Left as it was, the rule would make this ticket impossible: every Observation
-- a replayed Test produces is backed by a `replay` Receipt, so a Finding could
-- cite none of the evidence its own claim rests on. Widened rather than
-- dropped, because `proxy_internal` is still exactly what 034 was refusing.
CREATE OR REPLACE FUNCTION reject_non_agent_evidence() RETURNS trigger
LANGUAGE plpgsql AS $fn$
DECLARE v_lane text; v_kind text; v_obs uuid;
BEGIN
    v_obs := (to_jsonb(NEW) ->> TG_ARGV[0])::uuid;
    IF v_obs IS NULL THEN RETURN NEW; END IF;

    SELECT o.provenance_kind, r.lane INTO v_kind, v_lane
      FROM observations o LEFT JOIN receipts r ON r.id = o.receipt_id
     WHERE o.id = v_obs;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'ungrounded: observation % does not exist', v_obs;
    END IF;
    IF v_kind = 'receipt' AND coalesce(v_lane, 'missing') NOT IN ('agent', 'replay') THEN
        RAISE EXCEPTION
            'ungrounded: observation % is backed by a % receipt; evidence may cite the agent and replay lanes',
            v_obs, coalesce(v_lane, 'missing');
    END IF;
    RETURN NEW;
END $fn$;

COMMENT ON FUNCTION reject_non_agent_evidence() IS
    'A cited Observation exists and, if it rests on a Receipt, rests on one '
    'from a lane somebody asked for: the agent''s own traffic or a Test the '
    'harness replayed. `proxy_internal` is what this refuses, and the reason '
    'the check is at INSERT is 005''s: a citation resolved at scoring time is '
    'a Finding discarded after the work.';

-- Its sibling, widened with it and for the same reason. 034 attached both to
-- `finding_chain_step_citations` -- this one reads the cited Receipt, the one
-- above reads the Receipt behind a cited Observation -- so leaving it alone
-- would make one table answer two different ways about one replay exchange:
-- admissible cited through the Observation it produced, inadmissible cited
-- directly. 040 is what builds chains, and it should find one rule there.
CREATE OR REPLACE FUNCTION reject_non_agent_citation() RETURNS trigger
LANGUAGE plpgsql AS $fn$
DECLARE v_lane text;
BEGIN
    IF NEW.receipt_id IS NOT NULL THEN
        SELECT lane INTO v_lane FROM receipts WHERE id = NEW.receipt_id;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'ungrounded: receipt % does not exist', NEW.receipt_id;
        END IF;
        IF v_lane NOT IN ('agent', 'replay') THEN
            RAISE EXCEPTION
                'ungrounded: receipt % is on the % lane; a report may cite the agent and replay lanes',
                NEW.receipt_id, v_lane;
        END IF;
    END IF;
    RETURN NEW;
END $fn$;

COMMENT ON FUNCTION reject_non_agent_citation() IS
    'A cited Receipt exists and is one somebody asked for: the agent''s own '
    'traffic or a Test the harness replayed. The same rule as '
    '`reject_non_agent_evidence`, read off the Receipt rather than through an '
    'Observation.';


-- ---------------------------------------------------------------------------
-- 7. Opening one
-- ---------------------------------------------------------------------------
-- The three outcomes are `created`, `merged` and `refused`, and the caller is
-- told which. `merged` is criterion 3's "merge or refuse deterministically",
-- and it is a merge rather than a refusal because the second holding run of a
-- second claim on the same cell is evidence -- refusing it would throw away the
-- observation that two different claims about one cell both held.
--
-- Everything the row carries beside the class and the title is copied here, in
-- one statement, from rows that were written by something else.

CREATE FUNCTION open_finding(
        p_hypothesis uuid,
        p_test_run   uuid,
        p_class      text,
        p_title      text,
        p_agent_run  uuid DEFAULT NULL)
RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p          uuid := rk2_program_required();
    v_refusal  text;
    v_hyp      hypotheses%ROWTYPE;
    v_title    text := nullif(btrim(coalesce(p_title, '')), '');
    v_existing findings%ROWTYPE;
    v_id       uuid;
    v_label    text;
    v_outcome  text;
    v_added    integer := 0;
    v_agent_run uuid;
    v_cell     text;
    v_shown    jsonb;
BEGIN
    PERFORM set_actor('runtime');

    -- Provenance, and only this Program's. An agent run belonging to somebody
    -- else is not provenance for a row here, and the composite key would raise
    -- on it -- which would lose the proposal along with the mistake.
    SELECT ar.id INTO v_agent_run
      FROM agent_runs ar WHERE ar.id = p_agent_run AND ar.program_id = p;

    v_refusal := rk2_finding_refusal(p, p_hypothesis, p_test_run, p_class);

    -- A title is the one field a human reads and no rule does, so it is checked
    -- here rather than in the refusal function: an empty title is a malformed
    -- call, not a claim that failed to hold up.
    IF v_refusal IS NULL AND v_title IS NULL THEN
        v_refusal := 'a Finding carries a title';
    END IF;

    IF v_refusal IS NOT NULL THEN
        INSERT INTO finding_proposals
            (program_id, hypothesis_id, test_run_id, agent_run_id, class_id,
             title, outcome, refusal)
        VALUES
            (p,
             (SELECT id FROM hypotheses WHERE id = p_hypothesis AND program_id = p),
             (SELECT id FROM test_runs  WHERE id = p_test_run   AND program_id = p),
             v_agent_run, p_class, coalesce(v_title, '(none)'), 'refused', v_refusal);
        RETURN jsonb_build_object('outcome', 'refused', 'refusal', v_refusal);
    END IF;

    SELECT * INTO v_hyp FROM hypotheses WHERE id = p_hypothesis;

    -- The cell, under a lock on the cell itself. `FOR UPDATE` locks the row
    -- that is there and locks nothing when there is none, which is the half of
    -- the race that matters: two runs settling at once on an empty cell would
    -- both find nothing, both insert, and the loser would take a unique
    -- violation from `findings_cell_idx` -- neither a merge nor a refusal, and
    -- an aborted transaction takes the `finding_proposals` row down with it, so
    -- criterion 6's record of the attempt would be lost along with it.
    -- 023's lock, taken 023's way: on the key rather than on the table, so
    -- opens on different cells still run at once, and held to the end of the
    -- transaction, so it is still held when the insert lands.
    v_cell := rk2_finding_cell(p, v_hyp.property_class, v_hyp.subject_entity_id,
                               v_hyp.identity_a_entity_id, v_hyp.identity_b_entity_id);
    PERFORM pg_advisory_xact_lock(hashtextextended(v_cell, 0));

    SELECT * INTO v_existing FROM findings f
     WHERE f.program_id = p
       AND f.duplicate_of_finding_id IS NULL
       AND f.status <> 'rejected'
       AND rk2_finding_cell(f.program_id, f.property_class, f.subject_entity_id,
                            f.identity_a_entity_id, f.identity_b_entity_id) = v_cell
       FOR UPDATE;

    IF FOUND THEN
        v_id      := v_existing.id;
        v_label   := v_existing.label;
        v_shown   := v_existing.demonstrated;
        v_outcome := 'merged';
    ELSE
        INSERT INTO findings
            (program_id, subject_entity_id, identity_a_entity_id,
             identity_b_entity_id, property_class, class_id, title,
             severity, severity_basis, status, opened_by_test_run_id,
             demonstrated)
        VALUES
            (p, v_hyp.subject_entity_id, v_hyp.identity_a_entity_id,
             v_hyp.identity_b_entity_id, v_hyp.property_class, p_class, v_title,
             'info', 'undetermined', 'candidate', p_test_run,
             rk2_demonstrated(p_test_run))
        RETURNING id, label, demonstrated INTO v_id, v_label, v_shown;
        v_outcome := 'created';
    END IF;

    -- The claim, and then its Observations. `ON CONFLICT DO NOTHING` on both:
    -- a merge of a claim that is already on this Finding is a second holding
    -- run of the same claim, which is a fact worth having in `finding_proposals`
    -- and not a second edge.
    INSERT INTO finding_hypotheses (finding_id, hypothesis_id, program_id)
    VALUES (v_id, p_hypothesis, p)
    ON CONFLICT DO NOTHING;

    -- Criterion 2's evidence references. Supporting Evidence only: a `refutes`
    -- edge on a supported claim is a run that disagreed and lost, and it
    -- belongs on the claim -- where it is -- rather than in the citation list
    -- of the Finding the claim produced.
    --
    -- The ordinal continues from whatever is already there, so a merge appends
    -- rather than colliding with the first claim's citations.
    WITH candidate AS (
        SELECT he.observation_id,
               row_number() OVER (ORDER BY o.observed_at, o.id) AS n
          FROM hypothesis_evidence he
          JOIN observations o ON o.id = he.observation_id
         WHERE he.hypothesis_id = p_hypothesis
           AND he.polarity = 'supports'
           AND NOT EXISTS (SELECT 1 FROM finding_evidence fe
                            WHERE fe.finding_id = v_id
                              AND fe.observation_id = he.observation_id)
    ), start AS (
        SELECT coalesce(max(ordinal), 0) AS base
          FROM finding_evidence WHERE finding_id = v_id
    )
    INSERT INTO finding_evidence (finding_id, observation_id, ordinal, program_id)
    SELECT v_id, c.observation_id, s.base + c.n, p
      FROM candidate c CROSS JOIN start s
    ON CONFLICT DO NOTHING;
    GET DIAGNOSTICS v_added = ROW_COUNT;

    INSERT INTO finding_proposals
        (program_id, hypothesis_id, test_run_id, agent_run_id, class_id,
         title, outcome, finding_id)
    VALUES (p, p_hypothesis, p_test_run, v_agent_run, p_class, v_title,
            v_outcome, v_id);

    -- `demonstrated` is read off the row, not derived again from this run: the
    -- document names a Finding, so what it says that Finding demonstrates has
    -- to be what the Finding says. On a merge the two differ -- the row holds
    -- the reading of the run that opened it -- and the second run's own reading
    -- is on its own `test_runs` row for anybody who wants it.
    RETURN jsonb_build_object(
        'outcome',       v_outcome,
        'finding_id',    v_id,
        'finding',       v_label,
        'hypothesis',    v_hyp.label,
        'class',         p_class,
        'evidence_added', v_added,
        'demonstrated',  v_shown);
END $fn$;

COMMENT ON FUNCTION open_finding(uuid, uuid, text, text, uuid) IS
    'Open one candidate Finding from a supported claim and the run that settled '
    'it, or merge into the candidate already on that cell, or refuse and file '
    'why. Everything the row states about the target is copied from the claim '
    'and the run; what a caller supplies is a class from the vocabulary and a '
    'title no rule reads.';

REVOKE ALL ON FUNCTION open_finding(uuid, uuid, text, text, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION open_finding(uuid, uuid, text, text, uuid) TO rk2_runtime;


-- ---------------------------------------------------------------------------
-- 8. What the model may read
-- ---------------------------------------------------------------------------
-- The cell and the derived behaviour. An agent writing a Finding up needs to
-- say which Identity pair it is about and what the run showed; both are copied
-- from rows it can already read, and publishing them here saves it the join --
-- which matters, because a join it makes itself is a join it can make wrong.
--
-- `severity_basis` goes with them so that a reader can tell `info` meaning
-- "nothing demonstrated" from `info` meaning "demonstrated, and it is minor".
-- `opened_by_test_run_id` does not: 020 publishes no raw run identifiers, and
-- the run is reachable by label through the surfaces that already exist.
--
-- `finding_proposals` stays unpublished in full. A refusal sentence names the
-- claim and the run of whoever proposed it, and a hunter reading other hunters'
-- refusals is reading work it was not given.

INSERT INTO state_read_surface (table_name, column_name, added_by) VALUES
    ('findings', 'property_class',       '36'),
    ('findings', 'identity_a_entity_id', '36'),
    ('findings', 'identity_b_entity_id', '36'),
    ('findings', 'demonstrated',         '36'),
    ('findings', 'severity_basis',       '36');

SELECT apply_state_grants();


-- ---------------------------------------------------------------------------
-- 9. The check
-- ---------------------------------------------------------------------------

CREATE FUNCTION check_finding_candidates()
RETURNS TABLE (problem text, subject text, detail text)
LANGUAGE sql STABLE AS $fn$
    -- A Finding that names no holding run. Unreachable through `open_finding`
    -- and reachable by anyone holding INSERT, which is the case the check is
    -- for: the birth guard is a trigger, and a later migration that disables it
    -- to backfill something leaves no other trace.
    SELECT 'finding_without_holding_run', f.label,
           'created ' || f.created_at::date::text || ' and names no Test run'
      FROM findings f
     WHERE f.opened_by_test_run_id IS NULL

    UNION ALL
    -- A Finding whose holding run stopped holding. `test_runs` is immutable so
    -- the outcome cannot have moved, but the run can be repointed by a Finding
    -- that was written around the function.
    SELECT 'finding_run_does_not_hold', f.label,
           'rests on a run that concluded ' || run.outcome
      FROM findings f JOIN test_runs run ON run.id = f.opened_by_test_run_id
     WHERE run.outcome <> 'holds'

    UNION ALL
    -- A Finding resting on a claim that is no longer supported. Not an error in
    -- itself -- 034 can reopen a claim, and a Finding on a reopened claim is
    -- exactly what an operator should be looking at -- but it is never nothing.
    SELECT 'finding_claim_not_supported', f.label,
           h.label || ' is ' || h.status
      FROM findings f
      JOIN finding_hypotheses fh ON fh.finding_id = f.id
      JOIN hypotheses h          ON h.id = fh.hypothesis_id
     WHERE f.status IN ('candidate', 'validating') AND h.status <> 'supported'

    UNION ALL
    -- A candidate carrying a severity it has not earned. The CHECK makes the
    -- pairing unreachable; this reports one that exists, for the reason above.
    SELECT 'candidate_states_impact', f.label,
           'severity ' || f.severity || ' on basis ' || f.severity_basis
      FROM findings f
     WHERE f.status = 'candidate'
       AND (f.severity <> 'info' OR f.severity_basis <> 'undetermined')

    UNION ALL
    -- Two live Findings on one cell. The index makes it unreachable, and the
    -- index is partial -- a later ticket that learns to unmark a duplicate
    -- brings a second row back onto the cell without touching this file.
    SELECT 'findings_share_a_cell',
           string_agg(f.label, ', ' ORDER BY f.label),
           min(coalesce(f.property_class, '(none)'))
      FROM findings f
     WHERE f.duplicate_of_finding_id IS NULL AND f.status <> 'rejected'
     GROUP BY rk2_finding_cell(f.program_id, f.property_class, f.subject_entity_id,
                               f.identity_a_entity_id, f.identity_b_entity_id)
    HAVING count(*) > 1

    UNION ALL
    -- The lock, asserted rather than commented, for 023's reason: the race it
    -- closes is invisible in every test that runs one transaction at a time, so
    -- a later edit that drops it looks like a simplification and reports
    -- nothing until two hunters settle on one cell at once.
    SELECT 'open_finding_takes_no_cell_lock', 'open_finding',
           'the empty-cell race is open again'
      FROM pg_proc pr
     WHERE pr.pronamespace = 'public'::regnamespace AND pr.proname = 'open_finding'
       AND pr.prosrc !~ 'pg_advisory_xact_lock'

    UNION ALL
    -- A refused proposal that reached a Finding after all. The CHECK makes it
    -- unreachable; the reverse -- an accepted proposal naming no Finding -- is
    -- not reported, because 047's importer will write accepted rows for
    -- Findings it did not open and the proposal is still the honest record of
    -- what was asked.
    SELECT 'proposal_disagrees_with_findings', fp.id::text,
           'refused and naming ' || f.label
      FROM finding_proposals fp JOIN findings f ON f.id = fp.finding_id
     WHERE fp.outcome = 'refused'

    UNION ALL
    -- A stored behaviour the shape rule would refuse, for the reason 035 gave:
    -- the constraint is a function, and a later ticket that tightens it does
    -- not revalidate what is already stored.
    SELECT 'finding_demonstrated_refused', f.label,
           rk2_demonstrated_problem(f.demonstrated)
      FROM findings f
     WHERE f.demonstrated IS NOT NULL
       AND rk2_demonstrated_problem(f.demonstrated) IS NOT NULL
$fn$;

COMMENT ON FUNCTION check_finding_candidates() IS
    'What a Finding looks like when it was not opened by `open_finding`: no '
    'holding run, a run that did not hold, a claim that stopped being '
    'supported, a candidate stating impact, two Findings on one cell, and a '
    'proposal record that disagrees with the Findings it names. And one thing '
    'that is about the function rather than the rows: whether it still takes '
    'the lock that keeps two opens off one cell.';

REVOKE ALL ON FUNCTION check_finding_candidates() FROM PUBLIC, rk2_state, rk2_proxy;
GRANT EXECUTE ON FUNCTION check_finding_candidates() TO rk2_runtime, rk2_human;

INSERT INTO standing_checks(name, query, owner_ticket, note) VALUES
    ('finding_candidates', 'SELECT * FROM check_finding_candidates()', '36',
     'every Finding names the holding Test run it was opened from, rests on a claim that is still supported, states no impact it has not demonstrated, and shares its cell with no other -- and the open still takes the lock that keeps it that way');


-- ---------------------------------------------------------------------------
-- 10. The invariants this file must not have broken
-- ---------------------------------------------------------------------------

SELECT enforce_always_triggers();

-- The birth guard is only a guard while it is the inversion of an allowlist. A
-- later file that rewrote it as a list of forbidden columns would leave every
-- column added after it silently permitted at birth, which is the failure this
-- section exists to make loud. Asserted rather than commented, because the file
-- that would break it is one nobody has written yet.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_proc
         WHERE proname = 'enforce_finding_birth'
           AND prosrc LIKE '%rk2_finding_birth_columns()%') THEN
        RAISE EXCEPTION
            'enforce_finding_birth no longer reads rk2_finding_birth_columns';
    END IF;
END $$;

-- The two callable sites read the cell off one function. An inlined predicate
-- in either would be a third writing of the dedup key, and the way that failure
-- shows up is a merge that does not merge -- a second Finding on a cell the
-- index still thinks is one, or a check that stops reporting the pair.
DO $$
DECLARE v_missing text;
BEGIN
    SELECT string_agg(want.proname, ', ' ORDER BY want.proname) INTO v_missing
      FROM (VALUES ('open_finding'), ('check_finding_candidates')) AS want(proname)
     WHERE NOT EXISTS (
        SELECT 1 FROM pg_proc p
         WHERE p.pronamespace = 'public'::regnamespace
           AND p.proname = want.proname
           AND p.prosrc LIKE '%rk2_finding_cell%');
    IF v_missing IS NOT NULL THEN
        RAISE EXCEPTION 'the cell key is written out again in %', v_missing;
    END IF;
END $$;

-- And the vocabularies the demonstrated behaviour is drawn from are 035's, not
-- copies of them. A later file that inlined the two arrays would let the two
-- drift, and the first sign of it would be a Finding stating a role no Test can
-- carry.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_proc
         WHERE proname = 'rk2_demonstrated_problem'
           AND prosrc LIKE '%rk2_test_assertion_kinds()%'
           AND prosrc LIKE '%rk2_test_roles()%') THEN
        RAISE EXCEPTION
            'rk2_demonstrated_problem no longer reads ticket 35''s vocabularies';
    END IF;
END $$;
