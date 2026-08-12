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

A refusal is durable, and it is final. `agent_run` closes the Agent run,
returns its Task to the queue with its attempt given back, releases what the
run held and emits the one occurrence Event before the refusal reaches the
caller. Then it latches: a process that has refused starts no further Agent
run. The latch is process state on purpose -- what a refusal measured is a fact
about the machine this process is running on, so the thing that clears it is a
restart, which measures the machine again.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from redkraken import _startup, isolation, packet as packet_module, pg, roster
from redkraken.outcome import STARTUP_REFUSED, Ledger, Report, Violation, report


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

#: The hook events a launch must register, and what each one is for. Three of
#: the four exist so the fourth can be trusted: `PreToolUse` is the decision,
#: `SubagentStart` is what turns an agent id into an attribution rather than a
#: claim, and the two completions are what give an admitted delegation back. A
#: launch missing any of them is a launch whose gate counts up and never down.
GATE_EVENTS = ("PreToolUse", "SubagentStart", "PostToolUse", "PostToolUseFailure")

#: How much of a failed child's output is quoted back in the error that reports
#: it. A bound on the diagnostic, not on what the child produced.
DIAGNOSTIC = 1500

#: The name of the runtime's own MCP server, and the one tool it serves. Named
#: here rather than in `_launch` because the assertion checks them: a launch is
#: contained partly by what it may call, so what this server offers is a field
#: `assess` reads and not a detail of the module that builds the server.
SERVER = "rk2"
SERVER_VERSION = "0.1.0"

#: The two groups `_launch` builds handlers for: the bounded state reads and
#: the one outbound proposal. Named as groups rather than as tools so that
#: moving a tool between groups in the roster moves it here too -- a served
#: tool that had quietly changed authority class would otherwise be a hole the
#: compile cannot see.
SERVED_GROUPS = ("state.read", "state.propose")

#: Everything this launch actually serves. The roster says what a role may
#: call; this says what exists to be called, and the allowlist a launch carries
#: is the intersection. It is derived rather than written because two hand-kept
#: lists is how a tool comes to be granted and not served.
SERVED = tuple(
    sorted(name for group in SERVED_GROUPS for name in roster.TOOL_GROUPS[group])
)

#: The bare tool names, which is what the MCP server registers. The SDK
#: prefixes `mcp__<server>__` on the way out, so these two lists are the same
#: list seen from either side of that prefix.
BARE = {name: name.removeprefix(f"mcp__{SERVER}__") for name in SERVED}

#: How the child answers permission questions. `bypassPermissions` is the
#: contained value here rather than the wide one: there is no human attached to
#: an Agent run, so a prompt is a hang. It is safe because it is not what
#: decides anything: the permission mode says whether a call is questioned, and
#: `roster.Gate` says whether it happens. The gate's denial is the one decision
#: this mode cannot overrule, which is why the allowlist lives in the roster.
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

#: How one refusal is made durable: the Program this session speaks for, and the
#: one call that closes the run. Everything the cleanup does -- the run, its
#: Task, the session binding, the Identity Leases and the Event -- happens
#: inside that call, so the cleanup is one statement and therefore one
#: transaction, and a repeat of it is one statement that finds nothing open.
BIND = "SELECT set_config('rk2.program_id', $1, false)"
CLOSE = "SELECT close_startup_refusal($1::uuid, $2, $3, $4, $5::jsonb)"


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


class Latched(StartupRefusal):
    """The refusal this process already made, raised at a run it will not start.

    A subclass rather than an error of its own because it is not another
    finding: the violations are the ones that were measured, and a caller that
    knows what to do with a refusal knows what to do with this one. What it adds
    is which attempt it refused -- this one was never spawned, because the
    process that would have spawned it has already been told what it would find.
    """

    @classmethod
    def of(cls, refusal: StartupRefusal) -> "Latched":
        """The same measurement, raised again at the run it now refuses."""
        return cls(refusal.violations, refusal.phase, refusal.sdk_version, refusal.cli_version)


