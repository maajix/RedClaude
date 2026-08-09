-- ---------------------------------------------------------------------------
-- 015_ticket06_fixes.sql   (ticket 06, reopened by ticket 32)
--
-- Closes the six divergences ticket 32 attributed to ticket 06, minus D10
-- (`identities_slot_idx` global uniqueness), which belongs to ticket 35 along
-- with the other cross-program holes C24/C25/C26.
--
--   D4  unit of deletion is one whole program or one artifact blob, nothing
--       narrower. No code change: `ON DELETE RESTRICT` is the correct
--       expression of "no such operation exists". Asserted by C32.
--   D6  `status` becomes causally unforgeable: the cache may only move when a
--       transition row for that row, that `to_status`, and *this* transaction
--       exists. Replaces the `pg_trigger_depth() < 2` gate, which stopped
--       application code and nothing else.
--   D7  C23 a transition may not cite a `proxy_internal` receipt;
--       C27 `validated_by_test_run_id` must be a run of a test of one of the
--           finding's own hypotheses;
--       C28 that run's `outcome` must be `holds`, pinned by a composite FK so a
--           later rewrite of the outcome is blocked too.
--       Plus the stronger form of the same invariant: a receipt-requiring
--       conclusion must cite a receipt the test run actually produced.
--   D8  `%s` -> `%` in the illegal-transition message.
--   D9  labels are assigned by the database, from `label_prefixes`.
--
-- Also lands the schema debt other tickets left on 06's tables: ticket 08's
-- `tasks.finding_id` (D13) and ticket 09's `evidence_profiles` plus the task
-- columns the PreToolUse hook writes.
-- ---------------------------------------------------------------------------


-- ===========================================================================
-- D9 — labels
-- ===========================================================================

-- The prefix set as reviewable data rather than nine trigger arguments. `kind`
-- is the entity type for `entities` and the table name everywhere else, which is
-- what lets one lookup serve both cases.
CREATE TABLE label_prefixes (
    kind   text PRIMARY KEY,
    prefix text NOT NULL UNIQUE CHECK (prefix ~ '^[A-Z]{1,4}$')
);

INSERT INTO label_prefixes (kind, prefix) VALUES
    -- entity types
    ('domain','DOM'), ('host','HST'), ('service','SVC'), ('application','APP'),
    ('endpoint','EP'), ('parameter','PRM'), ('technology','TEC'),
    ('identity','IDN'),
    -- labelled tables
    ('hypotheses','H'), ('observations','O'), ('receipts','R'),
    ('tool_runs','TR'), ('tasks','T'), ('agent_runs','AR'),
    ('tests','TST'), ('findings','F');

-- next_label() is gap-free because it holds the counter row to commit, which
-- serialises concurrent inserts of one prefix within one program. Deliberate:
-- labels are what an agent cites in prose, and holes in `H42` invite the model
-- to reason about the holes.
--
-- The loop exists because fixtures and humans may insert explicit labels, and
-- `next_label()` cannot know about them. It is an indexed lookup on the same
-- unique key the insert would violate.
CREATE FUNCTION free_label(p_program uuid, p_kind text, p_table text) RETURNS text
LANGUAGE plpgsql AS $$
DECLARE
    p     text;
    l     text;
    taken integer;
    guard integer := 0;
BEGIN
    SELECT prefix INTO p FROM label_prefixes WHERE kind = p_kind;
    IF p IS NULL THEN
        RAISE EXCEPTION 'no label prefix registered for kind %', p_kind;
    END IF;

    LOOP
        guard := guard + 1;
        IF guard > 1000 THEN
            RAISE EXCEPTION 'could not allocate a % label for program % in 1000 tries',
                p, p_program;
        END IF;
        l := next_label(p_program, p);
        EXECUTE format('SELECT 1 FROM %I WHERE program_id = $1 AND label = $2', p_table)
           INTO taken USING p_program, l;
        EXIT WHEN taken IS NULL;
    END LOOP;

    RETURN l;
END $$;

