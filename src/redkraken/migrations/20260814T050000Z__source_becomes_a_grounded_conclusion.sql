-- ===========================================================================
-- Production harness 32 -- the JS analyst reads a source Artifact
-- ===========================================================================
-- The `js_analyst` role has existed since 019 and has had nothing to run: the
-- roster gives it `exec.tool_run` without `net.request`, and 030's registry
-- holds one tool that queries JSON. This file gives it the three runs the
-- ticket names -- parsing, endpoint extraction and source-map recovery -- and,
-- more to the point, makes what comes out of them citable as something other
-- than a sentence a model wrote after looking at a bundle.
--
-- The problem this file exists for is narrow and specific. An analyst reading
-- minified JavaScript is the single easiest place in this harness to invent an
-- endpoint: the input is enormous, the model sees a fraction of it, and a route
-- that sounds right is indistinguishable in prose from a route that is there.
-- So nothing here trusts the reading. A conclusion names the source Artifact it
-- came from, the Tool run that read it, and the exact bytes that run was given,
-- and promotion refuses it when any of those three do not hold. A conclusion
-- that names a route is held to one more thing: the run it cites has to have
-- named that route, out of its own answer, which is the difference between a
-- reading that could have come from the file and one that did.
--
-- Six things, one per criterion:
--
--   1. What an analysis tool may be given is narrowed to source.
--      `artifact_reference_kinds` turns 006's three-value check into the table
--      it always was, and `offline_tool_arguments.artifact_kind` lets an
--      argument require one of them. The three tools below require `source`,
--      so an analyst cannot point one at a stored response body or at the
--      output of its own previous run and call the result source analysis.
--   2. None of them has a network. `offline_tools.network` is already the only
--      way an offline tool reaches anything, all three rows say `none`, and
--      `check_source_conclusions` reports a source tool that ever acquires one.
--      There is no credential path to close: `open_offline_tool_run` mints no
--      capability, and the container these run in gets no identity, no proxy
--      and no database.
--   3. What ran, and over exactly which bytes. `tool_run_inputs` is one row per
--      materialised argument, carrying the Artifact's label, its hash and the
--      kind it is held as; `tool_runs.analyser_sha256` carries the hash of the
--      analyser the harness shipped into the container. Between them a run says
--      what its output is a function of, which is what makes a second run of
--      the same tool over the same bytes a check rather than a repetition.
--   4. A conclusion cites the source it came from. An element of a staged
--      result may carry `source_artifact_label` and `source_sha256` beside the
--      Tool run it already cites, and `rk2_source_citation` is the one place
--      that decides whether the citation holds.
--   5. Promotion refuses the ways it can fail to. The Artifact is not one this
--      Program holds, the hash the element names is not the hash the label
--      resolves to, the Artifact is held as something other than source, the
--      cited run never read it -- or the run read it and never named the route
--      the element proposes, which is `tool_run_paths` and is the one refusal
--      that is about the answer rather than about the citation. Each is its own
--      `proposal_drops.reason`, because an agent told "your citation is wrong"
--      learns nothing it can act on.
--   6. The negative controls are the refusals themselves, and
--      `tests/test_database.py` walks a synthetic bundle through all three
--      tools, holds the extracted routes against the ones the bundle really
--      calls, and shows the decoy -- a path that appears in the file and is
--      never requested -- staying out of both the tool's answer and the
--      canonical surface.


-- ---------------------------------------------------------------------------
-- 1. What a Program holds an Artifact as
-- ---------------------------------------------------------------------------
-- 006 wrote the three kinds as a check constraint, which was right when
-- nothing else in the schema had an opinion about them. Two things now do --
-- an argument that may only be given source, and a promotion that may only
-- ground a conclusion in source -- and a vocabulary that two tables refer to
-- is a table. The values are unchanged, so nothing that already holds an
-- Artifact has to move.

CREATE TABLE artifact_reference_kinds (
    kind        text PRIMARY KEY,
    description text NOT NULL
);

INSERT INTO artifact_reference_kinds (kind, description) VALUES
    ('runtime',     'the harness stored these bytes in the course of doing its own work'),
    ('tool_output', 'a stream or declared output of a Tool run this Program made'),
    ('source',      'application source this Program fetched or recovered, and the one '
                    'kind a source analysis tool may be pointed at');

COMMENT ON TABLE artifact_reference_kinds IS
    'Why a Program holds an Artifact, as a table rather than a check '
    'constraint: the argument schema and the promotion rule both refer to '
    '`source`, and a vocabulary two things depend on needs a key they can '
    'point at.';

ALTER TABLE artifact_references DROP CONSTRAINT artifact_references_kind_check;
ALTER TABLE artifact_references ADD CONSTRAINT artifact_references_kind_fkey
    FOREIGN KEY (kind) REFERENCES artifact_reference_kinds(kind);

INSERT INTO program_global_tables (table_name, reason) VALUES
    ('artifact_reference_kinds',
     'the vocabulary a reference is labelled in; a per-program copy would let '
     'one Program mean something wider by source than the promotion rule does');

INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
    ('artifact_reference_kinds', 'reference',
     'why an Artifact is held, changed only by migration', '32');

GRANT SELECT ON artifact_reference_kinds TO rk2_runtime;


-- ---------------------------------------------------------------------------
-- 2. Three columns the registry was missing
-- ---------------------------------------------------------------------------
-- 030's registry describes tools an image happens to hold. Two of the three
-- runs this ticket needs are not in any image: parsing JavaScript and reading
-- a source map are this harness's own work, and shipping them as a second
-- container image would put the analysis outside the reach of the suite that
-- has to prove it does not invent routes.
--
-- So the registry gains the ability to name a program the harness ships. The
-- pattern is 031's, one level up: `browser.py` puts its driver into the
-- container as a read-only input and runs `python3 <driver>`, and this makes
-- that a row rather than a special case. What the runtime supplies is the
-- bytes and their hash; what the registry supplies is which file, and the
-- refusal when the two do not agree about whether there is one.

