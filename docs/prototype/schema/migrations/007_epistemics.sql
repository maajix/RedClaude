-- ---------------------------------------------------------------------------
-- 007_epistemics.sql   (ticket 06, decisions 2, 4, 10, 13, 15, 17)
-- ---------------------------------------------------------------------------

CREATE TABLE observations (
    id                uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id        uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    label             text NOT NULL DEFAULT '',
    agent_run_id      uuid REFERENCES agent_runs(id) ON DELETE SET NULL,
    subject_entity_id uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    kind              text NOT NULL,          -- vocabulary: ticket 27
    summary           text NOT NULL,
    provenance_kind   text NOT NULL CHECK (provenance_kind IN ('receipt','tool_run')),
    receipt_id        uuid REFERENCES receipts(id) ON DELETE CASCADE,
    tool_run_id       uuid REFERENCES tool_runs(id) ON DELETE CASCADE,
    observed_at       timestamptz NOT NULL DEFAULT now(),
    metadata          jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (program_id, label),
    -- decision 13: exactly one provenance record, never none
    CHECK ((provenance_kind = 'receipt'  AND receipt_id IS NOT NULL AND tool_run_id IS NULL)
        OR (provenance_kind = 'tool_run' AND tool_run_id IS NOT NULL AND receipt_id IS NULL))
);

CREATE INDEX observations_subject_idx ON observations (subject_entity_id, observed_at DESC);

-- decision 15: the proxy fetching its own CSRF tokens is not anybody's
-- observation.
CREATE FUNCTION reject_proxy_internal_evidence() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE l text;
BEGIN
    IF NEW.receipt_id IS NOT NULL THEN
        SELECT lane INTO l FROM receipts WHERE id = NEW.receipt_id;
        IF l = 'proxy_internal' THEN
            RAISE EXCEPTION 'receipt % is lane proxy_internal and cannot back an observation',
                NEW.receipt_id;
        END IF;
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER observations_lane_guard
    BEFORE INSERT ON observations
    FOR EACH ROW EXECUTE FUNCTION reject_proxy_internal_evidence();

-- Q22: observations have no status; they exist or they do not.
CREATE FUNCTION reject_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '% rows are immutable', TG_TABLE_NAME;
END $$;

CREATE TRIGGER observations_immutable
    BEFORE UPDATE OR DELETE ON observations
    FOR EACH ROW EXECUTE FUNCTION reject_mutation();

CREATE TABLE hypotheses (
    id                   uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id           uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    label                text NOT NULL DEFAULT '',
    subject_entity_id    uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    identity_a_entity_id uuid REFERENCES identities(entity_id) ON DELETE CASCADE,
    identity_b_entity_id uuid REFERENCES identities(entity_id) ON DELETE CASCADE,
    property_class       text NOT NULL,     -- vocabulary: ticket 27
    statement            text NOT NULL,
    status               text NOT NULL DEFAULT 'proposed'
                         CHECK (status IN ('proposed','testable','testing',
                                           'supported','refuted','inconclusive')),
    status_changed_at    timestamptz NOT NULL DEFAULT now(),
    observed_fingerprint text,              -- Q26 conditions: app version at refutation
    superseded_by        uuid REFERENCES hypotheses(id) ON DELETE SET NULL,
    created_at           timestamptz NOT NULL DEFAULT now(),
    UNIQUE (program_id, label)
);

-- decision 17: the Q14 dedup key IS the constraint. A duplicate hypothesis is a
-- unique violation, not something the pgvector stage hopefully catches.
CREATE UNIQUE INDEX hypotheses_dedup_idx
    ON hypotheses (subject_entity_id, identity_a_entity_id,
                   identity_b_entity_id, property_class)
 WHERE superseded_by IS NULL;

CREATE INDEX hypotheses_open_idx ON hypotheses (program_id, status)
    WHERE status IN ('proposed','testable','testing');

-- decision 2: evidence is this edge, with a polarity and a role.
CREATE TABLE hypothesis_evidence (
    hypothesis_id  uuid NOT NULL REFERENCES hypotheses(id) ON DELETE CASCADE,
    observation_id uuid NOT NULL REFERENCES observations(id) ON DELETE CASCADE,
    polarity       text NOT NULL CHECK (polarity IN ('supports','refutes')),
    role           text NOT NULL CHECK (role IN ('baseline','variant','control','context')),
    added_at       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (hypothesis_id, observation_id, role)
);

-- Q26 retest triggers: rows, because the scheduler joins them against surface
-- deltas.
CREATE TABLE hypothesis_retest_triggers (
    id                uuid PRIMARY KEY DEFAULT uuidv7(),
    hypothesis_id     uuid NOT NULL REFERENCES hypotheses(id) ON DELETE CASCADE,
    kind              text NOT NULL CHECK (kind IN (
                          'new_deploy','response_fingerprint_changed',
                          'new_parameter','new_identity_class')),
    watched_entity_id uuid REFERENCES entities(id) ON DELETE CASCADE,
    fingerprint       text,
    UNIQUE (hypothesis_id, kind, watched_entity_id)
);

