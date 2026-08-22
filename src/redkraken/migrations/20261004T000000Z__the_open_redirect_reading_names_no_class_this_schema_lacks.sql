-- ---------------------------------------------------------------------------
-- 20261004T000000Z__the_open_redirect_reading_names_no_class_this_schema_lacks.sql
--                                                                  (ticket 113)
--
-- Two corpus files and one migration comment routed open-redirect work into a
-- hole with three separate bottoms, and a reader met all three as one sentence:
-- "the class is `client_side.navigation` and the Playbook is `routing`", with a
-- `redirect_target` trigger under it.
--
--   (a) The class does not exist and never has. `property_class_families` holds
--       the eight rows `0018_vocabularies.sql:47-64` inserted and no later file
--       inserts a ninth, so there is no `client_side` family and therefore no
--       `client_side.` leaf under it.
--   (b) `redirect_target` is real and is listed by nobody. It is registered at
--       `0032_playbooks.sql:66`, it is computed from a `redirects_to`
--       relationship on every rebuild of `subject_facts`, and no row of
--       `playbook_triggers` names it. It is a fact this harness computes for no
--       consumer.
--   (c) `routing` asks a different question. It is `business_logic`, it emits
--       `business_logic.workflow_order`, and it triggers on `flow_step` and
--       `state_changing_method`. It has never asked where a browser is sent and
--       it cannot claim a class about it.
--
-- WHAT WAS DECIDED, AND WHY THIS FILE IS THE SMALL HALF OF IT.
--
-- Ticket 113 carries the argument in full and its outcome is that the reading
-- earns a new leaf in the existing `injection` family -- the browser's URL
-- resolver is an interpreter, and the three browser-side leaves minted before it
-- (`injection.client_channel`, `injection.client_path`,
-- `injection.foreign_resource`, all at `20260829T000000Z...:228-241`) are under
-- `injection` for exactly that reason. It is not folded into
-- `injection.url_authority`, because the two are settled by different proofs:
-- `url_authority` is a disagreement read off a response body
-- (`20260902T000000Z...:274-275`) and this one is a `Location` header or a
-- navigation a browser performed, and a fixture that graded both would have to
-- accept two proofs for one class. `routing` does not take the trigger, because
-- handing it a second output in another family would make it two Playbooks
-- sharing one name.
--
-- The leaf itself is not written here. It arrives with the fixture that grades
-- it, which is ticket 100's migration, and the Playbook that emits it and gives
-- `redirect_target` its first consumer is ticket 101's. A class inserted here
-- would be a promise with no path to it -- the thing `authentication.recovery_flow`
-- already is -- and `tools/check_wiring.py`'s W9 says so out loud for every
-- declared class no Playbook emits.
--
-- So what this file closes is the part that can be closed today: the corpus
-- stops asserting a class this schema does not hold. Both Playbook-side
-- sentences were rewritten to name no class for the browser side at all and to
-- stop sending the reading to `routing`, and the migration comment that repeated
-- the bad name is superseded here.
--
-- WHY THE COMMENT IS SUPERSEDED RATHER THAN CORRECTED.
--
-- The third site is `20260902T000000Z...:530-540`, a `--` comment above the
-- `playbook_references` insert. A recorded migration whose file has changed is
-- schema drift and `rk db migrate` refuses the whole corpus for it, so the
-- correction has to arrive as a new file. The house standard for that is
-- `20260922T060000Z__a_fixture_may_own_its_own_handshake.sql:100-104`, re-issued
-- by `20260926T000000Z` on the same reasoning: a `--` comment is dated by the
-- file it sits in, and a `COMMENT ON` has no date on it at all.
--
-- What is superseded is the class name and nothing else. The rest of that
-- comment is doing something different from the two Playbook pages and is
-- correct: it explains why a v1 page whose subject is graded elsewhere is
-- attached to `ssrf-url-routing` at all, and the answer -- "the disposition
-- ledger records where each v1 page went, not where its subject is graded" -- is
-- load-bearing for ticket 47's ledger. That sentence is promoted onto the live
-- table comment, where a reader of `\d+ playbook_references` meets it, instead
-- of being left to be found beside a class name that was never real.
--
-- WHY TWO DIGESTS MOVE.
--
-- `playbooks/ssrf-url-routing/playbook.md` and its `open-redirection.md`
-- reference both changed body text, and both are registered with a digest that
-- `tools/check_coverage.py` and `playbook_references` respectively compare
-- against the file this checkout ships. A document whose text moved and whose
-- digest did not is a catalogue asserting it knows what a maintainer will read
-- while the maintainer reads something else. Neither number is a decision; they
-- are measurements. Nothing else about either document changes: no frontmatter
-- field moves, `ssrf-url-routing` still emits `injection.url_authority` alone,
-- and `routing` is not touched by this file in any way.
--
-- Depends on 0018 (the families and the leaves), 0032 (`surface_facts`,
-- `playbook_triggers`, `playbook_outputs`), 20260823T000000Z (the
-- `playbook_references` table and the comment being replaced), 20260902T000000Z
-- (the reference rows and the `--` comment being superseded) and
-- 20260928T050000Z (the digests this file moves off). It writes two rows,
-- asserts that it wrote two, and adds no vocabulary and no grant.
-- ---------------------------------------------------------------------------


