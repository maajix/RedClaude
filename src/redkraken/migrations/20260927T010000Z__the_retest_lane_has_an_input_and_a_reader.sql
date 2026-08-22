-- ---------------------------------------------------------------------------
-- 20260927T010000Z__the_retest_lane_has_an_input_and_a_reader.sql
--                                                                  (ticket 114)
--
-- "Keep a refutation, notice when the ground moved, say so" is one design in
-- three files, and it was connected at none of the three joints.
--
-- THE MAPPING. `rk2_negative_relevant_deltas` inner-joins
-- `surface_delta_property_classes` on `pc.kind = d.kind AND pc.property_class_id
-- = n.property_class`, so a Property class with no row in that table is a class
-- no Surface delta can ever put back in question. 022 seeded it for the
-- eighteen classes the vocabulary held on 2026-08-13. MEASURED on a scratch
-- database with the whole corpus applied: 57 classes declared, 18 mapped, 39
-- with no row. Every refutation recorded in one of those thirty-nine is
-- permanent whatever changes on the target, and it is permanent silently --
-- the join returns nothing, which reads exactly like a Surface that never
-- moved.
--
-- THE INPUT. `hypothesis_retest_triggers` is 007's other lane, the one that
-- covers a claim with no recorded refutation to make due. Four functions read
-- it -- `cancel_reason_for`, `novelty_for`, `scheduler_idle_report` and
-- `refresh_negative_knowledge`, the last of which UPDATEs `fired_at` and
-- `fingerprint` -- and nothing in this corpus has ever inserted a row.
-- `grep -rn "INSERT INTO hypothesis_retest_triggers"` over the migrations and
-- over `src/redkraken/*.py` returns nothing; the only writer in the tree is a
-- test that writes one by hand and says so in a comment.
--
-- THE OUTPUT. `v_negative_knowledge` and `v_surface_deltas` are both granted to
-- `rk2_runtime` and both read only by `tests/test_database.py`. A grant is a
-- claim that somebody reads it, and neither claim was true.
--
-- THE VERB NOBODY CALLED. The same sentence about grants applies once more, and
-- the other way round. `rk2_hypothesis_negative(uuid)` is executable by
-- `rk2_runtime` and is called from one place in the corpus, the body of the
-- `v_records` view, which `rk2_state` reads. Section 4 takes the runtime's
-- grant away rather than inventing a caller for it.
--
-- WHAT THIS FILE DOES NOT DO. It adds no Property class and no emitter. The
-- thirty-nine are not one bucket and the ticket says which six are left out:
-- `transport.datagram_transport` and `transport.request_framing`, which
-- `transport_makeability` declares `unmakeable`, and
-- `authentication.recovery_flow`, `rate_limiting.per_origin`,
-- `rate_limiting.resource_cost` and `transport.certificate_trust`, which no
-- Playbook emits. A mapping row for a class nothing can raise a claim in would
-- be a rule with no row to apply to, and both halves are already owed --
-- 101 owns the emitters, 100 owns the vocabulary. The remaining thirty-three
-- are classes a shipped Playbook declares as an output, and all thirty-three
-- are mapped below.
-- ---------------------------------------------------------------------------


-- ===========================================================================
-- 1. The thirty-three classes a Playbook emits and no delta reached
-- ===========================================================================

