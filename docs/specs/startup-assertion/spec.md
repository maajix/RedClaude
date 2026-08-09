# Startup assertion: refuse to begin an agent run off the subscription

Status: implemented
Next: tickets 01-08 under `issues/` are resolved; their comments record the
implementation commits and validation evidence. This artifact remains the
behaviour and acceptance contract.

Settles: the implementation-ready form of the startup assertion unblocked by
historical ticket 21, whose
answer is the evidence base for the version-bound rules below. Prototypes: branch
`docs/prototype/sdk-auth-probe` (`9d5b97e`) for the measurements and the reference
assertion, branch `prototype/walking-skeleton` for the seam it already runs at.
Also settles the receipt fence required by
historical ticket 57;
that adjacent decision is called out separately because it is not part of the
startup-assertion module.

Vocabulary: **startup assertion** and **credential vector** are now glossary
terms in `CONTEXT.md`. Earlier drafts of this spec called the module a
"subscription guard"; that name is retired.

## Problem Statement

The runtime drives Claude through `claude-agent-sdk`, which spawns its bundled
Claude Code CLI. Ticket 21 measured that stack on the host, where the CLI read the
operator's OAuth credentials directly. Ticket 14 subsequently chose the shipping
topology: the agent container holds only placeholder credentials and the proxy
adds the real `Authorization` header on the control lane. The startup assertion
runs inside that agent container. It is defence in depth for the subscription-only
constraint; the proxy and container topology remain the structural credential and
egress boundary.

**The harness needs no API key at all.** Not one is configured, stored or read
anywhere in the design. Every credential vector named in this spec appears only
as something to detect and refuse.

The failure mode is silent. In ticket 21's measured host topology, a single
truthy environment variable, or one key in a settings file the harness did not
write, replaced OAuth, selected another provider, redirected the destination, or
prevented the CLI from starting. An unusable API key failed rather than falling
back to OAuth. Those observations decide which inputs are refused; they do not
prove that every vector bills per token.

In ticket 21's host probe, `ANTHROPIC_BASE_URL` sent the live OAuth bearer token
to the named host. In the shipping topology the agent container has no live
OAuth token to expose, and the single-egress proxy must refuse the destination.
The startup assertion still refuses the vector, but reports a destination
override rather than claiming that the target topology leaked a token.

None of this is documented. It was recovered from the CLI binary's embedded
JavaScript (ticket 01), then measured on the wire (ticket 21), so it can change
on any version bump without notice.

The operator needs the runtime to refuse to start rather than to spend, and to be
told which credential vector was responsible.

## Solution

A **startup assertion**: a runtime-side check that refuses to begin an agent run
when a version-bound credential vector is observable in the effective launch
configuration, or when the CLI's init message reports an unexpected auth source.
It reports every violation observable in the current phase, including source and
measured effect. It does not claim that a clean start proves how a request was
billed; only the egress receipt can do that.

Three phases, because no single one covers every measured vector:

1. **Runtime gate.** Auth resolution is undocumented internal behaviour, so an
   SDK/CLI pair nobody has measured is refused rather than trusted.
2. **Effective launch configuration.** Every watched variable in the environment
   the CLI will actually inherit, plus `apiKeyHelper` and watched `env` keys in
   every settings file that will actually load. This is the only phase that catches
   `ANTHROPIC_AUTH_TOKEN`, the three cloud-provider switches, the
   file-descriptor vector and `ANTHROPIC_BASE_URL`.
3. **Init message.** The CLI's own `apiKeySource` on the init `SystemMessage`,
   checked once per agent run. Catches a key or helper the harness did not know
   about. A supplement, never a replacement.

Phases 1 and 2 run before the SDK transport is constructed, so a violating
configuration costs zero tokens. Phase 3 runs on the first message of the agent
run, before any tool is served. A refusal is loud, names every violation visible
at that phase, closes the run durably, and stops the runtime from scheduling
another run until the operator restarts it after remediation.

## User Stories

1. As an operator, I want the runtime to refuse to start when a credential vector
   is present, so that a known startup vector cannot silently move the run away
   from the subscription path.
