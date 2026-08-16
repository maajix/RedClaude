-- ---------------------------------------------------------------------------
-- 20260824T000000Z__a_playbook_earns_stable_against_fixtures_it_did_not_pick.sql
--                                                                   (ticket 46)
--
-- 036 built the shape of a Playbook test and left the catalogue empty. Every
-- table it created has zero rows in this corpus, so every clause of its verdict
-- has been unreachable since it applied: no fixture means no binding, no
-- binding means `untested`, and `untested` has been the answer for every
-- Playbook in the tree. This migration is what puts a target behind it, and
-- what closes the five places where the shape is not yet the rule ticket 46
-- asks for.
--
-- WHAT 036 ALREADY HAS, and is not re-litigated here:
--
--   * the total derived binding -- every fixture on one side or the other, from
--     `playbook_outputs x fixture_classes`, so no author picks their graders;
--   * R1-R4 on a run row: the side is computed, the text must be current, an
--     out-side discriminating finding is a contradiction, and a target with no
--     secure twin gets NULL rather than 0;
--   * the three categorical clauses -- ungrounded, admits-on-secure, fires-on-
--     the-out-side -- evaluated before any coverage clause;
--   * `untested` as a third outcome that blocks promotion and does not demote.
--
-- WHAT TICKET 46 ADDS, criterion by criterion:
--
--   1. fixtures independent of the Playbook author. The binding was already
--      derived; what was missing is the corpus. A goes and gets it, and
--      `fixture.py` refuses `bb:playbooks`/`bb:tests` on the way in, the same
--      way `playbook.py` refuses `bb:tested_against`.
--   2. a repeat records what it was. B adds the ground-truth digest, the false
--      positive count and the Skill texts the run loaded, and D computes every
--      count from the rows the run produced rather than accepting them.
--   3. the configured repeat, and runtime provenance for THIS text. E puts the
--      repeat minimum in a table, and C stops a Playbook from being promoted by
--      the evaluation that graded it.
--   4. under-declaring, always firing, no control, own-fixture credit. Three of
--      those 036 has; C is the fourth and it is the one 035 admitted.
--   5. edit, expiry and a later failing verdict demote. F, and 036's decision
--      to leave expiry alone is reversed there with the reason.
--   6. the end-to-end evaluator is `evaluation.py`, not SQL. C's marker is the
--      seam it writes through.
--
-- A: the catalogue gets the corpus behind it
-- B: a repeat records the instrument as well as the result
-- C: an evaluation Program cannot promote the Playbook it evaluates
-- D: the counts are computed, never supplied
-- E: how many repeats, stated once
-- F: demotion on a failing verdict, on expiry, and on an edit
-- G: the standing check, restated over the new arms
-- H: the registries every new table owes
-- ---------------------------------------------------------------------------


-- ===========================================================================
-- A -- the catalogue gets the corpus behind it
--
-- 036's `fixtures` carries what a REFUSAL has to read: the kind, the source
-- digest and the third-party coverage fraction. Two columns are missing for a
-- catalogue with files behind it.
--
--   `path`                where a maintainer finds it, and what a test compares
--                         against `fixture.FIXTURES` to catch the row and the
--                         tree disagreeing.
--   `ground_truth_sha256` the digest of `fixture.md`: how a run against this
--                         target is SCORED, which moves separately from what
--                         was SERVED. Rewriting the ground truth regrades every
--                         historical result without changing a byte the model
--                         ever saw, and a test result that froze only
--                         `source_sha256` could not tell you that had happened.
--
-- Both are NOT NULL with no default. The table is empty in every database this
-- migration can reach -- 036 seeded nothing -- so there is no back-fill to get
-- wrong, and a default here would be a value nobody chose surviving into a row
-- somebody later trusts.
-- ===========================================================================

ALTER TABLE fixtures
    ADD COLUMN path text NOT NULL
        CHECK (path ~ '^fixtures/[a-z0-9][a-z0-9-]*/fixture\.md$'),
    ADD COLUMN ground_truth_sha256 text NOT NULL
        CHECK (ground_truth_sha256 ~ '^[0-9a-f]{64}$');

COMMENT ON COLUMN fixtures.ground_truth_sha256 IS
 'The digest of `fixture.md`, which is how a result is graded. Separate from '
 '`source_sha256`, which is what was served: the two move independently and a '
 'run freezes both, so "was this the same target" and "was it graded the same '
 'way" have two answers.';


-- The corpus, one row per directory under `src/redkraken/fixtures/`. Written
-- out rather than loaded, for the reason 045 writes the Playbook row out: a
-- loader that reads the tree at migration time would make the schema depend on
-- the filesystem it is applied from, and the digests below are the whole point
-- of the row. `test_database` compares these against `fixture.FIXTURES` and
-- fails on drift, which is where an edited fixture is caught.
INSERT INTO fixtures (id, kind, path, source_sha256, ground_truth_sha256) VALUES
 ('object-ownership-pair', 'own_pair',
  'fixtures/object-ownership-pair/fixture.md',
  '457725c3d8ad05f33a841407c706cbd87265132035c600b3c23de75a827dee68',
  'a7a9703c8517e0b542b58258cfb3981eb0b2f9e514878abf9629ca0435832c75'),
 ('error-detail-pair', 'own_pair',
  'fixtures/error-detail-pair/fixture.md',
  '3f3cfbc857474fa47ee4632303864efafd77b14777cff5ad3a0841cbc9f8f0ce',
  'c8b76e8d1a6ea166771a9f1f8f57b62819359b7e960bb303ae6ff52f89e7179d');

-- The ground truth. `error-detail-pair` is here because criterion 1 asks for a
-- MEANINGFUL out-of-class negative and the word doing the work is meaningful:
-- an empty page is a negative nothing could fire on. This one holds a real
-- defect in a family no authorization Playbook declares, so a Playbook that
-- reports `authorization.object_ownership` against a route with no session, no
-- object and no second identity is reporting its own class rather than reading
-- the target -- which is what "fires on everything" looks like from outside.
INSERT INTO fixture_classes (fixture_id, property_class) VALUES
 ('object-ownership-pair', 'authorization.object_ownership'),
 ('error-detail-pair',     'information_disclosure.error_detail');


