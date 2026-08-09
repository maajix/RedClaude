# 51 — Migrate authorization and business-logic Playbooks

**What to build:** Deliver production-ready Playbooks and fixtures for the four v1 topics that compare object ownership, function access, workflow invariants and concurrency effects.

**Blocked by:** 46 — Evaluate and promote one Playbook; 48 — Rework v1 Agents, Skills, references and sink packs.

**Status:** ready-for-agent

- [ ] API Authorization, Payment Workflows, Race Conditions and Routing each exist as authored v2 Playbooks with complete trigger, output, risk and evidence metadata.
- [ ] Authorization tests use explicit owner, foreign-owner and nonexistent controls and compare authoritative after-state rather than status code alone.
- [ ] Business-logic and payment tests state their invariant, pristine baseline, allowed mutation and cleanup before execution.
- [ ] Race-condition fixtures require a sequential control and prove the broken invariant rather than treating timing alone as the Finding.
- [ ] Routing and verb behavior remains within configured scope and cannot expand to arbitrary host or availability testing.
- [ ] All four exact hashes pass relevant positive and adversarial false-positive evaluation before stable promotion.
