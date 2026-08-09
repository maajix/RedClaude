-- ---------------------------------------------------------------------------
-- 032_ticket30_lane_quota.sql   (ticket 30)
-- ---------------------------------------------------------------------------
-- Ticket 08 fixed the mechanism -- per-kind slot entitlements in
-- `scheduler_lanes`, greedy within a lane, no aging term -- and left open who
-- moves the numbers during a run. This migration is that policy, and it is
-- built so the answer to "who" is enforced rather than documented.
--
-- What it assumes underneath it, in order:
--   001..018  ticket 06/07/32/35/27      prototype/vocabularies      0879189
--   019       ticket 34 role -> kind     prototype/role-kind         a4bcfa9
--   020       ticket 12 state access     prototype/state-access      2f236f3
--   021       ticket 26 scope policy     prototype/scope-policy      2aa206c
--   022       ticket 13 hooks/receipts   prototype/hooks-events      8331814
--   023       ticket 08 the scheduler    prototype/scheduler         8301550
--   026       ticket 28 human control    prototype/control-surface   fb4edfb
--   028       ticket 16 eval store       prototype/eval-metrics      0557f77
--
-- The four things this migration is for:
--
--   1. A quota move is a ROW, versioned and append-only, the way
--      `scheduler_weights` is. `lane_quota_epochs` is that ledger and
--      `lane_quota_profiles` is the frozen set of numbers an epoch points at.
--      Decision 12 of ticket 08 guarantees a pass is deterministic given rows
--      plus `weights_version`; that guarantee was ALREADY short by one input,
--      because `rank_candidates()` reads `min_slots` live out of
--      `scheduler_lanes` and `scheduler.ranked` never recorded it. After this
--      migration the slate and the claim sequence are a function of rows,
--      `weights_version` and `quota_epoch`, and the epoch is itself a row.
--
--   2. The unversioned write path is REFUSED, not deprecated.
--      `scheduler_lanes` becomes immutable. Every entitlement move goes
--      through `advance_lane_quota()` (runtime, from a rule) or
--      `force_lane_quota()` (operator, authorised by membership of `rk2_human`
--      exactly as ticket 28 built it). There is no third writer, and in
--      particular there is no orchestrator-facing one: ticket 12 withheld
--      `scheduler_lanes` and `scheduler_weights` from `rk2_state` on the
--      grounds that an agent which can read the weights can aim at them, and
--      check (g) below fails if anything here becomes agent-reachable.
--
--   3. The wall-clock signal is not rejected by preference, it is
--      INEXPRESSIBLE. A signal is a registered SQL function over rows, and the
--      registry's trigger refuses one whose body reads the clock -- the same
--      textual rule as check (g) of `check_scheduler_closure()`. A quota that
--      moves on elapsed time makes two replays of the same rows disagree.
--
--   4. Reversal is not a special case. Going broad again in hour five is the
--      next epoch with a lower rung, and the widen rule is ordinal 1 so it
--      outranks every deepen rule -- otherwise a saturated hunt lane pins the
--      program in depth exactly when a new subdomain has appeared.
--
-- Every NUMBER here is a default and is unvalidated: the rungs, the thresholds
-- and the dwell are on the operator's queue, like every number in
-- `scheduler_weights`. What is asserted is the shape.
-- ---------------------------------------------------------------------------

-- ---------------------------------------------------------------------------
-- Folded into the ticket-33 baseline from `prototype/lane-quota` 39a0214
-- (`032_ticket30_lane_quota.sql`). Five changes, all of them because the
-- baseline now does centrally what 032 did for itself:
--
--   * `lane_quota_epoch_append_only()` gained the `app.purging` exemption.
--     Ticket 33 rule F (`check_purge_reachability()`) refuses a BEFORE DELETE
--     row trigger on a program-scoped table whose body never reads
--     `app.purging`: a program carrying an epoch could not be purged. 013's
--     `reject_mutation_unless_purging()` is the idiom; the ledger keeps its own
--     function only for its message and hint.
--   * 032's RLS loop over program-scoped tables is removed. `apply_state_rls()`
--     is a finalizer as of ticket 33 and runs that exact rule after every
--     migration, so re-running it per migration is the defect 33 fixed.
--   * 032's closing `ENABLE ALWAYS TRIGGER` sweep is removed:
--     `enforce_always_triggers()` is a finalizer and does it corpus-wide.
--   * 032's inline `check_state_access()` self-assert is removed. It ran before
--     the finalizers, so with the RLS loop gone it asserted a state that does
--     not exist yet. The registered standing check `state_access` (owner 12)
--     asserts the same thing after the finalizers, on every `up`.
--   * Section 11 is new: 032 registered `program_global_tables` but not the
--     three registries the baseline enforces -- event classification,
--     `purge_cascade_edges`, and `standing_checks`.
--
-- The grants are kept verbatim. 032's `REVOKE ALL ... FROM PUBLIC` is
-- load-bearing for checks (g) and the function rule; its narrow
-- `GRANT SELECT ... TO rk2_runtime` is a no-op against the baseline's
-- `ALTER DEFAULT PRIVILEGES FOR ROLE rk2_owner ... TO rk2_runtime`, which is
-- itself asserted by `check_runtime_connection()`. Ticket 30 wanting the
-- runtime read-only on the quota catalogue and the baseline granting it
-- read-write on every managed table is a real tension between two resolved
-- tickets; nothing here resolves it, and the smaller change stays as written.
-- ---------------------------------------------------------------------------
SET client_min_messages = warning;


-- ===========================================================================
-- 1. The ladder: named, frozen sets of entitlements
-- ===========================================================================