-- decision 4: legal transitions live in a table, not in prose.
CREATE TABLE transition_rules (
    machine                 text NOT NULL CHECK (machine IN ('hypothesis','finding')),
    from_status             text NOT NULL,
    to_status               text NOT NULL,
    required_actor_kind     text CHECK (required_actor_kind IN ('llm','runtime','human')),
    requires_receipt        boolean NOT NULL DEFAULT false,
    min_supporting_evidence integer NOT NULL DEFAULT 0,
    min_control_evidence    integer NOT NULL DEFAULT 0,
    PRIMARY KEY (machine, from_status, to_status)
);

INSERT INTO transition_rules
    (machine, from_status, to_status, required_actor_kind, requires_receipt,
     min_supporting_evidence, min_control_evidence) VALUES
    ('hypothesis','proposed',    'testable',     'llm',     false, 0, 0),
    -- the hinge: only the tool runtime may start a test, and only with a receipt
    ('hypothesis','testable',    'testing',      'runtime', true,  0, 0),
    ('hypothesis','testing',     'supported',    'runtime', true,  2, 1),
    ('hypothesis','testing',     'refuted',      'runtime', true,  1, 0),
    ('hypothesis','testing',     'inconclusive', 'runtime', true,  0, 0),
    -- Q22's way back: retest_due is re-entry, not a sixth state
    ('hypothesis','refuted',     'testable',     'runtime', false, 0, 0),
    ('hypothesis','inconclusive','testable',     'runtime', false, 0, 0),
    ('hypothesis','supported',   'testable',     'runtime', false, 0, 0),
    ('finding','candidate', 'validating', 'runtime', false, 0, 0),
    ('finding','validating','validated',  'runtime', true,  2, 1),
    ('finding','validating','rejected',   'runtime', false, 0, 0),
    ('finding','validated', 'reported',   'human',   false, 0, 0);

CREATE TABLE hypothesis_transitions (
    id            uuid PRIMARY KEY DEFAULT uuidv7(),
    hypothesis_id uuid NOT NULL REFERENCES hypotheses(id) ON DELETE CASCADE,
    from_status   text NOT NULL,
    to_status     text NOT NULL,
    actor_kind    text NOT NULL CHECK (actor_kind IN ('llm','runtime','human')),
    agent_run_id  uuid REFERENCES agent_runs(id) ON DELETE SET NULL,
    receipt_id    uuid REFERENCES receipts(id) ON DELETE SET NULL,
    rationale     text,
    at            timestamptz NOT NULL DEFAULT now()
);

CREATE TRIGGER hypothesis_transitions_immutable
    BEFORE UPDATE OR DELETE ON hypothesis_transitions
    FOR EACH ROW EXECUTE FUNCTION reject_mutation();

CREATE FUNCTION enforce_hypothesis_transition() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    r         transition_rules%ROWTYPE;
    cur       text;
    n_support integer;
    n_control integer;
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
        RAISE EXCEPTION 'illegal transition %s -> %s', NEW.from_status, NEW.to_status;
    END IF;

    IF r.required_actor_kind IS NOT NULL AND NEW.actor_kind <> r.required_actor_kind THEN
        RAISE EXCEPTION 'transition % -> % requires actor_kind %, got %',
            NEW.from_status, NEW.to_status, r.required_actor_kind, NEW.actor_kind;
    END IF;

    IF r.requires_receipt AND NEW.receipt_id IS NULL THEN
        RAISE EXCEPTION 'transition % -> % requires a tool receipt',
            NEW.from_status, NEW.to_status;
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

    UPDATE hypotheses
       SET status = NEW.to_status, status_changed_at = now()
     WHERE id = NEW.hypothesis_id;

    RETURN NEW;
END $$;

CREATE TRIGGER hypothesis_transition_guard
    BEFORE INSERT ON hypothesis_transitions
    FOR EACH ROW EXECUTE FUNCTION enforce_hypothesis_transition();

-- status is a trigger-maintained cache; writing it directly is an error.
-- pg_trigger_depth() is 1 when this trigger fires from an application UPDATE and
-- 2 when it fires from the transition trigger's UPDATE.
CREATE FUNCTION guard_status_cache() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.status IS DISTINCT FROM OLD.status AND pg_trigger_depth() < 2 THEN
        RAISE EXCEPTION
            '%.status is maintained by the transition table; insert a transition row',
            TG_TABLE_NAME;
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER hypotheses_status_guard
    BEFORE UPDATE ON hypotheses
    FOR EACH ROW EXECUTE FUNCTION guard_status_cache();
