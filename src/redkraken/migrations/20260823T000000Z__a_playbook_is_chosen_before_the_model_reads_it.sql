-- ---------------------------------------------------------------------------
-- ph2-45   A Playbook is chosen before the model reads it
--
-- Ticket 45. 032 built the selection machinery and left the catalogue empty:
-- `select_playbooks()` has been a correct function over zero rows since it
-- applied, and nothing in the tree could write one. `src/redkraken/playbooks/`
-- is now the statement of what a Playbook is, and this file is the database's
-- copy of it -- with, as with the Skill corpus, everything here existing so that
-- copy can be checked rather than trusted.
--
-- Six things happen.
--
--   1. `playbooks` grows the two columns criterion 1 asks for and loses one it
--      never had a meaning for. `provenance` is where the Playbook came from,
--      and `version` is the digest of the *projection* -- what the model was
--      handed -- beside `source_sha256`, which is the document. The two move
--      independently and that is the point: editing a maintainer reference
--      moves neither, editing the review date moves the document and not the
--      projection, editing the body moves both.
--
--   2. `playbook_references` records the human-only material. It is recorded so
--      a maintainer can find it and it is deliberately not published to
--      `rk2_state`, which is criterion 2's "structurally absent from the model
--      projection while remaining linked for maintainers" in the one form that
--      does not rely on a filter somebody could forget.
--
--   3. `dropped_because` becomes a foreign key. 032 wrote free text into it and
--      `select_playbooks()` produced exactly one value, `'conflicts_with:'||path`
--      -- a typed reason and its subject concatenated into a string nothing can
--      group by. The reason is now a vocabulary row and the subject is its own
--      column, which is criterion 5.
--
--   4. `playbook_candidates()` states the metadata rules once and returns the
--      reason each excluded playbook was excluded for. `playbooks_by_metadata()`
--      becomes the survivors of it. 032 had the rules as seven anonymous
--      conjuncts in a WHERE clause: correct, and unable to say why anything was
--      missing.
--
--   5. `record_playbook_selection()` writes the selection down -- kept rows and
--      dropped rows both -- and freezes the Skill hashes beside the Playbook
--      hashes. A pair of triggers makes the frozen columns frozen: they are
--      filled from the catalogue at insert and refused at update, so criterion
--      4's "later edits cannot change what a running Agent received" is a
--      property of the table rather than a discipline of its writers.
--
--   6. The corpus, as rows: one Playbook, `playbooks/object-ownership`.
--
-- What this file deliberately does not do is refuse an expired Playbook at
-- import. `stale_after` is a review date; a corpus that refused to load on the
-- day it passed would stop `rk` from running because a document needed reading.
-- Expiry is a selection-time exclusion with a typed reason, plus a suite test
-- that fails on the day, which is the only version of a review date that gets
-- read.
-- ---------------------------------------------------------------------------


-- ===========================================================================
-- 1. What a Playbook declares
-- ===========================================================================

ALTER TABLE playbooks
    ADD COLUMN version    text CHECK (version ~ '^[0-9a-f]{64}$'),
    ADD COLUMN provenance text CHECK (provenance <> '');

COMMENT ON COLUMN playbooks.version IS
    'sha256 of the model projection: the path, description, output classes, '
    'required skills, risk, effects, baseline, evidence expectations and body, '
    'canonicalised as sorted JSON. Distinct from `source_sha256`, which is the '
    'document. A Playbook''s reference material and review date are in the '
    'document and not in the projection, so editing them moves one digest and '
    'not the other -- which is what makes "did the Agent see different text" a '
    'question with an answer.';

COMMENT ON COLUMN playbooks.provenance IS
    'Where the Playbook came from, in one line: the ticket, the upstream card, '
    'the write-up. One line because it is where a maintainer starts looking, '
    'not a citation format -- the argument goes in a reference file.';

-- `okf_type` came from the v1 prototype and arrived here in 032 unchanged: a
-- NOT NULL free-text discriminator with no vocabulary, no reader, no comment
-- and no definition anywhere in the tree. Criterion 1 enumerates what a
-- Playbook declares and this is not on the list, so the choice was between
-- inventing a meaning for it at the moment the catalogue gets its first row, or
-- removing it while removing it is still free. The catalogue is empty; it is
-- free now and it is not free later.
DELETE FROM state_read_surface
 WHERE table_name = 'playbooks' AND column_name = 'okf_type';
ALTER TABLE playbooks DROP COLUMN okf_type;


-- ===========================================================================
-- 2. The material the model never gets
-- ===========================================================================

-- A Playbook's reference files are written for a person deciding whether the
-- Playbook is still right: the failure it was written against, why a control
-- row is required, what the review date means. None of it helps a model hunt,
-- and a model that read it would be relitigating a decision the runtime already
-- made.
--
-- So the rows exist, the digests exist, and there is no grant to `rk2_state`
-- and no `state_read_surface` entry below. The compiler enforces the same thing
-- from the other side by having nowhere on the projection to put the text.
CREATE TABLE playbook_references (
    playbook_id uuid NOT NULL REFERENCES playbooks(id) ON DELETE CASCADE,
    name        text NOT NULL CHECK (name ~ '^[a-z0-9][a-z0-9_.-]*$'),
    path        text NOT NULL UNIQUE CHECK (path ~ '^playbooks/[a-z0-9][a-z0-9/_-]*\.md$'),
    sha256      text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    PRIMARY KEY (playbook_id, name)
);