-- One switch or continuous drift, settled: discrete named rungs. `min_slots`
-- is bounded above by the roster's `max_concurrent`, which is 1 or 2 for every
-- lane in the shipped roster, so a "continuously drifting" quota has at most
-- three distinct values per lane. A continuous controller over a three-valued
-- output is a discrete controller carrying extra state, and the extra state is
-- not auditable: `breadth -> balanced` names itself in an event payload and a
-- drifting numerator does not.
CREATE TABLE lane_quota_profiles (
    profile     text PRIMARY KEY,
    rung        smallint NOT NULL UNIQUE,   -- 0 = broadest
    description text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE lane_quota_profile_slots (
    profile   text     NOT NULL REFERENCES lane_quota_profiles(profile) ON DELETE CASCADE,
    kind      text     NOT NULL REFERENCES task_kinds(kind),
    min_slots smallint NOT NULL CHECK (min_slots >= 0 AND min_slots <= 8),
    PRIMARY KEY (profile, kind)
);

COMMENT ON TABLE lane_quota_profile_slots IS
  'Only min_slots. max_slots left scheduler_lanes in migration 023 -- capacity is the roster''s roles.max_concurrent and no program may raise it, so the phase switch is a min_slots move and nothing else.';

-- A profile an epoch has pointed at is history, and history does not get
-- edited. This is what makes "recorded the way weights are" true rather than
-- aspirational: `scheduler_weights` gets a new version row, and a used quota
-- profile gets a new profile name.
CREATE FUNCTION lane_quota_profile_frozen() RETURNS trigger
LANGUAGE plpgsql AS $fn$
DECLARE prof text := coalesce(OLD.profile, NEW.profile);
BEGIN
    IF EXISTS (SELECT 1 FROM lane_quota_epochs e WHERE e.profile = prof) THEN
        RAISE EXCEPTION
            'lane quota profile % has been used by an epoch and is frozen', prof
            USING ERRCODE = '42501',
                  HINT = 'add a new profile and a new policy version; a replayed run must see the numbers it ran with';
    END IF;
    RETURN coalesce(NEW, OLD);
END $fn$;


-- ===========================================================================
-- 2. The signal registry, and the clock that cannot be registered
-- ===========================================================================

CREATE TABLE lane_quota_signals (
    signal      text PRIMARY KEY,
    fn          text NOT NULL,
    direction   text NOT NULL CHECK (direction IN ('falling','rising')),
    description text NOT NULL
);

-- Candidate 1: recon novelty across the program. MAX, not mean: the mean is
-- dragged down by a long tail of stale pending recon tasks, and one highly
-- novel recon subject IS a reason to stay broad. `novelty_for` is ticket 08's
-- own per-kind function, so this signal cannot disagree with the ranking.
CREATE FUNCTION lane_signal_recon_novelty(p uuid) RETURNS numeric
LANGUAGE sql STABLE AS $fn$
    SELECT coalesce(max(novelty_for(t)), 0)
      FROM tasks t
     WHERE t.program_id = p AND t.kind = 'recon' AND t.status = 'pending';
$fn$;

-- Candidate 2: testable hypotheses with nowhere to run. The ticket's wording,
-- literally: the count is reported only while the hunt lane has no headroom,
-- because a queue with a free slot is not backpressure, it is a queue.
CREATE FUNCTION lane_signal_hunt_backpressure(p uuid) RETURNS numeric
LANGUAGE sql STABLE AS $fn$
    SELECT CASE
        WHEN (SELECT s.headroom FROM scheduler_lane_state s
               WHERE s.program_id = p AND s.kind = 'hunt') > 0 THEN 0
        ELSE (SELECT count(*) FROM tasks t
                JOIN hypotheses h ON h.id = t.hypothesis_id
               WHERE t.program_id = p AND t.kind = 'hunt'
                 AND t.status = 'pending' AND h.status = 'testable'
                 AND ready_for(t) IS NULL)
      END::numeric;
$fn$;

-- Candidate 3: budget consumed against budget remaining. Registered so the
-- A/B can measure it; deliberately NOT in the shipped policy, see section 3.
CREATE FUNCTION lane_signal_budget_fraction(p uuid) RETURNS numeric
LANGUAGE sql STABLE AS $fn$
    SELECT CASE WHEN b.token_budget IS NULL OR b.token_budget = 0 THEN 0
                ELSE round(b.tokens_spent::numeric / b.token_budget, 6) END
      FROM program_budget b WHERE b.program_id = p;
$fn$;

-- Candidate 4, elapsed wall clock, is refused HERE rather than argued about.
-- A quota that moves on the clock makes the claim sequence a function of when
-- the replay happens, which is exactly what decision 12 exists to forbid;
-- ticket 08 kept `now()` out of the priority formula for the same reason and
-- checked it against the function text. Same rule, same shape.
CREATE FUNCTION lane_quota_signal_is_clockfree() RETURNS trigger
LANGUAGE plpgsql AS $fn$
DECLARE src text;
BEGIN
    SELECT regexp_replace(pr.prosrc, '--[^' || chr(10) || ']*', '', 'g')
      INTO src FROM pg_proc pr
     WHERE pr.pronamespace = 'public'::regnamespace AND pr.proname = NEW.fn;
    IF src IS NULL THEN
        RAISE EXCEPTION 'signal % names function %(), which does not exist',
            NEW.signal, NEW.fn USING ERRCODE = 'check_violation';
    END IF;
    IF src ~* '(now\(\)|current_timestamp|clock_timestamp|localtimestamp|current_date)' THEN
        RAISE EXCEPTION
            'signal % reads the clock in %(); a quota that moves on elapsed time is not replayable',
            NEW.signal, NEW.fn
            USING ERRCODE = 'check_violation',
                  HINT = 'ticket 08 decision 12: a pass is a function of rows, and a lane quota is an input to the pass';
    END IF;
    RETURN NEW;
END $fn$;

CREATE TRIGGER lane_quota_signals_clockfree
    BEFORE INSERT OR UPDATE ON lane_quota_signals
    FOR EACH ROW EXECUTE FUNCTION lane_quota_signal_is_clockfree();
ALTER TABLE lane_quota_signals ENABLE ALWAYS TRIGGER lane_quota_signals_clockfree;

INSERT INTO lane_quota_signals (signal, fn, direction, description) VALUES
 ('recon_novelty',     'lane_signal_recon_novelty',     'falling',
  'max novelty_for() over pending recon tasks: surface enumeration drying up'),
 ('hunt_backpressure', 'lane_signal_hunt_backpressure', 'rising',
  'testable hypotheses with a ready hunt task while the hunt lane has no headroom'),
 ('budget_fraction',   'lane_signal_budget_fraction',   'rising',
  'program tokens spent / token_budget');
-- `recon_novelty_rise` is registered in section 4: it reads the epoch ledger,
-- and a LANGUAGE sql body is parsed at CREATE time, so it cannot be written
-- before the view it reads exists.

CREATE FUNCTION lane_quota_signals_of(p uuid) RETURNS jsonb
LANGUAGE plpgsql STABLE AS $fn$
DECLARE s record; out jsonb := '{}'::jsonb; v numeric;
BEGIN
    FOR s IN SELECT * FROM lane_quota_signals ORDER BY signal LOOP
        EXECUTE format('SELECT %I($1)', s.fn) INTO v USING p;
        out := out || jsonb_build_object(s.signal, v);
    END LOOP;
    RETURN out;
END $fn$;


-- ===========================================================================
-- 3. The policy: operator-authored, versioned, one active
-- ===========================================================================

-- Shaped exactly like `scheduler_weights`: a numbered row, one active, every
-- number in it unvalidated. This is the sense in which the operator writes the
-- quotas -- the operator writes the RULE, offline and versioned, and the
-- runtime executes it. Neither "operator pokes numbers mid-run" (a six-hour
-- unattended run then never switches, and Q4 wants unattended runs) nor
-- "orchestrator writes them through a tool" (section 9) survives contact.
CREATE TABLE lane_quota_policies (
    version          integer PRIMARY KEY,
    seed_profile     text    NOT NULL REFERENCES lane_quota_profiles(profile),
    min_dwell_passes smallint NOT NULL DEFAULT 2 CHECK (min_dwell_passes >= 0),
    active           boolean NOT NULL DEFAULT false,
    notes            text    NOT NULL
);
CREATE UNIQUE INDEX lane_quota_policies_one_active
    ON lane_quota_policies ((true)) WHERE active;

CREATE TABLE lane_quota_rules (
    policy_version integer  NOT NULL REFERENCES lane_quota_policies(version) ON DELETE CASCADE,
    ord            smallint NOT NULL,
    rule           text     NOT NULL,
    from_profile   text     REFERENCES lane_quota_profiles(profile),  -- NULL = any rung
    to_profile     text     NOT NULL REFERENCES lane_quota_profiles(profile),
    signal         text     NOT NULL REFERENCES lane_quota_signals(signal),
    op             text     NOT NULL CHECK (op IN ('<=','>=')),
    threshold      numeric  NOT NULL,
    PRIMARY KEY (policy_version, ord),
    CHECK (from_profile IS DISTINCT FROM to_profile)
);

COMMENT ON TABLE lane_quota_rules IS
  'First match in ord order wins. The widen rule is ordinal 1 on purpose: a saturated hunt lane would otherwise pin the program in depth exactly when a new subdomain has appeared, and reversibility would be a claim rather than a behaviour.';


-- ===========================================================================
-- 4. The ledger: append-only, one row per quota move
-- ===========================================================================

CREATE TABLE lane_quota_epochs (
    program_id     uuid     NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    epoch          integer  NOT NULL CHECK (epoch >= 0),
    profile        text     NOT NULL REFERENCES lane_quota_profiles(profile),
    policy_version integer  REFERENCES lane_quota_policies(version),
    rule           text,
    reason         text     NOT NULL CHECK (reason IN ('seed','rule','operator')),
    signals        jsonb    NOT NULL,
    actor_kind     text     NOT NULL CHECK (actor_kind IN ('runtime','human')),
    actor_id       text     NOT NULL,
    opened_at_pass bigint   NOT NULL,   -- the replay clock, see below
    pin_until_pass bigint   NOT NULL DEFAULT 0,
    opened_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (program_id, epoch),
    CHECK ((reason = 'rule') = (rule IS NOT NULL)),
    CHECK ((reason = 'operator') = (actor_kind = 'human'))
);

COMMENT ON COLUMN lane_quota_epochs.opened_at_pass IS
  'The number of scheduler.ranked events the program had emitted when this epoch opened. The dwell timer must not be a wall clock, and the pass count is the only monotone discrete clock in the schema that is itself a row.';

CREATE FUNCTION lane_quota_epoch_append_only() RETURNS trigger
LANGUAGE plpgsql AS $fn$
BEGIN
    -- Ticket 33 rule F: a BEFORE DELETE row trigger on a program-scoped table
    -- must consult `app.purging` or the program it belongs to can never be
    -- purged. Same exemption, same setting name, as 013's
    -- `reject_mutation_unless_purging()`; append-only still means append-only
    -- for everything that is not the purge.
    IF TG_OP = 'DELETE'
       AND coalesce(current_setting('app.purging', true), 'off') = 'on' THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'lane_quota_epochs is append-only (% refused on program %)',
        TG_OP, coalesce(OLD.program_id::text, '?')
        USING ERRCODE = '42501',
              HINT = 'a quota change that can be edited afterwards is not a record of what the run did';
END $fn$;

CREATE TRIGGER lane_quota_epochs_append_only
    BEFORE UPDATE OR DELETE ON lane_quota_epochs
    FOR EACH ROW EXECUTE FUNCTION lane_quota_epoch_append_only();
ALTER TABLE lane_quota_epochs ENABLE ALWAYS TRIGGER lane_quota_epochs_append_only;

CREATE TRIGGER lane_quota_profile_slots_frozen
    BEFORE UPDATE OR DELETE ON lane_quota_profile_slots
    FOR EACH ROW EXECUTE FUNCTION lane_quota_profile_frozen();
ALTER TABLE lane_quota_profile_slots ENABLE ALWAYS TRIGGER lane_quota_profile_slots_frozen;

-- The pass counter is derived, never stored: `rank_pass()` belongs to ticket 08
-- and this migration does not rewrite it.
CREATE FUNCTION lane_quota_pass(p uuid) RETURNS bigint
LANGUAGE sql STABLE AS $fn$
    SELECT count(*)::bigint FROM events e
     WHERE e.program_id = p AND e.type = 'scheduler.ranked';
$fn$;

CREATE VIEW current_lane_quota AS
    SELECT DISTINCT ON (e.program_id)
           e.program_id, e.epoch, e.profile, e.policy_version, e.rule, e.reason,
           e.opened_at_pass, e.pin_until_pass, e.actor_kind, e.signals
      FROM lane_quota_epochs e
     ORDER BY e.program_id, e.epoch DESC;

-- Candidate 1b, and the one the A/B actually selected. `recon_novelty` is a
-- LEVEL, and a level cannot tell "a new subdomain appeared" from "the original
-- recon queue is not finished yet": both read 1.0. What the ticket's hour-five
-- case is actually about is a RISE, and a rise needs a reference point that is
-- not a wall clock. The epoch ledger already stores one -- every epoch records
-- the signal vector it opened with -- so the reference is a row, and the signal
-- stays replayable.
CREATE FUNCTION lane_signal_recon_novelty_rise(p uuid) RETURNS numeric
LANGUAGE sql STABLE AS $fn$
    SELECT greatest(
        lane_signal_recon_novelty(p)
        - coalesce((SELECT (e.signals ->> 'recon_novelty')::numeric
                      FROM current_lane_quota e WHERE e.program_id = p),
                   lane_signal_recon_novelty(p)),
        0);
$fn$;

INSERT INTO lane_quota_signals (signal, fn, direction, description) VALUES
 ('recon_novelty_rise','lane_signal_recon_novelty_rise','rising',
  'recon novelty now, minus recon novelty when the current epoch opened');



-- ===========================================================================
-- 5. Resolution: the epoch is the per-program entitlement
-- ===========================================================================

-- Migration 023 made a per-program `scheduler_lanes` row reachable and left the
-- numbers static. Precedence now runs epoch -> program row -> default row, and
-- `overridden` stays true for either kind of override so check (b) of
-- `check_scheduler_closure()` still means what it meant.
CREATE OR REPLACE VIEW effective_lane_capacity AS
    SELECT p.id  AS program_id,
           k.kind,
           m.role,
           coalesce(q.min_slots, l.min_slots)          AS min_slots,
           r.max_concurrent                            AS max_slots,
           r.clamp_to_identity_leases,
           l.overridden OR q.min_slots IS NOT NULL     AS overridden,
           cq.epoch                                    AS quota_epoch,
           cq.profile                                  AS quota_profile
      FROM programs p
      CROSS JOIN task_kinds k
      JOIN role_task_kinds m ON m.kind = k.kind
      JOIN roles r           ON r.role = m.role
      CROSS JOIN LATERAL (
          SELECT sl.min_slots, sl.program_id IS NOT NULL AS overridden
            FROM scheduler_lanes sl
           WHERE sl.kind = k.kind
             AND (sl.program_id = p.id OR sl.program_id IS NULL)
           ORDER BY sl.program_id NULLS LAST
           LIMIT 1
      ) l
      LEFT JOIN current_lane_quota cq ON cq.program_id = p.id
      LEFT JOIN lane_quota_profile_slots q
             ON q.profile = cq.profile AND q.kind = k.kind;

COMMENT ON VIEW effective_lane_capacity IS
  'One row per (program, kind). min_slots is the program''s current quota epoch where one exists, then its scheduler_lanes override, then the default; max_slots is always the roster''s per-role max_concurrent, which no program may raise. quota_epoch is the second version number a replay needs, beside weights_version.';

-- The unversioned write path, closed. Before this trigger a plain
-- `UPDATE scheduler_lanes SET min_slots = ...` moved every future claim and
-- left nothing in the event log to replay -- which is how a switch breaks
-- decision 12 without anybody noticing.
CREATE FUNCTION scheduler_lanes_immutable() RETURNS trigger
LANGUAGE plpgsql AS $fn$
BEGIN
    -- Ticket 33 rule F again: `scheduler_lanes` is program-scoped, so a BEFORE
    -- DELETE trigger on it that never reads `app.purging` makes every program
    -- carrying a lane override unpurgeable. Immutability is about the
    -- unversioned quota write, not about the purge.
    IF TG_OP = 'DELETE'
       AND coalesce(current_setting('app.purging', true), 'off') = 'on' THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'scheduler_lanes is immutable after migration 032 (% refused)', TG_OP
        USING ERRCODE = '42501',
              HINT = 'move the entitlement with advance_lane_quota() or force_lane_quota(); an unversioned quota write is not replayable';
END $fn$;

-- INSERT is refused as well as UPDATE. Migration 023 left a per-program
-- `scheduler_lanes` row as a legitimate override, and that row is a quota move
-- with no version, no signal vector and no event -- the same hole as the
-- UPDATE, reached by a different verb. Today it is also inert, because
-- `effective_lane_capacity` prefers the epoch and every program gets a seed
-- epoch on its first pass; leaving it open would make the closure depend on a
-- policy being active.
CREATE TRIGGER scheduler_lanes_no_unversioned_write
    BEFORE INSERT OR UPDATE OR DELETE ON scheduler_lanes
    FOR EACH ROW EXECUTE FUNCTION scheduler_lanes_immutable();
ALTER TABLE scheduler_lanes ENABLE ALWAYS TRIGGER scheduler_lanes_no_unversioned_write;


-- ===========================================================================
-- 6. The runtime writer
-- ===========================================================================

INSERT INTO event_types (id, family, description) VALUES
 ('scheduler.quota_changed', 'occurrence',
  'a lane entitlement epoch opened: which profile, which rule, and every signal value that decided it');

CREATE FUNCTION lane_quota_slots_of(p_profile text) RETURNS jsonb
LANGUAGE sql STABLE AS $fn$
    SELECT coalesce(jsonb_object_agg(kind, min_slots), '{}'::jsonb)
      FROM lane_quota_profile_slots WHERE profile = p_profile;
$fn$;

-- Called by the loop between rank_pass() and offer_slate(). That position is
-- deliberate: the quota is an input to `rank_candidates()`'s entitlement sort
-- and to nothing in the priority formula, so moving it after the ranking
-- cannot invalidate the numbers the ranking just wrote.
CREATE FUNCTION advance_lane_quota(p_actor text DEFAULT 'runtime')
RETURNS jsonb LANGUAGE plpgsql AS $fn$
DECLARE
    p    uuid := rk2_program_required();
    pol  lane_quota_policies%ROWTYPE;
    cur  current_lane_quota%ROWTYPE;
    r    lane_quota_rules%ROWTYPE;
    sig  jsonb;
    pass bigint := lane_quota_pass(p);
    v    numeric;
    hit  lane_quota_rules%ROWTYPE;
BEGIN
    SELECT * INTO pol FROM lane_quota_policies WHERE active;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('changed', false, 'reason', 'no_active_policy');
    END IF;

    sig := lane_quota_signals_of(p);
    SELECT * INTO cur FROM current_lane_quota WHERE program_id = p;

    IF NOT FOUND THEN
        INSERT INTO lane_quota_epochs (program_id, epoch, profile, policy_version,
                                       reason, signals, actor_kind, actor_id,
                                       opened_at_pass)
        VALUES (p, 0, pol.seed_profile, pol.version, 'seed', sig, 'runtime',
                p_actor, pass);
        INSERT INTO events (program_id, type, actor_kind, payload)
        VALUES (p, 'scheduler.quota_changed', 'runtime', jsonb_build_object(
            'epoch', 0, 'from', NULL, 'to', pol.seed_profile, 'rule', NULL,
            'reason', 'seed', 'policy_version', pol.version, 'pass', pass,
            'signals', sig, 'min_slots', lane_quota_slots_of(pol.seed_profile)));
        RETURN jsonb_build_object('changed', true, 'epoch', 0,
                                  'to', pol.seed_profile, 'reason', 'seed');
    END IF;

    -- Two refusals before any rule is read. `pin_until_pass` is the operator's:
    -- forcing breadth in hour five and watching the rule undo it on the next
    -- pass would make the operator override decorative.
    IF pass < cur.pin_until_pass THEN
        RETURN jsonb_build_object('changed', false, 'reason', 'operator_pin',
                                  'until_pass', cur.pin_until_pass);
    END IF;
    IF pass - cur.opened_at_pass < pol.min_dwell_passes THEN
        RETURN jsonb_build_object('changed', false, 'reason', 'dwell',
                                  'passes_held', pass - cur.opened_at_pass);
    END IF;

    FOR r IN SELECT * FROM lane_quota_rules
              WHERE policy_version = pol.version ORDER BY ord
    LOOP
        CONTINUE WHEN r.from_profile IS NOT NULL AND r.from_profile <> cur.profile;
        CONTINUE WHEN r.to_profile = cur.profile;
        v := (sig ->> r.signal)::numeric;
        IF (r.op = '<=' AND v <= r.threshold)
        OR (r.op = '>=' AND v >= r.threshold) THEN
            hit := r; EXIT;
        END IF;
    END LOOP;

    IF hit.rule IS NULL THEN
        RETURN jsonb_build_object('changed', false, 'reason', 'no_rule_matched',
                                  'signals', sig, 'profile', cur.profile);
    END IF;

    INSERT INTO lane_quota_epochs (program_id, epoch, profile, policy_version,
                                   rule, reason, signals, actor_kind, actor_id,
                                   opened_at_pass)
    VALUES (p, cur.epoch + 1, hit.to_profile, pol.version, hit.rule, 'rule',
            sig, 'runtime', p_actor, pass);

    INSERT INTO events (program_id, type, actor_kind, payload)
    VALUES (p, 'scheduler.quota_changed', 'runtime', jsonb_build_object(
        'epoch', cur.epoch + 1, 'from', cur.profile, 'to', hit.to_profile,
        'rule', hit.rule, 'reason', 'rule', 'policy_version', pol.version,
        'pass', pass, 'signals', sig,
        'min_slots', lane_quota_slots_of(hit.to_profile)));

    RETURN jsonb_build_object('changed', true, 'epoch', cur.epoch + 1,
                              'from', cur.profile, 'to', hit.to_profile,
                              'rule', hit.rule, 'signals', sig);
END $fn$;


-- ===========================================================================
-- 7. The operator writer, riding on ticket 28's authorisation
-- ===========================================================================

-- No membership test is written here on purpose. `actor_kind = 'human'` on this
-- row is authorised by migration 026's catalogue-swept
-- `assert_actor_kind_authentic()` trigger, which is re-attached at the bottom
-- of this file; the GUC records and the ROLE authorises. A second check here
-- would be a second mechanism to keep in sync with the first.
CREATE FUNCTION force_lane_quota(p_profile text, p_reason text,
                                 p_pin_passes integer DEFAULT 3)
RETURNS jsonb SECURITY DEFINER LANGUAGE plpgsql AS $fn$
DECLARE
    p    uuid := rk2_program_required();
    cur  current_lane_quota%ROWTYPE;
    pass bigint := lane_quota_pass(p);
    pv   integer;
    sig  jsonb := lane_quota_signals_of(p);
    nxt  integer;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM lane_quota_profiles WHERE profile = p_profile) THEN
        RAISE EXCEPTION 'no lane quota profile named %', p_profile
            USING ERRCODE = 'check_violation';
    END IF;
    SELECT version INTO pv FROM lane_quota_policies WHERE active;
    SELECT * INTO cur FROM current_lane_quota WHERE program_id = p;
    nxt := coalesce(cur.epoch, -1) + 1;

    INSERT INTO lane_quota_epochs (program_id, epoch, profile, policy_version,
                                   reason, signals, actor_kind, actor_id,
                                   opened_at_pass, pin_until_pass)
    VALUES (p, nxt, p_profile, pv, 'operator', sig, 'human',
            coalesce(current_setting('app.actor_id', true), session_user),
            pass, pass + greatest(p_pin_passes, 0));

    INSERT INTO events (program_id, type, actor_kind, payload)
    VALUES (p, 'scheduler.quota_changed', 'human', jsonb_build_object(
        'epoch', nxt, 'from', cur.profile, 'to', p_profile, 'rule', NULL,
        'reason', 'operator', 'operator_reason', p_reason,
        'policy_version', pv, 'pass', pass, 'signals', sig,
        'pin_until_pass', pass + greatest(p_pin_passes, 0),
        'min_slots', lane_quota_slots_of(p_profile)));

    RETURN jsonb_build_object('changed', true, 'epoch', nxt,
                              'from', cur.profile, 'to', p_profile,
                              'pin_until_pass', pass + greatest(p_pin_passes, 0));
