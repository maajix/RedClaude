-- ---------------------------------------------------------------------------
-- 20260928T020000Z__the_corpus_is_refrozen_at_the_text_it_now_ships.sql
--                                                                   (ticket 97)
--
-- Ticket 97 rewrote twenty-nine Playbook bodies, and a Playbook body is a thing
-- this schema holds a digest of. `playbooks.source_sha256` is the document and
-- `playbooks.version` is the projection the model is actually handed, and the
-- header of 20260826T000000Z states the rule this file is the consequence of:
-- "editing the body moves both". A corpus edit that did not arrive here would
-- leave the catalogue selecting, grading and citing a text nobody ships.
--
-- `tools/check_coverage.py` is where that shows up, and it is worth naming
-- because it is what makes this file mandatory rather than tidy: it reads every
-- registration out of the concatenated migration corpus, compares each against
-- the bytes on disk, and refuses with "registered at X and ships Y". Its own
-- comment says last write wins, and that a Playbook re-frozen by a later ticket
-- is read at the digest that later ticket set. This is that later ticket.
--
-- AN UPDATE AND NOT AN UPSERT.
--
-- The eleven-column upsert those files use is how a Playbook ARRIVES: it states
-- the category, the risk, the effects, the baseline, the specificity and the
-- provenance because all of them are new. None of them moved here. Ticket 97
-- changed which instruction a step gives and changed nothing about what the
-- Playbook is for, what it may do, or what must be true of a subject before it
-- is offered -- so re-stating those columns would be this file claiming to
-- re-decide them, and a reader diffing it against the arrival file would have
-- to compare eleven values to find the two that moved.
--
-- Nothing is demoted by this and nothing should be.
-- `demote_edited_playbook` fires on exactly this UPDATE and returns on its
-- second arm for every row below: all twenty-nine are `draft` with no
-- `promoted_at`, because `stable` is unreachable until a fixture pair has run
-- against the exact text and no Playbook in this corpus has one. A row that HAD
-- earned standing would be demoted and would have a `playbook_demotions` row
-- filed at the digest it earned that standing under, which is the right
-- outcome and is why this file goes through the trigger rather than around it.
--
-- Depends on 20260826T000000Z, 20260827T000000Z, 20260828T000000Z,
-- 20260829T000000Z, 20260901T000000Z, 20260902T000000Z, 20260903T000000Z and
-- 20260904T000000Z, the eight files these twenty-nine rows arrived in, and on
-- 20260824T000000Z for the trigger above. A new file rather than an edit to any
-- of them: a recorded migration whose file has changed is schema drift and
-- `rk db migrate` refuses the whole corpus for it.
-- ---------------------------------------------------------------------------


-- ===========================================================================
-- 1. The twenty-nine, at the bytes they now are
-- ===========================================================================

