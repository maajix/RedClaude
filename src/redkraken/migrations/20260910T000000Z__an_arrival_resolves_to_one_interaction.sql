-- ===========================================================================
-- Ticket 67 -- an arrival resolves to one interaction
-- ===========================================================================
-- MEASURED on a live installation, 2026-08-12: `rk callback accept` handed the
-- same recorded interactsh arrival twice, at the same host, from the same file,
-- answered `CB1`/`O1` and then `CB3`/`O3`. The bytes were reused -- the store is
-- content-addressed, so the second call answered `stored: false` -- and the
-- arrival and the Observation were new rows. Two Observations then claim two
-- arrivals where the listener recorded one.
--
-- Nothing in an arrival was treated as an identity. `callback_interactions`
-- keys on `id` and takes `received_at DEFAULT now()`, so the same bytes at the
-- same name under the same correlator differ only in a timestamp the caller
-- never stated -- the acceptance moment, which is precisely what a replay
-- changes. 014 says an arrival is admitted by a live correlator on a declared
-- channel; it never said how many times one arrival may be admitted.
--
-- It matters more than a duplicate row usually would. A callback Observation is
-- the confirming half of a Hypothesis about an out-of-band interaction, and
-- "the canary fired twice" is a different claim about the target than "the
-- canary fired". An operator re-running a command after a crash must not be
-- able to manufacture the stronger claim by accident.
--
-- What an arrival is: one Program, one correlator, the name it arrived at, the
-- exact bytes, and the moment the listener recorded it. `received_at` has to
-- become the listener's own timestamp for that key to mean anything, which is
-- what `p_arrival ->> 'received_at'` is for. It stays fenced by
-- `enforce_callback_attribution`: a row claiming a moment before its correlator
-- was minted, after it expired, or in the future was refused before this file
-- and is refused after it.
--
-- Two real arrivals a resolver made in the same microsecond, at the same name,
-- with byte-identical requests collapse into one row. That is the right trade:
-- the harness records that this canary fired, which it did, and the alternative
-- is a schema in which no replay is distinguishable from a fact.
--
-- No row has to be repaired to install the constraint. Every arrival written
-- before this file took `received_at` from the default, so a replay recorded
-- under the old function differs from its original in exactly the column the
-- key is strictest about, and the duplicates that motivated the ticket do not
-- collide with each other.


-- ---------------------------------------------------------------------------
-- 1. The identity, as a constraint
-- ---------------------------------------------------------------------------
-- In the schema rather than in the writer, because the writer is a convenience:
-- a restore, a fixture loaded by the owner and a future caller that reaches
-- past `record_callback_interaction` all meet this, the way they already meet
-- `callback_interactions_attribution`.
--
-- `peer_class` is deliberately not part of it. It is what the listener could
-- tell about the peer, not a fact about the arrival, and two accepts of one
-- recording that disagree about it are still one arrival.

ALTER TABLE callback_interactions
    ADD CONSTRAINT callback_interactions_arrival_key
    UNIQUE (program_id, correlator_id, arrival_kind, observed_host,
            body_sha256, received_at);

COMMENT ON CONSTRAINT callback_interactions_arrival_key ON callback_interactions IS
  'One Program, one correlator, one name, one set of bytes, one moment: the identity of an arrival, so a recording handed to `rk callback accept` twice is one interaction and one Observation.';


-- ---------------------------------------------------------------------------
-- 2. The writer, which now resolves rather than writes again
-- ---------------------------------------------------------------------------
-- Two changes and nothing else: the arrival may state the moment it was
-- received, and an arrival that is already recorded is answered with the rows
-- that are already there.
--
-- `ON CONFLICT ON CONSTRAINT` names the arrival key rather than taking every
-- conflict, so the `(program_id, label)` collision that a broken label counter
-- would cause still raises instead of quietly resolving to somebody else's row.
--
-- Two things about that path are worth stating because they are not obvious.
-- The `BEFORE INSERT` triggers run before the conflict is detected, so a replay
-- is still put through `enforce_callback_attribution` in full: a recording
-- handed over after its correlator expired is refused rather than deduplicated,
-- which is the same answer `resolve_callback_correlator` gives it. And
-- `assign_label` has already advanced this Program's `CB` counter by then, so a
-- discarded insert leaves a gap in the label sequence. A gap is what a counter
-- that hands out identifiers is for; a reused number would be the defect.

