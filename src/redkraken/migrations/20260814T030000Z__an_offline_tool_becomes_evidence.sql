-- ===========================================================================
-- Production harness 30 -- an offline Tool run becomes evidence
-- ===========================================================================
-- `mcp__rk2__run_tool` has been a contract with nothing behind it: the roster
-- compiles it, the risk rules classify it, and no path in the harness starts a
-- process. This file is the half that was missing, and it is deliberately the
-- database's half -- what may run, with which arguments, under which ceilings,
-- and what has to be true of its output before anything it produced may be
-- cited as evidence.
--
-- Six things, one per criterion:
--
--   1. A closed registry. `offline_tools` names the executable, the version it
--      must report, the timeout, the memory, CPU and process ceilings and the
--      output bound; `offline_tool_arguments` is one row per parameter, so the
--      argument schema is data rather than a string the runtime parses;
--      `offline_tool_roles` says which roles may run it. Nothing composes an
--      argv from model text: this file's `open_offline_tool_run` builds the
--      argv and returns it, and the runtime runs what it was handed.
--   2. No network unless the registry says so. `offline_tools.network` is
--      `none` or `proxy` and nothing else, the one registered tool is `none`,
--      and a Receipt attributed to a `none` run is a standing violation.
--   3. Opened before the process starts, closed on every ending. The row is
--      written by the verb that validates the call, so a process that starts
--      has a row and a call that has no row started nothing. Death of the
--      supervisor has no closer by definition, so it is a check rather than a
--      promise: a run still open past twice its own declared timeout is a row
--      that says the thing that was going to close it is gone.
--   4. Every stream is stored, bounded, by hash. `tool_run_artifacts` links a
--      run to the artifacts its stdout, stderr and declared outputs became;
--      the run carries the version the tool reported of itself, so the bytes
--      have tool-version provenance one foreign key away and stored in one
--      place.
--   5. Shell text alone cannot create an Observation. An Observation citing an
--      offline Tool run is refused unless that run finished and its output was
--      stored: the citation reaches the Artifacts through the run, and a run
--      whose output nobody kept is a sentence a model wrote about bytes that
--      are gone.
--   6. The negative controls are the verb's refusals: an unknown or disabled
--      tool, an argument the schema does not declare, a required one missing, a
--      value outside its kind, a role the tool does not admit, an artifact this
--      Program does not hold, and an output that overran its bound. Every one
--      of them raises rather than degrades, and `tests/test_database.py` asserts
--      each by name.


