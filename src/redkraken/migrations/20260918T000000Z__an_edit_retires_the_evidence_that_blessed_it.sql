-- ---------------------------------------------------------------------------
-- 20260918T000000Z__an_edit_retires_the_evidence_that_blessed_it.sql  (PH2-64)
--
-- Story 176 asks for two exclusions and the funnel implements one. `expired`
-- is there. Edited is not: 046's `a0_playbook_edit_demotes` moves an edited
-- Playbook from `stable` to `draft` and files the digest it was stable at, and
-- 045's `playbook_candidates` admits `draft` -- only `deprecated` is excluded.
-- So a card whose text a maintainer changed this morning is selectable this
-- afternoon, at bytes no fixture has ever been run against, carrying the
-- standing it earned as the text it is no longer. That is the sentence the
-- story ends with: old evidence blessing new text.
--
-- Dropping `draft` is the obvious repair and the wrong one. Every Playbook in
-- this corpus is `draft` -- `stable` is unreachable until a fixture pair has
-- run against the exact text, and 045 admitted draft in the same breath as it
-- said so -- so a funnel that excluded drafts would exclude the catalogue, and
-- story 176 would be paid for with a selection that returns nothing.
--
-- The line the story draws is between a Playbook that has never been graded
-- and one that was graded and then changed. Only the second has evidence to be
-- wrong about. `playbook_demotions` already separates them: a row with cause
-- `edited` is written for a Playbook that was stable or promoted when its text
-- moved and for no other, and it carries the digest that standing belonged to.
-- Four states, and the ledger answers each:
--
--   * never promoted -- no `edited` row, so selectable, as it is today;
--   * edited since grading -- an `edited` row and none of them at the digest
--     the Playbook now carries, so dropped;
--   * edited and then reverted -- an `edited` row AT the current digest: these
--     are bytes that were stable once and the evidence is about them, so
--     selectable, and the maintainer who undid a change is not made to
--     re-earn what was never lost;
--   * re-promoted at the new text -- `stable`, which 035's guard does not hand
--     out until the evidence chain has been re-evaluated against that text.
--     That is what "until reevaluated" means here, and it is the path a
--     maintainer already walks.
--
-- The reason is a metadata reason and sits next to `expired`, because the two
-- are the story's own pair and because both are decided about the Playbook
-- alone. It sits after it rather than before for the ordering 045 gave: a
-- Playbook that is both past review and edited reads as past review, which is
-- the older fact.
-- ---------------------------------------------------------------------------

INSERT INTO playbook_drop_reasons (id, label, stage, description) VALUES
 ('edited', 'Edited since grading', 'metadata',
  'the text changed after the Playbook was graded and nothing has graded what it now says');

-- `rk2_runtime` reaches the ledger through 029's default privileges, which is
-- why 046 wrote no grant and nothing noticed. `rk2_human` is not covered by
-- them and holds EXECUTE on the funnel, so without this line the arm below
-- would answer an operator with a permission error on a table the question is
-- not about. `rk2_state` and `rk2_proxy` stay where they are: the model reads
-- the Playbook it was handed, never the catalogue's opinion of it.
GRANT SELECT ON playbook_demotions TO rk2_runtime, rk2_human;

CREATE OR REPLACE FUNCTION playbook_candidates(
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
             -- Two conditions and not one. The first is "this Playbook was
             -- graded and then edited", the second is "and the text has not
             -- come back"; without the first, a NOT EXISTS over a Playbook
             -- nobody ever edited is vacuously true and the arm would drop the
             -- whole catalogue. `stable` is excluded from the question rather
             -- than tested inside it, because a Playbook that is stable now
             -- was promoted at the text it now carries.
             WHEN p.status <> 'stable'
              AND EXISTS (SELECT 1 FROM playbook_demotions d
                           WHERE d.playbook_id = p.id AND d.cause = 'edited')
              AND NOT EXISTS (SELECT 1 FROM playbook_demotions d
                               WHERE d.playbook_id = p.id AND d.cause = 'edited'
                                 AND d.playbook_sha256 = p.source_sha256)
                  THEN 'edited'
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
    'Ticket 45 criterion 5 and story 176: the metadata stage with its reasons. '
    'One row per Playbook the subject''s facts matched; dropped_because is '
    'NULL for the ones that survive and a playbook_drop_reasons id for the '
    'ones that do not. The rules are here and nowhere else -- '
    'playbooks_by_metadata is the survivors of this, so the filter and the '
    'explanation cannot drift. `expired` and `edited` are story 176''s pair: '
    'a Playbook nobody has reviewed since its date, and one whose text has '
    'moved past the digest its standing was earned at.';

DO $$
DECLARE n integer;
BEGIN
    -- 045's second direction, run again because this file added a reason: every
    -- registered reason is one the selection can emit. The foreign key holds
    -- the first direction, and nothing but this notices the second.
    SELECT count(*) INTO n FROM playbook_drop_reasons r
     WHERE position(('''' || r.id || '''') IN
                    pg_get_functiondef('select_playbooks(uuid,uuid,text,text,text,integer)'::regprocedure)
                    || pg_get_functiondef('playbook_candidates(uuid,uuid,text,text,text)'::regprocedure)) = 0;
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-64 registered % drop reason(s) nothing can emit', n;
    END IF;

    -- The corpus is what it was a statement ago. This arm reads a ledger that
    -- is empty on a fresh database and near-empty on any other, and a migration
    -- that quietly retired a shipped Playbook would be story 176 doing the
    -- damage it exists to prevent.
    SELECT count(*) INTO n FROM playbooks p
     WHERE p.status <> 'stable'
       AND EXISTS (SELECT 1 FROM playbook_demotions d
                    WHERE d.playbook_id = p.id AND d.cause = 'edited')
       AND NOT EXISTS (SELECT 1 FROM playbook_demotions d
                        WHERE d.playbook_id = p.id AND d.cause = 'edited'
                          AND d.playbook_sha256 = p.source_sha256);
    IF n > 0 THEN
        RAISE WARNING 'ph2-64 excludes % playbook(s) edited since they were graded', n;
    END IF;
END $$;
