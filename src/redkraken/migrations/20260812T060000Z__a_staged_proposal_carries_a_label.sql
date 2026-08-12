-- ===========================================================================
-- Production harness 19 -- a staged proposal carries a label like every other row
-- ===========================================================================
-- 020 registered the prefix -- `INSERT INTO label_prefixes VALUES ('proposals',
-- 'PR')` -- and created `proposals` with `label text NOT NULL` and no default,
-- and did not attach the trigger that turns the first fact into the second.
-- Nothing noticed, because 020 created the table and ticket 19 is the first
-- code to insert into it.
--
-- The registration says what the intent was. Every other labelled table gets
-- its label from `assign_label()` on insert (015 for the nine original ones,
-- 026 for `pending_decisions`, the artifact-reference migration for `AF`), and
-- the reason is the same each time: a label is what an agent and an operator
-- cite a row by, and a caller that supplies its own is a second opinion about
-- the namespace. The alternative here would have been for the runtime's insert
-- to call `free_label()` itself, which is that second opinion with extra steps.
--
-- `assign_label()` reads the kind from `TG_TABLE_NAME`, so this needs no
-- argument and no variant: the trigger function already resolves 'proposals' to
-- 'PR' through the row 020 wrote.

CREATE TRIGGER proposals_assign_label
    BEFORE INSERT ON proposals
    FOR EACH ROW EXECUTE FUNCTION assign_label();

-- The gate. Both halves, because either alone is a trap: a trigger with no
-- registered prefix raises at the first insert rather than at migration time,
-- and a registered prefix with no trigger is what this file is fixing.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger t
          JOIN pg_class r ON r.oid = t.tgrelid
         WHERE r.relname = 'proposals'
           AND t.tgname = 'proposals_assign_label'
           AND NOT t.tgisinternal)
    THEN
        RAISE EXCEPTION 'proposals does not assign its own label';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM label_prefixes WHERE kind = 'proposals') THEN
        RAISE EXCEPTION 'no label prefix is registered for proposals';
    END IF;
END $$;
