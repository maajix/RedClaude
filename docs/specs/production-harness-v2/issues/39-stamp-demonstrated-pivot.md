# 39 — Stamp a demonstrated pivot

**What to build:** Issue one runtime-authored pivot stamp only when a validated Test proves that a Finding provides a named capability under explicit conditions.

**Blocked by:** 29 — Deliver pending decisions, Halt and resume verbs; 37 — Validate a Finding through a blind validator.

**Status:** ready-for-agent

- [ ] A pivot proposal names its member Finding, subject, Identity, required capabilities, provided capability, scope and safety conditions.
- [ ] The runtime resolves one holding Test run whose assertions demonstrate the claimed transition rather than merely the member vulnerability.
- [ ] Grant, Program, Artifact, Receipt and current Finding validity are rechecked when issuing the stamp.
- [ ] The immutable stamp records exact member, Test, conditions, vocabulary and source hashes and is emitted only by runtime authority.
- [ ] Missing, inferred, cross-Program, expired-grant and invalidated-member pivots are refused.
- [ ] Repeating the same valid issuance is idempotent, while changed evidence requires a new stamp.
