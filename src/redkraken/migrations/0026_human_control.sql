-- ---------------------------------------------------------------------------
-- 026_ticket28_human_control.sql   (ticket 28)
--
-- The human control surface, stated once:
--
--   1. HUMAN PROVENANCE IS A DATABASE IDENTITY, NOT A SESSION VARIABLE.
--      Ticket 07 made `app.actor_kind` mandatory, which stops a write with no
--      claimed actor. It does not stop a *false* claim: any session can
--      `SET app.actor_kind = 'human'`. So `actor_kind='human'` is additionally
--      bound to membership of the `rk2_human` role, checked by an ENABLE ALWAYS
--      trigger on every table that carries an `actor_kind` column. The runtime
--      connection is not a member and cannot become one.
--
--   2. THE MODEL NEVER NAMES A RISK CLASS. Ticket 13's `tool_risk_classes` is a
--      static per-tool floor. The per-call judgement is `assess_call_risk()`,
--      evaluated in the database over the runtime's own canonicalisation of the
--      request, and it may only ever escalate. `tool_runs.risk_class` below its
--      tool's floor, or lowered by an update, is a constraint violation.
--
--   3. `forbidden` NEVER PARKS. Ticket 13 added the fourth class precisely so a
--      refusal is not an escalation. `pending_decisions.risk_class` has a CHECK
--      forbidding it, so "always escalate" cannot be reintroduced by code.
--
--   4. THE DEADLINE IS A COLUMN, NOT A COUNTDOWN. Q29 says every abort resumes
--      from the event log, so no clock may live in a process. `deadline_at` is
--      stored at park time and evaluated by `expire_due_decisions()`, which is
--      called from `resume_program()` -- the one path every abort already takes.
--
--   5. AN APPROVAL IS FORWARD-LOOKING, NEVER RETROACTIVE. Parking ends the run
--      (ticket 08 decision 13), so the parked tool call is dead the moment it
--      parks and no answer can revive it. The answer authorises the *next*
--      equivalent request, matched on `equivalence_key`. Without that key the
--      resumed task re-asks the identical question and parks again, forever;
--      `tests/parkloop.sh` runs that loop with the key disabled.
--
-- The catalogue moves with the table: `decision.requested` / `decision.answered`
-- stop being occurrence events and become row events on `pending_decisions`
-- (ticket 07 decision 9 -- a trigger writes them, so no call site can forget).
--
-- `check_control_surface()` is rules 1-5 as a query.
-- ---------------------------------------------------------------------------

SET client_min_messages = notice;


-- ===========================================================================
-- 1. Rule 1 -- the actor role, and the claim a session cannot make
-- ===========================================================================

-- [ticket 33 consolidation] the CREATE ROLE block moved to `./migrate.sh
-- provision`: rk2_migrate has no CREATEROLE and must not get it. Refused by
-- ./migrate.sh lint.

CREATE FUNCTION human_actor_session() RETURNS boolean
LANGUAGE sql STABLE AS $$
    SELECT pg_has_role(session_user, 'rk2_human', 'MEMBER');
$$;

-- `session_user`, deliberately, not `current_user`: SECURITY DEFINER changes
-- `current_user` and a function owned by the schema owner would then vouch for
-- its own caller. `session_user` is the authenticated connection identity and
-- nothing running inside the session can change it without being a superuser
-- already.
CREATE FUNCTION assert_actor_kind_authentic() RETURNS trigger
LANGUAGE plpgsql AS $fn$
DECLARE claimed text := to_jsonb(NEW) ->> 'actor_kind';
BEGIN
    IF claimed = 'human' AND NOT human_actor_session() THEN
        RAISE EXCEPTION
            'actor_kind=human on %.% claimed by session_user %, which is not a member of rk2_human',
            TG_TABLE_NAME, coalesce(to_jsonb(NEW) ->> 'id', '?'), session_user
            USING ERRCODE = '42501',
                  HINT = 'human provenance is a database identity, not a session variable';
    END IF;
    RETURN NEW;
END $fn$;

-- Every table carrying `actor_kind`, found by catalogue rather than by list, so
-- a later migration that adds one is covered on its own re-run. `events` is in
-- the set, which is what covers `emit_event()`'s row events and every
-- occurrence event inserted directly.
CREATE FUNCTION attach_actor_kind_guards() RETURNS void LANGUAGE plpgsql AS $fn$
DECLARE t text;
BEGIN
    FOR t IN
        SELECT c.relname FROM pg_class c
         WHERE c.relkind = 'r' AND c.relnamespace = 'public'::regnamespace
           AND EXISTS (SELECT 1 FROM pg_attribute a
                        WHERE a.attrelid = c.oid AND a.attname = 'actor_kind'
                          AND a.attnum > 0 AND NOT a.attisdropped)
         ORDER BY c.relname
    LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS %I ON %I', t || '_actor_kind_guard', t);
        EXECUTE format('CREATE TRIGGER %I BEFORE INSERT OR UPDATE ON %I
                        FOR EACH ROW EXECUTE FUNCTION assert_actor_kind_authentic()',
                       t || '_actor_kind_guard', t);
        EXECUTE format('ALTER TABLE %I ENABLE ALWAYS TRIGGER %I',
                       t, t || '_actor_kind_guard');
    END LOOP;
END $fn$;


-- ===========================================================================
-- 2. Canonicalisation -- what makes two requests the same request
-- ===========================================================================
--
-- The equivalence key is computed in the database from the runtime's own
-- canonical form. Nothing accepts a key as an argument, so a model cannot
-- present one; and because the digest is stored beside the key, a human can see
-- afterwards exactly what was approved.
--
-- The fields are the ones `receipts` already records for the same request
-- (method, scheme, host, port, path) plus the identity slot the proxy will
-- inject. Deliberately IN: an approval that ignored `method` would authorise
-- DELETE from an approved GET, and one that ignored `identity_slot` would
-- authorise userB from an approval for userA -- and the Q15 differential is
-- built out of exactly that pair. Deliberately OUT: parameter and body VALUES,
-- and every id, label and timestamp of the asking run. Including values means
-- the second order id re-asks, which in a scan means asking forever, which in
-- practice means the operator approves without reading.

