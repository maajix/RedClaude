# 01 — Freeze the production boundary and v1 census

**What to build:** Establish an honest, machine-checkable starting point that distinguishes production code from design evidence and freezes the complete v1 knowledge inventory before implementation begins.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] Every existing implementation claim is classified as production, validated prototype, falsified prototype or documentation, and no prototype is described as a shipping runtime.
- [ ] A generated manifest records exactly 223 v1 artifacts with kind, relative source identity, line count and SHA-256: 11 Agent definitions, 28 Skill directories, 60 Playbook topics, 112 operator references, 9 sink packs and 3 reserved files.
- [ ] Regenerating the manifest is read-only and fails on missing, duplicate, added or changed source artifacts rather than silently updating the baseline.
- [ ] Every known startup, proxy, Receipt, Lane, encryption and actor-context review defect is registered as a required production regression case.
- [ ] A static production-boundary check rejects imports or execution dependencies on prototype, documentation, scratch or temporary trees.
- [ ] No engagement state, credential, raw capture or secret-bearing artifact is copied into the baseline, and secret scanning passes.