-- Path, document digest, projection digest, in the order the corpus directory
-- sorts. Neither digest is written by hand: `Playbook.sha256` is taken over the
-- source bytes and `Playbook.version` over the projection, which is the thing a
-- model is handed and therefore the thing a selection has to be able to say it
-- read.
--
-- The count is asserted in the same statement that writes it. An UPDATE that
-- matches nothing succeeds, so a mistyped path would leave the old digest in
-- place and report success -- which is this file failing in exactly the way it
-- exists to prevent, one layer up. `GET DIAGNOSTICS` is the only place that
-- number is available, so the statement is inside a block rather than beside
-- one that would have to re-state all twenty-nine paths to check them.
DO $$
DECLARE n integer;
BEGIN
    UPDATE playbooks p
       SET source_sha256 = v.source_sha256,
           version       = v.version
      FROM (VALUES
            ('playbooks/api/playbook.md',
             'fb9b71cd4384b6b8341938e98eabe6ff31994d14335efa64b65585afe082d4e7',
             'e95cdb2be4b8b3d7beb5f0748bd283f970f84a06229766549c01c7dcc2684f11'),
            ('playbooks/api-authorization/playbook.md',
             'e7d0c7c4dbe310550def00fd6c53fe7b988d4da6aa8cc6f900ffb65325b49647',
             'e27f0c2e62a2160fd1ff949a9204fd9865c8595004ffe590f0b43272e5619330'),
            ('playbooks/authentication/playbook.md',
             'd6c57e8546481aa8881da71ea46f2dfbc4c2a7675b0319c42a00a366455043b6',
             '68ffc9b0ebfe543f9b8f0a8050f89906227d92001986fe40a995250872addff9'),
            ('playbooks/browser-framing/playbook.md',
             '6c8c696e024a59108b274eea08a73cb03c26e15eae4221056f47d7325b97642b',
             '1eded40c2e2891448d1e6d3ce5c7d020deb4b9176a825221949749fc40842539'),
            ('playbooks/browser-realtime/playbook.md',
             'f491247c11bdde2b7efc9a7391253da724197814f114de0f661da9ad610707be',
             '23c1a0f66654b4cb76e457c78ac9366c086c761c127c3dc8e13bb4e871d7def6'),
            ('playbooks/browser-storage/playbook.md',
             'b969edec2994ff8859f7017cb82489ffd6a8783281f044ff3d689578dbfbecd9',
             'f4f43b26446df6591e6feb1eabb049875ecfe1f0445cbdf28fa17fe61d1d03fe'),
            ('playbooks/cms/playbook.md',
             '1dbf0bb72892e7ff82f9b5ebf31d98439beb046734d83a7a1eb2f54039243643',
             '719f3a3a6e104088d3ec5c281826435001c39006dcc961117b55d5dc1623f389'),
            ('playbooks/command-directory-injection/playbook.md',
             '5ba5a003e06bf93efd4eccea582780d062f41867b4c45f050b0025e6274d0c8d',
             '3f81fd1c364a806c69d7a63ef40c6093a3bd4f64b688873af1fc2de3aed1c071'),
            ('playbooks/deserialization/playbook.md',
             'd0d4f3b17b6a3a31d9a5c6f156ac566eb5596b5b5ef6113b34d66b92934afce2',
             '3c95d087ad634748d88b3780b09fd07b5d92cb3f3c73aadf1b3a0dcdc0c37a4a'),
            ('playbooks/exceptional-conditions/playbook.md',
             'c6674e7bd53eb17c264f287ab31d9aa10b9ba44bf90728c513ecd2e0fc5dbaad',
             'd4644ed68b3f928f0eb639971e6102c62abcb8693d178eed5e5186057b1caf7f'),
            ('playbooks/file-resolution/playbook.md',
             '2a78322dda9c1bc24824ecd7d20b662bf09fa821458ceede20517d5705f8c51a',
             '7894e144fa1bb026b37312ca22d1d1bb3081c7ddaedd64081b9ccd98af8f29ce'),
            ('playbooks/graphql/playbook.md',
             'cdd8dcf6e262f0c1474c927853f6c6f96eb116da2dd1884742f8a70b6b1adf35',
             'af8bf6afab311cc1efa97193c75d4867b94c2c79f1010f573ed7469eda7829bd'),
            ('playbooks/grpc/playbook.md',
             '24e7e87f9e965802a85ea35faad867a1378ce4aa76b1cbfdfa8f2da3665375c6',
             'a01fef7e904c8180f824cedb9b47a62454dea940cb005da6162280911881c34c'),
            ('playbooks/identity-lifecycle/playbook.md',
             '0c027ddcce6aefddc562692785d4f7560d9a462cad14483d14f4829759027777',
             '355490848b42305377eb52a5be8c7dec129191047cf52ceb313a37fb5420a7ac'),
            ('playbooks/identity-parsing/playbook.md',
             'd6ba8d7fa539c4f3ecff595c2af3ff5d6f2b44ccbed1ac02867afe0cd10595cb',
             '9a1a02568efdbc9f93384474fb0c2774518fd31c821f3e0eb7a7d4551482fd00'),
            ('playbooks/information-disclosure/playbook.md',
             'fd6c61f33029fd01f8f52cf9cef9fa9fbc4f073a8d3947743c4faf8a82bbf023',
             'b4e4ca78ea1a7e65baf3fa6c30f6526eb9d81f4a087fd31e85634d3a28e32b45'),
            ('playbooks/jwt-jose/playbook.md',
             'a045ca99dab9c9144eb0071649842e2221edb038cde30fd71a4b5aebf77d6576',
             '55692f83eb499f2deea492c41a4bf0098b0a1cbfbc1b6531a7798d9cacc6b5fc'),
            ('playbooks/logging/playbook.md',
             'ad2a91b737b7e0346231a4e053bd0bdf741a3bcd1e979b7e8d107102d15bdafd',
             '7c5ec989d51361aa873316f4cc2e3342d783139c604f7b4bf7f9496493b18989'),
            ('playbooks/nosql-injection/playbook.md',
             '59b8cd48f0af4145307abb62a6712a8aedd21783bf7c063c385169c64011c769',
             '7c8c2818904d5f03be26581ed7e5925dacdb784cf8452ebf65aa4ca653e222a5'),
            ('playbooks/object-ownership/playbook.md',
             'ca23748c88329a9f932c76b5fe66d83753a2fdf10aecd56354d68533ec0ea53e',
             'd3bc44a7cb1e3a3b4e3ce4cd879a013da5267b617a1ccc0fc29ed68acd0939f0'),
            ('playbooks/orm/playbook.md',
             'cb456b677ac45005b7026cc2eed7f8f20e5f9d2a99d72f5d06aa4c2b549e6593',
             'fcb36f805ace0a76a8e9363f5b19155d6ef3cbfdd0dda51b054a0ccf07f92503'),
            ('playbooks/payment-workflows/playbook.md',
             'afdf22a24475abb4378a146fef7b86aa595703c38b8b9c5b56391ab440006b2c',
             'f4c382a0a8b3db3f2e2c7161cadf4495576085ebe529c62c3547e5954384c8e6'),
            ('playbooks/routing/playbook.md',
             '2368d25030a3f5b4ab4bbe6118269fe8f1f3e62b43b938474398b705048b2d45',
             'c4de9c1ba1721f073063f267a84f7ff2df1d868d3adf8638c313c34f072f5f8e'),
            ('playbooks/spreadsheet-injection/playbook.md',
             'd807336891d7ed9b51dbb3c18e4873cabad919350671548214da971a11a521ca',
             '17cb7128c9909a968f4d2cb1d86fef965a5615a67b5a6c64c5ee85da241710c8'),
            ('playbooks/sql-injection/playbook.md',
             'b262e279d54e33100001b80eeb603bedbcdedd9bd8e7ddbc992b4cd7fa16270d',
             '4413bd5b31231faceb33fa79bdde7608cb9a02cf033c658a71ba124a3e018602'),
            ('playbooks/ssrf-url-routing/playbook.md',
             '2ff8e70ad6e2848840329831e75bae5bca7d1095dfce804779b6a7e08f0608ac',
             '5f192b70ec199a6c64f8d989e597699a9b3468499c83494fcac3f096bf66ddcb'),
            ('playbooks/ssti/playbook.md',
             'e6a480a3a88aa734eeff5027844a84b93400cf09fc1f03a335c3ba6c6b9810ee',
             'b365058a2dd42d5824d4790eac4dd6859e782994ee216113faddb233626dbf11'),
            ('playbooks/structured-injection/playbook.md',
             '19b07f9230d480fea28fadd645db8860c5dce6d852f0281625898e0a3101f817',
             '12c672544ce12616af9122fa251031f10123dd8a9e89517e3cb1df38edaa821c'),
            ('playbooks/web-cache/playbook.md',
             'fe5a82176664b8246caf3c40799851e39955746ae1c8f1141706cc5e195922b2',
             'a80884fae11c952df96be677e682dd284354e2476732b9818ce9e0c7a706f264')
           ) AS v(path, source_sha256, version)
     WHERE p.path = v.path;

    GET DIAGNOSTICS n = ROW_COUNT;
    IF n <> 29 THEN
        RAISE EXCEPTION 'ticket 97 re-froze % Playbook(s) and rewrote 29', n
          USING DETAIL = 'a path above names no row in this catalogue, so a '
                         'body that shipped rewritten is still registered at '
                         'the text it no longer is',
                ERRCODE = '23514';
    END IF;
