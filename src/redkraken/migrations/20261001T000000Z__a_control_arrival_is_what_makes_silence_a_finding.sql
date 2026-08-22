-- ---------------------------------------------------------------------------
-- 20261001T000000Z__a_control_arrival_is_what_makes_silence_a_finding.sql
--                                                                   (ticket 98)
--
-- The fifth criterion of ticket 98, and the last one: a positive control, so
-- that an out-of-band reading that comes back empty is a fact about the target
-- rather than a fact about us.
--
-- WHAT WAS WRONG WITH THE STATE THIS FILE FOUND.
--
-- Ticket 69 gave `rk oob up` one proof before it binds a name: `_listening`
-- asks the publisher for `/health` on the loopback address and refuses to bind
-- in front of nothing. That answers "is a socket open here", and it answers it
-- with a request the publisher deliberately does not record -- the health path
-- is the one target this host answers without writing anything down. So
-- nothing in the tree has ever demonstrated that an arrival on a channel would
-- reach `record_callback_interaction` at all. An hour later a step reports "no
-- arrival inside the declared window", and that sentence is indistinguishable
-- from "the correlator resolved to nothing", "the writer refused every row" and
-- "the publisher died at noon". A negative result carried no information.
--
-- WHAT A CONTROL IS HERE, AND WHAT IT DELIBERATELY IS NOT.
--
-- It is a request this harness makes of its own publisher at the name the
-- publisher is bound to, carrying a correlator minted for the occasion, which
-- travels the whole of the ordinary path: `Request._answer` reads the first
-- segment, `_serves` resolves it, `_record` stores the request bytes and calls
-- the writer, and a row lands in `callback_interactions`. When that row is
-- there, "nothing came back" is a statement about the target.
--
-- It is not a proof that Cloudflare's edge is routing. Proving that would mean
-- this process dialling a public hostname, and every outbound request this
-- installation makes goes through the door -- a second dialler in `oob.py`
-- reaching a name no scope rule admits is the alternate path the whole harness
-- is built to make impossible. So the control is taken at the socket the tunnel
-- forwards to, carrying the bound name in its `Host` header, which is byte for
-- byte the shape an arrival from the edge has on this side. What it proves is
-- everything from that socket inwards; the tunnel process being alive is the
-- other half, and `_reap` is what asks that.
--
-- WHY THE CORRELATOR THAT CARRIES IT HAS NO SUBJECT.
--
-- 14 wrote `subject_entity_id` NOT NULL and said why: "an Observation has a
-- subject, so a correlator with none would produce a fact about nothing". A
-- control is precisely the correlator that is about nothing -- no Entity of the
-- target was involved, and filing an Observation against whichever Entity
-- happened to be at hand would put a true sentence about our own fetch on the
-- evidence surface under a subject it is not about. So `is_control` and a null
-- subject are one state, tied together by a CHECK, and `record_callback_interaction`
-- writes the arrival and no Observation for it. The interaction is still a row,
-- still immutable, still cited by the freshness reader below; it is simply not
-- evidence, which is what "non-evidential for the target" means.
--
-- WHY THE REFUSAL IS IN TWO PLACES.
--
-- `rk callback provision` is the operator's path and `request_callback_correlator`
-- is the agent's, and they mint through the same table. A freshness clause in
-- the CLI alone would leave every Playbook step unguarded; one in the verb
-- alone would leave the operator unguarded. Both ask `callback_control_arrival`,
-- which is where the window is written down, so there is one number and not two.


-- ===========================================================================
-- 1. A correlator that is about our own plumbing rather than about a subject
-- ===========================================================================

ALTER TABLE callback_correlators
    ADD COLUMN is_control boolean NOT NULL DEFAULT false;

-- The NOT NULL 14 wrote is relaxed exactly as far as the marker above, and no
-- further: a canary still has a subject and a control still may not have one,
-- which is the same rule stated as an equality rather than as two columns that
-- happen to agree. `MATCH SIMPLE` is what makes this safe against the composite
-- key beneath it -- a row with a null in the pair is not checked against
-- `entities` at all, so 017's rule 3 still holds for every row that names one.
ALTER TABLE callback_correlators
    ALTER COLUMN subject_entity_id DROP NOT NULL,
    ADD CONSTRAINT callback_correlators_control_subject_check
        CHECK ((subject_entity_id IS NULL) = is_control);

