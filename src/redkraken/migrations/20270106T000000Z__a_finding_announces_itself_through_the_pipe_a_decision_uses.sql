-- ---------------------------------------------------------------------------
-- 20270106T000000Z__a_finding_announces_itself_through_the_pipe_a_decision_uses.sql
--
-- Two tickets, one file, and the reason they are one file is mechanical rather
-- than tidy: both rewrite `check_control_surface`, and a migration replaces a
-- function WHOLE. Two files would mean the second silently discarding the
-- first, with no error raised anywhere.
--
--   * ticket 228, wall 1 (`T228-01`). The `decision_unannounced` refusal named
--     the question and not the notifier. On 2026-08-30 the harness refused
--     every `rk run` and every `rk db migrate` with
--     `2 problem(s): (decision_unannounced,D27); (decision_unannounced,D28)`,
--     and four levels down the fact that ended the investigation was already
--     sitting in `decision_notifications.last_error`:
--     `GDBus.Error:org.freedesktop.DBus.Error.ServiceUnknown`. Written by
--     `record_notification_attempt`, read by nothing that refuses. It is read
--     now.
--
--   * ticket 229 (`T229-01`), option (b) as the ticket recommends. A Finding
--     had no notifier in this repository at all: the only one was
--     `notify.sh` in an engagement directory, which queries the database
--     itself, curls itself, dedups in its own `out/notified.txt`, and does not
--     travel. Measured the same day: `notified.txt` 0 lines, the notify log
--     empty. Meanwhile the decision pipe -- outbox, fan-out, retry, backoff,
--     attempt ceiling, placeholder whitelist, no-shell executor with a timeout,
--     and a sweep that already runs once per lap at `hunt.sh:70` -- was built,
--     in production, and carrying exactly one subject.
--
-- WHY (b) AND NOT (a) OR (c), in one line each, because the ticket prices all
-- three and the choice is load-bearing. (a) one generalised `notifications`
-- table is the better end state and needs a backfill of 30 live rows on a
-- database in the middle of a hunt, for a third subject that does not exist.
-- (c) a nullable discriminator on `decision_notifications` weakens the
-- composite FK that is the whole reason a notification is provably about a
-- decision of the same Program, and would leave the `decision_unannounced` arm
-- passing by accident because its subqueries key on a column that had become
-- NULL. (b) changes no function signature, therefore no `runtime_verb_surface`
-- row for an existing verb, and therefore not one line of Python:
-- `src/redkraken/decisions.py` selects `notification_id, label, body, channel,
-- to_json(argv)` by name and never reads `deadline_at`.
--
-- ONE DEFECT FOUND ON THE WAY AND FIXED HERE, because 228 wall 1 cannot land
-- without it: `check_control_surface`'s first arm returned `pg_class.relname`,
-- which is `name`, and UNION type resolution takes the first branch's type. So
-- EVERY `detail` this function returned, from every arm, was silently cut to 63
-- characters. It has never shown because every detail so far has been a label.
-- Two `::text` casts, at the two arms that produce a `name`. Reported in the
-- arm's own comment rather than only here.
--
-- THE ENDPOINT IS NOT IN HERE AND NEVER WILL BE. A push topic is a bearer
-- secret: whoever knows it can read and publish. It lives in
-- `notification_channels.argv` on the operator's own row, which is why that
-- table is in `program_global_tables` -- "a program that could add a channel
-- could exfiltrate its own decisions". This file seeds no URL, no host, no
-- topic and no default for one.
-- ---------------------------------------------------------------------------


-- ===========================================================================
-- 1. The floor, on the table that already holds the rest of channel policy
-- ===========================================================================
-- `notify.sh` kept this in `RK_NOTIFY_MIN`, an env var in a directory that is
-- not a git repository. It belongs beside `enabled`, `max_attempts` and
-- `backoff`, which are the other three things an operator tunes about a channel
-- without a migration -- D-10 disabled `desktop` on the live host with a plain
-- UPDATE, and this is the same kind of knob.
--
-- Per channel rather than global because the two channels want different
-- things: a desktop toast for every banded Finding is free, a push to somebody's
-- phone for every `low` is spam. The default is `medium`, which is the floor the
-- shell script used and the band SPEC condition 2 is about.
--
-- The order comes from `rk2_severity_rank`, which is the corpus's one ordering
-- of the five bands. A CHECK that re-listed them here would be a second
-- spelling, and a second spelling is a second answer.
ALTER TABLE notification_channels
    ADD COLUMN min_severity text NOT NULL DEFAULT 'medium'
        CONSTRAINT notification_channels_min_severity_is_a_band
        CHECK (rk2_severity_rank(min_severity) IS NOT NULL);