#: The refusal this process made, and the reason it will attempt no other run.
#: Module state, because what it remembers belongs to the process rather than to
#: any one request: a second run started from a process that has already
#: measured an exported key would be measured against the same key.
_LATCH: StartupRefusal | None = None


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

    `role` is required and is not a hint. It selects one row of `roster.ROLES`,
    and that row is the whole of what the child is: its model, its effort, its
    turn ceiling, the built-in tools it is offered, the served tools it may
    call, the Skills it may execute and how many of it may run at once. There
    is deliberately no way for a caller to set any of those individually --
    a request that could raise a worker's turn ceiling or hand it one more tool
    would be a second roster, and the one thing a roster cannot survive is a
    second one.

    `program_id` is what makes a refusal recordable, and it is optional for the
    one case where it cannot be given: every Event belongs to a Program, so a
    run started before any Program exists is a run whose refusal can only be
    raised and rendered.

    `packet` is everything the child may read, compiled before it starts. It is
    a field on the request rather than something the child fetches because the
    child cannot fetch: the container's one network reaches the capability
    proxy and nothing else, so a bounded read served inside it can only be
    served from what came in with the job. A request with no packet starts a
    child whose state reads all answer "nothing", which is the honest answer
    for a run the runtime compiled no state for.
    """

    agent_run_id: str
    objective: str
    container: isolation.AgentContainer
    role: str
    program_id: str | None = None
    packet: packet_module.Packet | None = None
    timeout: float = TIMEOUT


@dataclass(frozen=True, slots=True)
class AgentRunResult:
    """What one child reported having done. Raw, and true of nothing yet.

    `tool_ready` is a count and not a flag: the criterion is that the tool
    surface opens exactly once, and a flag cannot tell one opening from three.
    `api_key_source` is what the CLI reported rather than what the runtime
    required, for the same reason -- both are evidence, and evidence is what
    Promotion consumes.

    `denials` is the same argument applied to the gate. A run whose evidence
    said only which tools were served would not distinguish a model that never
    asked for a forbidden one from a model that asked and was refused, and the
    second is the more interesting run of the two.

    `mission_result` is the raw submission, or nothing where the child never
    made one. Raw is the operative word: it has been through a closed schema
    and through the gate, and through nothing else. What its Observations cite
    is checked on the runtime's own connection, by `proposal.stage`, because
    the check reads canonical rows and the child cannot. Ticket 20 owns that
    call: it is the ticket that runs one Task from a compiled packet to a
    promoted Observation, and this pair of fields is the seam it writes to.

    `mission_attempts` is how many times the child called the tool, which is
    not how many results it got to make. One result and three attempts is a
    model that argued with its own output and was refused twice, and that is
    worth being able to see from the row rather than only from the transcript.
    """

    agent_run_id: str
    role: str
    sdk_version: str | None
    cli_version: str | None
    api_key_source: str
    tool_ready: int
    tools_served: tuple[str, ...]
    denials: tuple[dict, ...]
    answers: int
    stop_reason: str | None
    text: str
    mission_result: Mapping[str, object] | None = None
    mission_attempts: int = 0

    def as_dict(self) -> dict:
        return {
            "agent_run_id": self.agent_run_id,
            "role": self.role,
            "sdk_version": self.sdk_version,
            "cli_version": self.cli_version,
            "api_key_source": self.api_key_source,
            "tool_ready": self.tool_ready,
            "tools_served": list(self.tools_served),
            "denials": [dict(denial) for denial in self.denials],
            "answers": self.answers,
            "stop_reason": self.stop_reason,
            "text": self.text,
            "mission_result": (
                None if self.mission_result is None else dict(self.mission_result)
            ),
            "mission_attempts": self.mission_attempts,
        }


def agent_run(
    request: AgentRunRequest, connection: pg.Connection | None = None
) -> AgentRunResult:
    """Start one isolated Agent child and return what it reported.

    The only external launch interface. It describes the run, starts the child
    that asserts and then uses it, and turns a refused child into the whole of
    what that refusal means: the Agent run closed, its Task back in the queue
    with its attempt returned, what it held released, one `startup.refused`
    Event, and a process that will start no further run. It does not decide
    what the run should do, and the only state it writes is that cleanup.

    `connection` and `request.program_id` are optional together, because a
    refusal can happen where there is nothing to record it against -- a run
    started before any Program exists. When either is absent the refusal is
    raised and nothing is written; when both are given they are checked before
    the child is started, because a run whose refusal could not be recorded is
    a run that should not have been started.

    The launch directory is not made here. The filesystem the child works in is
    the container's, not this process's, so the runtime states where the
    directory goes and the child creates it there -- which is also the only way
    the directory the assertion reads can be the directory the CLI is given.
    """
    global _LATCH
    program_id = _recording_program(request, connection)
    try:
        if _LATCH is not None:
            raise Latched.of(_LATCH)
        job = {
            "agent_run_id": request.agent_run_id,
            "objective": request.objective,
            "role": request.role,
            "workspace": isolation.WORKSPACE,
            "packet": (request.packet or packet_module.Packet()).as_dict(),
        }
        return _spawn(request, job)
    except StartupRefusal as refusal:
        # Latched first. The cleanup talks to a database, and a database that
        # is unreachable must not be the reason this process goes on to start
        # the run it has just refused.
        _LATCH = _LATCH or refusal
        if program_id is not None and connection is not None:
            try:
                close_refusal(connection, program_id, request.agent_run_id, refusal)
            except Exception as failure:
                # A cleanup that could not run is a row left open, which the
                # lease expiry is what reclaims. What must not happen is the
                # database's error replacing the refusal on the way out: the
                # caller would be told the run failed rather than that this
                # machine may not start one, and would exit as something else.
                raise refusal from failure
        raise


def close_refusal(
    connection: pg.Connection,
    program_id: str,
    agent_run_id: str,
    refusal: StartupRefusal,
) -> bool:
    """Make one refusal durable, and say whether this call was the one that did.

    Closes the Agent run, returns its Task to pending with the attempt it never
    spent, releases its Task and Identity Leases, unbinds its session and emits
    the one redacted `startup.refused` Event. `False` says there was nothing
    open to close -- a run that already finished, or one this Program does not
    own -- which is what a repeat of the cleanup finds, and why repeating it
    changes nothing rather than emitting a second Event.
    """
    connection.execute(BIND, (program_id,))
    closed = connection.execute(
        CLOSE,
        (
            agent_run_id,
            refusal.phase,
            refusal.sdk_version,
            refusal.cli_version,
            json.dumps(list(refusal.violations)),
        ),
    ).scalar()
    return bool(closed)


def diagnostics(refusal: StartupRefusal) -> Report:
    """One refusal as the outcome an operator reads and a caller exits on.

    Each record becomes a violation naming where the vector was found -- the
    variable, the settings file and key, the launch field, the init report --
    and the effect that was measured for it, and never the value: a diagnostic
    that printed what it found would publish the credential it refused.

    The report is the supervisor's rather than a command's, because the
    supervisor is what refuses; the command that prints it belongs to whatever
    later asks for an Agent run. What it fixes here is the status: a refused
    startup exits `EXIT_STARTUP_REFUSED`, so a caller can tell it from a run
    that started and went wrong.
    """
    ledger = Ledger()
    ledger.refuse(
        "startup_assertion",
        f"refused in {refusal.phase} by {len(refusal.violations)} vector(s)",
        [
            Violation(
                code=STARTUP_REFUSED,
                source=str(record["source"]),
                detail=f"{record['code']}, measured effect {record['effect']}",
            )
            for record in refusal.violations
        ],
    )
    return report(
        "agent run",
        ledger,
        phase=refusal.phase,
        sdk_version=refusal.sdk_version,
        cli_version=refusal.cli_version,
    )


def _recording_program(request: AgentRunRequest, connection: pg.Connection | None) -> str | None:
    """The Program a refusal of this run would be recorded against, if any.

    Asked before the child starts rather than in the refusal path. An
    identifier the cleanup could not use is a failure that would otherwise
    arrive at the one moment there is durable state to clean up and no way left
    to clean it.
    """
    if connection is None or request.program_id is None:
        return None
    for field, value in (
        ("program_id", request.program_id),
        ("agent_run_id", request.agent_run_id),
    ):
        try:
            uuid.UUID(str(value))
        except ValueError:
            raise ValueError(
                f"an agent run recorded against a Program needs a {field} that is a UUID"
            ) from None
    return request.program_id


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
    role: str,
    managed_settings: Sequence[Path] | None = None,
) -> tuple[dict, ...]:
    """Everything about this launch that can be decided before it happens.

    Takes the options value by duck typing so that the rules are reachable
    without the SDK installed, and so that the object the child assesses is the
    object the child then runs. Returns every violation it can see rather than
    the first, because an operator fixing one vector should be told about the
    other three in the same breath.

    `role` is what most of the option checks are checks *against*: this launch
    is contained by being one row of the roster, so the question is not whether
    the turn ceiling is reasonable but whether it is that role's. A role this
    roster does not have -- or one that runs no model, which this door cannot
    start -- is itself the refusal, and the option checks are skipped after it
    for the same reason they are skipped on an unmeasured runtime: they are
    statements about what a particular role's launch should look like, and
    there is no such role to compare against.

    `managed_settings` is a parameter so that the negative outcomes stay
    reachable from tests without writing to `/etc` on the machine running them.
    A launch supplies none: the CLI reads exactly the locations `MANAGED_SETTINGS`
    names, and a caller choosing them would be choosing what the assertion sees.
    Nothing rather than that tuple is the default, so the locations are the ones
    this module holds in the process that is asserting rather than the ones it
    held when some other process imported it.
    """
    launch = Path(launch_dir).resolve()
    managed = MANAGED_SETTINGS if managed_settings is None else managed_settings
    configuration: list[dict] = []

    unmeasured = _runtime_violations(options, runtime)
    configuration.extend(unmeasured)
    # A renderer is a role of this harness and not a session of this SDK. It
    # has no model, no turn and no tool, so there is nothing here for it to be
    # assessed as, and a door that started one would be a door that made it an
    # agent.
    launchable = role in roster.ROLES and not roster.ROLES[role].rendered
    if not launchable:
        configuration.append(_violation(INVALID_LAUNCH, "launch:role"))
    elif not any(violation["code"] == UNMEASURED_RUNTIME for violation in unmeasured):
        # Skipped rather than reported as failures on an unmeasured runtime.
        # Every one of those checks is a statement about what a field of *this*
        # SDK version does, and on a version this harness has not measured the
        # honest answer is that the options value was not interpreted at all.
        # The environment and the settings files are read either way: they are
        # facts about the machine, and an operator fixing the runtime pair
        # should learn about their exported key in the same breath.
        configuration.extend(_option_violations(options, launch, role))
    settings, settings_violations = _settings_documents(options, launch, managed)
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
    if options is None:
        # There is no options value to name an executable, and whatever made
        # the launch undescribable has already said so. Adding a second
        # violation here would report one fault as two.
        return []
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


def _option_violations(options: object, launch: Path, role: str) -> list[dict]:
    """The fields of the options value that decide what the child can reach.

    Each one is a containment property rather than a preference: an SDK `env`
    that is not empty can add a watched variable after it was inspected, a
    setting source that is not empty loads the operator's own files, a sandbox
    merges settings this runtime did not write, and a working directory that is
    not the runtime's own is a directory the runtime does not own.

    The rest are the roster, restated as a question about this options value.
    They are not asserted because a mismatch would be dangerous by itself --
    a turn ceiling of 60 on the orchestrator is merely wrong -- but because a
    launch that differs from the roster in any field is a launch some other
    thing decided, and the roster's whole claim is that nothing else does. The
    two tool lists are the sharp end: `tools` is what the model is shown and
    `allowed_tools` is what it may call unprompted, and neither may be wider
    than the compiled grants, because the permission mode is
    `bypassPermissions` and offering a tool under that mode is running it.

    Widening either one still would not widen the role's authority -- the gate
    denies from the roster and not from these lists -- but it would spend a
    turn on a call that was always going to be refused, and it would put a tool
    in a frame that is supposed to be the role's real surface.
    """
    served = getattr(options, "mcp_servers", None)
    expected = roster.ROLES[role]
    checks = {
        "env": getattr(options, "env", None) == {},
        "setting_sources": getattr(options, "setting_sources", None) == [],
        "sandbox": getattr(options, "sandbox", "unset") is None,
        "cwd": getattr(options, "cwd", None) == str(launch) and launch.is_dir(),
        "builtin_tools": getattr(options, "tools", None) == expected.visible_tools,
        "permission_mode": getattr(options, "permission_mode", None) == PERMISSION_MODE,
        "allowed_tools": getattr(options, "allowed_tools", None)
        == expected.allowed_tools(SERVED),
        "mcp_servers": isinstance(served, Mapping) and set(served) == {SERVER},
        "model": getattr(options, "model", "unset") == expected.model,
        "effort": getattr(options, "effort", "unset") == expected.effort,
        "max_turns": getattr(options, "max_turns", None) == expected.max_turns,
        "hooks": _gated(options),
    }
    return [
        _violation(INVALID_LAUNCH, f"launch:{field}")
        for field, holds in checks.items()
        if not holds
    ]


def _gated(options: object) -> bool:
    """Whether this options value carries the gate on every event it needs.

    Checked structurally rather than by identity. What the assertion can see is
    that each event has at least one matcher that matches every tool and has a
    callback behind it; that the callback is the roster's is a fact about the
    module that built the value, and `_launch` is the only module that can.
    """
    hooks = getattr(options, "hooks", None)
    if not isinstance(hooks, Mapping) or set(hooks) != set(GATE_EVENTS):
        return False
    return all(
        any(
            getattr(matcher, "matcher", "unset") is None and getattr(matcher, "hooks", ())
            for matcher in hooks[event]
        )
        for event in GATE_EVENTS
    )


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
        role=request.role,
        sdk_version=result.get("sdk_version"),
        cli_version=result.get("cli_version"),
        api_key_source=str(result.get("api_key_source")),
        tool_ready=int(result.get("tool_ready") or 0),
        tools_served=tuple(result.get("tools_served") or ()),
        denials=tuple(
            dict(denial)
            for denial in (result.get("denials") or ())
            if isinstance(denial, Mapping)
        ),
        answers=int(result.get("answers") or 0),
        stop_reason=result.get("stop_reason"),
        text=str(result.get("text") or ""),
        mission_result=(
            dict(mission) if isinstance(mission := result.get("mission_result"), Mapping) else None
        ),
        mission_attempts=int(result.get("mission_attempts") or 0),
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
