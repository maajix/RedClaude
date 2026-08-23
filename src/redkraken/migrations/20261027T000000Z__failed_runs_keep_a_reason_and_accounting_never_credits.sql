-- Goal 1 hardening: terminal failures are legible and token counters cannot
-- credit capacity by becoming negative.

-- Historical rows predate error_detail. Give them a bounded, non-secret
-- account before making the invariant structural.
UPDATE agent_runs
   SET error_detail = 'this run ended before durable error details were recorded'
 WHERE stop_reason IN ('error', 'aborted')
   AND coalesce(btrim(error_detail), '') = '';

CREATE FUNCTION default_agent_run_error_detail() RETURNS trigger
LANGUAGE plpgsql AS $fn$
BEGIN
    IF NEW.stop_reason IN ('error', 'aborted')
       AND coalesce(btrim(NEW.error_detail), '') = '' THEN
        NEW.error_detail := 'the runtime closed this run without a more specific error detail';
    END IF;
    RETURN NEW;
END $fn$;

CREATE TRIGGER agent_runs_default_error_detail
    BEFORE INSERT OR UPDATE ON agent_runs
    FOR EACH ROW EXECUTE FUNCTION default_agent_run_error_detail();

ALTER TABLE agent_runs ADD CONSTRAINT agent_runs_failed_with_detail
    CHECK (stop_reason NOT IN ('error', 'aborted')
           OR coalesce(btrim(error_detail), '') <> '');

ALTER TABLE agent_runs ADD CONSTRAINT agent_runs_accounting_nonnegative
    CHECK (coalesce(input_tokens, 0) >= 0
       AND coalesce(output_tokens, 0) >= 0
       AND coalesce(uncached_input_tokens, 0) >= 0
       AND coalesce(cache_creation_input_tokens, 0) >= 0
       AND coalesce(cache_read_input_tokens, 0) >= 0
       AND coalesce(answer_count, 0) >= 0
       AND coalesce(budget_tokens, 0) >= 0);

-- The direct runtime close and the bulk attempt close are both covered. The
-- trigger is deliberately a last-resort account: a measured reason already on
-- the row wins, and all details remain bounded to one operator-readable line.
UPDATE tool_runs
   SET exit_detail = 'this Tool run ended before durable error details were recorded'
 WHERE status = 'error' AND coalesce(btrim(exit_detail), '') = '';

CREATE FUNCTION default_tool_run_error_detail() RETURNS trigger
LANGUAGE plpgsql AS $fn$
BEGIN
    IF NEW.status = 'error' AND coalesce(btrim(NEW.exit_detail), '') = '' THEN
        NEW.exit_detail := 'the runtime closed this Tool run without a more specific error detail';
    END IF;
    IF NEW.exit_detail IS NOT NULL THEN
        NEW.exit_detail := left(NEW.exit_detail, 500);
    END IF;
    RETURN NEW;
END $fn$;

CREATE TRIGGER tool_runs_default_error_detail
    BEFORE INSERT OR UPDATE ON tool_runs
    FOR EACH ROW EXECUTE FUNCTION default_tool_run_error_detail();

ALTER TABLE tool_runs ADD CONSTRAINT tool_runs_exit_detail_bounded
    CHECK (exit_detail IS NULL OR length(exit_detail) <= 500);

ALTER TABLE tool_runs ADD CONSTRAINT tool_runs_failed_with_detail
    CHECK (status <> 'error' OR coalesce(btrim(exit_detail), '') <> '');

COMMENT ON FUNCTION default_agent_run_error_detail() IS
    'Last-resort durable detail for an error or aborted Agent run. A measured '
    'detail supplied by the child is kept.';

COMMENT ON FUNCTION default_tool_run_error_detail() IS
    'Last-resort durable detail for an errored Tool run and the 500-character '
    'bound shared by online and offline runs.';
