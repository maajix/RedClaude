-- PH2-13: the aggregate request budget is spent at the egress door, by every
-- Tool run of a Program together rather than by each process on its own.
--
-- The prototype kept its token bucket in the proxy's own memory, which made
-- "the Program may send 100 requests" mean "each proxy may send 100 requests"
-- -- and a second worker doubled the budget without anything refusing. So the
-- bucket is a row here, the counter that says how much of the Program's total
-- is gone is a row here, and the in-flight slots are rows here. A reservation
-- taken under `SELECT ... FOR UPDATE` is what makes two concurrent Tool runs
-- see one budget, whether they are two threads or two containers.


-- ===========================================================================
-- 1. The limits, on the version that compiled them
-- ===========================================================================
-- ALTER TABLE is DDL, so the append-only row trigger on this table does not
-- fire: the statement says nothing about any version already written.
--
-- Nullable, and a NULL refuses every request rather than admitting an
-- unbounded one. No backfill is needed and none would be right: `burst` is a
-- new key under `[budgets]`, so every configuration compiles to a policy
-- document that hashes differently and every Program writes a new version on
-- its next run. A version compiled before this migration authorises nothing
-- because it never stated what it was authorising.

ALTER TABLE program_scope_versions
    ADD COLUMN budget_burst          integer CHECK (budget_burst > 0),
    ADD COLUMN budget_concurrency    integer CHECK (budget_concurrency > 0),
    ADD COLUMN budget_requests       integer CHECK (budget_requests > 0),
    ADD COLUMN budget_window_seconds integer CHECK (budget_window_seconds > 0);

COMMENT ON COLUMN program_scope_versions.budget_burst IS
  'Bucket capacity and refill numerator: the most requests one target may take at once, and the number refilled over one window. NULL refuses every request; an unstated limit is not an absent one.';
COMMENT ON COLUMN program_scope_versions.budget_concurrency IS
  'How many requests to one target may be in flight at once, across every Tool run of the Program and every process serving them.';
COMMENT ON COLUMN program_scope_versions.budget_requests IS
  'The Program''s total target contacts. Not per target and not per window: it is the whole engagement''s aggregate, and it does not refill.';


-- ===========================================================================
-- 2. Where the aggregate is kept
-- ===========================================================================

-- One row per Program: the total that does not refill. Separate from the
-- per-target buckets because it is a different question -- "has this Program
-- spent its engagement" rather than "is this target being hit too fast" -- and
-- a single row is also the mutex that makes the two questions answerable
-- together. Every reserver takes this row first, so the lock order across the
-- two tables is fixed and two targets cannot deadlock against each other.
CREATE TABLE program_egress_spend (
    program_id uuid PRIMARY KEY REFERENCES programs(id) ON DELETE CASCADE,
    contacted  bigint NOT NULL DEFAULT 0 CHECK (contacted >= 0),
    exhausted  bigint NOT NULL DEFAULT 0 CHECK (exhausted >= 0),
    started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    last_at    timestamptz
);

COMMENT ON TABLE program_egress_spend IS
  'The Program''s total target contacts, counted once for every process. Incremented when a slot is reserved and given back only when the door refused before opening a socket, so the number is contacts rather than attempts.';
COMMENT ON COLUMN program_egress_spend.exhausted IS
  'How many requests this Program was refused after its total was gone. Kept because the count is the operator''s signal that the engagement needs a decision, not just a bigger number.';

-- One row per (Program, target), where the target is the scope rule that
-- authorised the request rather than the hostname that spelled it. A policy
-- that admits `*.example.com` admits one target with many names, and a bucket
-- per name would let a thousand subdomains spend a thousand budgets.
CREATE TABLE program_egress_budget (
    program_id  uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    target      text NOT NULL CHECK (btrim(target) <> ''),
    -- Fractional on purpose: a bucket refilled by elapsed time holds part of a
    -- request, and rounding that away would make a slow trickle of requests
    -- free.
    tokens      numeric NOT NULL CHECK (tokens >= 0),
    refilled_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    contacted   bigint NOT NULL DEFAULT 0 CHECK (contacted >= 0),
    throttled   bigint NOT NULL DEFAULT 0 CHECK (throttled >= 0),
    PRIMARY KEY (program_id, target)
);

COMMENT ON TABLE program_egress_budget IS
  'The shared token bucket for one target of one Program. A row rather than process memory: two proxies serving one Program must see one bucket, which is the whole difference between a per-target rate limit and a per-process one.';

