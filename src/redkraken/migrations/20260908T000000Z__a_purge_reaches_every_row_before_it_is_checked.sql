-- ===========================================================================
-- Ticket 74 -- a purge reaches every row before it is checked
-- ===========================================================================
-- `DELETE FROM programs` is the only row delete this schema permits, and 016
-- states how it is meant to work: `program_id` cascades, everything else is
-- NO ACTION, and NO ACTION is checked at the end of the statement --
--
--     by which time the program cascade has already removed the referencing
--     rows, so the purge passes.
--
-- "By which time" is the part that is not true by construction. PostgreSQL
-- queues AFTER-row triggers and drains that queue in order: deleting a Program
-- queues the RI trigger of every key that references `programs` (call those
-- generation 1), draining a generation-N event deletes rows and queues the RI
-- triggers of every key that references THAT table (generation N+1), and the
-- queue is FIFO, so every generation N is drained before any generation N+1.
-- A NO ACTION check on `child -> parent` is queued while the parent's rows are
-- being deleted, so it is drained one generation after the parent goes. The
-- child is emptied at its own generation -- the shortest chain of cascades from
-- `programs` that reaches it. So the check passes if and only if
--
--     generation(child) <= generation(parent)
--
-- and when it does not, whether the purge succeeds is decided by the order the
-- catalogue happens to hold two sibling keys in. MEASURED on this server, with
-- four tables and one row each: `p`, two children `a` and `b` cascading from
-- it, and `c` cascading from `b` while naming `a` NO ACTION. `DELETE FROM p`
-- raises 23503 when `a`'s key is the older of the two and succeeds when it is
-- the younger. Nothing about the schema differs between the two runs.
--
-- The corpus was in the failing case in four places, and the harness was
-- carrying a hand-written delete in front of three of them:
--
--   * `finding_hypotheses` -> `hypotheses`, found by `SlateClaimTest` (PH2-71),
--     which is the first case in the suite to write a Finding. Repaired since,
--     by 20260815T120000Z giving the rollup edge a cascade on both ends.
--   * `hypothesis_evidence` -> `proposals`, cleared by `MissionPacketTest`,
--     whose comment claimed a schema intent -- "the hypothesis side cascades
--     and the observation side does not" -- that two migrations had since
--     stopped being true.
--   * `finding_effects` -> `observations` and `finding_chain_step_citations` ->
--     `observations` and `-> receipts`, cleared by `ReportFixture`, whose
--     teardown says what it is doing: "an order PostgreSQL picks".
--
-- And one that no order could save. `interception_cas` (025) registers its
-- `program_id` in `purge_cascade_edges` -- "Purging a program destroys its CA
-- record" -- and then declares the key NO ACTION. No cascade reaches the table
-- at all, so a Program that has ever had a CA minted for it cannot be purged by
-- any statement this schema permits:
--
--     23503: update or delete on table "programs" violates foreign key
--     constraint "interception_cas_program_id_fkey" on table "interception_cas"
--
-- 016's rewrite loop cannot catch that. It strips cascades that no row in the
-- register accounts for; it has nothing to say about a register row that no key
-- accounts for, which is the same lie told the other way round.
--
-- The repair is the shape 016 gave every table that existed then: a table that
-- carries its own `program_id` reaches the purge root directly, and is
-- therefore emptied in generation 1, before any check that any later generation
-- can queue. Three tables added since never got that key, and the CA's key is
-- rewritten to the action its own register row claims. What keeps it is
-- `check_purge_travel()`, which asserts the generation rule over the whole
-- catalogue rather than over the four keys this file touches: 031 already
-- showed that a restore reorders keys, so a corpus that is merely lucky today
-- is a corpus that stops being lucky at the worst moment there is.
-- ---------------------------------------------------------------------------


