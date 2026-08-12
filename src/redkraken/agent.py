"""The one door an Agent run is started through.

`agent_run` is the whole external surface of the Agent runtime. Everything the
child runs with -- the boundary it starts in, the directory it works in, the
settings document that loads, the executable that is spawned -- is decided here
and nowhere else, because the alternative is a caller that validates one
description of a launch and then starts a different one.

The startup assertion is why the split between this module and `_launch` looks
the way it does. `assess` is pure and takes the options value by duck typing,
so the rules can be exercised without an SDK, a credential or a process; the
child then hands the *same* options object it was assessed with to the
transport. Two values would be two configurations, and the second one would be
the one that ran.

There is one launch mechanism, and it is `isolation.run`: the child is a
process in a container attached to one internal network whose only peer is the
runtime's proxy. That is what makes the environment a positive list rather than
a filtered copy -- nothing about the operator's machine is in the child's
filesystem to be inherited in the first place -- and it is what makes "no
direct path to a target" a property of the network rather than a request made
of a cooperative client through proxy variables.

Nothing here is durable. A refusal raised by this module is an exception and a
non-zero child status; closing the Agent run, returning its Task and emitting
the occurrence Event belong to ticket 17, which owns the transaction.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from redkraken import _startup, isolation


#: The module the child process runs as. Named rather than pathed, so a
#: checkout and an installed wheel start the same code. The interpreter that
#: runs it is `isolation.INTERPRETER`, because which interpreter exists is a
#: fact about the image and not about this module.
CHILD = "redkraken._launch"

#: What the child exits with when the startup assertion refused. `78` is
#: `EX_CONFIG`: the launch was not attempted because its configuration was
#: unusable, which is exactly what a refusal says.
REFUSED = 78

#: Where a refusal can happen, in the order the phases run. `pre_spawn` is
#: everything decidable before the SDK transport exists; `init` is the one
#: question only the running CLI can answer.
PHASES = ("pre_spawn", "init")

#: Settings the CLI loads whatever `setting_sources` says, so they are read
#: whether or not this runtime asked for them. Both platform locations are
#: inspected on every run; a machine that has neither contributes nothing.
MANAGED_SETTINGS = (
    Path("/etc/claude-code/managed-settings.json"),
    Path("/Library/Application Support/ClaudeCode/managed-settings.json"),
)

#: The one settings document a child may load, in the one directory the runtime
#: owns. A settings file anywhere else is refused rather than ignored: ignoring
#: it would mean the assertion had read a document the CLI had not.
SETTINGS = "settings.json"

#: And what the runtime writes in it. Empty on purpose -- the file exists to be
#: the only answer to "which settings loaded", not to configure anything.
SETTINGS_DOCUMENT: dict[str, dict] = {"env": {}}

#: The permission bits on everything the runtime creates for one launch.
PRIVATE = 0o700

#: How long a child may run before the supervisor stops waiting.
TIMEOUT = 900.0

#: How many turns a child may take when a caller does not say. Small, because
#: nothing above this ticket yet decides a budget, and a default that ran long
#: would be a budget chosen by omission.
MAX_TURNS = 6

#: How much of a failed child's output is quoted back in the error that reports
#: it. A bound on the diagnostic, not on what the child produced.
DIAGNOSTIC = 1500

#: The name of the runtime's own MCP server, and the one tool it serves. Named
#: here rather than in `_launch` because the assertion checks them: a launch is
#: contained partly by what it may call, so the roster is a field `assess` reads
#: and not a detail of the module that builds the server.
SERVER = "rk2"
SERVER_VERSION = "0.1.0"
READY = "ready"
TOOL = f"mcp__{SERVER}__{READY}"

#: How the child answers permission questions. `bypassPermissions` is the
#: contained value here rather than the wide one: there is no human attached to
#: an Agent run, so a prompt is a hang, and what the child may do is decided by
#: the empty built-in tool list and the one-tool roster above rather than by
#: answering questions about tools it does not have.
PERMISSION_MODE = "bypassPermissions"

#: What the init message must report. `none` is the CLI's own word for "no key
#: was resolved", which on a subscription-authenticated run is the only answer
#: that corroborates the pre-spawn assertion.
EXPECTED_KEY_SOURCE = "none"

#: The vocabulary of a refusal that is not a credential vector. Each one names
#: something the runtime could not verify rather than something it measured, so
#: they carry no vector and the effect `unverifiable`.
UNMEASURED_RUNTIME = "unmeasured_runtime"
INVALID_LAUNCH = "invalid_launch"
SETTINGS_UNREADABLE = "settings_unreadable"
AUTH_SOURCE_UNEXPECTED = "auth_source_unexpected"
INIT_UNCORROBORATED = "init_uncorroborated"
UNVERIFIABLE = "unverifiable"


class StartupRefusal(RuntimeError):
    """The runtime would not start, or would not keep, this Agent run.

    Carries records rather than prose because the diagnostics an operator sees
    must name the variable, the file and the measured effect without ever
    carrying the value: a refusal that printed what it found would be a refusal
    that leaked the credential it refused.
    """

    def __init__(
        self,
        violations: Sequence[Mapping[str, object]],
        phase: str = "pre_spawn",
        sdk_version: str | None = None,
        cli_version: str | None = None,
    ) -> None:
        self.violations = tuple(dict(violation) for violation in violations)
        self.phase = phase
        self.sdk_version = sdk_version
        self.cli_version = cli_version
        if phase not in PHASES or not self.violations:
            raise ValueError("a startup refusal needs a known phase and at least one violation")
        if any(set(violation) != _startup.VIOLATION_KEYS for violation in self.violations):
            raise ValueError("a startup refusal violation is a code, vector, source and effect")
        super().__init__(
            f"startup refused in {phase}: "
            + json.dumps(self.violations, sort_keys=True, separators=(",", ":"))
        )

    def as_dict(self) -> dict:
        return {
            "phase": self.phase,
            "sdk_version": self.sdk_version,
            "cli_version": self.cli_version,
            "violations": [dict(violation) for violation in self.violations],
        }


@dataclass(frozen=True, slots=True)
class AgentRunRequest:
    """One Agent run, described completely enough to be started.

    `objective` is the whole of what the child is told to do, and that is all
    ticket 16 needs it to be: the compiled mission packet -- scope, budget,
    identity leases, allowed skills, stop conditions -- is ticket 18's, and it
    arrives here as more fields rather than a different door.

    `container` is required rather than optional, and it is the whole of what
    the child can reach: the network it is attached to, the proxy that is the
    only peer on it, the root it is told to trust, and the three directories
    that are mounted into it. A request that could omit it would be a request
    that could start a child on the supervisor's own machine, with the
    supervisor's own home and a direct route to any target it can name.

    `model` and `max_turns` keep the SDK's own spelling: they set one option
    each and are not translated on the way, so a reader can check them against
    the SDK's documentation rather than against this file.
    """

    agent_run_id: str
    objective: str
    container: isolation.AgentContainer
    model: str | None = None
    max_turns: int = MAX_TURNS
    timeout: float = TIMEOUT


@dataclass(frozen=True, slots=True)
class AgentRunResult:
    """What one child reported having done. Raw, and true of nothing yet.

    `tool_ready` is a count and not a flag: the criterion is that the tool
    surface opens exactly once, and a flag cannot tell one opening from three.
    `api_key_source` is what the CLI reported rather than what the runtime
    required, for the same reason -- both are evidence, and evidence is what
    Promotion consumes.
    """

    agent_run_id: str
    sdk_version: str | None
    cli_version: str | None
    api_key_source: str
    tool_ready: int
    tools_served: tuple[str, ...]
    answers: int
    stop_reason: str | None
    text: str

    def as_dict(self) -> dict:
        return {
            "agent_run_id": self.agent_run_id,
            "sdk_version": self.sdk_version,
            "cli_version": self.cli_version,
            "api_key_source": self.api_key_source,
            "tool_ready": self.tool_ready,
            "tools_served": list(self.tools_served),
            "answers": self.answers,
            "stop_reason": self.stop_reason,
            "text": self.text,
        }


def agent_run(request: AgentRunRequest) -> AgentRunResult:
    """Start one isolated Agent child and return what it reported.

    The only external launch interface. It describes the run, starts the child
    that asserts and then uses it, and translates a refused child back into the
    refusal it raised. It does not decide what the run should do, and it does
    not write state.

    The launch directory is not made here. The filesystem the child works in is
    the container's, not this process's, so the runtime states where the
    directory goes and the child creates it there -- which is also the only way
    the directory the assertion reads can be the directory the CLI is given.
    """
    job = {
        "agent_run_id": request.agent_run_id,
        "objective": request.objective,
        "model": request.model,
        "max_turns": request.max_turns,
        "workspace": isolation.WORKSPACE,
    }
    return _spawn(request, job)


def launch_directory(workspace: Path | str, agent_run_id: str) -> Path:
    """The runtime-owned directory this run works in, made private.

    The identifier is one path component and is checked to be one. A run
    identifier that could contain a separator would be a run that chooses where
    the runtime writes, and the settings document the assertion trusts lives in
    exactly this directory.
    """
    root = Path(workspace).resolve()
    launch = (root / agent_run_id).resolve()
    if launch.parent != root or launch == root:
        raise ValueError("an agent run identifier must be one path component")
    launch.mkdir(parents=True, exist_ok=True)
    launch.chmod(PRIVATE)
    return launch


def write_settings(launch: Path) -> Path:
    """Put the one settings document the child may load where it may load it."""
    settings = launch / SETTINGS
    settings.write_text(json.dumps(SETTINGS_DOCUMENT), encoding="utf-8")
    settings.chmod(0o600)
    return settings


def assess(
    options: object,
    environment: Mapping[str, str],
    runtime: Mapping[str, object],
    *,
    launch_dir: Path | str,
    managed_settings: Sequence[Path] = MANAGED_SETTINGS,
) -> tuple[dict, ...]:
    """Everything about this launch that can be decided before it happens.

    Takes the options value by duck typing so that the rules are reachable
    without the SDK installed, and so that the object the child assesses is the
    object the child then runs. Returns every violation it can see rather than
    the first, because an operator fixing one vector should be told about the
    other three in the same breath.

    `managed_settings` is a parameter so that the negative outcomes stay
    reachable from tests without writing to `/etc` on the machine running them.
    A launch supplies none: the CLI reads exactly the locations the default
    names, and a caller choosing them would be choosing what the assertion sees.
    """
    launch = Path(launch_dir).resolve()
    configuration: list[dict] = []

    unmeasured = _runtime_violations(options, runtime)
    configuration.extend(unmeasured)
    if not any(violation["code"] == UNMEASURED_RUNTIME for violation in unmeasured):
        # Skipped rather than reported as failures on an unmeasured runtime.
        # Every one of those checks is a statement about what a field of *this*
        # SDK version does, and on a version this harness has not measured the
        # honest answer is that the options value was not interpreted at all.
        # The environment and the settings files are read either way: they are
        # facts about the machine, and an operator fixing the runtime pair
        # should learn about their exported key in the same breath.
        configuration.extend(_option_violations(options, launch))
    settings, settings_violations = _settings_documents(options, launch, managed_settings)
    configuration.extend(settings_violations)

    if not isinstance(environment, Mapping):
        configuration.append(_violation(INVALID_LAUNCH, "launch:environment"))
        environment = {}
    try:
        credentials = _startup.evaluate_inputs(
            {
                "environment": dict(environment),
                "settings": settings,
                "setting_sources": [],
            }
        )["violations"]
    except _startup.ManifestError:
        credentials = []
        configuration.append(_violation(INVALID_LAUNCH, "launch:environment"))

    configuration.sort(key=lambda item: (item["code"], item["source"]))
    return tuple(credentials + configuration)


def corroboration(api_key_source: object) -> tuple[dict, ...]:
    """What the init message has to say, and the refusal when it does not.

    The one question the pre-spawn phase cannot answer. Everything before this
    is a statement about the inputs; this is the CLI reporting which credential
    it actually resolved, and a source this runtime did not expect means a key
    reached it by a path the measured matrix does not name.
    """
    if api_key_source == EXPECTED_KEY_SOURCE:
        return ()
    return (_violation(AUTH_SOURCE_UNEXPECTED, "init:apiKeySource"),)


def uncorroborated(reason: str) -> tuple[dict, ...]:
    """The refusal for a child that never gave the runtime an init to read.

    Kept apart from `corroboration` because they are different findings. That
    one says the CLI resolved a credential this runtime did not expect; this
    one says the CLI produced work before the runtime had assessed it, or ended
    without ever announcing itself -- in both cases nothing was measured, so
    there is no key source to report.
    """
    return (_violation(INIT_UNCORROBORATED, f"init:{reason}"),)


def _violation(code: str, source: str) -> dict:
    """One refusal that names a thing the runtime could not verify."""
    return {"code": code, "vector": None, "source": source, "effect": UNVERIFIABLE}


def _runtime_violations(options: object, runtime: Mapping[str, object]) -> list[dict]:
    """The SDK, the CLI it bundles, and the executable that will actually run.

    One violation covers all three, because they are one fact: this is not a
    runtime pair the credential matrix was measured against, so nothing below
    can be relied on. A missing executable counts as an unmeasured runtime for
    the same reason -- the version a package declares is not evidence about a
    file that is not there.
    """
    pair = (runtime.get("sdk_version"), runtime.get("cli_version"))
    executable = bundled_executable(runtime)
    if pair != _startup.KNOWN_RUNTIME or executable is None:
        return [_violation(UNMEASURED_RUNTIME, "runtime:sdk-cli")]
    if getattr(options, "cli_path", None) != str(executable):
        # Not a runtime violation but the same failure it prevents: an options
        # value that does not name the measured executable is one the SDK would
        # resolve from `PATH`.
        return [_violation(INVALID_LAUNCH, "launch:cli_path")]
    return []


def bundled_executable(runtime: Mapping[str, object]) -> Path | None:
    """The bundled CLI this launch would run, or nothing if there is not one."""
    declared = runtime.get("cli_path")
    if declared is None:
        return None
    try:
        executable = Path(str(declared)).resolve()
    except (OSError, TypeError, ValueError):
        return None
    if not executable.is_file() or not os.access(executable, os.X_OK):
        return None
    return executable


def _option_violations(options: object, launch: Path) -> list[dict]:
    """The fields of the options value that decide what the child can reach.

    Each one is a containment property rather than a preference: an SDK `env`
    that is not empty can add a watched variable after it was inspected, a
    setting source that is not empty loads the operator's own files, a sandbox
    merges settings this runtime did not write, a working directory that is not
    the runtime's own is a directory the runtime does not own, and a built-in
    tool list that is not empty is a network path that does not pass the door.

    The last three are what the child may call, and they are assessed together
    because they only mean anything together. `bypassPermissions` is safe here
    exactly and only while the roster is the runtime's own one-tool server: the
    permission mode decides whether a call is questioned, and these two decide
    that there is nothing to question.
    """
    served = getattr(options, "mcp_servers", None)
    checks = {
        "env": getattr(options, "env", None) == {},
        "setting_sources": getattr(options, "setting_sources", None) == [],
        "sandbox": getattr(options, "sandbox", "unset") is None,
        "cwd": getattr(options, "cwd", None) == str(launch) and launch.is_dir(),
        "builtin_tools": getattr(options, "tools", None) == [],
        "permission_mode": getattr(options, "permission_mode", None) == PERMISSION_MODE,
        "allowed_tools": getattr(options, "allowed_tools", None) == [TOOL],
        "mcp_servers": isinstance(served, Mapping) and set(served) == {SERVER},
    }
    return [
        _violation(INVALID_LAUNCH, f"launch:{field}")
        for field, holds in checks.items()
        if not holds
    ]


def _settings_documents(
    options: object, launch: Path, managed_settings: Sequence[Path]
) -> tuple[list[dict], list[dict]]:
    """Every settings document that will load, and what was wrong with reading it.

    The managed locations are read unconditionally because the CLI reads them
    unconditionally. The explicit one is read only when it is the canonical
    file in the runtime's own directory: a settings path anywhere else is
    refused, and refused before it is parsed, so a document the runtime does
    not own never contributes a symbolic setting.
    """
    documents: list[dict] = []
    violations: list[dict] = []
    loading = [
        (path, "managed") for path in map(Path, managed_settings) if path.exists()
    ]

    declared = getattr(options, "settings", None)
    if declared is not None:
        try:
            path = Path(str(declared))
            owned = path.is_absolute() and path.resolve() == launch / SETTINGS
        except (OSError, TypeError, ValueError):
            owned = False
        if owned:
            loading.append((path.resolve(), "explicit"))
        else:
            # Refused, and the managed locations still read. They load whatever
            # this one turned out to be, so an operator with a stray settings
            # path and an exported key in `/etc` learns about both at once.
            violations.append(_violation(INVALID_LAUNCH, "launch:settings"))

    for path, kind in loading:
        document, refusal = _read_settings(path, kind)
        (violations if refusal else documents).append(refusal or document)
    return documents, violations


def _read_settings(path: Path, kind: str) -> tuple[dict | None, dict | None]:
    """One settings file as a symbolic document, or the refusal to read it.

    A file that cannot be read and a file that is not the shape the evaluator
    understands are the same refusal: either way this runtime cannot say what
    the CLI will load from it, and a launch it cannot describe is one it does
    not start.
    """
    source = f"settings:{kind}:{path}#document"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, _violation(SETTINGS_UNREADABLE, source)
    if not isinstance(document, dict) or not isinstance(document.get("env", {}), dict):
        return None, _violation(SETTINGS_UNREADABLE, source)
    return {"kind": kind, "path": str(path), "document": document}, None


def _spawn(request: AgentRunRequest, job: Mapping[str, object]) -> AgentRunResult:
    """Run the child in its boundary, and read back its result or its refusal.

    `-P` because the child's import path is the runtime's statement about which
    application and which SDK this launch is measured against, and a working
    directory on that path is a second answer to a question that has one.
    """
    child = isolation.run(
        request.container,
        (isolation.INTERPRETER, "-P", "-m", CHILD),
        stdin=json.dumps(job),
        timeout=request.timeout,
    )
    refusal = _refusal(child.stderr)
    if refusal is not None:
        raise refusal
    result = _last_document(child.stdout)
    if result is None:
        raise RuntimeError(
            f"the agent child exited {child.returncode} without a result: "
            + (child.stderr or child.stdout or "")[-DIAGNOSTIC:]
        )
    return AgentRunResult(
        agent_run_id=request.agent_run_id,
        sdk_version=result.get("sdk_version"),
        cli_version=result.get("cli_version"),
        api_key_source=str(result.get("api_key_source")),
        tool_ready=int(result.get("tool_ready") or 0),
        tools_served=tuple(result.get("tools_served") or ()),
        answers=int(result.get("answers") or 0),
        stop_reason=result.get("stop_reason"),
        text=str(result.get("text") or ""),
    )


def _refusal(stderr: str) -> StartupRefusal | None:
    """The refusal a child reported, if what it reported is a well-formed one.

    A malformed refusal record is not turned into a refusal. It would be a
    refusal this runtime invented from a broken child rather than one the
    assertion made, and the caller is better served by the unclassified error
    `_spawn` raises when there is no result either.
    """
    document = _last_document(stderr)
    if document is None or set(document) != {"startup_refusal"}:
        return None
    reported = document["startup_refusal"]
    if not isinstance(reported, Mapping):
        return None
    try:
        return StartupRefusal(
            reported.get("violations") or (),
            reported.get("phase") or "",
            reported.get("sdk_version"),
            reported.get("cli_version"),
        )
    except (TypeError, ValueError):
        return None


def _last_document(stream: str) -> dict | None:
    """The last JSON object on a stream, ignoring everything that is not one."""
    for line in reversed((stream or "").strip().splitlines()):
        if not line.startswith("{"):
            continue
        try:
            document = json.loads(line)
        except ValueError:
            continue
        if isinstance(document, dict):
            return document
    return None
