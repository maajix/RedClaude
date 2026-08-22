-- ---------------------------------------------------------------------------
-- 20261003T000000Z__a_key_collision_is_the_whole_of_the_trace.sql
--                                                                  (ticket 127)
--
-- THE PRODUCER THAT DOES NOT EXIST. `0010_embeddings.sql` declared two side
-- tables keyed by embedding model -- `hypothesis_embeddings` (`0010:7-13`) and
-- `observation_embeddings` (`0010:15-21`), each a `vector(1536)` under an HNSW
-- cosine index (`0010:23-26`) -- and nothing in this harness has ever written a
-- row into either. Measured over the whole tree rather than inferred:
-- `grep -rn "embedding" src/redkraken/*.py` returns nothing, and there is no
-- `INSERT` against either table anywhere in the corpus. The tables are not
-- half-wired; they have no producer at all, and the capability that would
-- produce one -- a model call -- happens in this harness only inside the child
-- process, where `claude_agent_sdk` is imported by `_launch.py` and
-- `_startup.py` and by nothing else. The runtime that holds the database
-- connection makes no model calls, and an embedding producer would put one on
-- the promotion path for every Hypothesis and every Observation.
--
-- WHAT THAT COST THE DEDUP SIDE. `hypothesis_near_matches` (`0012:69-79`)
-- declares three actions after `0018:429-436`: `suppressed`, `penalised` and
-- `key_collision`. Its only writer is `rk2_promote_hypotheses`
-- (`20260814T070000Z__a_proposal_becomes_a_canonical_hypothesis.sql:796-800`),
-- which names five columns -- `program_id, candidate_statement,
-- matched_hypothesis_id, action, agent_run_id` -- and writes `key_collision`.
-- So `similarity` and `embedding_model`, which
-- `hypothesis_near_matches_stage2_cols` requires to be NOT NULL for the other
-- two actions, are never written, and the two similarity-based actions cannot
-- be reached: the CHECK is satisfiable only on its `key_collision` arm.
--
-- THE SENTENCE THAT DECIDES IT is the design's own, written when the near-match
-- vocabulary was closed (`0018:414-418`): "What can be fixed is the *silence*:
-- ticket 08 built `hypothesis_near_matches` so a suppressed hypothesis leaves a
-- trace, and a hard key collision is the same event arriving through the index
-- instead of through pgvector." The trace is what the design said it wanted and
-- the trace ships. The embedding half would have widened *recall* -- catching
-- near duplicates the dedup key spells differently -- and the same paragraph
-- says why that is a losing chase: "The residual collision rate is 11/165 and
-- cannot be driven to zero by adding leaves -- three genuinely different SAML
-- defects share `authentication.federation_trust`." A vocabulary too coarse to
-- separate three real defects is not made finer by a cosine distance over their
-- prose; a semantic matcher would suppress or penalise the second SAML finding
-- on the strength of its resembling the first.
--
-- `candidate_hypothesis_id` IS NOT A FORGOTTEN WRITE, and it goes for a
-- different reason from the other two columns. `0023:161-166` added it so that
-- from the Hypothesis a candidate BECAME there is a way back to the near-match
-- row, and says in the same breath that the `penalised` action exists for
-- exactly that lookup and that `key_collision` "has no candidate row either".
-- It is NULL today because the only action ever written is the one that
-- correctly has no candidate. It is removed here because it is the storage for
-- an action that is being removed, not because nothing filled it.
--
-- WHAT THE HARNESS GIVES UP, said out loud in the migration that removes it. A
-- Hypothesis that is a near-duplicate of an existing one in meaning but not in
-- key is promoted as new, and nothing records the resemblance. There is no
-- `suppressed` and no `penalised`: the ranking pass no longer discounts a Task
-- for sitting on a hypothesis that resembles another, and `novelty_for('hunt')`
-- is evidence count alone. The trace that remains is `key_collision` -- the
-- same event arriving through the index -- and it names the row it collided
-- with and keeps the prose that converged.
--
-- WHAT WOULD HAVE TO COME BACK, so that "deferred" is not the word the next
-- audit reads. `0010` is thirty lines and the two arms of the CHECK are five;
-- what does not come back for free is the reasoning above. If semantic dedup is
-- wanted later it needs, in this order: a model identifier stable across a
-- campaign (`0010:5-6` already anticipates the migration story -- "switching
-- models inserts rows instead of rewriting the hot tables, and two models
-- coexist during a migration"); a place to run the call that is not the process
-- holding the `rk2_runtime` connection; and a dedup vocabulary fine enough that
-- a cosine distance is deciding between candidates rather than compensating for
-- a class that cannot tell three defects apart.
--
-- WHY `hnsw_headroom` GOES WITH THEM, and it is not tidying. `0027:359-376`
-- counts rows in the two embedding tables against `maintenance_work_mem` to say
-- whether the next HNSW build spills to disk, and the live
-- `check_server_baseline` asserts on it
-- (`20260811T120000Z__falsifiable_integrity_checks.sql:94-100`). Over two
-- permanently empty tables the answer is "infinite headroom" forever, and it
-- would begin failing on the first day anything wrote a vector -- which is the
-- worst possible moment for a baseline check to start speaking. The view also
-- cannot be left standing over dropped tables: measured, `DROP TABLE
-- observation_embeddings` as `rk2_migrate` refuses with `2BP01 ... view
-- hnsw_headroom depends on table observation_embeddings`. The two tables, the
-- two HNSW indexes, the view and its helper `hnsw_bytes_per_tuple` are one unit
-- and move together.
--
-- AND THE TWO `hnsw.*` SETTINGS GO WITH THE INDEXES THEY TUNED.
-- `apply_server_settings()` (`0028:44-135`) ships three `ALTER DATABASE ... SET`
-- values. `maintenance_work_mem = 256MB` stays: it is not a pgvector setting and
-- `0028:59-93` argues it on its own terms with a measured sweep. The other two
-- are HNSW scan knobs and nothing else -- `hnsw.iterative_scan = relaxed_order`
-- (`0028:127`) exists because an unfiltered HNSW scan returns fewer rows than
-- asked for, and `hnsw.max_scan_tuples = 40000` (`0028:133`) is the ceiling on
-- that scan. With no HNSW index in the schema they configure nothing, so they
-- are removed from the finalizer AND reset on the database: a
-- `pg_db_role_setting` row that survives its subject is configuration no file
-- declares. Their two baseline arms go with them.
--
-- WHAT IS NOT REMOVED, AND WHY -- the one element of ticket 127's decision this
-- file cannot pay. The decision says "pgvector comes out of the provision path
-- with them". It does not, and the obstacle is not `provision()`: it is
-- `0001_extensions.sql:2`, which is `CREATE EXTENSION IF NOT EXISTS vector` and
-- runs as `rk2_migrate` on every database the corpus is applied to from empty.
-- Measured on this image, against a fresh database with no `vector` in it:
--
--     [as rk2_migrate] CREATE EXTENSION IF NOT EXISTS vector
--         ERROR:  permission denied to create extension "vector"
--         HINT:   Must be superuser to create this extension.
--
-- Today that statement is a no-op only because `provision()`
-- (`src/redkraken/migrate.py:381`) has already installed the extension as a
-- superuser. Take the install out of `provision()` and `rk db migrate` stops
-- being able to reach migration two. So the extension stays installed and empty
-- until `0001` can be changed, and with it stay the `pgvector_version` and
-- `hnsw_cosine_opclass` baseline arms and `backup.PROVISIONED_EXTENSIONS`:
-- every one of those is still a true statement about what applying this corpus
-- requires. The line is drawn between the PRESENCE of the extension, which the
-- corpus still demands, and the BEHAVIOUR of HNSW indexes, of which there are
-- now none.
--
-- One consequence worth recording for whoever does remove it: after this file
-- nothing in the schema uses the `vector` type, so `--exclude-extension=vector`
-- in `backup.dump` no longer excludes any table definition -- only the
-- `COMMENT ON EXTENSION` `pg_dump` emits, which is still superuser work the
-- restore connection cannot do.
-- ---------------------------------------------------------------------------


SET client_min_messages = notice;


-- ===========================================================================
-- 1. The two readers of the columns that go
-- ===========================================================================

-- Replaced before the columns are dropped, for 126's reason in reverse: both
-- are string-bodied, so neither carries a catalogue dependency on
-- `hypothesis_near_matches.similarity` and neither would refuse the `ALTER
-- TABLE`. They would fail at their first call instead -- `novelty_for` inside
-- `rank_pass`, which is the ranking of every Task in the queue. `CREATE OR
-- REPLACE` rather than drop-and-create because `novelty_for(tasks)` is closed
-- to PUBLIC and held by `rk2_runtime` through a `runtime_verb_surface` row, and
-- a drop would take the grant with it and leave the register naming a verb the
-- runtime no longer holds.

-- 32/D14 is not closed by this file, it is withdrawn. The near-match discount
-- was the only reader of `similarity` in the corpus and it read a column no
-- writer ever filled: `coalesce(1 - sim, 1)` evaluated to 1 on every row, so
-- removing the lookup changes no number this function has ever returned. What
-- it changes is the claim -- a hunt Task is scored on how little evidence it
-- has, and on nothing else.
CREATE OR REPLACE FUNCTION novelty_for(t tasks) RETURNS numeric
LANGUAGE plpgsql STABLE AS $fn$
DECLARE
    covered   integer;
    total     integer;
    n_ev      integer;
    st        text;
    fired     boolean;
BEGIN
    IF t.kind = 'recon' THEN
        -- Ticket 27, measured: the denominator is the 8 FAMILIES, not the 33
        -- leaves. Family coverage ranged 0.625 across the corpus against 0.24
        -- for leaf coverage, so the leaf denominator makes every recon task
        -- look equally novel forever.
        --
        -- And the numerator routes through `hypotheses`, not `observations`:
        -- 27 executed the schema and found `observations` has no
        -- `property_class` at all, and said explicitly not to add one. A
        -- property class is a claim about what a test IS; an observation is a
        -- fact. What "has this property been looked at on this subject" means
        -- is therefore "has a hypothesis about it been written down".
        SELECT count(DISTINCT pc.family_id) INTO covered
          FROM hypotheses h
          JOIN property_classes pc ON pc.id = h.property_class
         WHERE h.subject_entity_id = t.subject_entity_id
           AND h.superseded_by IS NULL;
        SELECT count(*) INTO total FROM property_class_families;
        RETURN greatest(1.0 - covered::numeric / total, 0);

    ELSIF t.kind = 'analyze' THEN
        -- Same shape over the other vocabulary 27 built. "analysis-kind" is
        -- decidable now: it is a kind a tool run may back, which is exactly
        -- what offline analysis over a content-addressed artifact produces.
        SELECT count(DISTINCT o.kind) INTO covered
          FROM observations o
          JOIN observation_kinds k ON k.id = o.kind
         WHERE o.subject_entity_id = t.subject_entity_id
           AND o.provenance_kind = 'tool_run'
           AND 'tool_run' = ANY (k.allowed_provenance);
        SELECT count(*) INTO total
          FROM observation_kinds WHERE 'tool_run' = ANY (allowed_provenance);
        RETURN greatest(1.0 - covered::numeric / total, 0);

    ELSIF t.kind = 'hunt' THEN
        SELECT h.status INTO st FROM hypotheses h WHERE h.id = t.hypothesis_id;
        SELECT EXISTS (SELECT 1 FROM hypothesis_retest_triggers x
                        WHERE x.hypothesis_id = t.hypothesis_id
                          AND x.fired_at IS NOT NULL) INTO fired;
        IF st IN ('supported','refuted') AND NOT fired THEN
            RETURN 0;
        END IF;
        SELECT count(*) INTO n_ev
          FROM hypothesis_evidence WHERE hypothesis_id = t.hypothesis_id;
        -- Ticket 127: the `penalised` discount that used to multiply this is
        -- gone with the action it belonged to. There is no similarity in this
        -- schema to discount by.
        RETURN 1.0 / (1 + n_ev);

    ELSIF t.kind = 'validate' THEN
        -- 32/D13 was closed by migration 015: a validate task names its
        -- finding, so this is a lookup rather than a scan of the subject.
        RETURN CASE WHEN EXISTS (
                 SELECT 1 FROM findings f
                  WHERE f.id = t.finding_id
                    AND f.status IN ('validated','reported','rejected'))
               THEN 0 ELSE 1 END;

    ELSIF t.kind = 'report' THEN
        RETURN CASE WHEN EXISTS (
                 SELECT 1 FROM findings f
                  WHERE f.program_id = t.program_id AND f.status = 'validated'
                    AND f.reported_at IS NULL) THEN 1 ELSE 0 END;
    END IF;
    RETURN 0;
END $fn$;

-- Arm (e) -- "a penalised near-match names the hypothesis it penalises" -- is
-- withdrawn, and the letters of the arms after it are left where they are.
-- Renumbering them would make a `git log -S` for `near_match_penalty_unreachable`
-- land on a file that also appears to have moved six unrelated checks.
CREATE OR REPLACE FUNCTION check_scheduler_closure()
RETURNS TABLE (problem text, detail text) LANGUAGE sql STABLE AS $fn$
    -- (a) every kind the roster grants can be ranked by every factor. A kind
    --     with no branch in one of the three functions is a task that ranks 0
    --     forever and nobody notices.
    SELECT 'kind_has_no_cost_prior'::text, k.kind
      FROM task_kinds k, scheduler_weights w
     WHERE w.active AND NOT (w.cost_prior ? k.kind)
UNION ALL
    -- (b) the per-program lane override is reachable. This is the defect the
    --     migration exists to close; asserting it means dropping the view or
    --     reverting the join cannot make overrides silently inert again.
    SELECT 'lane_override_unreachable', p.id::text || ' ' || l.kind
      FROM scheduler_lanes l JOIN programs p ON p.id = l.program_id
     WHERE NOT EXISTS (SELECT 1 FROM effective_lane_capacity c
                        WHERE c.program_id = l.program_id AND c.kind = l.kind
                          AND c.overridden)
UNION ALL
    -- (c) an entitlement above the roster's cap, now for OVERRIDE rows too --
    --     ticket 34's check (e) reads `lane_capacity`, which only ever contains
    --     the NULL-program rows.
    SELECT 'lane_min_above_role_cap',
           coalesce(c.program_id::text, 'default') || ' ' || c.kind
      FROM effective_lane_capacity c WHERE c.min_slots > c.max_slots
UNION ALL
    -- (d) every skill a task requires is registered.
    SELECT 'task_requires_unregistered_skill', t.label || ' ' || s
      FROM tasks t CROSS JOIN LATERAL unnest(t.required_skills) AS s
     WHERE NOT EXISTS (SELECT 1 FROM skills k WHERE k.name = s)
UNION ALL
    -- (e) is gone with ticket 127. It asked whether a `penalised` near-match
    --     named the hypothesis it penalised; `penalised` is no longer an action
    --     `hypothesis_near_matches` accepts, and the CHECK on the column is
    --     what says so now, at write time rather than at check time.
    --
    -- (f) the slate cannot be larger than the table that holds it.
    SELECT 'slate_size_exceeds_task_slate', w.slate_size::text
      FROM scheduler_weights w WHERE w.active AND w.slate_size > 5
UNION ALL
    -- (g) the ranking pass has no clock in it. Decision 12 is a property of the
    --     text, so it is checked against the text: `now()` / `current_timestamp`
    --     inside the three factor functions would make two replays of the same
    --     rows disagree, and nothing else would ever say so. Comments are
    --     stripped first: the first version of this check fired on a comment
    --     explaining why the clock is absent, which is the check calling its
    --     own documentation a defect.
    SELECT 'ranking_factor_reads_the_clock', p.proname
      FROM pg_proc p
     WHERE p.pronamespace = 'public'::regnamespace
       AND p.proname IN ('novelty_for','cost_for','confidence_for')
       AND regexp_replace(p.prosrc, '--[^' || chr(10) || ']*', '', 'g')
           ~* '(now\(\)|current_timestamp|clock_timestamp)'
UNION ALL
    -- (h) the claim takes the lock. Ticket 32 found lane caps unheld without
    --     it, and ticket 08's text still says no lock is needed.
    SELECT 'claim_task_takes_no_advisory_lock', 'claim_task'
      FROM pg_proc p
     WHERE p.pronamespace = 'public'::regnamespace AND p.proname = 'claim_task'
       AND p.prosrc !~ 'pg_advisory_xact_lock'
UNION ALL
    -- (i) no scheduler function is callable by PUBLIC.
    SELECT 'scheduler_function_public_executable', p.proname
      FROM pg_proc p
     WHERE p.pronamespace = 'public'::regnamespace
       AND p.proname IN ('novelty_for','cost_for','confidence_for','ready_for',
                         'cancel_reason_for','rank_pass','rank_candidates',
                         'offer_slate','claim_task','sweep_expired_leases',
                         'scheduler_idle_report')
       AND has_function_privilege('public', p.oid, 'EXECUTE')
$fn$;


-- ===========================================================================
-- 2. The near-match vocabulary closes on the one action that has a writer
-- ===========================================================================

-- The three constraints that spoke about the two unreachable actions. The
-- foreign key goes with the column it keys, and `0023:168-179`'s reason for its
-- delete rule goes with it: there is no longer a second key between
-- `hypothesis_near_matches` and `hypotheses` for `enforce_fk_fire_order` to
-- order against `matched_hypothesis_id`.
ALTER TABLE hypothesis_near_matches
    DROP CONSTRAINT hypothesis_near_matches_stage2_cols,
    DROP CONSTRAINT hypothesis_near_matches_candidate_matches_action,
    DROP CONSTRAINT hypothesis_near_matches_candidate_fk;

-- Named rather than left to fall with its column, so that the drop of a partial
-- index whose predicate is `action = 'penalised'` is a line in this file rather
-- than a catalogue effect the next reader has to reconstruct.
DROP INDEX hypothesis_near_matches_candidate_idx;

ALTER TABLE hypothesis_near_matches
    DROP COLUMN similarity,
    DROP COLUMN embedding_model,
    DROP COLUMN candidate_hypothesis_id;

-- The vocabulary itself. `= 'key_collision'` rather than `IN ('key_collision')`
-- because a one-element IN reads as a list that lost its other members, which
-- is exactly the misreading `0018:429-436` would otherwise invite: this is not a
-- vocabulary waiting for the other two back, it is one action. Adding the
-- constraint validates the existing rows, so a database that somehow holds a
-- `suppressed` or `penalised` row refuses this migration instead of silently
-- keeping a row no CHECK covers.
ALTER TABLE hypothesis_near_matches
    DROP CONSTRAINT hypothesis_near_matches_action_check,
    ADD CONSTRAINT hypothesis_near_matches_action_check
        CHECK (action = 'key_collision');

COMMENT ON TABLE hypothesis_near_matches IS
  'Ticket 08''s trace, narrowed by ticket 127 to the half that has a writer: a hard key collision, the candidate statement that lost and the Hypothesis it collided with. The similarity-based actions and their stage-2 columns are gone with the embedding tables that never produced one.';

-- G8: a file that moves the closed set on a column re-issues that column's
-- comment in the same file. The set moved here from three spellings to one, and
-- the reason a reader of `\d+ hypothesis_near_matches` needs is why the other
-- two are not coming back rather than what they meant. `0018:414-421` is where
-- they were written down, and the sentence that retires them is its own.
COMMENT ON COLUMN hypothesis_near_matches.action IS
 'One spelling, because one is all that has a writer: `key_collision`, a candidate whose dedup key was already taken. `suppressed` and `penalised` left with ticket 127 -- both needed a similarity nothing in this harness computes, and `0018:414-418` says why the trace is enough without them: a hard key collision "is the same event arriving through the index instead of through pgvector".';

-- Three columns off the agent's read surface. `check_state_grants()` arm 5
-- reports `state_surface_names_missing_object` for a registry row whose column
-- no longer exists, so this is the difference between the migration applying
-- and the gate failing at the end of the run that applied it.
DO $$
DECLARE n integer;
BEGIN
    DELETE FROM state_read_surface
     WHERE table_name = 'hypothesis_near_matches'
       AND column_name IN ('similarity', 'embedding_model',
                           'candidate_hypothesis_id');
    GET DIAGNOSTICS n = ROW_COUNT;
    IF n <> 3 THEN
        RAISE EXCEPTION 'ticket 127: deleted % state_read_surface row(s), expected 3', n;
    END IF;
END $$;


-- ===========================================================================
-- 3. The headroom view, its helper, and the two tables
-- ===========================================================================

-- The view before the tables, because it is a real catalogue dependency and
-- `DROP TABLE` would refuse -- measured, not assumed: `2BP01 ... view
-- hnsw_headroom depends on table observation_embeddings`. The helper goes with
-- the view rather than after the tables, because `hnsw_headroom` was its only
-- caller and a bytes-per-tuple constant with nothing counting tuples is a
-- measurement with no subject. Every drop is plain: a CASCADE here would be a
-- statement whose blast radius the next reader has to work out from the
-- catalogue.
DROP VIEW hnsw_headroom;
DROP FUNCTION hnsw_bytes_per_tuple(int);

-- The two HNSW indexes go with their tables, as do the `derive_program_id`
-- triggers 017 gave them and the RLS policies `apply_state_rls()` did. Neither
-- table is a parent of anything: the only foreign keys they carry point out of
-- them, at `hypotheses` and `observations`.
DROP TABLE hypothesis_embeddings;
DROP TABLE observation_embeddings;


-- ===========================================================================
-- 4. The baseline arms, and the settings that tuned an index nobody has
-- ===========================================================================

-- `check_server_baseline` minus three arms and the cast that existed for two of
-- them. Everything else is `20260811T120000Z__falsifiable_integrity_checks.sql`
-- unchanged, including the four fixed runtime facts it delegates to
-- `evaluate_server_runtime` -- `pgvector_version` and `hnsw_cosine_opclass`
-- stay, because `0001_extensions.sql:2` still requires the extension to be
-- installed before this corpus can be applied at all.
CREATE OR REPLACE FUNCTION check_server_baseline(p_expected_migrations text[] DEFAULT NULL)
RETURNS TABLE (check_name text, ok boolean, detail text)
LANGUAGE plpgsql STABLE AS $fn$
DECLARE
    v_mwm bigint;
    v_src text;
    v_pgv text;
    v_uuidv7_oids bigint[];
    v_hnsw_cosine boolean;
    v_n int;
BEGIN
    SELECT array_agg(oid::bigint ORDER BY oid) INTO v_uuidv7_oids
      FROM pg_proc WHERE proname = 'uuidv7' AND pronargs = 0;
    SELECT extversion INTO v_pgv FROM pg_extension WHERE extname = 'vector';
    SELECT EXISTS (
        SELECT 1 FROM pg_opclass o JOIN pg_am a ON a.oid = o.opcmethod
         WHERE a.amname = 'hnsw' AND o.opcname = 'vector_cosine_ops'
    ) INTO v_hnsw_cosine;

    RETURN QUERY SELECT * FROM evaluate_server_runtime(
        current_setting('server_version_num')::integer,
        v_uuidv7_oids,
        v_pgv,
        v_hnsw_cosine
    );

    -- The `SELECT '[1]'::vector` that used to stand here is gone with the two
    -- `hnsw.*` arms below it. It loaded the pgvector library so those GUCs
    -- stopped being placeholders and appeared in `pg_settings` with a source;
    -- with no `hnsw.*` arm left to read, it loaded a library to answer nothing.

    SELECT setting::bigint, source INTO v_mwm, v_src
      FROM pg_settings WHERE name = 'maintenance_work_mem';
    RETURN QUERY SELECT 'maintenance_work_mem'::text,
        coalesce(v_mwm >= 262144 AND v_src = 'database', false),
        'maintenance_work_mem = ' || v_mwm || 'kB, source = ' || v_src;

    RETURN QUERY SELECT 'session_replication_role'::text,
        current_setting('session_replication_role') = 'origin',
        'session_replication_role = ' || current_setting('session_replication_role');

    RETURN QUERY SELECT 'default_transaction_isolation'::text,
        current_setting('default_transaction_isolation') = 'read committed',
        'default_transaction_isolation = ' || current_setting('default_transaction_isolation');

    RETURN QUERY SELECT 'schema_migrations_present'::text,
        to_regclass('rk2_meta.schema_migrations') IS NOT NULL,
        'schema_migrations'::text;

    IF to_regclass('rk2_meta.schema_migrations') IS NOT NULL THEN
        SELECT count(*) INTO v_n FROM (
            SELECT id, applied_seq, lag(id) OVER (ORDER BY applied_seq) AS prev_id
              FROM rk2_meta.schema_migrations
        ) s WHERE prev_id IS NOT NULL AND id < prev_id;
        RETURN QUERY SELECT 'migrations_in_declared_order'::text, v_n = 0,
            v_n || ' migration(s) applied out of filename order';

        IF p_expected_migrations IS NOT NULL THEN
            SELECT count(*) INTO v_n FROM (
                SELECT id FROM rk2_meta.schema_migrations
                EXCEPT SELECT unnest(p_expected_migrations)
            ) s;
            RETURN QUERY SELECT 'no_unknown_migrations'::text, v_n = 0,
                v_n || ' migration(s) in the database with no file';
            SELECT count(*) INTO v_n FROM (
                SELECT unnest(p_expected_migrations)
                EXCEPT SELECT id FROM rk2_meta.schema_migrations
            ) s;
            RETURN QUERY SELECT 'no_pending_migrations'::text, v_n = 0,
                v_n || ' migration file(s) not applied';
        END IF;
    END IF;

    SELECT count(*) INTO v_n FROM check_event_coverage()
     WHERE problem NOT LIKE 'undecided\_%';
    RETURN QUERY SELECT 'event_coverage'::text, v_n = 0,
        v_n || ' coverage problem(s)';
END $fn$;

-- `apply_server_settings` minus the two HNSW scan knobs and the cast that was
-- their precondition. `0028:29-41`'s reason for this being a function and not a
-- script is untouched and is why the body is rewritten rather than the settings
-- simply reset: `pg_dump` does not carry `ALTER DATABASE ... SET`, so a
-- restored database re-runs this function, and one that still set `hnsw.*`
-- would put both values straight back on the next `rk db migrate`.
CREATE OR REPLACE FUNCTION apply_server_settings() RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    -- ---------------------------------------------------------------------
    -- maintenance_work_mem = 256MB
    --
    -- Measured by ./measure_hnsw.sh on this image, 20 000 rows of vector(1536)
    -- (the shape `hypothesis_embeddings` had), 20 000 distinct vectors:
    --
    --      setting  spilled  at tuples  build     index
    --       32MB    yes       4879       74.0 s   156 MB
    --       64MB    yes       9751       54.6 s   156 MB   <- pgvector default
    --      128MB    yes      19505       15.6 s   156 MB
    --      256MB    no          -        12.7 s   156 MB   <- shipped
    --
    -- Ticket 127 removed the tables that sweep was run against, and the setting
    -- stays anyway: `maintenance_work_mem` is what every index build, `REINDEX`
    -- and autovacuum on this database gets, and 256MB was chosen as the
    -- smallest power-of-two step that builds a large index without spilling.
    -- The pgvector measurement is the evidence for the number, not the reason
    -- for the setting.
    --
    -- Applies to autovacuum workers on this database too (autovacuum_work_mem
    -- defaults to -1 = maintenance_work_mem). At three workers that is 768MB
    -- worst case on a local single-database host: accepted.
    -- ---------------------------------------------------------------------
    EXECUTE format('ALTER DATABASE %I SET maintenance_work_mem = %L',
                   current_database(), '256MB');
END $$;

-- The two values already sitting in `pg_db_role_setting` on every database this
-- corpus has been applied to. The finalizer above will not write them again;
-- this is what takes the ones already written away.
--
-- The vector cast is here, once, for the reason `0028:46-55` measured: until
-- the pgvector library is loaded into this backend, `hnsw.iterative_scan` is an
-- undefined custom GUC and touching one is superuser work, so the owner's
-- `ALTER DATABASE ... RESET` would be refused with `permission denied to set
-- parameter`. `CREATE EXTENSION` does not load the library; using a type from
-- it does. This is the last statement in the corpus that needs pgvector at
-- runtime.
DO $$
BEGIN
    PERFORM '[1]'::vector;
    EXECUTE format('ALTER DATABASE %I RESET "hnsw.iterative_scan"', current_database());
    EXECUTE format('ALTER DATABASE %I RESET "hnsw.max_scan_tuples"', current_database());
END $$;

SELECT apply_server_settings();


-- ===========================================================================
-- 5. The register rows, all three registers
-- ===========================================================================

-- A dropped table that keeps its register rows is worse than one that never had
-- them: two of these registers are policed by a check that reports a row naming
-- a missing table, and the third is policed by a check that joins to `pg_class`
-- and therefore goes blind at exactly the moment the row becomes wrong. Every
-- count is asserted, because a name that matched nothing would delete nothing
-- and let this file declare itself finished.
DO $$
DECLARE n integer;
BEGIN
    -- (a) emission. `0027:73-74` classified both `derived` -- "recomputable
    -- from hypotheses; bulk vector, never epistemic content" -- which was true
    -- and is now moot. `check_event_coverage()` answers `exempt_row_missing_table`
    -- for a survivor. The `hypothesis_near_matches` row is NOT touched: the
    -- table stays, and `0030:59-65` classified it `covered` on the ground that
    -- the emitting row names it.
    DELETE FROM event_table_exempt
     WHERE table_name IN ('hypothesis_embeddings', 'observation_embeddings');
    GET DIAGNOSTICS n = ROW_COUNT;
    IF n <> 2 THEN
        RAISE EXCEPTION 'ticket 127: deleted % event_table_exempt row(s), expected 2', n;
    END IF;

    -- (b) the purge graph. `0016:216-217`, one edge each, both to the parent
    -- that owns the row. `check_purge_travel()` joins the register to
    -- `pg_class`, so a stale row here is invisible to the check that is
    -- supposed to keep the register honest -- which is why it is deleted by
    -- hand. `hypothesis_near_matches` keeps its own edge: it has a `program_id`
    -- and is a purge root in its own right.
    DELETE FROM purge_cascade_edges
     WHERE table_name IN ('hypothesis_embeddings', 'observation_embeddings');
    GET DIAGNOSTICS n = ROW_COUNT;
    IF n <> 2 THEN
        RAISE EXCEPTION 'ticket 127: deleted % purge_cascade_edges row(s), expected 2', n;
    END IF;

    -- (c) the runtime's table surface. Twelve rows, four privileges on each of
    -- the two tables and four more on `hnsw_headroom` -- a view, which
    -- `runtime_relations` counts like any other relation. All twelve are
    -- `66-seed`: they arrived granted by 029's default privileges and 066
    -- recorded what the catalogue already held, so the runtime never asked for
    -- any of it. `runtime_table_surface_names_missing_object` is what a
    -- survivor would report.
    DELETE FROM runtime_table_surface
     WHERE table_name IN ('hypothesis_embeddings', 'observation_embeddings',
                          'hnsw_headroom');
    GET DIAGNOSTICS n = ROW_COUNT;
    IF n <> 12 THEN
        RAISE EXCEPTION 'ticket 127: deleted % runtime_table_surface row(s), expected 12', n;
    END IF;
END $$;

-- No `runtime_verb_surface` row is deleted and no verb is revoked, and the
-- absence is worth stating because the house rule pairs the two. Of the
-- functions this file touches, only `novelty_for(tasks)` is closed to PUBLIC
-- and held by `rk2_runtime`, and it is replaced in place rather than dropped,
-- so its grant and its register row are both untouched. `hnsw_bytes_per_tuple`,
-- which is dropped, was executable by PUBLIC and therefore never had a row.


-- ===========================================================================
-- 6. What this migration claims, asserted
-- ===========================================================================

-- Not "the tables were dropped" -- `DROP TABLE` already raises on an absent
-- table. The claims are that the embedding half leaves nothing behind that a
-- later reader could mistake for a hole where a producer used to be; that the
-- near-match trace still exists and is exactly one action wide; and that the
-- one thing this file deliberately did NOT remove is still true, so that the
-- next audit reads a measured limit rather than an oversight.
DO $$
DECLARE
    v_left text;
    v_n    integer;
BEGIN
    -- (a) nothing named for the retired half survives, as a relation or as a
    -- function.
    SELECT string_agg(c.relname, ', ' ORDER BY c.relname) INTO v_left
      FROM pg_class c
      JOIN pg_namespace ns ON ns.oid = c.relnamespace AND ns.nspname = 'public'
     WHERE (c.relname LIKE '%\_embeddings' OR c.relname LIKE 'hnsw\_%')
       AND NOT EXISTS (SELECT 1 FROM pg_depend d
                        WHERE d.classid = 'pg_class'::regclass
                          AND d.objid = c.oid AND d.deptype = 'e');
    IF v_left IS NOT NULL THEN
        RAISE EXCEPTION 'ticket 127: relations survive the retirement: %', v_left;
    END IF;

    -- Extension functions are excluded, for the reason
    -- `20260909T000000Z__the_runtime_holds_what_the_surface_declares.sql:135`
    -- gives about `runtime_verbs`: pgvector installs ~90 functions into `public`
    -- and three of them are `hnsw_bit_support`, `hnsw_halfvec_support` and
    -- `hnsw_sparsevec_support`. They are not the corpus's, and the extension
    -- stays -- so an arm that matched on the name alone would report the
    -- retirement had failed on the first run. `deptype = 'e'` is what tells the
    -- one function this corpus owned from the ninety it did not.
    SELECT string_agg(p.proname, ', ' ORDER BY p.proname) INTO v_left
      FROM pg_proc p
      JOIN pg_namespace ns ON ns.oid = p.pronamespace AND ns.nspname = 'public'
     WHERE p.proname LIKE 'hnsw\_%'
       AND NOT EXISTS (SELECT 1 FROM pg_depend d
                        WHERE d.classid = 'pg_proc'::regclass
                          AND d.objid = p.oid AND d.deptype = 'e');
    IF v_left IS NOT NULL THEN
        RAISE EXCEPTION 'ticket 127: functions survive the retirement: %', v_left;
    END IF;

    -- (b) no register row names one of them, in any of the five registers a
    -- table can appear in.
    SELECT count(*) INTO v_n FROM (
        SELECT table_name FROM event_table_exempt
        UNION ALL SELECT table_name FROM purge_cascade_edges
        UNION ALL SELECT table_name FROM runtime_table_surface
        UNION ALL SELECT table_name FROM state_read_surface
        UNION ALL SELECT table_name FROM program_global_tables
    ) r WHERE r.table_name LIKE '%\_embeddings' OR r.table_name LIKE 'hnsw\_%';
    IF v_n <> 0 THEN
        RAISE EXCEPTION 'ticket 127: % register row(s) still name a retired relation', v_n;
    END IF;

    -- (c) no `vector` column is left anywhere. Asked against the type rather
    -- than against the two table names, because the claim is about the
    -- capability and not about two relations: this is what makes "nothing in
    -- the schema uses pgvector" a fact a later reader can re-run.
    SELECT string_agg(c.relname || '.' || a.attname, ', ') INTO v_left
      FROM pg_attribute a
      JOIN pg_class c ON c.oid = a.attrelid
      JOIN pg_namespace ns ON ns.oid = c.relnamespace AND ns.nspname = 'public'
      JOIN pg_type t ON t.oid = a.atttypid
     WHERE a.attnum > 0 AND NOT a.attisdropped AND t.typname = 'vector';
    IF v_left IS NOT NULL THEN
        RAISE EXCEPTION 'ticket 127: vector column(s) survive: %', v_left;
    END IF;

    -- (d) the trace survives, and is one action wide. Read off the constraint
    -- rather than off the vocabulary table, because the CHECK is what a writer
    -- meets.
    SELECT count(*) INTO v_n FROM pg_constraint
     WHERE conrelid = 'hypothesis_near_matches'::regclass
       AND conname = 'hypothesis_near_matches_action_check'
       AND pg_get_constraintdef(oid) LIKE '%key_collision%'
       AND pg_get_constraintdef(oid) NOT LIKE '%penalised%'
       AND pg_get_constraintdef(oid) NOT LIKE '%suppressed%';
    IF v_n <> 1 THEN
        RAISE EXCEPTION 'ticket 127: hypothesis_near_matches does not close on key_collision alone';
    END IF;

    -- And it is still reachable: the one writer names five columns and all five
    -- remain, so a drop that had taken one of them would be found here rather
    -- than on the next converged proposal.
    SELECT count(*) INTO v_n
      FROM pg_attribute a
     WHERE a.attrelid = 'hypothesis_near_matches'::regclass
       AND a.attnum > 0 AND NOT a.attisdropped
       AND a.attname IN ('program_id','candidate_statement',
                         'matched_hypothesis_id','action','agent_run_id');
    IF v_n <> 5 THEN
        RAISE EXCEPTION
            'ticket 127: the key-collision writer names 5 columns and % survive', v_n;
    END IF;

    -- (e) the two settings are off this database, and the one that is not a
    -- pgvector setting is still on it.
    SELECT count(*) INTO v_n
      FROM pg_db_role_setting s
      JOIN pg_database d ON d.oid = s.setdatabase AND d.datname = current_database()
     CROSS JOIN LATERAL unnest(s.setconfig) AS item
     WHERE s.setrole = 0 AND item LIKE 'hnsw.%';
    IF v_n <> 0 THEN
        RAISE EXCEPTION 'ticket 127: % hnsw.* setting(s) survive on this database', v_n;
    END IF;

    SELECT count(*) INTO v_n
      FROM pg_db_role_setting s
      JOIN pg_database d ON d.oid = s.setdatabase AND d.datname = current_database()
     CROSS JOIN LATERAL unnest(s.setconfig) AS item
     WHERE s.setrole = 0 AND item = 'maintenance_work_mem=256MB';
    IF v_n <> 1 THEN
        RAISE EXCEPTION 'ticket 127: maintenance_work_mem left with the hnsw settings';
    END IF;

    -- (f) the limit this file could not pay, asserted as a limit. `0001` still
    -- installs the extension, so it is still present -- and the day somebody
    -- changes `0001_extensions.sql:2` and takes `CREATE EXTENSION` out of
    -- `provision()`, this arm fails and points at the two baseline checks and
    -- the archive exclusion that go with it. It is the only assertion in this
    -- file that is asking to be broken.
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        RAISE EXCEPTION
            'ticket 127: the vector extension is gone, so 0001_extensions.sql:2 cannot '
            'run on an empty database -- remove CREATE EXTENSION from provision(), the '
            'pgvector_version and hnsw_cosine_opclass baseline arms, and '
            'backup.PROVISIONED_EXTENSIONS, in one change';
    END IF;
END $$;
