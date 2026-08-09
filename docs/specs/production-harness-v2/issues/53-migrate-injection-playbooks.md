# 53 — Migrate injection Playbooks

**What to build:** Deliver production-ready Playbooks and fixtures for seven v1 injection topics with explicit controls that distinguish parser behavior from generic errors, reflection and latency noise.

**Blocked by:** 46 — Evaluate and promote one Playbook; 48 — Rework v1 Agents, Skills, references and sink packs.

**Status:** ready-for-agent

- [ ] Command/Directory Injection, NoSQL Injection, ORM, Spreadsheet Injection, SQL Injection, SSTI and Structured Injection each exist as authored v2 Playbooks.
- [ ] Output Property classes distinguish query language, command execution, template evaluation, structured-header/document parsing and formula interpretation.
- [ ] Detection defaults to the least mutating action and requires explicit risk/grant metadata before any write or execution effect.
- [ ] Timing, boolean, error and content differentials each include a neutralized control and configured repeat policy.
- [ ] Fixtures include secure twins, noisy endpoints and decoy reflections so a Playbook that always fires fails precision evaluation.
- [ ] All seven exact hashes are role-loadable, selected only on matching facts and pass grounded positive/adversarial promotion gates.
