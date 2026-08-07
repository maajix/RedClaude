-- ---------------------------------------------------------------------------
-- 011_lifecycle.sql   (ticket 06, decision 8)
-- ---------------------------------------------------------------------------

CREATE FUNCTION retire_program(p_program uuid) RETURNS void
LANGUAGE sql AS $$
    UPDATE programs
       SET closed_at = coalesce(closed_at, now()),
           purge_after = coalesce(closed_at, now()) + interval '90 days'
     WHERE id = p_program;
$$;

-- Artifact blobs are dropped at purge_after, receipts and findings are kept: a
-- receipt whose blob is gone still proves the request happened (Q20).
CREATE VIEW artifacts_due_for_purge AS
SELECT a.sha256
  FROM artifacts a
 WHERE a.purged_at IS NULL
   AND NOT EXISTS (
        SELECT 1 FROM receipts r JOIN programs p ON p.id = r.program_id
         WHERE (a.sha256 IN (r.request_agent_sha, r.request_wire_sha,
                             r.response_agent_sha, r.response_wire_sha))
           AND (p.purge_after IS NULL OR p.purge_after > now()));

-- Purge is DELETE FROM programs WHERE id = $1 -- every table above cascades,
-- including events. Blob deletion afterwards is refcounted by the same NOT
-- EXISTS query with the time predicate dropped: content-addressed storage means
-- another program may hold the identical bytes.
