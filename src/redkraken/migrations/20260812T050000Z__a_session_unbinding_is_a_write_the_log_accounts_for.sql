-- ===========================================================================
-- Production harness 17 -- unbinding a session is a write, and the log says so
-- ===========================================================================
-- `agent_sessions` was registered as an insert-only emitter: `session.bound`
-- names the row when the binding is made, and nothing names it again. Then 030
-- replaced the deletion in `resume_program()` and `park_for_human()` with
-- `unbound_at`, for a good reason -- deleting the row orphaned its event -- and
-- the update it put there is a write the log does not account for.
-- `check_event_log_integrity()` reports it as `row_last_write_unaccounted`: the
-- row's last writer left no event and registered no suppression, which is the
-- accounting the log exists to provide and exactly what 030 was fixing at the
-- other end.
--
-- `close_startup_refusal()` is the third function to make that write and the
-- first whose test asked the gate about it afterwards, which is how a hole two
-- migrations old became visible.
--
-- The fix is the one this log already prefers: completeness is a trigger, not a
-- caller's discipline. `session.unbound` becomes the table's update type, so
-- the emitter fires on the unbinding as well as on the binding and every
-- unbinding -- the two that exist, the refusal's, and any later one -- is
-- accounted for without anyone remembering to account for it. What the event
-- says is what the correlation table is for: from this moment a hook call
-- carrying that SDK session resolves to no agent run.

INSERT INTO event_types(id, family, subject_table, description) VALUES
 ('session.unbound', 'row', 'agent_sessions',
  'the runtime released an SDK session or subagent binding; from here the correlation resolves no tool call to that agent run');

UPDATE event_table_config
   SET updated_type = 'session.unbound'
 WHERE table_name = 'agent_sessions';

-- The trigger is created `AFTER INSERT` alone while `updated_type` is NULL, so
-- the config change above only reaches the table by re-attaching.
SELECT attach_event_triggers();

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger t
          JOIN pg_class r ON r.oid = t.tgrelid
         WHERE r.relname = 'agent_sessions'
           AND t.tgname = 'agent_sessions_emit_event'
           AND NOT t.tgisinternal
           AND (t.tgtype & 16) <> 0)      -- 16 = the UPDATE bit of tgtype
    THEN
        RAISE EXCEPTION 'agent_sessions does not emit on update';
    END IF;
END $$;