CREATE FUNCTION path_template(p_path text) RETURNS text
LANGUAGE sql IMMUTABLE AS $$
    SELECT '/' || coalesce(string_agg(
        CASE WHEN seg ~ '^[0-9]+$'
               OR seg ~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
               OR seg ~ '^[0-9a-fA-F]{32,}$'
             THEN '{id}' ELSE seg END, '/' ORDER BY ord), '')
      FROM unnest(string_to_array(ltrim(coalesce(p_path,'/'), '/'), '/'))
           WITH ORDINALITY AS t(seg, ord);
$$;

-- Only tools with a canonicaliser can produce a reusable approval. Anything
-- else gets `reusable:false` plus a nonce, so its key is unique to one call and
-- an approval for it can never match a second one. Fail-narrow: a tool nobody
-- has analysed does not silently acquire a class-wide grant.
CREATE FUNCTION canonical_request(p_tool text, p_args jsonb, p_nonce text)
RETURNS jsonb LANGUAGE plpgsql IMMUTABLE AS $fn$
DECLARE
    u  text;
    m  text[];
    sc text; ho text; po int; pa text; qs text;
BEGIN
    IF p_tool <> 'mcp__rk2__net_request' THEN
        -- Not reusable, so the nonce makes every key unique. `tool_name` is
        -- still carried because it is a risk FACT: a rule that names a fact the
        -- digest never holds is a rule that can never fire, which is a hole
        -- that looks like a policy. Carrying it cannot widen an approval --
        -- `reusable` is false either way.
        RETURN jsonb_build_object(
            'tool', p_tool, 'reusable', false, 'nonce', p_nonce,
            'tool_name', coalesce(p_args ->> 'tool_name', ''),
            'arg_names', (SELECT coalesce(jsonb_agg(k ORDER BY k), '[]'::jsonb)
                            FROM jsonb_object_keys(coalesce(p_args,'{}'::jsonb)) k));
    END IF;

    u := p_args ->> 'url';
    m := regexp_match(coalesce(u,''),
                      '^(https?)://([^/:?#]+)(?::([0-9]+))?([^?#]*)(?:\?([^#]*))?$');
    IF m IS NULL THEN
        RAISE EXCEPTION 'net_request url is not canonicalisable: %', coalesce(u,'<null>')
            USING ERRCODE = '22023';
    END IF;
    sc := lower(m[1]);
    ho := lower(m[2]);
    po := coalesce(m[3]::int, CASE sc WHEN 'https' THEN 443 ELSE 80 END);
    pa := path_template(nullif(m[4], ''));
    qs := coalesce(m[5], '');

    RETURN jsonb_build_object(
        'tool',          p_tool,
        'reusable',      true,
        'method',        upper(coalesce(p_args ->> 'method', 'GET')),
        'scheme',        sc,
        'host',          ho,
        'port',          po,
        'path_template', pa,
        'identity_slot', coalesce(p_args ->> 'identity_slot', ''),
        -- names, never values
        'query_names',   (SELECT coalesce(jsonb_agg(DISTINCT split_part(kv,'=',1)), '[]'::jsonb)
                            FROM unnest(string_to_array(qs,'&')) kv
                           WHERE kv <> ''),
        'body_keys',     (SELECT coalesce(jsonb_agg(k ORDER BY k), '[]'::jsonb)
                            FROM jsonb_object_keys(
                                 CASE WHEN jsonb_typeof(p_args -> 'body') = 'object'
                                      THEN p_args -> 'body' ELSE '{}'::jsonb END) k));
END $fn$;

-- jsonb stores its keys in a canonical order, so `digest::text` is stable for
-- equal documents regardless of how they were built. That property is what is
-- being hashed; the equivalence test in tests/equivalence.sql asserts it rather
-- than assuming it.
CREATE FUNCTION equivalence_key(p_digest jsonb) RETURNS text
LANGUAGE sql IMMUTABLE AS $$
    SELECT encode(sha256(convert_to(p_digest::text, 'UTF8')), 'hex');
$$;


-- ===========================================================================
-- 3. Rule 2 -- where the per-call judgement is computed
-- ===========================================================================
--
-- Ticket 28's own framing: an allowlist is a static boundary and a risk class
-- is a per-call judgement, so they are not the same mechanism. Ticket 13 built
-- the static half (`tool_risk_classes`, exact then longest glob then `*`). This
-- is the per-call half, and the two are composed by MAX, never by replacement.

CREATE FUNCTION risk_rank(p_class text) RETURNS smallint
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE p_class WHEN 'autonomous' THEN 0 WHEN 'constrained' THEN 1
                        WHEN 'approval_required' THEN 2 WHEN 'forbidden' THEN 3 END::smallint;
$$;

-- The facts a rule is allowed to name. This is a table and not a comment
-- because the failure it prevents is silent: a rule naming a key the
-- canonicaliser does not emit never fires, and a rule that never fires reads
-- exactly like a policy that is in force. The foreign key below stops one being
-- written; `risk_fact_not_in_digest` in check_control_surface() stops one being
-- declared here and then dropped from canonical_request().
CREATE TABLE digest_facts (
    fact   text PRIMARY KEY,
    source text NOT NULL CHECK (source IN ('canonicaliser','projection'))
);

INSERT INTO digest_facts (fact, source) VALUES
    ('method','canonicaliser'), ('scheme','canonicaliser'), ('host','canonicaliser'),
    ('port','canonicaliser'), ('path_template','canonicaliser'),
    ('identity_slot','canonicaliser'), ('query_names','canonicaliser'),
    ('body_keys','canonicaliser'), ('tool','canonicaliser'),
    ('tool_name','canonicaliser'), ('arg_names','canonicaliser'),
    ('reusable','canonicaliser'),
    -- stamped by gate_tool_call() from ticket 26's projection, never from args
    ('host_in_scope','projection'), ('scope_class','projection');

