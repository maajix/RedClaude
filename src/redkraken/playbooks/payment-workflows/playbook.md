---
description: Ask whether a payment conserves the amount and state the target publishes, by changing one price, discount, credit, currency, idempotency key or transition at a time and comparing the target's authoritative order, provider and ledger views with a legitimate control.
bb:category: business_logic
bb:outputs: ["business_logic.quantity_or_price", "business_logic.replay", "business_logic.workflow_order"]
bb:triggers_all: ["authenticated_endpoint", "quantity_valued_parameter", "state_changing_method"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: approval_required
bb:effects: mutates_object
bb:baseline: pristine_surface
bb:status: draft
bb:stale_after: 2027-09-01
bb:provenance: Written for ticket 51 as the v2 replacement for v1's payment-workflows pack and rewritten for ticket 101 against the mined ledger. Ticket 231 turns the amount-only reading into a quality and integrity method for amount authority, discounts, credits, refunds, currency arithmetic, idempotency and reconciliation; workflow_order and replay are declared because those procedures settle those existing business-logic classes rather than relabelling every payment defect as quantity_or_price.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_differential", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "response_differential", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "response_differential", "polarity": "supports", "min_count": 1}]
bb:references: ["payment-process-contracts.md"]
---

# Ask whether the payment conserves money and state

A payment result is not the response to one POST. It is an agreement between
the commercial order, the payment provider object, the customer balance, the
internal ledger and the invoice or payout record. This Playbook changes one
input or one transition at a time and reads those authoritative views. A `2xx`
to an illegal request is not a defect if no money, entitlement or payment state
moved; a refusal is not proof of safety if another view already moved.

Every reading is one Test proposed through `mcp__rk2__propose_test`, and every
send uses `mcp__rk2__http_request`. Use a Program-owned sandbox, test mode or a
Program-supplied reversible fixture. One Task holds one Identity throughout.
No method below authorizes a live charge, payout, chargeback, merchant
notification or mutation of another customer's object.

## 1. Freeze the contract and the five authoritative views

Before changing anything, write the invariant in the target's own terms. Record
the currency, exponent or minor-unit rule, listed unit price, quantity range,
discount order, tax basis, credit ceiling, capture ceiling, refundable amount
and the legal state transitions. Take them from the served UI, API schema,
merchant documentation or a Program-supplied provider contract, never from a
generic assumption that all currencies have two decimals or all coupons stack.

Create one fresh test order or equivalent object and record five views where
the target exposes them:

1. commercial order: lines, discounts, tax, shipping, gross and status;
2. provider object: authorised, captured, refunded, currency and provider id;
3. customer account: balance, credit, coupon redemptions and entitlements;
4. internal transaction or ledger view: debit, credit, fee and net entries;
5. invoice, settlement or payout view: gross, fee, refund and payable amount.

Read each view twice with nothing between the reads. If a material field moves
on its own, wait only for the Program's declared consistency window and repeat.
If it still moves, the baseline is not pristine and no arithmetic below can be
attributed. This step grades nothing.

For every later method the basic Test shape is six actions: baseline state,
legitimate control operation, state after control, fresh-object state, one
variant operation, state after variant. Add a negative control where the method
names one. The assertion differences the smallest authoritative field that
states the invariant; it never differences whole bodies containing timestamps.

## 2. Server-authoritative price and quantity

Use one listed item and one value the published rule permits. The control sends
the ordinary client document and reads the server-computed total. On a fresh
cart the variant changes exactly one client-carried number: negative quantity,
zero where the minimum is one, maximum plus one, a price or `unit_price` the
interface never sends, or an amount whose scale the contract forbids. Read the
cart and order back after each operation.

The supported `business_logic.quantity_or_price` result is the server's
authoritative total, entitlement or balance reflecting the forbidden value.
The operation's response code is only context. A variant total equal to the
fresh baseline, with the legal control landing, refutes this reading. A route
that accepts both legal and illegal documents while moving neither is
inconclusive because it may be a validator or preview rather than the writer.

Do not sweep values. Use the two nearest boundaries, one legal and one illegal,
then stop at the first discriminating total. Remove every line created here.

## 3. Discount, credit and coupon composition

Write the published composition equation first: whether discounts stack,
whether credit is applied before or after tax and shipping, whether one coupon
is single-use, whether a refund restores credit, and whether a promotion is per
account, cart, order or payment. Then use a fresh object for each sequence.

Run these sequences one at a time:

- control: item -> one valid discount -> quote;
- variant: the same discount twice -> quote;
- control: item -> valid account credit -> quote;
- variant: discount -> credit and credit -> discount on twin objects;
- variant: coupon -> remove item -> re-add item -> checkout preview;
- variant: coupon -> cancel or refund -> reuse the coupon on a fresh order;
- variant: code A -> code B -> code A again, where the rule says one code
  replaces the last rather than adding to it;
- negative control: a never-issued code of the same shape -> quote.

The verdict is the discount total, credit balance and redemption count after
the sequence. A second `2xx` without a second reduction is not replay. A
second reduction for one single-use value is `business_logic.replay`; an order
whose composition violates the stated equation is
`business_logic.quantity_or_price`; reaching a discount or refund step before
its prerequisite is `business_logic.workflow_order`. File the class the
authoritative state proves, not whichever endpoint name sounded closest.

Bound the spend to two issued test values. A value not issued to the test
Identity parks under `credential_needed`; a shared promotion or production
credit parks under `third_party_impact` before it is sent.

A recurring plan is the same equation over time. Where the target sells one,
record the published plan price, the billing period and the proration rule
first. The control is one ordinary upgrade. The variants are a client-carried
plan or tier identifier naming a plan the caller was never offered, which is
section 2's reading; and one upgrade followed by an immediate downgrade on a
fresh subscription, read through the credit balance and the next invoice. A
cycle that returns more credit than it consumed is
`business_logic.quantity_or_price`. Run the pair once and stop.

## 4. Currency, minor units and rounding

Never infer an exponent from the display string. Build the smallest matrix the
target and provider actually support: one zero-decimal currency, one ordinary
two-decimal currency and, if supported, one three-decimal currency. Record any
provider exception separately; the same currency can have different charge and
payout rules, and a provider's exponent can differ from ISO 4217.

For each currency use amounts around one rounding boundary, all in test mode:
the smallest positive unit, one below the minimum charge if the provider states
one, and a calculation that lands exactly half a minor unit after a published
discount or tax. The control submits the integer minor-unit amount derived from
the target's quote. The variants change one representation at a time:

- major-unit decimal where the API declares integer minor units;
- the two-decimal representation of a zero-decimal currency;
- the wrong currency with the original amount unchanged;
- the correct currency with the exponent from another supported currency;
- line-level rounding versus total-level rounding on twin baskets;
- discount-before-tax versus tax-before-discount where the contract fixes one.

Read back the order amount, provider amount, customer balance and invoice total.
Supported means those views disagree or the customer receives value exceeding
the amount the authoritative quote requires. A consistent rejection, with the
legal control landing, refutes the arm. A one-minor-unit difference is evidence,
not "noise"; repeat it only on a fresh twin to rule out an eventually consistent
view, never to accumulate credit.

## 5. Capture, cancel and refund order

First walk one Program-approved test payment through its legal order and record
the state after each step: create -> authorise -> capture -> refund, or the
target's documented equivalent. That is the control state machine. Each variant
uses a fresh twin and attempts exactly one forbidden transition:

- capture before authorisation or after cancellation;
- capture twice, or capture more than the authorised remainder;
- refund before capture;
- two partial refunds whose sum exceeds the captured amount;
- full refund followed by another partial refund;
- cancel or void after capture;
- fulfilment, entitlement or invoice-paid state before provider confirmation,
  including a return or success URL the caller can visit or revisit directly;
- a late failure or cancellation event after a terminal success.

After every arm read both the provider object and the target's order or ledger.
The HTTP response is not the verdict. If the provider refused but the local
order advanced, or the provider moved and the local order did not, record the
split state and stop; a second transition would make the cause ambiguous.

An illegal state reached is `business_logic.workflow_order`. An amount above
the authorised, captured or refundable remainder is
`business_logic.quantity_or_price`. Duplicate application of one provider
operation is `business_logic.replay`. Cleanup uses only the target's documented
test cancellation or refund route and records any object it could not restore.

## 6. Idempotency keys and ambiguous outcomes

Use an operation the target documents as idempotent and one fresh key. The
baseline reads the object before the operation. The control sends the operation
once with the key, reads the object, then sends the identical request with the
same key and reads again. The second read must describe one effect. A near-miss
control reuses the key with one harmless parameter changed and must be refused
or return the first operation without a new effect.

Variants, each on a fresh object, are:

- the identical operation without an idempotency key;
- the same key under a second account, merchant or operation type where the
  target claims the key is scoped more narrowly;
- a retry after a Program-supplied timeout or simulated `5xx`, never a network
  fault manufactured against production;
- the same business operation reached through a second API version;
- the same money parameter twice, allowed then forbidden and then reversed,
  where the carrier preserves duplicate keys.

The authoritative count, capture/refund total or created-object list grades the
reading. Reusing one key and observing two effects is
`business_logic.replay`. A changed payload silently replacing the first effect
is also supported. A cached error response alone is not a defect unless it
creates or hides an additional business effect.

Duplicate JSON keys and HTTP parameter pollution remain a lead unless the
recorded carrier preserves both occurrences end to end. If one component
validates the first value and another charges the last, the two ordering arms
and the resulting total are the proof; without both, report parser ambiguity
and stop.

## 7. Mass assignment and numeric conversion

On a Program-owned object, compare an ordinary update with the same update
carrying one extra server-owned property: `price`, `unit_price`, `currency`,
`discount_total`, `credit`, `captured_amount`, `refunded_amount`, `owner`,
`tenant_id` or `role`. The controls are a certainly unknown property and a
published writable property. Read the object back; the response to the update
does not prove binding.

For numeric conversion, keep the operation non-settling and compare an ordinary
integer with one 96-digit integer, zero, the negative boundary, exponent form
and a decimal just beyond the declared scale. The controls identify whether the
server collapsed the value to zero, infinity, a signed wraparound or a rounded
integer. If any arm moves a real total, stop after the first read-back and use
section 2's cleanup.

An extra field that binds is handed to `api-authorization` as
`authorization.object_property_write`; the payment claim remains the forbidden
amount or state the read-back proves. Do not report one request as two classes
without two distinct settled claims.

## 8. Reconcile five views

Reconcile five views only after the Program's declared asynchronous window has
closed. Join them by provider id, order id, currency and operation id; never by
amount alone. For each authorised test payment write the conservation equations
the target claims, for example captured <= authorised, refunded <= captured,
customer debit = order gross, and payout net = captured - refunds - fees. Use
the target's equation where it differs.

The control is one ordinary completed test payment whose five views agree. The
variant is one earlier bounded method that produced a state change, followed by
the same five reads. A second control repeats those reads after the normal
settlement delay without another write. Difference individual fields and retain
all five provider and local identifiers.

A mismatch that heals inside the declared window is eventual consistency and
not a Finding. A stable mismatch is filed under the mechanism that created it:
forbidden amount, replay or workflow order. A chargeback, payout or live invoice
that cannot be created safely is an operator audit item only; this Playbook
reads an existing Program-supplied test record and never initiates one.

## 9. Claims, cleanup and stop conditions

Propose the settled claim with `mcp__rk2__propose_finding`. Use mass_assignment
for `business_logic.quantity_or_price`, replay for
`business_logic.replay`, and workflow_bypass for
`business_logic.workflow_order`, matching the catalogue mapping. Cite the
before state, legal control, one-variable variant and authoritative after state.

Every created cart line, order, discount reservation and test payment is named
in the report. Remove or cancel it through the target's own route. A refund is
cleanup only where the Program explicitly treats a test-mode refund as cleanup;
it is never invented to reverse a live charge.

Park before sending under:

- `scope_ambiguous` when a payment endpoint or provider environment is not
  explicitly in scope;
- `credential_needed` when the method needs a Program-issued coupon, credit,
  signed event or sandbox account;
- `third_party_impact` for a live charge, payout, chargeback, merchant or
  customer notification;
- `destructive_action` when no supported cleanup exists.

Two techniques stay outside this Playbook because their proof needs volume
rather than one comparison. Repeating a trial, referral or first-order bonus
across fresh identities is account creation at scale: name the ceiling the
target publishes, record the single legitimate redemption, and hand the
consequence to the Program instead of farming it. Accumulating a sub-unit
rounding difference over many operations is the same shape: prove the one
boundary in section 4 and state the accumulation as an untested consequence in
those words. Neither loop is run.

A true parallel Double-Spend or TOCTOU pair is not performed here. The current
door sends one request and waits for it, so sequential replay cannot prove a
race. Ticket 232 owns the bounded two-request primitive; until it exists, record
the sequential control and the untested concurrent hypothesis in exactly those
words.