-- ---------------------------------------------------------------------------
-- 1. The three tables that never reached the root
-- ---------------------------------------------------------------------------
-- Each of these carries `program_id NOT NULL` and reaches it only through the
-- parent that owns it: `finding_effects` and `finding_chain_step_citations`
-- through the Finding and the chain step (034, 040), `hypothesis_evidence`
-- through the Hypothesis (009). That is one generation too late, because each
-- also names an Observation, a Receipt or a Proposal -- all of them generation
-- 1 -- with a key that is deliberately NO ACTION, so that nothing narrower than
-- a purge can take an Observation out from under the row that rests on it.
--
-- Both halves of that are worth keeping, so neither is given up: the NO ACTION
-- keys stay exactly as they are, and the row is brought forward to generation 1
-- instead. `ON DELETE CASCADE` on `program_id` is not a second way for a narrow
-- delete to half-succeed -- the narrow delete it would travel is the delete of
-- a Program, which is the purge itself.
--
-- The corpus states this rule twice and in opposite directions, so this file
-- has to say which one it is following. 016:188 is "every program-scoped table
-- reaches the purge root directly", and its INSERT gave that edge to every
-- table that had a `program_id` when it ran. 017:134, on the tables whose
-- `program_id` its own derive loop had just created, is:
--
--     No `REFERENCES programs(id)` on the derived tables. The composite key to
--     the owner pins the program already, and a second edge would put a
--     sixteenth delete action into the purge graph that `purge_cascade_edges`
--     and check B13 would then have to carry for nothing.
--
-- 016 is the one that is right, and 017's "for nothing" is what this ticket
-- measured and disproved: the composite key to the owner pins the program, but
-- it does not empty the row in time, and the generation the row is emptied in
-- is the whole question. Of the three tables here only `hypothesis_evidence`
-- (007) is 017-derived; `finding_effects` and `finding_chain_step_citations`
-- (034) declared `program_id` themselves and simply never got the root edge
-- 016 would have given them. Read 017:134 as answered here rather than as
-- standing: what makes the answer hold rather than accumulate is
-- `check_purge_travel()` below, which is the sixteenth delete action being
-- carried rather than taken on trust.

ALTER TABLE hypothesis_evidence
    ADD CONSTRAINT hypothesis_evidence_program_id_fkey
    FOREIGN KEY (program_id) REFERENCES programs (id) ON DELETE CASCADE;

ALTER TABLE finding_effects
    ADD CONSTRAINT finding_effects_program_id_fkey
    FOREIGN KEY (program_id) REFERENCES programs (id) ON DELETE CASCADE;

ALTER TABLE finding_chain_step_citations
    ADD CONSTRAINT finding_chain_step_citations_program_id_fkey
    FOREIGN KEY (program_id) REFERENCES programs (id) ON DELETE CASCADE;

INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
    ('hypothesis_evidence',          'program_id', 'program-scoped: the purge root'),
    ('finding_effects',              'program_id', 'program-scoped: the purge root'),
    ('finding_chain_step_citations', 'program_id', 'program-scoped: the purge root');


-- ---------------------------------------------------------------------------
-- 2. The CA record its own register row says the purge destroys
-- ---------------------------------------------------------------------------
-- 025 wrote "NO ACTION, not CASCADE: ticket 12 measured that a cascading delete
-- is a purge nobody recorded. Registered in purge_cascade_edges below instead."
-- The register row is the record, and it is already there. What the NO ACTION
-- bought was not a recorded purge but no purge at all: the key refuses the only
-- delete the schema has, and refuses it for the whole Program rather than for
-- the CA row.

ALTER TABLE interception_cas
    DROP CONSTRAINT interception_cas_program_id_fkey,
    ADD  CONSTRAINT interception_cas_program_id_fkey
         FOREIGN KEY (program_id) REFERENCES programs (id) ON DELETE CASCADE;


-- ---------------------------------------------------------------------------
-- 3. Two register rows that name a key which does not travel
-- ---------------------------------------------------------------------------
-- The register is "every cascade edge the whole-program purge is allowed to
-- travel". A row for a key that cascades nothing is not an edge, and it is
-- worse than absent: it is where the CA hid for six migrations. Both of these
-- tables are purged, and by a key that is registered -- `finding_gate_clearances`
-- through the Finding, `pending_decisions` through its own `program_id` -- so
-- what comes out is the claim, not the cascade.

DELETE FROM purge_cascade_edges
 WHERE (table_name, column_name) IN
       (('finding_gate_clearances', 'program_id'),
        ('pending_decisions',       'test_id'));


