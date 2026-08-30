-- ---------------------------------------------------------------------------
-- 20270107T000000Z__a_route_grant_answers_only_the_rule_it_was_granted_under.sql
--
-- Ticket 228, `T228-02` and `T228-03`. THREE defects on the applied
-- `route_grants` feature, in ONE file, because a migration replaces a function
-- WHOLE: two files touching `gate_tool_call` or `grant_route` would mean the
-- later one silently discarding the earlier one's change with no error raised.
-- That is the same reason `20270106T000000Z` carried two tickets.
--
-- ===========================================================================
-- 1. T228-02 -- the grant was matched against the wrong rule
-- ===========================================================================
-- `20270102T000000Z` gave `live_route_grant_for` no rule argument at all and
-- guarded the call from outside:
--
--     (SELECT live_route_grant_for(tr.program_id, digest)
--       WHERE verdict ->> 'rule' IS NOT NULL
--         AND EXISTS (SELECT 1 FROM route_grants g
--                      WHERE g.program_id = tr.program_id
--                        AND g.risk_rule = verdict ->> 'rule' ...))
--
-- The `EXISTS` asks whether the PROGRAM holds a grant under that rule. It does
-- not ask whether THIS grant does. A Program holding a grant on route A under
-- rule R and a grant on route B under rule R2 therefore admits a call on route
-- B that fires rule R: `live_route_grant_for` matches the route and returns the
-- route-B grant, and the unrelated route-A grant satisfies the guard in front
-- of it. The rule is checked, and it is checked against a different row than
-- the one that answers.
--
-- With exactly one live grant the hole cannot fire, which is why `rk2here` has
-- been held at one since -- `D-08` in the engagement's decision log. This file
-- lifts that ceiling. It does not create a grant; that is the operator's call.
--
-- The fix is the one the ticket named: the rule becomes an argument, so the row
-- that answers is the row that was checked. That changes the signature, so the
-- old `runtime_verb_surface` row goes and a new one lands -- with a SPACE after
-- each comma, because `runtime_verbs` spells a verb with `oidvectortypes`, and
-- that is what it produces.
--
-- `verdict ->> 'rule'` and not `'risk_rule'`. `assess_call_risk` returns
-- `jsonb_build_object('risk_class', base, 'rule', rule, 'question_code', qc)`
-- (`0026_human_control.sql:310`); `risk_rule` is the `pending_decisions` COLUMN
-- the value lands in later. Reading it under the column's name is a NULL, and a
-- NULL here is now a refusal rather than a bypass: `g.risk_rule = p_rule` is
-- never true for a NULL argument, so a caller that cannot name the rule gets no
-- grant. The old `WHERE verdict ->> 'rule' IS NOT NULL` guard is retired
-- because the join now says the same thing and says it inside the lookup.
--
-- ===========================================================================
-- 2. T228-03 -- two rough edges, and a third carried from an earlier handoff
-- ===========================================================================
--
-- (a) `grant_route` floors its hours into `make_interval(hours, mins)`, so any
--     `p_hours` below `1/60` floors to a zero interval, `expires_at` lands on
--     `now()` and the operator is handed a raw
--     `route_grants_expires_after_grant` constraint violation. The `p_hours <=
--     0` branch above it was already refusing this case in the verb's own
--     words for the value zero; it just could not see 0.005.
--
-- (b) `event_table_config` names ONE `updated_type` per table, and for
--     `route_grants` it is `route_grant.revoked`. So EVERY update is audited as
--     a revocation, including one that revokes nothing. The registration cannot
--     express two kinds of update -- `emit_event` reads one column -- so the
--     fix is to make the single name true rather than to weaken it to
--     `route_grant.changed`, which would buy an accurate label by throwing away
--     the withdrawal event `D-05` deliberately asked for.
--
--     Made true the way `callback_channel_bindings` makes its own single
--     `callback.released` true: a BEFORE UPDATE trigger under which the only
--     legal update IS the revocation. `enforce_callback_binding_release`
--     (`20260912T000000Z:170-185`) is the sibling, down to the `ENABLE ALWAYS`.
--
--     It closes a second thing on the way. Nothing but a migration or a future
--     SECURITY DEFINER verb can update this table today, but an `UPDATE
--     route_grants SET expires_at = ...` would have extended a standing egress
--     grant without passing `grant_route`'s "you may widen a yes, never
--     manufacture one" gate -- and the audit trail would have called that
--     extension a revocation.
--
--     The columns are compared as jsonb minus the three revocation ones rather
--     than restated by name. The sibling restates them and gives the reason --
--     "a column added later must be refused until somebody decides otherwise"
--     -- and the jsonb form is that reason honoured automatically instead of by
--     hand.
--
-- (c) `grant_route` does not require `grant_expires_at IS NOT NULL` on the
--     decision it widens, and it must. `answer_decision` writes `now() +
--     p_grant`, so an approval given with no grant window lands NULL, and a
--     grant widened from it is DEAD ON ARRIVAL rather than wrong: since
--     `20270103T000000Z` the gate resolves a grant back through
--     `granted_from` under arm (e)'s own two conditions -- `d.status =
--     'approved' AND d.grant_expires_at IS NOT NULL` -- so nothing resolves,
--     `route_l` is cleared, and the call is asked about anyway. The operator
--     would have had a row in `route_grants`, an audit event saying they
--     granted a route, and no call ever admitted by it.
--
--     Refused at grant time in the verb's own words, which is the same bar
--     `live_grant_for` has always held for the narrow lookup
--     (`AND d.grant_expires_at IS NOT NULL`). A grant may not outlive an
--     approval that was never given a window, because such an approval never
--     authorised anything past its own call.
--
-- ===========================================================================
-- What is deliberately NOT touched
-- ===========================================================================
--   * `live_grant_for`. Asserted against its own text below, as both earlier
--     files assert it: a migration that widened it by accident would look
--     exactly like this one.
--   * `check_receipt_integrity`. `D-11`'s rule holds -- the gate must not admit
--     a call it could only record as a violation -- and the way it holds is
--     that `gate_tool_call` still quotes arm (e)'s two exemptions verbatim. The
--     `DO` block at the foot asserts BOTH halves, so the day arm (e) changes
--     its exemptions, this file's descendant fails rather than the harness.
--   * `open_impact_replay` and `rk2_pivot_refusal`, which still ask. A grant to
--     POST a token endpoint is not consent to demonstrate impact.
--   * No Python. `live_route_grant_for` has one caller and it is
--     `gate_tool_call`; the console still sends `grant_route(label, hours,
--     reason)` and `revoke_route_grant(label, reason)` unchanged.
-- ---------------------------------------------------------------------------


-- ===========================================================================
-- The lookup takes the rule it is being asked about
-- ===========================================================================
-- Dropped and recreated rather than replaced: a new argument list is a new
-- function, so `CREATE OR REPLACE` would have left an overload behind and
-- `gate_tool_call` would have kept resolving to the old one.

DROP FUNCTION live_route_grant_for(uuid, jsonb);

CREATE FUNCTION live_route_grant_for(p_program uuid, p_digest jsonb, p_rule text)
RETURNS text
LANGUAGE sql STABLE AS $fn$
    SELECT g.label
      FROM route_grants g
     WHERE g.program_id = p_program
       AND g.risk_rule = p_rule
       AND g.revoked_at IS NULL
       AND g.expires_at > now()
       AND coalesce(p_digest -> 'host_in_scope' = 'true'::jsonb, false)
       AND coalesce(p_digest ->> 'unapproved_identity_slot', '') = ''
       AND g.tool          = p_digest ->> 'tool'
       AND g.method        = p_digest ->> 'method'
       AND g.scheme        = p_digest ->> 'scheme'
       AND g.host          = p_digest ->> 'host'
       AND g.port          = (p_digest ->> 'port')::integer
       AND g.path_template = p_digest ->> 'path_template'
       AND g.identity_slot = coalesce(p_digest ->> 'identity_slot', '')
     ORDER BY g.expires_at DESC
     LIMIT 1;
$fn$;

COMMENT ON FUNCTION live_route_grant_for(uuid, jsonb, text) IS
  'The route grant that answers this call under this risk rule, or NULL. The rule is matched against the grant that answers rather than against any grant the Program holds, so a Program may hold grants on two routes under two rules. Reads host_in_scope and unapproved_identity_slot from the digest in front of it rather than from the grant, so a host leaving scope withdraws its grants in the same breath.';

REVOKE ALL ON FUNCTION live_route_grant_for(uuid, jsonb, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION live_route_grant_for(uuid, jsonb, text) TO rk2_runtime;

-- A changed signature is a changed registration. The old row would fail
-- `runtime_verb_surface_names_missing_function` and the new one is owed by
-- `runtime_holds_undeclared_verb`; both arms of `standing:runtime_privileges`
-- halt the harness, so both moves belong in the same transaction.
DELETE FROM runtime_verb_surface WHERE verb = 'live_route_grant_for(uuid, jsonb)';

INSERT INTO runtime_verb_surface (verb, added_by, note) VALUES
    ('live_route_grant_for(uuid, jsonb, text)', '20270107T000000Z',
     'the second half of rule 5, read by gate_tool_call for a body-bearing call whose equivalence key can never repeat; the rule is an argument since T228-02, so the grant that answers is the grant that was checked')
ON CONFLICT DO NOTHING;


-- ===========================================================================
-- The gate asks about one grant instead of the Program's whole shelf
-- ===========================================================================
-- Reproduced whole from `20270103T000000Z`, which is what a `CREATE OR REPLACE`
-- of a plpgsql function is. The only change is rule 5's route branch: the guard
-- in front of the lookup is gone and the rule went inside it. Everything after
-- it -- the resolution through `granted_from`, arm (e)'s two conditions, the
-- clearing of `route_l` when nothing resolves -- is byte-for-byte the same.

CREATE OR REPLACE FUNCTION gate_tool_call(p_tool_run_id uuid) RETURNS jsonb
LANGUAGE plpgsql STABLE AS $fn$
DECLARE
    tr      tool_runs%ROWTYPE;
    digest  jsonb;
    verdict jsonb;
    grant_l text;
    route_l text;
BEGIN
    SELECT * INTO tr FROM tool_runs WHERE id = p_tool_run_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'no tool_run %', p_tool_run_id; END IF;

    digest  := current_request_digest(p_tool_run_id);
    verdict := assess_call_risk(tr.tool, digest);

    IF (SELECT decision FROM risk_classes
         WHERE risk_class = verdict ->> 'risk_class') <> 'ask' THEN
        RETURN verdict || jsonb_build_object(
            'decision', (SELECT decision FROM risk_classes
                          WHERE risk_class = verdict ->> 'risk_class'),
            'digest', digest, 'approval', NULL, 'route_grant', NULL);
    END IF;

    -- rule 5: a live grant answers the question instead of re-asking it, and
    -- since ticket 228 there are two kinds. The exact one first and unchanged.
    -- The route grant second, and only for the rule it was granted under: a
    -- body-bearing call carries a nonce it did not choose the bytes for, so its
    -- key matches nothing and the narrow lookup can never answer it.
    --
    -- `verdict ->> 'rule'`, because that is what `assess_call_risk` names it
    -- (`0026:310`). `risk_rule` is the COLUMN the rule is stored in once
    -- `park_for_human` has written it down, and reading the verdict under the
    -- column's name is a NULL that quietly refuses every grant this table
    -- holds -- filled, audited and never read.
    --
    -- T228-02: the rule is an ARGUMENT and no longer a guard standing beside
    -- the lookup. The guard asked whether the Program held a grant under this
    -- rule; the argument asks whether THIS grant is under it, which is the
    -- question that was meant. A NULL rule matches no row, so the old
    -- `verdict ->> 'rule' IS NOT NULL` test is now the join's own.
    --
    -- A branch and no longer a `coalesce`, because the two lookups answer with
    -- different things: the narrow one returns the decision itself, the route
    -- one returns a grant that has to be resolved back to the decision it
    -- widens before the receipt can name anybody.
    grant_l := live_grant_for(tr.program_id, equivalence_key(digest));

    IF grant_l IS NULL THEN
        route_l := live_route_grant_for(tr.program_id, digest, verdict ->> 'rule');

        -- The decision the grant widens, which is the authority the receipt
        -- will name. Read through `granted_from` rather than recomputed:
        -- `grant_route` writes the label of a decision it has just checked is
        -- approved, and that column exists to be the evidence of it.
        --
        -- The two conditions on the decision are arm (e)'s own, quoted rather
        -- than assumed: an approval with no standing grant on it is not one
        -- the check will accept as an authority, so the gate must not allow a
        -- call it could only record as a violation. Nothing resolves, nothing
        -- is granted, and the call is asked about -- which is what the operator
        -- would have been asked anyway.
        SELECT d.label INTO grant_l
          FROM route_grants g
          JOIN pending_decisions d
            ON d.program_id = g.program_id AND d.label = g.granted_from
         WHERE g.program_id = tr.program_id
           AND g.label = route_l
           AND d.status = 'approved'
           AND d.grant_expires_at IS NOT NULL;

        IF grant_l IS NULL THEN route_l := NULL; END IF;
    END IF;

    RETURN verdict || jsonb_build_object(
        'decision', CASE WHEN grant_l IS NULL THEN 'ask' ELSE 'allow' END,
        'digest', digest, 'approval', grant_l, 'route_grant', route_l);
END $fn$;

COMMENT ON FUNCTION gate_tool_call(uuid) IS
  'Ticket 11 rules 1-5 for one Tool run. `approval` is the human decision that admits the call -- the one whose exact key matched, or the one a route grant widens -- and `route_grant` is the standing grant that reached it, when a route grant is what answered. Since T228-02 a route grant answers only for the risk rule it was itself granted under.';


-- ===========================================================================
-- The operator's verb refuses what it used to write and let the gate ignore
-- ===========================================================================
-- Reproduced whole from `20270102T000000Z` with two refusals added and nothing
-- removed. `SECURITY DEFINER` is restated because `CREATE OR REPLACE` resets
-- what it is not told; the grants and the owner survive it.

CREATE OR REPLACE FUNCTION grant_route(p_from_label text, p_hours numeric, p_reason text)
RETURNS jsonb SECURITY DEFINER LANGUAGE plpgsql AS $fn$
DECLARE
    d pending_decisions%ROWTYPE;
    g route_grants%ROWTYPE;
    v_window interval;
BEGIN
    IF p_hours IS NULL OR p_hours <= 0 THEN
        RAISE EXCEPTION 'a route grant needs a positive number of hours, got %', p_hours;
    END IF;
    IF coalesce(btrim(p_reason), '') = '' THEN
        RAISE EXCEPTION 'a route grant needs a reason in the operator''s own words';
    END IF;

    -- T228-03(a). Computed once, here, so the refusal is about the window that
    -- was asked for rather than about the CHECK it would have violated. Below
    -- 1/60 both floors are zero, `expires_at` lands on `granted_at` and the
    -- operator used to be handed `route_grants_expires_after_grant`, which
    -- names a constraint and not a mistake.
    v_window := make_interval(hours => floor(p_hours)::integer,
                              mins  => floor((p_hours - floor(p_hours)) * 60)::integer);
    IF v_window <= interval '0' THEN
        RAISE EXCEPTION 'a route grant of % hours rounds down to no window at all; '
                        'the shortest one this verb writes is a minute (1/60)', p_hours;
    END IF;

    PERFORM set_actor('human', session_user);

    SELECT * INTO d FROM pending_decisions WHERE label = p_from_label;
    IF NOT FOUND THEN RAISE EXCEPTION 'no decision %', p_from_label; END IF;

    -- The rule this whole verb exists to hold: you may widen a yes, never
    -- manufacture one.
    IF d.status <> 'approved' THEN
        RAISE EXCEPTION 'decision % is %, and only an approved one may be widened '
                        'into a route grant', p_from_label, d.status;
    END IF;

    -- T228-03(c). A yes with no window on it authorises its own call and
    -- nothing after it -- `live_grant_for` has always required
    -- `grant_expires_at IS NOT NULL`, and so does arm (e) of
    -- `check_receipt_integrity`, which is why `gate_tool_call` quotes it when
    -- it resolves a grant back to its decision. Widening such an approval used
    -- to write a row that no call could ever be admitted under: granted,
    -- audited, and dead on arrival. Refused here instead.
    IF d.grant_expires_at IS NULL THEN
        RAISE EXCEPTION 'decision % was approved without a grant window, and a route '
                        'grant may not outlive an approval that was never given one',
                        p_from_label;
    END IF;

    IF d.tool <> 'mcp__rk2__net_request' THEN
        RAISE EXCEPTION 'decision % is about %, and a route is a net_request shape',
                        p_from_label, d.tool;
    END IF;
    IF d.request_digest ->> 'host' IS NULL OR d.request_digest ->> 'path_template' IS NULL THEN
        RAISE EXCEPTION 'decision % carries no route to grant', p_from_label;
    END IF;

    INSERT INTO route_grants (
        program_id, tool, method, scheme, host, port, path_template,
        identity_slot, risk_rule, granted_from, reason, granted_by, expires_at)
    VALUES (
        d.program_id,
        d.request_digest ->> 'tool',
        d.request_digest ->> 'method',
        d.request_digest ->> 'scheme',
        d.request_digest ->> 'host',
        (d.request_digest ->> 'port')::integer,
        d.request_digest ->> 'path_template',
        coalesce(d.request_digest ->> 'identity_slot', ''),
        d.risk_rule,
        d.label,
        p_reason,
        session_user,
        now() + v_window)
    RETURNING * INTO g;

    RETURN jsonb_build_object(
        'label', g.label, 'granted_from', g.granted_from,
        'route', g.method || ' ' || g.scheme || '://' || g.host || ':' || g.port
                 || g.path_template,
        'identity_slot', g.identity_slot, 'risk_rule', g.risk_rule,
        'expires_at', g.expires_at, 'granted_by', g.granted_by);
END $fn$;

COMMENT ON FUNCTION grant_route(text, numeric, text) IS
  'Widen one approved decision into a standing grant over its route and its risk rule, for a period. Refuses a decision that is not approved: an operator may widen a yes and may never manufacture one. Refuses one approved without a grant window, and a period that rounds down to nothing.';


-- ===========================================================================
-- The one update a route grant takes is its revocation
-- ===========================================================================
-- T228-03(b). `event_table_config` names one `updated_type` per table, so the
-- audit trail can only say one thing about an UPDATE here and it says
-- `route_grant.revoked`. This is what makes that true, rather than weakening it
-- to a name that covers anything: `callback_channel_bindings` holds its single
-- `callback.released` the same way, with `enforce_callback_binding_release`
-- (`20260912T000000Z:170-185`).
--
-- BEFORE UPDATE only. A DELETE on this table is the Program purge travelling
-- down `route_grants_program_id_fkey`, and a purge that cannot delete a grant
-- is a Program that cannot be purged -- ticket 33 rule F, and the reason
-- `reject_mutation_unless_purging` reads `app.purging` at all.

CREATE FUNCTION route_grants_only_revocation_moves() RETURNS trigger
LANGUAGE plpgsql AS $fn$
BEGIN
    IF OLD.revoked_at IS NOT NULL THEN
        RAISE EXCEPTION 'route grant % was already revoked at %', OLD.label, OLD.revoked_at
            USING ERRCODE = '23514';
    END IF;
    IF NEW.revoked_at IS NULL THEN
        RAISE EXCEPTION 'the only change a route grant takes is its revocation'
            USING ERRCODE = '23514',
                  HINT = 'revoke it and widen the decision again; a grant edited afterwards '
                         'is not the statement the operator made';
    END IF;
    -- Everything but the three revocation columns, compared whole. The sibling
    -- restates its columns by name and gives the reason -- a column added later
    -- must be refused until somebody decides otherwise -- and this is that
    -- reason honoured by construction instead of by hand.
    IF to_jsonb(NEW) - 'revoked_at' - 'revoked_by' - 'revoked_reason'
       IS DISTINCT FROM
       to_jsonb(OLD) - 'revoked_at' - 'revoked_by' - 'revoked_reason' THEN
        RAISE EXCEPTION 'a route grant may be revoked and not otherwise rewritten'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $fn$;

COMMENT ON FUNCTION route_grants_only_revocation_moves() IS
  'The one UPDATE a route grant admits is the one that revokes it, so that the single route_grant.revoked event_table_config names for this table is true of every update it ever audits.';

CREATE TRIGGER route_grants_revocation_only
    BEFORE UPDATE ON route_grants
    FOR EACH ROW EXECUTE FUNCTION route_grants_only_revocation_moves();

-- `enforce_always_triggers` would sweep this at the end of the run, but a
-- trigger that is only ALWAYS after the finalizer is one `SET
-- session_replication_role = 'replica'` away from being off in the window
-- between -- and inside a dry run there is no finalizer at all.
ALTER TABLE route_grants ENABLE ALWAYS TRIGGER route_grants_revocation_only;


DO $$
DECLARE n integer; src text;
BEGIN
    -- The two-argument form is gone rather than shadowed. An overload left
    -- behind would still resolve for any caller passing two arguments, which
    -- is the whole defect this file closes.
    SELECT count(*) INTO n FROM pg_proc
     WHERE pronamespace = 'public'::regnamespace AND proname = 'live_route_grant_for';
    IF n <> 1 THEN
        RAISE EXCEPTION 'T228-02: % live_route_grant_for overloads, expected exactly 1', n;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM runtime_verbs
                    WHERE verb = 'live_route_grant_for(uuid, jsonb, text)' AND closed AND held) THEN
        RAISE EXCEPTION 'T228-02: the runtime cannot execute the three-argument lookup';
    END IF;
    IF EXISTS (SELECT 1 FROM runtime_verb_surface
                WHERE verb = 'live_route_grant_for(uuid, jsonb)') THEN
        RAISE EXCEPTION 'T228-02: the two-argument row is still registered';
    END IF;

    SELECT prosrc INTO src FROM pg_proc
     WHERE pronamespace = 'public'::regnamespace AND proname = 'gate_tool_call';

    -- The Program-wide EXISTS is gone, and the rule travels as an argument.
    IF src LIKE '%g.risk_rule = verdict%' THEN
        RAISE EXCEPTION 'T228-02: gate_tool_call still matches the rule Program-wide';
    END IF;
    IF src NOT LIKE '%live_route_grant_for(tr.program_id, digest, verdict ->> ''rule'')%' THEN
        RAISE EXCEPTION 'T228-02: gate_tool_call does not pass the rule to the lookup';
    END IF;

    -- D-11's property, asserted from BOTH ends rather than remembered: the gate
    -- quotes arm (e)'s two exemptions, so it cannot admit a call it could only
    -- record as a violation. If arm (e) ever changes them, this fails here
    -- instead of halting a lap.
    IF src NOT LIKE '%d.status = ''approved''%'
       OR src NOT LIKE '%d.grant_expires_at IS NOT NULL%' THEN
        RAISE EXCEPTION 'T228-02: gate_tool_call no longer quotes arm (e)''s exemptions';
    END IF;
    SELECT prosrc INTO src FROM pg_proc
     WHERE pronamespace = 'public'::regnamespace AND proname = 'check_receipt_integrity';
    IF src NOT LIKE '%d.status = ''approved''%'
       OR src NOT LIKE '%d.grant_expires_at IS NOT NULL%' THEN
        RAISE EXCEPTION 'T228-02: arm (e) no longer carries the exemptions the gate quotes';
    END IF;

    -- The narrow lookup is untouched, as both earlier files assert it.
    IF (SELECT prosrc FROM pg_proc
         WHERE pronamespace = 'public'::regnamespace AND proname = 'live_grant_for')
       NOT LIKE '%equivalence_key = p_key%' THEN
        RAISE EXCEPTION 'ticket 228: live_grant_for no longer matches on the exact key';
    END IF;

    -- The two callers that must keep asking, and the one that must read.
    SELECT count(*) INTO n FROM pg_proc
     WHERE pronamespace = 'public'::regnamespace
       AND proname IN ('open_impact_replay', 'rk2_pivot_refusal')
       AND prosrc LIKE '%live_route_grant_for%';
    IF n > 0 THEN
        RAISE EXCEPTION 'ticket 228: % impact caller(s) now read a route grant', n;
    END IF;

    -- T228-03(b): the trigger that makes the single updated_type honest, and
    -- the state 016 requires of every enforcement trigger.
    IF NOT EXISTS (SELECT 1 FROM pg_trigger
                    WHERE tgrelid = 'route_grants'::regclass
                      AND tgname = 'route_grants_revocation_only'
                      AND tgenabled = 'A'
                      AND tgfoid = 'route_grants_only_revocation_moves'::regproc) THEN
        RAISE EXCEPTION 'T228-03: route_grants takes any update again';
    END IF;

    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, src FROM check_receipt_integrity(NULL, interval '1 hour')
     WHERE problem = 'decision_disagrees_with_risk_class';
    IF n > 0 THEN
        RAISE EXCEPTION 'a decision still departs from its risk class unexplained (%): %', n, src;
    END IF;
END $$;
