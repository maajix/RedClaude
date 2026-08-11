-- Origin: ticket 11, "Human control", read against the half of it that no
-- process runs. The database files a question, fans it out to every enabled
-- channel, gives the queue a deadline, and provides all three verbs a runtime
-- would need -- `expire_due_decisions`, `due_notifications`,
-- `record_notification_attempt`. Nothing in `src/` calls any of them. Both
-- halves were exercised by hand on the live rig:
--
--     D4 parked with a 2s deadline, then expire_due_decisions()
--       -> expired | runtime | "deadline passed with no human answer"
--       -> TR49 stays parked, still naming D4, digest still cleared
--     D5, desktop channel argv replaced with one that exits 7
--       -> attempts 5 = max_attempts, delivered_at NULL, question still pending
--
-- The first half already has an alarm: `check_control_surface` rule 4 makes a
-- pending decision past its deadline a standing failure, and on the rig it fired
-- exactly as written -- `rk db verify` exit 9,
-- `(decision_past_deadline_unswept,D6)`. Its comment says why it is loud: a
-- parked task and a stopped harness look identical from outside.
--
-- The second half has no alarm at all. A notification that burns its
-- `max_attempts` and never lands leaves the question sitting in the queue, and
-- the only thing that eventually happens to it is the deadline -- so the
-- decision is retired as a timeout against a human who was never told there was
-- anything to answer. `enabled_channel_delivers_nothing` catches an empty argv,
-- which is the same failure caught one step earlier, and nothing catches this
-- one.
--
-- This adds that arm. A question is unannounced when nothing has been delivered
-- for it and nothing is left that will ever be tried again: every channel it was
-- fanned out to is exhausted, or has since been disabled. Stated as "no attempt
-- remains" rather than "an attempt failed", because a channel that is still
-- retrying has not failed yet -- it is the queue working.


-- ===========================================================================
-- A question nobody was told about
-- ===========================================================================
CREATE OR REPLACE FUNCTION check_control_surface()
RETURNS TABLE(problem text, detail text)
LANGUAGE sql STABLE AS $$
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
$$;

COMMENT ON FUNCTION check_control_surface() IS
  'Ticket 28''s standing check: every pending decision is answerable, every '
  'answer closes exactly once, and every open question either reached a human '
  'or is still being tried.';

-- The registration is what an operator reads to find out what failed, so it
-- says the same thing the function now does.
SELECT set_actor('runtime', 'the control surface check gained an arm');

UPDATE standing_checks
   SET note = 'every pending decision is answerable, every answer closes exactly'
              ' once, and every open question either reached a human or is still'
              ' being tried'
 WHERE name = 'control_surface';
