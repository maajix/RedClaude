-- ---------------------------------------------------------------------------
-- 20260807T191600Z__ticket16_eval_store.sql   (ticket 16 -- the eval store)
--
-- Was `028_ticket16_eval_store.sql` on branch prototype/eval-metrics. What the
-- fold changed:
--
--   * 028 ended with a DO block that ran `check_program_isolation()` and raised
--     if it returned anything. On its branch nothing else would have. Ticket 33
--     made it a `standing_checks` row that runs at the end of every `up`, over
--     the whole corpus rather than over one migration, so the local copy is
--     removed rather than kept as a second place for the same rule.
--   * 028 classified none of its four tables for emission (section Z below).
--   * 028 registered four cascade edges and has five cascading foreign keys.
--     `eval_fn_attribution.near_match_id` cascades and was not declared; ticket
--     07 check (e) reads `conkey[1]`, so the missing row is a real hole and not
--     a formality. Added below.
--   * No RLS block and no grants, and none are added: `apply_state_rls()` is a
--     finalizer, and 028 published nothing to `rk2_state` -- an eval score is a
--     measurement of the hunter, and letting the hunter read it is the one thing
--     that would make the measurement worthless.
-- ---------------------------------------------------------------------------


SET client_min_messages = notice;


-- ===========================================================================
-- One run of one system under test, over one fixture catalogue
-- ===========================================================================

-- `run_key` is the sha256 of everything that must be equal for two runs to be
-- repeats of the same measurement (catalogue, fixture app, ground truth,
-- grading.py, metrics.py, playbook set, sut, config). `key_components` keeps
-- the pre-image so two runs that differ can be told WHERE they differ --
-- ticket 30 compares a run with a switch against the same run without it, and
-- a bare hash can only say "not equal".
CREATE TABLE eval_runs (
    id              uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id      uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    run_key         text NOT NULL,
    repeat_index    integer NOT NULL DEFAULT 0 CHECK (repeat_index >= 0),
    key_components  jsonb NOT NULL,
    sut             text NOT NULL,
    config          jsonb NOT NULL DEFAULT '{}'::jsonb,
    weights_version text,
    started_at      timestamptz NOT NULL DEFAULT now(),
    finished_at     timestamptz,
    UNIQUE (id, program_id),
    UNIQUE (program_id, run_key, repeat_index)
);

COMMENT ON COLUMN eval_runs.weights_version IS
  'The scheduler policy version in force (ticket 08). A score computed under a different ranking policy is not comparable with one computed under this policy, and the version is the only thing that says so.';


-- ===========================================================================
-- One (fixture, run) pair -- the unit everything is reported at
-- ===========================================================================