END $fn$;


-- ===========================================================================
-- 8. Defaults. Every number below is unvalidated and on the operator's queue.
-- ===========================================================================

INSERT INTO lane_quota_profiles (profile, rung, description) VALUES
 ('breadth',  0, 'ticket 08''s shipped default: recon holds an entitled slot'),
 ('balanced', 1, 'recon keeps its slot and hunt earns one'),
 ('depth',    2, 'recon drops its entitlement; hunt and analyze hold the subagent cap');

-- max_slots for reference, from the roster (019): recon 1, hunt 2, analyze 2,
-- validate 1, report 1. `sum(min_slots)` over SUBAGENT lanes must stay under
-- `max_concurrent_subagents` = 3; validate and report run as `session` and
-- `renderer` and do not consume it, which is why ticket 08's literal invariant
-- (`sum(min_slots) <= global_cap` over all lanes) would refuse a legal profile.
INSERT INTO lane_quota_profile_slots (profile, kind, min_slots) VALUES
 ('breadth','recon',1),('breadth','hunt',0),('breadth','analyze',0),
 ('breadth','validate',1),('breadth','report',0),
 ('balanced','recon',1),('balanced','hunt',1),('balanced','analyze',0),
 ('balanced','validate',1),('balanced','report',0),
 ('depth','recon',0),('depth','hunt',2),('depth','analyze',1),
 ('depth','validate',1),('depth','report',0);

