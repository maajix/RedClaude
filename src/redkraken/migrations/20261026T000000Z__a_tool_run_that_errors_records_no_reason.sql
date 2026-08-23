-- ===========================================================================
-- Production harness 149 -- a Tool run that errors records no reason
-- ===========================================================================
-- `rk2hunt8`, 2026-08-22. Three Tool runs against the live target, every one of
-- them closed `error`, every one of them with nothing said about it:
--
--     label|status|decision|started|finished
--     TR1  |error |allow   |t      |t
--     label|exit_code|detail|hook|url
--     TR1  |         |      |    |https://www.yekta-it.de
--
-- `exit_code`, `exit_detail` and `hook_error` all NULL, `"receipt": null` in the
-- run JSON, and a recon child with nothing to read filing nothing. Task `T1`
-- stayed pending and burned an attempt per lap. The investigation that found
-- the cause read `docker logs` on the door, which is not a step any operator
-- procedure names.
--
-- Two defects compound here and this migration owns the first. The failure was
-- silent because nothing could write the reason down -- and that is not an
-- omission at the call site, it is the schema refusing the column:
--
--     tool_runs_exit_detail_ck  CHECK (exit_detail IS NULL OR
--                                      offline_tool IS NOT NULL)
--
-- 018 added `exit_code` and `exit_detail` together and constrained both to an
-- offline tool, which is right about one of them and wrong about the other. An
-- exit code is a process's, and a run through the door starts no process, so
-- that constraint stays. A *reason* is every run's: the three that failed here
-- were online runs, so `offline_tool` was NULL, so the one column that could
-- have carried the account was the one the CHECK forbade them. The measurement
-- in the ticket is what a status with no reason costs the next reader.
--
-- The second defect -- that nothing notices when the door serves a database the
-- runtime has moved on from -- is the preflight's, not the schema's, and is
-- ticket 149's other half in `doctor`. The door binding one database for its
-- lifetime is correct and is ticket 82's design.
--
-- What is written here is only what this function actually knows. It closes
-- Tool runs that were still `running` when their Agent run ended, and that is
-- the whole of its account: it did not perform the request and it cannot read
-- the door's log. A sentence naming what it observed is worth more than a NULL
-- and is not worth inventing a cause for -- the door's own refusal, where there
-- is one, arrives as a blocked Receipt and says its own reason.

-- ---------------------------------------------------------------------------
-- 1. The column an errored run could not use
-- ---------------------------------------------------------------------------

ALTER TABLE tool_runs DROP CONSTRAINT tool_runs_exit_detail_ck;

COMMENT ON COLUMN tool_runs.exit_detail IS
    'Why this run ended as it did, in one sentence, bounded at 500 characters. '
    'Any run may carry one: an offline tool that failed says so, and a run the '
    'runtime closed because its Agent run ended says that. Only exit_code stays '
    'an offline tool''s, because a run through the door starts no process. '
    'Ticket 149: three online runs closed error with exit_code, exit_detail and '
    'hook_error all NULL, and the constraint that had forbidden the column was '
    'why the account had nowhere to go.';

-- ---------------------------------------------------------------------------
-- 2. The closing that now says what it did
-- ---------------------------------------------------------------------------
-- Signature and callers unchanged. The sentence is a constant rather than a
-- parameter because it is a constant fact: every row this statement touches is
-- one that was `running` when its Agent run stopped, and there is no caller
-- that knows anything more particular than that. A parameter would have been an
-- invitation to write a cause the runtime had not measured.
--
-- `exit_detail IS NULL` in the SET, not in the WHERE: a run that already
-- recorded its own reason keeps it, and one that recorded none gets this. The
-- `status = 'running'` predicate is untouched, so a second call still closes
-- nothing.

CREATE OR REPLACE FUNCTION close_tool_runs(p_agent_run uuid) RETURNS bigint
LANGUAGE plpgsql AS $fn$
DECLARE n bigint;
BEGIN
    UPDATE tool_runs
       SET status = 'error',
           finished_at = now(),
           exit_detail = coalesce(
               exit_detail,
               'the Agent run ended while this Tool run was still open, so the '
               'runtime closed it and revoked its capability; no receipt was '
               'filed for it and the reason it did not finish is the door''s')
     WHERE agent_run_id = p_agent_run AND status = 'running';
    GET DIAGNOSTICS n = ROW_COUNT;
    RETURN n;
END $fn$;

COMMENT ON FUNCTION close_tool_runs(uuid) IS
    'Closes every Tool run still open inside one Agent run, which is what '
    'revokes each one''s capability, and records why each one ended where it '
    'had recorded nothing. Idempotent: a Tool run already closed is not closed '
    'again, its finish time is the moment it actually ended, and a reason it '
    'wrote for itself is kept over this one.';