-- ===========================================================================
-- 1. The live comment says where a v1 page went, and stops saying where its
--    subject is graded
-- ===========================================================================

-- Ticket 45's sentence is kept whole, because it is still what this table is
-- for and it is the reason no column of it reaches `rk2_state`. What is added
-- is the second question a reader of this table actually asks -- why is a page
-- about somebody else's subject hanging off this Playbook -- answered with
-- 20260902's own reasoning, and then the one correction: the example that
-- comment reached for named a class this schema has never held.
COMMENT ON TABLE playbook_references IS
    'Ticket 45 criterion 2: human-only material, linked and hashed for a '
    'maintainer, absent from every surface a model reads. Not published to '
    'rk2_state on purpose -- the projection has no field it could occupy and '
    'the read surface has no row that would let it arrive another way. '
    'Attachment is provenance, not jurisdiction: a row records where a v1 page '
    'went, not where its subject is graded, which is why three of the four '
    'pages under ssrf-url-routing describe questions that Playbook does not '
    'ask. Ticket 113 supersedes one example of that in 20260902T000000Z, which '
    'said open-redirection.md is client_side.navigation and belongs to routing. '
    'The reasoning stands and the class name never did: there is no client_side '
    'family in property_class_families and so no such class, and routing emits '
    'business_logic.workflow_order on flow_step and state_changing_method. '
    'Where that reading belongs is settled by ticket 113, the leaf and its '
    'fixture are ticket 100 and the Playbook that emits it is ticket 101.';


-- ===========================================================================
-- 2. The Playbook is registered at the text it now ships
-- ===========================================================================

-- The path and the digest adjacent, in a `VALUES` row, because that shape is
-- the registration `tools/check_coverage.py` reads: it concatenates the
-- migration corpus and matches the literal pair, last write winning in apply
-- order, and never connects to a server. An `UPDATE ... SET` naming the path in
-- its `WHERE` would put the same two values in the same file and the gate would
-- still report this Playbook unregistered, so the shape is load-bearing rather
-- than stylistic.
--
-- The count is asserted in the statement that writes it, on 20260928T020000Z's
-- reason: an UPDATE that matches nothing succeeds, so a mistyped path would
-- leave the stale digest in place and report success -- this file failing in
-- exactly the way it exists to prevent.
DO $$
DECLARE n integer;
BEGIN
    UPDATE playbooks p
       SET source_sha256 = v.source_sha256,
           version       = v.version
      FROM (VALUES
            ('playbooks/ssrf-url-routing/playbook.md',
             '74756d30627e31dd3c136d0322231e59145cbbbe22bf0de5382b553b33b9a269',
             '429c2cd22ab0d5a0a848173d016affd04c0e3ed65fe960ae60585c8370d16e0e')
           ) AS v(path, source_sha256, version)
     WHERE p.path = v.path;

    GET DIAGNOSTICS n = ROW_COUNT;
    IF n <> 1 THEN
        RAISE EXCEPTION 'ticket 113: re-froze % Playbook row(s) and meant one', n
          USING DETAIL = 'the path above names no row in this catalogue, so a '
                         'body that shipped rewritten is still registered at '
                         'the text it no longer is',
                ERRCODE = '23514';
    END IF;