-- 022's own form, kept exactly: an `INSERT ... SELECT` over a `VALUES` list
-- with one note per row saying why that section moving puts that class back in
-- question, joined to the section registry so the twelve kinds stay derived.
-- The alternative is a cross product -- every section against every class --
-- and a cross product would make every delta invalidate every refutation,
-- which is the same as having no mapping at all with more rows.
--
-- Removals still map to nothing, for 022's reason: a subject that is gone tests
-- nothing, and a refutation about it is not made due by its subject
-- disappearing.
--
-- The four sections are what each row is an argument about, so what is in the
-- projection matters more than what the class is called. An endpoint element
-- carries the method, the path template, the auth flag and the request content
-- type; a parameter element carries its route, name, location, value class and
-- whether it reflects; a technology element carries a name and its versions; an
-- identity_relationship element carries a class of holder, the kind of hold and
-- its targets. A row below is a claim that one of those fields moving is news
-- about that Property class.
INSERT INTO surface_delta_property_classes (kind, property_class_id, note)
SELECT k.kind, m.property_class_id, m.note
  FROM (VALUES
    -- A route that appeared, or whose method, path, auth flag or content type
    -- moved, is a new place to ask everything that is settled per route.
    ('endpoint',  'authentication.factor_enforcement',
     'the auth flag is part of the element, so a route that appeared or stopped declaring authentication is a new place a step-up may not be asked for'),
    ('endpoint',  'authentication.federation_trust',
     'an assertion from an external issuer is presented at a route, so a route that appeared is a new place to present one'),
    ('endpoint',  'authorization.channel_subscription',
     'a stream or topic is subscribed to at a route, so a route that appeared is a subscription nobody has been asked who may take out'),
    ('endpoint',  'authorization.edge_rule',
     'the disagreement is about how one path is resolved, so a path template that changed is a new thing for the front end and the application to resolve differently'),
    ('endpoint',  'authorization.parallel_route',
     'a second route over the same records is a route, and one that appeared is the whole of what this claim is about'),
    ('endpoint',  'authorization.state_transition',
     'which operations an object accepts is settled per route, so a route that appeared is a new operation to attempt against a state that should forbid it'),
    ('endpoint',  'business_logic.replay',
     'a single-use action is taken at a route, so a route that appeared or changed method is a new action to take twice'),
    ('endpoint',  'business_logic.workflow_order',
     'a step of a workflow is a route, so a step that appeared is a new place to enter the sequence out of order'),
    ('endpoint',  'information_disclosure.artifact_exposure',
     'a document is served at a route, so a route that appeared may serve one nobody meant to publish'),
    ('endpoint',  'information_disclosure.credential_material',
     'a document the target publishes on purpose is served at a route, so a route that appeared may publish one that carries a credential'),
    ('endpoint',  'information_disclosure.excess_field',
     'what a response carries is settled per route, so a route that appeared or changed its content type may answer with more than the caller is entitled to'),
    ('endpoint',  'information_disclosure.log_record',
     'an activity, audit or trace view is a route, so one that appeared serves request data recorded for somebody'),
    ('endpoint',  'information_disclosure.undeclared_field',
     'the published contract a response is compared against is the route, so a route that changed may have stopped matching its own declaration'),
    ('endpoint',  'information_disclosure.workload_metadata',
     'a response that describes the platform rather than the application is a response to a route, so a route that appeared is a new one to ask'),
    ('endpoint',  'injection.stored_file',
     'how an uploaded file is served back is settled by the route that serves it, so a route that appeared or changed content type is a new way to get one back'),
    ('endpoint',  'session_handling.cross_origin_read',
     'the headers that permit a cross-origin read are settled per route, and 022 already treats a routes header behaviour as part of what a route is'),
    ('endpoint',  'session_handling.fixation',
     'the identifier is meant to change at the route that authenticates, so a route whose auth flag moved is where that swap is decided'),
    ('endpoint',  'session_handling.lifetime',
     'logout and revocation are routes, so a route that appeared or changed is a new way to end a session and a new place to present the old token afterwards'),
    -- A parameter is an input, and an input is what a caller controls.
    ('parameter', 'authorization.state_transition',
     'an identifier parameter is what names the object whose state the check is about'),
    ('parameter', 'business_logic.quantity_or_price',
     'an amount, price, quota or entitlement is submitted as an input, so a parameter that appeared or whose value class moved is a new number to push past what the rules allow'),
    ('parameter', 'business_logic.replay',
     'the token that makes an action single-use is an input, so a parameter that appeared or changed is a new one to send twice'),
    ('parameter', 'injection.client_path',
     'the page builds the path of its own request out of an input, so a parameter that appeared is a new way to reach that path'),
    ('parameter', 'injection.foreign_resource',
     'which external host supplies script, style or markup is decided by an input, so a parameter that appeared may decide it'),
    ('parameter', 'injection.formula',
     'an exported document cell is filled from an input, so a parameter that appeared is a new value a spreadsheet may evaluate'),
    ('parameter', 'injection.model_instruction',
     'a language model is handed an input, so a parameter that appeared is a new way to reach it with instructions'),
    ('parameter', 'injection.object_graph',
     'which type a route reconstructs is decided by an input, so a parameter that appeared or whose value class moved may decide it'),
    ('parameter', 'injection.parameter_precedence',
     'the disagreement is about one name occurring twice, so a parameter that appeared or moved location is a new name for two components to resolve differently'),
    ('parameter', 'injection.query_field',
     'which stored field or relation a query filters, orders or returns is decided by an input, so a parameter that appeared may decide it'),
    ('parameter', 'injection.query_operator',
     'an operator reaches the query as an input, so a parameter that appeared or whose value class moved is a new way to send one'),
    ('parameter', 'injection.stored_file',
     'the name a caller gives an uploaded file is an input, so a parameter that appeared is a new name to give one'),
    ('parameter', 'injection.url_authority',
     'the URL whose authority is validated is an input, so a parameter that appeared may carry one'),
    -- A stack that moved is the closest thing this schema has to a deploy, and
    -- it is where every default lives.
    ('technology', 'authentication.federation_trust',
     'the library that validates an external issuers assertion is in the stack, so a version that moved is a validator that moved'),
    ('technology', 'authorization.edge_rule',
     'the front end that enforces the rule is a stack element, and a proxy or gateway version that moved may resolve a path differently from the application behind it'),
    ('technology', 'authorization.parallel_route',
     'the platform that ships a second route over the same records is in the stack, so a platform that moved may have shipped another'),
    ('technology', 'information_disclosure.cached_response',
     'the cache and the key it stores under are the front ends and the frameworks, so a stack that moved moves what is stored and under what key'),
    ('technology', 'information_disclosure.client_storage',
     'where page script keeps a credential is the client frameworks default, and defaults move with versions'),
    ('technology', 'information_disclosure.dependency_manifest',
     'a manifest published beside a bundle is produced by the build the stack does, so a stack that moved may publish a different one'),
    ('technology', 'information_disclosure.workload_metadata',
     'what a platform adds to a response about itself is the platforms, so a platform that moved moves it'),
    ('technology', 'injection.client_channel',
     'the pages own message and event handling is the client frameworks, so a framework that moved moves the sinks that handling reaches'),
    ('technology', 'injection.foreign_resource',
     'which hosts a page may load script from is settled by the framework and by the header policy, and both move with the stack'),
    ('technology', 'injection.model_instruction',
     'the model and the client that calls it are stack elements, so a version that moved may act on instructions the last one ignored'),
    ('technology', 'injection.object_graph',
     'deserialisation is the frameworks, and which types it will reconstruct is the whole of what this claim is about'),
    ('technology', 'injection.parameter_precedence',
     'two components resolving one name differently is a fact about which two components, so a stack that moved is a new pair'),
    ('technology', 'session_handling.cross_origin_read',
     'cross-origin response headers are usually the servers defaults, and defaults move with versions'),
    ('technology', 'session_handling.fixation',
     'the session identifier is minted and rotated by the framework, so a framework that moved may have stopped rotating it'),
    ('technology', 'session_handling.lifetime',
     'expiry, logout and revocation are the session stores, and a store that moved moves all three'),
    ('technology', 'transport.tls_configuration',
     'the protocols and ciphers offered are the servers, so a server version that moved moves what it will negotiate'),
    -- A new class of Identity is a new pair to ask every entitlement question
    -- about, which is 022's own argument for the four rows it already holds.
    ('identity_relationship', 'authorization.channel_subscription',
     'a new class of holder is a new caller to ask which streams and topics it may subscribe to'),
    ('identity_relationship', 'information_disclosure.excess_field',
     'a new class of holder is a new entitlement to compare a response against'),
    ('identity_relationship', 'information_disclosure.log_record',
     'a new holder is a new pair for every question about whose recorded activity one caller can read')
  ) AS m(prefix, property_class_id, note)
  JOIN surface_projection_sections s ON s.delta_prefix = m.prefix
  JOIN surface_delta_kinds k ON k.section = s.section AND k.change IN ('added','changed');


