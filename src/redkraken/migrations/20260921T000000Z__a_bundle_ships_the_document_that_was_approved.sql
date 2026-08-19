-- Ticket 64: the report in a bundle is the report somebody read.
--
-- Story 203 asks for "each evidence bundle to contain redacted agent-view
-- material and verifiable hashes", and ticket 43's criterion 4 sharpened that
-- into a staleness check: an export whose Finding moved after a human approved
-- a rendering of it is refused. That check compares `source_digest` -- the rows
-- the document was made from -- and nothing compares the bytes.
--
-- The gap is the narrative. `report_renderings.content` is what a human read,
-- and the renderer takes an optional narrative that a filed rendering may carry
-- and that a fresh render of the same rows does not. So a bundle could ship a
-- `report.md` that differs from the approved rendering by whole paragraphs,
-- with `source_digest` equal on both sides and every hash in the manifest
-- internally consistent. The bundle asserted approval of a document nobody had
-- approved.
--
-- The bytes are what this function stops withholding. It already reads the row
-- that decides staleness; it now also answers what that row says, so that the
-- exporter can ship the approved document itself instead of a re-render that is
-- merely made from the same rows. `content_sha256` travels beside it because
-- the manifest names it: a recipient can then check that the file they were
-- sent is the rendering the approval points at, without this harness in the
-- middle.

CREATE OR REPLACE FUNCTION evidence_stale_rendering(p_finding uuid, p_template text)
RETURNS jsonb LANGUAGE sql STABLE AS $fn$
    SELECT jsonb_build_object(
             'rendering',      rr.id,
             'rendered_at',    to_char(rr.rendered_at AT TIME ZONE 'UTC',
                                       'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
             'approved',       EXISTS (SELECT 1 FROM finding_transitions ft
                                        WHERE ft.approved_rendering_id = rr.id),
             'source_digest',  rr.source_digest,
             'content',        rr.content,
             'content_sha256', rr.content_sha256,
             'digest_now',     finding_source_digest(p_finding, p_template),
             'stale',          rr.source_digest
                                 IS DISTINCT FROM finding_source_digest(p_finding, p_template))
      FROM report_renderings rr
     WHERE rr.finding_id = p_finding
       AND rr.template_id = p_template
       AND rr.program_id = rk2_program_required()
     -- The most recent one. Two renderings of one Finding under one form differ
     -- only in when they were made, and the question is about the document a
     -- human most recently read.
     ORDER BY rr.rendered_at DESC, rr.id DESC
     LIMIT 1;
$fn$;

COMMENT ON FUNCTION evidence_stale_rendering(uuid, text) IS
    'Ticket 43 criterion 4, extended by 64: the last filed rendering of this Finding under this form, whether the source it was made from is still the source, and the bytes it is. NULL when nothing has been filed, which is not staleness -- it is a Finding nobody has read yet.';


-- The two keys are load-bearing for the exporter, so a later redefinition that
-- dropped them would be caught here rather than by a bundle that quietly went
-- back to shipping a re-render.
DO $$
BEGIN
    IF (SELECT position('content_sha256' IN p.prosrc)
          FROM pg_proc p
          JOIN pg_namespace n ON n.oid = p.pronamespace
         WHERE p.proname = 'evidence_stale_rendering'
           AND n.nspname = current_schema()) = 0 THEN
        RAISE EXCEPTION 'evidence_stale_rendering must answer content_sha256';
    END IF;
END $$;
