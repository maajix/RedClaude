-- Origin: ticket 24, "Transport claims". `receipts_agent_transport_records_both
-- _sides` was written to make one shape unwritable: an agent-lane Receipt that
-- records what the agent's TLS stack negotiated and says nothing about what the
-- proxy negotiated upstream. That is the row a door which does not know it is
-- lying would write, and it stays unwritable here.
--
-- The predicate was symmetric, though, and the other direction is not a lie:
--
--     (agent_tls_version IS NULL) = (wire_tls_version IS NULL)
--
-- refuses a row that records the target's handshake and not the agent's. That
-- shape has a caller. A client may send an absolute-form `https://` request to
-- the door over a cleartext hop instead of opening a tunnel first -- `_request`
-- in `proxy.py` accepts it, and `_url` keeps the scheme -- and then there is a
-- target-side handshake to describe and no agent-side one to describe. Under the
-- symmetric rule the only writable row was the one with both columns empty, so
-- the certificate, the cipher and the verification outcome of the exchange that
-- actually happened were dropped to satisfy a constraint about the exchange that
-- did not.
--
-- The standing check has always read it one way round -- arm 4 of
-- `check_transport_claims` reports `one_sided_handshake_record` for
-- `agent_tls_version IS NOT NULL AND wire_tls_version IS NULL` and for nothing
-- else -- so this makes the table agree with the check that watches it rather
-- than changing what either of them means.
--
-- Recording the wire side alone is also the honest record of that hop: an
-- exchange whose agent columns are null is one where the agent was not offered
-- TLS at all, which `transport_divergence` then reports across every field.

ALTER TABLE receipts DROP CONSTRAINT receipts_agent_transport_records_both_sides;

ALTER TABLE receipts
    -- THE GAP MUST BE VISIBLE. On the agent lane, a Receipt that describes the
    -- handshake the agent saw must describe the one the proxy made as well. The
    -- converse is allowed: the proxy may record more than it presented.
    ADD CONSTRAINT receipts_agent_transport_records_both_sides CHECK (
        lane <> 'agent'
        OR agent_tls_version IS NULL
        OR wire_tls_version IS NOT NULL);


DO $$
DECLARE n integer; d text;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conrelid = 'receipts'::regclass
           AND conname = 'receipts_agent_transport_records_both_sides'
           AND pg_get_constraintdef(oid) LIKE '%wire_tls_version IS NOT NULL%') THEN
        RAISE EXCEPTION 'the one-sided handshake rule is not on the table';
    END IF;
    SELECT count(*), string_agg(problem || ' ' || subject || ': ' || detail, '; ')
      INTO n, d FROM check_transport_claims();
    IF n > 0 THEN
        RAISE EXCEPTION 'transport claims broken (% problems): %', n, d;
    END IF;
END $$;
