-- ---------------------------------------------------------------------------
-- An account the operator provisioned is not an account to ask about
--
-- WHAT WAS MEASURED. `rk2here`, 2026-08-26, the first campaign in this tree to
-- hold a provisioned Identity. Sixteen laps of the driver loop, of which these
-- are the first thirteen:
--
--     rk2here-01  T776 perform -> done    accepted True
--     rk2here-02  T602 hunt    -> parked  accepted False
--     rk2here-03  T603 hunt    -> parked  accepted False
--     rk2here-04  T151 recon   -> parked  accepted False
--     rk2here-05  T152 recon   -> parked  accepted False
--     rk2here-06  T153 recon   -> parked  accepted False
--     rk2here-07  T154 recon   -> parked  accepted False
--     rk2here-08  T105 recon   -> done    accepted True
--
-- Six of thirteen laps did no work. Every one of them stopped on the same rule
-- for the same reason -- `call_risk_rules:net_borrowed_identity` -- and each
-- spent one of its Task's three attempts to ask a question the operator had
-- already answered that morning about four other hosts.
--
-- WHAT THE CONFIGURATION ALREADY SAID. `program-here.toml`, line 40:
--
--     credential_use = true
--
-- with the operator's own comment above it: "credential_use is true because two
-- accounts of our own are in play." That control is a Rule of Engagement. It is
-- loaded by `config._rules_of_engagement`, compiled into the scope policy, and
-- written to `program_scope_versions.credential_use` on every revision. It is
-- the operator saying, in the one document this harness treats as authority,
-- that this campaign works its target logged in.
--
-- Nothing read it. `program.py` reported it in the controls table and no gate
-- consulted it, so the harness asked, per host, for permission it had been
-- given once in writing.
--
-- THE MECHANISM. `net_borrowed_identity` (0026:266) names the digest fact
-- `identity_slot` and escalates any value outside `{""}`. The slot is filled
-- for every request made as somebody, so the rule fires for every host --
-- and `equivalence_key` hashes the host, so one approval covers one host. With
-- 231 host entities in this Program, the operator is asked to say the same
-- thing 231 times.
--
-- THE RULE. The fact the escalation reads becomes `unapproved_identity_slot`:
-- the slot this request will act as, where the Program has NOT declared
-- credential use, and the empty string where it has. A Program that declared
-- nothing is unaffected -- the fact equals the slot and the rule fires exactly
-- as before. A Program whose operator wrote `credential_use = true` acts as the
-- accounts they provisioned, without being asked again.
--
-- WHAT IS NOT WIDENED.
--
--   * The other rules. `net_unsafe_method` still escalates any method outside
--     GET/HEAD/OPTIONS, so a state-changing request made as an account holder
--     is still a question -- and it is a question this file makes reachable,
--     because before it the credential rule got there first and named the
--     verdict after itself.
--   * The scope. `net_host_out_of_scope` is `forbidden` and no control lowers
--     it. Being logged in has never let a request leave for a host the
--     configuration does not name.
--   * Which accounts. The slot has to resolve to an Identity of this Program
--     with a live Lease, and the secret still comes from the vault through
--     `resolve_egress_identity`. This changes who is asked, not what is
--     reachable.
--   * The record. `identity_slot` stays in the digest and therefore in the
--     equivalence key and on the Receipt: every request still says which
--     account made it.
--
-- WHAT THIS INVALIDATES. `equivalence_key` hashes the whole digest, so a new
-- fact in it is a new key for every request -- and a standing grant is matched
-- on that key. Every live grant therefore stops matching, and every question
-- already open re-gates under the rule as it now reads. That is the correct
-- ending for both: a grant is an answer about a classification, and the
-- classification moved. `revalidate_decision` reports `policy_changed` for the
-- open ones, which is `supersede_decision`'s case, and the Task goes back to
-- the queue to be gated again under the policy that holds now.
-- ---------------------------------------------------------------------------

INSERT INTO digest_facts (fact, source) VALUES
    ('unapproved_identity_slot', 'projection');

