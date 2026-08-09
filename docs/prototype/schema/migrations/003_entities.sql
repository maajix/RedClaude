-- ---------------------------------------------------------------------------
-- 003_entities.sql   (ticket 06, decision 1)
-- ---------------------------------------------------------------------------

CREATE TABLE entities (
    id            uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id    uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    type          text NOT NULL CHECK (type IN (
                      'domain','host','application','endpoint',
                      'parameter','identity','technology','service')),
    label         text NOT NULL DEFAULT '',
    dedup_key     text NOT NULL,
    in_scope      boolean NOT NULL DEFAULT true,
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at  timestamptz NOT NULL DEFAULT now(),
    metadata      jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (program_id, label),
    UNIQUE (program_id, type, dedup_key),
    UNIQUE (id, type)              -- lets detail tables pin their own type
);

CREATE INDEX entities_program_type_idx ON entities (program_id, type);

-- Detail tables. `entity_type` is a pinned constant so that the composite FK
-- makes attaching an endpoint row to a host entity a foreign-key violation.

CREATE TABLE domains (
    entity_id   uuid PRIMARY KEY REFERENCES entities(id) ON DELETE CASCADE,
    entity_type text NOT NULL DEFAULT 'domain' CHECK (entity_type = 'domain'),
    fqdn        text NOT NULL,
    apex        text NOT NULL,
    wildcard    boolean NOT NULL DEFAULT false,
    FOREIGN KEY (entity_id, entity_type) REFERENCES entities (id, type)
);

CREATE TABLE hosts (
    entity_id   uuid PRIMARY KEY REFERENCES entities(id) ON DELETE CASCADE,
    entity_type text NOT NULL DEFAULT 'host' CHECK (entity_type = 'host'),
    address     inet,
    hostname    text,
    asn         integer,
    FOREIGN KEY (entity_id, entity_type) REFERENCES entities (id, type),
    CHECK (address IS NOT NULL OR hostname IS NOT NULL)
);

CREATE TABLE services (
    entity_id   uuid PRIMARY KEY REFERENCES entities(id) ON DELETE CASCADE,
    entity_type text NOT NULL DEFAULT 'service' CHECK (entity_type = 'service'),
    host_id     uuid NOT NULL REFERENCES hosts(entity_id) ON DELETE CASCADE,
    port        integer NOT NULL CHECK (port BETWEEN 1 AND 65535),
    protocol    text NOT NULL,
    banner      text,
    FOREIGN KEY (entity_id, entity_type) REFERENCES entities (id, type),
    UNIQUE (host_id, port, protocol)
);

CREATE TABLE applications (
    entity_id   uuid PRIMARY KEY REFERENCES entities(id) ON DELETE CASCADE,
    entity_type text NOT NULL DEFAULT 'application' CHECK (entity_type = 'application'),
    base_url    text NOT NULL,
    kind        text CHECK (kind IN ('web','api','spa','graphql','websocket')),
    FOREIGN KEY (entity_id, entity_type) REFERENCES entities (id, type)
);

CREATE TABLE endpoints (
    entity_id      uuid PRIMARY KEY REFERENCES entities(id) ON DELETE CASCADE,
    entity_type    text NOT NULL DEFAULT 'endpoint' CHECK (entity_type = 'endpoint'),
    application_id uuid NOT NULL REFERENCES applications(entity_id) ON DELETE CASCADE,
    method         text NOT NULL,
    path_template  text NOT NULL,
    auth_required  boolean,
    request_content_type text,
    FOREIGN KEY (entity_id, entity_type) REFERENCES entities (id, type),
    UNIQUE (application_id, method, path_template)
);

CREATE TABLE parameters (
    entity_id   uuid PRIMARY KEY REFERENCES entities(id) ON DELETE CASCADE,
    entity_type text NOT NULL DEFAULT 'parameter' CHECK (entity_type = 'parameter'),
    endpoint_id uuid NOT NULL REFERENCES endpoints(entity_id) ON DELETE CASCADE,
    name        text NOT NULL,
    location    text NOT NULL CHECK (location IN ('query','body','path','header','cookie')),
    value_class text,
    reflected   boolean,
    FOREIGN KEY (entity_id, entity_type) REFERENCES entities (id, type),
    UNIQUE (endpoint_id, location, name)
);

CREATE TABLE technologies (
    entity_id   uuid PRIMARY KEY REFERENCES entities(id) ON DELETE CASCADE,
    entity_type text NOT NULL DEFAULT 'technology' CHECK (entity_type = 'technology'),
    name        text NOT NULL,
    version     text,
    cpe         text,
    FOREIGN KEY (entity_id, entity_type) REFERENCES entities (id, type)
);

-- Identity (decision 11). No credential material: `secret_ref` is an op:// path
-- or a KEK-encrypted blob reference, and the agent-facing MCP layer never
-- selects it.
CREATE TABLE identities (
    entity_id        uuid PRIMARY KEY REFERENCES entities(id) ON DELETE CASCADE,
    entity_type      text NOT NULL DEFAULT 'identity' CHECK (entity_type = 'identity'),
    slot_name        text NOT NULL,          -- X-RedKraken-Identity value (Q15)
    class            text NOT NULL CHECK (class IN ('anonymous','user','privileged','service')),
    tenant_entity_id uuid REFERENCES entities(id) ON DELETE SET NULL,
    secret_ref       text,
    acquired_at      timestamptz,
    invalidated_at   timestamptz,
    FOREIGN KEY (entity_id, entity_type) REFERENCES entities (id, type),
    CHECK (class = 'anonymous' OR secret_ref IS NOT NULL)
);

CREATE UNIQUE INDEX identities_slot_idx
    ON identities (slot_name)
 INCLUDE (entity_id);   -- slot names are proxy-global; collisions across programs
                        -- would route one program's traffic with another's cookie