COMMENT ON COLUMN notification_channels.min_severity IS
  'the lowest Finding severity this channel is told about, ordered by rk2_severity_rank; a decision is not filtered by it, because a question the runtime cannot answer has no band';


-- ===========================================================================
-- 2. The sibling outbox
-- ===========================================================================
-- Shaped on `decision_notifications` (`0026_human_control.sql:576`) field for
-- field, with `finding_id` where that table has `pending_decision_id` and the
-- same composite-FK discipline: a notification is provably about a Finding of
-- the same Program, and that is a constraint rather than a convention.
--
-- WHAT IT DELIBERATELY DOES NOT DO. `UNIQUE (finding_id, channel)` means a
-- Finding restated from `medium` to `critical` does not produce a second
-- announcement -- the fan-out is ON CONFLICT DO NOTHING. That is the sibling's
-- behaviour (`UNIQUE (pending_decision_id, channel)`) and it is the cheap side
-- of a real trade: an operator is told once that a Finding crossed the floor,
-- and is not told again when it is sharpened. Re-announcing a restatement is a
-- second subject with its own dedup rule and it is not what this ticket buys.
CREATE TABLE finding_notifications (
    id              uuid NOT NULL DEFAULT uuidv7(),
    program_id      uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    finding_id      uuid NOT NULL,
    channel         text NOT NULL REFERENCES notification_channels(channel),
    body            text NOT NULL,
    attempts        smallint NOT NULL DEFAULT 0,
    next_attempt_at timestamptz NOT NULL DEFAULT now(),
    delivered_at    timestamptz,
    last_error      text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (id),
    UNIQUE (id, program_id),
    UNIQUE (finding_id, channel),
    CONSTRAINT finding_notifications_finding_id_fkey
        FOREIGN KEY (finding_id, program_id)
        REFERENCES findings (id, program_id)
);

COMMENT ON TABLE finding_notifications IS
  'the outbox for the second subject the decision pipe carries: one row per enabled channel whose floor a banded Finding reached. Read by due_notifications() and written by record_notification_attempt, both of which carry decisions through the same two verbs.';


-- What a new table owes. Four registrations, each of them enforced by a
-- standing check that halts the harness rather than by anybody remembering.
--
-- Exempt and not emitting, for the sibling's reason, written out at
-- `0030_corpus_corrections.sql:128`: an outbound attempt is audited through its
-- subject. The severity statement is the Event; this row is the record of
-- having tried to tell somebody about it.
INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
    ('finding_notifications', 'audit',
     'outbound notification attempts; the severity statement is the event', '229');

INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
    ('finding_notifications', 'program_id', 'program-scoped: the purge root')
ON CONFLICT (table_name, column_name) DO NOTHING;

-- Four, exactly as `decision_notifications` holds four. The runtime inserts
-- through the fan-out, selects through `due_notifications`, updates through
-- `record_notification_attempt`, and deletes through the purge.
INSERT INTO runtime_table_surface (table_name, privilege, added_by) VALUES
    ('finding_notifications', 'SELECT', '229'),
    ('finding_notifications', 'INSERT', '229'),
    ('finding_notifications', 'UPDATE', '229'),
    ('finding_notifications', 'DELETE', '229')
ON CONFLICT (table_name, privilege) DO NOTHING;

-- The fourth registration, `runtime_verb_surface`, is owed by a verb the
-- runtime may EXECUTE and that is closed to PUBLIC (`runtime_verbs.closed`).
-- `fan_out_finding_notification` is a trigger function reached only through the
-- trigger, exactly like `fan_out_decision_notification`, which holds no row
-- either -- and the two verbs this file replaces keep the rows they already
-- have, `due_notifications(uuid)` and
-- `record_notification_attempt(uuid, boolean, text)`, because a replacement is
-- the same verb. So there is no new row to write here, and `check_runtime_privileges`
-- arm 4 is what would say so if that ever stopped being true.


