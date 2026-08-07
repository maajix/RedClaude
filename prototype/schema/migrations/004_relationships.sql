-- ---------------------------------------------------------------------------
-- 004_relationships.sql   (ticket 06, decision 9)
-- ---------------------------------------------------------------------------

CREATE TABLE relationships (
    id            uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id    uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    src_entity_id uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    dst_entity_id uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    type          text NOT NULL CHECK (type IN (
                      'resolves_to',    -- domain  -> host
                      'serves',         -- host    -> application
                      'runs',           -- host|application -> technology
                      'owns',           -- identity -> entity (resource ownership)
                      'member_of',      -- identity -> identity (tenant/org)
                      'redirects_to',   -- endpoint -> endpoint
                      'same_as')),      -- dedup merge
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at  timestamptz NOT NULL DEFAULT now(),
    metadata      jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (src_entity_id, dst_entity_id, type),
    CHECK (src_entity_id <> dst_entity_id)
);

CREATE INDEX relationships_dst_idx ON relationships (dst_entity_id, type);

-- Lease exclusivity is the index, not the scheduler (decision 11).
CREATE TABLE identity_leases (
    id                 uuid PRIMARY KEY DEFAULT uuidv7(),
    identity_entity_id uuid NOT NULL REFERENCES identities(entity_id) ON DELETE CASCADE,
    holder_agent_run_id uuid NOT NULL,     -- FK added in 006 (agent_runs)
    acquired_at        timestamptz NOT NULL DEFAULT now(),
    expires_at         timestamptz NOT NULL,
    released_at        timestamptz
);

CREATE UNIQUE INDEX identity_leases_exclusive_idx
    ON identity_leases (identity_entity_id) WHERE released_at IS NULL;