-- Policy 1 was the first draft and it is SHIPPED INACTIVE, on purpose. The A/B
-- measured it and it lost: 14 epochs in 60 passes, because `recon_novelty >=
-- 0.67` is true for as long as any unreconned endpoint exists, and because
-- `deepen_on_recon_dry` with a NULL `from_profile` also fires FROM depth and
-- drags the program back to balanced. It stays in the migration as a row so the
-- comparison in `tests/ab.sql` can be re-run rather than believed.
INSERT INTO lane_quota_policies (version, seed_profile, min_dwell_passes, active, notes)
VALUES (1, 'breadth', 2, false,
        'first draft: level-triggered widen, dwell 2. Measured, oscillates, superseded by 5');

INSERT INTO lane_quota_rules
    (policy_version, ord, rule, from_profile, to_profile, signal, op, threshold)
VALUES
 (1, 1, 'widen_on_new_surface',    NULL, 'breadth',  'recon_novelty',     '>=', 0.67),
 (1, 2, 'deepen_on_backpressure',  NULL, 'depth',    'hunt_backpressure', '>=', 2),
 (1, 3, 'deepen_on_recon_dry',     NULL, 'balanced', 'recon_novelty',     '<=', 0.34);

-- Policy 2 exists unactivated so the A/B has a second arm to compare against:
-- the budget-only switch the ticket lists as a candidate.
INSERT INTO lane_quota_policies (version, seed_profile, min_dwell_passes, active, notes)
VALUES (2, 'breadth', 2, false, 'budget-only arm, for measurement');
INSERT INTO lane_quota_rules
    (policy_version, ord, rule, from_profile, to_profile, signal, op, threshold)