ALTER TABLE offline_tools ADD COLUMN analyser text
    CHECK (analyser IS NULL OR analyser ~ '^[a-z][a-z0-9_]{0,31}\.py$');

COMMENT ON COLUMN offline_tools.analyser IS
    'A program this harness ships, by bare filename, run by the executable '
    'above with the tool name as its first argument. NULL for a tool the image '
    'provides. The runtime reads the file off its own disk, hashes it and puts '
    'it in the container read-only -- it is never an Artifact, because it is '
    'not something a Program came to hold.';

-- The subcommand is the tool name and is not a column. Three registry rows
-- that differ only in which question they ask of the same file would otherwise
-- carry a fourth string each, and a row whose name and whose subcommand
-- disagreed would run something other than what an operator reading the
-- registry thinks it runs.

ALTER TABLE offline_tool_arguments ADD COLUMN artifact_kind text
    REFERENCES artifact_reference_kinds(kind);

ALTER TABLE offline_tool_arguments ADD CONSTRAINT offline_tool_arguments_kind_ck
    CHECK (artifact_kind IS NULL OR value_kind = 'artifact');

COMMENT ON COLUMN offline_tool_arguments.artifact_kind IS
    'Which kind of held Artifact this argument admits, or NULL for any. '
    'Criterion 1 in one column: a source analysis tool that could be pointed '
    'at a stored response body would produce conclusions about the target''s '
    'answers under the name of conclusions about its source.';

ALTER TABLE offline_tool_outputs ADD COLUMN reference_kind text NOT NULL
    DEFAULT 'tool_output' REFERENCES artifact_reference_kinds(kind);

COMMENT ON COLUMN offline_tool_outputs.reference_kind IS
    'What this Program comes to hold a declared output as. `tool_output` for '
    'almost everything; `source` for a recovered original file, which is '
    'source that was always there and is only now readable. Declared by '
    'migration rather than chosen at runtime, so nothing an agent does can '
    'make its own output into source for the next tool.';

-- `analyser_sha256` and not `program_sha256`: a Program is a bounty engagement
-- here, and a column beside `program_id` spelling the word for something else
-- would make the glossary's one reserved term ambiguous on a single row.
ALTER TABLE tool_runs ADD COLUMN analyser_sha256 text
    CHECK (analyser_sha256 IS NULL OR analyser_sha256 ~ '^[0-9a-f]{64}$');

ALTER TABLE tool_runs ADD CONSTRAINT tool_runs_analyser_sha256_ck
    CHECK (analyser_sha256 IS NULL OR offline_tool IS NOT NULL);

COMMENT ON COLUMN tool_runs.analyser_sha256 IS
    'The exact analyser bytes that ran, for a tool whose registry row names '
    'one. `tool_version` says what the program calls itself and this says what '
    'it was -- the same distinction 030 draws between the pattern the registry '
    'admits and the version the image reported, and provenance in the same '
    'sense: the registry never sees the file, so this is what the runtime '
    'hashed and not a claim the database can check. What it buys is that two '
    'runs of one tool over one Artifact are comparable, and that a conclusion '
    'rests on bytes that can be named rather than on a tool name.';


-- ---------------------------------------------------------------------------
-- 3. What a run read, and what it said
-- ---------------------------------------------------------------------------
-- Criterion 3. `tool_runs.args` has carried the labels since 030, which is
-- what was asked for; this carries what was given, which is not the same fact.
-- A label is resolved at open time and the resolution is what the tool saw, so
-- a conclusion citing this run cites bytes rather than a name that pointed at
-- them once.
--
-- The hash is not derivable from the label afterwards: `artifact_references`
-- is immutable, but a Program can be purged, and a run whose inputs could only
-- be recovered by re-resolving would lose its provenance exactly when someone
-- asks what it was.

CREATE TABLE tool_run_inputs (
    id             uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id     uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    tool_run_id    uuid NOT NULL,
    argument       text NOT NULL CHECK (argument ~ '^[a-z][a-z0-9_]{0,31}$'),
    artifact_label text NOT NULL,
    sha256         text NOT NULL REFERENCES artifacts(sha256),
    reference_kind text NOT NULL REFERENCES artifact_reference_kinds(kind),
    recorded_at    timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (tool_run_id, program_id) REFERENCES tool_runs (id, program_id),
    -- One argument takes one Artifact. The same Artifact under two arguments is
    -- a tool given the same file twice, which is legal and is two rows.
    UNIQUE (tool_run_id, argument)
);

CREATE INDEX tool_run_inputs_run_idx ON tool_run_inputs (tool_run_id);
CREATE INDEX tool_run_inputs_sha_idx ON tool_run_inputs (tool_run_id, sha256);

COMMENT ON TABLE tool_run_inputs IS
    'Which content-addressed Artifacts one offline Tool run was given, by '
    'argument. The half of provenance 030 left in `args`: that says which '
    'labels were asked for and this says which bytes arrived, which is what a '
    'conclusion citing the run is a function of.';

INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
    ('tool_run_inputs', 'program_id', 'program-scoped: the purge root');

INSERT INTO event_types (id, family, subject_table, description) VALUES
    ('tool_run.input_recorded', 'row', 'tool_run_inputs',
     'an offline Tool run was given the bytes of one Artifact this Program holds');

INSERT INTO event_table_config
    (table_name, created_type, updated_type, ignored_columns, redacted_columns) VALUES
    ('tool_run_inputs', 'tool_run.input_recorded', NULL, '{}', '{}');

SELECT attach_event_triggers();

-- Immutable for `tool_run_artifacts`' reason, read backwards. That one says a
-- run produced these bytes; this one says a run was handed them, and a row that
-- could be repointed would let a conclusion's input be changed under it after
-- the conclusion was promoted.
CREATE TRIGGER tool_run_inputs_immutable
    BEFORE UPDATE OR DELETE ON tool_run_inputs
    FOR EACH ROW EXECUTE FUNCTION reject_mutation_unless_purging();

