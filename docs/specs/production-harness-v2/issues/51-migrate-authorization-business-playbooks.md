# 51 — Migrate authorization and business-logic Playbooks

**What to build:** Deliver production-ready Playbooks and fixtures for the four v1 topics that compare object ownership, function access, workflow invariants and concurrency effects.

**Blocked by:** 46 — Evaluate and promote one Playbook; 48 — Rework v1 Agents, Skills, references and sink packs.

**Status:** resolved

**Deviation on criterion 6, inherited from 49 and 50:** the positive and adversarial
arrangement exists and is total; the evaluation that would grade it has not run, and cannot
run from this ticket. All four ship `draft`. `stable` is reachable only through
`playbook_test_verdict` returning `pass` for the exact text, and an evaluation run is an
Agent run against a fixture listening on loopback, which `scope.compile_policy` and
`authorize_identity_egress_address` both refuse. Ticket 78 is where that route is decided.
What moved is the measurement: the corpus is twenty Playbooks and twenty-one fixtures,
`playbook_fixture_binding` is still total over the fixture table, and each of the four new
fixtures is an out-of-class negative for the nineteen Playbooks that do not output its
class.

**Deviation on criterion 1, on which classes the four Playbooks output:** the ticket names
object ownership and function access, and neither is available. `authorization.object_ownership`
is 045's Playbook and `authorization.function_access` is 049's `grpc`, and the house rule
`playbook_fixture_binding` depends on is that a class has one Playbook -- two Playbooks
sharing a leaf would each be graded `in` on the other's target and neither result would mean
anything. So `api-authorization` outputs `authorization.state_transition` and `routing`
outputs `business_logic.workflow_order`. Both are the reading the v1 material actually
described: v1's IDOR page covered ownership and state together, and its routing pack was
about reaching a step of a flow rather than reaching a route the flow does not contain. The
other two are the ticket's own words: `payment-workflows` outputs
`business_logic.quantity_or_price` and `race-conditions` outputs `business_logic.replay`.

- [x] API Authorization, Payment Workflows, Race Conditions and Routing each exist as authored v2 Playbooks with complete trigger, output, risk and evidence metadata.
- [x] Authorization tests use explicit owner, foreign-owner and nonexistent controls and compare authoritative after-state rather than status code alone.
- [x] Business-logic and payment tests state their invariant, pristine baseline, allowed mutation and cleanup before execution.
- [x] Race-condition fixtures require a sequential control and prove the broken invariant rather than treating timing alone as the Finding.
- [x] Routing and verb behavior remains within configured scope and cannot expand to arbitrary host or availability testing.
- [ ] All four exact hashes pass relevant positive and adversarial false-positive evaluation before stable promotion. **Partial:** the fixtures exist and grade offline; the production evaluation waits on the route above. Ticket 78 closes it.

## Comments

Implemented on 2026-08-16.

### Four topics, four leaves, two of them not the ones the ticket named

The deviation above is the ticket's largest judgement, so it is worth saying what the four
Playbooks are about rather than only what they are not. `api-authorization` reads a write
against an object the caller owns and asks whether the object's *state* permitted it: a
shipped order that cancels is not an ownership defect, since the owner is the one who asked.
`routing` reads a step of a published flow and asks whether the steps before it were taken.
`payment-workflows` reads a number the target computes a total from. `race-conditions` reads
a single-use action applied twice.

Two of them are within a hair of a class somebody else holds, and both fixtures say so in
their own ground truth rather than leaving it to the reader. `state-transition-pair` answers
`403` to a foreign owner on both variants, so a run that reports
`authorization.object_ownership` against it has reported a control both halves enforce.
`workflow-order-pair` normalises `//`, `/./`, a trailing slash and mixed case identically on
both variants, so a run that reports a status-code bypass has reported the normaliser they
share.

### What tells the four apart on the Surface

Two new facts, and one that was computed but never read. `quantity_valued_parameter` is
`value_class = 'number'` -- the numeric sibling of `url_valued_parameter`, distinct from
`numeric_identifier`, which is about integers that name things rather than integers that are
counted. `flow_step` is `redirect_target` read at the other end of the same relationship: an
endpoint something else redirects to. `json_request` existed since 032 and no Playbook had
triggered on it.

Those three are what keeps `PlaybookCorpusSelectionTest` diagonal, and the diagonal is the
whole reason to care. Three of the four new subjects are authenticated writes with a request
body, which nothing in the existing vocabulary distinguishes. The value class separates the
payment one, the content type separates the concurrency one, and the redirect separates the
routing one. `api-authorization` is the fourth and it keys on a path segment.

That separation is a claim about the twenty documented subjects, not about every route a
recon pass can record. A real JSON write carrying a counted number satisfies both
`json_request` and `quantity_valued_parameter`, so `race-conditions` and `payment-workflows`
both select on it, and that is the ordinary case rather than a defect: triggers decide which
Playbooks are eligible and ranking decides which one runs first. What the diagonal buys is
that no *one* Playbook can pass the case by selecting everything -- each of the twenty has a
subject only it matches -- which is what the test is able to assert and all it asserts.

