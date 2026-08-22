-- ---------------------------------------------------------------------------
-- 20261006T000000Z__a_do_not_send_list_is_written_and_a_redaction_verifier_is_not.sql
--                                                                  (ticket 125)
--
-- Ticket 125 was cut over two tables that record why something must be held
-- back: `program_known_issues` (`0034_reports.sql:351`), which refuses a
-- report, and `redaction_failure` (`0024_secret_keying.sql:143`), which was to
-- record a redaction that did not hold. Neither had a writer. They get opposite
-- answers, and this file is the second half of the first answer and the whole
-- of the second.
--
-- THE DO-NOT-SEND LIST GETS A WRITER, AND IT IS THE CONFIGURATION DOCUMENT.
-- `0034:1073` registered the table as `reference` with the rationale "the
-- program's published do-not-send list, entered by the operator through the
-- control surface", and then no control surface entered one, so five columns
-- sat on the agent's read surface and all five were always NULL. The `source`
-- CHECK (`0034:356`) names three origins and two of them are the operator's:
-- `program_policy` is the published list transcribed and `operator` is their
-- own addition. Both are declarations, and this harness already has one place
-- an operator declares things -- the configuration `program.py` compiles, which
-- projects `identity`, `required_header` and `callback` the same way. So
-- `config._known_issue` reads the entry and `program._project_known_issues`
-- inserts what is new, updates what changed and deletes what the document
-- stopped naming. The third origin, `prior_submission`, is a runtime write that
-- happens after a report has gone out, and nothing in this tree sends one yet.
--
-- Nothing in the schema had to move for that. `rk2_runtime` already holds
-- SELECT, INSERT, UPDATE and DELETE on the table -- four `66-seed` rows in
-- `runtime_table_surface` -- and its row-level policy admits the runtime
-- unconditionally, so the writer had a door the whole time and no ticket had
-- walked through it. What was wrong was one sentence: a register that goes on
-- naming a control surface nobody built is a register that will send the next
-- reader looking for one. Section 1 replaces it, and section 4 asserts the
-- privileges the new writer depends on rather than trusting that they are
-- still there.
--
-- The gate itself is untouched, because it was never the missing part.
-- `report_blockers` already returns `'hard', 'known_issue'` joined on
-- `class_id` and `entity_like` (`0034:815-825`) and `0034:992` refuses on every
-- hard blocker, so the last thing ticket 125 asked for -- a Finding whose class
-- and entity match a known issue is refused rather than annotated -- is
-- enforced by a function that has always worked and never had a row to work on.
-- `rk finding clear-gate` (`cli.py`) has shipped since ticket 59 to let an
-- operator overrule this one gate; until now it could lift a gate that could
-- not be raised.
--
-- `redaction_failure` IS RETIRED, AND THIS IS THE ARGUMENT SO THAT THE NEXT
-- AUDIT DOES NOT RE-ADD IT. The table's own comment (`0024:139-141`) promises
-- two things: "A redaction that fails open is worse than none, so the
-- projection is withheld and the failure is a row here, not a log line." Both
-- were reconsidered, in prose, by the code that ended up doing the redaction.
--
--   * THE WITHHOLDING WAS REJECTED EXPLICITLY. `project_identity_response`
--     (`proxy.py`) opens with "Redaction and not suppression" and gives the
--     reason: withholding an exchange whole "would cite nothing and would make
--     an authenticated exchange -- the one an access control finding is made of
--     -- an exchange whose answer nobody may read." The compensating control is
--     named in the same docstring and it shipped: the Agent view and the wire
--     view are hashed separately and the difference is sealed, so an exchange
--     whose redaction was incomplete is one an auditor can still see whole.
--
--   * AND THE ROW CANNOT BE WRITTEN BY AN HONEST IMPLEMENTATION. The columns
--     say what would write it: `rule_id` is "which verifier tripped" and
--     `encoding_path` is "'raw', 'urldecode', 'base64>urldecode', ..."
--     (`0024:147-148`) -- a second pass re-scanning the redacted bytes through
--     each encoding for what should have gone. That vocabulary now lives in the
--     scrubber instead. `_renderings` (`proxy.py`) expands every injected
--     secret into eight spellings -- raw, percent-encoded, four base64 variants
--     and two hex cases -- and each one is replaced in the body and dropped
--     from the headers, on the response and, since ticket 96, on the request.
--     A verifier searching those same eight finds nothing by construction, and
--     a verifier searching for a ninth would be a better detector than the
--     scrubber, in which case it belongs IN the scrubber. Any detector good
--     enough to write the row is good enough to prevent it.
--
-- What the scrubber does not catch it says it does not catch, in the same
-- docstring: a target may transform a value beyond any spelling `_renderings`
-- knows -- "a hash, a truncation, half a value on each side of a template" --
-- and that "is not recoverable by search and is not pretended to be". That is a
-- stated residual risk with a stated control, not a missing writer. The rule
-- this schema now holds is one sentence: THE HARNESS REDACTS AND RECORDS; IT
-- DOES NOT VERIFY AND WITHHOLD, AND THE SEALED WIRE VIEW IS WHERE AN INCOMPLETE
-- REDACTION STAYS VISIBLE.
--
-- WHAT WOULD HAVE TO CHANGE BEFORE THE TABLE COMES BACK. Two things, and the
-- first is not a detector:
--
--   1. the withholding decision would have to be reversed -- somebody would
--      have to argue that an exchange nobody may read is worth more than an
--      access-control finding, against `project_identity_response`'s reasons
--      and against the seal that answers them;
--   2. a detector would have to exist that finds a spelling `_renderings`
--      cannot produce AND that cannot be moved into `_renderings`. A hash of a
--      secret is the candidate: it is not recoverable by search, but it is also
--      not findable by a verifier, which is why the residual risk is stated
--      rather than instrumented.
--
-- Until both, a row in this table would be a row the harness cannot honestly
-- write, and an empty audit table is read by the next reader as a hole rather
-- than as a decision. That is what this file replaces.
--
-- Depends on 0024 (the table, its artifact foreign key), 0030 (the three
-- register rows it was given), 20260909T000000Z (the four
-- `runtime_table_surface` rows 029's snapshot grant produced) and 0034 (the
-- do-not-send list, its blocker and its register sentence). Nothing else moves:
-- no constraint is redefined, no closed set is widened, and the only column
-- comment in play is the one on a table that ceases to exist.
-- ---------------------------------------------------------------------------