COMMENT ON TABLE playbook_references IS
    'Ticket 45 criterion 2: human-only material, linked and hashed for a '
    'maintainer, absent from every surface a model reads. Not published to '
    'rk2_state on purpose -- the projection has no field it could occupy and '
    'the read surface has no row that would let it arrive another way.';


-- ===========================================================================
-- 3. Why a Playbook was not selected, as a value rather than a sentence
-- ===========================================================================

CREATE TABLE playbook_drop_reasons (
    id          text PRIMARY KEY CHECK (id ~ '^[a-z][a-z0-9_]*$'),
    label       text NOT NULL CHECK (label <> ''),
    -- Whether the reason is decided about the Playbook alone, or about it
    -- against the set already kept. The two stages answer different questions
    -- and a reader that cannot tell them apart will read a cap as a filter.
    stage       text NOT NULL CHECK (stage IN ('metadata','assembly')),
    description text NOT NULL CHECK (description <> '')
);

COMMENT ON TABLE playbook_drop_reasons IS
    'The closed vocabulary a selection reports itself in. A dropped Playbook '
    'names one of these ids rather than a sentence, so the question "why was '
    'nothing selected" is answered by grouping rather than by reading prose.';

INSERT INTO playbook_drop_reasons (id, label, stage, description) VALUES
 ('status_deprecated', 'Deprecated', 'metadata',
  'the Playbook is retired; its text is kept so an old selection still resolves'),
 ('expired', 'Past review', 'metadata',
  'stale_after has passed, so nobody has confirmed the Playbook still matches the surface'),
 ('risk_forbidden', 'Forbidden', 'metadata',
  'the Playbook''s own risk floor is forbidden: the runtime does not run it at any ceiling'),
 ('risk_above_ceiling', 'Above ceiling', 'metadata',
  'the Playbook''s risk floor is higher than the autonomy ceiling this selection was made under'),
 ('class_mismatch', 'Wrong class', 'metadata',
  'the Playbook produces no Property class under the one asked for'),
 ('role_lacks_skill', 'Skill not loadable', 'metadata',
  'the role that would run it cannot load every Skill it needs, which is a load-time error and not a runtime escalation'),
 ('exhausted', 'Already exhausted', 'metadata',
  'a previous selection ran this Playbook against this subject and found nothing left to ask'),
 ('conflicts_with', 'Conflicts', 'assembly',
  'a Playbook already kept mutates what this one needs held still; dropped_detail names it'),
 ('over_cap', 'Over the cap', 'assembly',
  'the Playbook survived every filter and the small cap was already full');

ALTER TABLE playbook_selections
    ADD COLUMN playbook_version text CHECK (playbook_version ~ '^[0-9a-f]{64}$'),
    -- The subject of the reason, when the reason has one. `conflicts_with` is
    -- the only one that does, and 032 spelled it by concatenating the path onto
    -- the reason -- which made the pair unreadable from SQL in both directions.
    ADD COLUMN dropped_detail text CHECK (dropped_detail <> ''),
    ADD CONSTRAINT playbook_selections_dropped_because_fkey
        FOREIGN KEY (dropped_because) REFERENCES playbook_drop_reasons(id),
    ADD CONSTRAINT playbook_selections_detail_belongs_to_a_drop
        CHECK (dropped_detail IS NULL OR dropped_because IS NOT NULL),
    ADD CONSTRAINT playbook_selections_conflict_names_the_other
        CHECK (dropped_because IS DISTINCT FROM 'conflicts_with' OR dropped_detail IS NOT NULL),
    -- A kept row has a rank and a dropped row has none. 032 had the outcome
    -- half of this and not the rank half, so a dropped row could carry a
    -- position in a list it is not in.
    ADD CONSTRAINT playbook_selections_rank_means_kept
        CHECK ((rank IS NULL) = (dropped_because IS NOT NULL)),
    -- The target of `playbook_selection_skills`' composite key below, which is
    -- what keeps a frozen Skill hash inside the program its selection belongs to.
    ADD CONSTRAINT playbook_selections_id_program_key UNIQUE (id, program_id);

COMMENT ON COLUMN playbook_selections.playbook_version IS
    'The projection digest at selection, beside the document digest 032 froze. '
    'The pair answers the two different questions an audit asks: was this the '
    'same document, and was this the same text the model read.';

COMMENT ON COLUMN playbook_selections.dropped_detail IS
    'What the drop reason was about, when it is about something: the path of '
    'the other Playbook, for conflicts_with. Kept apart from dropped_because '
    'so that grouping by reason and naming the other side are two reads and '
    'not one string a caller has to take apart.';


-- ===========================================================================
-- 4. The Skill hashes, frozen onto the selection
-- ===========================================================================

