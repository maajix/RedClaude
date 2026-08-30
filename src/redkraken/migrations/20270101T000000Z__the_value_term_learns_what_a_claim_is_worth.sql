-- ---------------------------------------------------------------------------
-- 20270101T000000Z__the_value_term_learns_what_a_claim_is_worth.sql
--
-- Ticket 227. The value term, given the one thing it could not say.
--
-- Measured on `rk2here`, 2026-08-30, after five days and 1165 Tasks: nine
-- Findings, eight `candidate/info` and one `validated/low`. Not one reached
-- `medium`. The pending `hunt` queue explains why, and it explains it in two
-- numbers.
--
--   family                   n   direct_value  novelty  priority
--   information_disclosure  205     0.700       0.333    0.517
--   transport               202     0.700       0.333    0.517
--   authentication           21     0.700       0.333    0.517
--   session_handling         18     0.700       0.333    0.517
--   business_logic            3     0.700       0.333    0.517
--   authorization            15     0.700       0.250    0.388
--   injection                 3     0.700       0.250    0.388
--
-- `direct_value` is 0.700 on all 464. The two families that can pay out above
-- `medium` are the two at the bottom, with 428 Tasks in front of them that
-- cannot. And the ordering that put them there is not a judgement about worth:
--
--   0.250 / 0.333 = 0.7507      the novelty ratio
--   0.388 / 0.517 = 0.7505      the priority ratio
--
-- With `direct_value` constant and `unlock_value` 0 on all 1165 rows, the only
-- term in `priority` that varies across families is `novelty_for`, which is
-- `1.0 / (1 + n_ev)`. An authorization claim carries three evidence rows where
-- a header-policy claim carries two, so the harness ranks the claim it has
-- looked at hardest LAST. Five days of a live campaign chose TLS headers over
-- tenant isolation, and it chose correctly under the rules it was given.
--
-- WHERE THE RULE IS. `20261129T000000Z` gave the value term a floor to stand
-- on, and its own header names what it left: "Ticket 196 lists three [ways
-- out]. This is the second: a per-kind prior." A per-kind prior was the right
-- first move and it is why a priority exists at all. But `kind` cannot carry
-- impact, because impact is not a property of the action -- it is a property
-- of the claim the action tests. `authorization.object_ownership` and
-- `transport.header_policy` are both `hunt`, and under a per-kind prior they
-- resolve to the same 0.70 forever.
--
-- So this is that file's successor rather than its correction. Everything it
-- built is reused: the jsonb prior beside `cost_prior`, the coalesce chain
-- that prefers a model estimate over a prior, the CASE that keeps NULL
-- distinguishable from zero, and the closure arm that makes an unpriced entry
-- a named defect instead of a silent default. One link is added to the chain
-- and one arm to the check.
--
-- `gain_prior` is NOT touched. Gain is how much uncertainty the ACTION
-- resolves and a kind is exactly the right key for it; impact is what the
-- CLAIM is worth. Only one of the two was ever filed under the wrong noun.
--
-- KEYED BY CLASS AND NOT BY FAMILY, and the reason is three rows. A per-family
-- number is nine numbers instead of sixty-one and it is wrong where it matters
-- most: `transport.request_framing` is request smuggling and belongs at 0.90
-- inside the family whose median is 0.15; `information_disclosure
-- .credential_material` is a leaked secret at 0.95 inside a family whose
-- median is 0.45; `injection.formula` is the weakest member of the strongest
-- family. A family prior gets all three backwards.
--
-- THE NUMBERS ARE UNVALIDATED, exactly as decision 16 says every number in
-- this table is. What they encode is one ordering and it is the ordering a
-- bounty program pays: a class is scored by the severity its BEST case can
-- reach, not by the severity its average case does. A class whose best case is
-- a full account takeover outranks one whose best case is a verbose stack
-- trace, whatever the odds of either.
--
-- No backfill. `rank_pass` recomputes `direct_value` for every pending Task on
-- every pass, so the 735 `hunt` rows already standing re-rank on the first
-- pass after this migration and no UPDATE here has to reach them.
-- ---------------------------------------------------------------------------

