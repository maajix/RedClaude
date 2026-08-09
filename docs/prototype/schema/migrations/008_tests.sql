-- ---------------------------------------------------------------------------
-- 008_tests.sql   (ticket 06, decision 10)
-- ---------------------------------------------------------------------------

-- The Q27 spec, immutable once created: a changed spec is a new row that
-- supersedes the old one, otherwise "the runtime replayed the spec and the
-- assertions held" says nothing.
--
-- `spec` is JSONB by the decision-6 rule: it is a program, read whole by the
-- replay engine, never filtered on by field.
CREATE TABLE tests (
    id                 uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id         uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    label              text NOT NULL DEFAULT '',
    hypothesis_id      uuid NOT NULL REFERENCES hypotheses(id) ON DELETE CASCADE,
    spec               jsonb NOT NULL,
    spec_sha256        text NOT NULL,
    supersedes_test_id uuid REFERENCES tests(id) ON DELETE SET NULL,
    created_by_run_id  uuid REFERENCES agent_runs(id) ON DELETE SET NULL,
    created_at         timestamptz NOT NULL DEFAULT now(),
    UNIQUE (program_id, label)
);

CREATE TRIGGER tests_immutable
    BEFORE UPDATE OR DELETE ON tests
    FOR EACH ROW EXECUTE FUNCTION reject_mutation();

CREATE TABLE test_runs (
    id                uuid PRIMARY KEY DEFAULT uuidv7(),
    test_id           uuid NOT NULL REFERENCES tests(id) ON DELETE CASCADE,
    agent_run_id      uuid REFERENCES agent_runs(id) ON DELETE SET NULL,
    lane              text NOT NULL CHECK (lane IN ('agent','replay')),
    outcome           text NOT NULL CHECK (outcome IN ('holds','fails','error')),
    assertion_results jsonb NOT NULL,
    started_at        timestamptz NOT NULL DEFAULT now(),
    finished_at       timestamptz
);

CREATE TABLE test_run_receipts (
    test_run_id uuid NOT NULL REFERENCES test_runs(id) ON DELETE CASCADE,
    receipt_id  uuid NOT NULL REFERENCES receipts(id) ON DELETE CASCADE,
    ordinal     integer NOT NULL,
    PRIMARY KEY (test_run_id, ordinal)
);

ALTER TABLE tasks
    ADD CONSTRAINT tasks_hypothesis_fk
    FOREIGN KEY (hypothesis_id) REFERENCES hypotheses(id) ON DELETE CASCADE;
