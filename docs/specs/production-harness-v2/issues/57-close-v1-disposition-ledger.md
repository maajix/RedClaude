# 57 — Close the 223-row v1 disposition ledger

**What to build:** Prove that the complete v1 Agent, Skill and Playbook knowledge surface has a verified v2 outcome and that the production catalogue contains every planned web/API replacement.

**Blocked by:** 48 — Rework v1 Agents, Skills, references and sink packs; 49 — Migrate recon, API and protocol Playbooks; 50 — Migrate authentication and Identity Playbooks; 51 — Migrate authorization and business-logic Playbooks; 52 — Migrate browser and client-side Playbooks; 53 — Migrate injection Playbooks; 54 — Migrate server-side, file and disclosure Playbooks; 55 — Migrate platform and supply-chain Playbooks; 56 — Migrate HTTP integrity and parsing Playbooks.

**Status:** ready-for-agent

- [ ] The final ledger reconciles exactly 11 Agent definitions, 28 Skill directories, 60 Playbook topics, 112 operator references, 9 sink packs and 3 reserved files.
- [ ] Exactly 49 in-scope web/API Playbooks exist, validate, are loadable and have passing hash-specific production evaluations.
- [ ] Ten Android Playbooks, two Android Skills, one Android Agent and the 39 Android operator references carry explicit reversible scope-retirement records; one remaining topic is absorbed as reference material.
- [ ] All 73 in-scope references and 9 sink packs resolve from at least one bounded Skill or Playbook reference and none is injected globally.
- [ ] There are zero missing replacements, stale source hashes, dangling Skills, unloadable stable Playbooks, duplicate dispositions or unresolved manifest rows.
- [ ] Adding, deleting or modifying a v1 knowledge artifact makes the coverage gate fail with the exact unclassified identity.
