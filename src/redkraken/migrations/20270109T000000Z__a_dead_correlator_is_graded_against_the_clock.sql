-- ---------------------------------------------------------------------------
-- 20270109T000000Z__a_dead_correlator_is_graded_against_the_clock.sql
--                                                                  (ticket 215)
--
-- A correlator is minted against the wall clock: `mint_callback_correlator`
-- writes `clock_timestamp() + p_lifetime`. Resolving one also reads the wall
-- clock, because the question is whether it is live when that statement runs.
-- The insert guard said it asked the same question but compared `expires_at`
-- with `now()`, PostgreSQL's transaction-start timestamp. A transaction begun
-- while the correlator was live could therefore keep admitting it after the
-- wall clock passed its expiry. The one-millisecond test in
-- `CallbackAdmissionTest` exposed the same disagreement as a race between the
-- mint COMMIT and the refusing BEGIN.
--
-- `issued_at` deliberately stays on `now()`: it records the transaction that
-- minted the row. The expiry arm is not a stamping arm. It grades liveness at
-- the instant the guarded INSERT executes, so it uses `clock_timestamp()` just
-- like `resolve_callback_correlator`. `NEW.received_at` remains compared with
-- `now()` in the separate claimed-window arm; that check asks whether the
-- caller stated a future moment, not whether the correlator is live now.
--
-- Copied whole from
-- `20260912T000000Z__an_out_of_band_host_is_bound_not_declared.sql`; the only
-- executable change is `t.expires_at <= clock_timestamp()`.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION enforce_callback_attribution() RETURNS trigger
LANGUAGE plpgsql AS $fn$
DECLARE
    t          record;
    v_endpoint text;
BEGIN
    SELECT tk.program_id, tk.channel_name, tk.issued_at, tk.expires_at,
           tk.cleared_at, tk.correlator_sha256, tk.binding_id,
           c.kind, c.host, c.placement, c.provider
      INTO t
      FROM callback_correlators tk
      JOIN programs p
        ON p.id = tk.program_id AND p.closed_at IS NULL
      JOIN program_callback_channels c
        ON c.program_id = tk.program_id
       AND c.version = p.scope_version
       AND c.name = tk.channel_name
     WHERE tk.id = NEW.correlator_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'callback interaction names no live correlator on a declared channel'
            USING ERRCODE = '23514';
    END IF;
    IF t.program_id <> NEW.program_id THEN
        RAISE EXCEPTION 'callback correlator belongs to another Program'
            USING ERRCODE = '23514';
    END IF;
    -- Against the wall clock rather than against either `NEW.received_at` or
    -- the transaction clock. The row can backdate its own received_at, and
    -- `now()` is fixed when the transaction begins. Neither answers whether
    -- the correlator is live when this INSERT runs. The resolver reads
    -- `clock_timestamp()` for the same reason.
    IF t.cleared_at IS NOT NULL OR t.expires_at <= clock_timestamp() THEN
        RAISE EXCEPTION 'callback correlator was not live when the interaction arrived'
            USING ERRCODE = '23514';
    END IF;
    -- This is the other clock question. `received_at` is the listener's stated
    -- moment, so it must be inside the minted window and no later than the
    -- transaction accepting it. It does not decide whether the correlator is
    -- live now; the arm above does.
    IF NEW.received_at < t.issued_at
       OR NEW.received_at >= t.expires_at
       OR NEW.received_at > now() THEN
        RAISE EXCEPTION 'callback interaction claims to have arrived at %, outside its correlator''s lifetime',
            NEW.received_at USING ERRCODE = '23514';
    END IF;
    IF NEW.channel_name <> t.channel_name OR NEW.arrival_kind <> t.kind THEN
        RAISE EXCEPTION 'callback interaction claims channel % (%), correlator names % (%)',
            NEW.channel_name, NEW.arrival_kind, t.channel_name, t.kind
            USING ERRCODE = '23514';
    END IF;

    IF t.provider = 'static' THEN
        IF t.binding_id IS NOT NULL THEN
            RAISE EXCEPTION 'callback correlator names a binding on a channel that declares its own host'
                USING ERRCODE = '23514';
        END IF;
        v_endpoint := t.host;
    ELSE
        IF t.binding_id IS NULL THEN
            RAISE EXCEPTION 'callback correlator on channel % names no binding, and that channel''s endpoint is bound rather than declared',
                t.channel_name USING ERRCODE = '23514';
        END IF;
        SELECT b.endpoint_host INTO v_endpoint
          FROM callback_channel_bindings b
         WHERE b.id = t.binding_id AND b.program_id = t.program_id
           AND b.released_at IS NULL;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'callback correlator was minted against an endpoint that is no longer bound'
                USING ERRCODE = '23514';
        END IF;
    END IF;

    IF NOT callback_host_admitted(NEW.observed_host, v_endpoint) THEN
        RAISE EXCEPTION 'callback interaction arrived at %, which channel % does not admit',
            NEW.observed_host, t.channel_name
            USING ERRCODE = '23514';
    END IF;
    IF (t.placement = 'path') <> (NEW.observed_path IS NOT NULL) THEN
        RAISE EXCEPTION 'callback interaction on channel % carries % path, and its correlator sits in the %',
            t.channel_name,
            CASE WHEN NEW.observed_path IS NULL THEN 'no' ELSE 'a' END,
            t.placement USING ERRCODE = '23514';
    END IF;
    IF encode(digest(callback_correlator_claimed(t.placement, NEW.observed_host,
                                                 NEW.observed_path, v_endpoint),
                     'sha256'), 'hex')
       IS DISTINCT FROM t.correlator_sha256 THEN
        RAISE EXCEPTION 'callback interaction arrived at %, which does not carry the correlator it claims',
            coalesce(NEW.observed_path, NEW.observed_host) USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $fn$;

COMMENT ON FUNCTION enforce_callback_attribution() IS
    'Admits an arrival only under a live correlator and the endpoint it was minted against. Correlator liveness is graded against clock_timestamp(), while the caller-stated received_at is graded separately against the minted window and the accepting transaction.';

DO $check$
BEGIN
    IF position('t.expires_at <= clock_timestamp()' IN
                pg_get_functiondef('enforce_callback_attribution()'::regprocedure)) = 0 THEN
        RAISE EXCEPTION 'enforce_callback_attribution does not grade expiry against the wall clock';
    END IF;
END $check$;