-- ===========================================================================
-- B -- a repeat records the instrument as well as the result
--
-- Criterion 2 lists what one repeat must record. 036 has the Playbook hash, the
-- fixture hash, the claims, the true positives and the ungrounded count. Three
-- things are missing and each is missing for a different reason.
--
--   `fixture_ground_truth`  the grading text, frozen beside the served text.
--   `false_positives`       claims of a class the FIXTURE does not contain.
--                           036 counts `out_of_scope` -- outside the PLAYBOOK's
--                           declaration -- and the two are not the same
--                           question. A real `information_disclosure.error_
--                           detail` found by an authorization Playbook is out
--                           of scope and true; a claim of `injection.query_
--                           language` against a fixture with no interpreter is
--                           in scope of nothing and false. One is a gap in the
--                           fixture, the other is a defect in the Playbook, and
--                           a single column would report them as one number.
--   the Skills it loaded    a Playbook's result is a property of the texts the
--                           model actually read. 045 froze them on a selection
--                           for that reason; a test result that did not freeze
--                           them says "this Playbook passes" about an
--                           instrument that has since been rebuilt.
-- ===========================================================================

ALTER TABLE playbook_test_runs
    ADD COLUMN fixture_ground_truth text NOT NULL
        CHECK (fixture_ground_truth ~ '^[0-9a-f]{64}$'),
    ADD COLUMN false_positives integer NOT NULL CHECK (false_positives >= 0),
    -- A false positive is a claim that was made, so it cannot exceed the claims
    -- that were made. `fired_in_scope + out_of_scope` is 036's count of
    -- grounded, supported claims and this is a subset of it cut a different
    -- way: the two overlap and neither contains the other.
    ADD CONSTRAINT playbook_test_runs_false_positives_are_claims
        CHECK (false_positives <= fired_in_scope + out_of_scope);

COMMENT ON COLUMN playbook_test_runs.false_positives IS
 'Grounded, supported claims of a Property class this fixture''s ground truth '
 'does not contain. Cuts across `out_of_scope`, which is measured against the '
 'Playbook''s own declaration instead: a true finding outside the declaration '
 'is a fixture gap, a false one inside it is a Playbook defect.';


CREATE TABLE playbook_test_run_skills (
    run_id        uuid NOT NULL REFERENCES playbook_test_runs(id) ON DELETE CASCADE,
    skill_name    text NOT NULL REFERENCES skills(name) ON DELETE RESTRICT,
    -- Nullable for 045's reason: 008 created `skills` with a name and an
    -- enabled flag, so a registry row with no file behind it has nothing to
    -- freeze. G reports a run that froze nothing at all.
    skill_sha256  text CHECK (skill_sha256 ~ '^[0-9a-f]{64}$'),
    skill_version text CHECK (skill_version ~ '^[0-9a-f]{64}$'),
    PRIMARY KEY (run_id, skill_name)
);

COMMENT ON TABLE playbook_test_run_skills IS
 'The Skill texts one repeat loaded, copied from the freeze 045 took when the '
 'Playbook was selected in that Program rather than from `skills` at filing '
 'time. A Playbook is a document that names Skills and the model reads all of '
 'them, so a result recorded without them is a result about an instrument '
 'nobody wrote down -- and one recorded from the registry as it stands later is '
 'a result about an instrument that may already have been rebuilt.';

CREATE TRIGGER playbook_test_run_skills_immutable
    BEFORE UPDATE OR DELETE ON playbook_test_run_skills
    FOR EACH ROW EXECUTE FUNCTION reject_mutation_unless_purging();


-- R5, beside 036's four. Same argument as R2 one column over: a run is filed
-- against the fixture on disk, both halves of it. Without this a result can be
-- filed under a source digest the catalogue has moved past, and the row then
-- claims to be about a target that is not there.
CREATE FUNCTION enforce_playbook_test_fixture_text() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE f record;
BEGIN
    SELECT source_sha256, ground_truth_sha256 INTO f
      FROM fixtures WHERE id = NEW.fixture_id;

    IF NEW.fixture_sha256 <> f.source_sha256 THEN
        RAISE EXCEPTION 'test run filed against fixture % at source % but the corpus serves %',
            NEW.fixture_id, left(NEW.fixture_sha256, 12), left(f.source_sha256, 12)
          USING HINT = 'run the test against the application on disk',
                ERRCODE = 'check_violation';
    END IF;

    IF NEW.fixture_ground_truth <> f.ground_truth_sha256 THEN
        RAISE EXCEPTION 'test run graded against ground truth % but the corpus declares %',
            left(NEW.fixture_ground_truth, 12), left(f.ground_truth_sha256, 12)
          USING DETAIL = 'the ground truth decides which claims are true; a result '
                         'graded under an older one is not a result about this fixture',
                ERRCODE = 'check_violation';
    END IF;

    RETURN NEW;
END $$;

-- After 036's `a_playbook_test_run_guard`, which owns the side and the Playbook
-- text. Two triggers rather than a replaced body: 036's message is about the
-- Playbook and this one is about the fixture, and folding them together would
-- put one function in two migrations' hands.
CREATE TRIGGER b_playbook_test_run_fixture_guard
    BEFORE INSERT OR UPDATE ON playbook_test_runs
    FOR EACH ROW EXECUTE FUNCTION enforce_playbook_test_fixture_text();


-- ===========================================================================
-- C -- an evaluation Program cannot promote the Playbook it evaluates
--
-- Criterion 4's last clause: a Playbook "selected only because of its own
-- fixture data fails". 035's `playbook_promotion_evidence` is the chain a
-- promotion must point at, and it does not distinguish where the Program came
-- from. The evaluator in `evaluation.py` opens a real Program against a fixture
-- and hands it the same work callable `rk run` would hand a real target, so an
-- installation with an Agent boundary deposits exactly the selection ->
-- hypothesis -> observation chain 035 counts. (What it cannot reach today is
-- the door, which refuses to dial the loopback address a fixture listens on;
-- ticket 78 decides that route. This section is written for the installation
-- that has one, because the exclusion has to exist before the evidence does.)
--
-- So without this section the loop closes on itself: run the Playbook against
-- the fixture written for its own class, get a supported hypothesis, and the
-- evidence requirement is satisfied by the evaluation that was supposed to be
-- testing it. The fixture test would still have to pass, but "runtime
-- provenance for this exact text" would mean nothing beyond "we ran it once".
--
-- A Program is marked at creation, by the evaluator, and the marker names the
-- Playbook it exists to grade. That second column is not bookkeeping: the count
-- in D attributes hypotheses to a Playbook through (program, subject, class),
-- which is the only edge there is, and it is exact only because an evaluation
-- Program runs one Playbook. The guard below is what makes that true rather
-- than assumed.
-- ===========================================================================