-- ===========================================================================
-- 2. The writer 007 wrote four readers for
-- ===========================================================================

-- What a watch is for, which is the half of the retest lane
-- `refresh_negative_knowledge` step (1) does not cover. Step (1) walks
-- `negative_knowledge`, and `negative_knowledge` holds refutations alone: both
-- doors into `refuted` write a record through `settle_negative_knowledge`, and
-- nothing else in the corpus writes that table. So a claim that came to rest at
-- `supported` or at `inconclusive` has no record, is asked by no relevance
-- query, and is held down forever by `cancel_reason_for` answering `answered`
-- and `novelty_for` scoring it 0. 007's watch row is the vocabulary for exactly
-- that claim and it had no writer.
--
-- Only those two statuses, and the exclusion of `refuted` is the point rather
-- than an economy. A refutation is made due by a delta of a class the mapping
-- above says bears on it; a watch fires on any change to the Application at
-- all. Arming one on a refuted claim would put the coarse answer in front of
-- the precise one and make section 1 of this file decorative.
--
-- `superseded_by IS NULL`, because a claim a later one replaced is not a
-- question this Program still has. `cancel_reason_for` answers `superseded`
-- before it looks at anything else, so a watch on one would fire, write a
-- transition and reopen a claim nothing would then run.
--
-- The kind is `response_fingerprint_changed` and it is the only one of the four
-- this row can honestly carry. 007 wrote four words before 022 existed;
-- 022 gave an Application one fingerprint over all four sections of its
-- projection, so a single watch cannot tell a new deploy from a new parameter
-- from a new Identity class -- it can only say that the value it was armed at
-- is no longer the value. That is what `response_fingerprint_changed` says, and
-- no reader branches on the column: all four readers ask for `fired_at`,
-- `watched_entity_id` and `fingerprint` and none of them asks for `kind`.
--
-- The unique key is (hypothesis_id, kind, watched_entity_id), so one word per
-- claim per Application is also one row, and `ON CONFLICT DO NOTHING` is what
-- makes calling this on every pass free.
CREATE FUNCTION arm_retest_watches() RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p           uuid   := rk2_program_required();
    n_armed     bigint := 0;
    n_watching  bigint := 0;
    n_unwatched bigint := 0;
