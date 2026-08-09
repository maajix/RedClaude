# 01 — Replay the 17 auth-resolution cases offline

**What to build:** Give maintainers one credential-free CI check that replays the complete measured auth-resolution matrix and returns the same structured allow/refuse decision the startup assertion will use. The check must be grounded in sanitised wire facts rather than the current operator account or a hand-written expected verdict.

**Blocked by:** None — can start immediately

**Status:** resolved

- [x] One immutable manifest records its schema version, measured SDK/CLI pair, probe commit, retained-capture digest, symbolic inputs and normalised wire facts.
- [x] The manifest contains exactly the 17 case IDs named by the spec; missing, duplicate and additional cases each make CI fail before verdict comparison.
- [x] A private pure evaluator derives allow/refuse and deterministic `code`, `vector`, `source` and `effect` records for every case, including all mixed-vector cases.
- [x] First-party subscription OAuth is the only allowed measured outcome; absent requests, alternate auth, provider routing and destination override are refused with their distinct effects.
- [x] `ANTHROPIC_API_KEY=""` is the only measured empty value treated as unset; every other watched empty value fails closed.
- [x] The replay neither reads `HOME` nor imports side-effecting probe definitions, globs captures, opens the network, imports the SDK or requires credentials.
- [x] The checked-in fixture contains no header values, credential fingerprints, home-directory data, raw captures or mitmproxy key material, and a secret scan of the publishable fixture set passes.
- [x] The operator-run version-bump path can emit the same normalised manifest without making its raw evidence a repository fixture.

## Comments

Implemented on branch `implementation/startup-assertion`, commit `3a102f2`, on
2026-08-08. `python3 auth_resolution.py` replays 17/17 cases without `HOME`;
eight stdlib tests cover the exact case set, mixed-vector ordering, empty-value
asymmetry, settings isolation and a missing-request negative control. The
explicit four-batch normaliser reproduces the checked-in manifest byte for byte,
and Gitleaks reports no leak in `evidence/`.