CREATE TABLE evaluation_programs (
    program_id  uuid PRIMARY KEY REFERENCES programs(id) ON DELETE CASCADE,
    playbook_id uuid NOT NULL REFERENCES playbooks(id) ON DELETE CASCADE,
    fixture_id  text NOT NULL REFERENCES fixtures(id) ON DELETE RESTRICT,
    -- Which half of the pair this Program was pointed at. The secure half is
    -- the control and it is a separate Program on purpose: one Program holding
    -- both variants would put the control's observations and the vulnerable
    -- run's observations in one scope, and the count that says "the boundary
    -- held here" would be reading rows from where it did not.
    variant     text NOT NULL CHECK (variant IN ('vulnerable','secure')),
    marked_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (playbook_id, fixture_id, variant, program_id)
);

COMMENT ON TABLE evaluation_programs IS
 'Programs that exist to grade a Playbook, not to hunt a target. Excluded from '
 'promotion evidence: a Playbook promoted by the evaluation that graded it has '
 'been promoted by its own fixture data, which is criterion 4''s last clause.';


CREATE FUNCTION reject_foreign_playbook_in_evaluation() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE v_expected uuid;
BEGIN
    SELECT e.playbook_id INTO v_expected
      FROM evaluation_programs e WHERE e.program_id = NEW.program_id;

    IF v_expected IS NULL OR v_expected = NEW.playbook_id THEN
        RETURN NEW;
    END IF;

    RAISE EXCEPTION 'program % evaluates %, so it cannot also select %',
        NEW.program_id,
        (SELECT path FROM playbooks WHERE id = v_expected),
        (SELECT path FROM playbooks WHERE id = NEW.playbook_id)
      USING DETAIL = 'a test run attributes hypotheses to a Playbook through '
                     '(program, subject, class); with two Playbooks in one '
                     'evaluation Program that attribution is a guess',
            ERRCODE = 'check_violation';
END $$;

-- Before 045's `playbook_selection_freeze`, so a selection that will not be
-- countable is refused before its Skill texts are frozen.
CREATE TRIGGER a_evaluation_program_runs_one_playbook
    BEFORE INSERT OR UPDATE ON playbook_selections
    FOR EACH ROW EXECUTE FUNCTION reject_foreign_playbook_in_evaluation();


-- 035's body with one clause added. The signature and the columns are
-- unchanged, so `enforce_playbook_promotion` and every integrity check that
-- counts it keep working; what changes is which Programs may contribute.
CREATE OR REPLACE FUNCTION playbook_promotion_evidence(p_playbook uuid, p_sha text DEFAULT NULL)
RETURNS TABLE (program_id uuid, hypothesis_id uuid, property_class text,
               observation_id uuid, provenance_kind text)
LANGUAGE sql STABLE AS $$
    SELECT s.program_id, h.id, h.property_class, o.id, o.provenance_kind
      FROM playbook_selections s
      JOIN playbook_outputs po ON po.playbook_id = s.playbook_id
      JOIN hypotheses h
        ON h.program_id        = s.program_id
       AND h.subject_entity_id = s.subject_entity_id
       AND h.property_class    = po.property_class
       AND h.status            = 'supported'
      JOIN hypothesis_evidence he
        ON he.hypothesis_id = h.id AND he.polarity = 'supports'
      JOIN observations o ON o.id = he.observation_id
     WHERE s.playbook_id     = p_playbook
       AND s.dropped_because IS NULL
       AND s.outcome         = 'produced'
       AND s.playbook_sha256 = coalesce(
             p_sha, (SELECT source_sha256 FROM playbooks WHERE id = p_playbook))
       -- Ticket 46. The evaluation is the test, not the evidence.
       AND NOT EXISTS (SELECT 1 FROM evaluation_programs e
                        WHERE e.program_id = s.program_id);
$$;

COMMENT ON FUNCTION playbook_promotion_evidence(uuid, text) IS
 'The runtime-generated chain a promotion must point at, from Programs that '
 'were hunting rather than grading. Empty for every v1 card at import time, '
 'and empty for a Playbook whose only runs are its own evaluation -- which is '
 'the case that otherwise promotes a Playbook on its own fixture data.';


-- ===========================================================================
-- D -- the counts are computed, never supplied
--
-- 036 says every column on a run row is "a COUNT the harness produced ... not a
-- verdict a model reported", and then leaves the INSERT to whoever writes one.
-- A caller that computes its own numbers is a model one layer removed: the
-- harness would be recording what the evaluator believed about the run rather
-- than what the run left behind.
--
-- This function is the only intended way a run row is written. It takes the two
-- Programs the repeat ran in and derives everything else from the rows they
-- produced. Nothing about the result is an argument.
--
-- HOW A CLAIM IS ATTRIBUTED. Through (program, subject, class), which is 035's
-- edge and the only one there is -- made exact by C's guard rather than by
-- hope: an evaluation Program runs one Playbook, so every hypothesis on a
-- subject that Playbook was selected on is that Playbook's.
--
-- WHAT EACH COUNT MEANS, since four of them are close together:
--
--   claims            every non-superseded hypothesis the run produced, at any
--                     status. A proposal is output the Playbook produced even
--                     though it asserts nothing yet, and 036's accounting
--                     constraint needs the superset.
--   ungrounded        SUPPORTED claims citing no supporting observation.
--                     Structurally zero while 015's `testing -> supported`
--                     transition rule requires a test-linked receipt, and
--                     counted anyway: a clause that is redundant with a guard
--                     in another migration is exactly what notices that guard
--                     being edited, and it costs one FILTER.
--   fired_in_scope    grounded and supported, class in `playbook_outputs`.
--   out_of_scope      grounded and supported, class NOT in `playbook_outputs`.
--   false_positives   grounded and supported, class NOT in `fixture_classes`.
--   discriminating_tp in scope, in the ground truth, and NOT admitted by the
--                     secure half. The last conjunct is the control: a claim
--                     the Playbook also makes against the variant that enforces
--                     the boundary is not evidence it read anything. With no
--                     secure half there is no such conjunct to evaluate, so the
--                     count is 0 -- 036's R4 reasoning about `admitted_secure`
--                     applied to the number R4 exists to protect. Without that
--                     guard `NOT admitted` is vacuously true for a third-party
--                     fixture and every claim takes full credit uncontrolled,
--                     which is the shape 036 states it does not have: "third
--                     party = no secure twin, therefore no discriminating".
-- ===========================================================================

CREATE FUNCTION record_playbook_test_run(
    p_playbook   uuid,
    p_fixture    text,
    p_vulnerable uuid,
    p_secure     uuid DEFAULT NULL
) RETURNS uuid
LANGUAGE plpgsql AS $$
DECLARE
    v_sha          text;
    v_source       text;
    v_ground_truth text;
    v_kind         text;
    v_side         text;
    v_skills       text;
    v_ambiguous    text;
    v_repeat       integer;
    v_run          uuid;
    c              record;
