-- ===========================================================================
-- Production harness 29 -- the operator answers, and the work resumes
-- ===========================================================================
-- Ticket 11 built the door: a gate verdict of `ask` files a question, ends the
-- run and parks the Task. Ticket 13 built the Halt. What neither built is the
-- other side of the same transaction -- what an operator may do with the
-- question once it is filed, and what has to be true again before the work it
-- parked is allowed to move.
--
-- Six things were missing, and each one is a criterion of this ticket:
--
--   1. The five question codes were two independent CHECK lists, one on
--      `pending_decisions` and one on `call_risk_rules`. A code added to a rule
--      and not to the decision is a gate that files a question the table
--      refuses to hold.
--   2. Parking released the identity leases by hand -- ticket 24 has one verb
--      for both halves of a Lease and this predates it -- and closed only the
--      Tool run that asked. A sibling receipt of the same Agent run stayed
--      `running`, which is a live capability belonging to a run that has ended.
--   3. Nothing had to change: a parked Task is not `pending`, so `claimable_for`
--      already refuses it and offers its Program's others. This file asserts it
--      rather than implementing it.
--   4. `answer_decision` was EXECUTE-able by `rk2_runtime`. The write was still
--      refused -- `assert_actor_kind_authentic` will not let a non-operator
--      session claim `actor_kind = 'human'` -- but a control verb whose only
--      guard is a trigger three tables away is a guard nobody reads. And there
--      was no third verb at all: an operator could approve or deny a question
--      and could not withdraw one.
--   5. An approval made the Task ready with no second look. A question filed
--      under one scope version and answered a day later was answered about a
--      request whose classification may have changed underneath it.
--   6. The operator's own words went into `pending_decisions.answer`, which
--      `rk2_runtime` could read, and into the `decision.answered` payload
--      unredacted. Free text an operator writes for one question must not
--      become context a model is later handed.


-- ---------------------------------------------------------------------------
-- 1. The question codes are rows, and both writers point at them
-- ---------------------------------------------------------------------------
-- Two CHECK lists spelling the same five words is one vocabulary maintained in
-- two places, and the migration that adds the sixth word to one of them is the
-- migration that breaks the other. A registry with a foreign key from each
-- writer makes that impossible to get wrong and makes the vocabulary readable:
-- an operator answering D7 can ask the database what `credential_needed` means
-- instead of reading the rule that raised it.
CREATE TABLE decision_question_codes (
    question_code text PRIMARY KEY,
    meaning       text NOT NULL,
    asked_when    text NOT NULL,
    owner_ticket  text NOT NULL
);

COMMENT ON TABLE decision_question_codes IS
    'The stable vocabulary a parked question is filed under. Referenced by '
    '`call_risk_rules.question_code` (what a rule asks) and by '
    '`pending_decisions.question_code` (what was asked), so the two cannot '
    'drift. Changed only by migration: a code is a promise to whatever is '
    'reading the queue, and an operator console keyed on one of these must not '
    'find it renamed underneath it.';

INSERT INTO decision_question_codes (question_code, meaning, asked_when, owner_ticket) VALUES
    ('scope_ambiguous', 'the request addresses something the scope document does not clearly admit',
     'the resolved scope class of the host is not a target and not egress support', '11'),
    ('destructive_action', 'the request may change state at the target rather than read it',
     'an HTTP method outside the safe set', '11'),
    ('third_party_impact', 'the request may reach or affect somebody who is not the Program''s counterparty',
     'a tool whose blast radius is not confined to the subject', '11'),
    ('credential_needed', 'the request would be made under a borrowed identity',
     'an identity slot the autonomous policy does not grant unattended', '11'),
    ('policy_unclear', 'the static floor asks, and no rule named a better reason',
     'the tool''s own risk class is `approval_required` with no escalation rule fired', '11');

ALTER TABLE pending_decisions DROP CONSTRAINT pending_decisions_question_code_check;
ALTER TABLE pending_decisions ADD CONSTRAINT pending_decisions_question_code_fkey
    FOREIGN KEY (question_code) REFERENCES decision_question_codes(question_code);

ALTER TABLE call_risk_rules DROP CONSTRAINT call_risk_rules_question_code_check;
ALTER TABLE call_risk_rules ADD CONSTRAINT call_risk_rules_question_code_fkey
    FOREIGN KEY (question_code) REFERENCES decision_question_codes(question_code);

-- `assess_call_risk` names one code that no rule carries: the static floor's
-- own `policy_unclear`, written in the function body. The foreign keys above
-- cannot reach a literal, so the registry is asked here instead -- otherwise a
-- migration that renamed that code would leave the floor filing a question the
-- table now refuses, and would find out at the first `ask` in production.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM decision_question_codes
                    WHERE question_code = (assess_call_risk('mcp__rk2__run_tool',
                                           '{"tool_name":"probe"}'::jsonb)) ->> 'question_code') THEN
        RAISE EXCEPTION 'the static floor files a question code the registry does not hold';
    END IF;
END $$;

INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
    ('decision_question_codes', 'reference',
     'the question vocabulary, changed only by migration', '29');

-- Global for `call_risk_rules`' own reason, one step further back: a per-program
-- copy of the vocabulary would let a program mean something different by
-- `credential_needed` than the rule that files it does.
INSERT INTO program_global_tables (table_name, reason) VALUES
    ('decision_question_codes',
     'the question vocabulary the escalation policy files under; a per-program '
     'copy would let one program redefine a word the operator answers by');

-- The runtime's read comes from the schema's default privileges. `rk2_human` is
-- granted here because an operator answering D7 should be able to ask the
-- database what the code means. `rk2_state` is deliberately absent:
-- `call_risk_rules` is off the agent read surface for the reason ticket 13
-- gives -- a model that can enumerate what raises a question is a model that
-- can shape a request around it -- and the codes those rules file under are the
-- same table under another name.
GRANT SELECT ON decision_question_codes TO rk2_human;


