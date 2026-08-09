# sdk-auth-probe

PROTOTYPE - throwaway. Answers ticket 21, *Probe the SDK's live auth resolution
before the startup assertion ships* (historical ticket 21).

**Question.** The subscription-only constraint rests on an inference: that the
CLI resolves a credential vector *before* it ever considers the OAuth token, so
a stray `ANTHROPIC_API_KEY` silently moves billing off the Max subscription.
That was read off a disassembly, never watched happen. Which credential does a
*running* process actually put on the wire, for each vector, on this runtime?

**Runtime the answers are bound to.** `claude-agent-sdk` 0.2.132 driving its
own bundled CLI **2.1.224** (`claude_agent_sdk/_bundled/claude`) - not the 2.1.220
on `PATH`; `_find_cli()` prefers the bundled binary. Python 3.14.6,
mitmproxy 12.2.3. Auth resolution is undocumented internal behaviour, so every
number below is version-bound and the assertion fails closed on a runtime it
does not recognise.

## Run it

```sh
./run.sh            # 17 vectors + fd control + guard verification, all offline
./run.sh live       # the two real-endpoint controls (bills one Haiku turn)
```

No working API key is used anywhere. Every credential the probe sets is a
fabricated `sk-ant-...PROBE...` string that cannot authenticate.

The checked-in CI replay is narrower and needs neither the SDK, network nor
credentials:

```sh
python3 auth_resolution.py
python3 -m unittest -v test_auth_resolution.py
```

After an operator reruns the probe for a version bump, emit a new immutable,
sanitised manifest instead of replacing the previous version's file:

```sh
probe_commit="$(git rev-parse HEAD)"
python3 normalise_manifest.py \
  --probe-commit "$probe_commit" \
  --batch out/results-all.json out/capture-all.jsonl \
  > evidence/auth-resolution-sdk-NEW-cli-NEW.json
```

`--batch RESULTS CAPTURE` is repeatable for a probe run split into explicit
batches. The normaliser refuses missing or duplicate cases and prints only
symbolic inputs plus normalised wire facts; raw captures stay operator-retained.

## Instrument

`mitmdump` runs as a **fake upstream**, not a passthrough: an addon answers
every request itself with a canned Anthropic SSE response, so nothing egresses
and nothing bills. The CLI is pointed at it with `HTTPS_PROXY` plus the run CA
in `SSL_CERT_FILE`/`NODE_EXTRA_CA_CERTS`.

This shape, rather than `ANTHROPIC_BASE_URL` rewriting, because auth resolution
has a first-party-endpoint branch - overriding the base URL would change the
answer being measured. (`base_url` is then measured as its own vector.)

Each vector gets a **distinct** fake secret. Requests are recorded as
`sha256[:12]` of each credential header, never the value, and the fingerprint
table includes the real OAuth token, so every request can be attributed without
a secret ever reaching a log. Each vector runs in its own process off a scrubbed
env (`PATH HOME USER LOGNAME LANG TMPDIR XDG_RUNTIME_DIR` only), so nothing
leaks in from the operator's shell.

## What the wire showed

Credential on the inference call, `POST /v1/messages`. `oauth` = the real
subscription bearer token; anything else = off the subscription.

