# 02 — Boot an installable `rk doctor`

**What to build:** Give the operator one supported installation and diagnostic command that validates a Program configuration and reports local runtime readiness without starting an Agent run or contacting a target.

**Blocked by:** 01 — Freeze the production boundary and v1 census.

**Status:** ready-for-agent

- [ ] The project installs as one Python application and exposes stable `rk --version` and `rk doctor` commands without importing prototype code.
- [ ] `rk doctor` accepts a versioned declarative Program configuration, validates its schema and emits a structured success or failure result.
- [ ] Invalid configuration, missing runtime dependencies and unsupported version combinations return distinct non-zero outcomes without creating state or network traffic.
- [ ] Diagnostic output contains configuration hashes, versions and readiness facts but no secret values, credentials or required-header values.
- [ ] The command works from a clean checkout through the documented installation path and has one end-to-end CLI test.
- [ ] Production dependency versions and the supported Python range are declared and reproducible.