-- ---------------------------------------------------------------------------
-- 2. One request, canonicalised in one place
-- ---------------------------------------------------------------------------
-- `gate_tool_call` built the digest inline. Section 5 has to build the same
-- digest again -- that is what revalidating an answer against the current
-- configuration means -- and a second copy of the canonicalisation would be a
-- second answer to "what is this request", which is precisely the question the
-- equivalence key exists to have one answer to.
CREATE FUNCTION current_request_digest(p_tool_run_id uuid) RETURNS jsonb
LANGUAGE plpgsql STABLE AS $fn$
DECLARE
    tr     tool_runs%ROWTYPE;
    digest jsonb;
    raw    text[];
    sclass text;
BEGIN
    SELECT * INTO tr FROM tool_runs WHERE id = p_tool_run_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'no tool_run %', p_tool_run_id; END IF;

    digest := canonical_request(tr.tool, coalesce(tr.args,'{}'::jsonb), tr.label);
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
    RETURN digest;
END $fn$;

COMMENT ON FUNCTION current_request_digest(uuid) IS
    'What this Tool run''s request canonicalises to under the configuration in '
    'force now. The gate asks it before the call and the revalidation asks it '
    'again before an answer is allowed to release the Task, so "the same '
    'request" means the same thing at both ends of a question a person took '
    'time to answer.';

CREATE OR REPLACE FUNCTION gate_tool_call(p_tool_run_id uuid) RETURNS jsonb
LANGUAGE plpgsql AS $fn$
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

    -- rule 5: a live grant answers the question instead of re-asking it
    SELECT d.label INTO grant_l
      FROM pending_decisions d
     WHERE d.program_id = tr.program_id
       AND d.status = 'approved'
       AND d.equivalence_key = equivalence_key(digest)
       AND d.grant_expires_at IS NOT NULL
       AND d.grant_expires_at > now()
     ORDER BY d.grant_expires_at DESC LIMIT 1;

    RETURN verdict || jsonb_build_object(
        'decision', CASE WHEN grant_l IS NULL THEN 'ask' ELSE 'allow' END,
        'digest', digest, 'approval', grant_l);
END $fn$;


-- ---------------------------------------------------------------------------
-- 3. Parking releases everything the run was holding
-- ---------------------------------------------------------------------------
-- Criterion 2. Two of the three were already here; the parts this replaces are
-- the two that were not.
--
-- `release_leases` is ticket 24's single statement of "this run holds nothing
-- now", and it moves both halves of the Lease on one reading of the clock. The
-- hand-rolled `UPDATE identity_leases` this drops moved one half and left the
-- Task's `lease_expires_at` to a second statement below it, which is the two
-- clocks ticket 24 exists to refuse. It needs a bound Program and gets one:
-- `park_for_human` reaches here only through `authorize_tool_run`, which
-- refuses any Tool run whose `program_id` is not `rk2_program()`.
--
-- The sibling receipts are the other half. A run may have more than one Tool
-- run open -- a background exchange, a second call in flight -- and closing the
-- Agent run without closing them left a `running` receipt whose capability
-- still resolved, attributed to a run that had ended. `sweep_open_receipts`
-- says the same sentence Program-wide when a harness restarts; here it is said
-- about one run, at the moment that run stops.
CREATE OR REPLACE FUNCTION park_authorized_tool_run(
    p_tool_run_id uuid,
    p_ttl interval DEFAULT interval '4 hours'
) RETURNS text SECURITY DEFINER LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $fn$
DECLARE
    tr     tool_runs%ROWTYPE;
    g      jsonb;
    d      pending_decisions%ROWTYPE;
    n_hyp  bigint;
BEGIN
    PERFORM set_actor('runtime');
    SELECT * INTO tr FROM tool_runs WHERE id = p_tool_run_id;
    g := gate_tool_call(p_tool_run_id);

    IF g ->> 'decision' <> 'ask' THEN
        RAISE EXCEPTION 'tool_run % resolves to %/%, not to a human decision',
            tr.label, g ->> 'risk_class', g ->> 'decision'
            USING ERRCODE = '23514',
                  HINT = 'forbidden refuses and autonomous/constrained run; neither parks';
    END IF;

    INSERT INTO pending_decisions
        (program_id, task_id, agent_run_id, tool_run_id, tool, risk_class, risk_rule,
         question_code, request_digest, equivalence_key, question, deadline_at)
    VALUES (tr.program_id, tr.task_id, tr.agent_run_id, tr.id, tr.tool,
            g ->> 'risk_class', g ->> 'rule', g ->> 'question_code', g -> 'digest',
            equivalence_key(g -> 'digest'),
            render_decision_question(g -> 'digest', g ->> 'risk_class', g ->> 'rule'),
            now() + p_ttl)
    RETURNING * INTO d;

    -- the receipt: parked, terminal, and it never resumes -- the session that
    -- opened it is about to end
    UPDATE tool_runs SET status = 'parked', decision = 'deny',
                         decision_reason = 'parked for human decision ' || d.label,
                         pending_decision_id = d.id, closed_by = 'PreToolUse',
                         finished_at = now(), egress_token_sha256 = NULL,
                         risk_class = g ->> 'risk_class'
     WHERE id = tr.id;

    -- and every other receipt the same run had open, for the same reason: the
    -- run that owns them is one statement from over, and a capability that
    -- outlived its holder is the fault this is here to prevent rather than one
    -- to discover later at the door.
    UPDATE tool_runs
       SET status = 'abandoned', finished_at = now(), egress_token_sha256 = NULL,
           hook_error = coalesce(hook_error,
               'the run was parked for human decision ' || d.label
               || ' while this receipt was open; whether the tool ran is unknown')
     WHERE agent_run_id = tr.agent_run_id AND id <> tr.id AND status = 'running';

    -- both halves of the Lease, on one reading of the clock
    PERFORM release_leases(tr.agent_run_id);

    -- the run ends, the lane slot frees
    UPDATE agent_runs SET finished_at = now(), stop_reason = 'parked', result = NULL
     WHERE id = tr.agent_run_id AND finished_at IS NULL;

    UPDATE agent_sessions s SET unbound_at = now()
     WHERE s.agent_run_id = tr.agent_run_id AND s.unbound_at IS NULL;

    -- Ticket 08's parked shape omits the hypothesis, and it must not: `testing`
    -- means a live run is testing it, and after this statement there is no live
    -- run. Same transition `sweep_expired_leases()` makes, for the same reason.
    INSERT INTO hypothesis_transitions
        (program_id, hypothesis_id, from_status, to_status, actor_kind, rationale)
    SELECT tr.program_id, h.id, 'testing', 'testable', 'runtime',
           'parked for human decision ' || d.label
      FROM hypotheses h
      JOIN tasks t ON t.hypothesis_id = h.id
     WHERE t.id = tr.task_id AND h.status = 'testing';
    GET DIAGNOSTICS n_hyp = ROW_COUNT;

    -- attempts NOT incremented: parking is not a failed attempt (ticket 08).
    -- `lease_expires_at` is not cleared here either, and that is the point of
    -- the call above: one verb ends the hold, and this one records the state
    -- the Task is left in.
    UPDATE tasks SET status = 'parked', pending_decision_id = d.id,
                     claimed_at = NULL, priority = NULL
     WHERE id = tr.task_id;

    RETURN d.label;
