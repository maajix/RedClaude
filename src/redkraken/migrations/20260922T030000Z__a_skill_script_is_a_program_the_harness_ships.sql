-- Ticket 87: a Skill script is a program the harness ships.
--
-- `mcp__rk2__run_skill_script` has had a contract in `roster` since ticket 18
-- and no handler in any launch, so the only thing that has ever run a Skill
-- script is `skill.check` in CI. Story 169 asks for deterministic Skill logic
-- placed in scripts so that prompts are not used for work code can perform;
-- what shipped is the scripts and their checks, and what was missing is the
-- half that runs during a hunt.
--
-- The shape this file takes is not a second mechanism beside the offline tool
-- registry. It is the observation that a Skill script is already the thing that
-- registry calls an *analyser*: `jsscan.py` is a program this harness ships,
-- named by `offline_tools.analyser`, read off the runtime's own disk, hashed,
-- mounted read-only inside the container and run there. A Skill script is the
-- same object in a different directory. So the registry gains where the file
-- lives, and everything else it already decides -- which roles may run it, the
-- Halt, the ceilings, the version, the analyser digest a run records, and that
-- an Artifact argument is a *label* resolved against `artifact_references` for
-- this Program -- is thereby decided for a Skill script too, in the same words
-- and by the same code.
--
-- Two columns, because there are exactly two differences.
--
-- The first is the directory. `analyser` is a bare filename read as a sibling
-- of `tool.py`; a Skill script is `skills/<skill>/scripts/<file>.py`. What
-- changes is the *host* path. `rk2_offline_analyser_path` is untouched, because
-- the container path was never the part that differed.
--
-- The second is where the input arrives. Every row here today delivers its
-- input Artifacts on the argv, as paths under `/input`. A Skill script takes no
-- arguments at all: it reads one JSON object on standard input, and
-- `skill.Case.payload()` is the only executable statement of that object's
-- shape -- which is why the shipped scripts' checks run against it, and why a
-- script that read something else has been failing CI since it was written.
-- `input_delivery` is that difference as a column, so a row says how its tool
-- is fed rather than the runtime knowing by tool name.
--
-- What this file does not do is give the model a second way to name a program.
-- `run_skill_script` names a Skill and a script; `rk2_skill_script` turns that
-- pair into the one registry row that holds it, or refuses. There is no path
-- from a Skill name to a program the registry has not already admitted.

-- ---------------------------------------------------------------------------
-- 1. Where the program lives
-- ---------------------------------------------------------------------------

ALTER TABLE offline_tools ADD COLUMN skill text REFERENCES skills(name);

ALTER TABLE offline_tools ADD CONSTRAINT offline_tools_skill_ck
    CHECK (skill IS NULL OR skill ~ '^[a-z0-9][a-z0-9-]{0,63}$');

-- A Skill that names no program is a row with nothing to run. The analyser is
-- what makes this column mean a directory rather than a decoration: without
-- one there is no harness-shipped file for the Skill to be the directory of.
ALTER TABLE offline_tools ADD CONSTRAINT offline_tools_skill_needs_analyser_ck
    CHECK (skill IS NULL OR analyser IS NOT NULL);

COMMENT ON COLUMN offline_tools.skill IS
    'The Skill whose `scripts/` directory holds this row''s analyser, or NULL '
    'for an analyser that sits beside `tool.py`. A foreign key to `skills` and '
    'not a string, so a Skill that is renamed or retired takes its programs '
    'with it rather than leaving a row naming a directory nothing ships.';

-- ---------------------------------------------------------------------------
-- 2. How the program is fed
-- ---------------------------------------------------------------------------

ALTER TABLE offline_tools ADD COLUMN input_delivery text NOT NULL DEFAULT 'argv'
    CHECK (input_delivery IN ('argv', 'stdin'));

-- Only a program this harness ships may read the envelope, because the
-- envelope is this harness's own document. A registry row for a binary the
-- image provides has no claim on what that binary reads from a pipe.
ALTER TABLE offline_tools ADD CONSTRAINT offline_tools_stdin_needs_analyser_ck
    CHECK (input_delivery = 'argv' OR analyser IS NOT NULL);

COMMENT ON COLUMN offline_tools.input_delivery IS
    'Where this tool''s input Artifacts appear: `argv`, as read-only paths '
    'under /input, which is what every image tool and every analyser does, or '
    '`stdin`, as the one JSON object `skill.Case.payload()` defines. A `stdin` '
    'tool receives no argv beyond its own path -- the runtime writes the '
    'envelope and closes the pipe.';

