-- ---------------------------------------------------------------------------
-- 20260930T000000Z__the_desync_playbook_is_refrozen_at_the_text_it_ships.sql
--                                                          (ticket 96, late)
--
-- Ticket 96 gave a request a body, and it wrote the desync refusal into the one
-- file whose reader meets it: `playbooks/http-desync/playbook.md` now says, in
-- its own body, that this harness will not carry the split request a desync
-- proof needs. That was the right place for the sentence and the wrong way to
-- ship it. `playbooks.source_sha256` is a digest of that document, registered
-- when the corpus was frozen, and `tools/check_coverage.py` compares the two on
-- every run. A Playbook whose text moved and whose digest did not is a
-- catalogue asserting it knows what a model will read while the model reads
-- something else.
--
-- The gate caught it, which is what the gate is for, and it caught it several
-- commits after the fact, which is the part worth writing down: `check_coverage`
-- was not in the set of gates that pass was run against. It is registered at
-- `40c933022d7b` and ships `56baeca84765`, and this file closes that.
--
-- Nothing about the Playbook's meaning changes here. The `version` digest moves
-- with the source because it is derived from it, and neither number is a
-- decision -- they are measurements of a document that was already correct.
--
-- Depends on 0035's `playbooks` catalogue and on whatever most recently froze
-- this row. It touches one row, and it asserts that it touched one.
-- ---------------------------------------------------------------------------

DO $$
DECLARE n integer;
BEGIN
    -- The path and the digest adjacent, in a `VALUES` row, because that shape is
    -- the registration `tools/check_coverage.py` reads. The gate never connects
    -- to a server: it concatenates the migration corpus and matches the literal
    -- pair, last write winning in apply order. An `UPDATE ... SET` naming the
    -- path in its `WHERE` would put the same two values in the same file and
    -- the gate would still report this Playbook unregistered, so the shape is
    -- load-bearing rather than stylistic.
    UPDATE playbooks p
       SET source_sha256 = v.source_sha256,
           version       = v.version
      FROM (VALUES
            ('playbooks/http-desync/playbook.md',
             '56baeca84765f27ceb622c8bf936e4ddd6b596be8f70211b5b38d9cbc83fbd32',
             '59507e2a244f941305cc907d9765d16ccfdc938208683d1bc6d6541a8c2aec92')
           ) AS v(path, source_sha256, version)
     WHERE p.path = v.path;

    -- The count is asserted in the statement that writes it, on
    -- `20260928T020000Z`'s reason: an UPDATE that matches nothing succeeds, so a
    -- mistyped path would leave the stale digest in place and report success --
    -- this file failing in exactly the way it exists to prevent.
    GET DIAGNOSTICS n = ROW_COUNT;
    IF n <> 1 THEN
        RAISE EXCEPTION 'ticket 96: re-froze % desync Playbook row(s) and meant one', n;
    END IF;
END $$;