COMMENT ON TABLE digest_facts IS
  'The vocabulary an escalation rule may be written in: keys of the canonical request digest, either derived by the canonicaliser from the call itself or stamped by the runtime from what the Program has declared. There is no rule form that reads a model''s prose or a tool''s free-text argument.';


-- The digest, with the one fact that reads what the operator wrote.
--
-- Stamped unconditionally and not inside the host block above it: a fact that
-- is absent from the digest reads as NULL to `assess_call_risk`, whose `not_in`
-- arm answers false to a NULL -- so a digest that lost this key would silence
-- the rule rather than apply it, which is the failure this fact exists to
-- prevent in the other direction.
CREATE OR REPLACE FUNCTION current_request_digest(p_tool_run_id uuid) RETURNS jsonb
LANGUAGE plpgsql STABLE AS $fn$
DECLARE
    tr     tool_runs%ROWTYPE;
    digest jsonb;
    raw    text[];
    sclass text;
    nonce  text;
    cred   boolean;
BEGIN
    SELECT * INTO tr FROM tool_runs WHERE id = p_tool_run_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'no tool_run %', p_tool_run_id; END IF;

    -- Ticket 96. `park_for_human` closes the Tool run it asked about and the
    -- Task the operator releases is claimed again as a new one, so a key built
    -- on this Tool run's label is a key the next attempt cannot compute: the
    -- question would be asked again, answered again, and asked again. What the
    -- operator answered about is the Task, so that is what a body-bearing
    -- request is keyed on. Only that case: for every other tool the nonce is
    -- what it has always been, because widening any of them is a decision this
    -- ticket has no business taking.
    nonce := tr.label;
    IF tr.task_id IS NOT NULL
       AND tr.tool = 'mcp__rk2__net_request'
       AND coalesce(tr.args -> 'body_allowed' = 'true'::jsonb, false) THEN
        SELECT t.label INTO nonce FROM tasks t WHERE t.id = tr.task_id;
    END IF;

    digest := canonical_request(tr.tool, coalesce(tr.args,'{}'::jsonb), nonce);
    IF digest ->> 'host' IS NOT NULL THEN
        -- ticket 26's projection, resolved from the RAW path (the scope rules
        -- match on real paths, not on the templated one) at the program's
        -- current scope version. `scope_class` lands in the digest and is
        -- therefore part of the equivalence key: an approval given under one
        -- scope version does not survive a scope change that reclassifies the
        -- host, which is the behaviour ticket 26 asks for.
        raw := regexp_match(coalesce(tr.args ->> 'url',''),
                            '^https?://[^/:?#]+(?::[0-9]+)?([^?#]*)');
        SELECT s.scope_class INTO sclass
          FROM programs p
          CROSS JOIN LATERAL scope_class_of(p.id, p.scope_version,
                                            digest ->> 'host', (digest ->> 'port')::int,
                                            coalesce(nullif(raw[1],''),'/'),
                                            coalesce(nullif(raw[1],''),'/')) s
         WHERE p.id = tr.program_id;
        digest := digest || jsonb_build_object(
            'scope_class',   coalesce(sclass, 'not_addressable'),
            'host_in_scope', coalesce(sclass,'') IN ('target','egress_support'));
    END IF;

    -- Read at the Program's current scope version, exactly as the scope class
    -- above is: a control is part of a published revision, and a request judged
    -- against a revision nobody published would be judged against a file on
    -- somebody's disk. `false` where the row is missing, which is the same
    -- answer `config._rules_of_engagement` gives an absent control -- an absent
    -- control is a denial.
    SELECT v.credential_use INTO cred
      FROM programs p
      JOIN program_scope_versions v
        ON v.program_id = p.id AND v.version = p.scope_version
     WHERE p.id = tr.program_id;

    digest := digest || jsonb_build_object(
        'unapproved_identity_slot',
        CASE WHEN coalesce(cred, false)
             THEN ''
             ELSE coalesce(digest ->> 'identity_slot', '') END);

    RETURN digest;
