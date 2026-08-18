-- ===========================================================================
-- Production harness 61 -- a write in a subtransaction is still this write
-- ===========================================================================
-- What ticket 61's campaign found on its first restart: a Program that had
-- promoted one Observation could not be resumed. `rk run` refuses a
-- configuration that would leave the Program failing its own checks, and this
-- one was failing `event_log_integrity` with
--
--     (row_last_write_unaccounted, observations, 1)
--
-- for an Observation whose `observation.recorded` event was sitting right
-- there, written by the same statement.
--
-- Part (d) of `check_event_log_integrity()` asks whether the transaction that
-- produced a row's live tuple also wrote an event about it, and it asks by
-- comparing the tuple's `xmin` with the `xact_id` the event recorded. That
-- comparison has a hole, and every promotion falls through it: `xact_id`
-- defaults to `pg_current_xact_id()`, which is the TOP-LEVEL transaction id,
-- while `xmin` is the id of whatever (sub)transaction wrote the tuple. A
-- plpgsql `BEGIN ... EXCEPTION` block is a subtransaction, and
-- `promote_proposal()` writes every Entity, Relationship and Observation inside
-- one -- deliberately, because that is how an element the schema refuses
-- becomes a `proposal_drops` row instead of a lost promotion. So the row
-- carries the subtransaction's id, the event carries the top-level one, and the
-- check reads a matched pair as an unaccounted write:
--
--     xmin 777505   the Observation, written inside the exception block
--     xact_id 777502   its event, recording the transaction as a whole
--
-- The event is not missing and nothing was written behind the log's back. The
-- two ids name the same transaction and the comparison could not see it.
--
-- Taking the exception block out of `promote_proposal()` is not the answer:
-- that would trade a reporting defect for a promotion that dies on its first
-- refused element, which is what the block is there to prevent. Nor is making
-- the emitter stamp events with a subtransaction id -- `events.xact_id` means
-- the transaction as a whole to every reader it has, 013's actor guard and the
-- lease heartbeat compare it against `pg_current_xact_id()` by name, and 0042
-- asserts that binding is still in the emitter.
--
-- So (d) gains a second way to recognise the transaction that wrote a row: an
-- event whose OWN tuple was written by it. The emitter is an AFTER trigger of
-- the statement it accounts for, so it runs in the same subtransaction as the
-- write and its event carries the same `xmin` -- which makes the new disjunct
-- exact rather than lenient. What the check still catches is what it was
-- written to catch: a write with no event of its own from the transaction that
-- made it, subtransaction or not.
--
-- The same campaign found the same hole on the other arm, where it needs the
-- other half of the fix. A write that changed only ignored columns emits no
-- event and writes a `suppressed_writes` row instead -- 016's D5 -- and that
-- row recorded `pg_current_xact_id()` too. Convergent promotion runs into this
-- constantly: a second result naming subjects the first one already recorded
-- rewrites their rows without changing a column anybody logs. There the
-- recorded id is not merely a different name for the same transaction, it is
-- the PRIMARY KEY, so a second exception block's suppressed write collided
-- with the first one's row and was dropped -- leaving the second block's tuples
-- accounted for by nothing at all. `entities x2` and `relationships x1`, on a
-- Program whose only history was two promotions.
--
-- A tuple's own `xmin` is the answer on both arms; the difference is that a
-- suppression row is not written per row written, so it cannot carry the id in
-- its tuple header and has to record it. `emit_event` therefore asks the tuple
-- it is accounting for which transaction made it, and records THAT -- one
-- extra read, on the suppression path only, where a row was going to be
-- written anyway. 016's "one row per (program, table, transaction)" keeps its
-- intent and loses one collapse: ten thousand `last_seen_at` refreshes in one
-- statement are still one row, and two exception blocks that each suppress a
-- write are now two rows rather than one row accounting for the first of them.
-- (d)'s suppression comparison, untouched, becomes exact.
--
-- Everything else in both functions is carried verbatim, for the reason 0027
-- states: CREATE OR REPLACE on a checker is how a check disappears without
-- anyone deleting a line, so a replacement may only add rows.
-- ===========================================================================

CREATE OR REPLACE FUNCTION emit_event() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    cfg      event_table_config%ROWTYPE;
    new_j    jsonb := to_jsonb(NEW);
    old_j    jsonb;
    before_j jsonb := '{}'::jsonb;
    after_j  jsonb := '{}'::jsonb;
    k        text;
    changed  boolean := false;
    v_actor  text;
    v_xact   text;
    v_type   text;
    v_write  bigint;   -- the transaction that made the write, tuple by tuple