INSERT INTO program_global_tables (table_name, reason) VALUES
    ('digest_facts',
     'the vocabulary the escalation policy is written in; per-program copies would let a program silence a rule by renaming a fact');

-- `fact` names a key of the canonical digest -- i.e. a value the RUNTIME
-- derived, in the database, from the request it is about to make. There is no
-- rule form that reads a model's prose, a tool's free-text argument, or a class
-- the caller supplies, because there is no column for one.
CREATE TABLE call_risk_rules (
    rule_id      text PRIMARY KEY,
    tool_pattern text NOT NULL,
    fact         text NOT NULL REFERENCES digest_facts(fact),
    op           text NOT NULL CHECK (op IN ('in','not_in','is_false')),
    fact_values  text[] NOT NULL DEFAULT '{}',
    escalate_to  text NOT NULL REFERENCES risk_classes(risk_class),
    -- ticket 12's taxonomy, carried on the rule: the operator sees the escalation
    -- already classified rather than classified by whoever wrote the call site.
    question_code text NOT NULL CHECK (question_code IN (
        'scope_ambiguous','destructive_action','third_party_impact',
        'credential_needed','policy_unclear')),
    rationale    text NOT NULL
);

INSERT INTO call_risk_rules
    (rule_id, tool_pattern, fact, op, fact_values, escalate_to, question_code, rationale) VALUES
    ('net_unsafe_method', 'mcp__rk2__net_request', 'method', 'not_in',
     '{GET,HEAD,OPTIONS}', 'approval_required', 'destructive_action',
     'a method outside the safe set is a state-changing test on someone else''s system (Q4)'),
    ('net_host_out_of_scope', 'mcp__rk2__net_request', 'host_in_scope', 'is_false',
     '{}', 'forbidden', 'scope_ambiguous',
     'ticket 26 says the host is not in scope: the proxy refuses it, and no human approval can produce a receipt for a request that never leaves'),
    ('net_borrowed_identity', 'mcp__rk2__net_request', 'identity_slot', 'not_in',
     '{""}', 'approval_required', 'credential_needed',
     'a request that carries an injected identity acts as a real account holder; Q15 differentials are built out of exactly this'),
    ('exec_destructive_tool', 'mcp__rk2__run_tool', 'tool_name', 'in',
     '{sqlmap,ffuf-write,nuclei-dast}', 'approval_required', 'third_party_impact',
     'ticket 11''s run_tool enum contains entries whose blast radius is not bounded by the proxy''s scope check alone');

INSERT INTO program_global_tables (table_name, reason) VALUES
    ('call_risk_rules',
     'the per-call escalation policy; a per-program copy would let a program grant itself a lower class than the roster''s');

-- Returns {risk_class, rule}. `p_digest` is the runtime's canonicalisation, and
-- `host_in_scope` is stamped into it by `park_gate()` below from ticket 26's
-- projection -- never from anything the call claims.
CREATE FUNCTION assess_call_risk(p_tool text, p_digest jsonb)
RETURNS jsonb LANGUAGE plpgsql STABLE AS $fn$
DECLARE
    base text := resolve_risk_class(p_tool);
    rule text := 'tool_risk_classes:' || coalesce(resolve_risk_class_pattern(p_tool), '?');
    qc   text := 'policy_unclear';   -- the static floor asks, but names no reason
    r    call_risk_rules%ROWTYPE;
    v    jsonb;
    hit  boolean;