VALUES (2, 1, 'deepen_on_budget', NULL, 'depth', 'budget_fraction', '>=', 0.40);

-- Policy 3 is the null arm: no rules, so the program stays on the seed rung
-- for the whole run. This is the "same run without the switch" ticket 16's
-- comparison needs, and it is a policy row rather than a code path so that both
-- arms go through exactly the same statements.
INSERT INTO lane_quota_policies (version, seed_profile, min_dwell_passes, active, notes)
VALUES (3, 'breadth', 2, false, 'null arm: seed profile held for the whole run');

-- Policy 4 is the null arm at the other end. Without it "the switch beat the
-- null arm" would only say that some depth is better than none, which nobody
-- doubts; the question is whether MOVING beats picking a rung and staying.
INSERT INTO lane_quota_policies (version, seed_profile, min_dwell_passes, active, notes)
VALUES (4, 'depth', 2, false, 'null arm: locked depth, for measurement');

-- Policy 5 is what ships. Three differences from policy 1, each one forced by
-- a number in `tests/ab.sql`, not by taste:
--   * the widen rule is edge-triggered on `recon_novelty_rise`, so "the surface
--     grew" stops meaning "recon is not finished";
--   * `deepen_on_recon_dry` is anchored `from_profile = 'breadth'`, so the rung
--     below depth cannot pull a deepened program back up;
--   * dwell is 4 passes rather than 2. A pass is not a fixed amount of work and
--     4 is a guess -- see the residual.
INSERT INTO lane_quota_policies (version, seed_profile, min_dwell_passes, active, notes)
VALUES (5, 'breadth', 4, true,
        'shipped default, unvalidated numbers: edge-triggered widen, anchored deepen, dwell 4');
