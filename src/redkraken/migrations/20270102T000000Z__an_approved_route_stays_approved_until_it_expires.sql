-- ---------------------------------------------------------------------------
-- 20270102T000000Z__an_approved_route_stays_approved_until_it_expires.sql
--
-- Ticket 228, wall 2. The operator answered it: option (b).
--
-- Measured on `rk2here`, 2026-08-30. Four approvals were spent on one OAuth
-- token endpoint in a single day -- D25, D26, D27, D28 -- and each one halted
-- the campaign until a human answered. The four questions are the same
-- question. D25 and D27 differ by one field:
--
--     D25   "nonce": "T887"      approved, grant to 08-31 08:45
--     D27   "nonce": "T474"      pending
--
-- WHY THE GRANT COULD NOT BE REUSED, and it is not a defect. `canonical_request`
-- (`20260924T000000Z:511-530`) puts a nonce in the digest of any call opened
-- body-bearing, because the bytes are chosen by the child AFTER the row is
-- written and the door that carries them holds no write on `tool_runs`. The
-- honest key for a call the digest cannot fully describe is a key that matches
-- nothing else. `equivalence_key` is `sha256(digest::text)` and
-- `live_grant_for` matches on it, so a body-bearing POST can never hit a grant.
-- One approval, one call, forever.
--
-- WHAT THIS ADDS. Not a wider equivalence key -- that would silently widen
-- every approval ever given. A second, named thing: an operator may state that
-- one ROUTE is approved for a period, and state it only about a question they
-- have already answered yes to once. The two lookups stay separate and the
-- narrow one still answers first, so nothing about an existing approval moves.
--
-- WHY NOT A `pending_decisions` ROW. Tried first, refused by the schema, and
-- the schema is right. `pending_decisions_key_matches_digest` requires
-- `equivalence_key = equivalence_key(request_digest)`, so a route-shaped key
-- cannot live in that column; `pending_decisions_names_one_subject` requires
-- every row to name an agent run, a tool run or a test. A standing grant names
-- none of them, because it is not about a run. A row that is not about a run
-- does not belong in the table whose every constraint says it is.
--
-- WHAT IT DOES NOT COVER, and each of these is deliberate.
--
--   * Only `gate_tool_call`. `open_impact_replay` and `rk2_pivot_refusal` reach
--     `live_grant_for` too and are left asking: a grant to POST a token
--     endpoint is not consent to demonstrate impact, and ticket 226's whole
--     point is that a demonstration costs an operator answer.
--   * The risk rule is matched, not just the route. A grant answers
--     `call_risk_rules:net_unsafe_method` on this route; a different rule
--     firing on the same route is a different question and is asked.
--   * `host_in_scope` is re-read from the LIVE digest at every lookup, not
--     stored at grant time. A host that leaves scope takes its grants with it,
--     in the same breath, with no sweep to run and nothing to remember.
--   * `unapproved_identity_slot` likewise: a call reaching for a slot nobody
--     approved is never covered, whatever the route says.
--   * An expiry is mandatory and is a CHECK, so a grant that outlives the
--     engagement cannot be written rather than merely being unlikely.
-- ---------------------------------------------------------------------------

CREATE TABLE route_grants (
    id            uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id    uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    label         text NOT NULL,

    -- The route, in the digest's own spelling. Copied field by field rather
    -- than kept as the jsonb: `canonical_request` normalises a host, a port and
    -- a path template, and a lookup that re-derived any of that here would be a
    -- second canonicaliser to keep in step with the first.
    tool          text NOT NULL,
    method        text NOT NULL,
    scheme        text NOT NULL,
    host          text NOT NULL,
    port          integer NOT NULL,
    path_template text NOT NULL,
    identity_slot text NOT NULL,

    -- What was granted, and not merely where. A route with no rule on it would
    -- be consent to whatever a future policy decides to ask about this address.
    risk_rule     text NOT NULL,

    -- Provenance. `granted_from` is the decision this widens, and it is not
    -- decoration: the verb refuses to widen anything the operator has not
    -- already approved once, so this column is the evidence of that.
    granted_from  text NOT NULL,
    reason        text NOT NULL,
    granted_by    text NOT NULL,
    granted_at    timestamptz NOT NULL DEFAULT now(),
    expires_at    timestamptz NOT NULL,
    revoked_at    timestamptz,
    revoked_by    text,
    revoked_reason text,

    UNIQUE (program_id, label),
    CONSTRAINT route_grants_expires_after_grant CHECK (expires_at > granted_at),
    CONSTRAINT route_grants_revocation_complete
        CHECK ((revoked_at IS NULL) = (revoked_by IS NULL)
           AND (revoked_at IS NULL) = (revoked_reason IS NULL))
);

COMMENT ON TABLE route_grants IS
  'An operator''s standing statement that one route, under one risk rule, is approved for a period -- the thing a body-bearing call cannot get from an equivalence key, because its digest carries a nonce. Read only by gate_tool_call, and only for a call whose live digest still says the host is in scope.';