END $$;


-- ===========================================================================
-- 3. The reference page is registered at the bytes it now is
-- ===========================================================================

-- The same argument one table down. `playbook_references.sha256` is what tells
-- a maintainer whether the page moved since it was attached, and the page did
-- move: the section that used to route the browser side to a class that does
-- not exist is replaced by one that says what was decided and what has not
-- landed yet. A stale hash here would say that section is still the old one.
DO $$
DECLARE n integer;
BEGIN
    UPDATE playbook_references r
       SET sha256 = v.sha256
      FROM (VALUES
            ('playbooks/ssrf-url-routing/references/open-redirection.md',
             '0a10ef08841f1591c75d467eeff4e38953a03dac1b710944dfc4f78e5d2db95e')
           ) AS v(path, sha256)
     WHERE r.path = v.path;

    GET DIAGNOSTICS n = ROW_COUNT;
    IF n <> 1 THEN
        RAISE EXCEPTION 'ticket 113: re-hashed % reference row(s) and meant one', n
          USING DETAIL = 'the path above names no attached reference, so the '
                         'page a maintainer opens no longer matches the digest '
                         'that was recorded when it was attached',
                ERRCODE = '23514';
    END IF;
END $$;


-- ===========================================================================
-- 4. The migration refuses to finish if any clause of the new comment is false
-- ===========================================================================

-- A comment and two digests, so the only thing that can make this file wrong is
-- the schema disagreeing with what it now says. Every clause is asked of the
-- catalogue rather than assumed: the absent family, the untouched Playbook it
-- used to be routed to, the fact with no consumer, and the two rows above.
DO $$
DECLARE
    v_comment  text;
    v_outputs  text[];
    v_triggers text[];
    v_digest   text;
