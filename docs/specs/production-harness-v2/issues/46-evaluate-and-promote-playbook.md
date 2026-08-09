# 46 — Evaluate and promote one Playbook

**What to build:** Run one Playbook against independently authored positive and adversarial fixtures and permit stable promotion only when this exact text is grounded, reproducible and precise.

**Blocked by:** 35 — Execute a structured Test through the replay Lane; 45 — Select one Playbook by Property class.

**Status:** ready-for-agent

- [ ] Fixture ground truth and class binding are independent of the Playbook author and include at least one relevant positive and one meaningful out-of-class negative.
- [ ] Each repeat records Playbook hash, fixture hash, selected Skills, grounded canonical claims, true positives, false positives and ungrounded claims.
- [ ] Promotion requires the configured repeated positive result, zero disqualifying ungrounded/off-class claims and runtime provenance for this exact text.
- [ ] A Playbook that always fires, under-declares outputs, lacks a control or is selected only because of its own fixture data fails.
- [ ] Editing, expiry or a later failing verdict demotes the Playbook from stable without deleting historical test runs.
- [ ] The end-to-end evaluator uses the production Agent, proxy, Test and promotion seams against synthetic fixtures.