-- The in-flight slots. A concurrency limit cannot be a counter that is
-- incremented and decremented, because a proxy that is killed mid-exchange
-- never decrements and the limit would decay to zero. A row with an expiry is
-- self-healing: the slot comes back when the reservation lapses, whether or
-- not the process that took it is alive to release it.
CREATE TABLE egress_reservations (
    id          uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id  uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    tool_run_id uuid NOT NULL,
    target      text NOT NULL,
    reserved_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    expires_at  timestamptz NOT NULL,
    released_at timestamptz,
    -- NULL while the slot is held; on release, whether a socket was opened
    -- towards the target. What separates a spent request from a refunded one.
    contacted   boolean,
    CHECK (expires_at > reserved_at),
    CHECK ((released_at IS NULL) = (contacted IS NULL)),
    FOREIGN KEY (program_id, target)
        REFERENCES program_egress_budget (program_id, target) ON DELETE CASCADE,
    FOREIGN KEY (tool_run_id, program_id) REFERENCES tool_runs (id, program_id)
);

CREATE INDEX egress_reservations_live_idx
    ON egress_reservations (program_id, target)
 WHERE released_at IS NULL;

COMMENT ON TABLE egress_reservations IS
  'One live claim on one concurrency slot. Held rows are counted under the bucket lock, so admission is decided by rows every process can see rather than by a counter each one keeps.';

INSERT INTO purge_cascade_edges(table_name, column_name, rationale) VALUES
    ('program_egress_spend',  'program_id', 'program-scoped: the purge root'),
    ('program_egress_budget', 'program_id', 'program-scoped: the purge root'),
    ('egress_reservations',   'program_id', 'program-scoped: the purge root');

-- No row events. These three are counters on the hot path of every request,
-- and a row event per token spent would make the event log a copy of the
-- Receipt table with none of its meaning. What is durable about a refusal is
-- the blocked Receipt and the occurrence event below; what is durable about a
-- grant is the allowed Receipt.
INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
    ('program_egress_spend',  'bookkeeping',
     'the running total behind the receipts; every spend is a receipt already', '13'),
    ('program_egress_budget', 'bookkeeping',
     'the token bucket behind the receipts; refill is a clock reading, not an act', '13'),
    ('egress_reservations',   'bookkeeping',
     'in-flight slots, taken and given back within one exchange the receipt records', '13');

INSERT INTO event_types(id, family, subject_table, description) VALUES
    ('egress.throttled', 'occurrence', NULL,
     'the egress door refused a request for a per-target rate or concurrency limit'),
    ('egress.budget_exhausted', 'occurrence', NULL,
     'the egress door refused a request because the Program''s total is spent');


-- ===========================================================================
-- 3. Durable retry, on the Receipt that refused
-- ===========================================================================
-- An instant rather than a delay. The agent is not the only reader: a
-- scheduler deciding when to re-run a Task reads the row long after the
-- response header expired, and `Retry-After: 30` in a table means nothing
-- without the moment it was written beside it.

ALTER TABLE receipts ADD COLUMN retry_after timestamptz;
ALTER TABLE receipts ADD CONSTRAINT receipts_retry_after_is_a_refusal
    CHECK (retry_after IS NULL OR decision = 'blocked');

COMMENT ON COLUMN receipts.retry_after IS
  'When this refusal stops being true, for the refusals that stop being true. Null on a refusal that waiting does not fix -- a spent Program total is not a rate limit.';

CREATE OR REPLACE FUNCTION write_blocked_receipt(
    p_program uuid,
    p_receipt jsonb,
    p_capability text DEFAULT NULL
) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE
    v_receipt receipts%ROWTYPE;
    v_id      uuid;
    v_tool_run_id uuid;
    v_purpose text;
