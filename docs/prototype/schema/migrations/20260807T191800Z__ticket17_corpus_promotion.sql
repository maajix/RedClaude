-- ---------------------------------------------------------------------------
-- 20260807T191800Z__ticket17_corpus_promotion.sql   (ticket 17 -- the v1 corpus)
--
-- Was `030_ticket17_corpus.sql` on branch prototype/v1-corpus. It creates no
-- tables, so the fold changed nothing structural: no classification rows, no
-- purge edges, no grants, no RLS. `check_playbook_integrity()` is replaced, not
-- created, and the `standing_checks` row ticket 10 wrote above already names it,
-- so the promotion rules become standing the moment this applies.
-- ---------------------------------------------------------------------------

-- ===========================================================================
-- ticket 17: the v1 corpus migration
--
-- This migration creates no tables.  The corpus is markdown on disk and ticket
-- 10 already owns the catalogue; what was missing is the one rule the migration
-- cannot be trusted without.
--
-- THE PROBLEM, found by reading 027's executed code rather than its prose.
-- `playbooks.py:ingest()` says
--
--     "promoted": bool(fm.get("verified"))            ...  promoted_at = now()
--
-- and 59 of v1's 60 playbook cards carry a `verified:` block -- a date a human
-- typed into a markdown file after reading it.  Import the corpus as-is and the
-- whole catalogue arrives pre-promoted; one `UPDATE playbooks SET
-- status='stable'` then satisfies `playbooks_stable_is_promoted` and 59 cards
-- are stable on the strength of nothing a runtime ever committed.  That is
-- "LLM proposes, runtime commits" inverted at the catalogue layer.
--
-- The ticket frames the triage criterion as "only those that demonstrably found
-- something become stable".  Measured against v1's surviving evidence the
-- criterion is not satisfiable at migration time at all: 251 finding records
-- survive, every one carries `family`, NONE carries a playbook or skill key, and
-- each is model-authored JSON with no provenance record behind it.  So this
-- migration does not encode "which v1 cards were good".  It encodes what a
-- promotion has to be able to point at, and lets the catalogue arrive `draft`
-- and earn the rest.
--
-- A: promotion requires a runtime-generated evidence chain.
-- B: `playbook_unloadable` stops being a warning.
-- ===========================================================================


-- ===========================================================================
-- A -- promotion evidence
--
-- The chain, every hop of which is written by the runtime and none by a model:
--
--   playbook_selections   the runtime chose this playbook, for this subject,
--     (kept, produced)    at this exact text  (playbook_sha256)
--   hypotheses            a hypothesis on a property class the playbook
--     (supported)         DECLARES as an output reached `supported`
--   hypothesis_evidence   supporting evidence rows exist
--   observations          each of which carries provenance_kind receipt|tool_run,
--                         CHECKed non-null by 007 and re-checked by 007's
--                         `observations_provenance_guard` against proxy_internal
--
-- `playbook_sha256` is in the join on purpose: promotion is of a TEXT, not of a
-- path.  Edit a promoted playbook and its evidence stops matching, which
-- `check_playbook_integrity` then reports -- rather than the edit inheriting the
-- old text's standing.
-- ===========================================================================

CREATE FUNCTION playbook_promotion_evidence(p_playbook uuid, p_sha text DEFAULT NULL)
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
             p_sha, (SELECT source_sha256 FROM playbooks WHERE id = p_playbook));
$$;

COMMENT ON FUNCTION playbook_promotion_evidence(uuid, text) IS
 'The runtime-generated chain a promotion must point at. Empty for every v1 card '
 'at import time, which is the whole point: a v1 verified: block is a human''s '
 'markdown review date, not a state transition any runtime committed.';


-- Loadability, factored out so the trigger and the integrity check cannot
-- disagree about what it means.
CREATE FUNCTION playbook_loadable_by(p_playbook uuid)
RETURNS TABLE (role text) LANGUAGE sql STABLE AS $$
    SELECT r.role FROM (SELECT DISTINCT rs.role FROM role_skills rs) r
     WHERE NOT EXISTS (
        SELECT 1 FROM playbook_skills ps
         WHERE ps.playbook_id = p_playbook
           AND NOT EXISTS (SELECT 1 FROM role_skills x
                            WHERE x.role = r.role AND x.skill_name = ps.skill_name));
