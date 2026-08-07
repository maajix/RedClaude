-- ---------------------------------------------------------------------------
-- 005_artifacts_and_provenance.sql   (ticket 06, decisions 13, 14)
-- ---------------------------------------------------------------------------

-- One row per hash. Blob path is artifacts/<sha256[0:2]>/<sha256> (Q16); the
-- filename is the PLAINTEXT hash and the file content is the ciphertext, so a
-- receipt hash stays checkable against the stored blob and dedup survives
-- encryption.
CREATE TABLE artifacts (
    sha256       text PRIMARY KEY CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    byte_size    bigint NOT NULL,
    content_type text,
    visibility   text NOT NULL CHECK (visibility IN ('agent_visible','credential_bearing')),
    encrypted    boolean NOT NULL DEFAULT false,
    stored_at    timestamptz NOT NULL DEFAULT now(),
    purged_at    timestamptz,
    CHECK (visibility = 'agent_visible' OR encrypted)
);

CREATE TABLE tool_runs (
    id           uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id   uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    label        text NOT NULL DEFAULT '',
    agent_run_id uuid,                     -- FK added in 006
    tool         text NOT NULL,
    args         jsonb NOT NULL DEFAULT '{}'::jsonb,
    started_at   timestamptz NOT NULL DEFAULT now(),
    finished_at  timestamptz,
    status       text NOT NULL DEFAULT 'running'
                 CHECK (status IN ('running','success','error','denied')),
    UNIQUE (program_id, label)
);

-- Written by the proxy container under its own DB role, INSERT only. Column
-- shape follows the ticket-04 prototype, including the four hashes: the
-- agent-visible bytes and the wire bytes differ exactly by injected credential
-- material, so collapsing them forces a choice between reproducible evidence
-- and evidence that is safe to put in a model's context.
CREATE TABLE receipts (
    id                 uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id         uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    label              text NOT NULL DEFAULT '',
    tool_run_id        uuid REFERENCES tool_runs(id) ON DELETE SET NULL,
    lane               text NOT NULL CHECK (lane IN ('agent','replay','proxy_internal')),
    decision           text NOT NULL CHECK (decision IN ('allowed','blocked','deferred')),
    reason             text NOT NULL,
    identity_entity_id uuid REFERENCES identities(entity_id) ON DELETE SET NULL,
    method             text,
    scheme             text,
    host               text,
    port               integer,
    path               text,
    query_sha256       text,
    pinned_ips         text,
    status_code        integer,
    ts_arrival         timestamptz NOT NULL,
    ts_egress          timestamptz,
    waited_ms          numeric,
    request_agent_sha  text REFERENCES artifacts(sha256),
    request_wire_sha   text REFERENCES artifacts(sha256),
    response_agent_sha text REFERENCES artifacts(sha256),
    response_wire_sha  text REFERENCES artifacts(sha256),
    notes              text,
    UNIQUE (program_id, label)
);

CREATE INDEX receipts_program_ts_idx ON receipts (program_id, ts_arrival DESC);
CREATE INDEX receipts_lane_idx ON receipts (lane);