-- A trigger function cannot take declared arguments, so the kind is read from
-- TG_TABLE_NAME here and from NEW.type in the entities variant.
CREATE FUNCTION assign_label() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.label IS NULL OR NEW.label = '' THEN
        NEW.label := free_label(NEW.program_id, TG_TABLE_NAME, TG_TABLE_NAME);
    END IF;
    RETURN NEW;
END $$;

-- `entities` keys off the type, so an endpoint gets EP and a host gets HST.
CREATE FUNCTION assign_entity_label() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.label IS NULL OR NEW.label = '' THEN
        NEW.label := free_label(NEW.program_id, NEW.type, TG_TABLE_NAME);
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER entities_assign_label     BEFORE INSERT ON entities
    FOR EACH ROW EXECUTE FUNCTION assign_entity_label();
CREATE TRIGGER hypotheses_assign_label   BEFORE INSERT ON hypotheses
    FOR EACH ROW EXECUTE FUNCTION assign_label();
CREATE TRIGGER observations_assign_label BEFORE INSERT ON observations
    FOR EACH ROW EXECUTE FUNCTION assign_label();
CREATE TRIGGER receipts_assign_label     BEFORE INSERT ON receipts
    FOR EACH ROW EXECUTE FUNCTION assign_label();
CREATE TRIGGER tool_runs_assign_label    BEFORE INSERT ON tool_runs
    FOR EACH ROW EXECUTE FUNCTION assign_label();
CREATE TRIGGER tasks_assign_label        BEFORE INSERT ON tasks
    FOR EACH ROW EXECUTE FUNCTION assign_label();
CREATE TRIGGER agent_runs_assign_label   BEFORE INSERT ON agent_runs
    FOR EACH ROW EXECUTE FUNCTION assign_label();
CREATE TRIGGER tests_assign_label        BEFORE INSERT ON tests
    FOR EACH ROW EXECUTE FUNCTION assign_label();
CREATE TRIGGER findings_assign_label     BEFORE INSERT ON findings
    FOR EACH ROW EXECUTE FUNCTION assign_label();


-- ===========================================================================
-- Schema debt owed by tickets 08 and 09
-- ===========================================================================

-- Ticket 08 D13: a `validate` task must be able to name the finding it validates.
ALTER TABLE tasks
    ADD COLUMN finding_id uuid REFERENCES findings(id) ON DELETE CASCADE;

-- The dedup key has to grow with it, or two validate tasks for two different
-- findings collide on (program, kind, NULL subject, NULL hypothesis).
DROP INDEX tasks_live_dedup_idx;
CREATE UNIQUE INDEX tasks_live_dedup_idx
    ON tasks (program_id, kind, subject_entity_id, hypothesis_id, finding_id)
       NULLS NOT DISTINCT
 WHERE status IN ('pending','claimed','running','parked');

-- Ticket 09: the PreToolUse hook on `Skill` writes both of these onto the task
-- row, which is what binds a skill to a transition and what keeps a finding
-- reproducible across a skill edit.
ALTER TABLE tasks
    ADD COLUMN skill_name   text,
    ADD COLUMN skill_sha256 text CHECK (skill_sha256 ~ '^[0-9a-f]{64}$');

-- Ticket 09: a skill may declare a *stricter* admissibility profile. The profile
-- is a SQL predicate; registering one whose function does not exist is the exact
-- failure mode that got 06 reopened, so the registry checks.
CREATE TABLE evidence_profiles (
    id          text PRIMARY KEY CHECK (id ~ '^[a-z0-9_]+$'),
    description text NOT NULL
);

CREATE FUNCTION check_evidence_profile_exists() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF to_regprocedure('evidence_profile_' || NEW.id || '(uuid)') IS NULL THEN
        RAISE EXCEPTION
            'evidence profile % needs a function evidence_profile_%(uuid) returning boolean',
            NEW.id, NEW.id;
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER evidence_profiles_fn_guard
    BEFORE INSERT OR UPDATE ON evidence_profiles
    FOR EACH ROW EXECUTE FUNCTION check_evidence_profile_exists();