2. As an operator, I want the refusal message to name the exact variable or
   settings key responsible, so that I can clear it without bisecting my shell
   profile.
3. As an operator, I want the refusal to distinguish replacement auth, provider
   rerouting, startup denial and destination override, so that the message says
   what was measured without inventing billing or exfiltration impact in the
   shipping topology.
4. As an operator, I want `ANTHROPIC_API_KEY=""` treated as unset, because that
   is the empty-value case measured by ticket 21; an unmeasured empty value for
   another watched variable must fail closed.
5. As an operator, I want the assertion to refuse on an SDK or CLI version nobody
   has measured, so that an undocumented behaviour change is caught by a version
   pin rather than by a bill.
6. As an operator, I want the version gate to name the bundled CLI the SDK will
   actually spawn rather than whatever is on `PATH`, so that the pin describes the
   binary that resolves the credential.
7. As an operator, I want every statically observable violation refused before
   the SDK transport is constructed, so that those failures cost zero tokens;
   init corroboration remains the explicitly later backstop.
8. As an operator, I want a second check against the CLI's own reported auth
   source once the agent run is up, so that a settings file the harness never
   inspected is still caught.
9. As an operator, I want to be told when the CLI reports no auth source field at
   all, so that a silently ungrounded corroboration is a failure rather than a
   pass.
10. As an operator, I want the assertion to inspect only the settings files that
    will actually load for this run, so that an unrelated project's settings file
    does not block a run it cannot affect.
11. As an operator, I want managed settings files scanned unconditionally, so that
    a policy file outside my control is not silently trusted.
12. As an operator, I want a settings file that cannot be read or parsed to be a
    refusal, so that an unreadable file is never mistaken for a clean one.
13. As an operator, I want the agent run to carry a deliberately allowlisted
    environment, so that an inherited variable I forgot about cannot reach auth
    resolution in the first place.
14. As an operator, I want the assertion to read the environment the agent run
    actually has rather than the one the supervisor meant to pass, so that a
    scrubbing bug is caught by the same check.
15. As an operator, I want the harness to isolate itself from settings files it
    did not write, so that a project checkout cannot change how my runs are
    billed.
16. As an operator, I want to be told plainly that isolation is not sufficient on
    its own, so that I do not assume it covers the environment.
17. As an operator, I want to configure no credential of any kind, so that being
    logged in to Claude Code is the entire setup.
18. As a runtime, I want one interface through which every agent run is spawned,
    plus a CI import rule and the structural egress fence, so that an accidental
    raw-SDK call is caught and ungated egress is unservable.
19. As a runtime, I want the assertion to run inside the spawned agent run rather
    than only in the supervisor, so that it validates the process that will
    actually launch the CLI.
20. As a runtime, I want a refusal to be a runtime-authored `startup.refused`
    occurrence event on the program when a program is known, so that the audit
    trail records why a run did not happen without overloading `agent.refused`.
21. As a runtime, I want a refusal raised before any program exists to be fatal to
    the process, so that a misconfigured machine cannot start a hunt at all.
22. As a runtime, I want the assertion re-checked per agent run rather than once
    at boot, so that an environment mutated between runs is still caught.
23. As a runtime, I want the verdict to be a single refuse/allow decision that
    does not model credential precedence, so that its correctness does not depend
    on reproducing undocumented resolution order.
24. As a runtime, I want precedence knowledge kept as measurement metadata only,
    so that it never suppresses a present vector or changes the verdict.
25. As a runtime, I want the watched-vector table to be data rather than scattered
    literals, so that the test suite and the failure message read from one source.
26. As a hunter agent, I want no tool that can read or set a credential vector, so
    that model output can never move billing.
27. As a maintainer, I want every rule labelled with its measurement or explicitly
    marked conservative and unmeasured, so that reasoned coverage is never
    presented as observed behaviour.
28. As a maintainer, I want the test suite to replay a fixed, sanitised evidence
    manifest past the assertion and compare every structured violation against
    normalised wire outcomes, so that it is tested against evidence and not
    against my belief or the current operator account.