COMMENT ON COLUMN callback_correlators.is_control IS
  'Ticket 98. True for a correlator this harness minted to fetch itself: the arrival it carries proves the channel records, and is a fact about this installation rather than about any Entity. Such a correlator has no subject and its arrival gets no Observation.';

-- Re-issued because the constraint on this column moved in this file. 14's
-- reason for requiring it is unchanged and is now the reason a control is the
-- one correlator that may not have one.
COMMENT ON COLUMN callback_correlators.subject_entity_id IS
  'The Entity the Observation an arrival produces is about. Required for a canary, because an Observation has a subject and a correlator with none would produce a fact about nothing; refused for a control, which is the correlator that is about nothing.';

-- The freshness read below asks for the newest control arrival of one channel
-- on one binding. Partial, because controls are a handful of rows beside every
-- canary a Program ever minted.
CREATE INDEX callback_correlators_control_idx
    ON callback_correlators (program_id, channel_name, binding_id)
 WHERE is_control;


-- ===========================================================================
-- 2. Minting one, which is not `mint_callback_correlator`'s job
-- ===========================================================================
-- A separate verb rather than an argument on 14's, for two reasons that point
-- the same way. Its signature is the one `check_callback_admission` names and
-- `runtime_verb_surface` registers, so widening it would move a row in two
-- registries to add a flag one caller sets. And every refusal it makes is about
-- a subject this call does not have. What is shared is the shape gate and the
-- binding lookup, restated here because they are three lines each and because a
-- control minted on a channel with no live binding is a request to a name that
-- is not ours.
--
-- The lifetime is five minutes and takes no argument. A control is fetched by
-- the same command that minted it, a few hundred milliseconds later, and
-- `rk oob up` clears it as soon as the arrival lands; the five minutes are
-- headroom for a slow machine and a ceiling for the case where the command
-- died between the mint and the clear.

CREATE FUNCTION mint_control_correlator(p_channel text, p_correlator text)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE
    v_program  uuid := rk2_program();
    v_version  integer;
    c          record;
    v_binding  uuid;
    v_endpoint text;
    v_id       uuid;
BEGIN
    IF v_program IS NULL OR p_channel IS NULL OR p_correlator IS NULL THEN
        RAISE EXCEPTION 'control correlator refused' USING ERRCODE = '23514';
    END IF;
    -- 14's shape, because a control travels in exactly the same request a
    -- canary does and is read out of it by the same two functions.
    IF p_correlator !~ '^[a-z0-9][a-z0-9-]{0,62}$' THEN
        RAISE EXCEPTION 'a correlator is one lower-case DNS label'
            USING ERRCODE = '23514';
    END IF;

    SELECT p.scope_version INTO v_version
      FROM programs p WHERE p.id = v_program AND p.closed_at IS NULL;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('outcome', 'refused', 'refusal',
            'this Program is closed, so nothing may be minted for it');
    END IF;

    SELECT ch.kind, ch.placement, ch.provider INTO c
      FROM program_callback_channels ch
     WHERE ch.program_id = v_program AND ch.version = v_version
       AND ch.name = p_channel;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('outcome', 'refused', 'refusal',
            format('channel %s is not declared by the live scope policy', p_channel));
    END IF;
    -- The honest limit of this whole mechanism, refused in words rather than
    -- worked around. A control is a request to our own publisher; a static
    -- channel is a name the operator wrote down and something else answers at,
    -- so there is no publisher of ours to ask and no control to take. Silence
    -- on such a channel stays what it has always been -- the absence of a
    -- refutation and not a refutation -- and the readers below say so rather
    -- than refusing a mint they cannot improve.
    IF c.provider = 'static' THEN
        RETURN jsonb_build_object('outcome', 'refused', 'refusal',
            format('channel %s declares its own endpoint, which this harness does not '
                   'publish, so there is no publisher of ours to take a control at',
                   p_channel));
    END IF;

    SELECT b.id, b.endpoint_host INTO v_binding, v_endpoint
      FROM callback_channel_bindings b
     WHERE b.program_id = v_program AND b.channel_name = p_channel
       AND b.released_at IS NULL;
    IF v_binding IS NULL THEN
        RETURN jsonb_build_object('outcome', 'refused', 'refusal',
            format('channel %s has no live binding, so there is no name to take a '
                   'control at', p_channel));
    END IF;

    PERFORM set_actor('runtime');
    INSERT INTO callback_correlators
        (program_id, scope_version, channel_name, correlator_sha256, subject_entity_id,
         expires_at, binding_id, is_control)
    VALUES (v_program, v_version, p_channel,
            encode(digest(p_correlator, 'sha256'), 'hex'), NULL,
            clock_timestamp() + interval '5 minutes', v_binding, true)
    RETURNING id INTO v_id;

    RETURN jsonb_build_object(
        'outcome', 'minted',
        'correlator_id', v_id::text,
        'channel', p_channel,
        'kind', c.kind,
        'placement', c.placement,
        'endpoint', v_endpoint,
        'binding_id', v_binding::text);
