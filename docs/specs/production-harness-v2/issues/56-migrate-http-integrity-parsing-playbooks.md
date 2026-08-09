# 56 — Migrate HTTP integrity and parsing Playbooks

**What to build:** Deliver production-ready Playbooks and fixtures for the three v1 topics whose findings depend on HTTP message boundaries, request integrity and parser disagreement.

**Blocked by:** 46 — Evaluate and promote one Playbook; 48 — Rework v1 Agents, Skills, references and sink packs.

**Status:** ready-for-agent

- [ ] HTTP Desync, Request Integrity and Request Parsing each exist as authored v2 Playbooks with complete metadata and scoped risk effects.
- [ ] Tests distinguish target behavior from proxy transformation and use proxy-internal transport observations where interception would invalidate the claim.
- [ ] Smuggling, coalescing, host/header, parameter and integrity variants use controlled local fixtures and explicit negative baselines.
- [ ] Availability-impacting request patterns are absent unless separately granted and bounded.
- [ ] Protocol claims cite exact request/response bytes and transport path rather than banner, generic error or race-only behavior.
- [ ] All three exact hashes pass relevant positive and adversarial evaluation before stable promotion.
