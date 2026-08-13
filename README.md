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
- No third-party Python production dependencies. The Python runtime is standard
  library only; any package added later is declared as an exact pin and verified
  at startup. Operations that invoke a system executable check it at the point
  of use: TLS interception requires `openssl`, database dump and restore require
  `pg_dump` and `pg_restore`, and Agent network isolation requires Docker.

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
.venv/bin/pip install --no-build-isolation --check-build-dependencies .
```

`--check-build-dependencies` keeps the pinned build requirement enforced on
this path too; without it, skipping build isolation also skips the check.

`rk` is then on the virtual environment's `PATH`. `python3 -m redkraken` runs
the identical command line from a source checkout, with `src` on `PYTHONPATH`.

## Check the machine

```sh
rk doctor
```

`rk doctor` reports whether this machine can be trusted to run a Program. It
reads; it creates no state, sends no traffic and starts no run. Its result is
JSON on stdout: the application version, the interpreter version and the
supported range, one entry per readiness assertion, and every violation it
found.

Give it a Program configuration to validate that too:

```sh
rk doctor --config program.toml
```

## The Program configuration

A configuration is versioned and declarative. The schema is closed: an
unrecognised key is a refusal, not an ignored line. Absent permission is
denial, so a rule of engagement that is not set is off.

```toml
schema_version = 1

[program]
name = "acme-web"
platform = "hackerone"

[rules_of_engagement]
mutation = true

[budgets]
requests = 5000
tokens = 2000000
run_tokens = 40000
run_requests = 50
lane_tokens = 500000
lane_requests = 1000
concurrency = 2
burst = 500
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
slot_ref = "slot://identity/member"

[[required_header]]
name = "X-Bounty-Id"
value_ref = "slot://header/bounty-id"

[[callback]]
name = "oob-dns"
kind = "dns"
host = "oob.example.net"
```

A scope entry names a hostname, an address, or a wildcard such as
`*.example.com`. An inclusion's wildcard must name at least two labels of its
own, so `*.com` is refused. That is a floor, not a public-suffix rule: `*.co.uk`
passes it, and how wide an inclusion may be remains the operator's judgement
against the Program. An exclusion has no floor, because breadth there withdraws
authority rather than claiming it. Hosts are compared in one spelling —
lowercased, without a trailing root dot, addresses in canonical form — so two
ways of writing the same Program produce the same hash, and a repeated rule
counts once.

A path names a prefix on the host that carries it. It begins with a single
forward slash, so the protocol-relative `//elsewhere.example/admin` is refused;
it holds no `..` segment and no unprintable character, so what is printed is
what was matched.

Secret material is never written into a configuration. An identity carries a
`slot_ref` and a required header carries a `value_ref`. Both name a
runtime-owned slot — the `slot://` scheme and nothing else, so a configuration
cannot smuggle its own credential in a URL — which the runtime resolves and the
proxy injects. A key that would hold a secret inline is refused by name.

Diagnostic output follows the same rule. It reports names, counts, controls,
versions and the two hashes that identify a configuration — `source_sha256`
over the file as written and `canonical_sha256` over its normalised content, so
reformatting does not change the policy's identity — and never a reference or a
header value.

## Outcomes

`rk doctor` aggregates: it reports every violation it found, not the first, and
exits on the most fundamental one. A schema version this build cannot read is
the one exception, reported alone because it explains every other refusal such
a document would draw.

| Exit | Meaning |
| ---- | ------- |
| `0` | Ready. |
| `1` | A refusal this build cannot classify. |
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
