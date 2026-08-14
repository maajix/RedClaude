-- ---------------------------------------------------------------------------
-- 20260814T080000Z__a_refutation_is_kept_and_made_due.sql          (ticket 34)
-- ---------------------------------------------------------------------------
--   A refutation is a result and 007 stored it as a status. `refuted` says a
--   claim failed and says nothing about what it failed under: which Test
--   settled it, which Observations stood behind it, what the Surface looked
--   like at the time. That is enough to stop asking the question and not enough
--   to ever start again, which is why 007 wrote `observed_fingerprint` on the
--   claim and left it with no reader.
--
--   This file keeps the whole of it, as rows, because the two things the
--   scheduler does with a refutation are both joins: suppress the Task that
--   would ask the same question again, and stop suppressing it the moment the
--   Surface it was settled against has moved in a way that bears on the claim.
--
--   Three decisions run through everything below.
--
--   The record is written where the claim moves, not where somebody remembers
--   to write it. A trigger on `hypothesis_transitions` settles the record for
--   every `-> refuted` transition and a trigger on `hypotheses` catches the row
--   that arrives already refuted, so "every refutation left a record" is a
--   property of the schema rather than a discipline of the callers.
--
--   `basis` separates a refutation whose settling is on file from one whose is
--   not. `settled` means a Test run of this claim's own Test produced the
--   Receipt the transition cites; `unverified` means nobody can point at what
--   settled it -- the whole corpus of refutations that existed before this file
--   did, and any claim inserted straight into `refuted`. The distinction is the
--   sixth criterion: an imported negative does not get to suppress anything on
--   the strength of a status somebody typed.
--
--   Relevance is a join and not a judgement. 022 wrote the mapping from a typed
--   delta to the Property classes it puts back in question, and this file adds
--   the other half of the same join: the delta's subject is the claim's subject,
--   something under the claim's subject, or one of the claim's Identity cells,
--   and the delta belongs to a fingerprint of the claim's own Application newer
--   than the one recorded when the claim was settled. Everything else leaves the
--   refutation exactly where it was.
--
--   What is deliberately not here: a refutation about a subject that belongs to
--   no Application -- an Identity, a Host -- records no Surface condition, and
--   nothing can make it due. It is settled and stays settled. The alternative is
--   to pick some Application for it, and a condition nobody can defend is worse
--   than an absent one. `v_negative_knowledge` says `application` is null, and
--   the check counts them.
-- ---------------------------------------------------------------------------


-- ---------------------------------------------------------------------------
-- 1. The two keys this file needs
-- ---------------------------------------------------------------------------
-- 017 rule 1: a citation between two program-scoped rows carries the Program.
-- Neither of these two tables had ever been cited before, so neither had the
-- composite key that lets one be.

ALTER TABLE hypothesis_transitions
    ADD CONSTRAINT hypothesis_transitions_id_program_key UNIQUE (id, program_id);

ALTER TABLE surface_deltas
    ADD CONSTRAINT surface_deltas_id_program_key UNIQUE (id, program_id);

-- And two cascades declared, both the same shape. 007 wrote the watched entity
-- `ON DELETE CASCADE` -- a watch on an entity that is gone watches nothing --
-- and 008 wrote a run's receipt citation the same way. 016 then stripped the
-- delete action from every key not named in `purge_cascade_edges`, which is its
-- rule (e) and the right rule: a cascade nobody declared is a row disappearing
-- for a reason nothing in the schema states. Neither of these two was declared,
-- because neither was reachable then.
--
-- Undeclared, they make a Program unpurgeable once it holds either row.
-- `DELETE FROM programs` reaches `entities` and `receipts` directly and reaches
-- these two children only through `hypotheses` and `test_runs`, so the
-- referential check of a child nothing has deleted yet runs against a parent
-- that is already gone and refuses the delete. 031 repairs the firing order
-- WITHIN one parent-child pair; this is across two parents, which no ordering
-- fixes. This ticket's fixture is the first thing in the corpus to write either
-- row, which is why neither has been seen.
--
-- So the edge is declared, in the table 016 says is where a cascade is declared,
-- and the cascade its own migration wrote comes back with it. MEASURED: five
-- more keys in the corpus have this shape and no fixture writes them yet
-- (finding_chain_step_citations twice, finding_effects, finding_evidence,
-- finding_hypotheses, hypothesis_evidence twice); they are recorded in the
-- ticket as a follow-up rather than repaired blind here.
ALTER TABLE hypothesis_retest_triggers
    DROP CONSTRAINT hypothesis_retest_triggers_watched_entity_id_fkey;

ALTER TABLE hypothesis_retest_triggers
    ADD CONSTRAINT hypothesis_retest_triggers_watched_entity_id_fkey
    FOREIGN KEY (watched_entity_id, program_id) REFERENCES entities(id, program_id)
    ON DELETE CASCADE;

ALTER TABLE test_run_receipts
    DROP CONSTRAINT test_run_receipts_receipt_id_fkey;

ALTER TABLE test_run_receipts
    ADD CONSTRAINT test_run_receipts_receipt_id_fkey
    FOREIGN KEY (receipt_id, program_id) REFERENCES receipts(id, program_id)
    ON DELETE CASCADE;

INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
    ('hypothesis_retest_triggers', 'watched_entity_id',
     'a watch dies with the entity it watches, as 007 wrote it'),
    ('test_run_receipts',          'receipt_id',
     'a run cites a receipt and the citation dies with it, as 008 wrote it');

-- The Surface a claim was settled against, once. Three readers wanted the same
-- four lines -- the writer in section 4, the watch comparison in section 6, and
-- 022's own `compute_surface_fingerprint`, which keeps its copy because it is
-- asking for the PREVIOUS row while holding the new one.
--
-- No `program_id` filter, and 017 is the reason it is not needed rather than an
-- oversight: `surface_fingerprints` cites its Application through the composite
-- key, so an Application Entity belongs to exactly one Program and naming it
-- names the Program with it.
CREATE FUNCTION rk2_current_fingerprint(p_application uuid)
RETURNS TABLE (id uuid, fingerprint text)
LANGUAGE sql STABLE AS $fn$
    SELECT sf.id, sf.fingerprint FROM surface_fingerprints sf
     WHERE sf.application_entity_id = p_application
     ORDER BY sf.computed_at DESC, sf.id DESC
     LIMIT 1
$fn$;

COMMENT ON FUNCTION rk2_current_fingerprint(uuid) IS
    'The newest Surface fingerprint of one Application, as the row and its '
    'value. Empty for an Application this Program has never fingerprinted.';