-- ---------------------------------------------------------------------------
-- 4. The rule, so the fifth instance cannot ship quietly
-- ---------------------------------------------------------------------------
-- Four arms. (a) and (b) are one sentence read in both directions -- the
-- register and the catalogue say the same thing about what the purge travels --
-- and (b) in particular is 016's rewrite loop said as an invariant rather than
-- performed once: the loop ran in 016 and every migration since has been on its
-- honour. Both use the same three delete actions for "travels", CASCADE, SET
-- NULL and SET DEFAULT, because those are the three that do something to the
-- child row when the parent goes. NO ACTION and RESTRICT are not weaker
-- versions of travelling, they are the refusal to travel, and a register row
-- over a RESTRICT key would be the CA's lie with one more letter in it.
--
-- Arm (c) is the generation rule. It is deliberately conservative: it fails a
-- key whose child is emptied in the same generation as the check that asks
-- about it, even though such a pair succeeds when the two sibling cascades
-- happen to be ordered the right way -- which is what `hypothesis_evidence ->
-- proposals` was living on until this file. 031 rebuilds NO ACTION keys after a
-- restore precisely because that ordering is not stable, so "lucky" and "green"
-- are the same reading and only one of them survives a `pg_restore`.
--
-- Two exclusions, both because something else already answers them:
--
--   * a pair that also carries a cascade key is 017's check (d): the cascade
--     and the check fire on the same parent delete, in trigger-name order, and
--     (d) asserts the cascade is first. That is how every entity detail table
--     is purged -- `applications -> entities` is NO ACTION and CASCADE at once.
--   * a self-referencing key answers itself: all of one table's rows go in the
--     one delete that queues the check, so `interception_cas.superseded_by`
--     finds nothing left to point at.
--
-- A global parent is out of scope on purpose. `receipts -> artifacts` is NO
-- ACTION into a table the purge does not travel at all, which is 12's
-- content-addressed store working as written, not an ordering question.
--
-- Arm (d) is the CA's own defect asked of every table rather than of that one.
-- It is a separate arm because arm (c) structurally cannot see it: (c) compares
-- two generations and `programs` is not program-scoped, so a key straight into
-- the purge root is invisible to it. The failure it names is worse than an
-- ordering, and does not depend on one -- a NO ACTION key into `programs` from
-- a table nothing else empties refuses the delete outright, in every catalogue
-- order there is, for any Program that has a row in it.

