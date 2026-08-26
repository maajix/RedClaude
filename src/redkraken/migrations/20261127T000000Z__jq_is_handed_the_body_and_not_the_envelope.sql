-- ---------------------------------------------------------------------------
-- 20261127T000000Z__jq_is_handed_the_body_and_not_the_envelope.sql
--
-- The sixth offline tool joins the other five.
--
-- Measured on `rk2here`, 2026-08-26: forty-two `jq` runs, every one of them
-- `status = 'error'` with `exit_code = 5`, and no run of any other offline
-- tool. Reproduced outside the harness against `rk2tools:latest`:
--
--     $ printf 'HTTP/1.1 200 OK\r\n\r\n{"a":1}\n' | jq 'keys'
--     jq: parse error: Invalid numeric literal at line 1, column 9
--
-- Nothing is wrong with jq. Every Artifact the door files is the whole
-- exchange -- `artifacts.content_type` is `message/http` on all 3887 of them --
-- so a JSON response arrives with a status line in front of it. `jsscan.py`
-- knows this and says so in `carried_body`'s own docstring; jq is a binary and
-- has nowhere to keep the rule.
--
-- Which is the shape of the fix. Five registered tools run a program this
-- harness ships and digests into `tool_runs.analyser_sha256`; jq was the one
-- that ran a binary straight, so there was no file to put the rule in. It now
-- has one. `jqrun.py` applies `jsscan.carried_body`'s rule character for
-- character, hands jq the body on stdin, and passes back what jq wrote --
-- including the exit code, because jq's 1, 4 and 5 each mean something a
-- caller acts on.
--
-- The version probe grows rather than moves. `python3 /input/jqrun.py
-- --version` asks jq what it is and prints both, so the row keeps recording
-- which jq the image holds:
--
--     rk2-jq 1 (jq-1.7)
--
-- A wrapper that reported only itself would hide the tool it wraps, and
-- `tool_runs.tool_version` is the column that answers what ran.
--
-- AN UPDATE AND NOT AN UPSERT, for `20260928T020000Z`'s reason.
-- ---------------------------------------------------------------------------

UPDATE offline_tools
   SET executable      = '/usr/local/bin/python3',
       analyser        = 'jqrun.py',
       version_pattern = '^rk2-jq [0-9]+ \(jq-[0-9][0-9A-Za-z._-]*\)$',
       description     = 'Query one JSON Artifact with a jq filter. The Artifact is the '
                         'whole exchange the door filed, so the HTTP carrier is taken off '
                         'before jq reads it and the number of bytes skipped is reported.'
 WHERE tool = 'jq';


DO $$
DECLARE n integer; v text;
BEGIN
    SELECT count(*) INTO n FROM offline_tools
     WHERE tool = 'jq' AND analyser = 'jqrun.py'
       AND executable = '/usr/local/bin/python3';
    IF n <> 1 THEN
        RAISE EXCEPTION 'ticket 198: jq did not take the analyser';
    END IF;

    -- Every registered tool now runs something this harness ships. Written as
    -- the general statement rather than about jq, because the next tool
    -- registered as a bare binary is the next tool handed an envelope it
    -- cannot read, and this is the line that says so.
    SELECT count(*), string_agg(tool, ', ') INTO n, v
      FROM offline_tools WHERE enabled AND analyser IS NULL;
    IF n > 0 THEN
        RAISE EXCEPTION 'ticket 198: % enabled tool(s) run no analyser: %', n, v;
    END IF;

    -- And the probe still admits what the image will say. Held here rather
    -- than left to the first call, which is a Task that fails.
    SELECT version_pattern INTO v FROM offline_tools WHERE tool = 'jq';
    IF 'rk2-jq 1 (jq-1.7)' !~ v THEN
        RAISE EXCEPTION 'ticket 198: the jq version pattern admits nothing this wrapper says';
    END IF;
END $$;