BEGIN
    SELECT p.source_sha256 INTO v_sha FROM playbooks p WHERE p.id = p_playbook;
    IF v_sha IS NULL THEN
        RAISE EXCEPTION 'no playbook %', p_playbook USING ERRCODE = 'foreign_key_violation';
    END IF;

    SELECT f.source_sha256, f.ground_truth_sha256, f.kind
      INTO v_source, v_ground_truth, v_kind
      FROM fixtures f WHERE f.id = p_fixture;
    IF v_source IS NULL THEN
        RAISE EXCEPTION 'no fixture %', p_fixture USING ERRCODE = 'foreign_key_violation';
    END IF;

    SELECT b.side INTO v_side
      FROM playbook_fixture_binding(p_playbook) b WHERE b.fixture_id = p_fixture;

    -- The two Programs are the evaluator's, and they have to say so. A run
    -- counted out of an unmarked Program would be a run whose evidence C is
    -- still admitting into promotions: the marker is what makes the exclusion
    -- and the measurement read the same rows.
    PERFORM 1 FROM evaluation_programs e
      WHERE e.program_id = p_vulnerable AND e.playbook_id = p_playbook
        AND e.fixture_id = p_fixture AND e.variant = 'vulnerable';
    IF NOT FOUND THEN
        RAISE EXCEPTION 'program % is not marked as the vulnerable evaluation of % against %',
            p_vulnerable, (SELECT path FROM playbooks WHERE id = p_playbook), p_fixture
          USING HINT = 'mark it in evaluation_programs before the run, not after',
                ERRCODE = 'check_violation';
    END IF;

    IF v_kind = 'own_pair' THEN
        PERFORM 1 FROM evaluation_programs e
          WHERE e.program_id = p_secure AND e.playbook_id = p_playbook
            AND e.fixture_id = p_fixture AND e.variant = 'secure';
        IF NOT FOUND THEN
            RAISE EXCEPTION 'fixture % is a pair and its secure half was not run', p_fixture
              USING DETAIL = 'without the control, a claim on the vulnerable half cannot be '
                             'told apart from a claim the playbook makes about anything',
                    ERRCODE = 'check_violation';
        END IF;
    ELSIF p_secure IS NOT NULL THEN
        RAISE EXCEPTION 'fixture % has no secure twin; there is no second program to run',
            p_fixture USING ERRCODE = 'check_violation';
    END IF;

    -- Every count, from the rows the run left behind.
    WITH claim AS (
        SELECT h.property_class,
               h.status = 'supported' AS asserted,
               EXISTS (SELECT 1 FROM hypothesis_evidence he
                        WHERE he.hypothesis_id = h.id AND he.polarity = 'supports') AS grounded,
               EXISTS (SELECT 1 FROM playbook_outputs po
                        WHERE po.playbook_id = p_playbook
                          AND po.property_class = h.property_class) AS declared,
               EXISTS (SELECT 1 FROM fixture_classes fc
                        WHERE fc.fixture_id = p_fixture
                          AND fc.property_class = h.property_class) AS contained,
               -- Deliberately wider than the vulnerable side below, which is
               -- restricted to the subjects this Playbook was selected on: a
               -- claim of this class on the control disqualifies whatever
               -- selected it there. The asymmetry only ever REMOVES credit,
               -- and a control that let a claim through on a technicality
               -- about which selection produced it would be no control.
               EXISTS (SELECT 1 FROM hypotheses s
                         JOIN hypothesis_evidence se
                           ON se.hypothesis_id = s.id AND se.polarity = 'supports'
                        WHERE s.program_id = p_secure
                          AND s.superseded_by IS NULL
                          AND s.status = 'supported'
                          AND s.property_class = h.property_class) AS admitted
          FROM hypotheses h
         WHERE h.program_id = p_vulnerable
           AND h.superseded_by IS NULL
           AND EXISTS (SELECT 1 FROM playbook_selections s
                        WHERE s.program_id = p_vulnerable
                          AND s.playbook_id = p_playbook
                          AND s.subject_entity_id = h.subject_entity_id
                          AND s.dropped_because IS NULL)
    )
    SELECT count(*)::int AS claims,
           count(*) FILTER (WHERE asserted AND NOT grounded)::int AS ungrounded,
           count(*) FILTER (WHERE asserted AND grounded AND declared)::int AS fired_in_scope,
           count(*) FILTER (WHERE asserted AND grounded AND NOT declared)::int AS out_of_scope,
           count(*) FILTER (WHERE asserted AND grounded AND NOT contained)::int AS false_positives,
           count(*) FILTER (WHERE p_secure IS NOT NULL
                                  AND asserted AND grounded AND declared
                                  AND contained AND NOT admitted)::int AS discriminating_tp
      INTO c FROM claim;

    -- Repeats are numbered by the harness. A caller-supplied index is a caller
    -- that can overwrite the repeat it did not like.
    SELECT coalesce(max(r.repeat_index) + 1, 0) INTO v_repeat
      FROM playbook_test_runs r
     WHERE r.playbook_id = p_playbook AND r.playbook_sha256 = v_sha
       AND r.fixture_id = p_fixture;

    -- The instrument, from 045's freeze rather than from the registry as it
    -- stands now. `playbook_selection_skills` is what this Program was handed
    -- when the Playbook was selected in it; `skills` is what the catalogue holds
    -- at the moment of filing, and the two differ exactly when a Skill was
    -- edited between the run and the filing -- which is the case 045 froze them
    -- for. The counts above already read this run through `playbook_selections`,
    -- so taking its instrument from anywhere else would be one function keeping
    -- two accounts of one Program.
    --
    -- A Program that froze two texts of one Skill name is refused rather than
    -- deduplicated: the run's own key would then depend on which of them the
    -- insert happened to keep.
    SELECT string_agg(name, ', ' ORDER BY name) INTO v_ambiguous FROM (
        SELECT k.skill_name AS name
          FROM playbook_selection_skills k
          JOIN playbook_selections s ON s.id = k.selection_id
         WHERE s.program_id = p_vulnerable AND s.playbook_id = p_playbook
           AND s.dropped_because IS NULL
         GROUP BY k.skill_name
        HAVING count(DISTINCT (k.skill_sha256, k.skill_version)) > 1
    ) q;
    IF v_ambiguous IS NOT NULL THEN
        RAISE EXCEPTION 'program % froze more than one text of Skill %', p_vulnerable, v_ambiguous
          USING DETAIL = 'the repeat has no single instrument to record; re-run it against '
                         'a corpus that stopped moving',
                ERRCODE = 'check_violation';
    END IF;

    -- The run key: everything that must be equal for two rows to be repeats of
    -- one measurement. The Skill digests are in it because two runs that read
    -- different Skill texts measured different instruments, however identical
    -- the Playbook was.
    SELECT string_agg(DISTINCT k.skill_name || '@' || coalesce(k.skill_sha256, '-')
                      || '/' || coalesce(k.skill_version, '-'), ','
                      ORDER BY k.skill_name || '@' || coalesce(k.skill_sha256, '-')
                      || '/' || coalesce(k.skill_version, '-'))
      INTO v_skills
      FROM playbook_selection_skills k
      JOIN playbook_selections s ON s.id = k.selection_id
     WHERE s.program_id = p_vulnerable AND s.playbook_id = p_playbook
       AND s.dropped_because IS NULL;

    INSERT INTO playbook_test_runs
        (playbook_id, playbook_sha256, fixture_id, fixture_sha256, fixture_ground_truth,
         side, repeat_index, run_key,
         claims, ungrounded, fired_in_scope, out_of_scope, false_positives,
         discriminating_tp, admitted_secure, tool_runs)
    VALUES
        (p_playbook, v_sha, p_fixture, v_source, v_ground_truth,
         v_side, v_repeat,
         left(encode(sha256(convert_to(
              p_playbook::text || ':' || v_sha || ':' || p_fixture || ':' || v_source
              || ':' || v_ground_truth || ':' || coalesce(v_skills, ''), 'utf8')), 'hex'), 32),
         c.claims, c.ungrounded, c.fired_in_scope, c.out_of_scope, c.false_positives,
         c.discriminating_tp,
         -- 036's R4: NULL, never 0, for a target with no secure twin. Counted
         -- inside the Playbook's own declaration, because a correct claim about
         -- something else on the secure half is not a false alarm -- the
         -- out-side clause is what answers that.
         CASE WHEN v_kind = 'own_pair' THEN (
             SELECT count(*)::int FROM hypotheses h
               JOIN hypothesis_evidence he
                 ON he.hypothesis_id = h.id AND he.polarity = 'supports'
              WHERE h.program_id = p_secure AND h.superseded_by IS NULL
                AND h.status = 'supported'
                AND EXISTS (SELECT 1 FROM playbook_outputs po
                             WHERE po.playbook_id = p_playbook
                               AND po.property_class = h.property_class))
         END,
         (SELECT count(*)::int FROM tool_runs t
           WHERE t.program_id = p_vulnerable
              OR (p_secure IS NOT NULL AND t.program_id = p_secure)))
    RETURNING id INTO v_run;

    INSERT INTO playbook_test_run_skills (run_id, skill_name, skill_sha256, skill_version)
    SELECT DISTINCT v_run, k.skill_name, k.skill_sha256, k.skill_version
      FROM playbook_selection_skills k
      JOIN playbook_selections s ON s.id = k.selection_id
     WHERE s.program_id = p_vulnerable AND s.playbook_id = p_playbook
       AND s.dropped_because IS NULL;

    RETURN v_run;