REVOKE ALL ON FUNCTION rk2_current_fingerprint(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION rk2_current_fingerprint(uuid) TO rk2_runtime;


-- ---------------------------------------------------------------------------
-- 2. Where a claim lives
-- ---------------------------------------------------------------------------
-- A refutation is settled against one Application's Surface, and which one is
-- a fact about the claim's subject rather than something the caller declares.
-- Both functions below are the projection's own containment read backwards, so
-- neither invents a second answer to "what is under what".

CREATE FUNCTION rk2_application_of(p_entity uuid) RETURNS uuid
LANGUAGE sql STABLE AS $fn$
    -- An Application is its own; a route belongs to one; a parameter belongs to
    -- its route's. Anything else -- an Identity, a Host, a Service -- returns
    -- null, which is the honest answer rather than a default.
    SELECT coalesce(
        (SELECT ap.entity_id FROM applications ap WHERE ap.entity_id = p_entity),
        (SELECT en.application_id FROM endpoints en WHERE en.entity_id = p_entity),
        (SELECT en.application_id
           FROM parameters pa
           JOIN endpoints en ON en.entity_id = pa.endpoint_id
          WHERE pa.entity_id = p_entity))
$fn$;

COMMENT ON FUNCTION rk2_application_of(uuid) IS
    'The Application one row belongs to, or null for a row that belongs to none.';

CREATE FUNCTION rk2_claim_scope(p_subject uuid) RETURNS TABLE (entity_id uuid)
LANGUAGE sql STABLE AS $fn$
    -- The subject's containment path, both ways.
    --
    -- Down, because a claim about a route is a claim about that route's inputs:
    -- a parameter that appeared on it is a change to the thing the claim is
    -- about, and a rule that compared subjects for equality would miss every
    -- one of them. `rk2_surface_reach` answers for an Application and returns
    -- the argument alone for anything else, so it is both the Application case
    -- and the identity case in one line.
    --
    -- Up, because the converse is equally true: a claim about a parameter was
    -- settled under the route that parameter sits on, and `endpoint_changed`
    -- says that route stopped being what it was. Without this arm a route whose
    -- authentication was removed leaves every ownership refutation about its own
    -- inputs standing, which is the one case where the Surface moved under the
    -- claim and nothing said so.
    --
    -- NOT the Application, and the omission is measured rather than timid: no
    -- delta kind has an Application for a subject. A `technology_changed` delta
    -- names the technology Entity, so 022's five technology classes reach no
    -- claim through this function at all. Making them reach one means teaching
    -- `rk2_application_of` about the `runs` relationship, which is 022's rule to
    -- change and not this file's; the ticket records it.
    SELECT r.entity_id FROM rk2_surface_reach(p_subject) r
 UNION
    SELECT pa.entity_id FROM parameters pa WHERE pa.endpoint_id = p_subject
 UNION
    SELECT pa.endpoint_id FROM parameters pa WHERE pa.entity_id = p_subject
$fn$;

COMMENT ON FUNCTION rk2_claim_scope(uuid) IS
    'One claim subject and the Surface rows its containment path reaches: an '
    'Application''s routes and parameters, a route''s parameters, a parameter''s '
    'route, or just the subject itself.';

REVOKE ALL ON FUNCTION rk2_application_of(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION rk2_claim_scope(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION rk2_application_of(uuid) TO rk2_runtime;
GRANT EXECUTE ON FUNCTION rk2_claim_scope(uuid) TO rk2_runtime;


-- ---------------------------------------------------------------------------
-- 3. The record a refutation leaves
-- ---------------------------------------------------------------------------
-- The conditions are copied rather than joined, and that is the point of the
-- table. `hypotheses` carries the claim as it is now; this row carries the
-- claim as it was when it failed, so a subject that is later superseded or a
-- Property class the vocabulary later drops cannot rewrite what was settled.

CREATE TABLE negative_knowledge (
    id                    uuid NOT NULL PRIMARY KEY DEFAULT uuidv7(),
    program_id            uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    hypothesis_id         uuid NOT NULL,
    -- The transition that settled it. Null for a claim that arrived already
    -- refuted, which is the one way into `refuted` that leaves no transition.
    transition_id         uuid,
    basis                 text NOT NULL CHECK (basis IN ('settled','unverified')),
    settled_at            timestamptz NOT NULL,
    -- The claim, as it read at settling.
    subject_entity_id     uuid NOT NULL,
    property_class        text NOT NULL,
    identity_a_entity_id  uuid,
    identity_b_entity_id  uuid,
    -- The Surface it was settled against. Null together: an Application this
    -- subject does not belong to has no fingerprint to record, and a Program
    -- that has never fingerprinted has none either.
    application_entity_id uuid,
    fingerprint_id        uuid,
    -- What settled it. Null together, and `basis` is the column that says so
    -- rather than a reader having to test four columns for null.
    test_id               uuid,
    test_run_id           uuid,
    spec_sha256           text,
    outcome               text,
    assertion_results     jsonb,
    -- Not part of that group: this is the Receipt the settling TRANSITION
    -- cited, which is on file whether or not a run of this claim's own Test is
    -- behind it. An `unverified` record carrying one is the honest shape --
    -- somebody cited an exchange, and no run of this claim produced it.
    receipt_id            uuid,
    reason                text NOT NULL,
    FOREIGN KEY (hypothesis_id, program_id)        REFERENCES hypotheses(id, program_id),
    FOREIGN KEY (transition_id, program_id)        REFERENCES hypothesis_transitions(id, program_id),
    FOREIGN KEY (subject_entity_id, program_id)    REFERENCES entities(id, program_id),
    FOREIGN KEY (identity_a_entity_id, program_id) REFERENCES identities(entity_id, program_id),
    FOREIGN KEY (identity_b_entity_id, program_id) REFERENCES identities(entity_id, program_id),
    FOREIGN KEY (application_entity_id, program_id) REFERENCES entities(id, program_id),
    FOREIGN KEY (fingerprint_id, program_id)       REFERENCES surface_fingerprints(id, program_id),
    FOREIGN KEY (test_id, program_id)              REFERENCES tests(id, program_id),
    FOREIGN KEY (test_run_id, program_id)          REFERENCES test_runs(id, program_id),
    FOREIGN KEY (receipt_id, program_id)           REFERENCES receipts(id, program_id),
    -- `settled` is exactly "a Test run of this claim settled it". Stated as a
    -- constraint because every rule below reads `basis` and none of them
    -- re-derives it, so a row whose basis disagrees with its own columns would
    -- suppress work on the strength of provenance it does not have.
    CHECK ((basis = 'settled') = (test_run_id IS NOT NULL)),
    CHECK ((test_run_id IS NULL) = (test_id IS NULL)),
    -- Everything read OFF the run is present exactly when the run is. One
    -- direction only: a run whose outcome the schema allows to be null is still
    -- a run, and what this refuses is the other shape -- a record with no
    -- settling run carrying a spec digest or an outcome from somewhere else.
    CHECK (test_run_id IS NOT NULL
           OR (spec_sha256 IS NULL AND outcome IS NULL AND assertion_results IS NULL)),
    CHECK ((application_entity_id IS NULL) = (fingerprint_id IS NULL)),
    -- One record per settling. A claim refuted, retested and refuted again is
    -- two records and two sets of conditions; NULLS NOT DISTINCT makes the
    -- transition-less import idempotent under the same key.
    UNIQUE NULLS NOT DISTINCT (hypothesis_id, transition_id),
    -- 017 rule 1, for the two tables below that cite this one.
    UNIQUE (id, program_id)
);

-- The one read anything does: the newest record of a claim. No index on
-- (subject, property class), because nothing asks that question -- 033 makes two
-- equivalent claims converge on ONE Hypothesis row, so "what do we know is not
-- true about this subject" is already answered by the claim's own record.
CREATE INDEX negative_knowledge_hypothesis_idx
    ON negative_knowledge (hypothesis_id, settled_at DESC, id DESC);

CREATE TRIGGER negative_knowledge_immutable
    BEFORE UPDATE OR DELETE ON negative_knowledge
    FOR EACH ROW EXECUTE FUNCTION reject_mutation_unless_purging();

COMMENT ON TABLE negative_knowledge IS
    'One refuted Hypothesis kept with the conditions it was refuted under: the '
    'claim as it read, the Surface fingerprint it was settled against, and the '
    'Test run that settled it. Never updated; a later refutation is a new row.';

-- The edges as they stood, which is not the same list as the edges now. An
-- Observation attached to the claim after it was refuted did not settle it, and
-- a reader asking "what refuted this" has to be able to tell the two apart.
CREATE TABLE negative_knowledge_evidence (
    negative_id    uuid NOT NULL,
    program_id     uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    observation_id uuid NOT NULL,
    polarity       text NOT NULL CHECK (polarity IN ('supports','refutes')),
    role           text NOT NULL CHECK (role IN ('baseline','variant','control','context')),
    PRIMARY KEY (negative_id, observation_id, role),
    FOREIGN KEY (negative_id, program_id)    REFERENCES negative_knowledge(id, program_id) ON DELETE CASCADE,
    FOREIGN KEY (observation_id, program_id) REFERENCES observations(id, program_id)
);

CREATE TRIGGER negative_knowledge_evidence_immutable
    BEFORE UPDATE OR DELETE ON negative_knowledge_evidence
    FOR EACH ROW EXECUTE FUNCTION reject_mutation_unless_purging();

COMMENT ON TABLE negative_knowledge_evidence IS
    'The evidence edges a refutation was settled on, as they stood at settling.';

-- Why a record stopped being current. One row is written per record and never
-- more: a record that has been made due is done making claims about the world,
-- and the retest that follows produces its own record with its own conditions.
CREATE TABLE negative_knowledge_retests (
    id            uuid NOT NULL PRIMARY KEY DEFAULT uuidv7(),
    program_id    uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    negative_id   uuid NOT NULL,
    reason        text NOT NULL CHECK (reason IN ('surface_delta','unverified','watch')),
    -- The delta that did it, for `surface_delta`, and nothing for the other
    -- two: an unverified record is due because of what it does not say, and a
    -- watch fired on a fingerprint rather than on a delta. Neither has a row to
    -- point at.
    delta_id      uuid,
    -- The re-entry this wrote. Null when the claim had already left `refuted`
    -- by some other road, which is a fact worth keeping rather than a failure.
    transition_id uuid,
    became_due_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (negative_id, program_id)   REFERENCES negative_knowledge(id, program_id) ON DELETE CASCADE,
    FOREIGN KEY (delta_id, program_id)      REFERENCES surface_deltas(id, program_id),
    FOREIGN KEY (transition_id, program_id) REFERENCES hypothesis_transitions(id, program_id),
    CHECK ((reason = 'surface_delta') = (delta_id IS NOT NULL)),
    -- One retest per record, in the key rather than in the writer. A key on
    -- (negative_id, reason, delta_id) would admit a record made due twice under
    -- two reasons, and every reader below -- the standing, the view's `retest`
    -- subquery -- is written as though a record has at most one.
    UNIQUE (negative_id)
);

CREATE TRIGGER negative_knowledge_retests_immutable
    BEFORE UPDATE OR DELETE ON negative_knowledge_retests
    FOR EACH ROW EXECUTE FUNCTION reject_mutation_unless_purging();

COMMENT ON TABLE negative_knowledge_retests IS
    'One row per recorded refutation that stopped being current, naming what '
    'made it due and the re-entry transition it produced.';

INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
    ('negative_knowledge',          'program_id',  'program-scoped: the purge root'),
    ('negative_knowledge_evidence', 'program_id',  'program-scoped: the purge root'),
    ('negative_knowledge_retests',  'program_id',  'program-scoped: the purge root'),
    ('negative_knowledge_evidence', 'negative_id',
     'ON DELETE CASCADE to negative_knowledge: the edges are the conditions of one record and describe nothing once it is gone'),
    ('negative_knowledge_retests',  'negative_id',
     'ON DELETE CASCADE to negative_knowledge: a retest says why one record stopped being current and says nothing without it');

-- `covered`, not `derived`, and the covering row is whichever one the trigger
-- fired off. ADR-0001: a covered row is written in the same transaction as an
-- emitting row that names it, and both writers here satisfy that with a
-- different row -- the transition, whose `hypothesis.transitioned` carries the
-- receipt and the rationale, or the Hypothesis itself, whose
-- `hypothesis.created` is the only Event a claim that arrived already refuted
-- produces. Naming only the first would be a reason that is true of the settled
-- path and false of the unverified one, which is the distinction this file
-- exists to make.
--
-- `negative_knowledge_retests` is not here, and that is the difference between
-- the two: nothing else in the log says a settled question was reopened, so it
-- gets an Event of its own -- written by a trigger off `event_table_config`,
-- which is section 6.
INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
    ('negative_knowledge', 'covered',
     'written with the transition that settled the claim, or with the claim itself when it arrived already refuted; hypothesis.transitioned and hypothesis.created are the emitting events', '34'),
    ('negative_knowledge_evidence', 'covered',
     'written with the negative_knowledge row it copies the edges for, in the same statement as the record its own covering event names', '34');

GRANT SELECT, INSERT, DELETE ON negative_knowledge          TO rk2_runtime;
GRANT SELECT, INSERT, DELETE ON negative_knowledge_evidence TO rk2_runtime;
GRANT SELECT, INSERT, DELETE ON negative_knowledge_retests  TO rk2_runtime;

-- No UPDATE for anybody, including the runtime. The immutability trigger
-- refuses one anyway; withholding the privilege means a statement that tried
-- is refused before it reaches a trigger that would have to explain itself.


-- ---------------------------------------------------------------------------
-- 4. Writing it
-- ---------------------------------------------------------------------------
-- One writer, reached from two triggers and from the import in section 9, so
-- "what a record contains" is answered once. The settling Test run is found
-- through the Receipt the transition cites: 007 requires one for
-- `testing -> refuted`, `test_run_receipts` is what ties a Receipt to the run
-- that produced it, and `tests.hypothesis_id` is what keeps another claim's run
-- from being read as this claim's settling.

CREATE FUNCTION record_negative_knowledge(p_hypothesis uuid, p_transition uuid DEFAULT NULL)
RETURNS uuid
LANGUAGE plpgsql AS $fn$
DECLARE
    h        hypotheses%ROWTYPE;
    tr       hypothesis_transitions%ROWTYPE;
    -- Scalars rather than a `record`: a record variable that no row was
    -- assigned to raises on field access, and "no settling run on file" is the
    -- ordinary case here rather than the exception.
    v_run    uuid;
    v_test   uuid;
    v_spec   text;
    v_out    text;
    v_assert jsonb;
    v_app    uuid;
    v_fp     uuid;
    v_id     uuid;
BEGIN
    SELECT * INTO h FROM hypotheses WHERE id = p_hypothesis;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'no hypothesis %', p_hypothesis USING ERRCODE = 'no_data_found';
    END IF;

    -- The transition given, or the newest one that reached `refuted`. The
    -- second form is what the import in section 9 uses: a claim refuted before
    -- this file existed still has its transition, and reading it is the
    -- difference between importing a settled refutation and importing a status.
    IF p_transition IS NOT NULL THEN
        SELECT * INTO tr FROM hypothesis_transitions WHERE id = p_transition;
    ELSE
        SELECT * INTO tr FROM hypothesis_transitions t
         WHERE t.hypothesis_id = p_hypothesis AND t.to_status = 'refuted'
         ORDER BY t.at DESC, t.id DESC LIMIT 1;
    END IF;

    SELECT tr_.id, tr_.outcome, tr_.assertion_results, te.id, te.spec_sha256
      INTO v_run, v_out, v_assert, v_test, v_spec
      FROM test_run_receipts trr
      JOIN test_runs tr_ ON tr_.id = trr.test_run_id
      JOIN tests te      ON te.id  = tr_.test_id
     WHERE trr.receipt_id = tr.receipt_id
       AND te.hypothesis_id = p_hypothesis
     ORDER BY tr_.started_at DESC, tr_.id DESC
     LIMIT 1;

    -- The Surface as it stood, for the Application this claim's subject belongs
    -- to. A subject that belongs to none records nothing, and so does a Program
    -- that has never fingerprinted: both are "no condition on file", and the
    -- relevance rule treats them the same way.
    v_app := rk2_application_of(h.subject_entity_id);
    IF v_app IS NOT NULL THEN
        SELECT f.id INTO v_fp FROM rk2_current_fingerprint(v_app) f;
        IF v_fp IS NULL THEN
            v_app := NULL;
        END IF;
    END IF;

    INSERT INTO negative_knowledge
        (program_id, hypothesis_id, transition_id, basis, settled_at,
         subject_entity_id, property_class, identity_a_entity_id, identity_b_entity_id,
         application_entity_id, fingerprint_id,
         test_id, test_run_id, receipt_id, spec_sha256, outcome, assertion_results, reason)
    VALUES (h.program_id, h.id, tr.id,
            CASE WHEN v_run IS NOT NULL THEN 'settled' ELSE 'unverified' END,
            coalesce(tr.at, h.status_changed_at),
            h.subject_entity_id, h.property_class,
            h.identity_a_entity_id, h.identity_b_entity_id,
            v_app, v_fp,
            v_test, v_run, tr.receipt_id, v_spec, v_out, v_assert,
            coalesce(nullif(tr.rationale, ''),
                     CASE WHEN tr.id IS NULL
                          THEN 'refuted with no transition to read'
                          ELSE 'refuted with no settling test run to read' END))
    ON CONFLICT DO NOTHING
    RETURNING id INTO v_id;

    IF v_id IS NULL THEN
        -- Already recorded. Idempotent by the key rather than by a prior
        -- lookup, so two settlings racing on one claim produce one record.
        SELECT n.id INTO v_id FROM negative_knowledge n
         WHERE n.hypothesis_id = p_hypothesis
           AND n.transition_id IS NOT DISTINCT FROM tr.id;
        RETURN v_id;
    END IF;

    INSERT INTO negative_knowledge_evidence
        (negative_id, program_id, observation_id, polarity, role)
    SELECT v_id, h.program_id, e.observation_id, e.polarity, e.role
      FROM hypothesis_evidence e
     WHERE e.hypothesis_id = p_hypothesis;

    RETURN v_id;
END $fn$;

COMMENT ON FUNCTION record_negative_knowledge(uuid, uuid) IS
    'Keep one refutation with its conditions and return the record. Idempotent '
    'per settling transition; the only writer of negative_knowledge.';

-- 017's idiom, which is the corpus's answer to a trigger function serving two
-- tables: the trigger names the columns and the function never asks which table
-- it is on. First argument is the column naming the claim; a second, where the
-- row IS the settling transition, names the column holding it.
CREATE FUNCTION settle_negative_knowledge() RETURNS trigger
LANGUAGE plpgsql AS $fn$
BEGIN
    PERFORM record_negative_knowledge(
        (to_jsonb(NEW) ->> TG_ARGV[0])::uuid,
        CASE WHEN TG_NARGS > 1 THEN (to_jsonb(NEW) ->> TG_ARGV[1])::uuid END);
    RETURN NULL;
END $fn$;

-- AFTER, so 007's own transition trigger has already moved the status cache and
-- the record is written against the claim as the transition left it.
CREATE TRIGGER hypothesis_transitions_settle_negative
    AFTER INSERT ON hypothesis_transitions
    FOR EACH ROW WHEN (NEW.to_status = 'refuted')
    EXECUTE FUNCTION settle_negative_knowledge('hypothesis_id', 'id');

-- The other door into `refuted`, and the reason `basis` exists: a row inserted
-- with the status already set has no transition, no Receipt and no Test run
-- behind it, so it is a refutation nobody can produce the settling for.
CREATE TRIGGER hypotheses_settle_negative
    AFTER INSERT ON hypotheses
    FOR EACH ROW WHEN (NEW.status = 'refuted')
    EXECUTE FUNCTION settle_negative_knowledge('id');

REVOKE ALL ON FUNCTION record_negative_knowledge(uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION record_negative_knowledge(uuid, uuid) TO rk2_runtime;


-- ---------------------------------------------------------------------------
-- 5. What makes a record stop being current
-- ---------------------------------------------------------------------------

CREATE FUNCTION rk2_current_negative(p_hypothesis uuid) RETURNS uuid
LANGUAGE sql STABLE AS $fn$
    SELECT n.id FROM negative_knowledge n
     WHERE n.hypothesis_id = p_hypothesis
     ORDER BY n.settled_at DESC, n.id DESC
     LIMIT 1
$fn$;

COMMENT ON FUNCTION rk2_current_negative(uuid) IS
    'The newest recorded refutation of one claim, or null if it has none.';

-- Four words for what a record is doing, and the vocabulary is closed. Every
-- reader below asks this rather than testing `basis` and the retest table
-- again, because "settled" is the answer that suppresses work and two
-- statements of it are two chances to disagree.
CREATE FUNCTION rk2_negative_standing(p_negative uuid) RETURNS text
LANGUAGE sql STABLE AS $fn$
    SELECT CASE
        WHEN n.id IS DISTINCT FROM rk2_current_negative(n.hypothesis_id) THEN 'superseded'
        WHEN EXISTS (SELECT 1 FROM negative_knowledge_retests r
                      WHERE r.negative_id = n.id)                        THEN 'due'
        WHEN n.basis = 'settled'                                         THEN 'settled'
        ELSE 'unverified' END
      FROM negative_knowledge n
     WHERE n.id = p_negative
$fn$;

COMMENT ON FUNCTION rk2_negative_standing(uuid) IS
    'What one recorded refutation is doing: settled (it suppresses equivalent '
    'work), due (something invalidated it), unverified (nothing on file settles '
    'it) or superseded (a later refutation of the same claim replaced it).';

-- The relevance rule, as one query. 022 owns the first half -- which Property
-- classes a typed delta puts back in question -- and this is the second: where
-- the delta has to have happened for it to bear on this claim.
--
-- The comparison is against the recorded fingerprint row, not against a clock.
-- `detected_at` is transaction time, and a fingerprint computed in a
-- transaction that started before the settling one and committed after it would
-- carry an earlier timestamp than the refutation it invalidates. Ordering by
-- (computed_at, id) is the ordering `compute_surface_fingerprint` already uses
-- to find an Application's previous row, so a delta counts exactly when it
-- belongs to a fingerprint that came after the recorded condition.
CREATE FUNCTION rk2_negative_relevant_deltas(p_negative uuid)
RETURNS TABLE (delta_id uuid, kind text, subject_key text, detected_at timestamptz)
LANGUAGE sql STABLE AS $fn$
    SELECT d.id, d.kind, d.subject_key, d.detected_at
      FROM negative_knowledge n
      JOIN surface_fingerprints was ON was.id = n.fingerprint_id
      JOIN surface_deltas d
        ON d.program_id = n.program_id
       AND d.application_entity_id = n.application_entity_id
      JOIN surface_fingerprints now_fp ON now_fp.id = d.fingerprint_id
      JOIN surface_delta_property_classes pc
        ON pc.kind = d.kind AND pc.property_class_id = n.property_class
     WHERE n.id = p_negative
       AND (now_fp.computed_at, now_fp.id) > (was.computed_at, was.id)
       -- A delta whose key names no single row names nothing this claim can be
       -- compared against; 022 records it so the disappearance is on file, and
       -- reading it as "the claim's subject" would be a guess.
       AND d.subject_entity_id IS NOT NULL
       AND (d.subject_entity_id IN (SELECT s.entity_id
                                      FROM rk2_claim_scope(n.subject_entity_id) s)
            OR d.subject_entity_id = n.identity_a_entity_id
            OR d.subject_entity_id = n.identity_b_entity_id)
     ORDER BY now_fp.computed_at, now_fp.id, d.subject_key
$fn$;

COMMENT ON FUNCTION rk2_negative_relevant_deltas(uuid) IS
    'Every recorded Surface delta that invalidates one refutation: the right '
    'Property class, the right subject, and a fingerprint newer than the '
    'condition the refutation was settled against.';

REVOKE ALL ON FUNCTION rk2_current_negative(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION rk2_negative_standing(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION rk2_negative_relevant_deltas(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION rk2_current_negative(uuid) TO rk2_runtime;
GRANT EXECUTE ON FUNCTION rk2_negative_standing(uuid) TO rk2_runtime;
GRANT EXECUTE ON FUNCTION rk2_negative_relevant_deltas(uuid) TO rk2_runtime;


-- ---------------------------------------------------------------------------
-- 6. Making it due
-- ---------------------------------------------------------------------------

-- A row event on the retest row, and a trigger writes it. 026 settled this
-- shape when `decision.requested` stopped being an occurrence: a table exists
-- now, so the Event hangs off the table, because "completeness that depends on
-- every call site remembering is the convention this schema rejects everywhere
-- else". The payload is the row -- reason, delta, the transition it produced --
-- which is the whole of what a reader asking "why was this reopened" wants, and
-- the status it was reopened FROM is on the transition the row names.
INSERT INTO event_types (id, family, subject_table, description) VALUES
    ('hypothesis.retest_due', 'row', 'negative_knowledge_retests',
     'a recorded refutation stopped being current and the claim re-entered (ticket 34)');

INSERT INTO event_table_config
    (table_name, created_type, updated_type, ignored_columns, redacted_columns)
VALUES ('negative_knowledge_retests', 'hypothesis.retest_due', NULL, '{}', '{}');

SELECT attach_event_triggers();

-- One retest row, written the same way from both loops below. The guard is
-- inside rather than at each call site: "a record stops being current once" is
-- the rule the unique key states, and a writer that returned a second row would
-- raise on it rather than declining.
CREATE FUNCTION note_retest_due(p_negative uuid, p_reason text,
                                p_delta uuid, p_transition uuid) RETURNS uuid
LANGUAGE sql AS $fn$
    INSERT INTO negative_knowledge_retests
        (program_id, negative_id, reason, delta_id, transition_id)
    SELECT n.program_id, n.id, p_reason, p_delta, p_transition
      FROM negative_knowledge n
     WHERE n.id = p_negative
       -- Not a repetition of the caller's guard. Step (1) of the pass filters
       -- and re-reads under the lock; the WATCH loop does neither, because it
       -- selects trigger rows and only afterwards asks which record the claim
       -- was standing on. A claim in `inconclusive` whose record step (1) made
       -- due in this same pass reaches this line with the row already written,
       -- and without the guard the unique key would raise and take the pass
       -- down. Returning null instead is what makes "already due" ordinary.
       AND NOT EXISTS (SELECT 1 FROM negative_knowledge_retests x
                        WHERE x.negative_id = n.id)
    RETURNING id
$fn$;

COMMENT ON FUNCTION note_retest_due(uuid, text, uuid, uuid) IS
    'Record that one kept refutation stopped being current, naming what made it '
    'due and the re-entry it produced. Returns null for a record already due.';

REVOKE ALL ON FUNCTION note_retest_due(uuid, text, uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION note_retest_due(uuid, text, uuid, uuid) TO rk2_runtime;

-- 007 called `retest_due` re-entry rather than a sixth state, and this is where
-- that sentence becomes code: the claim goes back to `testable` through the
-- transition table like everything else, and the reason it went is a row.
--
-- Idempotent in the way that matters: the record is the unit, one retest row
-- per record, and the unique key is what says so. Calling this twice, or
-- calling it after a restart that interrupted the last call, writes nothing the
-- first call already wrote and emits no second Event.
--
-- The first call after this file lands is the exception, and it is deliberate:
-- every refutation the corpus already held imports as `unverified` in section 9
-- and is reopened here, once, with a transition and an Event each. Criterion 6
-- asks for an import that is not "active suppression", and in this corpus a
-- claim sitting in `refuted` IS suppression whatever the record says --
-- `cancel_reason_for` abandons its Task as `answered` and `novelty_for` scores
-- it 0, both on the status alone. Teaching those two to consult a standing
-- would make a claim that is refuted and open at the same time; reopening it
-- says the same thing in the vocabulary 007 already has. It happens once per
-- record, it is on the log, and the alternative is a refutation nobody can
-- produce the evidence for holding work down forever.
CREATE FUNCTION refresh_negative_knowledge() RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p             uuid := rk2_program_required();
    r             record;
    v_status      text;
    v_retest      uuid;
    v_transition  uuid;
    v_negative    uuid;
    v_reasons     text[] := '{}';
    n_due         bigint := 0;
    n_reopened    bigint := 0;
    n_watch       bigint := 0;
    n_unwatchable bigint := 0;
    by_reason     jsonb  := '{}'::jsonb;
BEGIN
    -- (1) The records. A record is due when nothing on file settles it, or when
    -- a delta this Program recorded invalidates the conditions it was settled
    -- under. Only the current record of a claim is asked, and only one that
    -- nothing has queued a retest for already.
    FOR r IN
        SELECT n.id AS negative_id, n.hypothesis_id,
               CASE WHEN n.basis = 'unverified' THEN 'unverified'
                    ELSE 'surface_delta' END AS reason,
               CASE WHEN n.basis = 'unverified' THEN NULL
                    ELSE d.delta_id END AS delta_id,
               d.kind, d.subject_key
          FROM negative_knowledge n
          LEFT JOIN LATERAL (
              SELECT * FROM rk2_negative_relevant_deltas(n.id) LIMIT 1) d ON true
         WHERE n.program_id = p
           AND n.id = rk2_current_negative(n.hypothesis_id)
           AND NOT EXISTS (SELECT 1 FROM negative_knowledge_retests x
                            WHERE x.negative_id = n.id)
           AND (n.basis = 'unverified' OR d.delta_id IS NOT NULL)
         ORDER BY n.settled_at, n.id
    LOOP
        -- The claim's row is the lock, taken before anything is written, so two
        -- passes reaching the same claim do not both write a transition -- the
        -- second would fail 007's stale check and take the whole pass with it.
        -- Re-read under it: in READ COMMITTED this statement sees what the
        -- other transaction committed while this one waited.
        SELECT h.status INTO v_status FROM hypotheses h
         WHERE h.id = r.hypothesis_id FOR UPDATE;
        CONTINUE WHEN EXISTS (SELECT 1 FROM negative_knowledge_retests x
                               WHERE x.negative_id = r.negative_id);

        v_transition := NULL;
        IF v_status = 'refuted' THEN
            INSERT INTO hypothesis_transitions
                (program_id, hypothesis_id, from_status, to_status, actor_kind, rationale)
            VALUES (p, r.hypothesis_id, 'refuted', 'testable', 'runtime',
                    CASE WHEN r.reason = 'unverified'
                         THEN 'retest due: nothing on file settles this refutation'
                         ELSE 'retest due: ' || r.kind || ' on ' || r.subject_key END)
            RETURNING id INTO v_transition;
            n_reopened := n_reopened + 1;
        END IF;

        -- The transition first, because the retest row names it and is
        -- immutable once written. The guard above is what makes this ordering
        -- safe rather than the writer's own key, which is why it is a re-read
        -- under the lock and not a repetition of it.
        v_retest := note_retest_due(r.negative_id, r.reason, r.delta_id, v_transition);
        IF v_retest IS NOT NULL THEN
            v_reasons := v_reasons || r.reason;
        END IF;
    END LOOP;

    -- (2) 007's watch rows, which are the other two statuses. 023 compared them
    -- against the Program's newest fingerprint, and 022 pointed out that a
    -- Program with two Applications has two rows racing to be it: the watch
    -- would fire on a change to an Application it is not watching, and then not
    -- fire on the one it is. The comparison is per watched Application now, and
    -- a watch naming no Application is not compared at all -- there is no
    -- honest "newest" for it, and the racing one was never it.
    FOR r IN
        SELECT x.id AS trigger_id, x.hypothesis_id, x.kind, cur.fingerprint
          FROM hypothesis_retest_triggers x
          JOIN hypotheses h ON h.id = x.hypothesis_id
          CROSS JOIN LATERAL (SELECT rk2_application_of(x.watched_entity_id) AS app) w
          LEFT JOIN LATERAL rk2_current_fingerprint(w.app) cur ON true
         WHERE h.program_id = p
           AND h.status IN ('refuted','inconclusive','supported')
           AND x.fired_at IS NULL
           AND cur.fingerprint IS NOT NULL
           AND x.fingerprint IS DISTINCT FROM cur.fingerprint
         ORDER BY x.id
    LOOP
        SELECT h.status INTO v_status FROM hypotheses h
         WHERE h.id = r.hypothesis_id FOR UPDATE;
        -- Step (1) may have reopened this claim while this loop was deciding.
        -- Firing the watch anyway would stamp `fired_at` on a claim already
        -- being retested and spend the one shot the watch has.
        CONTINUE WHEN v_status NOT IN ('refuted','inconclusive','supported');

        UPDATE hypothesis_retest_triggers
           SET fired_at = now(), fingerprint = r.fingerprint
         WHERE id = r.trigger_id AND fired_at IS NULL;
        CONTINUE WHEN NOT FOUND;
        n_watch := n_watch + 1;

        INSERT INTO hypothesis_transitions
            (program_id, hypothesis_id, from_status, to_status, actor_kind, rationale)
        VALUES (p, r.hypothesis_id, v_status, 'testable', 'runtime',
                'retest trigger fired')
        RETURNING id INTO v_transition;
        n_reopened := n_reopened + 1;

        -- The record this watch was standing on, if there is one. The watch
        -- predates the record and fires for two statuses that never produce one,
        -- so "no record" is ordinary here rather than a fault -- but where there
        -- is one, it has stopped being current, and a reader asking why has to
        -- find the answer in the same table it finds every other answer in.
        v_negative := rk2_current_negative(r.hypothesis_id);
        IF v_negative IS NOT NULL THEN
            v_retest := note_retest_due(v_negative, 'watch', NULL, v_transition);
            IF v_retest IS NOT NULL THEN
                -- Cast, or the untyped literal makes this `array || array` and
                -- Postgres tries to read `watch` as an array literal.
                v_reasons := v_reasons || 'watch'::text;
            END IF;
        END IF;
    END LOOP;

    SELECT count(*) INTO n_unwatchable
      FROM hypothesis_retest_triggers x
      JOIN hypotheses h ON h.id = x.hypothesis_id
     WHERE h.program_id = p AND x.fired_at IS NULL
       AND rk2_application_of(x.watched_entity_id) IS NULL;

    -- The tally, once, from what was actually written. Counting in the loops
    -- meant the same two lines in both of them and two places for the total to
    -- disagree with the rows.
    SELECT coalesce(sum(x.n), 0), coalesce(jsonb_object_agg(x.reason, x.n), '{}'::jsonb)
      INTO n_due, by_reason
      FROM (SELECT u AS reason, count(*) AS n
              FROM unnest(v_reasons) u GROUP BY u) x;

    RETURN jsonb_build_object(
        'due', n_due,
        'by_reason', by_reason,
        'reopened', n_reopened,
        'watches_fired', n_watch,
        'watches_unwatchable', n_unwatchable);
END $fn$;

COMMENT ON FUNCTION refresh_negative_knowledge() IS
    'Make every recorded refutation due whose conditions no longer hold, and '
    'fire 007''s watch rows against the Application each one watches. One '
    'retest row and one Event per record; calling it again writes nothing.';

REVOKE ALL ON FUNCTION refresh_negative_knowledge() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION refresh_negative_knowledge() TO rk2_runtime;


-- ---------------------------------------------------------------------------
-- 7. Suppression, and the pass that calls it
-- ---------------------------------------------------------------------------
-- `answered` conflated two different things: a claim the runtime settled and a
-- claim whose Task has nothing left to learn. A refuted claim gets its own
-- reason, because the operator reading a Task's end wants to know whether the
-- question was answered or is merely being held down by a record that could
-- stop being current tomorrow.

ALTER TABLE tasks DROP CONSTRAINT tasks_abandoned_reason_check;
ALTER TABLE tasks ADD CONSTRAINT tasks_abandoned_reason_check
    CHECK (abandoned_reason IN (
        'out_of_scope','superseded','answered','attempts_exhausted',
        'program_closed','budget_exhausted','near_duplicate',
        'decision_timeout','decision_denied','settled_negative'));

CREATE OR REPLACE FUNCTION cancel_reason_for(t tasks, w scheduler_weights) RETURNS text
LANGUAGE plpgsql STABLE AS $fn$
DECLARE ok boolean; st text; fired boolean; left_ bigint;
BEGIN
    IF EXISTS (SELECT 1 FROM programs p
                WHERE p.id = t.program_id AND p.closed_at IS NOT NULL) THEN
        RETURN 'program_closed';
    END IF;

    SELECT b.tokens_left INTO left_ FROM program_budget b WHERE b.program_id = t.program_id;
    IF left_ IS NOT NULL AND left_ <= 0 THEN RETURN 'budget_exhausted'; END IF;

    IF t.attempts >= w.max_attempts THEN RETURN 'attempts_exhausted'; END IF;

    IF t.subject_entity_id IS NOT NULL THEN
        SELECT e.in_scope INTO ok FROM entities e WHERE e.id = t.subject_entity_id;
        IF NOT coalesce(ok, false) THEN RETURN 'out_of_scope'; END IF;
    END IF;

    IF t.hypothesis_id IS NOT NULL THEN
        SELECT h.status, h.superseded_by IS NOT NULL INTO st, ok
          FROM hypotheses h WHERE h.id = t.hypothesis_id;
        IF ok THEN RETURN 'superseded'; END IF;
        -- 034: a refutation suppresses equivalent work only while it is still
        -- current AND something on file settles it. An imported negative is
        -- neither, and `refresh_negative_knowledge` reopens the claim in step
        -- (1) of the same pass that reaches this check in step (2), so the
        -- suppression it would otherwise inherit never survives a pass.
        IF st = 'refuted'
           AND rk2_negative_standing(rk2_current_negative(t.hypothesis_id)) = 'settled' THEN
            RETURN 'settled_negative';
        END IF;
        SELECT EXISTS (SELECT 1 FROM hypothesis_retest_triggers x
                        WHERE x.hypothesis_id = t.hypothesis_id
                          AND x.fired_at IS NOT NULL) INTO fired;
        IF st IN ('supported','refuted') AND NOT fired THEN RETURN 'answered'; END IF;
        -- a candidate that stage 2 suppressed leaves the hypothesis gone
        IF st IS NULL THEN RETURN 'near_duplicate'; END IF;
    END IF;

    IF t.kind = 'validate' AND EXISTS (
         SELECT 1 FROM findings f WHERE f.id = t.finding_id
           AND f.status IN ('validated','reported','rejected')) THEN
        RETURN 'answered';
    END IF;

    -- The general rule, last: nothing left to learn is nothing worth running.
    --
    -- Except for `report`, and the exception is not a special case -- it is the
    -- one kind whose novelty is a function of rows that have not arrived yet.
    -- `novelty_for('report')` is 1 exactly when an unreported validated finding
    -- exists, so a report task in a young program scores 0, and without this
    -- guard `rank_pass` would abandon it as `answered` on the first pass and
    -- the program would validate findings with no report task left alive. The
    -- admission matrix found this: the fixture happened to validate FG20 before
    -- the first pass, which hid it. Nothing to report yet is unready, not
    -- answered, and `ready_for` already says so.
    IF t.kind <> 'report' AND novelty_for(t) = 0 THEN RETURN 'answered'; END IF;
    RETURN NULL;
END $fn$;

CREATE OR REPLACE FUNCTION rank_pass(p_trigger text DEFAULT 'timer') RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p            uuid := rk2_program_required();
    w            scheduler_weights%ROWTYPE;
    n_cancelled  bigint := 0;
    n_ranked     bigint := 0;
    n_fired      bigint := 0;
    v_retests    jsonb;
    edges        jsonb;
    by_reason    jsonb;
    top          jsonb;
    t0           timestamptz := clock_timestamp();
BEGIN
    SELECT * INTO w FROM scheduler_weights WHERE active;
    IF NOT FOUND THEN RAISE EXCEPTION 'no active scheduler_weights row'; END IF;

    -- (1) Retest re-entry. Decision 11: the pass owns it, because it is the
    -- only runtime step that reads the whole program. 034 moved the body out
    -- into `refresh_negative_knowledge`, which is where the kept refutations
    -- are and where 022's per-Application fingerprint comparison had to go; the
    -- pass keeps the decision about WHEN, which is what decision 11 was about.
    --
    -- It stays first, and that ordering is load-bearing twice over. A claim
    -- whose refutation stopped being current has to be out of `refuted` before
    -- step (2) reads its status, or the Task asking the question again is
    -- abandoned in the same pass that reopened it. And an imported refutation
    -- -- one nothing on file settles -- is reopened here before step (2) could
    -- ever read it as suppression.
    v_retests := refresh_negative_knowledge();
    n_fired   := (v_retests ->> 'reopened')::bigint;

    -- (2) Cancellation, before ranking: a task that should not run must not be
    -- ranked into a slate this pass.
    WITH c AS (
        SELECT t.id, cancel_reason_for(t, w) AS reason
          FROM tasks t WHERE t.program_id = p AND t.status = 'pending'
    ), u AS (
        UPDATE tasks t SET status = 'abandoned', abandoned_reason = c.reason,
                           finished_at = now(), priority = NULL
          FROM c WHERE t.id = c.id AND c.reason IS NOT NULL
        RETURNING t.abandoned_reason AS reason
    )
    SELECT count(*), coalesce(jsonb_object_agg(reason, n), '{}'::jsonb)
      INTO n_cancelled, by_reason
      FROM (SELECT reason, count(*) AS n FROM u GROUP BY reason) g;

    -- (3) Dependency edges, after cancellation and before ranking, for the
    -- same reason in both directions: a Task abandoned above must stop
    -- unlocking anything, and an edge derived below must be visible to the
    -- ranking in this pass rather than the next one.
    edges := derive_task_dependencies();

    -- (4) The ranking. One statement, seven components, no clock in it.
    WITH r AS (
        SELECT t.id,
               novelty_for(t)         AS novelty,
               cost_for(t, w)         AS estimated_cost,
               time_for(t, w)         AS estimated_time,
               safety_for(t, w)       AS safety_cost,
               confidence_for(t, w)   AS confidence,
               value_for(t, w)        AS direct_value,
               unlock_for(t, w)       AS unlock_value
          FROM tasks t
         WHERE t.program_id = p AND t.status = 'pending'
    ), u AS (
        UPDATE tasks t
           SET novelty = r.novelty,
               estimated_cost = r.estimated_cost,
               estimated_time = r.estimated_time,
               safety_cost = r.safety_cost,
               confidence_of_execution = r.confidence,
               direct_value = r.direct_value,
               unlock_value = r.unlock_value,
               ranked_weights_version = w.version,
               -- NULL, not 0: an unestimated task must sink via NULLS LAST, and
               -- a task scored 0 is a different statement from one never scored
               priority = CASE
                   WHEN r.direct_value IS NULL THEN NULL
                   ELSE r.novelty * r.confidence
                        * (r.direct_value + w.w_unlock * r.unlock_value)
                        / greatest(w.w_tokens * r.estimated_cost
                                 + w.w_time   * r.estimated_time
                                 + w.w_safety * r.safety_cost, w.cost_floor)
               END
          FROM r WHERE t.id = r.id
        RETURNING t.id
    )
    SELECT count(*) INTO n_ranked FROM u;

    SELECT coalesce(jsonb_agg(j ORDER BY ord), '[]'::jsonb) INTO top
      FROM (
        SELECT row_number() OVER (ORDER BY t.priority DESC NULLS LAST,
                                           t.created_at, t.id) AS ord,
               jsonb_build_object(
                 'task', t.label, 'kind', t.kind,
                 'priority', round(t.priority, 6),
                 'factors', task_rank_factors(t)) AS j
          FROM tasks t WHERE t.program_id = p AND t.status = 'pending'
          ORDER BY t.priority DESC NULLS LAST, t.created_at, t.id
          LIMIT 10) s;

    INSERT INTO events (program_id, type, actor_kind, payload)
    VALUES (p, 'scheduler.ranked', 'runtime', jsonb_build_object(
        'trigger', p_trigger,
        'weights_version', w.version,
        'candidates', n_ranked,
        'retests', v_retests,
        'abandoned_by_reason', by_reason,
        'dependency_edges', edges,
        'lane_slots', (SELECT coalesce(jsonb_object_agg(kind, live_slots), '{}'::jsonb)
                         FROM scheduler_lane_state WHERE program_id = p),
        'top', top,
        'further_omitted', greatest(n_ranked - 10, 0),
        'duration_ms', round(extract(epoch FROM clock_timestamp() - t0) * 1000)));

    RETURN jsonb_build_object('ranked', n_ranked, 'abandoned', n_cancelled,
                              -- `retests_fired` is 023's key and stays what it
                              -- was: how many claims re-entered. `retests` is
                              -- the breakdown behind it, so a caller can tell a
                              -- pass that reopened nothing because nothing moved
                              -- from one that reopened nothing because it found
                              -- nothing to reopen.
                              'retests_fired', n_fired,
                              'retests', v_retests,
                              'edges_derived', edges -> 'derived',
                              'edges_withdrawn', edges -> 'withdrawn');
END $fn$;


-- ---------------------------------------------------------------------------
-- 8. What a reader is told
-- ---------------------------------------------------------------------------
-- The operator's read, with the conditions spelled out. No identifier columns,
-- which is 020's rule 5: a fingerprint is named by its own value because that
-- is what a fingerprint is, and everything else is named by its label.

CREATE VIEW v_negative_knowledge WITH (security_invoker = true) AS
SELECT hy.label                        AS hypothesis,
       hy.status                       AS hypothesis_status,
       rk2_negative_standing(n.id)     AS standing,
       n.basis,
       subj.label                      AS subject,
       n.property_class,
       ia.label                        AS identity_a,
       ib.label                        AS identity_b,
       app.label                       AS application,
       fp.fingerprint                  AS surface_fingerprint,
       te.label                        AS test,
       n.spec_sha256,
       n.outcome                       AS test_outcome,
       n.reason,
       n.settled_at,
       (SELECT coalesce(jsonb_agg(jsonb_build_object(
                            'observation', o.label,
                            'polarity', ev.polarity,
                            'role', ev.role) ORDER BY o.label, ev.role), '[]'::jsonb)
          FROM negative_knowledge_evidence ev
          JOIN observations o ON o.id = ev.observation_id
         WHERE ev.negative_id = n.id)  AS evidence,
       (SELECT jsonb_build_object(
                   'reason', rt.reason,
                   'delta_kind', d.kind,
                   'subject_key', d.subject_key,
                   'reopened', rt.transition_id IS NOT NULL,
                   'became_due_at', rk2_instant(rt.became_due_at))
          FROM negative_knowledge_retests rt
          LEFT JOIN surface_deltas d ON d.id = rt.delta_id
         WHERE rt.negative_id = n.id)  AS retest
  FROM negative_knowledge n
  JOIN hypotheses hy      ON hy.id = n.hypothesis_id
  JOIN entities subj      ON subj.id = n.subject_entity_id
  LEFT JOIN entities ia   ON ia.id = n.identity_a_entity_id
  LEFT JOIN entities ib   ON ib.id = n.identity_b_entity_id
  LEFT JOIN entities app  ON app.id = n.application_entity_id
  LEFT JOIN surface_fingerprints fp ON fp.id = n.fingerprint_id
  LEFT JOIN tests te      ON te.id = n.test_id;

COMMENT ON VIEW v_negative_knowledge IS
    'Every kept refutation with the conditions it was settled under, what it is '
    'currently doing, and what made it due if anything has.';

GRANT SELECT ON v_negative_knowledge TO rk2_runtime;

-- What a hunter is told, which is deliberately less. 020 kept Surface
-- fingerprints away from the model -- an agent that can read what the runtime
-- watches for change can aim at it -- and that decision survives here: the
-- record says a claim was refuted, when, why, and whether anything still
-- settles it. Not which fingerprint, not which delta, not which Application's
-- Surface is being compared.
CREATE FUNCTION rk2_hypothesis_negative(p_hypothesis uuid) RETURNS jsonb
LANGUAGE sql STABLE AS $fn$
    SELECT jsonb_build_object(
               'standing', rk2_negative_standing(n.id),
               'settled_at', rk2_instant(n.settled_at),
               'reason', n.reason)
      FROM negative_knowledge n
     WHERE n.id = rk2_current_negative(p_hypothesis)
$fn$;

COMMENT ON FUNCTION rk2_hypothesis_negative(uuid) IS
    'The Negative knowledge one claim carries, as a hunter may read it: what it '
    'is doing, when it was settled and the reason recorded. Null when the claim '
    'has never been refuted.';

REVOKE ALL ON FUNCTION rk2_hypothesis_negative(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION rk2_hypothesis_negative(uuid) TO rk2_runtime;

-- `v_records` is security invoker, so the model's own role executes these three
-- and reads the columns they touch. 030's rule: the readable surface is the
-- contents of `state_read_surface`, and publishing a column is a row in a diff.
GRANT EXECUTE ON FUNCTION rk2_hypothesis_negative(uuid) TO rk2_state;
GRANT EXECUTE ON FUNCTION rk2_current_negative(uuid)    TO rk2_state;
GRANT EXECUTE ON FUNCTION rk2_negative_standing(uuid)   TO rk2_state;

INSERT INTO state_read_surface (table_name, column_name, added_by) VALUES
    ('negative_knowledge', 'id',            '34'),
    ('negative_knowledge', 'program_id',    '34'),
    ('negative_knowledge', 'hypothesis_id', '34'),
    ('negative_knowledge', 'basis',         '34'),
    ('negative_knowledge', 'settled_at',    '34'),
    ('negative_knowledge', 'reason',        '34'),
    ('negative_knowledge_retests', 'negative_id', '34'),
    ('negative_knowledge_retests', 'program_id',  '34'),
    -- Published for the revision below and for nothing else. `v_records` is
    -- security invoker, so the model's own role runs `rk2_revision` over this
    -- row, and 030's registry is the only place a column it may touch is
    -- named. The value never leaves the view -- what comes out is the
    -- revision -- and the row's existence is already readable through
    -- `rk2_negative_standing` answering `due`.
    ('negative_knowledge_retests', 'id',          '34');

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
-- 9. What came before this file
-- ---------------------------------------------------------------------------
-- Every refutation already in the corpus, imported through the same writer the
-- triggers use. A claim refuted through a transition that cites a Test run's
-- Receipt imports as `settled` -- the provenance was always there, nothing had
-- read it. Everything else imports as `unverified`, which is criterion 6: the
-- import does not get to suppress work on the strength of a status.
--
-- No Surface condition is recorded for an import unless the Program has a
-- fingerprint for the subject's Application, and the ones that do get the
-- current fingerprint rather than a reconstruction: what the Surface looked
-- like when the claim was refuted is not knowable after the fact, and recording
-- today's row is the honest floor -- it makes the claim due on the next change,
-- not on a change that already happened.

DO $$
DECLARE h uuid; n integer := 0;
BEGIN
    FOR h IN SELECT id FROM hypotheses WHERE status = 'refuted' ORDER BY id
    LOOP
        PERFORM record_negative_knowledge(h, NULL);
        n := n + 1;
    END LOOP;
    RAISE NOTICE 'ph2-34: imported % refutation(s)', n;
END $$;


-- ---------------------------------------------------------------------------
-- 10. The standing check
-- ---------------------------------------------------------------------------
-- Four arms for what this file can get wrong and two for the structures whose
-- drift would make the first four read clean while meaning nothing.

CREATE FUNCTION check_negative_knowledge()
RETURNS TABLE (problem text, subject text, detail text)
LANGUAGE sql STABLE AS $fn$
    -- The triggers are the only writers and they cover both doors into
    -- `refuted`. A claim without a record got there some third way.
    SELECT 'refuted_without_record', hy.label,
           'a refuted claim with no kept refutation'
      FROM hypotheses hy
     WHERE hy.status = 'refuted'
       AND NOT EXISTS (SELECT 1 FROM negative_knowledge n
                        WHERE n.hypothesis_id = hy.id)

  UNION ALL
    -- `settled` is a claim about provenance, and the provenance has to be this
    -- claim's. A record naming another claim's Test would suppress work on the
    -- strength of an experiment that was never about it.
    SELECT 'settling_test_is_another_claims', hy.label,
           'the recorded settling Test belongs to a different Hypothesis'
      FROM negative_knowledge n
      JOIN hypotheses hy ON hy.id = n.hypothesis_id
      JOIN tests te      ON te.id = n.test_id
     WHERE te.hypothesis_id <> n.hypothesis_id

  UNION ALL
    -- A retest row is the claim re-entering. One that left the claim sitting in
    -- `refuted` reopened nothing, and the record it belongs to no longer
    -- suppresses anything either, so the question is neither asked nor closed.
    --
    -- Only the current record, and the restriction is the ordinary case rather
    -- than a corner: a claim reopened and refuted again is `refuted` today and
    -- its OLDER record's retest row is exactly the row that reopened it. Asking
    -- this of every record would report the successful path as the failure.
    SELECT 'due_claim_never_reopened', hy.label,
           'a retest was recorded and the claim is still refuted'
      FROM negative_knowledge_retests rt
      JOIN negative_knowledge n ON n.id = rt.negative_id
      JOIN hypotheses hy        ON hy.id = n.hypothesis_id
     WHERE hy.status = 'refuted'
       AND n.id = rk2_current_negative(n.hypothesis_id)

  UNION ALL
    -- The rule as a row: every `surface_delta` retest has to be one this file's
    -- own relevance query still agrees with. A mapping edited by hand, or a
    -- retest written by something other than `refresh_negative_knowledge`,
    -- shows up here rather than as a claim quietly retested for no reason.
    SELECT 'retest_names_an_unrelated_delta', hy.label,
           'the delta that made this refutation due does not bear on the claim'
      FROM negative_knowledge_retests rt
      JOIN negative_knowledge n ON n.id = rt.negative_id
      JOIN hypotheses hy        ON hy.id = n.hypothesis_id
     WHERE rt.reason = 'surface_delta'
       AND NOT EXISTS (SELECT 1 FROM rk2_negative_relevant_deltas(n.id) d
                        WHERE d.delta_id = rt.delta_id)

  UNION ALL
    -- The way back. 007 seeded `refuted -> testable` for the runtime, and
    -- without it every kept refutation is permanent however many deltas arrive:
    -- the retest row would be written and the transition would raise.
    SELECT 'no_way_back_from_refuted', 'hypothesis.refuted.testable',
           'transition_rules has no runtime rule from refuted to testable'
     WHERE NOT EXISTS (
        SELECT 1 FROM transition_rules
         WHERE machine = 'hypothesis' AND from_status = 'refuted'
           AND to_status = 'testable' AND required_actor_kind = 'runtime')

  UNION ALL
    -- 022's half of the relevance join. An empty mapping makes every delta
    -- irrelevant to every claim, which reads exactly like a Surface that never
    -- moved.
    SELECT 'delta_class_mapping_empty', 'surface_delta_property_classes',
           'no typed delta puts any Property class back in question'
     WHERE NOT EXISTS (SELECT 1 FROM surface_delta_property_classes)
$fn$;

REVOKE ALL ON FUNCTION check_negative_knowledge() FROM PUBLIC;

COMMENT ON FUNCTION check_negative_knowledge() IS
    'What keeping a refutation can get wrong, as rows, plus the two structures '
    'that keep the first four of them empty by construction.';

INSERT INTO standing_checks(name, query, owner_ticket, note) VALUES
    ('negative_knowledge', 'SELECT * FROM check_negative_knowledge()', '34',
     'every refuted claim is kept with the conditions it was refuted under, every retest names a delta that bears on the claim, and the way back from refuted is still open');


-- ---------------------------------------------------------------------------
-- 11. The invariants this file must not have broken
-- ---------------------------------------------------------------------------

SELECT enforce_always_triggers();
-- 031's finalizer, and this file is exactly the case it exists for: section 1
-- added two cascades and three tables' worth of keys, and a cascade that fires
-- after the NO ACTION key it has to beat is a purge that raises.
SELECT enforce_fk_fire_order();
SELECT apply_state_rls();
SELECT apply_state_grants();

DO $$
DECLARE n integer; d text;
BEGIN
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_program_isolation();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-34 breaks program isolation (% problems): %', n, d;
    END IF;

    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_event_coverage();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-34 breaks event coverage (% problems): %', n, d;
    END IF;

    SELECT count(*), string_agg(problem || ': ' || subject, '; ')
      INTO n, d FROM check_negative_knowledge();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-34 refuses to finish: % violation(s): %', n, d;
    END IF;
END $$;