END $fn$;

COMMENT ON FUNCTION park_authorized_tool_run(uuid, interval) IS
    'The parked shape, in one transaction: the question, the receipt that asked '
    'it, every other receipt the run had open, both halves of the Lease through '
    'ticket 24''s verb, the Agent run, its session binding, the hypothesis it '
    'was testing and the Task. Everything the run was holding is released here, '
    'so what is left waiting is a question and nothing else.';


-- ---------------------------------------------------------------------------
-- 4. What an answer is revalidated against
-- ---------------------------------------------------------------------------
-- Criterion 5. A question is filed at one moment and answered at another, and
-- between them the operator may have edited the scope document, changed the
-- risk policy, halted the Program or closed it. The answer was given about the
-- request as it was classified then; releasing the Task on it means asserting
-- that the classification still holds.
--
-- Read-only and reason-returning rather than raising: the console shows an
-- operator why a question can no longer be approved before they try, and
-- section 5 asks the same function for the same reason. NULL means the answer
-- still describes the request the runtime would make now.
CREATE FUNCTION revalidate_decision(p_label text) RETURNS text
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE
    d     pending_decisions%ROWTYPE;
    now_d jsonb;
    v     jsonb;
BEGIN
    SELECT * INTO d FROM pending_decisions
     WHERE label = p_label AND program_id = rk2_program_required();
    IF NOT FOUND THEN
        RAISE EXCEPTION 'no decision % in the bound Program', p_label
            USING ERRCODE = '23514';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM programs
                    WHERE id = d.program_id AND closed_at IS NULL) THEN
        RETURN 'program_closed';
    END IF;
    IF EXISTS (SELECT 1 FROM program_halts h
                WHERE h.program_id = d.program_id AND h.status = 'halted') THEN
        RETURN 'program_halted';
    END IF;
    -- A question whose Task was abandoned underneath it -- by the deadline
    -- sweep, by a purge of the hypothesis it was testing -- is a question about
    -- work that is over.
    IF d.task_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM tasks t
                        WHERE t.id = d.task_id AND t.status = 'parked'
                          AND t.pending_decision_id = d.id) THEN
        RETURN 'task_no_longer_parked';
    END IF;

    now_d := current_request_digest(d.tool_run_id);
    IF equivalence_key(now_d) IS DISTINCT FROM d.equivalence_key THEN
        -- The digest carries the scope class, so this is where an edited scope
        -- document lands: same URL, different classification, different
        -- request as far as every approval in this corpus is concerned.
        RETURN 'request_reclassified';
    END IF;

    v := assess_call_risk(d.tool, now_d);
    IF v ->> 'risk_class' = 'forbidden' THEN RETURN 'now_forbidden'; END IF;
    IF v ->> 'rule' IS DISTINCT FROM d.risk_rule THEN RETURN 'policy_changed'; END IF;
    RETURN NULL;
END $fn$;

COMMENT ON FUNCTION revalidate_decision(text) IS
    'NULL when the answer an operator is about to give still describes the '
    'request the runtime would make now, else the name of what changed under '
    'it: the Program closed or halted, the Task gone, the request '
    'reclassified by an edited scope document, or a risk policy that now '
    'refuses it outright or asks a different question.';


-- ---------------------------------------------------------------------------
-- 5. Three operator verbs, and no fourth path
-- ---------------------------------------------------------------------------
-- Criterion 4. `answer_decision` gains the guard `halt_program` has had since
-- ticket 13 -- an explicit refusal naming the role -- rather than relying on
-- the actor-kind trigger to refuse the write two tables away. A non-operator
-- reaching it got `42501` either way; what changes is that the rule is now
-- written where somebody looking for it would look.
--
-- Both verbs open with the same three lines, and the three are not separable.
-- A verb that checked the role and forgot `set_actor` would file the operator's
-- rows under whatever actor the session last declared; one that declared the
-- actor without checking would hand a non-operator a refusal from a trigger two
-- tables away instead of from the verb they called; one that took no reason
-- would write a closed decision nobody can account for. Saying it once means
-- the fourth operator verb inherits all three or none.
CREATE FUNCTION assert_operator_verb(p_verb text, p_reason text) RETURNS void
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $fn$
BEGIN
    IF NOT human_actor_session() THEN
        RAISE EXCEPTION 'only an operator may %', p_verb USING ERRCODE = '42501';
    END IF;
    IF p_reason IS NULL OR btrim(p_reason) = '' THEN
        RAISE EXCEPTION 'a reason is required to %', p_verb USING ERRCODE = '22023';
    END IF;
    PERFORM set_actor('human', session_user);