CREATE FUNCTION check_purge_travel()
RETURNS TABLE (problem text, subject text, detail text)
LANGUAGE sql STABLE AS $fn$
    WITH RECURSIVE reached(tbl, depth) AS (
            SELECT 'programs'::regclass, 0
        UNION
            -- Every cascade edge, followed one generation at a time. The bound
            -- is the cycle guard: this corpus is three deep and a chain that
            -- needed twelve would be a schema nobody could read.
            SELECT con.conrelid, r.depth + 1
              FROM reached r
              JOIN pg_constraint con
                ON con.confrelid = r.tbl
               AND con.contype = 'f'
               AND con.confdeltype = 'c'
               AND con.conrelid <> r.tbl
             WHERE r.depth < 12
        ),
        purge_depth AS (
            SELECT tbl, min(depth) AS depth FROM reached GROUP BY tbl
        )
    -- (a) the register claims an edge no key travels.
    SELECT 'registered_edge_does_not_travel'::text,
           e.table_name || '.' || e.column_name,
           'purge_cascade_edges says the purge travels this column and no '
           'foreign key on it has an ON DELETE action, so the rationale is a '
           'statement about a cascade that does not exist'
      FROM purge_cascade_edges e
      JOIN pg_class src ON src.relname = e.table_name
                       AND src.relnamespace = 'public'::regnamespace
     WHERE NOT EXISTS (
             SELECT 1 FROM pg_constraint con
              WHERE con.conrelid = src.oid AND con.contype = 'f'
                AND con.confdeltype IN ('c', 'n', 'd')
                AND (SELECT a.attname FROM pg_attribute a
                      WHERE a.attrelid = con.conrelid AND a.attnum = con.conkey[1])
                    = e.column_name)
  UNION ALL
    -- (b) a key travels and the register does not know about it.
    SELECT 'cascade_travels_unregistered',
           src.relname || '.' || con.conname,
           'ON DELETE ' || CASE con.confdeltype WHEN 'c' THEN 'CASCADE'
                                                WHEN 'n' THEN 'SET NULL'
                                                ELSE 'SET DEFAULT' END
                        || ' with no row in purge_cascade_edges; 016 rewrote '
                           'every unregistered one to NO ACTION and this is '
                           'that loop as a standing question'
      FROM pg_constraint con
      JOIN pg_class src ON src.oid = con.conrelid
     WHERE con.contype = 'f'
       AND con.confdeltype IN ('c', 'n', 'd')
       AND src.relnamespace = 'public'::regnamespace
       AND NOT EXISTS (
             SELECT 1 FROM purge_cascade_edges e
              WHERE e.table_name = src.relname
                AND e.column_name = (SELECT a.attname FROM pg_attribute a
                                      WHERE a.attrelid = con.conrelid
                                        AND a.attnum = con.conkey[1]))
  UNION ALL
    -- (c) the check is drained before the delete that answers it.
    SELECT 'check_precedes_the_delete_that_answers_it',
           src.relname || '.' || con.conname || ' -> ' || tgt.relname,
           'the parent is emptied in generation '
                || coalesce(dp.depth::text, 'none')
                || ' and the child in generation '
                || coalesce(dc.depth::text, 'none')
                || ', so this NO ACTION check is queued before the cascade that '
                   'would satisfy it and the purge succeeds only while the two '
                   'sibling keys happen to be in the right order'
      FROM pg_constraint con
      JOIN pg_class src ON src.oid = con.conrelid
      JOIN pg_class tgt ON tgt.oid = con.confrelid
      LEFT JOIN purge_depth dc ON dc.tbl = con.conrelid
      LEFT JOIN purge_depth dp ON dp.tbl = con.confrelid
     WHERE con.contype = 'f'
       AND con.confdeltype IN ('a', 'r')
       AND src.relnamespace = 'public'::regnamespace
       AND tgt.relnamespace = 'public'::regnamespace
       AND is_program_scoped(src.oid::regclass)
       AND is_program_scoped(tgt.oid::regclass)
       AND con.conrelid <> con.confrelid
       AND coalesce(dc.depth, 99) > coalesce(dp.depth, 99)
       AND NOT EXISTS (
             SELECT 1 FROM pg_constraint sib
              WHERE sib.contype = 'f' AND sib.confdeltype = 'c'
                AND sib.conrelid = con.conrelid
                AND sib.confrelid = con.confrelid)
  UNION ALL
    -- (d) a key into the purge root that the purge root's own delete cannot
    --     satisfy. Not an ordering: nothing empties the table, so there is no
    --     order in which this passes.
    SELECT 'root_key_blocks_the_purge',
           src.relname || '.' || con.conname,
           'this key names programs ON DELETE '
                || CASE con.confdeltype WHEN 'r' THEN 'RESTRICT'
                                        ELSE 'NO ACTION' END
                || ' and no cascade reaches the table, so DELETE FROM programs '
                   'is refused for any Program holding a row here'
      FROM pg_constraint con
      JOIN pg_class src ON src.oid = con.conrelid
     WHERE con.contype = 'f'
       AND con.confrelid = 'programs'::regclass
       AND con.conrelid <> con.confrelid
       AND con.confdeltype IN ('a', 'r')
       AND src.relnamespace = 'public'::regnamespace
       AND NOT EXISTS (SELECT 1 FROM purge_depth d WHERE d.tbl = con.conrelid)
$fn$;

REVOKE ALL ON FUNCTION check_purge_travel() FROM PUBLIC;

COMMENT ON FUNCTION check_purge_travel() IS
    'ticket 74: the whole-program purge reaches every row it has to reach, and '
    'reaches it before the NO ACTION check that asks about it. Answers the '
    'question 016 left to the order the catalogue was written in.';

INSERT INTO standing_checks(name, query, owner_ticket, note) VALUES
    ('purge_travel', 'SELECT * FROM check_purge_travel()', '74',
     'the register and the catalogue say the same thing about what the purge '
     'travels, no NO ACTION check is drained before the cascade that answers '
     'it, and no key into programs refuses the purge outright');


-- ---------------------------------------------------------------------------
-- 5. What has to hold the moment this file is applied
-- ---------------------------------------------------------------------------

DO $$
DECLARE n int; d text;
BEGIN
    SELECT count(*), string_agg(problem || ' ' || subject || ': ' || detail, '; ')
      INTO n, d FROM check_purge_travel();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-74 refuses to finish: % purge problem(s): %', n, d;
    END IF;

    -- The four keys above are new or rebuilt, so they hold the highest OIDs in
    -- the database and sort last among the RI triggers on their parents. That
    -- is the direction 031 rebuilds in, and 017's check (d) is what says so.
    SELECT count(*), string_agg(child || ' -> ' || parent, '; ')
      INTO n, d FROM fk_fire_order_violations();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-74 leaves % pair(s) firing in the wrong order: %', n, d;
    END IF;

    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_program_isolation();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-74 breaks program isolation (% problems): %', n, d;
    END IF;

END $$;
