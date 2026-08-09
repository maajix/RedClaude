# RedKraken

A local-first bug-bounty hunting harness for web and API targets. The operator
runs it on their own machine, against Programs they are authorised to test, and
keeps every artifact it produces.

This repository is being built one production increment at a time. Today it
installs as one Python application and exposes two stable commands: `rk
--version` and `rk doctor`.

## Requirements

- CPython `>=3.14,<3.15`. `pyproject.toml` and `rk doctor` declare the same
  range, and starting outside it is a refusal rather than a warning.
- No production dependencies. The runtime is standard library only; any
  dependency added later is declared as an exact pin and verified at startup.

## Install

From a clean checkout:

```sh
python3 -m venv .venv
.venv/bin/pip install .
.venv/bin/rk --version
```

Without network access, build against the interpreter's own setuptools instead
of a downloaded one:

```sh
python3 -m venv --system-site-packages .venv
.venv/bin/pip install --no-build-isolation .
```

`rk` is then on the virtual environment's `PATH`. `python3 -m redkraken` runs
the identical command line from a source checkout, with `src` on `PYTHONPATH`.

## Check the machine

```sh
rk doctor
```

`rk doctor` reports whether this machine can be trusted to run a Program. It
reads; it creates no state, sends no traffic and starts no run. Its result is
JSON on stdout: the application version, the interpreter version and the
supported range, one entry per check, and every violation it found.

Give it a Program configuration to validate that too:

```sh
rk doctor --config program.toml
```

## The Program configuration

A configuration is versioned and declarative. The schema is closed: an
unrecognised key is a refusal, not an ignored line. Absent permission is
denial, so an engagement control that is not set is off.

```toml
schema_version = 1

[program]
name = "acme-web"
platform = "hackerone"

[engagement]
mutation = true

[budgets]
requests = 5000
tokens = 2000000
concurrency = 2
window_seconds = 3600

[[scope.include]]
host = "app.example.com"
ports = [443]
protocols = ["https"]
paths = ["/api/"]

[[scope.exclude]]
host = "admin.example.com"
ports = [443]
protocols = ["https"]
paths = ["/"]

[[identity]]
name = "member"
credential_ref = "slot://identity/member"

[[required_header]]
name = "X-Bounty-Id"
value_ref = "slot://header/bounty-id"

[[callback]]
name = "oob-dns"
kind = "dns"
host = "oob.example.net"
```

Secret material is never written into a configuration. An identity carries a
`credential_ref` and a required header carries a `value_ref`: references the
runtime resolves elsewhere and injects at the proxy. A key that would hold a
secret inline is refused by name.

Diagnostic output follows the same rule. It reports names, counts, controls,
versions and the two hashes that identify a configuration — `source_sha256`
over the file as written and `canonical_sha256` over its normalised content, so
reformatting does not change the policy's identity — and never a reference or a
header value.

## Outcomes

`rk doctor` aggregates: it reports every violation it found, not the first, and
exits on the most fundamental one.

| Exit | Meaning |
| ---- | ------- |
| `0` | Ready. |
| `2` | The command line could not be understood. |
| `3` | `invalid_configuration`: the configuration was refused. |
| `4` | `unsupported_version`: an interpreter or schema version is out of range. |
| `5` | `missing_dependency`: a required module or pinned distribution is absent. |

## Tests

The suite is standard library only and runs offline:

```sh
python3 -m unittest discover -q
python3 tools/check_baseline.py
```