-- Criterion 4. `playbook_skills.skill_sha256_at_promotion` is the catalogue's
-- record of what a Skill looked like when the Playbook was promoted, which is a
-- fact about the corpus. This is the run's record of what it looked like when
-- an Agent actually loaded it, which is a fact about one mission -- and the two
-- differ precisely when a Skill was edited between promotion and use, which is
-- the case the criterion exists for.
CREATE TABLE playbook_selection_skills (
    selection_id  uuid NOT NULL,
    program_id    uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    skill_name    text NOT NULL REFERENCES skills(name) ON DELETE RESTRICT,
    skill_sha256  text CHECK (skill_sha256 ~ '^[0-9a-f]{64}$'),
    skill_version text CHECK (skill_version ~ '^[0-9a-f]{64}$'),
    PRIMARY KEY (selection_id, skill_name),
    FOREIGN KEY (selection_id, program_id)
        REFERENCES playbook_selections (id, program_id) ON DELETE CASCADE
);

COMMENT ON TABLE playbook_selection_skills IS
    'Ticket 45 criterion 4: the Skill text and dependency digests as they stood '
    'when this selection was made. Nullable because 032''s `skills` predates '
    'the corpus and a registry row with no file behind it has nothing to '
    'freeze; `check_playbook_integrity` reports a kept selection that froze '
    'nothing at all.';

CREATE TRIGGER playbook_selection_skills_immutable
    BEFORE UPDATE OR DELETE ON playbook_selection_skills
    FOR EACH ROW EXECUTE FUNCTION reject_mutation_unless_purging();


-- ===========================================================================
-- 5. What the catalogue offers this subject, and why the rest is missing
-- ===========================================================================

-- The metadata stage, stated once, with the reason attached. Every row the
-- trigger stage produced comes back: the survivors with a NULL reason, the rest
-- with the first rule that excluded them.
--
-- Ordered rather than arbitrary: a playbook can fail several rules at once, and
-- a reason that depended on which conjunct the planner evaluated first would be
-- a different sentence on two runs of the same query. The order runs from what
-- the Playbook says about itself, through what this selection asked for, to
-- what has already happened on this subject.
--
-- The trigger stage is not represented here. A Playbook whose facts the subject
-- does not carry is not a Playbook that was dropped -- it is one that is about
-- something else, and there are as many of those as there are Playbooks.
-- `playbook_funnel.after_trigger` is where that count lives.
-- `risk_rank` answers NULL for a string that is not a risk class, and a
-- comparison against NULL is unknown rather than false. So a misspelt ceiling
-- would not drop a single Playbook: `risk_above_ceiling` would be unreachable
-- and the stage that exists to hold the run under an authority would pass
-- everything. Refused instead, and refused in one place because both the stage
-- and the assembly take the argument.
CREATE FUNCTION reject_unrunnable_ceiling(p_ceiling text) RETURNS void
LANGUAGE plpgsql IMMUTABLE AS $$
BEGIN
    IF risk_rank(p_ceiling) IS NULL OR p_ceiling = 'forbidden' THEN
        RAISE EXCEPTION 'autonomy ceiling % is not a runtime risk class', p_ceiling;
    END IF;
END $$;

COMMENT ON FUNCTION reject_unrunnable_ceiling(text) IS
    'Ticket 45 criterion 3: a ceiling a run cannot operate under is refused '
    'rather than compared against. `forbidden` is a class no run holds, and '
    'anything else is not a class at all -- both would otherwise read as a '
    'ceiling that excludes nothing.';

CREATE FUNCTION playbook_candidates(
        p_program uuid, p_subject uuid, p_property_class text DEFAULT NULL,
        p_role text DEFAULT 'web_hunter', p_ceiling text DEFAULT 'constrained')
RETURNS TABLE (playbook_id uuid, path text, status text, specificity integer,
               dropped_because text)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    PERFORM reject_unrunnable_ceiling(p_ceiling);
    RETURN QUERY
    SELECT p.id, p.path, p.status, p.specificity,
           CASE
             WHEN p.status = 'deprecated' THEN 'status_deprecated'
             WHEN p.stale_after IS NOT NULL AND p.stale_after <= now() THEN 'expired'
             WHEN p.risk = 'forbidden' THEN 'risk_forbidden'
             WHEN risk_rank(p.risk) > risk_rank(p_ceiling) THEN 'risk_above_ceiling'
             WHEN p_property_class IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM playbook_outputs o
                               WHERE o.playbook_id = p.id
                                 AND (o.property_class = p_property_class
                                      -- 018's own spelling of a family name
                                      OR (p_property_class ~ '^[a-z_]+$'
                                          AND o.property_class LIKE p_property_class || '.%')))
                  THEN 'class_mismatch'
             WHEN EXISTS (SELECT 1 FROM playbook_skills ps
                           WHERE ps.playbook_id = p.id
                             AND NOT EXISTS (SELECT 1 FROM role_skills rs
                                              WHERE rs.role = p_role
                                                AND rs.skill_name = ps.skill_name))
                  THEN 'role_lacks_skill'
             WHEN EXISTS (SELECT 1 FROM playbook_selections s
                           WHERE s.program_id = p_program
                             AND s.subject_entity_id = p_subject
                             AND s.playbook_id = p.id
                             AND s.outcome = 'exhausted')
                  THEN 'exhausted'
           END
      FROM playbooks p
     WHERE p.id IN (SELECT playbooks_by_trigger(p_program, p_subject));
