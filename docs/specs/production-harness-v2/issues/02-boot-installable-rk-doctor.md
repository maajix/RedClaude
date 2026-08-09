# 02 — Boot an installable `rk doctor`

**What to build:** Give the operator one supported installation and diagnostic command that validates a Program configuration and reports local runtime readiness without starting an Agent run or contacting a target.

**Blocked by:** 01 — Freeze the production boundary and v1 census.

**Status:** resolved

- [x] The project installs as one Python application and exposes stable `rk --version` and `rk doctor` commands without importing prototype code.
- [x] `rk doctor` accepts a versioned declarative Program configuration, validates its schema and emits a structured success or failure result.
- [x] Invalid configuration, missing runtime dependencies and unsupported version combinations return distinct non-zero outcomes without creating state or network traffic.
- [x] Diagnostic output contains configuration hashes, versions and readiness facts but no secret values, credentials or required-header values.
- [x] The command works from a clean checkout through the documented installation path and has one end-to-end CLI test.
- [x] Production dependency versions and the supported Python range are declared and reproducible.

## Comments

Implemented on branch `implementation/startup-assertion` in commits `76b6bd3`
and `db441d2` on 2026-08-09.

`src/redkraken` is the whole application: `config` holds the closed, versioned
schema, `doctor` holds the readiness operation, `cli` is a thin adapter, and
`pyproject.toml` ships `rk` from a src layout with an exact build pin, an empty
production dependency table and `requires-python = ">=3.14,<3.15"` read from
the same constant `rk doctor` reports. 81 stdlib tests pass offline and
`tools/check_baseline.py` reports `classifications=10 regressions=7
artifacts=223`; `src` is classified production, so the boundary check now scans
it for prototype, documentation, scratch and temporary dependencies.

Outcomes stay distinct and were exercised through the installed script: 0
ready, 2 usage, 3 invalid configuration, 4 unsupported interpreter or schema
version, 5 missing module or unpinned distribution. Violations aggregate rather
than short-circuit, and the runtime outranks the operator when both refuse. An
audit-hook driver proves no socket, subprocess or write-mode open occurs on
either the success or the refusal path, and that no module loads from outside
`src`. Diagnostic output is a positive projection carrying `source_sha256`,
`canonical_sha256`, names, counts and versions; secret sentinels planted in a
valid and in an unparsable configuration reach neither stdout nor stderr.

Independent Standards and Spec reviews of `135c63a...76b6bd3` both reported
findings, and `db441d2` closes them: references are now restricted to the
runtime-owned `slot://` shape (a URL with userinfo was previously accepted, so
a configuration could carry its own credential), a wildcard scope host must
name at least two labels of its own (`*.com` was previously accepted), the
schema and result vocabulary follow CONTEXT.md (`[rules_of_engagement]`,
`slot_ref`, `Assertion`), and the packaging claim is now proved by a test that
builds and installs from a pristine copy and runs the shipped `rk`.

Two review findings were deliberately not actioned. A dependency lock artifact
is empty while the production dependency table is empty; the build requirement
is exact-pinned and the documented offline path now passes
`--check-build-dependencies` so the pin is enforced there too, and release
artifacts belong to the release ticket. `python -m redkraken` is kept as the
source-checkout entry point the tests and the README use; the shipped console
script is now covered independently.

Glossary gaps for `/domain-modeling`: `Diagnosis`, `Assertion` and `Violation`
name runtime concepts, and `callback` and `required_header` name configuration
concepts, none of which CONTEXT.md defines yet.