BEGIN
    IF base IS NULL THEN
        RAISE EXCEPTION 'no risk class resolves for tool %', p_tool;
    END IF;
    FOR r IN SELECT * FROM call_risk_rules ORDER BY rule_id LOOP
        CONTINUE WHEN NOT (p_tool = r.tool_pattern
                           OR (r.tool_pattern LIKE '%*'
                               AND p_tool LIKE replace(r.tool_pattern,'*','%')));
        v := p_digest -> r.fact;
        hit := CASE r.op
                 WHEN 'in'       THEN (v #>> '{}') = ANY (r.fact_values)
                 WHEN 'not_in'   THEN v IS NOT NULL AND NOT ((v #>> '{}') = ANY (r.fact_values))
                 WHEN 'is_false' THEN v = 'false'::jsonb
               END;
        -- one-way: a rule may raise the class, never lower it
        IF coalesce(hit, false) AND risk_rank(r.escalate_to) > risk_rank(base) THEN
            base := r.escalate_to;
            rule := 'call_risk_rules:' || r.rule_id;
            qc   := r.question_code;
        END IF;
    END LOOP;
    RETURN jsonb_build_object('risk_class', base, 'rule', rule, 'question_code', qc);
END $fn$;

-- The floor, as a constraint. `tool_runs.risk_class` is the only place a class
-- is ever written down, and this is what makes "the model can only make it
-- worse" true of the table rather than of the code that writes to it.
CREATE FUNCTION assert_risk_class_monotone() RETURNS trigger
LANGUAGE plpgsql AS $fn$
DECLARE floor_class text;
BEGIN
    IF NEW.risk_class IS NULL THEN RETURN NEW; END IF;
    floor_class := resolve_risk_class(NEW.tool);
    IF floor_class IS NOT NULL AND risk_rank(NEW.risk_class) < risk_rank(floor_class) THEN
        RAISE EXCEPTION
            'risk_class % is below the % floor tool_risk_classes gives %',
            NEW.risk_class, floor_class, NEW.tool
            USING ERRCODE = '23514',
                  HINT = 'the static class is a floor; a per-call rule may only escalate';
    END IF;
    IF TG_OP = 'UPDATE' AND OLD.risk_class IS NOT NULL
       AND risk_rank(NEW.risk_class) < risk_rank(OLD.risk_class) THEN
        RAISE EXCEPTION 'risk_class cannot be lowered from % to %',
            OLD.risk_class, NEW.risk_class USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $fn$;

CREATE TRIGGER tool_runs_risk_class_monotone
    BEFORE INSERT OR UPDATE ON tool_runs
    FOR EACH ROW EXECUTE FUNCTION assert_risk_class_monotone();


-- ===========================================================================
-- 4. The table
-- ===========================================================================
--
-- Ticket 12 created the stub -- id, program_id, task_id, question_code,
-- question, created_at, answered_at, answer -- to have something to declare
-- write-only. It is extended here rather than replaced: `question_code` is a
-- real taxonomy and it is kept, and `call_risk_rules` now has to name one, so
-- every escalation reaches the operator already classified.

ALTER TABLE pending_decisions
    -- what asked. `task_id` was already NOT NULL in the stub; the run and the
    -- receipt are added because a decision with no receipt is not evidence of
    -- anything, and one with no run cannot say whose lease was released.
    ADD COLUMN agent_run_id     uuid NOT NULL,
    ADD COLUMN tool_run_id      uuid NOT NULL,
    ADD COLUMN label            text NOT NULL,

    -- what is being approved
    ADD COLUMN tool             text NOT NULL,
    ADD COLUMN risk_class       text NOT NULL REFERENCES risk_classes(risk_class),
    ADD COLUMN risk_rule        text NOT NULL,   -- the ROW that decided, not just the verdict
    ADD COLUMN request_digest   jsonb NOT NULL,
    ADD COLUMN equivalence_key  text NOT NULL,

    -- the clock, rule 4
    ADD COLUMN deadline_at      timestamptz NOT NULL,

    -- the answer
    ADD COLUMN status           text NOT NULL DEFAULT 'pending'
                                CHECK (status IN ('pending','approved','denied','expired')),
    ADD COLUMN actor_kind       text CHECK (actor_kind IN ('human','runtime')),
    ADD COLUMN answered_by      text,   -- session_user of the answering connection
    -- NULL = one-shot. Set only on approval, and only by answer_decision().
    ADD COLUMN grant_expires_at timestamptz;

-- what the human reads. Rendered by the runtime from the digest: if the agent
-- supplied this string it would be authoring the prompt the human answers,
-- which is the whole attack the control surface exists to stop.
ALTER TABLE pending_decisions ALTER COLUMN question SET NOT NULL;

ALTER TABLE pending_decisions
    ADD CONSTRAINT pending_decisions_program_id_label_key UNIQUE (program_id, label),

    ADD CONSTRAINT pending_decisions_answer_complete CHECK (
        ((status = 'pending') = (answered_at IS NULL)) AND
        ((status = 'pending') = (actor_kind  IS NULL)) AND
        ((status = 'pending') = (answered_by IS NULL))),
    -- approved/denied are human verdicts by definition; only expiry is the
    -- runtime's, and only the runtime may write it.
    ADD CONSTRAINT pending_decisions_verdict_actor CHECK (
        CASE status WHEN 'pending' THEN actor_kind IS NULL
                    WHEN 'expired' THEN actor_kind = 'runtime'
                    ELSE actor_kind = 'human' END),
    ADD CONSTRAINT pending_decisions_grant_needs_approval CHECK (
        grant_expires_at IS NULL OR status = 'approved'),
    ADD CONSTRAINT pending_decisions_deadline_after_request CHECK (deadline_at > created_at),
    -- Rule 3, as a constraint. Ticket 13 added `forbidden` because "always
    -- escalate" puts a human in the loop for calls already refused; this is that
    -- decision made unwritable rather than merely documented.
    ADD CONSTRAINT pending_decisions_never_forbidden CHECK (risk_class <> 'forbidden'),
    ADD CONSTRAINT pending_decisions_key_matches_digest CHECK (
        equivalence_key = equivalence_key(request_digest)),

    ADD CONSTRAINT pending_decisions_agent_run_id_fkey
        FOREIGN KEY (agent_run_id, program_id) REFERENCES agent_runs (id, program_id),
    ADD CONSTRAINT pending_decisions_tool_run_id_fkey
        FOREIGN KEY (tool_run_id, program_id)  REFERENCES tool_runs  (id, program_id);

CREATE INDEX pending_decisions_open_idx
    ON pending_decisions (program_id, deadline_at) WHERE status = 'pending';
CREATE INDEX pending_decisions_grant_idx
    ON pending_decisions (program_id, equivalence_key) WHERE status = 'approved';

INSERT INTO label_prefixes (kind, prefix) VALUES ('pending_decisions', 'D');
CREATE TRIGGER pending_decisions_assign_label
    BEFORE INSERT ON pending_decisions
    FOR EACH ROW EXECUTE FUNCTION assign_label();

-- ticket 12 already registered this edge when it created the stub
INSERT INTO purge_cascade_edges (table_name, column_name, rationale)
VALUES ('pending_decisions', 'program_id', 'program-scoped: the purge root')
ON CONFLICT (table_name, column_name) DO NOTHING;

-- The two foreign keys the siblings left as comments. Ticket 08 wrote
-- "FK added by ticket 28" on `tasks.pending_decision_id`; ticket 13 wrote
-- "28 adds the constraint, once it says who may resolve one" on
-- `tool_runs.pending_decision_id`. Both are NO ACTION, which is what lets a
-- whole-program purge delete parent and child in one statement.
ALTER TABLE tasks ADD CONSTRAINT tasks_pending_decision_id_fkey
    FOREIGN KEY (pending_decision_id, program_id)
    REFERENCES pending_decisions (id, program_id);

ALTER TABLE tool_runs ADD CONSTRAINT tool_runs_pending_decision_id_fkey
    FOREIGN KEY (pending_decision_id, program_id)
    REFERENCES pending_decisions (id, program_id);

-- Ticket 08 gave `tasks` a `parked` status and a `pending_decision_id` column
-- and never tied them together. A parked task that names no decision is a task
-- nothing will ever un-park.
ALTER TABLE tasks ADD CONSTRAINT tasks_parked_names_a_decision
    CHECK (status <> 'parked' OR pending_decision_id IS NOT NULL);

-- Ticket 08's `abandoned_reason` enum could not tell a human "no" from a human
-- silence: both would have landed on `decision_timeout` or on `answered`.
-- Ticket 16 needs those apart -- one is a policy signal, the other is an
-- operator-availability signal.
ALTER TABLE tasks DROP CONSTRAINT tasks_abandoned_reason_check;
ALTER TABLE tasks ADD CONSTRAINT tasks_abandoned_reason_check
    CHECK (abandoned_reason IN (
        'out_of_scope','superseded','answered','attempts_exhausted',
        'program_closed','budget_exhausted','near_duplicate',
        'decision_timeout','decision_denied'));

CREATE FUNCTION render_decision_question(p_digest jsonb, p_risk text, p_rule text)
RETURNS text LANGUAGE sql IMMUTABLE AS $$
    SELECT format('[%s] %s %s%s (identity %s) -- %s',
                  p_risk,
                  coalesce(p_digest ->> 'method', p_digest ->> 'tool'),
                  coalesce(p_digest ->> 'host', ''),
                  coalesce(p_digest ->> 'path_template', ''),
                  coalesce(nullif(p_digest ->> 'identity_slot',''), 'none'),
                  p_rule);
$$;

-- The question is a projection of the digest, so it cannot say anything the
-- runtime did not derive. A persuasive sentence has nowhere to live.
CREATE FUNCTION assert_question_is_rendered() RETURNS trigger
LANGUAGE plpgsql AS $fn$
BEGIN
    IF NEW.question IS DISTINCT FROM
       render_decision_question(NEW.request_digest, NEW.risk_class, NEW.risk_rule) THEN
        RAISE EXCEPTION
            'pending_decisions.question is not the rendering of its own digest'
            USING ERRCODE = '23514',
                  HINT = 'the human reads a runtime projection, never model prose';
    END IF;
    RETURN NEW;
END $fn$;

CREATE TRIGGER pending_decisions_question_rendered
    BEFORE INSERT OR UPDATE ON pending_decisions
    FOR EACH ROW EXECUTE FUNCTION assert_question_is_rendered();

-- One legal update, so the semantic event name below cannot drift.
CREATE FUNCTION assert_decision_closes_once() RETURNS trigger
LANGUAGE plpgsql AS $fn$
BEGIN
    IF OLD.status <> 'pending' THEN
        RAISE EXCEPTION 'decision % is already %', OLD.label, OLD.status
            USING ERRCODE = '23514';
    END IF;
    IF NEW.status = 'pending' THEN
        RAISE EXCEPTION 'the only legal update to a pending decision is closing it'
            USING ERRCODE = '23514';
    END IF;
    IF (NEW.id, NEW.program_id, NEW.label, NEW.equivalence_key, NEW.request_digest,
        NEW.deadline_at, NEW.tool_run_id)
       IS DISTINCT FROM
       (OLD.id, OLD.program_id, OLD.label, OLD.equivalence_key, OLD.request_digest,
        OLD.deadline_at, OLD.tool_run_id) THEN
        RAISE EXCEPTION 'the request half of decision % is immutable', OLD.label
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $fn$;

CREATE TRIGGER pending_decisions_closes_once
    BEFORE UPDATE ON pending_decisions
    FOR EACH ROW EXECUTE FUNCTION assert_decision_closes_once();

CREATE TRIGGER pending_decisions_no_delete
    BEFORE DELETE ON pending_decisions
    FOR EACH ROW EXECUTE FUNCTION reject_mutation_unless_purging();


-- ===========================================================================
-- 5. The notification path (Q6: local only)
-- ===========================================================================
--
-- LISTEN/NOTIFY is the low-latency hint and is NOT the delivery guarantee: a
-- notification raised while nothing is listening is gone, and "the runtime may
-- itself be aborted" is a standing constraint, not an edge case. So the durable
-- part is an outbox row, and the dispatcher is a reader of that table.
--
-- The channel is an operator-supplied argv, executed with no shell. That single
-- `execve` is the whole untested surface: everything on either side of it --
-- fan-out, retry, backoff, the delivered stamp, the placeholder whitelist -- is
-- in the database and runs in tests/checks.sql.

CREATE TABLE notification_channels (
    channel      text PRIMARY KEY,
    argv         text[] NOT NULL,
    enabled      boolean NOT NULL DEFAULT true,
    max_attempts smallint NOT NULL DEFAULT 5 CHECK (max_attempts > 0),
    backoff      interval NOT NULL DEFAULT interval '30 seconds',
    rationale    text NOT NULL
);

INSERT INTO program_global_tables (table_name, reason) VALUES
    ('notification_channels',
     'operator configuration of the machine, not of a program: a program that could add a channel could exfiltrate its own decisions');

INSERT INTO notification_channels (channel, argv, enabled, rationale) VALUES
    ('desktop', ARRAY['notify-send','redKrakenV2 {label}','{body}'], true,
     'Q6 is local-only, so the default reaches a human who IS at the machine'),
    ('push',    ARRAY[]::text[], false,
     'the only part of this design that leaves the machine, and the only part that cannot be tested here: an operator-supplied argv (ntfy, Pushover, an SSH-triggered script). Disabled until an operator fills it in, because an empty argv silently delivering nothing is worse than a channel that says it is off');

-- A placeholder outside this set would let a channel interpolate something the
-- runtime never intended to send.
CREATE FUNCTION assert_channel_placeholders() RETURNS trigger
LANGUAGE plpgsql AS $fn$
DECLARE bad text;
BEGIN
    SELECT string_agg(ph, ',') INTO bad
      FROM (SELECT DISTINCT (regexp_matches(a, '\{[a-z_]+\}', 'g'))[1] AS ph
              FROM unnest(NEW.argv) a) x
     WHERE ph NOT IN ('{label}','{body}','{deadline}');
    IF bad IS NOT NULL THEN
        RAISE EXCEPTION 'channel % uses unknown placeholder(s) %', NEW.channel, bad
            USING ERRCODE = '23514';
    END IF;
    IF NEW.enabled AND cardinality(NEW.argv) = 0 THEN
        RAISE EXCEPTION 'channel % is enabled with an empty argv', NEW.channel
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $fn$;

CREATE TRIGGER notification_channels_placeholders
    BEFORE INSERT OR UPDATE ON notification_channels
    FOR EACH ROW EXECUTE FUNCTION assert_channel_placeholders();

CREATE TABLE decision_notifications (
    id                  uuid NOT NULL DEFAULT uuidv7(),
    program_id          uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    pending_decision_id uuid NOT NULL,
    channel             text NOT NULL REFERENCES notification_channels(channel),
    body                text NOT NULL,
    attempts            smallint NOT NULL DEFAULT 0,
    next_attempt_at     timestamptz NOT NULL DEFAULT now(),
    delivered_at        timestamptz,
    last_error          text,
    created_at          timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (id),
    UNIQUE (id, program_id),
    UNIQUE (pending_decision_id, channel),
    CONSTRAINT decision_notifications_pending_decision_id_fkey
        FOREIGN KEY (pending_decision_id, program_id)
        REFERENCES pending_decisions (id, program_id)
);

INSERT INTO purge_cascade_edges (table_name, column_name, rationale)
VALUES ('decision_notifications', 'program_id', 'program-scoped: the purge root')
ON CONFLICT (table_name, column_name) DO NOTHING;

CREATE FUNCTION fan_out_decision_notification() RETURNS trigger
LANGUAGE plpgsql AS $fn$
BEGIN
    INSERT INTO decision_notifications (program_id, pending_decision_id, channel, body)
    SELECT NEW.program_id, NEW.id, c.channel, NEW.question
      FROM notification_channels c WHERE c.enabled;
    PERFORM pg_notify('rk2_decision',
                      json_build_object('label', NEW.label,
                                        'deadline_at', NEW.deadline_at)::text);
    RETURN NEW;
END $fn$;

CREATE TRIGGER pending_decisions_notify
    AFTER INSERT ON pending_decisions
    FOR EACH ROW EXECUTE FUNCTION fan_out_decision_notification();

-- What the dispatcher claims: rows that are due, with attempts left, on an
-- enabled channel, for a decision still open. A decision answered before the
-- notification went out does not get sent.
CREATE FUNCTION due_notifications(p_program uuid DEFAULT NULL)
RETURNS TABLE (notification_id uuid, label text, body text, deadline_at timestamptz,
               channel text, argv text[])
LANGUAGE sql STABLE AS $$
    SELECT n.id, d.label, n.body, d.deadline_at, c.channel, c.argv
      FROM decision_notifications n
      JOIN pending_decisions d ON d.id = n.pending_decision_id
      JOIN notification_channels c ON c.channel = n.channel
     WHERE n.delivered_at IS NULL
       AND n.next_attempt_at <= now()
       AND n.attempts < c.max_attempts
       AND c.enabled
       AND d.status = 'pending'
       AND (p_program IS NULL OR n.program_id = p_program)
     ORDER BY n.next_attempt_at, n.id;
$$;

CREATE FUNCTION record_notification_attempt(p_id uuid, p_ok boolean, p_error text DEFAULT NULL)
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    PERFORM set_actor('runtime');
    UPDATE decision_notifications n
       SET attempts        = n.attempts + 1,
           delivered_at    = CASE WHEN p_ok THEN now() ELSE NULL END,
           last_error      = CASE WHEN p_ok THEN NULL ELSE p_error END,
           next_attempt_at = now() + (n.attempts + 1) *
                             (SELECT backoff FROM notification_channels c WHERE c.channel = n.channel)
     WHERE n.id = p_id;
END $$;


-- ===========================================================================
-- 6. Park, answer, expire
-- ===========================================================================

-- The gate the PreToolUse hook calls. Returns the verdict, and -- because ticket
-- 13 settled that a park and a refusal are the same wire shape -- the caller
-- gets `deny` plus a reason in both cases and cannot tell them apart. Only the
-- record separates them: `parked` + a decision row, or `denied`.
--
-- `host_in_scope` is stamped in here, from ticket 26's projection, over
-- whatever the digest already had. That is the point: an escalating fact is
-- resolved from committed state at gate time, never carried in by the call.
CREATE FUNCTION gate_tool_call(p_tool_run_id uuid) RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    tr      tool_runs%ROWTYPE;
    digest  jsonb;
    verdict jsonb;
    grant_l text;
    raw     text[];
    sclass  text;
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

-- Ticket 08 decision 13, executed. Parking ENDS the run: a blocked SDK session
-- would hold a lane slot and an identity lease for hours while Q4 asks for
-- multi-hour unattended runs.
--
-- `lease_expires_at` is nulled, and that is not tidiness. Ticket 08 ties the
-- identity lease to the task lease deliberately, so that one clock governs both;
-- a parked task that kept a live `lease_expires_at` would be swept back to
-- `pending` by `sweep_expired_leases()` and re-claimed while a human was still
-- reading the question. While parked there is no lease at all, so the deadline
-- is the only clock -- which is exactly the "two clocks" failure ticket 08
-- warned about, avoided by having one fewer, not one more.
CREATE FUNCTION park_for_human(p_tool_run_id uuid, p_ttl interval DEFAULT interval '4 hours')
RETURNS text LANGUAGE plpgsql AS $fn$
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

    -- the run ends, the lane slot frees
    UPDATE agent_runs SET finished_at = now(), stop_reason = 'parked', result = NULL
     WHERE id = tr.agent_run_id AND finished_at IS NULL;

    DELETE FROM agent_sessions s WHERE s.agent_run_id = tr.agent_run_id;

    UPDATE identity_leases SET released_at = now()
     WHERE holder_agent_run_id = tr.agent_run_id AND released_at IS NULL;

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
    UPDATE tasks SET status = 'parked', pending_decision_id = d.id,
                     lease_expires_at = NULL, claimed_at = NULL, priority = NULL
     WHERE id = tr.task_id;

    RETURN d.label;
END $fn$;

-- Who may resolve one, which is the question ticket 13 handed here. Two
-- independent gates, on purpose: the EXECUTE grant below (only `rk2_human`) and
-- the actor-kind trigger (which reads `session_user`, so SECURITY DEFINER does
-- not launder it). Removing either one leaves the other standing.
CREATE FUNCTION answer_decision(p_label text, p_verdict text, p_reason text,
                                p_grant interval DEFAULT interval '24 hours')
RETURNS jsonb SECURITY DEFINER LANGUAGE plpgsql AS $fn$
DECLARE d pending_decisions%ROWTYPE;
BEGIN
    IF p_verdict NOT IN ('approved','denied') THEN
        RAISE EXCEPTION 'verdict must be approved or denied, got %', p_verdict;
    END IF;
    PERFORM set_actor('human', session_user);

    SELECT * INTO d FROM pending_decisions WHERE label = p_label FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'no decision %', p_label; END IF;

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

REVOKE ALL ON FUNCTION answer_decision(text,text,text,interval) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION answer_decision(text,text,text,interval) TO rk2_human;

-- Rule 4. The deadline is evaluated here and nowhere else, from a stored
-- column, so a runtime that died at any point during the countdown reaches the
-- same state when it comes back as one that stayed up.
CREATE FUNCTION expire_due_decisions(p_program uuid DEFAULT NULL) RETURNS bigint
LANGUAGE plpgsql AS $fn$
DECLARE n bigint;
BEGIN
    PERFORM set_actor('runtime');

    WITH due AS (
        UPDATE pending_decisions d
           SET status = 'expired', actor_kind = 'runtime', answered_at = now(),
               answered_by = 'runtime',
               answer = 'deadline passed with no human answer'
         WHERE d.status = 'pending' AND d.deadline_at <= now()
           AND (p_program IS NULL OR d.program_id = p_program)
        RETURNING d.id, d.task_id
    ), retired AS (
        UPDATE tasks t
           SET status = 'abandoned', abandoned_reason = 'decision_timeout',
               finished_at = now(), pending_decision_id = NULL, priority = NULL
          FROM due WHERE t.id = due.task_id
        RETURNING t.id
    )
    SELECT count(*) INTO n FROM due;
    RETURN n;
END $fn$;

-- Ticket 13's body, plus one line. `resume_program()` is the single path Q29
-- gives every abort -- rate limit, crash, kill, operator stop -- so the deadline
-- sweep belongs in it rather than in a sixth thing someone has to remember to
-- call. Parked tasks are untouched by the rest of the body (it keys on
-- 'claimed'/'running'), which is correct: a parked task inside its deadline
-- survives the restart.
CREATE OR REPLACE FUNCTION resume_program(p_program uuid) RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    n_tasks bigint; n_runs bigint; n_leases bigint;
    n_hyp bigint; n_recs bigint; n_bind bigint; n_dec bigint;
BEGIN
    PERFORM set_actor('runtime');

    n_dec  := expire_due_decisions(p_program);
    n_recs := sweep_open_receipts(p_program);

    UPDATE tasks SET status = 'pending', claimed_at = NULL, priority = NULL
     WHERE program_id = p_program AND status IN ('claimed','running');
    GET DIAGNOSTICS n_tasks = ROW_COUNT;

    UPDATE agent_runs
       SET finished_at = now(), stop_reason = 'aborted', result = NULL
     WHERE program_id = p_program AND finished_at IS NULL;
    GET DIAGNOSTICS n_runs = ROW_COUNT;

    DELETE FROM agent_sessions s
     WHERE s.program_id = p_program
       AND EXISTS (SELECT 1 FROM agent_runs r
                    WHERE r.id = s.agent_run_id AND r.finished_at IS NOT NULL);
    GET DIAGNOSTICS n_bind = ROW_COUNT;

    UPDATE identity_leases SET released_at = now()
     WHERE program_id = p_program AND released_at IS NULL;
    GET DIAGNOSTICS n_leases = ROW_COUNT;

    INSERT INTO hypothesis_transitions
        (program_id, hypothesis_id, from_status, to_status, actor_kind, rationale)
    SELECT p_program, h.id, 'testing', 'testable', 'runtime',
           'runtime abort: test did not complete'
      FROM hypotheses h
     WHERE h.program_id = p_program AND h.status = 'testing';
    GET DIAGNOSTICS n_hyp = ROW_COUNT;

    RETURN jsonb_build_object('tasks_unclaimed', n_tasks,
                              'agent_runs_aborted', n_runs,
                              'leases_released', n_leases,
                              'hypotheses_returned_to_testable', n_hyp,
                              'tool_receipts_abandoned', n_recs,
                              'session_bindings_dropped', n_bind,
                              'decisions_expired', n_dec);
END $fn$;


-- ===========================================================================
-- 7. The catalogue moves with the table (ticket 07)
-- ===========================================================================
--
-- `decision.requested` / `decision.answered` were occurrence events because no
-- table existed to hang them on. One exists now, so they become row events and
-- a trigger writes them -- ticket 07 decision 9: completeness that depends on
-- every call site remembering is the convention this schema rejects everywhere
-- else, and a human decision is the last place to make an exception.
--
-- Decision 15 says generic names for mutable tables, semantic names only for
-- immutable ones, and this table is mutable. The names stay semantic anyway,
-- and `assert_decision_closes_once()` is why: `pending_decisions` has exactly
-- one legal update, pending -> closed, so `decision.answered` cannot drift from
-- what the delta says the way `task.claimed` could. The rule is really
-- "generic, unless the table has exactly one legal transition and a trigger
-- that says so".
UPDATE event_types
   SET family = 'row', subject_table = 'pending_decisions',
       description = 'human consultation opened (Q9): one pending_decisions row'
 WHERE id = 'decision.requested';

UPDATE event_types
   SET family = 'row', subject_table = 'pending_decisions',
       description = 'human consultation closed: answered by a human or expired by the runtime'
 WHERE id = 'decision.answered';

INSERT INTO event_table_config
    (table_name, created_type, updated_type, ignored_columns, redacted_columns)
VALUES ('pending_decisions', 'decision.requested', 'decision.answered', '{}', '{}');

SELECT attach_event_triggers();


-- ===========================================================================
-- 8. Privileges and RLS
-- ===========================================================================

GRANT SELECT, INSERT, UPDATE, DELETE ON pending_decisions, decision_notifications
    TO rk2_runtime;
GRANT SELECT ON call_risk_rules, notification_channels TO rk2_runtime;

-- `rk2_human` gets exactly one verb: answering. It reads the queue through a
-- view and writes through `answer_decision()`. No table write privilege at all,
-- so an operator console bug cannot rewrite the question it was asked.
CREATE VIEW v_decision_queue WITH (security_invoker = true) AS
    SELECT d.label, d.tool, d.risk_class, d.risk_rule, d.question_code, d.question,
           d.created_at AS requested_at, d.deadline_at, d.status, d.answered_by, d.answer,
           d.request_digest
      FROM pending_decisions d;

GRANT SELECT ON v_decision_queue TO rk2_human, rk2_runtime;
GRANT SELECT ON pending_decisions TO rk2_human;

-- `rk2_state` is granted nothing here. Ticket 12 already listed
-- `pending_decisions` among the write-only channels an agent must not read,
-- "since ticket 11 requires park_for_human not to re-enter any agent's
-- context". An agent that can read the decision queue can read the question it
-- caused and tune the next one.
REVOKE ALL ON pending_decisions, decision_notifications, call_risk_rules,
              notification_channels, v_decision_queue FROM rk2_state;

DO $$
DECLARE f text;
BEGIN
    FOREACH f IN ARRAY ARRAY[
        'gate_tool_call(uuid)', 'park_for_human(uuid,interval)',
        'expire_due_decisions(uuid)', 'assess_call_risk(text,jsonb)',
        'canonical_request(text,jsonb,text)', 'equivalence_key(jsonb)',
        'due_notifications(uuid)', 'record_notification_attempt(uuid,boolean,text)',
        'attach_actor_kind_guards()']
    LOOP
        EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC', f);
        EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO rk2_runtime', f);
    END LOOP;
END $$;

-- 020's own rule, re-run for the tables created since. Same loop 023 used.
DO $$
DECLARE t text;
BEGIN
    FOR t IN
        SELECT c.relname FROM pg_class c
         WHERE c.relkind = 'r' AND c.relnamespace = 'public'::regnamespace
           AND EXISTS (SELECT 1 FROM pg_attribute a
                        WHERE a.attrelid = c.oid AND a.attname = 'program_id'
                          AND a.attnum > 0 AND NOT a.attisdropped)
           AND c.relname NOT IN (SELECT table_name FROM program_global_tables)
           AND NOT c.relrowsecurity
         ORDER BY c.relname
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format(
            'CREATE POLICY %I ON %I AS PERMISSIVE FOR ALL TO rk2_state '
            'USING (program_id = rk2_program()) WITH CHECK (program_id = rk2_program())',
            t || '_rk2_state', t);
        EXECUTE format(
            'CREATE POLICY %I ON %I AS PERMISSIVE FOR ALL TO rk2_runtime '
            'USING (true) WITH CHECK (true)', t || '_rk2_runtime', t);
        RAISE NOTICE 'control-surface: enabled RLS on % (created after migration 020)', t;
    END LOOP;
END $$;

CREATE POLICY pending_decisions_rk2_human ON pending_decisions
    AS PERMISSIVE FOR ALL TO rk2_human USING (true) WITH CHECK (true);

SELECT attach_actor_kind_guards();

-- 016's N1 sweep, re-run so every trigger this migration created fires under
-- `session_replication_role = replica` too.
DO $$
DECLARE r record;
BEGIN
    FOR r IN
        SELECT c.relname AS tbl, t.tgname
          FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid
         WHERE NOT t.tgisinternal
           AND c.relnamespace = 'public'::regnamespace
           AND t.tgenabled <> 'A'
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ALWAYS TRIGGER %I', r.tbl, r.tgname);
    END LOOP;
END $$;


-- ===========================================================================
-- 9. The standing check
-- ===========================================================================

CREATE FUNCTION check_control_surface()
RETURNS TABLE (problem text, detail text) LANGUAGE sql STABLE AS $fn$
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
    -- rule 5: a grant with no live approval behind it
    SELECT 'grant_without_approval', d.label
      FROM pending_decisions d
     WHERE d.grant_expires_at IS NOT NULL AND d.status <> 'approved'
UNION ALL
    -- the agent connection must not reach the decision queue
    SELECT 'decision_queue_reachable_by_agent', table_name || '.' || privilege_type
      FROM information_schema.table_privileges
     WHERE grantee = 'rk2_state'
       AND table_name IN ('pending_decisions','decision_notifications',
                          'call_risk_rules','notification_channels','v_decision_queue')
UNION ALL
    -- an enabled channel with an empty argv delivers nothing, silently
    SELECT 'enabled_channel_delivers_nothing', c.channel
      FROM notification_channels c
     WHERE c.enabled AND cardinality(c.argv) = 0
$fn$;

DO $$
DECLARE n bigint; d text;
BEGIN
    SELECT count(*), string_agg(problem || ' ' || detail, ', ')
      INTO n, d FROM check_control_surface();
    IF n > 0 THEN
        RAISE EXCEPTION 'check_control_surface() reports % problem(s): %', n, d;
    END IF;
    RAISE NOTICE 'control-surface: check_control_surface() is silent';
END $$;