-- The analyst has to be able to see this, and for the reason 030 gives about
-- the output table: an agent that may cite which bytes its run read, and cannot
-- see them, can only cite what it was told in prose. The ceilings and the
-- registry stay where 030 left them.
INSERT INTO state_read_surface (table_name, column_name, added_by) VALUES
    ('tool_run_inputs', 'tool_run_id',    'ph2-32'),
    ('tool_run_inputs', 'argument',       'ph2-32'),
    ('tool_run_inputs', 'artifact_label', 'ph2-32'),
    ('tool_run_inputs', 'sha256',         'ph2-32'),
    ('tool_run_inputs', 'reference_kind', 'ph2-32'),
    ('tool_run_inputs', 'recorded_at',    'ph2-32'),
    ('tool_runs',       'analyser_sha256', 'ph2-32');

CREATE FUNCTION tool_run_input_is_this_runs_input() RETURNS trigger
LANGUAGE plpgsql AS $fn$
DECLARE
    v_run tool_runs%ROWTYPE;
    v_ref artifact_references%ROWTYPE;
BEGIN
    SELECT * INTO v_run FROM tool_runs
     WHERE id = NEW.tool_run_id AND program_id = NEW.program_id;
    IF NOT FOUND OR v_run.offline_tool IS NULL THEN
        RAISE EXCEPTION 'tool run % is not an offline Tool run of this Program',
            NEW.tool_run_id USING ERRCODE = '23503';
    END IF;
    IF v_run.status <> 'running' THEN
        RAISE EXCEPTION 'tool run % has already been closed as %',
            v_run.label, v_run.status USING ERRCODE = '23514';
    END IF;

    SELECT * INTO v_ref FROM artifact_references r
     WHERE r.program_id = NEW.program_id AND r.label = NEW.artifact_label;
    IF NOT FOUND THEN
        RAISE EXCEPTION '% is not an artifact of this Program', NEW.artifact_label
            USING ERRCODE = '42704';
    END IF;
    IF v_ref.sha256 <> NEW.sha256 OR v_ref.kind <> NEW.reference_kind THEN
        RAISE EXCEPTION '% does not name those bytes held that way', NEW.artifact_label
            USING ERRCODE = '23514',
                  HINT = 'the label, the hash and the kind are one reference and are recorded together';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM offline_tool_arguments a
                    WHERE a.tool = v_run.offline_tool AND a.name = NEW.argument
                      AND a.value_kind = 'artifact') THEN
        RAISE EXCEPTION '% takes no Artifact argument named %',
            v_run.offline_tool, NEW.argument USING ERRCODE = '42704';
    END IF;
    RETURN NEW;
END $fn$;

CREATE TRIGGER tool_run_inputs_is_this_runs_input
    BEFORE INSERT ON tool_run_inputs
    FOR EACH ROW EXECUTE FUNCTION tool_run_input_is_this_runs_input();

COMMENT ON FUNCTION tool_run_input_is_this_runs_input() IS
    'The three things an input row must be able to prove: the run is this '
    'Program''s offline run and still open, the label names exactly those bytes '
    'held exactly that way, and the argument is one the tool declares as an '
    'Artifact.';

GRANT SELECT, INSERT ON tool_run_inputs TO rk2_runtime;


-- The other half of a citation, and the half the database cannot read for
-- itself. `tool_run_inputs` says which bytes went in; this says which request
-- paths the answer that came out names. Both are needed for the same reason
-- and neither substitutes for the other: an Artifact and a run prove a
-- conclusion could have come from those bytes, and only the run's own answer
-- proves the run said it.
--
-- Filed here rather than derived on demand because the answer is an Artifact
-- in the store and the store is on the disk. The runtime reads it once, while
-- it has it, and what lands here is checkable afterwards by anyone: the row
-- names the hash it was read out of, so re-deriving it is reading those bytes
-- again.
CREATE TABLE tool_run_paths (
    id          uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id  uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    tool_run_id uuid NOT NULL,
    sha256      text NOT NULL REFERENCES artifacts(sha256),
    path        text NOT NULL CHECK (path <> '' AND length(path) <= 2048),
    recorded_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (tool_run_id, program_id) REFERENCES tool_runs (id, program_id),
    -- One row per path per run. An answer that names the same path from two
    -- call sites still names one path, and the sites are in the answer.
    UNIQUE (tool_run_id, path)
);

CREATE INDEX tool_run_paths_run_idx ON tool_run_paths (tool_run_id);

COMMENT ON TABLE tool_run_paths IS
    'Every request path one analyser run''s own answer names, by the hash of '
    'the bytes it was read out of. What a promoted route is held against: a '
    'citation says a conclusion could have come from an Artifact, and this is '
    'what says the run that read it reported the route.';

COMMENT ON COLUMN tool_run_paths.path IS
    'As the analyser printed it. Held against a proposal through '
    '`rk2_clean_path`, so the two are compared in the one spelling this schema '
    'stores rather than by string equality.';

INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
    ('tool_run_paths', 'program_id', 'program-scoped: the purge root');

INSERT INTO event_types (id, family, subject_table, description) VALUES
    ('tool_run.path_named', 'row', 'tool_run_paths',
     'an analyser run''s answer named one request path in the source it read');

INSERT INTO event_table_config
    (table_name, created_type, updated_type, ignored_columns, redacted_columns) VALUES
    ('tool_run_paths', 'tool_run.path_named', NULL, '{}', '{}');

SELECT attach_event_triggers();

-- Immutable for the reason the other two link tables are, and this one has the
-- sharpest version of it: a row that could be edited afterwards would let the
-- evidence a promoted route was checked against be rewritten to fit it.
CREATE TRIGGER tool_run_paths_immutable
    BEFORE UPDATE OR DELETE ON tool_run_paths
    FOR EACH ROW EXECUTE FUNCTION reject_mutation_unless_purging();

-- Readable by the analyst, and it is the one read here that changes what a
-- model can do rather than only what it can see: an agent that can ask which
-- paths its run named can propose exactly those and stop guessing.
INSERT INTO state_read_surface (table_name, column_name, added_by) VALUES
    ('tool_run_paths', 'tool_run_id', 'ph2-32'),
    ('tool_run_paths', 'sha256',      'ph2-32'),
    ('tool_run_paths', 'path',        'ph2-32'),
    ('tool_run_paths', 'recorded_at', 'ph2-32');