-- ---------------------------------------------------------------------------
-- 3. What pins a program the harness ships
-- ---------------------------------------------------------------------------
-- An image tool is pinned by asking it: `version_argv` runs, and
-- `version_pattern` says which answers this registry admits. That question is
-- worth asking of a binary somebody else built and shipped in an image this
-- migration has never seen.
--
-- It is not worth asking of a Skill script. The runtime reads that file off its
-- own disk and hashes it before anything starts -- that is what
-- `tool_runs.analyser_sha256` already records -- so the digest *is* the
-- version, and a `--version` flag would be a second answer to a question the
-- harness has already answered exactly. It would also be an argument on a
-- program whose whole contract is that it takes none.
--
-- So `version_argv` becomes nullable, for exactly the rows that carry a Skill,
-- and those rows admit a sha256 as their version.

ALTER TABLE offline_tools DROP CONSTRAINT offline_tools_version_argv_check;
ALTER TABLE offline_tools ALTER COLUMN version_argv DROP NOT NULL;

ALTER TABLE offline_tools ADD CONSTRAINT offline_tools_version_argv_check
    CHECK (version_argv IS NULL OR cardinality(version_argv) BETWEEN 1 AND 4);

-- Nullable for a Skill script and for nothing else. A row that named no Skill
-- and asked no version question would be a program nothing pins at all.
ALTER TABLE offline_tools ADD CONSTRAINT offline_tools_version_argv_ck
    CHECK (version_argv IS NOT NULL OR skill IS NOT NULL);

COMMENT ON COLUMN offline_tools.version_argv IS
    'How to ask the tool what it is, or NULL for a Skill script, whose version '
    'is the digest of the bytes the runtime read. A pattern is still required '
    'either way, so there is no row whose recorded version nothing constrains.';

-- ---------------------------------------------------------------------------
-- 4. The pair a Skill script is named by
-- ---------------------------------------------------------------------------

CREATE FUNCTION rk2_skill_script(p_skill text, p_script text) RETURNS text
LANGUAGE plpgsql STABLE AS $fn$
DECLARE v_tool text;
BEGIN
    SELECT tool INTO v_tool FROM offline_tools
     WHERE skill = p_skill AND analyser = p_script AND enabled;
    IF NOT FOUND THEN
        -- One answer for a Skill that has no such script, a script that is not
        -- registered and a row that is disabled. Telling them apart would make
        -- this verb a way to ask which files the corpus holds.
        RAISE EXCEPTION 'no registered script % in skill %', p_script, p_skill
            USING ERRCODE = '42704';
    END IF;
    RETURN v_tool;
END $fn$;

COMMENT ON FUNCTION rk2_skill_script(text, text) IS
    'The registry row one Skill script is, by the pair the model names it with. '
    'The tool name is the registry''s and is never on the model''s surface: a '
    'Skill and a filename are what a child holding a Skill can see, and this is '
    'the one step from that pair to a program this registry has admitted.';

REVOKE ALL ON FUNCTION rk2_skill_script(text, text) FROM PUBLIC, rk2_state, rk2_proxy;
GRANT EXECUTE ON FUNCTION rk2_skill_script(text, text) TO rk2_runtime, rk2_human;

-- Closed to PUBLIC and held by the runtime, so ticket 66's registry has to say
-- so out loud. Not `rk2_state`, for the reason the whole boundary exists: the
-- connection a model's own code can reach is the one that must not be able to
-- learn which programs exist, let alone start one.
INSERT INTO runtime_verb_surface (verb, added_by, note) VALUES
    ('rk2_skill_script(text, text)', '87',
     'the one step from the Skill and script a child names to the registry row '
     'that holds it; the runtime asks it before it opens a Tool run');

-- ---------------------------------------------------------------------------
-- 5. Opening a run, for either kind of program
-- ---------------------------------------------------------------------------
-- Dropped and rewritten rather than altered, which is what 032 did to 030's
-- copy and for the same reason: the body changes in three places and a reader
-- comparing two versions of it should be reading one file, not a patch.
--
-- Everything 030 and 032 refused is refused here in the same words. What is
-- added is the two columns, and the one thing that follows from them: a
-- `stdin` tool's argv is its own path and nothing else.