CREATE INDEX route_grants_live_idx
    ON route_grants (program_id, host, path_template)
 WHERE revoked_at IS NULL;

INSERT INTO label_prefixes (kind, prefix) VALUES ('route_grants', 'RG');

CREATE TRIGGER route_grants_take_a_label
    BEFORE INSERT ON route_grants
    FOR EACH ROW EXECUTE FUNCTION assign_label();


-- What a new table owes, and every one of these was named by a standing check
-- rather than remembered: `event_coverage`, `event_log_integrity`,
-- `purge_travel` and `runtime_privileges` each refused the first build of this
-- file, which is the four of them doing exactly what they are for.
--
-- The events are `row` family and are two rather than one, because a grant and
-- its withdrawal are the two moments an auditor asks about. The withdrawal is
-- an UPDATE, so it arrives through the same trigger.
INSERT INTO event_types (id, family, subject_table, description) VALUES
    ('route_grant.granted', 'row', 'route_grants',
     'an operator widened one approved decision into a standing grant over its route and its risk rule'),
    ('route_grant.revoked', 'row', 'route_grants',
     'a standing route grant was withdrawn or its row otherwise moved');

INSERT INTO event_table_config
    (table_name, created_type, updated_type, ignored_columns, redacted_columns)
VALUES ('route_grants', 'route_grant.granted', 'route_grant.revoked', '{}', '{}');

CREATE TRIGGER route_grants_emit_event
    AFTER INSERT OR UPDATE ON route_grants
    FOR EACH ROW EXECUTE FUNCTION emit_event();

-- The cascade is registered rather than rewritten to NO ACTION: a grant is one
-- Program's and dies with it, which is what `program-scoped: the purge root`
-- means everywhere else in this table.
INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
    ('route_grants', 'program_id', 'program-scoped: the purge root');

INSERT INTO runtime_table_surface (table_name, privilege, added_by) VALUES
    ('route_grants', 'SELECT', '20270102T000000Z');

-- The lookup. Beside `live_grant_for` rather than inside it, so the narrow
-- question -- "did somebody approve exactly this call" -- keeps exactly the
-- body and the meaning it has today.
--
-- The two guards read the LIVE digest and not the stored row, which is the
-- whole reason a grant here is safe to leave standing: a host that leaves
-- scope, or a call reaching for a slot nobody approved, is refused by the
-- request in front of us rather than by a sweep that has to have run.
CREATE FUNCTION live_route_grant_for(p_program uuid, p_digest jsonb) RETURNS text
LANGUAGE sql STABLE AS $fn$
    SELECT g.label
      FROM route_grants g
     WHERE g.program_id = p_program
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

COMMENT ON FUNCTION live_route_grant_for(uuid, jsonb) IS
  'The route grant that answers this call, or NULL. Reads host_in_scope and unapproved_identity_slot from the digest in front of it rather than from the grant, so a host leaving scope withdraws its grants in the same breath.';

REVOKE ALL ON FUNCTION live_route_grant_for(uuid, jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION live_route_grant_for(uuid, jsonb) TO rk2_runtime;
GRANT SELECT ON route_grants TO rk2_runtime, rk2_human;


-- The one changed caller. Reproduced whole because a `CREATE OR REPLACE` is
-- the whole body; the only change is rule 5's line and the comment above it.
-- `coalesce` and not a branch: the narrow grant is asked first and a route
-- grant is what answers when there was none, which is the order that keeps an
-- existing approval doing exactly what it did yesterday.
CREATE OR REPLACE FUNCTION gate_tool_call(p_tool_run_id uuid) RETURNS jsonb
LANGUAGE plpgsql STABLE AS $fn$
DECLARE
    tr      tool_runs%ROWTYPE;
    digest  jsonb;
    verdict jsonb;
    grant_l text;
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
            'digest', digest, 'approval', NULL);
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
    -- column's name is a NULL that quietly refuses every grant this file
    -- writes -- the table would be filled, audited and never read.
    grant_l := coalesce(
        live_grant_for(tr.program_id, equivalence_key(digest)),
        (SELECT live_route_grant_for(tr.program_id, digest)
          WHERE verdict ->> 'rule' IS NOT NULL
            AND EXISTS (SELECT 1 FROM route_grants g
                         WHERE g.program_id = tr.program_id
                           AND g.risk_rule = verdict ->> 'rule'
                           AND g.revoked_at IS NULL
                           AND g.expires_at > now())));

    RETURN verdict || jsonb_build_object(
        'decision', CASE WHEN grant_l IS NULL THEN 'ask' ELSE 'allow' END,
        'digest', digest, 'approval', grant_l);
END $fn$;