`flow_step` is the first trigger fact in that case's table that a Surface cannot carry
alone: something has to redirect to it. So the arrangement grew a second endpoint --
`POST /checkout/pay` on the routing Application, redirecting to the subject -- which is
where the fixture puts it too. It is an endpoint rather than a twenty-first Surface because
nothing asserts about it: it carries `redirect_target`, which no Playbook triggers on.

`object_identifier` is the fact this ticket had to stay off. 045's Playbook effectively
reserves it, so `api-authorization`'s subject carries a path segment whose value class is
`text`: an identifier a recon pass could classify as a uuid or an integer would make that
subject the object-ownership Surface as well, and two Playbooks would match it.

### The fixtures, and the control each one enforces on both variants

Every pair here holds one class, and the way to hold one class is to enforce everything else
identically on both halves. Each of the four does that at a different place.

`state-transition-pair` enforces authentication, existence and ownership on both variants:
`401` without a session, `404` for an order nobody has, `403` for Bob's order. The only
difference is whether a `shipped` order cancels, and the evidence is `GET /orders/{ref}`
afterwards rather than the status the cancel answered -- which is criterion 2's "authoritative
after-state rather than status code alone", written into the fixture rather than only into
the Playbook.

`quantity-or-price-pair` publishes its own rules. `GET /cart` returns the computed total and
the `MINIMUM`/`MAXIMUM` the target claims to enforce, so the invariant is the target's
statement rather than the reading's assumption, and the pristine baseline is a total of zero.
Both variants refuse an unknown sku and a non-integer quantity; only the secure one refuses a
quantity outside the published rule. `DELETE /cart/items/{sku}` is the cleanup, which is what
lets the pair be graded repeatedly.

`replay-pair` issues two coupons on purpose. One is spent by the sequential control -- both
variants answer `409` to a second sequential redemption, so an application with no single-use
rule at all could not pass for the vulnerable variant -- and the second is the unspent one the
concurrent pair uses. The gap between the check and the write is a 50ms sleep on both
variants, so the two answer at the same speed and a run reporting `timing_differential` has
measured the sleep. The evidence is the balance in `GET /account`: criterion 4's "prove the
broken invariant rather than treating timing alone as the Finding" is the balance moving twice
for one coupon.

It is also the one pair with no cleanup, which criterion 3 asks to be stated before execution
rather than discovered after. A coupon that can be un-redeemed is not single-use, so a reset
route would hand a reading a way to restore an invariant no real target restores, and a
Playbook that learned to reach for one would be reading a fixture rather than an application.
What is bounded is the spend instead: two codes, one per control, both named in the report,
and step 7 of the Playbook says so in those terms and tells a reading that has spent its
second item not to go looking for a third.

`workflow-order-pair` has two ordering rules and grades one. Pay-before-cart is refused
identically on both variants; confirm-before-pay is the difference. A pair that broke both
rules on one side would be grading how many rules a variant enforces rather than whether the
reading found one.

### Two requests, not twenty

`race-conditions` sends exactly two concurrent requests and its reference says why at length.
The v1 habit of firing twenty is a load test wearing a race's clothes: it is indistinguishable
from a rate-limit probe, it is the shape of traffic that gets a program's access pulled, and
it does not make the reading stronger -- two requests either both succeed against a single-use
action or they do not. The Playbook's own step order puts the sequential control first, so the
concurrent pair is only sent against an action that was already shown to be single-use.

That is also criterion 5's answer for this ticket's other half. `routing` reads path spellings
of a route the recon pass already recorded and verbs against that same route. It does not
resolve an origin address, downgrade a protocol, forge a proxy header or reach a route that is
not in scope -- those are `transport.request_framing`, `transport.header_policy` and
`authorization.function_access`, and `status-code-bypass.md` says which of the v1 page's halves
went where and why the other half stayed out. A `200` is not access: the reference's closing
rule is that a status change with no state change is a status change.

### The references

Five v1 pages came across, attached to two of the four Playbooks: `idor.md` and `uuids.md` on
`api-authorization`, `race-conditions-and-timing-attacks.md` on `race-conditions`, and
`http-attacks-verb-tampering.md` and `status-code-bypass.md` on `routing`. `payment-workflows`
shipped a README in v1 and no reference text, so it has nothing attached rather than a
placeholder.

Two of the five are split pages, and the split is the point of writing them fresh.
`race-conditions-and-timing-attacks.md` separates the race -- two requests inside a window,
which is `business_logic.replay` -- from stopwatch readings, which are a `timing_differential`
Property or `information_disclosure.identifier_oracle` and are not this Playbook's claim.
`status-code-bypass.md` separates the half about path spellings on a recorded route from the
half about origin addresses and proxy headers.

### What moved in the ledger

Nine rows crossed from promised to built: four `playbook:<name>` and five
`reference:playbooks/<topic>/references/<file>.md`, now citing `tests/test_playbook.py`
instead of `ticket:51`. The report's last line reads `built 89 promised 82 retired 52`.

Resolving this ticket came due on 48's rule for the third time, and moved the same example
test 49 and 50 moved. `test_a_row_that_names_an_open_migration_ticket_is_promised` had been
using `playbook:api-authorization` and `ticket:51`, which stopped being a promise here; it
uses `playbook:browser-framing` and `ticket:52` now.