SET client_min_messages = notice;


-- ===========================================================================
-- 1. The do-not-send list names the writer it actually has
-- ===========================================================================

-- `reference` is still the right kind and is left alone: the rows are the
-- operator's policy rather than the harness's epistemic state, so an event
-- about one would put a declaration in the log the loop is judged from. What
-- changes is the sentence, which sent a reader looking for a console. The
-- writer is named the way the other registry rows name theirs -- by the thing a
-- reader greps for next -- and the ticket that built it owns the row.
UPDATE event_table_exempt
   SET reason = 'the program''s published do-not-send list, declared in the operator''s '
                'configuration document and projected by program._project_known_issues; '
                'program_policy and operator are the document''s two origins and '
                'prior_submission is the harness''s own record of a report already sent',
       owner_ticket = '125'
 WHERE table_name = 'program_known_issues';


-- ===========================================================================
-- 2. The table the redaction verifier would have written
-- ===========================================================================

-- A plain `DROP TABLE`, which raises if the table is not there, so no CASCADE
-- and no `IF EXISTS`: this file's claim is that a known relation goes, not that
-- one might. `redaction_failure_sha_fk` (`0024:170-171`) is the table's own
-- foreign key onto `artifacts` and goes with it; nothing points the other way,
-- which is the shape ticket 125 measured -- no writer, no reader, no inbound
-- foreign key.
DROP TABLE redaction_failure;


