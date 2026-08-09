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

Implemented on branch `implementation/startup-assertion` in commits `76b6bd3`,
`db441d2` and `37753ae` on 2026-08-09.

`src/redkraken` is the whole application: `config` holds the closed, versioned
schema, `doctor` holds the readiness operation, `cli` is a thin adapter, and
`pyproject.toml` ships `rk` from a src layout with an exact build pin, an empty
production dependency table and `requires-python = ">=3.14,<3.15"` read from
the same constant `rk doctor` reports. 100 stdlib tests pass offline and
`tools/check_baseline.py` reports `classifications=10 regressions=7
artifacts=223`. `src` was already a production root, so the boundary check
scanned it before this ticket; what `76b6bd3` adds is its census entry, which
states the claim the scan enforces.

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

A third review of `135c63a...df8d037` found fifteen further issues, closed in
`37753ae`. The material ones were behavioural. `outcome.exit_code` returned `0`
for a violation class it did not recognise, so a refusal could be read as a
ready machine; an unrecognised class now exits `1` and sorts last. `config.load`
raised rather than reported on a directory, an unstattable path or a nesting
bomb, and imported `tomllib` at module scope, so an interpreter without it
crashed instead of reporting a missing dependency; it now refuses anything that
is not a regular file under 1 MiB and reports the absent parser as
`missing_dependency`. Hosts are normalised before matching, so `A.Example.Com.`
and `app.example.com` are one policy, `010.0.0.1` and `999.999.999.999` are
refused rather than read as names, and an exclusion may be as broad as the
operator likes while an inclusion keeps its two-label floor. A path may no
longer begin `//`, hold a `..` segment or carry an unprintable character. A
repeated scope rule now hashes as one rule. A bad identity name no longer
suppresses the `slot_ref` violation behind it. An unsupported schema version is
reported alone instead of behind a pile of unknown keys. `pyproject.toml` names
what it ships rather than discovering it, the installation test now skips
unless the ambient setuptools matches the pin and runs pip under a home of its
own, and the containment driver watches file-system mutation and
`os.posix_spawn` alongside network and process events.

One boundary gap is known and left open: `tests` is neither a production root
nor a classified path, so `tools/check_baseline.py` does not scan it. It cannot
be classified as it stands, because `tests/test_baseline.py` carries literal
`docs.prototype` strings as fixtures that the dependency rule would read as
real imports. Closing it belongs to ticket 01, which owns the boundary.

Glossary gaps for `/domain-modeling`: `Diagnosis`, `Assertion` and `Violation`
name runtime concepts, and `callback` and `required_header` name configuration
concepts, none of which CONTEXT.md defines yet.