29. As a maintainer, I want the six vectors the CLI's own report misses asserted
    explicitly, so that nobody later mistakes the init-message phase for the whole
    check.
30. As a maintainer, I want the test suite to need no network, no SDK and no
    credentials, so that it runs in CI on every commit.
31. As a maintainer, I want a documented procedure for extending the known-runtime
    list, so that a version bump re-runs the probe rather than editing a constant.
32. As a maintainer, I want the assertion to be a deep module with a small
    surface, so that the runtime calls it without knowing which vectors exist.
33. As a maintainer, I want the private SDK attribute the version gate depends on
    named as a known fragility, so that its disappearance is an expected breakage
    rather than a mystery.
34. As a maintainer, I want the vector that no startup assertion can catch named
    in the spec, so that coverage is not overstated.
35. As an auditor, I want every refusal recorded with its vectors and its source,
    so that "the run did not happen and here is why" is answerable from the log.
36. As an auditor, I want the coverage boundary written down, so that I know a
    clean start is not positive proof that a given request billed the
    subscription.
37. As an operator, I want the runtime to refuse rather than degrade to a cheaper
    model or a different provider when a vector is present, so that no fallback
    path spends money quietly.
38. As a scheduler, I want a startup refusal to close its `agent_runs` row,
    return the task to `pending` without consuming an attempt, release every
    identity lease and emit its event in one idempotent transaction, so that a
    machine misconfiguration cannot strand work or create a retry loop.

## Implementation Decisions

### Module and interface

The startup assertion is runtime-owned. It is not an MCP tool, is not
agent-reachable, and never receives or returns credential values. It lives behind
the existing `rk.agent_run()` seam; shipping promotes the prototype logic into
that runtime module rather than vendoring another copy.

The external interface remains one operation: `rk.agent_run(request)`. Its
interface includes `StartupRefusal` as an error outcome, but exposes no separate
`assert_*` methods and accepts no caller-supplied description of the effective
environment or selected CLI. The runtime module owns all of this behaviour:

1. construct the child environment from its allowlist;
2. resolve and pin the bundled CLI;
3. construct one `ClaudeAgentOptions` value;
4. assess that exact launch configuration;
5. start the SDK transport;
6. corroborate the first init message;
7. close the run durably on refusal.

Pure evaluators and the third-party SDK transport are private seams used by the
module's own tests. Callers cannot check one configuration and launch another.
The pre-spawn assessment collects runtime, launch and credential-vector
violations before raising; one failed check never short-circuits the other facts
that are still safely observable without constructing the SDK transport.

### One effective launch configuration

The supervisor inherits only `PATH HOME USER LOGNAME LANG TMPDIR
XDG_RUNTIME_DIR SHELL` into the agent-run process. Proxy and CA variables needed
by ticket 14 are added from runtime configuration, not inherited from the
operator shell. Phase 2 reads `os.environ` inside that child after those additions.

The child constructs `ClaudeAgentOptions` once, then passes that same value to
the private assessor and the SDK transport. These constraints are part of the
interface, not caller conventions:

- `env={}`. The SDK therefore adds no watched key to the inherited child
  environment after the assertion.
- `setting_sources=[]`. SDK skill defaults cannot widen it because it is explicit.
- `settings` is `None` or one canonical absolute path beneath the runtime-owned
  per-run directory. Inline JSON is refused.
- `sandbox=None`. Container isolation owns the sandbox; SDK sandbox merging
  would rewrite `settings` after inspection and is therefore unsupported.
- `cwd` is the same runtime-owned path inspected by the assertion.
- `cli_path` is set by the runtime to the package's existing bundled executable.
  A caller cannot override it and absence of the bundled executable is a refusal;
  there is no fallback to `PATH`.

CI contains a stdlib-AST check that `claude_agent_sdk`, `ClaudeAgentOptions` and
`query()` are imported or called only by this runtime module. That check prevents
an accidental second spawn path. It is not described as the security fence: the
receipt capability below makes an ungated network operation unservable even if a
future caller violates the import rule.

### Structured violations

`StartupRefusal` carries a non-empty, deterministically ordered tuple of records:

