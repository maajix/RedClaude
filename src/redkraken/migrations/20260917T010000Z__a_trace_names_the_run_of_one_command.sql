-- ---------------------------------------------------------------------------
-- 20260917T010000Z__a_trace_names_the_run_of_one_command.sql           (PH2-64)
--
-- `events.trace_id` has been read by `emit_event()` since 0013 and written by
-- nothing. Its column comment says it joins an OTel span, and there is no OTel
-- in this tree and no dependency that could put one there -- so every event row
-- ever written carries a null in the one column ADR 0002 lists among the
-- context a trigger cannot see. A promise nothing keeps is worse than an absent
-- column: it reads, to anyone querying the log, as tracing that is switched off
-- rather than as tracing that was never wired.
--
-- The writer now exists and is the connection helper, which is where ADR 0002
-- says this context comes from. What it writes is not a span id: it is one
-- identifier per connection the helper opens, and since one command opens one
-- connection, the rows sharing it are the rows one run of one command wrote.
-- That is the join the column was for. If a span ever arrives, it arrives in
-- the same place and this comment is what changes.
--
-- The column takes the setting as its default, because `emit_event()` is not
-- the only writer: `open_task` and a dozen functions like it insert their own
-- row naming the columns they care about, and a trace those rows lack is a hole
-- in the middle of the run they belong to. Reading the setting in the default
-- puts the answer where every writer passes, present and future, rather than
-- asking each one to remember. The explicit reads stay as they are -- they pass
-- exactly what the default would compute -- so no existing statement changes
-- meaning, and a session that never declared a trace still writes a null.
-- ---------------------------------------------------------------------------

ALTER TABLE events
    ALTER COLUMN trace_id SET DEFAULT nullif(current_setting('app.trace_id', true), '');

COMMENT ON COLUMN events.trace_id IS
    'The run of the command that wrote this row. Set once per connection by '
    'the runtime''s connection helper and taken from `app.trace_id` by default, '
    'so the rows of one `rk` invocation share it; null for a write no command '
    'made.';
