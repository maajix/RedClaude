-- ---------------------------------------------------------------------------
-- 20260819T000000Z__a_chain_unlock_earns_its_place_in_the_queue.sql  (41)
-- ---------------------------------------------------------------------------
--
-- 040 ends at "here is a graph, and here is whether it still holds". 026 ends at
-- "a Task is worth the pending Tasks a sound edge says it unblocks", and its own
-- comment on `tasks.unlock_value` names what it left out: "Direct unlock only:
-- what a Task adds over the unlocks already coming is ticket 41." This file is
-- the join between those two sentences.
--
-- The object of the derivation needs saying first, because the ticket's phrase
-- -- "missing requirements on sound kill-chain paths" -- reads at a glance like
-- something a sound chain has, and a sound chain has none. `rk2_chain_problem`
-- refuses `step L requires N, and no step provides it and the Program does not
-- start with it` before a chain can be built at all. So the missing requirement
-- is never inside the chain: it is the gap between what a sound chain has
-- obtained and what a pivot stamp OUTSIDE that chain needs before it could join.
-- That gap is the frontier, and closing one capability of it is a piece of work
-- somebody could be doing instead of something else. Which is a Task.
--
-- Six criteria, and where each of them lives:
--
--   1. derived only from sound chain requirements and current Surface subjects
--      -- section 2, which starts from `rk2_chain_unsoundness(...) IS NULL` and
--      joins `entities.in_scope`, and section 4, which creates the Task.
--   2. records the members and capabilities it would unlock, claiming nothing
--      -- section 3's table, which has no probability column and no verdict.
--   3. marginal, counting only newly reachable paths, no double counting
--      -- section 2's `cardinality(missing) = 1` and section 5's DISTINCT and
--      equal share.
--   4. invalidation removes the contribution on the next pass
--      -- section 4's withdrawal, which is the complement of the frontier.
--   5. value, probability, cost and safety still constrain; unlock cannot
--      bypass eligibility or the Rules of Engagement -- section 6, which leaves
--      the formula's shape alone.
--   6. fixtures -- tests/test_database.py.


-- ===========================================================================
-- 1. What a chain has already obtained
-- ===========================================================================
--
-- The entry set it started from and every capability its steps went on to
-- provide. Read off the stored `entry` rather than off `rk2_chain_entry(program)`
-- because the question is what THIS chain has, and the two are the same question
-- only for a sound chain -- 040's arm (b) is precisely the check that they still
-- agree, and section 2 asks for soundness before it asks for this.

CREATE FUNCTION rk2_chain_capabilities(p_chain uuid) RETURNS text[]
LANGUAGE sql STABLE AS $fn$
    SELECT ARRAY(SELECT k FROM (
                   SELECT unnest(c.entry) AS k
                    UNION
                   SELECT s.provides
                     FROM chain_steps cs
                     JOIN pivot_stamps s
                       ON s.id = cs.stamp_id AND s.program_id = cs.program_id
                    WHERE cs.chain_id = c.id) u
                  ORDER BY k)
      FROM chains c
     WHERE c.id = p_chain
$fn$;

COMMENT ON FUNCTION rk2_chain_capabilities(uuid) IS
  'Every capability a chain holds: the entry set it started from and what each of its steps provided, deduplicated and sorted. The left-hand side of every gap the frontier reports.';


-- ===========================================================================
-- 2. The frontier -- a missing requirement, and the Test that claims to close it
-- ===========================================================================
--
-- One row per (sound chain, missing capability, stamp that would become
-- reachable, Test that claims to provide it). Three of its predicates are the
-- whole of criteria 1 and 3 and are worth reading one at a time.
--
-- `cardinality(missing) = 1` is what makes the unlock MARGINAL rather than
-- aspirational. A stamp two capabilities short of joining this chain does not
-- become reachable when one of them arrives, and crediting the Task that
-- supplies one of two with the whole member would pay twice for a member
-- neither of them reaches. Exactly one missing means: obtain this, and that
-- member joins. Nothing weaker is a claim about what this Task adds.
--
-- The lookahead is one hop, deliberately. If the missing capability arrives, the
-- stamp joins, the chain then holds what that stamp provides, and a further
-- stamp may become reachable in turn -- and none of that is reachable until the
-- first hop has been DEMONSTRATED, which is work this Task has not done. A
-- transitive closure here would credit one Task with the value of a path whose
-- every later step is somebody else's Task, and the credit would compound with
-- the depth of the graph rather than with anything the Task is worth. The second
-- hop is not lost: it becomes the frontier of the next pass, once the stamp
-- exists.
--
-- `NOT EXISTS (... pivot_stamps ... test_id = t.id)` is the difference between
-- work and a memory of work. A Test that has already been stamped demonstrated
-- its pivot; running it again obtains nothing that is not already obtained, and
-- a frontier that offered it would offer the same Task forever.
--
-- `standing` is the same question 040 asks about a chain, asked about the one
-- stamp the chain does not have yet. Both halves of criterion 4 need it: the
-- chain is sound and the thing it is waiting for may not be, because rejecting a
-- Finding leaves its stamp row exactly where it was and that stamp is nobody's
-- step. Everything below therefore reads a stamp that 039 would still issue
-- today, under the scope document the Program is at now.
--
-- `e.in_scope` and `h.superseded_by IS NULL` are criterion 1's "current Surface
-- subjects" and criterion 5's Rules of Engagement, applied where the candidate is
-- born rather than only where it is cancelled. `cancel_reason_for` would abandon
-- both on the next pass anyway; deriving them and abandoning them would be a
-- Task created so that the pass after could throw it away.
--
-- What this reads that a model wrote: `tests.spec -> 'pivot' ->> 'provides'`,
-- through the generated `pivot_provides` column. That is the one model-authored
-- input, and it is a claim about what a Test WOULD obtain, recorded on the
-- unlock row so an operator can see who claimed it. Everything the unlock is
-- WORTH is read from rows a model cannot write: the stamps, which 039 issues
-- from a demonstrated transition, and the chains, which 040 builds and which
-- this function will not look at unless they are still sound.

CREATE FUNCTION rk2_chain_unlock_frontier(p_program uuid)
RETURNS TABLE (chain_id uuid, capability text, stamp_id uuid, finding_id uuid,
               hypothesis_id uuid, subject_entity_id uuid)