-- The operator's verb. Two independent gates, which is `answer_decision`'s
-- shape and its reason: the EXECUTE grant below (only `rk2_human`) and the
-- `session_user` this records, which SECURITY DEFINER does not launder.
--
-- It widens a decision rather than describing a route, and that is the safety
-- property worth the parameter being a label: an operator cannot grant a route
-- they have never been asked about and have never approved. The route, the
-- rule and the identity all come from the digest the runtime built, so nothing
-- here is typed and nothing here can be typed wrong.
CREATE FUNCTION grant_route(p_from_label text, p_hours numeric, p_reason text)
RETURNS jsonb SECURITY DEFINER LANGUAGE plpgsql AS $fn$
DECLARE d pending_decisions%ROWTYPE; g route_grants%ROWTYPE;
BEGIN
    IF p_hours IS NULL OR p_hours <= 0 THEN
        RAISE EXCEPTION 'a route grant needs a positive number of hours, got %', p_hours;
    END IF;
    IF coalesce(btrim(p_reason), '') = '' THEN
        RAISE EXCEPTION 'a route grant needs a reason in the operator''s own words';
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
        now() + make_interval(hours => floor(p_hours)::integer,
                              mins  => floor((p_hours - floor(p_hours)) * 60)::integer))
    RETURNING * INTO g;

    RETURN jsonb_build_object(
        'label', g.label, 'granted_from', g.granted_from,
        'route', g.method || ' ' || g.scheme || '://' || g.host || ':' || g.port
                 || g.path_template,
        'identity_slot', g.identity_slot, 'risk_rule', g.risk_rule,
        'expires_at', g.expires_at, 'granted_by', g.granted_by);
END $fn$;

COMMENT ON FUNCTION grant_route(text, numeric, text) IS
  'Widen one approved decision into a standing grant over its route and its risk rule, for a period. Refuses a decision that is not approved: an operator may widen a yes and may never manufacture one.';

REVOKE ALL ON FUNCTION grant_route(text, numeric, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION grant_route(text, numeric, text) TO rk2_human;


-- And the other direction, which is the reason a grant may be left standing at
-- all: an operator who changes their mind does not have to wait for an expiry.
CREATE FUNCTION revoke_route_grant(p_label text, p_reason text)
RETURNS jsonb SECURITY DEFINER LANGUAGE plpgsql AS $fn$
DECLARE g route_grants%ROWTYPE;
BEGIN
    IF coalesce(btrim(p_reason), '') = '' THEN
        RAISE EXCEPTION 'a revocation needs a reason in the operator''s own words';
    END IF;
    PERFORM set_actor('human', session_user);

    UPDATE route_grants
       SET revoked_at = now(), revoked_by = session_user, revoked_reason = p_reason
     WHERE label = p_label AND revoked_at IS NULL
    RETURNING * INTO g;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'no live route grant %', p_label;
    END IF;

    RETURN jsonb_build_object('label', g.label, 'revoked_at', g.revoked_at,
                              'revoked_by', g.revoked_by);
END $fn$;

REVOKE ALL ON FUNCTION revoke_route_grant(text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION revoke_route_grant(text, text) TO rk2_human;


INSERT INTO runtime_verb_surface (verb, added_by, note) VALUES
    ('live_route_grant_for(uuid, jsonb)', '20270102T000000Z',
     'the second half of rule 5, read by gate_tool_call for a body-bearing call whose equivalence key can never repeat')
ON CONFLICT DO NOTHING;


DO $$
DECLARE n integer;
BEGIN
    -- The narrow lookup is untouched. Asserted against the text, because a
    -- migration that widened it by accident would look exactly like this one.
    IF (SELECT prosrc FROM pg_proc
         WHERE pronamespace = 'public'::regnamespace AND proname = 'live_grant_for')
       NOT LIKE '%equivalence_key = p_key%' THEN
        RAISE EXCEPTION 'ticket 228: live_grant_for no longer matches on the exact key';
    END IF;

    -- The two callers that must keep asking. A route grant is not consent to
    -- demonstrate impact, and this is the line that says so out loud.
    SELECT count(*) INTO n FROM pg_proc
     WHERE pronamespace = 'public'::regnamespace
       AND proname IN ('open_impact_replay', 'rk2_pivot_refusal')
       AND prosrc LIKE '%live_route_grant_for%';
    IF n > 0 THEN
        RAISE EXCEPTION 'ticket 228: % impact caller(s) now read a route grant', n;
    END IF;

    -- And the one that must. A table nothing reads is the defect being fixed
    -- rather than the fix, which is `20270101T000000Z`'s lesson one file later.
    IF (SELECT prosrc FROM pg_proc
         WHERE pronamespace = 'public'::regnamespace AND proname = 'gate_tool_call')
       NOT LIKE '%live_route_grant_for%' THEN
        RAISE EXCEPTION 'ticket 228: gate_tool_call does not read a route grant';
    END IF;
END $$;
