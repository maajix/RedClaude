"""Reference startup assertion for the subscription-only constraint. Ticket 21.

PROTOTYPE - throwaway, but this is the shape the harness should carry.

Every rule here is one the probe measured on this exact runtime; nothing is
inferred from reading the CLI. See README.md for the evidence table.

Three phases, because no single one covers every vector:

1. ``assert_runtime_known``  - the resolution order is undocumented internal
   behaviour, so an untested SDK/CLI pair fails closed rather than being
   trusted.
2. ``assert_environment``    - the process env and every settings file that
   will actually load. This is the only phase that catches
   ANTHROPIC_AUTH_TOKEN and the three cloud-provider switches, which the
   runtime's own report does not name.
3. ``assert_init_message``   - the CLI's ``apiKeySource`` on the init message,
   checked once per session. Catches a key or helper the harness did not know
   about (a settings file it did not write), and nothing else.
"""

import json
import os
import pathlib

# Measured: each of these, set to a non-empty value, takes the inference call
# off the subscription. The first three replace the credential on the wire;
# the last three move the request off api.anthropic.com entirely.
BILLING_ENV_VARS = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
    "CLAUDE_CODE_USE_FOUNDRY",
)

# Not a billing vector: measured to send the live OAuth bearer token to
# whatever host it names. Same assertion, different reason.
EXFIL_ENV_VARS = ("ANTHROPIC_BASE_URL",)

WATCHED_ENV_VARS = BILLING_ENV_VARS + EXFIL_ENV_VARS

# (claude-agent-sdk, bundled CLI). Extend only after re-running probe.py.
KNOWN_RUNTIMES = {("0.2.132", "2.1.224")}

# Loaded by the CLI outside setting_sources control, so scanned unconditionally.
MANAGED_SETTINGS = (
    pathlib.Path("/etc/claude-code/managed-settings.json"),
    pathlib.Path("/Library/Application Support/ClaudeCode/managed-settings.json"),
)


class SubscriptionViolation(RuntimeError):
    """The runtime would not have billed the subscription."""


def assert_runtime_known(sdk_version: str, cli_version: str) -> None:
    if (sdk_version, cli_version) not in KNOWN_RUNTIMES:
        raise SubscriptionViolation(
            f"untested runtime: SDK {sdk_version} / CLI {cli_version}. "
            f"Auth resolution is undocumented internal behaviour; re-run the "
            f"ticket-21 probe against this pair before trusting it."
        )


def settings_files_that_load(
    cwd: str | os.PathLike, setting_sources: list[str] | None, settings_path: str | None
) -> list[pathlib.Path]:
    """The settings files the CLI will actually read, given the SDK options.

    Measured: with ``setting_sources=[]`` a project ``.claude/settings.json``
    carrying an apiKeyHelper is ignored, and a path passed as ``settings=`` is
    honoured anyway - it is a separate, higher-priority layer.
    """
    cwd = pathlib.Path(cwd)
    sources = ["user", "project", "local"] if setting_sources is None else setting_sources
    candidates = list(MANAGED_SETTINGS)
    if "user" in sources:
        candidates.append(pathlib.Path.home() / ".claude/settings.json")
    if "project" in sources:
        candidates.append(cwd / ".claude/settings.json")
    if "local" in sources:
        candidates.append(cwd / ".claude/settings.local.json")
    if settings_path:
        candidates.append(pathlib.Path(settings_path))
    return [path for path in candidates if path.exists()]


def _settings_violations(path: pathlib.Path) -> list[str]:
    try:
        body = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        # A settings file that cannot be read cannot be cleared either.
        return [f"{path}: unreadable ({exc})"]
    if not isinstance(body, dict):
        return [f"{path}: not an object"]

    found = []
    if body.get("apiKeyHelper"):
        found.append(f"{path}: apiKeyHelper")
    # Measured: a settings env block sets the variable for the CLI process, so
    # it reaches auth resolution exactly like a shell export.
    for name, value in (body.get("env") or {}).items():
        if name in WATCHED_ENV_VARS and value != "":
            found.append(f"{path}: env.{name}")
    return found


def assert_environment(
    env: dict[str, str] | None = None,
    cwd: str | os.PathLike = ".",
    setting_sources: list[str] | None = None,
    settings_path: str | None = None,
) -> None:
    env = os.environ if env is None else env

    # Measured: an empty value is treated as unset - the run stayed on OAuth -
    # so this tests truthiness, not presence.
    violations = [f"env {name}" for name in WATCHED_ENV_VARS if env.get(name)]
    for path in settings_files_that_load(cwd, setting_sources, settings_path):
        violations.extend(_settings_violations(path))

    if violations:
        raise SubscriptionViolation(
            "subscription-only constraint violated: " + ", ".join(violations)
        )


def assert_init_message(init_data: dict) -> None:
    """Second opinion from the runtime itself, on the init system message.

    Coverage is partial by measurement: ``apiKeySource`` names the source of
    the ``x-api-key`` header only. It reports "none" while ANTHROPIC_AUTH_TOKEN
    is billing, and "none" for the three cloud switches. It is a supplement to
    assert_environment, never a replacement.
    """
    source = init_data.get("apiKeySource")
    if source is None:
        raise SubscriptionViolation(
            "init message carries no apiKeySource: this CLI does not report the "
            "auth source, so the environment check cannot be corroborated"
        )
    if source != "none":
        raise SubscriptionViolation(f"CLI resolved an API key: apiKeySource={source!r}")
