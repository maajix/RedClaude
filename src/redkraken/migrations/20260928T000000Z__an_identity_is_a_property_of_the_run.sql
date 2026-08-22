-- ---------------------------------------------------------------------------
-- 20260928T000000Z__an_identity_is_a_property_of_the_run.sql
--                                                                   (ticket 97)
--
-- `identity_slot` is a property of the Tool run, never an argument, and
-- `mcp__rk2__http_request` goes on refusing it. Ticket 97 settles that, and
-- this file is the half of the settlement a reader meets in the database.
--
-- The reason is not taste, and it is not one layer's opinion. Four things are
-- true of this schema today, each of which would have to be undone before a
-- per-call identity could mean anything:
--
-- 1. `resolve_egress_identity(p_capability)` takes a capability and reads
--    `tool_runs.args ->> 'identity_slot'` for the run that capability resolves
--    to, then requires a live, unreleased, unexpired lease held by that agent
--    run (20260811T150000Z:436-453). `authorize_identity_egress_request` takes
--    the capability, the method, the protocol, the host, the port, two paths
--    and a body flag. Neither has a parameter an identity could arrive in.
-- 2. `rk2_proxy` holds no privilege of any kind on `tool_runs`. INSERT and
--    UPDATE belong to `rk2_owner` and `rk2_runtime`. So the one process that
--    sees an agent's request could not write a slot down even if it were told
--    one.
-- 3. `enforce_allowed_receipt_capability` re-checks the same key a third time
--    when the Receipt is written (20260811T150000Z:757-780), against the same
--    `tr.args ->> 'identity_slot'`.
-- 4. `net_borrowed_identity` (0026:266-268) escalates any non-empty slot to
--    `approval_required` asking `credential_needed`, and it is assessed against
--    the digest `current_request_digest` builds from `tool_runs` alone --
--    `gate_tool_call(uuid)` and `current_request_digest(uuid)` take a Tool run
--    id and nothing else. A slot named after that row was written would not
--    reach the digest, would not move the class, and would not move
--    `equivalence_key`, which is what a human's approval is keyed on. The whole
--    effect of an argument would be a model acting as a real account holder
--    outside the answer a person gave, which is the one thing the control
--    surface exists to prevent.
--
-- And one Tool run is many exchanges. `receipts.tool_run_id` carries a plain
-- foreign key with no unique index over it, so N Receipts share one row and
-- `resolve_egress_identity` gives every one of them the same slot. That is what
-- "property of the run" means concretely: an argument would be a per-call
-- answer to a question the row answers once, for every subresource and every
-- redirect that shares the capability.
--
-- WHAT THIS FILE CHANGES, AND WHAT IT REFUSES TO CHANGE.
--
-- No table, no function body, no row. Two `COMMENT ON` statements put the
-- settlement where `\df+` prints it, on the two functions a reader following
-- `identity_slot` through the door arrives at and which have carried no comment
-- since they were written. Everything else here is assertion: this is a
-- decision, and the only way a decision recorded in a comment goes wrong is the
-- schema under it moving, so each clause is asked of the catalogue rather than
-- asserted in prose. A file that applies is a file whose sentences were true of
-- the database it applied to.
--
-- The naming hazard is asserted here for the same reason. The served tool is
-- `mcp__rk2__http_request` and the Tool run is opened under
-- `mcp__rk2__net_request`; every `net_*` rule in `call_risk_rules` is written
-- against the second name, so a later ticket that opened a Tool run per agent
-- call under the served name would stop all three firing and nothing would
-- fail. Section 3 makes the arrangement explicit rather than incidental.
--
-- Depends on 0026 (the digest, the escalation table and the rule),
-- 20260811T150000Z (the two functions commented below), 20260814T020000Z and
-- 20260924T000000Z (the current `gate_tool_call` and `canonical_request`) and
-- 0038 (`receipts.tool_run_id`). A new file rather than an edit to any of them:
-- a recorded migration whose file has changed is schema drift and `rk db
-- migrate` refuses the whole corpus for it.
-- ---------------------------------------------------------------------------


