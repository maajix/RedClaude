-- ---------------------------------------------------------------------------
-- 002_programs.sql   (ticket 06)
-- ---------------------------------------------------------------------------

CREATE TABLE programs (
    id           uuid PRIMARY KEY DEFAULT uuidv7(),
    slug         text NOT NULL UNIQUE,
    name         text NOT NULL,
    platform     text,
    scope_policy jsonb NOT NULL DEFAULT '{}'::jsonb,   -- grammar: ticket 26
    opened_at    timestamptz NOT NULL DEFAULT now(),
    closed_at    timestamptz,
    purge_after  timestamptz            -- set by retire_program(), not generated:
);                                      -- timestamptz + interval is STABLE, not IMMUTABLE

-- Labels are DB-assigned, per program, per prefix. They are the only ids an
-- agent ever sees or cites (decision 5).
CREATE TABLE label_counters (
    program_id uuid   NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    prefix     text   NOT NULL,
    next_val   bigint NOT NULL DEFAULT 1,
    PRIMARY KEY (program_id, prefix)
);

CREATE FUNCTION next_label(p_program uuid, p_prefix text) RETURNS text
LANGUAGE plpgsql AS $$
DECLARE v bigint;
BEGIN
    INSERT INTO label_counters (program_id, prefix, next_val)
    VALUES (p_program, p_prefix, 1)
    ON CONFLICT (program_id, prefix) DO NOTHING;

    UPDATE label_counters SET next_val = next_val + 1
     WHERE program_id = p_program AND prefix = p_prefix
    RETURNING next_val - 1 INTO v;

    RETURN p_prefix || v::text;
END $$;
