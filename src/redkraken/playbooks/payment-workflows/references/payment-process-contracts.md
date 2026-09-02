# Payment process contracts

Maintainer material for ticket 231. It is not projected to an Agent; the
executable procedures and safety limits are in `playbook.md`.

Sources checked 2026-09-01:

- Stripe, Supported currencies:
  https://docs.stripe.com/currencies
- Stripe, Idempotent requests:
  https://docs.stripe.com/api/idempotent_requests
- Stripe, API v2 overview:
  https://docs.stripe.com/api-v2-overview
- Adyen, Currency codes and minor units:
  https://docs.adyen.com/development-resources/currency-codes
- PayPal, Idempotency:
  https://developer.paypal.com/reference/guidelines/idempotency/
- Stripe, Prorations:
  https://docs.stripe.com/billing/subscriptions/prorations
- Stripe, Billing mode comparison:
  https://docs.stripe.com/billing/subscriptions/billing-mode/compare

## Amount representation is a provider contract

Stripe APIs expect integer minor units, but zero-decimal currencies and special
charge/payout cases change the exponent. Adyen also uses minor units and
documents provider-specific differences from ISO 4217, including ISK. A test
therefore records the provider, API family, operation type and documented
exponent together. "ISO says" is not a control for what a provider API accepts.

## Idempotency is scoped and expires

Stripe API v1 and v2 have different operation coverage and retention semantics.
PayPal support is API-specific and uses `PayPal-Request-Id`; its documentation
also distinguishes simultaneous requests. A method must state endpoint,
account or merchant scope, operation type, payload equality and retention
window. Replaying a key outside that contract cannot refute idempotency.

## Reconciliation is the verdict

The response to a create, capture or refund call is one view. The payment method
requires the commercial object, provider object, customer balance, internal
ledger and settlement/invoice view because partial failures occur between them.
The stable disagreement is evidence; an error response by itself is not.

## A recurring plan is a documented credit path

Stripe computes proration to the second and issues the unused portion of the
old price as a negative invoice line rather than a refund. The provider's own
worked example is the reason the plan-cycling arm exists: under
`billing_mode=classic`, an upgrade taken with `proration_behavior=none`
followed later by a downgrade taken with `proration_behavior=always_invoice`
credits the customer for time at a price they never paid, and Stripe prints the
resulting invoice total as -334. Under `billing_mode=flexible` the same
sequence nets to zero because the credit is computed from the price last
actually billed. Stripe documents the same asymmetry for an unpaid invoice: a
customer who changes plan while owing money for the current term can be
credited for unused time they have not paid for.

A second worked example on the same page covers a coupon spread across several
subscription items. Removing the cheaper item refunds -250 under the classic
mode and -417 under the flexible mode, because the two modes disagree about how
much of an `amount_off` coupon belonged to the removed item. Neither number is
a defect in Stripe. Both are the reason a reading must record which mode the
merchant configured before it calls an unexpected credit a Finding: the same
merchant code produces two legitimate totals.

## Techniques on record

Each entry is a disclosed defect in a merchant integration, not in a provider,
and each maps to one arm of the projected method.

- Client-carried quantity accepted as authoritative, with a negative value
  reducing the order total:
  [Upserve/OLO, 364843](https://hackerone.com/reports/364843).
- A seat, tier or plan identifier taken from the request rather than from the
  offer the caller holds:
  [Krisp, 1446090](https://hackerone.com/reports/1446090),
  [Acronis, 1403176](https://hackerone.com/reports/1403176).
- A single-use promotion applied past its own redemption ceiling, reported
  against the provider's own promotion-code implementation:
  [Stripe, 1717650](https://hackerone.com/reports/1717650).
- Concurrent redemption of one coupon, gift card or payout, which is the arm
  this Playbook explicitly refuses to run until ticket 232 lands:
  [Instacart, 157996](https://hackerone.com/reports/157996),
  [Reverb, 759247](https://hackerone.com/reports/759247),
  [HackerOne, 220445](https://hackerone.com/reports/220445).
- Billing documents reachable by identifier rather than by ownership, which is
  an `object-ownership` reading and is listed here only so a hunter routes it:
  [Shopify, 2207248](https://hackerone.com/reports/2207248).
- The concurrency technique itself, and why a burst is not the same evidence as
  a synchronised pair:
  [Smashing the state machine](https://portswigger.net/research/smashing-the-state-machine),
  with the teaching labs at
  [race conditions](https://portswigger.net/web-security/race-conditions) and
  [business logic vulnerabilities](https://portswigger.net/web-security/logic-flaws).
- Survey material for the discount, currency and stale-coupon arms:
  [price manipulation in e-commerce](https://www.intigriti.com/blog/news/top-6-price-manipulation-vulnerabilities-ecommerce),
  [exploiting business logic errors](https://www.intigriti.com/researchers/blog/hacking-tools/exploiting-business-logic-error-vulnerabilities),
  and the methodology chapter at
  [OWASP WSTG business logic testing](https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/10-Business_Logic_Testing/README).
- The reason the numeric-conversion arm reads the total instead of the response
  code: an integer overflow in a value field once minted money that no ledger
  had authorised:
  [value overflow incident](https://en.bitcoin.it/wiki/Value_overflow_incident).

## What the method deliberately refuses

Two published techniques are named in `playbook.md` only to be declined, and
the reason is evidentiary rather than squeamish. Farming a signup, referral or
first-order bonus across many identities proves nothing that one redemption and
the target's own published ceiling do not already prove, and it creates
accounts an operator then has to clean up. Accumulating a sub-unit rounding
difference over thousands of operations has the same property: the single
boundary comparison in the currency method is the evidence, and the loop only
adds monetary effect. Both are recorded as untested consequences instead.

## Review rule

Re-open these sources when the Playbook reaches `bb:stale_after`, when the
Program uses another provider, or when its published proration, coupon or
minor-unit rules differ from the defaults above. Stripe's two billing modes are
the fact most likely to have moved, because the classic mode is the one that
produces the surprising credit and the flexible mode is the one new merchants
are placed on.