BEGIN
    -- An inner LATERAL join on `rk2_current_fingerprint`, which is what carries
    -- both guards the consumer needs. A claim whose subject belongs to no
    -- Application -- an Identity, a Host, a Service -- gets no row, because
    -- `rk2_application_of` returns null for it and a watch on nothing is what
    -- `refresh_negative_knowledge` already counts as `watches_unwatchable`. A
    -- claim on an Application this Program has never fingerprinted gets no row
    -- either: the fingerprint stamped here is the comparison, and a watch armed
    -- at null would report the FIRST fingerprint as a change, which is a
    -- Surface arriving rather than a Surface moving.
    WITH armed AS (
        INSERT INTO hypothesis_retest_triggers
            (hypothesis_id, kind, watched_entity_id, fingerprint)
        SELECT h.id, 'response_fingerprint_changed', a.app, cur.fingerprint
          FROM hypotheses h
          CROSS JOIN LATERAL (SELECT rk2_application_of(h.subject_entity_id) AS app) a
          JOIN LATERAL rk2_current_fingerprint(a.app) cur ON true
         WHERE h.program_id = p
           AND h.status IN ('supported', 'inconclusive')
           AND h.superseded_by IS NULL
        ON CONFLICT (hypothesis_id, kind, watched_entity_id) DO NOTHING
        RETURNING 1)
    SELECT count(*) INTO n_armed FROM armed;

    SELECT count(*) INTO n_watching
      FROM hypothesis_retest_triggers x
     WHERE x.program_id = p AND x.fired_at IS NULL;

    -- The other half of the same answer, and the one nothing else reports: a
    -- claim this Program has come to rest on that nothing is watching. Every
    -- row of it is a question that will never be re-asked however far the
    -- target moves, and the two ways to be one are the two guards above -- a
    -- subject that belongs to no Application, and an Application whose Surface
    -- has never been fingerprinted. `refresh_negative_knowledge` counts the
    -- watches it cannot compare; this counts the claims that have none.
    SELECT count(*) INTO n_unwatched
      FROM hypotheses h
     WHERE h.program_id = p
       AND h.status IN ('supported', 'inconclusive')
       AND h.superseded_by IS NULL
       AND NOT EXISTS (SELECT 1 FROM hypothesis_retest_triggers x
                        WHERE x.hypothesis_id = h.id);

    -- No Event. A watch that has been armed has decided nothing: no status
    -- moved, no work was suppressed and nothing was made due. The Event worth
    -- having is the one `note_retest_due` already writes on the pass where the
    -- watch fires, and a second one here would put a row on the log for every
    -- claim of every pass that changed nothing.
    RETURN jsonb_build_object(
        'armed', n_armed,
        'watching', n_watching,
        'unwatched', n_unwatched);