BEGIN
    IF p_program IS DISTINCT FROM rk2_program()
       OR coalesce(jsonb_typeof(p_receipt), 'null') <> 'object' THEN
        RAISE EXCEPTION 'blocked receipt refused' USING ERRCODE = '23514';
    END IF;
    IF p_capability IS NOT NULL
       AND position(p_capability IN p_receipt::text) > 0 THEN
        RAISE EXCEPTION 'receipt payload contains protected capability'
            USING ERRCODE = '23514';
    END IF;
    IF p_capability IS NOT NULL THEN
        SELECT a.tool_run_id INTO v_tool_run_id
          FROM resolve_egress_capability(p_capability) a;
    END IF;

    v_receipt := jsonb_populate_record(NULL::receipts, p_receipt);
    v_id := uuidv7();
    v_receipt.id := v_id;
    v_receipt.program_id := p_program;
    v_receipt.label := '';
    v_receipt.tool_run_id := v_tool_run_id;
    -- The caller states a purpose, never a lane: who acted is derived from what
    -- the request was for. A capability is the agent's, so it settles both.
    v_purpose := CASE WHEN p_capability IS NULL
                           AND p_receipt ->> 'purpose' = 'control_plane'
                      THEN 'control_plane' ELSE 'target_traffic' END;
    v_receipt.purpose := v_purpose;
    v_receipt.lane := CASE WHEN v_purpose = 'control_plane'
                           THEN 'proxy_internal' ELSE 'agent' END;
    v_receipt.decision := 'blocked';
    v_receipt.scope_version := CASE WHEN v_purpose = 'control_plane' THEN NULL
        ELSE (SELECT scope_version FROM programs WHERE id=p_program) END;
    v_receipt.scope_class := CASE WHEN v_purpose = 'control_plane'
        THEN 'control_plane' ELSE coalesce(v_receipt.scope_class, 'denied') END;
    v_receipt.ts_arrival := coalesce(v_receipt.ts_arrival, clock_timestamp());
    v_receipt.intercepted := coalesce(v_receipt.intercepted, true);

    PERFORM set_actor('runtime');
    INSERT INTO receipts (
        id, program_id, label, tool_run_id, lane, purpose, decision, reason,
        identity_entity_id, method, scheme, host, port, path, query_sha256,
        pinned_ips, status_code, ts_arrival, ts_egress, waited_ms, notes,
        retry_after, scope_version, scope_class, intercepted
    ) VALUES (
        v_receipt.id, v_receipt.program_id, v_receipt.label,
        v_receipt.tool_run_id, v_receipt.lane, v_receipt.purpose,
        v_receipt.decision,
        coalesce(v_receipt.reason, 'capability refused'),
        v_receipt.identity_entity_id, v_receipt.method, v_receipt.scheme,
        v_receipt.host, v_receipt.port, v_receipt.path,
        v_receipt.query_sha256, v_receipt.pinned_ips, v_receipt.status_code,
        v_receipt.ts_arrival, v_receipt.ts_egress, v_receipt.waited_ms,
        v_receipt.notes, v_receipt.retry_after, v_receipt.scope_version,
        v_receipt.scope_class, v_receipt.intercepted
    );
    RETURN v_id;
END $fn$;


-- ===========================================================================
-- 4. Taking a slot
-- ===========================================================================

-- How long a reservation may be held before another request may have the slot
-- back. Longer than the door's own target timeout, so an exchange that is
-- merely slow is never counted twice; short enough that a killed proxy costs
-- one minute of one slot rather than the rest of the engagement.
CREATE FUNCTION egress_reservation_life() RETURNS interval
LANGUAGE sql IMMUTABLE AS $fn$ SELECT interval '90 seconds' $fn$;

CREATE FUNCTION reserve_egress_slot(
    p_capability text,
    p_protocol   text,
    p_host       text,
    p_port       integer,
    p_path_raw   text,
    p_path_norm  text
) RETURNS TABLE (
    reservation uuid,
    granted     boolean,
    reason      text,
    retry_at    timestamptz,
    -- Not `target`: an output parameter is a PL/pgSQL variable, and two of the
    -- tables below have a column of that name. Every statement mentioning one
    -- would be ambiguous, and PostgreSQL says so rather than guessing.
    scope_target text
)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE
    v_auth    record;
    v_version integer;
    v_limits  record;
    v_class   text;
    v_ord     integer;
    v_target  text;
    v_spend   program_egress_spend%ROWTYPE;
    v_bucket  program_egress_budget%ROWTYPE;
    v_tokens  numeric;
    v_live    integer;
    v_soonest timestamptz;
