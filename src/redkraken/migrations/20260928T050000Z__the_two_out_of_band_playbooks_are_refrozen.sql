-- ---------------------------------------------------------------------------
-- 20260928T050000Z__the_two_out_of_band_playbooks_are_refrozen.sql
--                                                                   (ticket 98)
--
-- The registry holds the bytes a Playbook shipped as, and ticket 98 moved two
-- of them. `webhooks` step 1 said "ask the runtime for a correlator" and now
-- names the verb that answers; `ssrf-url-routing` step 1 told a reading to use
-- "a second label under" the callback host, which is the thing `rk oob serve`
-- refuses to bind -- a publisher serves one hostname and has no labels to vary
-- -- and now says where its second name really comes from.
--
-- Both digests move, and both have to be written down here or `check_coverage`
-- reports a Playbook registered at text it does not ship. Neither is written by
-- hand: `Playbook.sha256` is taken over the source bytes and `Playbook.version`
-- over the projection, which is what a model is handed and therefore what a
-- selection has to be able to say it read.


-- ===========================================================================
-- 1. Two paths, at the bytes they now are
-- ===========================================================================

-- The count is asserted in the same statement that writes it, for the reason
-- ticket 97's re-freeze gives: an UPDATE that matches nothing succeeds, so a
-- mistyped path would leave the old digest in place and report success, which
-- is this file failing in exactly the way it exists to prevent.
DO $$
DECLARE n integer;
BEGIN
    UPDATE playbooks p
       SET source_sha256 = v.source_sha256,
           version       = v.version
      FROM (VALUES
        ('playbooks/ssrf-url-routing/playbook.md',
         '230cd69c80b98685c962cddfdc3b63d4ecc488e16be9dbbb5e0e5adce8839c6e',
         '843d0cf8fee0ebac25ffebaf428cfed8c4b34479b49b6fa254edc8750d884628'),
        ('playbooks/webhooks/playbook.md',
         '2e4ab6e4fae677ee6a6c0849d55014f9b6965b1cb243f2f2799d05a56d402428',
         'ae4fc32557c157437efa26c02fa16dd737aeaff2c75539fd3a3b511d76bce276')
      ) AS v(path, source_sha256, version)
     WHERE p.path = v.path;

    GET DIAGNOSTICS n = ROW_COUNT;
    IF n <> 2 THEN
        RAISE EXCEPTION 'ticket 98 re-froze % Playbook(s) and rewrote 2', n
          USING DETAIL = 'a path above names no row in this catalogue, so a '
                         'body that shipped rewritten is still registered at '
                         'the text it no longer is',
                ERRCODE = '23514';
    END IF;
END $$;


-- ===========================================================================
-- 2. Nothing else moved
-- ===========================================================================

-- Both rows are `draft` and neither was promoted, so a demotion written here
-- would mean this edit took standing away from a Playbook that had some -- and
-- would mean the paragraph above is wrong about what these two edits are.
DO $$
DECLARE n integer;
BEGIN
    SELECT count(*) INTO n
      FROM playbook_demotions
     WHERE cause = 'edited' AND demoted_at > now() - interval '1 minute';
    IF n > 0 THEN
        RAISE EXCEPTION '% Playbook(s) lost standing to ticket 98''s edit', n
          USING ERRCODE = '23514';
    END IF;
END $$;