END $fn$;

COMMENT ON FUNCTION mint_control_correlator(text, text) IS
  'Mints the correlator a proof-of-life fetch carries: no subject, marked as a control, five minutes, against the channel''s live binding. Refuses a channel this harness does not publish, because a control is a request to our own publisher.';


-- ===========================================================================
-- 3. The one reader of the window, asked by both minting paths
-- ===========================================================================
-- Where the freshness window is written down, and it is written down once. Both
-- callers read `fresh` rather than the moment, so neither of them holds a copy
-- of the number and neither can drift from it.
--
-- Twenty-four hours, and the reason is in `oob.py`'s own first paragraph: a
-- quick tunnel's hostname is a fact about today. The control vouches for the
-- same span the name it was taken at is good for, and no longer -- a proof
-- taken last week says nothing about a machine that has been running since.
-- Shorter would be a trap: the only thing that takes a control is `rk oob up`,
-- and `up` cannot be re-run without releasing the binding, so a window an
-- operator could sit past in one working session would end an engagement's
-- canaries to prove they still worked.
--
-- `publishable` is the arm that keeps this honest for a channel nobody here
-- serves. It is false for a static channel, and both callers read it as "this
-- question does not apply", because refusing a static channel for want of a
-- control this harness has no way to take would withdraw a working capability
-- to make a point.