END $$;

COMMENT ON FUNCTION record_playbook_test_run(uuid, text, uuid, uuid) IS
 'Files one repeat. Every count is derived from the rows the two evaluation '
 'Programs produced, and the repeat index and run key are the harness''s: the '
 'caller says which Playbook ran against which fixture in which Programs, and '
 'nothing about how it went.';


-- ===========================================================================
-- E -- how many repeats, stated once
--
-- Criterion 3 asks for "the configured repeated positive result". 036's
-- sensitivity clause takes the MEDIAN over whatever repeats exist, which
-- degenerates to the single value when there is one run -- and one run of a
-- stochastic model is a coin that came up heads.
--
-- The number lives in a table rather than in the function body so it is one
-- edit, visible to a reader who does not read plpgsql, and so a deployment can
-- raise it without a migration touching the verdict. Three is the smallest
-- number for which a median means anything: at two, the median of {0,1} is 0.5
-- and the clause is decided by rounding rather than by agreement.
-- ===========================================================================

CREATE TABLE playbook_test_policy (
    id               integer PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    required_repeats integer NOT NULL CHECK (required_repeats BETWEEN 1 AND 32),
    changed_at       timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE playbook_test_policy IS
 'How many times every fixture in a Playbook''s binding must have been run at '
 'this exact text before the verdict is anything but `untested`. One row by '
 'primary key, unreadable by the agent connection.';

INSERT INTO playbook_test_policy (required_repeats) VALUES (3);


-- 036's body with clause 3b inserted, restated in full rather than wrapped.
-- The clause ORDER is the semantics here -- the three categorical failures are
-- evaluated before every coverage clause, so observed misbehaviour cannot be
-- laundered into "not measured" by an incomplete catalogue -- and a wrapper
-- can only add a clause at one end or the other, never into the middle of that
-- order. The alternative was to leave 036's clauses where they are and check
-- repeats afterwards, which would report `pass` for a Playbook measured once.
CREATE OR REPLACE FUNCTION playbook_test_verdict(p_playbook uuid, p_sha text DEFAULT NULL)
RETURNS TABLE (verdict text, reason text)
LANGUAGE plpgsql STABLE AS $$
DECLARE
    sha        text;
    n_in_pair  integer;
    n_out      integer;
    n_missing  integer;
    n_repeats  integer;
    bad        text;
BEGIN
    sha := coalesce(p_sha, (SELECT source_sha256 FROM playbooks WHERE id = p_playbook));
    SELECT required_repeats INTO n_repeats FROM playbook_test_policy WHERE id = 1;

    -- A. grounded. One occurrence at one repeat, both sides, categorical.
    SELECT string_agg(DISTINCT r.fixture_id, ',') INTO bad
      FROM playbook_test_runs r
     WHERE r.playbook_id = p_playbook AND r.playbook_sha256 = sha AND r.ungrounded > 0;
    IF bad IS NOT NULL THEN
        RETURN QUERY SELECT 'fail', 'ungrounded claim on ' || bad;
        RETURN;
    END IF;

    -- B. the secure twin stayed quiet. Never averaged: this is the clause that
    --    catches a playbook reporting its class whatever the target returned.
    SELECT string_agg(DISTINCT r.fixture_id, ',') INTO bad
      FROM playbook_test_runs r
     WHERE r.playbook_id = p_playbook AND r.playbook_sha256 = sha
       AND coalesce(r.admitted_secure, 0) > 0;
    IF bad IS NOT NULL THEN
        RETURN QUERY SELECT 'fail', 'admits a claim on the secure variant of ' || bad;
        RETURN;
    END IF;

    -- C. the `out` side. A claim on a fixture that does not contain the
    --    playbook's class is grounded, reproducible and not about anything.
    SELECT string_agg(DISTINCT r.fixture_id, ',') INTO bad
      FROM playbook_test_runs r
     WHERE r.playbook_id = p_playbook AND r.playbook_sha256 = sha
       AND r.side = 'out' AND r.fired_in_scope > 0;
    IF bad IS NOT NULL THEN
        RETURN QUERY SELECT 'fail',
            'fires inside its own declared classes on out-side fixture ' || bad;
        RETURN;
    END IF;

    -- D. ticket 46. A claim of a class the fixture does not contain, on either
    --    side. C catches the playbook that reports its OWN class everywhere;
    --    this catches the one that reports somebody else's, which the `out`
    --    clause reads as out of scope and 036 therefore never scored. Both are
    --    a playbook talking about a target it did not read.
    SELECT string_agg(DISTINCT r.fixture_id, ',') INTO bad
      FROM playbook_test_runs r
     WHERE r.playbook_id = p_playbook AND r.playbook_sha256 = sha
       AND r.false_positives > 0;
    IF bad IS NOT NULL THEN
        RETURN QUERY SELECT 'fail',
            'claims a class the ground truth does not contain on ' || bad;
        RETURN;
    END IF;

    -- 1. An `in` set of own PAIRS. Own pairs only: a third-party `in` fixture
    --    can fail this playbook and can never satisfy it, because
    --    `discriminating` is unevaluable with no control.
    SELECT count(*) INTO n_in_pair FROM playbook_fixture_binding(p_playbook) b
     WHERE b.side = 'in' AND b.kind = 'own_pair';
    IF n_in_pair = 0 THEN
        RETURN QUERY SELECT 'untested',
            'no own-pair fixture declares a class this playbook declares as an output';
        RETURN;
    END IF;

    -- 2. An `out` set. With none, specificity is unmeasured.
    SELECT count(*) INTO n_out FROM playbook_fixture_binding(p_playbook) b
     WHERE b.side = 'out';
    IF n_out = 0 THEN
        RETURN QUERY SELECT 'untested',
            'every fixture in the catalogue contains one of this playbook''s output classes; '
            'nothing measures whether it fires where it should not';
        RETURN;
    END IF;

    -- 3. The binding is total, so the run set must be too.
    SELECT count(*) INTO n_missing
      FROM playbook_fixture_binding(p_playbook) b
     WHERE NOT EXISTS (SELECT 1 FROM playbook_test_runs r
                        WHERE r.playbook_id = p_playbook AND r.playbook_sha256 = sha
                          AND r.fixture_id = b.fixture_id);
    IF n_missing > 0 THEN
        RETURN QUERY SELECT 'untested',
            n_missing || ' fixture(s) in the binding have no run at this text';
        RETURN;
    END IF;

    -- 3b. ticket 46: the configured repeat, on EVERY fixture rather than only
    --     the positive ones. A playbook that fires on the negative one time in
    --     three is a playbook that fires on the negative, and a single out-side
    --     run is as likely to miss that as a single in-side run is to miss a
    --     finding. The cost is the same order either way.
    SELECT string_agg(b.fixture_id || ' (' || (
               SELECT count(*) FROM playbook_test_runs r
                WHERE r.playbook_id = p_playbook AND r.playbook_sha256 = sha
                  AND r.fixture_id = b.fixture_id) || ')', ',') INTO bad
      FROM playbook_fixture_binding(p_playbook) b
     WHERE (SELECT count(*) FROM playbook_test_runs r
             WHERE r.playbook_id = p_playbook AND r.playbook_sha256 = sha
               AND r.fixture_id = b.fixture_id) < n_repeats;
    IF bad IS NOT NULL THEN
        RETURN QUERY SELECT 'untested',
            'fewer than ' || n_repeats || ' repeats at this text on ' || bad;
        RETURN;
    END IF;

    -- 4. sensitivity. STATISTICAL, so the median over repeats: a fixture whose
    --    repeats disagree is an instrument fault, not evidence the playbook is
    --    worse.
    SELECT string_agg(b.fixture_id, ',') INTO bad
      FROM playbook_fixture_binding(p_playbook) b
     WHERE b.side = 'in' AND b.kind = 'own_pair'
       AND coalesce(playbook_test_median_tp(p_playbook, sha, b.fixture_id), 0) < 1;
    IF bad IS NOT NULL THEN
        RETURN QUERY SELECT 'fail',
            'median discriminating finding < 1 on ' || bad;
        RETURN;
    END IF;

    RETURN QUERY SELECT 'pass',
        n_in_pair || ' in-pair, ' || n_out || ' out fixture(s), '
        || n_repeats || ' repeats each, all clean';
END $$;

COMMENT ON FUNCTION playbook_test_verdict(uuid, text) IS
 'pass / fail / untested. `untested` is not a soft fail and not a soft pass: it '
 'blocks promotion and does not demote. Ticket 46 added the false-positive '
 'clause and the configured repeat minimum; the clause order is load-bearing, '
 'because a playbook can fail before it is fully tested and cannot pass before '
 'it is.';


-- ===========================================================================
-- F -- demotion on a failing verdict, on expiry, and on an edit
--
-- Criterion 5: "Editing, expiry or a later failing verdict demotes the Playbook
-- from stable without deleting historical test runs." Three causes, one of
-- which 036 has.
--
-- EXPIRY. 036 argued expiry should not demote: `stale_after` is a review date,
-- `mark_stale_selections()` already excludes an expired Playbook at selection,
-- and the two exclusions are independent. The reasoning is right about
-- selection and wrong about the catalogue. `stable` is a claim in the operator's
-- face about which Playbooks are trusted, and a Playbook nobody has reviewed
-- since its date passed is not one -- it is merely one that is quietly never
-- chosen. Ticket 46 reverses the decision: expiry demotes, and re-promotion
-- after a review is the same path any other Playbook takes.
--
-- EDITING. 035's guard RAISES here: change the text of a promoted card and the
-- evidence chain is re-evaluated against the new digest, finds nothing, and
-- refuses the UPDATE. That makes an edit impossible rather than demoting, so a
-- maintainer's only route is to hand-clear `promoted_at` first -- an
-- undocumented two-step that the ledger below never sees. The trigger here runs
-- FIRST (`a0_` sorts before `a_` in both C and en_US.UTF-8, and PostgreSQL
-- fires row triggers in name order) and demotes, so 035's guard sees a row that
-- is no longer promoted and returns.
--
-- NOTHING IS DELETED. `playbook_test_runs` has no cascade from a status change
-- and this migration adds none. A demoted Playbook keeps every result it ever
-- produced, which is what makes "it used to pass, and here is what changed"
-- answerable at all.
-- ===========================================================================

CREATE TABLE playbook_demotions (
    id              uuid PRIMARY KEY DEFAULT uuidv7(),
    playbook_id     uuid NOT NULL REFERENCES playbooks(id) ON DELETE CASCADE,
    -- The text that WAS stable, which is not necessarily the text that is on
    -- disk afterwards: on an edit these differ, and that difference is the
    -- record of what was demoted.
    playbook_sha256 text NOT NULL CHECK (playbook_sha256 ~ '^[0-9a-f]{64}$'),
    cause           text NOT NULL CHECK (cause IN ('failed','expired','edited')),
    detail          text NOT NULL CHECK (detail <> ''),
    demoted_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX playbook_demotions_playbook_idx ON playbook_demotions (playbook_id, demoted_at);

COMMENT ON TABLE playbook_demotions IS
 'Why a Playbook stopped being stable, and at which text. Append-only: a '
 'catalogue that quietly re-promotes and re-demotes reads as a stable one from '
 'any single snapshot.';

CREATE TRIGGER playbook_demotions_immutable
    BEFORE UPDATE OR DELETE ON playbook_demotions
    FOR EACH ROW EXECUTE FUNCTION reject_mutation_unless_purging();


CREATE FUNCTION demote_edited_playbook() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.source_sha256 IS NOT DISTINCT FROM NEW.source_sha256 THEN
        RETURN NEW;
    END IF;
    IF OLD.status <> 'stable' AND OLD.promoted_at IS NULL THEN
        RETURN NEW;
    END IF;

    INSERT INTO playbook_demotions (playbook_id, playbook_sha256, cause, detail)
    VALUES (OLD.id, OLD.source_sha256, 'edited',
            'text changed from ' || left(OLD.source_sha256, 12)
            || ' to ' || left(NEW.source_sha256, 12));

    -- `deprecated` is left alone: retiring a card and rewriting it in one
    -- statement is still a retirement, and forcing it back to `draft` would
    -- make the catalogue offer it again.
    IF NEW.status = 'stable' THEN
        NEW.status := 'draft';
    END IF;
    NEW.promoted_at := NULL;
    RETURN NEW;
END $$;

COMMENT ON FUNCTION demote_edited_playbook() IS
 'A promoted Playbook whose text changes is demoted rather than refused: the '
 'promotion was a statement about the old bytes and the new bytes have not '
 'earned one. Runs at `a0_`, before 035''s promotion guard, which would '
 'otherwise refuse the edit outright.';

CREATE TRIGGER a0_playbook_edit_demotes
    BEFORE UPDATE ON playbooks
    FOR EACH ROW EXECUTE FUNCTION demote_edited_playbook();


DROP FUNCTION demote_failed_playbooks();

CREATE FUNCTION demote_playbooks()
RETURNS TABLE (path text, cause text, reason text) LANGUAGE sql AS $$
    WITH candidate AS (
        SELECT p.id, p.path, p.source_sha256,
               CASE WHEN v.verdict = 'fail' THEN 'failed' ELSE 'expired' END AS cause,
               CASE WHEN v.verdict = 'fail' THEN v.reason
                    ELSE 'stale_after passed on ' || p.stale_after::date::text
               END AS reason
          FROM playbooks p
          CROSS JOIN LATERAL playbook_test_verdict(p.id, p.source_sha256) v
         WHERE p.status = 'stable'
           -- `untested` is deliberately absent. It is what ADDING a fixture
           -- looks like from here, and demoting the catalogue because somebody
           -- widened its test is a rule nobody would widen a test under.
           AND (v.verdict = 'fail'
                OR (p.stale_after IS NOT NULL AND p.stale_after <= now()))
    ), ledger AS (
        INSERT INTO playbook_demotions (playbook_id, playbook_sha256, cause, detail)
        SELECT c.id, c.source_sha256, c.cause, c.reason FROM candidate c
        RETURNING 1
    ), demoted AS (
        UPDATE playbooks p SET status = 'draft', promoted_at = NULL
          FROM candidate c WHERE p.id = c.id
        RETURNING p.id
    )
    SELECT c.path, c.cause, c.reason FROM candidate c ORDER BY c.path;
$$;

COMMENT ON FUNCTION demote_playbooks() IS
 'Demotion is automatic and reversible; leaving a Playbook stable while its own '
 'test fails, or while nobody has reviewed it since its date passed, is what '
 'feeds bad selections. Writes the ledger and deletes no test run.';


-- ===========================================================================
-- G -- the standing check, restated over the new arms
--
-- Same two errors 036 registered plus one, and the warnings re-cut. Restated
-- in full for the reason the verdict is: the arms are a single UNION ALL and
-- there is no seam to add one at.
--
-- Nine arms, three of them new: `stable_playbook_expired`,
-- `test_run_for_superseded_fixture` and `test_run_froze_no_skills`. One of
-- 036's is gone rather than re-cut: `stale_playbook_test_passing` warned that
-- a Playbook past its review date still had a green test, which was a warning
-- because nothing acted on the date. Two things act on it now. F demotes it,
-- so a stable one is reported by the new hard arm for as long as it is still
-- stable; and 045's selection drops any Playbook past its date with
-- `expired`, whatever its status, so the draft case is a Playbook nothing can
-- select. What is left for a warning to say is that a green test is old, which
-- is what `stale_after` already says.
-- ===========================================================================

CREATE OR REPLACE FUNCTION check_playbook_tests()
RETURNS TABLE (severity text, problem text, detail text) LANGUAGE sql STABLE AS $$
    -- HARD: a stable playbook whose test fails. `demote_playbooks()` is owed.
    SELECT 'error'::text, 'stable_playbook_failing'::text, p.path || ' -> ' || v.reason
      FROM playbooks p
      CROSS JOIN LATERAL playbook_test_verdict(p.id, p.source_sha256) v
     WHERE p.status = 'stable' AND v.verdict = 'fail'
UNION ALL
    -- HARD: ticket 46. Stable and past its review date. Same shape as the
    -- above and the same remedy; 036 reported this as a warning because expiry
    -- did not demote, and it does now.
    SELECT 'error', 'stable_playbook_expired',
           p.path || ' -> stale_after passed on ' || p.stale_after::date::text
      FROM playbooks p
     WHERE p.status = 'stable' AND p.stale_after IS NOT NULL AND p.stale_after <= now()
UNION ALL
    -- HARD: a fixture declaring a class no vocabulary entry has is unwritable
    -- (FK), so a row here means the catalogue was bypassed.
    SELECT 'error', 'fixture_class_unknown', fc.fixture_id || ' -> ' || fc.property_class
      FROM fixture_classes fc
     WHERE NOT EXISTS (SELECT 1 FROM property_classes pc WHERE pc.id = fc.property_class)
UNION ALL
    -- WARNING: stable but no longer testable. Almost always a fixture was
    -- added and the suite has not caught up.
    SELECT 'warning', 'stable_playbook_untested', p.path || ' -> ' || v.reason
      FROM playbooks p
      CROSS JOIN LATERAL playbook_test_verdict(p.id, p.source_sha256) v
     WHERE p.status = 'stable' AND v.verdict = 'untested'
UNION ALL
    -- WARNING: the catalogue's untestable tail -- what "every playbook needs a
    -- test" costs against a catalogue that mostly does not exist yet.
    SELECT 'warning', 'draft_playbook_untestable', p.path || ' -> ' || v.reason
      FROM playbooks p
      CROSS JOIN LATERAL playbook_test_verdict(p.id, p.source_sha256) v
     WHERE p.status = 'draft' AND v.verdict = 'untested'
UNION ALL
    -- WARNING: a real finding outside the playbook's declaration. Never scored
    -- against the playbook; it is a ground-truth gap in the FIXTURE, and the
    -- fixture's owner is the one who has to answer it.
    SELECT 'warning', 'fixture_groundtruth_gap',
           r.fixture_id || ' <- ' || p.path || ' (' || r.out_of_scope
           || ' finding(s) outside its bb:outputs)'
      FROM playbook_test_runs r JOIN playbooks p ON p.id = r.playbook_id
     WHERE r.out_of_scope > 0
UNION ALL
    -- WARNING: test results for a text the card no longer has. R2 makes new
    -- rows impossible, so this is the residue of a re-text -- which is exactly
    -- why the standing does not transfer.
    SELECT 'warning', 'test_run_for_superseded_text',
           p.path || ' -> ' || left(r.playbook_sha256, 12)
      FROM playbook_test_runs r JOIN playbooks p ON p.id = r.playbook_id
     WHERE r.playbook_sha256 <> p.source_sha256
     GROUP BY p.path, r.playbook_sha256
UNION ALL
    -- WARNING: ticket 46. Results graded against a fixture the corpus has moved
    -- past. R5 makes new ones impossible; an old one is a result whose verdict
    -- was decided by text that is no longer the ground truth.
    SELECT 'warning', 'test_run_for_superseded_fixture',
           r.fixture_id || ' -> ' || left(r.fixture_ground_truth, 12)
      FROM playbook_test_runs r JOIN fixtures f ON f.id = r.fixture_id
     WHERE r.fixture_sha256 <> f.source_sha256
        OR r.fixture_ground_truth <> f.ground_truth_sha256
     GROUP BY r.fixture_id, r.fixture_ground_truth
UNION ALL
    -- WARNING: ticket 46. A repeat that recorded no Skill text for a Playbook
    -- that declares Skills. 045's warning one table over, for the same reason:
    -- the result is about an instrument nobody wrote down.
    SELECT 'warning', 'test_run_froze_no_skills', p.path || ' on ' || r.fixture_id
      FROM playbook_test_runs r JOIN playbooks p ON p.id = r.playbook_id
     WHERE EXISTS (SELECT 1 FROM playbook_skills ps WHERE ps.playbook_id = p.id)
       AND NOT EXISTS (SELECT 1 FROM playbook_test_run_skills s WHERE s.run_id = r.id)
     GROUP BY p.path, r.fixture_id;
$$;

-- The registration is 036's and its query is unchanged (`severity = 'error'`),
-- so the new hard arm is picked up without touching the row.


-- ===========================================================================
-- H -- the registries every new table owes
-- ===========================================================================

INSERT INTO program_global_tables (table_name, reason) VALUES
 ('playbook_test_run_skills',
  'the Skill texts one repeat loaded; belongs to the run, which is a statement about a Playbook text'),
 ('playbook_test_policy',
  'how many repeats a verdict needs; a per-program copy would let one Program promote on a single run'),
 ('playbook_demotions',
  'why a Playbook stopped being stable; the catalogue is global, so its history is'),
 -- This one HAS a `program_id` and is declared global anyway, which is the
 -- registry earning its keep. Under row level security the marker would be
 -- visible only inside the Program it marks, so the NOT EXISTS in
 -- `playbook_promotion_evidence` would see nothing for every other Program and
 -- the exclusion would silently become a no-op -- the exact failure mode the
 -- exclusion exists to prevent. It is unreadable to the agent connection by a
 -- different mechanism: no column of it is on the state read surface.
 ('evaluation_programs',
  'the marker is read by a catalogue-wide promotion rule; per-Program visibility would hide exactly the Programs a promotion must exclude');

INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
 ('playbook_test_run_skills', 'run_id',      'belongs to the run: the Skill texts one repeat loaded'),
 ('playbook_demotions',       'playbook_id', 'catalogue-scoped: the demotion history of a Playbook that no longer exists'),
 ('evaluation_programs',      'program_id',  'the marker dies with the Program it marks'),
 ('evaluation_programs',      'playbook_id', 'catalogue-scoped: a Program that graded a Playbook nobody has any more grades nothing');

INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
 ('playbook_test_run_skills', 'bookkeeping',
  'the Skill digests one repeat loaded; measurement of the harness against code we wrote, not knowledge about a target', '46'),
 ('playbook_test_policy',     'reference',
  'how many repeats a verdict needs, changed only by migration', '46'),
 ('playbook_demotions',       'bookkeeping',
  'why a Playbook left `stable`; a fact about the catalogue, not about a target', '46'),
 ('evaluation_programs',      'reference',
  'which Programs exist to grade a Playbook rather than to hunt; written once at creation', '46');

-- No `state_read_surface` rows, for any of this and for 036's tables either.
-- The fixture catalogue IS the answer key: an agent that could read
-- `fixture_classes` would be handed the ground truth it is being graded
-- against, and one that could read `evaluation_programs` would know it is being
-- tested rather than deployed. Both are exactly the reads that make a
-- measurement meaningless, so the surface stays empty and this comment is the
-- record that the omission was decided rather than forgotten.