-- ===========================================================================
-- 3. The fan-out
-- ===========================================================================
-- `state_severity` is the only writer of `findings.severity` and writes one
-- `severity_statements` row per statement, which makes that table the exact
-- counterpart of `pending_decisions` under `fan_out_decision_notification`
-- (`0026_human_control.sql:599`). The seam is the statement, not the Finding:
-- a band is an act somebody performed, and the announcement is about the act.
CREATE FUNCTION fan_out_finding_notification() RETURNS trigger
LANGUAGE plpgsql AS $fn$
BEGIN
    INSERT INTO finding_notifications (program_id, finding_id, channel, body)
    SELECT NEW.program_id, NEW.finding_id, c.channel,
           f.label || ' is ' || NEW.severity || ' (' || NEW.basis || '): ' || f.title
      FROM notification_channels c
      JOIN findings f ON f.id = NEW.finding_id AND f.program_id = NEW.program_id
     WHERE c.enabled
       AND rk2_severity_rank(NEW.severity) >= rk2_severity_rank(c.min_severity)
    ON CONFLICT (finding_id, channel) DO NOTHING;
    RETURN NEW;
END $fn$;

CREATE TRIGGER severity_statements_fan_out_notification
    AFTER INSERT ON severity_statements
    FOR EACH ROW EXECUTE FUNCTION fan_out_finding_notification();


-- ===========================================================================
-- 4. The two verbs, carrying a second subject
-- ===========================================================================
-- The signature does not change, which is the whole of why option (b) was
-- chosen: `runtime_verb_surface` keeps `due_notifications(uuid)` untouched, and
-- `decisions.py` -- which selects `notification_id, label, body, channel,
-- to_json(argv)` by name at `:42-45` and never reads `deadline_at` -- keeps
-- every line it has. `deadline_at` is NULL for a Finding because a Finding has
-- no deadline: nothing retires it in silence if nobody answers, which is the
-- one thing a decision's deadline exists to make dangerous.
--
-- The finding half's status filter and the standing check's status filter below
-- are the SAME predicate, deliberately. A Finding rejected after it was banded
-- must stop being offered AND stop being complained about; two filters that
-- drifted apart would leave a row nothing will ever deliver and a check that
-- refuses the harness for ever.
CREATE OR REPLACE FUNCTION due_notifications(p_program uuid DEFAULT NULL)
RETURNS TABLE (notification_id uuid, label text, body text, deadline_at timestamptz,
               channel text, argv text[])
LANGUAGE sql STABLE AS $$
    SELECT q.notification_id, q.label, q.body, q.deadline_at, q.channel, q.argv
      FROM (
        SELECT n.id AS notification_id, d.label, n.body, d.deadline_at,
               c.channel, c.argv, n.next_attempt_at
          FROM decision_notifications n
          JOIN pending_decisions d ON d.id = n.pending_decision_id
          JOIN notification_channels c ON c.channel = n.channel
         WHERE n.delivered_at IS NULL
           AND n.next_attempt_at <= now()
           AND n.attempts < c.max_attempts
           AND c.enabled
           AND d.status = 'pending'
           AND (p_program IS NULL OR n.program_id = p_program)
        UNION ALL
        SELECT n.id, f.label, n.body, NULL::timestamptz,
               c.channel, c.argv, n.next_attempt_at
          FROM finding_notifications n
          JOIN findings f ON f.id = n.finding_id
          JOIN notification_channels c ON c.channel = n.channel
         WHERE n.delivered_at IS NULL
           AND n.next_attempt_at <= now()
           AND n.attempts < c.max_attempts
           AND c.enabled
           AND f.status IN ('validated', 'reported')
           AND (p_program IS NULL OR n.program_id = p_program)
      ) q
     ORDER BY q.next_attempt_at, q.notification_id;
$$;

-- Two UPDATEs and not a discriminator argument. Both tables key on a `uuidv7()`
-- primary key, so at most one row in the whole database can carry any given id
-- and exactly one of these two statements can ever match -- that is a property
-- of the key generator and it is written down here rather than assumed, because
-- the day it stops being true is the day this function silently stamps two
-- rows. The alternative, a second verb, costs a new `runtime_verb_surface` row
-- AND a change in `decisions.py`, and buys nothing.
CREATE OR REPLACE FUNCTION record_notification_attempt(p_id uuid, p_ok boolean, p_error text DEFAULT NULL)
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
    UPDATE finding_notifications n
       SET attempts        = n.attempts + 1,
           delivered_at    = CASE WHEN p_ok THEN now() ELSE NULL END,
           last_error      = CASE WHEN p_ok THEN NULL ELSE p_error END,
           next_attempt_at = now() + (n.attempts + 1) *
                             (SELECT backoff FROM notification_channels c WHERE c.channel = n.channel)
     WHERE n.id = p_id;
