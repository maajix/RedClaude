# 06 — Remove raw allowed-receipt writes

**What to build:** Complete the contract half of the receipt-fence migration so an ungated request cannot egress or be represented by an allowed agent-lane receipt, even when a caller skips its expected hook.

**Blocked by:** 04 — Carry the egress capability through the proxy

**Status:** resolved

- [x] The proxy role has no direct `INSERT` privilege on receipts and every serving path uses the database-owned capability writer.
- [x] An `ENABLE ALWAYS` invariant rejects an allowed agent-lane receipt unless its tool run belongs to the same program, is active, has decision `allow` and carries a live capability digest.
- [x] The existing hole-open seed with an undecided tool run fails to load by database refusal even through the database-owner fixture loader.
- [x] Allowed receipts with no tool run, an undecided tool run and a fabricated capability each fail and contact no target.
- [x] No serving caller can supply its own `allowed` decision or tool-run identifier, and no legacy direct-write compatibility path remains.
- [x] Blocked requests use a separate writer that cannot create an allowed receipt and still leave an auditable blocked record.
- [x] Ticket 43's five refusal grounds, ticket 42's engagement checks and the receipt-integrity registry retain their prior behavior.
- [x] A registered standing check exercises each fence claim with a negative control that demonstrably turns it red.

## Comments

Implemented on branch `implementation/receipt-capability`, commit `d550fd3`, on
2026-08-09. The `rk2_proxy` writer-only role, database-owned writers, ALWAYS
invariant and K01-K10 negative controls pass the complete schema gate.