-- Written alongside skill_name/skill_sha256 by the same hook: the profile the
-- skill that ran declares. NULL means the default profile, which is the
-- transition_rules row itself.
ALTER TABLE tasks
    ADD COLUMN evidence_profile_id text REFERENCES evidence_profiles(id);


-- ===========================================================================
-- D7 — what a transition and a validation may cite
-- ===========================================================================

-- Three more rule columns, so the tightening stays in the rules table rather
-- than hardcoded status names in plpgsql (decision 4).
ALTER TABLE transition_rules
    ADD COLUMN requires_test_linked_receipt boolean NOT NULL DEFAULT false,
    ADD COLUMN requires_own_hypothesis_run  boolean NOT NULL DEFAULT false,
    ADD COLUMN consults_evidence_profile    boolean NOT NULL DEFAULT false;

-- A conclusion about a hypothesis must cite a receipt the test run of that
-- hypothesis actually produced. `testable -> testing` is deliberately excluded:
-- entering `testing` is the runtime starting work, and no test run exists yet.
UPDATE transition_rules SET requires_test_linked_receipt = true
 WHERE machine = 'hypothesis' AND from_status = 'testing'
   AND to_status IN ('supported','refuted','inconclusive');

UPDATE transition_rules
   SET requires_test_linked_receipt = true, requires_own_hypothesis_run = true
 WHERE machine = 'finding' AND from_status = 'validating' AND to_status = 'validated';

UPDATE transition_rules SET consults_evidence_profile = true
 WHERE machine = 'hypothesis' AND from_status = 'testing' AND to_status = 'supported';

-- C28: pin the outcome through a composite FK. Strictly stronger than an
-- insert-time trigger, because it also blocks a later
-- `UPDATE test_runs SET outcome='fails'` on a run that is validating a finding.
ALTER TABLE test_runs ADD CONSTRAINT test_runs_id_outcome_key UNIQUE (id, outcome);

ALTER TABLE findings
    ADD COLUMN validated_run_outcome text
        CHECK (validated_run_outcome = 'holds');

ALTER TABLE findings
    DROP CONSTRAINT findings_validated_by_test_run_id_fkey;

-- MATCH FULL: both columns NULL or both set, so a NULL outcome cannot smuggle
-- the reference past the FK.
ALTER TABLE findings
    ADD CONSTRAINT findings_validated_run_holds_fk
    FOREIGN KEY (validated_by_test_run_id, validated_run_outcome)
    REFERENCES test_runs (id, outcome) MATCH FULL ON DELETE RESTRICT;

-- The application never writes `validated_run_outcome`; the FK is what checks it.
CREATE FUNCTION set_validated_run_outcome() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.validated_run_outcome :=
        CASE WHEN NEW.validated_by_test_run_id IS NULL THEN NULL ELSE 'holds' END;
    RETURN NEW;
END $$;

CREATE TRIGGER findings_pin_validated_outcome
    BEFORE INSERT OR UPDATE ON findings
    FOR EACH ROW EXECUTE FUNCTION set_validated_run_outcome();

-- A test_run row is only ever created after the run finished — `outcome` is NOT
-- NULL — so the row is immutable by nature. Making that explicit closes two
-- things at once: the outcome pin cannot be rewritten, and an UPDATE can no
-- longer slip past `emit_event`, which is attached INSERT-only because
-- `event_table_config` declares the table immutable.
CREATE TRIGGER test_runs_immutable BEFORE UPDATE OR DELETE ON test_runs
    FOR EACH ROW EXECUTE FUNCTION reject_mutation_unless_purging();


-- ===========================================================================
-- D6, D7, D8 — the transition enforcers and the status cache
-- ===========================================================================

-- The causal marker the status guard reads. `events` already uses xid8 for the
-- same purpose.
ALTER TABLE hypothesis_transitions
    ADD COLUMN txid xid8 NOT NULL DEFAULT pg_current_xact_id();
ALTER TABLE finding_transitions
    ADD COLUMN txid xid8 NOT NULL DEFAULT pg_current_xact_id();