-- ===========================================================================
-- 1. The settlement, where a reader of the door's own functions finds it
-- ===========================================================================

-- Both functions are on the path an agent's request takes and neither has ever
-- said where the Identity comes from. A reader who has just been told by a
-- Playbook to "set `identity_slot`" and greps for the name lands on
-- `resolve_egress_identity` first, so this is the sentence that has to answer.
COMMENT ON FUNCTION resolve_egress_identity(text) IS
  'The Identity a capability spends, resolved from the Tool run it was minted '
  'against. The slot is read out of tool_runs.args and is a property of that '
  'row: the runtime writes it when it opens the run, one run serves every '
  'subresource and redirect the capability admits, and there is no parameter '
  'here and no argument on mcp__rk2__http_request through which a call could '
  'choose a different one. Ticket 97 settled that and it is not a gap. A '
  'reading that needs two Identities is two Tasks. Resolving to nothing is an '
  'answer: a run opened with an empty slot acts as no Identity at all, and a '
  'named slot with no live lease held by this agent run is refused rather than '
  'sent anonymously.';

COMMENT ON FUNCTION authorize_identity_egress_request(text, text, text, text, integer, text, text, boolean) IS
  'The door''s own authorizer: resolves the Identity the capability''s Tool run '
  'selected, then decides the request under it. The Identity is not among the '
  'arguments and will not be. What arrives at the door is a method and an '
  'address, decided against live policy; who the request is made as was decided '
  'when the Tool run was opened, was assessed by net_borrowed_identity against '
  'the digest built from that row, and may already have been answered by a '
  'person. The body flag is carried through untouched -- what a body is allowed '
  'to be is one decision, and it is taken in authorize_egress_request beside '
  'the method binding it mirrors.';


-- ===========================================================================
-- 2. The four layers, asked of the catalogue rather than asserted
-- ===========================================================================

-- Each arm is one clause of the sentence above. A file that stops applying here
-- is a file whose settlement somebody has begun to undo, and the failure names
-- which of the four moved.
DO $$
DECLARE
    v_empty  jsonb;
    v_named  jsonb;
    v_args   text;