-- Defaulted, filled, default dropped -- `20261129T000000Z`'s shape and its
-- reason: a new weights version must state its own priors rather than inherit
-- an old campaign's, and the existing version rows must be completed rather
-- than left empty, because `value_for` reads the row a replay names and not
-- the row that is active today.
ALTER TABLE scheduler_weights
    ADD COLUMN class_impact_prior jsonb NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE scheduler_weights
    DISABLE TRIGGER scheduler_weights_versions_are_immutable;

UPDATE scheduler_weights SET class_impact_prior = '{
  "authentication.credential_verification": 0.90,
  "authentication.factor_enforcement": 0.85,
  "authentication.federation_trust": 0.90,
  "authentication.recovery_flow": 0.85,

  "authorization.channel_subscription": 0.80,
  "authorization.edge_rule": 0.90,
  "authorization.function_access": 0.90,
  "authorization.object_ownership": 0.95,
  "authorization.object_property_write": 0.85,
  "authorization.parallel_route": 0.85,
  "authorization.state_transition": 0.85,
  "authorization.tenant_isolation": 0.95,
  "authorization.token_scope": 0.85,

  "business_logic.quantity_or_price": 0.85,
  "business_logic.replay": 0.75,
  "business_logic.workflow_order": 0.75,

  "information_disclosure.artifact_exposure": 0.65,
  "information_disclosure.cached_response": 0.50,
  "information_disclosure.client_storage": 0.55,
  "information_disclosure.credential_material": 0.95,
  "information_disclosure.dependency_manifest": 0.25,
  "information_disclosure.error_detail": 0.25,
  "information_disclosure.excess_field": 0.40,
  "information_disclosure.identifier_oracle": 0.45,
  "information_disclosure.log_record": 0.60,
  "information_disclosure.undeclared_field": 0.40,
  "information_disclosure.workload_metadata": 0.30,

  "injection.client_channel": 0.65,
  "injection.client_path": 0.65,
  "injection.command": 1.00,
  "injection.document_parser": 0.85,
  "injection.foreign_resource": 0.60,
  "injection.formula": 0.55,
  "injection.markup": 0.70,
  "injection.model_instruction": 0.70,
  "injection.object_graph": 0.95,
  "injection.parameter_precedence": 0.60,
  "injection.parser_differential": 0.80,
  "injection.path": 0.90,
  "injection.query_field": 0.85,
  "injection.query_language": 0.95,
  "injection.query_operator": 0.85,
  "injection.request_forgery": 0.90,
  "injection.stored_file": 0.90,
  "injection.template": 0.95,
  "injection.unclaimed_reference": 0.60,
  "injection.url_authority": 0.75,

  "rate_limiting.per_identity": 0.45,
  "rate_limiting.per_origin": 0.35,
  "rate_limiting.resource_cost": 0.50,

  "session_handling.cookie_parsing": 0.65,
  "session_handling.cookie_scope": 0.55,
  "session_handling.cross_origin_read": 0.70,
  "session_handling.csrf": 0.70,
  "session_handling.fixation": 0.75,
  "session_handling.lifetime": 0.45,

  "transport.certificate_trust": 0.45,
  "transport.datagram_transport": 0.35,
  "transport.header_policy": 0.15,
  "transport.request_framing": 0.90,
  "transport.tls_configuration": 0.40
}'::jsonb;

ALTER TABLE scheduler_weights
    ENABLE ALWAYS TRIGGER scheduler_weights_versions_are_immutable;

ALTER TABLE scheduler_weights
    ALTER COLUMN class_impact_prior DROP DEFAULT;

COMMENT ON COLUMN scheduler_weights.class_impact_prior IS
  'property class -> potential impact in [0,1], read by value_for() for a Task that names a hypothesis, ahead of the per-kind impact_prior. Scored by the severity the class''s best case can reach. Unvalidated, like every number in this table.';