CREATE OR REPLACE FUNCTION enforce_hypothesis_transition() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    r         transition_rules%ROWTYPE;
    cur       text;
    n_support integer;
    n_control integer;
    lane      text;
    v_profile text;
    v_ok      boolean;
BEGIN
    SELECT status INTO cur FROM hypotheses WHERE id = NEW.hypothesis_id FOR UPDATE;
    IF cur IS NULL THEN
        RAISE EXCEPTION 'no hypothesis %', NEW.hypothesis_id;
    END IF;
    IF cur IS DISTINCT FROM NEW.from_status THEN
        RAISE EXCEPTION 'stale transition: hypothesis % is %, not %',
            NEW.hypothesis_id, cur, NEW.from_status;
    END IF;

    SELECT * INTO r FROM transition_rules
     WHERE machine = 'hypothesis'
       AND from_status = NEW.from_status
       AND to_status = NEW.to_status;
    IF NOT FOUND THEN
        -- D8: plpgsql's placeholder is %, not %s.
        RAISE EXCEPTION 'illegal transition % -> %', NEW.from_status, NEW.to_status;
    END IF;

    IF r.required_actor_kind IS NOT NULL AND NEW.actor_kind <> r.required_actor_kind THEN
        RAISE EXCEPTION 'transition % -> % requires actor_kind %, got %',
            NEW.from_status, NEW.to_status, r.required_actor_kind, NEW.actor_kind;
    END IF;

    IF r.requires_receipt AND NEW.receipt_id IS NULL THEN
        RAISE EXCEPTION 'transition % -> % requires a tool receipt',
            NEW.from_status, NEW.to_status;
    END IF;

    -- D7 / C23: decision 15 applied to transitions, not only to observations.
    -- The proxy fetching its own CSRF token is not evidence of anything.
    IF NEW.receipt_id IS NOT NULL THEN
        SELECT receipts.lane INTO lane FROM receipts WHERE id = NEW.receipt_id;
        IF lane = 'proxy_internal' THEN
            RAISE EXCEPTION
                'receipt % is lane proxy_internal and cannot back a transition',
                NEW.receipt_id;
        END IF;
    END IF;

    -- The stronger form: the cited receipt must be one this hypothesis's test run
    -- produced, so a conclusion cannot rest on an unrelated request that happened
    -- to be receipted.
    IF r.requires_test_linked_receipt AND NOT EXISTS (
            SELECT 1
              FROM test_run_receipts trr
              JOIN test_runs tr ON tr.id = trr.test_run_id
              JOIN tests te     ON te.id = tr.test_id
             WHERE trr.receipt_id = NEW.receipt_id
               AND te.hypothesis_id = NEW.hypothesis_id) THEN
        RAISE EXCEPTION
            'transition % -> % must cite a receipt produced by a test run of hypothesis %',
            NEW.from_status, NEW.to_status, NEW.hypothesis_id;
    END IF;

    SELECT count(*) FILTER (WHERE role IN ('baseline','variant')),
           count(*) FILTER (WHERE role = 'control')
      INTO n_support, n_control
      FROM hypothesis_evidence WHERE hypothesis_id = NEW.hypothesis_id;

    IF n_support < r.min_supporting_evidence THEN
        RAISE EXCEPTION 'transition % -> % needs % evidence rows, found %',
            NEW.from_status, NEW.to_status, r.min_supporting_evidence, n_support;
    END IF;
    IF n_control < r.min_control_evidence THEN
        RAISE EXCEPTION 'transition % -> % needs a control observation',
            NEW.from_status, NEW.to_status;
    END IF;

    -- Ticket 09: a skill may be stricter than the default, never looser. The
    -- profile arrives on the task row from the PreToolUse hook. A transition with
    -- no agent run is not attributable to a skill and gets the default.
    IF r.consults_evidence_profile AND NEW.agent_run_id IS NOT NULL THEN
        SELECT tk.evidence_profile_id INTO v_profile
          FROM agent_runs ar JOIN tasks tk ON tk.id = ar.task_id
         WHERE ar.id = NEW.agent_run_id;
        IF v_profile IS NOT NULL THEN
            EXECUTE format('SELECT %I($1)', 'evidence_profile_' || v_profile)
               INTO v_ok USING NEW.hypothesis_id;
            IF NOT coalesce(v_ok, false) THEN
                RAISE EXCEPTION
                    'evidence profile % is not satisfied for hypothesis %',
                    v_profile, NEW.hypothesis_id;
            END IF;
        END IF;
    END IF;

    -- The cache write moved to the AFTER trigger below, so the transition row is
    -- already visible when guard_hypothesis_status_cache() looks for it.
    RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION enforce_finding_transition() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    r         transition_rules%ROWTYPE;
    cur       text;
    n_ev      integer;
    n_control integer;
    lane      text;
    v_run     uuid;