LANGUAGE sql STABLE AS $fn$
    WITH here AS (
        SELECT pr.scope_version FROM programs pr WHERE pr.id = p_program
    ), standing AS (
        -- The stamp that would JOIN, asked what 040 asks of the stamps a chain
        -- already HAS. Without this the frontier reads `pivot_stamps` and
        -- nothing else, and a member somebody rejected keeps paying: rejecting
        -- a Finding does not move the stamp row, and the stamp is not a step of
        -- the chain that is waiting for it, so the chain stays sound while the
        -- thing it is waiting for has stopped being one. That is criterion 4's
        -- "member" and "pivot" in a single call to 039's own sentence, with no
        -- second wording of either that could drift from it.
        --
        -- Once per stamp rather than once per (chain, stamp): the question is
        -- about the stamp and the answer does not change with which chain is
        -- asking, and `rk2_pivot_refusal` is a dozen lookups deep.
        --
        -- The scope comparison is criterion 4's third word, and it is the one
        -- clause in this file that restates a sentence rather than asking it.
        -- 040 arm (d) holds a chain unsound when a STEP was obtained under a
        -- scope document the Program has since replaced; there is no function
        -- that asks it of a stamp which is not yet a step, and paying now for a
        -- member that could only ever arrive unsound is paying for a path
        -- nobody will be allowed to walk. Guarded on NULL for 040's reason: a
        -- Program with no version has not replaced anything.
        SELECT z.id, z.finding_id, z.requires
          FROM pivot_stamps z CROSS JOIN here
         WHERE z.program_id = p_program
           AND (here.scope_version IS NULL OR z.scope_version = here.scope_version)
           AND rk2_pivot_refusal(p_program, z.tool_run_id) IS NULL
    ), sound AS (
        SELECT c.id, rk2_chain_capabilities(c.id) AS have
          FROM chains c
         WHERE c.program_id = p_program
           AND rk2_chain_unsoundness(p_program, c.id) IS NULL
    ), gap AS (
        SELECT sc.id AS chain_id, z.id AS stamp_id, z.finding_id,
               ARRAY(SELECT unnest(z.requires)
                     EXCEPT
                     SELECT unnest(sc.have)) AS missing
          FROM sound sc
          CROSS JOIN standing z
         WHERE NOT EXISTS (SELECT 1 FROM chain_steps cs
                            WHERE cs.chain_id = sc.id AND cs.stamp_id = z.id)
    ), one_short AS (
        -- The cardinality test lives here rather than in the WHERE below so
        -- that `missing[1]` is read only where the array has exactly one
        -- element. `EXCEPT` promises no order, and an expression whose meaning
        -- depends on which element came first would be one nobody could reason
        -- about from the text.
        SELECT g.chain_id, g.stamp_id, g.finding_id, g.missing[1] AS capability
          FROM gap g WHERE cardinality(g.missing) = 1
    )
    -- DISTINCT because the Test is not among the columns: two Tests of one
    -- hypothesis both claiming the capability are two ways to ask the same
    -- question, and the Task the derivation mints is the hypothesis's. Without
    -- it the second row would be an ON CONFLICT DO NOTHING away from mattering.
    SELECT DISTINCT g.chain_id, g.capability, g.stamp_id, g.finding_id,
           t.hypothesis_id, h.subject_entity_id
      FROM one_short g
      JOIN tests t      ON t.program_id = p_program
                       AND t.pivot_provides = g.capability
      JOIN hypotheses h ON h.id = t.hypothesis_id
      JOIN entities e   ON e.id = h.subject_entity_id
     WHERE h.superseded_by IS NULL
       AND e.in_scope
       AND NOT EXISTS (SELECT 1 FROM pivot_stamps s2
                        WHERE s2.program_id = p_program AND s2.test_id = t.id)
$fn$;

COMMENT ON FUNCTION rk2_chain_unlock_frontier(uuid) IS
  'Ticket 41 criteria 1 and 3: every capability exactly one of which a sound chain is short of a stamp it does not yet contain, paired with an unstamped Test claiming to provide it on a subject still on the Surface. One hop, because a second hop is not reachable until the first has been demonstrated.';

-- The join key section 2 made real. `pivot_provides` was a column 039 wrote so a
-- standing check could ask about it; it is now the right-hand side of a join run
-- once per Ranking pass over every stamp of the Program.
CREATE INDEX tests_pivot_provides_idx ON tests (program_id, pivot_provides)
    WHERE pivot_provides IS NOT NULL;


-- ===========================================================================
-- 3. The record -- what a candidate Task would unlock, and nothing else
-- ===========================================================================
--
-- Criterion 2 in one table. Four columns are the claim -- this Task, that chain,
-- this capability, that member -- and the columns that are ABSENT are the other
-- half of the criterion: there is no probability here, no expected value, no
-- verdict and no "would succeed" flag, so the row cannot be read as a prediction
-- however hard anybody squints at it. It says what becomes reachable if the
-- capability arrives. Whether it arrives is what running the Task finds out.
--
-- No `basis` column, and that is a decision rather than an omission. 026 needed
-- one because two kinds of edge compete for the same slot -- a model's opinion
-- and a derived rule -- and the vocabulary is what keeps the opinion worth zero.
-- Here there is only one kind of row: the derivation writes all of them from
-- sound chains, and a model has no way to state a chain unlock at all. A
-- vocabulary with one value in it would be the join in `chain_unlock_for` with
-- extra steps, and section 7 asks the question that vocabulary would have
-- answered -- is every stored row still one the frontier produces -- directly.

CREATE TABLE task_chain_unlocks (
    id         uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    -- the candidate Task: the work that would obtain the capability
    task_id    uuid NOT NULL,
    -- the sound chain that is short of it
    chain_id   uuid NOT NULL,
    capability text NOT NULL REFERENCES capabilities(capability),
    -- the member that would become reachable, and the Finding it is about
    stamp_id   uuid NOT NULL,
    finding_id uuid NOT NULL,
    derived_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (task_id, chain_id, capability, stamp_id),
    -- No delete action on any of the four, which is 026's reading of 016's purge
    -- rule: the only edge that may cascade is the one to the purge root, and it
    -- is the one registered below. A row that cascaded from a Task or a chain
    -- would be a second way for rows to leave a Program.
    FOREIGN KEY (task_id, program_id)    REFERENCES tasks (id, program_id),
    FOREIGN KEY (chain_id, program_id)   REFERENCES chains (id, program_id),
    FOREIGN KEY (stamp_id, program_id)   REFERENCES pivot_stamps (id, program_id),
    FOREIGN KEY (finding_id, program_id) REFERENCES findings (id, program_id)
);

COMMENT ON TABLE task_chain_unlocks IS
  'One row per claim that finishing one Task would obtain a capability a sound chain is one requirement short of, and so bring one more stamped member within reach. Records what would become reachable and never that it will: there is no probability, no expected value and no verdict on this table.';

COMMENT ON COLUMN task_chain_unlocks.capability IS
  'The missing requirement. Read from the pivot claim of a Test of the Task''s own hypothesis, which is the one model-authored input to the derivation -- kept on the row so an operator can see what was claimed, rather than only what it was worth.';

COMMENT ON COLUMN task_chain_unlocks.finding_id IS
  'The member''s Finding, which is the unit criterion 3 counts. Two stamps of one Finding, or one Finding reachable through two chains, are one thing becoming reachable and are counted once.';

CREATE INDEX task_chain_unlocks_finding_idx
    ON task_chain_unlocks (program_id, finding_id);

INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
    ('task_chain_unlocks', 'derived',
     'recomputed from the sound chains, the stamps and the Tests by every Ranking pass; scheduler.ranked records what they produced', '41');

INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
    ('task_chain_unlocks', 'program_id', 'program-scoped: the purge root');

GRANT SELECT, INSERT, DELETE ON task_chain_unlocks TO rk2_runtime;
GRANT SELECT ON task_chain_unlocks TO rk2_human;
REVOKE UPDATE ON TABLE task_chain_unlocks FROM rk2_runtime;
REVOKE ALL ON TABLE task_chain_unlocks FROM rk2_proxy, rk2_state;

