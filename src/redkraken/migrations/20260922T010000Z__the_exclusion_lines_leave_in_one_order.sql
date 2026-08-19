-- Ticket 64: the exclusion lines leave a bundle in one order.
--
-- Ticket 43 criterion 5 asks that "repeated export from identical canonical rows
-- is deterministic apart from explicitly excluded packaging metadata", and
-- `evidence.py` says how that is meant to hold: "the six reads the packing
-- needs, each ordered by the database". Five of the six are. `evidence_exclusions`
-- is five `UNION ALL` arms with no `ORDER BY`, and its rows land in the manifest
-- verbatim -- `"excluded": list(gathered.exclusions)` -- inside the document the
-- manifest digest is taken over.
--
-- Row order out of an unordered union is a planner choice, not a guarantee. Two
-- exports of the same rows on the same data can differ in it, and then two
-- honest exports of one Finding carry two digests, which is the one thing a
-- recipient checking a bundle against its manifest cannot be asked to explain.
-- The existing test cannot see this: it runs both exports in one session against
-- one plan, so it compares a choice with itself.
--
-- Ordered by `code`, which is the column a reader keys on and the one the arms
-- are already written in. The alias is spelled out because the output columns of
-- a `RETURNS TABLE` function are names in scope, and an `ORDER BY code` that
-- resolved to the OUT parameter would be a sort over a value this query has not
-- computed yet.

CREATE OR REPLACE FUNCTION evidence_exclusions(p_receipts uuid[])
RETURNS TABLE (code text, detail text, items bigint)
LANGUAGE sql STABLE AS $fn$
    WITH cited AS (
        SELECT r.*
          FROM receipts r
         WHERE r.id = ANY (p_receipts)
           AND r.program_id = rk2_program_required()
    ),
    named AS (
        SELECT v.sha, v.view
          FROM cited r
          CROSS JOIN LATERAL (VALUES ('wire', r.request_wire_sha),
                                     ('wire', r.response_wire_sha),
                                     ('agent', r.request_agent_sha),
                                     ('agent', r.response_agent_sha)) AS v(view, sha)
         WHERE v.sha IS NOT NULL
    ),
    held AS (
        SELECT DISTINCT n.view, a.sha256, a.visibility, a.encrypted, a.purged_at
          FROM named n JOIN artifacts a ON a.sha256 = n.sha
    )
    SELECT line_code, line_detail, line_items
      FROM (
        SELECT 'wire_artifact',
               'the exact bytes that crossed the network, sealed under a key this '
                 || 'bundle does not carry; the Agent view of the same exchange is '
                 || 'packaged instead',
               count(*)
          FROM held
         WHERE view = 'wire' AND visibility = 'credential_bearing'
        HAVING count(*) > 0
        UNION ALL
        SELECT 'identity_material',
               'Identity slots were leased for these exchanges; no credential, '
                 || 'cookie or required header value for any of them is in this bundle',
               count(DISTINCT identity_entity_id)
          FROM cited
         WHERE identity_entity_id IS NOT NULL
        HAVING count(*) > 0
        UNION ALL
        SELECT 'query_string',
               'these exchanges carried a query string; the harness recorded its '
                 || 'digest and never its text, so the bundle carries the digest',
               count(*)
          FROM cited
         WHERE query_sha256 IS NOT NULL
        HAVING count(*) > 0
        UNION ALL
        SELECT 'sealed_agent_view',
               'the Agent view of these exchanges is itself credential-bearing and '
                 || 'sealed; the report cites it by hash and the bundle carries the '
                 || 'hash and not the bytes',
               count(*)
          FROM held
         WHERE view = 'agent' AND (visibility = 'credential_bearing' OR encrypted)
        HAVING count(*) > 0
        UNION ALL
        SELECT 'purged_artifact',
               'these Agent-view artifacts were purged from this harness; a bundle '
                 || 'carrying them would be the one place that decision could be undone',
               count(*)
          FROM held
         WHERE view = 'agent' AND purged_at IS NOT NULL
        HAVING count(*) > 0
      ) AS lines(line_code, line_detail, line_items)
     ORDER BY line_code;
$fn$;

COMMENT ON FUNCTION evidence_exclusions(uuid[]) IS
    'Ticket 43 criteria 2 and 5: what these exchanges hold that a bundle does not carry, as a count and a reason, in one order. Stated rather than left to be inferred -- a reader cannot tell material that was excluded from material that was never there, and the two Agent-view arms are the ones `evidence_artifacts` withholds silently without them. Ordered by code because these lines are digested with the manifest, and an order the planner chooses is a digest that can change while the rows do not.';