END $$;

COMMENT ON FUNCTION playbook_candidates(uuid, uuid, text, text, text) IS
    'Ticket 45 criterion 5: the metadata stage with its reasons. One row per '
    'Playbook the subject''s facts matched; dropped_because is NULL for the '
    'ones that survive and a playbook_drop_reasons id for the ones that do '
    'not. The rules are here and nowhere else -- playbooks_by_metadata is the '
    'survivors of this, so the filter and the explanation cannot drift.';

-- Now the survivors of the above rather than a second copy of the rules. Same
-- signature and same result as 032's, which is what lets this replace it.
CREATE OR REPLACE FUNCTION playbooks_by_metadata(
        p_program uuid, p_subject uuid, p_property_class text,
        p_role text, p_ceiling text)
RETURNS SETOF uuid LANGUAGE sql STABLE AS $$
    SELECT c.playbook_id
      FROM playbook_candidates(p_program, p_subject, p_property_class, p_role, p_ceiling) c
     WHERE c.dropped_because IS NULL;
$$;

-- Two extra output columns, so the old shape has to go first.
DROP FUNCTION playbook_funnel(uuid, uuid, text, text, text, integer);
DROP FUNCTION select_playbooks(uuid, uuid, text, text, text, integer);

CREATE FUNCTION select_playbooks(
        p_program uuid, p_subject uuid, p_property_class text DEFAULT NULL,
        p_role text DEFAULT 'web_hunter', p_ceiling text DEFAULT 'constrained',
        p_limit integer DEFAULT 3)
RETURNS TABLE (playbook_id uuid, path text, rank integer,
               dropped_because text, dropped_detail text)
LANGUAGE plpgsql STABLE AS $$
DECLARE
    r        record;
    kept     uuid[] := '{}';
    n        integer := 0;
    c        uuid;
    conflict text;
BEGIN
    PERFORM reject_unrunnable_ceiling(p_ceiling);
    IF p_limit < 1 THEN
        -- A cap of zero is a call that asks for a selection and forbids one.
        -- 032 returned an empty set for it, which reads exactly like a subject
        -- nothing matched.
        RAISE EXCEPTION 'a selection cap of % keeps nothing', p_limit;
    END IF;
    FOR r IN
        SELECT k.playbook_id, k.path, k.status, k.specificity, k.dropped_because
          FROM playbook_candidates(p_program, p_subject,
                                   p_property_class, p_role, p_ceiling) k
         -- Deterministic and total, so two runs of the same surface hand the
         -- model the same set. Dropped rows sort last and among themselves by
         -- path: they are output, not input, and letting them into the greedy's
         -- order would make the cap depend on how many were excluded.
         ORDER BY (k.dropped_because IS NOT NULL),
                  (k.status = 'stable') DESC, k.specificity DESC, k.path
    LOOP
        -- The assembly stage, as a verdict on one candidate rather than four
        -- exits. Every branch below decides `dropped_because`; the row is built
        -- and emitted once, at the bottom, so a reason can never be added
        -- without the rank that goes with it.
        dropped_because := r.dropped_because;
        dropped_detail := NULL;

        IF dropped_because IS NULL THEN
            conflict := NULL;
            FOREACH c IN ARRAY kept LOOP
                IF playbooks_conflict(r.playbook_id, c) THEN
                    SELECT p2.path INTO conflict FROM playbooks p2 WHERE p2.id = c;
                    EXIT;
                END IF;
            END LOOP;
            IF conflict IS NOT NULL THEN
                dropped_because := 'conflicts_with';
                dropped_detail := conflict;
            ELSIF n >= p_limit THEN
                -- 032 left the loop here, so everything past the cap vanished
                -- without a row. The cap is a decision the runtime made and it
                -- is reported like every other one.
                dropped_because := 'over_cap';
            END IF;
        END IF;

        IF dropped_because IS NULL THEN
            n := n + 1;
            kept := kept || r.playbook_id;
            rank := n;
        ELSE
            rank := NULL;
        END IF;

        playbook_id := r.playbook_id;
        path := r.path;
        RETURN NEXT;
    END LOOP;
END $$;

COMMENT ON FUNCTION select_playbooks(uuid, uuid, text, text, text, integer) IS
    'Ticket 45 criterion 3: computed facts, then metadata, then derived '
    'conflict, then a strict small cap. Every Playbook the subject''s facts '
    'matched comes back exactly once -- kept with a rank, or dropped with a '
    'typed reason from playbook_drop_reasons.';

CREATE FUNCTION playbook_funnel(
        p_program uuid, p_subject uuid, p_property_class text DEFAULT NULL,
        p_role text DEFAULT 'web_hunter', p_ceiling text DEFAULT 'constrained',
        p_limit integer DEFAULT 3)
RETURNS TABLE (corpus integer, after_trigger integer, after_metadata integer,
               after_conflict integer, dropped integer)