-- ---------------------------------------------------------------------------
-- 1. What a value may be
-- ---------------------------------------------------------------------------
-- The kind is what makes path escape structural rather than checked. Of the
-- four, exactly one names a file, and what it names is an Artifact label --
-- never a path. The other three admit no `/` and no `\` at all, so no value a
-- model supplies can address the filesystem, whatever the tool would do with
-- it if it could.

CREATE TABLE offline_argument_kinds (
    value_kind   text PRIMARY KEY,
    pattern      text NOT NULL,
    materialised boolean NOT NULL,
    description  text NOT NULL
);

COMMENT ON TABLE offline_argument_kinds IS
    'What a supplied argument value may look like, by kind. The pattern is the '
    'floor: an argument row may narrow it further and may not widen it. '
    '`materialised` marks the one kind whose value is an Artifact label rather '
    'than a literal -- the runtime puts those bytes inside the container and '
    'the tool is given the path, so a tool never receives a path a model wrote.';

COMMENT ON COLUMN offline_argument_kinds.pattern IS
    'Anchored, and deliberately without the path separators. A kind that '
    'admitted `/` or `\` would make every argument of that kind a candidate for '
    'addressing the filesystem, and the refusal would then live in whichever '
    'tool happened to interpret it that way. No value may begin with `-` for the '
    'same reason one directory up: the argv is a list the tool re-reads, and a '
    'value that starts like an option is a value some tool will read as one -- '
    'which is a way to reach a switch the registry never listed. Bounded at 255 '
    'rather than at some rounder number because 255 is the largest repetition '
    'count the server''s own regular expressions accept, and a pattern the '
    'server refuses to compile is a rule that refuses everything.';

INSERT INTO offline_argument_kinds (value_kind, pattern, materialised, description) VALUES
    -- `]` leads each set so it is a member rather than the end of it, and `-`
    -- trails the second for the same reason; both are in because a jq filter
    -- without brackets is a jq filter that cannot index an array. The first
    -- character is spelled separately because it is the one position where `-`
    -- is absent, which costs one repeat off the bound and nothing else.
    ('text',
     '^[]A-Za-z0-9 _.:@=,+|?*(){}"''$[][]A-Za-z0-9 _.:@=,+|?*(){}"''$[-]{0,254}$', false,
     'a literal the tool reads as one word of its own language -- a filter, a pattern, an expression'),
    ('integer',  '^[0-9]{1,9}$', false,
     'a count, a limit or a depth, and never a negative one'),
    ('choice',   '^[A-Za-z0-9_.][A-Za-z0-9_.-]{0,63}$', false,
     'one of the values the argument row enumerates, and nothing else'),
    ('artifact', '^[A-Z]{1,4}[0-9]{1,9}$', true,
     'the label of an Artifact this Program holds; the tool is given a path to a read-only copy');

INSERT INTO program_global_tables (table_name, reason) VALUES
    ('offline_argument_kinds',
     'the vocabulary an argument schema is written in; a per-program copy would '
     'let one Program mean something wider by `text` than the tool registry does');

INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
    ('offline_argument_kinds', 'reference',
     'the argument value vocabulary, changed only by migration', '30');

GRANT SELECT ON offline_argument_kinds TO rk2_runtime;


-- ---------------------------------------------------------------------------
-- 2. The closed registry
-- ---------------------------------------------------------------------------
-- Criterion 1, and the shape of it is the point. An allowlist of names with the
-- rest of the description in code would be an allowlist of names: the timeout a
-- caller passes, the ceiling a caller passes and the argv a caller builds are
-- three ways to run something the allowlist never admitted. Here the name is
-- the key and everything that decides what running it means hangs off it.

CREATE TABLE offline_tools (
    tool             text PRIMARY KEY CHECK (tool ~ '^[a-z][a-z0-9_-]{0,31}$'),
    -- Absolute, so the registry names a file rather than a PATH lookup. Which
    -- program answers to `jq` is a property of the image and of whatever `PATH`
    -- the image was built with; which file is executed is this row.
    executable       text NOT NULL CHECK (executable ~ '^(/[A-Za-z0-9_.-]+){1,8}$'),
    -- How to ask the tool what it is, and what an acceptable answer looks like.
    -- A version pinned as a literal here would be a claim about an image this
    -- migration has never seen; a pattern is a claim the runtime can check
    -- against the image in front of it, and it refuses before the run opens.
    version_argv     text[] NOT NULL CHECK (cardinality(version_argv) BETWEEN 1 AND 4),
    version_pattern  text NOT NULL,
    network          text NOT NULL DEFAULT 'none' CHECK (network IN ('none','proxy')),
    timeout_seconds  integer NOT NULL CHECK (timeout_seconds BETWEEN 1 AND 900),
    memory_mb        integer NOT NULL CHECK (memory_mb BETWEEN 16 AND 4096),
    cpu_quota        numeric NOT NULL CHECK (cpu_quota > 0 AND cpu_quota <= 4),
    pids_limit       integer NOT NULL CHECK (pids_limit BETWEEN 1 AND 512),
    max_output_bytes integer NOT NULL CHECK (max_output_bytes BETWEEN 1024 AND 16777216),
    enabled          boolean NOT NULL DEFAULT true,
    description      text NOT NULL
);

COMMENT ON TABLE offline_tools IS
    'Every process this harness may start on purpose, and everything that '
    'decides what starting it means: the file, the version it must report, '
    'whether it has a network at all, and the four ceilings it runs under. '
    'Changed only by migration -- a runtime that could add a row could run '
    'anything, which is the whole of what this table exists to prevent.';

COMMENT ON COLUMN offline_tools.network IS
    'Criterion 2 in one column. `none` is a container with no interface but '
    'loopback; `proxy` is the one-peer boundary an Agent gets, where the only '
    'reachable peer is the capability proxy. There is no third value, so there '
    'is no way to spell "the host''s network".';

COMMENT ON COLUMN offline_tools.max_output_bytes IS
    'What the runtime will keep of each stream. A stream that overruns it is '
    'stored up to the bound and the Artifact row says so, because a truncated '
    'record that admits it is evidence and a silently clipped one is not.';

INSERT INTO offline_tools
    (tool, executable, version_argv, version_pattern, network, timeout_seconds,
     memory_mb, cpu_quota, pids_limit, max_output_bytes, description) VALUES
    ('jq', '/usr/bin/jq', '{--version}', '^jq-[0-9][0-9A-Za-z._-]*$', 'none',
     30, 256, 1.0, 32, 1048576,
     'query one stored JSON Artifact with a filter, and write the result to stdout');

-- One tool, because the ticket asks for one and because a registry seeded with
-- tools nobody has run is a registry of guesses. The extension point is the
-- table: a second tool is four columns and a role, not a code path.

CREATE TABLE offline_tool_arguments (
    tool        text NOT NULL REFERENCES offline_tools(tool),
    name        text NOT NULL CHECK (name ~ '^[a-z][a-z0-9_]{0,31}$'),
    position    integer NOT NULL CHECK (position >= 0),
    -- The flag the value is passed behind, or nothing for a positional. Written
    -- here rather than baked into the tool's description because it is the
    -- other half of the argv: a caller that could choose the flag could choose
    -- the argument.
    flag        text CHECK (flag IS NULL OR flag ~ '^--?[A-Za-z0-9][A-Za-z0-9-]{0,31}$'),
    value_kind  text NOT NULL REFERENCES offline_argument_kinds(value_kind),
    required    boolean NOT NULL DEFAULT false,
    pattern     text,
    choices     text[],
    description text NOT NULL,
    PRIMARY KEY (tool, name),
    UNIQUE (tool, position),
    -- `choices` and the `choice` kind are the same statement, and a row making
    -- one of them without the other is a row whose meaning depends on which
    -- half the reader looked at.
    CONSTRAINT offline_tool_arguments_choices_ck
        CHECK ((value_kind = 'choice') = (choices IS NOT NULL AND cardinality(choices) > 0))
);

COMMENT ON TABLE offline_tool_arguments IS
    'The argument schema, one row per parameter. `position` orders the argv and '
    'is unique per tool, so there is exactly one argv for a given set of values '
    'and the database is what builds it.';

COMMENT ON COLUMN offline_tool_arguments.pattern IS
    'Narrower than the kind, never wider: `open_offline_tool_run` applies both, '
    'and the kind is applied first. An argument that wanted to admit more than '
    'its kind wants a different kind.';

INSERT INTO offline_tool_arguments
    (tool, name, position, flag, value_kind, required, pattern, choices, description) VALUES
    ('jq', 'filter', 0, NULL, 'text', true, NULL, NULL,
     'the jq program, as one word -- the filter, not a file of filters'),
    ('jq', 'input', 1, NULL, 'artifact', true, NULL, NULL,
     'the Artifact whose bytes are queried');

-- A tool declaring an output declares a filename, never a path. The runtime
-- decides which directory the tool may write and mounts it; a row here says
-- which files in it are evidence when the process ends. Without the name
-- constraint this table would be the path escape the argument kinds close.
CREATE TABLE offline_tool_outputs (
    tool        text NOT NULL REFERENCES offline_tools(tool),
    name        text NOT NULL CHECK (name ~ '^[a-z][a-z0-9_.-]{0,63}$'),
    description text NOT NULL,
    PRIMARY KEY (tool, name)
);

COMMENT ON TABLE offline_tool_outputs IS
    'The files a tool writes that are worth keeping, by bare filename. Empty '
    'for `jq`, which writes to stdout and to nothing else; the mechanism is '
    'here because criterion 4 names declared outputs beside the two streams, '
    'and because a tool that produces a report file must not need a code change '
    'to have that file become an Artifact.';

CREATE TABLE offline_tool_roles (
    tool text NOT NULL REFERENCES offline_tools(tool),
    role text NOT NULL REFERENCES roles(role),
    PRIMARY KEY (tool, role)
);

COMMENT ON TABLE offline_tool_roles IS
    'Which roles may run which tool. A foreign key to `roles` rather than a '
    'text list, so a role that is renamed or retired takes its permissions with '
    'it instead of leaving a string that matches nothing and refuses quietly.';

INSERT INTO offline_tool_roles (tool, role) VALUES
    ('jq', 'recon'),
    ('jq', 'js_analyst');

INSERT INTO program_global_tables (table_name, reason) VALUES
    ('offline_tools',
     'what may be executed at all; a per-program registry would make the set of '
     'runnable programs something a Program''s own configuration could widen'),
    ('offline_tool_arguments',
     'the argument schema of a global registry'),
    ('offline_tool_outputs',
     'the declared outputs of a global registry'),
    ('offline_tool_roles',
     'which roles may run a globally registered tool');

INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
    ('offline_tools', 'reference',
     'the executable registry, changed only by migration', '30'),
    ('offline_tool_arguments', 'reference',
     'the argument schema, changed only by migration', '30'),
    ('offline_tool_outputs', 'reference',
     'the declared outputs, changed only by migration', '30'),
    ('offline_tool_roles', 'reference',
     'which roles may run which tool, changed only by migration', '30');

GRANT SELECT ON offline_tools, offline_tool_arguments, offline_tool_outputs,
                offline_tool_roles TO rk2_runtime;

-- `rk2_state` is absent from every grant above, and that is the same argument
-- ticket 13 makes about `call_risk_rules`. The model learns which tools exist
-- from the roster's compiled contract, which is a description of what it may
-- ask for; the registry is a description of what the runtime will then do, and
-- the two are not the same document. A model that could read the ceilings could
-- shape a call to sit just under them.


-- ---------------------------------------------------------------------------
-- 3. The Tool run says which tool, and which version of it
-- ---------------------------------------------------------------------------
-- `tool_runs.tool` stays `mcp__rk2__run_tool`: it is what `canonical_request`,
-- the risk rules and every existing count key on, and an offline run that
-- spelled its tool differently would be a run no rule matches. Which binary ran
-- is a second fact and gets a second column.

ALTER TABLE tool_runs
    ADD COLUMN offline_tool text REFERENCES offline_tools(tool),
    -- What the tool said about itself, read from the image before the run
    -- opened. The registry holds the pattern an answer must match; this holds
    -- the answer, so an Artifact's provenance is the version that produced it
    -- rather than the version the registry expected at some later date.
    ADD COLUMN tool_version text,
    ADD COLUMN exit_code    integer,
    -- Why the run ended as it did, in one sentence, and its own column rather
    -- than 0022's `hook_error`: that one means a hook this harness runs refused
    -- or broke, and a timeout inside a container is neither. Sharing it would
    -- make `closed_by` the only way to tell which of the two a sentence is
    -- about, and `closed_by` is NULL for every run here.
    ADD COLUMN exit_detail  text;

ALTER TABLE tool_runs ADD CONSTRAINT tool_runs_offline_version_ck
    CHECK ((offline_tool IS NULL) = (tool_version IS NULL));

ALTER TABLE tool_runs ADD CONSTRAINT tool_runs_exit_code_ck
    CHECK (exit_code IS NULL OR offline_tool IS NOT NULL);

ALTER TABLE tool_runs ADD CONSTRAINT tool_runs_exit_detail_ck
    CHECK (exit_detail IS NULL OR offline_tool IS NOT NULL);

COMMENT ON COLUMN tool_runs.offline_tool IS
    'The registry row this run executed, or NULL for every other kind of Tool '
    'run. Non-NULL is what makes the Observation rule apply: an Observation may '
    'cite this run only once its output is stored.';

-- The composite `tool_run_artifacts` needs to key on, and the same shape 017
-- gives every other program-scoped child: a foreign key that carries the
-- Program cannot be satisfied by a row of somebody else's.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conname = 'tool_runs_id_program_key'
                      AND conrelid = 'tool_runs'::regclass) THEN
        ALTER TABLE tool_runs ADD CONSTRAINT tool_runs_id_program_key
            UNIQUE (id, program_id);
    END IF;
END $$;

CREATE INDEX tool_runs_offline_open_idx
    ON tool_runs (offline_tool, started_at) WHERE status = 'running';


-- ---------------------------------------------------------------------------
-- 4. What the run produced
-- ---------------------------------------------------------------------------
-- Criterion 4. One row per stream, pointing at the Artifact the bytes became.
--
-- Deliberately thin: no tool name, no version, no byte size. Each of those is
-- one join away -- the version from the run, the size from `artifacts` -- and a
-- copy here would be a second answer to a question that already has one. What
-- this table holds is the two facts nothing else can: which stream of which run
-- these bytes are, and whether the stream was longer than what was kept.

CREATE TABLE tool_run_artifacts (
    id             uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id     uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    tool_run_id    uuid NOT NULL,
    stream         text NOT NULL CHECK (stream IN ('stdout','stderr','output')),
    output_name    text,
    sha256         text NOT NULL REFERENCES artifacts(sha256),
    -- How many bytes the stream actually reached. Equal to the Artifact's size
    -- for a stream that fitted, larger for one that did not, and never smaller:
    -- the trigger below holds that against `artifacts`, which is where the
    -- stored size lives.
    produced_bytes bigint NOT NULL CHECK (produced_bytes >= 0),
    truncated      boolean NOT NULL DEFAULT false,
    recorded_at    timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (tool_run_id, program_id) REFERENCES tool_runs (id, program_id),
    -- A declared output is named; the two streams are not. Both directions,
    -- because `stdout` with a name and `output` without one are equally
    -- unreadable as evidence.
    CONSTRAINT tool_run_artifacts_named_output_ck
        CHECK ((stream = 'output') = (output_name IS NOT NULL)),
    CONSTRAINT tool_run_artifacts_output_name_ck
        CHECK (output_name IS NULL OR output_name ~ '^[a-z][a-z0-9_.-]{0,63}$'),
    UNIQUE (tool_run_id, stream, output_name)
);

CREATE INDEX tool_run_artifacts_run_idx ON tool_run_artifacts (tool_run_id);

COMMENT ON TABLE tool_run_artifacts IS
    'Which content-addressed Artifacts one offline Tool run produced. The link '
    'is what an Observation citing that run stands on: the bytes are named by '
    'their hash, held by this Program, and attributable to the tool and version '
    'the run recorded.';

COMMENT ON COLUMN tool_run_artifacts.truncated IS
    'The stream was longer than the tool''s declared bound and what is stored '
    'is a prefix. Recorded rather than inferred so a reader of the Artifact '
    'knows it is reading part of something.';

INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
    ('tool_run_artifacts', 'program_id', 'program-scoped: the purge root');

INSERT INTO event_types (id, family, subject_table, description) VALUES
    ('tool_run.output_stored', 'row', 'tool_run_artifacts',
     'a stream of an offline Tool run became a content-addressed Artifact');

INSERT INTO event_table_config
    (table_name, created_type, updated_type, ignored_columns, redacted_columns) VALUES
    ('tool_run_artifacts', 'tool_run.output_stored', NULL, '{}', '{}');

SELECT attach_event_triggers();

-- The payload is identifiers, a hash and two counts, which is exactly what §6
-- allows into the log. There is no `redacted_columns` entry because there is no
-- column here that would need one -- the bytes are in the store, and the store
-- is not what the log records.

-- Immutable for `artifact_references`' reason, one step along: this row says a
-- run produced these exact bytes, and a row that could be repointed afterwards
-- would let the evidence behind an Observation be swapped out from under it.
CREATE TRIGGER tool_run_artifacts_immutable
    BEFORE UPDATE OR DELETE ON tool_run_artifacts
    FOR EACH ROW EXECUTE FUNCTION reject_mutation_unless_purging();

-- Criterion 5 needs a second half. A model that may cite these Artifacts and
-- cannot see that they exist can only cite what the supervisor told it in prose,
-- which is the shell text the ticket is about. So the link table joins the agent
-- read surface, column by column like everything else on it, together with the
-- four columns this file added to `tool_runs`.
--
-- `program_id` is absent for the reason 05 gives for `events`: row level
-- security scopes the read without the reading role having to see the column it
-- is scoped on. `id` is absent because nothing cites one of these rows -- an
-- Observation cites the run, and the bytes are named by their hash.
--
-- What is published is deliberately about this run and not about the registry.
-- `offline_tool` and `tool_version` are provenance, and a model that has just
-- asked for a tool by name learns nothing new from being told which one it got.
-- `exit_code` and `exit_detail` are the difference between an output and part of
-- one, which is exactly what a reader deciding whether to cite it needs. The
-- ceilings stay where section 2 left them: those say what the runtime would stop,
-- and a model that can read them can shape a call to sit just underneath.
INSERT INTO state_read_surface (table_name, column_name, added_by) VALUES
    ('tool_run_artifacts', 'tool_run_id',    'ph2-30'),
    ('tool_run_artifacts', 'stream',         'ph2-30'),
    ('tool_run_artifacts', 'output_name',    'ph2-30'),
    ('tool_run_artifacts', 'sha256',         'ph2-30'),
    ('tool_run_artifacts', 'produced_bytes', 'ph2-30'),
    ('tool_run_artifacts', 'truncated',      'ph2-30'),
    ('tool_run_artifacts', 'recorded_at',    'ph2-30'),
    ('tool_runs',          'offline_tool',   'ph2-30'),
    ('tool_runs',          'tool_version',   'ph2-30'),
    ('tool_runs',          'exit_code',      'ph2-30'),
    ('tool_runs',          'exit_detail',    'ph2-30');

-- Criterion 6's foreign-Artifact control, and it is a trigger rather than a
-- rule inside the verb because `rk2_runtime` holds INSERT on the table. A guard
-- that only the convenience verb applied would be a guard one statement gets
-- around.
CREATE FUNCTION tool_run_artifact_is_this_runs_output() RETURNS trigger
LANGUAGE plpgsql AS $fn$
DECLARE
    v_run   tool_runs%ROWTYPE;
    v_size  bigint;
BEGIN
    SELECT * INTO v_run FROM tool_runs
     WHERE id = NEW.tool_run_id AND program_id = NEW.program_id;
    IF NOT FOUND OR v_run.offline_tool IS NULL THEN
        RAISE EXCEPTION 'tool run % is not an offline Tool run of this Program',
            NEW.tool_run_id USING ERRCODE = '23503';
    END IF;
    -- Output is recorded while the run is open, and the close is what makes it
    -- final. A row arriving after the close would be output attributed to a run
    -- that had already reported what it produced.
    IF v_run.status <> 'running' THEN
        RAISE EXCEPTION 'tool run % has already been closed as %',
            v_run.label, v_run.status USING ERRCODE = '23514';
    END IF;

    -- The Artifact has to be one this Program holds. Reachability is the
    -- reference, never the hash: ticket 06's whole argument is that storage
    -- deduplicates across Programs and access does not, so a hash another
    -- Program stored resolves here to nothing.
    IF NOT EXISTS (SELECT 1 FROM artifact_references r
                    WHERE r.program_id = NEW.program_id AND r.sha256 = NEW.sha256) THEN
        RAISE EXCEPTION 'artifact % is not held by this Program', NEW.sha256
            USING ERRCODE = '42704',
                  HINT = 'store the bytes and reference them before recording them as output';
    END IF;

    SELECT byte_size INTO v_size FROM artifacts WHERE sha256 = NEW.sha256;
    IF NEW.produced_bytes < v_size THEN
        RAISE EXCEPTION 'a stream of % byte(s) cannot have stored % byte(s)',
            NEW.produced_bytes, v_size USING ERRCODE = '23514';
    END IF;
    IF NEW.truncated <> (NEW.produced_bytes > v_size) THEN
        RAISE EXCEPTION 'the truncation flag disagrees with the stored size'
            USING ERRCODE = '23514',
                  HINT = 'truncated is produced_bytes > the stored artifact size, and nothing else';
    END IF;

    IF NEW.stream = 'output'
       AND NOT EXISTS (SELECT 1 FROM offline_tool_outputs o
                        WHERE o.tool = v_run.offline_tool AND o.name = NEW.output_name) THEN
        RAISE EXCEPTION '% declares no output named %', v_run.offline_tool, NEW.output_name
            USING ERRCODE = '42704';
    END IF;
    RETURN NEW;
END $fn$;

CREATE TRIGGER tool_run_artifacts_is_this_runs_output
    BEFORE INSERT ON tool_run_artifacts
    FOR EACH ROW EXECUTE FUNCTION tool_run_artifact_is_this_runs_output();

COMMENT ON FUNCTION tool_run_artifact_is_this_runs_output() IS
    'The four things a link row must be able to prove: the run is this '
    'Program''s offline run and still open, the Artifact is one this Program '
    'holds, the sizes agree with what was stored, and a named output is one the '
    'tool declares.';

GRANT SELECT, INSERT ON tool_run_artifacts TO rk2_runtime;


-- ---------------------------------------------------------------------------
-- 5. Opening a run is validating the call
-- ---------------------------------------------------------------------------
-- Criteria 1, 3 and 6 are one function, because they are one moment. Everything
-- that decides whether this call may happen is asked before the row exists, the
-- row is written before anything starts, and what comes back is the exact argv
-- the runtime is to run -- not the arguments to build one from.

CREATE FUNCTION rk2_offline_tool(p_tool text) RETURNS offline_tools
LANGUAGE plpgsql STABLE AS $fn$
DECLARE v_tool offline_tools%ROWTYPE;
BEGIN
    SELECT * INTO v_tool FROM offline_tools WHERE tool = p_tool AND enabled;
    IF NOT FOUND THEN
        -- One answer for a tool that is not registered and one that is disabled.
        -- Both are "the registry will not run this", and telling them apart
        -- would say which names exist to whatever is asking.
        RAISE EXCEPTION 'no offline tool named %', p_tool USING ERRCODE = '42704';
    END IF;
    RETURN v_tool;
END $fn$;

COMMENT ON FUNCTION rk2_offline_tool(text) IS
    'One registered, enabled tool, or the refusal. The runtime asks this before '
    'it starts anything -- it has to know which executable to ask its version -- '
    'and the verb below asks it again, so a tool the registry will not run is '
    'refused in the same words wherever the question is put.';

CREATE FUNCTION rk2_offline_input_path(p_label text) RETURNS text
LANGUAGE sql IMMUTABLE AS $fn$ SELECT '/input/' || p_label $fn$;

CREATE FUNCTION rk2_offline_workspace() RETURNS text
LANGUAGE sql IMMUTABLE AS $fn$ SELECT '/work' $fn$;

COMMENT ON FUNCTION rk2_offline_input_path(text) IS
    'Where the bytes of one input Artifact appear inside the container. Stated '
    'once, here, and returned to the runtime rather than agreed with it: two '
    'definitions of this path would be two answers the day one of them moved.';

COMMENT ON FUNCTION rk2_offline_workspace() IS
    'The one directory an offline tool may write. Declared outputs are bare '
    'filenames inside it, so a declared output cannot name anything else.';

CREATE FUNCTION open_offline_tool_run(
        p_agent_run_id uuid,
        p_tool         text,
        p_version      text,
        p_arguments    jsonb DEFAULT '{}'::jsonb)
RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p         uuid := rk2_program_required();
    v_run     agent_runs%ROWTYPE;
    v_tool    offline_tools%ROWTYPE;
    v_arg     offline_tool_arguments%ROWTYPE;
    v_kind    offline_argument_kinds%ROWTYPE;
    v_name    text;
    v_value   text;
    v_sha     text;
    v_argv    text[] := '{}';
    v_inputs  jsonb := '[]'::jsonb;
    v_outputs jsonb;
    v_id      uuid;
    v_label   text;
BEGIN
    IF jsonb_typeof(p_arguments) <> 'object' THEN
        RAISE EXCEPTION 'the arguments of an offline Tool run are an object'
            USING ERRCODE = '22023';
    END IF;

    SELECT * INTO v_run FROM agent_runs
     WHERE id = p_agent_run_id AND program_id = p;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'agent run % is not a run of this Program', p_agent_run_id
            USING ERRCODE = '23503';
    END IF;
    IF v_run.finished_at IS NOT NULL THEN
        RAISE EXCEPTION 'agent run % has already ended', v_run.label
            USING ERRCODE = '23514';
    END IF;

    -- The Halt, and it is the only policy gate this verb applies. The risk gate
    -- decides whether a request may leave, mints the capability that lets it,
    -- and files a question when it will not; an offline run makes no request
    -- and is given no capability, so putting it through that gate would be
    -- asking a question about egress that has no egress in it. What a Halt
    -- means -- no new work until an operator lifts it -- does reach here, and
    -- starting a process is new work.
    IF EXISTS (SELECT 1 FROM program_halts h
                WHERE h.program_id = p AND h.status = 'halted') THEN
        RAISE EXCEPTION 'the Program is Halted and may not start new work'
            USING ERRCODE = '42501',
                  HINT = 'rk resume lifts the Halt';
    END IF;

    v_tool := rk2_offline_tool(p_tool);

    IF p_version IS NULL OR p_version !~ v_tool.version_pattern THEN
        RAISE EXCEPTION '% reported version %, which is not a version this registry admits',
            p_tool, coalesce(p_version, '<none>')
            USING ERRCODE = '22023',
                  HINT = 'the image holds a different build of the tool than the registry describes';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM offline_tool_roles r
                    WHERE r.tool = p_tool AND r.role = v_run.role) THEN
        RAISE EXCEPTION 'the % role may not run %', v_run.role, p_tool
            USING ERRCODE = '42501';
    END IF;

    -- Extra arguments first, and by name, so the refusal says which one. A verb
    -- that ignored what it did not recognise would run a shorter command than
    -- the one it was asked for and report success.
    FOR v_name IN SELECT jsonb_object_keys(p_arguments) LOOP
        IF NOT EXISTS (SELECT 1 FROM offline_tool_arguments a
                        WHERE a.tool = p_tool AND a.name = v_name) THEN
            RAISE EXCEPTION '% takes no argument named %', p_tool, v_name
                USING ERRCODE = '22023';
        END IF;
    END LOOP;

    FOR v_arg IN
        SELECT * FROM offline_tool_arguments WHERE tool = p_tool ORDER BY position
    LOOP
        v_value := p_arguments ->> v_arg.name;
        IF v_value IS NULL THEN
            IF v_arg.required THEN
                RAISE EXCEPTION '% requires the argument %', p_tool, v_arg.name
                    USING ERRCODE = '22023';
            END IF;
            CONTINUE;
        END IF;
        IF jsonb_typeof(p_arguments -> v_arg.name) <> 'string' THEN
            -- Every value is a word on a command line, so every value is a
            -- string here. A number would be accepted by `->>` and would make
            -- the argv depend on how jsonb renders it.
            RAISE EXCEPTION 'the argument % is given as text', v_arg.name
                USING ERRCODE = '22023';
        END IF;

        SELECT * INTO v_kind FROM offline_argument_kinds
         WHERE value_kind = v_arg.value_kind;
        IF v_value !~ v_kind.pattern THEN
            RAISE EXCEPTION 'the argument % is not a well formed %', v_arg.name, v_arg.value_kind
                USING ERRCODE = '22023';
        END IF;
        IF v_arg.pattern IS NOT NULL AND v_value !~ v_arg.pattern THEN
            RAISE EXCEPTION 'the argument % does not match what % accepts there',
                v_arg.name, p_tool USING ERRCODE = '22023';
        END IF;
        IF v_arg.choices IS NOT NULL AND NOT (v_value = ANY (v_arg.choices)) THEN
            RAISE EXCEPTION 'the argument % is not one of %',
                v_arg.name, array_to_string(v_arg.choices, ', ') USING ERRCODE = '22023';
        END IF;

        IF v_arg.flag IS NOT NULL THEN
            v_argv := v_argv || v_arg.flag;
        END IF;

        IF v_kind.materialised THEN
            SELECT r.sha256 INTO v_sha FROM artifact_references r
             WHERE r.program_id = p AND r.label = v_value;
            IF v_sha IS NULL THEN
                -- The same answer for a label nobody holds and a label another
                -- Program holds. Two answers here would make the argument a way
                -- to ask whether some other Program has these bytes.
                RAISE EXCEPTION '% is not an artifact of this Program', v_value
                    USING ERRCODE = '42704';
            END IF;
            v_inputs := v_inputs || jsonb_build_object(
                'argument', v_arg.name, 'label', v_value, 'sha256', v_sha,
                'path', rk2_offline_input_path(v_value));
            v_argv := v_argv || rk2_offline_input_path(v_value);
        ELSE
            v_argv := v_argv || v_value;
        END IF;
    END LOOP;

    SELECT coalesce(jsonb_agg(jsonb_build_object('name', o.name) ORDER BY o.name), '[]'::jsonb)
      INTO v_outputs FROM offline_tool_outputs o WHERE o.tool = p_tool;

    -- The row, and nothing has started. `args` records what was asked for --
    -- the tool and the arguments as given -- rather than the argv, because the
    -- argv is derivable from those two and the registry, and the thing worth
    -- keeping is the request. 022 redacts `args` from the event payload, which
    -- is what a stored filter should be.
    INSERT INTO tool_runs
        (program_id, agent_run_id, task_id, tool, args, status, transport,
         offline_tool, tool_version)
    VALUES
        (p, v_run.id, v_run.task_id, 'mcp__rk2__run_tool',
         jsonb_build_object('tool_name', p_tool, 'arguments', p_arguments),
         'running', 'runtime', p_tool, p_version)
    RETURNING id, label INTO v_id, v_label;

    RETURN jsonb_build_object(
        'tool_run_id', v_id,
        'tool_run', v_label,
        'tool', p_tool,
        'version', p_version,
        'executable', v_tool.executable,
        'argv', to_jsonb(array_prepend(v_tool.executable, v_argv)),
        'network', v_tool.network,
        'timeout_seconds', v_tool.timeout_seconds,
        'memory_mb', v_tool.memory_mb,
        'cpu_quota', v_tool.cpu_quota,
        'pids_limit', v_tool.pids_limit,
        'max_output_bytes', v_tool.max_output_bytes,
        'inputs', v_inputs,
        'outputs', v_outputs,
        'workspace', CASE WHEN jsonb_array_length(v_outputs) > 0
                          THEN rk2_offline_workspace() END);
END $fn$;

COMMENT ON FUNCTION open_offline_tool_run(uuid, text, text, jsonb) IS
    'Validate one offline tool call against the registry, record it before '
    'anything starts, and return the argv and the ceilings the runtime is to '
    'run it under. Every refusal is a raise: an unknown or disabled tool, a '
    'version the registry does not admit, a role that may not run it, an '
    'argument it does not declare, a required one missing, a value outside its '
    'kind, and an Artifact this Program does not hold.';

CREATE FUNCTION close_offline_tool_run(
        p_tool_run_id uuid,
        p_status      text,
        p_exit_code   integer DEFAULT NULL,
        p_detail      text DEFAULT NULL)
RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p       uuid := rk2_program_required();
    v_run   tool_runs%ROWTYPE;
    v_kept  bigint;
BEGIN
    IF p_status NOT IN ('success','error') THEN
        RAISE EXCEPTION 'an offline Tool run closes as success or error, not %', p_status
            USING ERRCODE = '22023';
    END IF;

    SELECT * INTO v_run FROM tool_runs
     WHERE id = p_tool_run_id AND program_id = p FOR UPDATE;
    IF NOT FOUND OR v_run.offline_tool IS NULL THEN
        RAISE EXCEPTION 'tool run % is not an offline Tool run of this Program',
            p_tool_run_id USING ERRCODE = '23503';
    END IF;
    IF v_run.status <> 'running' THEN
        RAISE EXCEPTION 'tool run % was already closed as %', v_run.label, v_run.status
            USING ERRCODE = '23514';
    END IF;

    SELECT count(*) INTO v_kept FROM tool_run_artifacts a WHERE a.tool_run_id = v_run.id;
    IF p_status = 'success' AND v_kept = 0 THEN
        -- A run that succeeded and kept nothing is a run whose output exists
        -- only in whatever the supervisor happened to print. Criterion 4 is
        -- that the output is the Artifacts, so a success with none of them is
        -- not a success this table can record.
        RAISE EXCEPTION 'tool run % stored none of its output', v_run.label
            USING ERRCODE = '23514',
                  HINT = 'record stdout, stderr and any declared outputs before closing a run as success';
    END IF;

    UPDATE tool_runs
       SET status = p_status,
           finished_at = now(),
           exit_code = p_exit_code,
           exit_detail = left(p_detail, 500)
     WHERE id = v_run.id;

    RETURN jsonb_build_object(
        'tool_run', v_run.label, 'status', p_status,
        'exit_code', p_exit_code, 'artifacts', v_kept);
END $fn$;

COMMENT ON FUNCTION close_offline_tool_run(uuid, text, integer, text) IS
    'Close one offline Tool run, once. A success has to have stored its output; '
    'a failure, a timeout and an overrun close as error and say so in the '
    'detail, because what a reader needs from those is that the run ended and '
    'why, not that it produced nothing.';

REVOKE ALL ON FUNCTION rk2_offline_tool(text),
                       open_offline_tool_run(uuid, text, text, jsonb),
                       close_offline_tool_run(uuid, text, integer, text)
    FROM PUBLIC, rk2_state, rk2_proxy, rk2_human;
GRANT EXECUTE ON FUNCTION rk2_offline_tool(text),
                          open_offline_tool_run(uuid, text, text, jsonb),
                          close_offline_tool_run(uuid, text, integer, text)
    TO rk2_runtime;

-- Not `rk2_state`, for the reason the whole boundary exists: the connection a
-- model's own code can reach is the one that must not be able to start a
-- process. The model asks through the contract, the runtime decides, and this
-- is the runtime's verb.


-- ---------------------------------------------------------------------------
-- 6. Shell text alone cannot create an Observation
-- ---------------------------------------------------------------------------
-- Criterion 5. An Observation citing an offline Tool run is a claim about what
-- that run's output said, so it stands or falls on the output still existing.
-- One rule, on the canonical table, rather than a copy of it in the staging
-- review as well: `promote_proposal` already catches `check_violation` per
-- element and records the server's sentence beside the element that earned it,
-- so a proposal citing a run that kept nothing loses that element and keeps the
-- rest -- which is the behaviour a second copy would have been written to get.
--
-- No new `proposal_drops` reason for the same reason. A reason nothing writes is
-- a vocabulary entry an agent could read the list and plan for, and what it
-- actually gets is `refused_by_invariant` with `tool run TR3 stored no output to
-- observe` in `cited`, which says more than a code would.

CREATE FUNCTION observation_cites_stored_tool_output() RETURNS trigger
LANGUAGE plpgsql AS $fn$
DECLARE v_run tool_runs%ROWTYPE;
BEGIN
    IF NEW.provenance_kind <> 'tool_run' THEN
        RETURN NEW;
    END IF;
    SELECT * INTO v_run FROM tool_runs WHERE id = NEW.tool_run_id;
    -- Every other kind of Tool run is somebody else's rule. The hook-opened
    -- ones are 022's, the proxy's own are 038's, and neither of them produces
    -- files: this rule is about a process whose entire output was bytes on two
    -- pipes.
    IF NOT FOUND OR v_run.offline_tool IS NULL THEN
        RETURN NEW;
    END IF;
    IF v_run.status = 'running' THEN
        RAISE EXCEPTION 'tool run % has not finished', v_run.label
            USING ERRCODE = '23514',
                  HINT = 'an observation about a run still in flight is a claim about output nothing has read';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM tool_run_artifacts a WHERE a.tool_run_id = v_run.id) THEN
        RAISE EXCEPTION 'tool run % stored no output to observe', v_run.label
            USING ERRCODE = '23514',
                  HINT = 'an offline tool run backs an observation through the artifacts it produced, never through what a model said about it';
    END IF;
    RETURN NEW;
END $fn$;

CREATE TRIGGER observations_tool_output_guard
    BEFORE INSERT ON observations
    FOR EACH ROW EXECUTE FUNCTION observation_cites_stored_tool_output();

COMMENT ON FUNCTION observation_cites_stored_tool_output() IS
    'An Observation citing an offline Tool run needs that run to have finished '
    'and to have kept what it produced. Without it the citation is a label, and '
    'the sentence beside it is the only evidence -- which is the thing ticket 30 '
    'says is not evidence.';


-- ---------------------------------------------------------------------------
-- 7. What can go wrong, as rows
-- ---------------------------------------------------------------------------
CREATE FUNCTION check_offline_tools()
RETURNS TABLE (problem text, detail text)
LANGUAGE sql STABLE AS $fn$
    -- criterion 1: a tool no role may run is a registry row that can never
    -- become a process, which reads as an allowlist entry and is not one.
    SELECT 'tool_no_role_may_run'::text, t.tool
      FROM offline_tools t
     WHERE t.enabled
       AND NOT EXISTS (SELECT 1 FROM offline_tool_roles r WHERE r.tool = t.tool)
UNION ALL
    -- criterion 1: an enumerated choice its own kind would refuse. The verb
    -- applies the kind first, so such a value is unreachable and the row reads
    -- as an option that exists.
    SELECT 'choice_outside_its_kind', a.tool || '.' || a.name || ' = ' || c.value
      FROM offline_tool_arguments a
      JOIN offline_argument_kinds k ON k.value_kind = a.value_kind
      CROSS JOIN LATERAL unnest(a.choices) AS c(value)
     WHERE c.value !~ k.pattern
UNION ALL
    -- criterion 1: an argument whose narrowing pattern is not narrower. Asked
    -- of the values the choices name, which is the only set this can be decided
    -- over without solving regular expression containment.
    SELECT 'argument_pattern_widens_its_kind', a.tool || '.' || a.name || ' = ' || c.value
      FROM offline_tool_arguments a
      JOIN offline_argument_kinds k ON k.value_kind = a.value_kind
      CROSS JOIN LATERAL unnest(a.choices) AS c(value)
     WHERE a.pattern IS NOT NULL AND c.value ~ a.pattern AND c.value !~ k.pattern
UNION ALL
    -- criterion 2: a tool declared to have no network, and a Receipt says it
    -- reached the wire. The strongest reading available from rows: the Receipt
    -- is written by the door, on the door's own connection.
    SELECT 'offline_run_reached_the_wire', tr.label
      FROM tool_runs tr
      JOIN offline_tools t ON t.tool = tr.offline_tool
      JOIN receipts r ON r.tool_run_id = tr.id
     WHERE t.network = 'none'
UNION ALL
    -- criterion 3: nothing closed it, and by now nothing will. Twice the tool's
    -- own timeout, so this is the supervisor dying rather than a slow run --
    -- `receipt_open_past_deadline` catches the same thing an hour later, which
    -- is the right horizon for a run whose duration nothing declared.
    SELECT 'offline_run_open_past_its_timeout', tr.label
      FROM tool_runs tr
      JOIN offline_tools t ON t.tool = tr.offline_tool
     WHERE tr.status = 'running'
       AND tr.started_at < now() - make_interval(secs => t.timeout_seconds * 2)
UNION ALL
    -- criterion 4: closed as a success with nothing kept. `close_offline_tool_run`
    -- refuses it; this finds the row that got there another way.
    SELECT 'successful_run_stored_nothing', tr.label
      FROM tool_runs tr
     WHERE tr.offline_tool IS NOT NULL AND tr.status = 'success'
       AND NOT EXISTS (SELECT 1 FROM tool_run_artifacts a WHERE a.tool_run_id = tr.id)
UNION ALL
    -- criterion 4: the version recorded on a run is one its tool's registry row
    -- would now refuse. Not a fault of the run -- it recorded what it read --
    -- but a pattern that was tightened under stored evidence, and an operator
    -- reading provenance should be told which runs it no longer describes.
    SELECT 'recorded_version_now_refused', tr.label || ' ran ' || tr.tool_version
      FROM tool_runs tr
      JOIN offline_tools t ON t.tool = tr.offline_tool
     WHERE tr.tool_version !~ t.version_pattern
UNION ALL
    -- criterion 6: output whose bytes this Program does not hold. The trigger
    -- refuses it on the way in; a reference purged afterwards would leave the
    -- link pointing at bytes nothing can reach.
    SELECT 'output_artifact_not_held', a.id::text
      FROM tool_run_artifacts a
     WHERE NOT EXISTS (SELECT 1 FROM artifact_references r
                        WHERE r.program_id = a.program_id AND r.sha256 = a.sha256)
UNION ALL
    -- criterion 5, from the other side: the Observation exists and the output
    -- behind it does not.
    SELECT 'observation_on_unstored_output', o.label
      FROM observations o
      JOIN tool_runs tr ON tr.id = o.tool_run_id
     WHERE tr.offline_tool IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM tool_run_artifacts a WHERE a.tool_run_id = tr.id)
UNION ALL
    -- the registry is the runtime's and the agent connection may not read it.
    -- A model that can read the ceilings is a model that can sit just under
    -- them, and one that can read the executable list has an inventory.
    SELECT 'registry_reachable_by_agent', table_name || '.' || privilege_type
      FROM information_schema.table_privileges
     WHERE grantee = 'rk2_state'
       AND table_name IN ('offline_tools','offline_tool_arguments',
                          'offline_tool_outputs','offline_tool_roles',
                          'offline_argument_kinds')
UNION ALL
    -- and no verb over it is reachable from a connection a model can influence,
    -- including the lookup: a function is executable by PUBLIC unless something
    -- says otherwise, and a readable registry behind a callable wrapper is a
    -- readable registry.
    SELECT 'offline_verb_reachable', p.proname || ' by ' || r.rolname
      FROM pg_proc p
      CROSS JOIN (VALUES ('rk2_state'),('rk2_proxy')) AS r(rolname)
     WHERE p.pronamespace = 'public'::regnamespace
       AND p.proname IN ('rk2_offline_tool','open_offline_tool_run',
                         'close_offline_tool_run')
       AND has_function_privilege(r.rolname, p.oid, 'EXECUTE')
$fn$;

COMMENT ON FUNCTION check_offline_tools() IS
    'What an offline tool run can get wrong: a registered tool no role may run, '
    'an enumerated value its own kind refuses, a run of a network-less tool with '
    'a Receipt against it, a run nothing closed, a success that kept nothing, a '
    'recorded version the registry would now refuse, output whose bytes are not '
    'held, an Observation on output that is gone, and the registry or its verbs '
    'reachable from a connection a model can influence.';

INSERT INTO standing_checks (name, query, owner_ticket, note) VALUES
    ('offline_tools', 'SELECT * FROM check_offline_tools()', '30',
     'every offline tool run is registered, bounded, closed, stored and citable');


-- ---------------------------------------------------------------------------
-- 8. The invariants this file must not have broken
-- ---------------------------------------------------------------------------
-- The runner's finalizers run after the last migration, and every assertion
-- below is about the database they will leave rather than the one this file
-- ends with: the triggers written above are still `O` until 027 sweeps them,
-- and `tool_run_artifacts` has no policy on it until 033's loop reaches it.
-- Idempotent by construction, which is what lets a migration ask its own
-- questions of the finished state.
SELECT enforce_always_triggers();
SELECT apply_state_rls();
SELECT apply_state_grants();
SELECT enforce_fk_fire_order();

DO $$
DECLARE n integer; d text;
BEGIN
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_offline_tools();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-30 refuses to finish: % offline tool violation(s): %', n, d;
    END IF;

    -- The registry is program-global, the link table is not, and getting that
    -- backwards is the failure 017 exists to catch.
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_program_isolation();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-30 breaks program isolation (% problems): %', n, d;
    END IF;

    SELECT count(*), string_agg(problem || ': ' || object || ' ' || detail, '; ')
      INTO n, d FROM check_rls_coverage();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-30 leaves a scoped table unguarded (% problems): %', n, d;
    END IF;

    SELECT count(*), string_agg(problem || ': ' || object || ' ' || detail, '; ')
      INTO n, d FROM check_state_grants();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-30 changes the agent read surface (% problems): %', n, d;
    END IF;

    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_event_coverage();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-30 leaves a table unaccounted for in the log (% problems): %', n, d;
    END IF;

    SELECT count(*), string_agg(problem || ': ' || object || ' ' || detail, '; ')
      INTO n, d FROM check_purge_reachability();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-30 makes a Program unpurgeable (% problems): %', n, d;
    END IF;
END $$;