END $fn$;

COMMENT ON FUNCTION assert_operator_verb(text, text) IS
    'The opening every operator verb shares: the session belongs to an operator, '
    'the operator gave a reason, and the actor for everything written next is '
    'that person. Called from inside a SECURITY DEFINER verb and deliberately not '
    'one itself -- it asserts about the session it is called in.';

CREATE OR REPLACE FUNCTION answer_decision(
    p_label text,
    p_verdict text,
    p_reason text,
    p_grant interval DEFAULT interval '24 hours'
) RETURNS jsonb SECURITY DEFINER LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $fn$
DECLARE
    d     pending_decisions%ROWTYPE;
    stale text;
BEGIN
    PERFORM assert_operator_verb('answer a decision', p_reason);
    IF p_verdict NOT IN ('approved','denied') THEN
        RAISE EXCEPTION 'verdict must be approved or denied, got %', p_verdict;
    END IF;

    SELECT * INTO d FROM pending_decisions
     WHERE label = p_label AND program_id = rk2_program()
     FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'no decision % in the bound Program', p_label; END IF;

    -- Approval only. A denial ends the work and needs nothing to still be true;
    -- an approval releases it, and that is the one direction where answering a
    -- question about a configuration that has since changed does damage.
    IF p_verdict = 'approved' THEN
        stale := revalidate_decision(p_label);
        IF stale IS NOT NULL THEN
            RAISE EXCEPTION 'decision % no longer validates against the current configuration: %',
                p_label, stale
                USING ERRCODE = '23514',
                      HINT = 'deny it, or supersede it and let the runtime ask again '
                             'under the configuration that holds now';
        END IF;
    END IF;

    UPDATE pending_decisions
       SET status = p_verdict, actor_kind = 'human', answered_at = now(),
           answered_by = session_user, answer = p_reason,
           grant_expires_at = CASE WHEN p_verdict = 'approved'
                                   THEN now() + p_grant ELSE NULL END
     WHERE id = d.id
    RETURNING * INTO d;

    IF p_verdict = 'approved' THEN
        UPDATE tasks SET status = 'pending', pending_decision_id = NULL, priority = NULL
         WHERE id = d.task_id;
    ELSE
        UPDATE tasks SET status = 'abandoned', abandoned_reason = 'decision_denied',
                         finished_at = now(), pending_decision_id = NULL, priority = NULL
         WHERE id = d.task_id;
    END IF;

    RETURN jsonb_build_object('label', d.label, 'status', d.status,
                              'answered_by', d.answered_by,
                              'grant_expires_at', d.grant_expires_at,
                              'equivalence_key', d.equivalence_key);
END $fn$;

COMMENT ON FUNCTION answer_decision(text, text, text, interval) IS
    'The operator''s answer to one question: approved, with a standing grant for '
    'equivalent requests, or denied, which ends the Task. An approval is '
    'revalidated first, so a question answered long after it was asked cannot '
    'release work under a configuration that no longer classifies it the way '
    'the operator was shown.';

-- The third verb. Without it an operator holding a question they can neither
-- approve (the scope changed under it) nor honestly deny (the work is fine,
-- the question is stale) has one move left: wait for the deadline and let it be
-- recorded as a timeout against a person who did in fact read it.
--
-- Superseding withdraws the question and puts the Task back where the gate
-- found it. The next attempt re-gates the request under the configuration in
-- force then, which is either allowed outright, or a new question with a new
-- digest -- and this is the one verb that leaves the runtime free to ask again.
CREATE FUNCTION supersede_decision(p_label text, p_reason text)
RETURNS jsonb SECURITY DEFINER LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $fn$
DECLARE d pending_decisions%ROWTYPE;
BEGIN
    PERFORM assert_operator_verb('supersede a decision', p_reason);

    SELECT * INTO d FROM pending_decisions
     WHERE label = p_label AND program_id = rk2_program()
     FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'no decision % in the bound Program', p_label; END IF;

    -- No grant, ever: `assert_decision_closes_once` refuses a second close, so
    -- a superseded question is closed and answers nothing afterwards.
    UPDATE pending_decisions
       SET status = 'superseded', actor_kind = 'human', answered_at = now(),
           answered_by = session_user, answer = p_reason
     WHERE id = d.id
    RETURNING * INTO d;

    UPDATE tasks SET status = 'pending', pending_decision_id = NULL, priority = NULL
     WHERE id = d.task_id AND status = 'parked';

    RETURN jsonb_build_object('label', d.label, 'status', d.status,
                              'answered_by', d.answered_by,
                              'task_returned_to_pending', d.task_id IS NOT NULL);
END $fn$;

COMMENT ON FUNCTION supersede_decision(text, text) IS
    'The operator withdraws a question rather than answering it, and the Task '
    'goes back to pending with no grant behind it. What resolves it next is a '
    'fresh gate verdict under the configuration in force then, which is what '
    'makes this the verb to reach for after changing the configuration the '
    'question was asked under.';

ALTER TABLE pending_decisions DROP CONSTRAINT pending_decisions_status_check;
ALTER TABLE pending_decisions ADD CONSTRAINT pending_decisions_status_check
    CHECK (status IN ('pending','approved','denied','expired','superseded'));

COMMENT ON COLUMN pending_decisions.status IS
    'pending until somebody closes it: approved or denied by an operator, '
    'superseded by an operator who withdrew it, expired by the runtime when the '
    'deadline passed unanswered. Only `approved` carries a grant.';

UPDATE event_types
   SET description = 'human consultation closed: answered or withdrawn by a human, or expired by the runtime'
 WHERE id = 'decision.answered';