INSERT INTO lane_quota_rules
    (policy_version, ord, rule, from_profile, to_profile, signal, op, threshold)
VALUES
 (5, 1, 'widen_on_new_surface',   NULL,      'breadth',  'recon_novelty_rise', '>=', 0.34),
 (5, 2, 'deepen_on_backpressure', NULL,      'depth',    'hunt_backpressure',  '>=', 2),
 (5, 3, 'deepen_on_recon_dry',    'breadth', 'balanced', 'recon_novelty',      '<=', 0.34);

-- Policy 6 is policy 5 with the widen rule made as sensitive as the signal can
-- be -- 0.125 is one property-class family out of eight, the smallest step
-- `novelty_for('recon')` can take. It exists because in the A/B the shipped
-- widen rule NEVER FIRED: the rise is measured against the value the current
-- epoch opened with, so a long-lived depth epoch carries a stale reference and
-- the detector goes blind as the epoch ages. Named, measured, not hidden.
INSERT INTO lane_quota_policies (version, seed_profile, min_dwell_passes, active, notes)
VALUES (6, 'breadth', 4, false, 'policy 5 with the most sensitive widen rule the signal admits');
INSERT INTO lane_quota_rules
    (policy_version, ord, rule, from_profile, to_profile, signal, op, threshold)
VALUES
 (6, 1, 'widen_on_new_surface',   NULL,      'breadth',  'recon_novelty_rise', '>=', 0.125),
 (6, 2, 'deepen_on_backpressure', NULL,      'depth',    'hunt_backpressure',  '>=', 2),
 (6, 3, 'deepen_on_recon_dry',    'breadth', 'balanced', 'recon_novelty',      '<=', 0.34);


-- ===========================================================================
-- 9. The surface is the runtime's and the operator's, never the agent's
-- ===========================================================================

-- Ticket 35's rule: a table is program-scoped or it is a registered exception.
-- The ladder, the signal registry and the policy are catalogue, exactly like
-- `scheduler_weights` and `roles` -- one program does not get its own rungs,
-- it gets its own EPOCHS, and `lane_quota_epochs` is program-scoped.
INSERT INTO program_global_tables (table_name, reason) VALUES
 ('lane_quota_profiles',      'the entitlement ladder is catalogue, like scheduler_weights'),
 ('lane_quota_profile_slots', 'the numbers on a rung of that ladder'),
 ('lane_quota_signals',       'the registry of replayable signals, one list for the harness'),
 ('lane_quota_policies',      'one active policy version, the way one weights row is active'),
 ('lane_quota_rules',         'the rules of a policy version');

-- Ticket 12 withheld `scheduler_weights` and `scheduler_lanes` from `rk2_state`
-- because an agent that can read the weights can aim at them. A quota is the
-- same class of number and gets the same treatment; check (g) below fails if a
-- later migration relaxes it. This is the whole argument against an
-- orchestrator-writable quota, made as a grant rather than as prose: an
-- orchestrator tool would have to reverse a resolved ticket to exist.
REVOKE ALL ON lane_quota_profiles, lane_quota_profile_slots, lane_quota_signals,
              lane_quota_policies, lane_quota_rules, lane_quota_epochs
         FROM PUBLIC;
REVOKE ALL ON current_lane_quota FROM PUBLIC;

GRANT SELECT ON lane_quota_profiles, lane_quota_profile_slots, lane_quota_signals,
                lane_quota_policies, lane_quota_rules, current_lane_quota
             TO rk2_runtime;
GRANT SELECT, INSERT ON lane_quota_epochs TO rk2_runtime;

DO $$
DECLARE f text;
BEGIN
    FOREACH f IN ARRAY ARRAY[
        'lane_signal_recon_novelty(uuid)', 'lane_signal_hunt_backpressure(uuid)',
        'lane_signal_budget_fraction(uuid)',
        'lane_signal_recon_novelty_rise(uuid)', 'lane_quota_signals_of(uuid)',
        'lane_quota_slots_of(text)', 'lane_quota_pass(uuid)',
        'advance_lane_quota(text)', 'force_lane_quota(text,text,integer)']
    LOOP
        EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC', f);
    END LOOP;