BEGIN
    SELECT * INTO cfg FROM event_table_config WHERE table_name = TG_TABLE_NAME;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'emit_event is attached to % with no event_table_config row',
            TG_TABLE_NAME;
    END IF;

    v_actor := nullif(current_setting('app.actor_kind', true), '');
    IF v_actor IS NULL THEN
        RAISE EXCEPTION
            'app.actor_kind is unset: every write declares its actor through set_actor()';
    END IF;
    v_xact := nullif(current_setting('app.actor_xact', true), '');
    IF v_xact IS DISTINCT FROM pg_current_xact_id()::text THEN
        RAISE EXCEPTION
            'actor context belongs to transaction %, not to this one (%): call set_actor() in every transaction that writes',
            coalesce(v_xact, '<none>'), pg_current_xact_id()::text;
    END IF;

    IF TG_OP = 'INSERT' THEN
        v_type  := cfg.created_type;
        after_j := new_j;
        FOREACH k IN ARRAY cfg.redacted_columns LOOP
            IF after_j ? k THEN
                after_j := jsonb_set(after_j, ARRAY[k], '"[redacted]"'::jsonb);
            END IF;
        END LOOP;
        FOREACH k IN ARRAY cfg.ignored_columns LOOP
            after_j := after_j - k;
        END LOOP;
        changed := true;
    ELSE
        v_type := cfg.updated_type;
        IF v_type IS NULL THEN
            RAISE EXCEPTION '% is declared immutable in event_table_config', TG_TABLE_NAME;
        END IF;
        old_j := to_jsonb(OLD);
        FOR k IN SELECT jsonb_object_keys(new_j) LOOP
            CONTINUE WHEN k = ANY (cfg.ignored_columns);
            CONTINUE WHEN new_j -> k IS NOT DISTINCT FROM old_j -> k;
            changed := true;
            IF k = ANY (cfg.redacted_columns) THEN
                before_j := before_j || jsonb_build_object(k, '[redacted]');
                after_j  := after_j  || jsonb_build_object(k, '[redacted]');
            ELSE
                before_j := before_j || jsonb_build_object(k, old_j -> k);
                after_j  := after_j  || jsonb_build_object(k, new_j -> k);
            END IF;
        END LOOP;
    END IF;

    -- D5: every changed column was ignored. Still nothing anyone asking "why
    -- did it think this" would care about, so still no event -- but the
    -- transaction is now on the record, which is what lets the integrity check
    -- tell a deliberate silence from a disabled trigger.
    IF NOT changed THEN
        -- Which transaction made this write is asked of the tuple rather than
        -- of the session, because the two are not always the same id: a
        -- plpgsql `BEGIN ... EXCEPTION` block is a subtransaction, and a row
        -- written inside one carries the subtransaction's id in `xmin` while
        -- `pg_current_xact_id()` still answers with the transaction as a
        -- whole. `promote_proposal` writes every Entity and Relationship
        -- inside such a block, so the id the session reports is the wrong one
        -- for exactly the writes this table exists to account for -- and,
        -- being one id for the whole transaction, it also collapsed two
        -- subtransactions' worth of suppressed writes into a single row that
        -- accounted for the first of them.
        --
        -- Still one row per (program, table, transaction) as 016 wrote it. A
        -- pass that refreshes ten thousand `last_seen_at` values in one
        -- statement still writes one row here; ten thousand exception blocks
        -- are ten thousand transactions as far as every tuple header is
        -- concerned, and one accounting row each is what they are owed.
        EXECUTE format('SELECT r.xmin::text::bigint FROM %I r WHERE r.id = $1', TG_TABLE_NAME)
           INTO v_write USING (new_j ->> 'id')::uuid;
        IF v_write IS NULL THEN
            RAISE EXCEPTION
                'emit_event cannot read back the % row whose write it is accounting for',
                TG_TABLE_NAME;
        END IF;
        INSERT INTO suppressed_writes (program_id, table_name, xact_id)
        VALUES ((new_j ->> 'program_id')::uuid, TG_TABLE_NAME, v_write::text::xid8)
        ON CONFLICT DO NOTHING;
        RETURN NEW;
    END IF;

    INSERT INTO events (
        program_id, type, subject_table, subject_id,
        actor_kind, agent_run_id, task_id, caused_by_event_id, trace_id, payload)
    VALUES (
        (new_j ->> 'program_id')::uuid,
        v_type, TG_TABLE_NAME, (new_j ->> 'id')::uuid,
        v_actor,
        nullif(current_setting('app.agent_run_id',       true), '')::uuid,
        nullif(current_setting('app.task_id',            true), '')::uuid,
        nullif(current_setting('app.caused_by_event_id', true), '')::uuid,
        nullif(current_setting('app.trace_id',           true), ''),
        CASE WHEN TG_OP = 'INSERT'
             THEN jsonb_build_object('after', after_j)
             ELSE jsonb_build_object('before', before_j, 'after', after_j)
        END);

    RETURN NEW;