$$;


CREATE FUNCTION enforce_playbook_promotion() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    n_evidence integer;
    n_roles    integer;
BEGIN
    IF NEW.promoted_at IS NULL THEN
        RETURN NEW;
    END IF;

    -- An untouched promotion on an untouched text is not re-litigated; the
    -- integrity check reports drift instead.  Otherwise every unrelated UPDATE
    -- would re-run the chain query.
    IF TG_OP = 'UPDATE'
       AND OLD.promoted_at   IS NOT DISTINCT FROM NEW.promoted_at
       AND OLD.source_sha256 IS NOT DISTINCT FROM NEW.source_sha256 THEN
        RETURN NEW;
    END IF;

    -- On INSERT this is structurally zero: playbook_selections has an FK to
    -- playbooks, so no selection can exist for a row not yet inserted.  A
    -- catalogue therefore CANNOT arrive pre-promoted, however the importer feels
    -- about `verified:`.
    SELECT count(*) INTO n_evidence
      FROM playbook_promotion_evidence(NEW.id, NEW.source_sha256);

    IF n_evidence = 0 THEN
        RAISE EXCEPTION
            'playbook % cannot be promoted: no runtime provenance for this text',
            NEW.path
          USING DETAIL  = 'promotion requires >=1 supported hypothesis on a declared '
                          'output class, produced by a kept selection of source_sha256 '
                          || left(NEW.source_sha256, 12) || ', backed by an observation '
                          'with a receipt or tool_run',
                HINT    = 'a v1 verified: block is not this. Import as status=draft, '
                          'promoted_at NULL, and let the eval suite earn the rest.',
                ERRCODE = 'check_violation';
    END IF;

    -- A promoted playbook no role can load is a catalogue entry nobody can run.
    -- Draft may be unloadable while the roster is still being assembled; promoted
    -- may not.
    SELECT count(*) INTO n_roles FROM playbook_loadable_by(NEW.id);
    IF n_roles = 0 AND EXISTS (SELECT 1 FROM playbook_skills ps WHERE ps.playbook_id = NEW.id) THEN
        RAISE EXCEPTION 'playbook % cannot be promoted: no role holds all of its skills',
            NEW.path
          USING DETAIL  = 'requires {' || (SELECT string_agg(ps.skill_name, ',' ORDER BY ps.skill_name)
                                             FROM playbook_skills ps
                                            WHERE ps.playbook_id = NEW.id) || '}',
                HINT    = 'either the roster gains a role holding the pair (ticket 11) '
                          'or the playbook splits',
                ERRCODE = 'check_violation';
    END IF;

    RETURN NEW;
END $$;

CREATE TRIGGER a_playbook_promotion_guard
    BEFORE INSERT OR UPDATE ON playbooks
    FOR EACH ROW EXECUTE FUNCTION enforce_playbook_promotion();


-- ===========================================================================
-- B -- `playbook_unloadable` becomes an error
--
-- 027 shipped it as a warning and recorded 21 of 183 corpus playbooks hit by it,
-- attributing the number to its generator's random skill keying.  Measured on
-- the real v1 catalogue the structural count is 0 -- v1's playbook/skill relation
-- is single-valued (`family:` is one scalar string on 172 of 181 files, and not
-- one file carries a list), so "a skill pair no single role holds" is not
-- expressible in v1 at all.  The generator's 21 is a generator artifact.
--
-- The residual defect is real and survives that: the format validator has no
-- loadability rule, so an unloadable playbook validates clean, ingests clean, and
-- shows up only as a warning in a report nobody is required to read.  A warning
-- is the wrong severity for a catalogue entry that can never be selected by
-- anyone -- it is dead corpus, exactly like `playbook_without_trigger`, which 027
-- already calls an error.  Reopens ticket 10 on the severity, and ticket 11 on
-- the property that makes it possible: the six roles' skill sets are not
-- union-closed, so a playbook may name two skills the roster holds and still be
-- loadable by nobody.
--
-- The rest of the function is 027's, restated verbatim because CREATE OR REPLACE
-- has no other option.  Two rows are new: the severity flip, and
-- `promoted_without_evidence`, which catches rows that got in before this
-- migration or whose text moved out from under a promotion.
-- ===========================================================================