DROP FUNCTION open_offline_tool_run(uuid, text, text, jsonb, text);

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
    v_verb    text;
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

    -- A Skill script is pinned by its own bytes, so the version and the hash
    -- are one fact and are held to being one. A runtime that reported some
    -- other digest as the version would be recording a program that is not the
    -- one it read.
    IF v_tool.skill IS NOT NULL AND p_version IS DISTINCT FROM p_analyser_sha256 THEN
        RAISE EXCEPTION 'a Skill script''s version is the digest of the bytes that ran'
            USING ERRCODE = '22023';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM offline_tool_roles r
                    WHERE r.tool = p_tool AND r.role = v_run.role) THEN
        RAISE EXCEPTION 'the % role may not run %', v_run.role, p_tool
            USING ERRCODE = '42501';
    END IF;

    -- The Skill as well as the role, for a program a Skill owns. A role that
    -- holds the tool and not the Skill would be reaching a script through the
    -- registry that the corpus never gave it, which is the widening
    -- `roster._check_skills` refuses on the instruction side.
    IF v_tool.skill IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM role_skills s
             WHERE s.role = v_run.role AND s.skill_name = v_tool.skill) THEN
        RAISE EXCEPTION 'the % role does not hold the % skill', v_run.role, v_tool.skill
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
    --
    -- A `stdin` tool gets neither the subcommand nor, below, any path: one file
    -- is one tool there, and its whole input is the envelope. An argv it did
    -- not expect is the one way a program that reads no arguments could be made
    -- to read one.
    IF v_tool.analyser IS NOT NULL THEN
        v_argv := ARRAY[rk2_offline_analyser_path(v_tool.analyser)];
        IF v_tool.input_delivery = 'argv' THEN
            v_argv := v_argv || p_tool;
        END IF;
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

        IF v_arg.flag IS NOT NULL AND v_tool.input_delivery = 'argv' THEN
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
            IF v_arg.artifact_kind IS NOT NULL AND v_ref.kind <> v_arg.artifact_kind THEN
                RAISE EXCEPTION '% is held as % and % takes % there',
                    v_value, v_ref.kind, v_arg.name, v_arg.artifact_kind
                    USING ERRCODE = '22023';
            END IF;
            v_inputs := v_inputs || jsonb_build_object(
                'argument', v_arg.name, 'label', v_value, 'sha256', v_ref.sha256,
                'kind', v_ref.kind,
                -- The path a `stdin` tool is not given, stated anyway: the run
                -- row records which bytes were read, and where they would have
                -- appeared is a property of the input rather than of the way
                -- this one row happens to be fed.
                'path', rk2_offline_input_path(v_value));
            IF v_tool.input_delivery = 'argv' THEN
                v_argv := v_argv || rk2_offline_input_path(v_value);
            END IF;
        ELSIF v_tool.input_delivery = 'argv' THEN
            v_argv := v_argv || v_value;
        ELSE
            -- Unreachable while `check_skill_scripts` holds, and a raise rather
            -- than a silent drop because the alternative is a run that recorded
            -- an argument it never passed.
            RAISE EXCEPTION '% reads an envelope and cannot be given the literal %',
                p_tool, v_arg.name USING ERRCODE = '22023';
        END IF;
    END LOOP;

    SELECT coalesce(jsonb_agg(jsonb_build_object('name', o.name, 'kind', o.reference_kind)
                              ORDER BY o.name), '[]'::jsonb)
      INTO v_outputs FROM offline_tool_outputs o WHERE o.tool = p_tool;

    -- Which model-facing verb this row is the record of. A Skill script and a
    -- registered binary are the same mechanism and are not the same act: an
    -- operator reading `tool_runs` should see which surface asked, and the two
    -- surfaces are the two members of `exec.tool_run`.
    v_verb := CASE WHEN v_tool.skill IS NULL
                   THEN 'mcp__rk2__run_tool' ELSE 'mcp__rk2__run_skill_script' END;

    INSERT INTO tool_runs
        (program_id, agent_run_id, task_id, tool, args, status, transport,
         offline_tool, tool_version, analyser_sha256)
    VALUES
        (p, v_run.id, v_run.task_id, v_verb,
         jsonb_strip_nulls(jsonb_build_object(
             'tool_name', p_tool, 'skill', v_tool.skill,
             'script', CASE WHEN v_tool.skill IS NOT NULL THEN v_tool.analyser END,
             'arguments', p_arguments)),
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
        'skill', v_tool.skill,
        'script', CASE WHEN v_tool.skill IS NOT NULL THEN v_tool.analyser END,
        'input_delivery', v_tool.input_delivery,
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
    'unknown or disabled tool, a version the registry does not admit, a role '
    'that may not run it or does not hold the Skill that owns it, an argument '
    'it does not declare, a required one missing, a value outside its kind, an '
    'Artifact this Program does not hold, and one held as the wrong kind.';

-- ---------------------------------------------------------------------------
-- 6. The two scripts the corpus already ships
-- ---------------------------------------------------------------------------
-- Both are `bb:scripts` entries with declared cases that have been running in
-- CI since they were written, so what is new is not the program -- it is that a
-- run may now start one.
--
-- The ceilings are an analyser's, halved where the work is smaller: neither
-- reads a bundle the way `jsscan.py` does, and both are one pass over text the
-- envelope already holds.

INSERT INTO offline_tools
    (tool, executable, version_argv, version_pattern, network, timeout_seconds,
     memory_mb, cpu_quota, pids_limit, max_output_bytes, analyser, skill,
     input_delivery, description) VALUES
    ('compare_responses', '/usr/local/bin/python3', NULL, '^[0-9a-f]{64}$', 'none',
     60, 256, 1.0, 32, 2097152, 'compare.py', 'compare-responses', 'stdin',
     'compare two stored Artifacts line by line and report what differs, as the '
     'deterministic half of the compare-responses Skill'),
    ('extract_paths', '/usr/local/bin/python3', NULL, '^[0-9a-f]{64}$', 'none',
     60, 256, 1.0, 32, 2097152, 'extract_paths.py', 'analyse-source', 'stdin',
     'pull the path-shaped string literals out of one stored source Artifact, '
     'with the count of literals scanned, as the deterministic half of the '
     'analyse-source Skill');

-- Positional and required, because the envelope is an array and the scripts
-- read it positionally. `first` and `second` are not interchangeable to a
-- reader of the answer -- `only_in_first` is a different claim from
-- `only_in_second` -- so the order is part of the call and not a convenience.
INSERT INTO offline_tool_arguments
    (tool, name, position, flag, value_kind, required, pattern, choices,
     artifact_kind, description) VALUES
    ('compare_responses', 'first',  0, NULL, 'artifact', true, NULL, NULL, NULL,
     'the Artifact the answer calls the first one'),
    ('compare_responses', 'second', 1, NULL, 'artifact', true, NULL, NULL, NULL,
     'the Artifact the answer calls the second one'),
    -- Source, like the other two tools that read a bundle. A response body is
    -- not what this script is for, and the kind is where that is said once.
    ('extract_paths', 'source', 0, NULL, 'artifact', true, NULL, NULL, 'source',
     'the source Artifact to pull path-shaped literals out of');

-- The role that holds the Skill, and only that role. `role_skills` already says
-- which is which; a second answer here that disagreed with it would be a role
-- reaching a script through the registry the corpus never gave it, which is
-- why the verb above asks both.
INSERT INTO offline_tool_roles (tool, role) VALUES
    ('compare_responses', 'web_hunter'),
    ('extract_paths',     'js_analyst');

-- ---------------------------------------------------------------------------
-- 7. What has to keep being true
-- ---------------------------------------------------------------------------

CREATE FUNCTION check_skill_scripts()
RETURNS TABLE (problem text, detail text)
LANGUAGE sql STABLE AS $fn$
    -- A row that says a Skill owns the program and a role that may run it
    -- without holding that Skill. The verb refuses the run; this finds the
    -- registry state that would make every such run a refusal nobody expected.
    SELECT 'script_role_does_not_hold_its_skill'::text,
           r.role || ' may run ' || r.tool || ' and does not hold ' || t.skill
      FROM offline_tool_roles r
      JOIN offline_tools t ON t.tool = r.tool
     WHERE t.skill IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM role_skills s
                        WHERE s.role = r.role AND s.skill_name = t.skill)
