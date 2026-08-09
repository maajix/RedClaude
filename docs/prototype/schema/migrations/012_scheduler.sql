-- ---------------------------------------------------------------------------
-- 012_scheduler.sql   (ticket 08; the ticket calls this "011_scheduler.sql",
-- renumbered because ticket 06 already occupies 011 — divergence D1)
-- ---------------------------------------------------------------------------

-- decision 14: the fifth role finally has a unit of work
ALTER TABLE tasks DROP CONSTRAINT tasks_kind_check;
ALTER TABLE tasks ADD CONSTRAINT tasks_kind_check
    CHECK (kind IN ('recon','hunt','analyze','validate','report'));

-- decision 13: parked is a status, not a blocked session
ALTER TABLE tasks DROP CONSTRAINT tasks_status_check;
ALTER TABLE tasks ADD CONSTRAINT tasks_status_check
    CHECK (status IN ('pending','claimed','running','parked',
                      'done','failed','abandoned'));

ALTER TABLE tasks
    ADD COLUMN lease_expires_at    timestamptz,
    ADD COLUMN attempts            smallint NOT NULL DEFAULT 0,
    -- decision 6 / confidence gate: knowable in advance, so never worth a run
    ADD COLUMN required_skills     text[]   NOT NULL DEFAULT '{}',
    ADD COLUMN pending_decision_id uuid,          -- FK added by ticket 28
    ADD COLUMN abandoned_reason    text CHECK (abandoned_reason IN (
        'out_of_scope','superseded','answered','attempts_exhausted',
        'program_closed','budget_exhausted','near_duplicate','decision_timeout'));

-- a bare status cannot tell ticket 16 "abandoned because answered" from
-- "abandoned because it kept crashing"
ALTER TABLE tasks ADD CONSTRAINT tasks_abandoned_reason_present
    CHECK ((status = 'abandoned') = (abandoned_reason IS NOT NULL));

-- decision 12: created_at ties inside one statement, so id is the final order
DROP INDEX tasks_queue_idx;
CREATE INDEX tasks_queue_idx
    ON tasks (program_id, priority DESC NULLS LAST, created_at, id)
 WHERE status = 'pending';

-- decision 6. NULLS NOT DISTINCT is load-bearing: recon tasks have a NULL
-- hypothesis_id and report tasks a NULL subject, and default NULL semantics
-- would let both duplicate freely.
CREATE UNIQUE INDEX tasks_live_dedup_idx
    ON tasks (program_id, kind, subject_entity_id, hypothesis_id)
       NULLS NOT DISTINCT
 WHERE status IN ('pending','claimed','running','parked');

ALTER TABLE agent_runs DROP CONSTRAINT agent_runs_stop_reason_check;
ALTER TABLE agent_runs ADD CONSTRAINT agent_runs_stop_reason_check
    CHECK (stop_reason IN ('completed','stop_condition','budget','refusal',
                           'error','aborted','parked'));

-- decision 11: without this a changed fingerprint re-fires on every pass
ALTER TABLE hypothesis_retest_triggers ADD COLUMN fired_at timestamptz;

-- decision 10
CREATE TABLE surface_fingerprints (
    id                    uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id            uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    application_entity_id uuid NOT NULL
                          REFERENCES applications(entity_id) ON DELETE CASCADE,
    fingerprint           text NOT NULL,     -- contents: ticket 29
    inputs                jsonb NOT NULL DEFAULT '{}'::jsonb,
    computed_at           timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX surface_fingerprints_latest_idx
    ON surface_fingerprints (application_entity_id, computed_at DESC);

-- decision 5
CREATE TABLE hypothesis_near_matches (
    id                    uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id            uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    candidate_statement   text NOT NULL,
    matched_hypothesis_id uuid NOT NULL REFERENCES hypotheses(id) ON DELETE CASCADE,
    similarity            numeric NOT NULL,
    embedding_model       text NOT NULL,
    action                text NOT NULL CHECK (action IN ('suppressed','penalised')),
    agent_run_id          uuid REFERENCES agent_runs(id) ON DELETE SET NULL,
    at                    timestamptz NOT NULL DEFAULT now()
);

CREATE TRIGGER hypothesis_near_matches_immutable
    BEFORE UPDATE OR DELETE ON hypothesis_near_matches
    FOR EACH ROW EXECUTE FUNCTION reject_mutation();

-- decision 16: one row per version, and every number in it is unvalidated
CREATE TABLE scheduler_weights (
    version               integer PRIMARY KEY,
    w_gain                numeric NOT NULL,
    w_impact              numeric NOT NULL,
    cost_reference_tokens bigint  NOT NULL,   -- = the agent-run token budget
    cost_floor            numeric NOT NULL,
    cost_prior            jsonb   NOT NULL,   -- kind -> fraction of C_ref
    confidence_prior      numeric NOT NULL,
    shrinkage_n0          integer NOT NULL,
    near_match_high       numeric NOT NULL,
    near_match_low        numeric NOT NULL,
    slate_size            smallint NOT NULL,
    lease_ttl             interval NOT NULL,
    max_attempts          smallint NOT NULL,
    active                boolean NOT NULL DEFAULT false,
    created_at            timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX scheduler_weights_one_active
    ON scheduler_weights ((true)) WHERE active;

INSERT INTO scheduler_weights
    (version, w_gain, w_impact, cost_reference_tokens, cost_floor, cost_prior,
     confidence_prior, shrinkage_n0, near_match_high, near_match_low,
     slate_size, lease_ttl, max_attempts, active) VALUES
    (1, 0.4, 0.6, 200000, 0.01,
     '{"recon":0.30,"hunt":0.60,"analyze":0.40,"validate":0.25,"report":0.40}',
     0.5, 5, 0.93, 0.85, 5, interval '30 minutes', 3, true);

-- decision 8. min_slots is an entitlement when tasks of that kind are
-- claimable, not an idle reservation; see the round-5 correction above.
CREATE TABLE scheduler_lanes (
    program_id uuid REFERENCES programs(id) ON DELETE CASCADE,   -- NULL = default
    kind       text NOT NULL CHECK (kind IN ('recon','hunt','analyze',
                                             'validate','report')),
    min_slots  smallint NOT NULL DEFAULT 0,
    max_slots  smallint NOT NULL,
    UNIQUE NULLS NOT DISTINCT (program_id, kind),
    CHECK (min_slots <= max_slots)
);

INSERT INTO scheduler_lanes (program_id, kind, min_slots, max_slots) VALUES
    (NULL,'recon',1,2), (NULL,'hunt',0,4), (NULL,'analyze',0,2),
    (NULL,'validate',1,2), (NULL,'report',0,1);