CREATE FUNCTION callback_control_arrival(p_channel text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE
    v_program uuid := rk2_program();
    -- The window, written down here and nowhere else. Its callers read `fresh`
    -- and print `window_seconds`; neither holds the number, so neither can
    -- drift from it.
    v_window  constant interval := interval '24 hours';
    v_seconds constant bigint := extract(epoch FROM v_window)::bigint;
    v_version integer;
    c         record;
    b         record;
    a         record;
BEGIN
    SELECT p.scope_version INTO v_version
      FROM programs p WHERE p.id = v_program AND p.closed_at IS NULL;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('declared', false, 'publishable', false,
            'has_control', false, 'fresh', false, 'window_seconds', v_seconds);
    END IF;

    SELECT ch.provider INTO c
      FROM program_callback_channels ch
     WHERE ch.program_id = v_program AND ch.version = v_version
       AND ch.name = p_channel;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('declared', false, 'publishable', false,
            'has_control', false, 'fresh', false, 'window_seconds', v_seconds);
    END IF;
    IF c.provider = 'static' THEN
        RETURN jsonb_build_object('declared', true, 'publishable', false,
            'has_control', false, 'fresh', false, 'window_seconds', v_seconds,
            'reason', format('channel %s declares its own endpoint, which this harness '
                             'does not publish; no arrival on it is a refutation on its '
                             'own', p_channel));
    END IF;

    SELECT bb.id, bb.endpoint_host INTO b
      FROM callback_channel_bindings bb
     WHERE bb.program_id = v_program AND bb.channel_name = p_channel
       AND bb.released_at IS NULL;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('declared', true, 'publishable', true,
            'bound', false, 'has_control', false, 'fresh', false,
            'window_seconds', v_seconds,
            'reason', format('channel %s has no live binding, so nothing has been '
                             'proved about it', p_channel));
    END IF;

    -- On this binding, and never on a released one. A control is a measurement
    -- of one endpoint: the name released this morning was proved yesterday, and
    -- carrying that proof forward to whatever `rk oob up` bound next would be
    -- the exact substitution this whole file exists to refuse.
    SELECT ci.label, ci.received_at, ci.correlator_id INTO a
      FROM callback_interactions ci
      JOIN callback_correlators t
        ON t.id = ci.correlator_id AND t.program_id = ci.program_id
     WHERE ci.program_id = v_program
       AND ci.channel_name = p_channel
       AND t.is_control
       AND t.binding_id = b.id
     ORDER BY ci.received_at DESC
     LIMIT 1;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('declared', true, 'publishable', true,
            'bound', true, 'endpoint', b.endpoint_host, 'has_control', false,
            'fresh', false, 'window_seconds', v_seconds,
            'reason', format('nothing has ever arrived at %s to prove this channel '
                             'records', b.endpoint_host));
    END IF;

    RETURN jsonb_build_object(
        'declared', true, 'publishable', true, 'bound', true,
        'endpoint', b.endpoint_host,
        'has_control', true,
        'fresh', a.received_at > clock_timestamp() - v_window,
        'interaction', a.label,
        'correlator_id', a.correlator_id::text,
        'received_at', a.received_at,
        'age_seconds', floor(extract(epoch FROM clock_timestamp() - a.received_at))::bigint,
        'window_seconds', v_seconds);
END $fn$;

COMMENT ON FUNCTION callback_control_arrival(text) IS
  'The proof-of-life arrival one channel is standing on: whether this harness publishes the channel at all, whether an arrival on a control correlator ever reached the live binding, when, and whether that is inside the window. The one place the window is written down; `rk callback provision` and `request_callback_correlator` both read `fresh` from here rather than the moment.';


-- ===========================================================================
-- 4. The writer, which now knows a control when it resolves one
-- ===========================================================================
-- 69's function, copied whole and changed in four places, because a control
-- arrives through the same call the publisher makes for every other request and
-- there must not be a second writer with its own opinion about attribution. The
-- four are marked in the body: one more local, one read of `is_control` off the
-- correlator, and the two branches that write an Observation, each now taken
-- only for a canary. Everything else -- the artifact registration, the arrival
-- key, the duplicate answer, every refusal -- is 69's, unmodified.

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
    v_path        text;
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
    v_control     boolean;
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

    -- Ticket 98's one addition to this function, and the whole of it. A control
    -- correlator is one this harness minted to fetch itself, so the arrival it
    -- carries is a fact about our own plumbing and about no Entity at all --
    -- which is why it has no subject to file an Observation under and why the
    -- two branches below skip writing one. Read from the table rather than
    -- added to `resolve_callback_correlator`'s return type, because that would
    -- be a DROP and a re-grant of a function three other things read, for a
    -- boolean this is the only caller of.
    SELECT cc.is_control INTO v_control
      FROM callback_correlators cc WHERE cc.id = t.correlator_id;
    -- The resolver just returned this row, so the SELECT above found it. The
    -- coalesce is there because a null would take neither branch below and
    -- write neither the Observation nor the refusal -- a canary that recorded
    -- an arrival nothing can cite, which is the one failure this function's
    -- own duplicate arm exists to shout about.
    v_control := coalesce(v_control, false);

    v_host   := lower(nullif(p_arrival ->> 'host', ''));
    -- Not lowercased and not decoded: a path is case-sensitive and the segment
    -- is compared against a digest.
    v_path   := nullif(p_arrival ->> 'path', '');
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
    IF (t.channel_placement = 'path') <> (v_path IS NOT NULL) THEN
        RAISE EXCEPTION 'channel % carries its correlator in the %, and this arrival states % path',
            t.channel_name, t.channel_placement,
            CASE WHEN v_path IS NULL THEN 'no' ELSE 'a' END
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
    -- The name, the path and the correlator arrive as separate arguments, and
    -- nothing but this makes them one claim: resolving a live correlator says a
    -- canary of this Program fired, and the arrival says which. Asked here as
    -- well as in the trigger, so the convenience and the guarantee refuse the
    -- same rows.
    IF callback_correlator_claimed(t.channel_placement, v_host, v_path, t.channel_host)
       IS DISTINCT FROM p_correlator THEN
        RAISE EXCEPTION 'callback interaction arrived at %, which does not carry the correlator it claims',
            coalesce(v_path, v_host) USING ERRCODE = '23514';
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
         observed_path, peer_class, received_at, body_sha256, byte_size)
    VALUES (t.program_id, t.correlator_id, t.channel_name, v_kind, v_host,
            v_path, v_peer, v_received, v_sha, v_size)
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
        -- constraint is enforced. `observed_path` is deliberately not among
        -- them -- it travels in the bytes of the request that produced it, so
        -- two arrivals differing only in path already differ in `body_sha256`.
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

        -- A control's arrival has no Observation to find, so not finding one is
        -- not the corruption this arm was written to catch. Everything above it
        -- still runs: a control fetched twice is still one arrival.
        IF NOT v_control THEN
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
        END IF;
    -- A new arrival on a canary. A new arrival on a control falls off the end of
    -- this block having written the interaction and nothing else, which is the
    -- point: 14 wrote that `subject_entity_id` is not optional "because an
    -- Observation has a subject, so a correlator with none would produce a fact
    -- about nothing", and a control is exactly the correlator that is about
    -- nothing on the target's side.
    ELSIF NOT v_control THEN
        -- The summary names the channel and the bytes and neither the host nor
        -- the path. Both carry the correlator, and this string is the one part
        -- of the record an agent reads.
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
        'received_at', v_received, 'duplicate', v_duplicate,
        'is_control', v_control);
