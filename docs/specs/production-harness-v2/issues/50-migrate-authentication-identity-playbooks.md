# 50 — Migrate authentication and Identity Playbooks

**What to build:** Deliver production-ready Playbooks and fixtures for the eight v1 topics concerning authentication, sessions, federation and identity lifecycle.

**Blocked by:** 46 — Evaluate and promote one Playbook; 48 — Rework v1 Agents, Skills, references and sink packs.

**Status:** ready-for-agent

- [ ] Authentication, Cookies, Identity Lifecycle, Identity Parsing, JWT/JOSE, OAuth, WebAuthn and Workload Identities each exist as authored v2 Playbooks.
- [ ] Playbooks distinguish credential verification, factor enforcement, federation trust, token scope, cookie scope, session lifecycle and identity parsing through controlled Property classes.
- [ ] Identity-pairing, response-comparison and flow-mapping capabilities use proxy-side Identity labels without exposing target credentials.
- [ ] Fixtures include positive, secure-control and out-of-class cases for enumeration, session handling, redirect trust and token/identity confusion.
- [ ] Risk effects correctly park credential-changing, session-mutating or third-party-impact actions when grants are absent.
- [ ] All eight exact hashes pass loadability, selection, grounded positive and adversarial precision gates before stable promotion.