END $fn$;

COMMENT ON FUNCTION arm_retest_watches() IS
 'Arm 007 watch rows for this Program: one per settled claim per Application, '
 'stamped with the fingerprint the claim came to rest at. Only `supported` and '
 '`inconclusive`, because a refuted claim is made due by the class mapping '
 'instead. Idempotent -- a claim already watched is left alone, fired or not.';

REVOKE ALL ON FUNCTION arm_retest_watches() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION arm_retest_watches() TO rk2_runtime;

-- 66's registry rather than the grant on its own: `apply_runtime_grants` grants
-- what this table names and `check_runtime_privileges` fails on anything the
-- runtime holds beyond it, so a verb with no row here is a verb the next
-- finalizer takes back.
INSERT INTO runtime_verb_surface (verb, added_by, note) VALUES
    ('arm_retest_watches()', '114',
     'writes the 007 watch rows four readers ask for and nothing has ever inserted');


-- ===========================================================================
-- 3. The two views say which Program they are about
-- ===========================================================================

-- Both are `security_invoker`, and for `rk2_state` that is the whole of their
-- scoping: the policy on every table under them is `program_id = rk2_program()`.
-- For `rk2_runtime`, which is the role they are granted to, the policy is
-- `USING (true)` -- the runtime reconciles leases and sweeps catalogues for
-- every Program on the machine -- so a runtime reading either view reads every
-- Program at once and has no column to tell them apart with.
--
-- 43 hit this exactly once before and answered it in this shape: it dropped
-- `v_decision_queue` and rebuilt it with `p.slug AS program` because "labels
-- are counted per Program, so `D1` exists in as many Programs as are open, and
-- a queue that did not say which one a question belongs to is a list an
-- operator can act on wrongly by reading it correctly". Every label in these
-- two views has the same property: `hypotheses` and `entities` are unique on
-- (program_id, label) and on nothing narrower.
--
-- The slug and not the id, which is 020's rule 5 unbroken: a `v_` read carries
-- no uuid, and the slug is the same word the operator typed into the
-- configuration this run was started from.

DROP VIEW v_negative_knowledge;

CREATE VIEW v_negative_knowledge WITH (security_invoker = true) AS
SELECT pr.slug                         AS program,
       hy.label                        AS hypothesis,
       hy.status                       AS hypothesis_status,
       rk2_negative_standing(n.id)     AS standing,
       n.basis,
       subj.label                      AS subject,
       n.property_class,
       ia.label                        AS identity_a,
       ib.label                        AS identity_b,
       app.label                       AS application,
       fp.fingerprint                  AS surface_fingerprint,
       te.label                        AS test,
       n.spec_sha256,
       n.outcome                       AS test_outcome,
       n.reason,
       n.settled_at,
       (SELECT coalesce(jsonb_agg(jsonb_build_object(
                            'observation', o.label,
                            'polarity', ev.polarity,
                            'role', ev.role) ORDER BY o.label, ev.role), '[]'::jsonb)
          FROM negative_knowledge_evidence ev
          JOIN observations o ON o.id = ev.observation_id
         WHERE ev.negative_id = n.id)  AS evidence,
       (SELECT jsonb_build_object(
                   'reason', rt.reason,
                   'delta_kind', d.kind,
                   'subject_key', d.subject_key,
                   'reopened', rt.transition_id IS NOT NULL,
                   'became_due_at', rk2_instant(rt.became_due_at))
          FROM negative_knowledge_retests rt
          LEFT JOIN surface_deltas d ON d.id = rt.delta_id
         WHERE rt.negative_id = n.id)  AS retest
  FROM negative_knowledge n
  JOIN programs pr        ON pr.id = n.program_id
  JOIN hypotheses hy      ON hy.id = n.hypothesis_id
  JOIN entities subj      ON subj.id = n.subject_entity_id
  LEFT JOIN entities ia   ON ia.id = n.identity_a_entity_id
  LEFT JOIN entities ib   ON ib.id = n.identity_b_entity_id
  LEFT JOIN entities app  ON app.id = n.application_entity_id
  LEFT JOIN surface_fingerprints fp ON fp.id = n.fingerprint_id
  LEFT JOIN tests te      ON te.id = n.test_id;