-- The one changed function, and one link longer than `20261129T000000Z` left
-- it. The order is estimate, then claim, then kind, and each step is a
-- statement about who knew more: a model that priced this Task beats a
-- catalogue, and a catalogue that knows the claim beats one that knows only
-- the verb.
--
-- A Task with no hypothesis -- every `recon`, every `report` -- takes the kind
-- prior it takes today, without a branch: the scalar subquery returns NULL,
-- `jsonb ->> NULL` is NULL, and the coalesce falls through. So does a class
-- nobody priced, which is what the new closure arm below exists to catch
-- before it can happen quietly.
--
-- `gain` is unchanged, character for character.
CREATE OR REPLACE FUNCTION value_for(t tasks, w scheduler_weights) RETURNS numeric
LANGUAGE sql STABLE AS $fn$
    SELECT CASE WHEN v.gain IS NULL OR v.impact IS NULL THEN NULL
                ELSE least(greatest(w.w_gain * v.gain + w.w_impact * v.impact, 0), 1.0)
           END
      FROM (SELECT coalesce(t.expected_information_gain,
                            (w.gain_prior   ->> t.kind)::numeric),
                   coalesce(t.potential_impact,
                            (w.class_impact_prior ->> (
                                SELECT h.property_class FROM hypotheses h
                                 WHERE h.id = t.hypothesis_id))::numeric,
                            (w.impact_prior ->> t.kind)::numeric)) AS v(gain, impact);
$fn$;

COMMENT ON FUNCTION value_for(tasks, scheduler_weights) IS
  'The Task''s own value under these weights, normalised into [0, 1]: the model''s estimate where there is one, this claim''s class prior where the Task names a hypothesis, this kind''s prior where it does not, and NULL for a kind with neither -- NULL and not zero, because an unpriced kind is a different statement from a worthless one.';


-- Arm (a) of the closure check gains a fourth question. Reproduced whole
-- because a `CREATE OR REPLACE` is the whole body; the only change is the arm
-- after `kind_has_no_impact_prior` and the comment above it. Everything from
-- (b) down is `20261129T000000Z` character for character.
CREATE OR REPLACE FUNCTION check_scheduler_closure()
RETURNS TABLE (problem text, detail text) LANGUAGE sql STABLE AS $fn$
    -- (a) every kind the roster grants can be ranked by every factor. A kind
    --     with no prior in one of them is a task that ranks NULL forever and
    --     nobody notices -- which is ticket 196, measured over 480 Tasks and
    --     eight hours of a live engagement. With all three priors present a
    --     NULL priority is unreachable, so these three arms ARE the check the
    --     ticket asked for and there is no fourth one counting unranked queues.
    SELECT 'kind_has_no_cost_prior'::text, k.kind
      FROM task_kinds k, scheduler_weights w
     WHERE w.active AND NOT (w.cost_prior ? k.kind)
UNION ALL
    SELECT 'kind_has_no_gain_prior', k.kind
      FROM task_kinds k, scheduler_weights w
     WHERE w.active AND NOT (w.gain_prior ? k.kind)
UNION ALL
    SELECT 'kind_has_no_impact_prior', k.kind
      FROM task_kinds k, scheduler_weights w
     WHERE w.active AND NOT (w.impact_prior ? k.kind)
UNION ALL
    -- (a2) ticket 227, and the same question one level down. An unpriced class
    --      does not rank NULL -- it falls through to the kind prior and ranks
    --      as an average `hunt`, which is the silence this arm exists to break.
    --      A class added to the catalogue without a number is worth saying out
    --      loud, because the failure it causes looks exactly like working.
    SELECT 'class_has_no_impact_prior', pc.id
      FROM property_classes pc, scheduler_weights w
     WHERE w.active AND NOT (w.class_impact_prior ? pc.id)
UNION ALL
    -- (b) the per-program lane override is reachable. This is the defect the
    --     migration exists to close; asserting it means dropping the view or
    --     reverting the join cannot make overrides silently inert again.
    SELECT 'lane_override_unreachable', p.id::text || ' ' || l.kind
      FROM scheduler_lanes l JOIN programs p ON p.id = l.program_id
     WHERE NOT EXISTS (SELECT 1 FROM effective_lane_capacity c
                        WHERE c.program_id = l.program_id AND c.kind = l.kind
                          AND c.overridden)
UNION ALL
    -- (c) an entitlement above the roster's cap, now for OVERRIDE rows too --
    --     ticket 34's check (e) reads `lane_capacity`, which only ever contains
    --     the NULL-program rows.
    SELECT 'lane_min_above_role_cap',
           coalesce(c.program_id::text, 'default') || ' ' || c.kind
      FROM effective_lane_capacity c WHERE c.min_slots > c.max_slots
UNION ALL
    -- (d) every skill a task requires is registered.
    SELECT 'task_requires_unregistered_skill', t.label || ' ' || s
      FROM tasks t CROSS JOIN LATERAL unnest(t.required_skills) AS s
     WHERE NOT EXISTS (SELECT 1 FROM skills k WHERE k.name = s)