LANGUAGE sql STABLE AS $$
    WITH s AS (SELECT * FROM select_playbooks(p_program, p_subject,
                                p_property_class, p_role, p_ceiling, p_limit))
    SELECT (SELECT count(*)::int FROM playbooks),
           (SELECT count(*)::int FROM playbooks_by_trigger(p_program, p_subject)),
           (SELECT count(*)::int FROM playbooks_by_metadata(p_program, p_subject,
                                        p_property_class, p_role, p_ceiling)),
           (SELECT count(*)::int FROM s WHERE s.dropped_because IS NULL),
           (SELECT count(*)::int FROM s WHERE s.dropped_because IS NOT NULL);
$$;

COMMENT ON FUNCTION playbook_funnel(uuid, uuid, text, text, text, integer) IS
 'The funnel as a measurement. `dropped` now counts every exclusion after the '
 'trigger stage, not only the conflicts: 032 could not see the metadata drops '
 'because select_playbooks did not emit them.';


-- ===========================================================================
-- 6. Freezing what was selected
-- ===========================================================================

-- The catalogue is the only source of the two digests. A caller passes NULL and
-- gets today's; a caller that passes a value gets it checked. Neither is a
-- convenience: a selection row whose hash was written by its writer is a
-- selection row that proves nothing about what ran.
CREATE FUNCTION freeze_playbook_selection() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE p record;
BEGIN
    SELECT source_sha256, version INTO p FROM playbooks WHERE id = NEW.playbook_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'playbook % is not in the catalogue', NEW.playbook_id;
    END IF;
    IF NEW.playbook_sha256 IS NULL THEN
        NEW.playbook_sha256 := p.source_sha256;
    ELSIF NEW.playbook_sha256 <> p.source_sha256 THEN
        RAISE EXCEPTION 'playbook % is at %, the selection claims %',
            NEW.playbook_id, p.source_sha256, NEW.playbook_sha256;
    END IF;
    IF NEW.playbook_version IS NULL THEN
        NEW.playbook_version := p.version;
    ELSIF NEW.playbook_version <> p.version THEN
        RAISE EXCEPTION 'playbook % projects %, the selection claims %',
            NEW.playbook_id, p.version, NEW.playbook_version;
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER playbook_selection_freeze
    BEFORE INSERT ON playbook_selections
    FOR EACH ROW EXECUTE FUNCTION freeze_playbook_selection();

-- `outcome` and `went_stale_at` are what a run updates. Everything that
-- describes the decision itself is written once, which is criterion 4: a later
-- edit to the catalogue cannot reach back through this row, and neither can a
-- later edit to this row.
CREATE FUNCTION enforce_playbook_selection_frozen() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF ROW(NEW.program_id, NEW.task_id, NEW.subject_entity_id, NEW.playbook_id,
           NEW.playbook_sha256, NEW.playbook_version, NEW.rank,
           NEW.dropped_because, NEW.dropped_detail, NEW.selected_at)
       IS DISTINCT FROM
       ROW(OLD.program_id, OLD.task_id, OLD.subject_entity_id, OLD.playbook_id,
           OLD.playbook_sha256, OLD.playbook_version, OLD.rank,
           OLD.dropped_because, OLD.dropped_detail, OLD.selected_at) THEN
        RAISE EXCEPTION
            'a selection records a decision that was already made; only outcome and went_stale_at move';
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER playbook_selection_frozen
    BEFORE UPDATE ON playbook_selections
    FOR EACH ROW EXECUTE FUNCTION enforce_playbook_selection_frozen();

-- The one writer. It derives the program and the role from the Task rather than
-- taking either, because a caller that could name them could record a selection
-- made under a role that will not run the Task.
CREATE FUNCTION record_playbook_selection(
        p_task uuid, p_subject uuid, p_property_class text DEFAULT NULL,
        p_ceiling text DEFAULT 'constrained', p_limit integer DEFAULT 3)
RETURNS integer LANGUAGE plpgsql AS $$
DECLARE
    v_program uuid;
    v_role    text;
    v_kept    integer := 0;
BEGIN
    SELECT t.program_id, m.role INTO v_program, v_role
      FROM tasks t LEFT JOIN role_task_kinds m ON m.kind = t.kind
     WHERE t.id = p_task;
    IF v_program IS NULL THEN
        RAISE EXCEPTION 'task % does not exist', p_task;
    END IF;
    IF v_role IS NULL THEN
        RAISE EXCEPTION 'no role executes the kind task % carries', p_task;
    END IF;

    -- One statement, because the freeze and the count are about the rows this
    -- call decided and nothing else. Reading them back off the Task instead
    -- would be a different question that happens to have the same answer today:
    -- `playbook_selections` is unique on (task_id, playbook_id), so a second
    -- call is refused before it can reach the freeze. That is a constraint
    -- somewhere else holding this function up, and it is one edit away from
    -- stopping.
    WITH decided AS (
        INSERT INTO playbook_selections
            (program_id, task_id, subject_entity_id, playbook_id,
             rank, dropped_because, dropped_detail)
        SELECT v_program, p_task, p_subject, s.playbook_id,
               s.rank, s.dropped_because, s.dropped_detail
          FROM select_playbooks(v_program, p_subject, p_property_class,
                                v_role, p_ceiling, p_limit) s
        RETURNING id, playbook_id, dropped_because
    ),
    -- A dropped Playbook was never loaded, and recording the Skills it would
    -- have used would be recording a run that did not happen.
    kept AS (
        SELECT id, playbook_id FROM decided WHERE dropped_because IS NULL
    ),
    frozen AS (
        INSERT INTO playbook_selection_skills
            (selection_id, program_id, skill_name, skill_sha256, skill_version)
        SELECT k.id, v_program, ps.skill_name, sk.source_sha256, sk.version
          FROM kept k
          JOIN playbook_skills ps ON ps.playbook_id = k.playbook_id
          JOIN skills sk ON sk.name = ps.skill_name
        RETURNING 1
    )
    SELECT count(*)::int INTO v_kept FROM kept;

    RETURN v_kept;