BEGIN
    SELECT status, validated_by_test_run_id INTO cur, v_run
      FROM findings WHERE id = NEW.finding_id FOR UPDATE;
    IF cur IS NULL THEN
        RAISE EXCEPTION 'no finding %', NEW.finding_id;
    END IF;
    IF cur IS DISTINCT FROM NEW.from_status THEN
        RAISE EXCEPTION 'stale transition: finding % is %, not %',
            NEW.finding_id, cur, NEW.from_status;
    END IF;

    SELECT * INTO r FROM transition_rules
     WHERE machine = 'finding' AND from_status = NEW.from_status AND to_status = NEW.to_status;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'illegal transition % -> %', NEW.from_status, NEW.to_status;
    END IF;

    IF r.required_actor_kind IS NOT NULL AND NEW.actor_kind <> r.required_actor_kind THEN
        RAISE EXCEPTION 'transition % -> % requires actor_kind %',
            NEW.from_status, NEW.to_status, r.required_actor_kind;
    END IF;

    IF r.requires_receipt AND NEW.receipt_id IS NULL THEN
        RAISE EXCEPTION 'transition % -> % requires a tool receipt',
            NEW.from_status, NEW.to_status;
    END IF;

    IF NEW.receipt_id IS NOT NULL THEN
        SELECT receipts.lane INTO lane FROM receipts WHERE id = NEW.receipt_id;
        IF lane = 'proxy_internal' THEN
            RAISE EXCEPTION
                'receipt % is lane proxy_internal and cannot back a transition',
                NEW.receipt_id;
        END IF;
    END IF;

    -- D7 / C27: the run that validates a finding must be a run of a test of one
    -- of that finding's own hypotheses. The composite FK already pins its
    -- outcome to `holds` (C28); this pins whose test it was.
    IF r.requires_own_hypothesis_run THEN
        IF v_run IS NULL THEN
            RAISE EXCEPTION
                'transition % -> % requires validated_by_test_run_id to be set first',
                NEW.from_status, NEW.to_status;
        END IF;
        IF NOT EXISTS (
                SELECT 1
                  FROM test_runs tr
                  JOIN tests te            ON te.id = tr.test_id
                  JOIN finding_hypotheses fh ON fh.hypothesis_id = te.hypothesis_id
                 WHERE tr.id = v_run
                   AND fh.finding_id = NEW.finding_id) THEN
            RAISE EXCEPTION
                'test run % is not a run of a test of any hypothesis of finding %',
                v_run, NEW.finding_id;
        END IF;
    END IF;

    IF r.requires_test_linked_receipt AND NOT EXISTS (
            SELECT 1 FROM test_run_receipts
             WHERE test_run_id = v_run AND receipt_id = NEW.receipt_id) THEN
        RAISE EXCEPTION
            'transition % -> % must cite a receipt produced by test run %',
            NEW.from_status, NEW.to_status, v_run;
    END IF;

    SELECT count(*) INTO n_ev FROM finding_evidence WHERE finding_id = NEW.finding_id;
    IF n_ev < r.min_supporting_evidence THEN
        RAISE EXCEPTION 'transition % -> % needs % evidence rows, found %',
            NEW.from_status, NEW.to_status, r.min_supporting_evidence, n_ev;
    END IF;

    SELECT count(*) INTO n_control
      FROM finding_evidence fe
      JOIN hypothesis_evidence he ON he.observation_id = fe.observation_id
     WHERE fe.finding_id = NEW.finding_id AND he.role = 'control';
    IF n_control < r.min_control_evidence THEN
        RAISE EXCEPTION 'transition % -> % needs a control observation',
            NEW.from_status, NEW.to_status;
    END IF;

    RETURN NEW;