UNION ALL
    -- (e) is gone with ticket 127. It asked whether a `penalised` near-match
    --     named the hypothesis it penalised; `penalised` is no longer an action
    --     `hypothesis_near_matches` accepts, and the CHECK on the column is
    --     what says so now, at write time rather than at check time.
    --
    -- (f) the slate cannot be larger than the table that holds it.
    SELECT 'slate_size_exceeds_task_slate', w.slate_size::text
      FROM scheduler_weights w WHERE w.active AND w.slate_size > 5
UNION ALL
    -- (g) the ranking pass has no clock in it. Decision 12 is a property of the
    --     text, so it is checked against the text: `now()` / `current_timestamp`
    --     inside the three factor functions would make two replays of the same
    --     rows disagree, and nothing else would ever say so. Comments are
    --     stripped first: the first version of this check fired on a comment
    --     explaining why the clock is absent, which is the check calling its
    --     own documentation a defect.
    SELECT 'ranking_factor_reads_the_clock', p.proname
      FROM pg_proc p
     WHERE p.pronamespace = 'public'::regnamespace
       AND p.proname IN ('novelty_for','cost_for','confidence_for')
       AND regexp_replace(p.prosrc, '--[^' || chr(10) || ']*', '', 'g')
           ~* '(now\(\)|current_timestamp|clock_timestamp)'
UNION ALL
    -- (h) the claim takes the lock. Ticket 32 found lane caps unheld without
    --     it, and ticket 08's text still says no lock is needed.
    SELECT 'claim_task_takes_no_advisory_lock', 'claim_task'
      FROM pg_proc p
     WHERE p.pronamespace = 'public'::regnamespace AND p.proname = 'claim_task'
       AND p.prosrc !~ 'pg_advisory_xact_lock'
UNION ALL
    -- (i) no scheduler function is callable by PUBLIC.
    SELECT 'scheduler_function_public_executable', p.proname
      FROM pg_proc p
     WHERE p.pronamespace = 'public'::regnamespace
       AND p.proname IN ('novelty_for','cost_for','confidence_for','ready_for',
                         'cancel_reason_for','rank_pass','rank_candidates',
                         'offer_slate','claim_task','sweep_expired_leases',
                         'scheduler_idle_report')
       AND has_function_privilege('public', p.oid, 'EXECUTE')
$fn$;


DO $$
DECLARE n integer; d text; authz numeric; hdr numeric;
BEGIN
    -- Every class in the catalogue is priced, which is what makes the fall
    -- through to the kind prior unreachable rather than merely unlikely.
    SELECT count(*), string_agg(detail, ', ')
      INTO n, d FROM check_scheduler_closure()
     WHERE problem = 'class_has_no_impact_prior';
    IF n > 0 THEN
        RAISE EXCEPTION 'ticket 227: % class(es) still unpriced: %', n, d;
    END IF;

    -- The function reads the column, asked of the text for arm (g)'s reason: a
    -- table full of correct numbers that nothing reads is the defect this file
    -- is fixing rather than the fix, and it is indistinguishable from the fix
    -- on every database that has no Tasks in it yet.
    IF (SELECT prosrc FROM pg_proc
         WHERE pronamespace = 'public'::regnamespace AND proname = 'value_for')
       NOT LIKE '%class_impact_prior%' THEN
        RAISE EXCEPTION 'ticket 227: value_for does not read class_impact_prior';
    END IF;

    -- And the ordering itself, over the rows that are really there. Skipped on
    -- a database with no `hunt` Task on either class -- which is every fresh
    -- one -- because the two arms above already hold there and this one has
    -- nothing to say.
    SELECT max(value_for(t, w)) FILTER (WHERE h.property_class LIKE 'authorization.%'),
           max(value_for(t, w)) FILTER (WHERE h.property_class = 'transport.header_policy')
      INTO authz, hdr
      FROM tasks t
      JOIN hypotheses h ON h.id = t.hypothesis_id
      CROSS JOIN scheduler_weights w
     WHERE w.active AND t.kind = 'hunt';

    IF authz IS NOT NULL AND hdr IS NOT NULL AND authz <= hdr THEN
        RAISE EXCEPTION
          'ticket 227: an authorization claim still values % against a header policy %',
          authz, hdr;
    END IF;
END $$;
