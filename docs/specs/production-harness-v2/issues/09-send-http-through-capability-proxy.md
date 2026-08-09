# 09 — Send one HTTP request through the capability proxy

**What to build:** Execute one allowed HTTP Tool run through the production proxy and persist an authoritative Receipt that no caller can fabricate or label allowed itself.

**Blocked by:** 07 — Encrypt credential-bearing wire Artifacts; 08 — Compile and enforce one Scope Policy.

**Status:** ready-for-agent

- [ ] An allowed Tool run mints a cryptographically random short-lived capability and stores only its digest canonically.
- [ ] The runtime sends the plaintext capability only to the local proxy, which resolves Program, Agent run, Tool run, Lane and current lifecycle before contacting the target.
- [ ] The target receives the intended request but never proxy authorization, capability material or internal control headers.
- [ ] The proxy creates one allowed Receipt through a database-owned writer and returns its stable identifier with the target response.
- [ ] Missing, fabricated, cross-Program, expired and cleared capabilities are blocked before target contact and create only auditable blocked records.
- [ ] The proxy role and even an owner-level negative fixture cannot directly insert a valid allowed Receipt outside the invariant.
