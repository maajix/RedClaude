-- ---------------------------------------------------------------------------
-- 20261105T000000Z__the_five_high_yield_playbooks_are_refrozen.sql
--                                                     (tickets 101 and 109)
--
-- Ticket 101, for the five High-Yield Playbooks Arbeitsblock 3 grades and for
-- the five capability rows those five actually need. Four of the five bodies
-- moved and are re-registered here; `object-ownership` needed nothing and is
-- not in the list below.
--
-- What moved, per file:
--
-- `attack-surface` said "`jq` is the only tool in `offline_tools`". That was
-- true when it was written and is not now -- the registry holds six programs --
-- and the sentence it wanted is about the grant rather than the registry: this
-- Playbook executes as `recon`, and `recon` is granted `jq` and nothing else.
--
-- `browser-script` named no tool at all, because until ticket 99 there was no
-- tool to name. It names `mcp__rk2__browse` now. Every action it already
-- described -- `navigate`, `inject`, `click`, `wait_for`, `capture_dom` and the
-- `markup_injection` probe -- was inside the registered ten before and is
-- inside them still.
--
-- `payment-workflows` described a send and never named one. Ticket 96 put a
-- body on `mcp__rk2__http_request`, so the step says which call carries the
-- edited number instead of leaving the model to infer it.
--
-- `cookies` was the furthest from what this harness can do, and all four
-- repairs are subtractions. It asked for a step that reports the browser's own
-- cookie jar: no such action exists and none is being added, so the control is
-- now the request side, which is recorded for every request a mission makes. It
-- asked for a navigation "captured with its network log": there is no such
-- Artifact. It asked for a cross-site request from a second origin: this lane
-- hosts no origin and will not, so that half is described with its
-- preconditions rather than sent. And it told the model to name the Identity
-- slot in the plan, which tickets 97 and 131 settled the other way and which
-- the `mcp__rk2__browse` schema does not admit.
--
-- What did not move: no `bb:` field in any of the four, so no class, no
-- trigger, no evidence bar and no fixture binding changes. All five stay
-- `draft`. Ticket 109 is settled as pairwise in the same block and rewrote no
-- body, because none of these five instructs a comparison over three arms.
--
-- The digests are the whole point of the file. `playbooks.source_sha256` is a
-- digest of the document a model reads and `tools/check_coverage.py` compares
-- it against the file on disk on every run, so a body that moved without this
-- is a catalogue asserting it knows what a model will read while the model
-- reads something else.
-- ---------------------------------------------------------------------------

DO $$
DECLARE n integer;
BEGIN
    -- The path and the digest adjacent in a `VALUES` row, because that shape is
    -- the registration `tools/check_coverage.py` reads. It never connects to a
    -- server: it concatenates the migration corpus and matches the literal pair,
    -- last write winning in apply order.
    UPDATE playbooks p
       SET source_sha256 = v.source_sha256,
           version       = v.version
      FROM (VALUES
            ('playbooks/attack-surface/playbook.md',
             'f0db61c67f6b1d5385b7358b183d3a999bdf1fd7598b5c76c16d19a7f42ac298',
             '0fbd375aaf7c4cb3d39a3edfc3264b9cbac9eb781d593682d6f0a43f6625a91a'),
            ('playbooks/browser-script/playbook.md',
             '80c0a88e797ef810f0ab2e5f5b27162eaad647759443252649a4914d370e958f',
             '5a6e172deb691a25c0bd5854f9c2cd5f7ced6cd78c8774f9eb7d7ab314ab7182'),
            ('playbooks/cookies/playbook.md',
             'da38b28f515296f139badc2293feb82f1fcff615004457f6e50c4dded1bf35b6',
             '51d1a005281e6d7b4b0472a3715958fee8867c1d26f552690c408ae465d06cec'),
            ('playbooks/payment-workflows/playbook.md',
             '53d7ca20d3f15e041d2f52b98fc7079768083c37f7fa57ea5775d0639da8f956',
             'f7b75a24abd16260dc6c680d4480f2f099441ac9d85d06976ebe70a62d121ddf')
           ) AS v(path, source_sha256, version)
     WHERE p.path = v.path;

    -- Asserted in the statement that writes it: an UPDATE that matches nothing
    -- succeeds, so a mistyped path would leave a stale digest in place and
    -- report success -- this file failing in the way it exists to prevent.
    GET DIAGNOSTICS n = ROW_COUNT;
    IF n <> 4 THEN
        RAISE EXCEPTION 'ticket 101: re-froze % Playbook row(s) and meant four', n;
    END IF;
END $$;
