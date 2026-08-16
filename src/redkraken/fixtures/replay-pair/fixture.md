---
description: A coupon API where a code is worth its value once, served twice from one source, one variant holding the check and the write together and the other leaving a gap between them.
bb:kind: own_pair
bb:classes: ["business_logic.replay"]
bb:subject: /coupons/redeem
bb:facts: ["authenticated_endpoint", "json_request", "state_changing_method"]
bb:identities: ["alice"]
bb:provenance: Written for ticket 51 against the ticket 18 vocabulary, from the class description rather than from any Playbook; no upstream corpus.
---

# One coupon, one balance, one lock

`POST /coupons/redeem` takes `{"code": ...}` and adds the coupon's value to the
account. `GET /account` is the count: the balance and the list of codes already
redeemed. Two codes are issued, `fix-alpha` and `fix-beta`, each worth the same,
so a reading has one for the sequential control and a second, unspent one for
the concurrent pair.

Both variants answer `401` to a session nobody issued, `404` to a code that was
never issued, and `409` to a second sequential attempt at a code already spent.
Both run the same three statements in the same order with the same gap between
the check and the write. The only difference between them is one lock:

* **vulnerable** holds nothing, so two requests inside the gap both read
  "unspent" and both write. The balance moves twice for one coupon.
* **secure** holds a mutex across the check and the write, so the second request
  finds the coupon spent and answers `409`. The balance moves once.

## What the ground truth claims, and what it does not

`business_logic.replay` is the whole of it. The vulnerable variant applies one
single-use action more than once, which is the class's description, and nothing
else here is a defect.

The sequential refusal is on both variants on purpose. An application that
accepted the same coupon twice in a row would have no single-use rule at all, so
the pair would be grading nothing, and a claim of replay against it would be
right for the wrong reason.

Timing is not what separates the variants. Both sleep for the same `GAP` in the
same place and both answer at the same speed, so a run that reports a
`timing_differential` here has measured the sleep. The evidence is the balance
in `GET /account`.

Neither variant issues its own coupons, moves money outward, or notifies
anything. The balance is a number in one process, which is what makes this
safe to grade repeatedly.

## Why there is no route that puts a coupon back

The other two business-logic pairs end with a cleanup -- `DELETE /cart/items/{sku}`
on one, `DELETE /checkout` on the other -- and this one deliberately does not.
A coupon that could be un-redeemed is not single-use, so a reset route would
hand a reading a way to restore the invariant that no real target offers, and a
Playbook that learned to reach for it would be reading a fixture rather than an
application. The two codes are the whole budget instead: one is spent by the
sequential control and one by the concurrent pair, which is what bounds the
mutation without pretending it can be undone.

## Why the gap is a sleep

The window in real code is a database round trip, and the defect is that nothing
holds the two statements together across it. A fixture that closed the window by
being fast would be a fixture where the vulnerable variant passes by luck, and
the pair would grade the scheduler rather than the lock. `GAP` is 50ms: long
enough that two loopback requests land inside it every time, short enough that a
whole reading costs nothing.