CREATE OR REPLACE FUNCTION check_playbook_integrity()
RETURNS TABLE (severity text, problem text, detail text) LANGUAGE sql STABLE AS $$
    SELECT 'error'::text, 'fact_not_computed'::text, f.id
      FROM surface_facts f
     WHERE position(('''' || f.id || '''') IN pg_get_viewdef('subject_facts'::regclass)) = 0
       AND position((f.id) IN pg_get_viewdef('subject_facts'::regclass)) = 0
UNION ALL
    SELECT 'error', 'skill_missing', p.path || ' -> ' || ps.skill_name
      FROM playbook_skills ps JOIN playbooks p ON p.id = ps.playbook_id
     WHERE NOT EXISTS (SELECT 1 FROM skills s WHERE s.name = ps.skill_name)
UNION ALL
    SELECT 'warning', 'skill_drift', p.path || ' -> ' || ps.skill_name
      FROM playbook_skills ps
      JOIN playbooks p ON p.id = ps.playbook_id
      JOIN skills s ON s.name = ps.skill_name
     WHERE ps.skill_sha256_at_promotion IS NOT NULL
       AND ps.skill_sha256_at_promotion <> s.source_sha256
UNION ALL
    -- 030: warning -> error, and the detail now names the skill set so the
    -- reader can tell a roster gap from a typo without a second query.
    SELECT 'error', 'playbook_unloadable',
           p.path || ' needs {' ||
           (SELECT string_agg(ps.skill_name, ',' ORDER BY ps.skill_name)
              FROM playbook_skills ps WHERE ps.playbook_id = p.id) || '}'
      FROM playbooks p
     WHERE EXISTS (SELECT 1 FROM playbook_skills ps WHERE ps.playbook_id = p.id)
       AND NOT EXISTS (SELECT 1 FROM playbook_loadable_by(p.id))
UNION ALL
    -- 030: a promotion whose chain does not exist -- imported pre-promoted, or
    -- the text moved after promotion and the evidence no longer describes it.
    SELECT 'error', 'promoted_without_evidence', p.path
      FROM playbooks p
     WHERE p.promoted_at IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM playbook_promotion_evidence(p.id, p.source_sha256))
UNION ALL
    SELECT 'warning', 'output_outside_category', p.path || ' -> ' || o.property_class
      FROM playbook_outputs o JOIN playbooks p ON p.id = o.playbook_id
      JOIN property_classes pc ON pc.id = o.property_class
     WHERE pc.family_id <> p.category
UNION ALL
    SELECT 'warning', 'stale_but_stable', p.path
      FROM playbooks p
     WHERE p.status = 'stable' AND p.stale_after IS NOT NULL AND p.stale_after <= now()
UNION ALL
    SELECT 'warning', 'stale_during_run', p.path || ' @ task ' || s.task_id::text
      FROM playbook_selections s JOIN playbooks p ON p.id = s.playbook_id
     WHERE s.went_stale_at IS NOT NULL AND s.outcome = 'running'
UNION ALL
    SELECT 'error', 'playbook_without_trigger', p.path
      FROM playbooks p
     WHERE NOT EXISTS (SELECT 1 FROM playbook_triggers t WHERE t.playbook_id = p.id);
$$;

COMMENT ON FUNCTION check_playbook_integrity() IS
 '030 raises playbook_unloadable from warning to error (dead corpus, same class '
 'as playbook_without_trigger) and adds promoted_without_evidence. Everything '
 'else is 027''s.';