CREATE TABLE eval_pair_scores (
    id                  uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id          uuid NOT NULL,
    eval_run_id         uuid NOT NULL,
    fixture_id          text NOT NULL,
    fixture_kind        text NOT NULL
                        CHECK (fixture_kind IN ('own_pair', 'third_party')),

    -- the two denominators, kept apart on purpose: `gt_declared` is what the
    -- fixture claims to contain, `gt_recallable` is what a hunter behind the
    -- proxy could possibly be charged with. Ticket 24's unmakeable classes are
    -- the difference, and burying them in one number is how a hunter gets
    -- marked down for not proving something the transport cannot express.
    gt_declared         integer NOT NULL CHECK (gt_declared >= 0),
    gt_recallable       integer NOT NULL CHECK (gt_recallable >= 0),

    tp                  integer NOT NULL DEFAULT 0 CHECK (tp >= 0),
    fp                  integer NOT NULL DEFAULT 0 CHECK (fp >= 0),
    duplicate           integer NOT NULL DEFAULT 0 CHECK (duplicate >= 0),
    unattributed_real   integer NOT NULL DEFAULT 0 CHECK (unattributed_real >= 0),

    fn_not_found        integer NOT NULL DEFAULT 0 CHECK (fn_not_found >= 0),
    fn_unproven         integer NOT NULL DEFAULT 0 CHECK (fn_unproven >= 0),
    fn_suppressed       integer NOT NULL DEFAULT 0 CHECK (fn_suppressed >= 0),
    fn_near_miss        integer NOT NULL DEFAULT 0 CHECK (fn_near_miss >= 0),

    recall_strict       numeric CHECK (recall_strict BETWEEN 0 AND 1),
    precision_strict    numeric CHECK (precision_strict BETWEEN 0 AND 1),
    false_positive_rate numeric CHECK (false_positive_rate BETWEEN 0 AND 1),
    pair_clean          boolean,

    tool_runs           integer NOT NULL DEFAULT 0 CHECK (tool_runs >= 0),
    converted_fraction  numeric CHECK (converted_fraction BETWEEN 0 AND 1),

    UNIQUE (id, program_id),
    UNIQUE (eval_run_id, fixture_id),
    FOREIGN KEY (eval_run_id, program_id)
        REFERENCES eval_runs (id, program_id) ON DELETE CASCADE,

    CONSTRAINT eval_recallable_le_declared
        CHECK (gt_recallable <= gt_declared),

    -- R1. The buckets partition the recallable denominator. Every ground-truth
    -- entry is found, or missing for exactly one nameable reason.
    CONSTRAINT eval_gt_accounting
        CHECK (tp + fn_not_found + fn_unproven + fn_suppressed + fn_near_miss
               = gt_recallable),

    -- R2. No secure variant, no precision. NULL is not 0.
    CONSTRAINT eval_third_party_has_no_precision
        CHECK (fixture_kind <> 'third_party'
               OR (precision_strict IS NULL
                   AND false_positive_rate IS NULL
                   AND pair_clean IS NULL)),

    -- ... and an own pair always has one, because a pair that cannot be
    -- scored for precision is a broken fixture, not a third-party target.
    CONSTRAINT eval_own_pair_is_scorable
        CHECK (fixture_kind <> 'own_pair' OR pair_clean IS NOT NULL),

    -- R3. Third-party recall is recall over the converted subset, and the
    -- fraction travels with it or the row does not exist.
    CONSTRAINT eval_third_party_declares_coverage
        CHECK ((fixture_kind = 'third_party') = (converted_fraction IS NOT NULL))
);

COMMENT ON TABLE eval_pair_scores IS
  'One (run, fixture) pair. Ticket 05''s decision: pairs are never averaged into a single suite score inside the database. eval_recall_by_kind() groups by kind so pooling own-fixture and third-party numbers is not expressible, and eval_precision() raises rather than return a mixed mean.';


-- ===========================================================================
-- Why each missing entry is missing, and who owns it
-- ===========================================================================

-- Citing ticket 08's row across the program boundary needs the sibling key 017
-- adds wherever a program-scoped row is referenced. Nothing referenced
-- `hypothesis_near_matches` before this file, so it does not have one yet;
-- adding it is additive and changes no existing behaviour (017's own idiom,
-- copied verbatim from its `test_runs_id_program_key` block).
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conname = 'hypothesis_near_matches_id_program_key'
                      AND conrelid = 'hypothesis_near_matches'::regclass) THEN
        ALTER TABLE hypothesis_near_matches
            ADD CONSTRAINT hypothesis_near_matches_id_program_key
            UNIQUE (id, program_id);
    END IF;
END $$;

CREATE TABLE eval_fn_attribution (
    id            uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id    uuid NOT NULL,
    pair_score_id uuid NOT NULL,
    gt_id         text NOT NULL,
    bucket        text NOT NULL CHECK (bucket IN ('fn_not_found', 'fn_unproven',
                                                  'fn_suppressed', 'fn_near_miss')),
    owner         text NOT NULL CHECK (owner IN ('hunter', 'harness', 'scheduler')),
    near_match_id uuid,
    detail        text NOT NULL DEFAULT '',

    UNIQUE (id, program_id),
    UNIQUE (pair_score_id, gt_id),
    FOREIGN KEY (pair_score_id, program_id)
        REFERENCES eval_pair_scores (id, program_id) ON DELETE CASCADE,
    -- ON DELETE CASCADE, not NO ACTION, and the purge is why: the near-match row
    -- is immutable outside a purge session, so this key can only ever fire
    -- during a whole-program delete -- where NO ACTION aborts the purge instead
    -- of clearing it (found by S8, which is what S8 is for). Cascading is also
    -- the right semantic: R4 makes the citation load-bearing, so an attribution
    -- whose proof is gone must go with it rather than survive as an orphan.
    FOREIGN KEY (near_match_id, program_id)
        REFERENCES hypothesis_near_matches (id, program_id) ON DELETE CASCADE,

    -- R4. `fn_suppressed` means stage-2 dedup merged the candidate into an
    -- existing hypothesis. That is a claim about the scheduler, so it cites the
    -- scheduler's own row -- and no other bucket may cite one, because a row
    -- that exists does not excuse a hunter that never proposed anything.
    CONSTRAINT eval_suppression_cites_the_row
        CHECK ((bucket = 'fn_suppressed') = (near_match_id IS NOT NULL)),

    -- The bucket determines the owner. Splitting false negatives was pointless
    -- if the split could still be filed against whoever is convenient.
    CONSTRAINT eval_bucket_owns
        CHECK ((bucket = 'fn_suppressed' AND owner = 'scheduler')
            OR (bucket = 'fn_unproven'   AND owner = 'harness')
            OR (bucket IN ('fn_not_found', 'fn_near_miss') AND owner = 'hunter'))
);


