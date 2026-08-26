-- ---------------------------------------------------------------------------
-- 20261117T000000Z__a_bundle_the_program_fetched_is_source_it_holds.sql
--
-- Ticket 186. The three source analysers have never been run.
--
-- What was measured. Database `rk2here`, 2026-08-25:
-- `SELECT count(*) FROM tool_runs WHERE offline_tool IS NOT NULL` answered `0`,
-- and `artifact_references` held 44 rows, every one of them `runtime`. Eight
-- applications had been recorded as `spa_surface`, which is the surface whose
-- routes live in a bundle and nowhere else.
--
-- Two of the three joins that were missing are made here. The third is not a
-- join at all -- see the last section.
--
-- 1. NOTHING FILED THE BYTES AS SOURCE. `offline_tool_arguments` declares
--    `artifact_kind = 'source'` for all three analysers and for
--    `extract_paths`, and `hold_receipt_transcripts` filed every half of every
--    exchange as `runtime`. The only writer of a `source` reference was
--    `rk artifact put --kind source`, which is an operator at a terminal, so
--    an agent could not reach the tools its role was granted.
--
--    The kind's own description already said what belongs in it: `application
--    source this Program fetched or recovered`. A response whose target
--    declared it JavaScript or JSON is that, and the door is the only party
--    that ever reads the declaration -- the Artifact is the whole message,
--    filed as `message/http`. So `receipts` gains the media type, the door
--    writes it, and the same trigger that files the `runtime` holding files a
--    `source` holding beside it. Two rows over one hash, both true: `runtime`
--    says this harness stored the bytes doing its work, `source` says what the
--    bytes are. `artifact_references` is unique on (program_id, sha256, kind),
--    which is what makes that expressible rather than a contradiction.
--
-- 2. NOTHING COULD OPEN THE TASK. `20261008T000000Z` refuses a suggested
--    `analyze` Task as `unopenable_kind`, because `js_analyst` holds no
--    `net.request` and the slice that dispatches a Task serves one target
--    request. That refusal is correct and is not touched here. What it leaves
--    is a role with a model, a skill and three tools and no Task it can ever be
--    given, which is why the tools are granted to `recon` below.
--
--    That contradicts `20260814T050000Z`, which granted them to the analyst
--    alone and said why: *a second role holding these tools would be a second
--    place a source conclusion could come from without the roster having said
--    so*. The roster is saying so, here, and the reason the earlier one gave
--    has been overtaken -- it assumed the analyst could be scheduled. `recon`
--    is the role that already fetched the bundle, already holds
--    `exec.tool_run`, and holds `jq` from 030; the analysers need no network
--    and read only Artifacts this Program already holds. The grounding rule is
--    unchanged: `check_source_citation` asks the same question of a `recon` run
--    that it asks of an analyst's.
--
-- 3. THE THIRD "JOIN" WAS NOT ONE, AND THE TICKET WAS WRONG ABOUT IT. 186 said
--    the analysers could not read a transcript. Measured against
--    `src/redkraken/jsscan.py` before any change, both `js_parse` and
--    `js_routes` read a transcript-wrapped bundle and returned exactly the
--    routes they return for the bare file -- the tokeniser separates code from
--    strings and a header block is neither. What the measurement did find is
--    narrower and worse: pointed at a response carrying the header
--    `X-Quote: he said "/api/fake" loudly`, `js_parse` reported `/api/fake`
--    among the file's path literals. `path_literals` says what the file holds,
--    and that string is one the *target* chose. `js_routes` was already immune,
--    because a header line is not a call.
--
--    Fixed in `jsscan.py` rather than here: version 3 reads the body of an HTTP
--    message when it is handed one and reports `carrier_bytes`, while
--    `source_sha256` still names the bytes as read, which is what the Tool run
--    recorded and what a citation is held against. `version_pattern` already
--    admits any integer, so no registry row moves for it.
-- ---------------------------------------------------------------------------


-- ===========================================================================
-- 1. What the target said it sent
-- ===========================================================================

ALTER TABLE receipts ADD COLUMN response_content_type text;

COMMENT ON COLUMN receipts.response_content_type IS
    'The media type the target declared for its answer, parameters dropped and lowercased, or NULL where it declared none. Written by the door, which is the only party that reads it: the Artifact this Receipt names is the whole message and is filed as message/http.';

-- Only the allowed writer. A blocked Receipt records a request that never got
-- an answer, so a column for what the answer declared would be a column that is
-- null by construction -- and `write_blocked_receipt` has no `agent_back` to
-- read it off. Verbatim from `20260815T000000Z` except for the two lines that
-- carry the new column, which are beside `status_code` so the INSERT reads in
-- the order the row does.

CREATE OR REPLACE FUNCTION write_allowed_receipt(p_capability text, p_receipt jsonb)
RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public
AS $fn$
DECLARE
    v_auth          record;
    v_receipt       receipts%ROWTYPE;
    v_scope_version integer;
    v_id            uuid;
BEGIN
    IF p_capability IS NULL
       OR coalesce(jsonb_typeof(p_receipt), 'null') <> 'object' THEN
        RAISE EXCEPTION 'egress capability refused' USING ERRCODE = '23514';
    END IF;
    IF position(p_capability IN p_receipt::text) > 0 THEN
        RAISE EXCEPTION 'receipt payload contains protected capability'
            USING ERRCODE = '23514';
    END IF;

    SELECT * INTO v_auth FROM resolve_egress_capability(p_capability);
    IF NOT FOUND THEN
        RAISE EXCEPTION 'egress capability refused' USING ERRCODE = '23514';
    END IF;
    SELECT scope_version INTO v_scope_version
      FROM programs WHERE id = v_auth.program_id;

    v_receipt := jsonb_populate_record(NULL::receipts, p_receipt);
    v_receipt.id := uuidv7();
    v_receipt.program_id := v_auth.program_id;
    v_receipt.label := '';
    v_receipt.tool_run_id := v_auth.tool_run_id;
    -- The one changed line. `agent` was correct while the only holder of a
    -- capability was a subagent; a replay holds one too, and which of them is
    -- acting is a fact about the Tool run rather than about this call.
    v_receipt.lane := rk2_capability_lane(v_auth.tool_run_id);
    v_receipt.decision := 'allowed';
    v_receipt.scope_version := v_scope_version;
    v_receipt.ts_arrival := coalesce(v_receipt.ts_arrival, clock_timestamp());
    v_receipt.intercepted := coalesce(v_receipt.intercepted, true);

    PERFORM set_actor('runtime');
    INSERT INTO receipts (
        id, program_id, label, tool_run_id, lane, decision, reason,
        identity_entity_id, identity_tls_cert_sha256,
        method, scheme, host, port, path, query_sha256,
        pinned_ips, status_code, response_content_type,
        ts_arrival, ts_egress, waited_ms,
        request_agent_sha, request_wire_sha, response_agent_sha,
        response_wire_sha, notes, scope_version, scope_class, intercepted,
        alpn_pin_mode, agent_tls_version, agent_cipher, agent_alpn,
        agent_cert_sha256, agent_cert_issuer, agent_cert_subject,
        agent_cert_not_after, wire_tls_version, wire_cipher, wire_alpn,
        wire_cert_sha256, wire_cert_issuer, wire_cert_subject,
        wire_cert_not_after, wire_sni, wire_chain_verified,
        wire_hostname_verified, interception_ca_id
    ) VALUES (
        v_receipt.id, v_receipt.program_id, v_receipt.label,
        v_receipt.tool_run_id, v_receipt.lane, v_receipt.decision,
        v_receipt.reason, v_receipt.identity_entity_id,
        v_receipt.identity_tls_cert_sha256, v_receipt.method,
        v_receipt.scheme, v_receipt.host, v_receipt.port, v_receipt.path,
        v_receipt.query_sha256, v_receipt.pinned_ips, v_receipt.status_code,
        v_receipt.response_content_type, v_receipt.ts_arrival, v_receipt.ts_egress, v_receipt.waited_ms,
        v_receipt.request_agent_sha, v_receipt.request_wire_sha,
        v_receipt.response_agent_sha, v_receipt.response_wire_sha,
        v_receipt.notes, v_receipt.scope_version, v_receipt.scope_class,
        v_receipt.intercepted, v_receipt.alpn_pin_mode,
        v_receipt.agent_tls_version, v_receipt.agent_cipher,
        v_receipt.agent_alpn, v_receipt.agent_cert_sha256,
        v_receipt.agent_cert_issuer, v_receipt.agent_cert_subject,
        v_receipt.agent_cert_not_after, v_receipt.wire_tls_version,
        v_receipt.wire_cipher, v_receipt.wire_alpn,
        v_receipt.wire_cert_sha256, v_receipt.wire_cert_issuer,
        v_receipt.wire_cert_subject, v_receipt.wire_cert_not_after,
        v_receipt.wire_sni, v_receipt.wire_chain_verified,
        v_receipt.wire_hostname_verified, v_receipt.interception_ca_id
    )
    RETURNING id INTO v_id;
    RETURN v_id;
END $fn$;


-- ===========================================================================
-- 2. The holding that says what the bytes are
-- ===========================================================================

-- Re-created for one added statement. Everything above the second INSERT is
-- verbatim from `20260811T220000Z__a_stored_transcript_is_held_by_name.sql`.
CREATE OR REPLACE FUNCTION hold_receipt_transcripts() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
BEGIN
    INSERT INTO artifact_references(program_id, sha256, kind)
    SELECT DISTINCT NEW.program_id, t.sha256, 'runtime'
      FROM (VALUES (NEW.request_agent_sha), (NEW.response_agent_sha)) AS t(sha256)
      JOIN artifacts a ON a.sha256 = t.sha256
     WHERE t.sha256 IS NOT NULL
       AND a.visibility = 'agent_visible'
       AND NOT a.encrypted
       AND a.purged_at IS NULL
       -- Labels come from a BEFORE INSERT trigger, which runs before the
       -- conflict is detected and spends a counter on a row that is then
       -- discarded. Filtering here keeps `AF1, AF2, AF3` contiguous; the
       -- ON CONFLICT stays, because two concurrent exchanges over the same
       -- bytes would both pass this test.
       AND NOT EXISTS (SELECT 1 FROM artifact_references x
                        WHERE x.program_id = NEW.program_id
                          AND x.sha256 = t.sha256 AND x.kind = 'runtime')
    ON CONFLICT (program_id, sha256, kind) DO NOTHING;

    -- The response half alone, and only where the target declared a type this
    -- harness has a reader for. A request transcript is what this Program sent
    -- and is not application source however it is typed; a page, an image and a
    -- stylesheet are answers with no route in them, and the three analysers
    -- registered against `artifact_kind = 'source'` read JavaScript and JSON.
    --
    -- The list is written here rather than seeded as a table because it is the
    -- set of types *these* readers accept, and a second place to say that is a
    -- second thing to keep in step with `offline_tools`. When a fourth reader
    -- arrives it will bring its types with it.
    --
    -- `NEW.decision = 'allowed'` because a refusal has no answer, and the
    -- column is null on those rows anyway; saying it makes the arm readable as
    -- what it is rather than as a filter that happens to hold.
    INSERT INTO artifact_references(program_id, sha256, kind)
    SELECT NEW.program_id, NEW.response_agent_sha, 'source'
      FROM artifacts a
     WHERE NEW.response_agent_sha IS NOT NULL
       AND NEW.decision = 'allowed'
       AND a.sha256 = NEW.response_agent_sha
       AND a.visibility = 'agent_visible'
       AND NOT a.encrypted
       AND a.purged_at IS NULL
       AND NEW.response_content_type IN (
             'application/javascript', 'text/javascript',
             'application/x-javascript', 'application/ecmascript',
             'text/ecmascript', 'application/json', 'application/manifest+json')
       AND NOT EXISTS (SELECT 1 FROM artifact_references x
                        WHERE x.program_id = NEW.program_id
                          AND x.sha256 = NEW.response_agent_sha
                          AND x.kind = 'source')
    ON CONFLICT (program_id, sha256, kind) DO NOTHING;
    RETURN NULL;
END $fn$;

COMMENT ON FUNCTION hold_receipt_transcripts() IS
    'Gives the Program a label for the agent-visible transcripts its Receipt names, and a second label of kind source for an answer the target declared as JavaScript or JSON. AFTER INSERT, so the reference exists exactly when the record does; never for wire or encrypted material.';

REVOKE ALL ON FUNCTION hold_receipt_transcripts() FROM PUBLIC;


-- ===========================================================================
-- 3. The role that fetched the bundle may read it
-- ===========================================================================

INSERT INTO offline_tool_roles (tool, role) VALUES
    ('js_parse',  'recon'),
    ('js_routes', 'recon'),
    ('js_map',    'recon')
ON CONFLICT (tool, role) DO NOTHING;


-- ===========================================================================
-- 4. What has to hold afterwards
-- ===========================================================================

DO $$
DECLARE n integer; d text;
BEGIN
    -- The column exists and the writer carries it. A function that compiled
    -- without the column would be a door writing null into every row, which is
    -- the failure this file exists to end and is invisible until an agent tries
    -- to read a bundle.
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'receipts'
                      AND column_name = 'response_content_type') THEN
        RAISE EXCEPTION 'receipts.response_content_type was not added';
    END IF;
    IF position('response_content_type' IN
                pg_get_functiondef('write_allowed_receipt(text, jsonb)'::regprocedure)) = 0 THEN
        RAISE EXCEPTION 'write_allowed_receipt does not write the new column';
    END IF;

    -- Three tools, two roles each. Read from the table rather than asserted,
    -- because an ON CONFLICT that swallowed a typo would leave this file
    -- looking applied and the capability still dark.
    SELECT count(*) INTO n FROM offline_tool_roles
     WHERE role = 'recon' AND tool IN ('js_parse', 'js_routes', 'js_map');
    IF n <> 3 THEN
        RAISE EXCEPTION 'recon holds % of the 3 source analysers', n;
    END IF;

    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_offline_tools();
    IF n > 0 THEN
        RAISE EXCEPTION 'the tool registry holds % problem(s): %', n, d;
    END IF;
END $$;