-- The grant above hands the whole of criterion 1 to whatever holds the runtime
-- connection unless something narrows it: one INSERT here buys a Task the value
-- of any member somebody names, and one DELETE takes a real one away. 026 met
-- the same exposure by making a sound `basis` the derivation's to write; this
-- table has no basis column because every row is derived, so the rule is the
-- simpler one -- every row is the derivation's to write.
--
-- Transaction-local and its own setting rather than 026's, because the licence
-- belongs to a step and not to a role: `derive_task_dependencies` has no
-- business writing chain unlocks, and one shared flag would give it that.
--
-- The body is 026's guard less one arm, and the missing arm is why there is a
-- second function rather than one taking the setting name as a trigger argument.
-- 026 guards the rows whose `basis` is `runtime_rule` and lets every other row
-- through, because a caller recording a claim of its own is what `proposed` is
-- for. Here every row is the derivation's, so there is no column to read and no
-- row to let through. A shared guard would have to take the predicate as well as
-- the setting, and a predicate over NEW and OLD passed as text is dynamic SQL in
-- a trigger on the table whose whole point is that nothing else writes it.
--
-- DELETE consults `app.purging` for the reason 026 does: a program-scoped table
-- with a BEFORE DELETE trigger that ignores it is a Program nobody can purge,
-- and 030 checks for precisely that.
CREATE FUNCTION task_chain_unlocks_are_derived() RETURNS trigger
LANGUAGE plpgsql AS $fn$
BEGIN
    IF coalesce(current_setting('app.deriving_chain_unlocks', true), 'off') = 'on'
       OR (TG_OP = 'DELETE'
           AND coalesce(current_setting('app.purging', true), 'off') = 'on') THEN
        RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
    END IF;

    RAISE EXCEPTION
        'a chain unlock is derive_chain_unlocks''s to write, not a caller''s'
        USING ERRCODE = 'insufficient_privilege',
              HINT = 'build a chain and stamp the pivot; the derivation writes the unlock when the rows support it';
END $fn$;

CREATE TRIGGER task_chain_unlocks_only_the_derivation_writes
    BEFORE INSERT OR UPDATE OR DELETE ON task_chain_unlocks
    FOR EACH ROW EXECUTE FUNCTION task_chain_unlocks_are_derived();

COMMENT ON FUNCTION task_chain_unlocks_are_derived() IS
  'Every row of task_chain_unlocks is written by the derivation and by nothing else. Without this the GRANT the derivation needs is a way for anything holding the runtime connection to mint the unlock value of its choice.';

REVOKE ALL ON FUNCTION task_chain_unlocks_are_derived() FROM PUBLIC;


-- ===========================================================================
-- 4. The derivation -- create the candidates, withdraw the stale, record the rest
-- ===========================================================================
--
-- Three statements in the order the rows need them: a candidate cannot carry an
-- unlock row until it exists, and a stale row must go before a fresh one is
-- counted beside it.
--
-- Withdrawal is stated as the complement of the frontier and not as a list of
-- the ways a row can go stale. 026 enumerated its withdrawal predicate because
-- its derivation is two hand-written rules with no single expression behind
-- them. This one has such an expression, and the list it would replace has six
-- entries -- the chain went unsound, the member joined it, something else
-- supplied the capability, a second requirement went missing, the Test got
-- stamped, the subject left the Surface -- every one of which is a second
-- wording of a clause in section 2, free to drift the day section 2 is edited.
-- "A row the frontier would not produce" cannot drift from the frontier.
--
-- That makes criterion 4 a property of the shape rather than of a case: a member
-- invalidated, a pivot 039 would no longer stamp, a scope version moved, an
-- Identity withdrawn -- each of them makes `rk2_chain_unsoundness` return a
-- sentence, which drops the chain out of `sound`, which drops every row under it
-- out of the frontier, which deletes them here. No arm of this function names
-- any of those four, and that is the point: the ways a chain can stop holding
-- are 040's list and this file must not keep a copy of it.
--
-- Candidate creation is guarded on a hunt Task for that hypothesis existing in
-- ANY status, not merely a live one. A Task that ran and finished is an answer;
-- deriving it again next pass because the answer was disappointing is a loop
-- with a database behind it. If the hypothesis is worth asking again, 034's
-- retest trigger is the thing that says so, and it moves the hypothesis rather
-- than minting a Task.

CREATE FUNCTION derive_chain_unlocks() RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p         uuid := rk2_program_required();
    n_tasks   bigint := 0;
    n_dropped bigint := 0;
    n_added   bigint := 0;
BEGIN
    PERFORM set_config('app.deriving_chain_unlocks', 'on', true);

    -- (1) The candidates. One per hypothesis on the frontier, because the Task
    --     that would obtain the capability is the Task that runs the Test, and
    --     `ready_for` asks a hunt Task for a testable hypothesis. Estimates are
    --     left NULL on purpose: what a Task is worth on its own is the model's
    --     sentence, and a runtime that filled it in would be inventing the one
    --     number criterion 5 relies on to constrain the unlock.
    WITH wanted AS (
        SELECT DISTINCT fr.hypothesis_id, fr.subject_entity_id
          FROM rk2_chain_unlock_frontier(p) fr
         WHERE NOT EXISTS (SELECT 1 FROM tasks k
                            WHERE k.program_id = p
                              AND k.kind = 'hunt'
                              AND k.hypothesis_id = fr.hypothesis_id)
    ), made AS (
        INSERT INTO tasks (program_id, kind, hypothesis_id, subject_entity_id)
        SELECT p, 'hunt', w.hypothesis_id, w.subject_entity_id FROM wanted w
        RETURNING 1 AS one
    )
    SELECT count(*) INTO n_tasks FROM made;

    -- (2) Withdrawal, as the complement of the frontier.
    WITH gone AS (
        DELETE FROM task_chain_unlocks u
         WHERE u.program_id = p
           AND NOT EXISTS (
                 SELECT 1
                   FROM rk2_chain_unlock_frontier(p) fr
                   JOIN tasks k ON k.id = u.task_id AND k.program_id = u.program_id
                  WHERE fr.chain_id   = u.chain_id
                    AND fr.capability = u.capability
                    AND fr.stamp_id   = u.stamp_id
                    AND fr.hypothesis_id = k.hypothesis_id
                    AND k.kind = 'hunt'
                    AND k.status = 'pending')
        RETURNING 1 AS one
    )
    SELECT count(*) INTO n_dropped FROM gone;

    -- (3) What the rows now support.
    WITH added AS (
        INSERT INTO task_chain_unlocks
            (program_id, task_id, chain_id, capability, stamp_id, finding_id)
        SELECT p, k.id, fr.chain_id, fr.capability, fr.stamp_id, fr.finding_id
          FROM rk2_chain_unlock_frontier(p) fr
          JOIN tasks k ON k.program_id = p
                      AND k.kind = 'hunt'
                      AND k.hypothesis_id = fr.hypothesis_id
                      AND k.status = 'pending'
        ON CONFLICT (task_id, chain_id, capability, stamp_id) DO NOTHING
        RETURNING 1 AS one
    )
    SELECT count(*) INTO n_added FROM added;

    PERFORM set_config('app.deriving_chain_unlocks', 'off', true);
    RETURN jsonb_build_object('candidates', n_tasks,
                              'derived', n_added, 'withdrawn', n_dropped);
END $fn$;

COMMENT ON FUNCTION derive_chain_unlocks() IS
  'Create the candidate Tasks the frontier asks for, withdraw every unlock row the frontier no longer produces, and record the ones it does. Called by rank_pass after the dependency edges and before ranking, so that a chain that went unsound has stopped paying by the time anything is scored.';

REVOKE ALL ON FUNCTION derive_chain_unlocks() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION derive_chain_unlocks() TO rk2_runtime;


