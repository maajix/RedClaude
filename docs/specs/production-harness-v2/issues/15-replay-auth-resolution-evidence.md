# 15 — Replay auth-resolution evidence in production

**What to build:** Promote the sanitised credential-vector evaluator into production so maintainers can verify the exact allow/refuse result for the measured SDK/CLI pair without credentials, SDK startup or network access.

**Blocked by:** 02 — Boot an installable `rk doctor`.

**Status:** ready-for-agent

- [ ] One immutable manifest contains exactly the 17 measured case identities, runtime pair, symbolic inputs, retained-evidence digest and normalized wire outcomes.
- [ ] A private pure evaluator returns deterministic structured violations for every single and mixed vector without modeling credential precedence.
- [ ] First-party subscription OAuth is the only allowed measured outcome; alternate auth, provider routing, destination override, startup denial and absent requests remain distinct refusals.
- [ ] Only the measured empty API-key case is treated as unset; unmeasured empty watched values fail closed.
- [ ] Replay reads neither operator home state nor raw captures and imports no SDK or side-effecting probe code.
- [ ] Missing, duplicate, additional or changed cases fail before verdict comparison, and the publishable fixture passes secret scanning.
