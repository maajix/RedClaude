# 16 — Start one clean real Agent child

**What to build:** Launch an actual isolated Agent process through the runtime-owned interface using one effective configuration that has passed the production startup assertion.

**Blocked by:** 10 — Send HTTPS through the same capability path; 12 — Use an Identity without exposing credentials; 15 — Replay auth-resolution evidence in production.

**Status:** resolved

- [x] `agent_run(request)` is the only external SDK launch interface and static checks reject direct SDK construction elsewhere.
- [x] The supervisor builds a positive environment allowlist plus runtime-owned proxy and CA settings, and the child assesses the environment it actually inherited.
- [x] One runtime-owned settings directory, bundled CLI path and SDK options value is used by both assessment and transport construction.
- [x] A real isolated child starts against a synthetic local control upstream, emits the expected first init message and becomes tool-ready exactly once.
- [x] The child has no API key, usable subscription credential, unrelated user/project settings or direct target network path.
- [x] Missing bundled metadata, executable or supported runtime pair refuses before transport construction without falling back to `PATH`.

## Comments

Implemented on branch `implementation/startup-assertion` in commit `5290efe` on
2026-08-12, and finished in the commit that follows this note. The first commit
ticked four criteria and named the two it did not; the second one joined the
launch to the container boundary and closed those two.

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

### Closing the last two criteria

Both turned on the same missing half, and the repo already had a name for it.
`redkraken.isolation.run` starts a process in a verified one-peer container:
internal network, DNS blackholed, one attached peer, no capabilities, read-only
root, the run certificate mounted and nothing else. Ticket 11 proved that raw
TCP, external DNS, and the target and control ports are all unreachable from
inside it. The child now goes through it, and that is the whole of the second
commit: there is one launch mechanism, and it is that one.

What the boundary had to learn is what an Agent needs in order to exist at all.
`AgentContainer` gained three host directories -- the application, the SDK the
pair is measured against, the home the credential resolves from -- and decides
itself where each is mounted and which may be written: the first two read-only
because a child that could write to them could choose what the next child is
measured as, the home writable because the CLI keeps session state in it. All
three default to absent, and absent is the contained value: a container with no
home mounted has no credential at all rather than somebody else's, and one with
no SDK mounted refuses at the assertion rather than starting a session. `run`
also gained a `stdin`, so the job crosses on a pipe rather than in `argv`.

`agent.child_environment` and `agent.INHERITED` are gone. They were the second
positive list, and the boundary's is narrower -- three usability variables,
plus `HOME`, `TMPDIR` and `PYTHONPATH`, which the runtime sets because each one
decides what a child resolves. Not `PATH` any more either: it comes from the
image. `AgentRunRequest` lost `workspace`, `proxy_url`, `certificate` and
`home` to one required `container` field, which is now the whole of what a
child can reach. The launch directory moved to the child, because the
supervisor's filesystem is not the child's, and a directory it made would be
one the child could not be given.

*Criterion 4* is met by `ContainedChildTest`: a real child, `python3 -P -m
redkraken._launch` inside the boundary, against `fixtures.ControlUpstream`
running as the network's one peer -- a container now rather than a loopback
thread, because `isolation.run` verifies that the proxy named in the URL *is*
that peer. The measured pair comes back from inside the container,
`apiKeySource` is `none`, the tool surface opens exactly once and the one tool
is served once. Every request the child made is read back out of the peer's own
log, and each one is addressed to `api.anthropic.com`.

*Criterion 5* now holds on all four clauses. No API key and no unrelated
settings were already tested. No usable subscription credential is stronger
than it was: the operator's home is not merely un-inherited, it is not in the
child's filesystem, and the only home there is the one the runtime mounted. No
direct target network path is the ticket-11 property, unchanged and now applied
to this child -- a property of the network rather than a request made of a
cooperative client through proxy variables.

Two test-side notes. `RK_TEST_AGENT_IMAGE` now defaults to `python:3.14-slim`
rather than `python:3.13-alpine`: the bundled CLI is a glibc-linked executable,
so a musl image is one no Agent child can start in, and a default that is not a
possible Agent image makes the topology proof about nothing. And
`isolation.container_environment` and `isolation._mounts` are split out of
`run`, so the half of the boundary that needs no engine is asserted on machines
that have none -- which is the same reasoning that keeps `assess` pure.

The suite is 651 tests. The two failures are the same pre-existing
environmental ones (`test_identity` and `test_proxy` need `os.memfd_create`,
absent from the uv CPython builds this machine runs). With
`RK_TEST_CONTAINERS=1`, `tests.test_agent` and `tests.test_isolation` are 40
tests green on the measured interpreter, one skip.
