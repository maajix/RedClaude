# 43 — Export a redacted evidence bundle

**What to build:** Package one rendered Finding or chain with independently verifiable, redacted evidence that remains usable outside the running database without exporting credentials.

**Blocked by:** 07 — Encrypt credential-bearing wire Artifacts; 42 — Render Findings and chains deterministically.

**Status:** ready-for-agent

- [ ] The bundle contains the deterministic report, replay specification, assertion outcomes, Receipt metadata, redacted Agent-view Artifacts and content hashes.
- [ ] Encrypted wire credentials, capabilities, cookies, secret headers, runtime keys and unrelated Program material are excluded by default.
- [ ] A standalone verifier checks manifest completeness and every included hash without database access.
- [ ] Export rechecks current Finding or chain soundness and refuses stale, invalidated or review-gated material.
- [ ] Repeated export from identical canonical rows is deterministic apart from explicitly excluded packaging metadata.
- [ ] Synthetic credential markers remain absent from the unpacked bundle and secret scanning passes.