-- ===========================================================================
-- Coverage, in ticket 27's unit
-- ===========================================================================

-- Ticket 27 measured it: the family is 2.6x more discriminating than the leaf,
-- and a coverage figure over 33 leaves has a 0.24 range that ranks nothing.
-- The family_id is a foreign key, so a fixture cannot be filed under a ninth
-- family by typo, and the denominator below is a count of 018's rows.
CREATE TABLE eval_family_coverage (
    id          uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id  uuid NOT NULL,
    eval_run_id uuid NOT NULL,
    family_id   text NOT NULL REFERENCES property_class_families (id),
    gt_entries  integer NOT NULL DEFAULT 0 CHECK (gt_entries >= 0),
    found       integer NOT NULL DEFAULT 0 CHECK (found >= 0),

    UNIQUE (id, program_id),
    UNIQUE (eval_run_id, family_id),
    FOREIGN KEY (eval_run_id, program_id)
        REFERENCES eval_runs (id, program_id) ON DELETE CASCADE,
    CONSTRAINT eval_found_le_entries CHECK (found <= gt_entries)
);


-- ===========================================================================
-- The program of a derived row is a consequence of its owner (017's idiom)
-- ===========================================================================

CREATE TRIGGER eval_pair_scores_program
    BEFORE INSERT ON eval_pair_scores FOR EACH ROW
    EXECUTE FUNCTION derive_program_id('eval_run_id', 'eval_runs', 'id');

CREATE TRIGGER eval_fn_attribution_program
    BEFORE INSERT ON eval_fn_attribution FOR EACH ROW
    EXECUTE FUNCTION derive_program_id('pair_score_id', 'eval_pair_scores', 'id');

CREATE TRIGGER eval_family_coverage_program
    BEFORE INSERT ON eval_family_coverage FOR EACH ROW
    EXECUTE FUNCTION derive_program_id('eval_run_id', 'eval_runs', 'id');

INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
    ('eval_runs',           'program_id',    'program-scoped: the purge root'),
    ('eval_pair_scores',    'eval_run_id',   'a score belongs to the run that produced it'),
    ('eval_fn_attribution', 'pair_score_id', 'an attribution belongs to the score it explains'),
    ('eval_family_coverage','eval_run_id',   'coverage belongs to the run it was measured over');


-- ===========================================================================
-- Reading the scores: the aggregations that are allowed, and the one that is not
-- ===========================================================================

-- Recall pools across kinds -- it is the same question either side -- but the
-- shape forces the coverage fraction to be printed next to the third-party
-- half, so nobody quotes 1.0 without the 0.33 that qualifies it.
CREATE FUNCTION eval_recall_by_kind(p_program uuid, p_run_key text)
RETURNS TABLE (fixture_kind text, pairs integer, recall numeric,
               converted_fraction numeric)
LANGUAGE sql STABLE AS $$
    SELECT s.fixture_kind,
           count(*)::integer,
           round(avg(s.recall_strict), 4),
           round(avg(s.converted_fraction), 4)
      FROM eval_pair_scores s
      JOIN eval_runs r ON r.id = s.eval_run_id AND r.program_id = s.program_id
     WHERE r.program_id = p_program AND r.run_key = p_run_key
     GROUP BY s.fixture_kind
     ORDER BY s.fixture_kind
$$;

-- Precision does not pool. It refuses.
CREATE FUNCTION eval_precision(p_program uuid, p_run_key text) RETURNS numeric
LANGUAGE plpgsql STABLE AS $$
DECLARE v_unpaired integer; v_value numeric;
BEGIN
    SELECT count(*) INTO v_unpaired
      FROM eval_pair_scores s
      JOIN eval_runs r ON r.id = s.eval_run_id AND r.program_id = s.program_id
     WHERE r.program_id = p_program AND r.run_key = p_run_key
       AND s.fixture_kind <> 'own_pair';

    IF v_unpaired > 0 THEN
        RAISE EXCEPTION 'refusing to aggregate precision over % unpaired pair(s) '
                        'in run_key %: an unpaired target has no secure variant, '
                        'so its precision is unevaluable, and averaging it as 0 '
                        'reads as a precision regression caused by adding the '
                        'target (ticket 16, R2)', v_unpaired, p_run_key;
    END IF;

    SELECT round(avg(s.precision_strict), 4) INTO v_value
      FROM eval_pair_scores s
      JOIN eval_runs r ON r.id = s.eval_run_id AND r.program_id = s.program_id
     WHERE r.program_id = p_program AND r.run_key = p_run_key;
    RETURN v_value;
END $$;

-- The denominator is a row count of 018's families, never a literal.
CREATE FUNCTION eval_family_coverage_of(p_run uuid) RETURNS numeric
LANGUAGE sql STABLE AS $$
    SELECT round((SELECT count(*) FROM eval_family_coverage
                   WHERE eval_run_id = p_run AND found > 0)::numeric
                 / (SELECT count(*) FROM property_class_families), 4)
$$;

-- Two runs are comparable only if everything outside `p_varying` is equal.
-- This is ticket 30's precondition, in the database rather than in the job that
-- happens to compute the delta.
CREATE FUNCTION eval_key_diff(p_a uuid, p_b uuid)
RETURNS TABLE (component text, a text, b text)
LANGUAGE sql STABLE AS $$
    SELECT k, a.key_components ->> k, b.key_components ->> k
      FROM eval_runs a, eval_runs b,
           LATERAL (SELECT DISTINCT jsonb_object_keys(a.key_components || b.key_components)) AS ks(k)
     WHERE a.id = p_a AND b.id = p_b
       AND a.key_components ->> k IS DISTINCT FROM b.key_components ->> k
     ORDER BY k
$$;

CREATE FUNCTION eval_comparable(p_a uuid, p_b uuid, p_varying text[])
RETURNS void LANGUAGE plpgsql STABLE AS $$
DECLARE v_extra text[]; v_diff text[];
BEGIN
    SELECT coalesce(array_agg(component ORDER BY component), '{}')
      INTO v_diff FROM eval_key_diff(p_a, p_b);
    SELECT coalesce(array_agg(c ORDER BY c), '{}') INTO v_extra
      FROM unnest(v_diff) c WHERE NOT (c = ANY (p_varying));

    IF cardinality(v_extra) > 0 THEN
        RAISE EXCEPTION 'runs differ in %, which must be held fixed: a delta '
                        'across them attributes the change to the wrong cause '
                        '(ticket 30)', v_extra;
    END IF;
    IF cardinality(v_diff) = 0 THEN
        RAISE EXCEPTION 'runs are repeats of one measurement, not a comparison: '
                        'no component of the run key differs';
    END IF;
END $$;


-- ===========================================================================
-- Z -- what the corpus requires: emission, and the purge edge 028 missed
-- ===========================================================================

-- Nothing here emits. The event log is the record of what the system LEARNED
-- about a program; these four tables record how well it did at learning, which
-- is a fact about the harness. An `eval.scored` event would put the grader's
-- opinion of a run inside the log the grader is grading.
INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
 ('eval_runs',            'bookkeeping', 'a run of the eval harness against a fixture; measurement of the system, not knowledge about a target', '16'),
 ('eval_pair_scores',     'bookkeeping', 'the score of one (fixture, run) pair; recomputable from the run and its ground truth, and about the harness either way', '16'),
 ('eval_fn_attribution',  'bookkeeping', 'why one ground-truth entry was missed and who owns it; a statement about the harness', '16'),
 ('eval_family_coverage', 'bookkeeping', 'coverage of the run in ticket 27''s unit; derived from the same measurement', '16');

-- The fifth cascading key. 028 declared the four that hang off the run and
-- missed the one that cites ticket 08's row -- the same key its own comment
-- argues hardest for, because R4 makes the citation load-bearing.
INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
 ('eval_fn_attribution', 'near_match_id',
  'R4: fn_suppressed cites the near-match row that suppressed it; if the proof is purged the attribution goes with it rather than surviving as an unsupported blame');
