-- ---------------------------------------------------------------------------
-- Folded into the ticket-33 baseline from `prototype/playbook-tests` d9be247
-- (`031_ticket25_playbook_tests.sql`).
--
-- The body is carried across unchanged. 031 needed no adaptation: it creates no
-- program-scoped table, so `apply_state_rls()` and `apply_state_grants()` have
-- nothing to do for it; it writes no grants of its own, so the baseline's
-- `ALTER DEFAULT PRIVILEGES FOR ROLE rk2_owner` is not being duplicated; and it
-- already registers its own `program_global_tables` and `purge_cascade_edges`
-- rows. Section 8 at the end is the only addition: the event classification
-- every managed table owes, and the `standing_checks` registration that turns
-- `check_playbook_tests()` from a function nothing calls into one that runs on
-- every `up`.
-- ---------------------------------------------------------------------------

-- ===========================================================================
-- 031 -- ticket 25: what a playbook test asserts
--
-- Ticket 05 left the candidate shape: run one playbook alone against a fixture
-- PAIR and require that it (a) fires and produces a grounded, discriminating
-- finding on the vulnerable variant and (b) admits nothing on the secure
-- variant.  That shape is necessary and it is not sufficient, for a reason
-- ticket 17 named from the other end:
--
--   ticket 16's fixture binding is DERIVED -- `pb.finds_class in
--   fixture.classes`.  A per-playbook test bound that way runs the playbook
--   only against fixtures that contain a class the playbook itself declared.
--   The author controls both sides of the pairing.  A playbook that fires on
--   everything can declare, as its `outputs`, the one class it gets right, and
--   its test then consists entirely of the case it passes.
--
-- So the binding here is still derived -- nothing is hand-maintained, ticket
-- 10's reason -- but it is TOTAL.  `playbook_fixture_binding` returns EVERY
-- fixture in the catalogue, labelled `in` or `out`.  The `out` half is the
-- negative case, it is not optional, and the playbook's author does not write
-- it: it is every fixture authored for some other playbook.
--
-- WHAT IS ASSERTED, per side (ticket 05's three predicates, split):
--
--   grounded            both sides, every claim, categorical.  A single
--                       ungrounded claim fails the test at one repeat --
--                       ticket 16's rule, grounding is not a statistical
--                       property.
--   reproducible_here   `in` side positively (>= 1 full-credit finding),
--                       `out` side negatively (ZERO claims inside the
--                       playbook's own declared output classes).
--   discriminating      `in` side only, and only on an own pair.  On a
--                       third-party target with no secure twin it is
--                       UNEVALUABLE, and an unevaluable predicate never
--                       produces a pass.
--
-- THE ASYMMETRY that answers "may a playbook pass on recall alone":  no.  An
-- unpaired third-party target can LOWER a verdict (an ungrounded claim there is
-- still an ungrounded claim, a claim off its declaration there is still off its
-- declaration) and can never RAISE one, because `n_in` below counts own pairs
-- only.  Same shape as ticket 16's `precision = NULL, never 0`.
--
-- A: the fixture catalogue and the total binding
-- B: test runs -- runtime-counted, never model-reported
-- C: the verdict, and the three-way split pass / fail / untested
-- D: promotion -- a second guard beside 030's, not a replacement
-- E: demotion, expiry, and the integrity check
--
-- 030's chain is necessary and, on its own, promotes the wrong playbook: it
-- joins a selection to a hypothesis on (program, subject, property_class) and
-- nothing else, so every playbook kept on that subject declaring that class
-- inherits the credit.  With ticket 10's measured `p_limit = 3` that is up to
-- three playbooks per supported hypothesis.  The decoy rides along.  D is where
-- that is closed; tests/checks.sql H1 shows 030 admitting it first.
-- ===========================================================================


-- ===========================================================================
-- A -- the fixture catalogue, and the binding is COMPUTED
--
-- Ticket 16 owns the fixture catalogue's CONTENT (`catalogue.json`); this is the
-- part of it a refusal has to be able to read.  Two facts per fixture: what
-- classes it contains, and whether it has a secure twin.
-- ===========================================================================

CREATE TABLE fixtures (
    id                 text PRIMARY KEY CHECK (id ~ '^[a-z0-9][a-z0-9-]*$'),
    -- `own_pair` = one source, one VARIANT flag, two ports (ticket 05).
    -- `third_party` = no secure twin, therefore no `discriminating`.
    kind               text NOT NULL CHECK (kind IN ('own_pair','third_party')),
    source_sha256      text NOT NULL CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
    -- ticket 16's rule, carried: a third-party list without its declared
    -- conversion fraction does not exist.  "Recall 1.0 on Juice Shop" without
    -- the fraction beside it is a statement about our transcription.
    upstream_list_size integer CHECK (upstream_list_size > 0),
    converted          integer CHECK (converted >= 0),
    CONSTRAINT fixtures_third_party_declares_coverage
        CHECK (kind <> 'third_party'
               OR (upstream_list_size IS NOT NULL AND converted IS NOT NULL
                   AND converted <= upstream_list_size)),
    CONSTRAINT fixtures_own_pair_declares_no_coverage
        CHECK (kind <> 'own_pair'
               OR (upstream_list_size IS NULL AND converted IS NULL))
);

COMMENT ON TABLE fixtures IS
 'The fixture catalogue as a refusal can read it. `kind` is load-bearing twice: '
 'it decides whether `discriminating` is evaluable, and it decides whether this '
 'fixture may ever contribute to a pass.';

-- What the fixture's ground truth declares it contains.  This is the fixture
-- author's statement, and R3 below is what stops it and the playbook's
-- `outputs` quietly disagreeing.
CREATE TABLE fixture_classes (
    fixture_id     text NOT NULL REFERENCES fixtures(id) ON DELETE CASCADE,
    property_class text NOT NULL REFERENCES property_classes(id),
    PRIMARY KEY (fixture_id, property_class)
);
CREATE INDEX fixture_classes_class_idx ON fixture_classes (property_class);


-- The binding.  TOTAL over the catalogue: every fixture is returned, on one
-- side or the other.  Nothing is declared in `bb:` frontmatter -- a
-- `tested_against:` key would be ticket 10's `composes_with` again, declared
-- where it should be computed, and would additionally let an author choose the
-- fixtures their own playbook is graded on.
CREATE FUNCTION playbook_fixture_binding(p_playbook uuid)
RETURNS TABLE (fixture_id text, side text, kind text)
LANGUAGE sql STABLE AS $$
    SELECT f.id,
           CASE WHEN EXISTS (
                    SELECT 1 FROM fixture_classes fc
                      JOIN playbook_outputs po ON po.property_class = fc.property_class
                     WHERE fc.fixture_id = f.id AND po.playbook_id = p_playbook)
                THEN 'in' ELSE 'out' END,
           f.kind
      FROM fixtures f;
$$;

COMMENT ON FUNCTION playbook_fixture_binding(uuid) IS
 'Derived, like ticket 16''s, and total. The `in` half alone is the trap ticket '
 '17 named: a test whose fixtures come from the playbook''s own declared outputs '
 'is a test the author selected. The `out` half is every fixture authored for '
 'somebody else''s playbook, which is why no author can write their own negative.';


-- ===========================================================================
-- B -- test runs: runtime-counted
--
-- Every column here is a COUNT the harness produced by replaying specs against
-- a fixture it started, not a verdict a model reported.  There is no
-- `passed boolean` column on purpose: a boolean is exactly the field a model
-- could be asked to fill in, and the verdict is a function of counts (C).
-- ===========================================================================

CREATE TABLE playbook_test_runs (
    id              uuid PRIMARY KEY DEFAULT uuidv7(),
    playbook_id     uuid NOT NULL REFERENCES playbooks(id) ON DELETE CASCADE,
    -- frozen, and equal to the playbook's text at insert time (R2): a test
    -- result is a statement about a TEXT, the same way 030 makes a promotion
    -- one.  Re-text the card and every row here stops matching.
    playbook_sha256 text NOT NULL CHECK (playbook_sha256 ~ '^[0-9a-f]{64}$'),
    fixture_id      text NOT NULL REFERENCES fixtures(id) ON DELETE RESTRICT,
    fixture_sha256  text NOT NULL CHECK (fixture_sha256 ~ '^[0-9a-f]{64}$'),
    -- computed at insert, never accepted from the caller (R1)
    side            text NOT NULL CHECK (side IN ('in','out')),
    repeat_index    integer NOT NULL CHECK (repeat_index >= 0),
    -- ticket 16's run key: everything that must be equal for two rows to be
    -- repeats of one measurement.
    run_key         text NOT NULL CHECK (run_key ~ '^[0-9a-f]{12,64}$'),

    -- claims the playbook made on the vulnerable (or, third party, the only)
    -- variant
    claims            integer NOT NULL CHECK (claims >= 0),
    -- of those, the ones failing `grounded` (ticket 16's class-aware form)
    ungrounded        integer NOT NULL CHECK (ungrounded >= 0),
    -- grounded AND reproducible_here AND class IN this playbook's outputs
    fired_in_scope    integer NOT NULL CHECK (fired_in_scope >= 0),
    -- grounded AND reproducible_here AND class NOT IN this playbook's outputs.
    -- Recorded, never scored: a real finding outside the declaration is a
    -- ground-truth gap (ticket 05 section 6), not a playbook defect.
    out_of_scope      integer NOT NULL CHECK (out_of_scope >= 0),
    -- full-credit attributions that are also `discriminating`
    discriminating_tp integer NOT NULL CHECK (discriminating_tp >= 0),
    -- claims admitted on the SECURE variant.  NULL, never 0, when the fixture
    -- has no secure twin (R4) -- ticket 16's rule for an unpaired target.
    admitted_secure   integer CHECK (admitted_secure >= 0),
    -- ticket 13's cost denominator.  A model can misreport its token use in
    -- either direction; it cannot make a tool_runs row appear or disappear.
    tool_runs         integer NOT NULL CHECK (tool_runs >= 0),
    ran_at            timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT playbook_test_runs_tp_is_in_scope
        CHECK (discriminating_tp <= fired_in_scope),
    CONSTRAINT playbook_test_runs_claims_accounted
        CHECK (ungrounded + fired_in_scope + out_of_scope <= claims),
    UNIQUE (playbook_id, playbook_sha256, fixture_id, repeat_index)
);
CREATE INDEX playbook_test_runs_lookup_idx
    ON playbook_test_runs (playbook_id, playbook_sha256);

-- Ticket 35's rule 2: a table is program-scoped or it says why it is not.  A
-- fixture is code, and a test result is a statement about a playbook's text, not
-- about a program -- the same reason `playbooks` itself is global.  Declaring it
-- is the point: an undeclared table is `table_not_program_scoped`, which is how
-- a per-program leak gets noticed rather than assumed away.
INSERT INTO program_global_tables (table_name, reason) VALUES
 ('fixtures',          'a fixture is code, checked out with the harness, identical on every program'),
 ('fixture_classes',   'belongs to the fixture'),
 ('playbook_test_runs','a statement about a playbook text and a fixture text; neither is program-scoped');

INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
 ('fixture_classes',    'fixture_id',  'catalogue-scoped: a fixture''s classes die with it'),
 ('playbook_test_runs', 'playbook_id', 'catalogue-scoped: a test result is a statement about a playbook that no longer exists');


-- R1/R2/R4 -- the three things about a run row a caller does not get to choose.
CREATE FUNCTION enforce_playbook_test_run() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    computed_side text;
    fixture_kind  text;
    current_sha   text;
BEGIN
    SELECT b.side, b.kind INTO computed_side, fixture_kind
      FROM playbook_fixture_binding(NEW.playbook_id) b
     WHERE b.fixture_id = NEW.fixture_id;

    IF computed_side IS NULL THEN
        RAISE EXCEPTION 'fixture % is not in the catalogue', NEW.fixture_id
          USING ERRCODE = 'foreign_key_violation';
    END IF;

    -- R1.  The side is a function of (playbook outputs x fixture classes) and
    -- the caller's opinion of it is discarded.  Without this, filing every run
    -- as `in` deletes the negative case and the test is ticket 05's again.
    IF NEW.side IS DISTINCT FROM computed_side THEN
        RAISE EXCEPTION 'test run for % on fixture % filed as side=%, binding computes %',
            (SELECT path FROM playbooks WHERE id = NEW.playbook_id),
            NEW.fixture_id, NEW.side, computed_side
          USING DETAIL = 'the binding is derived from playbook_outputs x fixture_classes; '
                         'declaring it is how an author picks the fixtures they are graded on',
                ERRCODE = 'check_violation';
    END IF;

    -- R2.  A test is always filed against the text currently on disk.  Ticket
    -- 10 made the version the sha256 of the file; 030 made promotion a property
    -- of a text.  A test result is the same kind of thing.
    SELECT source_sha256 INTO current_sha FROM playbooks WHERE id = NEW.playbook_id;
    IF NEW.playbook_sha256 <> current_sha THEN
        RAISE EXCEPTION 'test run filed for sha % but the playbook''s text is %',
            left(NEW.playbook_sha256, 12), left(current_sha, 12)
          USING HINT = 'run the test against the text on disk; an old result does not transfer',
                ERRCODE = 'check_violation';
    END IF;

    -- R3.  A full-credit, discriminating finding of a class the fixture says it
    -- does not contain.  One of the two declarations is wrong and neither is
    -- the harness's to guess.
    IF computed_side = 'out' AND NEW.discriminating_tp > 0 THEN
        RAISE EXCEPTION 'playbook produced % discriminating finding(s) on out-side fixture %',
            NEW.discriminating_tp, NEW.fixture_id
          USING DETAIL = 'either the playbook under-declares bb:outputs (which shrinks the '
                         'fixture set it is graded on) or the fixture''s ground truth omits '
                         'a class it contains',
                ERRCODE = 'check_violation';
    END IF;

    -- R4.  No secure twin, no secure number.  NULL, never 0 -- a 0 here reads
    -- as "clean on the secure variant" for a target that has none.
    IF fixture_kind = 'third_party' AND NEW.admitted_secure IS NOT NULL THEN
        RAISE EXCEPTION 'fixture % has no secure twin; admitted_secure must be NULL, not %',
            NEW.fixture_id, NEW.admitted_secure
          USING ERRCODE = 'check_violation';
    END IF;
    IF fixture_kind = 'own_pair' AND NEW.admitted_secure IS NULL THEN
        RAISE EXCEPTION 'fixture % is a pair; the secure variant was not run', NEW.fixture_id
          USING ERRCODE = 'check_violation';
    END IF;

    RETURN NEW;
END $$;

CREATE TRIGGER a_playbook_test_run_guard
    BEFORE INSERT OR UPDATE ON playbook_test_runs
    FOR EACH ROW EXECUTE FUNCTION enforce_playbook_test_run();


-- ===========================================================================
-- C -- the verdict: pass / fail / untested
--
-- Three outcomes, not two.  `untested` exists because the derived binding makes
-- the empty case the COMMON case: ticket 16's catalogue has 3 fixtures over 5
-- property classes of 33, ticket 17 converted 7 of 60 v1 cards, and a playbook
-- whose declared output class appears in no fixture derives to an empty `in`
-- set.  Under a two-valued verdict that reads as `pass` (nothing failed), which
-- is precisely the test that cannot fail.
--
-- `untested` blocks promotion (D) and does NOT demote (E).
-- ===========================================================================

CREATE FUNCTION playbook_test_median_tp(p_playbook uuid, p_sha text, p_fixture text)
RETURNS numeric LANGUAGE sql STABLE AS $$
    SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY r.discriminating_tp)
      FROM playbook_test_runs r
     WHERE r.playbook_id = p_playbook AND r.playbook_sha256 = p_sha
       AND r.fixture_id = p_fixture;
$$;

CREATE FUNCTION playbook_test_verdict(p_playbook uuid, p_sha text DEFAULT NULL)
RETURNS TABLE (verdict text, reason text)
LANGUAGE plpgsql STABLE AS $$
DECLARE
    sha        text;
    n_in_pair  integer;
    n_out      integer;
    n_missing  integer;
    bad        text;
BEGIN
    sha := coalesce(p_sha, (SELECT source_sha256 FROM playbooks WHERE id = p_playbook));

    -- The three CATEGORICAL clauses run FIRST, ahead of the coverage checks:
    -- a playbook can fail before it is fully tested, and cannot pass before it
    -- is. A fabricated receipt is a fabricated receipt whether or not some other
    -- fixture is missing, and deferring to `untested` would let an incomplete
    -- catalogue launder observed misbehaviour into "not measured".

    -- A. grounded. Ticket 16's rule: one occurrence at one repeat, both sides.
    SELECT string_agg(DISTINCT r.fixture_id, ',') INTO bad
      FROM playbook_test_runs r
     WHERE r.playbook_id = p_playbook AND r.playbook_sha256 = sha AND r.ungrounded > 0;
    IF bad IS NOT NULL THEN
        RETURN QUERY SELECT 'fail', 'ungrounded claim on ' || bad;
        RETURN;
    END IF;

    -- B. the secure twin. Ticket 16's `pair_clean`, which never averages. This
    --    is ticket 05's clause (b) and it catches the `confused` shape -- a
    --    playbook that reports its class whatever the target returned.
    SELECT string_agg(DISTINCT r.fixture_id, ',') INTO bad
      FROM playbook_test_runs r
     WHERE r.playbook_id = p_playbook AND r.playbook_sha256 = sha
       AND coalesce(r.admitted_secure, 0) > 0;
    IF bad IS NOT NULL THEN
        RETURN QUERY SELECT 'fail', 'admits a claim on the secure variant of ' || bad;
        RETURN;
    END IF;

    -- C. the `out` side. The clause ticket 05 does not have, and the only one
    --    that catches a playbook which always fires: its claim on a fixture
    --    that does not contain its class is grounded and reproducible and
    --    simply not about anything. Note where it bites hardest -- an out-side
    --    fixture with NO secure twin, where clause (b) is structurally unable
    --    to say anything because there is no secure variant to stay quiet on.
    SELECT string_agg(DISTINCT r.fixture_id, ',') INTO bad
      FROM playbook_test_runs r
     WHERE r.playbook_id = p_playbook AND r.playbook_sha256 = sha
       AND r.side = 'out' AND r.fired_in_scope > 0;
    IF bad IS NOT NULL THEN
        RETURN QUERY SELECT 'fail',
            'fires inside its own declared classes on out-side fixture ' || bad;
        RETURN;
    END IF;

    -- 1. An `in` set of own PAIRS.  Own pairs only: a third-party `in` fixture
    --    can fail this playbook but can never satisfy it, because
    --    `discriminating` is unevaluable there.  This is the whole answer to
    --    "may a playbook pass on recall alone".
    SELECT count(*) INTO n_in_pair FROM playbook_fixture_binding(p_playbook) b
     WHERE b.side = 'in' AND b.kind = 'own_pair';
    IF n_in_pair = 0 THEN
        RETURN QUERY SELECT 'untested',
            'no own-pair fixture declares a class this playbook declares as an output';
        RETURN;
    END IF;

    -- 2. An `out` set.  With none, specificity is unmeasured and the only
    --    negative left is the secure twin -- which catches ticket 05's
    --    `confused` and not the playbook that fires on everything.
    SELECT count(*) INTO n_out FROM playbook_fixture_binding(p_playbook) b
     WHERE b.side = 'out';
    IF n_out = 0 THEN
        RETURN QUERY SELECT 'untested',
            'every fixture in the catalogue contains one of this playbook''s output classes; '
            'nothing measures whether it fires where it should not';
        RETURN;
    END IF;

    -- 3. The binding is total, so the run set must be too.  A missing fixture is
    --    not a pass on the ones that ran.
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

    -- 4. sensitivity.  STATISTICAL, so the median over repeats, ticket 16's
    --     rule: a fixture whose repeats disagree is an instrument fault, not
    --     evidence the playbook is worse.  One repeat degenerates to itself.
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
        n_in_pair || ' in-pair, ' || n_out || ' out fixture(s), all clean';
END $$;

COMMENT ON FUNCTION playbook_test_verdict(uuid, text) IS
 'pass / fail / untested. `untested` is not a soft fail and not a soft pass: it '
 'blocks promotion and does not demote. It is the common case -- most of a real '
 'catalogue declares classes no fixture contains (ticket 17: 7 of 60 cards '
 'converted; ticket 16: 5 classes of 33 across 3 fixtures).';


-- ===========================================================================
-- D -- promotion
--
-- A SECOND trigger beside 030's, not a replacement: 030's body stays where it
-- is and is not vendored here.  Trigger order is alphabetical, so
-- `a_playbook_promotion_guard` (030) runs first and this runs after -- a
-- playbook with no runtime evidence chain is still refused for that reason
-- first, which keeps 030's message on the failure it owns.
--
-- WHY THIS IS NOT REDUNDANT WITH 030.  `playbook_promotion_evidence` joins
--   playbook_selections -> hypotheses  ON (program_id, subject_entity_id,
--                                          property_class)
-- and there is no other edge between a selection and the hypothesis it caused.
-- Ticket 10 measured `p_limit = 3`, so up to three playbooks are kept on one
-- subject; every one of them declaring the supported class inherits the chain.
-- A playbook that contributed nothing is promoted by another playbook's
-- finding, and the always-fires decoy is exactly the playbook most likely to be
-- sitting in that selection set.  tests/checks.sql H1 shows 030 admitting it.
-- ===========================================================================

CREATE FUNCTION enforce_playbook_test_promotion() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v text; r text;
BEGIN
    IF NEW.promoted_at IS NULL THEN
        RETURN NEW;
    END IF;
    IF TG_OP = 'UPDATE'
       AND OLD.promoted_at   IS NOT DISTINCT FROM NEW.promoted_at
       AND OLD.source_sha256 IS NOT DISTINCT FROM NEW.source_sha256 THEN
        RETURN NEW;
    END IF;

    SELECT t.verdict, t.reason INTO v, r
      FROM playbook_test_verdict(NEW.id, NEW.source_sha256) t;

    IF v <> 'pass' THEN
        RAISE EXCEPTION 'playbook % cannot be promoted: playbook test is %', NEW.path, v
          USING DETAIL  = r,
                HINT    = CASE v
                            WHEN 'untested' THEN
                              'a fixture pair containing one of its output classes, and at '
                              'least one fixture containing none of them, must exist and '
                              'must have been run at this exact text'
                            ELSE
                              'the runtime evidence chain (030) is necessary and not '
                              'sufficient: it attributes a supported hypothesis to every '
                              'playbook kept on that subject declaring that class'
                          END,
                ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER b_playbook_test_promotion_guard
    BEFORE INSERT OR UPDATE ON playbooks
    FOR EACH ROW EXECUTE FUNCTION enforce_playbook_test_promotion();


-- ===========================================================================
-- E -- demotion, expiry, integrity
--
-- DEMOTION on `fail`, not on `untested`.  A failing test at an UNCHANGED
-- `source_sha256` means the fixture catalogue or the world moved, not the card;
-- 030 already refuses re-texting a promoted card, so the text cannot be what
-- changed.  `untested` after a pass can only arise from a fixture being ADDED,
-- and demoting the catalogue because somebody added a fixture is a rule nobody
-- would add a fixture under.  It surfaces as a warning instead.
--
-- EXPIRY is untouched.  `stale_after` is ticket 10's review DATE, evaluated at
-- selection; a green test says the playbook still works against a frozen
-- fixture, which is no evidence at all that the world it hunts has not moved.
-- The two exclusions are independent and this migration adds no path from a
-- test result to `stale_after`.  A stale playbook whose test passes is still
-- excluded by `mark_stale_selections()`, and that is reported so it is visible
-- rather than looking like a bug.
-- ===========================================================================

CREATE FUNCTION demote_failed_playbooks()
RETURNS TABLE (path text, reason text) LANGUAGE sql AS $$
    WITH failing AS (
        SELECT p.id, p.path, v.verdict, v.reason
          FROM playbooks p
          CROSS JOIN LATERAL playbook_test_verdict(p.id, p.source_sha256) v
         WHERE p.status = 'stable' AND v.verdict = 'fail'
    ), u AS (
        UPDATE playbooks p SET status = 'draft', promoted_at = NULL
          FROM failing f WHERE p.id = f.id
        RETURNING p.path, f.reason)
    SELECT * FROM u;
$$;

COMMENT ON FUNCTION demote_failed_playbooks() IS
 'Demotion is automatic and reversible; leaving a playbook stable while its test '
 'fails is what feeds bad selections. Fires on `fail` only -- `untested` is a '
 'warning, because it is what adding a fixture looks like.';


CREATE FUNCTION check_playbook_tests()
RETURNS TABLE (severity text, problem text, detail text) LANGUAGE sql STABLE AS $$
    -- HARD: a stable playbook whose test fails.  demote_failed_playbooks() is
    -- owed and has not run.
    SELECT 'error'::text, 'stable_playbook_failing'::text, p.path || ' -> ' || v.reason
      FROM playbooks p
      CROSS JOIN LATERAL playbook_test_verdict(p.id, p.source_sha256) v
     WHERE p.status = 'stable' AND v.verdict = 'fail'
UNION ALL
    -- HARD: a fixture declaring a class no vocabulary entry has is unwritable
    -- (FK), so a row here means the catalogue was bypassed.
    SELECT 'error', 'fixture_class_unknown', fc.fixture_id || ' -> ' || fc.property_class
      FROM fixture_classes fc
     WHERE NOT EXISTS (SELECT 1 FROM property_classes pc WHERE pc.id = fc.property_class)
UNION ALL
    -- WARNING: stable but no longer testable.  Almost always a fixture was
    -- added and the suite has not caught up.
    SELECT 'warning', 'stable_playbook_untested', p.path || ' -> ' || v.reason
      FROM playbooks p
      CROSS JOIN LATERAL playbook_test_verdict(p.id, p.source_sha256) v
     WHERE p.status = 'stable' AND v.verdict = 'untested'
UNION ALL
    -- WARNING: the whole catalogue's untestable tail.  This is the number that
    -- says what "every playbook needs a test" costs against a catalogue that
    -- mostly does not exist yet (ticket 17: 53 of 60 v1 cards unauthored).
    SELECT 'warning', 'draft_playbook_untestable', p.path || ' -> ' || v.reason
      FROM playbooks p
      CROSS JOIN LATERAL playbook_test_verdict(p.id, p.source_sha256) v
     WHERE p.status = 'draft' AND v.verdict = 'untested'
UNION ALL
    -- WARNING: a real finding outside the playbook's declaration.  Never scored
    -- against the playbook; it is a ground-truth gap in the FIXTURE (ticket 05
    -- section 6) and the fixture's owner is the one who has to answer it.
    SELECT 'warning', 'fixture_groundtruth_gap',
           r.fixture_id || ' <- ' || p.path || ' (' || r.out_of_scope
           || ' finding(s) outside its bb:outputs)'
      FROM playbook_test_runs r JOIN playbooks p ON p.id = r.playbook_id
     WHERE r.out_of_scope > 0
UNION ALL
    -- WARNING: test results for a text the card no longer has.  R2 makes new
    -- rows impossible, so this is the residue of a re-text -- which is exactly
    -- why the standing does not transfer.
    SELECT 'warning', 'test_run_for_superseded_text',
           p.path || ' -> ' || left(r.playbook_sha256, 12)
      FROM playbook_test_runs r JOIN playbooks p ON p.id = r.playbook_id
     WHERE r.playbook_sha256 <> p.source_sha256
     GROUP BY p.path, r.playbook_sha256
UNION ALL
    -- WARNING: passing and past its review date.  A green test is not a reason
    -- to keep selecting it; the two exclusions are independent by design.
    SELECT 'warning', 'stale_playbook_test_passing', p.path
      FROM playbooks p
      CROSS JOIN LATERAL playbook_test_verdict(p.id, p.source_sha256) v
     WHERE p.stale_after IS NOT NULL AND p.stale_after <= now() AND v.verdict = 'pass';
$$;


-- ===========================================================================
-- 8. The two registries the baseline enforces
-- ===========================================================================

-- Ticket 33's rule: a managed table either emits an event or says why not. All
-- three of these are the harness measuring itself -- a fixture is code, a test
-- run is a statement about a playbook TEXT -- and none of them is a thing that
-- happened to a target, which is what the event log is for. `bookkeeping` is
-- the same class `eval_runs` got in ticket 16, for the same reason.
INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
 ('fixtures',           'reference',   'the fixture catalogue as a refusal can read it; checked out with the harness, identical on every program', '25'),
 ('fixture_classes',    'reference',   'the fixture author''s ground-truth declaration; belongs to the fixture', '25'),
 ('playbook_test_runs', 'bookkeeping', 'one repeat of one playbook against one fixture; measurement of the system against code we wrote, not knowledge about a target', '25');

-- 031 defined `check_playbook_tests()` and nothing ran it. The errors are the
-- two conditions that make a selection unsafe rather than merely untidy: a
-- stable playbook whose test fails (`demote_failed_playbooks()` is owed and has
-- not run), and a fixture declaring a class the vocabulary does not contain.
-- The five warnings are deliberately not registered -- an unmeasured playbook is
-- a gap in coverage, not a broken invariant, and a standing check that is
-- allowed to be noisy stops being read.
INSERT INTO standing_checks (name, query, owner_ticket, note) VALUES
 ('playbook_tests',
  'SELECT * FROM check_playbook_tests() WHERE severity = ''error''',
  '25',
  'no stable playbook is selected while its own test fails, and no fixture declares a class the vocabulary does not have');