END $fn$;


-- ===========================================================================
-- 5. The agent-facing verb, with the clause its own ticket left it owing
-- ===========================================================================
-- `request_callback_correlator` shipped in
-- `20260928T010000Z__a_step_mints_its_own_correlator.sql`, which is applied and
-- must not be edited: what applied, applied. So it is replaced here, whole, and
-- what is added is the sixth arm of the same block -- one more refusal in the
-- same shape as the five already there, and the `control` key beside the
-- address so that a step reading nothing back can cite what proved the channel
-- was listening.
--
-- Replaced rather than wrapped because the refusal has to sit between the
-- binding lookup and the mint. A wrapper would have to repeat the five lookups
-- to know where in the sequence it was, and a second function answering "may
-- this step mint" is the second answer that eventually disagrees.

CREATE OR REPLACE FUNCTION request_callback_correlator(
        p_channel    text,
        p_correlator text,
        p_subject    text,
        p_agent_run  uuid DEFAULT NULL)
RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p          uuid := rk2_program_required();
    v_channel  text := btrim(coalesce(p_channel, ''));
    v_said     text := btrim(coalesce(p_subject, ''));
    v_version  integer;
    v_declared text[];
    v_entity   uuid;
    v_tool_run uuid;
    v_binding  jsonb;
    v_control  jsonb;
    v_id       uuid;
    v_expires  timestamptz;