```json
{
  "code": "credential_vector|unmeasured_runtime|invalid_launch|settings_unreadable|auth_source_unexpected",
  "vector": "ANTHROPIC_API_KEY or null",
  "source": "env:ANTHROPIC_API_KEY",
  "effect": "off_subscription_auth|startup_denial|provider_reroute|destination_override|unverifiable"
}
```

`source` uses one of these stable forms:

- `env:<NAME>`;
- `settings:<managed|explicit|user|project|local>:<canonical-path>#<key>`;
- `runtime:sdk-cli`;
- `launch:<ClaudeAgentOptions field>`;
- `init:apiKeySource`.

It never contains a credential or settings value. Records sort first by the
module's vector-registry order, then lexically by `source`; non-vector violations
follow in `code,source` order. The rendered error and `startup.refused` event use
these records directly, so tests cover the audit payload and operator message
together.

Seven environment variables are watched. Their effect is the observed outcome
for SDK 0.2.132 with bundled CLI 2.1.224, not a general claim about Claude:

| credential vector | structured effect | measured outcome |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | `off_subscription_auth` | `x-api-key`; OAuth absent |
| `ANTHROPIC_AUTH_TOKEN` | `off_subscription_auth` | supplied bearer token; OAuth absent |
| `CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR` | `startup_denial` | SDK closed the fd and CLI refused; direct CLI use selected `x-api-key` |
| `CLAUDE_CODE_USE_BEDROCK` | `provider_reroute` | no request to `api.anthropic.com` |
| `CLAUDE_CODE_USE_VERTEX` | `provider_reroute` | queried the GCP metadata service |
| `CLAUDE_CODE_USE_FOUNDRY` | `provider_reroute` | no request to `api.anthropic.com` |
| `ANTHROPIC_BASE_URL` | `destination_override` | host probe sent OAuth to the named host; target topology contains the credential separately |

Every settings file that loads is also checked for `apiKeyHelper`
(`off_subscription_auth`) and an `env` block carrying any watched environment
name. A missing, unreadable, non-object settings document, or a non-object `env`
member is `unverifiable` and refuses.

Only `ANTHROPIC_API_KEY=""` is treated as unset because that is the empty case
ticket 21 measured. Presence of any other watched name, even with an empty value,
fails closed until that exact case is measured. `apiKeyHelper` is refused when
present rather than interpreted by the harness.

Precedence is not modelled. Mixed cases proved only that OAuth did not rescue the
run; every observed vector is reported, and no "likely culprit" can hide another
violation.

### Settings and runtime resolution

Managed settings paths are scanned unconditionally because the CLI reads them
outside `setting_sources` control. User, project and local settings remain absent
because the shipping options fix `setting_sources=[]`. The optional explicit
settings path is inspected regardless of sources and must be harness-owned.
Ticket 21 measured project-source isolation and explicit-path loading; managed
settings inspection is a conservative, explicitly unmeasured rule.

The known-runtime key is `(claude-agent-sdk version, bundled CLI version)`. The
SDK version comes from installed package metadata. The CLI version comes from
`claude_agent_sdk._cli_version.__cli_version__`; the runtime separately resolves
the package's `_bundled/claude` executable and supplies that exact path as
`cli_path`. Missing private metadata, a missing/non-executable bundled file or an
unknown pair is `unmeasured_runtime`. The private metadata and package layout are
named fragilities and deliberately fail closed.

### Init corroboration

The first SDK message must be an init `SystemMessage` whose `apiKeySource` is
exactly `"none"`. A different first message, a missing field or another source is
`auth_source_unexpected`. No tool may be served before this check completes.

The field remains a supplement: it misses `ANTHROPIC_AUTH_TOKEN`, the three cloud
switches, the file-descriptor vector and `ANTHROPIC_BASE_URL`. Phase 2 therefore
cannot be removed while phase 3 remains green.

### Durable refusal lifecycle

The event catalogue gains `startup.refused`, family `occurrence`, authored with
`actor_kind='runtime'`. It is distinct from `agent.refused`, which means that the
model declined. Its version-1 payload is exactly:

