-- ---------------------------------------------------------------------------
-- 20261128T000000Z__a_registry_row_answers_only_for_the_runs_it_describes.sql
--
-- The other half of 20261127T000000Z, which the gate found for us.
--
-- Changing jq's registry row made two standing arms report forty-two runs at
-- once:
--
--     standing:offline_tools
--     42 problem(s): (recorded_version_now_refused,"TR129 ran jq-1.7"); ...
--     standing:source_conclusions
--     42 problem(s): (analyser_run_without_its_hash,TR129); ...
--
-- Both arms are right about what they see and wrong about what it means. The
-- first holds each run's recorded version against the row's pattern; those
-- runs recorded `jq-1.7`, which is exactly what the image said at the time.
-- The second asks an analyser run for the hash of its analyser; those runs had
-- no analyser to hash, because the row did not name one yet.
--
-- Neither was written for a row that changes. Every registry row until now was
-- written once and left alone, so "every run of this tool" and "every run this
-- row describes" were the same set. They are not the same set any more, and
-- the difference is a moment.
--
-- So the row carries it. `contract_since` defaults to `-infinity`, which is
-- every other tool and is the behaviour both arms had before this file: a row
-- that has never changed describes every run of its tool. jq's is the moment
-- 20261127T000000Z changed it.
--
-- The alternative was deleting forty-two failed runs to make a check quiet.
-- That is the wrong way round -- those runs are the measurement in ticket 198,
-- and a harness that erases its own record to pass its own gate has stopped
-- being one.
--
-- The two functions are replaced whole, with the arm's original comment kept
-- above the new one, so the reason it was written and the reason it was scoped
-- are read together.
-- ---------------------------------------------------------------------------

ALTER TABLE offline_tools
    ADD COLUMN contract_since timestamptz NOT NULL DEFAULT '-infinity';

COMMENT ON COLUMN offline_tools.contract_since IS
    'When this row started describing its runs. A run started before it was '
    'made under a different row -- a different executable, analyser or version '
    'pattern -- so the standing arms that hold a run against this row skip it. '
    '`-infinity` means the row has never changed in a way a run can tell.';

-- jq, as of 20261127T000000Z. Taken from the ledger rather than from `now()`:
-- the moment that matters is when the row changed, and the ledger is what
-- recorded it.
UPDATE offline_tools
   SET contract_since = (SELECT applied_at FROM rk2_meta.schema_migrations
                          WHERE id LIKE '20261127T000000Z%')
 WHERE tool = 'jq';


CREATE OR REPLACE FUNCTION public.check_offline_tools()
 RETURNS TABLE(problem text, detail text)
 LANGUAGE sql
 STABLE
AS $function$
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
    -- Scoped to the runs the current row describes, since 20261127T000000Z.
    -- A run made before `contract_since` was made under a row that is not this
    -- one, and reporting it forever would make every tightening a permanent
    -- refusal rather than a notice about the runs it changed.
    SELECT 'recorded_version_now_refused', tr.label || ' ran ' || tr.tool_version
      FROM tool_runs tr
      JOIN offline_tools t ON t.tool = tr.offline_tool
     WHERE tr.tool_version !~ t.version_pattern
       AND tr.started_at >= t.contract_since
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
$function$;


CREATE OR REPLACE FUNCTION public.check_source_conclusions()
 RETURNS TABLE(problem text, detail text)
 LANGUAGE sql
 STABLE
AS $function$
    -- Scoped to the runs the current row describes, since 20261127T000000Z.
    -- A tool that acquires an analyser has runs behind it that were made
    -- without one, and they did not fail to record a hash -- there was none to
    -- record. `contract_since` is the moment the row started describing them.
    SELECT 'analyser_run_without_its_hash', tr.label
      FROM tool_runs tr
      JOIN offline_tools t ON t.tool = tr.offline_tool
     WHERE t.analyser IS NOT NULL AND tr.analyser_sha256 IS NULL
       AND tr.started_at >= t.contract_since
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
$function$;

DO $$
DECLARE n integer; v text;
BEGIN
    -- Both arms, quiet, which is the whole reason the column exists.
    SELECT count(*), string_agg(problem || ': ' || detail, '; ') INTO n, v
      FROM check_offline_tools() WHERE problem = 'recorded_version_now_refused';
    IF n > 0 THEN
        RAISE EXCEPTION 'ticket 198: % run(s) still held against a row they predate: %', n, v;
    END IF;

    SELECT count(*), string_agg(problem || ': ' || detail, '; ') INTO n, v
      FROM check_source_conclusions() WHERE problem = 'analyser_run_without_its_hash';
    IF n > 0 THEN
        RAISE EXCEPTION 'ticket 198: % run(s) still asked for a hash they never had: %', n, v;
    END IF;

    -- And nothing else moved. A scoping that silenced an arm it was not about
    -- would be the same mistake this file exists to avoid, one layer down.
    SELECT count(*), string_agg(problem || ': ' || detail, '; ') INTO n, v
      FROM (SELECT * FROM check_offline_tools()
            UNION ALL SELECT * FROM check_source_conclusions()) q;
    IF n > 0 THEN
        RAISE EXCEPTION 'the offline registry is not whole (%): %', n, v;
    END IF;

    -- The default is the old behaviour, said out loud: every other tool
    -- answers for every run of itself, exactly as it did before this file.
    SELECT count(*) INTO n FROM offline_tools
     WHERE tool <> 'jq' AND contract_since <> '-infinity';
    IF n <> 0 THEN
        RAISE EXCEPTION 'ticket 198: % row(s) narrowed that this file did not change', n;
    END IF;
END $$;