BEGIN
    -- The provenance guard first, in `propose_finding`'s words and for its
    -- reason: an Agent run belonging to another Program is not a run this
    -- correlator may be attributed to, and the composite foreign key on
    -- `callback_correlators` would raise on the Tool run resolved from it.
    IF NOT EXISTS (
        SELECT 1 FROM agent_runs ar WHERE ar.id = p_agent_run AND ar.program_id = p
    ) THEN
        RETURN jsonb_build_object('outcome', 'refused', 'refusal',
            'the Agent run asking for this correlator is not a run of this Program');
    END IF;

    SELECT pr.scope_version INTO v_version
      FROM programs pr WHERE pr.id = p AND pr.closed_at IS NULL;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('outcome', 'refused', 'refusal',
            'this Program is closed, so no new correlator may be minted for it');
    END IF;

    -- One channel per Program, checked as a count and reported as one. The
    -- scope compiler admits several and `mint_callback_correlator` would take
    -- any of them; what this verb will not do is pick. A model that is told
    -- "there are two, they are these" can say which; a model handed the first
    -- row has planted a name it did not choose in somebody else's system.
    SELECT array_agg(c.name ORDER BY c.name) INTO v_declared
      FROM program_callback_channels c
     WHERE c.program_id = p AND c.version = v_version;
    IF v_declared IS NULL THEN
        RETURN jsonb_build_object('outcome', 'refused', 'refusal',
            'this Program declares no out-of-band channel, so there is no name to plant');
    END IF;
    IF array_length(v_declared, 1) <> 1 THEN
        RETURN jsonb_build_object('outcome', 'refused', 'refusal',
            format('this Program declares %s out-of-band channels (%s) and a step mints on one',
                   array_length(v_declared, 1), array_to_string(v_declared, ', ')));
    END IF;
    IF v_declared[1] IS DISTINCT FROM v_channel THEN
        RETURN jsonb_build_object('outcome', 'refused', 'refusal',
            format('%s is not this Program''s out-of-band channel; it declares %s',
                   coalesce(nullif(v_channel, ''), '(none)'), v_declared[1]));
    END IF;

    SELECT e.id INTO v_entity
      FROM entities e WHERE e.program_id = p AND e.label = v_said;
    IF v_entity IS NULL THEN
        RETURN jsonb_build_object('outcome', 'refused', 'refusal',
            format('%s is not an Entity of this Program, and a correlator has a subject '
                   'because the Observation it produces has one',
                   coalesce(nullif(v_said, ''), '(none)')));
    END IF;

    -- The run that will plant it. `callback_correlators` binds to a Tool run or
    -- a Test run and to neither an Agent run nor a Task, so the narrowest true
    -- binding available for a child is the egress Tool run its own requests go
    -- out on -- the one `execution._authorize` opened for this attempt, which
    -- is also the run every Receipt for the planting request will hang off.
    --
    -- The literal is the tool name the RUNTIME opens the run under, which is
    -- not the name the model calls the door by. Ticket 97 recorded that hazard
    -- in `roster.py` above the served name; this is the other end of it, and a
    -- ticket that changed which name a Tool run is opened under would have to
    -- change this line with it.
    SELECT tr.id INTO v_tool_run
      FROM tool_runs tr
     WHERE tr.program_id = p AND tr.agent_run_id = p_agent_run
       AND tr.tool = 'mcp__rk2__net_request'
     ORDER BY tr.started_at DESC
     LIMIT 1;
    IF v_tool_run IS NULL THEN
        RETURN jsonb_build_object('outcome', 'refused', 'refusal',
            'this run has no egress Tool run, so it has no way to carry a correlator out');
    END IF;

    -- Where the channel is answering, asked of the database and not of any
    -- configuration this process read: a bound channel answers at whatever
    -- `rk oob up` last bound, and a name composed from a stale binding is a
    -- canary nothing can reach.
    v_binding := callback_channel_binding(v_channel);
    IF NOT coalesce((v_binding ->> 'bound')::boolean, false) THEN
        RETURN jsonb_build_object('outcome', 'refused', 'refusal',
            format('channel %s has no live binding, so there is no name to embed; '
                   '`rk oob up` binds one', v_channel));
    END IF;

    -- The sixth refusal, and the one ticket 98's fifth criterion is about. A
    -- canary that never comes back is only a fact about the target if something
    -- proves an arrival on this channel would have been recorded; without that
    -- proof a dead publisher and an uninteresting target are the same reading,
    -- and a step that reported the second would be reporting the first.
    -- `callback_control_arrival` is the same reader `rk callback provision`
    -- asks, and it is asked in both places on purpose: the clause in one and
    -- not the other would leave whichever half was missed minting against a
    -- channel nothing has vouched for.
    v_control := callback_control_arrival(v_channel);
    IF coalesce((v_control ->> 'publishable')::boolean, false)
       AND NOT coalesce((v_control ->> 'fresh')::boolean, false) THEN
        RETURN jsonb_build_object('outcome', 'refused', 'refusal',
            format('channel %s has no proof-of-life arrival inside the last %s second(s), '
                   'so nothing failing to come back on it would be a fact about the target; '
                   '`rk oob up` takes one when it binds the name',
                   v_channel, v_control ->> 'window_seconds'));
    END IF;

    -- Every refusal `mint_callback_correlator` can raise is about the same five
    -- things this function has just checked, so reaching one of them means the
    -- two disagree. It is still answered rather than raised: a child holding a
    -- tool that failed learns nothing, and a child holding the sentence can
    -- report it.
    BEGIN
        v_id := mint_callback_correlator(
            v_channel, p_correlator, v_entity, interval '1 hour', v_tool_run, NULL);
    EXCEPTION WHEN OTHERS THEN
        RETURN jsonb_build_object('outcome', 'refused', 'refusal', SQLERRM);
    END;

    SELECT cc.expires_at INTO v_expires
      FROM callback_correlators cc WHERE cc.id = v_id;

    RETURN jsonb_build_object(
        'outcome', 'minted',
        'correlator_id', v_id::text,
        -- The one string a step embeds, composed by the rule `callback._address`
        -- states for the operator path: a label channel is addressed by name,
        -- because a DNS query carries no path, and a path channel is one bound
        -- host serving every canary of a Program under its own first segment.
        -- Two copies of one rule, and the assertion in section 2 is what holds
        -- them together; a later ticket that gave `rk callback provision` this
        -- verb to call would leave one.
        'address', CASE WHEN v_binding ->> 'placement' = 'path'
                        THEN 'https://' || (v_binding ->> 'endpoint') || '/' || p_correlator || '/'
                        ELSE p_correlator || '.' || (v_binding ->> 'endpoint') END,
        'channel', v_channel,
        'kind', v_binding ->> 'kind',
        'placement', v_binding ->> 'placement',
        'subject_label', v_said,
        'expires_at', v_expires::text,
        -- Beside the address rather than instead of it. A step that reads
        -- nothing back has to cite what proved the channel was recording, and
        -- the moment it proved it, or the reading is an absence with no
        -- provenance.
        'control', v_control);