END $$;

COMMENT ON FUNCTION record_playbook_selection(uuid, uuid, text, text, integer) IS
    'Ticket 45 criterion 4: run the selection for a Task and write down what it '
    'decided, kept rows and dropped rows both, with the Playbook and Skill '
    'digests frozen as they stand now. The program and the role come from the '
    'Task; a caller that could name the role could record a selection made '
    'under one that will never run it.';


-- ===========================================================================
-- 7. The corpus, as rows
-- ===========================================================================

-- One Playbook, and it is `draft`. `playbooks_stable_is_promoted` and 036's
-- promotion guard together make `stable` unreachable until a fixture pair
-- carrying `authorization.object_ownership` has been run against this exact
-- text, and the fixture catalogue is empty. Draft is the honest state, and
-- selection admits it: only `deprecated` is excluded.
INSERT INTO playbooks (path, source_sha256, version, category, status, stale_after,
                       risk, effects, baseline, specificity, provenance) VALUES
 ('playbooks/object-ownership/playbook.md',
  '95d6dbd27186e25801458cb24cd8c62c4c172655a1177407924e8f0127c6bfc5',
  '693dd5aab95759c80d20790bf747a8ccb2b340bf0d0e54620b89b3a916cf8285',
  'authorization', 'draft', '2027-02-15T00:00:00Z',
  'constrained', 'read_only', 'stable_session', 2,
  'Written for ticket 45 against the object-ownership leaf of the ticket 18 vocabulary; no upstream card, no third-party list.')
ON CONFLICT (path) DO UPDATE SET
    source_sha256 = excluded.source_sha256,
    version       = excluded.version,
    category      = excluded.category,
    status        = excluded.status,
    stale_after   = excluded.stale_after,
    risk          = excluded.risk,
    effects       = excluded.effects,
    baseline      = excluded.baseline,
    specificity   = excluded.specificity,
    provenance    = excluded.provenance;

-- Every row has a document behind it, which is the condition these two columns
-- were waiting for.
ALTER TABLE playbooks
    ALTER COLUMN version SET NOT NULL,
    ALTER COLUMN provenance SET NOT NULL;

INSERT INTO playbook_triggers (playbook_id, mode, fact)
SELECT p.id, v.mode, v.fact
  FROM playbooks p, (VALUES
        ('all', 'multiple_test_identities'),
        ('all', 'object_identifier'),
        -- The object has to be named somewhere a request can carry it. Any one
        -- of the three will do, which is what `any` means -- and no fact here
        -- repeats one above, or the disjunction would exclude nothing.
        ('any', 'body_parameter'),
        ('any', 'path_parameter'),
        ('any', 'query_parameter')) AS v(mode, fact)
 WHERE p.path = 'playbooks/object-ownership/playbook.md'
ON CONFLICT (playbook_id, mode, fact) DO NOTHING;

INSERT INTO playbook_outputs (playbook_id, property_class)
SELECT p.id, 'authorization.object_ownership'
  FROM playbooks p WHERE p.path = 'playbooks/object-ownership/playbook.md'
ON CONFLICT (playbook_id, property_class) DO NOTHING;

-- `skill_sha256_at_promotion` stays NULL: this Playbook has not been promoted,
-- and a promotion hash written at ingest would be a drift baseline taken at a
-- moment no promotion happened. 032's `skill_drift` arm reads NULL as "nothing
-- to drift from", which is the correct answer here rather than a convenient one.
INSERT INTO playbook_skills (playbook_id, skill_name)
SELECT p.id, v.skill_name
  FROM playbooks p, (VALUES ('compare-responses'), ('use-identity')) AS v(skill_name)
 WHERE p.path = 'playbooks/object-ownership/playbook.md'
ON CONFLICT (playbook_id, skill_name) DO NOTHING;

-- Stricter than `transition_rules` and never looser: the two are a conjunction.
-- The `control` row is the one that matters and the one every write-up skips --
-- a refusal under the second Identity is only evidence of an enforced boundary
-- if that Identity's session was working at the time.
INSERT INTO playbook_evidence
        (playbook_id, to_status, role, observation_kind, polarity, min_count)
SELECT p.id, v.to_status, v.role, v.kind, v.polarity, v.min_count
  FROM playbooks p, (VALUES
        ('refuted',   'variant', 'response_invariant',   'refutes',  1),
        ('supported', 'control', 'credential_effect',    'supports', 1),
        ('supported', 'variant', 'response_differential','supports', 1))
        AS v(to_status, role, kind, polarity, min_count)
 WHERE p.path = 'playbooks/object-ownership/playbook.md'
