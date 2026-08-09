-- ---------------------------------------------------------------------------
-- 006_tasks_and_runs.sql   (ticket 06, decision 12)
-- ---------------------------------------------------------------------------

CREATE TABLE tasks (
    id                uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id        uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    label             text NOT NULL DEFAULT '',
    kind              text NOT NULL CHECK (kind IN ('recon','hunt','validate','report')),
    subject_entity_id uuid REFERENCES entities(id) ON DELETE CASCADE,
    hypothesis_id     uuid,                -- FK added in 007
    status            text NOT NULL DEFAULT 'pending'
                      CHECK (status IN ('pending','claimed','running','done','failed','abandoned')),
    -- model-estimated, kept apart from runtime-computed so the eval suite can
    -- ask whose estimate was wrong (Q14)
    expected_information_gain numeric,
    potential_impact          numeric,
    -- runtime-computed
    novelty                 numeric,
    estimated_cost          numeric,
    confidence_of_execution numeric,
    priority                numeric,       -- formula is ticket 08
    created_at  timestamptz NOT NULL DEFAULT now(),
    claimed_at  timestamptz,
    finished_at timestamptz,
    UNIQUE (program_id, label)
);

-- The scheduler's claim query: SELECT ... FOR UPDATE SKIP LOCKED (Q7).
CREATE INDEX tasks_queue_idx ON tasks (program_id, priority DESC NULLS LAST, created_at)
    WHERE status = 'pending';

CREATE TABLE agent_runs (
    id             uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id     uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    label          text NOT NULL DEFAULT '',
    task_id        uuid REFERENCES tasks(id) ON DELETE CASCADE,
    parent_run_id  uuid REFERENCES agent_runs(id) ON DELETE SET NULL,
    role           text NOT NULL CHECK (role IN (
                       'orchestrator','recon','hunter','js_analyst','validator','reporter')),
    model          text NOT NULL,
    effort         text NOT NULL CHECK (effort IN ('low','medium','high','xhigh','max')),
    mission_packet jsonb NOT NULL,   -- Q24 in; producer-shaped, read whole
    result         jsonb,            -- Q24 out, RAW and unpromoted; the promotion
                                     -- step writes relational rows from it
    stop_reason    text CHECK (stop_reason IN (
                       'completed','stop_condition','budget','refusal','error','aborted')),
    input_tokens   bigint,
    output_tokens  bigint,
    started_at     timestamptz NOT NULL DEFAULT now(),
    finished_at    timestamptz,
    UNIQUE (program_id, label)
);

ALTER TABLE tool_runs
    ADD CONSTRAINT tool_runs_agent_run_fk
    FOREIGN KEY (agent_run_id) REFERENCES agent_runs(id) ON DELETE SET NULL;

ALTER TABLE identity_leases
    ADD CONSTRAINT identity_leases_holder_fk
    FOREIGN KEY (holder_agent_run_id) REFERENCES agent_runs(id) ON DELETE CASCADE;
