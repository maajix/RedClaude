-- ---------------------------------------------------------------------------
-- 009_findings.sql   (ticket 06, decision 16)
-- ---------------------------------------------------------------------------

CREATE TABLE vulnerability_classes (
    id     text PRIMARY KEY,
    cwe_id text,
    name   text NOT NULL
);   -- seed set: ticket 19

CREATE TABLE findings (
    id                    uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id            uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    label                 text NOT NULL DEFAULT '',
    subject_entity_id     uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    class_id              text NOT NULL REFERENCES vulnerability_classes(id),
    title                 text NOT NULL,
    severity              text NOT NULL CHECK (severity IN ('info','low','medium','high','critical')),
    cvss_vector           text,
    status                text NOT NULL DEFAULT 'candidate'
                          CHECK (status IN ('candidate','validating','validated','rejected','reported')),
    status_changed_at     timestamptz NOT NULL DEFAULT now(),
    validated_by_test_run_id uuid REFERENCES test_runs(id) ON DELETE RESTRICT,
    duplicate_of_finding_id  uuid REFERENCES findings(id) ON DELETE SET NULL,
    external_ref          text,
    reported_at           timestamptz,
    created_at            timestamptz NOT NULL DEFAULT now(),
    UNIQUE (program_id, label),
    -- Q27 in the schema: validated means the runtime re-ran the spec.
    CHECK (status NOT IN ('validated','reported') OR validated_by_test_run_id IS NOT NULL)
);

CREATE TABLE finding_hypotheses (
    finding_id    uuid NOT NULL REFERENCES findings(id) ON DELETE CASCADE,
    hypothesis_id uuid NOT NULL REFERENCES hypotheses(id) ON DELETE CASCADE,
    PRIMARY KEY (finding_id, hypothesis_id)
);

CREATE TABLE finding_evidence (
    finding_id     uuid NOT NULL REFERENCES findings(id) ON DELETE CASCADE,
    observation_id uuid NOT NULL REFERENCES observations(id) ON DELETE CASCADE,
    ordinal        integer NOT NULL,
    PRIMARY KEY (finding_id, ordinal),
    UNIQUE (finding_id, observation_id)
);

CREATE TABLE finding_transitions (
    id           uuid PRIMARY KEY DEFAULT uuidv7(),
    finding_id   uuid NOT NULL REFERENCES findings(id) ON DELETE CASCADE,
    from_status  text NOT NULL,
    to_status    text NOT NULL,
    actor_kind   text NOT NULL CHECK (actor_kind IN ('llm','runtime','human')),
    agent_run_id uuid REFERENCES agent_runs(id) ON DELETE SET NULL,
    receipt_id   uuid REFERENCES receipts(id) ON DELETE SET NULL,
    rationale    text,
    at           timestamptz NOT NULL DEFAULT now()
);

-- Same shape as enforce_hypothesis_transition, over findings/finding_evidence.
-- Kept as a second function rather than one generic one: the evidence counting
-- differs, and a generic version would need dynamic SQL to reach either table.
CREATE FUNCTION enforce_finding_transition() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    r         transition_rules%ROWTYPE;
    cur       text;
    n_ev      integer;
    n_control integer;
BEGIN
    SELECT status INTO cur FROM findings WHERE id = NEW.finding_id FOR UPDATE;
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

    UPDATE findings SET status = NEW.to_status, status_changed_at = now()
     WHERE id = NEW.finding_id;

    RETURN NEW;
END $$;

CREATE TRIGGER finding_transition_guard
    BEFORE INSERT ON finding_transitions
    FOR EACH ROW EXECUTE FUNCTION enforce_finding_transition();

CREATE TRIGGER findings_status_guard
    BEFORE UPDATE ON findings
    FOR EACH ROW EXECUTE FUNCTION guard_status_cache();

CREATE TRIGGER finding_transitions_immutable
    BEFORE UPDATE OR DELETE ON finding_transitions
    FOR EACH ROW EXECUTE FUNCTION reject_mutation();
