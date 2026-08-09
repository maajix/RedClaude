# 38 — Authorize and prove impact separately

**What to build:** Turn an already validated detection into a separately authorized impact or exploitation Test so demonstrated impact can never be inferred from banners, errors or model confidence.

**Blocked by:** 29 — Deliver pending decisions, Halt and resume verbs; 35 — Execute a structured Test through the replay Lane; 37 — Validate a Finding through a blind validator.

**Status:** ready-for-agent

- [ ] Impact work is a new Task and immutable Test with an explicit risk class, expected side effect, cleanup and applicable operator grant.
- [ ] Missing or mismatched grant parks the Task for a human before any target request.
- [ ] Detection validation remains unchanged when impact execution is refused, inconclusive or unsafe.
- [ ] Demonstrated impact requires its own holding Test run, Receipts, after-state and cleanup evidence.
- [ ] Availability impact, third-party effects and out-of-scope pivots remain refused even when a lower-risk Finding is validated.
- [ ] Severity inputs distinguish demonstrated impact, constrained inference and program context with an auditable rationale.
