-- ---------------------------------------------------------------------------
-- 014_scheduler_event_deltas.sql
--
-- Not a file either ticket wrote. Ticket 08 ("Event payloads owed to ticket 07")
-- states two deltas as decided, but they land in ticket 07's catalogue and
-- config, which ticket 07 wrote before ticket 08 resolved. They are applied here
-- rather than by editing 013 so that 013 stays verbatim-as-resolved.
-- ---------------------------------------------------------------------------

-- ticket 08: scheduler.idle is a new occurrence type ticket 07's catalogue must
-- carry.
INSERT INTO event_types (id, family, subject_table, description) VALUES
    ('scheduler.idle', 'occurrence', NULL,
     'zero claimable tasks and zero runs in flight, with a reason breakdown');

-- ticket 08: a lease heartbeat would otherwise emit a task.updated per renewal.
UPDATE event_table_config
   SET ignored_columns = ignored_columns || '{lease_expires_at}'
 WHERE table_name = 'tasks';

SELECT attach_event_triggers();
