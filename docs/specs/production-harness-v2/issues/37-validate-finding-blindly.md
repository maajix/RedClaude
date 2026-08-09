# 37 — Validate a Finding through a blind validator

**What to build:** Give an independent validator only the canonical reproduction packet for one candidate Finding and let database rules decide whether its closed verdict can validate the Finding.

**Blocked by:** 18 — Compile and enforce the six-role roster; 36 — Create a candidate Finding from a supported Hypothesis.

**Status:** ready-for-agent

- [ ] The validation packet is built from an empty structure by a positive column allowlist over Finding, Hypothesis, Test, Test-run, Receipt and Artifact facts.
- [ ] Hunter reasoning, transcripts, prompts, pending-decision prose and unrelated Program data have no field or tool path into the packet.
- [ ] The validator runs as a fresh top-level session with no network, shell, source, Artifact browsing, Skill or delegation tools.
- [ ] Its only output is confirmed, refuted or insufficient plus closed failed-assertion identifiers.
- [ ] The verdict is stored as input while database constraints independently enforce the Finding transition.
- [ ] A smuggled field, foreign Receipt, missing holding replay or changed Artifact makes validation fail closed.
