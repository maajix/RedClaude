# 16 — Start one clean real Agent child

**What to build:** Launch an actual isolated Agent process through the runtime-owned interface using one effective configuration that has passed the production startup assertion.

**Blocked by:** 10 — Send HTTPS through the same capability path; 12 — Use an Identity without exposing credentials; 15 — Replay auth-resolution evidence in production.

**Status:** needs-triage

- [x] `agent_run(request)` is the only external SDK launch interface and static checks reject direct SDK construction elsewhere.
- [x] The supervisor builds a positive environment allowlist plus runtime-owned proxy and CA settings, and the child assesses the environment it actually inherited.
- [x] One runtime-owned settings directory, bundled CLI path and SDK options value is used by both assessment and transport construction.
- [ ] A real isolated child starts against a synthetic local control upstream, emits the expected first init message and becomes tool-ready exactly once.
- [ ] The child has no API key, usable subscription credential, unrelated user/project settings or direct target network path.
- [x] Missing bundled metadata, executable or supported runtime pair refuses before transport construction without falling back to `PATH`.

## Comments

Implemented on branch `implementation/startup-assertion` in commit `5290efe` on
2026-08-12. Four of the six criteria are ticked; the two that are not are
recorded below, which is why the status is `needs-triage` rather than
`resolved`.

`agent.py` is the supervisor and the only external launch interface;
`_launch.py` is the child and the only module in the application that
constructs the SDK. A static check parses every module under `src/redkraken`
and fails if any other one names `claude_agent_sdk`, string constants included,
so a second launch path cannot appear without failing the suite.

The supervisor builds the child environment from a positive list, adds the
runtime's proxy, trust root, home and import path, and passes the job on
standard input. The child asserts against the environment it actually
inherited, builds one options value and hands that same object to the
transport. `assess` is pure and duck-typed, so every rule is exercisable on a
machine with no SDK -- which is the same machine that has to be able to prove
the SDK's absence is a refusal.

Thirty-four tests in `tests/test_agent.py`: the SDK boundary, the launch
directory, the environment allowlist, each widened options field, the
unmeasured-runtime family, the settings documents the CLI loads whether or not
this runtime asked for them, init corroboration, the tool surface, the child's
order of operations, what the supervisor will believe about a child it did not
watch, and one real child end to end. The last of those starts against
`fixtures.ControlUpstream` -- a loopback CONNECT proxy holding a certificate
this run's own authority issued for `api.anthropic.com` -- and observes
`0.2.132`/`2.1.224`, `apiKeySource` `none`, the tool surface open exactly once,
the one tool served once, and every request the child made arriving at the
door, addressed to that one host.

The full suite is 648 tests. Two failures are pre-existing and environmental:
`test_identity` and `test_proxy` both need `os.memfd_create`, which the uv
CPython builds this machine runs do not provide. `tools/check_baseline.py`
reports `classifications=10 regressions=7 artifacts=223`, and
`python3 -m compileall -q src tests tools` is clean. Everything was run on both
interpreters -- the project's, which has no SDK, and one that has the measured
pair -- and each skips only the tests the other one proves.

### What the two review axes raised

The Standards axis found one hard breach: three places said the application has
no third-party dependencies while `_launch` imports one. Resolved by correcting
the claims rather than declaring the package. What this runtime requires is a
*pair*, an SDK version and the CLI version it bundles, and no requirement
specifier can name the second half; declaring the first half would state the
same fact twice in a weaker form that a resolver may satisfy with a pair
nothing has measured. The pair stays pinned in `_startup.KNOWN_RUNTIME`, and
`pyproject.toml`, `doctor.REQUIRED_DISTRIBUTIONS` and the `_launch` docstring
now say so. The consequence is deliberate: `rk doctor` passes on a machine that
cannot start an Agent run, and that machine refuses at the assertion with
`unmeasured_runtime` instead of failing every other command.

Also from that axis, and taken: the duplicated `6` and `1500` literals are now
named constants, `assess`'s `other` list is `configuration`, `_launch.SPOKEN`
is `ANSWER` (it named a character bound and collided with the fixture's spoken
text), the two-branch settings append happens once, and the `managed_settings`
and `environment`/`runtime`/`transport` test seams are documented in their
docstrings the way `doctor.diagnose` documents its own.

One Standards suggestion was not taken: adopting `outcome.Violation` for the
refusal records. It is a different value. `outcome.Violation` is
`(code, source, detail)`, feeds `PRECEDENCE` and `exit_code`, and carries prose
for an operator; a startup refusal is `(code, vector, source, effect)` and
carries no prose on purpose, because a refusal that printed what it found would
leak the credential it refused. What was genuinely duplicated was the shape, so
the shape is now stated once, as `_startup.VIOLATION_KEYS`.

The Spec axis found that `permission_mode`, `allowed_tools` and `mcp_servers`
were set but never assessed. They are assessed now, and together: the
permission mode decides whether a call is questioned, and the other two decide
that there is nothing to question, so `bypassPermissions` is contained exactly
and only while the roster is the runtime's own one-tool server. It also found
that `tool_ready` could not count past one, because the surface opened inside
corroboration and nothing looked afterwards; the drain loop now counts every
announcement, so a child that announced itself twice closes its own surface and
the count crosses back as the evidence. `AgentRunRequest.program` was
speculative -- it crossed to the child and nothing read it -- and is gone.

### The two criteria that are not ticked

Both turn on the same missing half, and it is the half this repo already has a
name for. `redkraken.isolation.run` starts a process in a verified one-peer
container: internal network, DNS blackholed, one attached peer, no capabilities,
read-only root, the run certificate mounted and nothing else. Ticket 11 proved
raw TCP, external DNS, target and control ports are unreachable from inside it.
The child this ticket starts does not go through it.

*Criterion 4* is met at the process level -- own process, `-P`, a positive-list
environment, a runtime-owned home, working directory and settings document, one
bundled executable, and a first init message and single tool-ready opening
observed live -- but `isolated` has a stronger meaning in this codebase than
the one the launch currently satisfies.

*Criterion 5* holds on three of its four clauses, each with a test: no API key,
no unrelated user or project settings, and no usable subscription credential
now that `HOME` is off the inherited list and `AgentRunRequest.home` is
required, so no launch can reach the operator's own credential by omission. The
fourth clause, no direct target network path, is closed only by proxy variables
today. Those ask a cooperative client to use the door; they do not stop
model-controlled code from opening its own socket, which is the exact gap
`isolation.py` was written to close.

Joining them needs an image carrying the application and the measured SDK pair,
and a control upstream that is a container peer rather than a loopback thread,
since `isolation.run` verifies that the proxy named in the URL *is* the one
other peer on an internal network. That is a ticket's worth of work and it is
not this ticket's, so it is left named rather than half-built. Ticket 20 is the
first one that runs a real Agent run and a real network Tool run together, and
ticket 62's third criterion is the release gate that reads the container tests;
whichever of those takes it, criteria 4 and 5 should be closed there.