BEGIN
    -- Resolved here rather than trusted from the first decision. The capability
    -- is re-resolved on every call for the same reason `authorize` re-decides
    -- the URL: a Program halted, a lease lapsed or a Tool run closed between
    -- the two calls, and a budget taken against a dead capability would spend a
    -- Program's total on a request nothing authorised.
    SELECT * INTO v_auth FROM resolve_egress_capability(p_capability);
    IF NOT FOUND THEN
        RAISE EXCEPTION 'egress capability refused' USING ERRCODE = '23514';
    END IF;

    SELECT p.scope_version INTO v_version FROM programs p WHERE p.id = v_auth.program_id;
    SELECT sv.budget_burst, sv.budget_concurrency, sv.budget_requests,
           sv.budget_window_seconds
      INTO v_limits
      FROM program_scope_versions sv
     WHERE sv.program_id = v_auth.program_id AND sv.version = v_version;

    -- Which target this is, in the policy's words. `rule_ord` names the rule
    -- that decided the request, and its pattern is the thing being rate
    -- limited: one bucket for `*.example.com` and everything under it.
    SELECT s.scope_class, s.rule_ord INTO v_class, v_ord
      FROM scope_class_of(v_auth.program_id, v_version,
                          p_host, p_port, p_path_raw, p_path_norm,
                          p_protocol, 'request') s;
    IF coalesce(v_class, 'denied') NOT IN ('target', 'egress_support') THEN
        RAISE EXCEPTION 'egress request is outside current scope' USING ERRCODE = '23514';
    END IF;
    SELECT r.pattern_text INTO v_target
      FROM program_scope_rules r
     WHERE r.program_id = v_auth.program_id AND r.version = v_version AND r.ord = v_ord;
    -- The scope decision above cited a rule, so this is defence rather than a
    -- branch anything reaches: falling back to the host keeps the bucket
    -- narrower than the policy rather than wider.
    v_target := coalesce(v_target, p_host);
    scope_target := v_target;

    IF v_limits.budget_burst IS NULL OR v_limits.budget_concurrency IS NULL
       OR v_limits.budget_requests IS NULL OR v_limits.budget_window_seconds IS NULL THEN
        -- A policy that never said what it was authorising authorises nothing.
        reservation := NULL; granted := false; retry_at := NULL;
        reason := 'budget not compiled';
        RETURN NEXT; RETURN;
    END IF;

    PERFORM set_actor('runtime');

    -- The Program row first, always, so two targets under one Program take
    -- their locks in one order and cannot wait on each other.
    INSERT INTO program_egress_spend (program_id) VALUES (v_auth.program_id)
        ON CONFLICT (program_id) DO NOTHING;
    SELECT * INTO v_spend FROM program_egress_spend
     WHERE program_id = v_auth.program_id FOR UPDATE;

    INSERT INTO program_egress_budget (program_id, target, tokens)
    VALUES (v_auth.program_id, v_target, v_limits.budget_burst)
        ON CONFLICT (program_id, target) DO NOTHING;
    SELECT * INTO v_bucket FROM program_egress_budget
     WHERE program_id = v_auth.program_id AND target = v_target FOR UPDATE;

    -- Slots whose holder never came back. Released rather than refunded: a
    -- proxy that died mid-exchange may well have reached the target, and
    -- handing the request back would let a crash loop spend the total twice.
    UPDATE egress_reservations
       SET released_at = clock_timestamp(), contacted = true
     WHERE program_id = v_auth.program_id AND target = v_target
       AND released_at IS NULL AND expires_at <= clock_timestamp();

    -- Refill by elapsed time, clamped to the bucket's capacity. `least` is what
    -- makes a shrunk `burst` take effect on the next request rather than after
    -- the old capacity has drained.
    v_tokens := least(
        v_limits.budget_burst::numeric,
        v_bucket.tokens
            + extract(epoch FROM clock_timestamp() - v_bucket.refilled_at)::numeric
              * v_limits.budget_burst::numeric / v_limits.budget_window_seconds::numeric
    );

    -- The total first: it is the limit that no amount of waiting clears, and a
    -- caller told to retry a request the engagement can never afford would spin
    -- until the capability expired.
    IF v_spend.contacted >= v_limits.budget_requests THEN
        UPDATE program_egress_spend SET exhausted = exhausted + 1
         WHERE program_id = v_auth.program_id;
        UPDATE program_egress_budget
           SET tokens = v_tokens, refilled_at = clock_timestamp()
         WHERE program_id = v_auth.program_id AND target = v_target;
        INSERT INTO events (program_id, type, actor_kind, agent_run_id, task_id, payload)
        VALUES (v_auth.program_id, 'egress.budget_exhausted', 'runtime',
                v_auth.agent_run_id, v_auth.task_id,
                jsonb_build_object('schema_version', 1, 'target', v_target,
                                   'requests', v_limits.budget_requests,
                                   'contacted', v_spend.contacted));
        reservation := NULL; granted := false; retry_at := NULL;
        reason := 'budget exhausted';
        RETURN NEXT; RETURN;
    END IF;

    SELECT count(*), min(expires_at) INTO v_live, v_soonest
      FROM egress_reservations
     WHERE program_id = v_auth.program_id AND target = v_target
       AND released_at IS NULL;

    IF v_live >= v_limits.budget_concurrency THEN
        UPDATE program_egress_budget
           SET tokens = v_tokens, refilled_at = clock_timestamp(),
               throttled = throttled + 1
         WHERE program_id = v_auth.program_id AND target = v_target;
        -- The soonest a slot is certainly free. In practice one frees earlier,
        -- when an exchange finishes; an upper bound is the only honest answer a
        -- row can give about a request still in flight.
        retry_at := v_soonest;
        reservation := NULL; granted := false;
        reason := 'too many concurrent requests';
        INSERT INTO events (program_id, type, actor_kind, agent_run_id, task_id, payload)
        VALUES (v_auth.program_id, 'egress.throttled', 'runtime',
                v_auth.agent_run_id, v_auth.task_id,
                jsonb_build_object('schema_version', 1, 'target', v_target,
                                   'limit', 'concurrency',
                                   'concurrency', v_limits.budget_concurrency,
                                   'retry_at', retry_at));
        RETURN NEXT; RETURN;
    END IF;

    IF v_tokens < 1 THEN
        UPDATE program_egress_budget
           SET tokens = v_tokens, refilled_at = clock_timestamp(),
               throttled = throttled + 1
         WHERE program_id = v_auth.program_id AND target = v_target;
        retry_at := clock_timestamp()
                  + make_interval(secs => ((1 - v_tokens)
                        * v_limits.budget_window_seconds::numeric
                        / v_limits.budget_burst::numeric)::double precision);
        reservation := NULL; granted := false;
        reason := 'rate limited';
        INSERT INTO events (program_id, type, actor_kind, agent_run_id, task_id, payload)
        VALUES (v_auth.program_id, 'egress.throttled', 'runtime',
                v_auth.agent_run_id, v_auth.task_id,
                jsonb_build_object('schema_version', 1, 'target', v_target,
                                   'limit', 'rate',
                                   'burst', v_limits.budget_burst,
                                   'window_seconds', v_limits.budget_window_seconds,
                                   'retry_at', retry_at));
        RETURN NEXT; RETURN;
    END IF;

    UPDATE program_egress_budget
       SET tokens = v_tokens - 1, refilled_at = clock_timestamp(),
           contacted = contacted + 1
     WHERE program_id = v_auth.program_id AND target = v_target;
    UPDATE program_egress_spend
       SET contacted = contacted + 1, last_at = clock_timestamp()
     WHERE program_id = v_auth.program_id;

    INSERT INTO egress_reservations (program_id, tool_run_id, target, expires_at)
    VALUES (v_auth.program_id, v_auth.tool_run_id, v_target,
            clock_timestamp() + egress_reservation_life())
    RETURNING id INTO reservation;

    granted := true; reason := 'reserved'; retry_at := NULL;
    RETURN NEXT;
