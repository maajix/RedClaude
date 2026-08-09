# 52 — Migrate browser and client-side Playbooks

**What to build:** Deliver production-ready Playbooks and browser fixtures for eight v1 topics whose evidence depends on origin, framing, messaging, script, storage or client-side navigation behavior.

**Blocked by:** 46 — Evaluate and promote one Playbook; 48 — Rework v1 Agents, Skills, references and sink packs.

**Status:** ready-for-agent

- [ ] Browser Framing, Browser Messaging, Browser Realtime, Browser Script, Browser Storage, Client-Side Path Traversal, External Resources and Web Cache each exist as authored v2 Playbooks.
- [ ] Each Playbook declares whether evidence requires browser, HTTP differential, DOM, storage, origin, framing or cache capabilities and is loadable by an appropriate role.
- [ ] Browser fixtures run through production containment and bind DOM, screenshot and network evidence to Receipts and Tool runs.
- [ ] Controls distinguish executable impact from reflection, browser policy from server policy and target behavior from proxy-induced protocol behavior.
- [ ] Cache, realtime and external-resource tests remain scope- and budget-bound and refuse uncontrolled third-party effects.
- [ ] All eight exact hashes pass positive and out-of-class adversarial evaluation with no human-only reference leakage into model projections.
