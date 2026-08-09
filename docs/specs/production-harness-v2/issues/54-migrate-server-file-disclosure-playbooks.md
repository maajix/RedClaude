# 54 — Migrate server-side, file and disclosure Playbooks

**What to build:** Deliver production-ready Playbooks and fixtures for seven v1 topics covering server-side object processing, files, request forgery, exceptional behavior and exposed information.

**Blocked by:** 46 — Evaluate and promote one Playbook; 48 — Rework v1 Agents, Skills, references and sink packs.

**Status:** ready-for-agent

- [ ] Deserialization, File Resolution, File Upload, SSRF/URL Routing, Exceptional Conditions, Information Disclosure and Secrets each exist as authored v2 Playbooks.
- [ ] Playbooks distinguish artifact exposure, excess fields, error detail, path resolution, upload interpretation, document parsing and server-side request behavior through Property classes.
- [ ] SSRF and URL-routing evidence uses configured callback or controlled local targets and cannot authorize adjacent-host discovery or third-party contact.
- [ ] File and deserialization tests declare mutation, cleanup and execution ceilings before any higher-risk action.
- [ ] Fixtures include secure normalization, harmless error, decoy secret and non-fetching URL controls.
- [ ] All seven exact hashes pass loadability, relevant positive recall and adversarial precision gates before stable promotion.