UNION ALL
    -- A `stdin` tool declaring an argument that is not an Artifact. Its whole
    -- input is the envelope, so such an argument is a value the caller may
    -- supply, the row records, and the program never sees.
    SELECT 'envelope_tool_takes_a_literal', a.tool || '.' || a.name
      FROM offline_tool_arguments a
      JOIN offline_tools t ON t.tool = a.tool
      JOIN offline_argument_kinds k ON k.value_kind = a.value_kind
     WHERE t.input_delivery = 'stdin' AND NOT k.materialised
UNION ALL
    -- A `stdin` tool declaring an output file. The envelope is answered on
    -- stdout; a declared output would be a second place the answer could be,
    -- and the Skill's checks only ever read the one.
    SELECT 'envelope_tool_declares_an_output', o.tool || ' writes ' || o.name
      FROM offline_tool_outputs o
      JOIN offline_tools t ON t.tool = o.tool
     WHERE t.input_delivery = 'stdin'
UNION ALL
    -- The registry row exists and the corpus no longer ships the file behind
    -- it. `skill_dependencies` is what the corpus declared it ships, so a row
    -- naming a script that is not in it is a program the next install will not
    -- have.
    SELECT 'registered_script_is_not_shipped', t.tool || ' names ' || t.skill || '/' || t.analyser
      FROM offline_tools t
     WHERE t.skill IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM skill_dependencies d
                        WHERE d.skill_name = t.skill AND d.kind = 'script'
                          AND d.path = 'scripts/' || t.analyser)