BEGIN
    -- Layer 1: no parameter an identity could arrive in, on either function.
    -- Matched on the argument list rather than on a count, because a widened
    -- signature is exactly the change this asserts against and a count would
    -- pass a rename.
    FOR v_args IN
        SELECT p.proname || '(' || pg_get_function_arguments(p.oid) || ')'
          FROM pg_proc p
         WHERE p.pronamespace = 'public'::regnamespace
           AND p.proname IN ('resolve_egress_identity',
                             'authorize_identity_egress_request',
                             'gate_tool_call',
                             'current_request_digest')
           AND pg_get_function_arguments(p.oid) ~ 'identity'
    LOOP
        RAISE EXCEPTION 'the door takes an identity as an argument: %', v_args
          USING DETAIL = 'ticket 97 settled that the slot is a property of the '
                         'Tool run; a parameter here is the other decision',
                ERRCODE = '23514';
    END LOOP;

    -- Layer 2: the process that sees the agent's request cannot write the row
    -- the slot lives in. Without this the parameter above would only be a
    -- missing convenience rather than a missing capability.
    IF EXISTS (
        SELECT 1 FROM information_schema.table_privileges
         WHERE table_name = 'tool_runs'
           AND grantee = 'rk2_proxy'
           AND privilege_type IN ('INSERT', 'UPDATE')) THEN
        RAISE EXCEPTION 'rk2_proxy can write tool_runs, so the door could name its own Identity'
          USING ERRCODE = '23514';
    END IF;

    -- Layer 3: the Receipt trigger reads the same key, so a slot that somehow
    -- changed between the gate and the wire would be caught when the record was
    -- written. Asserted on the body because the guard is what makes the other
    -- three a fence rather than three separate agreements.
    IF NOT EXISTS (
        SELECT 1 FROM pg_proc p
         WHERE p.pronamespace = 'public'::regnamespace
           AND p.proname = 'enforce_allowed_receipt_capability'
           AND p.prosrc LIKE '%identity_slot%') THEN
        RAISE EXCEPTION 'the receipt fence no longer re-checks the Tool run''s identity_slot'
          USING ERRCODE = '23514';
    END IF;

    -- Layer 4: the escalation the argument would step around, measured rather
    -- than cited. Two digests over one request, differing in the slot alone.
    v_empty := canonical_request(
        'mcp__rk2__net_request',
        '{"url":"https://ticket97.invalid/a","method":"GET",'
        '"identity_slot":"","body_allowed":false}'::jsonb, 'T97');
    v_named := canonical_request(
        'mcp__rk2__net_request',
        '{"url":"https://ticket97.invalid/a","method":"GET",'
        '"identity_slot":"member-a","body_allowed":false}'::jsonb, 'T97');

    IF assess_call_risk('mcp__rk2__net_request', v_empty) ->> 'risk_class'
       <> 'constrained' THEN
        RAISE EXCEPTION 'a request naming no Identity no longer rests on the static floor'
          USING ERRCODE = '23514';
    END IF;
    IF assess_call_risk('mcp__rk2__net_request', v_named)
       IS DISTINCT FROM jsonb_build_object(
           'risk_class', 'approval_required',
           'rule', 'call_risk_rules:net_borrowed_identity',
           'question_code', 'credential_needed') THEN
        RAISE EXCEPTION 'naming an Identity no longer asks a person: %',
                        assess_call_risk('mcp__rk2__net_request', v_named)
          USING ERRCODE = '23514';
    END IF;

    -- And the key the answer is filed under, which is the half that makes the
    -- escalation binding. Two requests that differ only in the slot must not
    -- share an approval, or a person who admitted the anonymous read would have
    -- admitted the authenticated one.
    IF equivalence_key(v_empty) = equivalence_key(v_named) THEN
        RAISE EXCEPTION 'an approval given for an anonymous read covers the same read under an Identity'
          USING ERRCODE = '23514';
    END IF;
END $$;


-- ===========================================================================
-- 3. One run, many exchanges -- and the two names that are not one name
-- ===========================================================================

-- The concrete form of "property of the run". If a Receipt were one-to-one with
-- a Tool run, "the slot the run was opened with" and "the slot this call used"
-- would be the same sentence and the settlement would be about nothing.
DO $$
DECLARE v_rules text[];
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_index i
         WHERE i.indrelid = 'receipts'::regclass
           AND i.indisunique
           AND pg_get_indexdef(i.indexrelid) LIKE '%tool_run_id%') THEN
        RAISE EXCEPTION 'a Tool run now carries at most one Receipt'
          USING DETAIL = 'the slot being a property of the run only says '
                         'something while one run answers many exchanges',
                ERRCODE = '23514';
    END IF;

    -- The naming hazard, made a property instead of a warning. Every rule whose
    -- id begins `net_` is written against the tool the RUNTIME opens, not the
    -- tool the model calls, and the two are spelled differently. A future
    -- ticket that opened a Tool run per agent call under `mcp__rk2__http_request`
    -- would leave these rules matching nothing, and the static floor would keep
    -- covering the call through the `mcp__rk2__*` glob -- so the escalations
    -- would go quiet and no check would fail. This one would.
    SELECT array_agg(r.rule_id ORDER BY r.rule_id) INTO v_rules
      FROM call_risk_rules r
     WHERE r.rule_id LIKE 'net\_%'
       AND r.tool_pattern <> 'mcp__rk2__net_request';
    IF v_rules IS NOT NULL THEN
        RAISE EXCEPTION 'a net_* risk rule is written against a tool other than mcp__rk2__net_request: %',
                        v_rules
          USING ERRCODE = '23514';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM call_risk_rules WHERE rule_id = 'net_borrowed_identity') THEN
        RAISE EXCEPTION 'the rule this settlement rests on is not in the escalation table'
          USING ERRCODE = '23514';
    END IF;
END $$;
