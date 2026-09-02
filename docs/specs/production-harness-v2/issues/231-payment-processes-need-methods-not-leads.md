# 231 — Payment processes need methods, not leads

**What to build:** A payment quality-assurance corpus that can grade incoming
provider webhook authenticity and replay separately from outbound webhook SSRF,
and that turns amount, discount, credit, refund, currency and reconciliation
questions into bounded baseline/variant/control procedures.

**Blocked by:** nothing.

**Status:** resolved

## Why now

`payment-workflows` can presently grade one edited quantity or price and a
sequential single-use replay. It names duplicate money parameters as a lead and
refuses concurrency. `webhooks` is exclusively an outbound request-integrity
Playbook. That leaves an imminent payment-process review without a routable method for
provider signature verification, delivery replay, currency minor units,
discount/refund sequences or reconciliation.

The important distinction is between a checklist and a Playbook. Each method
below must name the authoritative state, a positive control, a negative or
near-miss control, the one variable changed, the evidence that settles it and
the cleanup or stop condition. A list of payloads is not the requested result.

## Decision

Extend `payment-workflows` inside the business-logic family and add one
`payment-webhooks` Playbook inside authentication. Do not fold incoming webhook
verification into the existing `webhooks`: that Playbook concludes
`injection.request_forgery`, which is about an outbound request the target
makes. An unsigned incoming payment event instead asks whether a presented
provider credential is verified.

Provider-specific contracts live in a maintainer reference and the executable
procedure lives in the projected Playbook body. The model never receives a
reference, so putting the procedure only there would ship documentation and no
hunting capability.

## Acceptance criteria

- [x] `payment-workflows` provides bounded procedures for amount authority,
      discount/credit/coupon composition, capture/refund sequencing,
      currency/minor-unit/rounding boundaries, idempotency and reconciliation.
- [x] Incoming Stripe, Adyen and PayPal webhook methods each name the signed
      material, freshness or duplicate key, raw-body requirement and the
      authoritative state that proves whether processing occurred.
- [x] Forgery, exact replay, stale replay and out-of-order delivery are separate
      arms; a webhook's HTTP status is never treated as the business verdict.
- [x] Live charges, payouts, chargebacks, third-party notifications and secret
      extraction are refused. Test/sandbox events or Program-supplied signed
      fixtures are required.
- [x] The compiler, catalogue migration and database agree on both Playbooks'
      document digest, projection digest, triggers, outputs, skills, evidence
      and references.
- [x] The four repository gates pass, and the corpus applies from empty on a
      disposable PostgreSQL 18 / pgvector cluster.

## Resolution

The compiler and catalogue agree: `check_coverage` reports
`catalogue 51 skills 6 references 86`, all four gates return rc=0, and
`tests.test_playbook` plus `tests.test_coverage` pass with 99 tests.

The database half was run on 2026-09-02 against a disposable
`pgvector/pgvector:pg18` cluster. The first fresh application found that the
`VALUES` row used to re-freeze `payment-workflows` left `stale_after` as text;
PostgreSQL correctly refused to assign it to `timestamptz`, rolling the
migration back. The assignment now casts that value explicitly. A second clean
run passed 62 tests across `CleanCreationTest`, `PlaybookSelectionTest` and
`PlaybookCorpusSelectionTest`, including apply-from-empty, reapplication and the
full selection matrix. The last class now compares both Payment Playbooks'
document and projection digests, metadata, triggers, outputs, skills, evidence
and references directly against `playbook.PLAYBOOKS`; the acceptance criterion
therefore rests on a database assertion rather than on the static coverage
reader alone.

Both Playbooks and both reference notes now carry researched methods: coupon
alternation and plan-proration cycling in `payment-workflows`, scheme-tag and
empty-secret arms plus the too-generous-reading section in `payment-webhooks`.
The reference notes cite the disclosed reports and provider documentation each
arm was derived from.