CREATE OR REPLACE FUNCTION record_callback_interaction(
    p_correlator    text,
    p_arrival  jsonb,
    p_artifact jsonb
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE
    t             record;
    v_host        text;
    v_kind        text;
    v_peer        text;
    v_stated      text;
    v_received    timestamptz;
    v_sha         text;
    v_size        bigint;
    v_type        text;
    v_interaction uuid;
    v_label       text;
    v_reference   text;
    v_observation uuid;
    v_obs_label   text;
    v_duplicate   boolean;
    v_problem     text;
BEGIN
    IF p_correlator IS NULL
       OR coalesce(jsonb_typeof(p_arrival), 'null') <> 'object'
       OR coalesce(jsonb_typeof(p_artifact), 'null') <> 'object' THEN
        RAISE EXCEPTION 'callback interaction refused' USING ERRCODE = '23514';
    END IF;

    SELECT * INTO t FROM resolve_callback_correlator(p_correlator) r;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'callback correlator refused' USING ERRCODE = '23514';
    END IF;

    v_host   := lower(nullif(p_arrival ->> 'host', ''));
    v_kind   := nullif(p_arrival ->> 'arrival_kind', '');
    v_peer   := coalesce(nullif(p_arrival ->> 'peer_class', ''), 'unknown');
    v_stated := nullif(p_arrival ->> 'received_at', '');
    v_sha    := nullif(p_artifact ->> 'sha256', '');
    v_type   := nullif(p_artifact ->> 'content_type', '');
    v_size   := (p_artifact ->> 'byte_size')::bigint;

    IF v_host IS NULL OR v_kind IS NULL OR v_sha IS NULL OR v_size IS NULL THEN
        RAISE EXCEPTION 'a callback interaction states a host, a kind and the bytes it received'
            USING ERRCODE = '23514';
    END IF;
    IF v_sha !~ '^[0-9a-f]{64}$' OR v_size < 0 THEN
        RAISE EXCEPTION 'callback interaction names bytes with no hash or no byte count'
            USING ERRCODE = '23514';
    END IF;
    -- The listener's moment when there is one, and the acceptance moment when
    -- there is not. A caller with no timestamp is not refused: an operator
    -- holding a recording whose format carries no clock still has an arrival,
    -- and filing it under the acceptance moment is what this function did for
    -- every row that exists. What it costs them is the deduplication -- two
    -- accepts of that recording are two moments and therefore two arrivals.
    --
    -- `now()` and not `clock_timestamp()`, which is what the column's DEFAULT
    -- was and what `enforce_callback_attribution` requires: that trigger refuses
    -- a row whose moment is after `now()`, the moment this transaction began,
    -- and `clock_timestamp()` is by definition after it. MEASURED: stating it
    -- here answers `callback interaction claims to have arrived at ..., outside
    -- its correlator's lifetime` for an arrival that is being accepted right now.
    IF v_stated IS NULL THEN
        v_received := now();
    ELSE
        BEGIN
            v_received := v_stated::timestamptz;
        EXCEPTION WHEN invalid_datetime_format OR datetime_field_overflow THEN
            RAISE EXCEPTION 'callback interaction states a received_at that is not a moment: %',
                v_stated USING ERRCODE = '23514';
        END;
    END IF;
    -- The name and the correlator arrive as two arguments, and nothing but this
    -- makes them one claim: resolving a live correlator says a canary of this
    -- Program fired, and the name says which. Asked here as well as in the
    -- trigger, so the convenience and the guarantee refuse the same rows.
    IF callback_correlator_label(v_host, t.channel_host) IS DISTINCT FROM p_correlator THEN
        RAISE EXCEPTION 'callback interaction arrived at %, which does not carry the correlator it claims',
            v_host USING ERRCODE = '23514';
    END IF;

    PERFORM set_actor('runtime');
    INSERT INTO artifacts (sha256, byte_size, content_type, visibility, encrypted)
    VALUES (v_sha, v_size, v_type, 'agent_visible', false)
    ON CONFLICT (sha256) DO NOTHING;

    -- The same disagreement check `record_proxy_exchange` makes, for the same
    -- reason: the store is one namespace keyed by the hash of the plaintext, so
    -- these bytes may already be registered by another Program's identical
    -- ones. What must not pass is a hash registered with a different length or
    -- under a visibility this Observation may not cite.
    SELECT CASE
             WHEN a.sha256 IS NULL THEN 'not registered'
             WHEN a.byte_size <> v_size THEN 'registered as ' || a.byte_size || ' byte(s)'
             WHEN a.visibility <> 'agent_visible' OR a.encrypted
                  THEN 'registered as ' || a.visibility
             WHEN a.purged_at IS NOT NULL THEN 'purged'
           END
      INTO v_problem
      FROM (SELECT 1) one
      LEFT JOIN artifacts a ON a.sha256 = v_sha;
    IF v_problem IS NOT NULL THEN
        RAISE EXCEPTION 'callback interaction names bytes it did not store: % (%)',
            v_sha, v_problem USING ERRCODE = '23514';
    END IF;

    INSERT INTO artifact_references (program_id, sha256, kind)
    VALUES (t.program_id, v_sha, 'runtime')
    ON CONFLICT (program_id, sha256, kind) DO NOTHING;
    SELECT ar.label INTO v_reference
      FROM artifact_references ar
     WHERE ar.program_id = t.program_id AND ar.sha256 = v_sha AND ar.kind = 'runtime';

    INSERT INTO callback_interactions
        (program_id, correlator_id, channel_name, arrival_kind, observed_host,
         peer_class, received_at, body_sha256, byte_size)
    VALUES (t.program_id, t.correlator_id, t.channel_name, v_kind, v_host,
            v_peer, v_received, v_sha, v_size)
    ON CONFLICT ON CONSTRAINT callback_interactions_arrival_key DO NOTHING
    RETURNING id, label INTO v_interaction, v_label;

    v_duplicate := v_interaction IS NULL;

    IF v_duplicate THEN
        -- The arrival is already recorded. Answering with the rows it resolved
        -- to rather than raising is what makes `rk callback accept` safe to
        -- re-run: the operator asked for this arrival to be on the record, and
        -- it is. `duplicate` is how they tell that from having recorded a
        -- second one.
        --
        -- These six columns are the constraint's, restated because DO NOTHING
        -- yields no row and DO UPDATE would touch one the immutability trigger
        -- refuses. Whoever edits `callback_interactions_arrival_key` edits this
        -- WHERE with it: they are one identity written twice, and only the
        -- constraint is enforced.
        SELECT ci.id, ci.label INTO v_interaction, v_label
          FROM callback_interactions ci
         WHERE ci.program_id    = t.program_id
           AND ci.correlator_id = t.correlator_id
           AND ci.arrival_kind  = v_kind
           AND ci.observed_host = v_host
           AND ci.body_sha256   = v_sha
           AND ci.received_at   = v_received;

        -- The row this insert lost to can be one this transaction cannot see:
        -- under a snapshot older than the transaction that wrote it -- anything
        -- above READ COMMITTED -- the conflict is real and the row is invisible,
        -- and the SELECT above finds nothing. That is a lost race rather than a
        -- broken record, and the answer is to accept the file again, so it is
        -- reported under the class a caller retries rather than as a record that
        -- contradicts itself.
        IF v_interaction IS NULL THEN
            RAISE EXCEPTION 'this arrival is being recorded by another transaction that has not committed'
                USING ERRCODE = '40001';
        END IF;

        BEGIN
            SELECT o.id, o.label INTO STRICT v_observation, v_obs_label
              FROM observations o
             WHERE o.program_id = t.program_id
               AND o.callback_interaction_id = v_interaction;
        EXCEPTION
            WHEN no_data_found THEN
                RAISE EXCEPTION 'the arrival % is recorded with no Observation to cite', v_label
                    USING ERRCODE = '23514';
            WHEN too_many_rows THEN
                RAISE EXCEPTION 'the arrival % is cited by more than one Observation', v_label
                    USING ERRCODE = '23514';
        END;
    ELSE
        -- The summary names the channel and the bytes and not the host. The
        -- host carries the correlator, and this string is the one part of the
        -- record an agent reads.
        INSERT INTO observations
            (program_id, subject_entity_id, kind, summary, provenance_kind,
             callback_interaction_id, observed_at, metadata)
        VALUES (t.program_id, t.subject_entity_id, 'callback_interaction',
                'an out-of-band ' || v_kind || ' interaction arrived on channel '
                  || t.channel_name || ' carrying this subject''s correlator, '
                  || v_size || ' byte(s) stored as ' || coalesce(v_reference, v_sha),
                'callback', v_interaction, v_received,
                jsonb_build_object('interaction', v_label,
                                   'channel', t.channel_name,
                                   'arrival_kind', v_kind,
                                   'byte_size', v_size))
        RETURNING id, label INTO v_observation, v_obs_label;
    END IF;

    -- One answer for both paths, because they are the same answer: these are
    -- the rows this arrival resolves to. `duplicate` says whether this call is
    -- what put them there.
    RETURN jsonb_build_object(
        'interaction_id', v_interaction, 'interaction', v_label,
        'observation_id', v_observation, 'observation', v_obs_label,
        'artifact', v_reference, 'sha256', v_sha,
        'channel', t.channel_name, 'correlator_id', t.correlator_id,
        'received_at', v_received, 'duplicate', v_duplicate);
END $fn$;

COMMENT ON FUNCTION record_callback_interaction(text, jsonb, jsonb) IS
  'Accepts one inbound interaction: resolves the correlator, registers the exact bytes, writes the arrival and promotes it into an immutable Observation, in one transaction or not at all. An arrival already on the record -- same Program, correlator, name, bytes and moment -- resolves to the rows it already produced and answers duplicate.';

-- `observed_at` is the arrival's moment rather than the acceptance moment for
-- the same reason the arrival's own column is: an Observation whose timestamp
-- says when somebody got round to filing it is one that cannot be read against
-- the Receipt whose payload carried the canary. Rows written before this file
-- carry the acceptance moment, which is the closest thing to it that was
-- recorded; nothing rewrites them, because an Observation is immutable.


-- ---------------------------------------------------------------------------
-- 3. The invariants this file must not have broken
-- ---------------------------------------------------------------------------

DO $$
DECLARE n integer; d text;
BEGIN
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_program_isolation();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-67 refuses to finish: % isolation violation(s): %', n, d;
    END IF;

    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_purge_travel();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-67 refuses to finish: % purge violation(s): %', n, d;
    END IF;
END $$;