CREATE FUNCTION tool_run_path_is_this_runs_answer() RETURNS trigger
LANGUAGE plpgsql AS $fn$
DECLARE v_run tool_runs%ROWTYPE;
BEGIN
    SELECT * INTO v_run FROM tool_runs
     WHERE id = NEW.tool_run_id AND program_id = NEW.program_id;
    IF NOT FOUND OR v_run.offline_tool IS NULL THEN
        RAISE EXCEPTION 'tool run % is not an offline Tool run of this Program',
            NEW.tool_run_id USING ERRCODE = '23503';
    END IF;

    -- The whole of why this is trustworthy. An analyser is a program the
    -- harness shipped and hashed; a tool from the image is whatever the image
    -- holds, and one that could file rows here would be a way to print an
    -- invented route and have it become the ground truth routes are checked
    -- against.
    IF NOT EXISTS (SELECT 1 FROM offline_tools t
                    WHERE t.tool = v_run.offline_tool AND t.analyser IS NOT NULL) THEN
        RAISE EXCEPTION '% is not an analyser and names no paths', v_run.offline_tool
            USING ERRCODE = '23514',
                  HINT = 'only a harness-shipped analyser''s own answer is recorded';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM tool_run_artifacts a
                    WHERE a.tool_run_id = NEW.tool_run_id AND a.sha256 = NEW.sha256) THEN
        RAISE EXCEPTION 'tool run % did not produce those bytes', v_run.label
            USING ERRCODE = '23514',
                  HINT = 'a path is recorded against the answer it was read out of';
    END IF;

    -- Read out of the answer while the run is open, exactly as the output row
    -- beside it is. A row arriving later would be a claim about what a run
    -- reported, written after that run finished reporting.
    IF v_run.status <> 'running' THEN
        RAISE EXCEPTION 'tool run % has already been closed as %',
            v_run.label, v_run.status USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $fn$;

CREATE TRIGGER tool_run_paths_is_this_runs_answer
    BEFORE INSERT ON tool_run_paths
    FOR EACH ROW EXECUTE FUNCTION tool_run_path_is_this_runs_answer();

COMMENT ON FUNCTION tool_run_path_is_this_runs_answer() IS
    'The four things a recorded path must be able to prove: the run is this '
    'Program''s offline run, its tool is a harness analyser rather than '
    'something the image holds, the bytes it was read out of are bytes that '
    'run produced, and the run is still open.';

GRANT SELECT, INSERT ON tool_run_paths TO rk2_runtime;


-- ---------------------------------------------------------------------------
-- 4. The three tools
-- ---------------------------------------------------------------------------
-- One analyser file, asked three questions. They are three registry rows
-- rather than one tool with a mode because the ceilings differ, the arguments
-- differ, and only one of them writes a file -- and because a mode an agent
-- chooses is an argument, which would put "which analysis was this" inside the
-- thing being validated rather than in the row that says what ran.
--
-- The executable is the interpreter in the image, and the version answer comes
-- from the analyser rather than from Python: what has to be pinned is the
-- contract of the program that produces the evidence, and the interpreter that
-- ran it is already in the image the run recorded.

INSERT INTO offline_tools
    (tool, executable, version_argv, version_pattern, network, timeout_seconds,
     memory_mb, cpu_quota, pids_limit, max_output_bytes, analyser, description) VALUES
    ('js_parse', '/usr/local/bin/python3', '{--version}', '^rk2-jsscan [0-9]+$', 'none',
     120, 512, 1.0, 32, 4194304, 'jsscan.py',
     'read one source Artifact and report what it is made of: its size, its shape, '
     'the source map it points at and the string literals it holds'),
    ('js_routes', '/usr/local/bin/python3', '{--version}', '^rk2-jsscan [0-9]+$', 'none',
     120, 512, 1.0, 32, 4194304, 'jsscan.py',
     'extract every request path one source Artifact actually calls, each with the '
     'call site that grounds it'),
    ('js_map', '/usr/local/bin/python3', '{--version}', '^rk2-jsscan [0-9]+$', 'none',
     120, 512, 1.0, 32, 4194304, 'jsscan.py',
     'read one source map Artifact, index the original sources it carries, and '
     'recover one of them as a file');

INSERT INTO offline_tool_arguments
    (tool, name, position, flag, value_kind, required, pattern, choices,
     artifact_kind, description) VALUES
    ('js_parse',  'source', 0, NULL, 'artifact', true,  NULL, NULL, 'source',
     'the source Artifact to describe'),
    ('js_routes', 'source', 0, NULL, 'artifact', true,  NULL, NULL, 'source',
     'the source Artifact to extract request paths from'),
    ('js_map',    'map',    0, NULL, 'artifact', true,  NULL, NULL, 'source',
     'the source map Artifact to read'),
    -- Optional, and an index rather than a name: the analyser prints the index
    -- of every source the map carries, so the only way to name one is to have
    -- read that run's output. A name would be a string an agent could invent.
    ('js_map',    'select', 1, NULL, 'integer',  false, NULL, NULL, NULL,
     'which original source to recover, by its position in the index this tool prints');

INSERT INTO offline_tool_outputs (tool, name, reference_kind, description) VALUES
    ('js_map', 'source.js', 'source',
     'the recovered original file, held as source so the other two tools may be '
     'pointed at it');

INSERT INTO offline_tool_roles (tool, role) VALUES
    ('js_parse',  'js_analyst'),
    ('js_routes', 'js_analyst'),
    ('js_map',    'js_analyst');

-- Only the analyst. `recon` holds `jq` from 030 and finds hosts; reading a
-- bundle is what this role exists for, and a second role holding these tools
-- would be a second place a source conclusion could come from without the
-- roster having said so.


-- ---------------------------------------------------------------------------
-- 5. Opening a run records what it will read
-- ---------------------------------------------------------------------------
-- Dropped and rewritten rather than replaced in place: the signature grows a
-- parameter, and an overload would leave two verbs where the four-argument
-- call is ambiguous. Everything 030 refused is refused here in the same words;
-- what is added is the analyser, the kind an Artifact argument admits, and the
-- input rows.