END $$;



CREATE OR REPLACE FUNCTION check_event_log_integrity(p_program uuid DEFAULT NULL)
RETURNS TABLE (problem text, detail text, count bigint)
LANGUAGE plpgsql AS $$
DECLARE c event_table_config%ROWTYPE;
BEGIN
    RETURN QUERY SELECT * FROM check_event_coverage();

    FOR c IN SELECT * FROM event_table_config LOOP
        RETURN QUERY EXECUTE format($q$
            SELECT 'row_without_event', %L, count(*)::bigint
              FROM %I r
             WHERE (%L::uuid IS NULL OR r.program_id = %L::uuid)
               AND NOT EXISTS (SELECT 1 FROM events e
                                WHERE e.subject_table = %L
                                  AND e.subject_id = r.id
                                  AND e.type = %L)
            HAVING count(*) > 0 $q$,
            c.table_name, c.table_name, p_program, p_program,
            c.table_name, c.created_type);

        RETURN QUERY EXECUTE format($q$
            SELECT 'event_without_row', %L, count(*)::bigint
              FROM events e
             WHERE e.subject_table = %L
               AND (%L::uuid IS NULL OR e.program_id = %L::uuid)
               AND NOT EXISTS (SELECT 1 FROM %I r WHERE r.id = e.subject_id)
            HAVING count(*) > 0 $q$,
            c.table_name, c.table_name, p_program, p_program, c.table_name);

        -- (d) the row's LAST write, not just its first (016).
        RETURN QUERY EXECUTE format($q$
            SELECT 'row_last_write_unaccounted', %L, count(*)::bigint
              FROM %I r
             WHERE (%L::uuid IS NULL OR r.program_id = %L::uuid)
               AND r.xmin::text::bigint <> 2
               AND NOT EXISTS (
                     SELECT 1 FROM events e
                      WHERE e.subject_table = %L AND e.subject_id = r.id
                        AND ((e.xact_id::text::numeric %% 4294967296)::bigint
                                 = r.xmin::text::bigint
                          OR e.xmin::text::bigint = r.xmin::text::bigint))
               AND NOT EXISTS (
                     SELECT 1 FROM suppressed_writes s
                      WHERE s.table_name = %L
                        AND s.program_id = r.program_id
                        AND (s.xact_id::text::numeric %% 4294967296)::bigint
                            = r.xmin::text::bigint)
            HAVING count(*) > 0 $q$,
            c.table_name, c.table_name, p_program, p_program,
            c.table_name, c.table_name);
    END LOOP;

    -- (e) the purge rule (016): a delete action nobody registered.
    RETURN QUERY
    SELECT 'fk_delete_action_not_no_action',
           src.relname || '.' || con.conname, 1::bigint
      FROM pg_constraint con
      JOIN pg_class src ON src.oid = con.conrelid
     WHERE con.contype = 'f'
       AND src.relnamespace = 'public'::regnamespace
       AND con.confdeltype IN ('c','n','d')
       AND NOT EXISTS (
             SELECT 1 FROM purge_cascade_edges e
              WHERE e.table_name  = src.relname
                AND e.column_name = (SELECT a.attname FROM pg_attribute a
                                      WHERE a.attrelid = con.conrelid
                                        AND a.attnum = con.conkey[1]));
END $$;


-- What the replacement is worth, asked of this database: a corpus carrying
-- promotions made before today reads clean under the new comparison, and one
-- that still reports an unaccounted write is reporting something else than the
-- defect above. Vacuous on a fresh database, which is the point -- the case
-- that proves the fix needs a promotion to have happened, so it lives beside
-- the promotions, in `SurfacePromotionTest`, rather than here.
DO $$
DECLARE v_bad bigint;
BEGIN
    SELECT coalesce(sum(count), 0) INTO v_bad FROM check_event_log_integrity()
     WHERE problem = 'row_last_write_unaccounted';
    IF v_bad > 0 THEN
        RAISE EXCEPTION 'the event log still reports % unaccounted write(s): %',
            v_bad,
            (SELECT string_agg(detail || ' x' || count, ', ')
               FROM check_event_log_integrity()
              WHERE problem = 'row_last_write_unaccounted');
    END IF;
END $$;
