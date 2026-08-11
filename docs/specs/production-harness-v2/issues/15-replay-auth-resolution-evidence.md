# 15 — Replay auth-resolution evidence in production

**What to build:** Promote the sanitised credential-vector evaluator into production so maintainers can verify the exact allow/refuse result for the measured SDK/CLI pair without credentials, SDK startup or network access.

**Blocked by:** 02 — Boot an installable `rk doctor`.

**Status:** resolved

- [x] One immutable manifest contains exactly the 17 measured case identities, runtime pair, symbolic inputs, retained-evidence digest and normalized wire outcomes.
- [x] A private pure evaluator returns deterministic structured violations for every single and mixed vector without modeling credential precedence.
- [x] First-party subscription OAuth is the only allowed measured outcome; alternate auth, provider routing, destination override, startup denial and absent requests remain distinct refusals.
- [x] Only the measured empty API-key case is treated as unset; unmeasured empty watched values fail closed.
- [x] Replay reads neither operator home state nor raw captures and imports no SDK or side-effecting probe code.
- [x] Missing, duplicate, additional or changed cases fail before verdict comparison, and the publishable fixture passes secret scanning.

## Comments

Implemented on branch `implementation/startup-assertion` in commits `be02876`
and `b8647cf` on 2026-08-11. The application now ships one digest-pinned
measurement manifest and a private standard-library evaluator. Nine focused
tests cover the exact 17-case set, literal structured records, mixed-vector
ordering, the empty-value asymmetry, changed-manifest refusal, positive-request
requirements, effect corroboration against each vector's measured wire shape,
ambient-dependency exclusion and fixture sanitisation. The installed-package
test also replays all 17 cases under isolated Python.

The full suite is 534 tests, green with 14 environment-dependent skips.
`tools/check_baseline.py` reports `classifications=10 regressions=7
artifacts=223`; `python3 -m compileall -q src/redkraken tests` is clean because
the repository has no configured typechecker. Gitleaks scanned the publishable
measurement directory with no leaks. Final independent Standards and Spec
reviews both pass with zero remaining findings.
