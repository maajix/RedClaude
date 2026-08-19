-- ---------------------------------------------------------------------------
-- 20260917T000000Z__the_agent_reads_by_reference_not_by_hash.sql       (PH2-64)
--
-- The door has one exception to withholding an authenticated response from the
-- Agent, and until now it asked the wrong thing to decide it. When the wire
-- bytes an Identity's exchange came back with are already an Agent artifact,
-- withholding them withholds nothing -- the Agent can read them under the hash
-- it already holds -- and sealing them a second time under the other
-- classification is a write the Receipt cannot make. That is sound. What was
-- not sound is the question: the door asked `store.holds`, and the store is a
-- content-addressed heap on disk that five modules write and no Program owns.
--
-- Readability is not a fact about the heap. An Agent reaches bytes through
-- `v_artifacts`, which is `artifact_references` under row level security, and a
-- reference belongs to one Program. So bytes filed by another Program -- or by
-- the legacy import, or by a Tool run of an engagement that ended -- answered
-- the door's question with "yes, the Agent can already read this" about an
-- Agent that could not. A target that can arrange for its authenticated answer
-- to have been filed elsewhere first could then have the door hand its
-- credential-reflecting response to the Agent in full.
--
-- `program_reads_artifact` asks the question the exception is actually about:
-- does this capability's own Program hold an agent-visible reference to these
-- bytes. It resolves the capability rather than taking a Program, the way every
-- other function this role may call does, so the proxy role cannot enumerate
-- what another Program holds; it is `STABLE` and reads two tables; and it says
-- nothing about bytes beyond yes or no.
-- ---------------------------------------------------------------------------


-- ---------------------------------------------------------------------------
-- 1. The question the door asks before it declines to withhold
-- ---------------------------------------------------------------------------
-- Purged rows are excluded because a purge is what "the Agent may no longer
-- read this" is written down as, and a reference to bytes that are gone is a
-- reference the Agent cannot follow.
CREATE FUNCTION program_reads_artifact(
    p_capability text,
    p_sha256     text
) RETURNS boolean
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE
    v_auth record;
BEGIN
    -- Re-resolved on every call, like `reserve_egress_slot` does it: a
    -- capability that lapsed between the dial and the answer is not a capability
    -- whose Program still gets an answer about its own holdings.
    SELECT * INTO v_auth FROM resolve_egress_capability(p_capability);
    IF NOT FOUND THEN
        RAISE EXCEPTION 'egress capability refused' USING ERRCODE = '23514';
    END IF;

    RETURN EXISTS (
        SELECT 1
          FROM artifact_references x
          JOIN artifacts a ON a.sha256 = x.sha256
         WHERE x.program_id = v_auth.program_id
           AND x.sha256 = p_sha256
           AND a.visibility = 'agent_visible'
           AND a.purged_at IS NULL
    );
END;
$fn$;

REVOKE ALL ON FUNCTION program_reads_artifact(text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION program_reads_artifact(text, text) TO rk2_proxy;

COMMENT ON FUNCTION program_reads_artifact(text, text) IS
    'Whether the capability''s Program already holds an agent-visible reference '
    'to these bytes. The door asks before it declines to withhold an '
    'authenticated response, because a hit in the content-addressed store is a '
    'fact about the disk and not about what this Agent may read.';