END $$;

GRANT EXECUTE ON FUNCTION advance_lane_quota(text), lane_quota_pass(uuid),
                          lane_quota_signals_of(uuid), lane_quota_slots_of(text),
                          lane_signal_recon_novelty(uuid),
                          lane_signal_hunt_backpressure(uuid),
                          lane_signal_budget_fraction(uuid) TO rk2_runtime;

-- Two independent gates on the operator's verb, the way ticket 28 gated
-- `answer_decision`: the EXECUTE grant, and the actor_kind trigger.
-- SECURITY DEFINER for the same reason 026 used it on `answer_decision`: the
-- actor-kind trigger reads `session_user`, so definer rights do not launder the
-- claim. `rk2_human` therefore gets no table write privilege anywhere -- an
-- operator console bug cannot hand-write an epoch, only call the verb -- and
-- check (k) fails if a later migration grants one.
-- One line 032 could not have known it needed. Ticket 33's `roles_and_grants`
-- carries `ALTER DEFAULT PRIVILEGES FOR ROLE rk2_owner IN SCHEMA public GRANT
-- EXECUTE ON FUNCTIONS TO rk2_runtime`, so every function this migration
-- creates is executable by the runtime the moment it is created, and revoking
-- from PUBLIC does not touch a direct grant. Check (h) below is the first thing
-- in the corpus to assert an operator-only verb at the grant level, and it
-- fires without this. The same hole is open on ticket 28's `answer_decision`
-- and is NOT closed here -- see the fold report; that is ticket 28's and
-- ticket 33's to settle, not this migration's.
REVOKE EXECUTE ON FUNCTION force_lane_quota(text,text,integer) FROM rk2_runtime;
GRANT EXECUTE ON FUNCTION force_lane_quota(text,text,integer) TO rk2_human;
GRANT SELECT ON current_lane_quota, lane_quota_profiles, lane_quota_profile_slots
             TO rk2_human;

-- 032 re-ran migration 020's RLS loop here, because 023 and 026 had each had
-- to re-run it for their own tables and 028 had forgotten to. That whole class
-- of defect is what ticket 33 removed: `apply_state_rls()` runs the identical
-- rule as a finalizer at the end of every `up`, over every program-scoped table
-- in the corpus, so `lane_quota_epochs` is covered without this migration
-- saying anything. Deleted rather than kept alongside.

-- `lane_quota_epochs` carries `actor_kind`, so ticket 28's guard has to cover
-- it. Re-running 026's own sweep is how, and it is idempotent by construction.
SELECT attach_actor_kind_guards();


-- ===========================================================================
-- 10. The standing check
-- ===========================================================================

CREATE FUNCTION check_lane_quota_closure()
RETURNS TABLE (problem text, detail text) LANGUAGE sql STABLE AS $fn$
    -- (a) a profile that does not name every kind silently reverts that lane
    --     to the default, which is a quota move nobody wrote down.
    SELECT 'profile_missing_kind'::text, pr.profile || ' ' || k.kind
      FROM lane_quota_profiles pr CROSS JOIN task_kinds k
     WHERE NOT EXISTS (SELECT 1 FROM lane_quota_profile_slots s
                        WHERE s.profile = pr.profile AND s.kind = k.kind)
UNION ALL
    -- (b) an entitlement above what the roster will staff.
    SELECT 'profile_min_above_role_cap', s.profile || ' ' || s.kind
      FROM lane_quota_profile_slots s
      JOIN role_task_kinds m ON m.kind = s.kind
      JOIN roles r ON r.role = m.role
     WHERE s.min_slots > r.max_concurrent
UNION ALL
    -- (c) ticket 08's invariant, corrected for the roster: only subagent lanes
    --     spend the concurrent-subagent cap.
    SELECT 'profile_subagent_min_over_cap', s.profile || ' ' || sum(s.min_slots)::text
      FROM lane_quota_profile_slots s
      JOIN role_task_kinds m ON m.kind = s.kind
      JOIN roles r ON r.role = m.role
     CROSS JOIN scheduler_weights w
     WHERE w.active AND r.runs_as = 'subagent'
     GROUP BY s.profile, w.max_concurrent_subagents
    HAVING sum(s.min_slots) > max(w.max_concurrent_subagents)
UNION ALL
    -- (d) a registered signal that reads the clock. The trigger refuses one at
    --     write time; this refuses one that arrived by CREATE OR REPLACE on the
    --     function afterwards.
    SELECT 'signal_reads_the_clock', s.signal
      FROM lane_quota_signals s JOIN pg_proc pr ON pr.proname = s.fn
     WHERE pr.pronamespace = 'public'::regnamespace
       AND regexp_replace(pr.prosrc, '--[^' || chr(10) || ']*', '', 'g')
           ~* '(now\(\)|current_timestamp|clock_timestamp|localtimestamp|current_date)'
UNION ALL
    -- (e) THE replay invariant, checked as data: every epoch has the event that
    --     reproduces it. An epoch with no event is a quota move the log cannot
    --     replay, which is decision 12 broken.
    SELECT 'epoch_without_event', e.program_id::text || ' #' || e.epoch
      FROM lane_quota_epochs e
     WHERE NOT EXISTS (
        SELECT 1 FROM events ev
         WHERE ev.program_id = e.program_id
           AND ev.type = 'scheduler.quota_changed'
           AND (ev.payload ->> 'epoch')::integer = e.epoch)
UNION ALL
    -- (f) the unversioned write path is still closed.
    SELECT 'scheduler_lanes_mutable', coalesce(t.tgname, 'missing')
      FROM (SELECT 1) x
      LEFT JOIN pg_trigger t
             ON t.tgrelid = 'scheduler_lanes'::regclass
            AND t.tgname = 'scheduler_lanes_no_unversioned_write'
     WHERE t.tgname IS NULL OR t.tgenabled <> 'A'
UNION ALL
    -- (g) ticket 12's rule, extended: nothing about quotas is agent-reachable.
    SELECT 'lane_quota_readable_by_agent', c.relname
      FROM pg_class c
     WHERE c.relnamespace = 'public'::regnamespace
       AND c.relkind IN ('r','v')
       AND (c.relname LIKE 'lane_quota%' OR c.relname = 'current_lane_quota')
       AND has_table_privilege('rk2_state', c.oid, 'SELECT')
