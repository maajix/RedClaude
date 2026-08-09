# 05 — Prove Program isolation and bounded reads

**What to build:** Allow compact state inspection by stable labels while proving that one Program cannot name, infer or mutate another Program's rows.

**Blocked by:** 04 — Create or resume a Program with the same command.

**Status:** ready-for-agent

- [ ] Two Programs may contain colliding short labels without either Program resolving the other's rows.
- [ ] Program identity is bound by runtime database context and is absent from every model-facing argument schema.
- [ ] Compact reads return stable labels, revisions, digests, counts and omission markers under configured size limits.
- [ ] Full records are retrievable by a stable label previously exposed to the same Program.
- [ ] Unknown and cross-Program labels return indistinguishable absence without leaking foreign existence.
- [ ] Repeating every read leaves database bytes and Lease state unchanged.
