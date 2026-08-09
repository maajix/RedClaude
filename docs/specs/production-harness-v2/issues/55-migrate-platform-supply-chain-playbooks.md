# 55 — Migrate platform and supply-chain Playbooks

**What to build:** Deliver production-ready Playbooks and fixtures for five v1 topics that reason about deployed platforms, orchestration, logging and dependency boundaries.

**Blocked by:** 46 — Evaluate and promote one Playbook; 48 — Rework v1 Agents, Skills, references and sink packs.

**Status:** ready-for-agent

- [ ] CMS, Deployment, Kubernetes, Logging and Supply Chain each exist as authored v2 Playbooks with attributable source references and expiry.
- [ ] Version or technology fingerprints create hypotheses only and can never confirm applicability or impact without exact configuration and Test evidence.
- [ ] Kubernetes and deployment checks remain limited to explicitly scoped web/API ingress and do not expand into infrastructure discovery.
- [ ] Logging and supply-chain fixtures distinguish public metadata from credential/artifact exposure and runtime reachability.
- [ ] Stale upstream knowledge or expired verification prevents stable selection until reevaluated.
- [ ] All five exact hashes pass role loadability, matching selection and positive/adversarial fixture promotion gates.
