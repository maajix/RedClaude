# 42 — Render Findings and chains deterministically

**What to build:** Produce submission-ready Finding and kill-chain reports as deterministic projections of currently validated canonical rows.

**Blocked by:** 37 — Validate a Finding through a blind validator; 40 — Build and evaluate a sound kill chain.

**Status:** ready-for-agent

- [ ] The reporter is a pure renderer with no model, tools, target access or state mutation.
- [ ] Only validated Findings and sound, review-cleared chains can render; candidate, rejected, invalidated or gated records are refused.
- [ ] Reports include scope, affected subjects, reproduction, baseline/variant/controls, demonstrated impact, limitations, evidence identifiers and remediation context.
- [ ] Chain reports distinguish individually demonstrated composition from an actually executed end-to-end chain.
- [ ] Equivalent input rows in different order render byte-identically.
- [ ] Optional narrative is off by default and, when enabled, cannot introduce an identifier or factual field absent from the deterministic projection.