```json
{
  "schema_version": 1,
  "phase": "pre_spawn|init",
  "sdk_version": "0.2.132",
  "cli_version": "2.1.224",
  "violations": [
    {
      "code": "credential_vector",
      "vector": "ANTHROPIC_BASE_URL",
      "source": "env:ANTHROPIC_BASE_URL",
      "effect": "destination_override"
    }
  ]
}
```

The `violations` array contains the records above and no values. Normal event
columns carry `program_id`, `agent_run_id` and `task_id` when those rows exist.
The two version fields are strings when discovery succeeded and JSON `null` when
discovery itself is the refusal.

When a claimed run refuses, one idempotent runtime transaction locks the open
`agent_runs` row, sets `finished_at`, `stop_reason='refusal'` and `result=NULL`,
returns its task to `pending` without consuming an attempt, clears claim/lease
timestamps, releases its identity leases, deletes any `agent_sessions` binding, and
inserts exactly one `startup.refused` event. A repeat call sees the finished row
and changes nothing. No hypothesis transition is needed because pre-spawn and
init refusal occur before a tool receipt can move one to `testing`.

After the transaction the supervisor stops accepting agent runs and exits
non-zero. That prevents an immediate retry loop against the same machine
configuration. If no program exists yet, no event can satisfy the event schema;
the same structured refusal is rendered to stderr and the process exits non-zero.
There is no provider, model or credential fallback.

### Version-bump procedure

The known-runtime allowlist changes only after the ticket-21 probe runs against
the new pair and produces the sanitised manifest described below. Raw captures,
credential fingerprints and mitmproxy key material stay outside the repository.
Only the normalised manifest is a test fixture.

### Adjacent architecture decision: the receipt is the ticket-57 fence

The startup seam prevents accidental raw SDK use; it does not make ungated egress
unservable. For ticket 57, the **receipt is the fence**:

1. `gate_tool_call` remains a pure decision function.
2. A runtime-only database command evaluates it, stamps the `tool_runs` decision
   and, only for `allow`, mints a cryptographically random 256-bit egress
   capability. Only its SHA-256 is stored in
   `tool_runs.egress_token_sha256`; the plaintext never reaches the model,
   events, receipts or canonical state. The runtime network adapter carries the
   plaintext only as `Proxy-Authorization: RedKraken <capability>` to the local
   proxy; the proxy strips and redacts that hop-by-hop header before forwarding.
3. The proxy must resolve that capability against an active allowed tool run
   before egress. It independently canonicalises and scope-checks the actual
   request; missing, mismatched, expired or cleared capabilities cannot egress.
   "Active" means `tool_runs.status='running'`, `decision='allow'`, an unfinished
   parent agent run, and a current task lease when the tool run has a task.
   A capability is scoped to one program, tool run and active lifetime; it may
   back multiple in-scope subresource receipts from that tool run, but never a
   later or different run.
4. `rk2_proxy` loses direct `INSERT` on `receipts`. Security-definer writer
   functions derive `tool_run_id` and `decision` from the resolved capability;
   they never accept an `allowed` literal from the caller. Blocked requests use a
   separate writer that cannot produce an allowed receipt.
5. An `ENABLE ALWAYS` receipt trigger rejects an allowed agent-lane receipt
   unless its tool run belongs to the same program, is active, has
   `decision='allow'` and carries a live capability hash. This makes the existing
   hole-open seed fail even when fixtures are loaded by the database owner.
6. Finishing, denying, parking or aborting a tool run clears its capability.

Thus a caller-side `IF` is not the guarantee. A tool call that skipped the gate
has no capability, the proxy cannot serve it, and an allowed receipt for it is
unwritable. The implementation proof must load the existing hole-open seed and
observe a database refusal while preserving ticket 43's five refusal grounds and
ticket 42's engagement checks.

"Unservable" here means unable to produce an outbound exchange or allowed
agent-lane receipt, which is the scope-enforcement hole ticket 57 found. Pure
state reads and proposals produce no network receipt; their structural fences
remain named RLS views and runtime-only promotion rather than a fabricated
network record.