END $$;

-- The cache write, now AFTER INSERT so the row the guard looks for exists.
--
-- Consequence to know about: AFTER ROW triggers fire at end of statement, so two
-- chained transitions in one multi-row INSERT would have the second read a stale
-- from_status and be refused. One statement per transition. The runtime commits
-- each transition separately regardless.
CREATE FUNCTION apply_hypothesis_status() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    UPDATE hypotheses
       SET status = NEW.to_status, status_changed_at = now()
     WHERE id = NEW.hypothesis_id;
    RETURN NULL;
END $$;

CREATE FUNCTION apply_finding_status() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    UPDATE findings
       SET status = NEW.to_status, status_changed_at = now()
     WHERE id = NEW.finding_id;
    RETURN NULL;
END $$;

CREATE TRIGGER hypothesis_transitions_apply_status
    AFTER INSERT ON hypothesis_transitions
    FOR EACH ROW EXECUTE FUNCTION apply_hypothesis_status();

CREATE TRIGGER finding_transitions_apply_status
    AFTER INSERT ON finding_transitions
    FOR EACH ROW EXECUTE FUNCTION apply_finding_status();

-- D6. The old guard gated on pg_trigger_depth() < 2, which stops application
-- code — the easy case — and permits anything running inside another trigger. A
-- trigger on `programs` was able to set H1 to `refuted` with zero rows in
-- `hypothesis_transitions`.
--
-- The new gate is causal rather than positional: the cache may move to X only if
-- a transition row from the current status to X, for this row, exists in THIS
-- transaction. A rogue trigger can still insert a transition, but then it is
-- subject to the rules table, the actor-kind gate, the receipt gates and the
-- evidence counts — which is the invariant, not a bypass of it.
--
-- Two functions rather than one generic one, for the same reason
-- enforce_finding_transition() is a second function: a generic version needs
-- dynamic SQL to reach either transitions table.
CREATE FUNCTION guard_hypothesis_status_cache() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.status IS DISTINCT FROM OLD.status AND NOT EXISTS (
            SELECT 1 FROM hypothesis_transitions
             WHERE hypothesis_id = NEW.id
               AND from_status = OLD.status
               AND to_status   = NEW.status
               AND txid = pg_current_xact_id()) THEN
        RAISE EXCEPTION
            'hypotheses.status is maintained by hypothesis_transitions; insert a transition row';
    END IF;
    RETURN NEW;
END $$;

CREATE FUNCTION guard_finding_status_cache() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.status IS DISTINCT FROM OLD.status AND NOT EXISTS (
            SELECT 1 FROM finding_transitions
             WHERE finding_id = NEW.id
               AND from_status = OLD.status
               AND to_status   = NEW.status
               AND txid = pg_current_xact_id()) THEN
        RAISE EXCEPTION
            'findings.status is maintained by finding_transitions; insert a transition row';
    END IF;
    RETURN NEW;
END $$;

DROP TRIGGER hypotheses_status_guard ON hypotheses;
DROP TRIGGER findings_status_guard   ON findings;
DROP FUNCTION guard_status_cache();

CREATE TRIGGER hypotheses_status_guard BEFORE UPDATE ON hypotheses
    FOR EACH ROW EXECUTE FUNCTION guard_hypothesis_status_cache();
CREATE TRIGGER findings_status_guard   BEFORE UPDATE ON findings
    FOR EACH ROW EXECUTE FUNCTION guard_finding_status_cache();

-- New columns on `findings` and `tasks`, so the emitter's column diff sees them.
SELECT attach_event_triggers();
