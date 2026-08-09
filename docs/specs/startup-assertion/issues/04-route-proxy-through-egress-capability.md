# 04 — Carry the egress capability through the proxy

**What to build:** Migrate the real runtime-to-proxy request path onto capability-backed receipts so a valid active tool run can make its request and subresource requests without revealing the capability to the model or target.

**Blocked by:** 02 — Add a capability-backed receipt path beside legacy writes

**Status:** resolved

- [x] The runtime network adapter receives the plaintext capability only in memory and sends it to the local proxy as `Proxy-Authorization: RedKraken <capability>`.
- [x] The proxy redacts and strips the proxy-auth header before forwarding; neither the target fixture, receipt nor logs observe its value.
- [x] Every outbound exchange resolves the capability and independently canonicalises and scope-checks the actual request before egress.
- [x] One capability is limited to its program, tool run and active lifetime but may back multiple in-scope subresource receipts produced by that tool run.
- [x] A request with a missing, fabricated, mismatched, expired or cleared capability is refused before the target is contacted.
- [x] Finishing, denying, parking or aborting the tool run clears the capability and prevents its reuse.
- [x] A local end-to-end probe demonstrates one permitted request plus subresources through the new writer and proves that a different run cannot reuse the capability.
- [x] The legacy direct-write path remains temporarily available only for the contract ticket; all known serving callers have migrated to the capability path.

## Comments

Implemented on branch `implementation/receipt-capability`, commit `d550fd3`, on
2026-08-09. The composed proxy proof records two independently authorised
subresource receipts from one capability and refuses missing, fabricated,
cross-program, expired and cleared capabilities before target contact.