## Testing Decisions

### Sanitised evidence manifest

The central CI fixture is a single immutable JSON manifest produced by the live
probe's normalisation step. It contains:

- `schema_version`, SDK version, bundled CLI version, probe commit and digest of
  the operator-retained raw capture;
- each case's symbolic input shape — variable names and synthetic sentinel
  values only;
- normalised wire facts: `route` (`anthropic_first_party|other|none`),
  `auth_class` (`subscription_oauth|api_key|other_bearer|none`), destination
  class, request count and init `apiKeySource`;
- no header values, credential hashes, home-directory data, CA material or raw
  capture lines.

The required case IDs are fixed independently of the fixture and compared for
exact set equality before any verdict is checked:

```text
baseline api_key auth_token api_key_empty base_url api_key_helper fd
bedrock vertex foundry settings_env_key proj_helper_isolated
proj_helper_loaded prec_key_vs_token prec_key_vs_helper
prec_token_vs_helper prec_key_vs_bedrock
```

A missing, duplicate or additional case fails CI. The replay derives allow/refuse
from the normalised wire facts — first-party subscription OAuth is the only
allowed measured outcome — then compares that result and the structured
violation to the private pure vector evaluator. This internal seam can replay
historical configurations such as `setting_sources=["project"]` even though the
shipping launch interface refuses them. It does not read `HOME`, call
`credential_names()`, import the probe's side-effecting `vectors()`, or glob
capture files.

`docs/prototype/sdk-auth-probe/verify_guard.py` is historical prior art only. It is
not promoted: it depends on the current operator credential fingerprint and
ambient captures, so it cannot satisfy the offline contract. A secret scan over
the publishable fixture tree is a release gate.

### Module-interface tests

Tests exercise `rk.agent_run()` through a private fake SDK transport and local
filesystem substitutes. They assert observable outcomes rather than helper call
order. The evidence replay above owns the complete historical matrix; the launch
interface tests own the shipping constraints:

- at least one interface case for every violation `code` and `effect`, including
  exact `source` and stable multi-vector ordering;
- all six vectors the init field misses;
- the measured runtime accepted and any changed SDK/CLI pair refused;
- missing bundled CLI, caller-supplied `cli_path`, non-empty options `env`,
  non-empty `setting_sources`, inline-JSON settings and SDK sandbox settings
  refused before transport construction;
- `ANTHROPIC_API_KEY=""` allowed, while an empty value for every other watched
  variable fails closed;
- multiple simultaneous vectors returned together in stable registry order;
- project settings ignored under the shipping `setting_sources=[]`, while the
  runtime-owned explicit settings file and managed settings are scanned;
- missing, unreadable, malformed, non-object settings and non-object `env`
  members refused;
- first init message absent/wrong, `apiKeySource` absent, and non-`none` source
  refused; a correct init allows tool service;
- two consecutive agent runs with the child environment mutated between them
  produce different verdicts, proving the check is per run;
- the child receives only inherited allowlist keys plus runtime-constructed
  proxy/CA keys, and the assessed options object is the object handed to the
  transport;
- the AST import rule admits exactly the runtime launch module and the agent tool
  roster exposes no environment, settings, credential or raw-process operation.

### Durable-state tests

An integration test begins with a claimed task, open `agent_runs` row,
`agent_sessions` binding and identity lease. Both pre-spawn and init refusal must, in one
transaction:

- finish the run with `stop_reason='refusal'` and no promoted result;
- restore the task to `pending` without increasing attempts;
- release the lease and remove the `agent_sessions` binding;
- append one runtime-authored `startup.refused` event with the exact payload and
  no credential values;
- make an identical second cleanup call a no-op;
- stop the supervisor from launching a second run.

The no-program case asserts structured stderr, non-zero exit and zero SDK
construction. The init-refusal case also asserts that no tool run or receipt was
opened before corroboration.

### Receipt-fence test