END $fn$;

COMMENT ON FUNCTION reserve_egress_slot(text,text,text,integer,text,text) IS
  'Takes one request''s worth of the Program''s shared budget under a row lock, or refuses with the reason and the moment the refusal stops being true. Called after the request is authorized and before the name is resolved, so a throttled request emits no DNS query.';


-- ===========================================================================
-- 5. Giving it back
-- ===========================================================================

CREATE FUNCTION release_egress_slot(p_reservation uuid, p_contacted boolean)
RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE
    v_row  egress_reservations%ROWTYPE;
    v_held egress_reservations%ROWTYPE;
BEGIN
    IF p_reservation IS NULL OR p_contacted IS NULL THEN
        RETURN false;
    END IF;
    PERFORM set_actor('runtime');

    -- Which slot this is, read without locking anything, because the refund
    -- below has to take the counters in the reserver's order -- Program row,
    -- then bucket -- and it cannot know which bucket without reading the row
    -- first. An unlocked read is enough: the UPDATE further down carries the
    -- whole idempotency guard, so a release that lost a race changes no row and
    -- refunds nothing, having only taken locks it then drops.
    --
    -- Taking them the other way round is the bug this shape exists to avoid. A
    -- refund holding the bucket and waiting for the Program row, against a
    -- reservation holding the Program row and waiting for the bucket, is a
    -- cycle, and PostgreSQL breaks a cycle by killing one of the two.
    SELECT * INTO v_held FROM egress_reservations
     WHERE id = p_reservation AND program_id = rk2_program() AND released_at IS NULL;
    IF NOT FOUND THEN
        RETURN false;
    END IF;

    IF NOT p_contacted THEN
        PERFORM 1 FROM program_egress_spend
         WHERE program_id = v_held.program_id FOR UPDATE;
        PERFORM 1 FROM program_egress_budget
         WHERE program_id = v_held.program_id AND target = v_held.target FOR UPDATE;
    END IF;

    UPDATE egress_reservations
       SET released_at = clock_timestamp(), contacted = p_contacted
     WHERE id = p_reservation AND program_id = rk2_program() AND released_at IS NULL
    RETURNING * INTO v_row;
    IF NOT FOUND THEN
        RETURN false;
    END IF;

    -- A request the door refused after reserving never reached the target, so
    -- the token and the count go back. This is what makes the totals a count of
    -- target contacts rather than of attempts -- which is the number the
    -- criterion is about, and the number an operator means by "requests".
    IF NOT p_contacted THEN
        UPDATE program_egress_spend
           SET contacted = greatest(contacted - 1, 0)
         WHERE program_id = v_row.program_id;
        UPDATE program_egress_budget
           SET tokens = tokens + 1, contacted = greatest(contacted - 1, 0)
         WHERE program_id = v_row.program_id AND target = v_row.target;
    END IF;
    RETURN true;
