# 03 — Make `rk.agent_run()` own the effective launch

**What to build:** Make one runtime interface construct, assess and launch the exact agent-run configuration so callers cannot validate clean descriptions and then start different SDK options.

**Blocked by:** 01 — Replay the 17 auth-resolution cases offline

**Status:** resolved

- [x] `rk.agent_run()` is the only external launch interface; version, environment, settings and CLI assertion helpers remain private.
- [x] The supervisor inherits only its declared environment allowlist, adds proxy/CA configuration itself, and the child assesses its actual environment on every agent run.
- [x] The runtime constructs one options value and hands that same value to the assessor and transport: SDK `env` and `setting_sources` are empty, SDK sandbox merging is disabled, and `cwd` is the inspected runtime-owned directory.
- [x] Settings are absent or one canonical runtime-owned file; inline JSON, missing paths, unreadable/malformed documents, non-object documents and non-object `env` members refuse before transport construction.
- [x] Managed settings are inspected unconditionally, while user/project/local settings remain excluded by the fixed source configuration.
- [x] The runtime resolves the installed SDK metadata and exact bundled CLI executable, supplies that path itself, and refuses unknown pairs, missing private metadata, missing executables and caller overrides without falling back to `PATH`.
- [x] Pre-spawn assessment aggregates every safely observable runtime, launch and credential-vector violation in stable order and never includes values.
- [x] A clean launch constructs the fake transport exactly once; any violating launch constructs it zero times, and two runs with a mutated child environment receive independent verdicts.
- [x] A stdlib import check admits SDK construction only in the runtime launch module, and the hunter tool roster exposes no environment, settings, credential or raw-process operation.

## Comments

Implemented on branch `implementation/startup-launch`, commit `61ac4e1`, on
2026-08-08. Ten stdlib tests cover the single launch interface, environment
allowlist, exact options identity, runtime and settings refusal, deterministic
redacted records, per-run reassessment and the static SDK/tool boundary. The
eight ticket-01 replay tests remain green; an offline check with the installed
SDK 0.2.132 resolved its executable bundled CLI 2.1.224. Compile and diff-only
Gitleaks checks pass. The destructive Docker walking-skeleton reset was not run.
