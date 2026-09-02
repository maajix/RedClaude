-- ---------------------------------------------------------------------------
-- 20270110T000000Z__a_payment_process_gets_methods_and_a_verified_webhook_arrives.sql
--                                                                   (ticket 231)
--
-- `payment-workflows` graded one edited quantity or price and a sequential
-- single-use replay, and named duplicate money parameters as a lead. `ticket
-- 231's rewrite turns amount, discount/credit/coupon, capture/refund,
-- currency/minor-unit, idempotency and five-view reconciliation into bounded
-- procedures, and the frontmatter that carries moved with the body: `bb:risk`
-- rises from `constrained` to `approval_required` (state moves real money, so
-- the runtime's floor rises with it), `bb:stale_after` moves out to
-- 2027-09-01, `bb:outputs` gains `business_logic.replay` and
-- `business_logic.workflow_order` beside `business_logic.quantity_or_price`
-- because sections 3, 5 and 6 now settle those existing classes rather than
-- relabelling every payment defect as one, and `bb:references` gains
-- `payment-process-contracts.md`, the maintainer note ticket 231 wrote and
-- attaches for the first time. `bb:evidence`, `bb:skills` and `bb:triggers_all`
-- did not move: the ledger rewrite already left evidence at
-- `response_differential` on every role (20261219T000000Z), and the trigger
-- and skill sets are unchanged from 20260828T000000Z.
--
-- `payment-webhooks` is new. `webhooks` concludes `injection.request_forgery`,
-- which is about an outbound request the target makes; this Playbook asks
-- whether a presented provider credential on an *incoming* payment event is
-- verified, which is `authentication.credential_verification` -- already
-- claimed by `authentication` itself and, like `payment-workflows`'s three
-- classes above, a class this corpus now lets a second procedure settle.
--
-- Depends on 20260828T000000Z (payment-workflows's arrival, source of the
-- `constrained`/2027-03-15 row this file replaces), 20261219T000000Z (the
-- corpus rewrite that last froze payment-workflows's text and evidence),
-- 20260823T000000Z (`playbook_references`, `playbooks.specificity`) and
-- 0018_vocabularies.sql (`authentication.credential_verification`,
-- `business_logic.replay`, `business_logic.workflow_order`, the
-- `response_differential` observation kind). Values are read out of
-- `playbook.PLAYBOOKS` after the on-disk rewrite, not typed by hand.
-- ---------------------------------------------------------------------------


-- ===========================================================================
-- 1. payment-workflows, re-frozen at the text and floor it now ships
-- ===========================================================================

-- An UPDATE and not an upsert: `category`, `effects`, `baseline`, `status` and
-- `bb:triggers_all`/`bb:skills` did not move, so only the five columns that did
-- are restated, for 20260928T020000Z's reason -- re-stating an unmoved column
-- would be this file claiming to re-decide it.
-- `('path', 'sha256'` as an adjacent literal pair, in that shape, is what
-- `tools/check_coverage.py`'s `REGISTRATION` pattern reads a registration out
-- of (its own comment: "the shape every migration writes and the only place
-- the two appear adjacent"), so the values travel through a `VALUES` tuple
-- rather than a plain `SET col = 'val' WHERE path = 'val'`.
DO $$
DECLARE n integer;
BEGIN
    UPDATE playbooks p
       SET source_sha256 = v.source_sha256,
           version       = v.version,
           risk          = v.risk,
           stale_after   = v.stale_after::timestamptz,
           provenance    = v.provenance
      FROM (VALUES
            ('playbooks/payment-workflows/playbook.md',
             'f7a7ec6e71b3f8bb26f74cd51325d75c951ff0076c22c6ca1696b208e0f9046e',
             '7dacc053a4995e4c4cb9109da8edab59270995f351b1805e0c5d82492d8a7204',
             'approval_required',
             '2027-09-01T00:00:00Z',
             'Written for ticket 51 as the v2 replacement for v1''s payment-workflows pack and rewritten for ticket 101 against the mined ledger. Ticket 231 turns the amount-only reading into a quality and integrity method for amount authority, discounts, credits, refunds, currency arithmetic, idempotency and reconciliation; workflow_order and replay are declared because those procedures settle those existing business-logic classes rather than relabelling every payment defect as quantity_or_price.')
           ) AS v(path, source_sha256, version, risk, stale_after, provenance)
     WHERE p.path = v.path;
    GET DIAGNOSTICS n = ROW_COUNT;
    IF n <> 1 THEN
        RAISE EXCEPTION 'ticket 231: payment-workflows row not found to re-freeze';
    END IF;
END $$;

-- Sections 3 and 5 now settle a duplicate coupon/credit sequence and an
-- illegal capture/refund transition on their own authoritative state, which is
-- `business_logic.replay` and `business_logic.workflow_order` -- already bound
-- to `replay-pair` and `workflow-order-pair` (20260828T000000Z) through
-- `race-conditions` and `routing`. Sharing the class is the point: those two
-- fixtures grade this Playbook's own procedure at the same bar rather than
-- payment-workflows inventing a fourth reading of a class two Playbooks
-- already settle. An INSERT rather than a DELETE+re-INSERT, because
-- `business_logic.quantity_or_price` is unmoved and only these two are new.
DO $$
DECLARE n integer;
BEGIN
    INSERT INTO playbook_outputs (playbook_id, property_class)
    SELECT p.id, v.property_class
      FROM playbooks p, (VALUES
            ('playbooks/payment-workflows/playbook.md', 'business_logic.replay'),
            ('playbooks/payment-workflows/playbook.md', 'business_logic.workflow_order'))
            AS v(path, property_class)
     WHERE p.path = v.path
    ON CONFLICT (playbook_id, property_class) DO NOTHING;
    GET DIAGNOSTICS n = ROW_COUNT;
    IF n <> 2 THEN
        RAISE EXCEPTION 'ticket 231: payment-workflows gained % output(s) and meant 2', n;
    END IF;
END $$;

-- The maintainer note ticket 231 wrote: provider currency/idempotency/
-- reconciliation contracts, checked 2026-09-01. Not projected to the model,
-- for 20260823T000000Z's reason -- `playbook_references` is absent from the
-- read surface on purpose.
DO $$
DECLARE n integer;
BEGIN
    INSERT INTO playbook_references (playbook_id, name, path, sha256)
    SELECT p.id, v.name, v.path, v.sha256
      FROM playbooks p, (VALUES
            ('playbooks/payment-workflows/playbook.md', 'payment-process-contracts.md',
             'playbooks/payment-workflows/references/payment-process-contracts.md',
             '45434366a1c8c66c2f72560b1ac378bfee848cf8d0d8f44b2677c67be7da2101'))
            AS v(playbook_path, name, path, sha256)
     WHERE p.path = v.playbook_path
    ON CONFLICT (playbook_id, name) DO NOTHING;
    GET DIAGNOSTICS n = ROW_COUNT;
    IF n <> 1 THEN
        RAISE EXCEPTION 'ticket 231: payment-workflows gained % reference(s) and meant 1', n;
    END IF;
END $$;


-- ===========================================================================
-- 2. payment-webhooks, as a row
-- ===========================================================================

-- `approval_required` and `mutates_object`, the same pairing 20260828T000000Z
-- gave payment-workflows: a verified event still applies a real transition to
-- a Program-owned object. `pristine_surface` for the same reason -- every
-- reading here is arithmetic on the authoritative payment state, and a second
-- writer underneath turns the difference into a statement about two runs
-- rather than one credential. `draft` with no `promoted_at`: `stable` stays
-- unreachable until a fixture pair has run against this exact text, and none
-- has.
INSERT INTO playbooks (path, source_sha256, version, category, status, stale_after,
                       risk, effects, baseline, specificity, provenance) VALUES
 ('playbooks/payment-webhooks/playbook.md',
  'da19536cc2702f347c0bff14ded4bce39b60e5261981fde99bf4567d0ed38b07',
  '8bf660ca60a8d7b7262c6f553cc56a7a546ab8fe5555dda4547f91c558de7fa3',
  'authentication', 'draft', '2027-09-01T00:00:00Z',
  'approval_required', 'mutates_object', 'pristine_surface', 3,
  'Written for ticket 231 from the current official Stripe, Adyen and PayPal webhook verification contracts. Kept separate from webhooks because that Playbook asks whether caller input controls an outbound server request and concludes injection.request_forgery; this one asks whether a credential on an incoming provider event is verified and concludes authentication.credential_verification.')
ON CONFLICT (path) DO UPDATE SET
    source_sha256 = excluded.source_sha256,
    version       = excluded.version,
    category      = excluded.category,
    status        = excluded.status,
    stale_after   = excluded.stale_after,
    risk          = excluded.risk,
    effects       = excluded.effects,
    baseline      = excluded.baseline,
    specificity   = excluded.specificity,
    provenance    = excluded.provenance;

-- Three facts, none of them `object_identifier`: an incoming delivery is
-- addressed by endpoint and event, not by a path segment naming an object.
-- `unauthenticated_endpoint` because the route carries no session or bearer
-- credential of its own -- the provider's signature is the credential this
-- Playbook grades, which is the whole reason it is not folded into a generic
-- unauthenticated-route reading.
INSERT INTO playbook_triggers (playbook_id, mode, fact)
SELECT p.id, v.mode, v.fact
  FROM playbooks p, (VALUES
        ('playbooks/payment-webhooks/playbook.md', 'all', 'json_request'),
        ('playbooks/payment-webhooks/playbook.md', 'all', 'state_changing_method'),
        ('playbooks/payment-webhooks/playbook.md', 'all', 'unauthenticated_endpoint'))
        AS v(path, mode, fact)
 WHERE p.path = v.path
ON CONFLICT (playbook_id, mode, fact) DO NOTHING;

-- One class, already claimed by `authentication` and bound to
-- `credential-verification-pair` (20260827T000000Z). Sharing it is the point
-- made above for payment-workflows: this Playbook settles the same class for
-- the one surface `authentication`'s own procedure does not reach, a
-- provider-signed delivery rather than a caller-held session credential.
INSERT INTO playbook_outputs (playbook_id, property_class)
SELECT p.id, v.property_class
  FROM playbooks p, (VALUES
        ('playbooks/payment-webhooks/playbook.md', 'authentication.credential_verification'))
        AS v(path, property_class)
 WHERE p.path = v.path
ON CONFLICT (playbook_id, property_class) DO NOTHING;

-- `compare-responses` differences the five authoritative views against a
-- control; `handle-untrusted-content` is what an unauthenticated route with a
-- provider-shaped body needs, the same pairing `webhooks` and `ssrf-url-routing`
-- already load through `web_hunter`.
INSERT INTO playbook_skills (playbook_id, skill_name)
SELECT p.id, v.skill_name
  FROM playbooks p, (VALUES
        ('playbooks/payment-webhooks/playbook.md', 'compare-responses'),
        ('playbooks/payment-webhooks/playbook.md', 'handle-untrusted-content'))
        AS v(path, skill_name)
 WHERE p.path = v.path
ON CONFLICT (playbook_id, skill_name) DO NOTHING;

-- `response_differential` on all three roles, the kind 20261107T000000Z's
-- `close_test_replay` writes for an action a differencing assertion names --
-- every arm here compares a control delivery's authoritative state against a
-- variant delivery's, never an unchanging invariant.
INSERT INTO playbook_evidence
        (playbook_id, to_status, role, observation_kind, polarity, min_count)
SELECT p.id, v.to_status, v.role, v.kind, v.polarity, v.min_count
  FROM playbooks p, (VALUES
        ('playbooks/payment-webhooks/playbook.md', 'refuted',   'variant', 'response_differential', 'refutes',  1),
        ('playbooks/payment-webhooks/playbook.md', 'supported', 'control', 'response_differential', 'supports', 1),
        ('playbooks/payment-webhooks/playbook.md', 'supported', 'variant', 'response_differential', 'supports', 1))
        AS v(path, to_status, role, kind, polarity, min_count)
 WHERE p.path = v.path
ON CONFLICT (playbook_id, to_status, role, observation_kind) DO NOTHING;

-- The Stripe/Adyen/PayPal contract note ticket 231 wrote, checked 2026-09-01.
INSERT INTO playbook_references (playbook_id, name, path, sha256)
SELECT p.id, v.name, v.path, v.sha256
  FROM playbooks p, (VALUES
        ('playbooks/payment-webhooks/playbook.md', 'provider-webhook-contracts.md',
         'playbooks/payment-webhooks/references/provider-webhook-contracts.md',
         'cb2166af8e270a863748d59bdd624389616ffbb3f1f7c302f45cda7293f2942a'))
        AS v(playbook_path, name, path, sha256)
 WHERE p.path = v.playbook_path
ON CONFLICT (playbook_id, name) DO NOTHING;


-- ===========================================================================
-- 3. The catalogue is fifty-one
-- ===========================================================================

DO $$
DECLARE n integer;
BEGIN
    SELECT count(*) INTO n FROM playbooks;
    IF n <> 51 THEN
        RAISE EXCEPTION 'ticket 231: the catalogue holds % Playbooks and this file arrives the fifty-first', n;
    END IF;
END $$;