BEGIN
    -- The comment this file exists to write, read back rather than trusted.
    v_comment := obj_description('playbook_references'::regclass, 'pg_class');
    IF v_comment IS NULL OR v_comment NOT LIKE '%ticket 113%' THEN
        RAISE EXCEPTION 'the live comment on playbook_references does not carry the supersession'
          USING ERRCODE = '23514';
    END IF;
    IF v_comment NOT LIKE '%where a v1 page went, not where its subject is graded%' THEN
        RAISE EXCEPTION 'the supersession dropped the disposition reasoning it was told to keep'
          USING DETAIL = 'ticket 47''s ledger rests on that sentence and only the '
                         'class name in 20260902T000000Z was wrong',
                ERRCODE = '23514';
    END IF;

    -- Bottom one. The whole reason the old sentence was unfollowable: a family
    -- that is not there, and so a leaf that cannot be under it.
    IF EXISTS (SELECT 1 FROM property_class_families WHERE id = 'client_side') THEN
        RAISE EXCEPTION 'a client_side family exists after all, and this file understates the vocabulary'
          USING ERRCODE = '23514';
    END IF;
    IF EXISTS (SELECT 1 FROM property_classes WHERE id LIKE 'client\_side.%') THEN
        RAISE EXCEPTION 'a client_side leaf exists after all, and this file understates the vocabulary'
          USING ERRCODE = '23514';
    END IF;

    -- Bottom three. `routing` is left exactly as it was, which is the point of
    -- choosing to correct the two sentences rather than the shipped Playbook.
    SELECT array_agg(o.property_class ORDER BY o.property_class) INTO v_outputs
      FROM playbook_outputs o JOIN playbooks p ON p.id = o.playbook_id
     WHERE p.path = 'playbooks/routing/playbook.md';
    IF v_outputs IS DISTINCT FROM ARRAY['business_logic.workflow_order']::text[] THEN
        RAISE EXCEPTION 'routing emits %, so the reading was not corrected away from it',
                        coalesce(v_outputs::text, 'nothing')
          USING ERRCODE = '23514';
    END IF;

    SELECT array_agg(t.fact ORDER BY t.fact) INTO v_triggers
      FROM playbook_triggers t JOIN playbooks p ON p.id = t.playbook_id
     WHERE p.path = 'playbooks/routing/playbook.md' AND t.mode = 'all';
    IF v_triggers IS DISTINCT FROM ARRAY['flow_step', 'state_changing_method']::text[] THEN
        RAISE EXCEPTION 'routing requires %, and this file was not allowed to change that',
                        coalesce(v_triggers::text, 'nothing')
          USING ERRCODE = '23514';
    END IF;

    -- Bottom two, which this file does not close and says so. The fact is real
    -- and nothing lists it; ticket 101 is where it gets its first consumer, and
    -- if some earlier file ever gives it one this assertion is where that is
    -- found out and this comment is re-issued.
    IF NOT EXISTS (SELECT 1 FROM surface_facts WHERE id = 'redirect_target') THEN
        RAISE EXCEPTION 'redirect_target is not a surface fact, so 20260902''s trigger claim was wrong twice'
          USING ERRCODE = '23514';
    END IF;
    IF EXISTS (SELECT 1 FROM playbook_triggers WHERE fact = 'redirect_target') THEN
        RAISE EXCEPTION 'redirect_target has a consumer already, and ticket 113 records that it has none'
          USING ERRCODE = '23514';
    END IF;

    -- Section 2, read back. The digest is the one this checkout ships and the
    -- Playbook still emits one class, so nothing was folded into it on the way.
    SELECT source_sha256 INTO v_digest
      FROM playbooks WHERE path = 'playbooks/ssrf-url-routing/playbook.md';
    IF v_digest IS DISTINCT FROM
       '74756d30627e31dd3c136d0322231e59145cbbbe22bf0de5382b553b33b9a269' THEN
        RAISE EXCEPTION 'ssrf-url-routing is registered at %, not at the text this file froze',
                        coalesce(v_digest, 'no row at all')
          USING ERRCODE = '23514';
    END IF;

    SELECT array_agg(o.property_class ORDER BY o.property_class) INTO v_outputs
      FROM playbook_outputs o JOIN playbooks p ON p.id = o.playbook_id
     WHERE p.path = 'playbooks/ssrf-url-routing/playbook.md';
    IF v_outputs IS DISTINCT FROM ARRAY['injection.url_authority']::text[] THEN
        RAISE EXCEPTION 'ssrf-url-routing emits %, and the browser reading was not to be folded into it',
                        coalesce(v_outputs::text, 'nothing')
          USING ERRCODE = '23514';
    END IF;

    -- Section 3, read back.
    SELECT sha256 INTO v_digest
      FROM playbook_references
     WHERE path = 'playbooks/ssrf-url-routing/references/open-redirection.md';
    IF v_digest IS DISTINCT FROM
       '0a10ef08841f1591c75d467eeff4e38953a03dac1b710944dfc4f78e5d2db95e' THEN
        RAISE EXCEPTION 'open-redirection.md is attached at %, not at the bytes this file hashed',
                        coalesce(v_digest, 'no row at all')
          USING ERRCODE = '23514';
    END IF;
END $$;