CREATE FUNCTION rk2_offline_analyser_path(p_name text) RETURNS text
LANGUAGE sql IMMUTABLE AS $fn$ SELECT '/input/' || p_name $fn$;

COMMENT ON FUNCTION rk2_offline_analyser_path(text) IS
    'Where a harness-shipped analyser appears inside the container. The same '
    'directory the input Artifacts land in, and it cannot collide with one: an '
    'Artifact label is upper case and digits, and an analyser name ends in .py.';

DROP FUNCTION open_offline_tool_run(uuid, text, text, jsonb);

CREATE FUNCTION open_offline_tool_run(
        p_agent_run_id   uuid,
        p_tool           text,
        p_version        text,
        p_arguments      jsonb DEFAULT '{}'::jsonb,
        p_analyser_sha256 text DEFAULT NULL)
RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p         uuid := rk2_program_required();
    v_run     agent_runs%ROWTYPE;
    v_tool    offline_tools%ROWTYPE;
    v_arg     offline_tool_arguments%ROWTYPE;
    v_kind    offline_argument_kinds%ROWTYPE;
    v_ref     artifact_references%ROWTYPE;
    v_name    text;
    v_value   text;
    v_argv    text[] := '{}';
    v_inputs  jsonb := '[]'::jsonb;
    v_outputs jsonb;
    v_input   jsonb;
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

    -- Both directions. A tool that names an analyser and was given no hash is a
    -- run whose evidence would have no statement of what produced it; a hash
    -- given for a tool that names none is a runtime that put a file into the
    -- container this registry row never asked for.
    IF (v_tool.analyser IS NOT NULL) <> (p_analyser_sha256 IS NOT NULL) THEN
        RAISE EXCEPTION 'the registry says % % analyser and the runtime supplied %',
            p_tool,
            CASE WHEN v_tool.analyser IS NULL THEN 'runs no' ELSE 'runs an' END,
            CASE WHEN p_analyser_sha256 IS NULL THEN 'none' ELSE 'one' END
            USING ERRCODE = '22023';
    END IF;
    IF p_analyser_sha256 IS NOT NULL AND p_analyser_sha256 !~ '^[0-9a-f]{64}$' THEN
        RAISE EXCEPTION 'the analyser hash is not a sha256' USING ERRCODE = '22023';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM offline_tool_roles r
                    WHERE r.tool = p_tool AND r.role = v_run.role) THEN
        RAISE EXCEPTION 'the % role may not run %', v_run.role, p_tool
            USING ERRCODE = '42501';
    END IF;

    FOR v_name IN SELECT jsonb_object_keys(p_arguments) LOOP
        IF NOT EXISTS (SELECT 1 FROM offline_tool_arguments a
                        WHERE a.tool = p_tool AND a.name = v_name) THEN
            RAISE EXCEPTION '% takes no argument named %', p_tool, v_name
                USING ERRCODE = '22023';
        END IF;
    END LOOP;

    -- The analyser and the question, before anything a caller supplied. Which
    -- analysis this is comes from the registry key rather than from an
    -- argument, so it is not something a validated call can differ in.
    IF v_tool.analyser IS NOT NULL THEN
        v_argv := ARRAY[rk2_offline_analyser_path(v_tool.analyser), p_tool];
    END IF;

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
            SELECT * INTO v_ref FROM artifact_references r
             WHERE r.program_id = p AND r.label = v_value;
            IF NOT FOUND THEN
                -- The same answer for a label nobody holds and a label another
                -- Program holds. Two answers here would make the argument a way
                -- to ask whether some other Program has these bytes.
                RAISE EXCEPTION '% is not an artifact of this Program', v_value
                    USING ERRCODE = '42704';
            END IF;
            -- Criterion 1. The kind is a property of how this Program came to
            -- hold the bytes, so this refuses a stored response body and the
            -- output of an earlier run alike -- including this tool's own, on
            -- any tool whose outputs are not declared to be source.
            IF v_arg.artifact_kind IS NOT NULL AND v_ref.kind <> v_arg.artifact_kind THEN
                RAISE EXCEPTION '% is held as % and % takes % there',
                    v_value, v_ref.kind, v_arg.name, v_arg.artifact_kind
                    USING ERRCODE = '22023';
            END IF;
            v_inputs := v_inputs || jsonb_build_object(
                'argument', v_arg.name, 'label', v_value, 'sha256', v_ref.sha256,
                'kind', v_ref.kind, 'path', rk2_offline_input_path(v_value));
            v_argv := v_argv || rk2_offline_input_path(v_value);
        ELSE
            v_argv := v_argv || v_value;
        END IF;
    END LOOP;

    SELECT coalesce(jsonb_agg(jsonb_build_object('name', o.name, 'kind', o.reference_kind)
                              ORDER BY o.name), '[]'::jsonb)
      INTO v_outputs FROM offline_tool_outputs o WHERE o.tool = p_tool;

    INSERT INTO tool_runs
        (program_id, agent_run_id, task_id, tool, args, status, transport,
         offline_tool, tool_version, analyser_sha256)
    VALUES
        (p, v_run.id, v_run.task_id, 'mcp__rk2__run_tool',
         jsonb_build_object('tool_name', p_tool, 'arguments', p_arguments),
         'running', 'runtime', p_tool, p_version, p_analyser_sha256)
    RETURNING id, label INTO v_id, v_label;

    -- After the run row and before anything starts, which is the same moment
    -- the row itself is written for: a run that never comes back still says
    -- which bytes it was going to read.
    FOR v_input IN SELECT * FROM jsonb_array_elements(v_inputs) LOOP
        INSERT INTO tool_run_inputs
            (program_id, tool_run_id, argument, artifact_label, sha256, reference_kind)
        VALUES (p, v_id, v_input ->> 'argument', v_input ->> 'label',
                v_input ->> 'sha256', v_input ->> 'kind');
    END LOOP;

    RETURN jsonb_build_object(
        'tool_run_id', v_id,
        'tool_run', v_label,
        'tool', p_tool,
        'version', p_version,
        'executable', v_tool.executable,
        'analyser', v_tool.analyser,
        'analyser_path', CASE WHEN v_tool.analyser IS NOT NULL
                             THEN rk2_offline_analyser_path(v_tool.analyser) END,
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

REVOKE ALL ON FUNCTION open_offline_tool_run(uuid, text, text, jsonb, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION open_offline_tool_run(uuid, text, text, jsonb, text) TO rk2_runtime;

COMMENT ON FUNCTION open_offline_tool_run(uuid, text, text, jsonb, text) IS
    'Validate one offline tool call against the registry, record it and the '
    'bytes it will read before anything starts, and return the argv and the '
    'ceilings the runtime is to run it under. Every refusal is a raise: an '
    'unknown or disabled tool, a version the registry does not admit, an '
    'analyser the runtime and the registry disagree about, a role that may not '
    'run it, an argument it does not declare, a required one missing, a value '
    'outside its kind, an Artifact this Program does not hold, and an Artifact '
    'held as something the argument does not take.';


-- ---------------------------------------------------------------------------
-- 6. A conclusion cites the source it came from
-- ---------------------------------------------------------------------------
-- Criteria 4 and 5, and they are one function because they are one question
-- asked in two directions: an element that names a source Artifact must have
-- named one that holds up, and an element grounded in a run that read source
-- must name which source. Either way round, the answer is a row or a refusal.
--
-- The six reasons are six different mistakes and an agent told the wrong one
-- will send the same claim back:
--
--   `no_such_artifact`       the label is not one this Program holds. Missing
--                            and another Program's are the same answer here,
--                            for 030's reason -- two answers would make a
--                            citation a way to ask what somebody else has.
--   `artifact_not_source`    the label resolves and the bytes are held as a
--                            tool's output or as something the runtime stored.
--                            A conclusion about source grounded in a response
--                            body is a conclusion about the wrong thing.
--   `artifact_changed`       the element names a hash and the label resolves to
--                            different bytes. References are immutable, so this
--                            is the element being wrong rather than the store
--                            having moved -- which is exactly the failure mode
--                            a model summarising a large file falls into.
--   `artifact_not_read`      the citation holds and the cited Tool run never
--                            read those bytes. The one that catches a real
--                            Artifact and a real run wired to each other after
--                            the fact.
--   `no_source_citation`     the element is grounded in a run that read source
--                            and does not say which. Criterion 4 from the other
--                            side: a run may read more than one file, and an
--                            unnamed one is not a citation. What the run read is
--                            `tool_run_inputs`, not what its tool could have
--                            been given.
--   `path_not_in_output`     the element proposes a route and the run it cites
--                            never named it. The five above prove a conclusion
--                            could have come from those bytes; this is the one
--                            that asks whether the run said so, and it is the
--                            answer to the failure the other five leave open --
--                            a model that read a bundle, invented a route and
--                            cited the real analysis of the real file.

ALTER TABLE proposal_drops DROP CONSTRAINT proposal_drops_reason_check;
ALTER TABLE proposal_drops ADD CONSTRAINT proposal_drops_reason_check
    CHECK (reason IN ('no_such_receipt','receipt_other_program',
                      'receipt_proxy_internal','receipt_other_run',
                      'no_such_tool_run','no_such_label',
                      'label_other_program','no_provenance',
                      'no_subject','unknown_kind','incompatible_provenance',
                      'refused_by_invariant',
                      'malformed_field','no_parent','out_of_scope',
                      'invalid_direction','is_containment',
                      'no_such_artifact','artifact_not_source','artifact_changed',
                      'artifact_not_read','no_source_citation',
                      'path_not_in_output'));

CREATE FUNCTION rk2_source_citation(p_program uuid, p_element jsonb, p_tool_run uuid)
RETURNS TABLE(fault text, cited text)
LANGUAGE plpgsql STABLE AS $fn$
DECLARE
    v_label  text := nullif(btrim(p_element ->> 'source_artifact_label'), '');
    v_claim  text := lower(nullif(btrim(p_element ->> 'source_sha256'), ''));
    v_route  text := nullif(btrim(p_element ->> 'path_template'), '');
    v_ref    artifact_references%ROWTYPE;
BEGIN
    IF v_label IS NULL THEN
        -- Nothing cited, and nothing to check unless the evidence behind this
        -- element is a run that read source through an argument declared to
        -- take it. Both halves are load-bearing and neither is enough alone:
        -- the registry alone would demand a citation from a run that left an
        -- optional source argument empty, and the run's inputs alone would
        -- demand one from `jq` handed a file this Program happens to hold as
        -- source, which is a query over bytes and not an analysis of them.
        IF p_tool_run IS NOT NULL AND EXISTS (
                SELECT 1 FROM tool_runs tr
                  JOIN tool_run_inputs i ON i.tool_run_id = tr.id
                  JOIN offline_tool_arguments a
                    ON a.tool = tr.offline_tool AND a.name = i.argument
                 WHERE tr.id = p_tool_run
                   AND a.artifact_kind = 'source'
                   AND i.reference_kind = 'source') THEN
            RETURN QUERY SELECT 'no_source_citation', NULL::text;
        END IF;
        RETURN;
    END IF;

    SELECT * INTO v_ref FROM artifact_references r
     WHERE r.program_id = p_program AND r.label = v_label;
    IF NOT FOUND THEN
        RETURN QUERY SELECT 'no_such_artifact', v_label;
        RETURN;
    END IF;
    IF v_ref.kind <> 'source' THEN
        RETURN QUERY SELECT 'artifact_not_source', v_label;
        RETURN;
    END IF;
    IF v_claim IS NOT NULL AND v_claim <> v_ref.sha256 THEN
        RETURN QUERY SELECT 'artifact_changed', v_label;
        RETURN;
    END IF;
    IF p_tool_run IS NULL OR NOT EXISTS (
            SELECT 1 FROM tool_run_inputs i
             WHERE i.tool_run_id = p_tool_run AND i.sha256 = v_ref.sha256) THEN
        RETURN QUERY SELECT 'artifact_not_read', v_label;
        RETURN;
    END IF;

    -- The citation holds; what is left is whether the run said this. Only for
    -- an element that proposes a route, because a route is the one thing the
    -- analysers report and so the one thing there is an answer to check
    -- against. A run that named no path at all fails this too, and has to: an
    -- Artifact read by something that reported no routes grounds a conclusion
    -- about what is in it and not a conclusion that it calls one.
    --
    -- Both sides are cleaned, so `/api/v1/login/` and `/api/v1/login` are the
    -- one route this schema stores rather than two strings. A route that does
    -- not clean is not answered here: promotion has a word for a malformed
    -- field, and this one would say something false about the run.
    IF v_route IS NOT NULL THEN
        SELECT c.path INTO v_route FROM rk2_clean_path(v_route) c;
    END IF;
    IF v_route IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM tool_run_paths p
             WHERE p.tool_run_id = p_tool_run
               AND (SELECT c.path FROM rk2_clean_path(p.path) c) = v_route) THEN
        RETURN QUERY SELECT 'path_not_in_output', v_route;
        RETURN;
    END IF;
END $fn$;

REVOKE ALL ON FUNCTION rk2_source_citation(uuid, jsonb, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION rk2_source_citation(uuid, jsonb, uuid) TO rk2_runtime;

COMMENT ON FUNCTION rk2_source_citation(uuid, jsonb, uuid) IS
    'Whether one proposed element''s citation of a source Artifact holds, and '
    'the reason it does not. No row is the answer when it holds, so a caller '
    'joins it laterally and gets back only the elements it must refuse.';


-- ---------------------------------------------------------------------------
-- 7. Where the refusal is applied
-- ---------------------------------------------------------------------------
-- On the staging row, by a trigger, rather than inside `promote_proposal`. Two
-- reasons, and the second is the one that decided it:
--
--   Every walk in `promote_proposal` already begins by skipping an element
--   that has a drop row at its path -- that is how 020's provenance check
--   reaches promotion without promotion knowing about it -- so a drop written
--   when the proposal is staged is a promotion that refuses the element. There
--   is nothing to add to the three walks and no fourth copy of the refusal.
--
--   `hypotheses` is not one of those walks. Nothing promotes a hypothesis yet,
--   so a citation checked only at promotion would be a citation never checked
--   at all for the one element list criterion 4 names beside endpoints and
--   parameters. Here it is checked wherever the row came from.
--
-- A trigger rather than a step inside `proposal.stage`, for the reason 030
-- gives about its own link table: `rk2_runtime` holds INSERT on `proposals`,
-- and a guard only the convenience verb applied is a guard one statement gets
-- around.

-- The element paths are `promote_proposal`'s own spelling, and this is the one
-- place that spells them: only objects are numbered, because only objects are
-- elements, and a path that counted the strings would point promotion at the
-- wrong one. Two callers below walk a payload and both have to agree with
-- promotion about which element is which, so the walk is a function rather than
-- a shape copied twice.
-- Four lists: the three `promote_proposal` walks and `hypotheses`, which it
-- does not. A Relationship is here because it can carry a citation like any
-- other element, and a list left out would be a list where an ungrounded
-- conclusion promotes.
CREATE FUNCTION rk2_proposal_elements(p_payload jsonb)
RETURNS TABLE(list text, ordinal integer, path text, element jsonb)
LANGUAGE sql IMMUTABLE AS $fn$
    SELECT l.name, (x.n - 1)::integer, l.name || '[' || (x.n - 1) || ']', x.value
      FROM (VALUES ('new_entities'),('relationships'),
                   ('observations'),('hypotheses')) AS l(name)
      CROSS JOIN LATERAL (
            SELECT value, row_number() OVER () AS n
              FROM jsonb_array_elements(
                      CASE WHEN jsonb_typeof(p_payload -> l.name) = 'array'
                           THEN p_payload -> l.name ELSE '[]'::jsonb END)
             WHERE jsonb_typeof(value) = 'object') x
$fn$;

COMMENT ON FUNCTION rk2_proposal_elements(jsonb) IS
    'Every proposed Entity, Observation and Hypothesis in one staged payload, '
    'each with the `proposal_drops.element_path` that names it. The numbering '
    'is `promote_proposal`''s, which is what makes a drop written here an '
    'element promotion skips.';

-- One rule for where the next drop goes, because `proposal_drops` has two
-- writers -- this trigger at staging and the runtime afterwards -- and an
-- ordinal is part of the key. Both ask this rather than each spelling the
-- aggregate, so neither can start numbering somewhere the other does not.
CREATE FUNCTION rk2_next_drop_ordinal(p_proposal uuid) RETURNS integer
LANGUAGE sql STABLE AS $fn$
    SELECT coalesce(max(ordinal) + 1, 0)::integer
      FROM proposal_drops WHERE proposal_id = p_proposal
$fn$;

REVOKE ALL ON FUNCTION rk2_next_drop_ordinal(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION rk2_next_drop_ordinal(uuid) TO rk2_runtime;

COMMENT ON FUNCTION rk2_next_drop_ordinal(uuid) IS
    'Where the next `proposal_drops` row for this proposal is numbered. Read '
    'rather than assumed: the staging trigger writes drops before the runtime '
    'does, so a second writer that started at zero would collide with the '
    'first.';

CREATE FUNCTION proposal_grounds_its_source_citations() RETURNS trigger
LANGUAGE plpgsql AS $fn$
DECLARE
    v_next integer := rk2_next_drop_ordinal(NEW.id);
    v_row  record;
BEGIN
    FOR v_row IN
        SELECT e.path AS path, f.fault AS fault, f.cited AS cited
          FROM rk2_proposal_elements(NEW.payload) e
          CROSS JOIN LATERAL rk2_element_evidence(NEW.program_id, e.element) ev
          CROSS JOIN LATERAL rk2_source_citation(NEW.program_id, e.element, ev.tool_run_id) f
         ORDER BY e.list, e.ordinal
    LOOP
        INSERT INTO proposal_drops
            (proposal_id, program_id, ordinal, element_path, reason, cited)
        VALUES (NEW.id, NEW.program_id, v_next, v_row.path, v_row.fault, v_row.cited);
        v_next := v_next + 1;
    END LOOP;
    RETURN NULL;
END $fn$;

CREATE TRIGGER proposals_ground_source_citations
    AFTER INSERT ON proposals
    FOR EACH ROW EXECUTE FUNCTION proposal_grounds_its_source_citations();

COMMENT ON FUNCTION proposal_grounds_its_source_citations() IS
    'Refuse, at staging, every proposed Entity, Relationship, Observation and '
    'Hypothesis whose citation of a source Artifact does not hold -- and every '
    'one grounded in a run that read source and does not say which. The '
    'refusal is a proposal_drops row, which is what promotion skips.';


-- ---------------------------------------------------------------------------
-- 8. The standing check
-- ---------------------------------------------------------------------------
-- What can be true later that no trigger could have refused earlier. Four of
-- the five are about a run: an analyser that ran without saying which bytes it
-- was, a source run that recorded nothing it read, an input whose bytes the
-- Program no longer holds, and a source analysis tool that has acquired a
-- network. The fifth re-asks the promotion question of everything already
-- promoted, which is the only way a citation that held when it was checked and
-- stopped holding afterwards becomes visible.

CREATE FUNCTION check_source_conclusions()
RETURNS TABLE(problem text, detail text)
LANGUAGE sql STABLE AS $fn$
    SELECT 'analyser_run_without_its_hash', tr.label
      FROM tool_runs tr
      JOIN offline_tools t ON t.tool = tr.offline_tool
     WHERE t.analyser IS NOT NULL AND tr.analyser_sha256 IS NULL
UNION ALL
    -- A closed run of a tool that requires source and was given none. The verb
    -- refuses a missing required argument, so this is a run that got there
    -- another way, and its output is evidence about nothing.
    SELECT 'source_run_read_nothing', tr.label
      FROM tool_runs tr
     WHERE tr.offline_tool IS NOT NULL
       AND tr.status <> 'running'
       AND EXISTS (SELECT 1 FROM offline_tool_arguments a
                    WHERE a.tool = tr.offline_tool AND a.artifact_kind = 'source'
                      AND a.required)
       AND NOT EXISTS (SELECT 1 FROM tool_run_inputs i WHERE i.tool_run_id = tr.id)
UNION ALL
    SELECT 'input_artifact_not_held', i.tool_run_id::text || ' ' || i.artifact_label
      FROM tool_run_inputs i
     WHERE NOT EXISTS (SELECT 1 FROM artifact_references r
                        WHERE r.program_id = i.program_id AND r.sha256 = i.sha256
                          AND r.kind = i.reference_kind)
UNION ALL
    -- Criterion 2, as a property of the registry rather than of a run. A tool
    -- that reads source and can reach a network is a way to send the source
    -- somewhere, and it would be true of every run made after the row changed.
    SELECT 'source_tool_has_network', t.tool || ' has the ' || t.network || ' network'
      FROM offline_tools t
     WHERE t.network <> 'none'
       AND EXISTS (SELECT 1 FROM offline_tool_arguments a
                    WHERE a.tool = t.tool AND a.artifact_kind = 'source')
UNION ALL
    SELECT 'promoted_element_cites_ungrounded_source',
           pp.label || ' ' || e.path || ': ' || f.fault
      FROM proposals pp
      CROSS JOIN LATERAL rk2_proposal_elements(pp.payload) e
      CROSS JOIN LATERAL rk2_element_evidence(pp.program_id, e.element) ev
      CROSS JOIN LATERAL rk2_source_citation(pp.program_id, e.element, ev.tool_run_id) f
     WHERE pp.status = 'promoted'
       AND NOT EXISTS (SELECT 1 FROM proposal_drops d
                        WHERE d.proposal_id = pp.id AND d.element_path = e.path)
$fn$;

COMMENT ON FUNCTION check_source_conclusions() IS
    'What a source analysis can get wrong after the fact: an analyser run that '
    'does not say which analyser, a source run that recorded nothing it read, '
    'an input whose bytes are gone, a source tool that has acquired a network, '
    'and a promoted conclusion whose citation no longer holds.';

INSERT INTO standing_checks (name, query, owner_ticket, note) VALUES
    ('source_conclusions', 'SELECT * FROM check_source_conclusions()', '32',
     'every source conclusion names the bytes it came from and the run that read them');


-- ---------------------------------------------------------------------------
-- 9. The invariants this file must not have broken
-- ---------------------------------------------------------------------------
SELECT enforce_always_triggers();
SELECT apply_state_rls();
SELECT apply_state_grants();
SELECT enforce_fk_fire_order();

DO $$
DECLARE n integer; d text;
BEGIN
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_source_conclusions();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-32 refuses to finish: % source conclusion violation(s): %', n, d;
    END IF;

    -- 030's check runs again because this file changed the registry it reads:
    -- three tools, four arguments and one declared output, each of which it has
    -- an opinion about.
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_offline_tools();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-32 breaks the offline tool registry (% problems): %', n, d;
    END IF;

    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_program_isolation();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-32 breaks program isolation (% problems): %', n, d;
    END IF;

    SELECT count(*), string_agg(problem || ': ' || object || ' ' || detail, '; ')
      INTO n, d FROM check_rls_coverage();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-32 leaves a scoped table unguarded (% problems): %', n, d;
    END IF;

    SELECT count(*), string_agg(problem || ': ' || object || ' ' || detail, '; ')
      INTO n, d FROM check_state_grants();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-32 changes the agent read surface (% problems): %', n, d;
    END IF;

    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_event_coverage();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-32 leaves a table unaccounted for in the log (% problems): %', n, d;
    END IF;

    SELECT count(*), string_agg(problem || ': ' || object || ' ' || detail, '; ')
      INTO n, d FROM check_purge_reachability();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-32 makes a Program unpurgeable (% problems): %', n, d;
    END IF;
END $$;