The ticket-57 integration test attempts all three bypasses: an allowed receipt
with no tool run, one pointing at an undecided tool run, and one carrying a
fabricated capability. Each must be refused by Postgres and produce no egress.
Only a capability minted by the runtime command for an allowed active tool run
may resolve. The proxy role is also asserted to lack direct `INSERT` on
`receipts`, and the target fixture must never observe `Proxy-Authorization` or
the capability value.

### CI boundary and prior evidence

The CI suite needs no network, SDK installation or credentials. The live probe
and its two endpoint controls remain operator-run version-bump tools. Ticket 31's
throwaway subshells show that eight named vectors reached the existing spawn
shape; they are supporting evidence, not a claim that the final single-interface
and lifecycle tests already ran.

## Out of Scope

- **`create_api_key`.** Ticket 14 found a ninth credential path, beyond the
  seven environment variables plus `apiKeyHelper`, that is a
  network call to Anthropic's API, so no startup assertion can catch it. The
  assertion verifiably returns no violation for it. It is refused at the proxy on
  the `control` lane, and belongs to the topology work.
- **Positive proof that a request billed the subscription.** A clean start proves
  only that no version-bound vector was observed in the inputs this assertion
  inspects at that moment. It does not prove the `Authorization` header on a
  given request. That proof belongs to the single egress receipt.
- **Measuring managed settings.** The assertion scans the managed-settings paths,
  but no such file existed on the probe machine, so that scan is reasoned rather
  than measured. Called out rather than quietly claimed.
- **A full picture of the Vertex vector.** It was cut off at 45 s while still
  querying the GCP metadata service. It never chose a credential, which is enough
  for the verdict and is not a complete characterisation.
- **Supporting any non-subscription auth mode.** There is no configuration under
  which the harness runs on an API key. There is no bypass flag.
- **Re-running the probe in CI.** It needs mitmproxy, a fake upstream and real
  OAuth credentials on the box. It is an operator-run tool for version bumps.
- **OAuth refresh in the credential-free container topology.** Ticket 14 proved
  header injection but left refresh-token body handling open. This assertion
  neither carries the refresh token into the container nor claims to solve that
  topology gap.
- **The egress allowlist.** The probe incidentally recorded the eleven hosts and
  paths one zero-tool turn touches, including a Datadog intake. That feeds ticket
  14, not this spec.

## Further Notes

**Vocabulary.** `CONTEXT.md` previously had no term for either concept, and the
nearest neighbours were both wrong: **Halt** is an operator stop enforced at the
egress door, **Review gate** blocks rendering. This is a standing precondition on
beginning an agent run. **Startup assertion** and **credential vector** are now
glossary entries, chosen because they are what the repo already said: 22 uses of
"startup assertion" across tickets 01, 21 and 31, and 11 of "credential vector".
"Billing vector" survives in prose as a deliberate subset, the vectors that move
billing, as against `ANTHROPIC_BASE_URL` which keeps the credential and moves the
destination.

**ADR relations.** Refusal-as-occurrence-event follows ADR 0002's explicit
carve-out ("a refusal, a resume, a rate limit have no row, so no trigger can fire
for them and the runtime inserts them directly"). The implementation extends the
event catalogue with runtime-authored `startup.refused`; it does not reuse the
LLM-authored `agent.refused`. The durable cleanup transaction and one launch
interface keep the occurrence event coupled to the refusal it describes.

**Map clusters this touches.** Ticket 57 is answered by the receipt capability,
not by claiming that one current call site is structural. Ticket 58's shape
("standing checks assert less than their registration claims") is answered by
the exact fixture-set, blind-spot, lifecycle and bypass tests, so each registered
claim has a leg that can go red.

**Everything here is version-bound.** SDK 0.2.132 driving bundled CLI 2.1.224,
Python 3.14.6. Auth resolution is undocumented internal behaviour. The design
assumes it will change, which is why phase 1 exists and why the probe is kept
runnable even though it is throwaway.

**Ticket 31 is supporting evidence, not completion.** The walking skeleton
asserted all eight named startup vectors in throwaway subshells and observed
`apiKeySource=none` on every live init. It did not exercise the final
single-interface contract, target container credential placement, structured
effects, durable refusal transaction or sanitised CI manifest; the tests above
own those claims.