UNION ALL
    -- A recorded Skill script run whose version is not the digest the same row
    -- says ran. The verb holds the two together; this finds a row that got
    -- there another way, and whose provenance names two different programs.
    SELECT 'script_run_version_is_not_its_digest', tr.label
      FROM tool_runs tr
      JOIN offline_tools t ON t.tool = tr.offline_tool
     WHERE t.skill IS NOT NULL AND tr.tool_version IS DISTINCT FROM tr.analyser_sha256
$fn$;

COMMENT ON FUNCTION check_skill_scripts() IS
    'Ticket 87 as five readings of the registry and the runs made against it: a '
    'role that may run a script without holding its Skill, an envelope tool '
    'declaring an argument the envelope cannot carry, an envelope tool '
    'declaring an output the envelope does not answer on, a registry row whose '
    'file the corpus does not ship, and a recorded run whose version and digest '
    'name two different programs.';

INSERT INTO standing_checks (name, query, owner_ticket, note) VALUES
    ('skill_scripts', 'SELECT * FROM check_skill_scripts()', '87',
     'a Skill script is a registered program and the registry says so consistently');

-- ---------------------------------------------------------------------------
-- 8. The Skill text that named the argument this file removed
-- ---------------------------------------------------------------------------
-- `compare-responses/SKILL.md` told a hunter to call `run_skill_script` with
-- `input_artifact_hashes`, which is the argument section 4 took off the
-- contract. Left standing, the one Skill this file exists to serve would be
-- instructing the model to make a call the gate refuses -- so the text names
-- `arguments` and the registry follows it here.
--
-- It has to follow it here rather than anywhere else: `skills.source_sha256`
-- and `skill_dependencies.sha256` are a copy of what is on disk, and a copy is
-- only worth having because something compares it. The version moves with them
-- because a Skill's version is the digest over its dependencies' digests, which
-- is what makes "the text changed" a fact the database can state.

UPDATE skills
   SET source_sha256 = '5f0b023bd866c91f580d0db1ca6107abc0f5e41a9d1502d65020ef1ad47f1429',
       version       = '310522bf12380535f5741d8feaa76c75e2dfe66a68936d0fbced8290b09b5fa2'
 WHERE name = 'compare-responses';

UPDATE skill_dependencies
   SET sha256 = '5f0b023bd866c91f580d0db1ca6107abc0f5e41a9d1502d65020ef1ad47f1429'
 WHERE skill_name = 'compare-responses'
   AND kind = 'instruction'
   AND path = 'SKILL.md';

-- ---------------------------------------------------------------------------
-- 9. Bring the corpus to true
-- ---------------------------------------------------------------------------
-- This file's own three, and not `assert_standing_checks()`. Two of the
-- registered checks read triggers that `enforce_always_triggers` has not run
-- over yet -- the finalizers run after the last file, not inside it -- so a
-- migration at the end of the corpus that asserted the whole registry would be
-- asserting it one step too early and would fail on work that was never its own.

DO $$
DECLARE n integer; d text;
BEGIN
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_skill_scripts();
    IF n > 0 THEN
        RAISE EXCEPTION 'ticket 87 refuses to finish: % skill script violation(s): %', n, d;
    END IF;

    -- 030's control still has to pass: this file rewrote its verb and widened
    -- its table, and a repair that broke the thing it repaired would show up
    -- here first.
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_offline_tools();
    IF n > 0 THEN
        RAISE EXCEPTION 'ticket 87 breaks ph2-30 (% problems): %', n, d;
    END IF;

    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_source_conclusions();
    IF n > 0 THEN
        RAISE EXCEPTION 'ticket 87 breaks ph2-32 (% problems): %', n, d;
    END IF;
END $$;