END $$;


-- ===========================================================================
-- 2. And the one Skill, for the same reason
-- ===========================================================================

-- `use-identity` step 2 told the model to call `mcp__rk2__http_request` with
-- `identity_slot` set and gave a JSON example using it -- a call the closed
-- schema refuses before a handler exists to be confused by it -- so ticket 97
-- rewrote it and its digests moved with it. `skills` freezes exactly the two
-- `playbooks` does, and `CleanCreationTest` compares the registry against what
-- `redkraken.skill` derives from the file, so a Skill edit that stopped here
-- would be found by that test rather than by a reader.
--
-- The upsert this time, not an UPDATE, because that is what
-- 20260822T000000Z's statement is and because this row has been re-registered
-- once before by exactly that path: that file updated the registration
-- 20260811T150000Z wrote, for a text that named a tool this roster never
-- served. Two of the five columns are re-stated unchanged for the same reason
-- the digests are re-stated at all -- the upsert has one shape, and the one it
-- has is the whole row.
INSERT INTO skills (name, enabled, description, source_sha256, version, evidence_profile_id) VALUES
    ('use-identity', true,
     'Authenticated target requests through a named RedKraken Identity. Use when testing logged-in reachability, comparing two leased Identities, or following redirects and subresources within an authenticated session.',
     'c5a93f0c5a17fb057d7e8791b229b4b723e36b529991600fdacdae89545b9e5f',
     '8e864dc7a95028781e85484d5c840304d1c069d8ab14ffb59c46c35ba56f7585', 'identity_differential')