END $fn$;

-- Re-issued because what this verb answers changed: it refuses one more thing
-- and it hands back one more key. The comment 98 wrote enumerated the five
-- lookups; a reader who found that list and not the sixth would think a step
-- may mint on a channel nothing has vouched for.
COMMENT ON FUNCTION request_callback_correlator(text, text, text, uuid) IS
    'Ticket 98. The agent-facing half of `mint_callback_correlator`: a channel '
    'name and an Entity label a child can read, resolved to the live scope '
    'version, the Program''s one declared channel, its live binding, the '
    'subject Entity, the egress Tool run that will carry the name out, and the '
    'proof-of-life arrival that says this channel records at all. Answers the '
    'address to embed, the correlator id and the control to cite beside a '
    'reading, or a refusal in words. The correlator itself is minted by the '
    'caller and the lifetime is fixed here, because neither is the model''s to '
    'choose.';


-- ===========================================================================
-- 6. What the runtime may execute, and the registry that says so
-- ===========================================================================
-- Both new verbs are the runtime's alone, for the reason every other callback
-- verb is: they write or read rows that carry correlators, and the three other
-- roles have no business in either. `request_callback_correlator` keeps the
-- grant and the registry row 98 gave it -- `CREATE OR REPLACE` disturbs
-- neither -- so nothing about it is re-issued here.