| vector | what was set | `apiKeySource` | credential on `/v1/messages` | outcome |
| --- | --- | --- | --- | --- |
| `baseline` | nothing | `none` | `Authorization: Bearer oauth` | PROBE_OK |
| `api_key` | `ANTHROPIC_API_KEY` | `ANTHROPIC_API_KEY` | `x-api-key: env_api_key`, **no oauth** | PROBE_OK |
| `auth_token` | `ANTHROPIC_AUTH_TOKEN` | `none` | `Authorization: Bearer env_auth_token` | PROBE_OK |
| `api_key_empty` | `ANTHROPIC_API_KEY=""` | `none` | `Authorization: Bearer oauth` | PROBE_OK |
| `base_url` | `ANTHROPIC_BASE_URL=http://127.0.0.1:8899` | `none` | `Authorization: Bearer oauth` **to 127.0.0.1** | PROBE_OK |
| `api_key_helper` | `settings.apiKeyHelper` (flag layer) | `apiKeyHelper` | `Authorization: Bearer helper_key` + `x-api-key: helper_key` | PROBE_OK |
| `fd` (via SDK) | `CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR` | `none` | *no inference call* | `Not logged in · Please run /login` |
| `fd_direct` (CLI spawn, `pass_fds`) | same | `ANTHROPIC_API_KEY` | `x-api-key: fd_key` | PROBE_OK |
| `bedrock` | `CLAUDE_CODE_USE_BEDROCK=1` | `none` | *no request at all* | `API Error: Could not load credentials from any providers` |
| `vertex` | `CLAUDE_CODE_USE_VERTEX=1` | `none` | *none; hit 169.254.169.254 + metadata.google.internal* | timed out at 45s on the GCP metadata service |
| `foundry` | `CLAUDE_CODE_USE_FOUNDRY=1` | `none` | *no request at all* | ``API Error: Must provide one of the `baseURL` or `resource` arguments, or the ANTHROPIC_FOUNDRY_RESOURCE environment variable`` |
| `settings_env_key` | `settings.env.ANTHROPIC_API_KEY` | `ANTHROPIC_API_KEY` | `x-api-key: settings_env_key` | PROBE_OK |
| `proj_helper_isolated` | `cwd/.claude/settings.json` helper, `setting_sources=[]` | `none` | `Authorization: Bearer oauth` | PROBE_OK |
| `proj_helper_loaded` | same file, `setting_sources=["project"]` | `apiKeyHelper` | `proj_helper_key` in both headers | PROBE_OK |
| `prec_key_vs_token` | key + token | `ANTHROPIC_API_KEY` | `Authorization: Bearer env_auth_token` + `x-api-key: env_api_key` | PROBE_OK |
| `prec_key_vs_helper` | key + helper | `ANTHROPIC_API_KEY` | `Authorization: Bearer helper_key` + `x-api-key: env_api_key` | PROBE_OK |
| `prec_token_vs_helper` | token + helper | `apiKeyHelper` | `Authorization: Bearer env_auth_token` + `x-api-key: helper_key` | PROBE_OK |
| `prec_key_vs_bedrock` | key + bedrock | `ANTHROPIC_API_KEY` | *no request at all* | bedrock error - the provider switch owns routing |

Two controls against the real `api.anthropic.com` (`live_control.py`, Haiku):

| run | result |
| --- | --- |
| `live_baseline` | `PROBE_OK`, `apiKeySource: none`, `total_cost_usd 0.000525` - a plain `query()` does complete on the subscription |
| `live_api_key` | `Failed to authenticate. API Error: 401 API key is invalid.`, `is_error: true`, `apiKeySource: ANTHROPIC_API_KEY` - the unusable key was **chosen over** a perfectly good OAuth token, and the CLI never fell back |

`live_api_key` also emitted, on stderr:

> `⚠ claude.ai connectors are disabled because ANTHROPIC_API_KEY or another auth source is set and takes precedence over your claude.ai login · Unset it to load your organization's connectors`

## Answers

- **The inference holds.** Every credential vector is resolved ahead of the
  OAuth token, and there is no fallback: an unusable key fails the call rather
  than deferring to the subscription (`live_api_key`, `fd`).
- **Six vectors, plus two the ticket did not list.** A settings file's `env`
  block is a seventh carrier - scanning settings for `apiKeyHelper` alone is not
  enough. `ANTHROPIC_BASE_URL` is not a billing vector but sends the **live
  OAuth bearer token to whatever host it names**; measured, the token went to
  `127.0.0.1:8899`. Same assertion, different reason.
- **Empty is unset.** `ANTHROPIC_API_KEY=""` stayed on OAuth, so the assertion
  tests truthiness, not presence - and blanking an inherited value is a valid
  way to neutralise it.
- **Precedence never rescues the subscription.** `Authorization` goes to
  `ANTHROPIC_AUTH_TOKEN`, else `apiKeyHelper`, else OAuth; `x-api-key` goes to
  `ANTHROPIC_API_KEY`, else `apiKeyHelper`; a cloud switch overrides routing
  entirely. In **every** mixed case the OAuth token was absent from the
  inference request. The assertion therefore does not need to model precedence:
  any vector set at all means the call is not on the subscription.
- **Isolation works, and is not sufficient.** `setting_sources=[]` kept a
  project `.claude/settings.json` with an `apiKeyHelper` out of the auth path,
  while a path passed as `settings=` was honoured anyway - it is a separate,
  higher-priority layer. Isolation covers files the harness does not write; it
  does nothing about the env.