ON CONFLICT (name) DO UPDATE SET
    enabled             = excluded.enabled,
    description         = excluded.description,
    source_sha256       = excluded.source_sha256,
    version             = excluded.version,
    evidence_profile_id = excluded.evidence_profile_id;

-- And the row the version is taken over, which is the reason the version moved
-- at all. `check_skill_registry` does not trust the number above: it re-derives
-- it by hashing `kind || ' ' || path || ' ' || sha256` over this skill's
-- dependency rows, so the number and the row have to move together or the
-- standing check reports `version_disagrees` on every run. `use-identity` owns
-- no scripts and no references, so its manifest is this one line and its
-- version is the digest of that line -- which is why re-stating `source_sha256`
-- in `skills` above is not enough on its own.
INSERT INTO skill_dependencies (skill_name, path, kind, sha256) VALUES
    ('use-identity', 'SKILL.md', 'instruction',
     'c5a93f0c5a17fb057d7e8791b229b4b723e36b529991600fdacdae89545b9e5f')
ON CONFLICT (skill_name, path) DO UPDATE SET
    kind   = excluded.kind,
    sha256 = excluded.sha256;


-- ===========================================================================
-- 3. Nothing else moved
-- ===========================================================================

-- The two claims the header makes about what this file is not. A demotion row
-- written here would mean a Playbook had standing this edit took away, which
-- would be true and would also mean the header's second paragraph is wrong
-- about the corpus -- so it is asked rather than asserted in prose. And the
-- catalogue is still fifty: an UPDATE cannot add a row, but a reader of this
-- file two tickets from now is entitled to see that stated by the file that
-- touched twenty-nine of them.
DO $$
DECLARE n integer;
BEGIN
    SELECT count(*) INTO n
      FROM playbook_demotions
     WHERE cause = 'edited' AND demoted_at > now() - interval '1 minute';
    IF n > 0 THEN
        RAISE EXCEPTION '% Playbook(s) lost standing to ticket 97''s edit', n
          USING DETAIL = 'the header says every row here is draft with no '
                         'promoted_at, and a demotion says otherwise',
                ERRCODE = '23514';
    END IF;

    SELECT count(*) INTO n FROM playbooks;
    IF n <> 50 THEN
        RAISE EXCEPTION 'the catalogue holds % Playbooks and ticket 97 rewrote 29 of 50', n
          USING ERRCODE = '23514';
    END IF;
END $$;