-- ===========================================================================
-- 3. The registry rows, all three registers that named it
-- ===========================================================================

-- A dropped table that keeps its register rows is worse than one that never had
-- them: `check_event_coverage()` answers with `exempt_row_missing_table` and
-- `check_runtime_privileges()` with `runtime_table_surface_names_missing_object`,
-- so this is the difference between the migration applying and the standing
-- checks failing at the end of the run that applied it. Each count is asserted,
-- because a name that matched nothing would delete nothing and let this file
-- declare itself finished.
DO $$
DECLARE n integer;
BEGIN
    -- (a) emission. `0030:130` classified it `audit`: "a redaction that did not
    -- hold; the row is the record and must not be re-emitted into a readable
    -- table". The classification was right about a row this harness will never
    -- write.
    DELETE FROM event_table_exempt WHERE table_name = 'redaction_failure';
    GET DIAGNOSTICS n = ROW_COUNT;
    IF n <> 1 THEN
        RAISE EXCEPTION 'ticket 125: deleted % event_table_exempt row(s), expected 1', n;
    END IF;

    -- (b) the purge graph. `0030:526-527` registered the `ON DELETE SET NULL`
    -- on `artifact_sha` -- "the artifact may go, the record that a redaction
    -- did not hold may not". `check_purge_travel()` joins the register to
    -- `pg_class` and so cannot see a row for a table that no longer exists,
    -- which is exactly why it is deleted here by hand: a stale row would be
    -- invisible to the check that keeps the register honest.
    DELETE FROM purge_cascade_edges WHERE table_name = 'redaction_failure';
    GET DIAGNOSTICS n = ROW_COUNT;
    IF n <> 1 THEN
        RAISE EXCEPTION 'ticket 125: deleted % purge_cascade_edges row(s), expected 1', n;
    END IF;

    -- (c) program isolation. `0030:504` declared it global, on the ground that
    -- it names an artifact sha and "the row must survive a program purge".
    DELETE FROM program_global_tables WHERE table_name = 'redaction_failure';
    GET DIAGNOSTICS n = ROW_COUNT;
    IF n <> 1 THEN
        RAISE EXCEPTION 'ticket 125: deleted % program_global_tables row(s), expected 1', n;
    END IF;

    -- (d) the runtime's table surface. Four rows, one per privilege, all
    -- stamped `66-seed`: 024 sorts before 029, so this table was already there
    -- when 029 took its snapshot -- `GRANT SELECT, INSERT, UPDATE, DELETE ON
    -- ALL TABLES IN SCHEMA public` -- rather than arriving under the default
    -- privileges the same file set as the standing rule for everything created
    -- after it, and 066's seed read the catalogue and recorded what was held
    -- either way. The runtime never called any of it, because there was nothing
    -- to call.
    DELETE FROM runtime_table_surface WHERE table_name = 'redaction_failure';
    GET DIAGNOSTICS n = ROW_COUNT;
    IF n <> 4 THEN
        RAISE EXCEPTION 'ticket 125: deleted % runtime_table_surface row(s), expected 4', n;
    END IF;
END $$;

-- No `runtime_verb_surface` row is deleted and no grant is issued, so the house
-- rule that a GRANT declares a verb and a REVOKE deletes it has nothing to
-- match: this file grants nothing and revokes nothing. The table surface above
-- is the other register and it is emptied of the relation that is gone.


-- ===========================================================================
-- 4. What this migration claims, asserted
-- ===========================================================================

-- Two claims, one per half.
--
-- The retirement claim is not "a table was dropped" -- `DROP TABLE` already
-- raises if it is absent. It is that `redaction_failure` leaves NOTHING behind:
-- no relation, no constraint naming it, and no row in any of the five registers
-- that a later reader could take for a hole where a subsystem used to be.
--
-- The writer's claim is the opposite shape: the do-not-send list is now
-- written, so the things the writer depends on have to be true here rather than
-- discovered at the first `rk run`. Those are the four privileges, the
-- row-level policy that admits the runtime, and the blocker that makes a row
-- worth writing at all. `report_blockers` is asked for its definition rather
-- than exercised: exercising it needs a Program, an Entity and a Finding, and a
-- migration that manufactured three of those to prove a join would be leaving
-- the rows behind as the price of the proof.
DO $$
DECLARE
    v_left text;
    v_n    integer;