COMMENT ON VIEW v_negative_knowledge IS
    'Every kept refutation with the conditions it was settled under, what it is '
    'currently doing, and what made it due if anything has. Named by its '
    'Program, because every other citation in it is a label and labels are '
    'counted per Program.';

GRANT SELECT ON v_negative_knowledge TO rk2_runtime;

DROP VIEW v_surface_deltas;

CREATE VIEW v_surface_deltas WITH (security_invoker = true) AS
SELECT pr.slug             AS program,
       app.label            AS application,
       now_fp.fingerprint   AS fingerprint,
       was_fp.fingerprint   AS previous_fingerprint,
       d.kind,
       k.section,
       k.change,
       subject.label        AS subject,
       d.subject_key,
       d.before_element,
       d.after_element,
       d.detected_at,
       (SELECT coalesce(jsonb_agg(pc.property_class_id ORDER BY pc.property_class_id),
                        '[]'::jsonb)
          FROM surface_delta_property_classes pc
         WHERE pc.kind = d.kind) AS property_classes
  FROM surface_deltas d
  JOIN programs pr ON pr.id = d.program_id
  JOIN surface_delta_kinds k ON k.kind = d.kind
  JOIN entities app ON app.id = d.application_entity_id
  JOIN surface_fingerprints now_fp ON now_fp.id = d.fingerprint_id
  JOIN surface_fingerprints was_fp ON was_fp.id = d.previous_fingerprint_id
  LEFT JOIN entities subject ON subject.id = d.subject_entity_id;

COMMENT ON VIEW v_surface_deltas IS
    'Every recorded Surface delta with its Program, its subject and the Property '
    'classes it puts back in question. Reading it computes nothing.';

GRANT SELECT ON v_surface_deltas TO rk2_runtime;


-- ===========================================================================
-- 4. The projection the runtime was granted and never called
-- ===========================================================================
--
-- `rk2_hypothesis_negative(uuid)` is one claim's Negative knowledge as a hunter
-- may read it, and 034's own comment above it says so: "What a hunter is told,
-- which is deliberately less." The role that executes it is `rk2_state`, inside
-- the `v_records` body, which is where the model meets it. The `rk2_runtime`
-- grant written beside it has never had a caller: the runtime's reader of this
-- lane is `v_negative_knowledge`, a strict superset of the three keys this
-- function builds, and section 3 above is what finally gave that view one.
--
-- The register in `tools/check_wiring.py` books this gap to ticket 114 on the
-- theory that giving the view a reader would reach the function. It cannot: W3
-- follows calls from one function body to another, a view body contributes no
-- edge, and the only call site is a view either way. So the repair is the other
-- one W3 admits -- the runtime does not call the verb, so the runtime stops
-- holding it. `rk2_state` keeps the grant `v_records` needs.
--
-- The registry row goes with the grant. It is one of 066's `66-seed` rows,
-- written because the function was closed to PUBLIC and held by the runtime,
-- and arm 5 of `check_runtime_privileges()` fails on a row naming a verb the
-- runtime cannot execute. The count is asserted for the reason 066 asserts its
-- own hand-written list: a name that matched nothing would delete nothing and
-- let this file declare itself finished.

REVOKE EXECUTE ON FUNCTION rk2_hypothesis_negative(uuid) FROM rk2_runtime;

DO $$
DECLARE n integer;
BEGIN
    DELETE FROM runtime_verb_surface WHERE verb = 'rk2_hypothesis_negative(uuid)';
    GET DIAGNOSTICS n = ROW_COUNT;
    IF n <> 1 THEN
        RAISE EXCEPTION
            'ticket 114: % runtime_verb_surface rows name rk2_hypothesis_negative(uuid), expected 1', n;
    END IF;
END $$;


