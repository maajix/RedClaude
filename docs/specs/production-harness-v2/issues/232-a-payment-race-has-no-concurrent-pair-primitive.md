# 232 — A payment race has no concurrent-pair primitive

**What to build:** One bounded capability that releases exactly two declared
HTTP requests together, records both Receipts under one Test arm, and compares
the authoritative state afterwards so concurrent duplicate processing and
check-to-write consistency can be measured rather than described.

**Blocked by:** nothing.

**Status:** ready-for-agent

## The gap

`mcp__rk2__http_request` sends one request and waits for one response. Browser
steps are ordered, and scheduler concurrency is concurrency between isolated
runs rather than two sends under one Identity lease. The current
`race-conditions` Playbook therefore performs only sequential replay and
correctly refuses to call it a race.

For an imminent payment-process review the manual technique is known, but the harness
cannot record it honestly. A burst is not the answer: it resembles load and
cannot say which two requests shared the check-to-write window.

## Required shape

- Exactly two requests, each fully declared before release.
- One Identity, one target, one operation class and an operator-approved
  sandbox or reversible object.
- A barrier release with both response Receipts recorded independently.
- A distinct-item concurrent control and a sequential same-item control.
- The verdict comes from the target's authoritative balance, redemption count,
  capture total or refund total after the pair, never from two `2xx` responses.
- No widening from two requests to a burst without a new operator decision.

## Acceptance criteria

- [ ] The public tool contract can express and authorize the pair.
- [ ] Replay records both sends, both responses and their timing under one Test.
- [ ] A deterministic fixture is vulnerable only under the concurrent pair and
      secure under an atomic update.
- [ ] The sequential control cannot accidentally satisfy the race claim.
- [ ] Two-request and third-party-impact ceilings are enforced before egress.