END $$;


-- ===========================================================================
-- 5. The control surface
-- ===========================================================================
-- Replaced WHOLE, which is the corpus idiom for this function: every arm below
-- is the live text except the three named in the comments -- the rewritten
-- `decision_unannounced` (ticket 228 wall 1), the extended
-- `decision_queue_reachable_by_agent` list (ticket 229 hop 8, the hop that is
-- invisible unless somebody walks it) and the two new arms at the end.

CREATE OR REPLACE FUNCTION check_control_surface()
RETURNS TABLE (problem text, detail text)
LANGUAGE sql STABLE AS $fn$
    -- rule 1: every table carrying actor_kind is guarded, and the guard fires
    -- under replica too
    --
    -- `::text` ON THIS ONE COLUMN IS A BUG FIX, and it is the reason ticket 228
    -- wall 1 could not simply be written. `c.relname` is `name`, `name` is 64
    -- bytes, and UNION type resolution takes the FIRST branch's type -- so every
    -- `detail` this function has ever returned, from every arm below, was
    -- silently cut to 63 characters. Nothing noticed because every detail in
    -- the corpus so far has been a label. The refusal 228 asks for is 90
    -- characters and would have arrived as
    -- `D27 -- desktop: exit 1: GDBus.Error:org.freedesktop.DBus.Error.S`,
    -- which is worse than the bare label it replaces: it looks complete.
    -- `human_role_reachable` below is the other `name` and takes the same cast.
    SELECT 'actor_kind_unguarded'::text, c.relname::text
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
    SELECT 'human_role_reachable', r.rolname::text
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
    -- the agent connection must not reach the decision queue.
    --
    -- ticket 229, hop 8. `finding_notifications` is added to this list, and the
    -- list is the reason the hop exists: it is a fixed string list, so a new
    -- outbox is reachable by `rk2_state` with nothing anywhere saying so. The
    -- table takes no `state_read_surface` rows, so `apply_state_grants` grants
    -- it nothing -- and this arm is what proves that stayed true.
    SELECT 'decision_queue_reachable_by_agent', table_name || '.' || privilege_type
      FROM information_schema.table_privileges
     WHERE grantee = 'rk2_state'
       AND table_name IN ('pending_decisions','decision_notifications',
                          'finding_notifications',
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
    --
    -- TICKET 228, WALL 1. The predicate is byte-identical; the DETAIL is what
    -- changed. It used to be `d.label`, so the refusal that stopped the whole
    -- harness on 2026-08-30 read `(decision_unannounced,D27)` -- the name of a
    -- question, when what was broken was a channel. Four levels of digging
    -- later the sentence that ended it was already on the row this arm joins:
    -- `desktop`, five of five attempts, `GDBus.Error:...ServiceUnknown`. It is
    -- read here now, per channel, so the refusal names the notifier.
    --
    -- Clipped at 120 characters because a `detail` is read inside a one-line
    -- refusal. `ERROR_BYTES` already bounds the column at 200 at write time
    -- (`decisions.py`), so this bounds the line rather than the storage. The
    -- channel is marked when it is disabled, because "spent its attempts" and
    -- "somebody turned it off" are two different things to go and do.
    SELECT 'decision_unannounced',
           d.label || ' -- ' || coalesce(
               (SELECT string_agg(
                           n.channel
                           || CASE WHEN c.enabled THEN '' ELSE ' (disabled)' END
                           || ': ' || coalesce(left(n.last_error, 120), 'no error recorded')
                           || ', ' || n.attempts || '/' || c.max_attempts || ' attempts',
                           '; ' ORDER BY n.channel)
                  FROM decision_notifications n
                  JOIN notification_channels c ON c.channel = n.channel
                 WHERE n.pending_decision_id = d.id),
               'fanned out to no channel')
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
UNION ALL
    -- TICKET 229, the state arm. The same sentence as the one above, about the
    -- other subject: a banded Finding the notifier tried to announce, that
    -- reached nobody, and that nothing will try again.
    --
    -- WHAT IT DOES NOT ASSERT, and why not. Not "a validated Finding has an
    -- announcement". Live `rk2here` holds one validated Finding and zero rows
    -- in this table at the moment this file applies, and a standing check that
    -- returns rows refuses every pass -- so that arm would halt the harness on
    -- lap 1 for a Finding that predates the mechanism. `EXISTS (a row for this
    -- Finding)` is what scopes it to Findings the fan-out actually reached, and
    -- it is the same shape ticket 226 used for `check_kill_chains` arm (h): the
    -- state half alone is true on a healthy Program and cannot be the whole arm.
    --
    -- The floor is NOT repeated here. `min_severity` already decided which
    -- Findings enter the pipe, so a second `>= medium` in this arm would be a
    -- second policy that could disagree with the first. The status filter, on
    -- the other hand, IS repeated -- it is the one predicate that must match
    -- `due_notifications` exactly, because a row that stopped being offered and
    -- did not stop being complained about refuses the harness for ever.
    SELECT 'finding_unannounced',
           f.label || ' -- ' || coalesce(
               (SELECT string_agg(
                           n.channel
                           || CASE WHEN c.enabled THEN '' ELSE ' (disabled)' END
                           || ': ' || coalesce(left(n.last_error, 120), 'no error recorded')
                           || ', ' || n.attempts || '/' || c.max_attempts || ' attempts',
                           '; ' ORDER BY n.channel)
                  FROM finding_notifications n
                  JOIN notification_channels c ON c.channel = n.channel
                 WHERE n.finding_id = f.id),
               'fanned out to no channel')
      FROM findings f
     WHERE f.status IN ('validated', 'reported')
       AND EXISTS (SELECT 1 FROM finding_notifications n WHERE n.finding_id = f.id)
       AND NOT EXISTS (SELECT 1 FROM finding_notifications n
                        WHERE n.finding_id = f.id
                          AND n.delivered_at IS NOT NULL)
       AND NOT EXISTS (SELECT 1 FROM finding_notifications n
                        JOIN notification_channels c ON c.channel = n.channel
                        WHERE n.finding_id = f.id
                          AND n.delivered_at IS NULL
                          AND n.attempts < c.max_attempts
                          AND c.enabled)
UNION ALL
    -- TICKET 229, the wiring arm, and the one that can be true on a Program
    -- holding no Findings at all. The arm above is scoped to Findings the
    -- fan-out reached, which is exactly what makes it safe to apply to a live
    -- database -- and exactly what would make it silent if somebody removed the
    -- fan-out. Then no Finding would ever get a row, no row would ever be
    -- missing, and the check would read green while the announcement mechanism
    -- was gone. That is the vacuous green ticket 226 names, arriving here by a
    -- different door.
    --
    -- So this asks the wiring, not the state: the trigger exists on the table
    -- `state_severity` writes, it calls this function and not another, and it
    -- has not been switched off. False on any healthy corpus, whatever rows it
    -- holds.
    SELECT 'finding_notification_fan_out_is_unwired', 'severity_statements'
     WHERE NOT EXISTS (SELECT 1 FROM pg_trigger t
                        WHERE t.tgrelid = 'severity_statements'::regclass
                          AND NOT t.tgisinternal
                          AND t.tgfoid = 'fan_out_finding_notification'::regproc
                          AND t.tgenabled <> 'D')
$fn$;


-- ===========================================================================
-- 6. What this file claims, asserted rather than assumed
-- ===========================================================================
DO $$
DECLARE n integer; names text[];
BEGIN
    -- The two verbs kept their signatures. That is the entire reason option (b)
    -- costs no Python and no `runtime_verb_surface` change, so it is checked
    -- rather than believed: a later hand that widened either signature would
    -- break `decisions.py` silently, at the next sweep, on a live engagement.
    IF to_regprocedure('due_notifications(uuid)') IS NULL
       OR to_regprocedure('record_notification_attempt(uuid, boolean, text)') IS NULL THEN
        RAISE EXCEPTION 'ticket 229: a notification verb changed signature; decisions.py reads these two by name';
    END IF;

    -- And `decisions.py` is untouched because the column names it selects are
    -- still the column names this function returns.
    SELECT p.proargnames INTO names FROM pg_proc p
     WHERE p.oid = to_regprocedure('due_notifications(uuid)');
    SELECT count(*) INTO n
      FROM unnest(ARRAY['notification_id','label','body','channel','argv']) AS want(col)
     WHERE NOT (want.col = ANY (names));
    IF n > 0 THEN
        RAISE EXCEPTION 'ticket 229: due_notifications no longer returns the columns decisions.py selects by name';
    END IF;
END $$;