-- ===========================================================================
-- 5. What this migration claims, asserted
-- ===========================================================================

DO $$
DECLARE
    n_unmapped integer;
    unmapped   text;
BEGIN
    -- Criterion 1 as a query. Every class a Playbook declares as an output has
    -- a row, and the six that do not are named here so that a seventh arriving
    -- with no emitter fails this migration rather than joining them quietly.
    SELECT count(*), string_agg(p.id, ', ' ORDER BY p.id)
      INTO n_unmapped, unmapped
      FROM property_classes p
     WHERE EXISTS (SELECT 1 FROM playbook_outputs o WHERE o.property_class = p.id)
       AND NOT EXISTS (SELECT 1 FROM surface_delta_property_classes m
                        WHERE m.property_class_id = p.id);
    IF n_unmapped > 0 THEN
        RAISE EXCEPTION 'ticket 114: % emitted Property class(es) no delta reaches: %',
            n_unmapped, unmapped;
    END IF;

    -- And the converse, which is the failure a cross product would produce: a
    -- `_removed` kind that puts something back in question. 022 decided
    -- removals map to nothing, and this file adds fifty rows to the same table
    -- through the same join, so the decision is worth re-asserting after them.
    IF EXISTS (SELECT 1 FROM surface_delta_property_classes m
                JOIN surface_delta_kinds k ON k.kind = m.kind
               WHERE k.change = 'removed') THEN
        RAISE EXCEPTION 'ticket 114: a removal was mapped to a Property class';
    END IF;

    -- The input. The verb exists, the runtime may run it, and the runtime may
    -- write the table it writes -- the last because the function is security
    -- invoker like every other verb in this lane, so the grant on the function
    -- is only half of being able to call it.
    IF NOT EXISTS (
        SELECT 1 FROM pg_proc
         WHERE proname = 'arm_retest_watches'
           AND has_function_privilege('rk2_runtime', oid, 'EXECUTE')
    ) OR NOT has_table_privilege('rk2_runtime', 'hypothesis_retest_triggers', 'INSERT') THEN
        RAISE EXCEPTION 'ticket 114: the retest lane still has no writer that can write';
    END IF;

    -- The word the writer uses is still a word the column accepts. The check
    -- constraint is 007's and this file is its first writer, so a later
    -- migration narrowing that vocabulary would cost nothing yesterday and
    -- would silently stop every watch being armed today.
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conrelid = 'hypothesis_retest_triggers'::regclass
           AND conname = 'hypothesis_retest_triggers_kind_check'
           AND pg_get_constraintdef(oid) LIKE '%response_fingerprint_changed%'
    ) THEN
        RAISE EXCEPTION 'ticket 114: the watch vocabulary no longer holds the kind this file writes';
    END IF;

    -- The output. Both views name their Program and both are still readable by
    -- the role that reads them, which a DROP and CREATE is exactly the way to
    -- lose.
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'v_negative_knowledge' AND column_name = 'program'
    ) OR NOT EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'v_surface_deltas' AND column_name = 'program'
    ) THEN
        RAISE EXCEPTION 'ticket 114: a view a runtime reads still cannot say which Program it is about';
    END IF;

    IF NOT has_table_privilege('rk2_runtime', 'v_negative_knowledge', 'SELECT')
       OR NOT has_table_privilege('rk2_runtime', 'v_surface_deltas', 'SELECT') THEN
        RAISE EXCEPTION 'ticket 114: the reader lost the grant it was written for';
    END IF;

    -- Section 4 both ways. The runtime no longer holds the projection it never
    -- called, and the model still does, because `v_records` is security invoker
    -- and would start raising for every reader of it if this went one grant too
    -- far.
    IF EXISTS (SELECT 1 FROM pg_proc
                WHERE proname = 'rk2_hypothesis_negative'
                  AND has_function_privilege('rk2_runtime', oid, 'EXECUTE')) THEN
        RAISE EXCEPTION 'ticket 114: the runtime still holds a verb it never calls';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_proc
                    WHERE proname = 'rk2_hypothesis_negative'
                      AND has_function_privilege('rk2_state', oid, 'EXECUTE')) THEN
        RAISE EXCEPTION 'ticket 114: the revoke took the grant `v_records` reads with';
    END IF;
END $$;