-- ===========================================================================
-- 5. The number
-- ===========================================================================
--
-- 026's `unlock_for` over a different unit, and deliberately the same shape: sum
-- over the DISTINCT things this Task would make reachable, each shared between
-- the pending Tasks that could reach it, capped at one. The parallel is the
-- point -- two unlock terms that disagreed about double counting would be two
-- answers to one question -- and the two functions stay separate because the
-- unit differs. 026 counts pending Tasks, whose worth is `value_for`. This
-- counts Findings, which have no `value_for` and are not Tasks.
--
-- So what a member is worth needs saying, and the answer is its severity band.
-- The obvious alternative was the CVSS score, which needs no vocabulary and is
-- already a number -- and it would have been a term that is always zero. 038
-- dropped `apply_computed_severity` and left `apply_computed_cvss` behind it,
-- and nothing in this corpus calls that function: `findings.cvss_vector` is
-- NULL on every Finding this harness has ever produced. A currency nothing
-- denominates is not a conservative choice, it is a dead term wearing one.
--
-- The band needs a number, so this is a vocabulary table. It is not the band
-- vocabulary restated -- that lives in a CHECK on `findings.severity` and there
-- is nothing to point a foreign key at -- it is what a band is worth TO THE
-- QUEUE, which is a scheduling policy and belongs to the scheduler. Section 7
-- asks whether the two have drifted, over the rows rather than over the
-- constraint text, so a band this table has no weight for is a standing failure
-- rather than a member that silently stopped counting.
--
-- Even spacing, and that is a decision. A band is an ordinal; the formula needs
-- a ratio; four equal steps assert the ordering and nothing else. Any other
-- curve would be a claim about how much worse a critical Finding is than a high
-- one, and nobody in this system has made that claim.
--
-- A member whose severity rests on `undetermined` contributes nothing rather
-- than its band. That is 026's rule for a dependent with no estimates, applied
-- to the other axis, and 036's own column is what states it: `info` on an
-- undetermined basis is the default a candidate Finding is born with, not a
-- measurement, and letting the default count would pay for reachability that
-- nobody has assessed. A member stated `info` on a real basis does count -- at
-- zero, which is what that statement means.

CREATE TABLE severity_unlock_weights (
    severity text PRIMARY KEY,
    weight   numeric NOT NULL CHECK (weight >= 0 AND weight <= 1),
    note     text NOT NULL
);

COMMENT ON TABLE severity_unlock_weights IS
  'What a member Finding''s severity band is worth to the ranking when reaching it is what a Task would unlock. A scheduling policy over 009''s bands, not a second copy of them: the queue needs a ratio and a band is an ordinal.';

INSERT INTO severity_unlock_weights (severity, weight, note) VALUES
    ('info',     0.00, 'stated as worth nothing, which is a measurement and counts as one'),
    ('low',      0.25, 'one step'),
    ('medium',   0.50, 'two steps'),
    ('high',     0.75, 'three steps'),
    ('critical', 1.00, 'the top of the scale the unlock term is capped at');

INSERT INTO program_global_tables (table_name, reason) VALUES
    ('severity_unlock_weights', 'what a band is worth to the queue is a property of the harness, not of a target');

INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
    ('severity_unlock_weights', 'reference',
     'the scheduling weight of a severity band, changed only by migration', '41');

-- The revoke is the sentence, not the grant. 029 set `ALTER DEFAULT PRIVILEGES
-- FOR ROLE rk2_owner ... GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO
-- rk2_runtime`, so a reference table that says "changed only by migration" and
-- stops at a GRANT SELECT is saying it to a role that can already reprice every
-- band in it -- and repricing `critical` to zero is a way to make a member stop
-- counting without touching a Finding.
--
-- Two verbs and not three, for the reason `20260811T170000Z` gives about the
-- egress buckets: `readwrite_on_every_managed_table` asserts the runtime keeps
-- SELECT and INSERT on every managed table, and a table it cannot INSERT into
-- fails the gate the whole harness opens on. The retained verb is not a way in.
-- `severity` is the primary key and 009 fixes the five bands a Finding may
-- carry, so an INSERT can only add a row for a band no member can be on -- and
-- a weight nothing joins to is a row nothing reads.
GRANT SELECT ON severity_unlock_weights TO rk2_runtime, rk2_human;
REVOKE UPDATE, DELETE ON severity_unlock_weights FROM rk2_runtime;
REVOKE ALL ON severity_unlock_weights FROM rk2_state, rk2_proxy;

-- The cap is at one for 026's reason: no amount of downstream reachability makes
-- a single Task's numerator unbounded. It also keeps the sum in section 6 inside
-- the CHECK on the column.
CREATE FUNCTION chain_unlock_for(t tasks) RETURNS numeric
LANGUAGE sql STABLE AS $fn$
    SELECT least(coalesce(sum(s.share), 0), 1.0)
      FROM (SELECT DISTINCT u.finding_id,
                   sw.weight
                     / greatest((SELECT count(DISTINCT u2.task_id)
                                   FROM task_chain_unlocks u2
                                   JOIN tasks k2
                                     ON k2.id = u2.task_id
                                    AND k2.program_id = u2.program_id
                                  WHERE u2.finding_id = u.finding_id
                                    AND u2.program_id = u.program_id
                                    AND k2.status = 'pending'), 1) AS share
              FROM task_chain_unlocks u
              JOIN findings f ON f.id = u.finding_id AND f.program_id = u.program_id
              -- Inner, so an unweighted band and an undetermined basis leave the
              -- member out of the sum by the same mechanism: no row, no share.
              JOIN severity_unlock_weights sw ON sw.severity = f.severity
             WHERE u.task_id = t.id
               AND u.program_id = t.program_id
               AND f.severity_basis <> 'undetermined') s;
$fn$;

COMMENT ON FUNCTION chain_unlock_for(tasks) IS
  'What this Task would add to what is already reachable: the severity weight of each DISTINCT Finding a sound chain is one requirement short of, shared between the pending Tasks that could supply that requirement, capped at one. A member whose severity nobody has stated contributes nothing rather than a guess.';