-- `assert_operator_verb` is revoked from everyone and granted to nobody: the
-- verbs that call it are SECURITY DEFINER and reach it as their owner, so the
-- only way to run it is through a verb that then does something with the actor
-- it declared. A role holding EXECUTE on it directly could declare itself the
-- human actor for the rest of its transaction and write nothing this file
-- guards.
REVOKE ALL ON FUNCTION answer_decision(text, text, text, interval),
                       supersede_decision(text, text),
                       assert_operator_verb(text, text),
                       revalidate_decision(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION answer_decision(text, text, text, interval),
                       supersede_decision(text, text),
                       assert_operator_verb(text, text),
                       revalidate_decision(text)
    FROM rk2_runtime, rk2_state, rk2_proxy, rk2_human;
GRANT EXECUTE ON FUNCTION answer_decision(text, text, text, interval),
                          supersede_decision(text, text),
                          revalidate_decision(text) TO rk2_human;

-- `current_request_digest` is the gate's own reading and belongs to the two
-- roles that gate: the runtime that asks before a call, and the operator whose
-- revalidation asks again. `rk2_state` is the model's connection and gets
-- neither -- the digest is where the scope classification of a request lives.
REVOKE ALL ON FUNCTION current_request_digest(uuid) FROM PUBLIC, rk2_state, rk2_proxy;
GRANT EXECUTE ON FUNCTION current_request_digest(uuid) TO rk2_runtime;

-- Ticket 24's recovery verb, which unclaims Tasks, aborts Agent runs and
-- releases Leases. It was reachable by every role including the two a model can
-- influence, which made "resume" a verb the model's own read connection could
-- use to dissolve a competitor's Lease. It stays the runtime's and does not
-- become an operator verb: its first statement is `set_actor('runtime')`, so an
-- operator calling it would file every row it writes under the runtime's name.
-- The operator's half of resuming is clearing the Halt; the runtime's half runs
-- at the next `rk run`, which is where it already runs.
REVOKE ALL ON FUNCTION resume_program(uuid) FROM PUBLIC, rk2_state, rk2_proxy, rk2_human;
GRANT EXECUTE ON FUNCTION resume_program(uuid) TO rk2_runtime;

-- Every operator verb names a Program: the two Halt verbs by id, the two
-- decision verbs through the session binding `answer_decision` resolves a label
-- inside. `rk2_human` could reach none of them, so the console had no way to
-- turn the slug an operator types into the Program those verbs want. The row
-- holds the campaign's standing and its budgets and no secret material.
GRANT SELECT ON programs TO rk2_human;

-- And the queue the operator reads before reaching for a verb. Labels are
-- counted per Program, so `D1` exists in as many Programs as are open, and a
-- queue that did not say which one a question belongs to is a list an operator
-- can act on wrongly by reading it correctly. The slug and not the id: a `v_`
-- view carries no uuid, and the slug is the citation the same operator will
-- type into the verb.
DROP VIEW v_decision_queue;
CREATE VIEW v_decision_queue WITH (security_invoker = true) AS
    SELECT p.slug AS program,
           d.label,
           d.tool,
           d.risk_class,
           d.risk_rule,
           d.question_code,
           d.question,
           d.created_at AS requested_at,
           d.deadline_at,
           d.status,
           d.answered_by,
           d.answer,
           d.request_digest
      FROM pending_decisions d
      JOIN programs p ON p.id = d.program_id;

COMMENT ON VIEW v_decision_queue IS
    'The operator''s queue: every question, whose Program it belongs to and '
    'what was answered. Readable by rk2_human alone -- the answer column is '
    'free text an operator wrote and the runtime is what compiles the documents '
    'a model is handed.';

GRANT SELECT ON v_decision_queue TO rk2_human;


-- ---------------------------------------------------------------------------
-- 6. The operator's words stay the operator's
-- ---------------------------------------------------------------------------
-- Criterion 6. `pending_decisions.answer` is free text a person wrote for one
-- question. It had two ways into a model's context and this closes both.
--
-- The first is the column. `rk2_runtime` held table-level SELECT, and the
-- runtime is what compiles every document a child is handed. Column-level
-- privileges cannot subtract from a table-level grant, so the table grant goes
-- and every column except the answer comes back -- which is also why this is
-- generated rather than listed: the list is the table's, and a copy of it here
-- would be one migration away from being wrong.
--
-- `xmin` is granted by name because the table grant it used to ride on is
-- gone. `check_event_log_integrity` reads `r.xmin` on every table in
-- `event_table_config` to find a row whose last write emitted no event, and a
-- system column is reachable through a table-level SELECT or through a grant
-- naming it -- not through a grant of every user column. Without this line the
-- revoke above does not hide the answer from a check, it blinds the check: the
-- integrity gate stops being able to run at all on the one table this ticket
-- adds rows to, and every `program.run` fails with a permission error instead
-- of a verdict.
DO $$
DECLARE cols text;
BEGIN
    SELECT string_agg(quote_ident(a.attname), ', ' ORDER BY a.attnum) INTO cols
      FROM pg_attribute a
     WHERE a.attrelid = 'pending_decisions'::regclass
       AND (a.attnum > 0 OR a.attname = 'xmin')
       AND NOT a.attisdropped AND a.attname <> 'answer';
    EXECUTE 'REVOKE SELECT ON pending_decisions FROM rk2_runtime';
    EXECUTE format('GRANT SELECT (%s) ON pending_decisions TO rk2_runtime', cols);
END $$;

-- `readwrite_on_every_managed_table` asked that question with
-- `has_table_privilege`, which answers false for a role holding every column
-- and no table grant. The arm exists so that the runtime is never locked out of
-- a table it has to work on, and a column-level read is not being locked out --
-- so it asks `has_any_column_privilege` for the read half. The write half stays
-- table-level: a partial INSERT grant is a table the runtime cannot write a row
-- to, which is the fault the arm was written for. Which column the runtime may
-- not read is a narrower claim than this arm makes, and section 7 makes it.
CREATE OR REPLACE FUNCTION check_runtime_connection(p_role text DEFAULT current_user)
RETURNS TABLE (check_name text, ok boolean, detail text)
LANGUAGE plpgsql STABLE AS $fn$
DECLARE
    v_role oid;
    v_n int;
    v_tbl text;
BEGIN
    SELECT oid INTO v_role FROM pg_roles WHERE rolname = p_role;

    RETURN QUERY SELECT 'role_exists'::text, v_role IS NOT NULL, 'role = ' || p_role;
    RETURN QUERY SELECT 'not_superuser'::text,
        v_role IS NOT NULL AND NOT coalesce(
            (SELECT rolsuper FROM pg_roles WHERE oid = v_role), true),
        p_role || ' rolsuper = ' || coalesce(
            (SELECT rolsuper::text FROM pg_roles WHERE oid = v_role), '<absent>');
    RETURN QUERY SELECT 'not_bypassrls'::text,
        v_role IS NOT NULL AND NOT coalesce(
            (SELECT rolbypassrls FROM pg_roles WHERE oid = v_role), true),
        p_role || ' rolbypassrls';
    RETURN QUERY SELECT 'not_owner'::text,
        v_role IS NOT NULL AND NOT rk2_role_has_usage(p_role, 'rk2_owner'),
        p_role || ' member of rk2_owner = '
            || rk2_role_has_usage(p_role, 'rk2_owner')::text;

    SELECT count(*), min(m.table_name) INTO v_n, v_tbl
      FROM managed_tables m JOIN pg_class c ON c.oid = m.oid
     WHERE v_role IS NULL OR pg_has_role(v_role, c.relowner, 'USAGE');
    RETURN QUERY SELECT 'owns_no_managed_table'::text,
        v_role IS NOT NULL AND v_n = 0,
        v_n || ' table(s) owned' || coalesce(', e.g. ' || v_tbl, '');

    RETURN QUERY SELECT 'cannot_set_replication_role'::text,
        v_role IS NOT NULL AND NOT has_parameter_privilege(
            v_role, 'session_replication_role', 'SET'),
        p_role || ' SET on session_replication_role';

    SELECT count(*), min(m.table_name) INTO v_n, v_tbl
      FROM managed_tables m
     WHERE v_role IS NULL
        OR NOT has_any_column_privilege(v_role, m.oid, 'SELECT')
        OR NOT has_table_privilege(v_role, m.oid, 'INSERT');
    RETURN QUERY SELECT 'readwrite_on_every_managed_table'::text,
        v_role IS NOT NULL AND v_n = 0,
        v_n || ' table(s) not readable/writable' || coalesce(', e.g. ' || v_tbl, '');

    SELECT count(*) INTO v_n FROM managed_tables m
     WHERE v_role IS NOT NULL AND has_table_privilege(v_role, m.oid, 'TRUNCATE');
    RETURN QUERY SELECT 'no_truncate_anywhere'::text,
        v_role IS NOT NULL AND v_n = 0,
        v_n || ' table(s) truncatable';
END $fn$;

-- INSERT and UPDATE are deliberately untouched: `expire_due_decisions` writes
-- the answer column as the runtime when a deadline passes, and write-only is
-- exactly what criterion 6 asks for.
COMMENT ON COLUMN pending_decisions.answer IS
    'What the operator wrote, or the runtime''s sentence when a deadline passed. '
    'Write-only to everything but the operator: `rk2_runtime` may set it and '
    'may not read it, because the runtime is what compiles the documents a '
    'model is handed and this text is not one of them.';

-- The second is the view, and the schema's default privileges hand every new
-- one to the runtime -- including the one section 5 just rebuilt. This one is
-- `security_invoker`, so the column grant above would refuse the answer through
-- it anyway; the grant goes because a view nobody may usefully read is a grant
-- that only survives to be inherited by whatever replaces it. What the standing
-- check below asks about is the grant and not the invoker setting, for the same
-- reason: the leak arrives the day someone writes the queue's successor without
-- it.
REVOKE ALL ON v_decision_queue FROM rk2_runtime;

-- And the third, which is the one that would have been missed: the event log.
-- `decision.answered` is emitted by comparing rows, so the answer text was in
-- the payload of every close, and `events` is read by the runtime and quoted
-- into what it compiles. 016's redaction list is the mechanism the corpus
-- already has for a column whose value must not be republished.
UPDATE event_table_config
   SET redacted_columns = redacted_columns || '{answer}'
 WHERE table_name = 'pending_decisions';

-- One diagnostic asks every column of every table whether it holds a value, and
-- until this file there was no column any caller of it could not read. It runs
-- as its caller, deliberately -- a scan that ran as the owner would answer the
-- runtime "is the operator's answer the string I guessed", one guess at a time,
-- which is the leak this section closes wearing a different hat. So it skips
-- what its caller may not read rather than raising on it: a marker hunt that
-- stops at the first denied column is a diagnostic that stopped working, and
-- the answer it would have given about the rest is the one worth having.
-- Completeness is now the caller's to arrange, by running it as a role that can
-- read everything, and the comment says so where someone reaching for it reads.
CREATE OR REPLACE FUNCTION find_in_database(needle text)
RETURNS TABLE (relation text, attribute text, hits bigint)
LANGUAGE plpgsql STABLE AS $fn$
DECLARE r record; n bigint; q text;
BEGIN
    IF needle IS NULL OR needle = '' THEN
        RAISE EXCEPTION 'find_in_database needs something to look for';
    END IF;
    FOR r IN
        SELECT c.relname, a.attname, t.typname
          FROM pg_attribute a
          JOIN pg_class c ON c.oid = a.attrelid
          JOIN pg_namespace ns ON ns.oid = c.relnamespace AND ns.nspname = 'public'
          JOIN pg_type t ON t.oid = a.atttypid
         WHERE c.relkind IN ('r', 'p', 'm') AND a.attnum > 0 AND NOT a.attisdropped
           AND has_column_privilege(c.oid, a.attnum, 'SELECT')
         ORDER BY c.relname, a.attnum
    LOOP
        IF r.typname = 'bytea' THEN
            q := format('SELECT count(*) FROM public.%I WHERE position($1::bytea in %I) > 0',
                        r.relname, r.attname);
        ELSE
            q := format('SELECT count(*) FROM public.%I WHERE strpos(%I::text, $1) > 0',
                        r.relname, r.attname);
        END IF;
        EXECUTE q INTO n USING needle;
        IF n > 0 THEN
            relation := r.relname; attribute := r.attname; hits := n;
            RETURN NEXT;
        END IF;
    END LOOP;
END $fn$;

COMMENT ON FUNCTION find_in_database(text) IS
    'Every table column holding this value that the calling role may read. For '
    'synthetic markers and incident response: the needle travels as a query '
    'parameter, so do not pass a real credential. A column the caller has no '
    'SELECT on is skipped rather than raised on -- `pending_decisions.answer` '
    'is one for every role but the operator -- so a scan that has to be '
    'complete is run as a role that can read everything.';


-- ---------------------------------------------------------------------------
-- 7. What can go wrong, as rows
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION check_control_surface()
RETURNS TABLE (problem text, detail text)
LANGUAGE sql STABLE AS $fn$
    -- rule 1: every table carrying actor_kind is guarded, and the guard fires
    -- under replica too
    SELECT 'actor_kind_unguarded'::text, c.relname
      FROM pg_class c
     WHERE c.relkind = 'r' AND c.relnamespace = 'public'::regnamespace
       AND EXISTS (SELECT 1 FROM pg_attribute a WHERE a.attrelid = c.oid
                     AND a.attname = 'actor_kind' AND a.attnum > 0 AND NOT a.attisdropped)
       AND NOT EXISTS (SELECT 1 FROM pg_trigger t
                        WHERE t.tgrelid = c.oid AND NOT t.tgisinternal
                          AND t.tgname = c.relname || '_actor_kind_guard'
                          AND t.tgenabled = 'A')
UNION ALL
    -- rule 1: the human role is not reachable from the two connections a model
    -- can influence
    SELECT 'human_role_reachable', r.rolname
      FROM pg_roles r
     WHERE r.rolname IN ('rk2_state','rk2_runtime')
       AND pg_has_role(r.oid, 'rk2_human', 'MEMBER')
UNION ALL
    -- rule 2: nothing in the control surface accepts a risk class as an
    -- argument. A model's only route into the judgement is the request itself.
    SELECT 'risk_class_is_an_argument', p.proname || '(' || pg_get_function_arguments(p.oid) || ')'
      FROM pg_proc p
     WHERE p.pronamespace = 'public'::regnamespace
       AND p.proname IN ('gate_tool_call','park_for_human','assess_call_risk','answer_decision')
       AND pg_get_function_arguments(p.oid) ~ 'risk'
UNION ALL
    -- rule 2: the escalation table cannot lower a class below a floor
    SELECT 'escalation_rule_lowers', r.rule_id || ' -> ' || r.escalate_to
      FROM call_risk_rules r
     WHERE risk_rank(r.escalate_to) IS NULL
UNION ALL
    -- rule 2: a declared fact the canonicaliser stopped emitting. The rules
    -- that name it would still be there, still readable as policy, and would
    -- never fire again. Probed against the real function, not a list.
    SELECT 'risk_fact_not_in_digest', f.fact
      FROM digest_facts f
     WHERE f.source = 'canonicaliser'
       AND f.fact NOT IN (
           SELECT jsonb_object_keys(canonical_request(
                      'mcp__rk2__net_request',
                      '{"url":"https://probe.invalid/a"}'::jsonb, 'probe'))
           UNION
           SELECT jsonb_object_keys(canonical_request(
                      'mcp__rk2__run_tool', '{"tool_name":"probe"}'::jsonb, 'probe')))
UNION ALL
    -- rule 3: no open decision on a forbidden call, ever
    SELECT 'forbidden_decision', d.label
      FROM pending_decisions d WHERE d.risk_class = 'forbidden'
UNION ALL
    -- rule 4: a decision past its deadline that nothing swept. Loud, because a
    -- parked task and a stopped harness look identical from outside.
    SELECT 'decision_past_deadline_unswept', d.label
      FROM pending_decisions d
     WHERE d.status = 'pending' AND d.deadline_at <= now()
UNION ALL
    -- rule 4: a parked task must hold no lease. Two clocks is ticket 08's named
    -- failure and this is where it would show up.
    SELECT 'parked_task_holds_a_lease', t.label
      FROM tasks t WHERE t.status = 'parked' AND t.lease_expires_at IS NOT NULL
UNION ALL
    SELECT 'parked_task_holds_an_identity', t.label
      FROM tasks t
      JOIN agent_runs a ON a.task_id = t.id
      JOIN identity_leases l ON l.holder_agent_run_id = a.id
     WHERE t.status = 'parked' AND l.released_at IS NULL
UNION ALL
    -- 29, criterion 2: the third resource a parked run could still be holding.
    -- An open receipt is a capability the door would resolve, belonging to a run
    -- that ended when the question was filed.
    SELECT 'parked_task_holds_an_open_receipt', t.label || '/' || tr.label
      FROM tasks t
      JOIN agent_runs a ON a.task_id = t.id
      JOIN tool_runs tr ON tr.agent_run_id = a.id
     WHERE t.status = 'parked' AND tr.status = 'running'
UNION ALL
    -- rule 5: a grant with no live approval behind it
    SELECT 'grant_without_approval', d.label
      FROM pending_decisions d
     WHERE d.grant_expires_at IS NOT NULL AND d.status <> 'approved'
UNION ALL
    -- 29, criterion 4: a closed question whose Task nobody moved. The three
    -- verbs each end with the Task somewhere else; a Task still parked on a
    -- decision that is over is work no operator can reach and no scheduler will
    -- offer.
    SELECT 'closed_decision_left_task_parked', d.label
      FROM pending_decisions d
      JOIN tasks t ON t.pending_decision_id = d.id
     WHERE d.status <> 'pending' AND t.status = 'parked'
UNION ALL
    -- the agent connection must not reach the decision queue
    SELECT 'decision_queue_reachable_by_agent', table_name || '.' || privilege_type
      FROM information_schema.table_privileges
     WHERE grantee = 'rk2_state'
       AND table_name IN ('pending_decisions','decision_notifications',
                          'call_risk_rules','notification_channels','v_decision_queue',
                          'decision_question_codes')
UNION ALL
    -- 29, criterion 4: the operator verbs are the operator's. Asked of the
    -- privilege itself rather than of the grants, so a role that reached one
    -- through membership of another would still be found.
    SELECT 'operator_verb_reachable', p.proname || ' by ' || r.rolname
      FROM pg_proc p
      CROSS JOIN (VALUES ('rk2_runtime'),('rk2_state'),('rk2_proxy')) AS r(rolname)
     WHERE p.pronamespace = 'public'::regnamespace
       AND p.proname IN ('answer_decision','supersede_decision',
                         'halt_program','clear_program_halt')
       AND has_function_privilege(r.rolname, p.oid, 'EXECUTE')
UNION ALL
    -- 29, criterion 6: the operator's free text, reachable by something that
    -- composes a model's context.
    SELECT 'decision_free_text_readable', c.grantee || ' reads ' || c.column_name
      FROM information_schema.column_privileges c
     WHERE c.table_name = 'pending_decisions' AND c.column_name = 'answer'
       AND c.privilege_type = 'SELECT'
       AND c.grantee NOT IN ('rk2_human','rk2_owner','rk2_migrate','rk2_restore')
UNION ALL
    -- and the same text reached through a view, which runs as its owner and
    -- would hand back what the column grant refuses. Found through the
    -- dependency graph rather than by reading definitions: a view that selects
    -- the column depends on the column, whatever it calls it.
    SELECT 'decision_free_text_in_a_view', v.relname || ' read by ' || tp.grantee
      FROM pg_depend dep
      JOIN pg_rewrite rw ON rw.oid = dep.objid AND rw.rulename = '_RETURN'
      JOIN pg_class v ON v.oid = rw.ev_class AND v.relkind = 'v'
      JOIN information_schema.table_privileges tp
        ON tp.table_name = v.relname AND tp.table_schema = 'public'
       AND tp.privilege_type = 'SELECT'
     WHERE dep.classid = 'pg_rewrite'::regclass
       AND dep.refobjid = 'pending_decisions'::regclass
       AND dep.refobjsubid = (SELECT a.attnum FROM pg_attribute a
                               WHERE a.attrelid = 'pending_decisions'::regclass
                                 AND a.attname = 'answer')
       AND tp.grantee NOT IN ('rk2_human','rk2_owner','rk2_migrate','rk2_restore')
UNION ALL
    -- 29, criterion 6: and the log. The answer is redacted from the payload
    -- rather than kept out of the row, so this asks the registry that does it.
    SELECT 'decision_free_text_in_the_log', c.table_name
      FROM event_table_config c
     WHERE c.table_name = 'pending_decisions'
       AND NOT ('answer' = ANY (c.redacted_columns))
UNION ALL
    -- an enabled channel with an empty argv delivers nothing, silently
    SELECT 'enabled_channel_delivers_nothing', c.channel
      FROM notification_channels c
     WHERE c.enabled AND cardinality(c.argv) = 0
UNION ALL
    -- rule 4, one step earlier: an open question that nobody was told about and
    -- nobody will be. Every channel it was fanned out to has spent its attempts
    -- or has since been disabled, so the only thing that will ever happen to it
    -- is the deadline -- and it would then be retired as a timeout against a
    -- human who never heard the question. A decision with no notification row at
    -- all counts too: that is a fan-out that reached no channel.
    SELECT 'decision_unannounced', d.label
      FROM pending_decisions d
     WHERE d.status = 'pending'
       AND NOT EXISTS (SELECT 1 FROM decision_notifications n
                        WHERE n.pending_decision_id = d.id
                          AND n.delivered_at IS NOT NULL)
       AND NOT EXISTS (SELECT 1 FROM decision_notifications n
                        JOIN notification_channels c ON c.channel = n.channel
                        WHERE n.pending_decision_id = d.id
                          AND n.delivered_at IS NULL
                          AND n.attempts < c.max_attempts
                          AND c.enabled)
$fn$;

COMMENT ON FUNCTION check_control_surface() IS
    'What the human control surface can get wrong: an unguarded actor kind, the '
    'operator role reachable from a model-facing connection, a risk class '
    'passed as an argument, an escalation that lowers, a rule keyed on a fact '
    'nothing emits, an open question on a forbidden call, a deadline nothing '
    'swept, a parked Task still holding a lease, an identity or an open '
    'receipt, a grant with no approval, a closed question whose Task nobody '
    'moved, the queue or a control verb reachable by the agent, and the '
    'operator''s free text readable by anything that composes what a model is '
    'handed.';


-- ---------------------------------------------------------------------------
-- 8. The invariants this file must not have broken
-- ---------------------------------------------------------------------------
DO $$
DECLARE n integer; d text;
BEGIN
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_control_surface();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-29 refuses to finish: % control surface violation(s): %', n, d;
    END IF;

    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_program_halt();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-29 breaks the Halt (% problems): %', n, d;
    END IF;
END $$;
