# 36 — Create a candidate Finding from a supported Hypothesis

**What to build:** Create one canonical candidate Finding from a Hypothesis settled by its own holding Test run without granting validation, reporting or exploitation status.

**Blocked by:** 35 — Execute a structured Test through the replay Lane.

**Status:** ready-for-agent

- [ ] Finding creation requires a supported Hypothesis and the exact holding Test run that settled it.
- [ ] The Finding records vulnerability class, affected subjects, identities, demonstrated behavior and evidence references using controlled vocabulary.
- [ ] Duplicate candidates for the same Program, Property class and affected cell merge or refuse deterministically.
- [ ] Candidate creation cannot set validated, reported, severity-from-impact or exploited state.
- [ ] An unrelated Receipt, adjacent Hypothesis, failed replay or model completion claim cannot satisfy the creation guard.
- [ ] Rejected candidate proposals remain auditable without polluting canonical Findings.