UNION ALL
    SELECT 'lane_quota_function_public_executable', pr.proname
      FROM pg_proc pr
     WHERE pr.pronamespace = 'public'::regnamespace
       AND pr.prorettype <> 'trigger'::regtype   -- a trigger fn is not callable
       AND (pr.proname LIKE 'lane_quota%' OR pr.proname LIKE 'lane_signal%'
            OR pr.proname IN ('advance_lane_quota','force_lane_quota'))
       AND has_function_privilege('public', pr.oid, 'EXECUTE')
UNION ALL
    -- (h) the operator's verb is the operator's.
    SELECT 'force_lane_quota_open_to_runtime', 'rk2_runtime'
      FROM pg_proc pr
     WHERE pr.pronamespace = 'public'::regnamespace
       AND pr.proname = 'force_lane_quota'
       AND has_function_privilege('rk2_runtime', pr.oid, 'EXECUTE')
UNION ALL
    -- (i) the ledger is append-only.
    SELECT 'epoch_ledger_mutable', 'lane_quota_epochs_append_only'
     WHERE NOT EXISTS (SELECT 1 FROM pg_trigger t
                        WHERE t.tgrelid = 'lane_quota_epochs'::regclass
                          AND t.tgname = 'lane_quota_epochs_append_only'
                          AND t.tgenabled = 'A')
UNION ALL
    -- (k) the operator writes through the verb or not at all.
    SELECT 'human_writes_ledger_directly', c.relname
      FROM pg_class c
     WHERE c.relnamespace = 'public'::regnamespace AND c.relkind = 'r'
       AND c.relname LIKE 'lane_quota%'
       AND has_table_privilege('rk2_human', c.oid, 'INSERT, UPDATE, DELETE')
UNION ALL
    -- (j) a rule pointing at a rung the ladder does not contain, or an active
    --     policy with a seed the ladder does not contain.
    SELECT 'policy_seed_not_on_ladder', p.version::text
      FROM lane_quota_policies p
     WHERE NOT EXISTS (SELECT 1 FROM lane_quota_profiles pr
                        WHERE pr.profile = p.seed_profile)
$fn$;

DO $$
DECLARE v text;
BEGIN
    SELECT string_agg(problem || ' ' || detail, '; ' ORDER BY problem, detail)
      INTO v FROM check_lane_quota_closure();
    IF v IS NOT NULL THEN
        RAISE EXCEPTION 'lane quota is not closed after 032: %', v;
    END IF;
    RAISE NOTICE 'lane-quota: check_lane_quota_closure() is silent';
END $$;

DO $$
DECLARE v text;
BEGIN
    SELECT string_agg(problem || ' ' || detail, '; ' ORDER BY problem, detail)
      INTO v FROM check_scheduler_closure();
    IF v IS NOT NULL THEN
        RAISE EXCEPTION 'ticket 08 closure broken by 032: %', v;
    END IF;
    RAISE NOTICE 'lane-quota: check_scheduler_closure() is still silent';
END $$;

-- 032's `check_state_access()` self-assert lived here. It ran inside the
-- migration, i.e. before the finalizers, so with the RLS loop gone it asserted
-- a state that does not exist yet at this point in the transaction. The
-- standing check `state_access` (owner 12) asserts exactly this after
-- `apply_state_rls()` and `apply_state_grants()`, on every `up`.

DO $$
DECLARE v text;
BEGIN
    SELECT string_agg(problem || ' ' || detail, '; ' ORDER BY problem, detail)
      INTO v FROM check_program_isolation();
    IF v IS NOT NULL THEN
        RAISE EXCEPTION 'program isolation is not closed after 032: %', v;
    END IF;
END $$;

-- 032 closed with ticket 07's `ENABLE ALWAYS TRIGGER` sweep. That is
-- `enforce_always_triggers()`, a finalizer since ticket 33, run corpus-wide
-- after every migration; the copy is deleted.


-- ===========================================================================
-- 11. The three registries the baseline enforces
-- ===========================================================================
-- 032 registered `program_global_tables` (section 9) because ticket 35's rule
-- was already being asserted inside migration 017. The other three registries
-- are ticket 33's, and a table that is in none of them is a corpus problem
-- rather than a per-migration one, so they are filled in here.

-- (i) Event classification. Five of the six are catalogue in the same sense as
-- `roles` and `scheduler_weights`. The sixth is the ledger, and it is covered
-- rather than silent: `advance_lane_quota()` and `force_lane_quota()` write the
-- `scheduler.quota_changed` event in the same transaction as the row, and
-- rule (e) of `check_lane_quota_closure()` above fails if one is ever missing.
INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
 ('lane_quota_profiles',      'reference',  'the entitlement ladder; catalogue shipped with the code, not something that happens to a target', '30'),
 ('lane_quota_profile_slots', 'reference',  'the numbers on a rung of that ladder', '30'),
 ('lane_quota_signals',       'reference',  'the registry of replayable signal functions', '30'),
 ('lane_quota_policies',      'reference',  'the versioned rule set; a new policy is a new corpus row, not a program event', '30'),
 ('lane_quota_rules',         'reference',  'the rules of a policy version', '30'),
 ('lane_quota_epochs',        'covered',    'every epoch is written with its own scheduler.quota_changed event by advance_lane_quota()/force_lane_quota(); check_lane_quota_closure() rule (e) fails on an epoch without one', '30');

-- (ii) Ticket 07's rule: no FK may carry a delete action unless the edge is
-- declared. 032 has three.
INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
 ('lane_quota_profile_slots', 'profile',        'the slots ARE the rung; a profile that is deleted takes its numbers with it, and lane_quota_profile_frozen() refuses the delete outright once an epoch has pointed at it'),
 ('lane_quota_rules',         'policy_version', 'a rule has no meaning outside its policy version; dropping an unused version drops its rules'),
 ('lane_quota_epochs',        'program_id',     'program-scoped: the purge root');

-- (iii) The standing check. 032 asserted `check_lane_quota_closure()` once, in
-- its own transaction, which is the defect ticket 33 named: an invariant
-- asserted by the migration that introduced it is not asserted again by
-- anything. Registered, so `run_standing_checks()` runs it on every `up`.
INSERT INTO standing_checks (name, query, owner_ticket, note) VALUES
 ('lane_quota_closure',
  'SELECT * FROM check_lane_quota_closure()',
  '30',
  'the quota is a row, the move is replayable, and nothing about it is agent-reachable or human-writable except through force_lane_quota()');

-- No `state_read_surface` rows on purpose, and this is the one registry where
-- silence is the decision rather than an omission: ticket 12 withheld
-- `scheduler_weights` and `scheduler_lanes` from `rk2_state` because an agent
-- that can read the numbers can aim at them, and check (g) above fails if a
-- later migration registers a quota column here.