REVOKE ALL ON FUNCTION mint_control_correlator(text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION callback_control_arrival(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION mint_control_correlator(text, text) TO rk2_runtime;
GRANT EXECUTE ON FUNCTION callback_control_arrival(text) TO rk2_runtime;

-- 066's registry. `check_runtime_privileges` refuses a verb the runtime can
-- execute that no row here names, so each grant above is made twice on purpose:
-- the second half is the one a reader of the surface finds.
INSERT INTO runtime_verb_surface (verb, added_by, note) VALUES
    ('mint_control_correlator(text, text)',
     '98',
     'mints the subjectless correlator a proof-of-life fetch carries, so that an arrival on this channel can be demonstrated rather than assumed'),
    ('callback_control_arrival(text)',
     '98',
     'the proof-of-life arrival a channel is standing on, and whether it is inside the window -- the one place that window is written down');


-- ===========================================================================
-- 7. What this migration claims, asserted
-- ===========================================================================

DO $$
DECLARE
    v_definition text;
    v_source     text;
    n            integer;
    d            text;
BEGIN
    -- The marker and the state it is tied to. Asserted as the constraint's own
    -- text rather than by writing a row, because what has to stay true is that
    -- a control with a subject and a canary without one are both unwritable --
    -- and the only way to demonstrate that with a row is to leave one behind.
    SELECT pg_get_constraintdef(oid) INTO v_definition
      FROM pg_constraint
     WHERE conrelid = 'callback_correlators'::regclass
       AND conname = 'callback_correlators_control_subject_check';
    IF v_definition IS NULL
       OR v_definition NOT LIKE '%subject_entity_id IS NULL%'
       OR v_definition NOT LIKE '%is_control%' THEN
        RAISE EXCEPTION 'ticket 98: a control correlator and a subjectless one are no longer the same row'
          USING DETAIL = coalesce(v_definition, 'no such constraint');
    END IF;

    -- Nothing that already exists is a control. The column arrives defaulted
    -- false, and a corpus applied over an installation whose correlators were
    -- minted before this file must not have promoted any of them to a proof of
    -- anything.
    SELECT count(*) INTO n FROM callback_correlators WHERE is_control;
    IF n > 0 THEN
        RAISE EXCEPTION 'ticket 98: % correlator(s) minted before controls existed claim to be one', n;
    END IF;

    -- The writer reads the marker. If a later file replaced
    -- `record_callback_interaction` from 69's text without this read, every
    -- control arrival would try to file an Observation with a null subject --
    -- which `observations` refuses, so the publisher would answer targets and
    -- record nothing, silently, on the one path this ticket exists to make
    -- trustworthy.
    SELECT p.prosrc INTO v_source
      FROM pg_proc p WHERE p.proname = 'record_callback_interaction';
    IF v_source IS NULL OR v_source NOT LIKE '%is_control%' THEN
        RAISE EXCEPTION 'ticket 98: the arrival writer no longer knows a control from a canary';
    END IF;

    -- And the two minting paths ask the same reader. This is the claim the
    -- whole file rests on: the clause in one and not the other is the failure
    -- mode ticket 98 named in advance.
    SELECT p.prosrc INTO v_source
      FROM pg_proc p WHERE p.proname = 'request_callback_correlator';
    IF v_source IS NULL OR v_source NOT LIKE '%callback_control_arrival%' THEN
        RAISE EXCEPTION 'ticket 98: the agent-facing mint no longer asks whether anything proved the channel';
    END IF;

    -- Executable by its callers, and by them alone.
    IF NOT has_function_privilege('rk2_runtime', 'mint_control_correlator(text, text)', 'EXECUTE')
       OR NOT has_function_privilege('rk2_runtime', 'callback_control_arrival(text)', 'EXECUTE') THEN
        RAISE EXCEPTION 'ticket 98: the runtime cannot take or read a control';
    END IF;
    FOR d IN SELECT unnest(ARRAY['rk2_state', 'rk2_proxy', 'rk2_human']) LOOP
        IF has_function_privilege(d, 'mint_control_correlator(text, text)', 'EXECUTE')
           OR has_function_privilege(d, 'callback_control_arrival(text)', 'EXECUTE') THEN
            RAISE EXCEPTION 'ticket 98: % can reach a control verb', d;
        END IF;
    END LOOP;

    -- 69's closing move, for the same reason it made it: every arm of the
    -- standing check reads the two tables this file has just altered.
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_callback_admission();
    IF n > 0 THEN
        RAISE EXCEPTION 'ticket 98 refuses to finish: % callback problem(s): %', n, d;
    END IF;
END $$;