BEGIN
    IF to_regclass('public.redaction_failure') IS NOT NULL THEN
        RAISE EXCEPTION 'ticket 125: redaction_failure survives its own retirement'
          USING ERRCODE = '23514';
    END IF;

    SELECT count(*) INTO v_n FROM (
        SELECT table_name FROM event_table_exempt
        UNION ALL SELECT table_name FROM event_table_config
        UNION ALL SELECT table_name FROM purge_cascade_edges
        UNION ALL SELECT table_name FROM runtime_table_surface
        UNION ALL SELECT table_name FROM state_read_surface
        UNION ALL SELECT table_name FROM program_global_tables
    ) r WHERE r.table_name = 'redaction_failure';
    IF v_n <> 0 THEN
        RAISE EXCEPTION 'ticket 125: % register row(s) still name redaction_failure', v_n
          USING ERRCODE = '23514';
    END IF;

    -- The four privileges the projection needs, asked of the catalogue and of
    -- the register together. Either one alone would pass on a database where
    -- the other had drifted, and `apply_runtime_grants()` reads the register.
    SELECT string_agg(p.privilege, ', ' ORDER BY p.privilege) INTO v_left
      FROM (VALUES ('SELECT'),('INSERT'),('UPDATE'),('DELETE')) AS p(privilege)
     WHERE NOT has_table_privilege('rk2_runtime', 'program_known_issues', p.privilege)
        OR NOT EXISTS (SELECT 1 FROM runtime_table_surface s
                        WHERE s.table_name = 'program_known_issues'
                          AND s.privilege = p.privilege);
    IF v_left IS NOT NULL THEN
        RAISE EXCEPTION
            'ticket 125: rk2_runtime cannot project the do-not-send list; missing %', v_left
          USING DETAIL = 'program._project_known_issues inserts, updates and deletes these rows',
                ERRCODE = '42501';
    END IF;

    -- And the policy, because a grant without a policy is a writer whose rows
    -- row-level security silently discards.
    IF NOT EXISTS (
        SELECT 1 FROM pg_policy
         WHERE polrelid = 'program_known_issues'::regclass
           AND polname = 'program_known_issues_rk2_runtime') THEN
        RAISE EXCEPTION 'ticket 125: no row-level policy admits rk2_runtime to the do-not-send list'
          USING ERRCODE = '42501';
    END IF;

    -- The gate the rows exist to raise. Both halves of the join, because a
    -- blocker matched on the class alone would refuse every Finding of a class
    -- one instance of which the program knows about.
    IF NOT EXISTS (
        SELECT 1 FROM pg_proc
         WHERE proname = 'report_blockers'
           AND prosrc LIKE '%known_issue%'
           AND prosrc LIKE '%k.class_id = f.class_id%'
           AND prosrc LIKE '%e.dedup_key LIKE k.entity_like%') THEN
        RAISE EXCEPTION
            'ticket 125: report_blockers no longer refuses on the do-not-send list, so the '
            'rows this ticket taught the runtime to write block nothing'
          USING ERRCODE = '23514';
    END IF;

    -- The register sentence section 1 rewrote, asked back. A reader who greps
    -- `program_known_issues` has to reach the writer rather than a console.
    IF NOT EXISTS (
        SELECT 1 FROM event_table_exempt
         WHERE table_name = 'program_known_issues'
           AND exempt_kind = 'reference'
           AND reason LIKE '%project_known_issues%') THEN
        RAISE EXCEPTION 'ticket 125: the register still does not name the list''s writer'
          USING ERRCODE = '23514';
    END IF;
END $$;
