# 45 — Select one Playbook by Property class

**What to build:** Ingest one production Playbook and select its model projection for a matching subject using Property class, Surface facts, role, risk, Skills, conflict, status and expiry.

**Blocked by:** 33 — Promote an evidence-backed Hypothesis; 44 — Compile capability-based Skills.

**Status:** resolved

**Deviation on criterion 1:** conflict is derived, not declared. `bb:conflicts` is a
refused key in `playbook.py`, and `playbooks_conflict()` (032) decides from the pair's
`baseline` and `effects`. A declared list would be a second statement of the same fact,
and the two would drift the first time a Playbook's effects changed without its list
being edited.

- [x] Playbook metadata declares Property class, trigger facts, output classes, risk effects, baseline, required Skills, evidence expectations, conflicts, provenance and expiry.
- [x] Human-only reference material is structurally absent from the model projection while remaining linked for maintainers.
- [x] Selection filters by computed facts, named Property class, compatible role, risk ceiling, complete Skill loadability, status and expiry before applying a strict small cap.
- [x] Selected Playbook and Skill hashes are frozen onto the Task so later edits cannot change what a running Agent received.
- [x] Missing triggers, dangling Skills, unloadable combinations, expired text, forbidden risk and deterministic conflicts are refused or omitted with typed reasons.
- [x] A matching and non-matching synthetic subject prove useful selection without loading the full catalogue.