END $fn$;

COMMENT ON FUNCTION current_request_digest(uuid) IS
  'The canonical digest of the request a Tool run is about to make, stamped with what the Program has declared about it: the scope class of the host at the Program''s current scope version, and whether the Identity this request acts as is one the Rules of Engagement already admit. Hashed whole by equivalence_key, so every stamp here is part of what an approval covers.';


-- The rule, reading the fact that accounts for the Rules of Engagement.
--
-- Everything else about it is unchanged: same id, same tool, same operator,
-- same class, same question code. A Program that declared no credential use
-- sees the identical behaviour, because for one of those the new fact and the
-- old one are the same string.
UPDATE call_risk_rules
   SET fact = 'unapproved_identity_slot',
       rationale = 'a request that carries an injected identity acts as a real '
                   'account holder; Q15 differentials are built out of exactly '
                   'this. Asked once per Program in the configuration rather '
                   'than once per host at the door: where rules_of_engagement.'
                   'credential_use is true the operator has already said this '
                   'campaign works its target logged in, and the fact this rule '
                   'reads is empty for such a Program'
 WHERE rule_id = 'net_borrowed_identity';


-- ===========================================================================
-- What this migration claims, asserted
-- ===========================================================================

DO $$
DECLARE
    v_named jsonb;
    n integer;
BEGIN
    SELECT count(*) INTO n FROM call_risk_rules
     WHERE rule_id = 'net_borrowed_identity' AND fact = 'unapproved_identity_slot';
    IF n <> 1 THEN
        RAISE EXCEPTION 'the credential rule does not read the control-aware fact';
    END IF;

    -- Every fact a rule names has to be one the digest carries, which is what
    -- `digest_facts` is for. Asserted here as well because this file is the one
    -- that repoints a rule at a fact nothing had produced before it.
    SELECT count(*) INTO n FROM call_risk_rules r
     WHERE NOT EXISTS (SELECT 1 FROM digest_facts f WHERE f.fact = r.fact);
    IF n <> 0 THEN
        RAISE EXCEPTION '% rule(s) name a fact no digest carries', n;
    END IF;

    -- A Program that declared nothing is a Program this file did not change.
    -- Built by hand rather than measured off a row, because the assertion is
    -- about the rule and not about whichever Programs happen to exist here.
    v_named := canonical_request(
        'mcp__rk2__net_request',
        '{"url":"https://ticket206.invalid/a","method":"GET",'
        '"identity_slot":"member-a","body_allowed":false}'::jsonb, 'T1')
        || '{"unapproved_identity_slot":"member-a"}'::jsonb;
    IF assess_call_risk('mcp__rk2__net_request', v_named) ->> 'risk_class'
       <> 'approval_required' THEN
        RAISE EXCEPTION 'a Program that declared no credential use stopped being asked';
    END IF;

    -- And one that did declare it rests on the static floor.
    v_named := v_named || '{"unapproved_identity_slot":""}'::jsonb;
    IF assess_call_risk('mcp__rk2__net_request', v_named) ->> 'risk_class'
       <> 'constrained' THEN
        RAISE EXCEPTION 'a declared credential use still asks per host';
    END IF;

    -- The method rule is untouched and is now reachable behind the one this
    -- file quietens. Asserted because it is the whole of what keeps this
    -- narrow: being logged in does not admit a state-changing request.
    v_named := canonical_request(
        'mcp__rk2__net_request',
        '{"url":"https://ticket206.invalid/a","method":"POST",'
        '"identity_slot":"member-a","body_allowed":true}'::jsonb, 'T1')
        || '{"unapproved_identity_slot":""}'::jsonb;
    IF assess_call_risk('mcp__rk2__net_request', v_named)
       ->> 'rule' <> 'call_risk_rules:net_unsafe_method' THEN
        RAISE EXCEPTION 'a state-changing request as an account holder is no longer asked about: %',
            assess_call_risk('mcp__rk2__net_request', v_named);
    END IF;
END $$;