REVOKE ALL ON FUNCTION rk2_chain_capabilities(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION rk2_chain_unlock_frontier(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION chain_unlock_for(tasks) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION rk2_chain_capabilities(uuid) TO rk2_runtime, rk2_human;
GRANT EXECUTE ON FUNCTION rk2_chain_unlock_frontier(uuid) TO rk2_runtime, rk2_human;
GRANT EXECUTE ON FUNCTION chain_unlock_for(tasks) TO rk2_runtime;


-- ===========================================================================
-- 6. Into the pass, without touching the shape of the formula
-- ===========================================================================
--
-- Criterion 5 is met by what this section does NOT do. The formula stays
--
--     priority = novelty * confidence * (value + w_unlock * unlock)
--                / max(w_tokens*cost + w_time*time + w_safety*safety, cost_floor)
--
-- character for character, and `unlock` gains a second summand. Three
-- consequences follow from leaving it alone, and all three are the criterion:
-- `direct_value` NULL still makes `priority` NULL, so a Task with the whole
-- frontier under it and no estimate on it still sinks below every scored Task
-- rather than leading the queue; confidence still multiplies, so a Task whose
-- skills are disabled is still worth zero; and cost, time and safety still
-- divide, so a dangerous or expensive way to obtain a capability is still ranked
-- behind a cheap one that obtains the same thing.
--
-- No new weight, either. `w_unlock` already says what this operator thinks
-- unlocking is worth relative to doing, and a second weight would make that one
-- sentence two -- with no way to state, in either of them, what the two kinds of
-- unlock are worth relative to each other.
--
-- The two summands are capped together and recorded apart. Together, because
-- `tasks.unlock_value` is bounded in [0, 1] by 026's CHECK and because the cap is
-- the statement that no Task's numerator runs away. Apart, because 026's own
-- reason for making the components columns was that a rank result has to be
-- auditable, and one number that two different derivations both moved is not.

ALTER TABLE tasks ADD COLUMN chain_unlock_value numeric;

ALTER TABLE tasks
    ADD CONSTRAINT tasks_chain_unlock_value_ck
        CHECK (chain_unlock_value IS NULL
               OR (chain_unlock_value >= 0 AND chain_unlock_value <= 1));

COMMENT ON COLUMN tasks.chain_unlock_value IS
  'The half of unlock_value that came from the kill chains: what this Task would make newly reachable that nothing already reaches. Recorded beside the total because two derivations feed one number, and a number two things moved cannot be audited from the number.';

-- 026 wrote the second sentence of this comment as a forward reference. The
-- reference has arrived, so the sentence has to stop saying "direct unlock only".
COMMENT ON COLUMN tasks.unlock_value IS
  'What this Task unblocks, capped at one: the value of the pending Tasks a sound dependency edge says it unblocks, plus the chain members a sound chain is one requirement short of. The second summand is on chain_unlock_value as well, so the two can be read apart.';

CREATE OR REPLACE FUNCTION task_rank_factors(t tasks) RETURNS jsonb
LANGUAGE sql STABLE AS $fn$
    SELECT jsonb_build_object(
        'novelty',         round(t.novelty, 6),
        'gain',            t.expected_information_gain,
        'impact',          t.potential_impact,
        'value',           round(t.direct_value, 6),
        'cost',            round(t.estimated_cost, 6),
        'time',            round(t.estimated_time, 6),
        'safety',          round(t.safety_cost, 6),
        'unlock',          round(t.unlock_value, 6),
        'chain_unlock',    round(t.chain_unlock_value, 6),
        'confidence',      round(t.confidence_of_execution, 6),
        'weights_version', t.ranked_weights_version);
$fn$;

COMMENT ON FUNCTION task_rank_factors(tasks) IS
  'Every component of this Task''s priority and the weights version that combined them, in the one spelling the Slate and the scheduler.ranked event both report. `unlock` is the total that entered the formula and `chain_unlock` is the part of it the kill chains contributed.';

-- 026's `rank_pass` with one step and two expressions added. Restated whole
-- because that is what CREATE OR REPLACE means for a function, and 026 restated
-- 023's for the same reason.
CREATE OR REPLACE FUNCTION rank_pass(p_trigger text DEFAULT 'timer') RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p            uuid := rk2_program_required();
    w            scheduler_weights%ROWTYPE;
    n_cancelled  bigint := 0;
    n_ranked     bigint := 0;
    n_fired      bigint := 0;
    v_retests    jsonb;
    edges        jsonb;
    unlocks      jsonb;
    by_reason    jsonb;
    top          jsonb;
    t0           timestamptz := clock_timestamp();
BEGIN
    SELECT * INTO w FROM scheduler_weights WHERE active;
    IF NOT FOUND THEN RAISE EXCEPTION 'no active scheduler_weights row'; END IF;

    -- (1) Retest re-entry. Decision 11: the pass owns it, because it is the
    -- only runtime step that reads the whole program. 034 moved the body out
    -- into `refresh_negative_knowledge`, which is where the kept refutations
    -- are and where 022's per-Application fingerprint comparison had to go; the
    -- pass keeps the decision about WHEN, which is what decision 11 was about.
    --
    -- It stays first, and that ordering is load-bearing twice over. A claim
    -- whose refutation stopped being current has to be out of `refuted` before
    -- step (2) reads its status, or the Task asking the question again is
    -- abandoned in the same pass that reopened it. And an imported refutation
    -- -- one nothing on file settles -- is reopened here before step (2) could
    -- ever read it as suppression.
    v_retests := refresh_negative_knowledge();
    n_fired   := (v_retests ->> 'reopened')::bigint;

    -- (2) Cancellation, before ranking: a task that should not run must not be
    -- ranked into a slate this pass.
    WITH c AS (
        SELECT t.id, cancel_reason_for(t, w) AS reason
          FROM tasks t WHERE t.program_id = p AND t.status = 'pending'
    ), u AS (
        UPDATE tasks t SET status = 'abandoned', abandoned_reason = c.reason,
                           finished_at = now(), priority = NULL
          FROM c WHERE t.id = c.id AND c.reason IS NOT NULL
        RETURNING t.abandoned_reason AS reason
    )
    SELECT count(*), coalesce(jsonb_object_agg(reason, n), '{}'::jsonb)
      INTO n_cancelled, by_reason
      FROM (SELECT reason, count(*) AS n FROM u GROUP BY reason) g;

    -- (3) Dependency edges, after cancellation and before ranking, for the
    -- same reason in both directions: a Task abandoned above must stop
    -- unlocking anything, and an edge derived below must be visible to the
    -- ranking in this pass rather than the next one.
    edges := derive_task_dependencies();

    -- (3b) Chain unlocks, after the edges for the first of those two reasons
    -- and before the ranking for the second. Not folded into (3): that function
    -- is 026's two rules over `ready_for` and this one creates Tasks, and a
    -- derivation that both restates a readiness predicate and mints rows would
    -- be two jobs sharing a name and a transaction-local licence.
    --
    -- The Tasks it creates are not put through (2). They cannot need it: the
    -- frontier will not name a subject off the Surface or a superseded
    -- hypothesis, and the other cancellation reasons are about a history a Task
    -- created moments ago does not have. The pass after this one asks anyway.
    unlocks := derive_chain_unlocks();

    -- (4) The ranking. One statement, eight components, no clock in it.
    WITH r AS (
        SELECT t.id,
               novelty_for(t)         AS novelty,
               cost_for(t, w)         AS estimated_cost,
               time_for(t, w)         AS estimated_time,
               safety_for(t, w)       AS safety_cost,
               confidence_for(t, w)   AS confidence,
               value_for(t, w)        AS direct_value,
               unlock_for(t, w)       AS direct_unlock,
               chain_unlock_for(t)    AS chain_unlock
          FROM tasks t
         WHERE t.program_id = p AND t.status = 'pending'
    ), u AS (
        UPDATE tasks t
           SET novelty = r.novelty,
               estimated_cost = r.estimated_cost,
               estimated_time = r.estimated_time,
               safety_cost = r.safety_cost,
               confidence_of_execution = r.confidence,
               direct_value = r.direct_value,
               chain_unlock_value = r.chain_unlock,
               unlock_value = least(r.direct_unlock + r.chain_unlock, 1.0),
               ranked_weights_version = w.version,
               -- NULL, not 0: an unestimated task must sink via NULLS LAST, and
               -- a task scored 0 is a different statement from one never scored
               priority = CASE
                   WHEN r.direct_value IS NULL THEN NULL
                   ELSE r.novelty * r.confidence
                        * (r.direct_value
                           + w.w_unlock * least(r.direct_unlock + r.chain_unlock, 1.0))
                        / greatest(w.w_tokens * r.estimated_cost
                                 + w.w_time   * r.estimated_time
                                 + w.w_safety * r.safety_cost, w.cost_floor)
               END
          FROM r WHERE t.id = r.id
        RETURNING t.id
    )
    SELECT count(*) INTO n_ranked FROM u;

    SELECT coalesce(jsonb_agg(j ORDER BY ord), '[]'::jsonb) INTO top
      FROM (
        SELECT row_number() OVER (ORDER BY t.priority DESC NULLS LAST,
                                           t.created_at, t.id) AS ord,
               jsonb_build_object(
                 'task', t.label, 'kind', t.kind,
                 'priority', round(t.priority, 6),
                 'factors', task_rank_factors(t)) AS j
          FROM tasks t WHERE t.program_id = p AND t.status = 'pending'
          ORDER BY t.priority DESC NULLS LAST, t.created_at, t.id
          LIMIT 10) s;

    INSERT INTO events (program_id, type, actor_kind, payload)
    VALUES (p, 'scheduler.ranked', 'runtime', jsonb_build_object(
        'trigger', p_trigger,
        'weights_version', w.version,
        'candidates', n_ranked,
        'retests', v_retests,
        'abandoned_by_reason', by_reason,
        'dependency_edges', edges,
        'chain_unlocks', unlocks,
        'lane_slots', (SELECT coalesce(jsonb_object_agg(kind, live_slots), '{}'::jsonb)
                         FROM scheduler_lane_state WHERE program_id = p),
        'top', top,
        'further_omitted', greatest(n_ranked - 10, 0),
        'duration_ms', round(extract(epoch FROM clock_timestamp() - t0) * 1000)));

    RETURN jsonb_build_object('ranked', n_ranked, 'abandoned', n_cancelled,
                              -- `retests_fired` is 023's key and stays what it
                              -- was: how many claims re-entered. `retests` is
                              -- the breakdown behind it, so a caller can tell a
                              -- pass that reopened nothing because nothing moved
                              -- from one that reopened nothing because it found
                              -- nothing to reopen.
                              'retests_fired', n_fired,
                              'retests', v_retests,
                              'edges_derived', edges -> 'derived',
                              'edges_withdrawn', edges -> 'withdrawn',
                              'unlock_candidates', unlocks -> 'candidates',
                              'unlocks_derived', unlocks -> 'derived',
                              'unlocks_withdrawn', unlocks -> 'withdrawn');
END $fn$;


-- ===========================================================================
-- 7. What the audit reads
-- ===========================================================================
--
-- Three of 026's arms are about a LIST rather than about ranking: no step of the
-- pass reads the clock, no scheduler function is callable by PUBLIC, and no
-- ranked Task is missing a component. 023 wrote that list into a check, 026
-- copied it and added four names, and this file would be the third copy and the
-- second author to have to remember. So the list becomes a table both checks
-- read, and 026's check is restated over it. `severity_unlock_weights` is the
-- same move for the same reason one section earlier: a fact more than one
-- migration needs is a row, not a literal repeated per migration.
--
-- Two memberships and not one, because the two rules are not about the same set:
-- everything here is a scheduler function and may not be reachable by PUBLIC,
-- and the subset that runs INSIDE a pass may not read the clock. A check
-- function is a scheduler function that no pass calls, and would fail the clock
-- rule for asking `now()` a legitimate question.

CREATE TABLE ranking_pass_functions (
    proname      text PRIMARY KEY,
    in_the_pass  boolean NOT NULL,
    owner_ticket text NOT NULL,
    note         text NOT NULL
);

COMMENT ON TABLE ranking_pass_functions IS
  'Every function the Ranking pass is made of, and whether it runs inside a pass. Two rules are asked of these names and of no others: a scheduler function is not callable by PUBLIC, and a step of a pass does not read the clock. The list is a table so that a ticket adding a factor registers it once instead of editing every check that had a copy.';

COMMENT ON COLUMN ranking_pass_functions.in_the_pass IS
  'True for a step `rank_pass` calls, which decision 12 forbids to read the clock. False for a check or a verb about the pass, which may: a standing check that could not ask what time it is would be a check with one hand tied.';

INSERT INTO ranking_pass_functions (proname, in_the_pass, owner_ticket, note) VALUES
    ('value_for',                 true,  '26', 'the model''s estimate, shrunk'),
    ('time_for',                  true,  '26', 'the time term'),
    ('safety_for',                true,  '26', 'the safety term'),
    ('unlock_for',                true,  '26', 'the direct unlock term'),
    ('shrunk_toward',             true,  '26', 'the shrinkage all three priors use'),
    ('task_rank_factors',         true,  '26', 'what the components are reported as'),
    ('derive_task_dependencies',  true,  '26', 'the edges, derived before the ranking'),
    ('check_task_ranking',        false, '26', 'the standing check over all of it'),
    ('rk2_chain_capabilities',    true,  '41', 'what a chain already holds'),
    ('rk2_chain_unlock_frontier', true,  '41', 'the gap a candidate would close'),
    ('chain_unlock_for',          true,  '41', 'the chain unlock term'),
    ('derive_chain_unlocks',      true,  '41', 'the candidates and their unlock rows'),
    ('check_chain_unlocks',       false, '41', 'the standing check over this file');

INSERT INTO program_global_tables (table_name, reason) VALUES
    ('ranking_pass_functions', 'the shape of the Ranking pass is a property of the harness, not of a target');

INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
    ('ranking_pass_functions', 'reference',
     'the names the two scheduler rules are asked of, changed only by migration', '41');

-- Section 5's revoke, for section 5's reason and with one of its own. A DELETE
-- here is how a rule stops being asked of a function without anybody editing a
-- check, and an UPDATE of `in_the_pass` is the same move more quietly. INSERT
-- stays for `readwrite_on_every_managed_table`, and it is the harmless
-- direction: a name added to this table is a name the two rules are asked OF,
-- and if the function does not exist arm (b2) says so on the next check.
GRANT SELECT ON ranking_pass_functions TO rk2_runtime, rk2_human;
REVOKE UPDATE, DELETE ON ranking_pass_functions FROM rk2_runtime;
REVOKE ALL ON ranking_pass_functions FROM rk2_state, rk2_proxy;

-- 026's check with its first two arms reading the table instead of a literal,
-- one arm added for a name in the table that no longer exists, and the component
-- arm extended to the column section 6 added. Restated whole because that is
-- what CREATE OR REPLACE means for a function; every other arm is 026's, to the
-- character.
CREATE OR REPLACE FUNCTION check_task_ranking()
RETURNS TABLE (problem text, subject text, detail text)
LANGUAGE sql STABLE AS $fn$
    -- (a) decision 12, over every step registered as running inside a pass.
    --     Comments are stripped first, as check_scheduler_closure's arm (g)
    --     does: the first version of that check fired on a comment explaining
    --     why the clock is absent.
    --
    --     `derive_task_dependencies` is in the table and its rows carry
    --     `derived_at`, which is not a contradiction: the default on the column
    --     stamps when the pass ran, and no branch of the function reads it.
    SELECT 'ranking_factor_reads_the_clock'::text, p.proname::text,
           'a Ranking pass step reads the clock; two replays of one set of rows would disagree'::text
      FROM pg_proc p
      JOIN ranking_pass_functions r ON r.proname = p.proname AND r.in_the_pass
     WHERE p.pronamespace = 'public'::regnamespace
       AND regexp_replace(p.prosrc, '--[^' || chr(10) || ']*', '', 'g')
           ~* '(now\(\)|current_timestamp|clock_timestamp)'
UNION ALL
    -- (b) no scheduler function is callable by PUBLIC, the rule 023 states for
    --     the three factors that existed then.
    SELECT 'scheduler_function_public_executable', p.proname::text,
           'a model-reachable role could call a scheduler function'
      FROM pg_proc p
      JOIN ranking_pass_functions r ON r.proname = p.proname
     WHERE p.pronamespace = 'public'::regnamespace
       AND has_function_privilege('public', p.oid, 'EXECUTE')
UNION ALL
    -- (b2) the cost of holding the list in a table: a name that has been renamed
    --      or dropped stops being checked and nothing says so. A registry that
    --      can silently empty itself is worse than the literal it replaced.
    SELECT 'ranking_function_registered_but_absent', r.proname,
           'a registered Ranking pass function does not exist; the two scheduler rules are no longer asked of it'
      FROM ranking_pass_functions r
     WHERE NOT EXISTS (SELECT 1 FROM pg_proc p
                        WHERE p.pronamespace = 'public'::regnamespace
                          AND p.proname = r.proname)
UNION ALL
    -- (c) criterion 4, as a property of the code rather than of today's rows.
    --     Dropping the join is the one edit that makes every proposed edge
    --     move a priority, and the rows it would corrupt look exactly like
    --     rows that were ranked correctly.
    SELECT 'unlock_ignores_the_basis_table', 'unlock_for',
           'unlock_for no longer joins task_dependency_bases; an unsound edge would be worth its full value'
      FROM pg_proc p
     WHERE p.pronamespace = 'public'::regnamespace
       AND p.proname = 'unlock_for'
       AND p.prosrc !~ 'task_dependency_bases'
UNION ALL
    -- (d) the vocabulary has to keep both answers. A basis table where
    --     everything is sound is the join in (c) with extra steps.
    SELECT 'dependency_basis_vocabulary_incomplete', 'task_dependency_bases',
           'the vocabulary no longer distinguishes a sound basis from an unsound one'
     WHERE NOT EXISTS (SELECT 1 FROM task_dependency_bases WHERE sound)
        OR NOT EXISTS (SELECT 1 FROM task_dependency_bases WHERE NOT sound)
UNION ALL
    -- (e) a priority nobody can reproduce.
    SELECT 'ranked_without_weights_version', t.label,
           'a stored priority with no weights version beside it'
      FROM tasks t
     WHERE t.priority IS NOT NULL AND t.ranked_weights_version IS NULL
UNION ALL
    -- (f) criterion 1, on the rows: a rank result exposes its components, so a
    --     ranked Task missing one is a result that cannot be audited.
    --     `chain_unlock_value` joins the list here rather than in a second check
    --     of its own, for the reason the table above exists.
    SELECT 'ranked_without_every_component', t.label,
           'a stored priority with a component missing under it'
      FROM tasks t
     WHERE t.priority IS NOT NULL
       AND (t.novelty IS NULL OR t.estimated_cost IS NULL
         OR t.estimated_time IS NULL OR t.safety_cost IS NULL
         OR t.confidence_of_execution IS NULL
         OR t.direct_value IS NULL OR t.unlock_value IS NULL
         OR t.chain_unlock_value IS NULL)
UNION ALL
    -- (g) an edge that outlived its reason. The derivation withdraws these;
    --     this is the assertion that it ran.
    SELECT 'dependency_edge_predicate_stale', t.label,
           'a runtime-derived edge claims a predicate the blocked Task does not report'
      FROM task_dependencies d
      JOIN tasks t ON t.id = d.task_id AND t.program_id = d.program_id
     WHERE d.basis = 'runtime_rule'
       AND t.status = 'pending'
       AND ready_for(t) IS DISTINCT FROM d.predicate
UNION ALL
    -- (h) criterion 5's other half. The weights are what every priority in the
    --     installation is computed from, so the verb that moves them is the
    --     operator's -- and 029's default privileges hand every new function to
    --     the runtime, which means the revoke above is load-bearing and a
    --     DROP/CREATE of this function silently undoes it.
    SELECT 'weights_verb_reachable_by_the_runtime', p.proname::text,
           'a connection a model reaches through can version the scheduler weights'
      FROM pg_proc p
     WHERE p.pronamespace = 'public'::regnamespace
       AND p.proname = 'version_scheduler_weights'
       AND (has_function_privilege('rk2_runtime', p.oid, 'EXECUTE')
         OR has_function_privilege('rk2_state', p.oid, 'EXECUTE'))
UNION ALL
    -- (i) criterion 4 again, against the grant that makes it necessary. The
    --     runtime holds INSERT and DELETE on the edges because the derivation
    --     runs as the runtime; without the trigger, that grant is a way to mint
    --     a sound basis, and the vocabulary the other arms guard would be
    --     decoration.
    SELECT 'sound_basis_is_writable_by_hand', 'task_dependencies',
           'no trigger holds runtime_rule to the derivation; any holder of the runtime connection could mint unlock value'
     WHERE NOT EXISTS (
        SELECT 1 FROM pg_trigger g
          JOIN pg_proc p ON p.oid = g.tgfoid
         WHERE g.tgrelid = 'task_dependencies'::regclass
           AND NOT g.tgisinternal
           AND p.proname = 'task_dependencies_runtime_rule_is_derived')
$fn$;

-- CREATE OR REPLACE keeps a function's privileges, and this one is restated in a
-- migration 029 gave default privileges to the runtime. Re-issued rather than
-- relied upon: arm (b) would report it, and a rule that has to fail before it
-- holds is a rule that held by accident.
REVOKE ALL ON FUNCTION check_task_ranking() FROM PUBLIC;

CREATE FUNCTION check_chain_unlocks()
RETURNS TABLE (problem text, subject text, detail text)
LANGUAGE sql STABLE AS $fn$
    -- The frontier of every Program that has unlock rows, computed once. Driven
    -- off the stored rows rather than off `programs`, so that a corpus with no
    -- unlock rows anywhere pays one index scan instead of re-deriving the
    -- soundness of every chain it holds.
    WITH frontier AS MATERIALIZED (
        SELECT g.program_id, fr.*
          FROM (SELECT DISTINCT program_id FROM task_chain_unlocks) g
          CROSS JOIN LATERAL rk2_chain_unlock_frontier(g.program_id) fr
    )
    -- (a) criterion 4, on the rows. Every stored row is one the frontier would
    --     produce today, which is the only claim this table makes.
    SELECT 'chain_unlock_the_frontier_no_longer_supports'::text,
           k.label::text,
           ('an unlock row for ' || c.label || ' that the frontier would not derive')::text
      FROM task_chain_unlocks u
      JOIN tasks k  ON k.id = u.task_id
      JOIN chains c ON c.id = u.chain_id
     WHERE NOT EXISTS (
             SELECT 1 FROM frontier fr
              WHERE fr.program_id = u.program_id
                AND fr.chain_id = u.chain_id
                AND fr.capability = u.capability
                AND fr.stamp_id = u.stamp_id
                AND fr.hypothesis_id = k.hypothesis_id)
UNION ALL
    -- (b) an unlock paid to work that is over. The derivation withdraws these;
    --     this is the assertion that it ran.
    SELECT 'chain_unlock_on_a_settled_task', k.label::text,
           'an unlock row under a Task that is ' || k.status
      FROM task_chain_unlocks u
      JOIN tasks k ON k.id = u.task_id
     WHERE k.status <> 'pending'
UNION ALL
    -- (c) the other direction, and the one an attacker would want: a number on
    --     a Task with nothing under it saying where the number came from.
    --
    --     Of the pending ones, because a settled Task keeps the last components
    --     it was scored with. 026 clears `priority` when it abandons a Task and
    --     leaves `novelty`, `direct_value` and `unlock_value` where they are --
    --     the priority is an instruction and the components are a measurement,
    --     and the measurement is the record of why the queue did what it did.
    --     This column is a component and follows them. What must not survive the
    --     abandonment is the unlock ROW, and arm (b) is the one that says so.
    SELECT 'chain_unlock_value_without_a_row', t.label::text,
           'a pending Task scored a chain unlock with no unlock row to account for it'
      FROM tasks t
     WHERE t.status = 'pending'
       AND coalesce(t.chain_unlock_value, 0) > 0
       AND NOT EXISTS (SELECT 1 FROM task_chain_unlocks u WHERE u.task_id = t.id)
UNION ALL
    -- (d) criterion 1 and criterion 4 as a property of the code. Dropping
    --     either call is the edit that makes a chain pay whether it holds or
    --     not, and the rows it would corrupt look exactly like correct rows.
    --     Two names because the frontier asks two soundness questions of two
    --     different things: 040's about the chain it reads, and 039's about the
    --     stamp that would join it. Losing the second is the quieter of the two
    --     -- every chain still holds and a withdrawn member goes on paying.
    SELECT 'frontier_ignores_soundness', 'rk2_chain_unlock_frontier',
           'the frontier no longer consults ' || w.callee
           || '; a chain or a stamp that has stopped holding would pay in full'
      FROM pg_proc p
      CROSS JOIN unnest(ARRAY['rk2_chain_unsoundness', 'rk2_pivot_refusal']) AS w(callee)
     WHERE p.pronamespace = 'public'::regnamespace
       AND p.proname = 'rk2_chain_unlock_frontier'
       AND p.prosrc !~ w.callee
UNION ALL
    -- (e) the drift section 5 accepted when it put the bands in a second table.
    --     Asked of the Findings rather than of the constraint text, because a
    --     band nobody has ever used is a vocabulary question and a band a
    --     Finding carries with no weight beside it is a member that has
    --     silently stopped counting.
    SELECT DISTINCT 'severity_band_without_an_unlock_weight', f.severity::text,
           'a Finding carries a severity the unlock term has no weight for; every member on that band counts as nothing'
      FROM findings f
     WHERE NOT EXISTS (SELECT 1 FROM severity_unlock_weights sw
                        WHERE sw.severity = f.severity)
$fn$;

COMMENT ON FUNCTION check_chain_unlocks() IS
  'Ticket 41. Everything about a chain unlock that is true of the corpus rather than of one pass: every stored row is one the frontier still produces, none of them sits under a settled Task, no Task carries a chain unlock nothing accounts for, the frontier still asks whether the chain holds, and every severity a Finding carries has a weight beside it. What this file adds to the two rules over the whole pass is a row in ranking_pass_functions, which check_task_ranking asks.';

REVOKE ALL ON FUNCTION check_chain_unlocks() FROM PUBLIC, rk2_state, rk2_proxy;
GRANT EXECUTE ON FUNCTION check_chain_unlocks() TO rk2_runtime, rk2_human;

INSERT INTO standing_checks (name, query, owner_ticket, note) VALUES
    ('check_chain_unlocks',
     'SELECT * FROM check_chain_unlocks()',
     '41',
     'A chain unlock earns its place in the queue: every unlock row is one the frontier still derives from a sound chain, under a Task that is still pending, and every chain unlock value on a ranked Task has rows accounting for it.');

SELECT apply_state_rls();


-- ===========================================================================
-- 8. What this migration asserts about itself
-- ===========================================================================

DO $$
DECLARE n integer; d text;
BEGIN
    -- Criterion 1, as the shortest proof there is: no role but the runtime can
    -- write this table at all, the runtime cannot rewrite a row it wrote, and
    -- the two roles a model can reach cannot see it. The trigger is the second
    -- half and is asserted separately, because a GRANT with no trigger behind it
    -- is exactly the hole section 3 describes.
    IF has_table_privilege('rk2_runtime', 'task_chain_unlocks', 'UPDATE')
       OR has_table_privilege('rk2_human', 'task_chain_unlocks', 'INSERT')
       OR has_table_privilege('rk2_human', 'task_chain_unlocks', 'DELETE')
       OR has_table_privilege('rk2_state', 'task_chain_unlocks', 'SELECT')
       OR has_table_privilege('rk2_proxy', 'task_chain_unlocks', 'SELECT') THEN
        RAISE EXCEPTION 'task_chain_unlocks is reachable by a role that has no business writing or reading it';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_trigger
                    WHERE tgrelid = 'task_chain_unlocks'::regclass
                      AND tgname = 'task_chain_unlocks_only_the_derivation_writes') THEN
        RAISE EXCEPTION 'task_chain_unlocks has the derivation''s grant and not the derivation''s guard';
    END IF;

    -- The two reference tables say "changed only by migration", and 029's
    -- default privileges are what makes that a claim rather than a fact. The
    -- two verbs that can change what an existing row SAYS, and not INSERT --
    -- 029's other rule is that the runtime keeps INSERT everywhere, and the
    -- grants above say why adding a row to either of these is inert.
    IF has_table_privilege('rk2_runtime', 'severity_unlock_weights', 'UPDATE')
       OR has_table_privilege('rk2_runtime', 'severity_unlock_weights', 'DELETE')
       OR has_table_privilege('rk2_runtime', 'ranking_pass_functions', 'UPDATE')
       OR has_table_privilege('rk2_runtime', 'ranking_pass_functions', 'DELETE') THEN
        RAISE EXCEPTION 'a reference table only a migration may change is rewritable by the runtime';
    END IF;

    -- And the rule that revoke has to stay inside. Asked here rather than left
    -- to `migrate.sh verify`, because a REVOKE that locks the runtime out of a
    -- managed table fails the gate every `program.run` opens on, and finding
    -- that out from 1100 red tests is finding it out the long way.
    IF NOT has_table_privilege('rk2_runtime', 'severity_unlock_weights', 'INSERT')
       OR NOT has_table_privilege('rk2_runtime', 'ranking_pass_functions', 'INSERT')
       OR NOT has_table_privilege('rk2_runtime', 'task_chain_unlocks', 'INSERT') THEN
        RAISE EXCEPTION 'a table this file added is one readwrite_on_every_managed_table will refuse';
    END IF;

    -- And that the list the two scheduler rules are asked of still holds this
    -- file's four steps and its check. A registry nobody registered into is a
    -- check that passes because it asks nothing.
    IF (SELECT count(*) FROM ranking_pass_functions WHERE owner_ticket = '41') <> 5 THEN
        RAISE EXCEPTION 'ticket 41 did not register its Ranking pass functions';
    END IF;

    -- Restating a neighbouring ticket's check makes its answer this file's
    -- problem, and the two arms that now read a table instead of a literal are
    -- exactly where a restatement could quietly stop asking anything.
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_task_ranking();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-41 leaves % ranking problem(s) behind it: %', n, d;
    END IF;

    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_chain_unlocks();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-41 refuses to finish: % chain unlock problem(s): %', n, d;
    END IF;

    -- Criterion 5, as a property of the text rather than of a run: the formula
    -- still divides by the cost terms and still multiplies by confidence. An
    -- unlock that bypassed eligibility would have had to delete one of them.
    IF (SELECT p.prosrc FROM pg_proc p
         WHERE p.pronamespace = 'public'::regnamespace AND p.proname = 'rank_pass')
       !~ 'w\.w_tokens \* r\.estimated_cost' THEN
        RAISE EXCEPTION 'rank_pass no longer divides by the cost terms';
    END IF;

    -- And that the two unlock terms are capped together rather than separately,
    -- which is what keeps `unlock_value` inside 026's CHECK.
    IF (SELECT p.prosrc FROM pg_proc p
         WHERE p.pronamespace = 'public'::regnamespace AND p.proname = 'rank_pass')
       !~ 'least\(r\.direct_unlock \+ r\.chain_unlock, 1\.0\)' THEN
        RAISE EXCEPTION 'rank_pass no longer caps the two unlock terms together';
    END IF;
END $$;