END $fn$;

COMMENT ON FUNCTION release_egress_slot(uuid,boolean) IS
  'Frees one in-flight slot, and refunds the request when the door refused before opening a socket. Idempotent: a slot released twice, or already expired, changes nothing.';

REVOKE ALL ON FUNCTION reserve_egress_slot(text,text,text,integer,text,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION release_egress_slot(uuid,boolean) FROM PUBLIC;
REVOKE ALL ON FUNCTION egress_reservation_life() FROM PUBLIC;
-- Named roles as well as PUBLIC: the owner's default privileges grant EXECUTE
-- on new functions to the runtime, so a definer function that only revoked
-- PUBLIC would still be callable by the process the model runs inside.
REVOKE ALL ON FUNCTION reserve_egress_slot(text,text,text,integer,text,text),
                       release_egress_slot(uuid,boolean)
    FROM rk2_runtime, rk2_state, rk2_human;
-- The proxy alone. The runtime does not send target traffic and the state role
-- reads; a budget verb reachable from either is a budget the model's own
-- process could spend on its own terms.
GRANT EXECUTE ON FUNCTION reserve_egress_slot(text,text,text,integer,text,text) TO rk2_proxy;
GRANT EXECUTE ON FUNCTION release_egress_slot(uuid,boolean) TO rk2_proxy;

REVOKE ALL ON TABLE program_egress_spend, program_egress_budget, egress_reservations
    FROM PUBLIC;
REVOKE ALL ON TABLE program_egress_spend, program_egress_budget, egress_reservations
    FROM rk2_proxy, rk2_state, rk2_human;

-- And `rk2_runtime` by name, which is the one that matters and the one a
-- `FROM PUBLIC` revoke does not touch: 0029 standing-grants INSERT, UPDATE and
-- DELETE on every table the owner creates to the runtime, so without this the
-- process the model runs inside could refill its own bucket, zero its own
-- total, or delete the rows holding its concurrency down -- and never call a
-- verb to do any of it.
--
-- Two verbs rather than all of them, because `readwrite_on_every_managed_table`
-- asserts the runtime keeps SELECT and INSERT everywhere, and narrowing that
-- surface generally is ticket 66's, not this one's. Neither retained verb is a
-- way in. An INSERT cannot lower a count that already exists, and a bucket
-- inserted pre-filled is clamped on the next read: the refill is
-- `least(burst, ...)`, so a token that policy never granted does not survive
-- being looked at. What is left is the ability to spend against yourself, which
-- is the direction a fence may safely fail in.
REVOKE UPDATE, DELETE
    ON TABLE program_egress_spend, program_egress_budget, egress_reservations
    FROM rk2_runtime;

-- The same hole, on the table the Halt itself lives in. `20260811T130000Z`
-- revoked `program_halts` from PUBLIC only, and the actor-kind guard it relies
-- on is a BEFORE INSERT OR UPDATE trigger -- so DELETE was checked by nothing
-- and reachable by the runtime, and deleting the row is exactly as good as
-- clearing the Halt: `resolve_egress_capability` asks whether a halted row
-- exists. INSERT stays for the same reason as above and is closed by other
-- means -- the actor-kind guard does see an insert, and one Program has one
-- Halt row.
REVOKE UPDATE, DELETE ON TABLE program_halts FROM rk2_runtime, rk2_proxy, rk2_state;


-- ===========================================================================
-- 6. The standing check
-- ===========================================================================

CREATE FUNCTION check_egress_budget()
RETURNS TABLE(problem text, detail text)
LANGUAGE sql STABLE AS $fn$
    -- (a) The verbs are the proxy's and nobody else's.
    SELECT 'proxy_cannot_reserve', 'rk2_proxy cannot execute the egress budget verbs'
     WHERE NOT has_function_privilege(
               'rk2_proxy',
               'reserve_egress_slot(text,text,text,integer,text,text)', 'EXECUTE')
        OR NOT has_function_privilege('rk2_proxy', 'release_egress_slot(uuid,boolean)', 'EXECUTE')
    UNION ALL
    SELECT 'runtime_can_reserve', 'rk2_runtime can execute reserve_egress_slot'
     WHERE has_function_privilege(
               'rk2_runtime',
               'reserve_egress_slot(text,text,text,integer,text,text)', 'EXECUTE')
    UNION ALL
    -- (b) ...and the counters are nobody's to change directly. A role that could
    --     UPDATE the bucket could refill it, which is the same as having no
    --     bucket at all, and one that could DELETE a reservation could free its
    --     own concurrency. Every role below the owner is named, the runtime most
    --     of all: it is the process the model runs inside, and it is the one the
    --     owner's default privileges hand new tables to.
    --
    --     INSERT is asked of the roles that should not reach these tables at all
    --     and not of the runtime, which keeps it deliberately -- see the revoke.
    SELECT 'budget_tables_writable',
           p.grantee || ' holds ' || p.privilege_type || ' on ' || p.table_name
      FROM (
        SELECT g.grantee, t.table_name, g.privilege_type
          FROM (VALUES ('program_egress_spend'), ('program_egress_budget'),
                       ('egress_reservations')) AS t(table_name),
               (VALUES ('rk2_runtime', 'UPDATE'), ('rk2_runtime', 'DELETE'),
                       ('rk2_proxy', 'INSERT'), ('rk2_proxy', 'UPDATE'),
                       ('rk2_proxy', 'DELETE'),
                       ('rk2_state', 'INSERT'), ('rk2_state', 'UPDATE'),
                       ('rk2_state', 'DELETE'),
                       ('rk2_human', 'INSERT'), ('rk2_human', 'UPDATE'),
                       ('rk2_human', 'DELETE')) AS g(grantee, privilege_type)
         WHERE has_table_privilege(g.grantee, t.table_name, g.privilege_type)
      ) p
    UNION ALL
    -- (c) The rows, not the shapes: a Program whose door let through more
    --     exchanges than any policy it has ever carried allows. Counted over
    --     allowed Receipts because those are the exchanges an auditor can see,
    --     and every one of them spent a reservation.
    --
    --     Against the widest version rather than the live one, because a check
    --     that read only the live one would fire for good on the day an operator
    --     narrowed a budget: the exchanges already made were authorised by the
    --     policy that was live when they were made, and a standing check nobody
    --     can clear stops being a signal.
    SELECT 'budget_overspent',
           p.slug || ': ' || count(r.id) || ' allowed of ' || w.widest
      FROM programs p
      JOIN (
        SELECT sv.program_id, max(sv.budget_requests) AS widest
          FROM program_scope_versions sv
         WHERE sv.budget_requests IS NOT NULL
         GROUP BY sv.program_id
      ) w ON w.program_id = p.id
      JOIN receipts r
        ON r.program_id = p.id AND r.decision = 'allowed' AND r.lane = 'agent'
     GROUP BY p.slug, w.widest
    HAVING count(r.id) > w.widest
    UNION ALL
    -- (d) A reservation that says it is both held and finished. The pair is
    --     what the concurrency count reads, so a row that disagrees with itself
    --     is a slot that is either leaked or double-counted.
    SELECT 'reservation_state_incoherent', res.id::text
      FROM egress_reservations res
     WHERE (res.released_at IS NULL) <> (res.contacted IS NULL);
$fn$;

REVOKE ALL ON FUNCTION check_egress_budget() FROM PUBLIC;
INSERT INTO standing_checks(name, query, owner_ticket, note) VALUES
    ('egress_budget', 'SELECT * FROM check_egress_budget()', '13',
     'the budget verbs are the proxy''s alone, the counters are nobody''s to write, and no Program has more allowed exchanges than any policy it carried permits');

COMMENT ON FUNCTION check_egress_budget() IS
  'The aggregate request budget, asserted from both ends: who may spend it, and whether more was spent than exists.';


-- ===========================================================================
-- 7. The Halt, closed at the table as well as at the verb
-- ===========================================================================
--
-- Criterion 2 is about who can lift a Halt, and `20260811T130000Z` answered it
-- for the verbs only: `clear_program_halt` is the operator's, and the check
-- below already says so. But a Halt is lifted by any of three things -- clearing
-- it, updating its status, or deleting the row -- and the previous check probed
-- the verb, so the two writes went unseen. They are revoked above; this is the
-- assertion that keeps them revoked.

CREATE OR REPLACE FUNCTION check_program_halt()
RETURNS TABLE(problem text, detail text)
LANGUAGE sql STABLE AS $fn$
    SELECT 'human_cannot_connect', 'rk2_human cannot connect to this database'
     WHERE NOT has_database_privilege('rk2_human', current_database(), 'CONNECT')
    UNION ALL
    SELECT 'human_cannot_use_schema', 'rk2_human cannot use the public schema'
     WHERE NOT has_schema_privilege('rk2_human', 'public', 'USAGE')
    UNION ALL
    SELECT 'human_cannot_change_halt', 'rk2_human cannot execute both Halt verbs'
     WHERE NOT has_function_privilege('rk2_human', 'halt_program(uuid,text)', 'EXECUTE')
        OR NOT has_function_privilege(
               'rk2_human', 'clear_program_halt(uuid,text)', 'EXECUTE')
    UNION ALL
    SELECT 'runtime_can_halt', 'rk2_runtime can execute halt_program'
     WHERE has_function_privilege('rk2_runtime', 'halt_program(uuid,text)', 'EXECUTE')
    UNION ALL
    SELECT 'runtime_can_clear_halt', 'rk2_runtime can execute clear_program_halt'
     WHERE has_function_privilege('rk2_runtime', 'clear_program_halt(uuid,text)', 'EXECUTE')
    UNION ALL
    SELECT 'proxy_can_change_halt', 'rk2_proxy can change Program Halt state'
     WHERE has_function_privilege('rk2_proxy', 'halt_program(uuid,text)', 'EXECUTE')
        OR has_function_privilege('rk2_proxy', 'clear_program_halt(uuid,text)', 'EXECUTE')
    UNION ALL
    -- The row itself. DELETE above all: the actor-kind guard is a BEFORE INSERT
    -- OR UPDATE trigger, so it never sees a delete, and a deleted Halt is an
    -- absent Halt -- which is what `resolve_egress_capability` reads.
    --
    -- INSERT is not asked, and is not revoked either: the guard does fire on it,
    -- one Program has one Halt row, and an insert cannot lift a Halt that is
    -- already there.
    SELECT 'halt_row_writable',
           h.grantee || ' holds ' || h.privilege_type || ' on program_halts'
      FROM (
        SELECT g.grantee, v.privilege_type
          FROM (VALUES ('UPDATE'), ('DELETE')) AS v(privilege_type),
               (VALUES ('rk2_runtime'), ('rk2_proxy'), ('rk2_state')) AS g(grantee)
         WHERE has_table_privilege(g.grantee, 'program_halts', v.privilege_type)
      ) h
    UNION ALL
    SELECT 'allowed_receipt_during_halt', r.label
      FROM receipts r JOIN program_halts h ON h.program_id = r.program_id
     WHERE h.status = 'halted' AND r.decision = 'allowed' AND r.ts_arrival >= h.changed_at;
$fn$;

UPDATE standing_checks
   SET note = 'only an operator changes Halt state, by verb or by row, and a current Halt admits no later allowed Receipt'
 WHERE name = 'program_halt';