- **The fd vector is real, but unreachable through the SDK.** anyio/asyncio
  closes every inherited fd above stderr, so the CLI found the variable set,
  could not read the fd, and refused to start rather than falling back to OAuth
  (`Not logged in`). Spawned directly with `pass_fds`, the same fd authenticated
  normally (`fd_direct.py`). So through the SDK it is a denial-of-service
  vector; at CLI level it is a billing vector. Assert against it either way.

### Corrections to ticket 01

1. `_find_cli()` prefers the SDK's **bundled** CLI over `PATH`. Ticket 01's
   version pin should name the bundled binary - here 2.1.224 while `PATH` had
   2.1.220.
2. "No API reports the resolved auth source back to Python" is wrong. The init
   `SystemMessage` carries **`apiKeySource`**. It is genuinely useful but
   **incomplete**: it names the source of the `x-api-key` header only, so it
   reports `none` while `ANTHROPIC_AUTH_TOKEN` is billing, and `none` for all
   three cloud switches, the fd vector, and `ANTHROPIC_BASE_URL` (verified in
   `verify_guard.py`).

## The assertion this produces

`subscription_guard.py` - three phases, because no single one covers every
vector:

1. `assert_runtime_known(sdk, cli)` - refuse an SDK/CLI pair this probe has not
   measured.
2. `assert_environment(env, cwd, setting_sources, settings_path)` - the seven
   variables, truthy-valued, plus `apiKeyHelper` and a watched `env` key in
   every settings file that will actually load. The only phase that catches
   `ANTHROPIC_AUTH_TOKEN` and the cloud switches.
3. `assert_init_message(init_data)` - `apiKeySource == "none"`, once per
   session. Catches a key or helper the harness did not know about; a
   supplement, never a replacement.

`verify_guard.py` replays every vector definition past the guard and compares
its verdict to what the wire showed - guard refuses iff the inference call did
not go out on the subscription:

```
OK: guard verdict matches the wire on every measured vector      (17/17)
runtime gate: SDK 0.2.132 / CLI 2.1.224 accepted, CLI 9.9.9 refused
```

It also asserts the six vectors `apiKeySource` alone would miss, so nobody
later mistakes phase 3 for the whole check.

## Limits

- Everything is bound to SDK 0.2.132 / CLI 2.1.224. Re-run on any bump.
- Only phases 1-3 are code the harness would ship. Positive proof that a given
  request billed the subscription still requires looking at the actual
  `Authorization` header - which the single-egress-path design makes possible
  later, and which this probe does at the proxy.
- Managed settings (`/etc/claude-code/managed-settings.json`) are scanned by the
  guard but were **not** measured - no such file exists on this machine.
- `vertex` was cut off at 45s while it was still asking the GCP metadata
  service; it never chose a credential, which is enough for the assertion but is
  not a full picture of that vector.

## Incidental: what one turn actually talks to

From the `baseline` capture - relevant to the container/network-topology work,
where the egress allowlist has to be written down:

`api.anthropic.com` with the OAuth token: `POST /v1/messages` (x2),
`GET /api/claude_cli/bootstrap`, `GET /v1/mcp_servers`,
`GET /api/claude_code_penguin_mode`, `GET /api/oauth/account/settings`,
`GET /api/claude_code_grove`, `POST /api/eval/sdk-<id>`,
`POST /api/event_logging/v2/batch`; unauthenticated
`GET /mcp-registry/v0/servers`; and `POST /api/v2/logs` to
**`http-intake.logs.us5.datadoghq.com`**. Eleven requests for one one-turn,
zero-tool session.

## Files

| file | what |
| --- | --- |
| `probe.py` | the matrix: vector table, fake-upstream lifecycle, attribution |
| `runner.py` | one SDK `query()` per process, dumps every message |
| `fake_upstream.py` | mitmproxy addon: records fingerprints, answers everything locally |
| `fd_direct.py` | the fd vector spawned straight at the CLI, bypassing the SDK |
| `live_control.py` | the two real-endpoint controls |
| `subscription_guard.py` | the reference startup assertion |
| `verify_guard.py` | runs the assertion against every measured vector |
| `out/results-*.json` | per-batch SDK-side results (`results-all.json` is the first 12 vectors; the rest are their own batches) |
| `out/capture-*.jsonl` | per-request wire records, keyed by run marker |
| `out/live-results.json`, `out/fd-direct.json` | the two controls |