ON CONFLICT (playbook_id, to_status, role, observation_kind) DO NOTHING;

INSERT INTO playbook_references (playbook_id, name, path, sha256)
SELECT p.id, 'why-two-identities.md',
       'playbooks/object-ownership/references/why-two-identities.md',
       'a0575ef3f40454e48954fda01dd31adf4f1257e7df2c12c6ba9f156bb6b7f01f'
  FROM playbooks p WHERE p.path = 'playbooks/object-ownership/playbook.md'
ON CONFLICT (playbook_id, name) DO NOTHING;


-- ===========================================================================
-- 8. What the catalogue has to keep being true
-- ===========================================================================

-- 035's function plus four arms, and 035 is the base on purpose: `CREATE OR
-- REPLACE` has no way to add an arm without restating every other one, so a
-- restatement that reached back to 032 would quietly undo 035's two decisions
-- -- `playbook_unloadable` as an error rather than a warning, and
-- `promoted_without_evidence` -- while looking like an addition. They are
-- restated here verbatim, including the `needs {...}` detail and the call to
-- `playbook_loadable_by`, so the rule stays in one place.
--
-- The four that are new are the three ticket 45 makes checkable -- a derived
-- number the importer could have got wrong, a Playbook that cannot make its own
-- claim, a selection that froze nothing -- and the drift arm that is the point
-- of freezing anything.
CREATE OR REPLACE FUNCTION check_playbook_integrity()
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
    -- HARD (035): no role can load every skill this playbook needs, so it can
    -- never be selected by anyone -- dead corpus, the same class as
    -- `playbook_without_trigger`. The detail names the skill set so a roster
    -- gap reads differently from a typo without a second query.
    SELECT 'error', 'playbook_unloadable',
           p.path || ' needs {' ||
           (SELECT string_agg(ps.skill_name, ',' ORDER BY ps.skill_name)
              FROM playbook_skills ps WHERE ps.playbook_id = p.id) || '}'
      FROM playbooks p
     WHERE EXISTS (SELECT 1 FROM playbook_skills ps WHERE ps.playbook_id = p.id)
       AND NOT EXISTS (SELECT 1 FROM playbook_loadable_by(p.id))
UNION ALL
    -- HARD (035): a promotion whose chain does not exist -- imported
    -- pre-promoted, or the text moved after promotion and the evidence no
    -- longer describes it.
    SELECT 'error', 'promoted_without_evidence', p.path
      FROM playbooks p
     WHERE p.promoted_at IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM playbook_promotion_evidence(p.id, p.source_sha256))
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
     WHERE NOT EXISTS (SELECT 1 FROM playbook_triggers t WHERE t.playbook_id = p.id)
UNION ALL
    -- HARD: `specificity` is the tie-break in `select_playbooks` and it is
    -- derived, so this is the database recomputing what the importer wrote
    -- down. A number that stopped matching the list beside it would reorder the
    -- catalogue silently, which is the failure mode a hand-maintained version
    -- has and the reason nothing else here is hand-maintained.
    SELECT 'error', 'specificity_disagrees',
           format('%s says %s, it requires %s fact(s)', p.path, p.specificity,
                  (SELECT count(*) FROM playbook_triggers t
                    WHERE t.playbook_id = p.id AND t.mode = 'all'))
      FROM playbooks p
     WHERE p.specificity <> (SELECT count(*) FROM playbook_triggers t
                              WHERE t.playbook_id = p.id AND t.mode = 'all')
UNION ALL
    -- HARD: a playbook that declares nothing for `supported` cannot make the
    -- claim it exists to make, and `enforce_playbook_evidence` would have
    -- nothing to enforce -- so the guard would pass by being empty.
    SELECT 'error', 'evidence_missing', p.path
      FROM playbooks p
     WHERE NOT EXISTS (SELECT 1 FROM playbook_evidence e
                        WHERE e.playbook_id = p.id AND e.to_status = 'supported')
UNION ALL
    -- HARD: a kept selection whose playbook needs skills and which froze none.
    -- Criterion 4 with teeth: the freeze is what makes the record evidence, and
    -- a record that skipped it looks identical to one that did not.
    SELECT 'error', 'selection_unfrozen',
           p.path || ' @ task ' || s.task_id::text
      FROM playbook_selections s JOIN playbooks p ON p.id = s.playbook_id
     WHERE s.dropped_because IS NULL
       AND EXISTS (SELECT 1 FROM playbook_skills ps WHERE ps.playbook_id = s.playbook_id)
       AND NOT EXISTS (SELECT 1 FROM playbook_selection_skills k
                        WHERE k.selection_id = s.id)
UNION ALL
    -- WARNING: the text a selection was made against is not the text installed
    -- now. Reported and never prevented, for ticket 44's reason: a selection
    -- records what ran, and forcing it to match today's corpus would make an
    -- old run unrecordable rather than visible.
    SELECT 'warning', 'selection_playbook_drift',
           format('task %s ran %s at %s, the catalogue holds %s',
                  s.task_id, p.path, s.playbook_sha256, p.source_sha256)
      FROM playbook_selections s JOIN playbooks p ON p.id = s.playbook_id
     WHERE s.playbook_sha256 <> p.source_sha256
UNION ALL
    SELECT 'warning', 'selection_skill_drift',
           format('task %s loaded %s at %s, the registry holds %s',
                  s.task_id, k.skill_name, k.skill_sha256, sk.source_sha256)
      FROM playbook_selection_skills k
      JOIN playbook_selections s ON s.id = k.selection_id
      JOIN skills sk ON sk.name = k.skill_name
     WHERE k.skill_sha256 IS NOT NULL AND k.skill_sha256 <> sk.source_sha256;
$$;

-- Reissued rather than inherited. A comment survives `CREATE OR REPLACE`, so
-- leaving it would leave 035's description of a function that has five more
-- arms than it describes.
COMMENT ON FUNCTION check_playbook_integrity() IS
 '035''s eight arms -- playbook_unloadable as an error and '
 'promoted_without_evidence among them -- plus 045''s five: '
 'specificity_disagrees and evidence_missing on the catalogue, '
 'selection_unfrozen, selection_playbook_drift and selection_skill_drift on '
 'what a Task recorded. Drift is reported and never prevented: a selection '
 'records what ran, and forcing it to match today''s corpus would make an old '
 'run unrecordable rather than visible.';


-- ===========================================================================
-- Z. Wiring
-- ===========================================================================

INSERT INTO program_global_tables (table_name, reason) VALUES
 ('playbook_references',   'belongs to the playbook, which is one document on every program'),
 ('playbook_drop_reasons', 'the vocabulary a selection reports itself in; a property of the schema');

INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
 ('playbook_references', 'reference',
  'belongs to the playbook; loaded and replaced with it', '45'),
 ('playbook_drop_reasons', 'reference',
  'the drop-reason vocabulary; changed only by migration', '45'),
 ('playbook_selection_skills', 'covered',
  'written in the same transaction as the selection it belongs to, which is itself covered by the task it names; a third event for one decision would triple-count it', '45');

INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
 ('playbook_references',      'playbook_id',   'catalogue child: a reference without its playbook is not a row'),
 ('playbook_selection_skills','program_id',    'program-scoped: the purge root'),
 ('playbook_selection_skills','selection_id',  'the freeze belongs to the selection and has no meaning without it');

-- Columns added to an already-published table are NOT published by inheritance,
-- which is the property ticket 33 bought. These four are the ones a reader of
-- the selection needs; `playbook_references` gets no rows at all, which is
-- criterion 2 on the read surface rather than in the projection.
INSERT INTO state_read_surface (table_name, column_name, added_by) VALUES
 ('playbooks',           'version',          '45'),
 ('playbooks',           'provenance',       '45'),
 ('playbook_selections', 'playbook_version', '45'),
 ('playbook_selections', 'dropped_detail',   '45');

GRANT SELECT ON playbook_references, playbook_drop_reasons, playbook_selection_skills
    TO rk2_runtime, rk2_human;
REVOKE UPDATE, DELETE ON playbook_references, playbook_drop_reasons FROM rk2_runtime;
REVOKE ALL ON playbook_references, playbook_drop_reasons FROM rk2_state, rk2_proxy;
REVOKE ALL ON playbook_selection_skills FROM rk2_state, rk2_proxy;

-- Named beside the two it guards: both run as their caller, so a role that may
-- ask for candidates must be able to reach the refusal that comes first.
GRANT EXECUTE ON FUNCTION reject_unrunnable_ceiling(text)
    TO rk2_runtime, rk2_human;
GRANT EXECUTE ON FUNCTION playbook_candidates(uuid, uuid, text, text, text)
    TO rk2_runtime, rk2_human;
GRANT EXECUTE ON FUNCTION record_playbook_selection(uuid, uuid, text, text, integer)
    TO rk2_runtime, rk2_human;

DO $$
DECLARE n integer;
BEGIN
    SELECT count(*) INTO n FROM check_playbook_integrity() WHERE severity = 'error';
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-45 left the catalogue failing its own check, % row(s)', n;
    END IF;

    -- The corpus is one Playbook and it is the one this file inserted. A second
    -- one would mean an earlier migration wrote a row nothing here knows about.
    SELECT count(*) INTO n FROM playbooks;
    IF n <> 1 THEN
        RAISE EXCEPTION 'ph2-45 expected one playbook in the catalogue, found %', n;
    END IF;

    -- Every reason `select_playbooks` can emit is a row, and every row is a
    -- reason it can emit. The first direction is the foreign key's; this is the
    -- second, which nothing else would notice.
    SELECT count(*) INTO n FROM playbook_drop_reasons r
     WHERE position(('''' || r.id || '''') IN
                    pg_get_functiondef('select_playbooks(uuid,uuid,text,text,text,integer)'::regprocedure)
                    || pg_get_functiondef('playbook_candidates(uuid,uuid,text,text,text)'::regprocedure)) = 0;
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-45 registered % drop reason(s) nothing can emit', n;
    END IF;
END $$;
